"""chinchk.py <model> <traces model> [line=chin]: does the front trace carry the chin's width? The traced chin line's
width at heights above its lowest point (menton) vs the model's silhouette matched to it (through the model's front
camera), mm; and the model's own full jaw-underside silhouette (every silhouette vertex below the mouth)."""
import json
import sys

import numpy as np

import outl
from hifipushie import humanfit, store

name, trm = sys.argv[1], sys.argv[2]
line = sys.argv[3] if len(sys.argv) > 3 else "chin"
sp = store.load(name)
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
v, cam = refs["views"][0], refs["cameras"][0]
o = np.asarray(outl.traced(trm, v["image"], (line,))[0], float)
st = humanfit.state(sp["base"])
Rc = humanfit._cam_rot(cam)
z = ((st["L"][:68] - np.asarray(cam["centre"])) @ Rc.T + np.asarray(cam["t"]))[:, 2].mean()
mmpx = z / cam["f"] * 1000


def width(P, h):
    """Width of a U-shaped polyline P (px) at h px above its lowest point."""
    y0 = P[:, 1].max()
    y = y0 - h
    xs = []
    for a, b in zip(P[:-1], P[1:]):
        if (a[1] - y) * (b[1] - y) <= 0 and a[1] != b[1]:
            t = (y - a[1]) / (b[1] - a[1])
            xs.append(a[0] + t * (b[0] - a[0]))
    return (max(xs) - min(xs)) * mmpx if len(xs) >= 2 else float("nan")


# the model's whole silhouette near the chin: a dense copy of the trace, extended sideways, matched
ext = np.r_[o[:1] + (o[0] - o[1]) * np.arange(6, 0, -1)[:, None], o, o[-1:] + (o[-1] - o[-2]) * np.arange(1, 7)[:, None]]
t = np.linspace(0, len(ext) - 1, 6 * len(ext))
dense = np.c_[np.interp(t, np.arange(len(ext)), ext[:, 0]), np.interp(t, np.arange(len(ext)), ext[:, 1])]
sl = humanfit._silhouette(st, cam, dense)
uv = humanfit.project(cam, sl["X"])
# order the matched model contour along the trace
M = uv[np.argsort(np.arange(len(uv)))]
print(f"mm/px {mmpx:.2f}; trace lowest y {o[:, 1].max():.1f}, model contour lowest y {M[:, 1].max():.1f}")
for hmm in (4, 8, 12, 16, 20):
    h = hmm / mmpx
    print(f"  {hmm:2d} mm above menton: trace width {width(o, h):6.1f} mm | model contour {width(M, h):6.1f} mm")
