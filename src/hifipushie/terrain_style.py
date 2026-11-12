"""Terrain styles: the ground and rock drawn in the plants' art styles (blobby, anime, ... realistic), zone by zone on one
terrain, with the transition between styles left to the engine's shader.

Spec: `"styles": {"blobby": "dumpling_downs", "anime": ["east", "knoll_hill"], "cartoon": {"in": zone, "band": m,
"sheet": {...overrides}}}` (style -> a zone / any region address / a list of them; everywhere else is "realistic").

A style is a SHEET of numbers over general operations (`terrain_styles/<name>.json`; a sixth style is a new sheet):
- `colour`: the terrain's own layer colours turned by saturation / value (the same keys as the plant styles, so the
  ground's colour steps match the plants'), `layers.<l>.color` overrides one.
- `layers.<l>`: a tileable texture per ground layer (grass, turf, scrub, forest_floor, sand, earth, rock, wet_rock,
  snow) made of ops (`OPS`: blotch, pillow, strokes, bands, ripples, dots, grain, cracks, facets), each giving a tone
  field (-1..1, albedo x (1 + albedo t), warm tint where t > 0 and cool where t < 0) and a height (m); `like` = take
  another layer's ops (its own colour); `scale_m` = the texture's side in metres, `projection` top | triplanar.
- `macro` (share of the baked tile colour's variation kept), `macro_normal` (share of the baked normal's tilt kept),
  `detail` (the realistic tiling detail swatches: on / off / a strength), `overlay` (a style's own small-scale
  multiplier swatch, e.g. anime brush dabs).
- `seasons`: per season per layer {"mix": sRGB, "amount"} (like the plants'), `snow`: numbers for the engine's snow.
- `rock` (shape, stage 3): how the zone's rock is shaped in the tiles' geometry.

What an engine gets (`write`): materials/<style>/<layer>_albedo.png (sRGB) / _normal.png (tangent, glTF: +x east or
along the strike, +y north or up) / _height.png (16-bit, 0.5 = 0, +- height_m), an overlay swatch, styles/
<style>_sd.png (signed distance to the style's zone edge, m) and styles/weights<g>.png (the weights with the default
band), and a manifest section (`manifest`): the styles, their zones and sheets' numbers, per tile the styles reaching
it, seasons and snow, and the recipe. The per-tile baked maps stay style-neutral in meaning: the realistic look.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at terrain_style.NAME: C422). terrain_style_fields: periodic fields: band noise, Worley, the pattern ops
(blotch, pillow, strokes, tufts, bands, ripples, dots, grain, cracks, facets, stones), `texture`, `overlay`.
terrain_style_zones: seasons and snow; zones on the map (style fields, layer edges, rock scale); rock shape (styles,
stack form, variants, pillow carve). terrain_style_files: files: tileable images, the layers and overlay written, the
code key and cache, `write`, `export_styles`. terrain_style_looks: looks: swatch and season sheets, the transition
strip; the game's view of the ground.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
from . import moved

CONTRACT = 5
CONTRACT_LOG = {
    5: "stream beds: three new layers on terrains with running rivers, in every style: `gravel` (cobbles and gravel under "
       "the water and on bars), `silt` (fine sediment in pools and slack margins), `bank` (the bank's damp foot), all "
       "top-projected; they come LAST in the tiles' layer list, so the older layers keep their channels (read each "
       "layer's weights attribute and channel from the manifest: past 8 layers there is a third group, _WEIGHTS2 / "
       "weights map 2; on the island gravel is _WEIGHTS1.a, silt and bank _WEIGHTS2.r / .g); `wet_rock` is present on any terrain "
       "with rivers (bedrock in the bed), sea or not. New texture op `stones`. Nothing changes on a terrain without "
       "rivers",
    4: "every materials/<style>/<layer>_albedo.png (and small.albedo, the plain one) is RGBA: RGB the sRGB albedo as "
       "before, ALPHA the layer's height (linear 8-bit, 0.5 = 0, (a - 0.5) x 2 x height_m metres; the same values as "
       "_height.png at 8 bits), flagged by layers[l].albedo_alpha = \"height\"; _height.png (16-bit) is still written "
       "for older readers. Load the albedo's alpha as data (it is not colour): no packing at runtime",
    3: "styles[].layer_edge {height, depth} (cartoon, anime; null = cross-fade as before): re-weight the layers by their "
       "height maps where they meet (recipe step 1) so layer edges are crisp painted shapes; layers[l].small {albedo, "
       "normal, face_m, thick_m} + maps.rock_scale (RG 8-bit: face height x face_m, half-thickness x thick_m): on "
       "small or thin rock (sea stacks, fins) show the layer's plain texture instead (anime strata fade off them); "
       "cartoon macro 0 and anime 0.15 (flat colour fields), new texture sizes (read size_m, never assume)",
    1: "styles: materials/<style>/<layer>_albedo (sRGB) / _normal / _height (+ _overlay_*), styles/<style>_sd.png and "
       "styles/weights<g>.png, manifest `styles` (list, zones, layers, seasons, snow, tiles, recipe)",
    2: "projection: layers with projection 'top' (grass, turf, scrub, forest_floor, sand, earth, snow) are ALWAYS laid "
       "from the top, also on steep faces (side planes at v = world height turned their tone patches into terraces up "
       "a slope); only projection 'triplanar' layers (rock, wet_rock) use side planes. Triplanar layers carry "
       "`v_jitter_m` (strata wander along the strike, so a band texture doesn't repeat straight up a cliff)",
}
DIR = Path(__file__).parent / "terrain_styles"
STYLE_LAYERS = ("grass", "turf", "scrub", "forest_floor", "sand", "earth", "rock", "wet_rock", "snow", "gravel", "silt",
                "bank")
PX = 1024           # texture side in pixels
BAND = 20.0         # m: the default transition band (centred on the zone's edge)
SD_RANGE = 64.0     # m: the signed distance maps run -SD_RANGE..SD_RANGE
SEASONS = ("spring", "summer", "autumn", "winter")
# a layer's `fade_small` ops (e.g. anime strata) give way to its plain texture on small or thin rock: full where the face
# is over face_m[1] tall AND the rock over thick_m[1] thick (half-thickness in plan), none under the [0]s
SMALL_FADE = {"face_m": [4.0, 12.0], "thick_m": [3.0, 10.0]}
ROCK_SCALE = {"face_m": 64.0, "thick_m": 32.0}  # (the rock_scale map's full range: R and G = value / range)


# ------------------------------------------------------------------------------------------------ sheets
def names() -> list[str]:
    return sorted(p.stem for p in DIR.glob("*.json"))


def merge(a, b):
    """b over a, key by key (dicts merge, anything else replaces; None deletes)."""
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def sheet(name: str, over: dict | None = None) -> dict:
    """A style's sheet: terrain_styles/<name>.json over the base sheet (`_base.json`), then `over`."""
    f = DIR / f"{name}.json"
    if not f.exists():
        raise ValueError(f"no terrain style {name!r} (sheets: {', '.join(n for n in names() if not n.startswith('_'))}; "
                         "a new style is a new sheet in terrain_styles/)")
    base = json.loads((DIR / "_base.json").read_text())
    st = merge(base, json.loads(f.read_text()))
    st = merge(st, over or {})
    st["name"] = name
    return st


def resolve(spec: dict) -> list[dict]:
    """The spec's "styles" as [{"name", "zones": [address...], "band", "sheet"}], in the spec's order (a later style
    wins where zones overlap). Realistic is implicit (everywhere else) unless named."""
    out = []
    for name, v in (spec.get("styles") or {}).items():
        if isinstance(v, dict):
            unknown = set(v) - {"in", "band", "sheet"}
            if unknown:
                raise ValueError(f"styles.{name}: unknown keys {sorted(unknown)} (in, band, sheet)")
            zones, band, over = v.get("in"), float(v.get("band", BAND)), v.get("sheet")
        else:
            zones, band, over = v, BAND, None
        if zones is None:
            raise ValueError(f"styles.{name}: give the zone it covers (\"styles\": {{\"{name}\": \"<zone>\"}})")
        zones = zones if isinstance(zones, list) else [zones]
        out.append({"name": name, "zones": zones, "band": band, "sheet": sheet(name, over)})
    return out


def _srgb_lin(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _lin_srgb(c):
    c = np.clip(np.asarray(c, float), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def _hsv(c, sat=1.0, val=1.0):
    """An sRGB colour with its HSV saturation and value scaled (the plant styles' `colour` numbers)."""
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*[float(x) for x in c])
    r, g, b = colorsys.hsv_to_rgb(h, min(s * sat, 1.0), min(v * val, 1.0))
    return [r, g, b]


def layer_colour(st: dict, layer: str, ref: dict) -> list:
    """The style's mean colour (sRGB) of a layer: its own `color`, else the terrain's reference colour turned by the
    style's (and the layer's) saturation / value."""
    L = layer_sheet(st, layer)
    if L.get("color"):
        return [float(x) for x in L["color"]]
    c = st.get("colour") or {}
    return _hsv(ref[layer]["color"], c.get("saturation", 1.0) * L.get("saturation", 1.0),
                c.get("value", 1.0) * L.get("value", 1.0))


def layer_sheet(st: dict, layer: str) -> dict:
    """A layer's numbers: the sheet's "*" defaults, under the layer it is `like` (if any), under its own."""
    lay = st.get("layers") or {}
    own = lay.get(layer) or {}
    like = own.get("like")
    base = merge(lay.get("*") or {}, lay.get(like) or {}) if like else dict(lay.get("*") or {})
    if like:
        base.pop("color", None)
    return merge(base, {k: v for k, v in own.items() if k != "like"})


# ------------------------------------------------------------------------------------------------ rock shape (geometry)
ROCK_BAND = 10.0  # m: the default band over which one style's rock shape hands over to the next (in the field)
ROCK_KEYS = {"relief", "pillow", "soften_m", "fallen", "micro", "band_m", "kind", "stack", "lip", "build"}

_CODE = None

RECIPE = (
    "Per pixel, for each style s with weight ws (styles/weights<g>.png, or your own band from styles/<s>_sd.png: ws = "
    "smoothstep(-band/2, band/2, sd + ragged noise), normalised so the weights sum to 1; realistic takes the rest) and "
    "each ground layer l with weight wl (the tiles' layer weights: maps/<tile>_weights<g>.png / splats / _WEIGHTS):\n"
    "1. A_s = sum_l wl x texture(materials/<s>/<l>_albedo, uv_l) (RGB sRGB -> linear; its alpha is the height, contract 4), uv_l = world (x, y) / size_m on the "
    "ground (projection top; image +x east, +y north). Layers with projection 'top' are laid from the top EVERYWHERE, "
    "also on steep ground (what artists do: ground is top-down, rock is triplanar; side planes turned soft layers' tone "
    "patches into terraces up a slope). Layers with projection 'triplanar' (rock): top plane + side planes blended by "
    "|n|^4 (side planes: u along the face, v = (world z + v_jitter_m x (2 n(u / 23 m) - 1)) / size_m, n = a smooth 1D "
    "value noise 0..1, so painted strata stay level but wander along the strike and don't repeat straight up a "
    "cliff every size_m). Layer edges: a style with `layer_edge` {height, depth} (contract 3) re-weights its layers "
    "by their height maps before the sum, so where two layers meet the edge is a crisp painted shape, not a soft "
    "cross-fade: h_l = 2 x <l>_height - 1 (-1..1), s_l = wl + height x h_l x min(1, 4 wl), m = max_l s_l, "
    "wl' = max(s_l - (m - depth), 0) / sum (styles without it: wl as is). On small or thin rock (maps.rock_scale: face "
    "height F = R x face_m, half-thickness Th = G x thick_m) a layer with a `small` entry shows its plain texture "
    "instead: k = smoothstep(small.face_m[0], small.face_m[1], F) x smoothstep(small.thick_m[0], small.thick_m[1], "
    "Th), albedo = mix(small.albedo, albedo, k), normal likewise (anime strata fade off sea stacks and fins). "
    "Anti-tiling as the detail recipe: a second sampling "
    "at uv / 1.618 + (0.37, 0.71), CHOSEN between by a smooth noise mask over ~3 x size_m patches (not mixed 50/50); "
    "keep strata textures (projection triplanar on rock) unrotated so the bands stay level.\n"
    "2. R = sum_l wl x layers[l].color_linear of the REALISTIC style (what the baked base colour holds, minus its "
    "variation). albedo_s = A_s x mix(1, baked_base_colour / R, macro_s): realistic (macro 1) is exactly the baked "
    "look with the layer textures as modulation, blobby (macro 0) its own flat colours, others in between.\n"
    "3. Detail: styles with detail > 0 add the realistic tiling detail (manifest detail / ground_detail recipes) x "
    "detail; a style's overlay (materials/<s>/overlay_*) multiplies on top within its fade_m.\n"
    "4. Normal: Nm_s = normalize(mix(N_vertex, N_baked, macro_normal_s)); then RNM-combine the style layers' normals "
    "(sum wl x normal, scaled by normal_strength) onto it.\n"
    "5. Roughness: sum_l wl x layers[l].roughness (the baked ORM.g for realistic). Occlusion: the baked ORM.r (AO "
    "only: no lighting is baked into any style's textures).\n"
    "6. Seasons: albedo x layers[l].seasons[season].tint_linear (per layer, before the sum); snow by `snow` (per style, "
    "as the plants' snow numbers).\n"
    "7. Blend the styles: albedo = sum_s ws albedo_s, normal = normalize(sum_s ws Nm_s), and the same for roughness.")


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("terrain_style_fields", "terrain_style_zones", "terrain_style_files", "terrain_style_looks")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C427)
