"""meshcmp.py <model> <model>: the built meshes (store.build) of two models: per part vertex / face counts and, for
the body, the largest distance between them near the mouth."""
import sys

import numpy as np
from scipy.spatial import cKDTree

from hifipushie import humanfit, store

out = []
for name in sys.argv[1:3]:
    b = store.build(name)
    out.append(b)
    print(name, {k: (len(v["V"]) if isinstance(v, dict) and "V" in v else type(v).__name__) for k, v in (b.items() if isinstance(b, dict) else [])})
print(type(out[0]))
