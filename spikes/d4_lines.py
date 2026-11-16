"""D4: SEAMS ON BODY LINES, the dress-form start. Each seam of the pattern is pinned along ONE line on the body (a style
line taped on a dress form) by arc length, both sides of the seam on the same line, so the start's seams meet by
construction; each piece's flat is then bent between its laid seams (ARAP, the laid points as handles); a follower cut
in its host's frame (facing on a front, collar on an undercollar) is its host's map at its own flat, a layer in / out.

  HIFIPUSHIE_HOME=<ws> slot uv run python spikes/d4_lines.py <out> <loaded.pkl> <d3 cnet run dir> <reference.png>
Writes <out>/cnet.pkl (d1_where / d4_solve read it), X_start.npy, laid.npz (root ids, positions), lines.json (every
line: points, length; every seam: its arc vs its line's), lines_quick_sheet.png (the lines alone on the body).

SPIKE TABLE (not src: the seam -> line assignment is written per piece pair here; the general rule for the tools is the
verdict's job). Lines: centre back (body mid line), shoulder (hps -> shoulder point over the surface), front/side and
side/back (step 2's chest shares, the same shares at waist / hips / seat: step 2 declares only the chest), armhole (the
armhole_front + armhole_back tapes as one loop from the shoulder point), sleeve fore / hind (down the arm from the laid
armhole's junctions through biceps / elbow / wrist, the arm girths split by the two sleeve pieces' own widths), neckline
(the neck loop from the centre back: no collar line was measured)."""
import json
import os
import pickle
import sys

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import factorized

from hifipushie.chain_core import GAP, LAYER

out, src, run, ref = sys.argv[1:5]
os.makedirs(out, exist_ok=True)
log = lambda m: print(m, flush=True)
d = pickle.load(open(src, "rb"))
pat, body = d["pat"], d["body"]
g = pickle.load(open(os.path.join(run, "cnet.pkl"), "rb"))
c = g["cnet"]
T = pat.M["starts"]["tapes"]
CT = body.contact
names = c.names
MIR = np.array([-1.0, 1, 1])


# ---------- geometry on the body
def onto(P, gap=GAP, passes=4):
    """P moved onto the body's surface, gap off it (in or out)."""
    P = np.array(P, float)
    for _ in range(passes):
        s, n = CT.query(P)
        P = P - (s - gap)[:, None] * n
    return P


def resample(P, step=0.005):
    P = np.asarray(P, float)
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    k = max(2, int(np.ceil(s[-1] / step)) + 1)
    t = np.linspace(0, s[-1], k)
    return np.c_[[np.interp(t, s, P[:, i]) for i in range(3)]].T


def surface_path(pts, step=0.005):
    """Points joined by straight runs, put on the surface (GAP off), resampled, again on the surface."""
    return onto(resample(onto(resample(pts, step)), step))


def arclen(P):
    return np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]


def at_arc(P, s):
    a = arclen(P)
    return np.c_[[np.interp(s, a, P[:, i]) for i in range(3)]].T


def extend(P, metres):
    """The line run on straight past its end by `metres` (a seam longer than the line it is laid on)."""
    t = P[-1] - P[-4]
    t /= np.linalg.norm(t)
    return np.r_[P, P[-1] + np.linspace(0.005, metres, int(metres / 0.005))[:, None] * t]


def half_ring(L):
    """A girth loop as the left half ring from the centre front (x = 0, y < 0) to the centre back: (points, arc)."""
    L = np.asarray(L, float)
    i0 = np.argmin(np.where(L[:, 1] < 0, np.abs(L[:, 0]), 9))
    L = np.roll(L, -i0, axis=0)
    if L[len(L) // 8, 0] < 0:
        L = np.r_[L[:1], L[1:][::-1]]
    j = np.argmin(np.where((L[:, 1] > 0) & (np.arange(len(L)) > 4), np.abs(L[:, 0]), 9))
    H = L[: j + 1]
    return H, arclen(H)


def mid_line(side, z0, z1):
    """The body's mid line (x = 0) on the front (side -1) or back (+1), from z0 down to z1, GAP off the surface."""
    zs = np.arange(z0, z1, -0.01)
    P = np.c_[np.zeros(len(zs)), np.full(len(zs), 0.3 * side), zs]
    for _ in range(4):
        P = onto(P)
        P[:, 0] = 0
        P[:, 2] = zs
    return surface_path(onto(P))


# ---------- seams as runs of sewn roots
R = c.root
pairs = {}
for a, b in c.sew:
    pa, pb = names[c.piece[a]], names[c.piece[b]]
    if pa > pb:
        a, b, pa, pb = b, a, pb, pa
    pairs.setdefault((pa, pb), []).append((a, b))
bnd = {}
for (a, b), p, k in zip(c.chain_v, c.chain_piece, c.chain_kind):
    if k == 0:
        bnd.setdefault(int(a), set()).add(int(b))
        bnd.setdefault(int(b), set()).add(int(a))


def runs(pa, pb):
    """The seams joining pa and pb: [[(a, b) pairs in order along pa's outline], ...] (two runs: two separate seams).
    A run breaks where more than 2 unsewn outline vertices lie between two of its sewn ones."""
    P = pairs[(pa, pb) if pa < pb else (pb, pa)]
    if pa > pb:
        P = [(b, a) for a, b in P]
    of = {}
    for a, b in P:
        of.setdefault(a, b)
    ol = np.asarray(c.outlines[pa])
    pos = {int(v): k for k, v in enumerate(ol)}
    ks = sorted(pos[a] for a in of if a in pos)
    n = len(ol)
    gaps = [(ks[(i + 1) % len(ks)] - ks[i]) % n for i in range(len(ks))]
    cuts = [i for i, gp in enumerate(gaps) if gp > 3]
    if not cuts:
        cuts = [int(np.argmax(gaps))]
    out_ = []
    for j, ci in enumerate(cuts):
        nxt = cuts[(j + 1) % len(cuts)]
        idx = [(ci + 1 + t) % len(ks) for t in range((nxt - ci) % len(ks) or len(ks))]
        out_.append([(int(ol[ks[i]]), of[int(ol[ks[i]])]) for i in idx])
    return out_


def flat_arc(ids):
    """Arc along ids in the flat; a step between two pieces (a run joined at a junction) counts 0."""
    ids = np.asarray(ids)
    st = np.linalg.norm(np.diff(c.uv[ids], axis=0), axis=1)
    st[c.piece[ids[1:]] != c.piece[ids[:-1]]] = 0
    return np.r_[0, np.cumsum(st)]


def seam_arc(run_):
    """Each pair's arc along the seam: the mean of its two sides' own arcs, and the two sides' lengths."""
    A, B = np.array([p[0] for p in run_]), np.array([p[1] for p in run_])
    sa, sb = flat_arc(A), flat_arc(B)
    return (sa + sb) / 2, float(sa[-1]), float(sb[-1])


def landmark(name):
    """A pattern point's nearest chain vertex of its piece (by its flat)."""
    p = name.split(":")[0]
    v = c.verts(p)
    return int(v[np.argmin(np.linalg.norm(c.uv[v] - pat.M["uv"][pat.M["points"][name]], axis=1))])


sys.path.insert(0, os.path.dirname(__file__))
from d4_resew import bad_groups, resew_armholes  # noqa: E402

BAD0 = bad_groups(c)
log(f"bad sewn groups in D3's network: {len(BAD0)} same-piece pairs, e.g. {BAD0[:4]}")
c, RESEW = resew_armholes(c, landmark, log=log)
BAD1 = bad_groups(c)
log(f"after re-sewing the armholes: {len(BAD1)} {BAD1[:6]}")
R = c.root
pairs = {}
for a, b in c.sew:
    pa, pb = names[c.piece[a]], names[c.piece[b]]
    if pa > pb:
        a, b, pa, pb = b, a, pb, pa
    pairs.setdefault((pa, pb), []).append((a, b))


def oriented(run_, start_root=None, near=None):
    """The run turned to start at the end whose root is start_root, or nearest (flat) the vertex `near`."""
    if start_root is not None:
        if R[run_[-1][0]] == start_root:
            return run_[::-1]
        assert R[run_[0][0]] == start_root, "run does not end at the root"
        return run_
    u = c.uv[near]
    return run_ if np.linalg.norm(c.uv[run_[0][0]] - u) <= np.linalg.norm(c.uv[run_[-1][0]] - u) else run_[::-1]


# ---------- laying
laid = {}  # root -> position
seam_rep = []


def lay(name, run_, line, mode, segs=None):
    """segs: the run as consecutive sub-runs (one per piece pair), each arc its own, joined end to start.
    Lay a seam run on a line: mode 'arc' from the run's first pair by arc length (the line run on if the seam is
    longer); 'fit' both ends on the line's ends (a seam between two junctions), the excess as an outward bulge."""
    if segs:
        run_, ss, la, lb, off = [], [], 0.0, 0.0, 0.0
        for k, r in enumerate(segs):
            s_k, a_k, b_k = seam_arc(r)
            if k and R[r[0][0]] == R[run_[-1][0]]:
                r, s_k = r[1:], s_k[1:]
            run_ += r
            ss.append(s_k + off)
            off, la, lb = off + float(seam_arc(segs[k])[0][-1]), la + a_k, lb + b_k
        s = np.concatenate(ss)
    else:
        s, la, lb = seam_arc(run_)
    Ll = float(arclen(line)[-1])
    Ls = float(s[-1])
    if mode == "arc":
        L2 = line if Ll >= Ls else extend(line, Ls - Ll + 0.02)
        P = at_arc(L2, s)
    else:
        t = s / Ls
        P = at_arc(line, t * Ll)
        if Ls > Ll:
            a = (2 / np.pi) * np.sqrt(Ll * (Ls - Ll))
            _, n = CT.query(P)
            P = P + (a * np.sin(np.pi * t))[:, None] * n
    if name.startswith("armhole"):
        log(f"  dbg {name} s {s[:3]} .. {s[-1]:.3f} Ll {Ll:.3f} line z {line[:, 2].min():.3f}-{line[:, 2].max():.3f} "
            f"P z {P[:, 2].min():.3f}-{P[:, 2].max():.3f} n {len(run_)} {len(P)}")
    for (va, vb), q in zip(run_, P):
        laid[int(R[va])] = q
    seam_rep.append({"seam": name, "mode": mode, "side_a_mm": round(la * 1e3, 1), "side_b_mm": round(lb * 1e3, 1),
                     "laid_mm": round(Ls * 1e3, 1), "line_mm": round(Ll * 1e3, 1),
                     "seam_vs_line_pct": round((Ls / Ll - 1) * 100, 1), "pairs": len(run_)})
    return P




J2 = json.load(open(os.path.join(os.environ["HIFIPUSHIE_HOME"], "garrett/garments/jacket.json")))
PAN = J2["steps"]["2"]["output"]["panels"][0]["shares"]  # (step 2: the chest only)
SH_FS = PAN["front"]["share"]
SH_SB = PAN["front"]["share"] + PAN["side"]["share"]
lines = {}
JUNC = {}
for side, sg in (("L", 1.0), ("R", -1.0)):
    m = np.array([sg, 1, 1])
    f, s_, b, st, su = (f"{k}.{side}" for k in ("front", "side", "back", "sleeve_top", "sleeve_under"))
    sp = body.p("shoulder.L") * m
    # neckline first: the neck loop from the centre back, through the hps, forward
    H, a = half_ring(np.asarray(T["neck"]["pts"]))
    NK = surface_path((H * m)[::-1])
    lines[f"neckline.{side}"] = NK
    rb = oriented(runs(b, "undercollar")[0], near=landmark(f"back.{side}:cbNeck"))
    rf = oriented(runs(f, "undercollar")[0], near=landmark(f"front.{side}:neck"))
    sb, _, _ = seam_arc(rb)
    PB = lay(f"neck_back.{side}", rb, NK, "arc")
    i = int(np.searchsorted(arclen(NK), sb[-1]))
    lay(f"neck_front.{side}", rf, np.r_[PB[-1:], NK[i:]], "arc")
    # shoulder: from the laid neck point to the shoulder point over the surface
    rs = oriented(runs(b, f)[0], near=landmark(f"back.{side}:hps"))
    lines[f"shoulder.{side}"] = SL = surface_path(np.array([laid[int(R[rs[0][0]])], sp]))
    lay(f"shoulder.{side}", rs, SL, "fit")
    j_shoulder = int(R[rs[-1][0]])
    # armhole: one loop from the shoulder point, front first
    loop = np.r_[np.asarray(T["armhole_front"]["pts"]), np.asarray(T["armhole_back"]["pts"])[::-1][1:]] * m
    sa_tot = (RESEW[side]["body_mm"] + RESEW[side]["cap_mm"]) / 2e3
    k_ah = sa_tot / float(arclen(surface_path(loop))[-1])
    loop = sp + k_ah * (loop - sp)  # (the arm-root loop scaled about the shoulder point to the armhole's own length:
    # a jacket's armhole sits lower than the arm root; step 3 measured only the arm root)
    lines[f"armhole.{side}"] = AH = surface_path(loop)
    rs_ = RESEW[side]
    run_ = list(zip(rs_["B"] + rs_["B"][:1], rs_["C"] + rs_["C"][:1]))
    PA = lay(f"armhole.{side}", run_, AH, "fit")
    Jf, Jh = laid[int(R[rs_["fore"]])], laid[int(R[rs_["hind"]])]
    JUNC[side] = {"fore": Jf.tolist(), "hind": Jh.tolist()}
    # front/side and side/back: the armhole's junction -> step 2's chest shares round chest, waist, hips, seat
    for nm, share, pa, pb, top in (("front_side", SH_FS, f, s_, f"front.{side}:fsArmhole"),
                                   ("side_back", SH_SB, s_, b, f"back.{side}:bsArmholeHollow")):
        pts = []
        for gn in ("chest", "waist", "hips", "seat"):
            Hg, ag = half_ring(np.asarray(T[gn]["pts"]))
            pts.append(at_arc(Hg, [share * ag[-1]])[0] * m)
        rr = runs(pa, pb)
        k0 = int(np.argmin([min(np.linalg.norm(c.uv[r[0][0]] - c.uv[landmark(top)]),
                                np.linalg.norm(c.uv[r[-1][0]] - c.uv[landmark(top)])) for r in rr]))
        r_ = oriented(rr[k0], near=landmark(top))
        segs_ = [r_]
        for r2 in sorted([r for k, r in enumerate(rr) if k != k0], key=lambda r: np.linalg.norm(c.uv[r[0][0]] - c.uv[r_[-1][0]])):
            segs_.append(oriented(r2, near=segs_[-1][-1][0]))  # (a seam broken by an unsewn stretch: one line)
        start = laid.get(int(R[r_[0][0]]))
        line = surface_path(np.r_[[start] if start is not None else np.zeros((0, 3)), pts])
        lines[f"{nm}.{side}"] = line
        lay(f"{nm}.{side}", None, line, "arc", segs=segs_)
    if side == "L":  # centre back: from the laid neck's centre
        r_ = oriented(runs("back.L", "back.R")[0], near=landmark("back.L:cbNeck"))
        cb = mid_line(+1, body.p("cb_neck")[2] - 0.01, 0.87)
        cb = surface_path(np.r_[[laid[int(R[r_[0][0]])]], cb])
        lines["centre_back"] = cb
        lay("centre_back", r_, cb, "arc")
        lines["centre_front"] = mid_line(-1, body.p("cf_neck")[2], 0.80)
    # sleeve fore / hind: from the armhole's junctions down the arm, the arm girths split by the sleeves' widths
    loops = [np.asarray(T[k]["pts"]) * m for k in ("biceps", "elbow", "wrist")]
    Wt = np.linalg.norm(c.uv[landmark(f"{st}:tsLeftEdge")] - c.uv[landmark(f"{st}:tsRightEdge")])
    Wu = np.linalg.norm(c.uv[landmark(f"{su}:usLeftEdge")] - c.uv[landmark(f"{su}:usRightEdge")])
    half = np.pi * Wt / (Wt + Wu)
    pts_f, pts_h = [Jf], [Jh]
    for L_ in loops:
        c0 = L_.mean(0)
        _, _, Vt = np.linalg.svd(L_ - c0)
        u, v = Vt[0], Vt[1]
        ang = lambda P_: np.arctan2((P_ - c0) @ v, (P_ - c0) @ u)
        af, ah = ang(Jf), ang(Jh)
        mid = np.angle(np.exp(1j * af) + np.exp(1j * ah))
        outer = max((mid, mid + np.pi), key=lambda t: sg * (np.cos(t) * u + np.sin(t) * v)[0])  # (top: off the body)
        sgn = 1.0 if np.angle(np.exp(1j * (af - outer))) > 0 else -1.0
        for tgt, a_ in ((pts_f, outer + sgn * half), (pts_h, outer - sgn * half)):
            tgt.append(L_[np.argmin(np.abs(np.angle(np.exp(1j * (ang(L_) - a_)))))])
    rr = runs(st, su)
    log(f"sleeve runs {[(len(x), round(seam_arc(x)[1] * 1e3, 1)) for x in rr]}")
    used = []
    for nm, pts, J in (("sleeve_fore", pts_f, Jf), ("sleeve_hind", pts_h, Jh)):
        line = surface_path(np.array(pts))
        lines[f"{nm}.{side}"] = line
        dist = lambda v: np.linalg.norm(laid[int(R[v])] - J) if int(R[v]) in laid else 9.0
        r_ = min([r for r in rr if r[0] not in used], key=lambda r: min(dist(r[0][0]), dist(r[-1][0])))
        used.append(r_[0])
        r_ = r_ if dist(r_[0][0]) <= dist(r_[-1][0]) else r_[::-1]
        lay(f"{nm}.{side}", r_, line, "arc")
for r_ in seam_rep:
    log(f"seam {r_['seam']:18s} {r_['mode']:3s} a {r_['side_a_mm']:7.1f} b {r_['side_b_mm']:7.1f} line "
        f"{r_['line_mm']:7.1f} seam/line {r_['seam_vs_line_pct']:+6.1f} %")


# ---------- bends between: each piece's flat bent between its laid points (ARAP, the laid points as handles)
def piece_edges(v):
    s = set(v.tolist())
    F = c.F[np.isin(c.F, v).all(1)]
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [0, 2]]], 1), axis=0)
    return E, F


def kabsch(A, B):
    a0, b0 = A.mean(0), B.mean(0)
    U, _, Vt = np.linalg.svd((A - a0).T @ (B - b0))
    D = np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))])
    return U @ D @ Vt, a0, b0


def arap(v, hid, hpos, iters=40, wh=100.0):
    """The piece's flat (vertices v) mapped into 3D as rigidly as possible with v[hid] pulled to hpos."""
    loc = {int(x): k for k, x in enumerate(v)}
    E, _ = piece_edges(v)
    E = np.vectorize(loc.get)(E)
    U = np.c_[c.uv[v], np.zeros(len(v))]
    Rm, a0, b0 = kabsch(U[hid], hpos)
    X = (U - a0) @ Rm + b0
    n, ne = len(v), len(E)
    rows = np.r_[np.arange(ne), np.arange(ne), ne + np.arange(len(hid))]
    cols = np.r_[E[:, 0], E[:, 1], hid]
    vals = np.r_[np.ones(ne), -np.ones(ne), np.full(len(hid), np.sqrt(wh))]
    A = coo_matrix((vals, (rows, cols)), shape=(ne + len(hid), n)).tocsc()
    solve = factorized((A.T @ A + 1e-9 * coo_matrix((np.ones(n), (np.arange(n), np.arange(n))), (n, n))).tocsc())
    nb = [[] for _ in range(n)]
    for k, (i, j) in enumerate(E):
        nb[i].append(k)
        nb[j].append(k)
    for _ in range(iters):
        Rs = np.zeros((n, 3, 3))
        e0 = U[E[:, 0]] - U[E[:, 1]]
        e1 = X[E[:, 0]] - X[E[:, 1]]
        S = np.einsum("ki,kj->kij", e0, e1)
        Si = np.zeros((n, 3, 3))
        np.add.at(Si, E[:, 0], S)
        np.add.at(Si, E[:, 1], S)
        Uu, _, Vt = np.linalg.svd(Si)
        det = np.sign(np.linalg.det(Uu @ Vt))
        Uu[:, :, 2] *= det[:, None]
        Rs = np.transpose(Uu @ Vt, (0, 2, 1))  # (maps flat edge to 3D edge)
        Rk = (Rs[E[:, 0]] + Rs[E[:, 1]]) / 2
        rhs_e = np.einsum("kij,kj->ki", Rk, e0)
        rhs = np.r_[rhs_e, np.sqrt(wh) * hpos]
        Atb = A.T @ rhs
        X = np.c_[[solve(Atb[:, i]) for i in range(3)]].T
    return X


X = np.full((c.n, 3), np.nan)
for r_, q in laid.items():
    X[R == r_] = q
shells = ["front.L", "front.R", "side.L", "side.R", "back.L", "back.R", "sleeve_top.L", "sleeve_top.R",
          "sleeve_under.L", "sleeve_under.R", "undercollar"]
for p in [q for q in names if q in shells]:
    v = c.verts(p)
    hid = np.where(~np.isnan(X[v, 0]))[0]
    Xp = arap(v, hid, X[v[hid]])
    X[v] = Xp
    log(f"arap {p}: {len(v)} points, {len(hid)} laid")


def host_map(fol, host, off):
    """A follower cut in its host's frame: its host's map at its own flat (barycentric in the host's faces), `off` along
    the host's outward side (negative: inside)."""
    from scipy.spatial import Delaunay
    hv = c.verts(host)
    tri = Delaunay(c.uv[hv])
    Fl = tri.simplices
    fv = c.verts(fol)
    t = tri.find_simplex(c.uv[fv])
    P = np.full((len(fv), 3), np.nan)
    for k, (x, ti) in enumerate(zip(fv, t)):
        if ti < 0:
            j = np.argmin(np.linalg.norm(c.uv[hv] - c.uv[x], axis=1))
            P[k] = X[hv[j]]
            continue
        a, b_, cc = hv[Fl[ti]]
        T2 = np.c_[c.uv[b_] - c.uv[a], c.uv[cc] - c.uv[a]]
        w = np.linalg.solve(T2, c.uv[x] - c.uv[a])
        P[k] = X[a] + w[0] * (X[b_] - X[a]) + w[1] * (X[cc] - X[a])
    _, n = CT.query(P)
    return fv, P + off * n


for fol, host, off in (("facing.L", "front.L", -LAYER), ("facing.R", "front.R", -LAYER), ("collar", "undercollar", LAYER)):
    fv, P = host_map(fol, host, off)
    sewn = np.isin(R[fv], list(laid))
    X[fv] = P
    log(f"follower {fol} on {host}: {len(fv)} points")
# sewn groups at one place (a follower's sewn point takes its host's)
for r_ in np.unique(R):
    g_ = np.where(R == r_)[0]
    if len(g_) > 1 and not np.isnan(X[g_, 0]).any():
        X[g_] = X[g_[0]] if r_ not in laid else laid[r_]


def seams_gap(X):
    gp = np.linalg.norm(X[c.sew[:, 0]] - X[c.sew[:, 1]], axis=1) * 1e3
    return {"mean_mm": round(float(np.nanmean(gp)), 2), "max_mm": round(float(np.nanmax(gp)), 2)}


cur = np.linalg.norm(X[c.link_j] - X[c.link_i], axis=1)
s = (cur / np.maximum(c.link_L, 1e-12) - 1) * 100
ok = ~np.isnan(s)
sd, _ = CT.query(np.nan_to_num(X[~np.isnan(X[:, 0])]))
rep = {"seams": seam_rep, "start_seam_gap": seams_gap(X), "links_over_2pct": int((np.abs(s[ok]) > 2).sum()),
       "links": int(ok.sum()), "links_worst_pct": round(float(np.abs(s[ok]).max()), 1),
       "inside": int((sd < 0).sum()), "deepest_mm": round(float(-sd.min()) * 1e3, 1), "junctions": JUNC,
       "shares": {"front_side": SH_FS, "side_back": SH_SB}}
log(json.dumps({k: v for k, v in rep.items() if k != "seams"}))
np.save(os.path.join(out, "X_start.npy"), X)
pickle.dump({"keep": g["keep"], "cnet": c, "TH0": g.get("TH0")}, open(os.path.join(out, "cnet.pkl"), "wb"))
np.savez(os.path.join(out, "laid.npz"), roots=np.array(list(laid)), pos=np.array(list(laid.values())))
json.dump({"lines": {k: {"mm": round(float(arclen(v)[-1]) * 1e3, 1), "pts": np.round(v, 4).tolist()}
                     for k, v in lines.items()}, **rep}, open(os.path.join(out, "lines.json"), "w"), default=float)

# ---------- the lines alone on the body (quick drawing), beside the reference
from PIL import Image, ImageDraw

PAL = {"neck": "#d62728", "shou": "#ff7f0e", "armh": "#2ca02c", "fron": "#1f77b4", "side": "#9467bd",
       "cent": "#000000", "slee": "#e377c2"}
ims = []
S = 900
for nm, dv in (("front", [0, -1, 0.05]), ("left", [1, 0, 0.05]), ("back", [0, 1, 0.05]), ("right", [-1, 0, 0.05])):
    dv = np.array(dv, float) / np.linalg.norm(dv)
    right = np.cross(dv, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, dv)
    allp = body.V
    lo = np.array([(allp @ right).min(), (allp @ up).min()])
    sc = (S - 40) / max(np.ptp(allp @ right), np.ptp(allp @ up))
    pr = lambda P: np.c_[(P @ right - lo[0]) * sc + 20, S - ((P @ up - lo[1]) * sc + 20)]
    im = Image.new("RGB", (S, S), "white")
    dr = ImageDraw.Draw(im)
    for q in pr(body.V[::3]):
        dr.point(tuple(q), fill="#cccccc")
    for k, L_ in lines.items():
        Q = pr(L_)
        facing = (L_ @ dv) >= (body.V @ dv).mean() - 0.01  # (the near side drawn in colour, the far side pale)
        for i in range(len(Q) - 1):
            dr.line([tuple(Q[i]), tuple(Q[i + 1])], fill=PAL[k[:4]] if facing[i] else "#e8e8e8", width=3)
    dr.text((10, 10), nm, fill="black")
    ims.append(im)
Rf = Image.open(ref).convert("RGB")
r = Rf.resize((int(Rf.width * S / Rf.height), S))
sheet = Image.new("RGB", (r.width + S * 4, S), "white")
sheet.paste(r, (0, 0))
for k, im in enumerate(ims):
    sheet.paste(im, (r.width + k * S, 0))
sheet.save(os.path.join(out, "lines_quick_sheet.png"))
log(os.path.join(out, "lines_quick_sheet.png"))
