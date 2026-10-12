"""shade.py <copy> [..]: the COLOUR OF SHADE in a picture set, from the cached frames ($G/out/frames_<copy>.pkl).
Over the trusted skin pixels (lips, brows left out): regress log(rho_c) on log(rho_Y) (rho = picture / our render, levelled
on the plain skin): slopes q_r, q_g, q_b. Neutral shade: 1, 1, 1. Warm (bounce light off skin, scatter): q_r < 1 < q_b.
Also per region: d L / a / b against the plain skin's."""
import os, pickle, sys
import numpy as np
from hifipushie import skin_read as sr

G = os.environ["G"] + "/out"
Y = np.array([0.2126, 0.7152, 0.0722])
for name in sys.argv[1:]:
    frames = pickle.load(open(f"{G}/frames_{name}.pkl", "rb"))
    c = sr.context(name, frames=frames, log=lambda s: None)
    R = sr.regions(c)
    skin = np.max([R[z] for z in sr.ZONES], 0)
    lips = c.alb.zone("lips", 1.4)
    brow = c.alb.zone("brow", 2.5)
    print(f"== {name}")
    for v in c.views + [{"view": None}]:
        m = (c.w > 0) & (skin > 0.3) & (lips < 0.05) & (brow < 0.05) & ((c.view == v["view"]) if v["view"] is not None else True)
        lr = np.log(np.maximum(c.rho[m], 1e-4))
        ly = np.log(np.maximum(c.rho[m] @ Y, 1e-4))
        ly0 = np.median(ly)
        x = ly - ly0
        for lab_, sel in (("all", np.ones(len(x), bool)), ("darker", x < -0.05), ("lighter", x > 0.05)):
            if sel.sum() < 500:
                continue
            q = [float(np.polyfit(x[sel], lr[sel][:, k] - np.median(lr[:, k]), 1)[0]) for k in range(3)]
            print(f"  view {v['view']}: {lab_:8s} n {sel.sum():7d}  q r g b = {q[0]:.3f} {q[1]:.3f} {q[2]:.3f}   (spread of log Y {x[sel].std():.3f})")
    plain = c.plain > 0.5
    d0 = sr._wmedian(c.dlab[plain], c.w[plain] + 1e-9)
    print("  plain d", np.round(d0, 2))
    for k in sr.ZONES:
        W = c.w * R[k]
        if W.sum() < sr.MIN_PX:
            continue
        d = sr._wmedian(c.dlab, W) - d0
        print(f"  {k:14s} px {W.sum():7.0f}  d - plain: L {d[0]:+6.2f} a {d[1]:+5.2f} b {d[2]:+5.2f}")
