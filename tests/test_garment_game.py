"""garment_game known answers: two flat panels sewn along one edge, re-gridded in pattern space."""
import numpy as np

from hifipushie import garment_game as gg


def _grid(n, x0):
    xs = np.linspace(0, 0.2, n)
    U, V = np.meshgrid(xs, xs, indexing="ij")
    uv = np.stack([U.ravel(), V.ravel()], 1)
    q = np.arange(n * n).reshape(n, n)
    a, b, c, d = q[:-1, :-1].ravel(), q[1:, :-1].ravel(), q[1:, 1:].ravel(), q[:-1, 1:].ravel()
    F = np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d], 1)])
    P = np.stack([uv[:, 0] + x0, uv[:, 1], np.zeros(len(uv))], 1)
    return uv, F, P, q


def _drape(n=11):
    uvA, FA, PA, qA = _grid(n, 0.0)
    uvB, FB, PB, qB = _grid(n, 0.2)
    off = len(uvA)
    sew = np.stack([qA[-1, :], qB[0, :] + off], 1)  # A's right edge to B's left edge
    return {"name": "test", "V": np.vstack([PA, PB]), "F": np.vstack([FA, FB + off]), "uv": np.vstack([uvA, uvB]),
            "piece": np.r_[np.zeros(off, int), np.ones(off, int)], "names": ["A", "B"], "sew": sew,
            "sew_seam": np.zeros(len(sew), int), "made": [], "drop": set(), "color": "#808080", "thickness": 0.001}


def test_seam_shared_no_cracks_and_area_kept():
    d = _drape()
    for h in (0.02, 0.035, 0.07):
        pieces = gg.remesh(d, h)
        assert all(p["missing_boundary_edges"] == 0 for p in pieces)
        m = gg.merged(pieces)
        V, T = m["V"], m["T"]
        area = 0.5 * np.linalg.norm(np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]), axis=1).sum()
        assert abs(area - 0.08) < 1e-6, area
        # the seam: vertices on x = 0.2 from both panels share welded ids and positions
        on = np.abs(V[:, 0] - 0.2) < 1e-9
        assert set(m["piece"][on]) == {0, 1}
        acc = {}
        for w, p in zip(m["weld"][on], V[on]):
            acc.setdefault(w, []).append(p)
        assert all(len(v) == 2 for v in acc.values())
        # one consistent winding, no folded faces
        fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
        assert (np.sign(fn[:, 2]) == np.sign(fn[0, 2])).all()
        assert gg.folded_faces(V, T) == 0


def test_density_follows_h_and_rims_only_on_free_edges():
    d = _drape()
    n = [len(gg.merged(gg.remesh(d, h))["T"]) for h in (0.02, 0.04)]
    assert 3.0 < n[0] / n[1] < 5.0  # triangles ~ 1 / h^2
    m = gg.merged(gg.remesh(d, 0.04))
    sh = gg.shell(m, m["T"])
    # free boundary = the outline of the joined 0.4 x 0.2 sheet (1.2 m), ~h apart: 2 rim triangles per edge
    assert abs(sh["rim_faces"] / 2 - 1.2 / 0.04) <= 4
    assert sh["inner_faces"] == sh["outer_faces"] == len(m["T"])


def test_pierce_faces_known_answers():
    """Face-level pierce: crossing between the under sheet's vertices is caught (the vertex test misses it); two
    parallel sheets 2 mm apart are not; a plane through the sheet finds exactly the faces it cuts."""
    gg._selftest_pierce_faces()
