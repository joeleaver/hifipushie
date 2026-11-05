"""The soft primary forms: "super" (superellipsoid) and "loft" (one seamless mass through cross-sections)."""

import copy

import numpy as np
import pytest

from hifipushie import fit as fitmod
from hifipushie import sdf
from hifipushie.spec import SpecError, compile_prims

# a cartoon pig's head and body as one pear (z, half width, y front, y back): the case that exposed the gap
PIG = [(0.16, .175, -.15, .14), (0.24, .195, -.19, .17), (0.32, .20, -.18, .18), (0.40, .18, -.16, .16),
       (0.45, .19, -.17, .15), (0.56, .205, -.18, .17), (0.68, .19, -.16, .135)]


def pear(**kw):
    secs = [{"z": z, "half_width": w, "half_depth": (b - a) / 2, "offset_y": (a + b) / 2} for z, w, a, b in PIG]
    return {"shape": "loft", "sections": secs, "top": {"z": 0.77}, "bottom": {"z": 0.08}, **kw}


def spec_of(**blobs):
    return {"symmetry": True, "blend": 0.03, "joints": {}, "bones": {}, "blobs": blobs}


def one(bl):
    return compile_prims(spec_of(x=bl))[0]


def sd(p, pts):
    return sdf.SDF[p.kind](np.asarray(pts, float), p.params)


def test_super_at_two_is_the_ellipsoid():
    P = np.random.default_rng(0).uniform(-0.4, 0.4, (3000, 3))
    e = one({"size": [0.2, 0.1, 0.15], "rot": [10, 20, 30]})
    s = one({"size": [0.2, 0.1, 0.15], "rot": [10, 20, 30], "shape": "super", "squareness": 2})
    de, ds = sd(e, P), sd(s, P)
    near = de > -0.05  # deep inside, super is clamped to its true depth
    assert np.abs(de[near] - ds[near]).max() < 1e-9


def test_super_fills_toward_a_box():
    """Higher squareness reaches further into the corners, axis extents unchanged."""
    corner = np.array([[0.2, 0.15, 0.1]]) * 0.75
    vals = [float(sd(one({"size": [0.2, 0.15, 0.1], "shape": "super", "squareness": n}), corner)[0])
            for n in (2, 3, 5, 10)]
    assert vals[0] > 0 > vals[-1] and vals == sorted(vals, reverse=True)
    for n in (2, 4, 10):
        p = one({"size": [0.2, 0.15, 0.1], "shape": "super", "squareness": n})
        assert np.abs(sd(p, [[0.2, 0, 0], [0, 0.15, 0], [0, 0, 0.1]])).max() < 1e-9
        assert sd(p, [[0.25, 0, 0]])[0] == pytest.approx(0.05, rel=0.02)


def test_super_exponents_per_axis_and_refusals():
    p = one({"size": [0.2, 0.2, 0.2], "shape": "super", "exponents": [6, 6, 2]})
    # square seen from above (x, y), round seen from the side (x, z)
    assert sd(p, [[0.17, 0.17, 0]])[0] < 0 < sd(p, [[0.17, 0, 0.17]])[0]
    for bad in ({"squareness": 40}, {"exponents": [2, 3]}, {"size": [0.1, 0, 0.1]}):
        with pytest.raises(SpecError):
            one({"size": [0.1, 0.1, 0.1], "shape": "super", **bad})


def test_loft_passes_through_its_sections_and_caps():
    p = one(pear())
    for z, w, a, b in PIG:
        pts = [[w, (a + b) / 2, z], [-w, (a + b) / 2, z], [0, a, z], [0, b, z]]
        assert np.abs(sd(p, pts)).max() < 2e-3, z
    assert abs(sd(p, [[0, -0.0125, 0.77]])[0]) < 2e-3 and abs(sd(p, [[0, -0.005, 0.08]])[0]) < 2e-3
    assert 0.07 < p.lo[2] <= 0.08 and 0.77 <= p.hi[2] < 0.78  # the box, padded 2 %


def _radius(p, zs, y=0.0):
    """Half width of the surface at heights zs (bisection along +X)."""
    lo, hi = np.zeros(len(zs)), np.full(len(zs), 0.5)
    for _ in range(50):
        mid = (lo + hi) / 2
        inside = sd(p, np.stack([mid, np.full_like(mid, y), zs], 1)) < 0
        lo, hi = np.where(inside, mid, lo), np.where(inside, hi, mid)
    return lo


def _curvature_jumps(p, zs, y=0.0):
    h = zs[1] - zs[0]
    curv = np.diff(_radius(p, zs, y), 2) / h ** 2
    return np.abs(np.diff(curv))


def test_loft_has_no_crease_where_sections_or_caps_change():
    """A groove or band is a jump in the profile's curvature: the half width's curvature up the body, on a 2 mm
    step, must change smoothly across every section and where each cap starts (it only climbs near the tips,
    as any dome's does). A rounded box, measured the same way, jumps where its flat side meets its edge."""
    zs = np.arange(0.12, 0.72, 0.002)
    assert _curvature_jumps(one(pear()), zs, y=-0.005).max() < 5.0
    box = one({"at": [0, 0, 0.4], "shape": "box", "size": [0.2, 0.17, 0.3], "round": 0.12})
    assert _curvature_jumps(box, zs).max() > 1000.0
    sup = one({"at": [0, 0, 0.42], "shape": "super", "size": [0.2, 0.17, 0.4], "squareness": 4})
    assert _curvature_jumps(sup, zs).max() < 5.0


def test_loft_distance_is_close_to_true():
    p = one(pear())
    g = sdf.evaluate([p], resolution=140)
    v = sdf.mesh(g, smooth=0)[0]
    from scipy.spatial import cKDTree
    rng = np.random.default_rng(1)
    Q = rng.uniform(p.lo - 0.08, p.hi + 0.08, (8000, 3))
    d = sd(p, Q)
    t = cKDTree(v).query(Q)[0]
    near = (np.abs(d) < 0.05) & (t > 0.006)
    ratio = np.abs(d[near]) / t[near]
    assert 0.7 < ratio.min() and ratio.max() < 1.3
    far = d > 0.05
    assert (d[far] / t[far]).max() < 1.1  # never overstates: clipping and fillets rely on it


def test_loft_clipping_matches_unclipped_with_a_blend():
    s = spec_of(body=pear(blend=0.06), snout={"at": [0, -0.2, 0.6], "size": [0.06, 0.05, 0.04], "blend": 0.03},
                ear={"at": [0.15, 0, 0.78], "shape": "super", "size": [0.06, 0.02, 0.05], "squareness": 3})
    prims = compile_prims(s)
    P = np.random.default_rng(2).uniform([-0.3, -0.35, 0], [0.3, 0.3, 0.9], (20000, 3))
    a, b = sdf.field_at(prims, P, clip=True), sdf.field_at(prims, P, clip=False)
    band = np.abs(b) < 0.015  # clipping keeps real values near the surface, the sign everywhere
    assert np.abs(a[band] - b[band]).max() < 1e-6
    assert (np.sign(a) == np.sign(b)).all()


def test_loft_refusals():
    for bad in ({"sections": [{"z": 0, "half_width": 0.1, "half_depth": 0.1}]},
                {"sections": [{"z": 0.2, "half_width": 0.1, "half_depth": 0.1},
                              {"z": 0.1, "half_width": 0.1, "half_depth": 0.1}]},
                {"sections": [{"z": 0, "half_width": 0.1, "half_depth": 0.1},
                              {"z": 0.1, "half_width": 0.1, "half_depth": 0.1, "widht": 1}]},
                {**pear(), "top": {"z": 0.6}}):
        with pytest.raises(SpecError):
            one({"shape": "loft", **bad})


def _world_ref(spec, view, res=160):
    g = sdf.evaluate(compile_prims(spec), res)
    sil = sdf.silhouettes(g)[view]
    return sil["mask"], (sil["u"][0] - g.voxel / 2, sil["v"][1] + g.voxel / 2, g.voxel)


def test_fit_moves_loft_sections_and_squareness():
    target = spec_of(body=pear())
    start = copy.deepcopy(target)
    for s in start["blobs"]["body"]["sections"]:
        s["half_width"] *= 0.85
    start["blobs"]["body"]["sections"][2]["squareness"] = 2.0
    params = fitmod.parameters(start)
    assert ("blobs", "body", "sections", (2, "half_width")) in params
    assert ("blobs", "body", "sections", (2, "squareness")) in params
    assert ("blobs", "body", "top", "z") in params
    refs = {v: _world_ref(target, v) for v in ("front", "side")}
    res = fitmod.fit(start, refs, iterations=8, resolution=110)
    assert res.iou_after["front"] > res.iou_before["front"] + 0.02
    assert res.iou_after["front"] > 0.97
    assert any("sections[" in c for c in res.changes)


def test_fit_moves_super_squareness():
    target = spec_of(b={"at": [0, 0, 0.2], "shape": "super", "size": [0.2, 0.15, 0.18], "squareness": 5})
    start = copy.deepcopy(target)
    start["blobs"]["b"]["squareness"] = 2.5
    assert ("blobs", "b", "squareness", None) in fitmod.parameters(start)
    refs = {v: _world_ref(target, v) for v in ("front", "side")}
    res = fitmod.fit(start, refs, groups=("shape",), iterations=10, resolution=110, max_step=0.5)
    assert res.spec["blobs"]["b"]["squareness"] > 3.5


def test_loft_sections_from_outlines():
    target = spec_of(body=pear())
    start = copy.deepcopy(target)
    for s in start["blobs"]["body"]["sections"]:
        s.update(half_width=0.18, half_depth=0.16, offset_y=0.0)
    refs = {v: _world_ref(target, v, 200) for v in ("front", "side")}
    out, lines = fitmod.loft_from_refs(start, refs, "body", resolution=110)
    assert len(lines) == len(PIG)
    for s, (z, w, a, b) in zip(out["blobs"]["body"]["sections"], PIG):
        assert s["half_width"] == pytest.approx(w, abs=0.006)
        assert s["half_depth"] == pytest.approx((b - a) / 2, abs=0.006)
        assert s["offset_y"] == pytest.approx((a + b) / 2, abs=0.006)


def test_loft_sections_from_outlines_keep_a_row_another_part_crosses():
    target = spec_of(body=pear(), arm={"at": [0.24, 0, 0.32], "size": [0.08, 0.05, 0.06]})
    start = copy.deepcopy(target)
    refs = {v: _world_ref(target, v, 200) for v in ("front", "side")}
    out, lines = fitmod.loft_from_refs(start, refs, "body", resolution=110)
    assert "kept" in lines[2] and out["blobs"]["body"]["sections"][2]["half_width"] == 0.20
