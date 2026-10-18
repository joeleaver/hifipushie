"""dirmeasure.py <ref crop> <res crop> [grid=6] [sigma=3]: strand DIRECTION measured, not judged: the orientation field
(structure tensor of the luminance, strands run across the gradient) over the hair of a reference crop and the same
framing of ours, per grid cell: angle in degrees (0 = horizontal, + = rising to the picture's right; axial, mod 180)
and coherence. Prints both grids and the coherence-weighted mean |difference| over cells where both have hair.
In a profile / three-quarter crop facing picture left, + angles = up and BACK, - angles = up and FORWARD.
(Reviewers contradicted themselves round to round on comb direction: hair-garrett 2026-10-14.)"""
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

kw = dict(a.split("=", 1) for a in sys.argv[3:])
G = int(kw.get("grid", 6))
S = float(kw.get("sigma", 3))


def field(p):
    a = np.asarray(Image.open(p).convert("RGB").resize((480, 480), Image.LANCZOS), float) / 255
    L = a.mean(2)
    sat = a.max(2) - a.min(2)
    hair = (sat < 0.12) & (L < 0.72)  # grey hair: low saturation, darker than the backdrop (skin is saturated)
    hair = ndi.binary_opening(hair, iterations=2)
    gx = ndi.sobel(ndi.gaussian_filter(L, 1.0), 1)
    gy = ndi.sobel(ndi.gaussian_filter(L, 1.0), 0)
    jxx = ndi.gaussian_filter(gx * gx, S); jyy = ndi.gaussian_filter(gy * gy, S); jxy = ndi.gaussian_filter(gx * gy, S)
    th = 0.5 * np.arctan2(2 * jxy, jxx - jyy)  # gradient direction (image y down)
    coh = np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / (jxx + jyy + 1e-9)
    ang = np.degrees(th) + 90.0  # strand = across the gradient; flip y so + = rising to the right
    ang = -((ang + 90) % 180 - 90)
    ang = (ang + 90) % 180 - 90
    return ang, coh, hair


def cells(ang, coh, hair):
    n = ang.shape[0] // G
    out = np.full((G, G), np.nan); w = np.zeros((G, G))
    for i in range(G):
        for j in range(G):
            sl = (slice(i * n, (i + 1) * n), slice(j * n, (j + 1) * n))
            m = hair[sl]
            if m.mean() < 0.35:
                continue
            c = coh[sl][m]; t = np.radians(ang[sl][m]) * 2
            v = (c * np.exp(1j * t)).sum() / max(c.sum(), 1e-9)
            out[i, j] = np.degrees(np.angle(v) / 2); w[i, j] = abs(v)
    return out, w


R = cells(*field(sys.argv[1])); O = cells(*field(sys.argv[2]))
fmt = lambda g: "\n".join(" ".join("   ." if np.isnan(x) else f"{x:+4.0f}" for x in row) for row in g)
print("reference angles\n" + fmt(R[0]) + "\nours\n" + fmt(O[0]))
both = ~np.isnan(R[0]) & ~np.isnan(O[0])
d = np.abs(((R[0] - O[0]) + 90) % 180 - 90)
w = np.minimum(R[1], O[1])
print(f"cells {both.sum()}  mean |diff| {np.nansum(d[both] * w[both]) / max(w[both].sum(), 1e-9):.1f} deg"
      f"  ref mean {np.nanmean(R[0][both]):+.1f}  ours mean {np.nanmean(O[0][both]):+.1f}")
