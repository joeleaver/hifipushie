"""eyedetail: the face stage's local refinement (scene.refine_box's exact box cut) and the lash ribbons (lashes.py)
on a synthetic eye: a ball behind a skin sheet with an almond hole."""
import numpy as np

from hifipushie import lashes, scene


def _plane(n=21):
    xs = np.linspace(-1, 1, n)
    X, Y = np.meshgrid(xs, xs)
    V = np.c_[X.ravel(), Y.ravel(), np.zeros(X.size)]
    F = []
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j
            F += [[a, a + 1, a + n + 1], [a, a + n + 1, a + n]]
    return V, np.tile([0, 0, 1.0], (len(V), 1)), np.array(F)


def _area(V, F):
    return 0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1).sum()


def test_box_split_is_exact():
    V, N, F = _plane()
    lo, hi = np.array([-0.33, -0.27, -1.0]), np.array([0.41, 0.5, 1.0])
    V2, N2, fi, fo = scene._box_split(V, N, F, lo, hi)
    assert abs(_area(V2, fi) - 0.74 * 0.77) < 1e-9
    assert abs(_area(V2, fi) + _area(V2, fo) - 4.0) < 1e-9
    assert np.all(V2[np.unique(fi)] >= lo - 1e-12) and np.all(V2[np.unique(fi)] <= hi + 1e-12)
    assert np.allclose(np.linalg.norm(N2, axis=1), 1.0)


def _eye_head(r=0.012, hole=(0.010, 0.005), y0=-0.0125):
    """A skin sheet (facing -y) in front of an eyeball at the origin, with an almond hole: the head dict lashes reads."""
    n = 161
    xs = np.linspace(-0.03, 0.03, n)
    X, Z = np.meshgrid(xs, xs)
    a, b = hole
    inside = (X / a) ** 2 + (Z / b) ** 2 < 1
    V = np.c_[X.ravel(), np.full(X.size, y0), Z.ravel()]
    F = []
    for i in range(n - 1):
        for j in range(n - 1):
            q = [i * n + j, i * n + j + 1, (i + 1) * n + j + 1, (i + 1) * n + j]
            if not any(inside.ravel()[q]):
                F.append(q)
    from scipy.spatial import cKDTree
    return {"verts": V, "faces": F, "normals": np.tile([0, -1.0, 0], (len(V), 1)), "eyes": [np.array([0.03, 0.0, 0.0]) * 0],
            "eye_r": r, "forward": np.array([0, -1.0, 0]), "tree": cKDTree(V)}


def test_lid_lines_find_the_hole():
    head = _eye_head()
    head["eyes"] = [np.array([0.0, 0.0, 0.0])]
    L = lashes.lid_lines(head)[0]
    top = L["o2"][1] + L["rho"][np.argmax(L["dirs"] @ L["up"])]
    width = np.ptp(L["o2"][0] + (L["dirs"] @ L["side"]) * L["rho"])
    assert abs(top - 0.005) < 0.0006, top
    assert abs(width - 0.020) < 0.0012, width


def test_lashes_build():
    head = _eye_head()
    head["eyes"] = [np.array([0.0, 0.0, 0.0])]
    cfg = lashes.wanted({"base": {"lashes": {"upper": {"count": 40, "curl": 68}, "lower": {"count": 20}}}})
    m = lashes.build(head, cfg)
    seg = cfg["segments"]
    assert len(m["tris"]) == (40 + 20) * 2 * seg
    assert np.isfinite(m["verts"]).all()
    # every lash point outside the ball and in front of the skin sheet
    assert (np.linalg.norm(m["verts"], axis=1) > head["eye_r"] - 1e-5).all()
    assert (m["verts"][:, 1] <= -0.0125 + 1e-6 + 2e-3).all()
    up = m["lid"] == 0
    # upper lashes end above their roots, lower ones below
    tips = m["along"] == 1.0
    assert (m["verts"][up & tips, 2] > m["root"][up & tips, 2]).mean() > 0.9
    assert (m["verts"][~up & tips, 2] < m["root"][~up & tips, 2]).mean() > 0.9


def test_lash_shapes_ride_the_lid():
    """A lid vertex turned 25 deg down about the eye's x axis: its lash turns rigidly with it."""
    c = np.array([0.03, 0.0, 1.6])
    root = c + np.array([0.0, -0.012, 0.004])
    ang = np.radians(-25)

    def rot(q, a):
        return np.c_[q[:, 0], np.cos(a) * q[:, 1] + np.sin(a) * q[:, 2], -np.sin(a) * q[:, 1] + np.cos(a) * q[:, 2]]
    lash = root + np.array([[0, 0, 0], [0, -0.003, 0.001], [0, -0.006, 0.003]])
    part = {"verts": lash, "lash_root": np.repeat(root[None], 3, 0), "lash_centre": np.repeat(c[None], 3, 0)}
    skinX = np.array([root, root + [0.01, 0, 0]])
    d = rot(skinX - c, ang) + c - skinX
    D = lashes.shapes_from_lids(part, [(skinX, {"eyeBlinkLeft": d, "jawOpen": np.zeros_like(d)})],
                                ["eyeBlinkLeft", "jawOpen"])
    want = rot(lash - c, ang) + c - lash
    assert np.allclose(D["eyeBlinkLeft"], want, atol=1e-9)
    assert np.abs(D["jawOpen"]).max() == 0


def test_aperture_from_mask():
    """Two almond openings (picture left / right): heights, widths and corner angles from the mask."""
    from hifipushie import aperture
    H, W = 200, 400
    y, x = np.mgrid[0:H, 0:W].astype(float)
    m = np.zeros((H, W), bool)
    for cx in (100, 300):
        # a lens: two circular arcs meeting at the corners, 120 px wide, 40 px tall
        half, h = 60.0, 20.0
        R = (half ** 2 + h ** 2) / (2 * h)
        up = np.hypot(x - cx, y - (100 + R - h)) < R
        lo = np.hypot(x - cx, y - (100 - R + h)) < R
        m |= up & lo
    r = aperture.from_mask(m, 0.1)
    assert len(r) == 2
    for e in r:
        assert abs(e["open"] - 4.0) < 0.25, e
        assert abs(e["width"] - 12.0) < 0.3, e
        # a lens of half-width 60, sagitta 20: each arc leaves the corner at atan(2 h / half) ~ 33.7 deg -> ~67 deg
        assert 50 < e["inner_angle"] < 80 and 50 < e["outer_angle"] < 80, e


def test_lashes_default_and_off():
    assert lashes.wanted({"base": {"body": {"source": "human"}, "head": {"seed": 1}}}) is not None
    assert lashes.wanted({"base": {"body": {"source": "human"}, "head": {"seed": 1}, "lashes": False}}) is None
    assert lashes.wanted({"base": {"template": "male_stylized"}}) is None


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
