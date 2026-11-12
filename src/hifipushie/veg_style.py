"""Vegetation styles: the same grown plant dressed another way (spec `"style": "blobby"` or {"sheet": "blobby",
...overrides}).

A style never touches the growth: the skeleton, height, crown extent and lean are the realistic tree's. It is a SHEET
of ordinary numbers (vegetation_styles/<name>.json, every key overridable in the spec) over a few general operations:

- `wood`: which limbs are drawn (the stoutest `limbs`), how far along them (`reach`), how fat (`radius` x, never
  thinner than `taper_floor` x the limb's base), bends smoothed, ends rounded, bark one flat colour.
- `crown` kind "masses": the twigs' positions are clustered (k-means), each cluster becomes an ellipsoid (its
  principal axes x `spread` + `pad` twig lengths, no semi-axis under 0.75 x `min_feature`), the ellipsoids are joined by a
  smooth union (`blend` m) and meshed (marching cubes on the field, decimated to the budget, vertices put back on the
  field). Closed, no leaves, no alpha. How many masses: the fewest in `masses` [lo, hi] whose silhouette is within
  0.01 IoU of the best (measured against the realistic tree's own silhouette from three sides, at true scale).
- normals: the field's gradient (smooth over each mass and across the blends), mixed `normals` toward the direction
  out of the crown's middle.
- colour: one tone per mass, `tones` steps across the tree by the mass's height (top lighter, a little warmer), as
  COLOR_0 (a multiplier of the material's colour, so season variants only swap the material).
- wind: a mass moves as a whole with the limb it sits on (the limb's branch weight and phase).

What artists do (sources in vegetation_guide.md): blob / low-poly trees are a few smooth-shaded lumps on a trunk;
soft "Ghibli" foliage gets its shading from normals transferred off a rounded proxy hull. Here the proxy IS the
crown (blobby), and later styles put cards on it and take its normals.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at veg_style.NAME: C422). veg_style_wood: wood: the limbs that are drawn, their tubes and field, meshing a
field, capsules. veg_style_crown: crown masses: leaf points, masses and subclumps, the crown's field and mesh;
silhouettes (is it still the same tree?). veg_style_dress: the fit (once per tree and sheet) and `dress`: shell and
cards, big leaves. veg_style_small: small plants (veg_small clumps) in a style: sweeps, slabs, heads, `dress_clump`,
lines, warnings.
"""
from __future__ import annotations

import colorsys
import json
from pathlib import Path

import numpy as np

from . import vegetation
from . import moved

STYLES = Path(__file__).with_name("vegetation_styles")
AZIMUTHS = (0, 60, 120)
AUTUMN = [0.78, 0.56, 0.16]
SEASONS = ("spring", "summer", "autumn", "winter", "snow")
_FIT: dict = {}


def names() -> list[str]:
    return ["realistic"] + sorted(p.stem for p in STYLES.glob("*.json"))


def sheet(spec: dict) -> dict | None:
    """The style's numbers for this spec (the sheet under the spec's own overrides), or None for realistic."""
    st = spec.get("style")
    if not st or st == "realistic":
        return None
    name, over = (st, {}) if isinstance(st, str) else (st.get("sheet", "realistic"), {k: v for k, v in st.items() if k != "sheet"})
    if name == "realistic":
        if over:
            raise ValueError('style overrides need a sheet: {"sheet": "blobby", ...}')
        return None
    p = STYLES / f"{name}.json"
    if not p.exists():
        raise ValueError(f"no vegetation style {name!r}; styles: {names()}")
    base = json.loads(p.read_text())
    for k, v in over.items():
        if k not in base:
            raise ValueError(f"style: unknown key {k!r}; the {name} sheet has {sorted(base)}")
        if isinstance(v, dict):
            bad = set(v) - set(base[k])
            if bad:
                raise ValueError(f"style.{k}: unknown keys {sorted(bad)}; it takes {sorted(base[k])}")
    out = vegetation._merge(base, over)
    con = out.pop("conifer", None)
    if con and conifer(spec):  # the sheet's own numbers for needle trees (tiers, a bare pole), under the spec's overrides
        out = vegetation._merge(vegetation._merge(out, con), {k: v for k, v in over.items() if k != "conifer"})
        out = vegetation._merge(out, over.get("conifer") or {})
    out["name"] = name
    return out


def conifer(spec: dict) -> bool:
    return str((spec.get("leaves") or {}).get("shape", "")).startswith("needle")


def describe(name: str) -> dict:
    return json.loads((STYLES / f"{name}.json").read_text())


# ---------------------------------------------------------------- colour
def styled(rgb, sat: float = 1.0, val: float = 1.0) -> list:
    h, s, v = colorsys.rgb_to_hsv(*[float(c) for c in rgb])
    return [round(c, 4) for c in colorsys.hsv_to_rgb(h, min(s * sat, 1.0), min(v * val, 1.0))]


def lin(c) -> list:
    return [float(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c]


def evergreen(spec: dict) -> bool:
    lf = spec["leaves"]
    return bool(lf.get("evergreen", str(lf.get("shape", "")).startswith("needle")))


def season_color(spec: dict, season: str, st: dict | None = None):
    """The foliage's one colour in a season (sRGB), or None when the plant is bare then. With a style sheet the colour
    goes through its `colour` (saturation, value). spring = `leaves.spring`, else the summer colour mixed toward a
    fresh yellow-green; snow = mixed toward white; autumn = `leaves.autumn` (an evergreen keeps its colour)."""
    lf = spec["leaves"]
    eg = evergreen(spec)
    ss = (st or {}).get("seasons") or {}
    mix = lambda a, b, t: [a[i] * (1 - t) + b[i] * t for i in range(3)]
    if spec.get("plant") == "clump":  # a small plant has its own states through the year (veg_small.SEASONS)
        from . import veg_small
        stt = veg_small.season_state(spec, season)
        if stt is None:
            return None
        c = stt["color"]
        if st:
            co = st.get("colour") or {}
            c = styled(c, co.get("saturation", 1.0), co.get("value", 1.0))
        if season == "snow":
            sn = ss.get("snow") or {"mix": [0.93, 0.95, 0.98], "amount": 0.7}
            c = mix(c, sn["mix"], sn["amount"])
        return [round(float(x), 4) for x in c]
    base = list(lf.get("color", [0.16, 0.3, 0.08]))
    if season in ("winter", "snow", "bare", "dead") and (not eg or season == "dead"):  # (snow = winter + snow laid on it)
        return None
    c = base
    if season == "autumn" and not eg:
        c = list(lf.get("autumn", AUTUMN))
    elif season == "spring":
        sp = ss.get("spring") or {"mix": [0.55, 0.78, 0.25], "amount": 0.45}
        c = list(lf["spring"]) if isinstance(lf.get("spring"), (list, tuple)) else mix(base, sp["mix"], sp["amount"] * (float(sp.get("evergreen", 0.4)) if eg else 1.0))
    if st:
        co = st.get("colour") or {}
        c = styled(c, co.get("saturation", 1.0), co.get("value", 1.0))
    if season == "snow":
        sn = ss.get("snow") or {"mix": [0.93, 0.95, 0.98], "amount": 0.7}
        c = mix(c, sn["mix"], sn["amount"])
    return [round(float(x), 4) for x in c]


def material_color(rgb, st: dict) -> list:
    """The crown material's LINEAR colour factor: the season's colour x the tones' gain, scaled back as a whole when a
    channel would pass 1 (clipped per channel, autumn's orange lost its tone steps and its hue)."""
    c = np.array(lin(rgb)) * color_gain(st)
    return (c / max(1.0, float(c.max()))).tolist()


def srgb(c) -> np.ndarray:
    c = np.clip(np.asarray(c, float), 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


def season_ramp(spec: dict, season: str, st: dict | None):
    """A season that paints the masses' EDGES another colour (sheet `seasons.<season>.tips` = {"color" sRGB, "band"}:
    an evergreen's spring = the fresh shoots at the rims of its tiers, which a one-colour crown can't show): None, or
    a function u -> (n, 3) linear colour x the tones' gain, scaled back as material_color is. u = TEXCOORD_0.x of a
    styled crown (0 at a mass's foot .. 1 at its top: a cone tier's rim is u 0). The export writes it as a ramp
    texture over u in that season's material (factor x texture = this); looks colour the vertices with it."""
    if not st or (st.get("crown") or {}).get("kind", "masses") == "clouds" or spec.get("plant") == "clump":
        return None
    tp = ((st.get("seasons") or {}).get(season) or {}).get("tips")
    base = season_color(spec, season, st)
    if not tp or base is None:
        return None
    co = st.get("colour") or {}
    tip = styled(tp["color"], co.get("saturation", 1.0), co.get("value", 1.0))
    band = tp.get("band", 0.3)  # u under which the edge colour is whole, fading out by `band` (or [whole, gone])
    b0, band = (float(band[0]), float(band[1])) if isinstance(band, (list, tuple)) else (0.0, float(band))
    g = color_gain(st)
    a0, a1 = np.array(lin(base)) * g, np.array(lin(tip)) * g
    m = max(1.0, float(a0.max()), float(a1.max()))

    def ramp(u):
        x = np.clip((np.asarray(u, float) - b0) / max(band - b0, 1e-6), 0, 1)
        w = 1 - x * x * (3 - 2 * x)
        return (a0[None] * (1 - w[:, None]) + a1[None] * w[:, None]) / m
    return ramp


def ramp_texture(ramp, n: int = 64) -> tuple[np.ndarray, list]:
    """(sRGB image n x 4 x 3 in 0..1, factor rgb) whose product is ramp(u) across the image's width."""
    c = ramp((np.arange(n) + 0.5) / n)
    s = max(float(c.max()), 1e-6)
    img = np.repeat(srgb(c / s)[None], 4, axis=0)
    return img, [s, s, s]


def bark_color(spec: dict, st: dict) -> list:
    co = st.get("colour") or {}
    c = styled((spec.get("bark") or {}).get("color", [0.5, 0.45, 0.4]), co.get("bark_saturation", 1.0), co.get("bark_value", 1.0))
    if co.get("bark_mix"):  # toward one painted colour (anime: flat and cool)
        a = float(co.get("bark_mix_amount", 0.5))
        c = [round(c[i] * (1 - a) + float(co["bark_mix"][i]) * a, 4) for i in range(3)]
    return c


def color_gain(st: dict) -> float:
    """What the crown material's colour is multiplied by (COLOR_0 holds each mass's tone divided by it)."""
    cr = st.get("crown") or {}
    if cr.get("gradient"):  # (pixar: a gradient base-to-tip, warmer at the tips)
        return float(max(cr["gradient"]) * (1 + abs(float(cr.get("warm_tip", 0.1)))) * (1 + abs(float(cr.get("hue_jitter", 0.0)))))
    return float(max(cr.get("tone", [0.85, 1.15])) * (1 + abs(float(cr.get("warm_top", 0.0)))))


CLUMP = {"blades": [5, 9], "width": 0.2, "thick": 0.6, "curl": 0.35, "heads": 3, "ball": 0.06, "stalk": 0.012, "normals_up": 0.35,
         "tones": 3, "tone": [0.8, 1.15], "budget": 800, "roughness": 0.8}


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("veg_style_wood", "veg_style_crown", "veg_style_dress", "veg_style_small")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
