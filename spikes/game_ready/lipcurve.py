"""lipcurve.py img ...: the smile's lower-lip curve against the corner-to-corner line (MediaPipe 478, % io, + = below the line).
Per contour (inner lower, outer lower, inner upper), the sag of each point measured perpendicular to the line through the
mouth corners (61 / 291), ordered corner -> corner; prints the middle sag, the sag at 1/4 and 3/4, and the 'bow' =
middle sag - mean of the quarter sags (a crescent has a deep middle and quarters well above it: bow > 0 large ~ round;
a slit has every point near 0). Also the sag profile resampled at 9 stations along the line."""
import sys, numpy as np
from PIL import Image
from hifipushie import likeness
C = {"in_lo": [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308],
     "out_lo": [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291],
     "in_up": [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308]}
fs = sys.argv[1:]; L = likeness.detect([Image.open(f).convert("RGB") for f in fs])
for f, l in zip(fs, L):
    name = "/".join(f.split("/")[-4:]) if "offload" in f else f.split("/")[-1]
    if l is None: print(name, "no face"); continue
    l = np.asarray(l, float)[:, :2]; io = np.linalg.norm(l[[33, 133]].mean(0) - l[[362, 263]].mean(0))
    a, b = l[61], l[291]; t = (b - a) / np.linalg.norm(b - a); n = np.array([-t[1], t[0]])
    if n[1] < 0: n = -n
    W = np.linalg.norm(b - a)
    out = []
    for k, ids in C.items():
        p = l[ids]; u = (p - a) @ t / W; s = 100 * ((p - a) @ n) / io
        o = np.argsort(u); u, s = u[o], s[o]
        st = np.interp(np.linspace(0.1, 0.9, 9), u, s)
        mid, q = np.interp(0.5, u, s), (np.interp(0.25, u, s) + np.interp(0.75, u, s)) / 2
        out.append(f"{k} mid {mid:+.1f} q {q:+.1f} bow {mid - q:+.1f} [{' '.join(f'{v:+.1f}' for v in st)}]")
    print(f"{name}: width {100 * W / io:.0f}% io | " + " | ".join(out))
