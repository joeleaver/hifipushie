"""run_retopo.py model out.npz: retopo.wrap on a model, saved as {verts, loops, sizes, origin}; prints the log."""
import sys
import time

import numpy as np

from hifipushie import retopo, store

t = time.time()
r = retopo.wrap(store.load(sys.argv[1]))
np.savez(sys.argv[2], verts=r["verts"], loops=r["loops"], sizes=r["sizes"], origin=r["origin"])
print("\n".join(r["log"]))
for k, rings in r["patches"].items():
    np.save(sys.argv[2].replace(".npz", f"_{k}.npy"), np.array(rings))
print(f"{time.time() - t:.1f}s")
