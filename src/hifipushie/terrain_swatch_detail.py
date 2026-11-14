"""A swatch as detail on the ground: the detail image, the repetition's profile and fade, `write`, the bed-aligned projection. Part of the terrain's material swatches (terrain_swatch.py has the overview)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import terrain_swatch
from .terrain_swatch import smoothstep
from .terrain_swatch_make import detail_swatch, swatch, tileability
from .terrain_swatch_periodic import spectral

# repetition shows where the detail's image has a periodicity above `periodicity` while its contrast is above
# `contrast` (2% luminance, about a just-noticeable step), measured on a `px`-pixel frontal view; the fade runs over
# `span` x the footprint where it starts. Calibrated on the alps wall at 40 m (n02/n03): every scan (1.5-2.7 m) showed a
# grid there and measures 0.37-0.61 at 37-53 m in local windows; ours (4 m) never does and stays 0.16-0.26
def detail_image(S, p, px=768, light=(-0.5, 0.45, 0.74)):
    """What the detail draws on a flat face seen square-on at footprint p m/px (px x px pixels): the swatch's albedo
    luminance x Lambert shading of its normal under a raking light (the detail's own contribution, the macro flat),
    laid as the shader lays it (the swatch at 1x and at VARIATION_SCALE x, mixed by the variation mask) and read from
    the mip level a GPU would pick for that footprint (2x2 box pyramid, bilinear)."""
    n, L = S["n"], S["size_m"]
    Lv = np.asarray(light, float) / np.linalg.norm(light)
    img0 = S["albedo"].mean(-1) * np.clip((S["normal"] * Lv).sum(-1), 0, 1)
    img0 = img0 / img0.mean()
    lvl = max(0, int(np.floor(np.log2(max(p * n / L, 1.0)))))
    mip = img0
    for _ in range(lvl):
        if mip.shape[0] < 2:
            break
        mip = 0.25 * (mip[0::2, 0::2] + mip[1::2, 0::2] + mip[0::2, 1::2] + mip[1::2, 1::2])
    m = mip.shape[0]
    g = (np.arange(px) + 0.5) * p
    U, V = np.meshgrid(g, g)
    samp = lambda u, v: ndimage.map_coordinates(mip, [(v / L * m - 0.5) % m, (u / L * m - 0.5) % m], order=1,
                                                mode="grid-wrap")
    a = samp(U, V)
    sc = terrain_swatch.VARIATION_SCALE
    b = samp(U / sc + terrain_swatch.VARIATION_OFFSET[0] * L, V / sc + terrain_swatch.VARIATION_OFFSET[1] * L)
    var = smoothstep(-0.25, 0.25, spectral(256, 2.0, 4242 + 990, lo=2))
    w = ndimage.map_coordinates(var, [(V / terrain_swatch.VARIATION_M * 256 - 0.5) % 256, (U / terrain_swatch.VARIATION_M * 256 - 0.5) % 256],
                                order=1, mode="grid-wrap")
    return a * (1 - w) + b * w


def repetition_profile(S, ps=None):
    """How visible the swatch's repetition is with the pixel footprint p: per p, the detail image's (`detail_image`)
    contrast (std of luminance) and periodicity (the largest autocorrelation above its radial mean, from 2 px out
    to a third of the view: the measure terrain_facets.periodicity uses for lattice patterns). A repeat shows where
    both are above REPEAT's limits. Returns [(p, contrast, periodicity)]."""
    ps = ps if ps is not None else np.geomspace(0.004, 0.25, 13)
    out = []
    px = terrain_swatch.REPEAT["px"]
    wn = px // 3  # (local windows: the anti-tiling mask mixes the two samplings over ~24 m, so a whole-view
    # autocorrelation averaged the repeat away, but within one patch of the mask the repeat is exact: rock_face_03 read
    # as a grid at 40 m (n03) while the whole-view measure gave 0.28)
    yy, xx = np.mgrid[:2 * wn, :2 * wn]
    rb = np.rint(np.hypot(yy - wn, xx - wn)).astype(int)
    cnt = np.maximum(np.bincount(rb.ravel()), 1)
    for p in ps:
        im = detail_image(S, float(p), px)
        c = float(im.std())
        sh = im - ndimage.gaussian_filter(im, wn / 4, mode="reflect")
        per = 0.0
        for i in range(3):
            for j in range(3):
                w = sh[i * wn:(i + 1) * wn, j * wn:(j + 1) * wn]
                A = np.fft.rfft2(w - w.mean(), s=(2 * wn, 2 * wn))
                ac = np.fft.fftshift(np.fft.irfft2(np.abs(A) ** 2))
                ac /= max(ac[wn, wn], 1e-12)
                mean = np.bincount(rb.ravel(), ac.ravel()) / cnt
                per = max(per, float((ac - mean[rb])[(rb > 2) & (rb < wn // 2)].max()))
        out.append((round(float(p), 5), round(c, 4), round(per, 3)))
    return out


def repetition_fade(S):
    """The detail's fade by repetition (the way engines fade a tiling detail: mipmaps take care of aliasing; what
    the fade is for is the repeat that shows once many copies are on screen): full until the first footprint where
    the repeat is visible (REPEAT), gone `span` x further. ([p_full, p_gone] m/px or None if it never shows, the
    profile)."""
    prof = repetition_profile(S)
    vis = [p for p, c, per in prof if per > terrain_swatch.REPEAT["periodicity"] and c > terrain_swatch.REPEAT["contrast"]]
    if not vis:
        return None, prof
    return [vis[0], round(vis[0] * terrain_swatch.REPEAT["span"], 5)], prof


def write(out_dir, rock=None, name="rock", size=terrain_swatch.SIZE, res=terrain_swatch.RES, macro_density=8.0, source="procedural", S=None):
    """The swatch's images in out_dir/materials (rows top = up the face): <name>_detail_albedo.png (linear RGB,
    value x 2 = the multiplier on the macro colour: 0.5 = unchanged), _normal.png (tangent space, glTF/OpenGL: +x along
    the strike u, +y up the beds v), _height.png (16-bit, 0.5 = 0, +-height_m), _rough.png (value x 2 = the multiplier
    on roughness). Returns the manifest entry, with the wrap seam's measure per image."""
    from PIL import Image
    d = out_dir / "materials"
    d.mkdir(exist_ok=True)
    if S is None:
        S = swatch(rock, size, res) if not str(source).startswith("scan:") else detail_swatch(rock, source)
    size = float(S["size_m"])
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
    fade, prof = repetition_fade(S)
    pa = 2 * math.tan(math.radians(terrain_swatch.REF_VIEW[1] / 2)) / terrain_swatch.REF_VIEW[0]  # (rad per pixel)
    return {"layer": name, **files, "source": S.get("source", "procedural"), "size_m": float(size),
            "texels_per_m": float(S["texels_per_m"]),
            "variation_m": terrain_swatch.VARIATION_M, "variation_scale": terrain_swatch.VARIATION_SCALE, "variation_offset": terrain_swatch.VARIATION_OFFSET,
            "pixels": int(S["n"]), "height_m": round(hr, 5), "wrap_seam": seams,
            "tileable": all(max(v) <= terrain_swatch.TILE_LIMIT for v in seams.values()),
            "fade": {"footprint_m": fade, "limits": dict(terrain_swatch.REPEAT),
                     "distance_m": [round(p / pa, 1) for p in fade] if fade else None,
                     "distance_view": {"width_px": terrain_swatch.REF_VIEW[0], "fov_deg": terrain_swatch.REF_VIEW[1]},
                     "repetition": [{"footprint_m": p, "contrast": c, "periodicity": r} for p, c, r in prof]}}


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
