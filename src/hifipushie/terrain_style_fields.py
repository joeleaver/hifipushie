"""Periodic fields: band noise, Worley, the pattern ops (blotch, pillow, strokes, tufts, bands, ripples, dots,
grain, cracks, facets, stones), `texture`, `overlay`. Part of the terrain styles (terrain_style.py has the overview)."""
from __future__ import annotations

import hashlib
import math

import numpy as np
from scipy import ndimage

from . import terrain_style
from .terrain_style import _lin_srgb, _srgb_lin, layer_sheet

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


def _discs(n, L, size, seed, jitter, gap):
    """Round stones on the L x L torus: seeds about `size` m apart (a jittered grid), each a disc as big as its
    nearest neighbour allows (so sizes vary and none overlap). Returns (d: distance from the stone's centre over its
    radius (< 1 inside), id per texel, count)."""
    from scipy.spatial import cKDTree
    k = max(1, int(round(L / size)))
    rng = np.random.default_rng(seed)
    g = (np.arange(k) + 0.5) / k * L
    sx, sy = np.meshgrid(g, g)
    pts = np.c_[sx.ravel(), sy.ravel()] + (rng.random((k * k, 2)) - 0.5) * jitter * L / k
    allp = np.concatenate([pts + np.array([dx, dy]) * L for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
    tree = cKDTree(allp)
    nn = tree.query(pts, k=2)[0][:, 1]
    r = np.minimum(0.5 * nn * (1 - gap), 0.62 * L / k)
    t = (np.arange(n) + 0.5) * (L / n)
    X, Y = np.meshgrid(t, t)
    d, i = tree.query(np.c_[X.ravel(), Y.ravel()])
    cid = (i % (k * k)).reshape(n, n)
    return d.reshape(n, n) / np.maximum(r[cid], 1e-6), cid, k * k


def op_stones(n, L, o, seed):
    """Rounded stones about `size` m apart (a pebble or cobble bed, seen from above), smaller ones (`fill` x the size)
    in the gaps between: each a dome with its own tone (`vary`), dark gravel between (`gap`, a share of the size;
    `gap_tone`); `dome` lights each stone's top against its foot; `flat` 0..1 flattens the domes' tops (painted
    stones); `outline` (a share of a stone's radius) draws an ink ring inside each stone's edge (cartoon); `steps`
    quantises the stones' tones; `bare` = the share of seeds left without a stone."""
    size = float(o.get("size", 0.15))
    gap = float(o.get("gap", 0.07))
    rng = np.random.default_rng(seed + 3)
    tone = np.full((n, n), -float(o.get("gap_tone", 0.8)))
    hgt = np.zeros((n, n))
    ol = float(o.get("outline", 0.0))
    flat = float(o.get("flat", 0.0))
    for lev, (sz, amp) in enumerate(((size * float(o.get("fill", 0.45)), 0.5), (size, 1.0))):
        if sz <= 0 or sz < 2.5 * L / n:
            continue
        d, cid, k = _discs(n, L, sz, seed + 11 * lev, float(o.get("jitter", 0.95)), gap)
        has = rng.random(k) >= float(o.get("bare", 0.0)) * (1.0 if lev else 0.3)
        tc = rng.uniform(-1, 1, k)
        if o.get("steps"):
            tc = _steps(tc, int(o["steps"]), 0.0)
        inside = (d < 1) & has[cid]
        dome = np.sqrt(np.clip(1 - d * d, 0, 1))
        dome = dome * (1 - flat) + flat * np.clip(dome * 3, 0, 1)
        t = tc[cid] * float(o.get("vary", 0.5)) + float(o.get("dome", 0.3)) * (dome - 0.7)
        if ol > 0:
            t = np.where(d > 1 - ol, -1.0, t)
        m = np.clip((1 - d) * sz * (n / L) * 0.5, 0, 1) * inside  # (an edge a couple of texels soft)
        tone = tone * (1 - m) + t * m
        hgt = np.maximum(hgt, amp * dome * inside)
    return np.clip(tone, -1, 1), hgt


OPS = {"stones": op_stones, "blotch": op_blotch, "pillow": op_pillow, "strokes": op_strokes, "tufts": op_tufts, "bands": op_bands, "ripples": op_ripples,
       "dots": op_dots, "grain": op_grain, "cracks": op_cracks, "facets": op_facets}


def _seed(*parts):
    return int(hashlib.sha1("/".join(map(str, parts)).encode()).hexdigest()[:8], 16) % 1_000_000


def texture(st: dict, layer: str, colour_srgb, px: int = terrain_style.PX, plain: bool = False) -> dict:
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
