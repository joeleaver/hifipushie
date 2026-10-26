"""Known answers for the canvas / interfacing bending stiffness (bending.py; garment_pull.STYLE_BEND; canvas thread,
2026-10-23). Each: a small strip in the styling solve (garment_pull.relax with its hang: a weak downward field, the
threads capped), bending ON at the module's default scale."""
import numpy as np
import pytest

from hifipushie import bending as bd
from hifipushie import garment_pull as gp


def _strip(L=0.12, W=0.04, nx=49, ny=9):
    uv = np.array([(x, y) for x in np.linspace(0, L, nx) for y in np.linspace(0, W, ny)])
    ix = lambda i, j: i * ny + j  # noqa: E731
    F = [f for i in range(nx - 1) for j in range(ny - 1)
         for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))]
    return {"F": np.array(F), "uv": uv, "piece": np.zeros(len(uv), int), "names": ["strip"], "sew": [], "points": {}}


@pytest.fixture
def bend_on(monkeypatch):
    monkeypatch.setattr(gp, "STYLE_BEND", True)


def _tip_drop(kind, verbose=True):
    M = _strip()
    X = np.c_[M["uv"], np.zeros(len(M["uv"]))]
    M["bend_w"] = np.full(len(X), bd.BEND_KIND[kind])
    Xn, inf = gp.relax(M, X, M["uv"][:, 0] < 0.012, hang=True, hang_iters=1500)
    tip = Xn[M["uv"][:, 0] > 0.1199]
    drop = -float(tip[:, 2].mean())
    if verbose:
        print(f"{kind:8s} tip drop {drop * 1000:6.1f} mm of 108 free, {inf}")
    return drop


def test_hinge_stencil_reads_the_fold_angle():
    """bending.hinges: the stencil vanishes on any planar placement (rotated, moved) and reads the fold angle of one
    hinge folded by 30 deg within 5 % (|alpha . x| = |e| sin-ish theta)."""
    M = _strip(L=0.02, W=0.02, nx=2, ny=2)  # (two triangles, one interior edge)
    H, al, el, ar = bd.hinges(M["F"], M["uv"])
    assert len(H) == 1
    th = 0.7
    R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
    X = np.c_[M["uv"], np.zeros(4)] @ R.T + [0.3, -0.1, 0.2]
    assert np.abs(al @ X[H[0]]).max() < 1e-12
    B = bd.Bending(M["F"], M["uv"], 4, np.ones(4), 1.0)
    # fold the far triangle about the shared edge (the diagonal) by 30 deg
    P = np.c_[M["uv"], np.zeros(4)]
    a, b, d = P[H[0, 0]], P[H[0, 1]], H[0, 3]
    ax = (b - a) / np.linalg.norm(b - a)
    r = P[d] - a
    t = np.radians(30)
    P[d] = a + r * np.cos(t) + np.cross(ax, r) * np.sin(t) + ax * np.dot(ax, r) * (1 - np.cos(t))
    assert abs(B.fold_deg(P)[0] - 30) < 1.5, B.fold_deg(P)


def test_canvassed_strip_holds_where_plain_cloth_bends(bend_on, verbose=True):
    """A 120 x 40 mm strip clamped at one end (12 mm), the rest free under the styling's hang: plain cloth hangs (its
    tip drops more than 60 % of the free 108 mm); fused interfacing holds better than plain; a canvassed strip holds
    near straight (tip drop under 15 mm: a canvassed lapel or chest keeps its shape with nothing holding it)."""
    d = {k: _tip_drop(k, verbose) for k in ("plain", "fusible", "canvas")}
    assert d["plain"] > 0.6 * 0.108, d
    assert d["canvas"] < 0.015, d
    assert d["canvas"] < d["fusible"] < d["plain"], d


def _rolled(R=0.012, turn=np.pi, L=0.10, nx=41, ny=17):
    """A collar strip ROLLED (made: interfaced and shaped) round a half cylinder of radius R about x: u along the
    roll's axis (L), v round it (R x turn)."""
    M = _strip(L=L, W=R * turn, nx=nx, ny=ny)
    u, v = M["uv"][:, 0], M["uv"][:, 1]
    a = v / R
    X = np.c_[u, R * np.sin(a), R - R * np.cos(a)]  # (from the stand's seam at the bottom, z = 0, up and over)
    return M, X


def _roll_radius(X, M):
    """Mean radius of each cross section's circle (Kasa fit in y / z), mm."""
    rs = []
    for u0 in np.unique(np.round(M["uv"][:, 0], 6))[2:-2]:
        s = X[np.abs(M["uv"][:, 0] - u0) < 1e-7][:, 1:]
        A = np.c_[2 * s, np.ones(len(s))]
        c = np.linalg.lstsq(A, (s ** 2).sum(1), rcond=None)[0]
        rs.append(np.sqrt(c[2] + c[0] ** 2 + c[1] ** 2))
    return 1000 * float(np.mean(rs))


def test_rolled_collar_keeps_its_roll(bend_on, verbose=True):
    """A collar's roll (a strip made round a 12 mm half cylinder, its edge at the top: 24 mm over the seam) held along
    its stand (its first 5 mm, sewn to the neckline), under the hang: interfaced (fusible) it keeps its roll (radius within 15 % of 12 mm, its edge
    within 4 mm of 24 mm up); plain it falls (its edge drops more than 10 mm). The styling rest is the made shape for
    interfaced cloth only (plain cloth rests flat), so the term holds the roll, not a flat strip."""
    out = {}
    for kind in ("plain", "fusible"):
        M, X = _rolled()
        M["bend_w"] = np.full(len(X), bd.BEND_KIND[kind])
        Xn, inf = gp.relax(M, X, M["uv"][:, 1] < 0.005, hang=True, hang_iters=1500)  # (the stand: sewn to its neckline)
        edge = M["uv"][:, 1] > M["uv"][:, 1].max() - 1e-7
        out[kind] = (_roll_radius(Xn, M), 1000 * float(Xn[edge, 2].mean()))
        if verbose:
            print(f"{kind:8s} roll radius {out[kind][0]:.1f} mm (made 12.0), edge {out[kind][1]:.1f} mm up (24), {inf}")
    assert abs(out["fusible"][0] - 12.0) <= 0.15 * 12.0, out
    assert abs(out["fusible"][1] - 24.0) <= 4.0, out
    assert out["plain"][1] < 24.0 - 10.0, out


def test_bending_keeps_a_declared_fold(bend_on, verbose=True):
    """A strip FOLDED 150 deg along its middle (a pressed fold: the rest shape carries it), held at one end, under the
    hang: with the stiffness on (canvas) the fold stays within 10 deg of 150 (the term never flattens a fold that is
    part of the rest)."""
    M = _strip(L=0.10, W=0.04, nx=41, ny=9)
    u = M["uv"][:, 0]
    t = np.radians(150)
    X = np.c_[M["uv"], np.zeros(len(u))]
    far = u > 0.05
    X[far, 0] = 0.05 + (u[far] - 0.05) * np.cos(t)
    X[far, 2] = (u[far] - 0.05) * np.sin(t)
    M["bend_w"] = np.full(len(X), bd.BEND_KIND["canvas"])
    Xn, _ = gp.relax(M, X, u < 0.012, hang=True, hang_iters=1500)
    a = Xn[(np.abs(u - 0.03) < 1e-7)].mean(0) - Xn[(np.abs(u - 0.05) < 1e-7)].mean(0)
    b = Xn[(np.abs(u - 0.07) < 1e-7)].mean(0) - Xn[(np.abs(u - 0.05) < 1e-7)].mean(0)
    ang = 180 - np.degrees(np.arccos(np.dot(a, b) / np.linalg.norm(a) / np.linalg.norm(b)))
    if verbose:
        print(f"fold {ang:.1f} deg (made 150)")
    assert abs(ang - 150) <= 10, ang


def test_drafted_canvas_region_covers_its_area():
    """An interfacing AREA (cloth.interfacing "region": a jacket forepart's half canvas, canvas s2): share 1 inside the
    drafted polygon and on its outline (the piece's own edges stay fully interfaced), ramping to 0 over "feather" outside;
    the bending weight follows (canvas 20)."""
    from hifipushie import cloth
    M = _strip(L=0.12, W=0.04, nx=49, ny=9)
    pc = {"name": "strip", "P": [[0, 0], [0.12, 0], [0.12, 0.04], [0, 0.04]], "names": {"a": 0, "b": 1, "c": 2, "d": 3}, "marks": {"m": [0.06, 0.0]}}
    Bp = {"pieces": {"strip": pc}, "interfaced": [{"piece": "strip", "region": ["a", "m", [0.06, 0.04], "d"],
                                                   "feather": 0.02, "kind": "canvas"}]}
    s = cloth.interfacing(Bp, M)
    u = M["uv"][:, 0]
    assert np.all(s[u < 0.06 + 1e-9] == 1.0) and np.all(s[u > 0.08 + 1e-9] == 0.0)
    assert np.allclose(s[np.abs(u - 0.07) < 1e-9], 0.5)
    w = bd.weights(Bp, M)
    assert np.isclose(w[u < 0.04].min(), bd.BEND_KIND["canvas"]) and np.isclose(w[u > 0.08].max(), 1.0)


def _walked_bend(kind):
    """A 120 mm strip clamped at one end (12 mm), resting flat; its tip walked in 20 steps round a quarter bend whose arc
    keeps the strip's length (a shape its threads allow). -> (thread strain max, mid-strip z mm, the arc's mid z mm)."""
    M = _strip()
    u = M["uv"][:, 0]
    X = np.c_[M["uv"], np.zeros(len(u))]
    M["bend_w"] = np.full(len(X), bd.BEND_KIND[kind])
    M["_bend_rest"] = X.copy()
    r = 0.108 * 2 / np.pi
    tip = u > 0.1199
    Xn = X.copy()
    for f in np.linspace(0.05, 1, 20):
        th, rf = (u[tip] - 0.012) / r * f, r / f
        Xn[tip, 0] = 0.012 + rf * np.sin(th)
        Xn[tip, 2] = -(rf - rf * np.cos(th))
        Xn, _ = gp.relax(M, Xn, (u < 0.012) | tip, iters=40)
    ln = _thread_lengths(M, Xn)
    um = u[np.argmin(np.abs(u - 0.066))]
    mid = np.abs(u - um) < 1e-7
    return (float(ln.max() - 1), 1000 * float(Xn[mid, 2].mean()), -1000 * (r - r * np.cos((um - 0.012) / r)),
            float(1 - ln.min()))


def _thread_lengths(M, X):
    """Per face warp / weft length (pattern = 1): > 1 stretched, < 1 eased."""
    F, D = gp.thread_faces(M)
    return np.linalg.norm(np.stack([X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]]], -1) @ D, axis=1)


def test_stiffness_never_buys_shape_with_stretch(bend_on, verbose=True):
    """THREADS FIRST (canvas s2; Joe: "it shouldn't really be a choice between stiffness and stretch"): bending stiffness
    changes how cloth bends, never how far its threads give. A canvassed strip walked round a bend its threads allow
    keeps its threads within ~1 % (the weighted sum alone bought the stiff shape with 12.4 % strain) and takes the
    bend's arc (the least-bending shape the threads allow: mid within 3 mm); plain cloth's threads stay within 1 % too.
    (C225, canvas s15: the threads' hard rule is STRETCH, read apart from easing: a thread may ease / buckle shorter,
    here up to 2 %, as the cap no longer pushes eased faces back out.)"""
    out = {k: _walked_bend(k) for k in ("plain", "canvas")}
    if verbose:
        print(out)
    assert out["plain"][0] < 0.0125 and out["canvas"][0] < 0.015, out
    assert out["plain"][3] < 0.02 and out["canvas"][3] < 0.02, out
    assert abs(out["canvas"][1] - out["canvas"][2]) < 3.0, out


def test_threads_outweigh_bending_in_the_one_solve(bend_on, monkeypatch, verbose=True):
    """C209 (canvas s9): under STYLE_TF_PD the threads' term in the global step weighs STYLE_TF_PD_MEM x the stiff
    cloth's median bending weight (at weight 1 the canvas bending was ~3900 x the threads: Garrett d2's hem pull, a
    solve with nothing moved, tore the canvassed lapel 6.9 -> 63 %; with the weight 6.9 %). Here: the weight is applied,
    and a canvassed rolled strip swung 15 deg off its made roll, its stand held, relaxes with its threads within 1.5 %."""
    monkeypatch.setattr(gp, "STYLE_TF_PD", True)
    M, X = _rolled()
    M["bend_w"] = np.full(len(X), bd.BEND_KIND["canvas"])
    M["_bend_rest"] = X.copy()
    A = gp.FlatARAP(M, X)
    kd = A.bend.K.diagonal()
    if gp.STYLE_TF_PD_LOCAL:  # (C226: per face; at every stiff vertex the threads' diagonal >= MEM x its bending's)
        st = kd > 0
        assert np.all(A.L0.diagonal()[st] >= 0.99 * gp.STYLE_TF_PD_MEM * kd[st]), A.mem_w
    else:
        assert A.mem_w * np.median(A.L0.diagonal()) >= 0.99 * gp.STYLE_TF_PD_MEM * np.median(kd), A.mem_w
    held = M["uv"][:, 1] < 0.005
    c, s = np.cos(np.radians(15)), np.sin(np.radians(15))
    Y = X.copy()
    Y[~held] = X[~held] @ np.array([[1, 0, 0], [0, c, -s], [0, s, c]]).T
    for _ in range(3):
        Y, _inf = gp.relax(M, Y, held, hang=False)
    t, _ = gp.thread_strain(M, Y)
    if verbose:
        print("mem_w", A.mem_w, "threads p99", np.percentile(t.max(1), 99))
    assert np.percentile(t.max(1), 99) < 0.015


def test_pressed_canvas_keeps_its_pressing_through_the_styling(bend_on, monkeypatch, verbose=True):
    """C214 (canvas s11): a strip PRESSED into a curve (the rolled strip: canvas pad-stitched and steamed round a 12 mm
    half cylinder, its rest = that shape, the styling start) held along its first 5 mm, through a styling relax AND a
    smooth (the hand flattening ripples): canvassed it keeps its pressing (radius within 15 % of 12 mm, edge within
    4 mm of 24 mm up); plain cloth does not (it falls, edge > 10 mm lower). With SMOOTH_PRESSED off the smooth's fair
    aims at zero curvature and irons the canvas's pressing out too (the A/B the default switch rests on)."""
    monkeypatch.setattr(gp, "SMOOTH_PRESSED", True)
    out = {}
    for kind in ("plain", "canvas"):
        M, X = _rolled()
        M["bend_w"] = np.full(len(X), bd.BEND_KIND[kind])
        M["_bend_rest"] = X.copy()
        held = M["uv"][:, 1] < 0.005
        X1, _ = gp.relax(M, X, held, hang=True, hang_iters=1500)
        X2, inf = gp.smooth(M, X1, held, ["strip"], tol=0.02)
        edge = M["uv"][:, 1] > M["uv"][:, 1].max() - 1e-7
        out[kind] = (_roll_radius(X2, M), 1000 * float(X2[edge, 2].mean()), inf["rounds"])
        if verbose:
            print(f"{kind:8s} pressed roll radius {out[kind][0]:.1f} mm (12.0), edge {out[kind][1]:.1f} mm up (24), smooth {inf}")
    assert abs(out["canvas"][0] - 12.0) <= 0.15 * 12.0, out
    assert abs(out["canvas"][1] - 24.0) <= 4.0, out
    assert out["plain"][1] < 24.0 - 10.0, out
    # (the A/B: the same canvas strip smoothed flat-aimed loses more of its pressing)
    monkeypatch.setattr(gp, "SMOOTH_PRESSED", False)
    M, X = _rolled()
    M["bend_w"] = np.full(len(X), bd.BEND_KIND["canvas"])
    M["_bend_rest"] = X.copy()
    held = M["uv"][:, 1] < 0.005
    X1, _ = gp.relax(M, X, held, hang=True, hang_iters=1500)
    X2, inf = gp.smooth(M, X1, held, ["strip"], tol=0.02)
    r_flat = _roll_radius(X2, M)
    if verbose:
        print(f"canvas, flat-aimed smooth: radius {r_flat:.1f} mm, {inf}")
    assert abs(out["canvas"][0] - 12.0) <= abs(r_flat - 12.0) + 0.05, (out, r_flat)


def test_threads_first_never_pushes_eased_cloth_out(bend_on, monkeypatch, verbose=True):
    """C225 (canvas s15): THREADS FIRST IS NO THREAD LONGER, NOT NONE SHORTER. A canvassed strip folded 170 deg along its
    middle (a lapel's edge with its facing turned under), the facing half pressed in EASED (its threads laid 4 % short:
    its rest), held at one end, through the stiff styling's hang: it keeps its ease (a thread still >= 2.5 % short) and
    no thread stretches past 0.5 %. With the old two-sided caps (THREAD_CAP_LO: eased faces pushed back out to 1 %) the
    ease is ironed out (<= 1.5 %): on Garrett's open jacket that push-out, at the lapel's roll above the break (78 faces
    of ~3 mm2), stretched their neighbours and took the canvas threads p99 5.8 -> 12.4 % in one relax."""
    out = {}
    for lo in (True, False):
        monkeypatch.setattr(gp, "STYLE_THREAD_CAP_LO", lo)
        M = _strip(L=0.10, W=0.04, nx=41, ny=9)
        u = M["uv"][:, 0]
        X = np.c_[M["uv"], np.zeros(len(u))]
        far = u > 0.05
        s_ = (u[far] - 0.05) * (1 - 0.04)
        t = np.radians(170)
        X[far, 0] = 0.05 + s_ * np.cos(t)
        X[far, 2] = s_ * np.sin(t)
        M["bend_w"] = np.full(len(X), bd.BEND_KIND["canvas"])
        M["_bend_rest"] = X.copy()
        Xn, _ = gp.relax(M, X, u < 0.012, hang=True, hang_iters=600)
        ln = _thread_lengths(M, Xn)
        out[lo] = (float(ln.max() - 1), float(1 - ln.min()))
        if verbose:
            print(f"cap lo {lo}: stretch max {out[lo][0] * 100:.2f} %, ease max {out[lo][1] * 100:.2f} %")
    assert out[False][1] >= 0.025 and out[False][0] <= 0.005, out
    assert out[True][1] <= 0.015, out


def test_a_canvassed_panel_lets_its_plain_cloth_hang(bend_on, verbose=True):
    """C226 (canvas s15): THE THREADS OUTWEIGH THE BENDING WHERE THERE IS BENDING. A woven sheet (300 x 400 mm, top edge
    held, started 30 deg off plumb: test_garment_pull's hung sheet) canvassed over its top 160 mm, plain below, under the
    stiff styling's hang: the plain cloth hangs (its hem at least 75 % of the way from where it started to plumb under
    the canvas's lower edge) with its threads p99 under 3 % (the default styling's hung sheet, no bending: 1.9 %, its
    bound 2.5 %; here the canvas rows by the hold carry the plain cloth's weight: 2.4 %). With C209's one scalar weight
    (x ~13000 on every face: within its band a face's threads term is a lag spring on every move) the hem does not move
    (under 20 % of the way): Garrett's stiff-styled lower front never hung (o0b). The canvas itself keeps its stiffness
    (test_canvassed_strip_holds_where_plain_cloth_bends)."""
    import importlib, sys as _s
    sys_path = __import__("os").path.dirname(__file__)
    if sys_path not in _s.path:
        _s.path.insert(0, sys_path)
    hung = importlib.import_module("test_garment_pull")._hung_sheet
    out = {}
    for case in ("plain", "scalar", "local"):
        M, X, top = hung()
        v = M["uv"][:, 1]
        M["bend_w"] = np.ones(len(X)) if case == "plain" else np.where(v > 0.24, bd.BEND_KIND["canvas"], 1.0)
        M["_bend_rest"] = X.copy()
        old = gp.STYLE_TF_PD_LOCAL
        gp.STYLE_TF_PD_LOCAL = case != "scalar"
        try:
            Xn, _ = gp.relax(M, X, top, hang=True)
        finally:
            gp.STYLE_TF_PD_LOCAL = old
        hem0, hem = X[v < 1e-9, 1].mean(), Xn[v < 1e-9, 1].mean()
        ce = Xn[np.abs(v - 0.24) < 0.008, 1].mean()
        out[case] = ((hem - hem0) / (ce - hem0), float(np.percentile(_thread_lengths(M, Xn).max(1) - 1, 99)))
        if verbose:
            print(f"{case:7s}: hem {(hem - hem0) * 1000:.0f} mm of {(ce - hem0) * 1000:.0f} to plumb ({out[case][0]:.2f}), "
                  f"stretch p99 {out[case][1] * 100:.2f} %")
    assert out["local"][0] >= 0.75, out
    assert out["scalar"][0] < 0.2, out
    assert out["local"][1] <= 0.03, out
