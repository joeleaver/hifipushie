"""secplot.py <prof json> <out png> [label=key ...]: sagittal sections of the upper lid at the inner third / pupil / outer third
(col.py columns 0.25 / 0.5 / 0.75; (forward, up) mm relative to the lid margin, the eye's centre behind), and the fold line
across the lid (crease height over the margin per column) + the platform shown per column."""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

D = json.load(open(sys.argv[1]))
items = [a.split("=", 1) if "=" in a else (a, a) for a in sys.argv[3:]] or [(k, k) for k in D]
FR = (0.12, 0.25, 0.37, 0.5, 0.63, 0.75, 0.88)
cols_ix = {"inner third": 1, "pupil": 3, "outer third": 5}
colors = ["#222222", "#cc3311", "#0077bb", "#33aa55", "#ee7733", "#aa3377"]
fig, ax = plt.subplots(1, 5, figsize=(22, 5.2), gridspec_kw={"width_ratios": [1, 1, 1, 1.3, 1.3]})
for j, (key, lab) in enumerate(items):
    d = D[key]
    for a, (nm, ci) in zip(ax[:3], cols_ix.items()):
        P = d["prof"][ci]
        if P is None:
            continue
        P = np.asarray(P) * 1000
        P = P - P[0]
        c = d["cols"][ci]
        a.plot(P[:, 0], P[:, 1], color=colors[j], lw=2, label=lab)
        # the crease (reader's height) marked
        hh = c["h"]
        k = int(np.argmin(np.abs(P[:, 1] - hh)))
        a.plot(P[k, 0], P[k, 1], "o", color=colors[j], ms=6)
        a.set_title(f"section at the {nm}")
    h = [c["h"] if c else np.nan for c in d["cols"]]
    sh = [c["show"] if c else np.nan for c in d["cols"]]
    ax[3].plot(FR, h, "-o", color=colors[j], label=lab)
    ax[4].plot(FR, sh, "-o", color=colors[j], label=lab)
import os
if os.environ.get("PHOTO"):
    pts = [tuple(map(float, q.split(":"))) for q in os.environ["PHOTO"].split(",")]
    ax[3].plot([p[0] for p in pts], [p[1] for p in pts], "k*--", ms=16, label="Tess photo's line (at our iris scale)")
for a in ax[:3]:
    a.set_aspect("equal"); a.set_xlabel("forward, mm (toward the camera)"); a.set_ylabel("up over the lid margin, mm")
    a.set_ylim(-1, 13); a.grid(alpha=0.3)
ax[0].legend(fontsize=9)
ax[3].set_title("the fold line across the lid: crease height over the margin"); ax[3].set_xlabel("inner corner -> outer corner")
ax[3].set_ylabel("mm"); ax[3].set_ylim(0, 9); ax[3].grid(alpha=0.3); ax[3].legend(fontsize=9)
ax[4].set_title("platform shown from the front"); ax[4].set_xlabel("inner corner -> outer corner"); ax[4].set_ylabel("mm")
ax[4].set_ylim(0, 8); ax[4].grid(alpha=0.3)
plt.tight_layout()
plt.savefig(sys.argv[2], dpi=100)
print("wrote", sys.argv[2])
