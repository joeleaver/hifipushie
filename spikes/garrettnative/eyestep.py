"""eyestep.py <src> <out> [fold=none] [expression=0]: THE EYE STEP as the tool does it (server.lid_read match=True:
identity only, the opening solved for the eye ruler's margins and canthi in mm; fold="none": no designed fold), then
|c|, the largest component and the eye ruler again."""
import sys

import numpy as np

from hifipushie import blockin as bi, server, store

src, out = sys.argv[1:3]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
G = "/mnt/data/hifipushie/garrettnative/out"
r = server.lid_read(src, match=True, out=out, fold=kw.get("fold", "none"), expression=kw.get("expression", "0") == "1",
                    seen="eye ruler: opening at the pupil +3.0 mm, lower margin 2.5 mm low, fissure +6.7 mm against the front painting",
                    save=f"{G}/eyestep_{out}.png")
print(r[-1] if isinstance(r, list) else r)
c0, c = bi.identity(store.load(src)), bi.identity(store.load(out))
print(f"== {out}: |dc| {np.linalg.norm(c - c0):.2f}; |c| {np.linalg.norm(c):.2f}, largest {np.abs(c).max():.2f} sd")
r = server.eye_ruler(out, save=f"{G}/er_{out}.png")
print(r[-1] if isinstance(r, list) else r)
