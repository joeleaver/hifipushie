"""iris.py <tag>=<image>[@mm_per_px] ...: the iris' diameter by its LIMBUS edge (not the detector's iris points, which
under-read our renders by ~20 %): from the detector's iris centre, luminance along rays in the two lateral sectors
(+-35 deg about the eye's own axis: the lids cover the rest), the radius of the steepest dark -> light step within
0.6-1.8 detector radii, median over rays; centre refined once from the two sides. Also the iris' mean colour (sRGB,
the ring 0.45-0.85 r, lateral sectors, highlights dropped)."""
import sys

import numpy as np
from PIL import Image

from hifipushie import likeness, lidfold
from hifipushie.likeness_eyes import frame


def limbus(img, P):
    P = np.asarray(P, float)[:, :2]
    L = lidfold._lum(img)
    A = np.asarray(img.convert("RGB"), float) / 255.0
    ex, ey = (np.asarray(v, float) for v in frame(P))
    out = []
    for s in (0, 1):
        c = P[lidfold.IRIS_C[s]].copy()
        r0 = float(np.mean([np.linalg.norm(P[i] - c) for i in lidfold.IRIS_RIM[s]]))
        rr = np.arange(0.5 * r0, 1.9 * r0, 0.1)
        sm = max(1, int(round(0.04 * r0 / 0.1)))
        for _ in range(2):
            sides = []
            for sg in (-1, 1):
                rs = []
                for a in np.radians(np.arange(-35, 36, 5)):
                    d = sg * (np.cos(a) * ex + np.sin(a) * ey)
                    prof = lidfold._bilinear(L, *(c + rr[:, None] * d).T)
                    prof = np.convolve(prof, np.ones(2 * sm + 1) / (2 * sm + 1), mode="same")
                    g = np.gradient(prof)
                    g[:sm + 1] = g[-sm - 1:] = 0
                    rs.append(rr[int(np.argmax(g))])
                sides.append(float(np.median(rs)))
            c = c + 0.5 * (sides[1] - sides[0]) * ex
        r = 0.5 * (sides[0] + sides[1])
        cols = []
        for sg in (-1, 1):
            for a in np.radians(np.arange(-35, 36, 5)):
                d = sg * (np.cos(a) * ex + np.sin(a) * ey)
                for q in np.linspace(0.5, 0.85, 8) * r:
                    p = c + q * d
                    cols.append(A[int(round(p[1])), int(round(p[0]))])
        cols = np.array(cols)
        lum = cols.mean(1)
        keep = (lum < np.percentile(lum, 80)) & (lum > np.percentile(lum, 10))
        out.append({"d_px": 2 * r, "mp_px": 2 * r0, "rgb": cols[keep].mean(0)})
    return out


if __name__ == "__main__":
    for a in sys.argv[1:]:
        tag, path = a.split("=", 1)
        path, _, mm = path.partition("@")
        im = Image.open(path).convert("RGB")
        P = likeness.detect([im])[0]
        r = limbus(im, P)
        d = float(np.mean([e["d_px"] for e in r]))
        mp = float(np.mean([e["mp_px"] for e in r]))
        rgb = np.mean([e["rgb"] for e in r], 0)
        pd = float(np.linalg.norm(P[473, :2] - P[468, :2]))
        hexc = "#%02x%02x%02x" % tuple(int(round(255 * x)) for x in rgb)
        print(f"{tag}: limbus {d:.1f} px ({r[0]['d_px']:.1f} / {r[1]['d_px']:.1f}), detector {mp:.1f} px, pupil distance {pd:.1f} px "
              f"= {pd / d:.2f} irises, iris colour {hexc}" + (f", iris {d * float(mm):.2f} mm, pd {pd * float(mm):.1f} mm" if mm else ""), flush=True)
