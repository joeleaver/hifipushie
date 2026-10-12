"""gnmnative debug: the sock's points in the head's field."""
import sys

import numpy as np

from hifipushie import base as basemod
from hifipushie import store
from hifipushie import spec as specmod

sp = store.load(sys.argv[1])
e = specmod.expand_mirror(sp)
head = basemod.head_of({"joints": e["joints"]}, sp["base"])
sk = basemod.sock_points(head)
mp = basemod.gnm_mouth(head)
M, o, up, side = mp["frame"]
c = mp["sock"]["verts"].mean(0)
print("sock points", None if sk is None else len(sk["verts"]), "centroid behind M", ((M - c) @ o) * 1000)
print("normals toward the centroid (mean cos):", float(np.mean(((c - sk["verts"]) * sk["normals"]).sum(1) / np.linalg.norm(c - sk["verts"], axis=1))))
print("imls of the sock alone at its centroid mm:", float(basemod._imls(c[None], sk)[0]) * 1000)
surf = basemod.surface(e, sp["base"])
print("surface verts", len(surf["verts"]), "hmax", surf["hmax"], "h of sock max", sk["h"].max(), "median", np.median(sk["h"]))
pr = {"verts": surf["verts"], "normals": surf["normals"], "h": surf["h"], "hmax": surf["hmax"], "tree": surf["tree"], "wt": surf.get("wt"), "seam": surf.get("seam")}
for back in (0.005, 0.01, 0.02, 0.03, 0.04):
    x = M - o * back
    d, i = surf["tree"].query(x, k=4)
    print(f"at {back * 1000:.0f} mm behind M: body field {float(basemod.sd_base(x[None], pr)[0]) * 1000:+.2f} mm; sock alone {float(basemod._imls(x[None], sk)[0]) * 1000:+.2f}; "
          f"nearest body point {d[0] * 1000:.1f} mm (row {i[0]} of {len(surf['verts'])}, sock rows start {len(surf['verts']) - len(sk['verts'])})")
x = M - o * 0.03
d, i = surf["tree"].query(x, k=32)
n0 = len(surf["verts"]) - len(sk["verts"])
P, N = surf["verts"][i], surf["normals"][i]
s = ((x - P) * N).sum(1)
print("neighbours sock?", (i >= n0).sum(), "of 32; s mm", (s * 1000).round(1)[:8], "h", (surf["h"][i] * 1000).round(2)[:8])
print("same rows in sk: pos diff", np.abs(surf["verts"][i[i >= n0]] - sk["verts"][i[i >= n0] - n0]).max(), "normal dot", (surf["normals"][i[i >= n0]] * sk["normals"][i[i >= n0] - n0]).sum(1)[:6])
print("mode", basemod.mouth_mode(sp["base"], head), "seal_field", basemod.source(sp["base"]).get("seal_field") is not None)
tr = __import__("scipy.spatial", fromlist=["cKDTree"]).cKDTree(surf["verts"])
dd = tr.query(sk["verts"])[0]
print("sock points' distance to the nearest surface point: max mm", dd.max() * 1000, "share within 1e-6:", float((dd < 1e-6).mean()))
