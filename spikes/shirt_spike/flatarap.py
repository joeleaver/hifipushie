"""flatarap.py <from> <out> '{"pts": [apart, below_hps, stand_off], "steps", "iters", "band": [apart_bottom]}':
the OPEN state by STAGED moves, as-rigid-as-possible against the FLAT PATTERN: every triangle keeps its own pattern
shape (per-face rotations, rest = its uv; Liu et al. 2008's local / global), sewn pairs welded, bending free.
Start = the closed fit. Held: back, yoke, sleeves, cuffs, the fronts below the first fastened button. Moved step by
step: the collar points from where the closed fit has them to the target (apart / below HPS; y kept + stand_off).
Free: the band, the collar, the fronts above the button. Inside-the-body cloth pushed out after each step."""
import sys, json, pickle
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import splu
from scipy.spatial import cKDTree
D = "/mnt/data/hifipushie/shirt_spike/"
src, tag = sys.argv[1], sys.argv[2]; A = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
d = pickle.load(open(f"{D}{src}.pkl", "rb")); X0 = np.asarray(d["A"], float); M = d["mesh"]
F = np.asarray(M["F"]); pid = np.asarray(M["piece"]); nm = list(M["names"]); uv = np.asarray(M["uv"], float); P = M["points"]
par = np.arange(len(X0))
def f_(i):
    while par[i] != i: par[i] = par[par[i]]; i = par[i]
    return i
for a, b in np.asarray(M["sew"]).reshape(-1, 2):
    ra, rb = f_(a), f_(b)
    if ra != rb: par[rb] = ra
root = np.array([f_(i) for i in range(len(X0))]); _, inv = np.unique(root, return_inverse=True); n = inv.max() + 1
W0 = np.zeros((n, 3)); np.add.at(W0, inv, X0); W0 /= np.bincount(inv)[:, None]
U = uv[F]                                   # rest per face (its own piece's pattern), (m, 3, 2)
WF = inv[F]
good = (WF[:, 0] != WF[:, 1]) & (WF[:, 1] != WF[:, 2]) & (WF[:, 0] != WF[:, 2])
e1, e2 = U[:, 1] - U[:, 0], U[:, 2] - U[:, 0]; good &= np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) > 1e-10
U, WF = U[good], WF[good]; m = len(WF)
# cot weights of each half-edge (i, j) = 0.5 cot(angle opposite), from the rest triangle
HE = [(0, 1, 2), (1, 2, 0), (2, 0, 1)]
I, J, Wt = [], [], []
for a, b, c in HE:
    p, q = U[:, a] - U[:, c], U[:, b] - U[:, c]
    cot = (p * q).sum(1) / np.maximum(np.abs(p[:, 0] * q[:, 1] - p[:, 1] * q[:, 0]), 1e-12)
    Wt.append(np.clip(0.5 * cot, 1e-4, 5.0)); I.append(WF[:, a]); J.append(WF[:, b])
Wt = np.stack(Wt, 1); I = np.stack(I, 1); J = np.stack(J, 1)
Lw = coo_matrix((np.r_[Wt.ravel(), Wt.ravel()], (np.r_[I.ravel(), J.ravel()], np.r_[J.ravel(), I.ravel()])), shape=(n, n)).tocsr()
deg = np.asarray(Lw.sum(1)).ravel()
from scipy.sparse import diags
# BENDING (interfacing / cloth stiffness): across every interior edge of a piece, a spring holding the two opposite
# corners at their flat-pattern distance (the classic hinge spring), weight KB (x the cot weights' scale), rotated
# like the first face's frame in the local step. Edges on a declared fold row (and within FOLD_BAND of one) are left
# out, so the pattern's folds (the collar's roll, the fronts' bands) stay hinges.
KB = A.get("kb", 0.0)
KBP = A.get("kb_pieces")  # per piece weight {name: w} (default: KB everywhere)
fold_v = np.zeros(len(X0), bool)
for fd in M.get("folds") or []:
    for row in fd["rows"]: fold_v[np.asarray(row, int)] = True
if A.get("fold_band", 0.004) > 0 and fold_v.any():
    fv = np.where(fold_v)[0]; tr = cKDTree(uv[fv]); dd, jj = tr.query(uv)
    fold_v |= (dd < A.get("fold_band", 0.004)) & (pid == pid[fv[jj]])
Fg = F[good]
from collections import defaultdict
emap = defaultdict(list)
for fi_, (a, b, c) in enumerate(Fg):
    for p_, q_, r_ in ((a, b, c), (b, c, a), (c, a, b)):
        emap[(min(p_, q_), max(p_, q_))].append((fi_, r_))
HA, HB, HF, HW = [], [], [], []
for (p_, q_), lst in emap.items():
    if len(lst) != 2: continue
    (f1, r1), (f2, r2) = lst
    if pid[r1] != pid[r2] or (fold_v[p_] and fold_v[q_]): continue
    w = KB if KBP is None else KBP.get(nm[pid[r1]], 0.0) * KB
    if w <= 0: continue
    HA.append(r1); HB.append(r2); HF.append(f1); HW.append(w)
HA, HB, HF, HW = np.array(HA, int), np.array(HB, int), np.array(HF, int), np.array(HW)
HUa, HUb = uv[HA], uv[HB]; HAw, HBw = inv[HA], inv[HB]
print(f"bending hinges {len(HA)} (kb {KB})")
if len(HA):
    Lb = coo_matrix((np.r_[HW, HW], (np.r_[HAw, HBw], np.r_[HBw, HAw])), shape=(n, n)).tocsr()
    Lw = Lw + Lb; deg = np.asarray(Lw.sum(1)).ravel()
L = (diags(deg) - Lw).tocsc()
def frames(Y):
    S = np.zeros((m, 3, 2))
    for k, (a, b, c) in enumerate(HE):
        S += Wt[:, k, None, None] * (Y[WF[:, a]] - Y[WF[:, b]])[:, :, None] * (U[:, a] - U[:, b])[:, None, :]
    Uu, _, Vt = np.linalg.svd(S, full_matrices=False)
    return Uu @ Vt
if len(HA) and A.get("bend_rest", "made") == "made":
    R0 = frames(W0); d0 = W0[HAw] - W0[HBw]
    Hr2 = np.einsum("mij,mi->mj", R0[HF], d0)                       # in-plane part (pattern frame)
    Hn = np.cross(R0[HF][:, :, 0], R0[HF][:, :, 1]); Hh = (Hn * d0).sum(1)  # normal part
else:
    Hr2, Hh = HUa - HUb, np.zeros(len(HA))
if len(HA):
    _R = frames(W0); _t = np.einsum("mij,mj->mi", _R[HF], Hr2) + Hh[:, None] * np.cross(_R[HF][:, :, 0], _R[HF][:, :, 1])
    _res = np.linalg.norm((W0[HAw] - W0[HBw]) - _t, axis=1)
    print(f"hinge rest residual at the start: p50 {np.median(_res)*1000:.3f} max {_res.max()*1000:.3f} mm; |d0| p50 {np.median(np.linalg.norm(W0[HAw]-W0[HBw],axis=1))*1000:.2f} mm; weights cot p50 {np.median(Wt):.2f}")
def solve(Y, fixed, iters):
    fi, ci = np.where(~fixed)[0], np.where(fixed)[0]
    lu = splu(L[fi][:, fi].tocsc()); Lfc = L[fi][:, ci]
    for _ in range(iters):
        # local: per face the closest 3x2 orthonormal map from its rest edges to its current edges
        S = np.zeros((m, 3, 2))
        for k, (a, b, c) in enumerate(HE):
            S += Wt[:, k, None, None] * (Y[WF[:, a]] - Y[WF[:, b]])[:, :, None] * (U[:, a] - U[:, b])[:, None, :]
        Uu, _, Vt = np.linalg.svd(S, full_matrices=False)
        R = Uu @ Vt                              # (m, 3, 2)
        rhs = np.zeros((n, 3))
        for k, (a, b, c) in enumerate(HE):
            v = Wt[:, k, None] * np.einsum("mij,mj->mi", R, U[:, a] - U[:, b])
            np.add.at(rhs, WF[:, a], v); np.add.at(rhs, WF[:, b], -v)
        if len(HA):
            Nn = np.cross(R[HF][:, :, 0], R[HF][:, :, 1])
            v = HW[:, None] * (np.einsum("mij,mj->mi", R[HF], Hr2) + A.get("hnorm", 1.0) * Hh[:, None] * Nn)
            np.add.at(rhs, HAw, v); np.add.at(rhs, HBw, -v)
        r = rhs[fi] - Lfc @ Y[ci]
        Y = Y.copy(); Y[fi] = np.column_stack([lu.solve(r[:, k]) for k in range(3)])
    return Y
BV, BF = d["bodyV"], d["bodyF"]
nn = np.cross(BV[BF[:, 1]] - BV[BF[:, 0]], BV[BF[:, 2]] - BV[BF[:, 0]]); vn = np.zeros_like(BV)
for k in range(3): np.add.at(vn, BF[:, k], nn)
vn /= np.linalg.norm(vn, axis=1)[:, None] + 1e-12; bt = cKDTree(BV)
def push(Y, keep, gap=0.002):
    _, j = bt.query(Y); s = ((Y - BV[j]) * vn[j]).sum(1); bad = (s < gap) & ~keep
    Y = Y.copy(); Y[bad] += (gap - s[bad])[:, None] * vn[j[bad]]; return Y, bad
fz = [X0[np.asarray(v)].mean(0)[2] for c in M.get("closures") or [] if c.get("name") == "front" for v in (c.get("v") or [])]
zb = max(fz)
held_v = np.isin(pid, [nm.index(k) for k in ("back", "yoke", "sleeve.L", "sleeve.R", "cuff.L", "cuff.R")]) | \
         (np.isin(pid, [nm.index("front.L"), nm.index("front.R")]) & (X0[:, 2] < zb - 0.005))
hW = np.zeros(n, bool); hW[inv[held_v]] = True
hps = np.asarray(d["at"]["hps.L"]).reshape(-1)[-3:]
pts = {s: inv[P[f"collar:{s}TopEdge"]] for s in ("left", "right")}
start = {s: W0[v].copy() for s, v in pts.items()}
tgt = {}
if A.get("pts"):
    apart, below, off = A["pts"]
    for s, v in pts.items():
        sg = np.sign(W0[inv[P[f"collar:{s}TopHinge"]], 0]); tgt[s] = np.array([sg * apart / 2, start[s][1] - off, hps[2] - below])
# the band's bottom corners (sewn to the fronts' CF neck points): each moved `band` m further from CF (x), `band_back` m back
bnd = {}
def rodr(p, axis, th):
    axis = axis / np.linalg.norm(axis); K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return p @ (np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K).T
if A.get("swing"):
    # each band end swung like a door about its hinge ruling (Simon's own hinge marks on the band, at the side of the
    # neck): the end edge's corners are the handles; sense: the end moves away from CF
    for s in ("left", "right"):
        hb, ht = W0[inv[P[f"stand:{s}BottomHinge"]]], W0[inv[P[f"stand:{s}TopHinge"]]]
        ends = [inv[P[k]] for k in (f"stand:{s}BottomCf", f"stand:{s}BottomEdge", f"stand:{s}TopCf")]
        sg = np.sign(hb[0])  # (the side from the hinge, well off CF: a band END crosses CF where the ends overlap)
        q = max((1, -1), key=lambda q_: sg * (hb + rodr((W0[ends[0]] - hb)[None], ht - hb, q_ * 0.2))[0][0])
        for v in ends:
            bnd[v] = [W0[v].copy(), (hb, ht - hb, q * np.radians(A["swing"]))]
STEPS = A.get("steps", 6)
Y = W0.copy()
print(f"faces {m}, verts {n}; first button z {zb*1000:.0f}; points start {[np.round(start[s]*1000).astype(int).tolist() for s in start]} target {[np.round(tgt[s]*1000).astype(int).tolist() for s in tgt]}")
# step 0: relax as-is against the flat pattern (what the closed fit costs in this energy)
Y = solve(Y, hW.copy(), A.get("iters", 20))
for k in range(1, STEPS + 1):
    f = k / STEPS; T = Y.copy(); fixed = hW.copy()
    for s in tgt:
        T[pts[s]] = start[s] + f * (tgt[s] - start[s]); fixed[pts[s]] = True
    for v, (a0, (hb, ax, th)) in bnd.items():
        T[v] = hb + rodr((a0 - hb)[None], ax, f * th)[0]; fixed[v] = True
    Y = solve(T, fixed, A.get("iters", 20))
    for _ in range(3):
        Yp, bad = push(Y, fixed)
        if not bad.any(): break
        Y = solve(Yp, fixed | bad, 6)
    print(f"step {k}: inside (free) {int(push(Y, fixed)[1].sum())}")
Y = solve(Y, hW | np.isin(np.arange(n), list(pts.values()) + list(bnd)), 10)
for v, (a0, (hb, ax, th)) in bnd.items():
    print("band handle", np.round(a0*1000).astype(int), "->", np.round((hb + rodr((a0 - hb)[None], ax, th)[0])*1000).astype(int), "got", np.round(Y[v]*1000).astype(int))
X = Y[inv]
E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
lu_ = np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1); l3 = np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1)
ok = (lu_ > 1e-5) & (pid[E[:, 0]] == pid[E[:, 1]]); st = np.abs(l3[ok] / lu_[ok] - 1)
print(f"edge strain vs the pattern: p50 {np.median(st)*100:.1f} %, p99 {np.percentile(st,99)*100:.1f} %")
out = dict(d); out["A"] = X; out["A_info"] = dict(d["A_info"], flatarap=A, worn_open_mm=None)
pickle.dump(out, open(f"{D}{tag}.pkl", "wb")); print("saved", tag)
