"""irismeas.py <model> <eye png (ours, the eye crop)> [<photo pair png>]: the render's scale at eye.L (px per mm from the
fitted camera), the iris' and the opening's widths along the pupil's row in ours (and, by the same scale, in the
photo's crop), against what the spec asks (skin.eyes.iris_size) and anatomy (11-12.5 mm)."""
import json
import sys

import numpy as np
from PIL import Image

import stage
from hifipushie import store
from hifipushie.spec import expand_mirror

name, png = sys.argv[1], sys.argv[2]
spec = store.load(name)
J = {k: np.asarray(v["pos"], float) for k, v in expand_mirror(spec)["joints"].items() if "pos" in v}
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
v, cam = refs["views"][0], refs["cameras"][0]
U = np.array(list(v["points"].values()), float)
lo, hi = U.min(0), U.max(0)
s = 0.95 * (hi - lo)[0]
a, b = np.asarray(v["points"]["lm45"], float), np.asarray(v["points"]["lm36"], float)
ec = a + 0.17 * (b - a)
es = 0.3 * s
fr = stage.fitted_frame(cam, [ec[0] - es / 2, ec[1] - es / 2, ec[0] + es / 2, ec[1] + es / 2], "eye")
img = np.asarray(Image.open(png).convert("RGB"), float)
PX = img.shape[1]
dist = float(np.linalg.norm(J["eye.L"] - np.asarray(fr["eye"])))
ppmm = PX / (2 * dist * np.tan(np.radians(fr["fov"]) / 2)) / 1000
print(f"camera {dist:.3f} m from eye.L, {ppmm:.2f} px/mm")


def widths(im):
    L = im.mean(2)
    # the pupil: the darkest blob's centre
    y, x = np.unravel_index(np.argmin(np.where(L < 25, 0, 1e9) + L), L.shape)
    ys, xs = np.nonzero(L < 25)
    cy, cx = int(np.median(ys)), int(np.median(xs))
    row = im[cy - 2:cy + 3].mean(0)
    sat = row.max(1) - row.min(1)
    Lr = row.mean(1)
    # iris: from the pupil outward until the sclera (bright and unsaturated) begins
    scl = (Lr > 0.8 * np.percentile(Lr, 98)) & (sat < 40)
    l_ = cx - np.argmax(scl[cx::-1])
    r_ = cx + np.argmax(scl[cx:])
    pw = np.count_nonzero(L[cy] < 25)
    return cx, cy, (r_ - l_), pw


cx, cy, iw, pw = widths(img)
sk = (spec.get("skin") or {}).get("eyes") or {}
print(f"ours: iris {iw / ppmm:.1f} mm wide across the pupil's row, pupil {pw / ppmm:.1f} mm "
      f"(spec iris_size {sk.get('iris_size', 'default')} pupil {sk.get('pupil', 0.36)})")
if len(sys.argv) > 3:
    pair = np.asarray(Image.open(sys.argv[3]).convert("RGB"), float)
    ph = pair[:, :pair.shape[1] // 2]
    cx, cy, iw2, pw2 = widths(ph)
    print(f"photo (same crop scale): iris {iw2 / ppmm:.1f} mm, pupil {pw2 / ppmm:.1f} mm")
