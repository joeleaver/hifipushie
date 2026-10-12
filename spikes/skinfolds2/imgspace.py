"""imgspace.py <model> [frames=<pkl tag>]: IMAGE-SPACE colour, like with like: per view and region the picture's pixels
(levelled to our render's exposure by the plain skin: P / gain) against our render's at the same pixels, CIE Lab of the
weighted mean (what the eye compares on a sheet), beside the reader's albedo-space d. Regions: plain, lips, eye zones,
lower face. frames= reads $G/out/frames_<tag>.pkl instead of capturing."""
import os, pickle, sys
import numpy as np
from hifipushie import skin_read as sr

name = sys.argv[1]
kw = dict(a.split("=") for a in sys.argv[2:])
G = os.environ["G"] + "/out"
f_ = f"{G}/frames_{kw.get('frames', name)}.pkl"
frames = pickle.load(open(f_, "rb")) if os.path.exists(f_) else sr.capture(name, log=lambda s: None)
if not os.path.exists(f_):
    pickle.dump(frames, open(f_, "wb"))
c = sr.context(name, frames=frames, log=lambda s: None)
R = sr.regions(c)
R["PLAIN"] = (c.plain > 0.5).astype(float)
R["FACE"] = np.max([R[z] for z in sr.ZONES], 0)
rows = ["PLAIN", "FACE", "lip_upper", "lip_lower", "eyelid", "under_eye", "cheek", "forehead", "jaw", "jowl", "chin", "mouth_corner", "nose_tip"]
print(f"== {name}: image space (picture levelled to our exposure | our render | d) and the albedo-space read's d")
for v in c.views:
    f = next(q for q in frames if q["view"] == v["view"])
    m = c.view == v["view"]
    P = f["P"].reshape(-1, 3)[c.pix[m]] / np.asarray(v["gain"])
    Rr = f["R"].reshape(-1, 3)[c.pix[m]]
    print(f" view {v['view']} (gain {v['gain']}, weight {v['weight']})")
    for k in rows:
        W = (c.w[m] if not k.startswith("lip") else np.ones(m.sum())) * R[k][m]
        if W.sum() < 40:
            continue
        lp, lr = sr.lab((P * W[:, None]).sum(0) / W.sum()), sr.lab((Rr * W[:, None]).sum(0) / W.sum())
        da = sr._wmedian(c.dlab[m], W + 1e-12)
        print(f"   {k:13s} px {W.sum():7.0f}  picture {np.round(lp, 1)}  ours {np.round(lr, 1)}  d {np.round(lp - lr, 1)}   hue {np.degrees(np.arctan2(lp[2], lp[1])):5.1f} / {np.degrees(np.arctan2(lr[2], lr[1])):5.1f}"
              f"   | albedo-space d {np.round(da, 1)}")
