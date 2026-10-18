"""orgrid.py <img> [...]: the signed axial orientation of a crop in a 4 x 4 grid of windows (structure tensor, 1.5 px
gradients, coherence-weighted doubled angle): deg, + = rising to the image's right, 0 = across; '.' = no hair (light
or flat window). Compares a reference crop's flow FIELD with ours (laycal's lay is |angle| only: no sign, no place)."""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage as nd

def grid(p, n=4):
    L = np.asarray(Image.open(p).convert("L"), float)
    gx = nd.gaussian_filter(L, 1.5, order=(0, 1)); gy = nd.gaussian_filter(L, 1.5, order=(1, 0))
    jxx, jyy, jxy = gx * gx, gy * gy, gx * gy
    z = (jxx - jyy) + 2j * (-jxy)  # y up
    hair = nd.uniform_filter(L, 25) < 150
    h, w = L.shape
    out = []
    for i in range(n):
        row = []
        for j in range(n):
            sl = (slice(i * h // n, (i + 1) * h // n), slice(j * w // n, (j + 1) * w // n))
            m = hair[sl]
            if m.mean() < 0.4:
                row.append("    .    "); continue
            zz = z[sl][m].sum() / (jxx[sl][m] + jyy[sl][m]).sum()
            th = np.degrees(np.angle(zz) / 2) + 90  # strand = across the gradient
            th = (th + 90) % 180 - 90
            row.append(f"{th:+5.0f}/{abs(zz):.2f}")
        out.append(row)
    return out

for p in sys.argv[1:]:
    print(p.rsplit("/", 1)[-1])
    for r in grid(p):
        print("   " + "  ".join(r))
