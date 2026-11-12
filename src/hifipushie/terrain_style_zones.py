"""Seasons and snow; zones on the map (style fields, layer edges, rock scale); rock shape (styles, stack form,
variants, pillow carve). Part of the terrain styles (terrain_style.py has the overview)."""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from . import terrain_style
from .terrain_style import _hsv, _srgb_lin, resolve

# ------------------------------------------------------------------------------------------------ seasons, snow
def season_colours(st: dict, layer: str, colour_srgb) -> dict:
    """{season: {"color" sRGB, "tint_linear": colour / the summer colour (multiply the texture by it)}}."""
    out = {}
    base = np.array(colour_srgb, float)
    for se in terrain_style.SEASONS:
        S = ((st.get("seasons") or {}).get(se) or {})
        m = S.get(layer) or S.get("*") or {}
        if layer in (S.get("skip") or []):
            m = {}
        mix = m.get("mix", base)
        if m.get("mix") is not None and m.get("turn", True):  # (the season's colour in the style's palette too)
            cc = st.get("colour") or {}
            mix = _hsv(mix, cc.get("saturation", 1.0), cc.get("value", 1.0))
        c = base * (1 - float(m.get("amount", 0))) + np.array(mix, float) * float(m.get("amount", 0))
        tint = _srgb_lin(c) / np.maximum(_srgb_lin(base), 1e-6)
        out[se] = {"color": [round(float(x), 4) for x in c], "tint_linear": [round(float(x), 4) for x in tint]}
    return out


def snow_numbers(st: dict) -> dict:
    """Snow for the engine's own shader, in the plants' form (veg_export.snow_numbers) plus the ground's own: a snow
    line by height and the share that lies on steep ground."""
    S = st.get("snow") or {}
    c = float(S.get("coverage", 0.8))
    col = S.get("color", [0.93, 0.95, 0.98])
    return {"color": [float(x) for x in col], "color_linear": [round(float(x), 4) for x in _srgb_lin(col)],
            "shadow_color": S.get("shadow_color"), "coverage": c,
            "by_normal": {"from": round(1.0 - 1.3 * c, 3), "to": round(1.25 - 1.3 * c, 3),
                          "formula": "snow = saturate((N.up + breakup * (noise(p / breakup_m) - 0.5) - from) / (to - "
                                     "from)) x height_term; albedo = mix(albedo, color, snow); roughness = max(roughness, "
                                     "0.6 snow); N = the macro normal (the baked map), so snow lies on what the big forms "
                                     "hold"},
            "breakup": float(S.get("breakup", 0.5)), "breakup_m": float(S.get("breakup_m", 6.0)),
            "edge": S.get("edge", "soft"),
            "by_height": S.get("by_height") or {"from_m": None, "to_m": None,
                                                "how": "a snow line: snow x smoothstep(from_m, to_m, world z); null = "
                                                       "no line (snow down to the sea)"},
            "layers": S.get("layers") or {"wet_rock": 0.0, "sand": 0.6}}


# ------------------------------------------------------------------------------------------------ zones on the map
def style_fields(T, styles: list[dict]) -> dict:
    """Per style on the terrain grid: the signed distance to its zone's edge (m, + inside) and its weight with its
    band; "realistic" = what is left. {"sd": {name: grid}, "w": {name: grid}, "order": [names]}."""
    from .terrain_design import region
    if not styles:
        return {"sd": {}, "w": {}, "order": ["realistic"]}
    masks = {}
    for s in styles:
        try:
            masks[s["name"]] = np.max([region(T, z) for z in s["zones"]], axis=0) >= 0.5
        except ValueError as e:
            raise ValueError(f"styles.{s['name']}: {e}") from None
    # a partition: a later style wins where zones overlap, realistic is what no zone holds
    order = [s["name"] for s in styles]
    taken = np.zeros_like(next(iter(masks.values())))
    for nm in reversed(order):
        masks[nm] = masks[nm] & ~taken
        taken = taken | masks[nm]
    bands = {s["name"]: s["band"] for s in styles}
    if "realistic" not in masks:
        masks["realistic"] = ~taken
        bands["realistic"] = max(bands.values())
        order = order + ["realistic"]
    else:
        masks["realistic"] = masks["realistic"] | ~taken
    sd, raw = {}, {}
    for nm in order:
        m = masks[nm]
        if m.all() or not m.any():
            d = np.full(m.shape, terrain_style.SD_RANGE if m.all() else -terrain_style.SD_RANGE)
        else:
            d = (ndimage.distance_transform_edt(m) - ndimage.distance_transform_edt(~m)) * T.cell
            d = d - 0.5 * T.cell * np.sign(d)  # (the edge half-way between cells)
        sd[nm] = np.clip(d, -terrain_style.SD_RANGE, terrain_style.SD_RANGE)
        e = np.clip(sd[nm] / max(bands[nm], 1e-6) + 0.5, 0, 1)
        raw[nm] = e * e * (3 - 2 * e)
    tot = np.maximum(sum(raw.values()), 1e-9)
    w = {nm: raw[nm] / tot for nm in order}
    return {"sd": sd, "w": w, "order": order}


def layer_edge(st: dict) -> dict | None:
    """A style's layer-edge numbers ({"height", "depth"}: how far the layers' height maps push where two layers meet,
    and how wide the crossing is, in weight units), or None (layers cross-fade by weight)."""
    E = st.get("layer_edge")
    if not E:
        return None
    return {"height": float(E.get("height", 0.4)), "depth": float(E.get("depth", 0.1))}


def edge_weights(W, Hn, edge):
    """The recipe's layer-edge re-weighting: W (k, ...) layer weights, Hn (k, ...) their height maps -1..1."""
    if not edge:
        return W
    S = W + edge["height"] * Hn * np.minimum(1.0, 4 * W)
    m = S.max(0, keepdims=True)
    w = np.maximum(S - (m - edge["depth"]), 0.0)
    return w / np.maximum(w.sum(0, keepdims=True), 1e-9)


def rock_scale(T) -> tuple[np.ndarray, np.ndarray]:
    """Per terrain cell, how big the rock there is: (face height m, half-thickness m in plan). Face height = the visible
    relief (water at its level) within ~40 m, averaged over the steep cells within ~8 m; thickness = how far the
    piece standing up (over the middle of the relief within ~100 m) reaches inside, its largest within ~15 m. A sea stack or a
    thin fin reads a few metres thick, a headland tens. What a layer's `fade_small` ops fade on (the engine reads it
    from styles/rock_scale.png)."""
    H = np.asarray(T.H, float)
    water = getattr(T, "water", None)
    vis = H if water is None else np.where(np.isnan(water), H, np.maximum(H, np.nan_to_num(water, nan=-1e9)))
    vb = ndimage.gaussian_filter(vis, 1.0)
    odd = lambda m: max(3, int(round(m / T.cell)) | 1)
    w = odd(40.0)
    top, foot = ndimage.maximum_filter(vb, w), ndimage.minimum_filter(vb, w)
    rel = top - foot
    face = (T._slope() > 40).astype(float)
    sig = max(1.0, 8.0 / T.cell)
    g = ndimage.gaussian_filter(face, sig)
    Hf = np.where(g > 1e-3, ndimage.gaussian_filter(rel * face, sig) / np.maximum(g, 1e-3), 0.0)
    w2 = odd(100.0)  # (the piece standing up, judged over a wider window: a 40 m one lost a plateau's inland part)
    top2, foot2 = ndimage.maximum_filter(vb, w2), ndimage.minimum_filter(vb, w2)
    up = (vb > 0.5 * (top2 + foot2)) & (top2 - foot2 > 2.0)
    thick = ndimage.distance_transform_edt(up) * T.cell
    thick = ndimage.maximum_filter(thick, odd(30.0))
    # sea stacks are solid columns in the 3D tiles (terrain_volumes.stacks): the heightfield holds only a slim core, so
    # round each one its own size is written in (half-thickness = its radius, its height over the sea)
    st = (getattr(T, "sea", None) or {}).get("stacks") if isinstance(getattr(T, "sea", None), dict) else None
    if st:
        from .terrain_mesh import STACK
        for a in st:
            r = STACK["radius"] * float(a["radius"])
            m = np.hypot(T.X - a["xy"][0], T.Y - a["xy"][1]) < r + 3.0 * T.cell
            thick[m] = r
            Hf[m] = np.maximum(Hf[m], float(a["height"]))
    return Hf, thick


def rock_styles(T) -> list[dict]:
    """The styles whose sheet shapes the rock (`rock` with any of relief / pillow / soften_m / fallen / micro), each
    {"name", "w": weight grid on the terrain's cells (the zone partition with the rock's band, 0..1), "rock": the
    numbers}. [] when no style shapes rock: the field is then exactly the unstyled one."""
    styles = resolve(T.spec)
    shaped = []
    for s in styles:
        R = s["sheet"].get("rock") or {}
        bad = set(R) - terrain_style.ROCK_KEYS
        if bad:
            raise ValueError(f"style {s['name']}: rock keys {sorted(bad)} unknown ({', '.join(sorted(terrain_style.ROCK_KEYS))})")
        if set(R) - {"kind", "band_m", "stack"}:  # (a sea stack's form is read by stack_form, not by the field)
            shaped.append(s)
    if not shaped:
        return []
    geo = [{**s, "band": float((s["sheet"].get("rock") or {}).get("band_m", terrain_style.ROCK_BAND))} for s in styles]
    F = style_fields(T, geo)
    return [{"name": s["name"], "w": np.ascontiguousarray(F["w"][s["name"]], float), "rock": s["sheet"]["rock"]}
            for s in shaped]


def stack_form(T, xy) -> dict:
    """The sea stack form overrides (terrain_stack.FORM keys) at a stack's centre: the `rock.stack` of the style whose
    zone weighs over half there (a stack is one rock: it takes one style's form whole), else {} (realistic)."""
    styles = resolve(T.spec)
    if not any((s["sheet"].get("rock") or {}).get("stack") for s in styles):
        return {}
    geo = [{**s, "band": float((s["sheet"].get("rock") or {}).get("band_m", terrain_style.ROCK_BAND))} for s in styles]
    F = style_fields(T, geo)
    iy = int(np.clip(np.rint((xy[1] - T.ys[0]) / T.cell), 0, len(T.ys) - 1))
    ix = int(np.clip(np.rint((xy[0] - T.xs[0]) / T.cell), 0, len(T.xs) - 1))
    for s in styles:
        if float(F["w"][s["name"]][iy, ix]) > 0.5:
            return dict((s["sheet"].get("rock") or {}).get("stack") or {})
    return {}


def rock_variant(rock: dict, relief: dict | None) -> dict:
    """The realistic rock numbers with a style's `relief` multipliers: facets, bedding, size (x), blocks (false =
    none)."""
    out = dict(rock)
    for k in ("facets", "bedding", "size"):
        if relief and k in relief:
            out[k] = rock[k] * float(relief[k])
    if relief and relief.get("blocks") is False:
        out["blocks"] = None
    return out


def _hash3(c, seed):
    """Per integer cell (n, 3) three uniform numbers in [0, 1) (a splitmix-style hash: the same everywhere)."""
    c = np.asarray(c, np.int64).astype(np.uint64)
    h = (c[:, 0] * np.uint64(0x9E3779B97F4A7C15)) ^ (c[:, 1] * np.uint64(0xC2B2AE3D27D4EB4F)) ^ \
        (c[:, 2] * np.uint64(0x165667B19E3779F9)) ^ np.uint64(seed * 0x27D4EB2F165667C5 & 0xFFFFFFFFFFFFFFFF)
    out = []
    for k in range(3):
        h = h ^ (h >> np.uint64(31))
        h = h * np.uint64(0x7FB5D329728EA185)
        h = h ^ (h >> np.uint64(27))
        h = h * np.uint64(0x81DADEF4BC2DD44D)
        h = h ^ (h >> np.uint64(33))
        out.append((h >> np.uint64(11)).astype(np.float64) / float(1 << 53))
        h = h + np.uint64(0x9E3779B97F4A7C15)
    return np.stack(out, -1)


def pillow_carve(p, size=3.0, depth=0.8, round_=0.4, seed=11, stretch=1.0):
    """Pillow-rounded rock as a field offset (+ carves): 3D cells about `size` m across (a jittered lattice; `stretch`
    x taller than wide, so the seams run mostly up the face and few cut under a cushion), each a cushion; grooves
    `depth` m deep where two cells meet, rounding over `round_` x size (smoothstep^2: no crease at the groove's bottom,
    flat-ish cushion tops). Pointwise and deterministic (tiles agree)."""
    p = np.asarray(p, float)
    q = p / (float(size) * np.array([1.0, 1.0, float(stretch)]))
    base = np.floor(q).astype(np.int64)
    f1 = np.full(len(p), np.inf)
    f2 = np.full(len(p), np.inf)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = base + np.array([dx, dy, dz])
                s = c + 0.1 + 0.8 * _hash3(c, seed)
                d = np.sqrt(((q - s) ** 2).sum(1))
                f2 = np.where(d < f1, f1, np.minimum(f2, d))
                f1 = np.minimum(f1, d)
    e = np.clip((f2 - f1) / max(float(round_), 1e-3), 0, 1)
    sm = e * e * (3 - 2 * e)
    return float(depth) * (1 - sm) ** 2


def soften_height(H, cell, styles) -> np.ndarray:
    """The ground grid with each style's `soften_m` Gaussian applied in its zone (blobby: rounded lips and forms)."""
    out = H
    for s in styles:
        sg = float(s["rock"].get("soften_m", 0) or 0)
        if sg <= 0:
            continue
        sm = ndimage.gaussian_filter(H, sg / cell)
        out = out + s["w"] * (sm - H)
    return out
