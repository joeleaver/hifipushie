"""groundtruth: the surface-distance measure (spikes/groundtruth/gt.py) on synthetic cases with known answers.
Run: uv run python tests/test_groundtruth.py (no dataset needed)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spikes" / "groundtruth"))
import gt  # noqa: E402


def _sphere(r, n=48, centre=(0.0, 0.0, 0.0)):
    th, ph = np.meshgrid(np.linspace(0, np.pi, n), np.linspace(0, 2 * np.pi, 2 * n, endpoint=False), indexing="ij")
    V = r * np.stack([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)], -1).reshape(-1, 3) + np.asarray(centre)
    m = 2 * n
    F = []
    for i in range(n - 1):
        for j in range(m):
            a, b, c, d = i * m + j, i * m + (j + 1) % m, (i + 1) * m + (j + 1) % m, (i + 1) * m + j
            F += [[a, c, b], [a, d, c]]
    return V, np.asarray(F)


def test_point_to_triangle_exact():
    """One triangle: points over its inside, an edge and a corner; distances by hand."""
    V = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0]])
    s = gt.Surface(V, np.array([[0, 1, 2]]))
    P = np.array([[0.2, 0.2, 0.5], [0.5, -0.3, 0.0], [-1.0, -1.0, 0.0], [1.0, 1.0, 0.0], [2.0, 0.0, 1.0]])
    Q, d, fi, bw = s.closest(P)
    want = np.array([0.5, 0.3, np.sqrt(2), np.sqrt(0.5), np.sqrt(2)])
    assert np.allclose(d, want, atol=1e-12), (d, want)
    assert np.allclose(Q[0], [0.2, 0.2, 0]) and np.allclose(Q[1], [0.5, 0, 0]) and np.allclose(Q[2], [0, 0, 0]) and np.allclose(Q[3], [0.5, 0.5, 0])
    assert np.allclose((bw[:, :, None] * V[None]).sum(1), Q)


def test_two_spheres():
    """A sphere inside a sphere 2 mm larger: the two-sided distance is 2 mm (to the faceting: a 96-gon's sagitta),
    and it does NOT depend on where the vertices sit (the second sphere is tessellated differently and turned)."""
    Va, Fa = _sphere(0.100, 48)
    Vb, Fb = _sphere(0.102, 37)
    Vb = Vb @ gt.rotvec([0.3, -0.2, 0.5]).T
    r = gt.two_sided(Va, Fa, Vb, Fb)
    sag = 0.102 * (1 - np.cos(np.pi / 37))          # the coarser mesh's flat faces stand this far inside its sphere
    assert abs(r["a2b"].mean() - 0.002) < sag and abs(r["b2a"].mean() - 0.002) < sag, (r["a2b"].mean(), r["b2a"].mean(), sag)
    assert r["a2b"].max() < 0.002 + 1e-9 and r["a2b"].min() > 0.002 - sag - 1e-9
    assert abs(r["mean"] - 0.002) < sag and r["p90"] < 0.0021 + sag


def test_shifted_plane_and_nearest_vertex_bias():
    """A coarse plane (two big triangles) against a fine plane 3 mm above it: point-to-SURFACE is 3 mm everywhere; a
    nearest-VERTEX distance would be up to half a metre. This is why the measure is point-to-triangle."""
    A = np.array([[0.0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]])
    FA = np.array([[0, 1, 2], [0, 2, 3]])
    g = np.linspace(0.1, 0.9, 30)
    X, Y = np.meshgrid(g, g)
    B = np.c_[X.ravel(), Y.ravel(), np.full(X.size, 0.003)]
    n = len(g)
    FB = np.array([[i * n + j, i * n + j + 1, (i + 1) * n + j + 1] for i in range(n - 1) for j in range(n - 1)]
                  + [[i * n + j, (i + 1) * n + j + 1, (i + 1) * n + j] for i in range(n - 1) for j in range(n - 1)])
    d = gt.Surface(A, FA).closest(B)[1]
    assert np.allclose(d, 0.003, atol=1e-12), (d.min(), d.max())
    from scipy.spatial import cKDTree
    assert cKDTree(A).query(B)[0].max() > 0.5


def test_similarity_roundtrip():
    rng = np.random.default_rng(3)
    P = rng.standard_normal((40, 3))
    S = (1.07, gt.rotvec([0.2, -0.4, 0.9]), np.array([0.3, -0.1, 2.0]))
    Q = gt.apply(S, P)
    s, R, t = gt.umeyama(P, Q)
    assert abs(s - 1.07) < 1e-9 and np.allclose(R, S[1]) and np.allclose(t, S[2])
    assert np.allclose(gt.apply(gt.inverse(S), Q), P)
    S2 = (0.9, gt.rotvec([-0.1, 0.3, 0.2]), np.array([1.0, 2.0, 3.0]))
    assert np.allclose(gt.apply(gt.compose(S2, S), P), gt.apply(S2, gt.apply(S, P)))


def test_region_table_on_a_known_offset():
    """GNM's own head against a copy of itself pushed 1.5 mm out along its normals (as a 'scan'): every region reads
    1.5 mm (+- the offset surface's curvature error), signed +, both directions. Skipped without the GNM asset."""
    try:
        G = gt.gnm()
    except Exception as e:      # the asset pack is not on this machine
        print("skipped (no GNM asset):", str(e)[:80])
        if "pytest" in sys.modules:
            import pytest
            pytest.skip("no GNM asset pack")
        return "skipped"
    V = gt.verts(np.zeros(170))
    F = G["F"]
    vn = gt.vertex_normals(V, F)
    used = np.zeros(len(V), bool)
    used[F.ravel()] = True
    Vs = np.where(used[:, None], V + 0.0015 * vn, V)
    Vs2, Fs2, _ = gt.submesh(Vs, F, used)
    g = gt.gaps(V, gt.Surface(Vs2, Fs2), samples=Vs2, sample_normals=gt.vertex_normals(Vs2, Fs2))
    for k in ("forehead", "nose", "cheeks", "chin", "jaw line", "face"):
        t = g["table"][k]
        assert abs(t["mean"] - 1.5) < 0.15, (k, t)
        assert abs(t["signed"] - 1.5) < 0.2, (k, t)
        assert abs(t["g2s"] - 1.5) < 0.2 and abs(t["s2g"] - 1.5) < 0.2, (k, t)


if __name__ == "__main__":
    n = sk = 0
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            r = f()
            n += 1
            sk += r == "skipped"
            print("ok" if r != "skipped" else "SKIPPED", k)
    print(f"{n} tests, {sk} skipped")
