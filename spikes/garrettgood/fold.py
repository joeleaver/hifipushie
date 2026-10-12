"""fold.py <model> <out> [fold]: THE EYE STEP as a test (lid_read(match=True), default the crisp fold = recipe A) on a
solved head: is it unforced here? Prints the step's report, |c| before / after, |dc|, the largest component."""
import sys
import numpy as np
from hifipushie import server, blockin as bi, store
src, out = sys.argv[1], sys.argv[2]
kw = {"fold": sys.argv[3]} if len(sys.argv) > 3 else {}
r = server.lid_read(src, match=True, out=out, save=f"/mnt/data/hifipushie/garrettgood/out/{out}.png", **kw)
print(r if isinstance(r, str) else "\n".join(x for x in r if isinstance(x, str)))
a, b = bi.identity(store.load(src)), bi.identity(store.load(out))
print(f"\nFOLD TEST {src} -> {out} ({kw or 'crisp'}): |c| {np.linalg.norm(a):.2f} -> {np.linalg.norm(b):.2f}, |dc| {np.linalg.norm(b - a):.2f}, "
      f"largest component {np.abs(b).max():.2f} sd, comps past 2.5 sd {int((np.abs(b) > 2.5).sum())}, past 3 sd {int((np.abs(b) > 3).sum())}")
