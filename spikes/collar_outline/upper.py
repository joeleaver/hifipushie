"""upper.py <tag> [json]: the shirt's upper body as a CHAIN NETWORK hung from the open band (<tag>S.pkl).
Pieces back, yoke, front.L, front.R. Fixed: vertices sewn to the band (its neckline as solved), to the sleeves (armholes,
as fitted), and everything below button1 - `below` (buttoned, as fitted). Chains: every piece's boundary edges + its
fold rows (the placket press), sewn edges merged. Steps: A fill (Laplace over the pieces, seams as stiff edges);
B chains settle (lengths hard: interfaced exact, soft at most; little bending; body floor; under the collar's fall);
C refill the interiors between the chains; D interior settle (lengths hard), chains held."""
import sys, json, pickle
import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve
from scipy.spatial import cKDTree
D = "/mnt/data/hifipushie/folds_ab/D/"; t = sys.argv[1]; P = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
d = pickle.load(open(f"{D}{t}S.pkl", "rb")); X = np.asarray(d["A"], float).copy(); M = d["mesh"]; F = np.asarray(M["F"])
uv = M["uv"]; pc = M["piece"]; nm = M["names"]; PT = {k: int(np.atleast_1d(v)[0]) for k, v in M["points"].items()}
iS, iC = nm.index("stand"), nm.index("collar")
PIE = [nm.index(n) for n in ("back", "yoke", "front.L", "front.R")]
inP = np.isin(pc, PIE); Xfit = X.copy()
cl = [c for c in M["closures"] if c["name"] == "front"][0]; zB = Xfit[cl["v"][0][0], 2]
sew = np.asarray(M["sew"])
fixed = np.zeros(len(X), bool); fixed[~inP] = True                       # everything outside these pieces is held
for a, b in sew:                                                          # sewn to a held piece: take its position
    for p_, q_ in ((a, b), (b, a)):
        if inP[p_] and not inP[q_]: X[p_] = X[q_]; fixed[p_] = True
low = inP & (Xfit[:, 2] < zB - P.get("below", 0.04)); fixed[low] = True
for v_ in cl["v"][0]: fixed[v_] = True                                   # the first fastened button: the pivot
inner = [(a, b) for a, b in sew if inP[a] and inP[b]]                    # seams inside the network
# mesh edges of the pieces + seams
Fp = F[np.all(inP[F], axis=1)]
ed = np.unique(np.sort(np.r_[Fp[:, [0, 1]], Fp[:, [1, 2]], Fp[:, [2, 0]]], axis=1), axis=0)
Lf = np.linalg.norm(uv[ed[:, 0]] - uv[ed[:, 1]], axis=1)
u_, c_ = np.unique(ed, axis=0, return_counts=True)
Ef = np.sort(np.r_[Fp[:, [0, 1]], Fp[:, [1, 2]], Fp[:, [2, 0]]], axis=1); uu, cc = np.unique(Ef, axis=0, return_counts=True)
bnd = {tuple(e) for e in uu[cc == 1]}
isb = np.array([tuple(e) in bnd for e in ed])
foldv = set()
for f_ in M["folds"]:
    if nm.index(f_["piece"]) in PIE:
        for row in f_["rows"]: foldv.update(int(v) for v in row)
isfold = np.array([a in foldv and b in foldv for a, b in ed])
ischain = isb | isfold
# interfaced (the pattern): placket strips near each front's centre
des = json.load(open(__import__("hifipushie.cloth", fromlist=["x"]).__file__.replace("cloth.py", "cloth_designs.json")))["simon"]
intf = np.zeros(len(X), bool)
for e in des["interfaced"]:
    if isinstance(e, dict) and nm.index(e["piece"]) in PIE:
        pv = np.where(pc == nm.index(e["piece"]))[0]; cfx = uv[PT[f"{e['piece']}:cfNeck"], 0]
        intf[pv[np.abs(uv[pv, 0] - cfx) < e.get("within", 0.02)]] = True
exact = intf[ed[:, 0]] & intf[ed[:, 1]]
# the button is part of the network: lines across the placket from it to its piece's chains, at their flat lengths
xe = []
chv_ = np.unique(ed[ischain])
for bv_ in cl["v"][0]:
    near_ = chv_[(pc[chv_] == pc[bv_]) & (np.linalg.norm(uv[chv_] - uv[bv_], axis=1) < P.get("btn_r", 0.03))]
    xe += [sorted((int(bv_), int(v_))) for v_ in near_[::2] if v_ != bv_]
if xe:
    xe = np.array(xe); ed = np.r_[ed, xe]; Lf = np.r_[Lf, np.linalg.norm(uv[xe[:, 0]] - uv[xe[:, 1]], axis=1)]
    ischain = np.r_[ischain, np.ones(len(xe), bool)]; exact = np.r_[exact, np.ones(len(xe), bool)]; isfold = np.r_[isfold, np.zeros(len(xe), bool)]
    print(f"button ties: {len(xe)} lines across the placket")
print(f"network: {inP.sum()} vertices, {ischain.sum()} chain links ({isfold.sum()} fold), {exact.sum()} interfaced, {len(inner)} seam pairs; held {fixed[inP].sum()}")
# A: fill (Laplace over pieces + seams)
ids = np.where(inP)[0]; li = -np.ones(len(X), int); li[ids] = np.arange(len(ids)); n = len(ids)
w = 1.0 / np.maximum(Lf, 1e-5); w[len(ed) - len(xe):] = 0 if len(xe) else w[len(ed) - len(xe):]
I = np.r_[li[ed[:, 0]], li[ed[:, 1]]]; J = np.r_[li[ed[:, 1]], li[ed[:, 0]]]; W = np.r_[w, w]
if inner:
    sa = np.array(inner); I = np.r_[I, li[sa[:, 0]], li[sa[:, 1]]]; J = np.r_[J, li[sa[:, 1]], li[sa[:, 0]]]; W = np.r_[W, np.full(2 * len(sa), 1e4)]
Lm = sp.coo_matrix((W, (I, J)), shape=(n, n)).tocsr(); Lm = sp.diags(np.asarray(Lm.sum(1)).ravel()) - Lm
def fill(Xref, known):
    Dd = np.zeros((n, 3)); Dd[known] = (X - Xref)[ids][known]; fr = ~known
    Dd[fr] = np.column_stack([spsolve(Lm[fr][:, fr].tocsc(), -Lm[fr][:, known] @ Dd[known][:, k]) for k in range(3)])
    return Xref[ids] + Dd
X[ids] = fill(Xfit, fixed[ids])
# helpers: body floor, under the collar's fall, seam merge
bV = d["bodyV"]; bF = d["bodyF"]; bN = np.zeros_like(bV); fnb = np.cross(bV[bF[:, 1]] - bV[bF[:, 0]], bV[bF[:, 2]] - bV[bF[:, 0]])
for k in range(3): np.add.at(bN, bF[:, k], fnb)
bN /= np.linalg.norm(bN, axis=1)[:, None]; bkd = cKDTree(bV)
Fc = F[np.all(pc[F] == iC, axis=1)]; cvv = np.unique(Fc); VNc = np.zeros_like(X)
fnc = np.cross(X[Fc[:, 1]] - X[Fc[:, 0]], X[Fc[:, 2]] - X[Fc[:, 0]])
for k in range(3): np.add.at(VNc, Fc[:, k], fnc)
VNc /= np.maximum(np.linalg.norm(VNc, axis=1), 1e-12)[:, None]
cen = np.array([0, (d["at"]["cf_neck"][1] + d["at"]["cb_neck"][1]) / 2, 0])
VNc[cvv] *= np.sign(np.einsum("ij,ij->i", VNc[cvv][:, :2], (X[cvv] - cen)[:, :2]))[:, None]; kc = cKDTree(X[cvv])
def contacts(vs):
    _, j = bkd.query(X[vs]); sd = np.einsum("ij,ij->i", X[vs] - bV[j], bN[j]); lo_ = sd < 0.002
    X[vs[lo_]] += bN[j[lo_]] * (0.002 - sd[lo_])[:, None]
    dd, j = kc.query(X[vs]); q = X[cvv[j]]; nq = VNc[cvv[j]]; s_ = np.einsum("ij,ij->i", X[vs] - q, nq)
    ov = (s_ > -0.0012) & (dd < 0.01); X[vs[ov]] -= nq[ov] * (s_[ov] + 0.0012)[:, None]
def merge():
    for a, b in inner:
        if fixed[a] and not fixed[b]: X[b] = X[a]
        elif fixed[b] and not fixed[a]: X[a] = X[b]
        elif not fixed[a]: m_ = (X[a] + X[b]) / 2; X[a] = m_; X[b] = m_
def lengths(sel, movable, passes):
    e0, e1, L0, ex = ed[sel, 0], ed[sel, 1], Lf[sel], exact[sel]
    for _ in range(passes):
        dv = X[e1] - X[e0]; l = np.linalg.norm(dv, axis=1)
        e = np.where(ex, l - L0, np.maximum(l - L0, 0)) / np.maximum(l, 1e-9); corr = 0.5 * e[:, None] * dv
        acc = np.zeros_like(X); cnt = np.zeros(len(X)); ma, mb = movable[e0], movable[e1]
        np.add.at(acc, e0[ma], corr[ma] * np.where(mb[ma], 1, 2)[:, None]); np.add.at(cnt, e0[ma], 1)
        np.add.at(acc, e1[mb], -corr[mb] * np.where(ma[mb], 1, 2)[:, None]); np.add.at(cnt, e1[mb], 1)
        m = cnt > 0; X[m] += acc[m] / cnt[m][:, None] * 0.9
        merge()
# B: chains settle (chain vertices move; interior held for now), with a little bending along the chains
chainv = np.unique(ed[ischain]); mov = np.zeros(len(X), bool); mov[chainv] = True; mov &= ~fixed
nbr = {}
for a, b in ed[ischain]: nbr.setdefault(a, []).append(b); nbr.setdefault(b, []).append(a)
cm = np.array([v for v in chainv if mov[v]])
for it in range(P.get("iters_b", 200)):
    lengths(ischain, mov, 6)
    Xs = X.copy()
    for v in cm:
        nb = nbr[v]
        if len(nb) == 2: Xs[v] = (1 - P.get("smooth_b", 0.15)) * X[v] + P.get("smooth_b", 0.15) * (X[nb[0]] + X[nb[1]]) / 2
    X[cm] = Xs[cm]; contacts(cm)
# lengths get the last word: length-only passes on the chains until they stop moving
bsel = ischain | (mov[ed[:, 0]] & fixed[ed[:, 1]]) | (mov[ed[:, 1]] & fixed[ed[:, 0]])   # links from chains to held cloth count too
for it in range(P.get("final_b", 1500)):
    lengths(bsel, mov, 2)
    if it % 25 == 0: contacts(cm)
lc = np.linalg.norm(X[ed[ischain, 1]] - X[ed[ischain, 0]], axis=1) / Lf[ischain] - 1; mc = mov[ed[ischain, 0]] | mov[ed[ischain, 1]]
print(f"chains after the length pass: longest free link over cut {lc[mc].max()*100:.2f} %")
# C: refill interiors between the chains
known = fixed.copy(); known[chainv] = True
Xa = X.copy(); X[ids] = fill(Xa, known[ids])                             # zero displacement: interiors follow chains...
X[ids] = fill(np.where(known[:, None], X, Xa), known[ids])
# D: interior settle, chains held
movI = inP & ~known
iv = np.where(movI)[0]
for it in range(P.get("iters_d", 300)):
    lengths(np.ones(len(ed), bool), movI, P.get("passes", 20) // 10 + 1); contacts(iv)
dv = X[ed[:, 1]] - X[ed[:, 0]]; l = np.linalg.norm(dv, axis=1) / Lf - 1
touched = (np.linalg.norm(X - Xfit, axis=1) > 1e-6)[ed[:, 0]] | (np.linalg.norm(X - Xfit, axis=1) > 1e-6)[ed[:, 1]]
lfit = np.linalg.norm(Xfit[ed[:, 1]] - Xfit[ed[:, 0]], axis=1) / Lf - 1
for name_, u_p, v_p in (("shoulder L", "yoke:neck", "yoke:shoulder"), ("shoulder R", "yoke:neck.m", "yoke:shoulder.m")):
    a_, b_ = PT[u_p], PT[v_p]; print(f"  {name_} end to end: 3D {np.linalg.norm(X[a_]-X[b_])*1e3:.1f} mm, flat chord {np.linalg.norm(uv[a_]-uv[b_])*1e3:.1f} mm, fit {np.linalg.norm(Xfit[a_]-Xfit[b_])*1e3:.1f} mm")
print(f"moved region: longest link over cut {l[touched].max()*100:.1f} % (fit's own max there {lfit[touched].max()*100:.1f} %); chains {np.abs(l[ischain & touched]).max()*100:.1f} %")
d["A"] = X; pickle.dump(d, open(f"{D}{t}U.pkl", "wb")); print("saved", t + "U")
