"""R1 step 6 (CUT AND FLATTEN) of drape first, and the comparison with s4-31's approved pattern.

  slot uv run python spikes/r1_flat.py <toile dir> <loaded.pkl> <jacket.json>

CUT: the sleeves off the body EXACTLY along the armhole: the plane of D4's armhole loop, through the toile, near the
arm (both sides share the one curve, so the cap and the armhole are equal in 3D by construction); then the marks as
cuts along mesh edges (shortest edge path through each mark's points, its inner vertices snapped back onto the mark):
shoulder, front/side, side/back, centre back on the body; fore and hind seams on each sleeve. Pieces = faces joined
across uncut edges; named by their mean angle round the body / their area (top sleeve the larger).
FLATTEN: LSCM (two far pins), then ARAP (local-global, cotan, 60 iterations). Strain per triangle from the 3D -> 2D
map's singular values (s1 >= s2): stretch s1 - 1, compression 1 - s2: a draper's reading: compression = cloth to take
out (a dart), stretch = cloth to add (ease, a seam).
COMPARE: grain-up overlays beside s4-31's pieces (same scale), widths along the chest / waist / hips levels, seams.
Writes <toile dir>/flat.npz, flat.json, flat_sheet.png, cut_sheet.png."""
import json
import os
import pickle
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.sparse.linalg import factorized, spsolve
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(__file__))
from r1_common import PAL, clip, compact, face_components, render, sheet  # noqa: E402

tdir, src, jpath = sys.argv[1:4]
Z = np.load(os.path.join(tdir, "toile.npz"))
V, F = Z["V"], Z["F"]
ca, na, sh, A, alen, yc = Z["ca"], Z["na"], Z["sh"], Z["A"], float(Z["alen"]), float(Z["yc"])
MK = {k: np.asarray(v["pts"]) for k, v in json.load(open(os.path.join(tdir, "marks.json"))).items()}
steps = json.load(open(jpath))["steps"]
fit = steps["0"]["output"]["fit"]
MIR = np.array([-1.0, 1, 1])
log = lambda m: print(m, flush=True)


def folded(P):
    return P * np.where(P[:, :1] < 0, MIR, 1)


AH = np.asarray(json.load(open(os.path.join(tdir, "..", "..", "d4", "start", "lines.json")))["lines"]["armhole.L"]["pts"])
e1 = np.cross(na, [0, 0, 1.0])
e1 /= np.linalg.norm(e1)
e2 = np.cross(na, e1)
_d = AH - ca
_psi = np.arctan2(_d @ e2, _d @ e1)
_o = np.argsort(_psi)
PSI, RAD = _psi[_o], np.linalg.norm(_d - np.outer(_d @ na, na), axis=1)[_o]


def arm_plane(P, margin=0.035):
    """(signed distance past the armhole's plane, > 0 where the point is in the sleeve's reach: its projection on the
    plane within the armhole loop's radius + margin, or 6 cm past the plane)."""
    Q = folded(P)
    d = Q - ca
    s = d @ na
    r = np.linalg.norm(d - np.outer(s, na), axis=1)
    R = np.interp(np.arctan2(d @ e2, d @ e1), PSI, RAD, period=2 * np.pi)
    t = np.clip((Q - sh) @ A, 0, alen)
    dax = np.linalg.norm(Q - (sh + t[:, None] * A), axis=1)
    return s, np.maximum(R + margin - r, np.minimum(s - 0.06, 0.11 - dax))


pl, near = arm_plane(V)
phi = np.minimum(pl, near)
Vs, Fs = clip(V, F, phi)
Vt, Ft = clip(V, F, -phi)
res = np.abs((AH - ca) @ na)
log(f"sleeves {len(Vs)} v, body {len(Vt)} v; D4's body armhole off its plane: mean {res.mean()*1000:.1f} max {res.max()*1000:.1f} mm")


def boundary_loops_edges(F):
    E = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    u, c = np.unique(E, axis=0, return_counts=True)
    return u[c == 1]


def edge_graph(V, F):
    E = np.unique(np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1), axis=0)
    w = np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1)
    G = coo_matrix((np.r_[w, w], (np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]])), shape=(len(V), len(V)))
    return csr_matrix(G)


def cut_paths(V, F, names, anchors=None):
    """Edge paths along each mark; returns (set of cut edges, {name: vertex path})."""
    G = edge_graph(V, F)
    kd = cKDTree(V)
    cut, paths = set(), {}
    for nm in names:
        if nm not in MK or len(MK[nm]) < 2:
            continue
        P = MK[nm]
        _, idx = kd.query(P)
        idx = [i for k, i in enumerate(idx) if k == 0 or i != idx[k - 1]]
        path = [idx[0]]
        for a, b in zip(idx[:-1], idx[1:]):
            _, pred = dijkstra(G, indices=a, return_predecessors=True, limit=0.30)
            seg = [b]
            while seg[-1] != a and pred[seg[-1]] >= 0:
                seg.append(pred[seg[-1]])
            path += seg[::-1][1:]
        # a mark that stops short of the toile's edge (the hem, the wrist, the armhole) runs on to it: <= 10 cm
        B = boundary_loops_edges(F)
        bset = np.unique(B)
        for end in (0, -1):
            if path[end] in set(bset.tolist()):
                continue
            anchor = (anchors or {}).get(nm) if end == 0 else None
            dist, pred = dijkstra(G, indices=path[end], return_predecessors=True, limit=np.inf if anchor is not None else 0.10)
            db = dist[bset]
            if anchor is not None:  # a sleeve seam starts at its junction on the armhole (D4's)
                db = np.where(np.isfinite(db), np.linalg.norm(V[bset] - anchor, axis=1), np.inf)
            if np.isfinite(db).any():
                tgt = int(bset[np.argmin(db)])
                seg = [tgt]
                while seg[-1] != path[end] and pred[seg[-1]] >= 0:
                    seg.append(pred[seg[-1]])
                path = path + seg[::-1][1:] if end == -1 else seg[:-1] + path
        for a, b in zip(path[:-1], path[1:]):
            cut.add((min(a, b), max(a, b)))
        # snap the path's inner vertices onto the mark (the jag of the edge path taken out)
        seg_a, seg_b = P[:-1], P[1:]
        for v in path[1:-1]:
            d = seg_b - seg_a
            t = np.clip(np.einsum("ij,ij->i", V[v] - seg_a, d) / np.maximum(np.einsum("ij,ij->i", d, d), 1e-12), 0, 1)
            Q = seg_a + t[:, None] * d
            q = Q[np.argmin(np.linalg.norm(Q - V[v], axis=1))]
            if np.linalg.norm(q - V[v]) < 0.006:
                V[v] = q
        paths[nm] = path
        log(f"  cut {nm}: {len(path)} v, ends on the edge: {path[0] in set(bset.tolist())}, {path[-1] in set(bset.tolist())}")
    return cut, paths


def pieces(V, F, cut, min_area=0.01):
    lab = face_components(F, len(V), cut)
    ar = 0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1)
    out = []
    for l in np.unique(lab):
        m = lab == l
        if ar[m].sum() >= min_area:
            out.append(m)
    return out, ar


body_marks = ["shoulder.L", "shoulder.R", "front_side.L", "front_side.R", "side_back.L", "side_back.R", "centre_back"]
cutT, pathsT = cut_paths(Vt, Ft, body_marks)
JN = json.load(open(os.path.join(tdir, "..", "..", "d4", "start", "lines.json")))["junctions"]
anchorsS = {f"sleeve_{k}.{s}": np.asarray(JN[s][k]) for s in "LR" for k in ("fore", "hind")}
cutS, pathsS = cut_paths(Vs, Fs, ["sleeve_fore.L", "sleeve_hind.L", "sleeve_fore.R", "sleeve_hind.R"], anchorsS)
PC = {}
mT, arT = pieces(Vt, Ft, cutT)
for m in mT:
    C = (Vt[Ft[m]].mean(1) * arT[m, None]).sum(0) / arT[m].sum()
    side = "L" if C[0] > 0 else "R"
    th = np.degrees(np.arctan2(abs(C[0]), -(C[1] - yc)))
    PC.setdefault(side, []).append((th, m, C))
names = {}
for side, lst in PC.items():
    lst.sort(key=lambda x: x[0])
    tags = ["front", "side", "back"] if len(lst) == 3 else [f"body{i}" for i in range(len(lst))]
    for tg, (th, m, C) in zip(tags, lst):
        names[f"{tg}.{side}"] = ("T", m)
mS, arS = pieces(Vs, Fs, cutS)
SL = {}
for m in mS:
    C = Vs[Fs[m]].mean(1).mean(0)
    SL.setdefault("L" if C[0] > 0 else "R", []).append((arS[m].sum(), m))
for side, lst in SL.items():
    lst.sort(key=lambda x: -x[0])
    tags = ["sleeve_top", "sleeve_under"] if len(lst) == 2 else [f"sleeve{i}" for i in range(len(lst))]
    for tg, (_, m) in zip(tags, lst):
        names[f"{tg}.{side}"] = ("S", m)
log(f"pieces: {sorted(names)}")


# ---------- flatten
def lscm(V, F):
    n = len(V)
    e1 = V[F[:, 1]] - V[F[:, 0]]
    e2 = V[F[:, 2]] - V[F[:, 0]]
    x1 = np.linalg.norm(e1, axis=1)
    ex = e1 / x1[:, None]
    nn = np.cross(e1, e2)
    ar2 = np.linalg.norm(nn, axis=1)
    ey = np.cross(nn / ar2[:, None], ex)
    p = np.zeros((len(F), 3, 2))
    p[:, 1, 0] = x1
    p[:, 2, 0] = np.einsum("ij,ij->i", e2, ex)
    p[:, 2, 1] = np.einsum("ij,ij->i", e2, ey)
    s = 1 / np.sqrt(ar2)
    rows, cols, vals = [], [], []
    for j in range(3):
        a, b = (j + 1) % 3, (j + 2) % 3
        Wr = (p[:, b, 0] - p[:, a, 0]) * s
        Wi = (p[:, b, 1] - p[:, a, 1]) * s
        r = np.arange(len(F))
        # Re: Wr u - Wi v ; Im: Wi u + Wr v
        rows += [2 * r, 2 * r, 2 * r + 1, 2 * r + 1]
        cols += [F[:, j], n + F[:, j], F[:, j], n + F[:, j]]
        vals += [Wr, -Wi, Wi, Wr]
    M = csr_matrix(coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(2 * len(F), 2 * n)))
    i0 = 0
    i1 = int(np.argmax(np.linalg.norm(V - V[i0], axis=1)))
    i0 = int(np.argmax(np.linalg.norm(V - V[i1], axis=1)))
    d = np.linalg.norm(V[i1] - V[i0])
    pin = {i0: (0.0, 0.0), i1: (d, 0.0)}
    fixed = np.array([i0, i1, n + i0, n + i1])
    fv = np.array([0.0, d, 0.0, 0.0])
    free = np.setdiff1d(np.arange(2 * n), fixed)
    Mf, Mp = M[:, free], M[:, fixed]
    x = spsolve((Mf.T @ Mf).tocsc(), -(Mf.T @ (Mp @ fv)))
    U = np.zeros(2 * n)
    U[free] = x
    U[fixed] = fv
    return np.c_[U[:n], U[n:]], p


def arap(V, F, U, p, iters=60):
    n = len(V)
    # cotan weights from the 3D triangle (local coords p)
    rows, cols, vals = [], [], []
    W = np.zeros((len(F), 3))
    for k in range(3):
        i, j = (k + 1) % 3, (k + 2) % 3
        a = p[:, i] - p[:, k]
        b = p[:, j] - p[:, k]
        cot = np.einsum("ij,ij->i", a, b) / np.maximum(np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]), 1e-12)
        W[:, k] = 0.5 * cot
        I, J = F[:, i], F[:, j]
        rows += [I, J, I, J]
        cols += [I, J, J, I]
        vals += [W[:, k], W[:, k], -W[:, k], -W[:, k]]
    Lm = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)).tolil()
    Lm[0, 0] += 1e3
    solve = factorized(Lm.tocsc())
    X = p  # (f, 3, 2) rest coords
    for _ in range(iters):
        Ju = np.stack([U[F[:, 1]] - U[F[:, 0]], U[F[:, 2]] - U[F[:, 0]]], 2)  # (f, 2, 2) columns = edges
        Jx = np.stack([X[:, 1] - X[:, 0], X[:, 2] - X[:, 0]], 2)
        Jm = Ju @ np.linalg.inv(Jx)
        Us, S, Vt_ = np.linalg.svd(Jm)
        R = Us @ Vt_
        neg = np.linalg.det(R) < 0
        Us[neg, :, 1] *= -1
        R = Us @ Vt_
        b = np.zeros((n, 2))
        for k in range(3):
            i, j = (k + 1) % 3, (k + 2) % 3
            e = np.einsum("fab,fb->fa", R, X[:, i] - X[:, j]) * W[:, k, None]
            np.add.at(b, F[:, i], e)
            np.add.at(b, F[:, j], -e)
        b[0] += 1e3 * U[0]
        U = np.c_[solve(b[:, 0]), solve(b[:, 1])]
    Ju = np.stack([U[F[:, 1]] - U[F[:, 0]], U[F[:, 2]] - U[F[:, 0]]], 2)
    Jx = np.stack([X[:, 1] - X[:, 0], X[:, 2] - X[:, 0]], 2)
    S = np.linalg.svd(Ju @ np.linalg.inv(Jx), compute_uv=False)
    return U, S


def cross2(a, b):
    return a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]


def grain_up(U, Vp):
    """Rotate the flat so the 3D upward direction (z) runs up the flat's y (the grain: vertical on the body)."""
    g = np.linalg.lstsq(np.c_[U, np.ones(len(U))], Vp[:, 2], rcond=None)[0][:2]
    a = np.arctan2(g[0], g[1])
    c, s = np.cos(a), np.sin(a)
    U2 = U @ np.array([[c, -s], [s, c]]).T
    return U2 - U2.min(0)


FL = {}
report = {}
_mirror = "sleeve_top.L" not in names and "sleeve_top.R" in names  # (seams that did not split a side: its mirror)
for nm in sorted(names):
    slv = nm.startswith("sleeve")
    if not ((nm.endswith(".L") and not (slv and _mirror)) or (slv and _mirror and nm.endswith(".R"))):
        continue
    src_, m = names[nm]
    VV, FF = (Vt, Ft) if src_ == "T" else (Vs, Fs)
    Vp, Fp = compact(VV, FF[m])
    if nm.endswith(".R"):
        Vp, Fp, nm = Vp * MIR, Fp[:, ::-1].copy(), nm[:-2] + ".L"
    a2 = np.linalg.norm(np.cross(Vp[Fp[:, 1]] - Vp[Fp[:, 0]], Vp[Fp[:, 2]] - Vp[Fp[:, 0]]), axis=1)
    Fp = Fp[a2 > 2e-9]  # (the exact clips leave slivers where a cut grazes a vertex)
    lab = face_components(Fp, len(Vp))
    Fp = Fp[lab == np.bincount(lab).argmax()]
    Vp, Fp = compact(Vp, Fp)
    U, p = lscm(Vp, Fp)
    U, S = arap(Vp, Fp, U, p)
    U = grain_up(U, Vp)
    ar = 0.5 * np.linalg.norm(np.cross(Vp[Fp[:, 1]] - Vp[Fp[:, 0]], Vp[Fp[:, 2]] - Vp[Fp[:, 0]]), axis=1)
    st, co = S[:, 0] - 1, 1 - S[:, 1]
    bad = np.maximum(st, co)
    worst = np.argsort(-bad)[: max(1, len(bad) // 50)]
    Cw = Vp[Fp[worst]].mean(1)
    report[nm] = {"faces": int(len(Fp)), "area_cm2": round(ar.sum() * 1e4, 1),
                  "flat_area_ratio": round(float(0.5 * np.abs(cross2(U[Fp[:, 1]] - U[Fp[:, 0]], U[Fp[:, 2]] - U[Fp[:, 0]])).sum() / ar.sum()), 4),
                  "stretch_max_pct": round(st.max() * 100, 1), "compress_max_pct": round(co.max() * 100, 1),
                  "strain_mean_pct": round(float((bad * ar).sum() / ar.sum() * 100), 2),
                  "area_over_2pct": round(float(ar[bad > 0.02].sum() / ar.sum() * 100), 1),
                  "area_over_5pct": round(float(ar[bad > 0.05].sum() / ar.sum() * 100), 1),
                  "worst_2pct_at": {"z": round(float(Cw[:, 2].mean()), 3), "x": round(float(Cw[:, 0].mean()), 3),
                                    "y": round(float(Cw[:, 1].mean()), 3),
                                    "kind": "compression (dart)" if co[worst].mean() > st[worst].mean() else "stretch (ease)"}}
    FL[nm] = {"V": Vp, "F": Fp, "U": U, "bad": bad, "co": co, "st": st}
    log(f"{nm}: {report[nm]}")


# ---------- seams: shared 3D curves, their flat length on each side
def edge_len_on(nm, pred):
    """Flat and 3D length of the piece's boundary edges whose both ends satisfy pred(3D points)."""
    f = FL[nm]
    B = boundary_loops_edges(f["F"])
    ok = pred(f["V"][B[:, 0]]) & pred(f["V"][B[:, 1]])
    B = B[ok]
    return (float(np.linalg.norm(f["U"][B[:, 0]] - f["U"][B[:, 1]], axis=1).sum()) * 1000,
            float(np.linalg.norm(f["V"][B[:, 0]] - f["V"][B[:, 1]], axis=1).sum()) * 1000)


def shared(a, b, tol=1e-6):
    kb = cKDTree(FL[b]["V"])
    return lambda P: kb.query(P)[0] < tol


on_arm = lambda P: (np.abs(arm_plane(P)[0]) < 2e-5) & (arm_plane(P)[1] > -1e-4)
seams = []
for a, b in [("front.L", "side.L"), ("side.L", "back.L"), ("front.L", "back.L"), ("sleeve_top.L", "sleeve_under.L")]:
    if a in FL and b in FL:
        la, l3 = edge_len_on(a, shared(a, b))
        lb, _ = edge_len_on(b, shared(b, a))
        seams.append({"seam": f"{a}+{b}", "3d_mm": round(l3, 1), "a_flat_mm": round(la, 1), "b_flat_mm": round(lb, 1),
                      "diff_pct": round((la - lb) / max(min(la, lb), 1e-6) * 100, 2)})
arm_body = sum(edge_len_on(p, on_arm)[0] for p in ("front.L", "side.L", "back.L") if p in FL)
arm_body3 = sum(edge_len_on(p, on_arm)[1] for p in ("front.L", "side.L", "back.L") if p in FL)
cap = sum(edge_len_on(p, on_arm)[0] for p in ("sleeve_top.L", "sleeve_under.L") if p in FL)
seams.append({"seam": "armhole.L / cap", "3d_mm": round(arm_body3, 1), "a_flat_mm": round(arm_body, 1), "b_flat_mm": round(cap, 1),
              "diff_pct": round((cap - arm_body) / max(arm_body, 1e-6) * 100, 2), "note": "cap ease (s4-31: 8.8 %)"})
for s in seams:
    log(f"seam {s}")


# ---------- widths along the levels (each piece's level curve, flat length): the girth row on the flat
def level_len(nm, z):
    f = FL[nm]
    Vp, Fp, U = f["V"], f["F"], f["U"]
    s = Vp[:, 2] - z
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


lev = {n: fit[n]["level_z_m"] for n in ("chest", "waist", "hips")}
if "side.L" in FL:  # a level that would cut the armhole is taken at the underarm (draft_girths' rule)
    lev["chest"] = min(lev["chest"], float(FL["side.L"]["V"][:, 2].max()) - 0.01)


def level_len3(nm, z):
    FL["_tmp"] = {"V": FL[nm]["V"], "F": FL[nm]["F"], "U": FL[nm]["V"]}
    try:
        return level_len("_tmp", z)
    finally:
        FL.pop("_tmp")


widths = {n: {p: round(level_len(p, z), 1) for p in ("front.L", "side.L", "back.L") if p in FL} for n, z in lev.items()}
girth_rows = []
for n, w in widths.items():
    tot = 2 * sum(w.values())
    tot3 = 2 * sum(level_len3(p, lev[n]) for p in w)
    girth_rows.append({"girth": n, "z": round(lev[n], 3), "flat_round_mm": round(tot, 1),
                       "toile_pieces_3d_mm": round(tot3, 1), "plan_mm": fit[n]["garment_girth_mm"],
                       "diff_mm": round(tot - fit[n]["garment_girth_mm"], 1),
                       "shares": {p.split(".")[0]: round(v / sum(w.values()), 3) for p, v in w.items()}})
    log(f"girth {girth_rows[-1]}")

# ---------- s4-31's flat pieces (the approved pattern) for the overlay
d = pickle.load(open(src, "rb"))
M = d["pat"].M
OLD = {}
for i, nm in enumerate(M["names"]):
    if nm in FL:
        vid = np.where(np.asarray(M["piece"]) == i)[0]
        FF = np.asarray(M["F"])
        FF = FF[np.isin(FF, vid).all(1)]
        uv = np.asarray(M["uv"], float)
        OLD[nm] = (uv, FF)


def outline_segments(U, F):
    B = boundary_loops_edges(F)
    return U[B[:, 0]], U[B[:, 1]]


def old_width(nm, drop):
    """s4-31: the piece's width on a horizontal line `drop` below its top (flat y up the grain), even-odd."""
    from hifipushie import draft_girths as dg
    uv, FF = OLD[nm]
    a, b = outline_segments(uv, FF)
    top = uv[np.unique(FF)][:, 1].max()
    y = top - drop
    xs = []
    for p, q in zip(a, b):
        if (p[1] - y) * (q[1] - y) < 0:
            xs.append(p[0] + (y - p[1]) / (q[1] - p[1]) * (q[0] - p[0]))
    xs = sorted(xs)
    return sum(xs[i + 1] - xs[i] for i in range(0, len(xs) - 1, 2)) * 1000


cmp_rows = []
for n, z in lev.items():
    row = {"girth": n}
    for p in ("front.L", "side.L", "back.L"):
        if p in FL and p in OLD:
            drop = FL[p]["V"][:, 2].max() - z
            row[p] = {"r1": widths[n][p], "s4_31": round(old_width(p, drop), 1)}
    cmp_rows.append(row)
    log(f"compare {row}")
old_len = {}
for p in FL:
    if p in OLD:
        uv, FF = OLD[p]
        a, b = outline_segments(uv, FF)
        P = uv[np.unique(FF)]
        old_len[p] = {"s4_31_hw_mm": np.round((P.max(0) - P.min(0)) * 1000, 1).tolist(),
                      "r1_hw_mm": np.round((FL[p]["U"].max(0) - FL[p]["U"].min(0)) * 1000, 1).tolist()}
json.dump({"pieces": report, "seams": seams, "widths": widths, "girths": girth_rows, "compare": cmp_rows,
           "bbox": old_len}, open(os.path.join(tdir, "flat.json"), "w"), indent=1)
np.savez(os.path.join(tdir, "flat.npz"), **{f"{k}_{a}": v[a] for k, v in FL.items() for a in ("U", "F", "V", "bad")})

# ---------- flat sheet: each piece (strain coloured) beside s4-31's outline, same scale, grain up
order = [p for p in ("back.L", "side.L", "front.L", "sleeve_top.L", "sleeve_under.L") if p in FL]
S_ = 600  # px per m
tiles = []
for p in order:
    U, Fp, bad = FL[p]["U"], FL[p]["F"], FL[p]["bad"]
    o = OLD.get(p)
    w = 0.45
    hgt = max(U[:, 1].max(), 0.8) + 0.1
    im = Image.new("RGB", (int(2 * w * S_) + 20, int(hgt * S_) + 40), (255, 255, 255))
    dr = ImageDraw.Draw(im)
    H = im.height - 20
    for t, f in enumerate(Fp):
        c = bad[t]
        col = (255, int(255 * max(0, 1 - c / 0.06)), int(255 * max(0, 1 - c / 0.06))) if c > 0.005 else (225, 230, 240)
        dr.polygon([(10 + U[i, 0] * S_, H - U[i, 1] * S_) for i in f], fill=col)
    a, b = outline_segments(U, Fp)
    for q, r in zip(a, b):
        dr.line([(10 + q[0] * S_, H - q[1] * S_), (10 + r[0] * S_, H - r[1] * S_)], fill=(0, 0, 0), width=2)
    if o:
        uv, FF = o
        P = uv[np.unique(FF)]
        off = np.array([w * S_ + 10, 0]) - P.min(0) * [S_, 0]
        a, b = outline_segments(uv, FF)
        y0 = P[:, 1].min()
        for q, r in zip(a, b):
            dr.line([(off[0] + q[0] * S_, H - (q[1] - y0) * S_), (off[0] + r[0] * S_, H - (r[1] - y0) * S_)], fill=(30, 90, 200), width=2)
    dr.text((10, 4), f"{p}: R1 (strain red = 6 %) | s4-31 (blue)", fill=(0, 0, 0))
    tiles.append(im)
hh = max(t.height for t in tiles)
outim = Image.new("RGB", (sum(t.width for t in tiles) + 10 * len(tiles), hh), (255, 255, 255))
x = 0
for t in tiles:
    outim.paste(t, (x, hh - t.height))
    x += t.width + 10
outim.save(os.path.join(tdir, "flat_sheet.png"))

# ---------- the cut pieces in 3D (both sides), coloured by piece
meshes = []
for k, nm in enumerate(sorted(names)):
    src_, m = names[nm]
    VV, FF = (Vt, Ft) if src_ == "T" else (Vs, Fs)
    meshes.append((VV, FF[m], np.tile([PAL[sorted({n[:-2] for n in names}).index(nm[:-2]) % len(PAL)]], (m.sum(), 1))))
box = ((-0.62, 0.62), (0.80, 1.72))
tiles = [render(meshes, view=v, box=box) for v in ("front", "left", "back", "right")]
sheet(tiles, labels=["front", "left", "back", "right"]).save(os.path.join(tdir, "cut_sheet.png"))
log("wrote flat.json flat_sheet.png cut_sheet.png")
