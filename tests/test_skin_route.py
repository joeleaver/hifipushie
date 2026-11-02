"""The skin route's refusals, defaults and reply lines (skin_route.py). No renders."""
import json

import pytest

from hifipushie import server, skin_route as sr, store


def _spec(**sk):
    return {"skin": sk, "base": {"head": {"source": "gnm"}}}


ATLAS = {"albedo": "a", "confidence": "c", "delight": True}


def test_read_defaults_to_the_atlas_for_photographs():
    assert sr.plan_read(_spec(tone={"fitzpatrick": 2}), None, False, False)[0] is True


def test_fresh_atlas_is_reused(monkeypatch):
    monkeypatch.setattr("hifipushie.skin_project.stale", lambda s: False)
    do, line = sr.plan_read(_spec(tone={"fitzpatrick": 2}, projection=ATLAS), None, False, False)
    assert do is False and "fresh atlas" in line


def test_stale_atlas_is_remade_and_said(monkeypatch):
    monkeypatch.setattr("hifipushie.skin_project.stale", lambda s: True)
    do, line = sr.plan_read(_spec(tone={"fitzpatrick": 2}, projection=ATLAS), None, False, False)
    assert do is True and "STALE" in line


def test_refusals_of_the_read():
    with pytest.raises(ValueError, match="read_only"):
        sr.plan_read(_spec(), True, False, True)
    with pytest.raises(ValueError, match="painting"):
        sr.plan_read(_spec(), True, True, False)
    with pytest.raises(ValueError, match="painting=True"):
        sr.plan_read(_spec(tone={}, ), False, False, False)
    with pytest.raises(ValueError, match="skin.tone"):
        sr.plan_read(_spec(), None, False, False)


def test_painting_takes_the_per_picture_read():
    assert sr.plan_read(_spec(), None, True, False)[0] is False


def test_read_only_needs_no_tone():
    assert sr.plan_read(_spec(), None, False, True)[0] is False


def test_decals_refused_on_a_stack():
    with pytest.raises(ValueError, match="stack"):
        sr.refuse_decals(_spec(stack={"layers": []}))
    sr.refuse_decals(_spec())


def test_export_refuses_the_photo_overlay():
    with pytest.raises(ValueError, match="never ship"):
        sr.refuse_photo_skin(_spec(projection={"opacity": 1.0}))
    sr.refuse_photo_skin(_spec(projection={"opacity": 0.0}))


def test_stack_edit():
    sp = _spec(stack={"layers": [{"name": "redness", "opacity": 0.8}, {"name": "periorbital", "opacity": 0.3}]})
    out, line = sr.stack_edit(sp, "blush")
    assert "measured" in line and out["skin"]["stack"]["layers"][0]["opacity"] != 0.8
    with pytest.raises(ValueError, match="unknown"):
        sr.stack_edit(sp, "glow")
    with pytest.raises(ValueError, match="unknown"):
        sr.stack_edit(sp, {"nope": 1})
    with pytest.raises(ValueError, match="skin.stack"):
        sr.stack_edit(_spec(), "blush")


def test_no_effect_names_covered_keys(monkeypatch):
    def layers(sp, J):
        s = sp["skin"]
        return {"skin:midface": {"color": [s.get("zones", {}).get("m", 0)] * 3, "_pre": True},
                "skin:lid_shade": {"color": [s.get("zones", {}).get("lid", 0)] * 3}}
    monkeypatch.setattr("hifipushie.skin._build", layers)
    monkeypatch.setattr("hifipushie.skin._joints", lambda sp: {})
    monkeypatch.setattr("hifipushie.skin.part_base", lambda sp: ("body", {"color": [0, 0, 0], "roughness": 0.5}))
    old = _spec(stack={"layers": []}, zones={"m": 0, "lid": 0}, tone={"melanin": 0.2})
    patch = {"zones": {"m": 1, "lid": 1}, "tone": {"melanin": 0.3}}
    new = _spec(stack={"layers": []}, zones={"m": 1, "lid": 1}, tone={"melanin": 0.3})
    txt = sr.no_effect(old, new, patch)
    assert "NO EFFECT" in txt and "stack's): zones.m." in txt and "BODY ONLY" in txt and "tone.melanin" in txt
    assert sr.no_effect(_spec(), _spec(), patch) == ""


def test_fold_relief_and_limit():
    txt = sr.form_lines({"skin": {"folds": {"lid_fold": 0.6, "nasolabial": {"amount": 1.5, "depth": 2.5}}}})
    assert "fold relief" in txt and "lid_fold" in txt and "mm" in txt and "WARNING nasolabial" in txt


def test_head_approval(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    (tmp_path / "ok").mkdir()
    (tmp_path / "ok" / "spec.json").write_text(json.dumps({"base": {"head": {"a": 1, "attach": "x"}}}))
    (tmp_path / "approved.json").write_text(json.dumps({"approved": {"head/ok": {"model": "ok"}}}))
    assert sr.head_unapproved({"base": {"head": {"a": 1, "attach": "y"}}}) == ""
    assert "no approved head" in sr.head_unapproved({"base": {"head": {"a": 2}}})
    assert "head/ok" in sr.head_unapproved({"base": {"head": {"a": 2}, "head_approved": "head/ok"}})
    assert sr.head_unapproved({}) == ""


def test_look_skin_has_no_cycles_and_gates_beside():
    import inspect
    assert "engine" not in inspect.signature(server.look_skin).parameters
    from hifipushie import skin_look
    with pytest.raises(ValueError, match="one region"):
        skin_look.beside("x", "eye", flat=True)
    with pytest.raises(ValueError, match="light"):
        skin_look.beside("x", "eye", light="rake")
    with pytest.raises(ValueError, match="beside is one of"):
        skin_look.beside("x", "ear")


def test_every_skin_reply_ends_with_next():
    assert sr.after_reference().startswith("next:")
    for s in (sr.after_brows("m", True), sr.after_brows("m", False), sr.after_read("m", read_only=True),
              sr.next_look({"region": "eye"}, ["brows"])):
        assert "next:" in s.splitlines()[-1]


@pytest.mark.parametrize("q", ["pores", "stubble", "make-up", "paint skin texture"])
def test_find_tool_starts_the_skin_route(q):
    txt = server.find_tool(q)
    assert "Skin: approved head" in txt and "\n1. skin " in txt and "texture_from_reference" not in txt
