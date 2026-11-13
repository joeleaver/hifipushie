"""A long mass from its marks (masslines.py): the mark's own middle line and its width across it, on shapes whose
answer is known. Drawn here as point clouds, the way masses._flat hands a mark over."""
from __future__ import annotations

import numpy as np
import pytest

from hifipushie import featuremap, forms, masses, masslines, sdf
from hifipushie.spec import compile_prims

K = 0.00167  # metres per pixel


def _cloud(fn, w=200, h=200):
    ys, xs = np.mgrid[0:h, 0:w]
    m = fn(xs * K, ys * K)
    return np.stack([xs[m] * K, ys[m] * K], 1)


A = np.array([0.08, 0.05])
T = np.array([np.sin(np.radians(35)), np.cos(np.radians(35))])  # 35 degrees off upright
N = np.array([T[1], -T[0]])


def _capsule(x, y, r=0.025, length=0.11):
    p = np.stack([x, y], -1) - A
    t = np.clip(p @ T, 0, length)
    return np.hypot(*np.moveaxis(p - t[..., None] * T, -1, 0)) < r


def _box(x, y, half=0.025, length=0.14):
    p = np.stack([x, y], -1) - A
    return (np.abs(p @ N) < half) & (p @ T > 0) & (p @ T < length)


def test_a_slanted_limbs_width_is_read_across_it():
    """A slice across the page through a slanted limb is wider than the limb: the old tube built a 16 cm arm as
    an 8 cm chain of fat balls."""
    line = masslines.middle(_cloud(_capsule), K)
    assert abs(line["length"] - 0.160) < 0.005, line["length"]
    assert abs(np.median(line["half"]) - 0.025) < 0.002, np.median(line["half"])
    assert line["cut"] == [False, False]
    tip = lambda p: min(np.hypot(*(p - (A - 0.025 * T))), np.hypot(*(p - (A + 0.135 * T))))  # noqa: E731
    assert tip(line["c"][0]) < 0.004 and tip(line["c"][-1]) < 0.004, (line["c"][0], line["c"][-1])


def test_a_cut_end_is_the_middle_of_its_cut():
    pts = _cloud(_box)
    along = (pts - A) @ T
    touch = pts[(along < 3 * K) | (along > 0.14 - 3 * K)]  # both ends lie against a neighbour
    line = masslines.middle(pts, K, touch)
    assert line["cut"] == [True, True]
    ends = sorted([line["c"][0], line["c"][-1]], key=lambda p: p[1])
    assert np.hypot(*(ends[0] - A)) < 0.005 and np.hypot(*(ends[1] - (A + 0.14 * T))) < 0.005, ends
    assert abs(np.median(line["half"]) - 0.025) < 0.002
    # touched all round, it LIES OVER the other mass here: no end is a cut, and a stubby lump's line is its long
    # axis, not a corner-to-corner diagonal
    rect = _cloud(lambda x, y: (x > 0.10) & (x < 0.19) & (y > 0.05) & (y < 0.21))
    edge = rect[(rect[:, 0] < 0.10 + 3 * K) | (rect[:, 0] > 0.19 - 3 * K) | (rect[:, 1] < 0.05 + 3 * K) | (rect[:, 1] > 0.21 - 3 * K)]
    line = masslines.middle(rect, K, edge)
    assert line["cut"] == [False, False] and np.ptp(line["c"][:, 0]) < 0.012, (line["cut"], np.ptp(line["c"][:, 0]))
    assert abs(line["length"] - 0.16) < 0.008


def test_a_curl_is_followed():
    def horn(x, y):
        ang = np.arctan2(y - 0.16, x - 0.16) % (2 * np.pi)
        return (ang < 1.5 * np.pi) & (np.abs(np.hypot(x - 0.16, y - 0.16) - 0.09) < 0.004 + 0.02 * (1 - ang / (1.5 * np.pi)))
    line = masslines.middle(_cloud(horn), K)
    assert abs(line["length"] - 1.5 * np.pi * 0.09) < 0.03, line["length"]
    mid = line["c"][len(line["c"]) // 6: -len(line["c"]) // 6]
    off = np.abs(np.hypot(*(mid - 0.16).T) - 0.09)
    assert off.max() < 0.006, off.max()                 # on the ring all the way round
    thin = min(line["half"][2], line["half"][-3])
    assert thin < 0.011 and line["half"].max() > 0.017, (thin, line["half"].max())  # and it tapers


def test_a_tube_is_as_thick_as_its_mark_and_runs_on_under_its_neighbour():
    pts = _cloud(_box)
    along = (pts - A) @ T
    streak = _cloud(lambda x, y: (np.abs(x - 0.02) < 1.6 * K) & (y > 0.05) & (y < 0.165))  # a line mark in the other view
    notes: list = []
    f = {"xz": pts, "touch_xz": pts[along > 0.14 - 3 * K], "yz": streak, "line_yz": True, "px": K}
    out = masslines.tube("arm.L", f, {"joints": 4}, notes)
    j = [out["joints"][f"arm_j{i}.L"] for i in range(4)]
    assert all(abs(q["r"] - 0.025) < 0.003 for q in j), [q["r"] for q in j]
    assert all(abs(q["pos"][1] - 0.02) < 0.003 for q in j)                    # it runs where the line does
    top, tip = A + 0.14 * T, A
    root, far = np.array(j[0]["pos"])[[0, 2]], np.array(j[-1]["pos"])[[0, 2]]
    assert 0.3 * 0.025 < np.hypot(*(root - top)) < 0.8 * 0.025                # set in: its cap pokes into the neighbour
    assert abs(np.hypot(*(far - tip)) - 0.025) < 0.006                        # the free end's cap stops at the mark's end
    b = out["bones"]["arm_b0.L"]
    assert b["up"] == [0.0, -1.0, 0.0] and all(0.85 < v <= 1.0 for v in b["flat"]), b
    assert any("runs on under" in n and "capped where its mark stops" in n for n in notes), notes
    with pytest.raises(ValueError, match="no mark in a flat view"):
        masslines.tube("arm.L", {"px": K}, {}, [])


def test_a_trunk_leaves_out_rows_its_mark_only_fringes():
    body = _cloud(lambda x, y: (np.abs(x - 0.15) < 0.06) & (y > 0.10) & (y < 0.25))
    sliver = _cloud(lambda x, y: (np.abs(np.abs(x - 0.15) - 0.057) < 0.003) & (y > 0.08) & (y <= 0.10))
    notes: list = []
    kept = masses._solid(np.vstack([body, sliver]), K, "torso", notes)
    assert kept[:, 1].min() > 0.098 and len(kept) >= len(body) - 80 and notes and "slivers" in notes[0], (kept[:, 1].min(), notes)
    assert len(masses._solid(body, K, "torso", [])) == len(body)


def test_a_cut_that_parts_nothing_is_refused():
    fig = np.zeros((220, 200), bool)
    fig[10:210, 20:180] = True
    ok = featuremap._piece(fig, {"piece": [100, 40], "cuts": [[[10, 100], [190, 100]]]}, "front", {}, "x")
    assert ok[20:95].sum() > 0 and not ok[110:].any()
    with pytest.raises(ValueError, match="cut 2 .* changes nothing"):
        featuremap._piece(fig, {"piece": [100, 40], "cuts": [[[10, 100], [190, 100]], [[80, 60], [120, 60]]]}, "front", {}, "x")


def test_a_foreshortened_view_still_gives_the_lean():
    """A horn seen from the front is a short fat lump, but its lean outward shows only there: at each height the
    lump's middle is where the thing is (one mean place built every horn straight up)."""
    side = _cloud(_box)                                           # the view that shows its length: z 0.05 .. 0.165
    lump = _cloud(lambda x, y: (np.abs(x - (0.06 + 0.35 * (y - 0.05))) < 0.045) & (y > 0.05) & (y < 0.165))
    notes: list = []
    out = masslines.tube("horn.L", {"yz": side, "xz": lump, "px": K}, {"joints": 5}, notes)
    j = sorted((out["joints"][n]["pos"] for n in out["joints"]), key=lambda p: p[2])
    xs, zs = np.array([p[0] for p in j]), np.array([p[2] for p in j])
    assert np.all(np.diff(xs) > 0) and np.allclose(xs, 0.06 + 0.35 * (zs - 0.05), atol=0.008), (xs, zs)
    assert any("foreshortened" in n for n in notes), notes


def test_a_mass_in_several_pieces_is_one_lump_per_piece():
    """Hanging locks marked as a row of drops are a row of lumps, each with what the other view shows at its
    heights (one ball over the whole row's box was a bar)."""
    drops = np.vstack([_cloud(lambda x, y, c=c: ((x - c) / 0.012) ** 2 + ((y - 0.10) / 0.03) ** 2 < 1) for c in (0.05, 0.09, 0.13)])
    band = _cloud(lambda x, y: (np.abs(x - 0.20) < 0.015) & (y > 0.06) & (y < 0.14))
    notes: list = []
    out = masses._ball("fringe", {"xz": drops, "yz": band, "px": K}, {"as": "ball"}, notes)["blobs"]
    assert sorted(out) == ["fringe_1", "fringe_2", "fringe_3"], sorted(out)
    assert [round(out[n]["at"][0], 2) for n in sorted(out)] == [0.05, 0.09, 0.13]
    assert all(abs(b["size"][0] - 0.012) < 0.003 and abs(b["size"][2] - 0.03) < 0.004 and abs(b["at"][1] - 0.20) < 0.004 for b in out.values()), out
    assert any("3 separate pieces" in n for n in notes)
    assert list(masses._ball("knob", {"xz": drops[:400], "yz": band, "px": K}, {}, [])["blobs"]) == ["knob"]


def test_a_band_goes_all_the_way_round_a_limb():
    """A cuff marked as a strip across a limb in one view is one stroke round the limb's bone there (laid from the
    view it only covered the half that view sees)."""
    spec = {"symmetry": False, "blend": 0.02, "blobs": {}, "joints": {"a": {"pos": [0, 0, 0.4], "r": 0.03}, "b": {"pos": [0, 0, 0.1], "r": 0.03}},
            "bones": {"limb": {"a": "a", "b": "b"}}}
    strip = _cloud(lambda x, y: (np.abs(x - 0.05) < 0.04) & (np.abs(y - 0.19) < 0.012)) - np.array([0.05, 0.0])
    bd = forms.band(spec, ["limb"], strip, "front")
    assert bd["path"][0]["bone"] == "limb" and abs(bd["path"][0]["t"] - 0.7) < 0.03 and abs(bd["half"] - 0.012) < 0.003, bd
    st = {"op": "clay", "path": bd["path"], "width": 0.014, "depth": 0.008, "profile": "round"}
    prims = compile_prims({**spec, "strokes": {"cuff": st}})
    ring = np.array([[0.034, 0, 0.19], [-0.034, 0, 0.19], [0, 0.034, 0.19], [0, -0.034, 0.19], [0.024, 0.024, 0.19]])
    assert np.all(sdf.field_at(prims, ring) < 0), sdf.field_at(prims, ring)            # proud all the way round
    assert np.all(sdf.field_at(prims, ring + np.array([0, 0, 0.1])) > 0)                 # and only there
