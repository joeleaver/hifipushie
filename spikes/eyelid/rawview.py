"""rawview.py <out.png> <cols> <label>=<identity source> ...: GNM's RAW mesh round the left eye, no pipeline: per head a
front view of the quads (flat Lambert shade from a light 39 deg above the front, NO cast shadows: a down-facing band
reads dark, nothing more; every quad edge drawn = the mesh's resolution; ring 0 red, the crease rings 5-6 orange) and
under it the sagittal section at the pupil column (the rings as dots: stand-off from GNM's 14.5 mm ball against height
over the margin). Sources as lidstruct.ident. PHOTO=<png> puts a picture in the first cell."""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402

import lidmap as lm  # noqa: E402
import lidstruct as ls  # noqa: E402
from hifipushie import gnm_controls as gc  # noqa: E402

out, cols = sys.argv[1], int(sys.argv[2])
items = [a.split("=", 1) for a in sys.argv[3:]]
photo = os.environ.get("PHOTO")
n = len(items) + (1 if photo else 0)
rows = (n + cols - 1) // cols
g = gc.gnm()
t = lm.topo()
Q = g["quads"]
ext = g["groups"]["skin_exterior"]
Lg = np.array([0.1, 0.63, 0.77])
Lg /= np.linalg.norm(Lg)
fig, ax = plt.subplots(2 * rows, cols, figsize=(4.6 * cols, 6.4 * rows), gridspec_kw={"height_ratios": [3, 2] * rows})
ax = np.atleast_2d(ax)
for a in ax.ravel():
    a.axis("off")
k0 = 0
if photo:
    from PIL import Image
    ax[0, 0].imshow(Image.open(photo))
    ax[0, 0].set_title("REFERENCE: Tess, front picture", fontsize=10)
    k0 = 1
for i, (lab, src) in enumerate(items):
    r_, c_ = divmod(i + k0, cols)
    c = ls.ident(src)
    V = gc.vertices(c) * 1000
    ctr, r = lm.eye_frame_raw(c)
    X = V - ctr
    q = Q[ext[Q].all(1)]
    cen = X[q].mean(1)
    q = q[(np.abs(cen[:, 0]) < 19) & (cen[:, 1] > -9) & (cen[:, 1] < 17) & (cen[:, 2] > 0)]
    P = X[q]
    nrm = np.cross(P[:, 2] - P[:, 0], P[:, 3] - P[:, 1])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    if np.median(nrm[:, 2]) < 0:
        nrm = -nrm
    keep = nrm[:, 2] > 0.02
    P, nrm = P[keep], nrm[keep]
    sh = np.clip(nrm @ Lg, 0, 1) * 0.85 + 0.1
    o = np.argsort(P[:, :, 2].mean(1))
    a = ax[2 * r_, c_]
    a.add_collection(PolyCollection(P[o][:, :, :2], facecolors=plt.cm.gray(sh[o]), edgecolors=(0.15, 0.3, 0.6, 0.55), linewidths=0.35))
    for k, col in ((0, "red"), (5, "orange"), (6, "orange")):
        ids = t["loops"][k]
        ids = ids[g["T"][ids, 1] > g["J"][2][1] + 0.0005]
        ids = ids[np.argsort(X[ids, 0])]
        a.plot(X[ids, 0], X[ids, 1], color=col, lw=1.0)
    th = np.linspace(0, 2 * np.pi, 80)
    a.set_xlim(-18, 18)
    a.set_ylim(-8, 16)
    a.set_aspect("equal")
    a.plot([-17, -7], [-7, -7], "k", lw=2)
    a.text(-17, -6.5, "10 mm", fontsize=8)
    q_ = ls.mean_structure(c)
    a.set_title(f"{lab}\ntuck {q_['tuck']:.0f} deg, wall {q_['wall']:.0f}, platform {q_['platform_s']:.1f} mm off the ball, fold at {q_['crease_h']:.1f}", fontsize=9)
    b = ax[2 * r_ + 1, c_]
    b.axis("on")
    col = lm.column(V, ctr, 0.0)
    kk = np.array([x[0] for x in col if 0 <= x[0] <= 11])
    v = np.array([x[1] for x in col if 0 <= x[0] <= 11])
    w = np.array([x[2] for x in col if 0 <= x[0] <= 11])
    s = np.hypot(v, w) - r
    b.plot(s, v - v[0], "-o", ms=3.5, color="k", lw=1)
    for k_ in (5, 6):
        j = int(np.flatnonzero(kk == k_)[0])
        b.plot(s[j], v[j] - v[0], "o", ms=5, color="orange")
    b.axvline(0, color="gold", lw=2)
    b.set_xlim(-0.5, 9)
    b.set_ylim(-0.5, 12)
    b.set_aspect("equal")
    b.grid(alpha=0.3)
    b.set_xlabel("mm off the eyeball (gold) ->  forward", fontsize=8)
    b.set_ylabel("mm over the margin", fontsize=8)
    b.tick_params(labelsize=7)
fig.tight_layout(rect=(0, 0, 1, 0.975))
fig.savefig(out, dpi=95)
print("saved", out)
