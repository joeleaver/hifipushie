"""Tiling micro-relief swatches for skin, generated here (no scans): the fine detail a unique texture can't hold
(the user's rule, as for rock in terrain_swatch.py: unique maps carry the macro, tiling maps the fine detail).

Each swatch is a periodic DEPTH map (0 = the skin's surface, 1 = the bottom of the deepest furrow or pore; 16 bit,
SIZE px across PERIOD metres of skin), used by paint's "tile" generator: a layer's negative "height" x the swatch is
the relief, the same mask darkens and roughens the furrows. What they model (dermatology: the skin's microrelief is
polygonal plateaus bounded by furrows; primary lines 20-100 um deep, secondary 5-40 um; facial pores 0.2-0.5 mm
across, 10-90 per cm2):

  pores   the face: pores as pits (a clustered Poisson set, each its own size and depth, some drawn out along the
          skin's lines), joined by a faint net of furrows, and fine secondary lines between.
  lines   the body (neck, arms, backs of hands, torso): the polygonal net itself, two generations (primary cells
          ~1 mm, secondary ~0.35 mm), stretched one way a little (skin lines follow tension), with a pore at some
          crossings.
  coarse  knuckles, elbows, knees, heels, old skin: deep primary folds in diamonds ~1.6 mm, cracked plateaus.
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

VERSION = 8
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


def _smooth_noise(rng, cells: int) -> np.ndarray:
    """Periodic smooth noise 0..1 with `cells` features across (random lattice, cubic-interpolated by FFT zoom)."""
    f = np.fft.rfft2(rng.standard_normal((cells, cells)))
    big = np.zeros((SIZE, SIZE // 2 + 1), complex)
    h = cells // 2
    big[:h, :h + 1] = f[:h, :h + 1]
    big[-h:, :h + 1] = f[-h:, :h + 1]
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
    return 0.3 * (1 - _smooth_noise(rng, 14)) + 0.22 * (1 - _smooth_noise(rng, 6)) + 0.14 * (1 - _smooth_noise(rng, 30))


def brow_image(density: float = 0.8, thickness: float = 1.0, length_mm: float = 6.0, width_mm: float = 62.0,
               seed: int = 0, tail: float = 1.0):
    """A left eyebrow as hairs (RGBA PNG in the image store; white hairs, coverage in alpha: the layer gives the
    colour), inner end at the left: hairs grow up and out at the inner end, lie along the brow in its body and
    turn out and down in the tail; the band is thick inside and tapers. Returns (path, [width, height] in mm)."""
    from PIL import Image, ImageDraw
    from . import images
    key = f"{density:.3f}_{thickness:.3f}_{length_mm:.2f}_{width_mm:.1f}_{seed}_{tail:.2f}_{VERSION}"
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
            return 0.56 - 0.2 * np.sin(np.clip(t / 0.62, 0, 1) * np.pi / 2) + 0.3 * np.clip((t - 0.62) / 0.38, 0, 1) ** 1.6
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
        prim = _edges(P, _seeds(rng, int((mm / 0.95) ** 2)), 0.13 / mm, 1.6)
        sec = _edges(P, _seeds(rng, int((mm / 0.36) ** 2)), 0.06 / mm, 1.35)
        pits = _pits(P, rng, int(1.6 * mm * mm), (0.04, 0.09), mm)
        d = 0.85 * prim * (0.55 + 0.45 * _smooth_noise(rng, 8)) + 0.38 * sec + 0.35 * pits
        d = d + _meso(rng)
    elif kind == "coarse":
        prim = _edges(P, _seeds(rng, int((mm / 1.7) ** 2)), 0.26 / mm, 1.9)
        sec = _edges(P, _seeds(rng, int((mm / 0.6) ** 2)), 0.1 / mm, 1.5)
        d = prim * (0.6 + 0.4 * _smooth_noise(rng, 6)) + 0.4 * sec + 0.12 * _smooth_noise(rng, 48)
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
        # lines across u: level curves of a field rising along v and wobbled by noise; they pinch out and fork
        v = P[:, 1]
        wob = 0.045 * (_smooth_noise(rng, 5) - 0.5) + 0.012 * (_smooth_noise(rng, 14) - 0.5)
        ph = (v + wob) * 7.0  # 7 lines per period
        dist = np.abs(ph - np.round(ph)) / 7.0 * mm  # mm to the nearest line
        strength = np.clip((_smooth_noise(rng, 7) - 0.3) * 2.2, 0, 1)
        d = np.clip(1 - dist / (0.5 + 0.5 * strength), 0, 1) ** 1.3 * strength
        ph2 = (v + 1.6 * wob + 0.07) * 14.0
        d2 = np.abs(ph2 - np.round(ph2)) / 14.0 * mm
        d = np.maximum(d, 0.35 * np.clip(1 - d2 / 0.18, 0, 1) * np.clip((_smooth_noise(rng, 9) - 0.45) * 3, 0, 1))
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
