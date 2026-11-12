"""The front door for creatures and props (the area re-review, 2026-11-12; C435): a next line after every save and look,
an unknown blob shape refused, and a quadruped not told it is a human."""
import json
from pathlib import Path

import pytest

from hifipushie import next_steps, realism, spec as specmod

EXAMPLES = Path(__file__).parent.parent / "examples"


def _example(name: str) -> dict:
    return json.loads((EXAMPLES / f"{name}.json").read_text())


def test_a_quadruped_is_not_told_it_is_a_human():
    fox, troll = _example("fox"), _example("troll")
    assert not realism.looks_humanoid(fox) and realism.looks_humanoid(troll)
    assert not any(line.startswith("HUMANOID WITHOUT A BASE") for line in realism.audit(fox))
    assert realism.audit(troll)[0].startswith("HUMANOID WITHOUT A BASE")
    # by posture, not by name: the same joints laid along the ground are no biped
    lying = {"joints": {"head": {"pos": [0, -0.8, 0.3]}, "pelvis": {"pos": [0, 0.4, 0.3]}, "shoulder.L": {"pos": [0.2, -0.5, 0.3]},
                        "knee.L": {"pos": [0.1, 0.6, 0.2]}}}
    assert not realism.looks_humanoid(lying)
    lying["joints"]["head"]["pos"], lying["joints"]["pelvis"]["pos"] = [0, 0, 1.6], [0, 0, 0.9]
    assert realism.looks_humanoid(lying)
    assert realism.upright({"head": {"pos": [0, 0, 1]}})  # (no hips to compare with: the names alone decide, as before)


def test_an_unknown_blob_shape_is_refused_with_the_shapes_there_are():
    s = specmod.empty_spec()
    s["joints"]["a"] = {"pos": [0, 0, 1], "r": 0.1}
    s["blobs"]["ball"] = {"at": "a", "size": [0.1, 0.1, 0.1], "shape": "sphere"}
    with pytest.raises(specmod.SpecError, match=r"blob 'ball': unknown shape 'sphere' \(have ellipsoid, box, cylinder"):
        specmod.compile_prims(s)
    s["blobs"]["ball"]["shape"] = "ellipsoid"
    assert any(p.name == "ball" for p in specmod.compile_prims(s))
    del s["blobs"]["ball"]["shape"]
    assert any(p.name == "ball" for p in specmod.compile_prims(s))


def test_every_example_still_compiles():
    for p in sorted(EXAMPLES.glob("*.json")):
        s = json.loads(p.read_text())
        if isinstance(s, dict) and "blobs" in s and not s.get("base"):
            specmod.compile_prims({**specmod.empty_spec(), **s})  # (as put_model stores it: the defaults under it)


def test_a_save_and_a_look_of_a_creature_say_what_is_next():
    plain = {"joints": {}, "bones": {}, "blobs": {}}
    assert next_steps.after_save("owl", plain).startswith('next: look("owl")') and "set_plan" in next_steps.after_save("owl", plain)
    assert "set_plan" not in next_steps.after_save("owl", {**plain, "plan": {"views": {}}})
    for key in ("base", "cloth", "skin", "hair"):  # (a character's own tools speak for themselves)
        assert next_steps.after_save("tess", {**plain, key: {"x": 1}}) == ""
    none, some = next_steps.after_model_look("owl", False), next_steps.after_model_look("owl", True)
    assert none.startswith("next:") and "fit_concept_camera" in none and "set_plan" in none
    assert some.startswith('next: check("owl")') and "review_view" in some


def test_the_tools_put_those_lines_last():
    """put_model, edit_model and look end with the line (the server's instructions promise a next: on every tool)."""
    src = (Path(specmod.__file__).parent / "tools_model.py").read_text()
    assert src.count("+ _join_lines(name, joins) + _next_save(name, ") == 2
    assert "next_steps.after_model_look(name, _has_reference(name, sp_))" in src
