"""cmp_locks.py <model> <out.npy>: a 3-view look of the model's hair as saved (style "locks"), as a raw array.
Run once with this branch and once with PYTHONPATH=<main>/src, then compare the arrays (cmp_locks.py a.npy b.npy)."""
import sys, os
import numpy as np
if sys.argv[1].endswith(".npy"):
    a, b = np.load(sys.argv[1]).astype(int), np.load(sys.argv[2]).astype(int)
    print("shape", a.shape, b.shape, "max diff", int(np.abs(a - b).max()) if a.shape == b.shape else "n/a",
          "differing px", int((np.abs(a - b).max(-1) > 0).sum()) if a.shape == b.shape else "n/a")
    sys.exit()
import hifipushie
from hifipushie import hair, store
name, out = sys.argv[1], sys.argv[2]
spec = store.load(name)
print("code", os.path.dirname(hifipushie.__file__), "style", spec["hair"].get("style", "locks"))
sheet, sec, fr = hair.look(name, views=("front", "three_quarter", "back"), size=320, spec=spec)
np.save(out, np.asarray(sheet))
