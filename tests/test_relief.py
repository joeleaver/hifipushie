"""A picture's surface in the clay: the slope-adding solver (surfaceread.height), a relief pressed into a solid
(relief.py) and a solid of two skins (twoskin.py), each on a shape whose answer is known. The reader itself (a
learned model in its own venv) is not run here."""
from __future__ import annotations

import numpy as np
import pytest
from scipy import ndimage

from hifipushie import relief, sdf, store, surfaceread, twoskin
from hifipushie.spec import compile_prims

PX = 0.002
R, ZC, N = 0.1, 0.3, 121


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(relief, "_CACHE", {})
    return tmp_path


def _grid():
    xs = (np.arange(N) - N // 2) * PX
    X, Zd = np.meshgrid(xs, xs)          # columns = x, rows run down: z = ZC - Zd
    return xs, X, Zd


def _frame(xs):
    return {"o": [xs[0], 0.0, ZC + (N // 2) * PX], "U": [1, 0, 0], "V": [0, 0, -1], "F": [0, -1, 0], "px": PX}


def _cos(t):
    gy, gx = np.gradient(t, PX)
    return np.clip(1 / np.sqrt(1 + gx ** 2 + gy ** 2), 0.25, 1)


def _signed(a):
    return (ndimage.distance_transform_edt(~a) - ndimage.distance_transform_edt(a)) * PX


def _front_hits(prims, X, Zd, pick):
    ii, jj = np.where(pick)
    ys = np.linspace(-0.16, 0.0, 641)
    P = np.stack([np.repeat(X[ii, jj], len(ys)), np.tile(ys, len(ii)), np.repeat(ZC - Zd[ii, jj], len(ys))], 1)
    f = sdf.field_at(prims, P).reshape(len(ii), len(ys))
    k = np.argmax(f < 0, axis=1)
    r = np.arange(len(ii))
    a, b = f[r, k - 1], f[r, k]
    return ii, jj, -(ys[k - 1] + (ys[k] - ys[k - 1]) * a / (a - b))


def test_the_slopes_add_up_to_the_dome_and_the_pins_find_its_true_depth():
    n = 81
    y, x = np.mgrid[0:n, 0:n]
    X, Y = (x - 40) * PX, (y - 40) * PX
    Rd = 0.07
    mask = X ** 2 + Y ** 2 < Rd ** 2 * 0.98
    true = np.sqrt(np.clip(Rd ** 2 - X ** 2 - Y ** 2, 0, None)) * 0.8
    gy, gx = np.gradient(true * 0.6, PX)             # a read that mutes depth to 60 %
    nrm = np.stack([-gx, gy, np.ones_like(gx)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    rim = mask & (ndimage.distance_transform_edt(mask) < 2)
    pin = np.full(mask.shape, np.nan)
    pin[rim] = true[rim]
    pin[38:43, 38:43] = true[38:43, 38:43]
    z, gain = surfaceread.height(nrm, mask, PX, pin=pin, gain=(0.5, 3.0))
    inner = mask & (ndimage.distance_transform_edt(mask) > 6)
    assert 1.45 < gain < 1.8                          # 1 / 0.6 = 1.67 undoes the muting
    assert np.abs((z - true)[inner]).max() < 0.0015
    # a part hidden by something standing in front is carried through smoothly
    hole = mask & (np.abs(X + 0.02) < 0.012) & (np.abs(Y) < 0.012)
    z2, _ = surfaceread.height(nrm, mask, PX, pin=pin, data=mask & ~hole, gain=(0.5, 3.0))
    assert np.abs((z2 - true)[hole]).max() < 0.004
    # without pins a piece floats: zero-mean, the slopes as read
    z3 = surfaceread.height(nrm, mask, PX)
    assert abs(float(z3[mask].mean())) < 1e-6
    assert np.ptp(z3[inner]) == pytest.approx(0.6 * np.ptp(true[inner]), rel=0.1)


def test_a_relief_adds_and_cuts_up_to_its_height_map_and_leaves_the_far_side(home):
    xs, X, Zd = _grid()
    r2 = X ** 2 + Zd ** 2
    B = np.sqrt(np.clip(R * R - r2, 0, None))
    bump = 0.02 * np.exp(-((X - 0.02) ** 2 + (Zd + 0.01) ** 2) / (2 * 0.012 ** 2)) \
        - 0.015 * np.exp(-((X + 0.03) ** 2 + (Zd - 0.02) ** 2) / (2 * 0.01 ** 2))
    top = B + bump                                    # one bump out, one dent in
    foot = np.sqrt(r2) < 0.07
    maps = {"top": top, "lo": np.zeros_like(top), "add": _signed(foot), "cut": _signed(foot),
            "k": np.ones_like(top), "cos": _cos(top)}
    sha = relief.put(_frame(xs), maps)
    ball = {"at": [0, 0, ZC], "size": [R, R, R]}
    spec = {"symmetry": False, "blend": 0.0, "joints": {}, "bones": {},
            "blobs": {"ball": ball, "ball_relief_front": {"shape": "relief", "relief": sha}}}
    prims = compile_prims(spec)
    assert [p.kind for p in prims] == ["ellipsoid", "relief"] and prims[1].op == "modify"
    ii, jj, t = _front_hits(prims, X, Zd, np.sqrt(r2) < 0.06)
    assert np.abs(t - top[ii, jj]).max() < 0.0015     # the surface IS the height map, bump and dent
    back = np.array([[0.0, 0.1, ZC], [0.03, 0.09, ZC + 0.02], [0.0, 0.05, ZC]])
    bare = compile_prims({**spec, "blobs": {"ball": ball}})
    assert np.allclose(sdf.field_at(prims, back), sdf.field_at(bare, back))
    # outside its footprint the clay is the ball's
    ii, jj, t = _front_hits(prims, X, Zd, (np.sqrt(r2) > 0.078) & (np.sqrt(r2) < 0.09))
    assert np.abs(t - B[ii, jj]).max() < 0.002
    # the grid a model is built on reaches a relief that stands proud of every solid
    lo, voxel, shape = sdf.frame(prims, resolution=64)
    assert lo[1] <= -(R + 0.02)


def test_a_reliefs_weight_decides_how_far_the_picture_is_taken(home):
    xs, X, Zd = _grid()
    r2 = X ** 2 + Zd ** 2
    B = np.sqrt(np.clip(R * R - r2, 0, None))
    top = B + 0.02
    foot = np.sqrt(r2) < 0.07
    half = {"top": top, "lo": np.zeros_like(top), "add": _signed(foot), "cut": _signed(foot),
            "k": np.full_like(top, 0.5), "cos": _cos(top)}
    sha = relief.put(_frame(xs), half)
    spec = {"symmetry": False, "blend": 0.0, "joints": {}, "bones": {},
            "blobs": {"ball": {"at": [0, 0, ZC], "size": [R, R, R]}, "r": {"shape": "relief", "relief": sha}}}
    ii, jj, t = _front_hits(compile_prims(spec), X, Zd, np.sqrt(r2) < 0.03)
    assert 0.006 < float(np.median(t - B[ii, jj])) < 0.014     # half way between the clay and the picture


def test_a_relief_on_one_side_is_mirrored_with_its_side(home):
    xs, X, Zd = _grid()
    top = np.sqrt(np.clip(R * R - X ** 2 - Zd ** 2, 0, None)) + 0.01
    foot = np.sqrt(X ** 2 + Zd ** 2) < 0.07
    frame = _frame(xs)
    frame["o"] = [xs[0] + 0.2, 0.0, ZC + (N // 2) * PX]
    sha = relief.put(frame, {"top": top, "lo": np.zeros_like(top), "add": _signed(foot), "cut": _signed(foot),
                             "k": np.ones_like(top), "cos": _cos(top)})
    spec = {"symmetry": True, "blend": 0.0, "joints": {}, "bones": {},
            "blobs": {"ball.L": {"at": [0.2, 0, ZC], "size": [R, R, R]}, "r.L": {"shape": "relief", "relief": sha}}}
    prims = {p.name: p for p in compile_prims(spec)}
    assert prims["r.R"].params["U"][0] == -1 and prims["r.L"].params["U"][0] == 1
    at = np.array([[0.2, -R - 0.005, ZC], [-0.2, -R - 0.005, ZC]])
    f = sdf.field_at(list(prims.values()), at)
    assert f[0] < 0 and f[1] < 0                      # both balls stand 1 cm prouder there


def test_two_skins_make_the_solid_between_them(home):
    xs, X, Zd = _grid()
    r2 = X ** 2 + Zd ** 2
    hgt = np.sqrt(np.clip(R * R - r2, 1e-8, None))
    inside = r2 < R * R
    sha = twoskin.put(_frame(xs), {"front": hgt, "back": hgt * 0.5, "foot": _signed(inside), "cf": _cos(hgt),
                                   "cb": _cos(hgt * 0.5)})
    spec = {"symmetry": False, "blend": 0.0, "joints": {}, "bones": {}, "blobs": {"egg": {"shape": "twoskin", "skins": sha}}}
    prims = compile_prims(spec)
    assert prims[0].kind == "twoskin" and prims[0].op == "add"
    verts = sdf.mesh(sdf.evaluate(prims, resolution=96))[0]
    assert verts[:, 1].min() == pytest.approx(-R, abs=0.003)          # the front skin's top
    assert verts[:, 1].max() == pytest.approx(0.5 * R, abs=0.003)     # the back skin's, half as deep
    assert np.ptp(verts[:, 0]) == pytest.approx(2 * R, abs=0.008)     # the outline's width
    with pytest.raises(Exception, match="twoskin"):
        compile_prims({**spec, "blobs": {"egg": {"shape": "twoskin"}}})
