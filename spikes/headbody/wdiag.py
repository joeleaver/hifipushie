"""wdiag.py <model>: skin weights round the neck on the template (asset weights folded on the rig): per ring / row."""
import sys
import numpy as np
from hifipushie import base as B, onemesh, store, rig as rigmod, rig_template
from hifipushie.spec import expand_mirror
spec = store.load(sys.argv[1])
tpl = B.source(spec["base"])
a = onemesh.asset()
bones, idx, w = onemesh.weights(tpl)
print("asset bones near neck:", [b for b in bones if any(k in b for k in ("neck", "head", "spine", "clav", "should"))][:20])
ring = onemesh.seam_ring(tpl)
def dense(rows):
    D = np.zeros((len(rows), len(bones)))
    for c in range(idx.shape[1]):
        np.add.at(D, (np.arange(len(rows)), idx[rows, c]), w[rows, c])
    return D
D = dense(ring)
top = np.argsort(-D.sum(0))[:8]
print("seam ring (110, from the front centre round): bone: mean, min, max, largest step between neighbours")
for k in top:
    print(f"  {bones[k]:14s} {D[:,k].mean():.3f} {D[:,k].min():.3f} {D[:,k].max():.3f} step {np.abs(np.diff(np.r_[D[:,k], D[:1,k]])).max():.3f}")
nb, nmh = tpl["n_body"], tpl["n_mh"]
br = np.arange(nmh, nb)
Db = dense(br)
print("bridge rows (", len(br), "):", {bones[k]: (round(Db[:, k].mean(), 3), round(Db[:, k].min(), 3), round(Db[:, k].max(), 3)) for k in np.argsort(-Db.sum(0))[:8]})
C = np.full(int(tpl["fid"].max()) + 1, -1); C[tpl["fid"]] = np.arange(len(tpl["fid"]))
lc = C[a["loop_c"].astype(int)]
Dc = dense(lc)
print("loop C (42):", {bones[k]: (round(Dc[:, k].mean(), 3), round(Dc[:, k].min(), 3), round(Dc[:, k].max(), 3), "step", round(np.abs(np.diff(np.r_[Dc[:, k], Dc[:1, k]])).max(), 3)) for k in np.argsort(-Dc.sum(0))[:8]})
