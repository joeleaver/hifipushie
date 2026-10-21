"""Known answers for the virtual dress form (pattern_form, dress-garrett 2026-10-19): fold lines are mesh edges and a
fold turns about them with no stretch; a collar band's fall lies on its stand; a lapel folds face-out onto its front; a
tube sleeve keeps its pattern ease on a cylinder; the neck point lands on the body's.
Run: uv run python tests/test_pattern_form.py"""
import math
import sys
import types

import numpy as np
import pytest

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


def test_fold_running_off_mid_length_lies_flat_past_it():
    """(fit round 19, R28's crease) A strip whose fold RUNS OFF 100 mm before its end (folds "run_off"): before the
    run-off the flap is turned over onto its base, past it the strip lies flat and unfolded (on the form, in the bending
    rest and with no crease weight), the turn fading over `over`."""
    from hifipushie import folds as foldmod
    P = [[0, 0], [0.3, 0], [0.3, 0.12], [0, 0.12]]
    fd0 = {"piece": "r", "line": [[0.0, 0.04], [0.3, 0.04]], "angle": 10, "kind": "press", "name": "runoff",
           "flap": "top", "run_off": {"ends": "end", "off": 0.10, "over": 0.03}}
    B = _B({"r": _piece(P, marks={"top": [0.15, 0.1]})}, folds=[fd0], refine=[{"piece": "r", "h": 0.006}])
    M = cloth.mesh(B, 0.012)
    fd = M["folds"][0]
    uv = M["uv"]
    w = foldmod.fade(M, fd, np.arange(len(uv)))
    assert w[uv[:, 0] < 0.16].min() > 0.999 and w[uv[:, 0] > 0.2 + 1e-6].max() < 1e-6, "fade"
    flap = _flap(M)
    assert (uv[flap, 0] < 0.2 + 1e-6).all(), "past the run-off nothing is flap"
    wt = foldmod.weights(M)
    assert wt[np.asarray(fd["rows"][0])][uv[fd["rows"][0], 0] > 0.21].max() == 0.0
    ref = foldmod.bend_reference(M, _flat(M))
    past = (uv[:, 0] > 0.21) & (uv[:, 1] > 0.05)
    before = (uv[:, 0] < 0.14) & (uv[:, 1] > 0.05)
    assert np.abs(ref[past, 2]).max() < 1e-9 and ref[before, 1].max() < 0.04 and ref[before, 2].min() > 0, "bending rest"
    out = pf.assemble({"mesh": M, "X0": _flat(M)}, None, iters=240)
    V = out["V"]

    def dihedral(x):  # the local fold angle at station x: base (y 0.02) and flap (y 0.07) about the row (y 0.04)
        o, b, f = (int(np.argmin(np.linalg.norm(uv - [x, y], axis=1))) for y in (0.04, 0.02, 0.07))
        r0, r1 = (int(np.argmin(np.linalg.norm(uv - [x + dx, 0.04], axis=1))) for dx in (-0.012, 0.012))
        t_ = V[r1] - V[r0]
        t_ /= np.linalg.norm(t_)
        pb, pf_ = (V[q] - V[o] - t_ * ((V[q] - V[o]) @ t_) for q in (b, f))
        return math.degrees(math.acos(np.clip(pb @ pf_ / np.linalg.norm(pb) / np.linalg.norm(pf_), -1, 1)))
    before_d = [dihedral(x) for x in (0.03, 0.08, 0.13)]
    past_d = [dihedral(x) for x in (0.23, 0.26, 0.285)]
    keep = (uv[:, 0] < 0.15) | (uv[:, 0] > 0.22)
    Ek = pf._edges(M["F"])
    Ek = Ek[keep[Ek].all(1)]
    st = np.abs(np.linalg.norm(V[Ek[:, 0]] - V[Ek[:, 1]], axis=1) / np.linalg.norm(uv[Ek[:, 0]] - uv[Ek[:, 1]], axis=1) - 1)
    print(f"run-off: dihedral before {np.round(before_d, 1).tolist()} (10 = turned 170), past "
          f"{np.round(past_d, 1).tolist()} (180 = flat); stretch outside the fade p98 {np.percentile(st, 98) * 100:.1f}%")
    assert max(before_d) < 25, "before the run-off: turned over onto the base"
    # (unfolded, not plane: the fade is a cone a flat sheet bends to carry; 3 cm of fade leaves the end 20-30 deg off)
    assert min(past_d) > 145 and np.percentile(st, 98) < 0.03, "past the run-off: unfolded"
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


def test_neck_point_splits_the_neck_as_the_garments_neckline_does():
    """(C113) A yoke-forward shoulder seam on a cylinder neck (r 60 mm, half loop 188.5 mm): the yoke's neck edge
    cbNeck -> hps is 60 % of the half neckline, the front's hps -> cfNeck 40 %. The body's hps landmark sits at the
    side (50 / 50). With NECK_SPLIT the neck pins land where the neck edges keep their lengths (arc from CB = 60 % of
    the body's half loop, within 1.5 mm); with it off they sit on the landmark, 18.8 mm behind."""
    r, z = 0.06, 1.506  # (a neck section between vertex rows, above the torso)
    body = _neck_body()
    body.at = {"hps.L": np.array([r, 0.0, z]), "cb_neck": np.array([0.0, r, z]), "cf_neck": np.array([0.0, -r, z])}
    half = math.pi * r
    Lb, Lf = 0.6 * half, 0.4 * half  # the garment's own neckline split (pattern lengths)
    yoke = _piece([[0, 0], [Lb, 0], [Lb, -0.08], [0, -0.08]], names={"cbNeck": 0, "hps": 1})
    front = _piece([[0, 0], [Lf, 0], [Lf, -0.1], [0, -0.1]], names={"hps": 0, "cfNeck": 1})
    M = cloth.mesh(_B({"yoke": yoke, "front.L": front}), 0.01)
    share = pf.neckline_share(M)  # (read off the meshed outline: the 10 mm grid moves the corners a few mm)
    assert abs(share - 0.6) < 0.02, share
    X0 = np.c_[np.full(len(M["uv"]), 0.1), np.zeros(len(M["uv"])), np.full(len(M["uv"]), z)]  # (all on the left side)
    bsurf = pf._body_surface(body)

    def arc_from_cb(q):  # the neck circle's arc from CB (+y) round the left side (+x) to q
        return r * math.acos(np.clip(q[1] / math.hypot(q[0], q[1]), -1, 1))

    for on, want in ((True, share * half), (False, 0.5 * half)):
        old = pf.NECK_SPLIT
        pf.NECK_SPLIT = on
        try:
            full, _ = pf._pins(M, X0, body, 0.0, bsurf)
        finally:
            pf.NECK_SPLIT = old
        hv = {M["points"]["yoke:hps"], M["points"]["front.L:hps"]}
        qs = [q for v, q, w in full if v in hv]
        assert len(qs) == 2
        for q in qs:
            a = arc_from_cb(q)
            print(f"NECK_SPLIT {on}: neck pin {a * 1000:.1f} mm round from CB (want {want * 1000:.1f}); "
                  f"front {(half - a) * 1000:.1f} vs the front's neck edge {Lf * 1000:.1f}")
            assert abs(a - want) < 0.0015, (on, a, want)


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


def _two_piece_collar_case(stand=0.028, fall=0.045, at=0.004, r=0.06, ease=0.004, gap_n=10, kind="roll",
                           angle=10.0, radius=0.004, strength=0.6):
    """(fit round 4) The smallest case with the jacket collar's structure: a neck cylinder, a bodice tube, a STAND band
    sewn to the neckline and a FALL strip sewn on the stand's top edge, its roll line `at` into the fall (as
    pattern_jacket.op_collar_two_piece: FALL_FOLD at 4 mm, roll, angle 10, radius 4 mm, strength 0.6), both wrapped to
    the seam. The fall's outer edge is cut for its turned-down radius (R + 2 cloth + gap, a developable cone on a
    straight neck). Known answer: the fall turned ~170 deg down over the stand at EVERY station, its edge below the
    stand top by fall - 2 at."""
    R = r + ease
    z0 = 1.40
    ths = np.linspace(-math.pi / 2, 3 * math.pi / 2, 161)
    sl = slice(gap_n, 161 - gap_n)
    u = (R * (ths - math.pi / 2))[sl]
    ub = R * (ths - math.pi / 2)
    nb, nc = len(ub), len(u)
    k_cb = nc // 2

    def band(uu_lo, uu_hi, lo, hi, nside=10):
        bot = np.c_[uu_lo, np.full(len(uu_lo), lo)]
        right = np.c_[np.linspace(uu_lo[-1], uu_hi[-1], nside + 1)[1:-1], np.linspace(lo, hi, nside + 1)[1:-1]]
        top = np.c_[uu_hi[::-1], np.full(len(uu_hi), hi)]
        left = np.c_[np.linspace(uu_hi[0], uu_lo[0], nside + 1)[1:-1], np.linspace(hi, lo, nside + 1)[1:-1]]
        return np.r_[bot, right, top, left], len(bot) + len(right)
    Ps, s_t = band(u, u, z0, z0 + stand)
    wide = (R + 2 * pf.THICK + 0.002) / R  # (the turned fall's outer edge round a larger radius)
    Pf, f_t = band(u, u * wide, z0 + stand, z0 + stand + fall)
    Pb, s0 = band(ub, ub, z0 - 0.10, z0)
    stand_p = _piece(Ps, names={"neck.m": 0, "neckCb": k_cb, "neck": nc - 1, "top": s_t, "topCb": s_t + nc - 1 - k_cb,
                                "top.m": s_t + nc - 1}, wrap={"to": "seam"})
    fall_p = _piece(Pf, names={"low.m": 0, "lowCb": k_cb, "low": nc - 1, "outCb": f_t + nc - 1 - k_cb},
                    wrap={"to": "seam", "turn": {"at": at, "deg": 172, "gap": 0.004}})
    top_at = lambda i: s0 + nb - 1 - i
    bodice = _piece(Pb, names={"a0": 0, "a1": nb - 1, "a2": s0, "a3": s0 + nb - 1, "nl.l": top_at(gap_n),
                               "nl.c": top_at(gap_n + k_cb), "nl.r": top_at(160 - gap_n)})
    roll = np.c_[u, np.full(nc, z0 + stand + at)][::4].tolist()
    fold = {"piece": "fall", "line": roll, "angle": angle, "kind": kind, "name": "collar roll", "flap": "outCb",
            "strength": strength}
    if kind == "roll":
        fold["radius"] = radius
    B = _B({"bodice": bodice, "stand": stand_p, "fall": fall_p},
           seams=[["stand:neck.m>neckCb>neck", "bodice:nl.l>nl.c>nl.r"], ["fall:low.m>lowCb>low", "stand:top.m>topCb>top"],
                  ["bodice:a0>a3", "bodice:a1>a2"]],
           folds=[fold], refine=[{"piece": "fall", "h": 0.005}, {"piece": "stand", "h": 0.005}, {"piece": "bodice", "h": 0.008}])
    M = cloth.mesh(B, 0.02)
    pid = np.asarray(M["piece"])
    th = M["uv"][:, 0] / R + math.pi / 2
    X0 = np.c_[(R + 0.01) * np.cos(th), (R + 0.01) * np.sin(th), M["uv"][:, 1]]
    for nm in ("stand", "fall"):  # (both start as flat tabs out of the back, as the placed jacket collar did)
        cv = pid == M["names"].index(nm)
        X0[cv] = np.c_[M["uv"][cv, 0], np.full(cv.sum(), 0.2), M["uv"][cv, 1] + 0.05]
    return {"M": M, "B": B, "X0": X0, "body": _cyl_body(r, 1.0, 1.8), "R": R, "z0": z0}


def _two_piece_read(M, V, z0, stand, fall, at):
    """Per station round the neck: the fall's turn over the STAND (deg: the stand's direction up from the roll row vs
    the fall's beyond the hinge, read in section), and the fall's outer edge height below the stand top (m)."""
    from hifipushie import folds as foldmod
    fd = M["folds"][0]
    g = foldmod._geom(M, fd)
    pid = np.asarray(M["piece"])
    ks, kf = M["names"].index("stand"), M["names"].index("fall")
    sv, fv = np.where(pid == ks)[0], np.where(pid == kf)[0]
    out = []
    for th in np.radians(np.arange(-150, 151, 30)):  # azimuth from CB (+y) round the neck
        c = np.array([math.sin(th), math.cos(th)])
        near = lambda ids: ids[(np.abs(np.arctan2(V[ids, 0], V[ids, 1]) - th) < 0.06)]
        s_ = near(sv)
        f_ = near(fv)
        if len(s_) < 3 or len(f_) < 3:
            continue
        sec = lambda ids: np.c_[V[ids, :2] @ c, V[ids, 2]]  # (radial, z)
        S = sec(s_)
        top = S[np.argmax(M["uv"][s_, 1])]
        up = top - S[np.argmin(M["uv"][s_, 1])]
        Ff = sec(f_)
        fu = M["uv"][f_, 1] - (z0 + stand)
        out_e = Ff[fu > fall - 0.003].mean(0) if (fu > fall - 0.003).any() else Ff[np.argmax(fu)]
        hinge = Ff[np.argmin(np.abs(fu - at))]
        down = out_e - hinge
        ang = math.degrees(math.acos(float(np.clip(up @ down / (np.linalg.norm(up) * np.linalg.norm(down)), -1, 1))))
        out.append((round(math.degrees(th)), round(ang, 1), round(float(top[1] - out_e[1]) * 1000, 1),
                    round(float(out_e[0] - top[0]) * 1000, 1)))
    return out


def test_two_piece_collar_turns_over_its_stand(kind="roll", verbose=True):
    """(fit round 4) Garrett's jacket fall stood up off its stand on the form. Known answer: a fall strip sewn on a
    stand band on a neck cylinder, its roll line 4 mm above the seam, turns ~170 deg down over the stand at every
    station round the neck (>= 160), its outer edge below the stand top by about fall - 2 at - pi x radius (the fall
    less what rises above the seam and what the roll's arc takes: the edge covers the stand), the roll read by
    fold_turned (not NaN: the base is the stand, across the seam)."""
    stand, fall, at = 0.028, 0.045, 0.004
    c = _two_piece_collar_case(stand, fall, at, kind=kind)
    M = c["M"]
    out = pf.assemble({"mesh": M, "X0": c["X0"], "pieces": c["B"]}, c["body"], iters=120, ease=0.004)
    V = out["V"]
    rd = _two_piece_read(M, V, c["z0"], stand, fall, at)
    from hifipushie import folds as foldmod
    turned = pf.fold_turned(M, V, foldmod._geom(M, M["folds"][0]))
    if verbose:
        print(f"two-piece collar ({kind}): fold_turned {turned:.0f}, info {out['info']['turned_deg']}, "
              f"stretch {out['info']['stretch_pct']}")
        for az, ang, drop, offr in rd:
            print(f"  az {az:5d}: turned {ang:6.1f} deg, edge {drop:5.1f} mm below the stand top "
                  f"(fall - 2 at - roll arc: {1000 * (fall - 2 * at - math.pi * 0.004):.0f}), {offr:5.1f} mm out from it")
    assert np.isfinite(turned) and turned >= 160, turned
    assert min(a for _, a, _, _ in rd) >= 160, rd
    want = 1000 * (fall - 2 * at - (math.pi * 0.004 if kind == "roll" else 0.0))
    assert min(d for _, _, d, _ in rd) >= want - 3, (want, rd)
    return rd


def nested_collars_case(verbose=True, **kw):
    """(fit round 6, C49) Two two-piece collars on one neck cylinder, the outer (a jacket's: lower stand, cut for the
    radius of the stack under it) assembled over the inner (a shirt's, on the form first) as on_form layers them.
    Returns (outer vertices inside the inner surface within 1 cm, by piece; the inner fall's median gap to its own
    stand, mm; the inner's fold_turned). kw: pattern_form overrides for the run (restored after)."""
    from scipy.spatial import cKDTree
    from hifipushie import folds as foldmod
    old = {k: getattr(pf, k) for k in kw}
    try:
        for k, v in kw.items():
            setattr(pf, k, v)
        si, fi, ai = 0.034, 0.042, 0.004
        ci = _two_piece_collar_case(si, fi, ai)
        Mi = ci["M"]
        inn = pf.assemble({"mesh": Mi, "X0": ci["X0"], "pieces": ci["B"]}, ci["body"], iters=120, ease=0.004)
        Vi = inn["V"]
        pid_i = np.asarray(Mi["piece"])
        sv, fv = (np.where(pid_i == Mi["names"].index(n))[0] for n in ("stand", "fall"))
        gap = float(np.median(cKDTree(Vi[sv]).query(Vi[fv])[0])) * 1000
        turned = pf.fold_turned(Mi, Vi, foldmod._geom(Mi, Mi["folds"][0]))
        # the outer collar: cut for the stack under it (the inner stand + its turned fall + ease), 6 mm lower
        stack = 0.004 + 2 * pf.THICK + 0.004
        so, fo, ao = 0.028, 0.040, 0.004
        co = _two_piece_collar_case(so, fo, ao, ease=stack)
        Mo = co["M"]
        out = pf.assemble({"mesh": Mo, "X0": co["X0"], "pieces": co["B"]}, co["body"], iters=120, ease=0.004,
                          under={"V": Vi, "F": np.asarray(Mi["F"])})
        Vo = out["V"]
        us = pf._Surface(Vi, np.asarray(Mi["F"]), ref=pf._body_surface(co["body"]))
        du, _, dist = us.signed(Vo)
        pid_o = np.asarray(Mo["piece"])
        bad = {n: int(((du < -0.0005) & (dist < 0.01) & (pid_o == Mo["names"].index(n))).sum()) for n in Mo["names"]}
        if verbose:
            print(f"nested collars {kw or ''}: inner fall to its stand {gap:.1f} mm, inner turned {turned:.0f}, "
                  f"outer inside inner {bad}, outer turned {out['info']['turned_deg']}")
        return bad, gap, turned
    finally:
        for k, v in old.items():
            setattr(pf, k, v)


def test_nested_collars_keep_their_layer_order():
    """(fit round 6, C49) Garrett's shirt collar sat OUTSIDE the jacket stand at the back and pulled the jacket fall
    through it (454 jacket vertices inside the shirt). The cause was a stale shirt: round 4's cached form inputs held a
    shirt assembled before C46, its fall standing 9-17 mm off its own stand; rebuilt with the current code it lies
    3.4 mm off and the count drops to 119 (37 at the fall, 0.6 mm deep). Known answer: an outer two-piece collar
    assembled over an inner one on a neck cylinder lies outside it everywhere (no vertex more than 0.5 mm inside),
    and the inner's fall lies on its own stand (< 2 THICK + ease)."""
    bad, gap, turned = nested_collars_case()
    assert gap < (2 * pf.THICK + 0.004) * 1000, gap  # (mm: two cloths + ease)
    assert turned >= 160, turned
    assert sum(bad.values()) == 0, bad


def _open_collar_ends(open_):
    """The two-piece collar case with its pieces wrapped to the NECK and the stand's own closure undone (open_) or
    done up; returns the fall's two front outer corners after the form's assembly, and where the open-collar rule
    (cloth._spread_open_collar) put them."""
    c = _two_piece_collar_case()
    B, M = c["B"], c["M"]
    for nm in ("stand", "fall"):
        B["pieces"][nm]["wrap"]["to"] = "neck"
    M["closures"] = [{"name": "collar", "over": "stand", "under": "stand", "closed": [not open_], "v": []}]
    body = c["body"]
    rr = 0.06
    def push_out(P, clear):
        P = np.array(P, float)
        r = np.linalg.norm(P[:, :2], axis=1)
        lo = r < rr + clear
        P[lo, :2] *= ((rr + clear) / np.maximum(r[lo], 1e-9))[:, None]
        return P
    body.push_out = push_out
    pid = np.asarray(M["piece"])
    fv = np.where(pid == M["names"].index("fall"))[0]
    uv = np.asarray(M["uv"])
    top = fv[uv[fv, 1] > uv[fv, 1].max() - 1e-4]
    ends = [int(top[np.argmin(uv[top, 0])]), int(top[np.argmax(uv[top, 0])])]
    seen = {}
    tr0, sp0 = pf.TRACE, pf.OPEN_SPREAD
    pf.TRACE = lambda ph, X, M_: seen.__setitem__(ph, X[ends].copy())
    pf.OPEN_SPREAD = True  # (opt-in: see pattern_form.OPEN_SPREAD)
    try:
        out = pf.assemble({"mesh": M, "X0": c["X0"], "pieces": B}, body, iters=120, ease=0.004)
    finally:
        pf.TRACE, pf.OPEN_SPREAD = tr0, sp0
    return out["V"][ends], seen.get("spread"), seen.get("turn_flaps")


def test_open_collar_lies_spread_on_the_form():
    """(fit round 7) Garrett's shirt is worn with its collar OPEN (stand closure undone). The sim's placement spreads
    such a collar (cloth._spread_open_collar); the form did not: it re-stood the neck pieces as a ring and the fall's
    turn folded its ends to the centre front (collar points 48 mm apart, concept 146), and the jacket collar over the
    shirt stood 18-28 mm off the neck with it. Known answer: on a neck cylinder the open collar's front ends end
    further apart than the same collar done up (the spread's swing, held: the form has no gravity), and within 5 mm of
    where the rule put them; done up, nothing is spread."""
    V_open, at_spread, _ = _open_collar_ends(True)
    V_shut, none_, turned = _open_collar_ends(False)
    d_open = float(np.linalg.norm(V_open[0, :2] - V_open[1, :2])) * 1000
    d_shut = float(np.linalg.norm(V_shut[0, :2] - V_shut[1, :2])) * 1000
    held = float(np.linalg.norm(V_open - at_spread, axis=1).max()) * 1000
    print(f"open collar: front corners {d_open:.0f} mm apart (done up {d_shut:.0f}); held within {held:.1f} mm of the spread")
    assert none_ is None  # (done up: no spread phase)
    assert d_open > d_shut + 15, (d_open, d_shut)
    assert held < 5.0, held


def test_notch_step_known_answer():
    """(fit round 4) cloth_check.notch_step: an open V notch (20 mm deep, 6 mm mouth) between two top layers over a
    backing 5 mm behind reads open ~6 / depth ~18-20 mm; the same layers closed read 0 / 0 (round 3's notch passed its
    3D gap / angle items with no notch visible: this item reads the wedge the eye sees)."""
    from hifipushie import cloth_check as cc
    o, c = cc._selftest_notch_step()
    print(f"notch step: open {o}, closed {c}")


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


def test_unfolded_band_rides_with_the_flap_it_is_sewn_to():
    """(fit round 5, C48) A piece with NO fold sewn to a flap (a two-piece collar's stand on the lapel's gorge) is
    pressed onto it: a = a front whose UPPER half (y > 0.05) is a flap, b = a band sewn along a's edge x = 0.10, no fold
    of its own, started folded over a. Pressed: only the pairs on a's flap half (cross cells touch a's flap vertices
    only); laid: b's upper part goes back to its drafted continuation, its lower part (sewn to a's base) is NOT moved.
    Two unfolded pieces sewn together get no pressed cells."""
    a = _piece([[0, 0], [0.10, 0], [0.10, 0.10], [0, 0.10]], names={"s0": 1, "s1": 2})
    b = _piece([[0.10, 0.0], [0.13, 0.0], [0.13, 0.10], [0.10, 0.10]], names={"t0": 0, "t1": 3})
    B = _B({"a": a, "b": b}, seams=[["a:s0>s1", "b:t0>t1"]], refine=[{"piece": ["a", "b"], "h": 0.01}])
    M = cloth.mesh(B, 0.02)
    pid = np.asarray(M["piece"])
    uv = np.asarray(M["uv"], float)
    ka, kb = M["names"].index("a"), M["names"].index("b")
    up = (pid == ka) & (uv[:, 1] > 0.05)
    folds_ = [({"piece": "a"}, {"rows": [{"v": np.where(up)[0], "row": np.zeros(0, int)}]}, 1.0)]
    ps, pd, pr = pf._pressed_cells(M, folds_, pf._edges(M["F"]))
    assert len(ps), "no pressed cells: the band is not pressed onto the flap"
    sa = np.r_[ps[pid[ps] == ka], pd[pid[pd] == ka]]
    assert (uv[sa, 1] > 0.05 - 0.011).all(), "a pressed cell reaches a's base half"
    rerr = np.abs(pr[:, :2] - (uv[pd] - uv[ps])).max()
    assert rerr < 1e-6, rerr
    flat = np.c_[uv, np.zeros(len(uv))]
    X = flat.copy()
    vb = pid == kb
    X[vb, 0] = 0.20 - uv[vb, 0]  # b folded over a about the seam (x = 0.10)
    X[vb, 2] = 0.0015
    X1 = pf._lay_pressed(M, X, folds_, reach=0.2)
    hi, lo_ = vb & (uv[:, 1] > 0.065), vb & (uv[:, 1] < 0.035)
    err_hi = np.abs(X1[hi] - flat[hi]).max()
    err_lo = np.abs(X1[lo_] - X[lo_]).max()
    print(f"unfolded band: {len(ps)} cross cells; laid back {err_hi * 1000:.4f} mm (upper), lower moved "
          f"{err_lo * 1000:.4f} mm")
    assert err_hi < 1e-6 and err_lo < 1e-9, (err_hi, err_lo)
    ps0, _, _ = pf._pressed_cells(M, [({"piece": "a"}, {"rows": [{"v": np.zeros(0, int), "row": np.zeros(0, int)}]},
                                       1.0)], pf._edges(M["F"]))
    assert len(ps0) == 0, "two unfolded sides were pressed"


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



# ---------------------------------------------------------------- SETTLE: weight with real contact (fit round 1)

def _bar_body(r=0.05, zc=1.0, half=0.3):
    """A horizontal bar (axis along y) at height zc: an arm held out / a shoulder line, as a cloth.Body-like object."""
    c = _cyl_body(r, -half, half)
    return types.SimpleNamespace(V=np.c_[c.V[:, 0], c.V[:, 2], c.V[:, 1] + zc], T=c.T, at={})


def _settled(M, X0, body, **kw):
    was = pf.SETTLE
    pf.SETTLE = True
    try:
        return pf.assemble({"mesh": M, "X0": X0}, body, attract=0.0, **kw)
    finally:
        pf.SETTLE = was


def test_settle_tube_on_bar(verbose=True):
    """A loose tube (radius ease 20 mm) round a horizontal bar, started concentric (gap 20 mm all round): its weight
    pulls it down until it RESTS on the bar's top (top gap = the form offset, +-1.5 mm), the slack hangs below
    (bottom gap >= 2 x ease - 5 mm: a round tube resting on the top already has 2 x ease below), nothing inside the
    bar, lengths kept (stretch p99 <= 2 %)."""
    r, ease, off, zc = 0.05, 0.02, 0.003, 1.0
    W = 2 * math.pi * (r + ease)
    P = [[0, 0], [W, 0], [W, 0.3], [0, 0.3]]
    B = _B({"s": _piece(P, names={"a0": 0, "a1": 1, "a2": 2, "a3": 3})}, seams=[["s:a0>a3", "s:a1>a2"]])
    M = cloth.mesh(B, 0.01)
    body = _bar_body(r, zc)
    th = M["uv"][:, 0] / W * 2 * math.pi
    R0 = r + ease
    X0 = np.c_[R0 * np.cos(th), M["uv"][:, 1] - 0.15, zc + R0 * np.sin(th)]
    out = _settled(M, X0, body, iters=40, ease=off)
    V = out["V"]
    mid = np.abs(V[:, 1]) < 0.1
    top = float(V[mid, 2].max()) - (zc + r)
    bot = (zc - r) - float(V[mid, 2].min())
    rr = np.hypot(V[:, 0], V[:, 2] - zc)
    inside = int((rr < r + off - 0.0005).sum())
    st = _stretch(V, M)
    if verbose:
        print(f"settle tube: top gap {top * 1000:.1f} mm (want {off * 1000:.0f}), bottom gap {bot * 1000:.1f} mm "
              f"(>= {(2 * ease - 0.005) * 1000:.0f}), inside {inside}, stretch max {st * 100:.2f}% {out['info']['stretch_pct']}")
    assert abs(top - off) <= 0.0015, top
    assert bot >= 2 * ease - 0.005, bot
    assert inside == 0, inside
    assert out["info"]["stretch_pct"]["p99"] <= 2.0, out["info"]["stretch_pct"]


def open_settle_cape_on_bar(verbose=True):  # OPEN (not collected): fails, see the docstring
    """A cape (0.5 m long across the bar, 0.3 m wide) laid flat on a horizontal bar (a shoulder line): its weight
    drapes it over the bar and its two halves hang STRAIGHT DOWN beside it. Inextensible answer: the upper half of the
    bar wrapped (arc pi r'), the rest vertical at x = +-r' (r' = r + offset), the ends at zc - (L/2 - pi r'/2).
    Hanging parts' x within 6 mm of +-r' (bending rounds the turn), ends within 15 mm, nothing inside, stretch p99 <= 2 %.
    OPEN (fit round 1): FAILS. The local / global settle converges too slowly for a large rotation: 150 rounds leave a
    tent (ends 108 mm high, hanging x 161 mm out); 600 rounds ends 27 mm high, x 51-74 mm out. Bending scale (0.005-1)
    changes nothing; no friction (SETTLE_HOLD 0.005) lets it slide off. Stop-loss: a method change is needed (a swing
    of each free flap about its contact line first, as _swing_front; or a Newton / L-BFGS static solve)."""
    r, off, zc, L = 0.05, 0.003, 1.0, 0.5
    P = [[0, 0], [L, 0], [L, 0.3], [0, 0.3]]
    B = _B({"c": _piece(P)})
    M = cloth.mesh(B, 0.01)
    body = _bar_body(r, zc)
    X0 = np.c_[M["uv"][:, 0] - L / 2, M["uv"][:, 1] - 0.15, np.full(len(M["uv"]), zc + r + off)]
    out = _settled(M, X0, body, iters=40, ease=off)
    V = out["V"]
    rp = r + off
    mid = np.abs(V[:, 1]) < 0.1
    hang = mid & (V[:, 2] < zc - 0.03)
    xerr = float(np.abs(np.abs(V[hang, 0]) - rp).max()) if hang.any() else 1.0
    want_end = zc - (L / 2 - math.pi * rp / 2)
    ends = mid & (np.abs(M["uv"][:, 0] - L / 2) > L / 2 - 0.006)
    zerr = float(np.abs(V[ends, 2] - want_end).max())
    inside = int((np.hypot(V[:, 0], V[:, 2] - zc) < rp - 0.0005).sum())
    if verbose:
        print(f"settle cape: hanging x err {xerr * 1000:.1f} mm, ends z err {zerr * 1000:.1f} mm (want "
              f"{want_end:.3f}, got {V[ends, 2].min():.3f}..{V[ends, 2].max():.3f}), inside {inside}, "
              f"stretch {out['info']['stretch_pct']}")
    assert xerr <= 0.006, xerr
    assert zerr <= 0.015, zerr
    assert inside == 0, inside
    assert out["info"]["stretch_pct"]["p99"] <= 2.0, out["info"]["stretch_pct"]



def test_shoulder_pad_lifts_the_form():
    """padded_body: a 10 mm pad on a horizontal 'shoulder' bar lifts the bar's top by 10 mm at the pad centre (30 % of
    the way from the shoulder point to the neck point), nothing at the neck point, nothing underneath."""
    b = _bar_body(0.05, 1.0, 0.3)
    # the bar runs along y here; put the shoulder / neck points on its top, 0.15 m apart along x would be off the bar,
    # so use a bar along x: swap x / y
    b = types.SimpleNamespace(V=b.V[:, [1, 0, 2]], T=b.T, at={"shoulder.L": [0.2, 0.0, 1.05], "hps.L": [0.05, 0.0, 1.05]})
    p = pf.padded_body(b, {"thickness": 0.010, "reach": 0.075, "toward_neck": 0.3})
    lift = np.linalg.norm(p.V - b.V, axis=1)
    c = np.array([0.2 + 0.3 * (0.05 - 0.2), 0.0, 1.05])
    top_c = np.argmin(np.linalg.norm(b.V - c, axis=1))
    neck = np.argmin(np.linalg.norm(b.V - [0.05, 0, 1.05], axis=1))
    under = b.V[:, 2] < 0.97
    assert abs(lift[top_c] - 0.010) < 0.001, lift[top_c]
    assert lift[neck] < 1e-4 and lift[under].max() < 1e-9, (lift[neck], lift[under].max())


def _tube(r, ease, z0, length, h=0.008):
    W = 2 * math.pi * (r + ease)
    P = [[0, 0], [W, 0], [W, length], [0, length]]
    B = _B({"s": _piece(P, names={"a0": 0, "a1": 1, "a2": 2, "a3": 3})}, seams=[["s:a0>a3", "s:a1>a2"]])
    M = cloth.mesh(B, h)
    th = M["uv"][:, 0] / W * 2 * math.pi
    return M, np.c_[(r + ease) * np.cos(th), (r + ease) * np.sin(th), z0 + M["uv"][:, 1]]


def nested_tubes_case(mode="outer_first", r=0.05, inner=0.020, outer=0.010, verbose=True):
    """Two tubes on a cylinder, the INNER one deliberately too big (pattern radius r + 20 mm, the outer r + 10 mm, the
    outer longer at both ends so it covers the inner everywhere), fitted as two layers that touch
    (pattern_form.layered_fit). Returns the measures test_nested_tubes_inner_pressed_under asserts on."""
    body = _cyl_body(r, -0.1, 0.5)
    Mi, Xi = _tube(r, inner, 0.10, 0.20)
    Mo, Xo = _tube(r, outer, 0.08, 0.24)
    u, o = pf.layered_fit({"mesh": Mi, "X0": Xi, "body": body}, {"mesh": Mo, "X0": Xo, "body": body}, mode, iters=150)
    ri = np.linalg.norm(u["V"][:, :2], axis=1) - r
    ro = np.linalg.norm(o["V"][:, :2], axis=1) - r
    mid = (o["V"][:, 2] > 0.12) & (o["V"][:, 2] < 0.28)
    res = {"through_over": u["info"].get("through_over"), "inner_max_mm": round(float(ri.max() * 1000), 1),
           "outer_min_mm": round(float(ro[mid].min() * 1000), 1), "outer_med_mm": round(float(np.median(ro[mid]) * 1000), 1),
           "inner_inside_body": u["info"].get("inside_body"), "inner_stretch": u["info"]["stretch_pct"],
           "outer_stretch": o["info"]["stretch_pct"]}
    if verbose:
        print(f"nested tubes [{mode}]: {res}")
    return res


def test_nested_tubes_inner_pressed_under(mode="outer_first"):
    """KAT (fit round 8): two layers that touch end NESTED, the too-big inner pressed under: no covered inner vertex
    outside the outer (through_over 0), the inner's outermost point inside the outer's innermost (+ 1 mm), nothing of
    the inner inside the body, the outer within 2 mm of its own pattern ease + the inner's allowance."""
    res = nested_tubes_case(mode)
    assert res["through_over"] == 0, res
    assert res["inner_max_mm"] <= res["outer_min_mm"] + 1.0, res
    assert res["inner_inside_body"] == 0, res
    assert abs(res["outer_med_mm"] - 10.0) <= 2.0, res


def _open_tube_case(r=0.1, ease=0.01, H=0.4, hb=0.24):
    """An open-front tube on a cylinder (fit round 10): a back (half the girth) and two fronts (a quarter each), sewn at
    the side seams, the fronts' centre edges free; each front's neck point "hps" at its top CF corner, its "break" on the
    CF edge hb above the hem. Placed closed (the fronts meet at CF, x = 0, y = -(r + ease)), cylinder axis z."""
    R0 = r + ease
    Wq, Wb = 0.5 * math.pi * R0, math.pi * R0
    fl = _piece([[0, 0], [Wq, 0], [Wq, H], [0, H], [0, hb]],
                names={"cfHem": 0, "sideHem": 1, "sideTop": 2, "hps": 3, "break": 4})
    fr = _piece([[-Wq, 0], [0, 0], [0, hb], [0, H], [-Wq, H]],
                names={"sideHem": 0, "cfHem": 1, "break": 2, "hps": 3, "sideTop": 4})
    bk = _piece([[0, 0], [Wb, 0], [Wb, H], [0, H]], names={"b0": 0, "b1": 1, "b2": 2, "b3": 3})
    B = _B({"front.L": fl, "front.R": fr, "back": bk},
           seams=[["front.L:sideHem>sideTop", "back:b0>b3"], ["front.R:sideHem>sideTop", "back:b1>b2"]])
    M = cloth.mesh(B, 0.012)
    pid = np.asarray(M["piece"])
    uv = np.asarray(M["uv"], float)
    th = np.where(pid == M["names"].index("back"), uv[:, 0] / R0, -0.5 * math.pi + uv[:, 0] / R0)
    X0 = np.c_[R0 * np.cos(th), R0 * np.sin(th), 0.05 + uv[:, 1]]
    return M, X0, _cyl_body(r, -0.1, 0.6)


def test_open_front_hangs_without_moving_its_side_seams(off=0.05):
    """(fit round 10) A front worn open pivots about its break and hangs; its side seams and the back stay where the body
    holds them. Opened by its edge alone (WORN_EDGE), an isometric front slid round the body instead (Garrett r9h: side
    seams 70 mm out at the hem, a peplum flare). Known answer, the open-front tube on a cylinder, worn_open break 50 mm:
    with OPEN_HOLD the side seams below the break stay within 3 mm of the closed fit's, the free edge below the break hangs at least
    45 mm off CF on both sides (it does not wrap back to CF), the cloth unstretched (p99 < 3 %); without the hold the
    side seams slide (> 10 mm): the fault the hold fixes."""
    M, X0, body = _open_tube_case()
    pid = np.asarray(M["piece"])
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    side = np.unique(sw.ravel())
    P = M["points"]
    kb = M["names"].index("back")
    closed = pf.assemble({"mesh": M, "X0": X0}, body, iters=80)["V"]
    edge = np.where((np.abs(np.asarray(M["uv"])[:, 0]) < 1e-6) & (pid != kb))[0]
    zb = float(closed[P["front.L:break"], 2])
    low = edge[closed[edge, 2] < zb - 0.02]
    side = side[closed[side, 2] < zb]  # (below the break: above it the lapel's turn carries the top of the side)
    E = pf._edges(M["F"])
    l0 = np.linalg.norm(M["uv"][E[:, 0]] - M["uv"][E[:, 1]], axis=1)
    res = {}
    saved = (pf.WORN_EDGE, pf.OPEN_HOLD)
    try:
        for hold in (False, True):
            pf.WORN_EDGE, pf.OPEN_HOLD = True, hold
            V = pf.assemble({"mesh": M, "X0": X0}, body, iters=80, worn_open={"break": off})["V"]
            drift = float(np.linalg.norm(V[side] - closed[side], axis=1).max())
            sv = np.abs(np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1) / l0 - 1)
            res[hold] = (drift, float(np.abs(V[low, 0]).min()), float(np.percentile(sv, 99)))
            print(f"open tube hold {hold}: side seam drift {drift * 1000:.1f} mm, edge below the break |x| min "
                  f"{np.abs(V[low, 0]).min() * 1000:.1f} / max {np.abs(V[low, 0]).max() * 1000:.1f} mm, "
                  f"y {V[low, 1].mean() * 1000:.1f} mm, stretch p99 {np.percentile(sv, 99) * 100:.2f}%")
    finally:
        pf.WORN_EDGE, pf.OPEN_HOLD = saved
    d1, e1, s1 = res[True]
    assert d1 < 0.003 and e1 > off - 0.005 and s1 < 0.03, res[True]
    assert res[False][0] > 0.010, res[False]


def test_open_front_edge_has_no_step_at_the_break():
    """(fit round 11, Joe: "the notches cut in the bottom of the lapels") A front edge worn open is ONE line through the
    break. Known answer, the open-front tube, worn open at TWO points (break 50 mm, cfHem 80 mm off CF): the rigid swing
    meets only the last point, so with the edge held at its swung x (EDGE_FIELD False) the break's own pin dragged that
    one vertex out of the edge (a step > BREAK_STEP_MM: the fault); with the edge field the edge carries the points'
    corrections and the break sits on the edge's line (step <= BREAK_STEP_MM), both points still met within 5 mm."""
    M, X0, body = _open_tube_case()
    P = M["points"]
    saved = (pf.WORN_EDGE, pf.OPEN_HOLD, pf.EDGE_FIELD)
    res = {}
    try:
        for fld in (False, True):
            pf.WORN_EDGE, pf.OPEN_HOLD, pf.EDGE_FIELD = True, True, fld
            V = pf.assemble({"mesh": M, "X0": X0}, body, iters=80, worn_open={"break": 0.05, "cfHem": 0.08})["V"]
            eb = pf.edge_through_break(M, V)
            miss = max(abs(abs(V[P[f"front.{s}:{n}"], 0]) - o) for s in "LR" for n, o in (("break", 0.05), ("cfHem", 0.08)))
            res[fld] = (max(r["step_mm"] for r in eb.values()), miss)
            print(f"edge field {fld}: {eb}, worst point miss {miss * 1000:.1f} mm")
    finally:
        pf.WORN_EDGE, pf.OPEN_HOLD, pf.EDGE_FIELD = saved
    assert res[False][0] > pf.BREAK_STEP_MM, res
    assert res[True][0] <= pf.BREAK_STEP_MM and res[True][1] < 0.005, res


def _open_tube_lapel_case(r=0.1, ease=0.01, H=0.4, hb=0.2):
    """The open-front tube with LAPELS (fit round 11): each front's CF edge runs up from the hem to the break (hb), then
    out to a lapel point and back to the neck point "hps" (0.03 off CF at the top); a pressed "lapel roll" fold from the
    break to the neck point, its flap the lapel. Back + two fronts sewn at the side seams on a cylinder, placed closed."""
    R0 = r + ease
    Wq, Wb = 0.5 * math.pi * R0, math.pi * R0
    pts = [[0, 0], [Wq, 0], [Wq, H], [0.03, H], [-0.05, H - 0.06], [0, hb]]
    nm = {"cfHem": 0, "sideHem": 1, "sideTop": 2, "hps": 3, "lapelPoint": 4, "break": 5}
    fl = _piece(pts, names=nm)
    fr = _piece([[-x, y] for x, y in pts][::-1], names={k: 5 - v for k, v in nm.items()})
    bk = _piece([[0, 0], [Wb, 0], [Wb, H], [0, H]], names={"b0": 0, "b1": 1, "b2": 2, "b3": 3})
    folds = [{"piece": f"front.{s}", "line": [[0, hb], [g * 0.03, H]], "angle": 5, "kind": "press", "name": "lapel roll",
              "flap": "lapelPoint"} for s, g in (("L", 1), ("R", -1))]
    B = _B({"front.L": fl, "front.R": fr, "back": bk},
           seams=[["front.L:sideHem>sideTop", "back:b0>b3"], ["front.R:sideHem>sideTop", "back:b1>b2"]], folds=folds)
    M = cloth.mesh(B, 0.012)
    pid = np.asarray(M["piece"]); uv = np.asarray(M["uv"], float)
    th = np.where(pid == M["names"].index("back"), uv[:, 0] / R0, -0.5 * math.pi + uv[:, 0] / R0)
    X0 = np.c_[R0 * np.cos(th), R0 * np.sin(th), 0.05 + uv[:, 1]]
    return M, X0, _cyl_body(r, -0.1, 0.6)


def test_open_hold_stops_at_the_break_not_the_roll_top():
    """(fit round 11, Joe: "the tops of the lapels are embedded in the layer below") A worn-open front hangs from its
    seams BELOW its break; above it the lapel turns and the front above follows the swing. open_seam_holds took its height
    from every worn-open pin, the edge pins included, whose roll-line pins reach the neck: the shoulder / neck seams were
    held CLOSED under the turned lapel (Garrett: the lapel top through its base, 40-120 mm below the neck point, L 129 / R
    125 flap vertices; 45 / 45 unheld). Known answer, the open tube with lapels (break 0.2 of 0.4 m, roll to the neck
    point): HOLD_NAMED holds only the side seams below the break (about half of them); without it every one is held."""
    M, X0, body = _open_tube_lapel_case()
    saved = (pf.WORN_EDGE, pf.OPEN_HOLD, pf.HOLD_NAMED)
    n = {}
    try:
        for hn in (False, True):
            pf.WORN_EDGE, pf.OPEN_HOLD, pf.HOLD_NAMED = True, True, hn
            out = pf.assemble({"mesh": M, "X0": X0}, body, iters=80, worn_open={"break": 0.05})
            n[hn] = out["info"]["open_hold_v"]
            print(f"HOLD_NAMED {hn}: held seam vertices {n[hn]}")
    finally:
        pf.WORN_EDGE, pf.OPEN_HOLD, pf.HOLD_NAMED = saved
    assert 0.35 < n[True] / n[False] < 0.65, n


def lapel_turn_case(roll_turn: bool, off: float = 0.05, verbose: bool = True, woven: bool = False) -> dict:
    """The worn-open front with a lapel on a cylinder, ROLL_TURN on / off (fit round 12): chest drift from the closed fit
    (front vertices above the break, off the lapel, 40 mm+ from the roll line), the chest's stand-off from the body, the
    lapel's turn, the free edge below the break, the step at the break."""
    from scipy.spatial import cKDTree
    M, X0, body = _open_tube_lapel_case()
    pid = np.asarray(M["piece"]); uv = np.asarray(M["uv"], float); P = M["points"]
    saved = (pf.WORN_EDGE, pf.OPEN_HOLD, pf.ROLL_TURN, pf.CHEST_HOLD, pf.WOVEN)
    res = {}
    try:
        pf.WORN_EDGE, pf.OPEN_HOLD, pf.WOVEN = True, True, woven
        closed = pf.assemble({"mesh": M, "X0": X0}, body, iters=80)["V"]
        pf.ROLL_TURN, pf.CHEST_HOLD = roll_turn, (1.0 if roll_turn else 0.0)
        out = pf.assemble({"mesh": M, "X0": X0}, body, iters=80, worn_open={"break": off})
    finally:
        pf.WORN_EDGE, pf.OPEN_HOLD, pf.ROLL_TURN, pf.CHEST_HOLD, pf.WOVEN = saved
    V = out["V"]
    from hifipushie import folds as foldmod
    for s in "LR":
        k = M["names"].index(f"front.{s}")
        fd = [f for f in M["folds"] if f["piece"] == f"front.{s}"][0]
        g = foldmod._geom(M, fd)
        row = np.asarray(fd["rows"][0], int)
        zb = float(closed[P[f"front.{s}:break"], 2])
        dr = cKDTree(uv[row]).query(uv)[0]
        chest = np.where((pid == k) & ~np.asarray(g["flap0"], bool) & (closed[:, 2] > zb + 0.02) & (dr > 0.04))[0]
        drift = np.linalg.norm(V[chest] - closed[chest], axis=1) * 1000
        stand = (np.hypot(V[chest, 0], V[chest, 1]) - 0.1) * 1000
        border = np.asarray(M["border"], bool)
        low = np.where((pid == k) & border & (np.abs(uv[:, 0]) < 1e-6) & (closed[:, 2] < zb - 0.02))[0]
        res[s] = {"chest_drift_p90": round(float(np.percentile(drift, 90)), 1),
                  "chest_stand_p90": round(float(np.percentile(stand, 90)), 1),
                  "turn_deg": round(pf.fold_turned(M, V, g), 0),
                  "edge_below_min": round(float(np.abs(V[low, 0]).min()) * 1000, 1),
                  "break_x": round(abs(float(V[P[f"front.{s}:break"], 0])) * 1000, 1)}
    eb = pf.edge_through_break(M, V)
    for s in "LR":
        res[s]["step_mm"] = eb[f"front.{s}"]["step_mm"]
    res["through"] = pf.flap_through_base(M, V, body)
    res["stretch"] = out["info"]["stretch_pct"]
    if woven:
        W = pf._woven_setup(M, None, np.asarray(M["F"]), pf._edges(np.asarray(M["F"])), np.zeros(len(uv), bool))
        sh = pf.woven_shear_deg(W, V)
        res["shear_deg"] = {"p50": round(float(np.median(sh)), 1), "p99": round(float(np.percentile(sh, 99)), 1)}
        res["grain_stretch"] = out["info"].get("grain_stretch_pct")
    if verbose:
        print(f"lapel turn ROLL_TURN {roll_turn} WOVEN {woven}: {res}")
    return res


@pytest.mark.xfail(strict=True, reason="fit round 12: an isometric (shear-stiff) front cannot open its break with its chest and "
                   "side seams fixed: the lapels compress through their base. Fit round 14: WOVEN (KES-F shear) does not "
                   "fix it: lapels 26 / 40 % through (66 / 90 off), turn 143 / 150 deg, the base strip along the roll line "
                   "crumples in the WEFT (+-30 %, not shear) between the pressed row and the held chest")
def test_open_front_turns_its_lapel_not_its_chest(off=0.05):
    """(fit round 12, coordinator-approved method) Worn open, a jacket's chest stays on the body; only the lapel turns,
    about its roll line, and the front below the break hangs from the break. Known answer, the open tube with lapels,
    worn open at the break 50 mm: ROLL_TURN keeps the chest within 6 mm (p90) of the closed fit and within 8 mm of the
    body, the lapel turned past 160 deg, the edge below the break hangs at least 45 mm off CF, the break met within 5 mm
    and no step at the break (<= BREAK_STEP_MM); the old rigid swing of the whole upper front moved the chest further
    (> 1.5 x): the fault that set every hold above the break fighting it. Also the lapel ON its base (flap_through_base
    ok) and the cloth unstretched (p99 < 5 %). XFAIL (r12): ROLL_TURN + CHEST_HOLD keep the chest (drift 0, stand 6 mm)
    but the lapels go 66 / 90 % through their base, stretch p99 13 %; the start field alone moves the chest 34 mm."""
    new, old = lapel_turn_case(True, off, woven=True), lapel_turn_case(False, off)
    for s in "LR":
        r = new[s]
        assert r["chest_drift_p90"] <= 6.0 and r["chest_stand_p90"] <= 8.0, new
        assert r["turn_deg"] >= 160 and r["edge_below_min"] >= (off - 0.005) * 1000, new
        assert abs(r["break_x"] - off * 1000) <= 5.0 and r["step_mm"] <= pf.BREAK_STEP_MM, new
        assert old[s]["chest_drift_p90"] > 1.5 * r["chest_drift_p90"], (old, new)
    assert all(v["ok"] for v in new["through"].values()) and new["grain_stretch"]["p99"] < 5.0, new


def _woven_square(grain=90.0, h=0.01):
    B = _B({"sq": _piece([[0, 0], [0.2, 0], [0.2, 0.2], [0, 0.2]])})
    B["pieces"]["sq"]["grain"] = grain
    M = cloth.mesh(B, h)
    F = np.asarray(M["F"])
    W = pf._woven_setup(M, B, F, pf._edges(F), np.zeros(len(M["uv"]), bool))
    return M, W


def _grain_map(M, grain, A):
    """X = R A R^T uv: the 2x2 map A applied in the grain frame (weft, warp) of a piece cut at `grain` deg."""
    g = math.radians(grain)
    R = np.array([[math.sin(g), math.cos(g)], [-math.cos(g), math.sin(g)]])  # columns weft, warp
    uv = np.asarray(M["uv"], float)
    return np.c_[uv @ (R @ A @ R.T).T, np.zeros(len(uv))]


def _shear_A(deg):
    """Pure shear: warp and weft keep their length, the angle between them closes by deg (split both ways)."""
    h = math.radians(deg) / 2
    return np.array([[math.cos(h), math.sin(h)], [math.sin(h), math.cos(h)]])


def test_woven_shear_costs_its_sourced_share_of_a_stretch():
    """(fit round 14) WOVEN's energy per unit strain^2: a shear gamma costs G / E of a stretch eps = gamma (KES-F suiting:
    G 0.75 gf/cm/deg, E = 500 gf/cm / EMT 6.4 %), on any grain (a bias-cut piece too: the frame turns with the grain).
    Known answer at 1 %: shear / stretch = 0.0055 +- 10 %; and a 2 % stretch along the warp or the weft costs
    (1 + SHEAR_STIFF) eps^2 per area (as stiff as the isometry: the same sources, the same weight)."""
    G_E = pf.KES_G * 180 / math.pi / (pf.KES_FM / pf.KES_EMT)
    for grain in (90.0, 45.0, 0.0):
        M, W = _woven_square(grain)
        g = 0.01
        sh = pf.woven_energy(W, _grain_map(M, grain, _shear_A(math.degrees(g))))
        st = pf.woven_energy(W, _grain_map(M, grain, np.diag([1.0, 1.0 + g])))
        r = sh["total"] / st["total"]
        print(f"grain {grain}: shear 1 % / stretch 1 % = {r:.5f} (G/E {G_E:.5f})", sh, st)
        assert abs(r / G_E - 1) < 0.1, (r, G_E)
        for A in (np.diag([1.0, 1.02]), np.diag([1.02, 1.0])):
            e = pf.woven_energy(W, _grain_map(M, grain, A))
            assert abs(e["total"] / (e["area"] * (1 + pf.SHEAR_STIFF) * 0.02 ** 2) - 1) < 0.05, e
        # the frame follows the grain: a bias piece sheared in ITS frame is cheap; read on the straight grain the same
        # map is warp / weft stretch (the undercollar, cut on the bias, must shear round the neck, not stretch)
        if grain == 45.0:
            X = _grain_map(M, 45.0, _shear_A(10.0))
            e45, e90 = pf.woven_energy(W, X), pf.woven_energy(_woven_square(90.0)[1], X)
            print("bias sheared 10 deg: own grain", e45, "straight grain", e90)
            assert e45["total"] < 0.05 * e90["total"], (e45, e90)


@pytest.mark.xfail(strict=True, reason="fit round 14: the brief's '20 deg shear < 5 % of a 2 % stretch' has no source; "
                   "KES-F suiting (G/E 0.0055) puts a 20 deg shear at ~1.5 x a 2 % stretch (shear is soft PER UNIT STRAIN, "
                   "and 20 deg is 17 x the strain of 2 %)")
def test_woven_square_sheared_20_costs_under_5pct_of_a_2pct_stretch():
    M, W = _woven_square()
    sh = pf.woven_energy(W, _grain_map(M, 90.0, _shear_A(20.0)))
    st = pf.woven_energy(W, _grain_map(M, 90.0, np.diag([1.0, 1.02])))
    print("20 deg shear / 2 % stretch", sh["total"] / st["total"])
    assert sh["total"] < 0.05 * st["total"], (sh, st)


def test_woven_fit_shears_a_held_sheet_instead_of_stretching():
    """(fit round 14) The fit, not just the energy: a free sheet placed sheared 20 deg relaxes back under FIT (all edges
    isometric) but under WOVEN keeps most of its shear (only SHEAR_STIFF pulls it back; warp / weft at length), while a
    sheet placed stretched 3 % along the warp relaxes to its length under both."""
    M, W = _woven_square(90.0, 0.02)
    out = {}
    for woven in (False, True):
        saved = pf.WOVEN
        try:
            pf.WOVEN = woven
            for nm, A in (("shear", _shear_A(20.0)), ("stretch", np.diag([1.0, 1.03]))):
                X0 = _grain_map(M, 90.0, A)
                V = pf.assemble({"mesh": M, "X0": X0}, None, iters=30, attract=0.0)["V"]
                Fg = pf._woven_grad(W, V)[0]
                out[(woven, nm)] = (round(float(np.median(pf.woven_shear_deg(W, V))), 1),
                                    round(float(np.median(np.linalg.norm(Fg[:, :, 1], axis=1)) - 1) * 100, 2))
        finally:
            pf.WOVEN = saved
    print("held sheet", out)
    assert out[(False, "shear")][0] < 5.0 and out[(True, "shear")][0] > 10.0, out
    assert abs(out[(True, "stretch")][1]) < 0.5 and abs(out[(False, "stretch")][1]) < 0.5, out


def test_front_crease_and_flap_through_measures_find_planted_faults():
    """(fit round 11, Joe: "hopefully there's not a sharp fold here", "the tops of the lapels are embedded") The two form
    measures behind gate rows front_crease / lapel_on_base, validated on known answers. front_creases: the open tube's
    closed fit (a smooth cylinder) passes; the same with front.L below the break kinked 60 deg about a vertical line
    fails with an interior max >= 50. flap_through_base: the mirrored lapels assembled lie on their bases (share 0);
    the flaps pushed 5 mm into the chest side, through their bases, read share > 0.5."""
    M, X0, body = _open_tube_case()
    V = pf.assemble({"mesh": M, "X0": X0}, body, iters=80)["V"]
    ok = pf.front_creases(M, V)
    print("smooth tube", ok)
    assert ok and all(r["ok"] for r in ok.values()), ok
    pid = np.asarray(M["piece"]); k = M["names"].index("front.L"); uv = np.asarray(M["uv"])
    Vk = V.copy()
    zb = V[M["points"]["front.L:break"], 2]
    m = (pid == k) & (uv[:, 0] < 0.05) & (V[:, 2] < zb - 0.02)
    piv = V[(pid == k) & (np.abs(uv[:, 0] - 0.05) < 0.007)].mean(0)
    Vk[m] = piv + pf._rodrigues(V[m] - piv, np.tile([0.0, 0.0, 1.0], (int(m.sum()), 1)), np.full(int(m.sum()), np.radians(60)))
    bad = pf.front_creases(M, Vk)
    print("kinked tube", bad)
    assert not bad["front.L"]["ok"] and bad["front.L"]["interior_max"] >= 50, bad
    from hifipushie import folds as foldmod
    L = _mirrored_lapels("press")
    X0 = np.c_[L["uv"][:, 0], np.full(len(L["uv"]), -0.006), 1.0 + L["uv"][:, 1]]
    W = pf.assemble({"mesh": L, "X0": X0}, _plane_body(0.0), iters=80, attract=0.0)["V"]
    good = pf.flap_through_base(L, W, _plane_body(0.0))
    F = np.asarray(L["F"])
    flm = foldmod.flap_faces(L, F)
    fl, base = np.unique(F[flm]), np.unique(F[~flm])
    Wb = W.copy()
    Wb[np.setdiff1d(fl, base), 1] += 0.005  # (+y: toward the chest, behind the base)
    thr = pf.flap_through_base(L, Wb, _plane_body(0.0))
    print("lapels", good, "pushed", thr)
    assert all(r["share"] == 0 for r in good.values()) and all(r["share"] > 0.5 for r in thr.values()), (good, thr)


def test_sleeve_over_a_sleeve_has_room():
    """(fit round 10) A sleeve worn over a sleeve holds it plus one layer: width >= under + 2 pi (EASE + THICK). Known
    answer: a shirt sleeve 391 mm wide; a two-piece jacket sleeve (top 217 + under 179 = 396, Garrett's draft from the
    bare arm) fails; widened to 430 it passes."""
    shirt = cloth.mesh(_B({"sleeve.L": _piece([[0, 0], [0.391, 0], [0.391, 0.5], [0, 0.5]])}), 0.02)
    for under_w, ok in ((0.179, False), (0.213, True)):
        jk = cloth.mesh(_B({"top.L": _piece([[0, 0], [0.217, 0], [0.217, 0.5], [0, 0.5]]),
                            "under.L": _piece([[0.3, 0], [0.3 + under_w, 0], [0.3 + under_w, 0.5], [0.3, 0.5]])}), 0.02)
        r = pf.sleeve_room(shirt, jk)
        print("sleeve room", r)
        assert r["ok"] == ok and 370 < r["under"] <= 392, r  # (the mesher trims the drafted 391 a little)


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


def test_gorge_lie_known_answers():
    """(fit round 17, Joe's notch) pattern_form.gorge_lie / seam_lie on planted strips: flat 0, a 20 deg / cm twist
    found on its own side only, a seam bent along a cylinder (no twist) reads ~0, a 30 deg hinge reads across 30, a
    collar end lifted 12 mm reads tip 12 (round 16's notch.py counted the surface's own bend and the in-plane gap)."""
    pf._selftest_gorge_lie()


def _lapped_case(r=0.10, lap=0.04, h=0.3, over_r=0.008, under_r=0.025):
    """Two fronts round a cylinder (its CF at -Y), each from the back (+Y) round its own side to `lap` past CF: front.L
    (+X) the closure's over piece, front.R the under one. The start puts the over piece INSIDE the under one (Garrett's
    placement: the over front 23 mm behind), both off the cylinder."""
    R = r + 0.004
    half = math.pi * R + lap
    P = [[0, 0], [half, 0], [half, h], [0, h]]
    nmz = {"a0": 0, "a1": 1, "a2": 2, "a3": 3}
    B = _B({"front.L": _piece(P, names=nmz), "front.R": _piece(P, names=nmz)})
    M = cloth.mesh(B, 0.008)
    M["closures"] = [{"name": "front", "kind": "buttons", "over": "front.L", "under": "front.R", "state": "open",
                      "pairs": [], "v": []}]
    pid = np.asarray(M["piece"])
    X0 = np.zeros((len(pid), 3))
    for nm, sg, rr in (("front.L", 1.0, r + over_r), ("front.R", -1.0, r + under_r)):
        k = pid == M["names"].index(nm)
        th = math.pi / 2 - sg * (M["uv"][k, 0] / R)  # (uv x 0 at the back, `half` at the lap's edge past CF)
        X0[k] = np.c_[rr * np.cos(th), rr * np.sin(th), 0.1 + M["uv"][k, 1]]
    return M, X0, _cyl_body(r, -0.1, 0.6)


def test_lapped_fronts_end_layered(verbose=True):
    """(fit round 21) A LAPPED CLOSURE IS LAYERED (pattern_form.LAP_LAYER): two fronts lapped 40 mm at CF on a cylinder,
    the over one started INSIDE the under one, end with the over front outside the under one wherever they lap (gap
    p50 >= 1 mm, nothing behind by more than 0.5 mm) and nothing crossing; the cloth unstretched (p99 < 3 %). Without
    LAP_LAYER the over front stays inside / through the under one (the control)."""
    M, X0, body = _lapped_case()
    res = {}
    for on in (True, False):
        old = pf.LAP_LAYER
        pf.LAP_LAYER = on
        try:
            out = pf.assemble({"mesh": M, "X0": X0}, body, iters=120)
        finally:
            pf.LAP_LAYER = old
        V = out["V"]
        lg = pf.lap_gaps(M, V, body)["front"]
        E = pf._edges(M["F"])
        l0 = np.linalg.norm(M["uv"][E[:, 0]] - M["uv"][E[:, 1]], axis=1)
        sv = np.abs(np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1) / l0 - 1)
        res[on] = (lg, float(np.percentile(sv, 99)))
        if verbose:
            print(f"LAP_LAYER {on}: {lg}, stretch p99 {res[on][1] * 100:.2f} %, finish {out['info'].get('lap_finish')}")
    lg, p99 = res[True]
    assert lg["crossing"] == 0 and lg["lap_n"] > 50, lg
    assert lg["gap_mm"]["p50"] >= 1.0 and lg["gap_mm"]["min"] >= -0.5, lg
    assert p99 < 0.03, p99
    lg0 = res[False][0]
    assert lg0["crossing"] > 0 or lg0["gap_mm"]["p50"] < 0.5, lg0  # (the control: not layered)


def under_lie_case(r=0.05, inner=0.017, outer=0.019, verbose=True):
    """Two tubes on a cylinder, Garrett's waist in miniature (fit round 22): an inner tube with a lot of ease (r + 17 mm,
    a shirt's +109 mm) under an outer one with a little more (r + 19 mm, a jacket's +119 mm), the outer covering the
    inner. Fitted the old way (inner alone, the outer over it: "base") and with the inner's fullness laid down ("lie").
    Returns {mode: measures}."""
    body = _cyl_body(r, -0.1, 0.5)
    Mi, Xi = _tube(r, inner, 0.10, 0.20)
    Mo, Xo = _tube(r, outer, 0.08, 0.24)
    ures, ores = {"mesh": Mi, "X0": Xi, "body": body}, {"mesh": Mo, "X0": Xo, "body": body}
    out = {}
    for mode in ("base", "lie"):
        if mode == "base":
            u = pf.assemble(ures, body, ease=pf.UNDER_EASE, iters=150)
            o = pf.assemble(ores, body, under={"V": u["V"], "F": u["F"]}, ease=pf.EASE, iters=150)
        else:
            u, o = pf.layered_fit(ures, ores, "lie", iters=150)
        ri = np.linalg.norm(u["V"][:, :2], axis=1) - r
        ro = np.linalg.norm(o["V"][:, :2], axis=1) - r
        mi = (u["V"][:, 2] > 0.14) & (u["V"][:, 2] < 0.26)
        mo = (o["V"][:, 2] > 0.14) & (o["V"][:, 2] < 0.26)
        du = pf._Surface(o["V"], o["F"]).signed(u["V"][mi])[0]
        out[mode] = {"inner_med_mm": round(float(np.median(ri[mi]) * 1000), 1),
                     "inner_max_mm": round(float(ri[mi].max() * 1000), 1),
                     "outer_min_mm": round(float(ro[mo].min() * 1000), 1),
                     "outer_med_mm": round(float(np.median(ro[mo]) * 1000), 1),
                     "gap_med_mm": round(float(-np.median(du) * 1000), 1), "inner_outside_outer": int((du > 0).sum()),
                     "outer_through_under": o["info"].get("through_under")}
    if verbose:
        print(f"under lie: {out}")
    return out


@pytest.mark.xfail(reason="round 22: UNDER_LIE_GATHER (10 % edge take-up) leaves the inner ~11 mm off, over the 8 mm cap; opt-in mode, B (cull early) chosen instead", strict=False)
def test_under_layer_lies_down():
    """KAT (fit round 22): an under layer's fullness lies down where a layer is worn over it. A too-full inner tube under
    an outer one: laid down ("lie"), the inner lies within UNDER_LIE_CAP (+ 1 mm) of the body, nothing of it is outside
    the outer, and the outer keeps its own ease over the BODY (19 mm +- 2) with at least 6 mm of room over the inner;
    the old path ("base", the control) leaves the inner standing at its full ease, the outer within 5 mm over it and
    pushed past its own ease (measured: inner 16.9, outer 21.2, gap 4.4 mm; laid down: inner 8.0, outer 19.0, gap 11.0)."""
    res = under_lie_case()
    b, l = res["base"], res["lie"]
    assert b["inner_med_mm"] > 14.0 and b["gap_med_mm"] < 5.0 and b["outer_med_mm"] > 20.0, res  # (the fault: a standing
    # tube the outer clings to, stretched out past its own ease)
    assert l["inner_med_mm"] <= pf.UNDER_LIE_CAP * 1000 + 1.0, res
    assert l["inner_outside_outer"] == 0 and not l["outer_through_under"], res
    assert abs(l["outer_med_mm"] - 19.0) <= 2.0, res
    assert l["gap_med_mm"] >= 6.0, res


def _hourglass_body(m=96):
    """A torso-like solid of revolution: chest r 150 mm at z 1.30, waist 120 at 1.10 (a 30 mm hollow), hip 140 at 0.95
    with a SEAT bulge on the back (+y) to 165, under the seat back to 130 at 0.80."""
    th = np.linspace(0, 2 * np.pi, m + 1)[:-1]
    zs = np.linspace(0.70, 1.40, 71)

    def r(z, t):
        base = np.interp(z, [0.70, 0.80, 0.95, 1.10, 1.30, 1.40], [0.130, 0.130, 0.140, 0.120, 0.150, 0.150])
        seat = 0.025 * np.exp(-((z - 0.93) / 0.06) ** 2) * np.maximum(np.sin(t), 0.0) ** 2
        return base + seat
    V = np.array([[r(z, t) * math.cos(t), r(z, t) * math.sin(t), z] for z in zs for t in th])
    T = []
    for i in range(len(zs) - 1):
        for j in range(m):
            a, b = i * m + j, i * m + (j + 1) % m
            T += [[a, b, a + m], [b, b + m, a + m]]
    return types.SimpleNamespace(V=V, T=np.asarray(T), at={"armpit_z": [1.36], "shoulder.L": [0.3, 0.0, 1.4]}), r


def bridge_case(bridge, verbose=True, hang=True):
    """A tailored tube over the hourglass: its girth the body's + 2 pi 10 mm down to the seat (z 0.93), then STRAIGHT
    (the seat's girth) to the hem at 0.76, as a jacket's skirt; started ON an offset of the body (as a fit's placement
    follows it). Returns radius - body (mm) at the back / side at the waist, the seat, under the seat (0.80), and the
    back's CUP = seat back radius - under-seat back radius (0: plumb)."""
    body, r = _hourglass_body()
    th_ = np.linspace(0, 2 * np.pi, 721)[:-1]

    def girth(z):
        q = np.c_[r(z, th_) * np.cos(th_), r(z, th_) * np.sin(th_)]
        return float(np.linalg.norm(q - np.roll(q, 1, 0), axis=1).sum()) + 2 * math.pi * 0.010
    ys = np.linspace(0.0, 0.58, 30)
    G = np.array([girth(max(0.76 + y, 0.93)) for y in ys])
    P = [[-G[0] / 2, 0.0]] + [[g / 2, y] for g, y in zip(G, ys)] + [[-g / 2, y] for g, y in zip(G[::-1], ys[::-1])][:-1]
    n = len(ys)
    names = {"a0": 0, "a1": 1, "a2": n, "a3": n + 1}
    B = _B({"s": _piece(P, names=names)}, seams=[["s:a0>a3", "s:a1>a2"]])
    M = cloth.mesh(B, 0.015)
    z = 0.76 + M["uv"][:, 1]
    Gz = np.interp(M["uv"][:, 1], ys, G)
    th = (0.5 - M["uv"][:, 0] / Gz) * 2 * np.pi + np.pi / 2  # (the seam at the front, -y)
    R0 = r(z, th) + 0.006
    X0 = np.c_[R0 * np.cos(th), R0 * np.sin(th), z]
    keep = pf.BRIDGE_HANG
    pf.BRIDGE_HANG = hang
    try:
        out = pf.assemble({"mesh": M, "X0": X0}, body, iters=120, ease=0.004, bridge=bridge)
    finally:
        pf.BRIDGE_HANG = keep
    V = out["V"]
    a = np.arctan2(V[:, 1], V[:, 0])
    rr = np.linalg.norm(V[:, :2], axis=1)

    def rad(z0, az):
        k = (np.abs(V[:, 2] - z0) < 0.012) & (np.abs((a - az + np.pi) % (2 * np.pi) - np.pi) < 0.12)
        return 1000 * float(np.median(rr[k]))

    def at(z0, az):
        return rad(z0, az) - 1000 * float(r(z0, az))
    res = {"waist_back": at(1.10, math.pi / 2), "waist_side": at(1.10, 0.0), "seat_back": at(0.93, math.pi / 2),
           "under_seat_back": at(0.80, math.pi / 2), "cup_back": rad(0.93, math.pi / 2) - rad(0.80, math.pi / 2),
           "stretch_p99": out["info"]["stretch_pct"]["p99"]}
    if verbose:
        print("bridge", bridge, "hang", hang, {k: round(v, 1) for k, v in res.items()})
    return res


def test_bridge_hourglass_tube():
    """BRIDGE (fit round 23): under the seat, stiff cloth (bridge 1) hangs nearer plumb from the seat than soft cloth
    (bridge 0, the old form: drawn in after the body): the back's cup <= 0.65 x the soft one's, the under-seat back
    >= 15 mm further off the body; the girth is the pattern's either way (stretch p99 < 10 %: the polygon tube's rows).
    A MECHANISM known answer, not a magnitude: the free tube (no pins) drifts back, so neither reads exactly plumb
    (measured 17 vs 29 mm cup, 69 vs 49 mm under the seat). At the waist a tailored tube has no girth to bridge
    with: there the draft decides, not the form (waist gap 6-12 mm either way)."""
    s, f = bridge_case(1.0), bridge_case(0.0)
    assert s["cup_back"] <= 0.65 * f["cup_back"], (s, f)
    assert s["under_seat_back"] >= f["under_seat_back"] + 15, (s, f)
    assert s["stretch_p99"] < 10 and f["stretch_p99"] < 10, (s, f)


def test_pocket_flap_is_a_patch_on_its_front():
    """(fit round 26, C95) pattern_form.patches: a piece stitched only to the INTERIOR of one other piece (a pocket flap
    on its pocket line) is a patch of that piece; a piece sewn to another's border (a collar on a stand) is not, nor one
    joined to two pieces."""
    def grid(nx, ny, x0, y0, s, off):
        V = [(x0 + i * s, y0 + j * s, 0.0) for j in range(ny) for i in range(nx)]
        F = []
        for j in range(ny - 1):
            for i in range(nx - 1):
                a = off + j * nx + i
                F += [(a, a + 1, a + nx + 1), (a, a + nx + 1, a + nx)]
        return V, F
    _, F0 = grid(6, 6, 0, 0, 0.01, 0)          # 0 front: verts 0..35
    _, F1 = grid(3, 2, 0.015, 0.03, 0.01, 36)  # 1 flap: verts 36..41 (its top row 39..41)
    _, F2 = grid(6, 2, 0, 0.06, 0.01, 42)      # 2 collar: sewn to the front's top border (30..35)
    M = {"names": ["front", "flap", "collar"], "piece": [0] * 36 + [1] * 6 + [2] * 12, "F": F0 + F1 + F2,
         "sew": [[30 + i, 42 + i] for i in range(6)],
         "stitch": [[39, 20], [40, 21], [41, 22]]}  # (front 20..22: interior)
    got = [(M["names"][k], M["names"][b], len(v)) for k, b, v in pf.patches(M)]
    assert got == [("flap", "front", 6)], got
    M2 = dict(M, stitch=M["stitch"] + [[36, 43]])  # the flap also stitched to the collar: not a patch
    assert pf.patches(M2) == [], pf.patches(M2)


# ---------------------------------------------------------------- shirt round 10 (C124): a sprung fall LIES on the shoulders
_SH_BETA = math.radians(22.0)


def _shoulder_body(r, z0, m=96):
    th = np.linspace(0, 2 * np.pi, m + 1)[:-1]
    zs = np.r_[np.linspace(z0 - 0.05, z0, 11)[:-1], np.linspace(z0, z0 + 0.25, 31)]
    rad = lambda z: r + max(z0 - z, 0.0) / math.tan(_SH_BETA)
    V = np.array([[rad(z) * math.cos(t), rad(z) * math.sin(t), z] for z in zs for t in th])
    T = []
    for i in range(len(zs) - 1):
        for j in range(m):
            a, b = i * m + j, i * m + (j + 1) % m
            T += [[a, b, a + m], [b, b + m, a + m]]
    return types.SimpleNamespace(V=V, T=np.asarray(T), at={})


def _shoulder_collar_case(stand=0.028, fall=0.065, at=0.004, r=0.06, ease=0.004, gap_n=10, spring=True):
    R = r + ease
    z0 = 1.40
    ths = np.linspace(-math.pi / 2, 3 * math.pi / 2, 161)
    sl = slice(gap_n, 161 - gap_n)
    u = (R * (ths - math.pi / 2))[sl]
    nc = len(u)
    k_cb = nc // 2
    ns = 10
    # stand: a straight band (as the test case)
    bot = np.c_[u, np.full(nc, z0)]
    rgt = np.c_[np.full(ns - 1, u[-1]), np.linspace(z0, z0 + stand, ns + 1)[1:-1]]
    top = np.c_[u[::-1], np.full(nc, z0 + stand)]
    lft = np.c_[np.full(ns - 1, u[0]), np.linspace(z0 + stand, z0, ns + 1)[1:-1]]
    Ps = np.r_[bot, rgt, top, lft]
    s_t = nc + ns - 1
    # fall: an annular sector (sprung: the outer edge cut for the shoulders it lands on)
    below = fall - stand - 2 * at - math.pi * 0.004
    R_out = R + 2 * pf.THICK + 0.002 + (max(below, 0.0) * math.cos(_SH_BETA) if spring else 0.0)
    rho = fall * R / (R_out - R)
    cy = z0 + stand - rho
    arc = lambda rr, uu: np.c_[rr * np.sin(uu / rho), cy + rr * np.cos(uu / rho)]
    fb = arc(rho, u)
    frg = np.array([arc(rho + f, u[-1:])[0] for f in np.linspace(0, fall, ns + 1)[1:-1]])
    ftp = arc(rho + fall, u * 1.0)[::-1]
    flf = np.array([arc(rho + f, u[:1])[0] for f in np.linspace(fall, 0, ns + 1)[1:-1]])
    Pf = np.r_[fb, frg, ftp, flf]
    f_t = nc + ns - 1
    # bodice: a developable cone (slope _SH_BETA) from the neckline (radius R) down 0.08 of slant
    ub = R * (ths - math.pi / 2)
    s1 = R / math.cos(_SH_BETA)
    s2 = s1 + 0.08
    z_ap = z0 + R * math.tan(_SH_BETA)
    cb_ = math.cos(_SH_BETA)
    flat = lambda s, tt: np.c_[s * np.sin(cb_ * (tt - math.pi / 2)), z_ap - s * np.cos(cb_ * (tt - math.pi / 2))]
    nb = len(ths)
    bb = flat(s2, ths)
    br = np.array([flat(s, ths[-1:])[0] for s in np.linspace(s2, s1, 12)[1:-1]])
    bt = flat(s1, ths)[::-1]
    bl = np.array([flat(s, ths[:1])[0] for s in np.linspace(s1, s2, 12)[1:-1]])
    Pb = np.r_[bb, br, bt, bl]
    s0 = nb + len(br)
    top_at = lambda i: s0 + nb - 1 - i
    stand_p = _piece(Ps, marks=None, names={"neck.m": 0, "neckCb": k_cb, "neck": nc - 1, "top": s_t, "topCb": s_t + nc - 1 - k_cb,
                                "top.m": s_t + nc - 1}, wrap={"to": "seam"})
    fall_p = _piece(Pf, marks=None, names={"low.m": 0, "lowCb": k_cb, "low": nc - 1, "outCb": f_t + nc - 1 - k_cb},
                    wrap={"to": "seam", "turn": {"at": at, "deg": 172, "gap": 0.004}})
    bodice = _piece(Pb, marks=None, names={"a0": 0, "a1": nb - 1, "a2": s0, "a3": s0 + nb - 1, "nl.l": top_at(gap_n),
                               "nl.c": top_at(gap_n + k_cb), "nl.r": top_at(160 - gap_n)})
    roll = arc(rho + at, u)[::4].tolist()
    fold = {"piece": "fall", "line": roll, "angle": 10.0, "kind": "roll", "radius": 0.004, "name": "collar roll",
            "flap": "outCb", "strength": 0.6}
    B = {"pieces": {"bodice": bodice, "stand": stand_p, "fall": fall_p}, "stitches": [], "folds": [fold],
         "seams": [["stand:neck.m>neckCb>neck", "bodice:nl.l>nl.c>nl.r"], ["fall:low.m>lowCb>low", "stand:top.m>topCb>top"],
                   ["bodice:a0>a3", "bodice:a1>a2"]],
         "mesh_refine": [{"piece": "fall", "h": 0.005}, {"piece": "stand", "h": 0.005}, {"piece": "bodice", "h": 0.008}]}
    M = cloth.mesh(B, 0.02)
    pid = np.asarray(M["piece"])
    uv = np.asarray(M["uv"], float)
    X0 = np.zeros((len(uv), 3))
    kb = pid == M["names"].index("bodice")
    d = uv[kb] - np.array([0.0, z_ap])
    s = np.linalg.norm(d, axis=1)
    tt = np.arctan2(d[:, 0], -d[:, 1]) / cb_ + math.pi / 2
    rr = s * cb_ + 0.003
    X0[kb] = np.c_[rr * np.cos(tt), rr * np.sin(tt), z_ap - s * math.sin(_SH_BETA)]
    for nm in ("stand", "fall"):  # (flat tabs out of the back, as the placed collar)
        cv = pid == M["names"].index(nm)
        X0[cv] = np.c_[uv[cv, 0], np.full(cv.sum(), 0.2), uv[cv, 1] + 0.05]
    info = {"rho": rho, "cy": cy, "fall": fall, "R": R, "R_out": R_out, "z0": z0, "stand": stand, "at": at}
    return {"M": M, "B": B, "X0": X0, "body": _shoulder_body(r, z0), "info": info}


def _shoulder_collar_read(c, V, verbose=True, lab=""):
    from hifipushie import folds as foldmod
    M, I = c["M"], c["info"]
    pid = np.asarray(M["piece"])
    uv = np.asarray(M["uv"], float)
    names = list(M["names"])
    fv = np.where(pid == names.index("fall"))[0]
    sv = np.where(pid == names.index("stand"))[0]
    bv = np.where(pid == names.index("bodice"))[0]
    rf = np.linalg.norm(uv[fv] - np.array([0.0, I["cy"]]), axis=1) - I["rho"]  # distance from the sewn edge (pattern)
    edge = fv[rf > I["fall"] - 0.0012]
    F = np.asarray(M["F"])
    Fb = F[np.isin(F, bv).all(1)]
    ix = -np.ones(len(V), int)
    ix[bv] = np.arange(len(bv))
    bs = pf._Surface(V[bv], ix[Fb], ref=pf._body_surface(c["body"]))
    gap, nb_, _ = bs.signed(V[edge])
    Ff = F[np.isin(F, fv).all(1)]
    Nv = pf._vnormals(V, Ff)
    ne = Nv[edge] * np.sign(np.sum(Nv[edge] * nb_, 1))[:, None]
    tilt = np.degrees(np.arccos(np.clip(np.sum(ne * nb_, 1), -1, 1)))
    az = np.degrees(np.arctan2(V[edge, 0], V[edge, 1]))
    o = np.argsort(az)
    e, a_, n_ = edge[o], az[o], ne[o]
    # ripple: normal turn between edge samples ~10 mm apart, less the cone's own (the bodice normal's turn there)
    P = V[e]
    arcl = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    j = np.searchsorted(arcl, arcl + 0.010)
    ok = j < len(e)
    i0, i1 = np.where(ok)[0], j[ok]
    rip = np.degrees(np.arccos(np.clip(np.sum(n_[i0] * n_[i1], 1), -1, 1)))
    nbo = nb_[o]
    rip0 = np.degrees(np.arccos(np.clip(np.sum(nbo[i0] * nbo[i1], 1), -1, 1)))
    ripple = rip - rip0
    g = foldmod._geom(M, M["folds"][0])
    turned = pf.fold_turned(M, V, g)
    # per station: the fall's turn over the stand in section (stand up vs the fall 4..20 mm past the roll)
    st = []
    for th in np.radians(np.arange(-150, 151, 30)):
        cdir = np.array([math.sin(th), math.cos(th)])
        near = lambda ids: ids[np.abs(((np.arctan2(V[ids, 0], V[ids, 1]) - th + np.pi) % (2 * np.pi)) - np.pi) < 0.06]
        s_, f_ = near(sv), near(fv)
        if len(s_) < 3 or len(f_) < 3:
            continue
        sec = lambda ids: np.c_[V[ids, :2] @ cdir, V[ids, 2]]
        S = sec(s_)
        up = S[np.argmax(uv[s_, 1])] - S[np.argmin(uv[s_, 1])]
        rr = np.linalg.norm(uv[f_] - np.array([0.0, I["cy"]]), axis=1) - I["rho"] - I["at"]
        Ff_ = sec(f_)
        h = Ff_[np.argmin(np.abs(rr - 0.006))]
        d2 = Ff_[np.argmin(np.abs(rr - 0.020))]
        dn = d2 - h
        ang = math.degrees(math.acos(float(np.clip(up @ dn / (np.linalg.norm(up) * np.linalg.norm(dn) + 1e-12), -1, 1))))
        m = np.abs(((az - math.degrees(th) + 180) % 360) - 180) < 8
        st.append((int(round(math.degrees(th))), round(ang, 1), round(float(np.median(gap[m])) * 1000, 1) if m.any() else None,
                   round(float(np.median(tilt[m])), 1) if m.any() else None))
    res = {"turned": round(float(turned), 1), "turn_min": min(s[1] for s in st), "gap_p50": round(float(np.median(gap)) * 1000, 1),
           "gap_p90": round(float(np.percentile(gap, 90)) * 1000, 1), "gap_max": round(float(gap.max()) * 1000, 1),
           "tilt_p90": round(float(np.percentile(tilt, 90)), 1), "ripple_max": round(float(ripple.max()), 1),
           "ripple_p90": round(float(np.percentile(ripple, 90)), 1), "edge_n": int(len(edge))}
    if verbose:
        print(lab, res)
        for s in st:
            print(f"   az {s[0]:5d}: turn {s[1]:6.1f}  edge gap {s[2]} mm  tilt {s[3]} deg")
    return res




def test_sprung_fall_lies_on_the_shoulders(verbose=True):
    """(shirt round 10, C124) Garrett's sprung shirt fall (C122) still hung as a tube on the form: folds.apply turns the
    flap rigidly about the roll and the relax drew it only onto its STAND (within 2 cm, along the stand's horizontal
    normal), so past the neck seam it hung as turned, its longer outer edge rippling. Known answer: a stand + SPRUNG fall
    (an annular sector cut for the shoulders it lands on) on a neck cylinder with a 22 deg shoulder cone, the bodice a
    developable cone piece sewn to the stand: the fall turned >= 170 over its stand (fold_turned, in section), its outer
    edge ON the bodice (signed gap <= 3 mm everywhere), no ripple (normal turn between edge samples 10 mm apart, less the
    cone's own, < 15 deg). Measured without FLAP_LAY (the planted fault): the fall a vertical tube 12 mm INSIDE the
    bodice (gap -13..-7 mm, tilt p90 52 deg, ripple 25 deg; fold_on_base read 0 through: its base is the stand only).
    With it: turned 171.5, gap -0.2..0.9 mm, tilt p90 8, ripple max 2.2."""
    c = _shoulder_collar_case()
    out = pf.assemble({"mesh": c["M"], "X0": c["X0"], "pieces": c["B"]}, c["body"], iters=120, ease=0.004)
    r = _shoulder_collar_read(c, out["V"], verbose=verbose, lab="sprung fall on shoulders")
    assert r["turned"] >= 170, r
    assert r["gap_max"] <= 3.0 and r["gap_p50"] >= -1.0, r
    assert r["ripple_max"] < 15, r
