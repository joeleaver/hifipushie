"""outline.py <tag> [json]: the closed band + collar OUTLINE only, as chains of the pattern's link lengths.
Chains: neckline (band bottom, walked from CB, buttoned on the centre line), band top (= collar seam), collar roll line
(the pattern's fold row), collar outer edge, and the end edges. Held together only by the pattern's own cross lines at
their flat lengths (band: CB, hinge, CF lines; collar: CB line, neck-end -> point edges). Solved: only the bends (as
little bending as the lengths allow) + wear: the collar's edge outside the body. Initial shape: the closed build e9."""
import sys, json, pickle
import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation as Rot
D = "/mnt/data/hifipushie/folds_ab/D/"
TAG_ = sys.argv[1]; Pj = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
sys.argv = ["build2.py", "_closed_for_" + TAG_, json.dumps({"local_lean": False})]
exec(open(D + "build2.py").read())
Xc = X.copy()
def flatlen(o): return np.linalg.norm(np.diff(uv[o], axis=0), axis=1)
def border_path(piece, a, b, avoid):
    lp = border_loop(piece); ia, ib = int(np.where(lp == a)[0][0]), int(np.where(lp == b)[0][0])
    p1 = np.roll(lp, -ia)[: (ib - ia) % len(lp) + 1]; p2 = np.roll(lp, -ib)[: (ia - ib) % len(lp) + 1][::-1]
    return p1 if len(set(p1) & avoid) < len(set(p2) & avoid) else p2
# ---- chains (vertex orders)
neck_c = np.array(sorted(c2s, key=lambda v: uv[v, 0]))                # collar neck edge (sewn to the band top)
roll_rows = [f for f in M["folds"] if f["piece"] == "collar"][0]["rows"]
roll = np.array(sorted([v for v in roll_rows[0] if pc[v] == iC], key=lambda v: uv[v, 0]))
endL = border_path(iC, PT["collar:leftBottomEdge"], PT["collar:leftTopEdge"], set(outer) | set(neck_c))
endR = border_path(iC, PT["collar:rightBottomEdge"], PT["collar:rightTopEdge"], set(outer) | set(neck_c))
chains = {"band_top": st_top, "roll": roll, "outer": outer, "endL": endL, "endR": endR}
# neckline: chain from CB at the band bottom's flat links, buttoned on the centre line (as chain.py)
Lb = flatlen(sb); mid = int(np.argmin(np.abs(uv[sb, 0])))
from scipy.ndimage import gaussian_filter1d
Bs = gaussian_filter1d(B, Pj.get("neck_smooth", 10), axis=0, mode="nearest")    # the neckline is a smooth curve (~2 cm)
dirs = unit(np.diff(Bs, axis=0))
def walk(d_):
    C = np.zeros((len(sb), 3)); C[mid] = B[mid]
    for k in range(mid, len(sb) - 1): C[k + 1] = C[k] + d_[k] * Lb[k]
    for k in range(mid - 1, -1, -1): C[k] = C[k + 1] - d_[k] * Lb[k]
    return C
for cfkey in ("stand:rightBottomCf", "stand:leftBottomCf"):
    cf = int(np.argmin(np.abs(uv[sb, 0] - uv[PT[cfkey], 0]))); step = 1 if cf > mid else -1
    rng = np.arange(mid, cf, step); w = np.linspace(0, 1, len(rng)); tgt = np.array([0, B[cf, 1], B[cf, 2]])
    def bent0(om):
        d2 = dirs.copy()
        for kk, k in enumerate(rng): kk_ = k if step > 0 else k - 1; d2[kk_] = Rot.from_rotvec(om * w[kk]).apply(dirs[kk_])
        for k in (np.arange(cf, len(sb) - 1) if step > 0 else np.arange(0, cf)): d2[k] = Rot.from_rotvec(om).apply(dirs[k])
        return d2
    s0 = least_squares(lambda om: np.r_[(walk(bent0(om))[cf] - tgt) * [10, 1, 1], om * 0.01], np.zeros(3)); dd_ = bent0(s0.x)
    if step > 0: dirs[mid:] = dd_[mid:]
    else: dirs[:mid] = dd_[:mid]
C0 = walk(dirs); fixed = {v: C0[j] for j, v in enumerate(sb)}
OPEN_ = Pj.get("open", False)
if OPEN_:
    hu = abs(uv[PT["stand:rightBottomHinge"], 0])
    for j, v in enumerate(sb):
        if abs(uv[v, 0]) > hu: del fixed[v]                              # unbuttoned: free in front of the side necks
    chains["neckline"] = sb
    btn = [c for c in M["closures"] if c["name"] == "front"][0]["v"][0]   # first fastened button: the fronts stay closed there
    Vb = Xc[btn[0]].copy(); Vb[0] = 0.0; fixed[-1] = Vb
    PLK = []
    for fname, bv in (("front.L", btn[0]), ("front.R", btn[1])):        # the placket edge: button -> neck corner (pattern line)
        Lp = np.linalg.norm(uv[PT[f"{fname}:cfNeck"]] - uv[bv])
        corner = s2b_inv = None
        cands = [v for v in sb if s2b[v] == PT[f"{fname}:cfNeck"]] or [sb[int(np.argmin(np.linalg.norm(Xc[sb] - Xc[PT[f"{fname}:cfNeck"]], axis=1)))]]
        PLK.append((cands[0], Lp))
    print("open: placket edges", [round(L * 1e3, 1) for _, L in PLK], "mm from the button to the neck corner")
# ---- unknowns: every chain vertex not on the neckline; the collar neck edge is the band top (sewn)
alias = {v: c2s[v] for v in neck_c}                                    # collar neck vertex -> band top vertex
def key(v): return alias.get(v, v)
if Pj.get("band_from"):                                                 # the band is already solved (stiff, open): hold it
    bo = pickle.load(open(f"{D}{Pj['band_from']}_outline.pkl", "rb")); Bn, Tn_ = bo["chains"]["neckline"], bo["chains"]["band_top"]
    Bold = np.array([fixed[v] for v in sb]); Told = Xc[st_top].copy()
    for j, v in enumerate(sb): fixed[v] = Bn[j]
    for j, v in enumerate(st_top): fixed[v] = Tn_[j]
    C0 = Bn
    # starting guess for the collar: each vertex follows the band near it (local rigid fit, Kabsch)
    ci_all = np.where(pc == iC)[0]; kt = cKDTree(uv[st_top, :1])
    for v in ci_all:
        j = int(kt.query(uv[v, :1])[1]); lo_, hi_ = max(j - 8, 0), min(j + 9, len(st_top))
        jb = [int(np.argmin(np.abs(uv[sb, 0] - uv[st_top[jj], 0]))) for jj in range(lo_, hi_)]
        A_ = np.r_[Told[lo_:hi_], Bold[jb]]; B_ = np.r_[Tn_[lo_:hi_], Bn[jb]]
        ca, cb_ = A_.mean(0), B_.mean(0); H = (A_ - ca).T @ (B_ - cb_); U_, S_, Vt = np.linalg.svd(H)
        R_ = Vt.T @ U_.T
        if np.linalg.det(R_) < 0: Vt[-1] *= -1; R_ = Vt.T @ U_.T
        Xc[v] = R_ @ (Xc[v] - ca) + cb_
hu_ = abs(uv[PT["stand:rightBottomHinge"], 0])
def _fw(o):                                                           # past the side neck the stiff edges run straight
    if o is chains.get("neckline"): return 1.0
    u = np.abs(uv[o[1:-1], 0]); w = np.clip((u - hu_ * 0.9) / 0.03, 0, 1); return Pj.get("edge_stiff", 1.0) * (1 + (Pj.get("front_stiff", 1.0) - 1) * w * w * (3 - 2 * w))
FRONTW = {k_: _fw(o) for k_, o in chains.items() if k_ in ("outer", "roll")}
free = sorted({key(v) for o in chains.values() for v in o} - set(fixed))
ix = {v: i for i, v in enumerate(free)}; n = len(free)
x0 = np.concatenate([Xc[v] for v in free])
def pos(xv, v):
    v = key(v); return fixed[v] if v in fixed else xv[3 * ix[v]: 3 * ix[v] + 3]
# ---- constraints
links = []                                                             # (a, b, flat length, weight)
for nmc, o in list(chains.items()) + [("neckline_end", np.array([]))]:
    for a, b in zip(o[:-1], o[1:]): links.append((a, b, np.linalg.norm(uv[a] - uv[b]), "exact"))
cross_pairs = [("stand:bottomMid", "stand:topMid"), ("stand:leftBottomHinge", "stand:leftTopHinge"), ("stand:rightBottomHinge", "stand:rightTopHinge"),
               ("stand:leftBottomCf", "stand:leftTopCf"), ("stand:rightBottomCf", "stand:rightTopCf"), ("collar:bottomMid", "collar:topMid")]
cross_pairs = [(PT[a], PT[b]) for a, b in cross_pairs]
if OPEN_:
    if Pj.get("placket_tie", False):
        for cv, Lp in PLK: links.append((cv, -1, Lp, "atmost"))
mr = roll[int(np.argmin(np.abs(uv[roll, 0])))]; cross_pairs += [(PT["collar:bottomMid"], mr), (mr, PT["collar:topMid"])]
for endc, corner in ((endL, PT["collar:leftTopEdge"]), (endR, PT["collar:rightTopEdge"])):   # each point keeps its cut corner
    oc = int(np.where(outer == corner)[0][0])
    for k in (3, 6, 10, 15):
        a_ = endc[max(len(endc) - 1 - k, 0)]; b_ = outer[min(max(oc + (k if oc == 0 else -k), 0), len(outer) - 1)]
        cross_pairs.append((a_, b_))
RIGID = set()
for endc in (endL, endR):                                                  # the roll line ends on the end edge
    re_ = roll[int(np.argmin(np.min(np.linalg.norm(uv[roll][:, None] - uv[endc][None], axis=2), axis=1)))]
    for ev in endc[np.linalg.norm(uv[endc] - uv[re_], axis=1) < Pj.get("roll_tie", 0.012)]:
        cross_pairs.append((re_, ev)); RIGID.add((re_, ev))
kn, ko = cKDTree(uv[neck_c]), cKDTree(uv[outer])                    # the collar's width all along: seam -> roll -> edge
tr = tangent(uv[roll])
def across(rv_i, other):                                                 # the vertex of `other` straight across (flat)
    rv = roll[rv_i]; nrm2 = np.array([-tr[rv_i, 1], tr[rv_i, 0]]); dv = uv[other] - uv[rv]
    off_line = np.abs(dv @ tr[rv_i]); return other[int(np.argmin(off_line + 0.0 * np.abs(dv @ nrm2)))]
for i_ in range(0, len(roll), Pj.get("every", 15)):
    cross_pairs.append((across(i_, neck_c), roll[i_])); cross_pairs.append((roll[i_], across(i_, outer)))
for endc, corner in ((endL, PT["collar:leftTopEdge"]), (endR, PT["collar:rightTopEdge"])):   # the point's triangle: rigid
    oc = int(np.where(outer == corner)[0][0]); near_o = outer[np.linalg.norm(uv[outer] - uv[corner], axis=1) < Pj.get("rigid", 0.03)]
    near_e = endc[np.linalg.norm(uv[endc] - uv[corner], axis=1) < Pj.get("rigid", 0.03)]
    pts = np.unique(np.r_[near_o[::3], near_e[::3], corner])
    for i_ in range(len(pts)):
        for j_ in range(i_ + 1, len(pts)): cross_pairs.append((pts[i_], pts[j_])); RIGID.add((pts[i_], pts[j_]))
n_exact = 5                                                              # the band's CB / hinge / CF lines
links_exact_idx = set()
for k_, (a, b) in enumerate(cross_pairs):
    kind = "exact" if (k_ < n_exact or (a, b) in RIGID) else "atmost"
    if kind == "atmost" and Pj.get("back_full") and min(Xc[a, 1], Xc[b, 1]) > d["at"]["hps.L"][1] - 0.01 and pc[a] == iC and pc[b] == iC:
        kind = "exact"                                                   # at the back the fall lies flat on the band: full width
    links.append((a, b, np.linalg.norm(uv[a] - uv[b]), kind))
bend_w = Pj.get("bend", 0.02); HARD = Pj.get("hard", 20.0)   # pattern lengths are hard
bV = d["bodyV"]; bF = d["bodyF"]; bN = np.zeros_like(bV); fnb = np.cross(bV[bF[:, 1]] - bV[bF[:, 0]], bV[bF[:, 2]] - bV[bF[:, 0]])
for kk in range(3): np.add.at(bN, bF[:, kk], fnb)
bN = unit(bN + 1e-12); bkd = cKDTree(bV); off = Pj.get("off", 0.006)
outside = [v for v in outer] + [v for v in roll] + ([v for v in sb if v not in fixed] if OPEN_ else [])
if OPEN_:
    zc = Xc[st_top[len(st_top) // 2], 2]; nb = bV[(np.abs(bV[:, 2] - (zc - 0.02)) < 0.004) & (np.abs(bV[:, 0]) < 0.1) & (bV[:, 1] > -0.12) & (bV[:, 1] < 0.06)]
    neckW = 2 * np.abs(nb[:, 0]).max(); PT_X = Pj.get("spread", 1.7) * neckW / 2
    print(f"open: neck width {neckW*1e3:.0f} mm -> points {2*PT_X*1e3:.0f} mm apart (photo: 1.7 neck widths)")
_, jc = bkd.query(C0); sdC0 = np.einsum("ij,ij->i", C0 - bV[jc], bN[jc])          # how far the neckline stands off the body
hpsy = d["at"]["hps.L"][1]
LIE = [v for v in outer if Xc[v, 1] > hpsy - 0.01] if (Pj.get("pt_back") is not None or Pj.get("band_from")) else list(outer)
ang_ = lambda P_: np.arctan2(P_[..., 0], P_[..., 1] - yax)
kc = cKDTree(np.c_[np.cos(ang_(C0)), np.sin(ang_(C0))])
shv = np.where(np.isin(pc, [nm.index("front.L"), nm.index("front.R"), nm.index("yoke"), nm.index("back")]))[0]; ksh = cKDTree(Xc[shv])
_, jsh = bkd.query(Xc[shv]); sdsh = np.einsum("ij,ij->i", Xc[shv] - bV[jsh], bN[jsh])          # how far the shirt stands off the body
def lie_t(v):
    if Xc[v, 1] > hpsy - 0.01: return sdC0[kc.query([np.cos(ang_(Xc[v])), np.sin(ang_(Xc[v]))])[1]] + Pj.get("layers", 0.004)
    return sdsh[ksh.query(Xc[v])[1]] + Pj.get("layers", 0.004)                  # the leaves rest on the shirt front
LIE_T = np.array([lie_t(v) for v in LIE])
def res(xv):
    r_ = []
    for a, b, L, kind in links:
        e_ = np.linalg.norm(pos(xv, a) - pos(xv, b)) - L; r_.append(HARD * (e_ if kind == "exact" else max(e_, 0.0)))
    for nmc_, o in chains.items():                                   # bend as little as the lengths allow; the collar is interfaced
        bw = bend_w * (Pj.get("stiff", 3.0) if nmc_ in ("outer", "roll", "endL", "endR", "band_top", "neckline") else 1.0)
        P_ = np.array([pos(xv, v) for v in o]); fw = FRONTW.get(nmc_, 1.0)
        r_.extend(((bw * fw)[:, None] * (P_[2:] - 2 * P_[1:-1] + P_[:-2]) if np.ndim(fw) else bw * (P_[2:] - 2 * P_[1:-1] + P_[:-2])).ravel())
    P_ = np.array([pos(xv, v) for v in outside]); _, j = bkd.query(P_); sd = np.einsum("ij,ij->i", P_ - bV[j], bN[j])
    r_.extend(np.minimum(sd - off, 0) * 5)
    Po = np.array([pos(xv, v) for v in LIE]); _, j2 = bkd.query(Po); sd2 = np.einsum("ij,ij->i", Po - bV[j2], bN[j2])
    r_.extend(np.minimum(sd2 - LIE_T, 0) * 5)                          # it can't sink into the band / yoke ...
    r_.extend((sd2 - LIE_T) * Pj.get("rest", 0.3))                     # ... and rests down on them (bridges the hollows)
    if Pj.get("pt_back") is not None:                                  # reference: the point relative to the leaf's front top
        for endc in (endL, endR):
            p0, p1 = pos(xv, endc[0]), pos(xv, endc[-1])
            r_ += [(p1[1] - p0[1] - Pj["pt_back"]) * 5, (p0[2] - p1[2] - Pj["pt_down"]) * 5]
    if OPEN_:
        cbz = pos(xv, mr)[2]                                             # the roll at the centre back
        for endc in (endL, endR):
            p1 = pos(xv, endc[-1]); r_ += [(abs(p1[0]) - PT_X) * Pj.get("pt_w", 3.0), (cbz - p1[2] - Pj.get("pt_down", 0.107)) * Pj.get("pt_w", 3.0) / 3]
    if OPEN_ and Pj.get("band_gap"):                                   # style: the band ends part this far
        for k_, hk in (("stand:leftTopCf", "stand:leftTopHinge"), ("stand:rightTopCf", "stand:rightTopHinge")):
            own = np.sign(Xc[PT[hk], 0])                                # each end goes to its own side (they cross when buttoned)
            r_.append((pos(xv, PT[k_])[0] - own * Pj["band_gap"] / 2) * Pj.get("gap_w", 0.5))
    for bt, bb in ORI_BAND:
        pt_, pb_ = pos(xv, bt), pos(xv, bb); r_.append(min(pt_[2] - pb_[2] - 0.012, 0) * 10)
    for ro, ou in ORI_COL:
        pr, po = pos(xv, ro), pos(xv, ou)
        rr = np.hypot(pr[0], pr[1] - yax); ro_ = np.hypot(po[0], po[1] - yax); r_.append(min(ro_ - rr - 0.002, 0) * 10)
    A_ = xv.reshape(-1, 3); r_.extend(((A_[MA] - A_[MB] * [-1, 1, 1]) * Pj.get("sym", 1.0)).ravel())   # worn straight
    return np.array(r_)
kb = cKDTree(uv[sb, :1]); ORI_BAND = [(v, sb[kb.query(uv[v, :1])[1]]) for v in st_top[::6]]
ORI_COL = [(a_, b_) for a_, b_ in cross_pairs if a_ in set(roll) and b_ in set(outer)]
fv_ = np.array(free); posv = fv_[uv[fv_, 0] > 0.002]; negv = fv_[uv[fv_, 0] < -0.002]
mj = cKDTree(uv[negv] * [-1, 1]).query(uv[posv])[1]
MA = np.array([ix[v] for v in posv]); MB = np.array([ix[negv[j]] for j in mj])
# sparsity: which unknowns each residual touches (same order as res)
rows = []
def vars_of(*vs): return [3 * ix[key(v)] + c for v in vs if key(v) in ix for c in range(3)]
for a_, b_, L, w_ in links: rows.append(vars_of(a_, b_))
for o in chains.values():
    for i_ in range(len(o) - 2):
        vv = vars_of(o[i_], o[i_ + 1], o[i_ + 2]); rows += [vv] * 3
for v in outside: rows.append(vars_of(v))
for v in LIE: rows.append(vars_of(v))
for v in LIE: rows.append(vars_of(v))
if OPEN_ and Pj.get("band_gap"):
    for k_ in ("stand:leftTopCf", "stand:rightTopCf"): rows.append(vars_of(PT[k_]))
for bt, bb in ORI_BAND: rows.append(vars_of(bt, bb))
for ro, ou in ORI_COL: rows.append(vars_of(ro, ou))
if OPEN_:
    for endc in (endL, endR): rows += [vars_of(endc[-1], mr)] * 2
if Pj.get("pt_back") is not None:
    for endc in (endL, endR): rows += [vars_of(endc[0], endc[-1])] * 2
for ia, ib in zip(MA, MB):
    for c in range(3): rows.append([3 * ia + c, 3 * ib + c])
J = lil_matrix((len(rows), n * 3))
for r_i, vv in enumerate(rows):
    for c in vv: J[r_i, c] = 1
assert len(rows) == len(res(x0)), (len(rows), len(res(x0)))
sol = least_squares(res, x0, jac_sparsity=J, max_nfev=Pj.get("nfev", 80), verbose=0)
xv = sol.x
for nmc, o in chains.items():
    P_ = np.array([pos(xv, v) for v in o]); L3 = arclen(P_)[-1]; Lf = flatlen(o).sum()
    print(f"{nmc:9s}: {L3*1e3:6.1f} mm vs cut {Lf*1e3:6.1f}  (worst link {np.abs(np.linalg.norm(np.diff(P_,axis=0),axis=1)/flatlen(o)-1).max()*100:.1f} %)")
for a, b in cross_pairs:
    print(f"  cross {[k for k,v in PT.items() if v==a][:1] or a} -> {[k for k,v in PT.items() if v==b][:1] or b}: {np.linalg.norm(pos(xv,a)-pos(xv,b))*1e3:.1f} vs {np.linalg.norm(uv[a]-uv[b])*1e3:.1f} mm")
XO = Xc.copy()
for j, v in enumerate(sb): XO[v] = C0[j]
for o in chains.values():
    for v in o: XO[v] = pos(xv, v)
for v in neck_c: XO[v] = pos(xv, v)
out = {"C0": C0, "chains": {k: np.array([pos(xv, v) for v in o]) for k, o in chains.items()},
       "orders": {**{k: o for k, o in chains.items()}, "neckline": sb, "neck_c": neck_c}, "X": XO, "mesh": M, "at": d["at"],
       "cross": [(pos(xv, a), pos(xv, b)) for a, b in cross_pairs], "bodyV": d["bodyV"], "bodyF": d["bodyF"]}
pickle.dump(out, open(f"{D}{TAG_}_outline.pkl", "wb")); print("saved", TAG_)
