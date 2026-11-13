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


def test_a_side_outline_and_a_side_skin_bound_the_two_skins(home):
    xs, X, Zd = _grid()
    flat = np.full_like(X, 0.08)                                   # a block 16 cm deep between two flat skins
    square = (np.abs(X) < 0.1) & (np.abs(Zd) < 0.1)
    side_disc = np.sqrt(X ** 2 + Zd ** 2) < 0.06                    # the side picture shows a disc (y across, z up)
    side = {"foot": _signed(side_disc), "o": [0.0, xs[0], ZC + (N // 2) * PX], "U": [0, 1, 0], "V": [0, 0, -1],
            "px": PX, "top": np.full_like(X, 0.05), "cos": np.ones_like(X), "F": [1, 0, 0]}
    sha = twoskin.put(_frame(xs), {"front": flat, "back": flat, "foot": _signed(square), "cf": np.ones_like(X),
                                   "cb": np.ones_like(X)}, side)
    assert len(relief.get(sha)["rule"]) == 12                     # the measures it was made with travel with it
    prims = compile_prims({"symmetry": False, "blend": 0.0, "joints": {}, "bones": {},
                           "blobs": {"b": {"shape": "twoskin", "skins": sha}}})
    f = lambda *p: float(sdf.field_at(prims, np.array([p]))[0])
    assert f(0.0, 0.0, ZC) < 0
    assert f(0.045, 0.0, ZC) < 0 < f(0.056, 0.0, ZC)               # the side skin, from this side
    assert f(-0.045, 0.0, ZC) < 0 < f(-0.056, 0.0, ZC)             # and from the other
    assert f(0.0, 0.0, ZC + 0.05) < 0 < f(0.0, 0.0, ZC + 0.066)    # the side outline's disc, not the square's 10 cm
    assert f(0.0, -0.055, ZC) < 0 < f(0.0, -0.066, ZC)             # and in front, before the skin at 8 cm


def _ball_mesh(ripple=0.0):
    from hifipushie import surfacefuse
    spec = {"symmetry": False, "blend": 0.0, "joints": {}, "bones": {}, "blobs": {"ball": {"at": [0, 0, ZC], "size": [R, R, R]}}}
    V, F = sdf.mesh(sdf.evaluate(compile_prims(spec), resolution=80), smooth=2)
    V = V.astype(np.float64)
    n = surfacefuse.vertex_normals(V, F)
    return V + n * (ripple * np.sin(V[:, 2:3] * 2 * np.pi / 0.02)), F


def _ball_view(U, F, mirror=False):
    half, px = 0.13, 0.001
    g = np.arange(-half, half, px) + px / 2
    A, B = np.meshgrid(g, g)                                        # across the picture, and down it
    nx, ny = A / R, -B / R
    ok = nx ** 2 + ny ** 2 < 0.97
    nz = np.sqrt(np.clip(1 - nx ** 2 - ny ** 2, 0, None))
    return {"normals": np.stack([nx, ny, nz], -1).astype(np.float32), "mask": ok, "U": U, "F": F, "u0": -half,
            "z0": ZC + half, "px": px, "za": 1.0, "mirror": mirror}


def test_every_view_shapes_one_surface_and_the_big_shape_stays():
    from hifipushie import surfacefuse
    V, F = _ball_mesh(ripple=0.002)                                 # 2 mm ripples, 2 cm apart: wrong in the small
    views = [_ball_view([1, 0, 0], [0, -1, 0]), _ball_view([-1, 0, 0], [0, 1, 0]), _ball_view([0, 1, 0], [1, 0, 0]),
             _ball_view([0, 1, 0], [1, 0, 0], mirror=True)]
    rad = lambda P: np.linalg.norm(P - np.array([0, 0, ZC]), axis=1)
    side = np.abs(V[:, 2] - ZC) < 0.06                              # the band every side view sees (not top and bottom)
    V2 = surfacefuse.refine(V, F, views, scale=0.01, iters=3)
    assert rad(V2)[side].std() < 0.45 * rad(V)[side].std()          # the ripples go: the views say "a ball"
    assert abs(rad(V2)[side].mean() - R) < 0.0015                   # the ball stays the ball it was
    eased = surfacefuse.eased(rad(V) - R, F, rounds=4)
    assert np.abs(eased).max() < np.abs(rad(V) - R).max()


def test_a_nudge_moves_the_surface_it_was_taken_from_and_no_other(home):
    from hifipushie import meshclay
    k = np.arange(20000) + 0.5
    phi, th = np.arccos(1 - 2 * k / 20000), np.pi * (1 + 5 ** 0.5) * k
    pts = np.array([0, 0, ZC]) + R * np.stack([np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)], 1)
    sha = meshclay.put(pts, np.full(len(pts), 0.004))               # the ball's surface, moved out 4 mm
    spec = {"symmetry": False, "blend": 0.0, "joints": {}, "bones": {},
            "blobs": {"ball": {"at": [0, 0, ZC], "size": [R, R, R]}, "near": {"at": [0.215, 0, ZC], "size": [R, R, R]},
                      "moved": {"shape": "nudge", "nudge": sha, "layer": 60}}}
    prims = compile_prims(spec)
    assert [p.kind for p in prims][-1] == "nudge"
    f = lambda *p: float(sdf.field_at(prims, np.array([p]))[0])
    assert f(0, -(R + 0.003), ZC) < 0 < f(0, -(R + 0.005), ZC)      # the ball is 4 mm bigger
    assert f(0.215, -(R - 0.001), ZC) < 0 < f(0.215, -(R + 0.001), ZC)   # its neighbour, 1.5 cm away, is not
    with pytest.raises(ValueError):
        meshclay.put(pts, np.zeros(3))
