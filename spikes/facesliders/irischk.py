"""irischk.py <eyes_*.png> : the iris' diameter and the opening (detector, px of each tile; ratios need no scale) on
eyesolve's sheet (photo | start | end tiles): iris / opening and iris / eye width per tile."""
import sys

import numpy as np
from PIL import Image

from hifipushie import likeness

im = Image.open(sys.argv[1]).convert("RGB")
T = im.height
for i, lab in enumerate(("photo", "start", "end")):
    t = im.crop((i * T, 0, i * T + T, T)).resize((2 * T, 2 * T), Image.LANCZOS)
    d = likeness.detect([t])[0]
    if d is None:
        print(lab, "no face")
        continue
    P = np.asarray(d, float)[:, :2]
    iris = np.mean([np.linalg.norm(P[469] - P[471]), np.linalg.norm(P[474] - P[476])])
    op = np.mean([np.linalg.norm(P[159] - P[145]), np.linalg.norm(P[386] - P[374])])
    wd = np.mean([np.linalg.norm(P[33] - P[133]), np.linalg.norm(P[263] - P[362])])
    print(f"{lab}: iris / opening {iris / op:.2f}, iris / eye width {iris / wd:.2f}, opening / width {op / wd:.2f}")
