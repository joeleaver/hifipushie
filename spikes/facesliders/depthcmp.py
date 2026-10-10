"""depthcmp.py <model>...: profile DEPTH measures of each model's identity on GNM's raw head (mm, GNM frame: z forward,
y up), for the view-consistency test (fits to front + 3/4 only vs profile only vs all):
  tip_proj      pronasale ahead of subnasale (lm 30 vs 33, z)
  nose_len      nasion to subnasale (lm 27 -> 33, y)
  dorsum_mid    the dorsum's midpoint ahead of the nasion-pronasale chord's ... (lm 28/29 z minus the chord's z there)
  ul_ahead      labrale superius ahead of the subnasale-pogonion line (lm 51 vs 33-8)
  ll_ahead      labrale inferius ahead of that line (lm 57)
  sulcus        the deepest point between lower lip and chin behind the line (mesh, midline)
  chin_ahead    pogonion ahead of subnasale (lm 8 vs 33, z)
  ul_height / ll_height   vermilion heights (lm 51 - 62 / 66 - 57, y)."""
import sys

import numpy as np

from hifipushie import headfit

headfit.N = 170
from hifipushie import base as basemod, humanfit, store  # noqa: E402

g = basemod._gnm_data()
TPL = np.asarray(g["template_vertex_positions"], float)
IB = np.asarray(g["vertex_identity_basis"], float)
names = [str(x) for x in g["identity_names"]]
hc = [i for i, x in enumerate(names) if x.startswith("head")]
EXT = np.asarray(g["groups"]["skin_exterior"], float) > 0.5


def lm(V):
    return np.array([sum(float(w) * V[int(v)] for v, w in zip(r[0::2], r[1::2])) for r in g["lm68"]])


def measures(c):
    V = TPL + np.tensordot(c, IB[hc], 1)
    L = lm(V) * 1000
    Vm = V * 1000
    sn, pg = L[33], L[8]

    def ahead(p):   # ahead of the line sn -> pg in the (y, z) midsagittal plane, + = forward
        t = (pg[1:] - sn[1:]) / np.linalg.norm(pg[1:] - sn[1:])
        nrm = np.array([-t[1], t[0]])
        if nrm[1] < 0:
            nrm = -nrm
        return float((p[1:] - sn[1:]) @ nrm)
    mid = EXT & (np.abs(Vm[:, 0]) < 1.0) & (Vm[:, 1] < L[57, 1]) & (Vm[:, 1] > L[8, 1])
    sul = min((ahead(p) for p in Vm[mid]), default=float("nan"))
    chord = L[27] + (L[30] - L[27]) * ((L[29, 1] - L[27, 1]) / (L[30, 1] - L[27, 1]))
    return {"tip_proj": L[30, 2] - L[33, 2], "nose_len": L[27, 1] - L[33, 1], "dorsum_mid": L[29, 2] - chord[2],
            "ul_ahead": ahead(L[51]), "ll_ahead": ahead(L[57]), "sulcus": sul, "chin_ahead": L[8, 2] - L[33, 2],
            "ul_height": L[51, 1] - L[62, 1], "ll_height": L[66, 1] - L[57, 1]}


rows = {}
for m in sys.argv[1:]:
    rows[m] = measures(humanfit.identity(store.load(m)["base"]))
keys = list(next(iter(rows.values())))
print(f"{'model':22s}" + "".join(f"{k:>11s}" for k in keys))
for m, r in rows.items():
    print(f"{m:22s}" + "".join(f"{r[k]:11.2f}" for k in keys))
