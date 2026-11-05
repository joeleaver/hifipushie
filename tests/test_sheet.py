"""The "sheet" element: one seamless thick sheet along a spine (a floppy ear folded through ~100 degrees)."""

import numpy as np
import pytest

from hifipushie import fit as fitmod
from hifipushie import sdf
from hifipushie.sheet import _spine_eval
from hifipushie.spec import SpecError, compile_prims, expand_mirror

# a cartoon pig's ear: root on the head, up over a fold, the outer half forward and down (the case that exposed the gap)
EAR = {"shape": "sheet", "curve": "bezier",
       "spine": [[0.105, -0.005, 0.745], [0.115, -0.01, 0.80], [0.16, -0.06, 0.835], [0.178, -0.095, 0.725]],
       "stations": [{"half_width": 0.06, "half_thickness": 0.012},
                    {"half_width": 0.045, "half_thickness": 0.011},
                    {"half_width": 0.02, "half_thickness": 0.008}]}


def spec_of(**blobs):
    return {"symmetry": True, "blend": 0.01, "joints": {}, "bones": {}, "blobs": blobs}


def one(bl):
    return compile_prims(spec_of(x=bl))[0]


def sd(p, pts):
    return sdf.SDF[p.kind](np.asarray(pts, float), p.params)


def frame(p, u):
    pr = p.params
    P, D, _ = _spine_eval(pr["sp"], np.asarray(u, float))
    T = D / np.linalg.norm(D, axis=1)[:, None]
    W = pr["W"][np.round(np.asarray(u) * (len(pr["W"]) - 1)).astype(int)]
    return P, T, W, pr["hand"] * np.cross(T, W)


def test_exact_across_the_thickness_all_round_the_fold():
    p = one(EAR)
    u = np.linspace(0.35, 0.85, 9)  # past the root's rounding, before the tip's
    P, T, W, N = frame(p, u)
    s = np.interp(u, np.linspace(0, 1, len(p.params["S"])), p.params["S"])
    ht = np.interp(s, p.params["ts"], p.params["V"][:, 1])
    for off in (-0.03, -0.006, 0.0, 0.004, 0.02, 0.05):
        d = sd(p, P + off * N)
        want = np.maximum(np.abs(off) - ht, -ht)
        assert np.abs(d - want).max() < 1.5e-3, off  # station thickness is a spline: ht interpolated linearly here


def test_one_smooth_field_no_knuckles():
    """Along the outer surface over the whole fold the field stays at zero and its gradient turns smoothly: a chain
    of blades has a bump (and a jump in the normal) at every joint."""
    p = one(EAR)
    u = np.linspace(0.3, 0.9, 400)
    P, T, W, N = frame(p, u)
    s = np.interp(u, np.linspace(0, 1, len(p.params["S"])), p.params["S"])
    ht = np.interp(s, p.params["ts"], p.params["V"][:, 1])
    surf = P + (ht + 1e-4)[:, None] * N
    h = 1e-4
    g = np.stack([(sd(p, surf + h * e) - sd(p, surf - h * e)) / (2 * h) for e in np.eye(3)], 1)
    g /= np.linalg.norm(g, axis=1)[:, None]
    turn = np.degrees(np.arccos(np.clip((g[1:] * g[:-1]).sum(1), -1, 1)))
    assert turn.max() < 1.5  # 400 steps over a ~100 degree fold: smooth, no step anywhere
    assert np.abs(sd(p, surf)).max() < 1.5e-3


def test_distance_estimate_is_well_scaled():
    p = one(EAR)
    R = np.random.default_rng(0).uniform(p.lo, p.hi, (20000, 3))
    d = sd(p, R)
    h = 1e-4
    g = np.stack([(sd(p, R + h * e) - sd(p, R - h * e)) / (2 * h) for e in np.eye(3)], 1)
    gn = np.linalg.norm(g, axis=1)[np.abs(d) < 0.02]
    assert 0.85 < np.percentile(gn, 1) and np.percentile(gn, 99) < 1.25
    assert (d < 0).mean() > 0.005  # it has volume inside its box


def test_width_axis_does_not_twist_on_a_planar_fold():
    """A fold in one plane keeps its width axis exactly the plane's normal from root to tip (default axis)."""
    p = one({**EAR, "spine": [[0.1, 0, 0.745], [0.1, -0.005, 0.80], [0.1, -0.055, 0.835], [0.1, -0.09, 0.725]]})
    W = p.params["W"]
    assert np.abs(W @ W[0]).min() > 1 - 1e-9 and abs(W[0][0]) > 1 - 1e-9
    P = p.params["P"]
    assert np.abs((P - P[0]) @ W[0]).max() < 1e-9  # ...and it is the spine plane's normal


def test_width_axis_follows_a_space_curve_without_spin():
    """Rotation-minimising: the width axis turns only as the tangent does (no rotation about the tangent)."""
    helix = [[0.05 * np.cos(a), 0.05 * np.sin(a), 0.03 * a] for a in np.linspace(0, 3, 7)]
    p = one({"shape": "sheet", "spine": helix, "width_axis": [0, 0, 1],
             "stations": [{"half_width": 0.02, "half_thickness": 0.004}]})
    T, W = p.params["T"], p.params["W"]
    dW = np.diff(W, axis=0)
    Tm = (T[1:] + T[:-1]) / 2
    Nm = np.cross(Tm, (W[1:] + W[:-1]) / 2)
    assert np.abs((dW * Nm).sum(1)).max() < 2e-4  # no component about the tangent, step by step
    assert np.abs((W * T).sum(1)).max() < 1e-9


def test_taper_twist_and_cup():
    p = one(EAR)
    P, T, W, N = frame(p, [0.5])
    hw = 0.045
    assert sd(p, P + 0.9 * (hw - 0.011) * W)[0] < 0 < sd(p, P + 1.1 * hw * W)[0]
    tw = one({**EAR, "stations": [dict(s, twist=40) for s in EAR["stations"]]})
    P2, T2, W2, N2 = frame(tw, [0.5])
    c, s = np.cos(np.radians(40)), np.sin(np.radians(40))
    Wt = c * W2 + s * N2
    assert sd(tw, P2 + 0.03 * Wt)[0] < 0 < sd(tw, P2 + 0.03 * W2)[0]
    cup = one({**EAR, "stations": [dict(s, cup=0.01) for s in EAR["stations"]]})
    P3, T3, W3, N3 = frame(cup, [0.5])
    edge = P3 + 0.03 * W3
    assert sd(cup, edge + 0.0045 * N3)[0] < 0 < sd(cup, edge - 0.008 * N3)[0]  # the edges lift toward +normal


def test_mirror_keeps_the_normal_on_the_same_side():
    s = expand_mirror(spec_of(**{"ear.L": {**EAR, "stations": [dict(x, cup=0.01) for x in EAR["stations"]]}}))
    L, R = s["blobs"]["ear.L"], s["blobs"]["ear.R"]
    assert R["spine"][0] == [-L["spine"][0][0], *L["spine"][0][1:]]
    pl, pr = compile_prims(spec_of(**{"ear.L": {**EAR, "stations": [dict(x, cup=0.01) for x in EAR["stations"]]}}))
    pts = np.random.default_rng(1).uniform(pl.lo, pl.hi, (3000, 3))
    mirrored = pts * [-1, 1, 1]
    assert np.abs(sd(pl, pts) - sd(pr, mirrored)).max() < 1e-9


def test_spline_spine_and_bezier_agree_on_a_straight_line():
    st = [{"half_width": 0.03, "half_thickness": 0.005}]
    a = one({"shape": "sheet", "spine": [[0, 0, 0], [0, 0, 0.1]], "width_axis": [1, 0, 0], "stations": st})
    b = one({"shape": "sheet", "curve": "bezier", "spine": [[0, 0, 0], [0, 0, 0.033], [0, 0, 0.066], [0, 0, 0.1]],
             "width_axis": [1, 0, 0], "stations": st})
    pts = np.random.default_rng(2).uniform(-0.05, 0.15, (2000, 3))
    assert np.abs(sd(a, pts) - sd(b, pts)).max() < 1e-3
    assert sd(a, [[0, 0, 0.05]])[0] == pytest.approx(-0.005, abs=1e-6)
    assert sd(a, [[0, 0.02, 0.05]])[0] == pytest.approx(0.015, abs=1e-6)


@pytest.mark.parametrize("bad", [
    {"spine": [[0, 0, 0]]},
    {"curve": "bezier", "spine": [[0, 0, 0], [0, 0, 0.1], [0, 0, 0.2]]},
    {"curve": "polyline"},
    {"stations": []},
    {"stations": [{"half_width": 0.01, "half_thickness": 0.02}]},
    {"stations": [{"half_width": 0.03, "half_thickness": 0.01, "wiggle": 1}]},
    {"spine": [[0, 0, 0], [0, 0, 0.1]]},  # straight, no width_axis
    {"tip": 0.2},  # rounding longer than the sheet
    # a fold tighter than the sheet is thick: the inside would fold through itself
    {"curve": "bezier", "spine": [[0, 0, 0], [0, 0, 0.03], [0.02, 0, 0.03], [0.02, 0, 0]]},
])
def test_refusals(bad):
    with pytest.raises(SpecError):
        compile_prims(spec_of(x={**EAR, **bad}))


def test_fit_moves_spine_points_and_widths():
    spec = spec_of(**{"ear.L": EAR})
    ps = fitmod.parameters(spec, groups=("pos", "size"))
    spine = [p for p in ps if p[2] == "spine"]
    widths = [p for p in ps if p[2] == "stations"]
    assert len(spine) == 12 and len(widths) == 6
    assert all(fitmod._is_size(p) for p in widths) and not any(fitmod._is_size(p) for p in spine)
    s2 = {**spec, "blobs": {"ear.L": dict(EAR)}}
    fitmod._set(s2, ("blobs", "ear.L", "spine", (2, 2)), 0.85)
    fitmod._set(s2, ("blobs", "ear.L", "stations", (1, "half_width")), 0.05)
    assert fitmod._get(s2, ("blobs", "ear.L", "spine", (2, 2))) == 0.85
    assert fitmod._get(s2, ("blobs", "ear.L", "stations", (1, "half_width"))) == 0.05
    assert EAR["spine"][2][2] == 0.835 and EAR["stations"][1]["half_width"] == 0.045  # copies, not in place
    compile_prims(s2)


def test_puff_makes_a_lens_thickest_mid_width():
    """puff 1: an elliptic cross-section (pillowy clay, a leaf); 0: a slab with round edges; a blend between."""
    lens = one({**EAR, "stations": [dict(s, puff=1) for s in EAR["stations"]]})
    slab = one(EAR)
    P, T, W, N = frame(lens, [0.5])
    hw, ht = 0.045, 0.011
    # same thickness at mid-width, thinner toward the edge: (1 - 0.7^2)^0.5 = 0.71 of it at 70 % out
    assert sd(lens, P + 0.010 * N)[0] < 0 and sd(slab, P + 0.010 * N)[0] < 0
    at = P + 0.7 * hw * W
    assert sd(slab, at + 0.010 * N)[0] < 0 < sd(lens, at + 0.010 * N)[0]
    assert sd(lens, at + 0.0072 * N)[0] < 0
    half = one({**EAR, "stations": [dict(s, puff=0.5) for s in EAR["stations"]]})
    pts = np.random.default_rng(3).uniform(lens.lo, lens.hi, (4000, 3))
    assert np.allclose(sd(half, pts), 0.5 * sd(lens, pts) + 0.5 * sd(slab, pts))
    with pytest.raises(SpecError):
        one({**EAR, "stations": [dict(s, puff=2) for s in EAR["stations"]]})
