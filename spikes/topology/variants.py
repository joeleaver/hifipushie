"""MODEL=m variants.py out_dir ENV=val[,ENV=val] ...: retopo.wrap per variant (env settings), then the eval numbers."""
import os
import sys

import numpy as np

import wrap_eval as W
from hifipushie import retopo, store

out = sys.argv[1]
for v in sys.argv[2:]:
    for kv in v.split(","):
        if "=" in kv:
            k, val = kv.split("=")
            os.environ[k] = val
    r = retopo.wrap(store.load(os.environ["MODEL"]))
    path = f"{out}/v_{v.replace(',', '_').replace('=', '-')}.npz"
    np.savez(path, verts=r["verts"], loops=r["loops"], sizes=r["sizes"])
    print(v, [l for l in r["log"] if l.startswith(("untangle", "wrapped"))])
    W.evaluate(path, out, render=False)
    for kv in v.split(","):
        os.environ.pop(kv.split("=")[0], None)
