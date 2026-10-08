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

CONTRACT = 3
CONTRACT_LOG = {
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
STYLE_LAYERS = ("grass", "turf", "scrub", "forest_floor", "sand", "earth", "rock", "wet_rock", "snow")
PX = 1024           # texture side in pixels
BAND = 20.0         # m: the default transition band (centred on the zone's edge)
SD_RANGE = 64.0     # m: the signed distance maps run -SD_RANGE..SD_RANGE
SEASONS = ("spring", "summer", "autumn", "winter")
# a layer's `fade_small` ops (e.g. anime strata) give way to its plain texture on small or thin rock: full where the face
# is over face_m[1] tall AND the rock over thick_m[1] thick (half-thickness in plan), none under the [0]s
SMALL_FADE = {"face_m": [4.0, 12.0], "thick_m": [2.0, 6.0]}
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


def noise_rows(n, cycles, seed, count, width=0.6):
    """`count` independent periodic 1D noises of n samples, features about n / cycles, -1..1 (1st..99th pct)."""
    rng = np.random.default_rng(seed)
    f = np.abs(np.fft.fftfreq(n) * n)
    amp = np.where(f > 0, np.exp(-0.5 * (np.log(np.maximum(f, 1e-9) / max(cycles, 0.5)) / width) ** 2), 0.0)
    z = np.real(np.fft.ifft(amp[None, :] * np.exp(2j * np.pi * rng.random((count, n))), axis=1))
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
    """Large soft blotches (`size` m), quantised to `steps` tones (`soft` edges): blobby / painted colour fields.
    `share`: with 2 steps, the share of the ground in the upper tone (patches on a ground colour, not a 50/50
    camouflage); `width` the spread of sizes (wider = less regular)."""
    t = band_noise(n, L / float(o.get("size", 3.0)), seed, width=float(o.get("width", 0.5)),
                   stretch=tuple(o.get("stretch", (1.0, 1.0))))
    if o.get("share") is not None:
        t = np.clip(t - np.quantile(t, 1 - float(o["share"])), -1, 1)
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
    `tones` [lo, hi] (`levels` n: only n evenly spaced tones in that range), painted one over another (soft edges):
    painted grass, a hand-drawn tuft field."""
    rng = np.random.default_rng(seed)
    px = n / L
    N = int(float(o.get("per_m2", 30)) * L * L)
    lo, hi = o.get("tones", [-1.0, 1.0])
    lenm, widm = o.get("length", 0.3), o.get("width", 0.06)
    lenm = lenm if isinstance(lenm, list) else [0.7 * lenm, 1.3 * lenm]
    widm = widm if isinstance(widm, list) else [0.7 * widm, 1.3 * widm]
    ang0, spread = math.radians(float(o.get("angle", 90))), math.radians(float(o.get("spread", 25)))
    taper = float(o.get("taper", 0.6))
    levels = int(o.get("levels", 0))
    levels = levels if levels >= 2 else 0
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
        if levels:  # (a painter's few mixed tones, not a continuum: a continuum of dab tones read as noise)
            tv = lo + (hi - lo) * np.round(np.clip((tv - lo) / max(hi - lo, 1e-9), 0, 1) * (levels - 1)) / (levels - 1)
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


def op_tufts(n, L, o, seed):
    """Hand-drawn tufts: `per_m2` marks, each `blades` short tapered strokes fanning up from one base point (`length`,
    `width` m, `fan` deg either side), in a dark ink `tone`: cartoon grass, Wind Waker's tick marks."""
    rng = np.random.default_rng(seed)
    px = n / L
    N = int(float(o.get("per_m2", 1.0)) * L * L)
    tone = np.zeros((n, n))
    alpha = np.zeros((n, n))
    lo, hi = o.get("blades", [2, 4])
    fan = math.radians(float(o.get("fan", 30)))
    lm, wm = float(o.get("length", 0.15)), float(o.get("width", 0.02))
    tv = float(o.get("tone", -1.0))
    for _ in range(N):
        bx, by = rng.random(2) * n
        k = int(rng.integers(lo, hi + 1))
        for b in range(k):
            a = math.pi / 2 + (b - (k - 1) / 2) / max((k - 1) / 2, 1) * fan + rng.normal(0, 0.1)
            ln = lm * rng.uniform(0.7, 1.2) * px / 2
            wd = wm * px / 2
            cx, cy = bx + math.cos(a) * ln, by + math.sin(a) * ln  # (the stroke's middle: it starts at the base)
            r = int(ln + wd + 2)
            ii, jj = np.mgrid[int(cy) - r:int(cy) + r + 1, int(cx) - r:int(cx) + r + 1]
            dx, dy = jj - cx, ii - cy
            u = (dx * math.cos(a) + dy * math.sin(a)) / max(ln, 1e-6)
            v = (-dx * math.sin(a) + dy * math.cos(a)) / max(wd, 1e-6)
            w_ = np.clip(1 - (u + 1) / 2 * 0.9, 0.1, 1)  # (full at the base, a point at the tip)
            m = np.clip((1 - u * u - (v / w_) ** 2) * 3, 0, 1) * (np.abs(u) <= 1)
            sl = (ii % n, jj % n)
            alpha[sl] = np.maximum(alpha[sl], m)
    tone = tv * alpha
    return tone, alpha - alpha.mean()


def op_bands(n, L, o, seed):
    """Horizontal strata (rows = up): bands `thickness` [lo, hi] m filling the texture's height exactly, tones cycling
    through `tones`, edges `edge` m soft, rows wavering `wave` m; each band proud or set back by its tone (height).
    Along the strike (columns) the strata need not stay even: `pinch` (each band's thickness wanders by that share
    over `pinch_len` m: strata swell and thin), `breaks` (share of each band's length where it wedges out to nothing,
    its neighbours closing over it, in lenses `break_len` m long) and `vary` (each band's tone strength wanders by
    that share over `vary_len` m). Every wander is periodic along u (the texture tiles); the bands fill the height."""
    rng = np.random.default_rng(seed)
    lo, hi = o.get("thickness", [0.3, 1.2])
    th = []
    while sum(th) < L:
        th.append(rng.uniform(lo, hi))
    th = np.array(th) * (L / sum(th))
    nb = len(th)
    tones = o.get("tones", [-0.8, 0.2, 0.9, -0.2])
    bt = np.array([tones[i % len(tones)] for i in range(nb)]) + rng.normal(0, float(o.get("jitter", 0.1)), nb)
    t = (np.arange(n) + 0.5) * (L / n)
    wave = band_noise(n, max(1.0, L / float(o.get("wave_len", 3.0))), seed + 1)[0] * float(o.get("wave", 0.08))
    # (rows: v up; columns: u. Shifted half the first band: an edge on the wrap row was a seam line every tile)
    V = (t[:, None] + wave[None, :] + 0.5 * th[0]) % L
    e = max(float(o.get("edge", 0.02)), 1e-4)
    pinch, vary, brk = float(o.get("pinch", 0.0)), float(o.get("vary", 0.0)), float(o.get("breaks", 0.0))
    W = np.repeat(th[:, None], n, 1)  # (each band's thickness along u)
    if pinch > 0:
        W = W * (1 + min(pinch, 0.95) * noise_rows(n, max(1.0, L / float(o.get("pinch_len", 8.0))), seed + 2, nb))
    if brk > 0:  # (a lens: the band thins to nothing over a stretch and comes back; tapering, never a vertical edge)
        Bn = noise_rows(n, max(1.0, L / float(o.get("break_len", 6.0))), seed + 4, nb)
        cut = np.quantile(Bn, brk, axis=1)[:, None]
        B = np.clip((Bn - cut) / 1.2, 0, 1)
        W = W * (B * B * (3 - 2 * B))
    # each edge moves by half the change of the bands either side, so a band's change is taken up by its two
    # neighbours (a cumulative sum let the changes random-walk: whole stacks of strata swung metres up and down)
    dW = W - th[:, None]
    d = np.zeros((nb + 1, n))
    d[1:-1] = 0.5 * (dW[:-1] - dW[1:])
    E = np.concatenate([[0], np.cumsum(th)])[:, None] + d
    E = np.clip(np.maximum.accumulate(E, 0), 0.0, L)  # (edges never cross)
    S = np.ones((nb, n))
    if vary > 0:
        S = 1 - vary * (0.5 - 0.5 * noise_rows(n, max(1.0, L / float(o.get("vary_len", 8.0))), seed + 3, nb))
    tone = np.zeros((n, n))
    hgt = np.zeros((n, n))
    step = float(o.get("step", 1.0))
    for k in range(nb):
        a, b = E[k][None, :], E[k + 1][None, :]
        inside = np.clip((V - a) / e + 0.5, 0, 1) * np.clip((b - V) / e + 0.5, 0, 1)
        if k == 0:  # (the wrap: the first band also continues past the last edge)
            inside = np.maximum(inside, np.clip((V - (L + a)) / e + 0.5, 0, 1))
        v = inside * bt[k] * S[k][None, :]
        tone += v
        hgt += v * step
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
    """Discs `size` [lo, hi] m, `per_m2`, each a tone in `tones`: pebbles, flecks, flowers seen from above.
    `clusters` [per_m2, radius m]: the dots gathered in clumps (a patch of daisies) instead of strewn evenly."""
    rng = np.random.default_rng(seed)
    px = n / L
    N = int(float(o.get("per_m2", 20)) * L * L)
    lo, hi = o.get("size", [0.02, 0.06])
    tl, th_ = o.get("tones", [-1.0, 1.0])
    tone = np.zeros((n, n))
    hgt = np.zeros((n, n))
    if o.get("clusters"):
        cn, cr = o["clusters"]
        C = rng.random((max(1, int(round(float(cn) * L * L))), 2)) * n
        pos = C[rng.integers(0, len(C), N)] + rng.normal(0, float(cr) * px, (N, 2))
    else:
        pos = None
    for q in range(N):
        cx, cy = rng.random(2) * n if pos is None else pos[q] % n
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
    h = h - h.mean()
    return tone, h / max(float(np.abs(h).max()), 1e-9)  # (-1..1: `height` is the planes' amplitude in m)


OPS = {"blotch": op_blotch, "pillow": op_pillow, "strokes": op_strokes, "tufts": op_tufts, "bands": op_bands, "ripples": op_ripples,
       "dots": op_dots, "grain": op_grain, "cracks": op_cracks, "facets": op_facets}


def _seed(*parts):
    return int(hashlib.sha1("/".join(map(str, parts)).encode()).hexdigest()[:8], 16) % 1_000_000


def texture(st: dict, layer: str, colour_srgb, px: int = PX, plain: bool = False) -> dict:
    """One style's tileable texture for a layer: {"albedo" (n, n, 3) sRGB 0..1 (linear mean = the colour), "height" m,
    "normal" (n, n, 3) tangent (+x along the image's x, +y up the image), "size_m", "projection"}. Rows run up.
    An op with `"paint": sRGB` lays that colour where it marks (|tone| x `albedo` as coverage: flowers, a pale tick)
    instead of shading the layer's own colour. plain=True: without the ops marked `"fade_small": true` (what the engine
    shows on small or thin rock, by the manifest's `rock_scale` map)."""
    L = layer_sheet(st, layer)
    size = float(L.get("scale_m", 4.0))
    n = int(px)
    tone = np.zeros((n, n))
    hgt = np.zeros((n, n))
    paints = []
    for k, o in enumerate(L.get("ops") or []):
        fn = OPS.get(o.get("op"))
        if fn is None:
            raise ValueError(f"style {st['name']}: layer {layer}: unknown op {o.get('op')!r} (ops: {', '.join(OPS)})")
        if plain and o.get("fade_small"):
            continue
        t, h = fn(n, size, o, _seed(st["name"], layer, k, o.get("seed", 0)))
        if o.get("paint") is not None:
            paints.append((np.clip(np.abs(t), 0, 1) * float(o.get("albedo", 1.0)), _srgb_lin(o["paint"])))
        else:
            tone += float(o.get("albedo", 0.0)) * t
        hgt += float(o.get("height", 0.0)) * h
    base = _srgb_lin(colour_srgb)
    warm = np.array(L.get("warm", [1, 1, 1]), float)
    cool = np.array(L.get("cool", [1, 1, 1]), float)
    tp, tn = np.clip(tone, 0, None)[..., None], np.clip(-tone, 0, None)[..., None]
    tint = 1 + tp * (warm - 1) + tn * (cool - 1)
    lin = base * np.clip(1 + tone, 0.05, None)[..., None] * tint
    for m, c in paints:
        lin = lin * (1 - m[..., None]) + c * m[..., None]
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
    return Hf, thick


# ------------------------------------------------------------------------------------------------ rock shape (geometry)

ROCK_BAND = 10.0  # m: the default band over which one style's rock shape hands over to the next (in the field)
ROCK_KEYS = {"relief", "pillow", "soften_m", "fallen", "micro", "band_m", "kind", "stack", "lip"}


def rock_styles(T) -> list[dict]:
    """The styles whose sheet shapes the rock (`rock` with any of relief / pillow / soften_m / fallen / micro), each
    {"name", "w": weight grid on the terrain's cells (the zone partition with the rock's band, 0..1), "rock": the
    numbers}. [] when no style shapes rock: the field is then exactly the unstyled one."""
    styles = resolve(T.spec)
    shaped = []
    for s in styles:
        R = s["sheet"].get("rock") or {}
        bad = set(R) - ROCK_KEYS
        if bad:
            raise ValueError(f"style {s['name']}: rock keys {sorted(bad)} unknown ({', '.join(sorted(ROCK_KEYS))})")
        if set(R) - {"kind", "band_m", "stack"}:  # (a sea stack's form is read by stack_form, not by the field)
            shaped.append(s)
    if not shaped:
        return []
    geo = [{**s, "band": float((s["sheet"].get("rock") or {}).get("band_m", ROCK_BAND))} for s in styles]
    F = style_fields(T, geo)
    return [{"name": s["name"], "w": np.ascontiguousarray(F["w"][s["name"]], float), "rock": s["sheet"]["rock"]}
            for s in shaped]


def stack_form(T, xy) -> dict:
    """The sea stack form overrides (terrain_stack.FORM keys) at a stack's centre: the `rock.stack` of the style whose
    zone weighs over half there (a stack is one rock: it takes one style's form whole), else {} (realistic)."""
    styles = resolve(T.spec)
    if not any((s["sheet"].get("rock") or {}).get("stack") for s in styles):
        return {}
    geo = [{**s, "band": float((s["sheet"].get("rock") or {}).get("band_m", ROCK_BAND))} for s in styles]
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
    # (against the mean step between ALL neighbouring rows / columns: against the one row beside it, a sparse texture
    # with a pebble on the seam read 4x)
    beside = np.abs(np.diff(a, axis=0)).mean() + np.abs(np.diff(a, axis=1)).mean()
    q = 1.0 / 255  # (steps under an 8-bit level are invisible: a flat blobby swatch's 1e-4 steps read 1.7 as noise)
    return round(float((seam + q) / (beside + q)), 3)


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
        has_plain = any(o.get("fade_small") for o in (Ls.get("ops") or []))
        kinds = ("albedo", "normal", "height") + (("plain_albedo", "plain_normal") if has_plain else ())
        meta = None
        if kd is not None and (kd / "meta.json").exists():  # (the PNGs as made before: identical bytes)
            meta = json.loads((kd / "meta.json").read_text())
            for k in kinds:
                shutil.copyfile(kd / f"{k}.png", out / f"materials/{st['name']}/{nm}_{k}.png")
        if meta is None:
            S = texture(st, nm, col, px)
            hr = float(max(np.abs(S["height"]).max(), 1e-5))
            imgs = [("albedo", _q8(S["albedo"])), ("normal", _q8(S["normal"] * 0.5 + 0.5)),
                    ("height", _q16(S["height"] / hr * 0.5 + 0.5))]
            if has_plain:
                Sp = texture(st, nm, col, px, plain=True)
                imgs += [("plain_albedo", _q8(Sp["albedo"])), ("plain_normal", _q8(Sp["normal"] * 0.5 + 0.5))]
            for k, a in imgs:
                _png(out / f"materials/{st['name']}/{nm}_{k}.png", a[::-1],
                     "I;16" if a.dtype == np.uint16 else None)  # (image rows run down)
            meta = {"size_m": S["size_m"], "projection": S["projection"], "height_m": round(hr, 5),
                    "roughness": S["roughness"], "wrap_seam": max(tileable(S["albedo"]),
                                                                  tileable(Sp["albedo"]) if has_plain else 0.0)}
            if kd is not None:
                try:
                    kd.mkdir(parents=True, exist_ok=True)
                    for k in kinds:
                        shutil.copyfile(out / f"materials/{st['name']}/{nm}_{k}.png", kd / f"{k}.png")
                    (kd / "meta.json").write_text(json.dumps(meta))
                except OSError:
                    pass
        files = {k: f"materials/{st['name']}/{nm}_{k}.png" for k in ("albedo", "normal", "height")}
        res[nm] = {**files, **{k: meta[k] for k in ("size_m", "projection", "height_m")},
                   "color": [round(float(x), 4) for x in col],
                   "color_linear": [round(float(x), 4) for x in _srgb_lin(col)],
                   "roughness": meta["roughness"], "normal_strength": float(Ls.get("normal_strength", 1.0)),
                   "v_jitter_m": float(Ls.get("v_jitter_m", 0.0)) if meta["projection"] == "triplanar" else 0.0,
                   "seasons": season_colours(st, nm, col), "wrap_seam": meta["wrap_seam"]}
        if has_plain:  # (the layer without its fade_small ops: shown on small or thin rock, by maps.rock_scale)
            fade = {**SMALL_FADE, **(Ls.get("small_fade") or {})}
            res[nm]["small"] = {"albedo": f"materials/{st['name']}/{nm}_plain_albedo.png",
                                "normal": f"materials/{st['name']}/{nm}_plain_normal.png",
                                "face_m": fade["face_m"], "thick_m": fade["thick_m"]}
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
    if getattr(T, "H", None) is not None:  # (how big the rock is: where `fade_small` ops give way to plain textures)
        Hf, thick = rock_scale(T)
        rg = np.stack([Hf / ROCK_SCALE["face_m"], thick / ROCK_SCALE["thick_m"], np.zeros_like(Hf)], -1)
        _png(out / "styles/rock_scale.png", _q8(rg)[::-1])
        maps["rock_scale"] = "styles/rock_scale.png"
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
                        "layer_edge": layer_edge(st),
                        "layers": lay, "snow": snow_numbers(st), "rock": st.get("rock") or {}})
    return {"contract": {"version": CONTRACT, "changes": {str(k): v for k, v in CONTRACT_LOG.items()}},
            "order": order, "styles": entries,
            "maps": {"sd": maps["sd"], "weights": maps["weights"], "range_m": SD_RANGE,
                     "rock_scale": ({"file": maps["rock_scale"], "face_m": ROCK_SCALE["face_m"],
                                     "thick_m": ROCK_SCALE["thick_m"],
                                     "how": "RGB 8-bit, linear, the same grid as the sd maps: face height = R x face_m, "
                                            "half-thickness in plan = G x thick_m (metres)"}
                                    if maps.get("rock_scale") else None),
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


def season_sheet(styles: list[dict], refs: dict, layers, path, px: int = 160) -> Path:
    """Rows: style x layer; columns: spring, summer, autumn, winter, snow (by the snow numbers on a flat ground: the
    coverage's share of the texture whitened where its own normal faces up most). Lit with a low sun."""
    from PIL import Image, ImageDraw
    cols = list(SEASONS) + ["snow"]
    rows = [(st, nm) for st in styles for nm in layers]
    W, H = 200 + len(cols) * (px + 4), 24 + len(rows) * (px + 4)
    im = Image.new("RGB", (W, H), (32, 32, 34))
    dr = ImageDraw.Draw(im)
    for c, se in enumerate(cols):
        dr.text((200 + c * (px + 4) + 4, 6), se, fill=(230, 230, 230))
    for r, (st, nm) in enumerate(rows):
        y = 24 + r * (px + 4)
        dr.text((8, y + px // 2), f"{st['name']} {nm}", fill=(240, 240, 240))
        col = layer_colour(st, nm, refs)
        S = texture(st, nm, col, 256)
        sc = season_colours(st, nm, col)
        sn = snow_numbers(st)
        for c, se in enumerate(cols):
            lin = S["albedo_linear"] * np.array(sc[se if se != "snow" else "winter"]["tint_linear"])
            if se == "snow":
                up = S["normal"][..., 2]
                b = sn["by_normal"]
                f = np.clip((up - (1 - sn["coverage"] * 0.3) - b["from"]) / max(b["to"] - b["from"], 1e-6), 0, 1)
                f = np.clip(sn["coverage"] + 0.5 * (f - 0.5), 0, 1) * float((sn["layers"] or {}).get(nm, 1.0))
                lin = lin * (1 - f[..., None]) + np.array(sn["color_linear"]) * f[..., None]
            l = np.array([-0.5, 0.45, 0.75])
            l /= np.linalg.norm(l)
            ndl = np.clip((S["normal"] * l).sum(-1), 0, 1)
            img = _lin_srgb(lin * (0.25 + 0.75 * ndl)[..., None])
            pim = Image.fromarray(_q8(img[::-1])).resize((px, px), Image.LANCZOS)
            im.paste(pim, (200 + c * (px + 4), y))
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


# ------------------------------------------------------------------------------------------------ the game's view

def _pyramid(img):
    """Box-filtered mip levels of a periodic (n, n, c) image (n a power of two), as a GPU's mipmaps."""
    lv = [img]
    while lv[-1].shape[0] > 4:
        a = lv[-1]
        lv.append(0.25 * (a[0::2, 0::2] + a[1::2, 0::2] + a[0::2, 1::2] + a[1::2, 1::2]))
    return lv


def _sample(lv, u, v, lod):
    """Trilinear sample of a pyramid at periodic uv (0..1 = one tile; rows run up) and per-point level."""
    lod = np.clip(lod, 0, len(lv) - 1)
    l0 = np.floor(lod).astype(int)
    f = (lod - l0)[..., None]
    out = np.zeros(u.shape + (lv[0].shape[2],))

    def bil(a, uu, vv):
        n = a.shape[0]
        x, y = uu * n - 0.5, vv * n - 0.5
        x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
        fx, fy = (x - x0)[..., None], (y - y0)[..., None]
        x0, y0, x1, y1 = x0 % n, y0 % n, (x0 + 1) % n, (y0 + 1) % n
        return ((a[y0, x0] * (1 - fx) + a[y0, x1] * fx) * (1 - fy) + (a[y1, x0] * (1 - fx) + a[y1, x1] * fx) * fy)

    for k in np.unique(l0):
        m = l0 == k
        a = bil(lv[k], u[m], v[m])
        b = bil(lv[min(k + 1, len(lv) - 1)], u[m], v[m])
        out[m] = a * (1 - f[m]) + b * f[m]
    return out


def ground_view(styles: list[dict], refs: dict, path, layers=("grass", "earth"), size=(560, 315), px: int = 1024,
                light: str = "game") -> Path:
    """What the ground looks like in the game, per style: a row of eye-level views (1.7 m up, looking along a gently
    curving path of the second layer through the first) and views from 25 m up, 40 deg down. The ground is flat, so
    only the textures, their layer edges (`layer_edge`) and mipmaps show: lit as the game's cel styles light flat ground
    (light "game": albedo x (sun band + flat ambient), no specular), sampled through mip levels as a GPU does. A stand-in
    for the baked macro colour (realistic's 60 / 15 m colour patches) is applied by each style's `macro`."""
    from PIL import Image, ImageDraw
    W, Hh = size
    fov = math.radians(70.0)
    cams = [("eye 1.7 m", 1.7, math.radians(-6.0)), ("25 m up", 25.0, math.radians(-40.0))]
    tiles = []
    for st in styles:
        tex = []
        for nm in layers:
            S = texture(st, nm, layer_colour(st, nm, refs), px)
            hr = max(float(np.abs(S["height"]).max()), 1e-6)
            tex.append((S["size_m"], _pyramid(np.concatenate([S["albedo_linear"], (S["height"] / hr)[..., None]], -1))))
        row = []
        for title, h, pitch in cams:
            jj, ii = np.meshgrid(np.arange(W) + 0.5, np.arange(Hh) + 0.5)
            t = math.tan(fov / 2)
            x = (2 * jj / W - 1) * t
            y = (1 - 2 * ii / Hh) * t * Hh / W
            # camera looking +y, pitched down
            dy = math.cos(pitch) - y * math.sin(pitch)
            dz = math.sin(pitch) + y * math.cos(pitch)
            dx = x
            hit = dz < -1e-4
            tt = np.where(hit, -h / np.minimum(dz, -1e-4), 0.0)
            px_ang = 2 * t / W
            dn = np.sqrt(dx * dx + dy * dy + dz * dz)
            Xw, Yw = dx * tt, dy * tt
            dist = tt * dn
            graze = np.clip(-dz / dn, 0.02, 1)
            across = dist * px_ang
            foot = across * np.sqrt(np.minimum(1 / graze, 8.0))  # (anisotropic filtering takes some of the stretch)
            # the second layer as a curving path 3 m wide, soft over ~1 m as the tiles' weight maps are
            cx = 2.5 * np.sin(Yw / 9.0) + 1.0
            we = np.clip((1.9 - np.abs(Xw - cx)) / 1.0 + 0.5, 0, 1)
            we = we * we * (3 - 2 * we)
            Wl = np.stack([1 - we, we]) if len(layers) == 2 else np.ones((1,) + Xw.shape)
            cols, hts = [], []
            for (L, lv) in tex:
                lod = np.log2(np.maximum(foot / (L / px), 1e-6))
                # the recipe's anti-tiling: a second sampling at uv / 1.618 + (0.37, 0.71), chosen by patches ~3 tiles
                pick = (np.sin(Xw / (0.9 * L) + np.sin(Yw / (1.3 * L))) * np.sin(Yw / (1.1 * L) + 0.5)) > 0
                s = _sample(lv, Xw / L, Yw / L, lod)
                s2 = _sample(lv, Xw / L / 1.618 + 0.37, Yw / L / 1.618 + 0.71, lod - math.log2(1.618))
                s = np.where(pick[..., None], s2, s)
                cols.append(s[..., :3])
                hts.append(s[..., 3])
            Wl = edge_weights(Wl, np.stack(hts), layer_edge(st))
            col = sum(Wl[k][..., None] * cols[k] for k in range(len(cols)))
            # the baked macro colour's variation (realistic's broad patches), kept by `macro`
            n1 = np.sin(Xw / 9.3 + 1.3 * np.sin(Yw / 13.0)) * np.sin(Yw / 11.7 + 0.7 * np.sin(Xw / 7.0))
            n2 = np.sin(Xw / 31.0 + 2.0) * np.sin(Yw / 27.0 + 0.4)
            var = 1 + 0.10 * n1 + 0.07 * n2
            col = col * (1 + float(st.get("macro", 1.0)) * (var - 1))[..., None]
            if light == "game":
                # (flat ground: fully in the sun band, the flat ambient on top, no specular: one factor)
                col = col * 0.92
            sky = np.array([0.42, 0.52, 0.66])
            haze = 1 - np.exp(-dist / 900.0)
            col = col * (1 - haze[..., None]) + sky * haze[..., None]
            img = np.where(hit[..., None], col, sky)
            im = Image.fromarray(_q8(_lin_srgb(img)))
            ImageDraw.Draw(im).text((6, 4), f"{st['name']}: {title}", fill=(255, 255, 255))
            row.append(im)
        tiles.append(row)
    out = Image.new("RGB", (W * len(cams) + 4 * (len(cams) - 1), Hh * len(styles) + 4 * (len(styles) - 1)), (30, 30, 30))
    for r, row in enumerate(tiles):
        for c, im in enumerate(row):
            out.paste(im, (c * (W + 4), r * (Hh + 4)))
    path = Path(path)
    out.save(path)
    return path
