"""lidfold: the fold's profile and modifier on a flat skin, its config, and the photo reader on a synthetic lid."""
import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

from hifipushie import lidfold, sdf

MM = 0.001


def _params(n=101, G=1.0, w=0.8, O=0.6, so=1.6, Pl=0.15, h=4.0):
    x = np.linspace(-0.015, 0.015, n)
    P = np.c_[x, np.zeros(n), np.zeros(n)]
    sp = float(x[1] - x[0])
    sa = 1.5 * sp
    s = np.linspace(0, 1, n)
    e = np.clip(np.minimum(s, 1 - s) / 0.12, 0, 1)
    return {"pts": P, "nrm": np.tile([0, 0, 1.0], (n, 1)), "up": np.tile([0, 1.0, 0], (n, 1)),
            "along": np.tile([1.0, 0, 0], (n, 1)), "taper": e * e * (3 - 2 * e), "sa": sa,
            "wfull": float(np.sqrt(2 * np.pi) * sa / sp) * 0.98, "reach": 3 * MM, "G": np.full(n, G * MM),
            "sg": np.full(n, w * MM / 2.355), "O": np.full(n, O * MM), "so": np.full(n, so * MM),
            "Pl": np.full(n, Pl * MM), "ph": np.full(n, (h - 0.8) * MM), "radius": 0.02, "k": 30,
            "tree": cKDTree(P)}


def _surface(pr, t):
    """The modified plane's height (m) over (0, t): the zero of z - disp along z."""
    zs = np.linspace(-0.003, 0.003, 6001)
    P = np.c_[np.zeros(len(zs)), np.full(len(zs), t), zs]
    f = sdf.mod_fold(zs.copy(), P, pr)
    return float(zs[np.argmin(np.abs(f))])


def test_fold_profile_on_a_plane():
    pr = _params()
    groove = _surface(pr, 0.0)
    assert -1.05 * MM < groove < -0.9 * MM, groove  # the crease: ~crease_depth in
    roll = max(_surface(pr, t * MM) for t in (1.0, 1.4, 1.8))
    assert 0.45 * MM < roll < 0.65 * MM, roll  # the fold's roll out over it
    assert _surface(pr, -2.0 * MM) < 0  # the platform a little in
    assert abs(_surface(pr, -6.0 * MM)) < 1e-5 and abs(_surface(pr, 9.0 * MM)) < 0.05 * MM
    # narrow: half the depth within ~half the width either side
    half = _surface(pr, 0.4 * MM)
    assert half > 0.6 * groove  # (shallower at 0.4 mm than at the line)
    # smooth along the line (no ripple between samples) and faded at the ends
    along = [sdf.mod_fold(np.array([0.0]), np.array([[x, 0.0, 0.0]]), pr)[0] for x in np.linspace(-0.005, 0.005, 41)]
    assert np.ptp(along) < 0.01 * MM
    end = sdf.mod_fold(np.array([0.0]), np.array([[0.0149, 0.0, 0.0]]), pr)[0]
    assert abs(end) < 0.1 * MM


def test_line_distance():
    pr = _params()
    d = lidfold.line_distance(np.array([[0, 0.0005, 0.0], [0, 0.003, 0.0], [0.0, 0.0, -0.001]]), pr)
    assert abs(d[0] - 0.0005) < 1e-4 and abs(d[1] - 0.003) < 2e-4 and d[2] < 1e-4


def test_config():
    assert lidfold.config({"base": {"head": {}}}) is None
    c = lidfold.config({"base": {"body": {"sex": 0.0}, "head": {"fold": True}}})
    assert c["crease_height"] == 4.0 and c["crease_depth"] == lidfold.DEFAULTS["crease_depth"]
    assert lidfold.config({"base": {"body": {"sex": 1.0}, "head": {"fold": {"crease_depth": 0.5}}}})["crease_height"] == 3.0
    try:
        lidfold.config({"base": {"head": {"fold": {"bogus": 1}}}})
        raise AssertionError("unknown key accepted")
    except ValueError:
        pass


def test_read_lid_synthetic():
    """A bright face, the lid line at y 200, a soft dark crease 8 px over it, the iris 20 px across (11.7 mm)."""
    W = 400
    im = Image.new("L", (W, W), 205)
    d = ImageDraw.Draw(im)
    for k in range(-2, 3):  # the crease: a dark band ~3 px wide
        d.line([(60, 192 + k), (340, 192 + k)], fill=int(120 + 25 * abs(k)))
    d.line([(60, 200), (340, 200)], fill=40)  # the lash line
    P = np.zeros((478, 2))
    P[168], P[152] = (200, 100), (200, 380)
    for s, (xi, xo) in enumerate(((180, 100), (220, 300))):
        for i, x in zip(lidfold.UPPER[s], np.linspace(xo, xi, len(lidfold.UPPER[s]))):
            P[i] = (x, 200)
        for i, x in zip(lidfold.BROW_LOW[s], np.linspace(xo, xi, len(lidfold.BROW_LOW[s]))):
            P[i] = (x, 170)
        P[lidfold.INNER[s]], P[lidfold.OUTER[s]] = (xi, 200), (xo, 200)
        c = np.array([(xi + xo) / 2, 205.0])
        P[lidfold.IRIS_C[s]] = c
        for i, a in zip(lidfold.IRIS_RIM[s], (0, np.pi / 2, np.pi, 3 * np.pi / 2)):
            P[i] = c + 10 * np.array([np.cos(a), np.sin(a)])
    r = lidfold.read_lid(im.convert("RGB"), P)
    mmpx = 11.7 / 20
    for cols in r:
        for c in cols:
            assert abs(c["tps"] - 8 * mmpx) < 0.6, c
            assert c["dark"] > 0.2 and abs(c["bfs"] - 22 * mmpx) < 0.7, c


def test_paint_may_be_near_a_fold():
    """paint.check_refs accepts `near` on a fold prim (its crease line), as store.save runs it (tess, main 37b0014)."""
    from hifipushie import paint
    from hifipushie.spec import Prim
    pr = _params()
    fold = Prim("lid_fold.L", "fold", "modify", 0.0, 0, pr["pts"].min(0) - 0.01, pr["pts"].max(0) + 0.01, pr)
    ball = Prim("eye.L", "ellipsoid", "add", 0.0, 0, np.full(3, -0.01), np.full(3, 0.01),
                {"c": np.zeros(3), "size": np.full(3, 0.01), "rot": np.eye(3)})
    spec = {"joints": {}, "blobs": {"eye.L": {"at": [0, 0, 0], "size": [0.01] * 3}}, "parts": {"body": {}},
            "paint": {"crease": {"part": "body", "color": [0.5, 0.5, 0.5], "near": ["lid_fold.L"], "within": 0.0003}}}
    paint.check_refs(spec, [ball, fold])


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
