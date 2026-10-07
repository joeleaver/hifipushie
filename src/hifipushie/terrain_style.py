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
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy import ndimage

CONTRACT = 1
CONTRACT_LOG = {
    1: "styles: materials/<style>/<layer>_albedo (sRGB) / _normal / _height (+ _overlay_*), styles/<style>_sd.png and "
       "styles/weights<g>.png, manifest `styles` (list, zones, layers, seasons, snow, tiles, recipe)",
}
DIR = Path(__file__).parent / "terrain_styles"
STYLE_LAYERS = ("grass", "turf", "scrub", "forest_floor", "sand", "earth", "rock", "wet_rock", "snow")
PX = 1024           # texture side in pixels
BAND = 20.0         # m: the default transition band (centred on the zone's edge)
SD_RANGE = 64.0     # m: the signed distance maps run -SD_RANGE..SD_RANGE
SEASONS = ("spring", "summer", "autumn", "winter")


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


# ------------------------------------------------------------------------------------------------ periodic fields

def _freq(n):
    fx = np.fft.fftfreq(n)[None, :] * n
    fy = np.fft.fftfreq(n)[:, None] * n
    return fx, fy


def band_noise(n, cycles, seed, width=0.6, stretch=(1.0, 1.0)):
    """Periodic noise with features about n / cycles px (a log-normal band of frequencies), -1..1 (1st..99th pct)."""
    rng = np.random.default_rng(seed)
    fx, fy = _freq(n)
    f = np.hypot(fx * stretch[0], fy * stretch[1])
    amp = np.where(f > 0, np.exp(-0.5 * (np.log(np.maximum(f, 1e-9) / max(cycles, 0.5)) / width) ** 2), 0.0)
    z = np.real(np.fft.ifft2(amp * np.exp(2j * np.pi * rng.random((n, n)))))
    lo, hi = np.percentile(z, [1, 99])
    return np.clip(2 * (z - lo) / max(hi - lo, 1e-12) - 1, -1, 1)


def _worley(n, L, size, seed, jitter=0.9):
    """F1, F2 (m) and the nearest seed's id on the L x L torus, seeds about `size` m apart (a jittered grid with a
    whole number of cells across, so it tiles)."""
    from scipy.spatial import cKDTree
    k = max(1, int(round(L / size)))
    rng = np.random.default_rng(seed)
    g = (np.arange(k) + 0.5) / k * L
    sx, sy = np.meshgrid(g, g)
    pts = np.c_[sx.ravel(), sy.ravel()] + (rng.random((k * k, 2)) - 0.5) * jitter * L / k
    ids = np.arange(k * k)
    tiles = [pts + np.array([dx, dy]) * L for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
    allp = np.concatenate(tiles)
    allid = np.tile(ids, 9)
    t = (np.arange(n) + 0.5) * (L / n)
    X, Y = np.meshgrid(t, t)
    d, i = cKDTree(allp).query(np.c_[X.ravel(), Y.ravel()], k=2)
    return d[:, 0].reshape(n, n), d[:, 1].reshape(n, n), allid[i[:, 0]].reshape(n, n), k * k


def _steps(x, steps, soft):
    """x (-1..1) quantised into `steps` tones with soft edges (soft 0 = hard, 1 = no steps)."""
    if not steps or steps < 2:
        return x
    u = (np.clip(x, -1, 1) + 1) / 2 * steps
    k = np.floor(u)
    f = u - k
    s = max(float(soft), 1e-3) / 2
    e = np.clip((f - (0.5 - s)) / (2 * s), 0, 1)
    e = e * e * (3 - 2 * e)
    q = (np.minimum(k, steps - 1) + e) / steps
    return 2 * q - 1


def _norm(t):
    lo, hi = np.percentile(t, [1, 99])
    if hi - lo < 1e-12:
        return np.zeros_like(t)
    return np.clip(2 * (t - lo) / (hi - lo) - 1, -1, 1)


# each op: (n, L m, numbers, seed) -> (tone -1..1, height m); albedo / height amounts are applied by the caller

def op_blotch(n, L, o, seed):
    """Large soft blotches (`size` m), quantised to `steps` tones (`soft` edges): blobby / painted colour fields."""
    t = band_noise(n, L / float(o.get("size", 3.0)), seed, width=float(o.get("width", 0.5)),
                   stretch=tuple(o.get("stretch", (1.0, 1.0))))
    q = _steps(t, int(o.get("steps", 0)), float(o.get("soft", 0.5)))
    return q, t  # (height from the unstepped field: the steps' edges drew contour lines in the normal map)


def op_pillow(n, L, o, seed):
    """Rounded cushions (`size` m apart) with soft seams between them: blobby rock, pebble-smooth."""
    f1, f2, cid, k = _worley(n, L, float(o.get("size", 2.0)), seed, float(o.get("jitter", 0.9)))
    e = (f2 - f1) / max(float(o.get("size", 2.0)), 1e-6)  # (0 on a seam, ~0.5 at a cushion's middle)
    r = float(o.get("round", 0.35))
    h = 1 - np.exp(-e / max(r, 1e-3) * 2)
    h = ndimage.gaussian_filter(h, max(1.0, n / L * float(o.get("blur", 0.02))), mode="wrap")
    rng = np.random.default_rng(seed + 7)
    tone = rng.uniform(-1, 1, k)[cid] * float(o.get("vary", 0.5)) + (h - h.mean()) * float(o.get("dome", 1.0))
    return np.clip(tone, -1, 1), h - h.mean()


def op_strokes(n, L, o, seed):
    """Brush dabs: `per_m2` elongated dabs `length` x `width` m at `angle` deg (+- `spread`), each a tone in
    `tones` [lo, hi], painted one over another (soft edges): painted grass, a hand-drawn tuft field."""
    rng = np.random.default_rng(seed)
    px = n / L
    N = int(float(o.get("per_m2", 30)) * L * L)
    lo, hi = o.get("tones", [-1.0, 1.0])
    lenm, widm = o.get("length", 0.3), o.get("width", 0.06)
    lenm = lenm if isinstance(lenm, list) else [0.7 * lenm, 1.3 * lenm]
    widm = widm if isinstance(widm, list) else [0.7 * widm, 1.3 * widm]
    ang0, spread = math.radians(float(o.get("angle", 90))), math.radians(float(o.get("spread", 25)))
    taper = float(o.get("taper", 0.6))
    tone = np.zeros((n, n))
    alpha_acc = np.zeros((n, n))
    hgt = np.zeros((n, n))
    bias = band_noise(n, max(1.0, L / float(o.get("cluster", 1.5))), seed + 3) * float(o.get("cluster_tone", 0.4))
    for _ in range(N):
        cx, cy = rng.random(2) * n
        a = ang0 + rng.normal(0, spread)
        ln = rng.uniform(*lenm) * px / 2
        wd = rng.uniform(*widm) * px / 2
        tv = rng.uniform(lo, hi) + bias[int(cy) % n, int(cx) % n]
        r = int(ln + wd + 2)
        ii, jj = np.mgrid[int(cy) - r:int(cy) + r + 1, int(cx) - r:int(cx) + r + 1]
        dx, dy = jj - cx, ii - cy
        u = (dx * math.cos(a) + dy * math.sin(a)) / max(ln, 1e-6)
        v = (-dx * math.sin(a) + dy * math.cos(a)) / max(wd, 1e-6)
        w_ = 1 - taper * (u + 1) / 2  # (a dab narrows toward its tip)
        d = u * u + (v / np.maximum(w_, 0.15)) ** 2
        m = np.clip((1 - d) * 3, 0, 1)
        if not m.any():
            continue
        sl = (ii % n, jj % n)
        tone[sl] = tone[sl] * (1 - m) + tv * m
        alpha_acc[sl] = np.maximum(alpha_acc[sl], m)
        hgt[sl] = hgt[sl] * (1 - m) + m * (0.3 + 0.7 * np.sqrt(np.clip(1 - d, 0, 1)))
    gap = float(o.get("gap", -0.6))  # (tone where no dab landed: the shadow between strokes)
    tone = tone * alpha_acc + gap * (1 - alpha_acc)
    return np.clip(tone, -1, 1), hgt - hgt.mean()


def op_bands(n, L, o, seed):
    """Horizontal strata (rows = up): bands `thickness` [lo, hi] m filling the texture's height exactly, tones cycling
    through `tones`, edges `edge` m soft, rows wavering `wave` m; each band proud or set back by its tone (height)."""
    rng = np.random.default_rng(seed)
    lo, hi = o.get("thickness", [0.3, 1.2])
    th = []
    while sum(th) < L:
        th.append(rng.uniform(lo, hi))
    th = np.array(th) * (L / sum(th))
    edges = np.concatenate([[0], np.cumsum(th)])
    tones = o.get("tones", [-0.8, 0.2, 0.9, -0.2])
    bt = np.array([tones[i % len(tones)] for i in range(len(th))]) + rng.normal(0, float(o.get("jitter", 0.1)), len(th))
    t = (np.arange(n) + 0.5) * (L / n)
    wave = band_noise(n, max(1.0, L / float(o.get("wave_len", 3.0))), seed + 1)[0] * float(o.get("wave", 0.08))
    V = (t[:, None] + wave[None, :]) % L  # (rows: v up; columns: u)
    e = max(float(o.get("edge", 0.02)), 1e-4)
    tone = np.zeros((n, n))
    hgt = np.zeros((n, n))
    step = float(o.get("step", 1.0))
    for k in range(len(th)):
        a, b = edges[k], edges[k + 1]
        inside = np.clip((V - a) / e + 0.5, 0, 1) * np.clip((b - V) / e + 0.5, 0, 1)
        if k == 0:  # (the wrap: the first band also continues past the last edge)
            inside = np.maximum(inside, np.clip((V - (L + a)) / e + 0.5, 0, 1))
        tone += inside * bt[k]
        hgt += inside * bt[k] * step
    return np.clip(tone, -1, 1), hgt - hgt.mean()


def op_ripples(n, L, o, seed):
    """Soft parallel bands (`spacing` m, `angle` deg from east) wandering by `warp`: wind ripples on sand."""
    sp = float(o.get("spacing", 0.15))
    a = math.radians(float(o.get("angle", 20)))
    mx, my = int(round(L / sp * math.cos(a))), int(round(L / sp * math.sin(a)))
    t = (np.arange(n) + 0.5) / n
    X, Y = np.meshgrid(t, t)
    w = band_noise(n, max(1.0, L / float(o.get("warp_len", 2.0))), seed) * float(o.get("warp", 0.6))
    ph = 2 * np.pi * (mx * X + my * Y) + w * 2 * np.pi
    s = np.sin(ph)
    sharp = float(o.get("sharp", 0.0))
    s = np.sign(s) * np.abs(s) ** (1 - 0.8 * sharp) if sharp else s
    patch = 1.0
    if o.get("patches"):
        patch = np.clip(0.5 + band_noise(n, L / float(o["patches"]), seed + 2), 0, 1)
    return s * patch, s * patch


def op_dots(n, L, o, seed):
    """Discs `size` [lo, hi] m, `per_m2`, each a tone in `tones`: pebbles, flecks, flowers seen from above."""
    rng = np.random.default_rng(seed)
    px = n / L
    N = int(float(o.get("per_m2", 20)) * L * L)
    lo, hi = o.get("size", [0.02, 0.06])
    tl, th_ = o.get("tones", [-1.0, 1.0])
    tone = np.zeros((n, n))
    hgt = np.zeros((n, n))
    for _ in range(N):
        cx, cy = rng.random(2) * n
        r = rng.uniform(lo, hi) / 2 * px
        ri = int(r + 2)
        ii, jj = np.mgrid[int(cy) - ri:int(cy) + ri + 1, int(cx) - ri:int(cx) + ri + 1]
        d = np.hypot(ii - cy, jj - cx) / max(r, 1e-6)
        m = np.clip((1 - d) * max(r, 1.0), 0, 1)
        sl = (ii % n, jj % n)
        tone[sl] = tone[sl] * (1 - m) + rng.uniform(tl, th_) * m
        hgt[sl] = np.maximum(hgt[sl], np.sqrt(np.clip(1 - d * d, 0, 1)))
    return tone, hgt


def op_grain(n, L, o, seed):
    """Fine noise with features about `size` m: grit, soil, real rock's grain."""
    t = band_noise(n, L / float(o.get("size", 0.05)), seed, width=float(o.get("width", 0.8)))
    return t, t


def op_cracks(n, L, o, seed):
    """Ink cracks: a few Voronoi edges (cells `size` m), only `share` of them drawn, `width` m wide: cartoon rock."""
    f1, f2, cid, k = _worley(n, L, float(o.get("size", 1.5)), seed)
    rng = np.random.default_rng(seed + 5)
    draw = rng.random(k) < float(o.get("share", 0.4))
    edge = (f2 - f1) < float(o.get("width", 0.02))
    line = edge & draw[cid]
    line = ndimage.gaussian_filter(line.astype(float), 0.7, mode="wrap")
    return -np.clip(line * 2, 0, 1), -np.clip(line * 2, 0, 1)


def op_facets(n, L, o, seed):
    """Flat facets `size` m across: each Voronoi cell a tilted plane (heights continuous only in tone): chunky
    cartoon rock in the normal map."""
    f1, f2, cid, k = _worley(n, L, float(o.get("size", 1.0)), seed)
    rng = np.random.default_rng(seed + 9)
    tilt = rng.normal(0, float(o.get("tilt", 0.25)), (k, 2))
    t = (np.arange(n) + 0.5) * (L / n)
    X, Y = np.meshgrid(t, t)
    h = tilt[cid, 0] * X + tilt[cid, 1] * Y
    h = h - ndimage.uniform_filter(h, n // 4, mode="wrap")  # (the planes as local tilts, not a staircase)
    tone = rng.uniform(-1, 1, k)[cid]
    return tone, h * float(o.get("size", 1.0))


OPS = {"blotch": op_blotch, "pillow": op_pillow, "strokes": op_strokes, "bands": op_bands, "ripples": op_ripples,
       "dots": op_dots, "grain": op_grain, "cracks": op_cracks, "facets": op_facets}


def _seed(*parts):
    return int(hashlib.sha1("/".join(map(str, parts)).encode()).hexdigest()[:8], 16) % 1_000_000


def texture(st: dict, layer: str, colour_srgb, px: int = PX) -> dict:
    """One style's tileable texture for a layer: {"albedo" (n, n, 3) sRGB 0..1 (linear mean = the colour), "height" m,
    "normal" (n, n, 3) tangent (+x along the image's x, +y up the image), "size_m", "projection"}. Rows run up."""
    L = layer_sheet(st, layer)
    size = float(L.get("scale_m", 4.0))
    n = int(px)
    tone = np.zeros((n, n))
    hgt = np.zeros((n, n))
    for k, o in enumerate(L.get("ops") or []):
        fn = OPS.get(o.get("op"))
        if fn is None:
            raise ValueError(f"style {st['name']}: layer {layer}: unknown op {o.get('op')!r} (ops: {', '.join(OPS)})")
        t, h = fn(n, size, o, _seed(st["name"], layer, k, o.get("seed", 0)))
        tone += float(o.get("albedo", 0.0)) * t
        hgt += float(o.get("height", 0.0)) * h
    base = _srgb_lin(colour_srgb)
    warm = np.array(L.get("warm", [1, 1, 1]), float)
    cool = np.array(L.get("cool", [1, 1, 1]), float)
    tp, tn = np.clip(tone, 0, None)[..., None], np.clip(-tone, 0, None)[..., None]
    tint = 1 + tp * (warm - 1) + tn * (cool - 1)
    lin = base * np.clip(1 + tone, 0.05, None)[..., None] * tint
    lin = lin * (base / np.maximum(lin.reshape(-1, 3).mean(0), 1e-6))  # (mean = the layer's colour)
    texel = size / n
    gx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) / (2 * texel)
    gy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) / (2 * texel)  # (rows run up: +y)
    s = float(L.get("normal", 1.0))
    nrm = np.stack([-gx * s, -gy * s, np.ones_like(gx)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    return {"albedo": _lin_srgb(lin), "albedo_linear": lin, "height": hgt - hgt.mean(), "normal": nrm, "size_m": size,
            "projection": L.get("projection", "triplanar" if layer in ("rock", "wet_rock") else "top"),
            "roughness": float(L.get("roughness", 0.9))}


def overlay(st: dict, px: int = 512) -> dict | None:
    """A style's own small-scale multiplier swatch (mean 1), drawn over every layer within `fade_m`: anime brush
    dabs. None when the sheet has none."""
    O = st.get("overlay")
    if not O:
        return None
    n = int(px)
    size = float(O.get("scale_m", 1.0))
    tone = np.zeros((n, n))
    hgt = np.zeros((n, n))
    for k, o in enumerate(O.get("ops") or []):
        t, h = OPS[o["op"]](n, size, o, _seed(st["name"], "overlay", k))
        tone += float(o.get("albedo", 0.0)) * t
        hgt += float(o.get("height", 0.0)) * h
    mult = np.clip(1 + tone, 0.05, None)
    mult /= mult.mean()
    texel = size / n
    gx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) / (2 * texel)
    gy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) / (2 * texel)
    nrm = np.stack([-gx, -gy, np.ones_like(gx)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    return {"mult": mult, "normal": nrm, "size_m": size, "fade_m": list(O.get("fade_m", [15.0, 60.0])),
            "strength": float(O.get("strength", 1.0))}


# ------------------------------------------------------------------------------------------------ seasons, snow

def season_colours(st: dict, layer: str, colour_srgb) -> dict:
    """{season: {"color" sRGB, "tint_linear": colour / the summer colour (multiply the texture by it)}}."""
    out = {}
    base = np.array(colour_srgb, float)
    for se in SEASONS:
        S = ((st.get("seasons") or {}).get(se) or {})
        m = S.get(layer) or S.get("*") or {}
        if layer in (S.get("skip") or []):
            m = {}
        c = base * (1 - float(m.get("amount", 0))) + np.array(m.get("mix", base), float) * float(m.get("amount", 0))
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
            d = np.full(m.shape, SD_RANGE if m.all() else -SD_RANGE)
        else:
            d = (ndimage.distance_transform_edt(m) - ndimage.distance_transform_edt(~m)) * T.cell
            d = d - 0.5 * T.cell * np.sign(d)  # (the edge half-way between cells)
        sd[nm] = np.clip(d, -SD_RANGE, SD_RANGE)
        e = np.clip(sd[nm] / max(bands[nm], 1e-6) + 0.5, 0, 1)
        raw[nm] = e * e * (3 - 2 * e)
    tot = np.maximum(sum(raw.values()), 1e-9)
    w = {nm: raw[nm] / tot for nm in order}
    return {"sd": sd, "w": w, "order": order}


# ------------------------------------------------------------------------------------------------ files

def _png(path, a, mode=None):
    from PIL import Image
    Image.fromarray(np.ascontiguousarray(a), mode).save(path)


def _q8(a):
    return np.round(np.clip(a, 0, 1) * 255).astype(np.uint8)


def _q16(a):
    return np.round(np.clip(a, 0, 1) * 65535).astype(np.uint16)


def tileable(img: np.ndarray) -> float:
    """The wrap seam's step against the steps beside it (1 = invisible), the worst channel."""
    a = np.asarray(img, float)
    a = a if a.ndim == 3 else a[..., None]
    seam = np.abs(a[0] - a[-1]).mean() + np.abs(a[:, 0] - a[:, -1]).mean()
    beside = np.abs(a[1] - a[0]).mean() + np.abs(a[:, 1] - a[:, 0]).mean()
    return round(float(seam / max(beside, 1e-9)), 3)


def write_layers(out: Path, st: dict, refs: dict, layers, px: int = PX) -> dict:
    """materials/<style>/<layer>_albedo|_normal|_height.png for `layers`; returns the manifest entries per layer."""
    d = out / "materials" / st["name"]
    d.mkdir(parents=True, exist_ok=True)
    import shutil
    res = {}
    cache = _cache_dir()
    for nm in layers:
        if nm not in refs:
            continue
        col = layer_colour(st, nm, refs)
        Ls = layer_sheet(st, nm)
        key = hashlib.sha1(json.dumps([st["name"], nm, Ls, [round(float(x), 6) for x in col], int(px), _code()],
                                      sort_keys=True).encode()).hexdigest()[:24]
        kd = cache / key if cache else None
        meta = None
        if kd is not None and (kd / "meta.json").exists():  # (the PNGs as made before: identical bytes)
            meta = json.loads((kd / "meta.json").read_text())
            for k in ("albedo", "normal", "height"):
                shutil.copyfile(kd / f"{k}.png", out / f"materials/{st['name']}/{nm}_{k}.png")
        if meta is None:
            S = texture(st, nm, col, px)
            hr = float(max(np.abs(S["height"]).max(), 1e-5))
            for k, a in (("albedo", _q8(S["albedo"])), ("normal", _q8(S["normal"] * 0.5 + 0.5)),
                         ("height", _q16(S["height"] / hr * 0.5 + 0.5))):
                _png(out / f"materials/{st['name']}/{nm}_{k}.png", a[::-1],
                     "I;16" if a.dtype == np.uint16 else None)  # (image rows run down)
            meta = {"size_m": S["size_m"], "projection": S["projection"], "height_m": round(hr, 5),
                    "roughness": S["roughness"], "wrap_seam": tileable(S["albedo"])}
            if kd is not None:
                try:
                    kd.mkdir(parents=True, exist_ok=True)
                    for k in ("albedo", "normal", "height"):
                        shutil.copyfile(out / f"materials/{st['name']}/{nm}_{k}.png", kd / f"{k}.png")
                    (kd / "meta.json").write_text(json.dumps(meta))
                except OSError:
                    pass
        files = {k: f"materials/{st['name']}/{nm}_{k}.png" for k in ("albedo", "normal", "height")}
        res[nm] = {**files, **{k: meta[k] for k in ("size_m", "projection", "height_m")},
                   "color": [round(float(x), 4) for x in col],
                   "color_linear": [round(float(x), 4) for x in _srgb_lin(col)],
                   "roughness": meta["roughness"], "normal_strength": float(Ls.get("normal_strength", 1.0)),
                   "seasons": season_colours(st, nm, col), "wrap_seam": meta["wrap_seam"]}
    return res


_CODE = None


def _code():
    global _CODE
    if _CODE is None:
        _CODE = hashlib.sha1(Path(__file__).read_bytes()).hexdigest()
    return _CODE


def _cache_dir():
    """Where written layer PNGs are kept by their inputs ($HIFIPUSHIE_STYLE_CACHE; 0 = off): making a dab layer
    takes seconds, copying it none."""
    import os
    v = os.environ.get("HIFIPUSHIE_STYLE_CACHE")
    if v in ("0", "off", "false"):
        return None
    return Path(v) if v else Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "hifipushie" / "terrain_style"


def write_overlay(out: Path, st: dict) -> dict | None:
    O = overlay(st)
    if O is None:
        return None
    d = out / "materials" / st["name"]
    d.mkdir(parents=True, exist_ok=True)
    fa, fn = f"materials/{st['name']}/overlay_albedo.png", f"materials/{st['name']}/overlay_normal.png"
    _png(out / fa, _q8(0.5 * O["mult"])[::-1])
    _png(out / fn, _q8(O["normal"] * 0.5 + 0.5)[::-1])
    return {"albedo": fa, "normal": fn, "size_m": O["size_m"], "fade_m": O["fade_m"], "strength": O["strength"],
            "how": "albedo x (1 + s (2 a - 1)), s = strength x (1 - smoothstep(fade_m[0], fade_m[1], view distance)); "
                   "normal RNM-combined by s; top projection on the ground, triplanar on rock"}


RECIPE = (
    "Per pixel, for each style s with weight ws (styles/weights<g>.png, or your own band from styles/<s>_sd.png: ws = "
    "smoothstep(-band/2, band/2, sd + ragged noise), normalised so the weights sum to 1; realistic takes the rest) and "
    "each ground layer l with weight wl (the tiles' layer weights: maps/<tile>_weights<g>.png / splats / _WEIGHTS):\n"
    "1. A_s = sum_l wl x texture(materials/<s>/<l>_albedo, uv_l) (sRGB -> linear), uv_l = world (x, y) / size_m on the "
    "ground (projection top; image +x east, +y north), triplanar for projection 'triplanar' and on faces steeper than "
    "~35 deg (side planes: u along the face, v = world z / size_m, so painted strata stay level). Height-blend the "
    "layers with <l>_height for crisper layer edges if you like. Anti-tiling as the detail recipe: a second sampling "
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


def write(out: Path, T, refs: dict, spec: dict | None = None, tiles: list | None = None, px: int = PX,
          layers=None) -> dict:
    """Every style's files into `out` (an export directory, or any directory) and the manifest section. `refs` = the
    realistic layers' reference looks ({layer: {"color", "roughness", "scale"}}, Materials.layer_ref), `tiles` =
    [(i, j, (x0, y0, x1, y1))] to say which styles reach each tile. Cached per sheet + layer + code (texture making
    is a few seconds a layer)."""
    from PIL import Image
    out = Path(out)
    spec = spec if spec is not None else T.spec
    styles = resolve(spec)
    if not any(s["name"] == "realistic" for s in styles):
        styles_all = styles + [{"name": "realistic", "zones": [], "band": BAND, "sheet": sheet("realistic")}]
    else:
        styles_all = styles
    layers = [nm for nm in (layers or STYLE_LAYERS) if nm in refs]
    F = style_fields(T, styles)
    order = F["order"]
    sdir = out / "styles"
    sdir.mkdir(parents=True, exist_ok=True)
    maps = {"sd": {}, "weights": []}
    (x0, y0), (x1, y1) = T.spec["extent"]
    for nm in (order if styles else []):
        fn = f"styles/{nm}_sd.png"
        _png(out / fn, _q16(F["sd"][nm] / (2 * SD_RANGE) + 0.5)[::-1], "I;16")
        maps["sd"][nm] = fn
    if styles:
        W = [F["w"][nm] for nm in order]
        for g in range(0, len(W), 4):
            grp = W[g:g + 4] + [np.zeros_like(W[0])] * (4 - len(W[g:g + 4]))
            fn = f"styles/weights{g // 4}.png"
            Image.fromarray(np.ascontiguousarray(_q8(np.stack(grp, -1))[::-1]), "RGBA").save(out / fn)
            maps["weights"].append(fn)
    per_tile = []
    for (i, j, (bx0, by0, bx1, by1)) in (tiles or []):
        sel = (T.X >= bx0 - T.cell) & (T.X <= bx1 + T.cell) & (T.Y >= by0 - T.cell) & (T.Y <= by1 + T.cell)
        reach = [nm for nm in order if (F["w"][nm][sel].max() if styles else 1.0) > 0.005]
        per_tile.append({"i": i, "j": j, "styles": reach})
    entries = []
    for s in styles_all:
        st = s["sheet"]
        lay = write_layers(out, st, refs, layers, px)
        entries.append({"name": s["name"], "zones": s["zones"], "band_m": s["band"], "about": st.get("about", ""),
                        "sd": maps["sd"].get(s["name"]),
                        "weights": ([f"styles/weights{order.index(s['name']) // 4}.png", order.index(s["name"]) % 4]
                                    if styles else None),
                        "macro": float(st.get("macro", 1.0)), "macro_normal": float(st.get("macro_normal", 1.0)),
                        "detail": float(st.get("detail", 0.0)), "overlay": write_overlay(out, st),
                        "layers": lay, "snow": snow_numbers(st), "rock": st.get("rock") or {}})
    return {"contract": {"version": CONTRACT, "changes": {str(k): v for k, v in CONTRACT_LOG.items()}},
            "order": order, "styles": entries,
            "maps": {"sd": maps["sd"], "weights": maps["weights"], "range_m": SD_RANGE,
                     "extent": [[x0, y0], [x1, y1]], "cell_m": float(T.cell),
                     "uv": "north-up images over the terrain's extent: pixel centre (c, r) at x = x0 + (c + 0.5) cell, "
                           "y = y1 - (r + 0.5) cell; sd 16-bit, value 0.5 = the edge, (v - 0.5) x 2 x range_m metres, "
                           "positive inside the style's zone; weights RGBA in `order`, groups of 4, sum 1"},
            "tiles": per_tile, "recipe": RECIPE,
            "note": "colours: `color` sRGB, `color_linear` / `tint_linear` linear; albedo PNGs are sRGB, normal / "
                    "height PNGs linear (never sRGB). Shape (rock, landform) per style is in the tiles' geometry; "
                    "textures and seasons here are for the engine's shader."}


def refs_of(T) -> dict:
    """The realistic layers' reference looks for terrain T without the 3D field (as Materials.layer_ref: the rock
    colour is the median of the steep cells' rock colour)."""
    from . import terrain_mesh as tm
    refs = {k: dict(v) for k, v in tm.LAYERS.items()}
    rg = tm.rock_colours(T)
    steep = T._slope() > 45
    rr = np.median(rg[steep] if steep.any() else rg.reshape(-1, 3), 0)
    refs["rock"]["color"] = [round(float(x), 3) for x in rr]
    refs["wet_rock"]["color"] = [round(float(x) * 0.45, 3) for x in rr]
    return refs


def export_styles(T, out, mats=None, G=None, px: int = PX) -> dict:
    """The styles' files for terrain T into `out` (an export_terrain tiles directory, or a fresh one beside it): the
    textures, the zone maps, styles.json (= the manifest section) and, when out/manifest.json exists, its "styles"
    key. `mats` / `G` (terrain_mesh.Materials / Grid) are made when not given (the 3D field's setup: seconds)."""
    from . import terrain_mesh as tm
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = {**tm.DEFAULTS, **((T.spec.get("export") or {}).get("tiles") or {})}
    if mats is None:
        field = tm.build_field(T, cfg)[0]
        mats = tm.Materials(T, field)
    if G is None:
        G = tm.Grid(T, cfg)
    refs = {nm: mats.layer_ref(nm) for nm in mats.layers}
    tiles = []
    for j in range(G.nj):
        for i in range(G.ni):
            lo, hi = G.bounds(i, j)
            tiles.append((i, j, (float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1]))))
    sec = write(out, T, refs, tiles=tiles, layers=mats.layers, px=px)
    (out / "styles.json").write_text(json.dumps(sec, indent=1))
    mf = out / "manifest.json"
    if mf.exists():
        M = json.loads(mf.read_text())
        M["styles"] = sec
        mf.write_text(json.dumps(M, indent=1))
    return sec


def summary(sec: dict) -> str:
    """A few lines for a tool reply: each style, its zones, layers and how many tiles it reaches."""
    lines = [f"styles (contract {sec['contract']['version']}): {', '.join(sec['order'])}"]
    for s in sec["styles"]:
        n = sum(1 for t in sec["tiles"] if s["name"] in t["styles"])
        lines.append(f"- {s['name']}: zones {s['zones'] or ['(everywhere else)']}, band {s['band_m']:g} m, "
                     f"{n} of {len(sec['tiles'])} tiles, macro {s['macro']:g}, layers "
                     + ", ".join(f"{k} {v['size_m']:g} m" for k, v in s["layers"].items())
                     + (", overlay" if s.get("overlay") else ""))
    worst = max((v["wrap_seam"], s["name"], k) for s in sec["styles"] for k, v in s["layers"].items())
    lines.append(f"worst wrap seam: {worst[1]} {worst[2]} {worst[0]:g} (1 = invisible; over 1.5 shows)")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ looks

def _shade(S, light=(-0.5, 0.45, 0.75)):
    l = np.array(light, float)
    l /= np.linalg.norm(l)
    ndl = np.clip((S["normal"] * l).sum(-1), 0, 1)
    lin = S["albedo_linear"] * (0.25 + 0.75 * ndl)[..., None]
    return _lin_srgb(lin)


def swatch_sheet(styles: list[dict], refs: dict, layers, path, px: int = 384, tiled: int = 2) -> Path:
    """A contact sheet: a row per style, per layer the albedo tiled `tiled` x `tiled` (the wrap shows if it seams),
    then lit with a low sun, then its normal map. Rows: style names; columns: layers."""
    from PIL import Image, ImageDraw
    cell = px
    cols = len(layers) * 3
    W, H = 160 + cols * (cell + 4), 40 + len(styles) * (cell + 24)
    im = Image.new("RGB", (W, H), (32, 32, 34))
    dr = ImageDraw.Draw(im)
    for c, nm in enumerate(layers):
        x = 160 + c * 3 * (cell + 4)
        dr.text((x + 4, 8), f"{nm}: albedo x{tiled * tiled} tiles | lit | normal", fill=(230, 230, 230))
    for r, st in enumerate(styles):
        y = 40 + r * (cell + 24)
        dr.text((8, y + cell // 2), st["name"], fill=(240, 240, 240))
        for c, nm in enumerate(layers):
            col = layer_colour(st, nm, refs)
            S = texture(st, nm, col, 512)
            x = 160 + c * 3 * (cell + 4)
            alb = np.tile(S["albedo"][::-1], (tiled, tiled, 1))
            panels = [alb, np.tile(_shade(S)[::-1], (tiled, tiled, 1)), S["normal"][::-1] * 0.5 + 0.5]
            for k, a in enumerate(panels):
                pim = Image.fromarray(_q8(a)).resize((cell, cell), Image.LANCZOS)
                im.paste(pim, (x + k * (cell + 4), y))
            dr.text((x + 2, y + cell + 2), f"{S['size_m']:g} m a tile ({tiled * S['size_m']:g} m shown)",
                    fill=(200, 200, 200))
    path = Path(path)
    im.save(path)
    return path


def transition_strip(styles: list[dict], refs: dict, layer: str, path, length_m: float = 60.0, band: float = BAND,
                     px_per_m: int = 24, width_m: float = 8.0) -> Path:
    """A top view of one layer walking through the styles in order, each pair blended over `band` m as the recipe
    does (weights by a smoothstep, a lit preview): what the engine's transition should look like."""
    from PIL import Image
    n_st = len(styles)
    Wm = length_m * n_st
    w_px, h_px = int(Wm * px_per_m), int(width_m * px_per_m)
    xs = (np.arange(w_px) + 0.5) / px_per_m
    ys = (np.arange(h_px) + 0.5) / px_per_m
    X, Y = np.meshgrid(xs, ys)
    acc = np.zeros((h_px, w_px, 3))
    wsum = np.zeros((h_px, w_px))
    for k, st in enumerate(styles):
        col = layer_colour(st, layer, refs)
        S = texture(st, layer, col, 512)
        L = S["size_m"]
        n = S["albedo"].shape[0]
        lit = _srgb_lin(_shade(S))
        ii = ((Y / L * n).astype(int)) % n
        jj = ((X / L * n).astype(int)) % n
        a, b = k * length_m, (k + 1) * length_m  # (this style's stretch; the strip's own ends don't blend)
        d = np.minimum(X - a if k > 0 else np.full_like(X, 1e9), b - X if k < n_st - 1 else np.full_like(X, 1e9))
        e = np.clip(d / band + 0.5, 0, 1)
        w = e * e * (3 - 2 * e)
        acc += w[..., None] * lit[ii, jj]
        wsum += w
    img = _lin_srgb(acc / np.maximum(wsum, 1e-6)[..., None])
    Image.fromarray(_q8(img)).save(path)
    return Path(path)
