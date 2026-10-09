"""turned.py <slider> [value]: where the template quads that turn over under a slider are (mm from the left eye's
inner / outer corners, the quad's area, its vertices' GNM ids, exterior or not)."""
import copy
import sys

import numpy as np

from hifipushie import base, gnmloops, humanfit, humans, onemesh

nm = sys.argv[1]
v = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
sp = humans.spec(age=40, sex=1.0, seed=None, skin=False, source="human")
st0 = humanfit.state(sp["base"])
b = copy.deepcopy(sp["base"])
b.setdefault("head", {})["sliders"] = {nm: v}
st1 = humanfit.state(b)
P0, P1 = np.asarray(st0["tpl"]["P"]), np.asarray(st1["tpl"]["P"])
Q = np.asarray(st0["tpl"]["L"]).reshape(-1, 4)
n0 = np.cross(P0[Q[:, 2]] - P0[Q[:, 0]], P0[Q[:, 3]] - P0[Q[:, 1]])
n1 = np.cross(P1[Q[:, 2]] - P1[Q[:, 0]], P1[Q[:, 3]] - P1[Q[:, 1]])
bad = np.flatnonzero((n0 * n1).sum(1) < 0)
L = np.asarray(st0["L"])
gid = np.asarray(onemesh.asset()["gnm_exact"])[np.asarray(st0["tpl"]["fid"])]
ext = np.asarray(base._gnm_data()["groups"]["skin_exterior"]) > 0.5
for q in bad:
    c = P0[Q[q]].mean(0)
    g = gid[Q[q]]
    print(f"quad {q}: from inner L {1000*(c-L[42]).round(4)} outer L {1000*(c-L[45]).round(4)} area "
          f"{1e6*np.linalg.norm(n0[q])/2:.3f} mm2, gnm {g.tolist()}, exterior {[bool(ext[x]) if x < gnmloops.N_RAW else 'new' for x in g]}, "
          f"moves mm {(1000*np.linalg.norm(P1[Q[q]]-P0[Q[q]], axis=1)).round(2).tolist()}")
