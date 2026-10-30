"""band_open.py <tag> [json]: the band ALONE, unbuttoned. Chains: neckline (band bottom) + band top, exact pattern links.
Lines across the band (bottom -> top at the same flat x) exact (interfaced). Back of the neckline (between the side
necks) stays where the closed build put it (sewn to the yoke, resting on the neck). Free: the rest. Solved: stiff
bending, outside the body, mirror symmetry, + style: the top CF ends part by `gap` (0 = just unbuttoned)."""
import sys, json, pickle
import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix
from scipy.spatial import cKDTree
D = "/mnt/data/hifipushie/folds_ab/D/"
tag = sys.argv[1]; P = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
o = pickle.load(open(D + "O15_outline.pkl", "rb"))
X0 = o["X"]; M = o["mesh"]; uv = M["uv"]; PT = {k: int(np.atleast_1d(v)[0]) for k, v in M["points"].items()}
sb, st = np.asarray(o["orders"]["neckline"]), np.asarray(o["orders"]["band_top"])
B0 = o["C0"]; T0 = o["chains"]["band_top"]
hu = abs(uv[PT["stand:rightBottomHinge"], 0]) * P.get("free_from", 1.0)
freeB = np.abs(uv[sb, 0]) > hu                                       # front stretches of the neckline
nB, nT = len(sb), len(st)
def unpack(x):
    B = B0.copy(); B[freeB] = x[:3 * freeB.sum()].reshape(-1, 3); T = x[3 * freeB.sum():].reshape(-1, 3); return B, T
from scipy.spatial.transform import Rotation as Rot
Bg, Tg = B0.copy(), T0.copy()
if P.get("swing0"):                                                   # starting guess: each front swung open at its side hinge
    for side in ("left", "right"):
        hb, ht = X0[PT[f"stand:{side}BottomHinge"]], X0[PT[f"stand:{side}TopHinge"]]; k = (ht - hb) / np.linalg.norm(ht - hb)
        su = np.sign(uv[PT[f"stand:{side}BottomHinge"], 0]); own = np.sign(hb[0])
        for C, order in ((Bg, sb), (Tg, st)):
            sel = (np.sign(uv[order, 0]) == su) & (np.abs(uv[order, 0]) > hu)
            w = np.clip((np.abs(uv[order[sel], 0]) - hu) / P.get("ramp", 0.03), 0, 1); w = w * w * (3 - 2 * w) if P.get("ramp") else w
            for sgn in (1, -1):
                R = Rot.from_rotvec(k * np.radians(P["swing0"]) * sgn)
                if (R.apply(X0[PT[f"stand:{side}TopCf"]] - hb)[0] + hb[0] - X0[PT[f"stand:{side}TopCf"], 0]) * own > 0: break
            C[sel] = hb + np.array([Rot.from_rotvec(k * np.radians(P["swing0"]) * sgn * wi).apply(c - hb) for c, wi in zip(C[sel], w)])
x0 = np.r_[Bg[freeB].ravel(), Tg.ravel()]
LB = np.linalg.norm(np.diff(uv[sb], axis=0), axis=1); LT = np.linalg.norm(np.diff(uv[st], axis=0), axis=1)
kb = cKDTree(uv[sb, :1]); XL = [(j, int(kb.query(uv[v, :1])[1])) for j, v in enumerate(st) if j % 4 == 0 or j == nT - 1]
XLL = np.array([np.linalg.norm(uv[st[j]] - uv[sb[i]]) for j, i in XL])
bV = o["bodyV"]; bF = o["bodyF"]; bN = np.zeros_like(bV); fn = np.cross(bV[bF[:, 1]] - bV[bF[:, 0]], bV[bF[:, 2]] - bV[bF[:, 0]])
for k in range(3): np.add.at(bN, bF[:, k], fn)
bN /= np.linalg.norm(bN, axis=1)[:, None]; bkd = cKDTree(bV)
mB = cKDTree(uv[sb] * [-1, 1]).query(uv[sb])[1]; mT = cKDTree(uv[st] * [-1, 1]).query(uv[st])[1]
HARD, BEND, GAPW = P.get("hard", 20.0), P.get("bend", 4.0), P.get("gap_w", 1.0)
ends = [(int(np.argmin(np.abs(uv[st, 0] - uv[PT[k], 0]))), np.sign(X0[PT[h], 0])) for k, h in
        (("stand:leftTopCf", "stand:leftTopHinge"), ("stand:rightTopCf", "stand:rightTopHinge"))]
def ramp(u):
    w = np.clip((np.abs(u) - hu) / 0.03, 0, 1); return w * w * (3 - 2 * w)
FRONT = {False: ramp(uv[sb, 0]), True: ramp(uv[st, 0])}
_cl = [c for c in M["closures"] if c["name"] == "front"][0]["v"][0]; _bt = X0[_cl[0]].copy(); _bt[0] = 0.0
PLACKET = []
for side, bv in (("front.L", _cl[0]), ("front.R", _cl[1])):
    cfn = PT[f"{side}:cfNeck"]; Lp = float(np.linalg.norm(uv[cfn] - uv[bv]))
    ci_ = int(np.argmin(np.linalg.norm(B0 - X0[cfn], axis=1)))
    PLACKET.append((ci_, _bt, Lp))
def res(x):
    B, T = unpack(x); r = []
    r.append(HARD * (np.linalg.norm(np.diff(B, axis=0), axis=1) - LB))
    r.append(HARD * (np.linalg.norm(np.diff(T, axis=0), axis=1) - LT))
    r.append(HARD * (np.array([np.linalg.norm(T[j] - B[i]) for j, i in XL]) - XLL))
    if P.get("rest_shape", True):                                     # bending measured from its own (made, pressed) shape
        for C, C0_ in ((B, B0), (T, T0)):
            k1, k0 = C[2:] - 2 * C[1:-1] + C[:-2], C0_[2:] - 2 * C0_[1:-1] + C0_[:-2]
            relax = 1 - P.get("relax", 0.0) * FRONT[C is T][1:-1]                     # spring: the pressed curve relaxes at the front
            r.append(BEND * (np.linalg.norm(k1, axis=1) - relax * np.linalg.norm(k0, axis=1)))
            tw = np.cross(C[1:-1] - C[:-2], C[2:] - C[1:-1]); tw0 = np.cross(C0_[1:-1] - C0_[:-2], C0_[2:] - C0_[1:-1])
    else:
        r.append(BEND * (B[2:] - 2 * B[1:-1] + B[:-2]).ravel()); r.append(BEND * (T[2:] - 2 * T[1:-1] + T[:-2]).ravel())
    BT = np.array([T[j] - B[i] for j, i in XL]); BT0 = np.array([T0[j] - B0[i] for j, i in XL])
    r.append(P.get("lean_w", 2.0) * (BT[2:] - 2 * BT[1:-1] + BT[:-2]).ravel())   # the band's lean changes smoothly along it
    Q = np.r_[B[freeB], T]; _, j = bkd.query(Q); r.append(5 * np.minimum(np.einsum("ij,ij->i", Q - bV[j], bN[j]) - 0.004, 0))
    r.append((B - B[mB] * [-1, 1, 1]).ravel()); r.append((T - T[mT] * [-1, 1, 1]).ravel())
    for ci_, bpos, Lp in PLACKET: r.append(HARD * np.array([max(np.linalg.norm(B[ci_] - bpos) - Lp, 0.0)]))   # sewn placket: at most its cut
    if P.get("gap"): r.append(np.array([GAPW * (T[j, 0] - s * P["gap"] / 2) for j, s in ends]))
    return np.concatenate(r)
sol = least_squares(res, x0, max_nfev=P.get("nfev", 200), x_scale="jac" if P.get("xs") else 1.0)
B, T = unpack(sol.x)
# lengths are HARD: project the band's links and its lines across back to their cut lengths (the back neckline stays)
for it in range(400):
    worst = 0.0
    for C, L, free_mask in ((B, LB, freeB), (T, LT, np.ones(nT, bool))):
        for i in range(len(L)):
            dv = C[i + 1] - C[i]; l = np.linalg.norm(dv); e = (l - L[i]) / l; worst = max(worst, abs(l - L[i]) / L[i])
            fa, fb = free_mask[i], free_mask[i + 1]
            if fa and fb: C[i] += 0.5 * e * dv; C[i + 1] -= 0.5 * e * dv
            elif fa: C[i] += e * dv
            elif fb: C[i + 1] -= e * dv
    for (j, i), L in zip(XL, XLL):
        dv = B[i] - T[j]; l = np.linalg.norm(dv); e = (l - L) / l; worst = max(worst, abs(l - L) / L)
        if freeB[i]: T[j] += 0.5 * e * dv; B[i] -= 0.5 * e * dv
        else: T[j] += e * dv
    for ci_, bpos, Lp in PLACKET:
        dv = B[ci_] - bpos; l = np.linalg.norm(dv)
        if l > Lp: B[ci_] -= dv * (l - Lp) / l; worst = max(worst, (l - Lp) / Lp)
    if worst < 1e-4: break
print(f"length projection: {it+1} passes, worst link {worst*100:.3f} %")
eb = np.abs(np.linalg.norm(np.diff(B, axis=0), axis=1) / LB - 1).max(); et = np.abs(np.linalg.norm(np.diff(T, axis=0), axis=1) / LT - 1).max()
print(f"{tag}: cost {sol.cost:.2e} nfev {sol.nfev}; worst link neckline {eb*100:.1f} % band top {et*100:.1f} %")
print("  top CF ends x:", [round(T[j, 0] * 1e3, 1) for j, _ in ends], " bottom CF ends x:", [round(B[int(np.argmin(np.abs(uv[sb, 0] - uv[PT[k], 0]))), 0] * 1e3, 1) for k in ("stand:leftBottomCf", "stand:rightBottomCf")])
out = dict(o); out["chains"] = {"band_top": T, "neckline": B}; out["cross"] = [(T[j], B[i]) for j, i in XL]
pickle.dump(out, open(f"{D}{tag}_outline.pkl", "wb"))
