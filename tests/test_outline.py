"""Extruded outlines and lettering (outline.py): exact distance, holes, bevel, text set one blob per letter."""
import numpy as np
import pytest

from hifipushie import assemble_expand, outline
from hifipushie.spec import SpecError, compile_prims

SQUARE = [[-0.1, 0.0], [0.1, 0.0], [0.1, 0.2], [-0.1, 0.2]]
HOLE = [[-0.05, 0.05], [-0.05, 0.15], [0.05, 0.15], [0.05, 0.05]]  # drawn the other way round, as fonts do


def _prim(**bl):
    spec = {"symmetry": False, "blend": 0.0, "joints": {}, "bones": {},
            "blobs": {"o": {"shape": "outline", "at": [0, 0, 0], **bl}}}
    return compile_prims(assemble_expand.expand(spec))[0]


def test_distance_is_exact_off_the_faces_and_negative_inside():
    p = _prim(loops=[SQUARE], depth=0.04)
    d = outline.sd_outline(np.array([[0.3, 0, 0.1], [0, -0.12, 0.1], [0, 0, 0.1], [0.09, 0, 0.1]]), p.params)
    assert d == pytest.approx([0.2, 0.1, -0.02, -0.01], abs=1e-9)


def test_a_loop_inside_a_loop_is_a_hole():
    p = _prim(loops=[SQUARE, HOLE], depth=0.04)
    assert outline.sd_outline(np.array([[0.0, 0, 0.1]]), p.params)[0] == pytest.approx(0.05)


def test_the_bevel_cuts_the_front_edge_at_45_degrees():
    p = _prim(loops=[SQUARE], depth=0.04, bevel=0.01)
    # the corner point of the unbevelled slab (x = 0.1, y = -0.02) lies outside, b / sqrt 2 off the chamfer
    d = outline.sd_outline(np.array([[0.1, -0.02, 0.1], [0.0, -0.02, 0.1]]), p.params)
    assert d == pytest.approx([0.01 / np.sqrt(2), 0.0], abs=1e-9)


def test_text_is_one_outline_blob_per_letter_on_the_cap_height():
    spec = {"symmetry": False, "blend": 0.0, "joints": {}, "bones": {},
            "blobs": {"t": {"shape": "text", "text": "AB C", "height": 0.3, "depth": 0.05, "at": [0, 0, 0]}}}
    s = assemble_expand.expand(spec)
    assert list(s["blobs"]) == ["t/A#0", "t/B#1", "t/C#2"]
    prims = compile_prims(s)
    assert [p.kind for p in prims] == ["outline"] * 3
    top = max(p.hi[2] for p in prims)
    assert top == pytest.approx(0.3, abs=0.02)  # cap height (round letters overshoot it a little)
    lo, hi = min(p.lo[0] for p in prims), max(p.hi[0] for p in prims)
    assert abs(lo + hi) < 0.02  # centred on `at`


def test_bad_outlines_and_fonts_are_refused():
    with pytest.raises(SpecError, match="depth"):
        _prim(loops=[SQUARE], depth=0.02, bevel=0.02)
    with pytest.raises(SpecError, match="no font"):
        assemble_expand.expand({"symmetry": False, "joints": {}, "bones": {},
                                "blobs": {"t": {"shape": "text", "text": "A", "font": "comic-sans"}}})


def test_grow_moves_the_outline_out_and_arc_lifts_the_middle_letters():
    p = _prim(loops=[SQUARE], depth=0.04, grow=0.01)
    assert outline.sd_outline(np.array([[0.3, 0, 0.1]]), p.params)[0] == pytest.approx(0.19)
    g = outline.text_glyphs("HHH", height=0.3, arc=0.05)
    base = [min(pz for lp in loops for _, pz in lp) for _, loops in g]
    assert base[1] == pytest.approx(0.05, abs=1e-6) and base[0] == pytest.approx(base[2]) and base[0] < base[1]
