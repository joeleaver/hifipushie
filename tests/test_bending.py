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
    t, _ = gp.thread_strain(M, Xn)
    um = u[np.argmin(np.abs(u - 0.066))]
    mid = np.abs(u - um) < 1e-7
    return float(t.max()), 1000 * float(Xn[mid, 2].mean()), -1000 * (r - r * np.cos((um - 0.012) / r))


def test_stiffness_never_buys_shape_with_stretch(bend_on, verbose=True):
    """THREADS FIRST (canvas s2; Joe: "it shouldn't really be a choice between stiffness and stretch"): bending stiffness
    changes how cloth bends, never how far its threads give. A canvassed strip walked round a bend its threads allow
    keeps its threads within ~1 % (the weighted sum alone bought the stiff shape with 12.4 % strain) and takes the
    bend's arc (the least-bending shape the threads allow: mid within 3 mm); plain cloth's threads stay within 1 % too."""
    out = {k: _walked_bend(k) for k in ("plain", "canvas")}
    if verbose:
        print(out)
    assert out["plain"][0] < 0.01 and out["canvas"][0] < 0.015, out
    assert abs(out["canvas"][1] - out["canvas"][2]) < 3.0, out
