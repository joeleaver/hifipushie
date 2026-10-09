"""Made pieces constructed on a finished drape (cloth_made): a shirt collar on a synthetic neck, a pressed flap.
Run: uv run python tests/test_cloth_made.py  (or pytest)."""
import numpy as np

from hifipushie import cloth_made as cm
from hifipushie import cloth_layers


def _neck(n_ang=96, n_z=60):
    """A body of revolution about z: a neck (r 60 mm) on shoulders sloping away below z = 0; closed top and bottom."""
    zs = np.linspace(-0.12, 0.16, n_z)
    r = np.where(zs > 0, 0.060 + 0.0 * zs, 0.060 + 0.9 * np.abs(zs) ** 1.0)
    r = np.where(np.abs(zs) < 0.015, 0.060 + 0.9 * (0.015 - zs) ** 2 / 0.06, r)  # a rounded corner
    th = np.linspace(0, 2 * np.pi, n_ang, endpoint=False)
    V = np.stack([np.outer(r, np.cos(th)), np.outer(r, np.sin(th)), np.repeat(zs[:, None], n_ang, 1)], -1).reshape(-1, 3)
    F = []
    for i in range(n_z - 1):
        for j in range(n_ang):
            a, b = i * n_ang + j, i * n_ang + (j + 1) % n_ang
            F += [[a, b, b + n_ang], [a, b + n_ang, a + n_ang]]
    top, bot = len(V), len(V) + 1
    V = np.concatenate([V, [[0, 0, zs[-1]], [0, 0, zs[0]]]])
    for j in range(n_ang):
        F.append([(n_z - 1) * n_ang + j, (n_z - 1) * n_ang + (j + 1) % n_ang, top])
        F.append([(j + 1) % n_ang, j, bot])
    return V, np.array(F)


def _neckline(open_deg=40.0, n=41, z=-0.012, off=0.004):
    """A seam round the neck's base, open at the front (-y), from one front end round the back to the other."""
    a0 = np.radians(-90 + open_deg / 2)
    th = np.linspace(a0, a0 + np.radians(360 - open_deg), n)
    r = 0.060 + 0.9 * abs(z) + off
    return np.stack([r * np.cos(th), r * np.sin(th), np.full(n, z)], 1)


def _build(**kw):
    V, F = _neck()
    P = _neckline()
    out = cm.shirt_collar(P, {"V": V, "F": F}, [], (np.zeros(3), np.array([0, 0, 1.0])), **kw)
    return V, F, P, out


def test_shirt_collar_honours_its_parameters():
    V, F, P, out = _build(stand=0.028, fall_over=0.012, points=0.07, open=0.0)
    stand, fall = out["parts"]
    n, m = stand["grid"]
    S = stand["V"].reshape(n, m, 3)
    assert np.allclose(S[::2][:len(P)][:, 0][0], P[0], atol=1e-9)  # the seam row starts on the seam
    # every seam vertex is a vertex of the stand's first row (welded: no gap)
    d = np.linalg.norm(S[:, 0][None] - P[:, None], axis=2).min(1)
    assert d.max() < 1e-9
    cb = n // 2
    rise = np.linalg.norm(np.diff(S[cb], axis=0), axis=1).sum()
    assert abs(rise - 0.028) < 0.002, rise
    assert S[cb, -1, 2] - S[cb, 0, 2] > 0.022  # it stands
    nf, mf = fall["grid"]
    G = fall["V"].reshape(nf, mf, 3)
    cbf = nf // 2
    depth = np.linalg.norm(np.diff(G[cbf], axis=0), axis=1).sum()
    assert abs(depth - 0.040) < 0.004, depth
    assert G[cbf, -1, 2] < S[cb, 0, 2] + 0.004  # the fall covers the seam at centre back
    # the points: as long as asked, in the pattern and as laid
    uv = fall["uv"].reshape(nf, mf, 2)
    for k in (0, nf - 1):
        assert abs(np.linalg.norm(uv[k, -1] - uv[k, 0]) - 0.07) < 0.002
        laid = np.linalg.norm(np.diff(G[k], axis=0), axis=1).sum()
        assert abs(laid - 0.07) < 0.008, laid
    # near isometric
    assert 0.9 < out["info"]["fall_stretch"]["p50"] < 1.06
    assert out["info"]["fall_stretch"]["p95"] < 1.35


def test_shirt_collar_clears_the_body():
    V, F, P, out = _build()
    Fo = cm.outward(V, F)
    for pt in out["parts"]:
        assert cloth_layers.between_crossings(pt["V"], pt["F"], V, Fo) == 0, pt["name"]
        Q, N, _ = cm.closest(pt["V"], V, Fo)
        sd = ((pt["V"] - Q) * N).sum(1)
        assert sd.min() > 0.0005, (pt["name"], sd.min())
    # a taller stand is taller; a longer point is longer
    a = _build(stand=0.022)[3]["parts"][0]
    b = _build(stand=0.032)[3]["parts"][0]
    assert b["V"][:, 2].max() - a["V"][:, 2].max() > 0.006


def test_solid_is_closed():
    V, F, P, out = _build()
    pt = out["parts"][1]
    Vs, Fs = cm.solid(pt["V"], pt["F"], 0.0016)
    E = np.sort(np.concatenate([Fs[:, [0, 1]], Fs[:, [1, 2]], Fs[:, [2, 0]]]), axis=1)
    _, cnt = np.unique(E, axis=0, return_counts=True)
    assert (cnt == 2).all()


def test_press_flap_lays_the_mirror_image():
    # a flat square piece, the strip x > 0.08 folded over the line x = 0.08
    xs = np.linspace(0, 0.12, 13)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    uv = np.stack([X.ravel(), Y.ravel()], 1)
    V = np.c_[uv, np.zeros(len(uv))]
    F = cm.grid_faces(13, 13)
    flap = np.where(uv[:, 0] > 0.08 + 1e-9)[0]
    Vn = cm.press_flap(V, F, uv, flap, ((0.08, 0.0), (0.0, 1.0)), lay=0.003, wedge=0.35,
                       out=np.tile([0, 0, 1.0], (len(V), 1)))
    assert np.allclose(Vn[flap, 0], 0.16 - uv[flap, 0], atol=1e-9)
    assert np.allclose(Vn[flap, 1], uv[flap, 1], atol=1e-9)
    assert (Vn[flap, 2] > 0).all() and Vn[flap, 2].max() <= 0.003 + 1e-12
    keep = np.setdiff1d(np.arange(len(V)), flap)
    assert np.allclose(Vn[keep], V[keep])


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
