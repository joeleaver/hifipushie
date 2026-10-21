"""openarap.py <from tag> <out tag> '{"open": m, "steps": n, "back": m, "lift": m}': the OPEN state from a closed fit by
STAGED as-rigid-as-possible moves (hifipushie.correctives.arap). Rest = the closed fit's own 3D shape, every sewn pair
welded, so ARAP keeps what the closed fit made (lengths, the collar's fold, the band's curve) and changes only what the
handles force. Held: back, yoke, sleeves, cuffs, and the fronts below the first fastened button. Moved, step by step:
each front's edge above that button, outward by open x w (w: 0 at the button, 1 at the neck) and back by `back` x w.
Free: band, collar, the rest of the fronts. After each step, vertices inside the body are pushed out and held."""
import sys, json, pickle
import numpy as np
from scipy.spatial import cKDTree
from hifipushie.correctives import arap
D = "/mnt/data/hifipushie/shirt_spike/"
src, tag = sys.argv[1], sys.argv[2]; A = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
d = pickle.load(open(f"{D}{src}.pkl", "rb")); X0 = np.asarray(d["A"], float); M = d["mesh"]
F = np.asarray(M["F"]); pid = np.asarray(M["piece"]); nm = list(M["names"]); uv = np.asarray(M["uv"]); P = M["points"]
# weld sewn pairs (union-find)
par = np.arange(len(X0))
def f_(i):
    while par[i] != i: par[i] = par[par[i]]; i = par[i]
    return i
for a, b in np.asarray(M["sew"]).reshape(-1, 2):
    ra, rb = f_(a), f_(b)
    if ra != rb: par[rb] = ra
root = np.array([f_(i) for i in range(len(X0))]); uniq, inv = np.unique(root, return_inverse=True)
W0 = np.zeros((len(uniq), 3)); np.add.at(W0, inv, X0); W0 /= np.bincount(inv)[:, None]
WF = inv[F]; WF = WF[(WF[:, 0] != WF[:, 1]) & (WF[:, 1] != WF[:, 2]) & (WF[:, 0] != WF[:, 2])]
wpid = np.full(len(uniq), -1); wpid[inv] = pid
piece_of = lambda names: np.isin(pid, [nm.index(n) for n in names])
# the first fastened button's height: the highest closed front-closure vertex
fz = [X0[np.asarray(v)].mean(0)[2] for c in M.get("closures") or [] if c.get("name") == "front"
      for v, cl in zip(c.get("v") or [], c.get("closed") or [True] * 99) if cl]
zb = max(fz) if fz else X0[P["front.L:cfNeck"], 2] - 0.05
zn = X0[P["front.L:cfNeck"], 2]
print(f"first fastened button z {zb*1000:.0f}, cfNeck z {zn*1000:.0f} ({(zn-zb)*1000:.0f} mm above)")
held = piece_of(["back", "yoke", "sleeve.L", "sleeve.R", "cuff.L", "cuff.R"]) | (piece_of(["front.L", "front.R"]) & (X0[:, 2] < zb - 0.005))
edgeR = (pid == nm.index("front.R")) & (uv[:, 0] > uv[P["front.R:placketTopOut"], 0] - 0.003) & (X0[:, 2] >= zb - 0.005)
edgeL = (pid == nm.index("front.L")) & (uv[:, 0] < uv[P["front.L:placketTopFold1"], 0] + 0.003) & (X0[:, 2] >= zb - 0.005)
# the band's end edges continue the front edges (Joe's photos): they turn with them
bandR = np.zeros(len(X0), bool); bandL = np.zeros(len(X0), bool)
st_ = pid == nm.index("stand")
for sd, msk in (("left", bandR), ("right", bandL)):  # (stand "left" end is sewn to front.R)
    a_, b_ = X0[P[f"stand:{sd}BottomEdge"]], X0[P[f"stand:{sd}TopCf"]]
    ab = b_ - a_; t = np.clip(((X0 - a_) @ ab) / (ab @ ab), 0, 1); dd = np.linalg.norm(X0 - (a_ + t[:, None] * ab), axis=1)
    msk |= st_ & (dd < 0.003)
edgeR |= bandR; edgeL |= bandL
hW = np.zeros(len(uniq), bool); hW[inv[held]] = True
eW = {s: np.unique(inv[e]) for s, e in (("R", edgeR), ("L", edgeL))}
for s in eW: hW[eW[s]] = True
# body: push-out
BV, BF = d["bodyV"], d["bodyF"]
n_ = np.cross(BV[BF[:, 1]] - BV[BF[:, 0]], BV[BF[:, 2]] - BV[BF[:, 0]]); vn = np.zeros_like(BV)
for k in range(3): np.add.at(vn, BF[:, k], n_)
vn /= np.linalg.norm(vn, axis=1)[:, None] + 1e-12; bt = cKDTree(BV)
def push(Y, gap=0.002, keep=None):
    _, j = bt.query(Y); s = ((Y - BV[j]) * vn[j]).sum(1); bad = s < gap
    if keep is not None: bad &= ~keep
    Y = Y.copy(); Y[bad] += (gap - s[bad])[:, None] * vn[j[bad]]; return Y, bad
OPEN, BACK, STEPS = A.get("open", 0.03), A.get("back", 0.0), A.get("steps", 6)
ROLL = A.get("roll")  # deg: ROLL mode (the edge handles above are not used)
if ROLL is not None:
    hW = np.zeros(len(uniq), bool); hW[inv[held]] = True
    flaps = {}
    for fr in ("front.R", "front.L"):
        k = nm.index(fr); v = np.where(pid == k)[0]
        a = X0[P[f"{fr}:neck"]]  # the side-neck point
        # the first fastened button on this front's edge: the closure vertex of this piece nearest zb
        cv = [int(x) for c in M.get("closures") or [] if c.get("name") == "front" for pr in (c.get("v") or []) for x in pr if pid[int(x)] == k]
        b = X0[min(cv, key=lambda i: abs(X0[i, 2] - zb))] if cv else np.array([X0[P[f"{fr}:cfNeck"], 0], X0[P[f"{fr}:cfNeck"], 1], zb])
        ua, ub = uv[P[f"{fr}:neck"]], uv[min(cv, key=lambda i: abs(X0[i, 2] - zb))] if cv else uv[P[f"{fr}:cfNeck"]] - [0, zn - zb]
        cr = lambda q: (ub[0] - ua[0]) * (q[:, 1] - ua[1]) - (ub[1] - ua[1]) * (q[:, 0] - ua[0])
        side_cf = np.sign(cr(uv[[P[f"{fr}:cfNeck"]]]))[0]
        fl = v[np.sign(cr(uv[v])) == side_cf]
        near = np.abs(cr(uv[v])) / np.linalg.norm(ub - ua) < A.get("hinge", 0.008)
        flaps[fr] = (a, b, np.unique(inv[fl]), np.unique(inv[v[(np.sign(cr(uv[v])) != side_cf) & ~near]]))
        print(fr, "flap verts", len(fl), "roll line from", np.round(a * 1000).astype(int), "to", np.round(b * 1000).astype(int))

Y = W0.copy()
def rodr(p, axis, th):
    axis = axis / np.linalg.norm(axis); K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return p @ (np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K).T
sense = {}
for k in range(1, STEPS + 1):
    f = k / STEPS; T = Y.copy(); fixed = hW.copy()
    if ROLL is not None:
        for fr, (a, b, fl, base) in flaps.items():
            if fr not in sense:  # the sense that turns the corner OFF the body (its cfNeck away from the skin) first
                c0 = W0[inv[P[f"{fr}:cfNeck"]]]
                def sdist(p):
                    _, jj = bt.query(p); return float(((p - BV[jj]) * vn[jj]).sum())
                sense[fr] = max((1, -1), key=lambda q: sdist(a + rodr((c0 - a)[None], b - a, q * 0.3)[0]))
                print(fr, "roll sense", sense[fr])
            th = sense[fr] * np.radians(ROLL) * f
            T[fl] = a + rodr(W0[fl] - a, b - a, th); fixed[fl] = True
            T[base] = W0[base]; fixed[base] = True
    else:
        for s, sg in (("R", -1.0), ("L", 1.0)):
            e = eW[s]; piv = np.array([0.0, W0[e, 1].mean(), zb])
            piv[0] = W0[e][np.argmin(np.abs(W0[e, 2] - zb)), 0]
            th = -sg * np.arctan2(OPEN * f, zn - zb)
            c, s_ = np.cos(th), np.sin(th); R = np.array([[c, 0, -s_], [0, 1, 0], [s_, 0, c]])
            T[e] = piv + (W0[e] - piv) @ R.T
            fixed[e] = True
    Y = arap(W0, WF, T, ~fixed, iters=A.get("iters", 15))
    for _ in range(2):
        Yp, bad = push(Y, keep=fixed)
        if not bad.any(): break
        Y = arap(W0, WF, Yp, ~(fixed | bad), iters=8)
    print(f"step {k}: inside (free cloth) {int(push(Y, keep=fixed)[1].sum())}")
X = Y[inv]
E = np.r_[WF[:, [0, 1]], WF[:, [1, 2]], WF[:, [2, 0]]]
L0 = np.linalg.norm(W0[E[:, 0]] - W0[E[:, 1]], axis=1); L1 = np.linalg.norm(Y[E[:, 0]] - Y[E[:, 1]], axis=1)
ok = L0 > 1e-5; st = np.abs(L1[ok] / L0[ok] - 1)
print(f"edge change vs the closed fit: p99 {np.percentile(st, 99)*100:.1f} %, max {st.max()*100:.0f} %")
out = dict(d); out["A"] = X; out["A_info"] = dict(d["A_info"], openarap=A, folds=d["A_info"].get("folds", []), worn_open_mm=None)
pickle.dump(out, open(f"{D}{tag}.pkl", "wb")); print("saved", tag)
