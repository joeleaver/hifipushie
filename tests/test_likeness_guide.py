"""The likeness guide hands a block-in head to the tools that take it (the area re-review: it taught fit_likeness,
which refuses a block-in model, as the step after the block-in)."""
from pathlib import Path

import pytest

from hifipushie import head_route

GUIDE = (Path(head_route.__file__).parent / "likeness_guide.md").read_text()


def test_after_the_block_in_the_guide_names_the_hand_step_and_the_ruler():
    order = GUIDE[GUIDE.index("ORDER:"):GUIDE.index("Sub-topics")]
    assert "block_in_step(name, {\"mm:<measure>\": mm}" in order and "face_ruler" in order
    assert "refuses a block-in model" in order and "for features after it" not in GUIDE
    staged = GUIDE[GUIDE.index("## Staged fitting from the sheet"):]
    assert staged.splitlines()[0].endswith("(a `human` model without the block-in)")
    assert "NOT on a block-in model" in staged.split("|", 1)[0]


def test_the_guide_says_what_the_tool_does(tmp_path, monkeypatch):
    """fit_likeness really refuses a block-in model, with the same two tools in its message."""
    from hifipushie import store
    monkeypatch.setattr(store, "HOME", tmp_path)
    (tmp_path / "bi").mkdir()
    (tmp_path / "bi" / "human_refs.json").write_text('{"blockin": {}}')
    with pytest.raises(ValueError, match=r"fit_likeness: REFUSED on bi, a block-in model.*block_in_step.*face_ruler"):
        head_route.refuse_off_route("bi", "fit_likeness")


def test_a_feature_of_a_block_in_head_leads_with_the_hand_step_and_a_start_with_the_start():
    s = {"block_in_start": 1.0, "block_in_step": 0.2, "face_ruler": 0.1, "build_forms": 0.9}
    lead = lambda q: max(head_route.pin_block_in(q, s).items(), key=lambda kv: kv[1])[0]  # noqa: E731
    assert lead("fit the nose and mouth of my block-in head to the photos") == "block_in_step"
    assert sorted(head_route.pin_block_in("move the nose of my block-in head", s).items(), key=lambda kv: -kv[1])[1][0] == "face_ruler"
    assert lead("start a block-in of a person from photos") == "block_in_start"
    assert lead("make this head from the references") == "block_in_start"
    assert head_route.pin_block_in("lay the brows and sockets of the reference on my block-in", s) == s  # (any model's block-out)
    assert head_route.pin_block_in("the nose of the hair on my block-in head", s) == s  # (another domain is named)
