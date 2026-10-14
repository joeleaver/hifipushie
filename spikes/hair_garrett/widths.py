"""widths.py <model> [views=0,1] [tags=a,b]: the hair's outline by HEIGHT, ours vs the picture, through the fitted cameras:
per 1 cm band from the head centre's height down, the hair-or-head mask's width (front-ish views) or its reach behind
the skull's back edge (side views), mm. Masks from the face parser (hair + face + skin), so a cluttered room or a
dark couch does not matter (the reader's stand-off only counts where the hair meets the backdrop, and her room hid
most of the outline). Ours from $TOUT/s_<model>_v<i>.png."""
import os
import sys

import numpy as np
from scipy import ndimage as ndi

from hifipushie import hair_read, store

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
OUT = os.environ["TOUT"]
views = [int(v) for v in kw.get("views", "0,1").split(",")]
spec = store.load(m)
fp = hair_read.frames(m, spec)
fo = hair_read.frames(m, spec, images={i: f"{OUT}/s_{m}_v{i}.png" for i in views})


def mask(f):
    hm = ndi.binary_opening(f["hair"] > 0.5, iterations=2)
    lab, n = ndi.label(hm)
    if n > 1:
        sz = ndi.sum(hm, lab, range(1, n + 1))
        hm = np.isin(lab, 1 + np.nonzero(sz >= 0.2 * sz.max())[0])
    return hm


for i in views:
    a = next(f for f in fp if f["i"] == i)
    b = next(f for f in fo if f["i"] == i)
    side = abs(((a["yaw"] + 180) % 360) - 180) > 60
    print(f"view {i} (yaw {a['yaw']:.0f}): {'reach behind the skull' if side else 'width'} by height, ours | picture (mm)")
    for name, f in (("picture", a), ("ours", b)):
        f["_m"] = mask(f)
    cy = a["c"][1]
    mm = a["mm"]
    for dz in range(-60, 241, 20):
        y = int(round(cy + dz / mm))
        vals = []
        for f in (b, a):
            row = f["_m"][max(y - 2, 0):y + 3].any(0)
            xs = np.nonzero(row)[0]
            if not len(xs):
                vals.append(None)
                continue
            if side:
                sk = np.nonzero(f["skull"][y])[0] if 0 <= y < f["skull"].shape[0] else np.zeros(0, int)
                if not len(sk):
                    vals.append(None)
                    continue
                back = sk.max() if a["c"][0] < sk.mean() else sk.min()  # (the skull's back edge on this row)
                far = xs.max() if a["c"][0] < sk.mean() else xs.min()
                vals.append(round(abs(far - back) * mm, 0) if len(sk) else None)
            else:
                vals.append(round((xs.max() - xs.min()) * mm, 0))
        print(f"  {dz:+4d} mm: {vals[0]} | {vals[1]}")
