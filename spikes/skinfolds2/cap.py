"""cap.py <source> <copy> [fresh=1]: fork <source> to <copy> (sg_* only; kept when it exists unless fresh=1), capture the
reader's frames of the copy (pickled to $G/out/frames_<copy>.pkl: the fit can then be iterated without Blender), and
print the EXPOSURE DECOMPOSITION per view: the picture's plain-skin luminance P, our render's R under the fitted light,
our albedo A there; P / A = the picture's light x exposure on the skin, R / A = ours."""
import os, pickle, sys
import numpy as np
from hifipushie import skin_read as sr, blockin as bi, store

src, dst = sys.argv[1:3]
kw = dict(a.split("=") for a in sys.argv[3:])
assert dst.startswith("sg_"), dst
G = os.environ["G"] + "/out"
if kw.get("fresh") or not (store._dir(dst) / "spec.json").exists():
    bi.fork(src, dst, replace=True)
frames = sr.capture(dst, log=print)
pickle.dump(frames, open(f"{G}/frames_{dst}.pkl", "wb"))
c = sr.context(dst, frames=frames, log=lambda s: None)
Y = np.array([0.2126, 0.7152, 0.0722])
for v in c.views:
    f = next(f_ for f_ in frames if f_["view"] == v["view"])
    m = (c.view == v["view"]) & (c.plain > 0.5) & (c.w > 0)
    P = f["P"].reshape(-1, 3)[c.pix[m]]; R = f["R"].reshape(-1, 3)[c.pix[m]]; A = c.A0[m]
    med = lambda a: float(np.median(a @ Y))
    print(f"view {v['view']}: plain px {m.sum()}  P Y {med(P):.3f} (L {sr.lab(np.median(P, 0))[0]:.1f})  R Y {med(R):.3f} (L {sr.lab(np.median(R, 0))[0]:.1f})  "
          f"A Y {med(A):.3f} (L {sr.lab(np.median(A, 0))[0]:.1f})  P/A {med(P) / med(A):.3f}  R/A {med(R) / med(A):.3f}  P/R {med(P) / med(R):.3f}  gain {v['gain']}")
    lt = sr.lighting(dst, v["view"])
    print("   light:", {k: lt[k] for k in ("fitted", "view", "exposure")}, [(round(l["energy"], 2)) for l in lt["lights"]], lt["world"])
