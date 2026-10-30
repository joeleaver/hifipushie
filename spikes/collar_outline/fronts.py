"""fronts.py <tag>: hang the soft shirt fronts from the open band (band + collar from <tag>S.pkl, held).
Front neck edges move with the band's neckline (sewn); below (button1 - 40 mm) the buttoned fit stays; between: a
displacement fill (Laplace) then a length-hard settle: soft cloth can't stretch (may slacken), the interfaced placket
strip keeps its lengths exactly, light gravity, the body as a floor, the fronts stay under the collar's fall."""
import sys, json, pickle
import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve
from scipy.spatial import cKDTree
D = "/mnt/data/hifipushie/folds_ab/D/"; t = sys.argv[1]; P = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
d = pickle.load(open(f"{D}{t}S.pkl", "rb")); X = np.asarray(d["A"], float).copy(); M = d["mesh"]; F = np.asarray(M["F"])
uv = M["uv"]; pc = M["piece"]; nm = M["names"]
iS, iC = nm.index("stand"), nm.index("collar"); FR = [nm.index("front.L"), nm.index("front.R")]
X0 = X.copy()
cl = [c for c in M["closures"] if c["name"] == "front"][0]; zB = X0[cl["v"][0][0], 2]
sew = {}
for a, b in M["sew"]:
    if pc[a] == iS and pc[b] in FR: sew[b] = a
    elif pc[b] == iS and pc[a] in FR: sew[a] = b
fv = np.where(np.isin(pc, FR))[0]
low = fv[X0[fv, 2] < zB - P.get("below", 0.04)]                     # buttoned: stays
neckf = np.array(list(sew)); target = {q: X[sew[q]] for q in neckf}
region = np.setdiff1d(fv, np.r_[low, neckf])
# 0) start guess: the lapel (above button 1, on the CF side of the line button1 -> side neck) turned back about that line
from scipy.spatial.transform import Rotation as Rot
b1 = cl["v"][0]; Pn = {k: int(np.atleast_1d(v)[0]) for k, v in M["points"].items()}
for fname, bv in (("front.L", b1[0]), ("front.R", b1[1])):
    pv = np.where(pc == nm.index(fname))[0]; A = X0[bv]; H = X0[Pn[f"{fname}:neck"]]; k = (H - A) / np.linalg.norm(H - A)
    E = X0[Pn[f"{fname}:cfNeck"]]; Et = target[min(neckf, key=lambda q: np.linalg.norm(X0[q] - E))]
    def ang_to(th):
        return Rot.from_rotvec(k * th).apply(E - A) + A
    ths = np.linspace(-np.pi, np.pi, 721); th = ths[np.argmin([np.linalg.norm(ang_to(t_) - Et) for t_ in ths])]
    side = np.cross(k, E - A); wv = ((X0[pv] - A) @ side) / (np.linalg.norm(side) * 0.03); wv = np.clip(wv + 0.3, 0, 1)
    wv *= (X0[pv, 2] > A[2] - 0.005); wv = wv * wv * (3 - 2 * wv)
    X0g = np.array([Rot.from_rotvec(k * th * w_).apply(x_ - A) + A for x_, w_ in zip(X0[pv], wv)])
    X[pv] = X0g
    print(f"{fname}: lapel start turned {np.degrees(th):.0f} deg")
X0 = X.copy()
# 1) displacement fill on the fronts' mesh (flat edge weights)
Ff = F[np.all(np.isin(pc[F], FR), axis=1)]; ids = np.unique(Ff); li = {v: i for i, v in enumerate(ids)}
ed = np.unique(np.sort(np.r_[Ff[:, [0, 1]], Ff[:, [1, 2]], Ff[:, [2, 0]]], axis=1), axis=0)
w = 1.0 / np.maximum(np.linalg.norm(uv[ed[:, 0]] - uv[ed[:, 1]], axis=1), 1e-5)
a_, b_ = np.array([li[v] for v in ed[:, 0]]), np.array([li[v] for v in ed[:, 1]]); n = len(ids)
L = sp.coo_matrix((np.r_[w, w], (np.r_[a_, b_], np.r_[b_, a_])), shape=(n, n)).tocsr(); L = sp.diags(np.asarray(L.sum(1)).ravel()) - L
Dsp = np.zeros((n, 3)); known = np.zeros(n, bool)
for q in neckf: Dsp[li[q]] = target[q] - X0[q]; known[li[q]] = True
for q in low: known[li[q]] = True
fr_ = ~known; Dsp[fr_] = np.column_stack([spsolve(L[fr_][:, fr_].tocsc(), -L[fr_][:, known] @ Dsp[known][:, k]) for k in range(3)])
X[ids] = X0[ids] + Dsp
# 2) settle: lengths (flat), placket strip exact, soft at-most; gravity; body floor; under the collar's fall
Lf = np.linalg.norm(uv[ed[:, 0]] - uv[ed[:, 1]], axis=1)
intf = np.zeros(len(X), bool)
des = json.load(open(__import__("hifipushie.cloth", fromlist=["x"]).__file__.replace("cloth.py", "cloth_designs.json")))["simon"]
for e in des["interfaced"]:
    if isinstance(e, dict) and nm.index(e["piece"]) in FR:
        pv = np.where(pc == nm.index(e["piece"]))[0]; c = uv[M["points"][f"{e['piece']}:cfNeck"] if False else pv].copy()
        cfx = np.median(uv[pv[np.argsort(np.abs(uv[pv, 0]))[:50]], 0]) if False else None
exact = np.zeros(len(ed), bool)
for pname, within in (("front.L", 0.02), ("front.R", 0.016)):           # the pattern's interfaced placket strips
    pv = np.where(pc == nm.index(pname))[0]; ux = uv[pv, 0]; cf_x = ux.min() if abs(ux.min()) < abs(ux.max()) else ux.max()
    edge_x = ux[np.argmin(np.abs(ux))] if False else None
    near = pv[np.abs(uv[pv, 0] - uv[pv, 0][np.argmin(np.abs(uv[pv, 0] - np.median(uv[pv, 0][np.abs(uv[pv, 0]) < 0.03])))]) < within] if (np.abs(uv[pv, 0]) < 0.03).any() else np.array([], int)
    intf[near] = True
exact = intf[ed[:, 0]] & intf[ed[:, 1]]
movable = np.zeros(len(X), bool); movable[region] = True
bV = d["bodyV"]; bF = d["bodyF"]; bN = np.zeros_like(bV); fnb = np.cross(bV[bF[:, 1]] - bV[bF[:, 0]], bV[bF[:, 2]] - bV[bF[:, 0]])
for k in range(3): np.add.at(bN, bF[:, k], fnb)
bN /= np.linalg.norm(bN, axis=1)[:, None]; bkd = cKDTree(bV)
Fc = F[np.all(pc[F] == iC, axis=1)]; cvv = np.unique(Fc); VNc = np.zeros_like(X)
fnc = np.cross(X[Fc[:, 1]] - X[Fc[:, 0]], X[Fc[:, 2]] - X[Fc[:, 0]])
for k in range(3): np.add.at(VNc, Fc[:, k], fnc)
VNc /= np.maximum(np.linalg.norm(VNc, axis=1), 1e-12)[:, None]
cen = np.array([0, (d["at"]["cf_neck"][1] + d["at"]["cb_neck"][1]) / 2, 0])
VNc[cvv] *= np.sign(np.einsum("ij,ij->i", VNc[cvv][:, :2], (X[cvv] - cen)[:, :2]))[:, None]
kc = cKDTree(X[cvv]); rv = region
for it in range(P.get("iters", 300)):
    X[rv, 2] -= P.get("g", 0.00005)                                    # light gravity
    for _ in range(P.get("passes", 4)):                                # lengths (Jacobi, averaged)
        p, q = X[ed[:, 0]], X[ed[:, 1]]; dv = q - p; l = np.linalg.norm(dv, axis=1)
        e = np.where(exact, l - Lf, np.maximum(l - Lf, 0)) / np.maximum(l, 1e-9)
        corr = 0.5 * e[:, None] * dv; acc = np.zeros_like(X); cnt = np.zeros(len(X))
        ma, mb = movable[ed[:, 0]], movable[ed[:, 1]]
        np.add.at(acc, ed[ma, 0], corr[ma] * np.where(mb[ma], 1, 2)[:, None]); np.add.at(cnt, ed[ma, 0], 1)
        np.add.at(acc, ed[mb, 1], -corr[mb] * np.where(ma[mb], 1, 2)[:, None]); np.add.at(cnt, ed[mb, 1], 1)
        m = cnt > 0; X[m] += acc[m] / cnt[m][:, None] * 0.9
    _, j = bkd.query(X[rv]); sd = np.einsum("ij,ij->i", X[rv] - bV[j], bN[j]); lo_ = sd < 0.002
    X[rv[lo_]] += bN[j[lo_]] * (0.002 - sd[lo_])[:, None]
    dd, j = kc.query(X[rv]); q = X[cvv[j]]; nq = VNc[cvv[j]]; s_ = np.einsum("ij,ij->i", X[rv] - q, nq)
    over = (s_ > -0.0012) & (dd < 0.01); X[rv[over]] -= nq[over] * (s_[over] + 0.0012)[:, None]
l = np.linalg.norm(X[ed[:, 1]] - X[ed[:, 0]], axis=1) / Lf - 1; m = movable[ed[:, 0]] | movable[ed[:, 1]]
print(f"fronts: {len(region)} vertices hung; longest link over cut {l[m].max()*100:.1f} % (soft may slacken: shortest {l[m].min()*100:.0f} %); placket strip links {exact.sum()}")
d["A"] = X; pickle.dump(d, open(f"{D}{t}F.pkl", "wb")); print("saved", t + "F")
