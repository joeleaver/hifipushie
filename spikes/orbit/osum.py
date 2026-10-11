"""osum.py: oval.py ruler's table: per variant / view subset, reader - truth for the orbit measures and the rows as
seen (bias / sd / rms, mm), the measure's population sd over the rms (S/N), and the mean error the solve itself claimed.
The one mesh takes the head's SIZE from the body, so (as faceruler's dval) the uniform-size part is taken out of both
sides' gaps before they are compared."""
import json
import os

import numpy as np

from hifipushie import gnm_mm

G = os.environ["G"] + "/out"
import glob
import sys
rows = [r for f in sorted(glob.glob(f"{G}/oval_ruler{sys.argv[1] if len(sys.argv) > 1 else ''}*.json")) for r in json.load(open(f))]
sd = gnm_mm.sd()
N = list(gnm_mm.NAMES)
sp = gnm_mm._space()
m0 = np.array([gnm_mm.readers(sp["T"])[m] for m in N])
w = 1.0 / np.array([sd[m] for m in N]) ** 2
J = gnm_mm.jacobian()[:len(N)]


def shape(g):
    g = np.asarray(g, float)
    return g - (g * m0 * w).sum() / (m0 * m0 * w).sum() * m0


def seen(g):
    return {row: sum(wt * g[N.index(k)] for k, wt in comb.items()) for row, comb in gnm_mm.ORBIT_SEEN.items()}


keys = [k for k in rows[0] if "/" in k and not k.endswith(("_orbit", "_cam", "_n")) and all(k in r for r in rows)]
print(f"{len(rows)} pairs (model A, dressed pictures of B, hair masked); truth gap rms: "
      + ", ".join(f"{m} {np.sqrt(np.mean([r['truth'][m] ** 2 for r in rows])):.1f}" for m in gnm_mm.ORBIT))
for key in keys:
    rr = [r for r in rows if key in r]
    T = np.array([shape([r["truth"][m] for m in N]) for r in rr])
    R = np.array([shape([r[key][m][0] for m in N]) for r in rr])
    E = np.array([[r[key][m][1] for m in N] for r in rr])
    print(f"\n== {key} ({len(rr)} pairs; reads: {rr[0][key + '_n']})")
    for m in gnm_mm.ORBIT:
        i = N.index(m)
        e = R[:, i] - T[:, i]
        print(f"   {m:22s} pop sd {sd[m]:4.1f} | bias {e.mean():+5.2f} sd {e.std():4.2f} rms {np.sqrt((e ** 2).mean()):4.2f} ({sd[m] / np.sqrt((e ** 2).mean()):3.1f}x) | the solve's own +- {E[:, i].mean():.2f}")
    for row, comb in gnm_mm.ORBIT_SEEN.items():
        a = np.zeros(len(N))
        for k, wt in comb.items():
            a[N.index(k)] = wt
        e = (R - T) @ a
        psd = float(np.linalg.norm(a @ J))
        print(f"   seen: {row:24s} pop sd {psd:4.1f} | bias {e.mean():+5.2f} sd {e.std():4.2f} rms {np.sqrt((e ** 2).mean()):4.2f} ({psd / np.sqrt((e ** 2).mean()):3.1f}x)")
    cams = [r[key + "_cam"] for r in rr if r.get(key + "_cam") and r[key + "_cam"][0]]
    if key.startswith("off") and cams:
        # the cameras' yaw: put off by offs[k][4], the solve's turn back
        kinds = ["front", "3q", "profile"] if "all" in key else (["front", "profile"] if "f+p" in key else ["front", "3q"])
        for vi, k in enumerate(kinds):
            d = np.array([r[key + "_cam"][0][vi][4] + r["offs"][k][4] for r in rr])
            print(f"   camera yaw left after the solve, {k}: bias {d.mean():+.2f} sd {d.std():.2f} deg (put off by sd {np.std([r['offs'][k][4] for r in rr]):.1f})")
