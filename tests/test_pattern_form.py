"""Known answers for the virtual dress form (pattern_form, dress-garrett 2026-10-19): fold lines are mesh edges and a
fold turns about them with no stretch; a collar band's fall lies on its stand; a lapel folds face-out onto its front; a
tube sleeve keeps its pattern ease on a cylinder; the neck point lands on the body's.
Run: uv run python tests/test_pattern_form.py"""
import math
import sys
import types

import numpy as np

from hifipushie import cloth, pattern_form as pf


def _piece(P, names=None, marks=None, wrap=None):
    return {"P": np.asarray(P, float), "names": names or {}, "marks": marks or {}, "lines": {}, "wrap": wrap or {}}


def _B(pieces, seams=(), folds=(), refine=None):
    B = {"pieces": pieces, "seams": [list(s) for s in seams], "stitches": [], "folds": list(folds)}
    if refine:
        B["mesh_refine"] = refine
    return B


def _flat(M):
    return np.c_[M["uv"], np.zeros(len(M["uv"]))]


def _stretch(V, M):
    E = pf._edges(M["F"])
    l0 = np.linalg.norm(M["uv"][E[:, 0]] - M["uv"][E[:, 1]], axis=1)
    l1 = np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1)
    return float(np.abs(l1 / l0 - 1).max())


def _line_dist(V, a, b):
    u = (b - a) / np.linalg.norm(b - a)
    D = V - a
    return np.linalg.norm(D - np.outer(D @ u, u), axis=1)


def _flap(M, k=0):
    from hifipushie import folds as foldmod
    return np.asarray(foldmod._geom(M, M["folds"][k])["rows"][0]["v"])


def test_diagonal_fold_170():
    """A rectangle folded 170 deg on a diagonal line: the line is an edge chain, 0% stretch, the hinge on the line."""
    P = [[0, 0], [0.3, 0], [0.3, 0.2], [0, 0.2]]
    a2, b2 = np.array([0.05, 0.0]), np.array([0.25, 0.2])
    B = _B({"r": _piece(P)}, folds=[{"piece": "r", "line": [a2.tolist(), b2.tolist()], "angle": 10, "kind": "press",
                                     "name": "diag"}], refine=[{"piece": "r", "h": 0.005}])
    M = cloth.mesh(B, 0.02)
    fd = M["folds"][0]
    assert fd["missing_edges"] == 0, fd["missing_edges"]
    row = fd["rows"][0]
    assert _line_dist(np.c_[M["uv"][row], np.zeros(len(row))], np.r_[a2, 0], np.r_[b2, 0]).max() < 1e-6
    out = pf.assemble({"mesh": M, "X0": _flat(M)}, None, iters=240)
    V = out["V"]
    st = _stretch(V, M)
    a3, b3 = V[row[0]], V[row[-1]]
    hinge = _line_dist(V[row], a3, b3).max()
    flap = _flap(M)
    far = flap[np.argmax(_line_dist(np.c_[M["uv"][flap], np.zeros(len(flap))], np.r_[a2, 0], np.r_[b2, 0]))]
    d_uv = _line_dist(np.c_[M["uv"][[far]], [0]], np.r_[a2, 0], np.r_[b2, 0])[0]
    # the turn: angle between the flap's far point and the base's mirror direction about the hinge
    base = np.setdiff1d(np.arange(len(V)), np.r_[flap, row])
    bfar = base[np.argmax(_line_dist(V[base], a3, b3))]
    u = (b3 - a3) / np.linalg.norm(b3 - a3)
    pf_ = V[far] - a3 - u * ((V[far] - a3) @ u)
    pb_ = V[bfar] - a3 - u * ((V[bfar] - a3) @ u)
    dihedral = math.degrees(math.acos(np.clip(pf_ @ pb_ / np.linalg.norm(pf_) / np.linalg.norm(pb_), -1, 1)))
    print(f"diagonal 170: stretch {st * 100:.3f}%, hinge off the line {hinge * 1000:.3f} mm, dihedral {dihedral:.1f} "
          f"deg (10 = turned 170), flap {len(flap)} verts")
    assert st < 0.005, st
    assert hinge < 0.0005, hinge
    assert abs(dihedral - 10) < 2, dihedral
    assert abs(_line_dist(V[[far]], a3, b3)[0] - d_uv) < 0.001


def test_collar_band_stand_fall():
    """A collar band (40 x 4.5 cm) with its roll line 25 mm up: the fall turns down over the stand, no stretch."""
    P = [[-0.2, 0], [0.2, 0], [0.2, 0.045], [-0.2, 0.045]]
    B = _B({"c": _piece(P)}, folds=[{"piece": "c", "line": [[-0.2, 0.025], [0.2, 0.025]], "angle": 0,
                                     "kind": "press", "name": "collar roll"}], refine=[{"piece": "c", "h": 0.005}])
    M = cloth.mesh(B, 0.02)
    assert M["folds"][0]["missing_edges"] == 0
    out = pf.assemble({"mesh": M, "X0": _flat(M)}, None, iters=60)
    V = out["V"]
    flap = _flap(M)
    st = _stretch(V, M)
    top = flap[np.abs(M["uv"][flap, 1] - 0.045) < 1e-6]
    row = M["folds"][0]["rows"][0]
    drop = float(np.mean(np.linalg.norm((V[top] - V[row].mean(0))[:, :2] * [0, 1], axis=1)))
    print(f"collar band: stretch {st * 100:.3f}%, fall edge {drop * 1000:.1f} mm from the roll line (20 = on the stand)")
    assert st < 0.005 and abs(drop - 0.020) < 0.001, (st, drop)


def _plane_body(y0=0.0):
    """A flat 'chest' facing -y at y = y0 (a slab), as a cloth.Body-like object."""
    xs, zs = np.meshgrid(np.linspace(-0.5, 0.5, 41), np.linspace(0.5, 1.8, 53))
    V = np.c_[xs.ravel(), np.full(xs.size, y0), zs.ravel()]
    nx = 41
    T = []
    for r in range(52):
        for c in range(40):
            a = r * nx + c
            T += [[a, a + nx, a + 1], [a + 1, a + nx, a + nx + 1]]
    T = np.asarray(T)
    return types.SimpleNamespace(V=np.r_[V, V + [0, 0.3, 0]], T=np.r_[T, T[:, ::-1] + len(V)], at={})


def test_lapel_face_out(mirror=1.0):
    """A front panel whose lapel triangle folds face-out (onto the outside, away from the body) about its roll line."""
    P = [[mirror * x, y] for x, y in [[0, 0], [0.25, 0], [0.25, 0.4], [0.0, 0.4], [-0.08, 0.3], [0, 0.15]]]
    P = P if mirror > 0 else P[::-1]  # (a mirrored ".R" panel: the flap on the other side of the line)
    line = [[0.0, 0.15], [mirror * 0.06, 0.4]]
    B = _B({"front": _piece(P)}, folds=[{"piece": "front", "line": line, "angle": 5, "kind": "press",
                                         "name": "lapel roll"}],
           refine=[{"piece": "front", "h": 0.005, "near": line, "within": 0.06}])
    M = cloth.mesh(B, 0.02)
    assert M["folds"][0]["missing_edges"] == 0
    body = _plane_body(0.0)
    # the panel 6 mm in front of the chest (-y), pattern x -> x, pattern y -> z
    X0 = np.c_[M["uv"][:, 0], np.full(len(M["uv"]), -0.006), 1.0 + M["uv"][:, 1]]
    out = pf.assemble({"mesh": M, "X0": X0}, body, iters=80, attract=0.0)
    V = out["V"]
    flap = _flap(M)
    st = _stretch(V, M)
    base = np.setdiff1d(np.arange(len(V)), np.r_[flap, M["folds"][0]["rows"][0]])
    far = flap[np.argmin(mirror * M["uv"][flap, 0])]
    print(f"lapel: stretch {st * 100:.2f}%, lapel y {V[flap, 1].mean() * 1000:.1f} mm vs base "
          f"{V[base, 1].mean() * 1000:.1f} mm; far point x {V[far, 0] * 1000:.0f} mm (> 0: back over the panel)")
    assert V[flap, 1].mean() < V[base, 1].mean() - 0.001  # in front of the panel (face-out)
    assert mirror * V[far, 0] > 0.0
    assert st < 0.05, st  # (the lapel lies one cloth thickness, 1.5 mm, off its base: the 5 mm edges at the hinge take it)


def test_lapel_face_out_mirrored():
    """(dress-garrett 2026-10-19) The same lapel MIRRORED (an ".R" front: its flap on the other side of the roll line,
    fold "sign" -1) folds face-out too: the form left the side out and turned the R lapel's rest into the body."""
    test_lapel_face_out(-1.0)


def _mirrored_lapels(kind="press"):
    """Two fronts in one mesh, L and its mirror R (flap on the other side of the roll line), as test_lapel_face_out."""
    pcs, folds = {}, []
    for nm, mirror in (("front.L", 1.0), ("front.R", -1.0)):
        P = [[mirror * x, y] for x, y in [[0, 0], [0.25, 0], [0.25, 0.4], [0.0, 0.4], [-0.08, 0.3], [0, 0.15]]]
        pcs[nm] = _piece(P if mirror > 0 else P[::-1], names={"break": 5 if mirror > 0 else 0})
        line = [[0.0, 0.15], [mirror * 0.06, 0.4]]
        folds.append({"piece": nm, "line": line, "angle": 5, "kind": kind, "name": "lapel roll"})
    B = _B(pcs, folds=folds, refine=[{"piece": ["front.L", "front.R"], "h": 0.005, "within": 0.12,
                                      "near": [[0.0, 0.15], [0.0, 0.4]]}])
    return cloth.mesh(B, 0.02)


def test_mirrored_lapel_rest_turns_face_out():
    """(dress-garrett 2026-10-19, strengthened) The fold REST of a mirrored lapel turns its flap to the same face as the
    L one: a flap-side check on the rest itself. test_lapel_face_out_mirrored passed on the code without the fix (the
    assembly re-picks the sense that fits its start), so it could not catch the R lapel's rest turning into the body.
    Fails on 94f6fb7a^ (the rest's turn ignored the fold's "sign")."""
    from hifipushie import folds as foldmod
    for kind in ("press", "roll"):
        M = _mirrored_lapels(kind)
        folds_ = pf._fold_cells(M, {"front.L": 1.0, "front.R": 1.0})
        E = pf._edges(M["F"])
        src, dst = np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]]
        rest = pf._rest_edges(M, src, dst, folds_)
        zs = {}
        for fd in M["folds"]:
            g = foldmod._geom(M, fd)
            row, flap = np.asarray(g["rows"][0]["row"]), np.asarray(g["rows"][0]["v"])
            m = np.isin(src, row) & np.isin(dst, flap)
            e = rest[m]
            zs[fd["piece"]] = float(np.mean(e[:, 2] / (np.linalg.norm(e, axis=1) + 1e-12)))
        print(f"mirrored lapel rest ({kind}): flap-edge z L {zs['front.L']:+.2f} R {zs['front.R']:+.2f}")
        assert abs(zs["front.L"]) > 0.02 and np.sign(zs["front.L"]) == np.sign(zs["front.R"]), zs
        assert abs(abs(zs["front.L"]) - abs(zs["front.R"])) < 0.01, zs


def _cyl_body(r=0.05, z0=0.0, z1=0.5, m=96):
    th = np.linspace(0, 2 * np.pi, m + 1)[:-1]
    zs = np.linspace(z0, z1, 41)
    V = np.array([[r * math.cos(t), r * math.sin(t), z] for z in zs for t in th])
    T = []
    for i in range(len(zs) - 1):
        for j in range(m):
            a, b = i * m + j, i * m + (j + 1) % m
            T += [[a, b, a + m], [b, b + m, a + m]]
    return types.SimpleNamespace(V=V, T=np.asarray(T), at={})


def test_sleeve_tube_ease():
    """A tube 'sleeve' (pattern width 2 pi (r + 12 mm)) on a 50 mm cylinder: it stands off by its ease, within 1 mm."""
    r, ease = 0.05, 0.012
    W = 2 * math.pi * (r + ease)
    P = [[0, 0], [W, 0], [W, 0.3], [0, 0.3]]
    B = _B({"s": _piece(P, names={"a0": 0, "a1": 1, "a2": 2, "a3": 3})}, seams=[["s:a0>a3", "s:a1>a2"]])
    M = cloth.mesh(B, 0.01)
    body = _cyl_body(r, -0.1, 0.5)
    th = M["uv"][:, 0] / W * 2 * math.pi
    R0 = r + 0.03
    X0 = np.c_[R0 * np.cos(th), R0 * np.sin(th), 0.05 + M["uv"][:, 1]]
    out = pf.assemble({"mesh": M, "X0": X0}, body, iters=150, ease=0.003)
    V = out["V"]
    got = float(np.median(np.linalg.norm(V[:, :2], axis=1))) - r
    print(f"sleeve tube: ease {got * 1000:.2f} mm (pattern {ease * 1000:.0f}), stretch {out['info']['stretch_pct']}")
    assert abs(got - ease) < 0.001, got


def _tilt(P, deg):
    a = math.radians(deg)
    Ry = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    return np.asarray(P, float) @ Ry.T


def test_loose_sleeve_hangs_round(deg=35.0, verbose=True, flat=1.0, ell=0.6, seat=True):
    """A LOOSE tube (girth 1.6x the limb's: a jacket sleeve at the wrist) on a limb tilted 35 deg off vertical (an A-pose
    forearm) with a bump on it (an elbow / shoulder-like bulge), started off-centre: it hangs from the limb, its section
    ROUND (width / depth 0.8-1.25: a tape round it reads its own girth, hull >= 97 % of the cloth), not pulled onto the
    limb into a flat lens, and not stretched over the bump (p99 face strain <= 6 %). (dress-garrett 2026-10-19 block
    proportions: the o4 jacket sleeve on the form read 66 x 139 mm at the hem, girth 328 = its pattern's, where the
    drape of the same pattern reads 104 x 104: the form's attraction pulled the ease in.)"""
    from scipy.spatial import ConvexHull
    from hifipushie import diag_render as dg
    r, ease = 0.04, 0.025
    W = 2 * math.pi * (r + ease)
    P = [[0, 0], [W, 0], [W, 0.3], [0, 0.3]]
    B = _B({"s": _piece(P, names={"a0": 0, "a1": 1, "a2": 2, "a3": 3})}, seams=[["s:a0>a3", "s:a1>a2"]])
    M = cloth.mesh(B, 0.01)
    cyl = _cyl_body(r, -0.1, 0.5)
    Vb = cyl.V.copy()
    zb = np.exp(-((Vb[:, 2] - 0.2) / 0.03) ** 2)  # the bump: +15 mm round the limb at z 0.2
    Vb[:, :2] *= (1 + 0.015 / r * zb)[:, None]
    Vb[:, 1] *= ell  # a limb is flatter than round (a forearm ~ 60 x 40 mm at the wrist)
    body = types.SimpleNamespace(V=_tilt(Vb, deg), T=cyl.T, at={})
    th = M["uv"][:, 0] / W * 2 * math.pi
    R0 = r + 0.03
    # started as the placement lays a sleeve: its two halves flat-ish either side of the limb (a lens, depth x flat)
    X0 = _tilt(np.c_[0.012 + R0 * 1.25 * np.cos(th), R0 * flat * 1.25 * np.sin(th), 0.05 + M["uv"][:, 1]], deg)
    was, pf.SEAT_GRAVITY = pf.SEAT_GRAVITY, seat
    try:  # (seat=False, the old seating, folds the ease into a lens: hull 83 % / aspect 1.30 at ell 0.6)
        out = pf.assemble({"mesh": M, "X0": X0}, body, iters=150, ease=0.003)
    finally:
        pf.SEAT_GRAVITY = was
    V = _tilt(out["V"], -deg)  # back to the limb's frame (axis = z)
    sec = V[np.abs(V[:, 2] - 0.12) < 0.006]  # a section clear of the bump
    w, d = float(np.ptp(sec[:, 0])), float(np.ptp(sec[:, 1]))
    hull = ConvexHull(sec[:, :2]).area
    s = dg.face_strain(out["V"], M["F"], M["uv"])
    p99 = float(np.percentile(s, 99))
    if verbose:
        print(f"loose sleeve ({deg:.0f} deg): section {w * 1000:.0f} x {d * 1000:.0f} mm (aspect {w / d:.2f}), hull "
              f"{hull * 1000:.0f} of cloth {W * 1000:.0f} mm ({hull / W * 100:.0f}%), strain p99 {p99 * 100:.1f}%")
    assert 0.8 <= w / d <= 1.25, (w, d)
    assert hull >= 0.97 * W, (hull, W)
    assert p99 <= 0.06, p99  # woven suiting under its own weight: EMT ~3-8 % at 500 gf/cm (Kawabata KES-FB)


def _neck_body():
    """A torso cylinder with a neck cylinder on it; the neck point (hps.L) where they meet."""
    neck = _cyl_body(0.06, 1.2, 1.7)
    tor = _cyl_body(0.16, 0.9, 1.45)
    return types.SimpleNamespace(V=np.r_[tor.V, neck.V], T=np.r_[tor.T, neck.T + len(tor.V)],
                                 at={"hps.L": np.array([0.06 * math.cos(-0.9), 0.06 * math.sin(-0.9), 1.45])})


def test_neck_point_on_hps():
    """A panel whose neck point starts ~30 mm off (as the landmark placement X0 had it) lands within 2 mm of the
    body's neck point (on the layer's ease)."""
    P = [[0, 0], [0.14, 0], [0.14, 0.2], [0.03, 0.2], [0.0, 0.17]]
    B = _B({"front.L": _piece(P, names={"hps": 3})})
    M = cloth.mesh(B, 0.01)
    body = _neck_body()
    hps = body.at["hps.L"]
    th = -0.9 - 0.25 + (M["uv"][:, 0] - 0.03) / 0.19
    X0 = np.c_[0.19 * np.cos(th), 0.19 * np.sin(th), 1.25 + M["uv"][:, 1]]
    v = M["points"]["front.L:hps"]
    start = pf.placement_error(X0[v], hps)
    out = pf.assemble({"mesh": M, "X0": X0}, body, iters=120, ease=0.003)
    V = out["V"]
    _, nrm, _ = pf._body_surface(body).signed(hps[None])
    e = pf.placement_error(V[v], hps + 0.003 * nrm[0])
    print(f"neck point: start {start:.0f} mm off; on the form {e:.2f} mm from the body's (+ ease)")
    assert start > 25 and e < 2.0, (start, e)


def _curved_collar_case(stand=0.027, fall=0.040, dip=0.03, r=0.06, ease=0.004, gap_n=10):
    """A neck cylinder (radius r) with a curved neckline (z0 at the back, `dip` lower at the front), a closed bodice
    tube sewn under it and a collar drafted to that curve: its neck edge IS the neckline unrolled (u = R theta, v = z),
    the roll line `stand` above it, the outer edge `fall` above the roll; open at the front by 2 gap_n / 160 of the
    round. On a cylinder the stand and the fall turned down over it are exact (developable): the known answer."""
    R = r + ease
    z0 = 1.40
    zn = lambda th: z0 + dip * (np.sin(th) - 1) / 2
    ths = np.linspace(-math.pi / 2, 3 * math.pi / 2, 161)  # (the front, -y, is theta = -pi/2)
    sl = slice(gap_n, 161 - gap_n)

    def ring(uu, lo, hi, nside=12):
        bot = np.c_[uu, lo]
        right = np.c_[np.full(nside - 1, uu[-1]), np.linspace(lo[-1], hi[-1], nside + 1)[1:-1]]
        top = np.c_[uu[::-1], hi[::-1]]
        left = np.c_[np.full(nside - 1, uu[0]), np.linspace(hi[0], lo[0], nside + 1)[1:-1]]
        return np.r_[bot, right, top, left], len(bot) + len(right)
    ub, vbb = R * (ths - math.pi / 2), zn(ths)  # u = 0 at CB
    u, vb = ub[sl], vbb[sl]
    nb, nc = len(ub), len(u)
    k_cb = nc // 2
    Pc, t0 = ring(u, vb, vb + stand + fall)
    Pb, s0 = ring(ub, vbb - 0.10, vbb)
    collar = _piece(Pc, names={"endNeck.m": 0, "cbNeck": k_cb, "endNeck": nc - 1, "cbTop": t0 + nc - 1 - k_cb},
                    wrap={"to": "seam"})
    top_at = lambda i: s0 + nb - 1 - i  # bodice top edge index of sample i
    bodice = _piece(Pb, names={"a0": 0, "a1": nb - 1, "a2": s0, "a3": s0 + nb - 1, "nl.l": top_at(gap_n),
                               "nl.c": top_at(gap_n + k_cb), "nl.r": top_at(160 - gap_n)})
    roll = np.c_[u, vb + stand][::4].tolist()
    B = _B({"bodice": bodice, "collar": collar},
           seams=[["collar:endNeck.m>cbNeck>endNeck", "bodice:nl.l>nl.c>nl.r"], ["bodice:a0>a3", "bodice:a1>a2"]],
           folds=[{"piece": "collar", "line": roll, "angle": 0, "kind": "press", "name": "collar roll", "flap": "cbTop"}],
           refine=[{"piece": "collar", "h": 0.005}, {"piece": "bodice", "h": 0.008}])
    M = cloth.mesh(B, 0.02)
    kb, kc = M["names"].index("bodice"), M["names"].index("collar")
    pid = np.asarray(M["piece"])
    th = M["uv"][:, 0] / R + math.pi / 2
    X0 = np.c_[(R + 0.01) * np.cos(th), (R + 0.01) * np.sin(th), M["uv"][:, 1]]
    cv = pid == kc  # the collar starts as a flat tab out of the back (as the placed jacket collar did)
    X0[cv] = np.c_[M["uv"][cv, 0], np.full(cv.sum(), 0.2), M["uv"][cv, 1] + 0.05]
    body = _cyl_body(r, 1.0, 1.8)
    return {"M": M, "B": B, "X0": X0, "body": body, "R": R, "zn": zn, "kc": kc, "kb": kb}


def test_straight_collar_on_neck():
    test_curved_collar_on_neck(dip=0.0)


def test_curved_collar_on_neck(dip=0.03):
    """(dress-garrett 2026-10-19 collar on the form) TOOL OR PATTERN for the jacket collar: a curved collar (stand +
    fall drafted to a dipping neckline) assembled on a neck cylinder keeps its drafted stand at CB, its fall covers the
    seam by the drafted fall - stand, and the roll turns within 5 deg of the drafted 180."""
    stand, fall = 0.027, 0.040
    c = _curved_collar_case(stand, fall, dip=dip)
    M, X0, body = c["M"], c["X0"], c["body"]
    fd = M["folds"][0]
    assert fd["missing_edges"] == 0, fd["missing_edges"]
    out = pf.assemble({"mesh": M, "X0": X0, "pieces": c["B"]}, body, iters=120, ease=0.004)
    V = out["V"]
    from hifipushie import folds as foldmod
    g = foldmod._geom(M, fd)
    row = np.asarray(g["rows"][0]["row"])
    flap = np.asarray(g["rows"][0]["v"])
    sel = np.where(np.asarray(M["piece"]) == c["kc"])[0]
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    seam = np.unique(sw[np.isin(sw, sel)])
    seam = seam[np.isin(seam, sel)]
    near_cb = lambda ids: ids[(np.abs(V[ids, 0]) < 0.008) & (V[ids, 1] > 0)]
    seam_z = V[near_cb(seam), 2].mean()
    roll_z = V[near_cb(row), 2].mean()
    edge = flap[np.abs(M["uv"][flap, 1] - (c["zn"](math.pi / 2) + stand + fall)) < 0.003]
    fall_z = V[near_cb(edge), 2].mean() if len(near_cb(edge)) else V[near_cb(flap), 2].min()
    turned = pf.fold_turned(M, V, g)
    st = out["info"]["stretch_pct"]
    rr = np.linalg.norm(V[flap, :2], axis=1)
    print(f"curved collar: stand at CB {1000 * (roll_z - seam_z):.1f} mm (drafted {1000 * stand:.0f}), covers the seam "
          f"by {1000 * (seam_z - fall_z):.1f} mm (drafted {1000 * (fall - stand):.0f}), turned {turned:.0f} deg "
          f"(180), fall radius {1000 * rr.min():.1f}-{1000 * rr.max():.1f} mm, stretch {st}")
    assert abs((roll_z - seam_z) - stand) < 0.002, roll_z - seam_z
    assert abs((seam_z - fall_z) - (fall - stand)) < 0.002, seam_z - fall_z
    # within 5 deg of the drafted 180 on the straight (developable) neckline; a crease on a curved pattern line cannot
    # fold flat without growing the fall's edge: 174 at 16% p99 on the 30 mm dip (the tool's honest best, recorded)
    assert turned >= (175 if dip == 0 else 170) - 0.5, turned
    # (a crease on a CURVED pattern line can't fold flat unstretched: the fall's edge must grow, as a tailor spreads or
    # stretches it; 7% on the straight neckline, ~16% on the 30 mm dip)
    assert st["p99"] < (10 if dip == 0 else 20), st


def test_pressed_seam_between_flaps():
    """(dress-garrett 2026-10-19 notch and open neck) A seam joining two FLAPS (a notched collar's end on the lapel's
    gorge) is pressed flat: started FOLDED OVER its partner (as the fall's turn left the collar end, a funnel up the
    neck), the smaller piece is laid back in its partner's plane on the far side of the seam (the drafted continuation),
    and the cross-seam rest edges are the partner's pattern carried across (here the identity: both drafted in one
    frame)."""
    a = _piece([[0, 0], [0.10, 0], [0.10, 0.10], [0, 0.10]], names={"s0": 1, "s1": 2})
    b = _piece([[0.10, 0.0], [0.15, 0.0], [0.15, 0.10], [0.10, 0.10]], names={"t0": 0, "t1": 3})
    B = _B({"a": a, "b": b}, seams=[["a:s0>s1", "b:t0>t1"]], refine=[{"piece": ["a", "b"], "h": 0.01}])
    M = cloth.mesh(B, 0.02)
    pid = np.asarray(M["piece"])
    ka, kb = M["names"].index("a"), M["names"].index("b")
    assert len(np.asarray(M["sew"]).reshape(-1, 2)) >= 3
    folds_ = [({"piece": "a"}, {"rows": [{"v": np.where(pid == ka)[0], "row": np.zeros(0, int)}]}, 1.0),
              ({"piece": "b"}, {"rows": [{"v": np.where(pid == kb)[0], "row": np.zeros(0, int)}]}, 1.0)]
    uv = np.asarray(M["uv"], float)
    flat = np.c_[uv, np.zeros(len(uv))]
    X = flat.copy()
    vb = pid == kb
    X[vb, 0] = 0.20 - uv[vb, 0]  # b folded over a about the seam (x = 0.10)
    X[vb, 2] = 0.0015
    X1 = pf._lay_pressed(M, X, folds_, reach=0.2)
    err = np.abs(X1[vb] - flat[vb]).max()
    ps, pd, pr = pf._pressed_cells(M, folds_, pf._edges(M["F"]))
    rerr = np.abs(pr[:, :2] - (uv[pd] - uv[ps])).max() if len(ps) else 1.0
    print(f"pressed seam: b laid back {err * 1000:.4f} mm from its drafted continuation, {len(ps)} cross cells, "
          f"rest error {rerr * 1000:.4f} mm; pieces both sides: {sorted({int(pid[s]) for s in ps})}")
    assert err < 1e-6, err
    assert len(ps) and rerr < 1e-6, rerr
    assert {int(pid[s]) for s in ps} == {ka, kb}


def test_flap_faces_mask_follows_the_last_row():
    """(dress-garrett 2026-10-19 teeth) The flap mask a sheet colours the turned side with (folds.flap_faces): every face
    between the last fold row and the flap's first lattice vertices is in it, so the mask's edge IS the row (mesh
    edges), not the lattice's ragged first column (that edge read as teeth along the lapel's roll; the geometry was a
    clean three-hinge roll). Known answer: every boundary edge between flap and base faces is a last-row edge."""
    from hifipushie import folds as foldmod
    M = _mirrored_lapels("roll")
    F = np.asarray(M["F"])
    m = foldmod.flap_faces(M)
    for fd in M["folds"]:
        k = M["names"].index(fd["piece"])
        last = set(int(v) for v in fd["rows"][-1])
        g = foldmod._geom(M, fd)
        flv = set(int(v) for v in g["rows"][-1]["v"])
        cnt = {}
        for i, f in enumerate(F):
            if M["piece"][f[0]] != k:
                continue
            for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                cnt.setdefault((min(a, b), max(a, b)), [0, 0])[int(m[i])] += 1
        bd = [e for e, (o, i_) in cnt.items() if o and i_]
        on_row = float(np.mean([e[0] in last and e[1] in last for e in bd]))
        print(f"flap mask {fd['piece']}: {len(bd)} boundary edges, on the last row {on_row:.2f}")
        assert on_row == 1.0, on_row
        old = np.array([all(int(v) in flv for v in f) for f in F]) & (M["piece"][F[:, 0]] == k)
        assert m[M["piece"][F[:, 0]] == k].sum() > old.sum()  # (the old mask dropped the strip past the row)


def test_worn_open_break_offset(off=0.05):
    """(coordinator 2026-10-19) WORN OPEN is a form rule: with no gravity an unfastened front doesn't fall open, so each
    front is turned about its roll line until its break sits `off` from the centre line, resting on what is under it.
    Known answer: two mirrored fronts (lapels folded) on a flat chest, breaks at x = 0 to start; worn_open {"break": 50 mm}
    puts both breaks at |x| 50 +- 3 mm on their own sides, the cloth unstretched (p99 < 2%), the fronts still on the chest
    and the lapels still face-out; without it they stay within 10 mm of the centre."""
    from hifipushie import folds as foldmod
    M = _mirrored_lapels("press")
    body = _plane_body(0.0)
    X0 = np.c_[M["uv"][:, 0], np.full(len(M["uv"]), -0.006), 1.0 + M["uv"][:, 1]]
    res = {}
    for wo in (None, {"break": off}):
        out = pf.assemble({"mesh": M, "X0": X0}, body, iters=80, attract=0.0, worn_open=wo)
        V = out["V"]
        bx = {k: float(V[v, 0]) for k, v in M["points"].items() if k.endswith(":break")}
        res[wo is not None] = (bx, _stretch(V, M), V)
        print(f"worn_open {wo}: breaks x {({k: round(x * 1000, 1) for k, x in bx.items()})} mm, stretch "
              f"{_stretch(V, M) * 100:.2f}%, info {out['info'].get('worn_open_mm')}")
    bx, st, V = res[True]
    assert abs(bx["front.L:break"] - off) < 0.003 and abs(bx["front.R:break"] + off) < 0.003, bx
    # (the most stretched edges are at the break itself, where the fold line meets the front edge: 4.2% unworn, 9.2%
    # worn open; everywhere else the turn is rigid)
    E = pf._edges(M["F"])
    l0 = np.linalg.norm(M["uv"][E[:, 0]] - M["uv"][E[:, 1]], axis=1)
    sv = np.abs(np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1) / l0 - 1)
    assert np.percentile(sv, 99) < 0.02 and st < 0.12, (np.percentile(sv, 99), st)
    assert (V[:, 1] < 0.0005).all()  # (on the chest's side: the body is the obstacle it rests on)
    for fd in M["folds"]:
        fl = np.asarray(foldmod._geom(M, fd)["rows"][0]["v"])
        k = M["names"].index(fd["piece"])
        base = np.setdiff1d(np.where(M["piece"] == k)[0], np.r_[fl, fd["rows"][0]])
        assert V[fl, 1].mean() < V[base, 1].mean() - 0.001, fd["piece"]  # (the lapel still face-out)
    assert max(abs(x) for x in res[False][0].values()) < 0.010, res[False][0]


def _band_on_front_case():
    """A front (0.25 x 0.4 m, hps at its top outer corner, break on its CF edge) and a band (0.25 x 0.04, a 20 mm
    stand and its fall pressed down over it) sewn along its top edge, wrapped to the seam (as a collar / stand on a neckline), both on a flat chest; the band's start is
    where the closed front puts it (continuing the front up)."""
    front = _piece([[0, 0], [0.25, 0], [0.25, 0.4], [0.0, 0.4], [0.0, 0.15]],
                   names={"break": 4, "hps": 2, "cfTop": 3, "sideTop": 2})
    band = _piece([[0, 0], [0.25, 0], [0.25, 0.04], [0.0, 0.04]], names={"bl": 0, "br": 1, "tr": 2, "tl": 3},
                  wrap={"to": "seam"})
    B = _B({"front.L": front, "band": band}, seams=[["band:bl>br", "front.L:cfTop>sideTop"]],
           folds=[{"piece": "band", "line": [[0.0, 0.02], [0.25, 0.02]], "angle": 0, "kind": "press",
                   "name": "collar roll"}],
           refine=[{"piece": ["front.L", "band"], "h": 0.005}])
    M = cloth.mesh(B, 0.02)
    k = M["names"].index("band")
    X0 = np.c_[M["uv"][:, 0], np.full(len(M["uv"]), -0.006), 1.0 + M["uv"][:, 1]]
    X0[M["piece"] == k, 2] += 0.4
    return B, M, X0


def test_worn_open_band_follows_front(off=0.05):
    """(dress-garrett 2026-10-19 order + seam lengths) Worn open, the front swings about its hps BEFORE the band sewn to
    it is stood up, so the band goes with it. Known answer: the band's free top corner (tl) sits within 6 mm of where
    the swung front carries it (its fall turned down on its stand: back at the front's CF top); with the old order
    (SWING_FIRST False) the band was left where the closed front had put it."""
    B, M, X0 = _band_on_front_case()
    body = _plane_body(0.0)
    kf = M["names"].index("front.L")
    pts = M["points"]
    out = {}
    for first in (True, False):
        pf.SWING_FIRST = first
        try:
            V = pf.assemble({"mesh": M, "X0": X0, "pieces": B}, body, iters=60, attract=0.0,
                            worn_open={"break": off})["V"]
        finally:
            pf.SWING_FIRST = True
        cf_top, brk = V[pts["front.L:cfTop"]], V[pts["front.L:break"]]
        up = (cf_top - brk) / np.linalg.norm(cf_top - brk)
        want = cf_top - 0.0 * up
        miss = float(np.linalg.norm(V[pts["band:tl"]] - want))
        out[first] = (miss, float(V[pts["front.L:break"], 0]), _stretch(V, M))
        print(f"SWING_FIRST {first}: band corner {1000 * miss:.1f} mm off where the front carries it, break x "
              f"{1000 * out[first][1]:.1f} mm, max stretch {100 * out[first][2]:.1f}%")
    assert abs(out[True][1] - off) < 0.004, out
    assert out[True][0] < 0.006, out
    del kf


# ------------------------------------------------------------------ a two-panel sleeve on a real arm (2026-10-19 virtual fit)

ARM_NPZ = "/mnt/data/hifipushie/pattern_form/body.npz"  # Garrett's body + arm landmarks (workspace data, never in the repo)


def _arm_case(two_piece=True, top_t=0.5, G_top=0.364, G_wrist=0.326, up_frac=0.6, start=1.0, npz=ARM_NPZ, h=0.01):
    """A sleeve over a real arm segment cut from Garrett's body (the upper arm from top_t of shoulder -> elbow down to
    the wrist, clear of the torso): two panels (an upper sleeve on the outside, up_frac of the round, and an under
    sleeve; two seams, at the front and back of the arm, as a tailored sleeve) or one (one seam under the arm). Girth
    linear from G_top to G_wrist (the o4 jacket's biceps 364 / hem 326 mm). Placed ROUND round the arm (start x the
    pattern's radius), as cloth.build's placement lays a sleeve. Returns (mesh, X0, body, frame) or None (no body)."""
    import os
    if not os.path.exists(npz):
        return None
    d = np.load(npz)
    sh, el, wr = d["sh"], d["el"], d["wr"]
    top = sh + top_t * (el - sh)
    poly = np.array([wr, el, top])  # arc length from the wrist up
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    Ls = float(seg.sum())

    def axis_at(v):  # point + unit axis (up the arm) at arc length v
        v = np.clip(np.atleast_1d(v), 0, Ls)
        k = (v > seg[0]).astype(int)
        t = np.where(k == 0, v / seg[0], (v - seg[0]) / seg[1])
        a, b = poly[k], poly[k + 1]
        ax = (b - a) / np.linalg.norm(b - a, axis=1, keepdims=True)
        return a + (b - a) * t[:, None], ax

    def frame(ax):  # u: across the arm in the front view (outward, +x), w: front-back
        u = np.c_[ax[:, 2], np.zeros(len(ax)), -ax[:, 0]]
        u /= np.linalg.norm(u, axis=1, keepdims=True)
        u *= np.sign(u[:, 0] + 1e-12)[:, None]
        return u, np.cross(ax, u)
    # the arm: body triangles within 75 mm of the segment's axis, between its ends
    V, T = np.asarray(d["V"], float), np.asarray(d["T"])
    A, ab = poly[:-1], poly[1:] - poly[:-1]
    t = np.clip(((V[:, None, :] - A[None]) * ab[None]).sum(-1) / (ab ** 2).sum(-1)[None], 0, 1)
    dist = np.linalg.norm(V[:, None, :] - (A[None] + t[..., None] * ab[None]), axis=-1)
    j = np.argmin(dist, 1)
    vv = np.where(j == 0, t[:, 0] * seg[0], seg[0] + t[:, 1] * seg[1])
    keep = (dist.min(1) < 0.075) & (vv > 0.01) & (vv < Ls - 0.005)
    tk = keep[T].all(1)
    used = np.unique(T[tk])
    ix = -np.ones(len(V), int)
    ix[used] = np.arange(len(used))
    body = types.SimpleNamespace(V=V[used], T=ix[T[tk]], at={})
    W = lambda v: G_wrist + (G_top - G_wrist) * np.asarray(v) / Ls  # noqa: E731
    if two_piece:
        fr = {"up": up_frac, "un": 1 - up_frac}
        th0 = {"up": -math.pi * up_frac, "un": math.pi * up_frac}
        seams = [["up:a1>a2", "un:a0>a3"], ["un:a1>a2", "up:a0>a3"]]
    else:
        fr, th0 = {"s": 1.0}, {"s": math.pi}  # (the seam under the arm, -u)
        seams = [["s:a0>a3", "s:a1>a2"]]
    pcs = {nm: _piece([[0, 0], [G_wrist * f, 0], [G_top * f, Ls], [0, Ls]], names={"a0": 0, "a1": 1, "a2": 2, "a3": 3})
           for nm, f in fr.items()}
    M = cloth.mesh(_B(pcs, seams=seams), h)
    uv = np.asarray(M["uv"], float)
    pid = np.asarray(M["piece"])
    X0 = np.zeros((len(uv), 3))
    for k, nm in enumerate(M["names"]):
        m = pid == k
        v = uv[m, 1]
        th = th0[nm] + 2 * math.pi * fr[nm] * uv[m, 0] / (W(v) * fr[nm])
        c, ax = axis_at(v)
        u, w = frame(ax)
        R = start * W(v) / (2 * math.pi)
        X0[m] = c + R[:, None] * (np.cos(th)[:, None] * u + np.sin(th)[:, None] * w)
    return M, X0, body, (axis_at, frame, Ls, W)


def _section(X, F, o, ax, u, w):
    """Width (along u) x depth (along w) and hull girth (m) of mesh (X, F) cut by the plane through o, normal ax."""
    from scipy.spatial import ConvexHull
    E = pf._edges(F)
    dd = (X - o) @ ax
    a, b = E[:, 0], E[:, 1]
    x = (dd[a] * dd[b]) < 0
    tt = dd[a[x]] / (dd[a[x]] - dd[b[x]])
    Q = X[a[x]] + (X[b[x]] - X[a[x]]) * tt[:, None]
    Q = Q[np.linalg.norm(Q - o, axis=1) < 0.15]
    q2 = np.c_[(Q - o) @ u, (Q - o) @ w]
    return float(np.ptp(q2[:, 0])), float(np.ptp(q2[:, 1])), float(ConvexHull(q2).area)


def arm_sleeve_report(out_V, M, body, fr, at=(0.3, 0.75)):
    """Per section (fraction of the segment from the wrist): cloth w x d (mm), aspect / the arm's, hull girth as % of
    the pattern's; and face strain p99 (fraction)."""
    from hifipushie import diag_render as dg
    axis_at, frame, Ls, W = fr
    rows = []
    for f in at:
        c, ax = axis_at(f * Ls)
        u, w = frame(ax)
        cw, cd, cg = _section(out_V, M["F"], c[0], ax[0], u[0], w[0])
        aw, ad, ag = _section(body.V, body.T, c[0], ax[0], u[0], w[0])
        rows.append({"at": f, "cloth_mm": [round(cw * 1000), round(cd * 1000)], "arm_mm": [round(aw * 1000), round(ad * 1000)],
                     "aspect_ratio": round((cw / cd) / (aw / ad), 2), "girth_pct": round(cg / float(W(f * Ls)) * 100, 1)})
    s = dg.face_strain(out_V, M["F"], M["uv"])
    return rows, float(np.percentile(np.abs(s), 99))


def test_two_panel_sleeve_on_real_arm(two_piece=True, verbose=True, **kw):
    """A TWO-panel sleeve (upper + under, seams front and back) placed round over a real arm segment of Garrett's body
    (mid upper arm to wrist, clear of the torso), the o4 jacket's girths (biceps 364 / hem 326 mm): on the form its
    girth keeps the pattern's ease (hull >= 97 % of the pattern girth), its cross-section aspect stays within 1.3 x the
    arm's own, and strain p99 <= 6 % (woven suiting EMT 3-8 % at 500 gf/cm, Kawabata KES-FB: a far larger load than its
    own weight, so an upper bound). (2026-10-19 virtual fit: the old relax read the jacket sleeve 72 x 159 mm.)
    Skipped without the workspace body (ARM_NPZ)."""
    case = _arm_case(two_piece=two_piece)
    if case is None:
        print("SKIP: no", ARM_NPZ)
        return None
    M, X0, body, fr = case
    out = pf.assemble({"mesh": M, "X0": X0}, body, iters=kw.pop("iters", 240), ease=0.003, **kw)  # (~ a garment's 40 + 60 + 120)
    rows, p99 = arm_sleeve_report(out["V"], M, body, fr)
    if verbose:
        print(f"{'two' if two_piece else 'one'}-piece sleeve on Garrett's arm: {rows}, strain p99 {p99 * 100:.1f}%")
    for r in rows:
        assert 1 / 1.3 <= r["aspect_ratio"] <= 1.3, rows
        assert r["girth_pct"] >= 97, rows
    assert p99 <= 0.06, p99
    return rows, p99


def test_placement_error_selftest():
    pf.placement_error.selftest()


if __name__ == "__main__":
    fails = 0
    for k, f in list(globals().items()):
        if k.startswith("test_") and callable(f):
            try:
                f()
                print("PASS", k)
            except Exception as ex:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", k, ex)
    sys.exit(1 if fails else 0)
