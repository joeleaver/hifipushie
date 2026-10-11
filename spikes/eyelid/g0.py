"""g0.py: what GNM's arrays hold (groups, expression families, joints)."""
import collections

import numpy as np

from hifipushie import gnm_controls as gc

g = gc.gnm()
print(g["T"].shape, g["IB"].shape, g["EB"].shape, len(g["quads"]))
print([(n, int(m.sum())) for n, m in g["groups"].items()])
ex = g["ex_names"]
print(collections.Counter(n.rsplit("_", 1)[0] for n in ex))
print(ex[:5], [n for n in ex if "eye" in n][:6])
print(g["id_names"][:5], g["id_names"][118:124], g["id_names"][-3:])
print("J", np.round(g["J"] * 1000, 1), g["parents"])
