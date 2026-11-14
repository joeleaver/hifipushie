"""Making a swatch: `swatch`, a scanned swatch, its stats, the detail swatch, tileability. Part of the terrain's material swatches (terrain_swatch.py has the overview)."""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from . import terrain_swatch
from . import noise
from .terrain_swatch import smoothstep
from .terrain_swatch_periodic import _veins, periodic_cells, periodic_facets, periodic_pits, spectral

def swatch(rock=None, size=terrain_swatch.SIZE, res=terrain_swatch.RES, seed=None):
    """The detail swatch of one rock type: {"height" (m, outward), "normal" (unit, tangent space: x along s, y up t,
    z out), "albedo" (a multiplier on the macro colour, mean 1 per channel), "rough" (a multiplier, mean 1), "cavity"
    (0..1)}; arrays rows = t up. Rock character at several scales, each periodic on the swatch:
    - planes: irregular facets 0.45 / 0.16 / 0.07 m (terrain_facets' seeds on a torus), the bigger ones stretched up
      the face like the rock's own;
    - fractures: few, on a facet net's zero lines, broken into lengths, each its own width (2-12 mm) and depth (to ~3
      cm), a V with a dark floor (uniform thin creases read as crumpled paper);
    - spall scars: polygons where a coarser facet field stands high, a crisp rim and a conchoidal bowl 1-3 cm deep
      that is paler (fresh rock) and smoother;
    - pits: sparse round pits 3-10 mm, dark inside;
    - grain: mineral speckle in albedo (pale and dark grains, a few mm) and roughness (glassy grains smoother), a
      sub-millimetre-to-cm roughness in the relief;
    - weathering patches 0.3-1 m and sparse crustose lichen.
    Nothing longer than a quarter of the swatch (a swatch-sized feature repeats visibly)."""
    seed = int((rock or {}).get("seed", 4242) if seed is None else seed) + 900
    n = int(round(size * res))
    L = float(size)
    texel = L / n
    T = terrain_swatch.TUNE
    # planes: polygonal fracture facets at three sizes, each size varying place to place; most of the relief is here
    # (a rock face is rough everywhere: the scans' surface slope is 0.1-0.2 rms in every octave from 0.5 m to 1 cm)
    cells = [periodic_cells(n, L, c["size"], seed + 1 + 5 * k, stretch=c["stretch"], vary=c["vary"], slope=c["slope"],
                            step=c["step"], cup=c["cup"], soft=c["soft"]) for k, c in enumerate(T["cells"])]
    big_id, big_e = cells[0][1], cells[0][2]
    rough_rel = spectral(n, T["rough_beta"], seed + 3, lo=24)
    # fractures: on the zero lines of facet nets at two sizes, in lengths (`on`), each its own width and depth
    frac = np.zeros((n, n))
    frac_d = np.zeros((n, n))
    for k, fr in enumerate(T["fractures"]):
        net = periodic_facets(n, L, fr["net"], seed + 4 + 30 * k, stretch=1.6)
        wob = spectral(n, 1.8, seed + 5 + 30 * k, lo=8)
        on = smoothstep(fr["on"][0], fr["on"][1], spectral(n, 2.2, seed + 7 + 30 * k, lo=4))  # (lengths ~1 m:
        # shorter lengths read as dashes)
        wvar = np.clip(0.5 + 0.5 * spectral(n, 1.4, seed + 14 + 30 * k, lo=10), 0, 1)  # (each length its own width)
        # (half-width never under ~1.5 texels: thinner, the V was sampled on and off along its length and read as a
        # dashed line; a fracture fades out by depth and darkness (`on`), not by narrowing to nothing)
        width = 1.5 * texel + fr["width"] * wvar ** 2                            # half-width, m
        gnet = np.hypot((np.roll(net, -1, 1) - np.roll(net, 1, 1)) / (2 * texel),  # (the net's slope; wrapped)
                        (np.roll(net, -1, 0) - np.roll(net, 1, 0)) / (2 * texel))
        dist = np.abs(net + 0.04 * wob) / np.maximum(ndimage.gaussian_filter(gnet, 3, mode="wrap"), 0.5)
        v = np.clip(1 - dist / width, 0, 1) * on
        frac = np.maximum(frac, v)
        frac_d = np.maximum(frac_d, (0.006 + fr["depth"] * wvar) * v ** 0.7)  # V depth
    # spall scars: a few big facets spalled off: a polygonal rim, a shallow conchoidal bowl
    hc = noise._hash(big_id, np.zeros_like(big_id), np.zeros_like(big_id), seed + 15)
    region = hc < T["scars"]
    sdepth = 0.004 + 0.008 * noise._hash(big_id, np.ones_like(big_id), np.zeros_like(big_id), seed + 17)
    bowl = np.where(region, sdepth * (1 - np.exp(-big_e / 0.03)), 0.0)
    scar = smoothstep(0.0, 0.003, bowl)
    # pits: crisp cups, clustered
    pit_d, pit = periodic_pits(n, L, seed + 18)
    vein = _veins(n, L, seed + 40, texel)
    h = (sum(c[0] for c in cells) * (1 - 0.5 * scar) + T["rough"] * rough_rel - frac_d - bowl - pit_d
         + 0.0006 * vein)
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) / (2 * texel)
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) / (2 * texel)  # (rows = t up)
    nrm = np.stack([-gx, -gy, np.ones_like(h)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    # cavity: concave places (the height's Laplacian over ~1 cm)
    lap = ndimage.laplace(ndimage.gaussian_filter(h, 1.5, mode="wrap"), mode="wrap") / (texel * texel)
    cav = np.clip(lap / max(np.percentile(np.abs(lap), 98), 1e-9), -1, 1)
    # albedo: variation in every octave (the scans' luminance varies 0.1-0.2 rms per octave, flat across them; ours had
    # 0.01-0.04 and read as stucco): each facet of each size its own tone, mineral grain, proud places lighter
    # (the scans: +0.2 correlation with high-passed height; concave places not darker on their own)
    g1 = spectral(n, 0.0, seed + 10, lo=64)                                  # (grain-sized white-ish noise)
    g2 = spectral(n, 0.0, seed + 20, lo=64)
    pale = smoothstep(0.3, 0.45, g1) * 0.3                                   # pale grains (quartz, calcite)
    dark = smoothstep(0.32, 0.47, g2) * 0.4                                  # dark grains
    dens = np.clip(0.55 + 0.6 * spectral(n, 1.4, seed + 23, lo=8), 0.1, 1.2)  # (grains cluster: no even salt and pepper)
    pale, dark = pale * dens, dark * dens
    tone = 1 + T["speck"] * spectral(n, T["speck_beta"], seed + 21, lo=8) + pale - dark
    for k, c in enumerate(cells):
        fh = noise._hash(c[1], np.full_like(c[1], 2), np.zeros_like(c[1]), seed + 16 + k)
        ct = (2 * fh - 1).astype(float)
        if T["cell_soft"] > 0:  # (each facet's tone fading into its neighbours': hard polygon tones read as terrazzo)
            ct = ndimage.gaussian_filter(ct, T["cell_soft"] * T["cells"][k]["size"] / texel, mode="wrap")
            ct = ct / max(ct.std(), 1e-9) * 0.577  # (the std a hard +-1 uniform tone has)
        tone = tone + T["cell_tone"][k] * ct
    hp = h - ndimage.gaussian_filter(h, 0.05 / texel, mode="wrap")
    tone = tone + T["proud"] * hp / max(hp.std(), 1e-9)
    # weathering: patches of rind darker or paler (0.2-1 m, irregular, soft-edged), grime soaked into the rock round
    # each fracture and washed down from it (the scans' darkest tones sit in and under their cracks, not on concave
    # facets)
    wz = spectral(n, 1.7, seed + 60, lo=6)
    tone = tone + T["patch"] * (smoothstep(-0.25, 0.35, wz) - 0.5) * 2
    halo = ndimage.gaussian_filter(frac, T["halo_m"] / texel, mode="wrap")
    halo = halo / max(halo.max(), 1e-9)
    kz = max(1, int(round(T["streak_m"] / texel)))
    ker = np.exp(-np.arange(4 * kz) / kz)
    # (rows = t up: grime runs down, so a row takes what the rows above it hold)
    streak = sum(ker[i] * np.roll(halo, -i, 0) for i in range(0, len(ker), max(1, kz // 8))) * max(1, kz // 8) / ker.sum()
    streak = streak / max(streak.max(), 1e-9)
    tone = tone * (1 - T["grime"] * np.clip(0.6 * halo + 0.7 * streak, 0, 1))
    # (skewed like the scans': a long pale tail, a short dark one (their 1st percentile 0.3-0.5 x the median, ours was
    # 0.3 with a symmetric spread: dark mottle on dark rock read as dirty granite)
    tone = np.exp(T["skew"] * (tone - 1.0))
    tone = (tone + 0.05 * scar) * (1 - 0.55 * frac) * (1 - 0.15 * pit)
    lic = smoothstep(0.66, 0.74, 0.5 + 0.5 * spectral(n, 1.8, seed + 11, lo=24)) * \
        smoothstep(0.0, 0.4, spectral(n, 1.6, seed + 12, lo=8)) * (1 - scar)
    # mineral variety: calcite veins (pale, cool), iron staining (warm, in patches, stronger in pits where water sits)
    iron = smoothstep(0.15, 0.6, spectral(n, 1.6, seed + 50, lo=8)) * (0.6 + 0.4 * pit)
    hue = 1 + iron[..., None] * np.array([0.10, 0.0, -0.13]) + vein[..., None] * np.array([0.14, 0.15, 0.17])
    alb = (tone[..., None] * hue) * (1 - 0.6 * lic[..., None]) + 0.6 * lic[..., None] * np.array([1.30, 1.34, 1.18])
    alb = np.clip(alb, 0.05, None)
    alb = alb / alb.reshape(-1, 3).mean(0)
    rough = 1 + T["rough_var"] * spectral(n, 1.0, seed + 13, lo=8) - 0.4 * pale + 0.08 * frac - 0.1 * scar \
        - 0.05 * lic - 0.15 * vein + 0.06 * pit
    rough = rough / rough.mean()
    return {"height": h, "normal": nrm, "albedo": alb, "rough": rough, "cavity": np.clip(-cav, 0, 1),
            "size_m": L, "texels_per_m": n / L, "n": n}


def scan_swatch(name, n=terrain_swatch.SCAN_PX):
    """A photoscanned rock texture set (asset pack "rock_scans", CC0, e.g. "rock_face_03") as a detail swatch, the same
    dict as `swatch` (rows = t up). Albedo: the scan's diffuse made linear and divided by its mean per channel (a
    multiplier on the macro colour: the scan's own hue goes, its variation stays); roughness the same; normal the
    tangent-space map as it is (OpenGL, +y up the image); height the displacement map in metres, its scale fitted so
    its slopes match the normal map's (the scan says 0..1, not metres)."""
    import json
    from PIL import Image
    from . import assets
    d = assets.pack("rock_scans")
    size = float(json.loads((d / "sets.json").read_text())[name]["size_m"])
    load = lambda k, ext: Image.open(d / name / f"{name}_{k}_2k.{ext}")
    rs = lambda im, mode: np.asarray(im.resize((n, n), mode), float)[::-1]  # (rows up)
    diff = rs(load("diff", "jpg").convert("RGB"), Image.LANCZOS) / 255
    lin = np.where(diff <= 0.04045, diff / 12.92, ((diff + 0.055) / 1.055) ** 2.4)
    alb = lin / lin.reshape(-1, 3).mean(0)
    rough = rs(load("rough", "jpg").convert("L"), Image.LANCZOS) / 255
    rough = rough / max(rough.mean(), 1e-6)
    nrm = rs(load("nor_gl", "png").convert("RGB"), Image.LANCZOS) / 255 * 2 - 1
    nrm /= np.maximum(np.linalg.norm(nrm, axis=-1, keepdims=True), 1e-9)
    disp = np.asarray(load("disp", "png"), float)
    disp = disp[..., 0] if disp.ndim == 3 else disp  # (some sets store it as RGBA)
    disp = np.asarray(Image.fromarray(disp.astype(np.float32), "F").resize((n, n), Image.LANCZOS), float)[::-1]
    disp = (disp - disp.mean()) / 65535.0
    texel = size / n
    gx = (np.roll(disp, -1, 1) - np.roll(disp, 1, 1)) / (2 * texel)
    gy = (np.roll(disp, -1, 0) - np.roll(disp, 1, 0)) / (2 * texel)
    tx, ty = -nrm[..., 0] / np.maximum(nrm[..., 2], 0.1), -nrm[..., 1] / np.maximum(nrm[..., 2], 0.1)
    k = float(((gx * tx).sum() + (gy * ty).sum()) / max((gx * gx).sum() + (gy * gy).sum(), 1e-12))
    h = disp * k
    lap = ndimage.laplace(ndimage.gaussian_filter(h, 1.5, mode="wrap"), mode="wrap") / (texel * texel)
    cav = np.clip(lap / max(np.percentile(np.abs(lap), 98), 1e-9), -1, 1)
    return {"height": h, "normal": nrm, "albedo": alb, "rough": rough, "cavity": np.clip(-cav, 0, 1), "size_m": size,
            "texels_per_m": n / size, "n": n, "source": f"scan:{name}", "height_scale_m": round(k, 4)}


def swatch_stats(S):
    """What a swatch is made of, comparable across procedural and scanned ones (the targets for tuning ours):
    - slope_octaves: rms surface slope (from the normal map) per octave of wavelength, 1 m down to 2 texels;
    - albedo: luminance std (of the multiplier), and its correlation with cavity (concave places darker: negative)
      and with high-passed height (proud places lighter: positive);
    - rough: std and p5/p95 of the roughness multiplier;
    - edges: the slope magnitude's p50/p90/p99 and its kurtosis (sharp-edged facets: flat faces + steep edges =
      a heavy tail);
    - fractures: valleys deeper than 2 mm (a 1.5 cm black top-hat of the height), as skeleton length per m2 and
      their widths (2 x the distance to the valley's edge along its skeleton) p50/p90 in mm."""
    from skimage.morphology import skeletonize
    n, L = S["n"], S["size_m"]
    tex = L / n
    nrm = S["normal"]
    sx, sy = -nrm[..., 0] / np.maximum(nrm[..., 2], 0.1), -nrm[..., 1] / np.maximum(nrm[..., 2], 0.1)
    fx = np.fft.fftfreq(n, tex)
    F = np.hypot(*np.meshgrid(fx, fx))
    P = np.abs(np.fft.fft2(sx)) ** 2 + np.abs(np.fft.fft2(sy)) ** 2
    lum = S["albedo"].mean(-1)
    PA = np.abs(np.fft.fft2(lum - lum.mean())) ** 2
    oct_ = []
    lam = 1.0
    while lam / 2 >= 2 * tex:
        band = (F >= 1 / lam) & (F < 2 / lam)
        oct_.append({"wavelength_m": [round(lam / 2, 4), lam], "slope_rms": round(float(np.sqrt(P[band].sum()) / n ** 2), 4),
                     "albedo_rms": round(float(np.sqrt(PA[band].sum()) / n ** 2), 4)})
        lam /= 2
    hp = S["height"] - ndimage.gaussian_filter(S["height"], 0.05 / tex, mode="wrap")
    cc = lambda a, b: float(np.corrcoef(a.ravel(), b.ravel())[0, 1])
    smag = np.hypot(sx, sy)
    k = ((smag - smag.mean()) ** 4).mean() / max(smag.var() ** 2, 1e-12)
    r = max(1, int(round(0.015 / tex)))
    th = ndimage.black_tophat(S["height"], size=2 * r + 1, mode="wrap")
    val = th > 0.002
    sk = skeletonize(val)
    wd = 2 * ndimage.distance_transform_edt(val)[sk] * tex * 1000
    return {"source": S.get("source", "procedural"), "size_m": L, "texels_per_m": round(n / L, 1),
            "slope_octaves": oct_,
            "albedo": {"lum_std": round(float(lum.std()), 3), "corr_cavity": round(cc(lum, S["cavity"]), 3),
                       "corr_height_hp": round(cc(lum, hp), 3)},
            "rough": {"std": round(float(S["rough"].std()), 3),
                      "p5_p95": [round(float(x), 3) for x in np.percentile(S["rough"], [5, 95])]},
            "edges": {"slope_p50_p90_p99": [round(float(x), 3) for x in np.percentile(smag, [50, 90, 99])],
                      "kurtosis": round(float(k), 2)},
            "fractures": {"length_m_per_m2": round(float(sk.sum() * tex / (L * L)), 2),
                          "width_mm_p50_p90": [round(float(x), 1) for x in np.percentile(wd, [50, 90])] if len(wd)
                          else None}}


def detail_swatch(rock=None, source="procedural"):
    """The swatch a detail layer uses: `swatch(rock)` or, for source "scan:<set>", `scan_swatch(<set>)`."""
    if source and str(source).startswith("scan:"):
        return scan_swatch(str(source)[5:])
    return swatch(rock)


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
