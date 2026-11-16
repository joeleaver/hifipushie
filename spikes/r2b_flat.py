"""R2b steps 5-6 (R2's spikes/r2_flat.py; R2b: the sleeves come off along the armhole CONE, r2b_common.Cone, and the
armhole / cap lengths are read where body and sleeve share their cut): mark, cut, flatten, unfold, true, compare.

  slot uv run python spikes/r2b_flat.py <toile dir> <loaded.pkl> <jacket.json> <d4 lines.json>

CUT, every line an exact clip by a scalar (no edge paths): sleeves off along the armhole's plane (R1); the body by D4's
marks as scalars: front / side by front_side's angle round the torso axis (D4's line moved out horizontally keeps its
angle), side / back by side_back's, above the underarm front / back by the shoulder line (y of D4's shoulder at x);
the sleeve by a TAILOR'S RULE, not D4's split: the under sleeve's seams set in from the arm's front line by 30 mm and
from its back line by 20 mm (arc on the tube), so the top sleeve is the rest (~60-65 % at the biceps).
Each piece must be ONE region: a mark that does not separate a piece is REFUSED (r2_common.one_piece), not mirrored.
FLATTEN: LSCM + ARAP per piece; strain max(s1 - 1, 1 - s2).
UNFOLD: the lapel (flattened alone, facing side out) is reflected about the roll line onto the forepart's flat
(Procrustes with reflection on the shared roll edge): the forepart with its lapel cut on. The collar (stand + fall
joined along the roll line) flattens in one piece: a folded strip is intrinsically flat, so flattening unfolds it.
COMPARE with s4-31: outlines at one scale, widths at chest / waist / hips, seams, cap ease, collar and lapel.
Writes <dir>/flat.json, flat.npz, flat_sheet.png, cut_sheet.png."""
import json
import os
import pickle
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(__file__))
from r1_common import PAL, clip, render, sheet  # noqa: E402
from r2_common import Refused, areas, boundary_edges, flatten, one_piece, strain  # noqa: E402
from r2b_common import Cone  # noqa: E402

tdir, src, jpath, lpath = sys.argv[1:5]
Z = np.load(os.path.join(tdir, "toile.npz"))
V, F = Z["V"], Z["F"]
ca, na, sh, A, alen, yc = Z["ca"], Z["na"], Z["sh"], Z["A"], float(Z["alen"]), float(Z["yc"])
CAX, RAX, tax = Z["CAX"], Z["RAX"], Z["tax"]
LAP = float(Z["lap"])
CONE = Cone.load(Z)


def armcut(P):
    """> 0 on the sleeve side: inside the armhole cone (r2b_common) and near the arm."""
    t = np.clip((P - sh) @ A, 0, alen)
    return np.minimum(CONE.sdist(P), 0.11 - np.linalg.norm(P - (sh + t[:, None] * A), axis=1))
steps = json.load(open(jpath))["steps"]
fit = steps["0"]["output"]["fit"]
LN = json.load(open(lpath))
L = LN["lines"]
MIR = np.array([-1.0, 1, 1])
log = lambda m: print(m, flush=True)
REP = {"refused": []}

# ---------- sleeves off along the armhole's plane (R1)
AH = np.asarray(L["armhole.L"]["pts"])
e1 = np.cross(na, [0, 0, 1.0])
e1 /= np.linalg.norm(e1)
e2 = np.cross(na, e1)
_d = AH - ca
_psi = np.arctan2(_d @ e2, _d @ e1)
_o = np.argsort(_psi)
PSI, RAD = _psi[_o], np.linalg.norm(_d - np.outer(_d @ na, na), axis=1)[_o]


def arm_plane(P, margin=0.035):
    d = P - ca
    s = d @ na
    r = np.linalg.norm(d - np.outer(s, na), axis=1)
    R = np.interp(np.arctan2(d @ e2, d @ e1), PSI, RAD, period=2 * np.pi)
    t = np.clip((P - sh) @ A, 0, alen)
    dax = np.linalg.norm(P - (sh + t[:, None] * A), axis=1)
    return s, np.maximum(R + margin - r, np.minimum(s - 0.06, 0.11 - dax))


def weld(parts, tol=1e-7):
    """Meshes joined where their vertices coincide (exact clips put shared cut vertices at equal positions)."""
    Vc = np.concatenate([p[0] for p in parts])
    off = np.cumsum([0] + [len(p[0]) for p in parts])[:-1]
    Fc = np.concatenate([p[1] + o for p, o in zip(parts, off)])
    _, first, inv = np.unique(np.round(Vc / tol).astype(np.int64), axis=0, return_index=True, return_inverse=True)
    return Vc[first], inv.ravel()[Fc]


# R1's armhole cut (the plane AND within the loop's radius + 35 mm) bit an island out of the side body under the arm
# and a hole into the under sleeve (the tube's web lies outside that radius). Now: the plane alone cuts; of what lies
# past it, the sleeve is the region that reaches the wrist; anything else past the plane stays with the body.
from r1_common import face_components  # noqa: E402

pl = armcut(V)
Vp_, Fp_ = clip(V, F, pl)
lab = face_components(Fp_, len(Vp_))
tip = Fp_[:, 0][np.argmin(np.linalg.norm(Vp_[Fp_[:, 0]] - CAX[-1], axis=1))]  # the face nearest the wrist's axis end
sl = lab == lab[np.argmax(Fp_[:, 0] == tip)]
Vs, Fs = Vp_, Fp_[sl]
Vt, Ft = weld([clip(V, F, -pl), (Vp_, Fp_[~sl])])
REP_ARM = {"past_plane_regions": int(lab.max() + 1), "returned_to_body_cm2": round(float(areas(Vp_, Fp_[~sl]).sum() * 1e4), 1)}
print(f"armhole cut: {REP_ARM}", flush=True)


# ---------- body marks as scalars
def theta(P):
    return np.arctan2(np.abs(P[:, 0]), -(P[:, 1] - yc))


def by_z(name):
    P = np.asarray(L[name]["pts"], float)
    o = np.argsort(P[:, 2])
    return P[o, 2], theta(P[o]), P[o, 2].max()


zf, tf, topf = by_z("front_side.L")
zb, tb, topb = by_z("side_back.L")
z_top = max(topf, topb)
SH = np.asarray(L["shoulder.L"]["pts"], float)
o = np.argsort(SH[:, 0])
y_sh = lambda x: np.interp(x, SH[o, 0], SH[o, 1])


def g_front(P):
    return np.where(P[:, 2] <= z_top, np.interp(P[:, 2], zf, tf) - theta(P), 5 * (y_sh(P[:, 0]) - P[:, 1]))


def g_back(P):
    return np.where(P[:, 2] <= z_top, theta(P) - np.interp(P[:, 2], zb, tb), 5 * (P[:, 1] - y_sh(P[:, 0])))


def cut(V, F, phis):
    for ph in phis:
        V, F = clip(V, F, ph(V))
    return V, F


PIECES = {}


def piece(name, V, F, by):
    try:
        PIECES[name] = one_piece(V, F, name, by)
    except Refused as e:
        REP["refused"].append(str(e))
        log(f"REFUSED {e}")


piece("front.L", *cut(Vt, Ft, [g_front]), ["front_side.L", "shoulder.L", "armhole.L"])
piece("side.L", *cut(Vt, Ft, [lambda P: -g_front(P), lambda P: -g_back(P)]), ["front_side.L", "side_back.L", "armhole.L"])
piece("back.L", *cut(Vt, Ft, [g_back]), ["side_back.L", "shoulder.L", "armhole.L", "centre_back"])
tot = areas(Vt, Ft).sum()
got = sum(areas(*PIECES[p]).sum() for p in ("front.L", "side.L", "back.L") if p in PIECES)
REP["body_partition"] = {"toile_cm2": round(tot * 1e4, 1), "pieces_cm2": round(got * 1e4, 1)}
log(f"body partition {REP['body_partition']}")


# ---------- sleeve: the tailor's split on the tube
def axis_foot(P):
    best = np.full(len(P), np.inf)
    out = np.zeros((len(P), 3))
    rr = np.zeros(len(P))
    dd = np.zeros((len(P), 3))
    for j in range(len(CAX) - 1):
        dv = CAX[j + 1] - CAX[j]
        u = np.clip(((P - CAX[j]) @ dv) / (dv @ dv), 0, 1)
        q = CAX[j] + u[:, None] * dv
        dist = np.linalg.norm(P - q, axis=1)
        b = dist < best
        best = np.where(b, dist, best)
        out[b] = q[b]
        rr = np.where(b, RAX[j] + u * (RAX[j + 1] - RAX[j]), rr)
        dd[b] = dv / np.linalg.norm(dv)
    return out, rr, dd


# the under sleeve's seams set in from the arm's front / back lines (arc, m): the fore seam ~2.5 cm behind the front
# crease (hidden from the front), the hind seam ~2 cm in from the back line: top = 1/2 + 50 mm / round (~63 % at the
# biceps). (A 69 % read in an earlier try was the old armhole cut's hole in the under sleeve, not the rule.)
FORE_IN, HIND_IN = 0.030, 0.020


def phi_arm(P):
    """0 under the arm (toward the body), +pi/2 its front line, -pi/2 its back line."""
    q, r, d = axis_foot(P)
    f0 = np.array([0, -1.0, 0]) - np.outer(d @ [0, -1.0, 0], np.ones(3)) * d
    f0 /= np.linalg.norm(f0, axis=1, keepdims=True)
    u0 = np.cross(d, f0)
    u0 *= np.sign(u0 @ [-1.0, 0, -1.0])[:, None]
    w = P - q
    return np.arctan2(np.einsum("ij,ij->i", w, f0), np.einsum("ij,ij->i", w, u0)), r


def g_under(P):
    ph, r = phi_arm(P)
    return np.minimum((np.pi / 2 - FORE_IN / r) - ph, ph + (np.pi / 2 - HIND_IN / r))


piece("sleeve_top.L", *cut(Vs, Fs, [lambda P: -g_under(P)]), ["the top / under sleeve rule (30 / 20 mm in)", "armhole.L"])
piece("sleeve_under.L", *cut(Vs, Fs, [g_under]), ["the top / under sleeve rule (30 / 20 mm in)", "armhole.L"])
# D4's split judged against the rule: where its fore / hind lines sit round the biceps
kb = int(np.argmin(np.abs(tax - 0.30 * alen)))
Cb, db = CAX[kb], (CAX[kb + 1] - CAX[kb]) / np.linalg.norm(CAX[kb + 1] - CAX[kb])


def round_share(lines):
    out = {}
    for nm in lines:
        P = np.asarray(L[nm]["pts"], float)
        k = int(np.argmin(np.abs((P - Cb) @ db)))
        out[nm] = float(phi_arm(P[k:k + 1])[0][0])
    return out


d4phi = round_share(["sleeve_fore.L", "sleeve_hind.L"])
d4_top = 1 - (d4phi["sleeve_fore.L"] - d4phi["sleeve_hind.L"]) / (2 * np.pi)


def level_len(Vp, Fp, U, s):
    tot = 0.0
    for tri in Fp[(np.sign(s[Fp]).min(1) < 0) & (np.sign(s[Fp]).max(1) > 0)]:
        q = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            a, b = tri[i], tri[j]
            if (s[a] < 0) != (s[b] < 0):
                t = s[a] / (s[a] - s[b])
                q.append(U[a] + t * (U[b] - U[a]))
        if len(q) == 2:
            tot += np.linalg.norm(q[0] - q[1])
    return tot * 1000


sl_round = {p: level_len(*PIECES[p], PIECES[p][0], (PIECES[p][0] - Cb) @ db) for p in ("sleeve_top.L", "sleeve_under.L") if p in PIECES}
REP["sleeve_split"] = {"rule": "under sleeve seams 30 mm in from the arm's front line, 20 mm in from its back line",
                       "biceps_round_mm": {k: round(v, 1) for k, v in sl_round.items()},
                       "top_share": round(sl_round.get("sleeve_top.L", 0) / max(sum(sl_round.values()), 1e-9), 3),
                       "d4_top_share_at_biceps": round(float(d4_top), 3)}
log(f"sleeve split {REP['sleeve_split']}")

# ---------- the lapel and the collar
Vl, Vl0, Fl = Z["Vl"], Z["Vl0"], Z["Fl"]
PIECES["lapel.L"] = (Vl, Fl)
PIECES["undercollar"] = (Z["Vu"], Z["Fu"])
PIECES["collar"] = (Z["Vtop"], Z["Fu"])

# ---------- flatten
FL, report = {}, {}
for nm, (Vp, Fp) in PIECES.items():
    U, S, Fp = flatten(Vp, Fp)
    bad = strain(S)
    ar = areas(Vp, Fp)
    worst = np.argsort(-bad)[: max(1, len(bad) // 50)]
    Cw = Vp[Fp[worst]].mean(1)
    report[nm] = {"faces": int(len(Fp)), "area_cm2": round(ar.sum() * 1e4, 1),
                  "strain_mean_pct": round(float((bad * ar).sum() / ar.sum() * 100), 2),
                  "area_over_2pct": round(float(ar[bad > 0.02].sum() / ar.sum() * 100), 1),
                  "area_over_5pct": round(float(ar[bad > 0.05].sum() / ar.sum() * 100), 1),
                  "stretch_max_pct": round(float((S[:, 0] - 1).max() * 100), 1), "compress_max_pct": round(float((1 - S[:, 1]).max() * 100), 1),
                  "worst_2pct_at": np.round(Cw.mean(0), 3).tolist(),
                  "worst_kind": "compression (dart)" if (1 - S[worst, 1]).mean() > (S[worst, 0] - 1).mean() else "stretch (ease)"}
    FL[nm] = {"V": Vp, "F": Fp, "U": U, "bad": bad}
    log(f"{nm}: {report[nm]}")


# ---------- unfold the lapel about the roll line onto the forepart
def roll_edge(Vp, Fp, U, Vref):
    B = np.unique(boundary_edges(Fp))
    x_r = np.interp(Vref[B, 2], Z["roll_z"], Z["roll_x"])
    m = (np.abs(Vref[B, 0] - x_r) < 2e-4) & (Vref[B, 2] > Z["z_brk"] + 0.003) & (Vref[B, 2] < Z["z_top"] - 0.003)
    B = B[m]
    o = np.argsort(Vref[B, 2])
    return Vref[B[o], 2], U[B[o]]


if "front.L" in FL:
    zf_, uf = roll_edge(None, FL["front.L"]["F"], FL["front.L"]["U"], PIECES["front.L"][0])
    zl_, ul = roll_edge(None, Fl, FL["lapel.L"]["U"], Vl0)
    zz = np.linspace(max(zf_.min(), zl_.min()), min(zf_.max(), zl_.max()), 40)
    Pf = np.c_[np.interp(zz, zf_, uf[:, 0]), np.interp(zz, zf_, uf[:, 1])]
    Pl = np.c_[np.interp(zz, zl_, ul[:, 0]), np.interp(zz, zl_, ul[:, 1])]
    fits = {}
    for refl in (False, True):
        Q = Pl * ([-1, 1] if refl else [1, 1])
        mq, mf = Q.mean(0), Pf.mean(0)
        Uu, _, Wt = np.linalg.svd((Q - mq).T @ (Pf - mf))
        Rm = Uu @ Wt
        if np.linalg.det(Rm) < 0:
            Uu[:, -1] *= -1
            Rm = Uu @ Wt
        tf_ = lambda X, Rm=Rm, mq=mq, mf=mf, refl=refl: (X * ([-1, 1] if refl else [1, 1]) - mq) @ Rm + mf
        res = np.linalg.norm(tf_(Pl) - Pf, axis=1)
        # the lapel must land OUTSIDE the forepart (across the roll line), not on it
        cl = tf_(FL["lapel.L"]["U"]).mean(0)
        cf_ = FL["front.L"]["U"].mean(0)
        tdir_ = Pf[-1] - Pf[0]
        nrm = np.array([-tdir_[1], tdir_[0]])
        across = np.sign((cl - Pf.mean(0)) @ nrm) != np.sign((cf_ - Pf.mean(0)) @ nrm)
        fits[refl] = (res.mean(), res.max(), across, tf_)
    refl = True
    FL["lapel.L"]["U2"] = fits[refl][3](FL["lapel.L"]["U"])
    REP["lapel_unfold"] = {"reflected": True, "hinge_mean_mm": round(fits[True][0] * 1000, 2), "hinge_max_mm": round(fits[True][1] * 1000, 2),
                           "lands_across_roll_line": bool(fits[True][2]), "unreflected_hinge_mean_mm": round(fits[False][0] * 1000, 2),
                           "roll_edge_flat_mm": {"front": round(float(np.linalg.norm(np.diff(uf, axis=0), axis=1).sum() * 1000), 1),
                                                 "lapel": round(float(np.linalg.norm(np.diff(ul, axis=0), axis=1).sum() * 1000), 1)}}
    log(f"lapel unfold {REP['lapel_unfold']}")


# ---------- seams
def edge_len_on(nm, pred):
    f = FL[nm]
    B = boundary_edges(f["F"])
    B = B[pred(f["V"][B[:, 0]]) & pred(f["V"][B[:, 1]])]
    return (float(np.linalg.norm(f["U"][B[:, 0]] - f["U"][B[:, 1]], axis=1).sum()) * 1000,
            float(np.linalg.norm(f["V"][B[:, 0]] - f["V"][B[:, 1]], axis=1).sum()) * 1000)


def shared(b, tol=1e-6):
    kb_ = cKDTree(FL[b]["V"])
    return lambda P: kb_.query(P)[0] < tol


seams = []
for a, b in [("front.L", "side.L"), ("side.L", "back.L"), ("front.L", "back.L"), ("sleeve_top.L", "sleeve_under.L")]:
    if a in FL and b in FL:
        la, l3 = edge_len_on(a, shared(b))
        lb, _ = edge_len_on(b, shared(a))
        seams.append({"seam": f"{a}+{b}", "3d_mm": round(l3, 1), "a_flat_mm": round(la, 1), "b_flat_mm": round(lb, 1),
                      "diff_pct": round((la - lb) / max(min(la, lb), 1e-6) * 100, 2)})
_kS = cKDTree(Vs[np.unique(Fs)])
_kB = cKDTree(Vt[np.unique(Ft)])
on_arm = lambda P: (_kS.query(P)[0] < 1e-6) & (_kB.query(P)[0] < 1e-6)  # the armhole: where body and sleeve share their cut
REP["armhole_cut"] = REP_ARM
arm_body = sum(edge_len_on(p, on_arm)[0] for p in ("front.L", "side.L", "back.L") if p in FL)
cap = sum(edge_len_on(p, on_arm)[0] for p in ("sleeve_top.L", "sleeve_under.L") if p in FL)
seams.append({"seam": "armhole.L / cap", "a_flat_mm": round(arm_body, 1), "b_flat_mm": round(cap, 1),
              "diff_pct": round((cap - arm_body) / max(arm_body, 1e-6) * 100, 2), "note": "cap ease (s4-31: 8.8 %)"})
Iu, kr = Z["Iu"], int(Z["k_roll"])
for nm in ("undercollar", "collar"):
    U = FL[nm]["U"]
    rowlen = lambda r: float(np.nansum(np.linalg.norm(np.diff(U[Iu[r]], axis=0), axis=1)) * 1000)
    rowlen3 = lambda r: float(np.linalg.norm(np.diff(FL[nm]["V"][Iu[r]], axis=0), axis=1).sum() * 1000)
    report[nm].update({"neck_edge_flat_mm": round(rowlen(0), 1), "neck_edge_3d_mm": round(rowlen3(0), 1),
                       "roll_flat_mm": round(rowlen(kr), 1), "fall_edge_flat_mm": round(rowlen(-1), 1),
                       "fall_edge_3d_mm": round(rowlen3(-1), 1), "bbox_mm": np.round((np.nanmax(U, 0) - np.nanmin(U, 0)) * 1000, 1).tolist()})
for s in seams:
    log(f"seam {s}")

# ---------- widths along the levels: the girth row on the flat
lev = {n: fit[n]["level_z_m"] for n in ("chest", "waist", "hips")}
if "side.L" in FL:
    lev["chest"] = min(lev["chest"], float(FL["side.L"]["V"][:, 2].max()) - 0.01)
widths = {n: {p: round(level_len(FL[p]["V"], FL[p]["F"], FL[p]["U"], FL[p]["V"][:, 2] - z), 1) for p in ("front.L", "side.L", "back.L") if p in FL}
          for n, z in lev.items()}
girth_rows = []
for n, w in widths.items():
    tot = 2 * sum(w.values()) - 2 * LAP * 1000
    girth_rows.append({"girth": n, "z": round(lev[n], 3), "flat_round_less_laps_mm": round(tot, 1), "plan_mm": fit[n]["garment_girth_mm"],
                       "diff_mm": round(tot - fit[n]["garment_girth_mm"], 1),
                       "shares": {p.split(".")[0]: round(v / sum(w.values()), 3) for p, v in w.items()}})
    log(f"girth {girth_rows[-1]}")

# ---------- s4-31
d = pickle.load(open(src, "rb"))
M = d["pat"].M
OLD = {}
uv = np.asarray(M["uv"], float)
for i, nm in enumerate(M["names"]):
    vid = np.where(np.asarray(M["piece"]) == i)[0]
    FF = np.asarray(M["F"])
    OLD[nm] = (uv, FF[np.isin(FF, vid).all(1)])


def outline(U, F):
    B = boundary_edges(F)
    return U[B[:, 0]], U[B[:, 1]]


def old_width(nm, drop):
    uv_, FF = OLD[nm]
    a, b = outline(uv_, FF)
    y = uv_[np.unique(FF)][:, 1].max() - drop
    xs_ = sorted(p[0] + (y - p[1]) / (q[1] - p[1]) * (q[0] - p[0]) for p, q in zip(a, b) if (p[1] - y) * (q[1] - y) < 0)
    return sum(xs_[i + 1] - xs_[i] for i in range(0, len(xs_) - 1, 2)) * 1000


cmp_rows = []
for n, z in lev.items():
    row = {"girth": n}
    for p in ("front.L", "side.L", "back.L"):
        if p in FL:
            row[p] = {"r2": widths[n][p], "s4_31": round(old_width(p, FL[p]["V"][:, 2].max() - z), 1)}
    cmp_rows.append(row)
    log(f"compare {row}")


def bbox(U):
    return np.round((np.nanmax(U, 0) - np.nanmin(U, 0)) * 1000, 1).tolist()


bb = {p: {"r2": bbox(FL[p]["U"]), "s4_31": bbox(OLD[p][0][np.unique(OLD[p][1])])} for p in FL if p in OLD}
if "lapel.L" in FL and "U2" in FL["lapel.L"]:
    bb["front.L+lapel"] = {"r2": bbox(np.r_[FL["front.L"]["U"], FL["lapel.L"]["U2"]]), "s4_31": bb["front.L"]["s4_31"]}
json.dump({"pieces": report, "seams": seams, "widths": widths, "girths": girth_rows, "compare": cmp_rows, "bbox_mm": bb, **REP},
          open(os.path.join(tdir, "flat.json"), "w"), indent=1)
np.savez(os.path.join(tdir, "flat.npz"), **{f"{k}_{a}": v[a] for k, v in FL.items() for a in ("U", "F", "V", "bad")})

# ---------- flat sheet: each piece (strain red = 6 %) beside s4-31's outline (blue), one scale, grain up
S_ = 600
order = [("back.L", "back.L"), ("side.L", "side.L"), ("front.L", "front.L"), ("sleeve_top.L", "sleeve_top.L"),
         ("sleeve_under.L", "sleeve_under.L"), ("undercollar", "undercollar"), ("collar", "collar")]


def draw_piece(dr, U, Fp, bad, off, H):
    for t, f in enumerate(Fp):
        c = bad[t]
        col = (255, int(255 * max(0, 1 - c / 0.06)), int(255 * max(0, 1 - c / 0.06))) if c > 0.005 else (225, 230, 240)
        dr.polygon([(off[0] + U[i, 0] * S_, H - (U[i, 1] - off[1]) * S_) for i in f], fill=col)
    a, b = outline(U, Fp)
    for q, r in zip(a, b):
        dr.line([(off[0] + q[0] * S_, H - (q[1] - off[1]) * S_), (off[0] + r[0] * S_, H - (r[1] - off[1]) * S_)], fill=(0, 0, 0), width=2)


tiles = []
for p, op in order:
    if p not in FL:
        continue
    U, Fp, bad = FL[p]["U"], FL[p]["F"], FL[p]["bad"]
    extra = [FL["lapel.L"]["U2"]] if p == "front.L" and "U2" in FL.get("lapel.L", {}) else []
    allU = np.concatenate([U] + extra)
    lo = np.nanmin(allU, 0)
    w = max(0.45, (np.nanmax(allU, 0) - lo)[0] + 0.05)
    hgt = max((np.nanmax(allU, 0) - lo)[1], 0.8) + 0.1
    im = Image.new("RGB", (int(2 * w * S_) + 30, int(hgt * S_) + 40), (255, 255, 255))
    dr = ImageDraw.Draw(im)
    H = im.height - 20
    draw_piece(dr, U - lo, Fp, bad, (10, 0), H)
    if extra:
        draw_piece(dr, extra[0] - lo, FL["lapel.L"]["F"], FL["lapel.L"]["bad"], (10, 0), H)
    if op in OLD:
        uv_, FF = OLD[op]
        P = uv_[np.unique(FF)]
        a, b = outline(uv_, FF)
        x0, y0 = P[:, 0].min() - w, P[:, 1].min()
        for q, r in zip(a, b):
            dr.line([(10 + (q[0] - x0) * S_, H - (q[1] - y0) * S_), (10 + (r[0] - x0) * S_, H - (r[1] - y0) * S_)], fill=(30, 90, 200), width=2)
    dr.text((10, 4), f"{p}: R2 (strain red = 6 %) | s4-31 (blue)", fill=(0, 0, 0))
    tiles.append(im)
hh = max(t.height for t in tiles)
outim = Image.new("RGB", (sum(t.width for t in tiles) + 10 * len(tiles), hh), (255, 255, 255))
x = 0
for t in tiles:
    outim.paste(t, (x, hh - t.height))
    x += t.width + 10
outim.save(os.path.join(tdir, "flat_sheet.png"))

# ---------- the cut pieces in 3D (left, and mirrored), coloured by piece
meshes = []
for k, (nm, (Vp, Fp)) in enumerate(PIECES.items()):
    c = np.tile([PAL[k % len(PAL)]], (len(Fp), 1))
    meshes.append((Vp, Fp, c))
    if nm not in ("undercollar", "collar"):
        meshes.append((Vp * MIR, Fp[:, ::-1], c))
meshes = [m for m in meshes if True]
box = ((-0.62, 0.62), (0.80, 1.72))
tiles = [render(meshes, view=v, box=box) for v in ("front", "left", "back", "right")]
sheet(tiles, labels=["front", "left", "back", "right"]).save(os.path.join(tdir, "cut_sheet.png"))
log(f"pieces: {list(PIECES)}; refused: {REP['refused']}")
log("wrote flat.json flat_sheet.png cut_sheet.png")
