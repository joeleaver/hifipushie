"""armlen.py <model> <garment>: the body's arm measures the draft uses vs the garment's sleeve (cap height, underarm
length, total), and the body's armpit -> wrist along the arm."""
import sys
import numpy as np
from hifipushie import cloth_workflow, pattern

c = cloth_workflow.Ctx(sys.argv[1], sys.argv[2])
m = c.meas
print({k: round(v, 1) for k, v in m.items() if any(s in k.lower() for s in ("wrist", "arm", "shoulder", "biceps", "elbow"))})
Bp = c.Bp
for nm in Bp["pieces"]:
    if nm.startswith("sleeve"):
        pc = Bp["pieces"][nm]
        P = pc["P"]
        def pt(n):
            return np.asarray(P[pattern.index_of(pc, n)], float)
        print(nm, "total", round(float(np.ptp(P[:, 1])) * 1000), "mm; capTop->underarm drop",
              round(float(pt("capTop")[1] - pt("underarmF")[1]) * 1000), "mm")
        break
b = c.body
J = b.J
for s in ("L",):
    sh, el, wr = (np.asarray(J[f"{j}.{s}"]) for j in ("shoulder", "elbow", "wrist"))
    print("joints shoulder->elbow->wrist", round(float(np.linalg.norm(el - sh) + np.linalg.norm(wr - el)) * 1000), "mm")
print("at:", {k: np.round(v, 3).tolist() for k, v in b.at.items() if "arm" in k or "shoulder" in k or "wrist" in k})
