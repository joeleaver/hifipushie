"""sealedge.py <model>: the template edges the seal stretches / squeezes most (seal 1 vs 0): where (mm from the mouth's
centre), which lip ring their ends are on, the lengths."""
import copy
import sys

import numpy as np

from hifipushie import faceslide, humanfit, onemesh, store

b0 = store.load(sys.argv[1])["base"]
P = {}
for s in (0.0, 1.0):
    b = copy.deepcopy(b0)
    b["head"]["lip_seal"] = s
    b["head"].pop("mouth_gap", None)
    b["head"].pop("interior", None)
    st = humanfit.state(b)
    P[s] = np.asarray(st["tpl"]["P"], float)
    Q = np.asarray(st["tpl"]["L"]).reshape(-1, 4)
    L = np.asarray(st["L"])
gid = np.asarray(onemesh.asset()["gnm_exact"], int)[np.asarray(st["tpl"]["fid"])]
R = faceslide._lip_rings()
ring_of = {int(v): k for k, r in enumerate(R["rings"]) for v in r}
E = np.unique(np.sort(np.r_[Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]], 1), axis=0)
l0 = np.linalg.norm(P[0.0][E[:, 0]] - P[0.0][E[:, 1]], axis=1)
l1 = np.linalg.norm(P[1.0][E[:, 0]] - P[1.0][E[:, 1]], axis=1)
r = l1 / np.maximum(l0, 1e-9)
c = 0.5 * (L[62] + L[66])
for lab, idx in (("stretched", np.argsort(-r)[:6]), ("squeezed", np.argsort(r)[:6])):
    for i in idx:
        a, b_ = E[i]
        m = 0.5 * (P[0.0][a] + P[0.0][b_])
        print(lab, f"x{r[i]:.2f} len {1000*l0[i]:.2f} -> {1000*l1[i]:.2f} mm at {(1000*(m - c)).round(1).tolist()} rings",
              ring_of.get(int(gid[a]), "-"), ring_of.get(int(gid[b_]), "-"))
