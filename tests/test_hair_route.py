"""The hair route (hair_route.py): a blind agent is walked down one path; wrong paths refuse or warn. No Blender."""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_hair_loose import _ball_head  # noqa: E402

from hifipushie import hair, hair_read, hair_route as hr, server, store  # noqa: E402


@pytest.fixture
def model(monkeypatch):
    """One in-memory model on a ball head: a saved spec, no disk, no meshing."""
    sc, _ = _ball_head()
    box = {"spec": {"base": {"head": {}}}, "sc": sc}

    def load(name):
        return store.copy.deepcopy(box["spec"])

    def save(name, spec, note="", checked=True):
        box["spec"] = store.copy.deepcopy(spec)
        return 1

    monkeypatch.setattr(store, "load", load)
    monkeypatch.setattr(store, "save", save)
    monkeypatch.setattr(hair, "scalp", lambda name, spec=None: box["sc"])
    return box


GROOM = {"seed": 1}


def _last(text):
    return text.strip().splitlines()[-1]


def test_a_first_groom_on_a_base_is_strands(model):
    r = server.groom_hair("m", groom=GROOM)
    assert model["spec"]["hair"]["style"] == "strands"
    assert _last(r).startswith("next: ")


def test_no_base_stays_locks(model):
    model["spec"] = {}
    server.groom_hair("m", groom=GROOM)
    assert "style" not in model["spec"]["hair"]


def test_explicit_locks_stay_and_warn(model):
    r = server.groom_hair("m", groom=GROOM, style="locks")
    assert model["spec"]["hair"]["style"] == "locks"
    assert 'WARNING style "locks"' in r and _last(r).startswith("next: ")


def test_a_grown_solid_groom_is_not_flipped():
    sp = {"base": {"head": {}}, "hair": {"locks": {"a": {}}}}
    hr.default_style(sp)
    assert "style" not in sp["hair"] and hr.style_warning(sp)


def test_cards_refused_from_groom_hair(model):
    with pytest.raises(Exception, match="look_hair"):
        server.groom_hair("m", style="cards")


@pytest.mark.parametrize("export, word", [({"styel": "shells"}, "styel"), ({"style": "shell"}, "style"),
                                          ({"shells": {"height": [1]}}, "height")])
def test_export_mistakes_refused(export, word):
    with pytest.raises(hair.HairError, match=word):
        hair.validate({"hair": {"export": export}})


def test_every_export_key_the_code_reads_passes():
    hair.validate({"hair": {"export": {k: None for k in hr.EXPORT_KEYS if k not in ("style",)}}})
    hair.validate({"hair": {"export": {"style": "shells", "shells": {"heights": [0.6], "tiers": {"far": 0}}}}})


def test_shells_reach_the_export_through_edit_model():
    sp = store.edit({"hair": {"locks": {}}}, [{"op": "set", "kind": "hair", "name": "export", "value": {"style": "shells"}}])
    assert sp["hair"]["export"]["style"] == "shells"


def _shaped(length):
    return {"locks": {"a": {"space": "xyz", "pts": [[0, 0, 0], [0, 0, length]]}}, "groom": {"loose": {"length": length}}}


def test_short_groom_is_told_about_shells(model):
    model["spec"] = {"base": {"head": {}}, "hair": {"style": "strands", **_shaped(0.03)}}
    assert "shells" in hr.groom_next("m", model["spec"])


def test_shells_on_long_hair_warn(model):
    sp = {"hair": {"export": {"style": "shells"}, **_shaped(0.3)}}
    assert hr.shells_warning("m", sp)
    sp = {"hair": {"export": {"style": "shells"}, **_shaped(0.03)}}
    assert not hr.shells_warning("m", sp)


def test_head_change_warns(model):
    server.groom_hair("m", groom=GROOM)
    assert model["spec"]["hair"]["head"] and not hr.head_warning("m", model["spec"])
    r0 = model["sc"].R
    model["sc"].R = r0 + 0.002
    assert "head changed" in hr.head_warning("m", model["spec"])
    assert "head changed" in hr.look_next("m", model["spec"], None)
    assert "head changed" in hr.export_next("m", "/x", ["main"])
    model["sc"].R = r0


def test_a_groom_without_a_stored_head_says_nothing(model):
    model["spec"] = {"hair": {"locks": {}}}
    assert hr.head_warning("m") == ""


def test_regrow_takes_the_new_head(model):
    server.groom_hair("m", groom=GROOM)
    was = model["spec"]["hair"]["head"]
    model["sc"].R = model["sc"].R + 0.002
    server.groom_hair("m", replace=True)
    assert model["spec"]["hair"]["head"] != was and not hr.head_warning("m", model["spec"])


def test_every_route_reply_ends_next(model):
    sp = {"base": {"head": {}}, "hair": {"style": "strands", "locks": {}}}
    model["spec"] = sp
    for t in (hr.groom_next("m", sp), hr.look_next("m", sp, None), hr.look_next("m", sp, "main"),
              hr.look_next("m", {"hair": {"stage": "mass"}}, None), hr.export_next("m", "/x", ["main"]),
              hr.reader_next("m", "", False), hr.reader_next("m", "", True), hr.compare_next("m"),
              hr.reference_next("m", True), hr.reference_next("m", False)):
        assert _last(t).startswith("next: "), t


def test_hair_from_reference_reply_ends_next(model, monkeypatch):
    monkeypatch.setattr(hair_read, "apply", lambda *a, **k: {"text": "read"})
    assert _last(server.hair_from_reference("m")).startswith("next: ")


def test_find_tool_hair_shows_the_path():
    text = server.find_tool("hair")
    assert text.startswith("Hair: describe")
    assert "tie_hair" in text and "groom_hair" in text and "look_hair" in text


def test_guide_states_one_default_path():
    src = open(os.path.join(os.path.dirname(hair.__file__), "hair_guide.md")).read()
    assert src.index("## The default path") < 40
