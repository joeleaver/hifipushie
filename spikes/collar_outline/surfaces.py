"""surfaces.py <tag>: fill band + collar between the outline chains (fixed) with the smoothest spanning surface on each
piece's own pattern mesh (Laplace, edge weights from the flat), then keep the collar outside the band by a layer."""
import sys, pickle
import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve
from scipy.spatial import cKDTree
D = "/mnt/data/hifipushie/folds_ab/D/"; t = sys.argv[1]
o = pickle.load(open(f"{D}{t}_outline.pkl", "rb")); X = o["X"].copy(); M = o["mesh"]; F = np.asarray(M["F"]); uv = M["uv"]; pc = M["piece"]; nm = M["names"]
fixed = set(int(v) for k_, ord_ in o["orders"].items() for v in ord_)
if not (len(sys.argv) > 2 and sys.argv[2] == "noturn"):          # the fold's turn: up the band, over a half circle, down outside
    iS_, iC_ = nm.index("stand"), nm.index("collar"); r_t = 0.0012
    neckc_ = np.asarray(o["orders"]["neck_c"]); rollc_ = np.asarray(o["orders"]["roll"]); sbo = np.asarray(o["orders"]["neckline"])
    S_ = X[neckc_]; kbx = cKDTree(uv[sbo, :1]); Bb = X[sbo[kbx.query(uv[neckc_, :1])[1]]]
    _n = len(S_); _i = np.arange(_n); tg = S_[np.clip(_i + 5, 0, _n - 1)] - S_[np.clip(_i - 5, 0, _n - 1)]   # wide stencil
    tg /= np.linalg.norm(tg, axis=1)[:, None]
    up = S_ - Bb; up -= tg * np.einsum("ij,ij->i", up, tg)[:, None]; up /= np.linalg.norm(up, axis=1)[:, None]
    nn = np.cross(tg, up); yax_ = (o["at"]["cf_neck"][1] + o["at"]["cb_neck"][1]) / 2
    nn *= np.sign(np.einsum("ij,ij->i", nn[:, :2], np.c_[S_[:, 0], S_[:, 1] - yax_]))[:, None]
    kn2 = cKDTree(uv[neckc_]); t_roll = float(np.median(kn2.query(uv[rollc_])[0]))
    L1 = max(t_roll - np.pi * r_t / 2, 0.0005); t_end = L1 + np.pi * r_t
    E2 = uv[neckc_]; ea, eb = E2[:-1], E2[1:]
    def proj(p2):                                      # (index, fraction, overshoot past the ends, distance across) on the flat seam
        v_ = eb - ea; w_ = p2 - ea; f0 = (w_ * v_).sum(1) / (v_ * v_).sum(1); f = np.clip(f0, 0, 1)
        q = ea + v_ * f[:, None]; dd_ = np.linalg.norm(p2 - q, axis=1); k = int(np.argmin(dd_))
        over = 0.0
        if k == 0 and f0[0] < 0: over = f0[0] * np.linalg.norm(v_[0])
        if k == len(ea) - 1 and f0[k] > 1: over = (f0[k] - 1) * np.linalg.norm(v_[k])
        nrm2 = np.array([-v_[k, 1], v_[k, 0]]) / np.linalg.norm(v_[k])
        return k, f[k], over, abs((p2 - (ea[k] + v_[k] * f0[k])) @ nrm2)
    def lerp(A_, k, f): return A_[k] * (1 - f) + A_[k + 1] * f
    cvs = np.where(pc == iC_)[0]; ns_ = set(neckc_); nturn = 0
    for v in cvs:
        if v in ns_: continue
        k, f, over, tt_ = proj(uv[v])
        if tt_ > t_end: continue
        Sv = lerp(S_, k, f); tv = lerp(tg, k, f); tv /= np.linalg.norm(tv); uvv = lerp(up, k, f); uvv /= np.linalg.norm(uvv)
        nv = lerp(nn, k, f); nv /= np.linalg.norm(nv)
        Sv = Sv + tv * over * (1 if k > 0 else 1)          # past the seam's end: carry on along it
        if tt_ <= L1: X[v] = Sv + uvv * tt_ + nv * 0.0003
        else:
            ph = (tt_ - L1) / r_t; C_ = Sv + uvv * L1 + nv * (r_t + 0.0003)
            X[v] = C_ - nv * r_t * np.cos(ph) + uvv * r_t * np.sin(ph)
        fixed.add(int(v)); nturn += 1
    sel = np.zeros(nturn)
    for v in rollc_: fixed.add(int(v))
    print(f"fold turn: {sel.sum()} vertices on the turn (crown at the roll line, {t_roll*1e3:.1f} mm up; radius {r_t*1e3:.1f} mm)")
for piece in (nm.index("stand"), nm.index("collar")):
    Fp = F[np.all(pc[F] == piece, axis=1)]; ids = np.unique(Fp); li = {v: i for i, v in enumerate(ids)}
    ed = np.unique(np.sort(np.r_[Fp[:, [0, 1]], Fp[:, [1, 2]], Fp[:, [2, 0]]], axis=1), axis=0)
    w = 1.0 / np.maximum(np.linalg.norm(uv[ed[:, 0]] - uv[ed[:, 1]], axis=1), 1e-5)
    a, b = np.array([li[v] for v in ed[:, 0]]), np.array([li[v] for v in ed[:, 1]]); n = len(ids)
    L = sp.coo_matrix((np.r_[w, w], (np.r_[a, b], np.r_[b, a])), shape=(n, n)).tocsr(); L = sp.diags(np.asarray(L.sum(1)).ravel()) - L
    fx = np.array([v in fixed for v in ids]); fr = ~fx
    A = L[fr][:, fr].tocsc(); rhs = -L[fr][:, fx] @ X[ids[fx]]
    X[ids[fr]] = np.column_stack([spsolve(A, rhs[:, k]) for k in range(3)])
    print(f"{nm[piece]}: {fx.sum()} chain vertices fixed, {fr.sum()} filled")
# the collar's fall stays a layer outside the band (it lies over it)
iS, iC = nm.index("stand"), nm.index("collar")
Fs = F[np.all(pc[F] == iS, axis=1)]; sv = np.unique(Fs); kd = cKDTree(X[sv])
VN = np.zeros_like(X); fn = np.cross(X[Fs[:, 1]] - X[Fs[:, 0]], X[Fs[:, 2]] - X[Fs[:, 0]])
for k in range(3): np.add.at(VN, Fs[:, k], fn)
VN /= np.maximum(np.linalg.norm(VN, axis=1), 1e-12)[:, None]
cen = np.array([0, (o["at"]["cf_neck"][1] + o["at"]["cb_neck"][1]) / 2, 0])
outw = np.sign(np.einsum("ij,ij->i", VN[sv][:, :2], (X[sv] - cen)[:, :2]))[:, None]; VN[sv] *= outw
neckc = np.asarray(o["orders"]["neck_c"]); rollc = np.asarray(o["orders"]["roll"])
kn_ = cKDTree(uv[neckc]); dr_ = np.median(kn_.query(uv[rollc])[0])
cv = np.array([v for v in np.where(pc == iC)[0] if v not in fixed])
inturn = np.zeros(len(cv), bool)                              # the fold's own turn wraps the band: leave it
Fc = F[np.all(pc[F] == iC, axis=1)]; idsC = np.unique(Fc); liC = {v: i for i, v in enumerate(idsC)}
edC = np.unique(np.sort(np.r_[Fc[:, [0, 1]], Fc[:, [1, 2]], Fc[:, [2, 0]]], axis=1), axis=0)
nbr = [[] for _ in idsC]
for a_, b_ in edC: nbr[liC[a_]].append(b_); nbr[liC[b_]].append(a_)
npush = 0
for it in range(30):                                                    # push out gently, re-smooth, repeat
    dd, j = kd.query(X[cv]); q = X[sv[j]]; nq = VN[sv[j]]
    sd = np.einsum("ij,ij->i", X[cv] - q, nq); push = (sd < 0.0015) & (dd < 0.01) & ~inturn
    npush = max(npush, int(push.sum()))
    X[cv[push]] += 0.5 * nq[push] * (0.0015 - sd[push])[:, None]
    Xn = X.copy()
    for k_, v in enumerate(cv):
        if inturn[k_]: continue
        Xn[v] = 0.5 * X[v] + 0.5 * X[nbr[liC[v]]].mean(0)
    X = Xn
print(f"collar: up to {npush} vertices pushed outside the band (gently, re-smoothed); {inturn.sum()} in the fold's turn left as filled")
# corner patch: the last stretch of each leaf near its neck end copies the clean profile 10 mm inside, rigidly
if not (len(sys.argv) > 2 and sys.argv[2] == "noturn"):
    from scipy.interpolate import LinearNDInterpolator as LNI
    ci_c = np.where(pc == iC_)[0]; interp = LNI(uv[ci_c], X[ci_c])
    seam_s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(E2, axis=0), axis=1))]; Ltot = seam_s[-1]
    def frame(k, f):
        tv = lerp(tg, k, f); tv /= np.linalg.norm(tv); uvv = lerp(up, k, f); uvv -= tv * (uvv @ tv); uvv /= np.linalg.norm(uvv)
        return lerp(S_, k, f), np.c_[tv, uvv, np.cross(tv, uvv)]
    REACH, BLEND, TMAX = P_C = (0.010, 0.008, 0.034)
    npatch = 0
    for v in ci_c:
        k, f, over, tt_ = proj(uv[v])
        if tt_ > TMAX: continue
        sv_ = seam_s[k] + f * (seam_s[k + 1] - seam_s[k]) + over
        dend = min(sv_, Ltot - sv_)                                # distance to the nearer seam end (negative past it)
        if dend > REACH + BLEND: continue
        end_sign = -1 if sv_ < Ltot / 2 else 1
        s_ref = sv_ - end_sign * (REACH - min(dend, REACH)) if dend < REACH else sv_
        s_ref = (REACH if end_sign < 0 else Ltot - REACH)
        kr = int(np.clip(np.searchsorted(seam_s, s_ref) - 1, 0, len(seam_s) - 2)); fr = (s_ref - seam_s[kr]) / (seam_s[kr + 1] - seam_s[kr])
        # the flat point at the same distance across, at the reference section
        seam_uv_v = ea[k] + (eb[k] - ea[k]) * f; seam_uv_r = ea[kr] + (eb[kr] - ea[kr]) * fr
        tv2 = (eb[kr] - ea[kr]) / np.linalg.norm(eb[kr] - ea[kr]); tv2v = (eb[k] - ea[k]) / np.linalg.norm(eb[k] - ea[k])
        rel = uv[v] - seam_uv_v; rel_r = np.array([rel @ tv2v, rel @ np.array([-tv2v[1], tv2v[0]])])
        uv_ref = seam_uv_r + tv2 * 0 + np.array([-tv2[1], tv2[0]]) * rel_r[1]
        Xr = interp(uv_ref[None])[0]
        if np.isnan(Xr[0]): continue
        So, Fo = frame(kr, fr); St, Ft = frame(k, f); St = St + Ft[:, 0] * over
        Xp = St + Ft @ (Fo.T @ (Xr - So)) + Ft[:, 0] * rel_r[0] * 0
        w = 1.0 if dend <= REACH else 1 - (dend - REACH) / BLEND
        w *= 1.0 if tt_ <= TMAX - 0.016 else max(0.0, (TMAX - tt_) / 0.016)
        w = w * w * (3 - 2 * w)
        X[v] = (1 - w) * X[v] + w * Xp; npatch += 1
    print(f"corner patches: {npatch} vertices copy the profile {P_C[0]*1e3:.0f} mm inside")

# the band stays under the collar's fall where they overlap (its tab past the collar's end); re-smooth the band after
FcC = F[np.all(pc[F] == iC, axis=1)]; VNc = np.zeros_like(X); fnc = np.cross(X[FcC[:, 1]] - X[FcC[:, 0]], X[FcC[:, 2]] - X[FcC[:, 0]])
for k in range(3): np.add.at(VNc, FcC[:, k], fnc)
VNc /= np.maximum(np.linalg.norm(VNc, axis=1), 1e-12)[:, None]
cvv = np.unique(FcC); VNc[cvv] *= np.sign(np.einsum("ij,ij->i", VNc[cvv][:, :2], (X[cvv] - cen)[:, :2]))[:, None]
neck_set = np.asarray(o["orders"]["neck_c"]); knn = cKDTree(uv[neck_set]); fall = cvv[knn.query(uv[cvv])[0] > 0.008]
svb = np.array([v for v in sv if v not in fixed]); FsB = F[np.all(pc[F] == iS, axis=1)]; liB = {v: i for i, v in enumerate(sv)}
nbB = [[] for _ in sv]
for a_, b_ in np.unique(np.sort(np.r_[FsB[:, [0, 1]], FsB[:, [1, 2]], FsB[:, [2, 0]]], axis=1), axis=0): nbB[liB[a_]].append(b_); nbB[liB[b_]].append(a_)
moved = 0
for it in range(30):
    kf = cKDTree(X[fall]); dd, j = kf.query(X[svb]); q = X[fall[j]]; n_ = VNc[fall[j]]
    sd = np.einsum("ij,ij->i", X[svb] - q, n_); bad = (sd > -0.0008) & (dd < 0.008)
    moved = max(moved, int(bad.sum()))
    X[svb[bad]] -= 0.6 * n_[bad] * (sd[bad] + 0.0008)[:, None]
    Xn = X.copy()
    for v in svb: Xn[v] = 0.6 * X[v] + 0.4 * X[nbB[liB[v]]].mean(0)
    X = Xn
print(f"band: up to {moved} vertices kept under the collar's fall")
pickle.dump({"A": X, "mesh": M, "bodyV": o["bodyV"], "bodyF": o["bodyF"], "at": o["at"]}, open(f"{D}{t}S.pkl", "wb")); print("saved", t + "S")
