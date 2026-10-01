"""Tiling rock detail: the rock's grain below ~0.5 m as a small seamless material, laid along the bedding.

Detail by scale (agreed 2026-10-01): geometry carries >= ~1 m (landform, cliffs, beds, blocks); each tile's unique maps
carry the macro (colour, staining, AO, layer weights, the normal of the >= 0.5 m structure) at a few texels/m; what
is finer (grain, small facets, hairline fractures, laminae, crustose lichen) is the same everywhere on one kind of
rock, so it is authored once per rock type as a tileable swatch, and the engine draws it sharp at any distance.

`swatch(rock)`: a SIZE x SIZE m patch of rock face at RES texels/m (s along the strike, t up the beds), made from
the same pieces as the bake's fine relief (terrain_bake.micro_relief): Poisson-disk facets on Delaunay triangles
(terrain_facets, its seeds hashed on a torus: `_seeds(period=)`), FFT spectra (periodic by construction), cracks on a
facet net's zero lines, laminae along the beds. Every term is periodic in both directions, so the swatch tiles
exactly (never cropped and cross-faded); `tileability` measures the wrap seam like the tile border checks.

`DetailProjection`: where the swatch lies. Strike-binned planar projection: BINS vertical planes round the compass
(u = p . d_k, to the right as one faces the rock) plus the top plane, v = the bed coordinate (z + the beds' offset:
terrain_rock.bed_offset + the wander, the same coordinate the solid rock's beds use), so the swatch's grain and laminae
run along the beds and are never stretched by more than 1 / cos(22.5 deg) = 1.08. Which planes apply follows the
rock's normal averaged over RADIUS (a pure function of position: tiles agree at their borders, LODs agree). Exported
per cliff-tile vertex as `_DETAIL` (strike x, y, side share, bed coordinate) for shaders that blend the two nearest planes
and the top (seamless, like triplanar), and as a UV set (each triangle on its nearest plane: stock engine detail maps
on a UV channel; seams where the plane changes). A single global UV can't follow the strike: round every peak the
faces close into a ring, and a function's gradient can't circulate (a least-squares strike coordinate came out at
0.37 m per metre on the alps wall: the swatch stretched 2.7x).
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import noise
from . import terrain_facets as tf

SIZE = 4.0        # m: the swatch's side
RES = 256         # texels per metre (1024 x 1024)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- periodic pieces

def periodic_facets(n, L, size, seed, stretch=1.0):
    """terrain_facets' irregular planar facets (~`size` m, stretched `stretch` up the face) on an n x n grid over an
    L x L torus (rows = t up, columns = s along). The facet size is rounded so the seed grid's cells fit the period
    exactly (within a few %). -1..1."""
    nx = max(3, int(round(L / (size * tf.CELL))))
    ny = max(3, int(round(L / (size * stretch * tf.CELL))))
    Px, Py = nx * tf.CELL, ny * tf.CELL  # the period in facet units
    pts, ids = tf._seeds(np.array([-tf.PAD, -tf.PAD]), np.array([Px + tf.PAD, Py + tf.PAD]), seed, period=(nx, ny))
    val = 2 * noise._hash(ids[:, 0], ids[:, 1], ids[:, 2], seed + 9) - 1
    from scipy.spatial import Delaunay
    tri = Delaunay(pts)
    g = (np.arange(n) + 0.5) / n
    S, Tt = np.meshgrid(g * Px, g * Py)
    q = np.c_[S.ravel(), Tt.ravel()]
    s = tri.find_simplex(q)
    Tr = tri.transform[s]
    bc = np.einsum("nij,nj->ni", Tr[:, :2], q - Tr[:, 2])
    out = (np.c_[bc, 1 - bc.sum(1)] * val[tri.simplices[s]]).sum(1)
    return np.clip(tf.GAIN * out, -1, 1).reshape(n, n)


def spectral(n, beta, seed, stretch=(1.0, 1.0), lo=4.0):
    """Periodic noise (as terrain_bake._spectral: random phases, 1/f^beta), zero mean, about -1..1, with nothing
    longer than a `lo`-th of the swatch: a feature as big as the swatch repeats visibly (one lichen patch a tile)."""
    rng = np.random.default_rng(seed)
    fx = np.fft.fftfreq(n)[None, :] * n * stretch[0]  # cycles per swatch
    fy = np.fft.fftfreq(n)[:, None] * n * stretch[1]
    f = np.sqrt(fx * fx + fy * fy)
    amp = np.where(f > 0, np.maximum(f, 1e-9) ** -beta, 0.0) * smoothstep(0.5 * lo, lo, f)
    z = np.real(np.fft.ifft2(amp * np.exp(2j * np.pi * rng.random((n, n)))))
    return 2 * (z - z.mean()) / max(np.ptp(z), 1e-9)


def swatch(rock=None, size=SIZE, res=RES, seed=None):
    """The detail swatch of one rock type: {"height" (m, outward), "normal" (unit, tangent space: x along s, y up t,
    z out), "albedo" (a multiplier on the macro colour, mean 1 per channel), "rough" (a multiplier, mean 1), "cavity"
    (0..1)}; arrays rows = t up. Facet sizes follow the rock's (terrain_bake.micro_relief's 0.45 m facets are its
    smallest; finer here)."""
    seed = int((rock or {}).get("seed", 4242) if seed is None else seed) + 900
    n = int(round(size * res))
    L = float(size)
    f45 = periodic_facets(n, L, 0.45, seed + 1, stretch=1.4)
    f16 = periodic_facets(n, L, 0.16, seed + 2, stretch=1.2)
    f07 = periodic_facets(n, L, 0.07, seed + 6, stretch=1.0)
    grain = spectral(n, 1.1, seed + 3, lo=16)
    net = periodic_facets(n, L, 0.55, seed + 4, stretch=1.6)
    wob = spectral(n, 1.8, seed + 5, lo=8)
    # hairline fractures on a facet net's zero lines, broken into short lengths of varying strength: many small ones
    # (a few long ones were the swatch's landmarks, repeated every 4 m)
    keep = smoothstep(0.3, 0.6, spectral(n, 1.6, seed + 7, lo=10)) * (0.5 + 0.5 * spectral(n, 1.2, seed + 14, lo=8))
    crack = np.clip(1 - np.abs(net + 0.05 * wob) / 0.03, 0, 1) ** 2 * np.clip(keep, 0, 1)
    # spalls: shallow shell-shaped scars a few cm to 20 cm across, crisp-edged, paler (fresh rock)
    # (angular: where another facet field stands high, a polygon; rounded noise blobs read as plaster)
    chip = smoothstep(0.66, 0.72, periodic_facets(n, L, 0.22, seed + 15, stretch=1.0))
    # (no laminae: lines at fixed heights in the swatch repeated every 4 m up the whole wall as ruled stripes; the
    # beds' own planes are in the lines map)
    h = 0.014 * f45 + 0.008 * f16 + 0.003 * f07 + 0.0015 * grain - 0.008 * crack - 0.004 * chip
    texel = L / n
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) / (2 * texel)
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) / (2 * texel)  # (rows = t up)
    nrm = np.stack([-gx, -gy, np.ones_like(h)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    # cavity: concave places (the height's Laplacian over ~2 cm) darker
    lap = ndimage.gaussian_filter(h, 2.0, mode="wrap")
    lap = ndimage.laplace(lap, mode="wrap") / (texel * texel)
    cav = np.clip(lap / max(np.percentile(np.abs(lap), 98), 1e-9), -1, 1)
    # albedo: grains (speckle, a few mm), weathering patches 0.3-1 m, facets to slightly different tones, darker
    # fractures, paler spalls, sparse crustose lichen (pale, rounded patches 2-10 cm)
    speck = spectral(n, 0.35, seed + 10, lo=16)
    patch = spectral(n, 1.5, seed + 16, lo=4)
    tone = (1 + 0.04 * f45 + 0.03 * f16 + 0.14 * speck + 0.08 * patch - 0.08 * np.clip(cav, 0, 1)
            + 0.07 * chip)
    tone = tone * (1 - 0.3 * crack)
    lic = smoothstep(0.66, 0.74, 0.5 + 0.5 * spectral(n, 1.8, seed + 11, lo=24)) * \
        smoothstep(0.0, 0.4, spectral(n, 1.6, seed + 12, lo=8))
    alb = tone[..., None] * (1 - 0.6 * lic[..., None]) + 0.6 * lic[..., None] * np.array([1.30, 1.34, 1.18])
    alb = alb / alb.reshape(-1, 3).mean(0)
    rough = 1 + 0.08 * spectral(n, 1.0, seed + 13, lo=8) + 0.06 * crack - 0.05 * lic - 0.04 * chip
    rough = rough / rough.mean()
    return {"height": h, "normal": nrm, "albedo": alb, "rough": rough, "cavity": np.clip(-cav, 0, 1),
            "size_m": L, "texels_per_m": n / L, "n": n}


def tileability(img):
    """How much the wrap seam stands out, per axis: the mean jump across it (last column -> first, top row -> bottom)
    over the mean jump between neighbours elsewhere. ~1.0 = invisible (the same measure as the tile border checks'
    jump excess)."""
    a = np.asarray(img, float)
    a = a.reshape(a.shape[0], a.shape[1], -1)
    dx = np.abs(np.diff(a, axis=1)).mean()
    dy = np.abs(np.diff(a, axis=0)).mean()
    wx = np.abs(a[:, 0] - a[:, -1]).mean()
    wy = np.abs(a[0] - a[-1]).mean()
    return [round(float(wx / max(dx, 1e-12)), 3), round(float(wy / max(dy, 1e-12)), 3)]


VARIATION_M = 24.0          # m: the anti-tiling mask's period on the detail UV
VARIATION_SCALE = 1.618     # the second sampling's size: the swatch at SIZE x this
VARIATION_OFFSET = [0.37, 0.71]  # its offset (in swatches)
TILE_LIMIT = 1.5  # a wrap seam jumping more than this x its neighbours' steps shows as a line every swatch


def write(out_dir, rock=None, name="rock", size=SIZE, res=RES):
    """The swatch's images in out_dir/materials (rows top = up the face): <name>_detail_albedo.png (linear RGB,
    value x 2 = the multiplier on the macro colour: 0.5 = unchanged), _normal.png (tangent space, glTF/OpenGL: +x along
    the strike u, +y up the beds v), _height.png (16-bit, 0.5 = 0, +-height_m), _rough.png (value x 2 = the multiplier
    on roughness). Returns the manifest entry, with the wrap seam's measure per image."""
    from PIL import Image
    d = out_dir / "materials"
    d.mkdir(exist_ok=True)
    S = swatch(rock, size, res)
    up = lambda a: np.ascontiguousarray(a[::-1])  # (image rows run down; ours run up the face)
    q8 = lambda a: np.round(np.clip(a, 0, 1) * 255).astype(np.uint8)
    hr = float(max(np.abs(S["height"]).max(), 1e-4))
    imgs = {"albedo": q8(0.5 * S["albedo"]), "normal": q8(S["normal"] * 0.5 + 0.5),
            "height": np.round((S["height"] / hr * 0.5 + 0.5) * 65535).astype(np.uint16),
            "rough": q8(0.5 * S["rough"])}
    # the anti-tiling mask: a smooth periodic noise sampled at the detail UV / VARIATION_M, choosing between the swatch
    # at 1x and at VARIATION_SCALE x (offset) place by place, so the 4 m repeat doesn't line up across a wall
    var = spectral(256, 2.0, int((rock or {}).get("seed", 4242)) + 990, lo=2)
    imgs["variation"] = q8(smoothstep(-0.25, 0.25, var))
    files, seams = {}, {}
    for k, a in imgs.items():
        fn = f"materials/{name}_detail_{k}.png"
        im = Image.fromarray(up(a), "I;16" if a.dtype == np.uint16 else None)
        im.save(out_dir / fn)
        files[k] = fn
        seams[k] = tileability(a)
    return {"layer": name, **files, "size_m": float(size), "texels_per_m": float(S["texels_per_m"]),
            "variation_m": VARIATION_M, "variation_scale": VARIATION_SCALE, "variation_offset": VARIATION_OFFSET,
            "pixels": int(S["n"]), "height_m": round(hr, 5), "wrap_seam": seams,
            "tileable": all(max(v) <= TILE_LIMIT for v in seams.values())}


# ---------------------------------------------------------------- the structure's lines (a macro map)

LINE_D = 0.5  # m: the lines map's signed distances run -LINE_D..LINE_D (8 bits: 4 mm a step)
LINE_GATE = (0.15, 0.3)  # m at 4 texels/m (scaled with the texel): a line's strength fades out between these


def structure_lines(field, X, texel=0.25, eps=0.02):
    """The rock structure's drawn lines at surface points X: the open bedding planes and the open joints
    (terrain_blocks.ids), as SIGNED distances (m) and strengths, for the lines map: (s_bed, a_bed, s_joint, a_joint).
    At a few texels per metre a crack 3-5 cm wide can't be baked into colour (it blurs into a 0.5 m smudge), but a
    signed distance interpolates linearly across the line, so the shader cuts it crisp at any width (as a font's
    distance field does). Unsigned, the bilinear minimum sat up to half a texel off zero (the line beaded); the sign
    comes from a probe eps along the line's normal (up for beds, along the strike for joints). The strength is that of
    the NEAREST line and fades out between LINE_GATE: half-way between two lines the distance flips sign, and the faded
    strength is what keeps the interpolated zero there from drawing a false line."""
    from . import terrain_blocks
    r = field.rock
    n = len(X)
    z = np.zeros(n)
    if not r or not r.get("blocks") or not n:
        return z, z, z, z
    B = r["blocks"]
    fd = field.face_dir(X[:, 0], X[:, 1])
    fl = np.maximum(np.linalg.norm(fd, axis=1, keepdims=True), 1e-9)
    along = np.c_[-fd[:, 1:2] / fl, fd[:, 0:1] / fl, np.zeros((n, 1))]
    Q = np.concatenate([X, X + [0.0, 0.0, eps], X + eps * along])
    zoff = r["bed_offset"](Q[:, :2]) if r.get("bed_offset") else 0.0
    I = terrain_blocks.ids(Q, B, np.concatenate([fd, fd, fd]), zoff)
    # (the gate scales with the texel: what has to be told apart is planes a few texels apart)
    g0, g1 = LINE_GATE[0] * texel / 0.25, LINE_GATE[1] * texel / 0.25
    gate = lambda s: 1.0 - smoothstep(g0, g1, np.abs(s))
    d0, du = I["bed_edge"][:n], I["bed_edge"][n:2 * n]
    s_b = np.where(du >= d0, 1.0, -1.0) * d0
    be = I["bed_edge"][:n]
    # (not inside thin beds: planes closer than ~2.5 texels can't be told apart, and the sign flipping half-way between
    # them drew zigzags; a thin package's planes are the swatch's laminae)
    a_b = I["bed_crack"][:n] * (I["thick"][:n] > 2.8 * texel) * gate(s_b)
    # joints: the family whose nearest open joint is nearest (weighted families only)
    D = np.stack([np.where(w[:n] > 0.05, o[:n], np.inf) for o, w in zip(I["open"], I["weights"])], 1)
    m = np.argmin(D, 1)
    rows = np.arange(n)
    dj = D[rows, m]
    ds = np.stack(I["open"], 1)[2 * n:][rows, m]
    wj = np.stack(I["weights"], 1)[:n][rows, m]
    fin = np.isfinite(dj)
    s_j = np.where(fin, np.where(~np.isfinite(ds) | (ds >= dj), 1.0, -1.0) * np.where(fin, dj, 0.0), LINE_D)
    # (a joint stops at its bed's planes: faded out within ~0.3 m of them. Cut off there, its distance jumped to the
    # next bed's at the plane, and the interpolated zero drew a hook along the plane at every crack's end)
    a_j = np.where(fin, np.clip(wj, 0, 1) * gate(s_j) * smoothstep(0.08, 0.3, be), 0.0)
    return np.clip(s_b, -LINE_D, LINE_D), a_b, np.clip(s_j, -LINE_D, LINE_D), a_j


# ---------------------------------------------------------------- the bed-aligned projection

class DetailProjection:
    """Where and how the swatch lies on the rock (see the module docstring): per point the smoothed face normal's
    strike, the bed coordinate and the side share; per triangle the nearest strike-binned plane (the UV set). Built
    once per terrain in the parent; pointwise afterwards (forked workers read it)."""

    BINS = 8          # strike planes, every 45 deg round the compass (u to the right as one faces the rock)
    RADIUS = 1.5      # m: the normal is averaged over a ball this size (a rough face's facets don't flip bins)

    def __init__(self, field, rock=None):
        self.field = field
        self.off = rock.get("bed_offset") if rock else None

    def smooth_normal(self, P):
        """The field's normal averaged over RADIUS (gradients at the point and six around it): a pure function of
        position, so both tiles at a border and every LOD agree."""
        P = np.asarray(P, float)
        r = self.RADIUS
        offs = np.array([[0, 0, 0], [r, 0, 0], [-r, 0, 0], [0, r, 0], [0, -r, 0], [0, 0, r], [0, 0, -r]], float)
        Q = (P[:, None, :] + offs[None]).reshape(-1, 3)
        g = np.zeros((len(Q), 3))
        for a in range(0, len(Q), 200_000):
            g[a:a + 200_000] = self.field.value_gradient(Q[a:a + 200_000], 0.5)[1]
        g = g.reshape(len(P), len(offs), 3)
        g /= np.maximum(np.linalg.norm(g, axis=2, keepdims=True), 1e-9)
        n = g.mean(1)
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)

    def bed_v(self, P):
        P = np.asarray(P, float)
        return P[:, 2] + (self.off(P[:, :2]) if self.off is not None else 0.0)

    @staticmethod
    def side_share(n):
        return smoothstep(0.45, 0.75, np.hypot(n[:, 0], n[:, 1]))

    @staticmethod
    def strike(n):
        """Unit horizontal vector along the face, to the right as one faces it (u x v = outward normal)."""
        s = np.c_[-n[:, 1], n[:, 0]]
        return s / np.maximum(np.linalg.norm(s, axis=1, keepdims=True), 1e-9)

    def attrs(self, P):
        """Per vertex _DETAIL = (strike x, strike y, side share, the bed coordinate in m). (One VEC4: Blender's glTF
        importer mixes up custom attributes of different widths.)"""
        n = self.smooth_normal(P)
        return np.c_[self.strike(n), self.side_share(n), self.bed_v(P)]

    def face_bins(self, P, F):
        """Per triangle the plane its UV set uses: 0..BINS-1 = the strike bin nearest its corners' mean smoothed
        normal, BINS = the top plane (flat rock: ledges, cave floors and roofs)."""
        n = self.smooth_normal(np.asarray(P, float)[F].mean(1))
        s = self.strike(n)
        k = np.round(np.arctan2(s[:, 1], s[:, 0]) / (2 * np.pi / self.BINS)).astype(np.int64) % self.BINS
        return np.where(self.side_share(n) < 0.5, self.BINS, k)

    def uv(self, P, b):
        """The UV set (metres; glTF v runs down) of points P on planes b: side planes u = p . d_b, v = bed coordinate;
        the top plane u = x, v = y (north up the image)."""
        P = np.asarray(P, float)
        a = np.asarray(b) * (2 * np.pi / self.BINS)
        u = P[:, 0] * np.cos(a) + P[:, 1] * np.sin(a)
        v = self.bed_v(P)
        top = np.asarray(b) == self.BINS
        u = np.where(top, P[:, 0], u)
        v = np.where(top, P[:, 1], v)
        return np.c_[u, -v]
