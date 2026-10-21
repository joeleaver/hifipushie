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
HA, HB, HF, HW, HC = [], [], [], [], []
for (p_, q_), lst in emap.items():
    if len(lst) != 2: continue
    (f1, r1), (f2, r2) = lst
    if pid[r1] != pid[r2] or (fold_v[p_] and fold_v[q_]): continue
    w = KB if KBP is None else KBP.get(nm[pid[r1]], 0.0) * KB
    if w <= 0: continue
    HA.append(r1); HB.append(r2); HF.append(f1); HW.append(w); HC.append((p_, q_, r1, r2))
HA, HB, HF, HW = np.array(HA, int), np.array(HB, int), np.array(HF, int), np.array(HW)
HCw = inv[np.array(HC, int).reshape(-1, 4)] if HC else np.zeros((0, 4), int)
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
if len(HA):
    if A.get("bend_rest", "made") == "flat":  # interfacing pressed FLAT: each cell's rest is its pattern (z = 0)
        _HCo = np.array(HC, int).reshape(-1, 4)
        _P0 = np.concatenate([uv[_HCo], np.zeros(_HCo.shape + (1,))], -1)
        _d0 = _P0[:, 2] - _P0[:, 3]
    else:
        _P0 = W0[HCw]; _d0 = W0[HAw] - W0[HBw]
    _P0c = _P0 - _P0.mean(1, keepdims=True)
def hinge_targets(Y):
    """each hinge cell's own PROPER rotation (Kabsch over its 4 corners, det +1: it can't mirror) applied to the cell's
    rest vector between the two opposite corners (rest = the closed fit's pressed shape)."""
    Q = Y[HCw]; Qc = Q - Q.mean(1, keepdims=True)
    H = np.einsum("nki,nkj->nij", _P0c, Qc)
    Uh, _, Vh = np.linalg.svd(H)
    dt = np.sign(np.linalg.det(np.einsum("nji,nkj->nik", Vh, Uh)))
    Dg = np.tile(np.eye(3), (len(H), 1, 1)); Dg[:, 2, 2] = dt
    Rt = np.einsum("nji,njk,nlk->nil", Vh, Dg, Uh)          # V D U^T
    return np.einsum("nij,nj->ni", Rt, _d0)
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
            v = HW[:, None] * hinge_targets(Y)
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
        # "lay" (deg): after the swing, the end ROLLS about the band's own length direction at the hinge (the
        # horizontal tangent round the neck), its top edge moving AWAY from the neck: the band end lies back with the
        # front rolling back, its outer face turning up / forward (Joe's photo: the band's inside shows on the far side)
        rad = np.r_[hb[:2], 0.0]; rad /= np.linalg.norm(rad)
        tang = np.cross(np.r_[0.0, 0.0, 1.0], rad)
        e0 = hb + rodr((W0[ends[2]] - hb)[None], ht - hb, q * np.radians(A["swing"]))[0]
        qd = max((1, -1), key=lambda q_: np.linalg.norm((hb + rodr((e0 - hb)[None], tang, q_ * 0.2))[0][:2]))
        rad = tang
        for v in ends:
            bnd[v] = [W0[v].copy(), (hb, ht - hb, q * np.radians(A["swing"])), (rad, qd * np.radians(A.get("lay", 0.0)))]
# ROLL: each front's corner above a roll line (from the neckline at arc `from` m from cfNeck, down to the first
# fastened button on the front's edge) turned rigidly about that line by `deg`, staged; the band rides on it (sewn).
rolls = {}
if A.get("roll"):
    RL = A["roll"]
    for fr in ("front.R", "front.L"):
        k = nm.index(fr); v = np.where(pid == k)[0]
        cv = [int(x) for c in M.get("closures") or [] if c.get("name") == "front" for pr in (c.get("v") or []) for x in pr if pid[int(x)] == k]
        bv = min(cv, key=lambda i: abs(X0[i, 2] - zb))           # this front's first fastened button vertex
        # the neckline: front vertices sewn to the stand, ordered by distance from cfNeck along the pattern
        sw_ = np.asarray(M["sew"]).reshape(-1, 2); stid = nm.index("stand")
        nk = np.unique([a for a, b in sw_ if pid[a] == k and pid[b] == stid] + [b for a, b in sw_ if pid[b] == k and pid[a] == stid])
        cfn = P[f"{fr}:cfNeck"]; o = nk[np.argsort(np.linalg.norm(uv[nk] - uv[cfn], axis=1))]
        d_ = np.r_[0, np.cumsum(np.linalg.norm(np.diff(uv[o], axis=0), axis=1))]
        nv = o[np.argmin(np.abs(d_ - RL.get("from", 0.03)))]
        ua, ub = uv[nv], uv[bv]
        cr = lambda q: (ub[0] - ua[0]) * (q[:, 1] - ua[1]) - (ub[1] - ua[1]) * (q[:, 0] - ua[0])
        sc = np.sign(cr(uv[[cfn]]))[0]
        fl = v[(np.sign(cr(uv[v])) == sc) & (X0[v, 2] >= zb - 0.002)]
        a3, b3 = W0[inv[nv]], W0[inv[bv]]
        c0 = W0[inv[cfn]]
        def sdist(p):
            _, jj = bt.query(p); return float(((p - BV[jj]) * vn[jj]).sum())
        sen = max((1, -1), key=lambda q_: sdist(a3 + rodr((c0 - a3)[None], b3 - a3, q_ * 0.3)[0]))
        rolls[fr] = (a3, b3, np.unique(inv[fl]), sen)
        print(f"{fr}: roll line from the neckline {RL.get('from', 0.03)*1000:.0f} mm off cfNeck to the button; flap {len(fl)} verts; sense {sen}")
STEPS = A.get("steps", 6)
Y = W0.copy()
print(f"faces {m}, verts {n}; first button z {zb*1000:.0f}; points start {[np.round(start[s]*1000).astype(int).tolist() for s in start]} target {[np.round(tgt[s]*1000).astype(int).tolist() for s in tgt]}")
_E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]; _l0 = np.linalg.norm(uv[_E[:, 0]] - uv[_E[:, 1]], axis=1)
_ok = (_l0 > 1e-5) & (pid[_E[:, 0]] == pid[_E[:, 1]])
def stp(Y, lab):
    if not A.get("trace"): return
    X_ = Y[inv]; st_ = np.abs(np.linalg.norm(X_[_E[:, 0]] - X_[_E[:, 1]], axis=1)[_ok] / _l0[_ok] - 1)
    sp_ = pid[_E[:, 0]][_ok] == nm.index("stand")
    print(f"  [{lab}] strain p99 all {np.percentile(st_,99)*100:.1f} %, stand {np.percentile(st_[sp_],99)*100:.1f} %")
stp(W0, "start")
# step 0: relax as-is against the flat pattern (what the closed fit costs in this energy)
for it_ in (1, 2, 5, 10, 20) if A.get("trace") else ():
    stp(solve(W0, hW.copy(), it_), f"relax {it_} it")
Y = solve(Y, hW.copy(), A.get("iters", 20))
for k in range(1, STEPS + 1):
    f = k / STEPS; T = Y.copy(); fixed = hW.copy()
    for s in tgt:
        T[pts[s]] = start[s] + f * (tgt[s] - start[s]); fixed[pts[s]] = True
    for fr, (a3, b3, flw, sen) in rolls.items():
        T[flw] = a3 + rodr(W0[flw] - a3, b3 - a3, sen * np.radians(A["roll"]["deg"]) * f); fixed[flw] = True
    for v, (a0, (hb, ax, th), (rad, dth)) in bnd.items():
        p1 = hb + rodr((a0 - hb)[None], ax, f * th)[0]
        T[v] = hb + rodr((p1 - hb)[None], rad, f * dth)[0]; fixed[v] = True
    Y = solve(T, fixed, A.get("iters", 20))
    for _ in range(0 if A.get("nopush") else 3):
        Yp, bad = push(Y, fixed)
        if not bad.any(): break
        Y = solve(Yp, fixed | bad, 6)
    print(f"step {k}: inside (free) {int(push(Y, fixed)[1].sum())}")
# PULL (Joe: "pull the point out and to the side, and let it go as far as it could without stretching"): after the
# staged moves, each collar point is dragged in small steps along (side x out-from-sideways + out x body normal), the
# rest solved each step; it stops at the last step where the cloth's stretch stayed within `tol` of the start's.
_Eo = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
_l0o = np.linalg.norm(uv[_Eo[:, 0]] - uv[_Eo[:, 1]], axis=1)
_oko = (_l0o > 1e-5) & (pid[_Eo[:, 0]] == pid[_Eo[:, 1]]) & np.isin(pid[_Eo[:, 0]], [nm.index(p) for p in ("collar", "stand", "front.L", "front.R")])
def stretch(Yw):
    Xw = Yw[inv]; return np.percentile(np.abs(np.linalg.norm(Xw[_Eo[_oko, 0]] - Xw[_Eo[_oko, 1]], axis=1) / _l0o[_oko] - 1), 99)
pull_info = {}
# PULLS: a sequence; each drags its handles ("points": the collar points; "corners": the collar's sewn ends = the band's
# top corners at CF; or ["piece:point", ...]) along its direction until the cloth would stretch (or `max` m). Handles
# pulled earlier are HELD where they ended (Joe: move these apart a little, then push the points a little more).
seq = A.get("pulls") or ([A["pull"]] if A.get("pull") else [])
done_h = {}
def handle_set(h, patch=0.0):
    """handles -> {key: welded vertex ids}. patch (m, pattern distance): grab the collar point WITH the cloth within
    `patch` of it as one rigid piece (a hand grabs an area; one vertex dragged pinches the tip)."""
    if h == "points":
        out = {}
        for s_ in ("left", "right"):
            o = P[f"collar:{s_}TopEdge"]; k = pid[o]
            vv = np.where((pid == k) & (np.linalg.norm(uv - uv[o], axis=1) <= patch))[0] if patch > 0 else np.array([o])
            out[s_] = np.unique(inv[vv])
        return out
    if h == "corners": return {s_: inv[P[f"collar:{s_}BottomEdge"]] for s_ in ("left", "right")}
    return {nmk: inv[P[nmk]] for nmk in h}
for k_, PL in enumerate(seq):
    H = handle_set(PL.get("handles", "points"), PL.get("patch", 0.0))
    H = {key: np.atleast_1d(v) for key, v in H.items()}
    hold = hW | np.isin(np.arange(n), list(bnd) + list(done_h.values()))
    s0 = stretch(Y); dirs = {}
    for key, v in H.items():
        _, jj = bt.query(Y[v].mean(0))
        side_lm = P.get(f"collar:{key}TopHinge") if key in ("left", "right") else None
        sg = np.sign(W0[inv[side_lm], 0]) if side_lm is not None else np.sign(W0[v, 0].mean())
        d_ = PL.get("side", 1.0) * np.r_[sg, 0, 0] + PL.get("out", 0.0) * vn[jj] + PL.get("up", 0.0) * np.r_[0, 0, 1]
        dirs[key] = d_ / np.linalg.norm(d_)
    pos = {key: Y[v].copy() for key, v in H.items()}; moved = 0.0; good_Y = Y.copy()
    # the grabbed point itself (a patch's lead vertex: the collar point), for the turning patch below
    lead = {key: (inv[P[f"collar:{key}TopEdge"]] if key in ("left", "right") else v[0]) for key, v in H.items()}
    def kabsch(A_, B_):  # proper rotation R and t with R A_ + t ~ B_
        a0, b0 = A_.mean(0), B_.mean(0); Hm = (A_ - a0).T @ (B_ - b0); Uk, _, Vk = np.linalg.svd(Hm)
        dk = np.sign(np.linalg.det(Vk.T @ Uk.T)); R_ = Vk.T @ np.diag([1, 1, dk]) @ Uk.T; return R_, b0 - R_ @ a0
    def plane_dir(Yc, key):
        """'pull outward along the plane of the collar' (Joe): at the point, the direction AWAY from the cloth (minus
        the mean direction to its near neighbours on the pattern, within 12 mm), projected onto the leaf's tangent
        plane there (normal: the mean face normal of those vertices). Follows the leaf as it turns."""
        o = P[f"collar:{key}TopEdge"]; k = pid[o]
        nb = np.where((pid == k) & (np.linalg.norm(uv - uv[o], axis=1) < 0.012))[0]
        w_ = inv[nb]; c_ = Yc[w_].mean(0); out = Yc[inv[o]] - c_
        fmask = np.isin(F[:, 0], nb) & np.isin(F[:, 1], nb) & np.isin(F[:, 2], nb)
        nn_ = np.cross(Yc[inv[F[fmask, 1]]] - Yc[inv[F[fmask, 0]]], Yc[inv[F[fmask, 2]]] - Yc[inv[F[fmask, 0]]]).sum(0)
        nn_ /= np.linalg.norm(nn_) + 1e-12
        out -= (out @ nn_) * nn_; return out / (np.linalg.norm(out) + 1e-12)
    PLANE = PL.get("dir") in ("plane", "easy") and PL.get("handles", "points") == "points"
    path = {key: pos[key].copy() for key in H}   # (the plane pull walks: each step from where the last one ended)
    while moved < PL.get("max", 0.08) - 1e-9:
        moved += PL.get("step", 0.003); T = good_Y.copy(); fx = hold.copy()
        if PLANE and PL.get("dir") == "plane":
            for key in H:
                dirs[key] = plane_dir(good_Y, key)
        if PL.get("dir") == "easy":
            # "let the cloth choose": candidates = side tilted toward +-normal / +-up by 0 / 35 / 70 deg; each probed with
            # a short solve (both sides together, mirrored), the least-stretch one taken for this step
            best = None
            for ax_ in ("n", "u"):
                for ang in (0, 35, -35, 70, -70):
                    if ax_ == "u" and ang == 0: continue
                    cand = {}
                    for key, v in H.items():
                        _, jj = bt.query(good_Y[lead[key]]); sgn = np.sign(W0[inv[P[f"collar:{key}TopHinge"]], 0])
                        sd = np.r_[sgn, 0, 0]; other = vn[jj] if ax_ == "n" else np.r_[0, 0, 1.0]
                        other = other - (other @ sd) * sd; other /= np.linalg.norm(other) + 1e-12
                        cand[key] = np.cos(np.radians(ang)) * sd + np.sin(np.radians(ang)) * other
                    Tp = good_Y.copy(); fxp = hold.copy()
                    for key2, v2 in done_h.items(): fxp[v2] = True
                    for key, v in H.items(): Tp[lead[key]] = good_Y[lead[key]] + PL.get("step", 0.003) * cand[key]; fxp[lead[key]] = True
                    stp_ = stretch(solve(Tp, fxp, PL.get("probe_iters", 4)))
                    if best is None or stp_ < best[0]: best = (stp_, cand)
            dirs = best[1]
        for key, v in done_h.items(): fx[v] = True
        if PL.get("turn") and any(len(v) > 1 for v in H.values()):
            # TURNING PATCH: drag the lead vertex alone, then fit each patch's unstretched start shape rigidly
            # (rotation + translation, Kabsch) onto that solution, pin it with the lead on its target, solve again
            tgt_lead = {key: (good_Y[lead[key]] + PL.get("step", 0.003) * dirs[key]) if PLANE else
                        (pos[key][list(v).index(lead[key])] + moved * dirs[key]) for key, v in H.items()}
            for key, v in H.items(): T[lead[key]] = tgt_lead[key]; fx[lead[key]] = True
            Yt = solve(T, fx, PL.get("iters", 12))
            for _r in range(PL.get("turn_rounds", 2)):
                T2 = Yt.copy(); fx2 = fx.copy()
                for key, v in H.items():
                    R_, t_ = kabsch(pos[key], Yt[v]); Pn = pos[key] @ R_.T + t_
                    li = list(v).index(lead[key]); Pn += tgt_lead[key] - Pn[li]
                    T2[v] = Pn; fx2[v] = True
                Yt = solve(T2, fx2, PL.get("iters", 12))
        else:
            for key, v in H.items(): T[v] = pos[key] + moved * dirs[key]; fx[v] = True
            Yt = solve(T, fx, PL.get("iters", 12))
        st_ = stretch(Yt)
        if st_ > s0 + PL.get("tol", 0.01): moved -= PL.get("step", 0.003); break
        good_Y = Yt
    Y = good_Y
    for key, v in H.items():
        for i_, vv in enumerate(np.atleast_1d(v)): done_h[f"{k_}:{key}:{i_}"] = vv
    pull_info[k_] = {"handles": PL.get("handles", "points"), "moved_mm": round(moved * 1000, 1), "stretch_p99": [round(s0 * 100, 2), round(stretch(Y) * 100, 2)]}
    print("pull", k_, pull_info[k_])
Y = solve(Y, hW | np.isin(np.arange(n), list(pts.values()) + list(bnd) + list(done_h.values())), 10)
# SMOOTH (Joe: "a 'smooth' operation ... in conjunction with the 'pull'; those are the two main operations to styling the
# clothing one is wearing"): within the brushed pieces, alternate (a) fair: each vertex moved `lam` of the way toward its
# one-ring centroid ALONG ITS NORMAL only (a hand flattening a ripple), (b) restore: the flat-pattern solve with
# everything outside the brush (and the pulled handles) held. Stop when the stretch would exceed the start's + tol, or the
# roughness stops dropping. Same rule as the pull: as far as it goes without stretching.
smooth_info = {}
if A.get("smooth"):
    SM = A["smooth"]; brush = np.zeros(n, bool)
    brush[inv[np.isin(pid, [nm.index(p) for p in SM.get("pieces", ["collar", "stand"])])]] = True
    keep = ~brush | hW | np.isin(np.arange(n), list(done_h.values()) + list(bnd))
    Ew = np.unique(np.sort(np.r_[WF[:, [0, 1]], WF[:, [1, 2]], WF[:, [2, 0]]], 1), axis=0)
    cnt = np.zeros(n); np.add.at(cnt, Ew[:, 0], 1); np.add.at(cnt, Ew[:, 1], 1)
    def vnorm(Yc):
        fn_ = np.cross(Yc[WF[:, 1]] - Yc[WF[:, 0]], Yc[WF[:, 2]] - Yc[WF[:, 0]]); vv = np.zeros_like(Yc)
        for k in range(3): np.add.at(vv, WF[:, k], fn_)
        return vv / (np.linalg.norm(vv, axis=1)[:, None] + 1e-12)
    def rough_(Yc):
        Sx = np.zeros_like(Yc); np.add.at(Sx, Ew[:, 0], Yc[Ew[:, 1]]); np.add.at(Sx, Ew[:, 1], Yc[Ew[:, 0]])
        d_ = Sx / np.maximum(cnt, 1)[:, None] - Yc; return d_, np.abs((d_ * vnorm(Yc)).sum(1))
    s0 = stretch(Y); r0 = np.percentile(rough_(Y)[1][brush & ~keep], 95); rr = r0; k_ = 0
    for k_ in range(1, SM.get("rounds", 20) + 1):
        d_, _ = rough_(Y); nv_ = vnorm(Y); T = Y.copy()
        mv = (d_ * nv_).sum(1)[:, None] * nv_ * SM.get("lam", 0.5)
        T[~keep] += mv[~keep]
        Yt = solve(T, keep.copy(), SM.get("iters", 6))
        rt = np.percentile(rough_(Yt)[1][brush & ~keep], 95)
        if stretch(Yt) > s0 + SM.get("tol", 0.005) or rt > rr * 0.995: break
        Y, rr = Yt, rt
    smooth_info = {"rounds": k_, "rough_p95_mm": [round(r0 * 1000, 3), round(rr * 1000, 3)], "stretch_p99": [round(s0 * 100, 2), round(stretch(Y) * 100, 2)]}
    print("smooth:", smooth_info)
for v, (a0, (hb, ax, th), _dr) in bnd.items():
    print("band handle", np.round(a0*1000).astype(int), "->", np.round((hb + rodr((a0 - hb)[None], ax, th)[0])*1000).astype(int), "got", np.round(Y[v]*1000).astype(int))
X = Y[inv]
E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
lu_ = np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1); l3 = np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1)
ok = (lu_ > 1e-5) & (pid[E[:, 0]] == pid[E[:, 1]]); st = np.abs(l3[ok] / lu_[ok] - 1)
print(f"edge strain vs the pattern: p50 {np.median(st)*100:.1f} %, p99 {np.percentile(st,99)*100:.1f} %")
out = dict(d); out["A"] = X; out["A_info"] = dict(d["A_info"], flatarap=A, worn_open_mm=None)
pickle.dump(out, open(f"{D}{tag}.pkl", "wb")); print("saved", tag)
