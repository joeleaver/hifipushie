"""Hard surface from the point cloud: the fitters recover known shapes from synthetic closed sculpts."""
import json
import math

import numpy as np
import pytest

from hifipushie.artretopo_mesh import Mesh
from hifipushie.hardsurf_solid import Solid
from hifipushie import hardsurf_fit as F
from hifipushie import hardsurf_frame as FR
from hifipushie import hardsurf_parts as P


def lathe_mesh(profile, origin=(0, 0, 0), axis=(0, 0, 1), seg=64):
    """a closed surface of revolution: profile [(t, r)] from the axis (r=0) round to the axis"""
    from hifipushie.hardsurf_solid import basis
    n, u, v = basis(axis); o = np.asarray(origin, float); V, F_ = [], []
    rows = []
    for t, r in profile:
        if r < 1e-9:
            V.append(o + n * t); rows.append([len(V) - 1])
        else:
            rows.append([len(V) + k for k in range(seg)])
            V += [o + n * t + r * (math.cos(2 * math.pi * k / seg) * u + math.sin(2 * math.pi * k / seg) * v) for k in range(seg)]
    for A, B in zip(rows[:-1], rows[1:]):
        if len(A) == 1:
            F_ += [[A[0], B[(k + 1) % seg], B[k]] for k in range(seg)]
        elif len(B) == 1:
            F_ += [[A[k], A[(k + 1) % seg], B[0]] for k in range(seg)]
        else:
            for k in range(seg):
                F_ += [[A[k], A[(k + 1) % seg], B[(k + 1) % seg]], [A[k], B[(k + 1) % seg], B[k]]]
    m = Mesh(np.array(V), np.array(F_), weld=False)
    if m.signed_volume() < 0: m = Mesh(m.V, m.F[:, ::-1], weld=False)
    return m


def merge(*ms):
    V, F_, off = [], [], 0
    for m in ms:
        V.append(m.V); F_.append(m.F + off); off += len(m.V)
    return Mesh(np.vstack(V), np.vstack(F_), weld=False)


STEP = [(0.0, 0), (0.0, 0.10), (0.20, 0.10), (0.20, 0.06), (0.35, 0.06), (0.35, 0)]      # a stepped post


def test_solid_volume_of_a_sphere():
    prof = [(math.cos(a) * 0.2, math.sin(a) * 0.2) for a in np.linspace(math.pi, 0, 40)]
    prof[0] = (-0.2, 0); prof[-1] = (0.2, 0)
    S = Solid(lathe_mesh(prof), step=0.004)
    vol = S.occ.sum() * S.step ** 3
    assert S.odd_columns == 0
    assert abs(vol - 4 / 3 * math.pi * 0.2 ** 3) / (4 / 3 * math.pi * 0.2 ** 3) < 0.03


def test_turned_recovers_a_stepped_profile_and_ignores_a_touching_bar():
    post = lathe_mesh(STEP)
    bar = lathe_mesh([(0, 0), (0, 0.015), (0.5, 0.015), (0.5, 0)], origin=(-0.25, 0.09, 0.28), axis=(1, 0, 0))   # touches at one side
    S = Solid(merge(post, bar), step=0.002)
    prof, V = F.turned_profile(S, (0, 0, 0), (0, 0, 1), -0.02, 0.37, 0.15, step=0.002, angles=48, tol=0.002)
    pr = np.array(prof)

    def r_at(t):      # the outermost radius of the profile polyline at t
        out = 0.0
        for (t0, r0), (t1, r1) in zip(pr[:-1], pr[1:]):
            if min(t0, t1) <= t <= max(t0, t1) and abs(t1 - t0) > 1e-9:
                out = max(out, r0 + (r1 - r0) * (t - t0) / (t1 - t0))
        return out
    assert all(abs(r_at(t) - 0.10) < 0.004 for t in (0.03, 0.1, 0.17))
    assert all(abs(r_at(t) - 0.06) < 0.004 for t in (0.23, 0.28, 0.32))
    assert abs(pr[:, 0].max() - 0.35) < 0.005
    d = F.turned(S, "post", (0, 0, 0), (0, 0, 1), -0.02, 0.37, 0.15, step=0.002, angles=48)
    assert "warning" not in d and P.validate(d)


def test_turned_traces_a_round_cup_and_warns_on_a_part_that_isnt_round():
    cup = lathe_mesh([(0, 0), (0, 0.10), (0.15, 0.10), (0.15, 0.094), (0.006, 0.094), (0.006, 0)])  # 6 mm wall
    d = F.turned(Solid(cup, step=0.003), "cup", (0, 0, 0), (0, 0, 1), -0.01, 0.16, 0.13, step=0.003, angles=36)
    assert "warning" not in d and any(abs(r - 0.094) < 0.004 for t, r in d["profile"])         # the inside wall traced
    cyl = lathe_mesh([(0, 0), (0, 0.15), (0.3, 0.15), (0.3, 0)])
    ell = Mesh(cyl.V * [1, 0.5, 1], cyl.F, weld=False)                                            # 2:1 ellipse
    d = F.turned(Solid(ell, step=0.003), "ell", (0, 0, 0), (0, 0, 1), -0.01, 0.31, 0.2, step=0.003, angles=36)
    assert "warning" in d


def test_trace_tube_follows_a_bar_and_measures_it():
    bar = lathe_mesh([(0, 0), (0, 0.02), (0.6, 0.02), (0.6, 0)], origin=(-0.3, 0, 0.1), axis=(1, 0, 0))
    S = Solid(bar, step=0.002)
    pts, r = F.trace_tube(S, (-0.2, 0.0, 0.1), (1, 0, 0), step=0.02)
    assert abs(r - 0.02) < 0.003 and len(pts) > 10
    assert np.abs(pts[:, 1:] - [0, 0.1]).max() < 0.003


def test_sweep_rounds_its_ends_and_blends_a_side_profile():
    prof = [(0, 0), (0.4, 0), (0.4, 0.1), (0, 0.1)]
    side = [(0, 0), (0.4, 0), (0.4, 0.16), (0, 0.16)]
    R_ = F.sweep_rings(prof, -0.2, 0.2, n=32, round_r=0.03, steps=3, mid=4, axis="x", side=side)
    assert len({len(r) for r in R_}) == 1 and len(R_) == 2 * 4 + 4
    hz = [max(p[2] for p in r) for r in R_]
    assert hz[0] < hz[len(R_) // 2] or hz[-1] < max(hz)            # ends inset
    assert max(hz) > 0.13 and min(hz[3:-3]) < 0.13                   # side profile near the ends, centre in the middle
    P.validate(F.sweep("slab", prof, -0.2, 0.2, axis="x"))


def test_inset_and_resample():
    sq = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], float) * 0.2
    q = F.inset(sq, 0.02)
    assert abs(q[:, 0].min() - 0.02) < 0.003 and abs(q[:, 0].max() - 0.18) < 0.003
    r = F.resample_closed(sq, 40, (-1, -1))
    assert len(r) == 40 and np.allclose(r[0], [0, 0], atol=1e-6)


def test_frame_squares_up_four_feet_and_scales_to_a_pair_gap():
    feet = []
    for x in (-0.3, 0.3):
        for y in (-0.5, 0.5):
            feet.append(lathe_mesh([(0, 0), (0, 0.05), (0.3, 0.05), (0.3, 0)], origin=(x, y, 0), axis=(0, 0, 1)))
    top = lathe_mesh([(0, 0), (0, 0.1), (0.9, 0.1), (0.9, 0)], origin=(0, -0.45, 0.32), axis=(0, 1, 0))
    m = merge(*feet, top)
    a = math.radians(30); Rz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    mi = Mesh(m.V @ Rz.T * 0.5 + [0.2, 0.1, 0.3], m.F, weld=False)               # turned, shrunk, moved; already z up
    out, info = FR.square_up(mi, up="z", contact_h=0.02, contacts=4, yaw="pairs", scale={"pair_gap": 1.0})
    c = np.array([d["centre"] for d in info["contacts"]])
    assert np.allclose(np.sort(np.abs(c[:, 0])), [0.3] * 4, atol=0.01)
    assert np.allclose(np.sort(np.abs(c[:, 1])), [0.5] * 4, atol=0.01)
    assert abs(out.V[:, 2].min()) < 1e-6 and abs(info["scale"] - 2.0) < 0.02


def test_parts_are_validated():
    with pytest.raises(ValueError):
        P.validate({"name": "x", "type": "lathe", "origin": [0, 0, 0], "axis": [0, 0, 1]})
    with pytest.raises(ValueError):
        P.validate({"name": "x", "type": "blob"})
    P.validate({"name": "lugs", "type": "radial", "origin": [0, 0, 0], "axis": [1, 0, 0], "count": 12, "r": 0.2, "size": [0.05, 0.03, 0.02]})


@pytest.mark.slow
def test_build_and_check_find_a_floating_part(tmp_path):
    from hifipushie import hardsurf_run as R
    d = tmp_path / "toy"; d.mkdir()
    m = lathe_mesh(STEP)
    from hifipushie.artretopo_mesh import write_ply
    write_ply(d / "high.ply", m.V, m.F)
    R.put_parts(str(d), [dict(type="lathe", name="post", origin=[0, 0, 0], axis=[0, 0, 1], profile=STEP),
                         dict(type="rbox", name="cap", c=[0, 0, 0.36], size=[0.1, 0.1, 0.02]),
                         dict(type="torus", name="loose", c=[0.5, 0, 0.2], axis=[0, 0, 1], R=0.05, r=0.01)])
    rep = R.build(str(d))
    assert rep["faces"]["post"] > 100 and rep["distance_to_sculpt"]["post"]["p95_mm"] < 3
    chk = R.check(str(d))
    assert chk["floating"] == [["loose"]]
