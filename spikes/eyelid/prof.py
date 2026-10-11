"""prof.py <tag> ...: the HOLISTIC lid read: luminance up vertical columns from the lash line to the brow, on fitted-
camera shots (out/s_<tag>.png dressed; "photo" = the picture; out/k_<tag>.png clay, read in the dressed shot's frame),
in each eye's ruler frame (eye_ruler.read: iris centre, margins). Columns u = -6, -3, 0, 3, 6 mm (2 mm wide strips), h =
0..14 mm above THAT image's upper margin at the column, luminance over the column's own bright skin level (its 85th
percentile over h 1..14): 1 = lit skin. Both eyes' mean.
Prints per tag: the fold line (the darkest narrow dip 2.5-8 mm up against the profile smoothed over 3 mm: height,
contrast), the platform's level (h 1 .. line - 0.7) and the drape's (line + 1 .. + 3.5), and the rms difference of the
whole profile (h 1..12, 5 columns) from the PHOTO's. Saves out/prof.json; profplot.py draws it."""
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter1d

from hifipushie import blockin_brows as bb, eye_ruler as er, likeness

G = os.environ["G"] + "/out"
bx = json.load(open(G + "/box.json"))
K, box = bx["K"], bx["box"]
q = bb._inputs("gd_T12")
mm = q["mm"]
COLS = (-6.0, -3.0, 0.0, 3.0, 6.0)
H = np.arange(0.0, 14.01, er.STEP)


def lum(A):
    return A[..., 0] * 0.2126 + A[..., 1] * 0.7152 + A[..., 2] * 0.0722


def profiles(A, eyes):
    """(eyes, cols, len(H)) luminance over the column's bright level."""
    out = []
    for e in eyes:
        fr = {k: np.asarray(v) for k, v in e["frame"].items() if k != "k"}
        pat = lum(er.patch(A, fr, e["frame"]["k"]))
        row = []
        for u in COLS:
            mv = float(np.interp(u, er.COLS, np.asarray(e["up"], float)))
            j0, j1 = er._iu(u - 1.0), er._iu(u + 1.0)
            col = np.nanmedian(pat[:, j0:j1 + 1], axis=1)
            p = np.interp(mv + H, er.V, col)
            ref = np.percentile(p[(H >= 1.0)], 85)
            row.append(p / max(ref, 1e-6))
        out.append(row)
    return np.array(out)


def features(p):
    """On one profile: the fold line and the levels round it."""
    sm = gaussian_filter1d(p, 0.15 / er.STEP)
    wide = gaussian_filter1d(p, 1.5 / er.STEP)
    sel = (H >= 2.5) & (H <= 8.0)
    d = (wide - sm)
    i = int(np.flatnonzero(sel)[np.argmax(d[sel])])
    h = float(H[i])
    pl = (H >= 1.0) & (H <= h - 0.7)
    dr = (H >= h + 1.0) & (H <= h + 3.5)
    return {"line_h": h, "line": float(d[i]), "platform": float(sm[pl].mean()) if pl.any() else np.nan, "drape": float(sm[dr].mean())}


res = json.load(open(G + "/prof.json")) if os.path.exists(G + "/prof.json") else {}
for tag in sys.argv[1:]:
    if tag == "photo":
        img = q["img"]
        eyes = er.read(img, q["P"], mm, debug=True)
        A = np.asarray(img.convert("RGB"), float) / 255
        res["photo"] = {"s": profiles(A, eyes).tolist()}
        continue
    im = Image.open(f"{G}/s_{tag}.png").convert("RGB")
    P = likeness.detect([im])[0]
    if P is None:
        P = (q["P"] - box[:2]) * K
    P = np.asarray(P, float)[:, :2] / K + box[:2]
    eyes = er.read(im, P, mm, scale=K, origin=box[:2], debug=True)
    res[tag] = {"s": profiles(np.asarray(im, float) / 255, eyes).tolist()}
    if os.path.exists(f"{G}/k_{tag}.png"):
        res[tag]["k"] = profiles(np.asarray(Image.open(f"{G}/k_{tag}.png").convert("RGB"), float) / 255, eyes).tolist()
json.dump(res, open(G + "/prof.json", "w"))
ph = np.array(res["photo"]["s"]).mean(0) if "photo" in res else None
sel = (H >= 1.0) & (H <= 12.0)
print(f"{'tag':10s} {'line h':>7s} {'line':>6s} {'platform':>8s} {'drape':>6s} {'plat/drape':>10s} {'rms vs photo':>12s}   (dressed; columns' mean)   | clay: line h, line, platform, drape")
for tag, v in res.items():
    if sys.argv[1:] and tag not in sys.argv[1:] and tag != "photo":
        continue
    p = np.array(v["s"]).mean(0)
    f = [features(x) for x in p]
    m = {k: float(np.nanmean([x[k] for x in f])) for k in f[0]}
    rms = float(np.sqrt(((p - ph)[:, sel] ** 2).mean())) if ph is not None else np.nan
    line = f"{tag:10s} {m['line_h']:7.2f} {m['line']:6.3f} {m['platform']:8.3f} {m['drape']:6.3f} {m['platform'] / m['drape']:10.3f} {rms:12.3f}"
    if "k" in v:
        fk = [features(x) for x in np.array(v["k"]).mean(0)]
        mk = {k: float(np.nanmean([x[k] for x in fk])) for k in fk[0]}
        line += f"   | {mk['line_h']:5.2f} {mk['line']:6.3f} {mk['platform']:6.3f} {mk['drape']:6.3f}"
    print(line)
