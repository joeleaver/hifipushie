"""crdir.py: candidate crease directions from the samples; cosines; their macro moves; sex alignment. -> out/crdir.npz"""
import json
import numpy as np
from hifipushie import gnm_sampler as gs
import lidgnm

G = "/mnt/data/hifipushie/gnmcrease/out/"
z = np.load(G + "s_gnm_1.npz", allow_pickle=True)
C = z["C"]
R = json.loads(str(z["geo"]))
M = json.loads(str(z["macro"]))
y = np.array([r["local"] for r in R])
hs = np.array([r["hsoft"] for r in R])
# population ridge (lam 100)
X = np.c_[C, np.ones(len(C))]
w = np.linalg.solve(X.T @ X + 100 * np.diag(np.r_[np.ones(170), 0]), X.T @ y)[:170]
# contrast: top 10 % of depth among creases at 3.5-6.5 mm vs all others at that height
band = (hs > 3.5) & (hs < 6.5)
thr = np.percentile(y[band], 90)
top = band & (y >= thr)
d_con = C[top].mean(0) - C[band & ~top].mean(0)
J = np.load(G + "jac_gd_T12.npz")
d_t = J["JR"][0]
sexd = gs.identity()(np.zeros(64), gs.id_label("male"))[0][lidgnm.HC] - gs.identity()(np.zeros(64), gs.id_label("female"))[0][lidgnm.HC]
u = lambda v: v / np.linalg.norm(v)  # noqa: E731
D = {"pop": u(w), "contrast": u(d_con), "tess_grad": u(d_t)}
print("n top", top.sum(), "thr", round(thr, 2))
for a in D:
    print(a, " ".join(f"cos({b}) {D[a] @ D[b]:+.2f}" for b in D), f"cos(sex m-f) {D[a] @ u(sexd):+.2f}")
# macros along each (linear fit of macro on c, per unit |dc|)
mk = list(M[0])
Mz = np.array([[m[k] for k in mk] for m in M])
Bm = np.linalg.lstsq(np.c_[C, np.ones(len(C))], Mz, rcond=None)[0][:170]
for a in D:
    mv = D[a] @ Bm
    o = np.argsort(-np.abs(mv))[:9]
    print(f"{a:10s} per |dc| 1: depth {D[a] @ w:+.3f} mm (pop) {D[a] @ d_t:+.3f} mm (Tess) | " + ", ".join(f"{mk[j]} {mv[j]:+.2f}" for j in o))
np.savez(G + "crdir.npz", **D, sex=u(sexd), Bm=Bm, mk=mk, w=w)
