"""build2.py <tag> [json]: model Simon's stand + collar on the closed fit v1 by bending the flat pieces.
Each piece is ruled: straight lines across it in the flat (seam edge -> far edge, matched by arc length between
landmarks) stay straight lines of the same length, at the same angle to the seam, in 3D. Only the fold of each ruling
about the seam is chosen: the stand leans in by the angle that gives its cut top-edge length; the collar rolls over
the stand top (radius r) and falls flared by the angle that gives its cut outer-edge length; where it meets the shirt it
lies on it. The neckline is the fit's, made mirror-symmetric with the band's CF on the centre line (it buttons there)."""
import sys, json, pickle
import numpy as np
from scipy.spatial import cKDTree
from scipy.interpolate import LinearNDInterpolator

D = "/mnt/data/hifipushie/folds_ab/D/"
tag = sys.argv[1]; P = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
r = P.get("r", 0.003); off = P.get("off", 0.0035)
d = pickle.load(open("/mnt/data/hifipushie/shirt_spike/v1.pkl", "rb"))
X = np.asarray(d["A"], float).copy(); M = d["mesh"]; uv = M["uv"]; pc = M["piece"]; nm = M["names"]; F = np.asarray(M["F"])
PT = {k: int(np.atleast_1d(v)[0]) for k, v in M["points"].items()}
iS, iC = nm.index("stand"), nm.index("collar")
bodyp = [nm.index(n) for n in ("back", "yoke", "front.R", "front.L")]
def pairs(a, b):
    out = {}
    for x, y in M["sew"]:
        if pc[x] == a and pc[y] == b: out[x] = y
        elif pc[y] == a and pc[x] == b: out[y] = x
    return out
c2s = pairs(iC, iS); s2b = {}
for bp in bodyp: s2b.update(pairs(iS, bp))
def arclen(Q): return np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
def unit(v): return v / np.linalg.norm(v, axis=-1, keepdims=True)
def tangent(Q, k=5):
    n = len(Q); i = np.arange(n); a, b = np.clip(i - k, 0, n - 1), np.clip(i + k, 0, n - 1); return unit(Q[b] - Q[a])

# ---------- neckline: the stand's bottom edge, symmetrised, CF on the centre line
sb = np.array(sorted(s2b, key=lambda v: uv[v, 0])); B = X[sb].copy()
mir = cKDTree(uv[sb] * [-1, 1]).query(uv[sb])[1]
B = (B + B[mir] * [-1, 1, 1]) / 2
cfL, cfR = uv[PT["stand:leftBottomCf"], 0], uv[PT["stand:rightBottomCf"], 0]
for sgn, cfu in ((1, cfR), (-1, cfL)):                 # each half: shift x so its CF point sits on x = 0
    j = np.argmin(np.abs(uv[sb, 0] - cfu)); dx = B[j, 0]
    w = np.clip(1 - np.abs(uv[sb, 0] - cfu) / 0.08, 0, 1)
    side = np.sign(uv[sb, 0]) == np.sign(cfu); B[side, 0] -= dx * w[side]
for cfu in (cfL, cfR):                                 # the tab past CF lies over the other band: mirror image
    half = np.sign(uv[sb, 0]) == np.sign(cfu); tab = half & (np.abs(uv[sb, 0]) > abs(cfu))
    body_ = half & ~tab & (np.abs(uv[sb, 0] - cfu) < 0.04); sx = np.sign(B[body_, 0].mean()); o = np.argsort(B[body_, 0])
    xs = B[body_][o]
    for j in np.where(tab)[0]:
        xm = -B[j, 0]
        if np.sign(xm) != sx: xm = -xm
        p = np.array([np.interp(xm, xs[:, 0], xs[:, k]) for k in range(3)]); B[j] = [-p[0], p[1], p[2]]
if P.get("rest", True):                                  # the back neckline rests on the neck base (the band has ease)
    j = np.argmin(np.abs(uv[sb, 0])); dz = B[j, 2] - d["at"]["cb_neck"][2]
    wB = np.cos(np.clip(np.abs(uv[sb, 0]) / 0.11, 0, 1) * np.pi / 2) ** 2
    if dz > 0:
        B[:, 2] -= dz * wB
        bm = np.isin(pc, bodyp); bi = np.where(bm)[0]; dist, k = cKDTree(B).query(X[bi])
        X[bi, 2] -= dz * wB[k] * np.clip(1 - dist / 0.05, 0, 1)
        print(f"back neckline lowered {dz*1e3:.1f} mm onto the neck base")
def rot(p, a, k, th):
    p = p - a; c, s_ = np.cos(th)[:, None], np.sin(th)[:, None]
    return a + p * c + np.cross(k, p) * s_ + k * (p @ k)[:, None] * (1 - c)
OPEN = P.get("open")                                     # turn-back angle (deg) of each front about side-neck -> V
if OPEN:
    zV = d["at"]["hps.L"][2] - P.get("v_below", 0.083); band = P.get("band", 0.03)
    frp = [nm.index("front.L"), nm.index("front.R")]; fm = np.isin(pc, frp)
    cand = np.where(fm & (np.abs(X[:, 0]) < 0.01) & (np.abs(X[:, 2] - zV) < 0.004))[0]
    Vp = X[cand[np.argmin(X[cand, 1])]].copy(); Vp[0] = 0.0; Vp[1] -= 0.002
    for half_sign in (1, -1):                            # by 3D side, landmark well off CF
        hp = np.array(d["at"]["hps.L"]) * [half_sign, 1, 1]
        H = B[np.argmin(np.linalg.norm(B - hp, axis=1))]
        k = unit(H - Vp); nrm_h = unit(np.cross(k, [0, -1.0, 0]))
        if nrm_h[0] * half_sign > 0: nrm_h = -nrm_h       # towards CF
        def field(Q, extra=None):
            w = np.clip(((Q - Vp) @ nrm_h) / band + 0.5, 0, 1); w = w * w * (3 - 2 * w)
            w *= (Q[:, 1] < H[1] + 0.01)                  # front of the neck only
            if extra is not None: w *= extra
            return w
        th = np.radians(OPEN)
        p0 = (H + Vp) / 2 + nrm_h * 0.01
        if (rot(p0[None], Vp, k, np.array([0.3]))[0, 0] - p0[0]) * half_sign < 0: th = -th
        # which neckline points belong to this half: the half whose band runs on this 3D side away from CF
        hb = np.where(np.sign(uv[sb, 0]) == np.sign(uv[sb[np.argmin(np.linalg.norm(B - hp, axis=1))], 0]))[0]
        B[hb] = rot(B[hb], Vp, k, th * field(B[hb]))
        fi = np.where(np.isin(pc, frp) & (np.sign(X[:, 0] + 1e-9) == half_sign) | (pc == frp[0 if half_sign > 0 else 1]))[0]
        fi = np.where(pc == (frp[0] if np.sign(X[pc == frp[0], 0].mean()) == half_sign else frp[1]))[0]
        wz = np.clip((X[fi, 2] - zV) / 0.02 + 0.5, 0, 1); wz = wz * wz * (3 - 2 * wz)
        X[fi] = rot(X[fi], Vp, k, th * field(X[fi], wz))
    print(f"opened: fronts turned back {OPEN} deg about side neck -> V ({P.get('v_below', 0.083)*1e3:.0f} mm below HPS)")
tB = tangent(B)
yax = (d["at"]["cf_neck"][1] + d["at"]["cb_neck"][1]) / 2

# ---------- ruled map of one piece: seam edge (3D known) -> far edge, flat rulings matched by arc length
META = []
def ruled(seam_v, far_v, seam_lm, far_lm, seam3, frame, n_lambda=40):
    """seam_v / far_v: ordered vertex ids; *_lm: matching landmark positions (indices into the orders);
    frame(i, phi_t, phi_n) -> 3D point for ruling i given its along / across offsets; returns flat grid + 3D grid."""
    sa, fa = arclen(uv[seam_v]), arclen(uv[far_v])
    def match(i):                                        # far-edge arc position matched to seam index i
        for (s0, f0), (s1, f1) in zip(zip(seam_lm, far_lm), zip(seam_lm[1:], far_lm[1:])):
            if s0 <= i <= s1:
                u = (sa[i] - sa[s0]) / max(sa[s1] - sa[s0], 1e-12); return fa[f0] + u * (fa[f1] - fa[f0])
        return None
    tf = tangent(uv[seam_v]); nf = np.c_[-tf[:, 1], tf[:, 0]]
    if np.dot(uv[far_v].mean(0) - uv[seam_v].mean(0), nf.mean(0)) < 0: nf = -nf
    G2, G3 = [], []; META.clear()
    for i in range(len(seam_v)):
        fpos = match(i)
        if fpos is None: continue
        q = np.array([np.interp(fpos, fa, uv[far_v, 0]), np.interp(fpos, fa, uv[far_v, 1])])
        a0 = uv[seam_v[i]]; R = q - a0
        along, across = R @ tf[i], R @ nf[i]; META.append((i, along, across, q))
        for lam in np.linspace(-0.03, 1.03, n_lambda):
            G2.append(a0 + lam * R); G3.append(frame(i, lam * along, lam * across))
    return np.array(G2), np.array(G3)

def edge_order(piece, seam_set):
    vs = [v for v in np.where(pc == piece)[0] if M["border"][v] and v not in seam_set]
    return np.array(sorted(vs, key=lambda v: uv[v, 0]))

def place(piece, G2, G3):
    ids = np.where(pc == piece)[0]; f = LinearNDInterpolator(G2, G3)(uv[ids])
    bad = np.isnan(f[:, 0])
    if bad.any():                                        # outside the ruled region (a band's tab): nearest grid point's offset
        k = cKDTree(G2).query(uv[ids[bad]])[1]; f[bad] = G3[k]
    return ids, f, bad.sum()

# ---------- stand: rulings bottom -> top, leaning in by beta
st_top = np.array(sorted([v for v in np.where(pc == iS)[0] if v in set(c2s.values())], key=lambda v: uv[v, 0]))
def lm_idx(order, keys): return [int(np.argmin(np.linalg.norm(uv[order] - uv[PT[k]], axis=1))) for k in keys]
s_lm = lm_idx(sb, ["stand:leftBottomCf", "stand:leftBottomHinge", "stand:bottomMid", "stand:rightBottomHinge", "stand:rightBottomCf"])
t_lm = lm_idx(st_top, ["stand:leftTopCf", "stand:leftTopHinge", "stand:topMid", "stand:rightTopHinge", "stand:rightTopCf"])
zp = np.tile([0, 0, 1.0], (len(sb), 1)); zp -= tB * np.einsum("ij,ij->i", zp, tB)[:, None]
inw = np.c_[-B[:, 0], yax - B[:, 1], np.zeros(len(sb))]
inw -= tB * np.einsum("ij,ij->i", inw, tB)[:, None]; inw -= unit(zp) * np.einsum("ij,ij->i", inw, unit(zp))[:, None]
zp, inw = unit(zp), unit(inw)
def stand(beta):
    beta = np.broadcast_to(beta, (len(sb),))
    U = zp * np.cos(beta)[:, None] + inw * np.sin(beta)[:, None]
    return ruled(sb, st_top, s_lm, t_lm, B, lambda i, a, t: B[i] + tB[i] * a + U[i] * t)
topcut = arclen(uv[st_top])[t_lm[-1]] - arclen(uv[st_top])[t_lm[0]]
LAMS = np.linspace(-0.03, 1.03, 40); J1 = int(np.argmin(np.abs(LAMS - 1)))
def toplen(G3, n=40): tops = G3[J1::n]; return arclen(tops)[-1]
lo, hi = np.radians(-30), np.radians(60)
for _ in range(25):
    m = (lo + hi) / 2
    if toplen(stand(m)[1]) > topcut: lo = m
    else: hi = m
beta = (lo + hi) / 2
if P.get("local_lean", True):                            # each stretch of the band leans so its top edge has the cut length
    from scipy.optimize import least_squares
    from scipy.sparse import lil_matrix
    stand(beta); meta = list(META); I = np.array([m[0] for m in meta]); AL = np.array([m[1] for m in meta])
    AC = np.array([m[2] for m in meta]); Q2 = np.array([m[3] for m in meta]); L2 = np.linalg.norm(np.diff(Q2, axis=0), axis=1)
    lam = P.get("smooth", 0.02)
    def tops(b_):
        U = zp[I] * np.cos(b_)[:, None] + inw[I] * np.sin(b_)[:, None]; return B[I] + tB[I] * AL[:, None] + U * AC[:, None]
    def res(b_):
        Tq = tops(b_); return np.r_[np.linalg.norm(np.diff(Tq, axis=0), axis=1) - L2, lam * np.diff(b_, 2)]
    n = len(I); Js = lil_matrix((n - 1 + n - 2, n))
    for j in range(n - 1): Js[j, j] = Js[j, j + 1] = 1
    for j in range(n - 2): Js[n - 1 + j, j:j + 3] = 1
    sol = least_squares(res, np.full(n, beta), jac_sparsity=Js, bounds=(np.radians(-40), np.radians(70)))
    bfull = np.full(len(sb), beta); bfull[I] = sol.x
    beta = bfull; print(f"stand lean per stretch: {np.degrees(sol.x.min()):.0f}..{np.degrees(sol.x.max()):.0f} deg (back {np.degrees(sol.x[n//2]):.0f})")
G2s, G3s = stand(beta); ids, f, nb = place(iS, G2s, G3s); X[ids] = f
print(f"stand: mean lean {np.degrees(np.mean(beta)):.1f} deg; top edge {topcut*1e3:.1f} mm cut; {nb} tab vertices placed by nearest ruling")

# ---------- collar: rulings neck edge -> outer edge; roll over the stand top, fall flared by alpha
neck = np.array(sorted(c2s, key=lambda v: uv[v, 0])); T = X[[c2s[v] for v in neck]]
tT = tangent(T)
Bt = cKDTree(uv[sb, :1]).query(uv[[c2s[v] for v in neck], :1])[1]
dn = unit(B[Bt] - T); dn = unit(dn - tT * np.einsum("ij,ij->i", dn, tT)[:, None])
nrm = unit(np.cross(tT, dn)); out = np.c_[T[:, 0], T[:, 1] - yax]
nrm *= np.sign(np.einsum("ij,ij->i", nrm[:, :2], out))[:, None]
hS = np.einsum("ij,ij->i", B[Bt] - T, dn)
def border_loop(piece):
    E = F[np.all(pc[F] == piece, axis=1)]; ed = np.sort(np.r_[E[:, [0, 1]], E[:, [1, 2]], E[:, [2, 0]]], axis=1)
    u, c = np.unique(ed, axis=0, return_counts=True); be = u[c == 1]; nb = {}
    for a, b in be: nb.setdefault(a, []).append(b); nb.setdefault(b, []).append(a)
    loop = [be[0, 0]]; prev = None
    while True:
        nx = [x for x in nb[loop[-1]] if x != prev][0]
        if nx == loop[0]: break
        prev = loop[-1]; loop.append(nx)
    return np.array(loop)
loop = border_loop(iC); cL, cR = PT["collar:leftTopEdge"], PT["collar:rightTopEdge"]
iL, iR = int(np.where(loop == cL)[0][0]), int(np.where(loop == cR)[0][0])
pa = np.roll(loop, -iL)[: (iR - iL) % len(loop) + 1]; pb = np.roll(loop, -iR)[: (iL - iR) % len(loop) + 1][::-1]
ns = set(neck); outer = pa if len(ns & set(pa)) < len(ns & set(pb)) else pb
n_lm = lm_idx(neck, ["collar:leftBottomEdge", "collar:bottomMid", "collar:rightBottomEdge"])
o_lm = lm_idx(outer, ["collar:leftTopEdge", "collar:topMid", "collar:rightTopEdge"])
smask = np.isin(pc, bodyp); sidx = np.where(smask)[0]; kd = cKDTree(X[sidx])
FS = F[np.all(smask[F], axis=1)]; VN = np.zeros_like(X)
fn = np.cross(X[FS[:, 1]] - X[FS[:, 0]], X[FS[:, 2]] - X[FS[:, 0]])
for k in range(3): np.add.at(VN, FS[:, k], fn)
VN = VN / np.maximum(np.linalg.norm(VN, axis=1), 1e-12)[:, None]
def surf(p):
    _, j = kd.query(p, k=24); q = X[sidx[j]].mean(0); nq = unit(VN[sidx[j]].mean(0)); return p - nq * np.dot(p - q, nq), nq
def collar(alpha):
    def frame(i, a, t):
        dd, nn = dn[i], nrm[i]; S0 = T[i] - dd * P.get("lift", 0.001)
        if t <= np.pi * r:
            ph = t / r; x = S0 - dd * r * np.sin(ph) + nn * r * (1 - np.cos(ph))
        else:
            h2 = t - np.pi * r; x = S0 + nn * 2 * r + h2 * (dd * np.cos(alpha) + nn * np.sin(alpha))
            if h2 > hS[i] + 0.008:
                q, nq = surf(x)
                if np.dot(x - q, nq) < off: x = q + nq * off
        return x + tT[i] * a
    return ruled(neck, outer, n_lm, o_lm, T, frame)
ocut = arclen(uv[outer])[-1]
if P.get("alpha") is None:
    lo, hi = 0.0, np.radians(70)
    for _ in range(14):
        m = (lo + hi) / 2
        if toplen(collar(m)[1]) < ocut: lo = m
        else: hi = m
    alpha = (lo + hi) / 2
else: alpha = np.radians(P["alpha"])
G2c, G3c = collar(alpha); ids, f, nb = place(iC, G2c, G3c); X[ids] = f
print(f"collar: flare {np.degrees(alpha):.1f} deg; outer edge 3D {toplen(G3c)*1e3:.1f} vs cut {ocut*1e3:.1f} mm; {nb} outside rulings")
if P.get("mirror", True):                                  # worn straight: one side built, the other its mirror image
    for piece in (iS, iC):
        ids = np.where(pc == piece)[0]; Lh = ids[uv[ids, 0] < 0]; Rh = ids[uv[ids, 0] >= 0]
        j = cKDTree(uv[Lh] * [-1, 1]).query(uv[Rh])[1]; X[Rh] = X[Lh[j]] * [-1, 1, 1]
        c0 = ids[np.abs(uv[ids, 0]) < 0.0015]; X[c0, 0] = 0.0                # on the centre line
for k in ["stand:leftTopCf", "stand:rightTopCf", "collar:leftBottomEdge", "collar:rightBottomEdge", "collar:leftTopEdge", "collar:rightTopEdge"]:
    v = PT[k]; print(f"  {k:22s} x {X[v,0]*1e3:+5.0f} y {X[v,1]*1e3:+5.0f} z {X[v,2]*1e3:.0f}")
for piece in (iS, iC):
    E = F[np.all(pc[F] == piece, axis=1)]; ed = np.r_[E[:, [0, 1]], E[:, [1, 2]], E[:, [2, 0]]]
    e = np.linalg.norm(X[ed[:, 0]] - X[ed[:, 1]], axis=1) / np.linalg.norm(uv[ed[:, 0]] - uv[ed[:, 1]], axis=1) - 1
    print(f"  {nm[piece]} edge length vs cut: p05 {np.percentile(e,5)*100:+.1f} % p50 {np.percentile(e,50)*100:+.1f} % p95 {np.percentile(e,95)*100:+.1f} %")
pickle.dump({"A": X, "mesh": M, "bodyV": d["bodyV"], "bodyF": d["bodyF"], "at": d["at"], "P": P}, open(f"{D}{tag}.pkl", "wb"))
print("saved", tag)
