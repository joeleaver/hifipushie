"""bm.py <tag>=<image> ...: the BROW over the upper lid, read the same way on a photo and on our renders (gnmbrow).
Per eye and column (inner third / pupil / outer third between the eye corners, MediaPipe points): the luminance up the
face from the upper lid margin, averaged over a 2 mm strip and blurred 1 mm; the brow = the darkest broad band 3-28 mm
up; its LOWER EDGE = where the profile is half way between the skin under it and the band's core. Everything in iris
diameters (the picture's own iris, no mm assumed) and in mm at an 11.7 mm iris.
Also: eye opening, eye width, pupil distance in iris diameters (scale checks) and the detector's own brow points.
Writes out/bm_<tag>.png (the columns and edges drawn) and out/bm.json (appended)."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import likeness, lidfold
from hifipushie.likeness_eyes import frame

G = os.environ.get("G", "/mnt/data/hifipushie/gnmbrow") + "/out"
BROW_UP = ((70, 63, 105, 66, 107), (300, 293, 334, 296, 336))
LOWER = ((33, 7, 163, 144, 145, 153, 154, 155, 133), (263, 249, 390, 373, 374, 380, 381, 382, 362))
FR = (0.25, 0.5, 0.75)


def read(img, P=None, draw=None):
    if P is None:
        P = likeness.detect([img])[0]
    P = np.asarray(P, float)[:, :2]
    L = lidfold._lum(img)
    ex, ey = (np.asarray(v, float) for v in frame(P))
    out = {"eyes": []}
    irs = []
    for s in (0, 1):
        r = np.mean([np.linalg.norm(P[i] - P[lidfold.IRIS_C[s]]) for i in lidfold.IRIS_RIM[s]])
        irs.append(2 * r)
    D = float(np.mean(irs))                    # iris diameter, px
    k = lidfold.IRIS_MM / D                    # mm / px at an 11.7 mm iris
    out["iris_px"] = D
    out["pd_iris"] = float(np.linalg.norm(P[473] - P[468]) / D)
    for s in (0, 1):
        pi, po = P[lidfold.INNER[s]], P[lidfold.OUTER[s]]
        span = float((po - pi) @ ex)
        e = {"width_iris": abs(span) / D, "cols": []}
        for f in FR:
            t = f * span
            lid = lidfold._interp_curve(P, lidfold.UPPER[s], t, ex, ey, pi)
            low = lidfold._interp_curve(P, LOWER[s], t, ex, ey, pi)
            b_lo = lidfold._interp_curve(P, lidfold.BROW_LOW[s], t, ex, ey, pi)
            b_up = lidfold._interp_curve(P, BROW_UP[s], t, ex, ey, pi)
            up = np.arange(0.0, 30.0, 0.05)
            hh = lid - up / k
            strip = np.linspace(-1.0, 1.0, 11) / k
            prof = np.mean([lidfold._bilinear(L, *(pi + (t + w) * ex + hh[:, None] * ey).T) for w in strip], 0)
            g = np.exp(-0.5 * (np.arange(-40, 41) * 0.05 / 0.5) ** 2)
            sm = np.convolve(np.pad(prof, 40, mode="edge"), g / g.sum(), mode="valid")
            i0, i1 = int(3.0 / 0.05), len(up) - 1
            ic = i0 + int(np.argmin(sm[i0:i1]))
            core = sm[ic]
            j0 = int(2.0 / 0.05)
            skin_lo = float(np.percentile(sm[j0:max(ic, j0 + 1)], 90))
            skin_hi = float(np.percentile(sm[ic:], 90))
            half = 0.5 * (skin_lo + core)
            i = ic
            while i > j0 and sm[i] < half:
                i -= 1
            half2 = 0.5 * (skin_hi + core)
            j = ic
            while j < len(up) - 1 and sm[j] < half2:
                j += 1
            c = {"edge_mm": float(up[i]), "edge_iris": float(up[i] / lidfold.IRIS_MM), "core_mm": float(up[ic]),
                 "top_mm": float(up[j]), "contrast": float((skin_lo - core) / max(skin_lo, 1e-6)),
                 "mp_low_mm": float((lid - b_lo) * k), "mp_up_mm": float((lid - b_up) * k),
                 "open_iris": float((low - lid) / D)}
            e["cols"].append(c)
            if draw is not None:
                base = pi + t * ex
                for hmm, colr in ((0.0, (0, 255, 0)), (c["edge_mm"], (255, 0, 0)), (c["core_mm"], (255, 255, 0)), (c["top_mm"], (255, 0, 255))):
                    q = base + (lid - hmm / k) * ey
                    draw.line([tuple(q - 6 * ex), tuple(q + 6 * ex)], fill=colr, width=2)
                q0, q1 = base + lid * ey, base + (lid - 30 / k) * ey
                draw.line([tuple(q0), tuple(q1)], fill=(0, 200, 255), width=1)
        out["eyes"].append(e)
    return out


def summary(r):
    """Mean of both eyes per column: lower edge in mm (11.7 iris) / iris diameters."""
    E = np.array([[c["edge_mm"] for c in e["cols"]] for e in r["eyes"]])
    C = np.array([[c["core_mm"] for c in e["cols"]] for e in r["eyes"]])
    O = np.array([[c["open_iris"] for c in e["cols"]] for e in r["eyes"]])
    return {"edge_mm": E.mean(0).round(2).tolist(), "edge_iris": (E.mean(0) / lidfold.IRIS_MM).round(3).tolist(),
            "core_mm": C.mean(0).round(2).tolist(), "open_iris_mid": float(O[:, 1].mean().round(3)),
            "width_iris": float(np.mean([e["width_iris"] for e in r["eyes"]]).round(3)), "pd_iris": round(r["pd_iris"], 3),
            "iris_px": round(r["iris_px"], 1), "per_eye_edge_mm": E.round(2).tolist()}


if __name__ == "__main__":
    jf = f"{G}/bm.json"
    allr = json.load(open(jf)) if os.path.exists(jf) else {}
    for a in sys.argv[1:]:
        tag, path = a.split("=", 1)
        im = Image.open(path).convert("RGB")
        dbg = im.copy()
        r = read(im, draw=ImageDraw.Draw(dbg))
        dbg.save(f"{G}/bm_{tag}.png")
        s = summary(r)
        allr[tag] = s
        print(tag, json.dumps(s), flush=True)
    json.dump(allr, open(jf, "w"), indent=1)
