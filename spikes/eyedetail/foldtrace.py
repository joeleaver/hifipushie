"""foldtrace.py <model> <tag>: the crease line traced on the photo and on ours (eyeshot's front close-up pair, the
same fitted camera, so pixels line up), read_lid at 20 columns corner to corner. Prints per third TPS (mm, the
model's scale) and the lateral extent (the last column from the outer corner where a line is found, dark > 0.12),
photo vs ours; writes out/<tag>_trace.png: the eye crops of photo | ours, each with the PHOTO's crease (red) and
OUR crease (green) and the lash line (yellow) drawn over it."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import stage
from hifipushie import likeness, lidfold, store
from hifipushie.likeness_eyes import frame
from hifipushie.spec import expand_mirror

name, tag = sys.argv[1], sys.argv[2]
E = "/mnt/data/hifipushie/eyedetail/out"
spec = store.load(name)
J = {k: np.asarray(v["pos"], float) for k, v in expand_mirror(spec)["joints"].items() if "pos" in v}
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
v, cam = refs["views"][0], refs["cameras"][0]
U = np.array(list(v["points"].values()), float)
lo, hi = U.min(0), U.max(0)
s = 0.95 * (hi - lo)[0] * float(os.environ.get("ZOOM_SCALE", "1"))
c = np.array([0.5 * (lo[0] + hi[0]), lo[1] + 0.55 * (hi[1] - lo[1])])
fr = stage.fitted_frame(cam, [c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2], "zoom")
dist = float(np.linalg.norm(0.5 * (J["eye.L"] + J["eye.R"]) - np.asarray(fr["eye"])))
FR = np.linspace(0.04, 1.0, 25)
UP = 2


def trace(im):
    mmpx = 2 * dist * np.tan(np.radians(fr["fov"]) / 2) * 1000 / im.width
    big = im.resize((im.width * UP, im.height * UP), Image.LANCZOS)
    d = likeness.detect([big])[0]
    if d is None:
        return None
    P = np.asarray(d, float)[:, :2]
    r = lidfold.read_lid(big, P, mmpx / UP, fractions=FR)
    ex, ey = (np.asarray(a, float) for a in frame(P))
    k = mmpx / UP
    out = []
    for sd, cols in zip((0, 1), r):
        pi, po = P[lidfold.INNER[sd]], P[lidfold.OUTER[sd]]
        span = float((po - pi) @ ex)
        pts, lash = [], []
        for f, c_ in zip(FR, cols):
            t = f * span
            lid = lidfold._interp_curve(P, lidfold.UPPER[sd], t, ex, ey, pi)
            b = pi + t * ex + lid * ey
            lash.append(b / UP)
            ok = np.isfinite(c_["tps"]) and c_["dark"] > 0.12
            pts.append((b - c_["tps"] / k * ey) / UP if ok else None)
        out.append({"cols": cols, "pts": pts, "lash": lash})
    return out


pair = Image.open(f"{E}/{tag}_face.png").convert("RGB")
w = pair.width // 2
ph, ours = pair.crop((0, 0, w, pair.height)), pair.crop((w, 0, 2 * w, pair.height))
tp, to = trace(ph), trace(ours)


def thirds(tr):
    res = []
    for e in tr:
        vals = np.array([c_["tps"] if c_["dark"] > 0.12 else np.nan for c_ in e["cols"]])
        thr = [np.nanmean(vals[(FR >= a) & (FR < b)]) for a, b in ((0, 0.34), (0.34, 0.67), (0.67, 1.01))]
        found = np.flatnonzero(np.isfinite(vals))
        res.append((thr, float(FR[found.max()]) if len(found) else np.nan, float(FR[found.min()]) if len(found) else np.nan))
    return res


for lab, tr in (("photo", tp), ("ours", to)):
    if tr is None:
        print(lab, "no face")
        continue
    for sd, (thr, out_f, in_f) in zip(("R", "L"), thirds(tr)):
        print(f"{lab:>6} {sd}: TPS inner / middle / outer {thr[0]:5.2f} {thr[1]:5.2f} {thr[2]:5.2f} mm; line found from "
              f"{in_f:.2f} to {out_f:.2f} of the way inner -> outer corner")
# overlay
S = Image.new("RGB", (2 * w, pair.height))
for i, im in enumerate((ph, ours)):
    im = im.copy()
    d = ImageDraw.Draw(im)
    for tr, col in ((tp, (255, 40, 40)), (to, (40, 230, 40))):
        if tr is None:
            continue
        for e in tr:
            pts = [tuple(p) for p in e["pts"] if p is not None]
            if len(pts) > 1:
                d.line(pts, fill=col, width=2)
    if tp is not None:
        for e in tp:
            d.line([tuple(p) for p in e["lash"]], fill=(255, 220, 0), width=1)
    S.paste(im, (i * w, 0))
S.save(f"{E}/{tag}_trace.png")
print("saved", f"{E}/{tag}_trace.png")
