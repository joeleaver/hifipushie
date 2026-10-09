"""Tiling micro-relief swatches for skin, generated here (no scans): the fine detail a unique texture can't hold
(the user's rule, as for rock in terrain_swatch.py: unique maps carry the macro, tiling maps the fine detail).

Each swatch is a periodic DEPTH map (0 = the skin's surface, 1 = the bottom of the deepest furrow or pore; 16 bit,
SIZE px across PERIOD metres of skin), used by paint's "tile" generator: a layer's negative "height" x the swatch is
the relief, the same mask darkens and roughens the furrows. What they model (dermatology: the skin's microrelief is
polygonal plateaus bounded by furrows; primary lines 20-100 um deep, secondary 5-40 um; facial pores 0.2-0.5 mm
across, 10-90 per cm2):

  pores   the face: pores as pits (a clustered Poisson set, each its own size and depth, some drawn out along the
          skin's lines), joined by a faint net of furrows, and fine secondary lines between.
  lines   the body (neck, arms, backs of hands, torso): two families of nearly parallel furrows crossing at an angle
          (rhomboids ~1 mm, longer along the skin's tension), each furrow fading in and out, a finer generation
          between, a pore here and there. Not a net of closed cells (`_glyphics`).
  coarse  knuckles, elbows, knees, heels, old skin: the same, deeper and ~1.7 mm apart.
  lips    lip skin: creases running one way (the caller lays it vertical), cut by a few cross lines.
Marks (1 = the mark, the same way: a mask):
  stubble   cut hairs as dots, 0.1-0.2 mm, ~200 per cm2, uneven.
  freckles  macules of 0.6-3 mm, most small and faint, a few large, in loose clusters.
  wrinkles  wandering lines ~7 mm apart running across the swatch (u), breaking and joining: forehead lines,
            neck rings; turned a quarter turn, the lines above the lip.
  hairs     fine hairs lying one way (along v), 3-6 mm long: body hair.

`make(kind)` returns the PNG's path in the content store (workspace/_images/skin_<kind>_<version>.png) and
`depth(kind)` the array; `normal_map(kind, depth_m)` writes a tangent-space normal map from it for engines (the
export's tiling detail normal).
"""
from __future__ import annotations

import numpy as np

VERSION = 13
SIZE = 1024
PERIOD = {"pores": 0.016, "lines": 0.016, "coarse": 0.024, "lips": 0.012, "stubble": 0.012, "freckles": 0.06,
          "wrinkles": 0.05, "hairs": 0.02}  # m of skin across the swatch
KINDS = tuple(PERIOD)
_CACHE: dict = {}


def _grid():
    u = (np.arange(SIZE) + 0.5) / SIZE
    return np.stack(np.meshgrid(u, u, indexing="xy"), -1).reshape(-1, 2)


def _seeds(rng, n: int, min_d: float = 0.0) -> np.ndarray:
    """n points on the unit torus: a jittered grid (even, never clumped into a visible repeat)."""
    k = int(np.ceil(np.sqrt(n)))
    g = (np.stack(np.meshgrid(np.arange(k), np.arange(k)), -1).reshape(-1, 2) + rng.uniform(0.08, 0.92, (k * k, 2))) / k
    return g[rng.permutation(len(g))[:n]]


def _voronoi(pts: np.ndarray, seeds: np.ndarray, stretch: float = 1.0, k: int = 2):
    """Distances to the k nearest seeds on the torus (in swatch units), the lookup squashed `stretch` along y (cells
    come out that much longer along y), and the nearest seed's index."""
    from scipy.spatial import cKDTree
    if stretch == 1.0:
        d, i = cKDTree(seeds, boxsize=1.0).query(pts, k=k)
        return d, i[:, 0]
    s = np.array([1.0, 1.0 / stretch])
    d, i = cKDTree(seeds * s, boxsize=s).query(pts * s, k=k)
    return d, i[:, 0]


def _edges(pts, seeds, width: float, stretch: float = 1.0) -> np.ndarray:
    """1 on the borders between cells falling to 0 `width` (swatch units) away: a net of furrows."""
    d, _ = _voronoi(pts, seeds, stretch)
    t = np.clip((d[:, 1] - d[:, 0]) / width, 0, 1)
    return (1 - t) ** 2


def _smooth_noise(rng, cells: int, cells_u: int | None = None) -> np.ndarray:
    """Periodic smooth noise 0..1 with `cells` features across (random lattice, interpolated by FFT zoom); cells_u:
    another count along u (features longer one way)."""
    cu = cells_u or cells
    f = np.fft.rfft2(rng.standard_normal((cells, cu)))
    big = np.zeros((SIZE, SIZE // 2 + 1), complex)
    h, hu = max(cells // 2, 1), max(cu // 2, 1)
    big[:h, :hu + 1] = f[:h, :hu + 1]
    big[-h:, :hu + 1] = f[-h:, :hu + 1]
    z = np.fft.irfft2(big, s=(SIZE, SIZE))
    z = (z - z.min()) / max(float(np.ptp(z)), 1e-12)
    return z.reshape(-1)


def _pits(pts, rng, n: int, r_mm: tuple, period_mm: float, stretch: float = 1.0, clump=None) -> np.ndarray:
    """Pores: n pits, radius r_mm[0]..r_mm[1] each (a rounded cup, depth growing with its size)."""
    from scipy.spatial import cKDTree
    seeds = _seeds(rng, n)
    if clump is not None:  # keep more where the clump noise is high: pores come in patches
        keep = rng.uniform(0, 1, len(seeds)) < 0.35 + 0.65 * clump[(np.floor(seeds[:, 1] * SIZE).astype(int) % SIZE) * SIZE
                                                                + np.floor(seeds[:, 0] * SIZE).astype(int) % SIZE]
        seeds = seeds[keep]
    r = rng.uniform(r_mm[0], r_mm[1], len(seeds)) ** 1.0 / period_mm
    s = np.array([1.0, 1.0 / stretch])
    d, i = cKDTree(seeds * s, boxsize=s).query(pts * s, k=3)
    out = np.zeros(len(pts))
    for j in range(3):
        rr = r[i[:, j]]
        t = np.clip(d[:, j] / rr, 0, 1)
        out = np.maximum(out, (1 - t * t) ** 1.5 * (0.45 + 0.55 * rr / r.max()))
    return out


def _meso(rng) -> np.ndarray:
    """The grain between a pore and a wrinkle (follicle bumps, fine swelling at 0.5-3 mm): a gentle undulation of the
    surface under the furrows."""
    return 0.34 * (1 - _smooth_noise(rng, 14)) + 0.3 * (1 - _smooth_noise(rng, 6)) + 0.2 * (1 - _smooth_noise(rng, 30))


def _glyphics(rng, mm: float, fams) -> np.ndarray:
    """The skin's line pattern as it is: families of nearly parallel furrows crossing at an angle (rhomboids, longer
    one way: lines follow the skin's tension), every furrow deeper and shallower along its length and gone for
    stretches. Never a net of closed cells: each cell outlined all round at one depth is dried mud (the Voronoi net
    this replaced read so on old and dark faces). fams: (lines across u, lines across v, wander, patch cells, share
    of a line that is missing, half width mm, weight); the line counts are whole numbers, so it tiles."""
    P = _grid()
    u, v = P[:, 0], P[:, 1]
    wob = 0.05 * (_smooth_noise(rng, 4) - 0.5) + 0.014 * (_smooth_noise(rng, 13) - 0.5)
    out = np.zeros(len(P))
    for ku, kv, wk, cells, lo, width, weight in fams:
        n = float(np.hypot(ku, kv))
        ph = ku * u + kv * v + n * wk * wob
        dist = np.abs(ph - np.round(ph)) / n * mm
        amp = np.clip((_smooth_noise(rng, cells) - lo) / (1 - lo), 0, 1)
        amp = amp * amp * (3 - 2 * amp)
        w = width * (0.5 + 0.7 * amp)
        out = np.maximum(out, weight * np.clip(1 - dist / np.maximum(w, 1e-6), 0, 1) ** 1.5 * amp)
    return out


def brow_image(density: float = 0.8, thickness: float = 1.0, length_mm: float = 6.0, width_mm: float = 62.0,
               seed: int = 0, tail: float = 1.0, fall: float = 1.0):
    """A left eyebrow as hairs (RGBA PNG in the image store; white hairs, coverage in alpha: the layer gives the
    colour), inner end at the left: hairs grow up and out at the inner end, lie along the brow in its body and
    turn out and down in the tail; the band is thick inside and tapers. Returns (path, [width, height] in mm)."""
    from PIL import Image, ImageDraw
    from . import images
    key = f"{density:.3f}_{thickness:.3f}_{length_mm:.2f}_{width_mm:.1f}_{seed}_{tail:.2f}_{VERSION}" + \
        (f"_f{fall:.2f}" if fall != 1.0 else "")  # (fall: how far the tail drops past the arch, x the default)
    import hashlib
    out = images.store_dir() / f"brow_{hashlib.sha1(key.encode()).hexdigest()[:12]}.png"
    h_mm = 0.42 * width_mm
    if not out.exists():
        S = 4  # supersampling
        W = 1024
        H = int(W * h_mm / width_mm)
        ppm = W / width_mm  # px per mm
        im = Image.new("L", (W * S, H * S), 0)
        dr = ImageDraw.Draw(im)
        rng = np.random.default_rng(700 + seed)
        n = int(1150 * density * thickness)
        # the brow's spine: rises from the inner end to the arch (~62% along), then falls into the tail
        def spine(t):
            return 0.56 - 0.2 * np.sin(np.clip(t / 0.62, 0, 1) * np.pi / 2) + 0.3 * fall * np.clip((t - 0.62) / 0.38, 0, 1) ** 1.6
        def half(t):  # half thickness (share of H)
            return thickness * (0.03 + 0.14 * np.clip((t + 0.02) / 0.12, 0, 1) * (1 - 0.82 * np.clip((t - 0.25) / 0.75, 0, 1) ** 0.9))
        for _ in range(n):
            t = float(np.clip(rng.beta(1.25, 1.5) * (0.97 * tail) + 0.03, 0.02, 0.99))
            off = float(np.clip(rng.normal(0, 0.45), -1, 1))
            x = (0.04 + 0.92 * t) * W
            y = (spine(t) + off * half(t)) * H
            # direction (0 = along +x, 90 = up): fans from ~80 deg at the inner end to ~12 in the body to -25 in the tail;
            # hairs under the spine lean up toward it, hairs over it lean down
            ang = 82 * (1 - np.clip(t / 0.22, 0, 1)) ** 1.3 + 14 * np.clip(t / 0.22, 0, 1) - 42 * np.clip((t - 0.55) / 0.45, 0, 1)
            ang += 16 * off * np.clip(t / 0.3, 0, 1) + rng.normal(0, 7)
            L = length_mm * ppm * rng.uniform(0.6, 1.1) * (1 - 0.35 * np.clip((t - 0.6) / 0.4, 0, 1))
            curl = rng.normal(0, 10)
            pts, a = [(x, y)], np.radians(ang)
            for k in range(8):
                a2 = a + np.radians(curl - 9) * k / 8
                pts.append((pts[-1][0] + np.cos(a2) * L / 8, pts[-1][1] - np.sin(a2) * L / 8))
            w0 = rng.uniform(0.11, 0.17) * ppm  # root width, mm -> px
            for k in range(8):
                wk = w0 * (1 - 0.8 * k / 8)
                dr.line([(pts[k][0] * S, pts[k][1] * S), (pts[k + 1][0] * S, pts[k + 1][1] * S)],
                        fill=int(255 * (0.75 + 0.25 * rng.random())), width=max(int(round(wk * S)), 1))
        a = np.asarray(im.resize((W, H), Image.LANCZOS), np.float32) / 255.0
        rgba = np.dstack([np.ones((H, W, 3), np.float32), np.clip(a * 1.25, 0, 1)])
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp.png")
        Image.fromarray(np.round(rgba * 255).astype(np.uint8), "RGBA").save(tmp)
        tmp.replace(out)
    return out, [width_mm, h_mm]


def eye_image(iris, pupil: float = 0.36, veins: float = 0.4, sclera=(0.92, 0.89, 0.85), seed: int = 0, span: float = 2.1):
    """The front of an eyeball as a picture (RGB PNG in the image store), `span` iris diameters across: an iris of
    radial fibres with a paler collarette round the pupil, a dark limbal ring fading into the white, a soft-edged
    pupil (`pupil` = its share of the iris' radius); the sclera warmer and pinker toward its edge, with fine
    vessels wandering in from the corners (`veins`). iris: sRGB colour. Returns the path."""
    import hashlib
    from PIL import Image, ImageDraw, ImageFilter
    from . import images
    iris = tuple(round(float(c), 4) for c in iris)
    key = hashlib.sha1(repr((iris, pupil, veins, tuple(sclera), seed, span, VERSION)).encode()).hexdigest()[:12]
    out = images.store_dir() / f"eye_{key}.png"
    if out.exists():
        return out
    S = 1024
    rng = np.random.default_rng(900 + seed)
    y, x = np.mgrid[0:S, 0:S].astype(np.float64)
    cx = cy = (S - 1) / 2
    R = S / (2 * span)  # the iris' radius in px
    r = np.hypot(x - cx, y - cy) / R
    th = np.arctan2(y - cy, x - cx)
    # sclera: off-white, warmer and pinker outward
    t = np.clip((r - 1.0) / (span - 1.0), 0, 1)[..., None]
    img = np.asarray(sclera)[None, None] * (1 - 0.1 * t) + t * 0.16 * (np.array([0.9, 0.62, 0.58]) - np.asarray(sclera))
    # vessels: thin wandering lines from the rim inward, mostly at the sides (toward the corners)
    vim = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(vim)
    for _ in range(int(30 * veins)):
        a = rng.choice([0.0, np.pi]) + rng.normal(0, 0.5)
        rr, pts, drift = span * 0.99, [], rng.normal(0, 0.006)
        stop = rng.uniform(1.1, 1.7)
        while rr > stop:  # a vessel wanders inward, turning slowly, and forks once or twice
            pts.append((cx + rr * R * np.cos(a), cy + rr * R * np.sin(a)))
            rr -= 0.012
            drift = 0.92 * drift + rng.normal(0, 0.0035)
            a += drift
            if len(pts) > 15 and rng.random() < 0.02:
                a2, r2, d2, q = a, rr, -2.5 * drift + rng.choice([-1, 1]) * 0.012, []
                for _k in range(int(rng.uniform(10, 30))):
                    q.append((cx + r2 * R * np.cos(a2), cy + r2 * R * np.sin(a2)))
                    r2 -= 0.01
                    a2 += d2
                    d2 *= 0.97
                d.line(q, fill=int(rng.uniform(60, 130)), width=1)
        if len(pts) > 1:
            d.line(pts, fill=int(rng.uniform(80, 190)), width=int(rng.choice([1, 1, 2])))
    v = np.asarray(vim.filter(ImageFilter.GaussianBlur(1.1)), np.float64)[..., None] / 255.0
    img = img + 0.55 * v * (np.array([0.72, 0.2, 0.18]) - img)
    # iris: radial fibres (angular noise, slowly changing with radius), collarette, limbal ring
    c = np.asarray(iris, np.float64)
    n = 720
    fib = np.zeros((4, n))
    for k, (fr, amp) in enumerate(((90, 0.5), (37, 0.3), (240, 0.2), (13, 0.25))):
        ph = rng.uniform(0, 2 * np.pi, fr)
        g = rng.normal(0, 1, fr)
        ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
        fib[k] = amp * np.interp(ang, np.linspace(0, 2 * np.pi, fr, endpoint=False), g, period=2 * np.pi)
    ai = ((th + np.pi) / (2 * np.pi) * n).astype(int) % n
    twist = ((th + np.pi + 0.25 * r) / (2 * np.pi) * n).astype(int) % n
    f = fib[0][ai] + fib[1][twist] + fib[2][ai] * np.clip(r * 1.3, 0, 1) + fib[3][ai]
    f = np.clip(0.5 + 0.28 * f, 0, 1)
    col = c[None, None] * (0.55 + 0.9 * f[..., None])
    coll = np.exp(-0.5 * ((r - (pupil + 0.16)) / 0.09) ** 2)[..., None]  # the collarette: a paler, yellower ring
    col = col + coll * 0.45 * (np.clip(c * 1.5 + np.array([0.16, 0.1, 0.0]), 0, 1) - col)
    limb = np.clip((r - 0.78) / 0.2, 0, 1)[..., None] ** 1.5  # the limbal ring
    col = col * (1 - 0.72 * limb)
    edge = np.clip((1.04 - r) / 0.07, 0, 1)[..., None]  # iris into sclera, soft
    img = img * (1 - edge) + col * edge
    pup = np.clip((pupil - r) / 0.035 + 0.5, 0, 1)[..., None]
    img = img * (1 - pup) + pup * np.array([0.012, 0.01, 0.01])
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.png")
    Image.fromarray(np.round(np.clip(img, 0, 1) * 255).astype(np.uint8), "RGB").save(tmp)
    tmp.replace(out)
    return out


def depth(kind: str) -> np.ndarray:
    """(SIZE, SIZE) float 0..1 depth of the swatch (see the module docstring)."""
    if kind not in PERIOD:
        raise ValueError(f"skin swatch {kind!r}: one of {', '.join(KINDS)}")
    if kind in _CACHE:
        return _CACHE[kind]
    rng = np.random.default_rng(1234 + KINDS.index(kind))
    P = _grid()
    mm = PERIOD[kind] * 1000
    if kind == "pores":
        clump = _smooth_noise(rng, 6)
        big = _pits(P, rng, int(0.9 * mm * mm), (0.09, 0.2), mm, 1.25, clump)  # ~90/cm2 visible pores
        small = _pits(P, rng, int(4.5 * mm * mm), (0.035, 0.07), mm)  # the fine ones between
        net = _edges(P, _seeds(rng, int((mm / 0.75) ** 2)), 0.1 / mm, 1.3)  # faint primary lines joining pores
        fine = _edges(P, _seeds(rng, int((mm / 0.3) ** 2)), 0.05 / mm, 1.15)
        d = np.maximum(big, 0.45 * small) + 0.3 * net * (0.4 + 0.6 * _smooth_noise(rng, 10)) + 0.14 * fine
        d = d + _meso(rng)
    elif kind == "lines":
        prim = _glyphics(rng, mm, [(5, 16, 1.0, 7, 0.3, 0.13, 1.0), (-9, 13, 1.6, 9, 0.42, 0.11, 0.8)])
        sec = _glyphics(rng, mm, [(13, 38, 2.0, 14, 0.35, 0.05, 1.0), (-30, 24, 2.4, 12, 0.45, 0.05, 0.8)])
        pits = _pits(P, rng, int(1.6 * mm * mm), (0.04, 0.09), mm)
        d = 0.85 * prim + 0.3 * sec + 0.35 * pits
        d = d + _meso(rng)
    elif kind == "coarse":
        prim = _glyphics(rng, mm, [(4, 13, 1.0, 6, 0.28, 0.24, 1.0), (-8, 10, 1.7, 7, 0.4, 0.2, 0.85)])
        sec = _glyphics(rng, mm, [(12, 34, 2.0, 12, 0.35, 0.09, 1.0), (-27, 20, 2.4, 11, 0.45, 0.08, 0.8)])
        d = prim + 0.32 * sec + 0.12 * _smooth_noise(rng, 48)
    elif kind == "stubble":
        d = np.maximum(_pits(P, rng, int(1.9 * mm * mm), (0.06, 0.1), mm, 1.0, _smooth_noise(rng, 5)),
                       0.8 * _pits(P, rng, int(1.2 * mm * mm), (0.045, 0.075), mm))
        d = np.clip(d * 1.6, 0, 1) ** 0.7
    elif kind == "freckles":
        clump = _smooth_noise(rng, 5)
        d = 0.75 * _pits(P, rng, int(0.085 * mm * mm), (0.45, 1.0), mm, 1.15, clump) ** 0.6
        d = np.maximum(d, 0.5 * _pits(P, rng, int(0.2 * mm * mm), (0.25, 0.5), mm, 1.0, clump) ** 0.6)
        d = np.maximum(d, 1.0 * _pits(P, rng, int(0.012 * mm * mm), (0.9, 1.6), mm, 1.3, clump) ** 0.5)
        d = d * (0.55 + 0.45 * _smooth_noise(rng, 14))
    elif kind == "wrinkles":
        # Creases across u, as real ones lie: each varies in depth along its length and fades out at its ends (never a
        # ruled line), neighbours branch into each other, they sit in a broader undulation of the skin, and the skin
        # between them is finely creped the same way.
        u, v = P[:, 0], P[:, 1]
        wob = 0.05 * (_smooth_noise(rng, 4) - 0.5) + 0.014 * (_smooth_noise(rng, 13) - 0.5)

        def family(n, wob_k, shift, cells, lo, width):
            ph = (v + wob_k * wob + shift + 0.01 * np.sin(2 * np.pi * (u + shift))) * n
            dist = np.abs(ph - np.round(ph)) / n * mm  # mm to the nearest crease
            amp = np.clip((_smooth_noise(rng, cells, 2) - lo) / (1 - lo), 0, 1)  # a crease runs on for centimetres
            amp = amp * amp * (3 - 2 * amp)  # eases to nothing: the ends taper
            w = width * (0.45 + 0.75 * amp)  # deeper stretches are wider
            t = np.clip(1 - dist / np.maximum(w, 1e-6), 0, 1)
            return t * t * (3 - 2 * t) * amp  # a rounded trough: a V with a sharp floor is a scratch
        # (a forehead line is a soft valley 2-3 mm across between rolls of skin, not a cut 0.7 mm wide)
        main = family(6, 1.0, 0.0, 6, 0.22, 1.7)
        branch = family(6, 1.9, 0.083, 8, 0.45, 1.2)  # a neighbour wandering across: forks and joins
        fine = family(19, 2.6, 0.03, 12, 0.3, 0.3)
        swell = 0.5 + 0.5 * np.cos(2 * np.pi * 6 * (v + wob))  # the roll between two creases
        d = np.maximum(main, 0.7 * branch) + 0.14 * fine + 0.3 * (1 - swell) * (0.4 + 0.6 * _smooth_noise(rng, 3))
    elif kind == "hairs":
        n = SIZE
        img = np.zeros((n, n), np.float32)
        k = int(11 * (mm / 10) ** 2 * 10)
        x0, y0 = rng.uniform(0, n, k), rng.uniform(0, n, k)
        ln = rng.uniform(3.0, 6.0, k) / mm * n
        ang = rng.normal(0, 0.22, k)
        bend = rng.normal(0, 0.25, k)
        for s in np.linspace(0, 1, 90):
            a = ang + bend * s
            x = (x0 + np.sin(a) * ln * s).astype(int) % n
            y = (y0 - np.cos(a) * ln * s).astype(int) % n
            np.maximum.at(img, (y, x), (1 - s) ** 0.6 * (0.6 + 0.4 * np.sin(np.pi * min(s * 6, 1) / 2)))
        from scipy.ndimage import gaussian_filter as _gf
        d = _gf(img, 0.9, mode="wrap").reshape(-1)
        d = np.clip(d / max(float(np.percentile(d, 99.7)), 1e-9), 0, 1)
    else:  # lips: long creases along y, a few cross lines
        long_ = _edges(P, _seeds(rng, int((mm / 0.9) ** 2 / 5)), 0.16 / mm, 9.0)
        fine = _edges(P, _seeds(rng, int((mm / 0.4) ** 2 / 4)), 0.07 / mm, 6.0)
        cross = _edges(P, _seeds(rng, int((mm / 1.6) ** 2)), 0.1 / mm, 0.6)
        d = 0.9 * long_ * (0.5 + 0.5 * _smooth_noise(rng, 6)) + 0.4 * fine + 0.2 * cross
    d = np.clip(d, 0, None).reshape(SIZE, SIZE)
    from scipy.ndimage import gaussian_filter
    d = gaussian_filter(d, 0.8, mode="wrap")  # no 1-px creases: they alias under the bump
    _CACHE[kind] = (d / d.max()).astype(np.float32)
    return _CACHE[kind]


def make(kind: str):
    """The swatch as a 16-bit grey PNG in the image store; its path."""
    from PIL import Image
    from . import images
    out = images.store_dir() / f"skin_{kind}_{VERSION}.png"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp.png")
        Image.fromarray(np.round(depth(kind) * 65535).astype(np.uint16)).save(tmp)
        tmp.replace(out)
    return out


def normal_map(kind: str, depth_m: float, out=None):
    """A tangent-space normal map (8-bit RGB PNG, +Y up, glTF's convention) of the swatch `depth_m` deep at its
    deepest: the tiling detail normal an engine lays over the baked maps. Returns its path."""
    from PIL import Image
    from . import images
    h = -depth(kind).astype(np.float64) * depth_m
    px = PERIOD[kind] / SIZE
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) / (2 * px)
    gy = (np.roll(h, 1, 0) - np.roll(h, -1, 0)) / (2 * px)  # image rows run down: +v is up
    n = np.dstack([-gx, -gy, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    out = out or images.store_dir() / f"skin_{kind}_{VERSION}_n{int(round(depth_m * 1e6))}.png"
    Image.fromarray(np.round((n * 0.5 + 0.5) * 255).astype(np.uint8)).save(out)
    return out


def sample(kind_or_path, uv: np.ndarray) -> np.ndarray:
    """The swatch (or any grey image file) at uv (n, 2), wrapping, bilinear: what paint's "tile" reads per point."""
    if kind_or_path in PERIOD:
        d = depth(kind_or_path)
    else:
        key = ("file", str(kind_or_path))
        if key not in _CACHE:
            from PIL import Image
            a = np.asarray(Image.open(kind_or_path).convert("F"), np.float32)
            _CACHE[key] = a / (65535.0 if a.max() > 255 else 255.0)
        d = _CACHE[key]
    H, W = d.shape
    x = (uv[:, 0] % 1.0) * W - 0.5
    y = (1.0 - uv[:, 1] % 1.0) * H - 0.5
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    g = lambda yy, xx: d[yy % H, xx % W]  # noqa: E731
    return (g(y0, x0) * (1 - fx) + g(y0, x0 + 1) * fx) * (1 - fy) + (g(y0 + 1, x0) * (1 - fx) + g(y0 + 1, x0 + 1) * fx) * fy
