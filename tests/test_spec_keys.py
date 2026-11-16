"""spec_keys: an unknown key on a joint, a bone or a blob is refused with the list (C442); it used to save in silence."""
import json
from pathlib import Path

import pytest

from hifipushie import spec as specmod, spec_keys, store

ROOT = Path(__file__).resolve().parent.parent


def _spec(**blob):
    return {"symmetry": True, "blend": 0.03, "joints": {"hip": {"pos": [0, 0, 1.0], "r": 0.1}, "top": {"pos": [0, 0, 1.4], "r": 0.08}},
            "bones": {"spine": {"a": "hip", "b": "top"}}, "blobs": {"belly": {"at": "hip", "size": [0.1, 0.1, 0.1], **blob}}}


def test_a_typo_on_a_blob_is_refused_with_the_nearest_key_and_the_list():
    with pytest.raises(specmod.SpecError) as e:
        spec_keys.check(_spec(sizee=[0.2, 0.2, 0.2]))
    msg = str(e.value)
    assert msg.startswith("blob 'belly': unknown key 'sizee' (did you mean 'size'?)") and "A blob takes: at, offset, size" in msg
    assert "Nothing was saved" in msg and "kit_reference" in msg
    with pytest.raises(specmod.SpecError, match=r"unknown key 'radius'\. A blob takes"):  # (no near key: the list alone)
        spec_keys.check(_spec(radius=0.2))


def test_joints_and_bones_too_and_every_unknown_key_is_counted():
    s = _spec()
    s["joints"]["hip"]["radius"] = 0.2
    s["bones"]["spine"]["r_c"] = 0.1
    s["blobs"]["belly"]["offest"] = [0, 0, 0.1]
    assert spec_keys.unknown(s) == [("joints", "hip", "radius", None), ("bones", "spine", "r_c", None),
                                    ("blobs", "belly", "offest", None)]
    with pytest.raises(specmod.SpecError, match=r"joint 'hip': unknown key 'radius' \(2 more unknown key\(s\): spine.r_c, belly.offest\)\. A joint takes: pos, r, on, lift, shift"):
        spec_keys.check(s)
    del s["joints"]["hip"]["radius"]
    with pytest.raises(specmod.SpecError, match=r"bone 'spine': unknown key 'r_c' \(did you mean 'r_[ab]'\?\)"):
        spec_keys.check(s)


def test_a_spec_is_refused_before_it_is_saved_and_the_known_keys_pass():
    with pytest.raises(specmod.SpecError, match="unknown key 'sizee'"):
        store.validate(_spec(sizee=[0.2, 0.2, 0.2]))
    store.validate(_spec(rot=[0, 0, 10], offset=[0, 0, 0.02], shape="box", round=0.01, layer=1, op="add", blend=0.02))
    for f in sorted((ROOT / "examples").glob("*.json")):
        s = json.loads(f.read_text())
        if isinstance(s, dict) and "joints" in s:
            assert spec_keys.unknown(s) == [], f.name


def test_the_shape_names_and_the_lists_are_strings_the_code_reads():
    """Every listed key is read somewhere in the modules that build these elements (a list that drifts refuses nothing)."""
    src = "\n".join(p.read_text() for p in sorted((ROOT / "src/hifipushie").glob("*.py")) if p.name != "spec_keys.py")
    for _, known in spec_keys.KEYS.values():
        missing = [k for k in known if f'"{k}"' not in src]
        assert not missing, missing


def test_a_hollow_or_chipped_bone_is_a_bone():
    """C442's bone list missed "hollow" and "chips" (element-level solids, on bones as on blobs): a hollow log was refused."""
    s = _spec()
    s["bones"]["spine"].update(hollow=0.01, chips={"depth": 0.004}, lumpy=0.003, ends="flat")
    store.validate(s)
    assert set(spec_keys.GENERIC) <= set(spec_keys.BONE_KEYS) and set(spec_keys.GENERIC) <= set(spec_keys.BLOB_KEYS)


def test_every_key_the_compile_reads_off_any_element_is_in_both_lists():
    """The compile (spec.py and the modules split off it) reads these off `el` whatever the element is (bone or blob):
    a key missing from either list refuses a spec the compile would have built. (The lists were first read off the
    saved specs: no saved bone was hollow.)"""
    import re
    from hifipushie import moved
    src = "".join((ROOT / "src/hifipushie" / f).read_text() for f in moved.files("spec"))
    keys = set(re.findall(r'\bel\.get\("(\w+)"', src)) | set(re.findall(r'\bel\["(\w+)"\]', src))
    assert {"hollow", "chips", "lumpy", "targets", "local"} <= keys
    assert keys <= set(spec_keys.BONE_KEYS) and keys <= set(spec_keys.BLOB_KEYS), keys - set(spec_keys.BONE_KEYS) & set(spec_keys.BLOB_KEYS)


def test_the_elements_inside_a_prefab_are_checked_and_named_with_it():
    s = _spec()
    s["prefabs"] = {"chair": {"joints": {"a": {"pos": [0, 0, 0], "r": 0.02}, "b": {"pos": [0, 0, 0.4], "r": 0.02}},
                              "bones": {"leg": {"a": "a", "b": "b", "hollow": 0.004}},
                              "blobs": {"seat": {"at": "b", "size": [0.2, 0.2, 0.02], "shape": "box"}}}}
    assert spec_keys.unknown(s) == []
    s["prefabs"]["chair"]["blobs"]["seat"]["sizes"] = [0.3, 0.3, 0.02]
    assert spec_keys.unknown(s) == [("blobs", "seat", "sizes", "chair")]
    with pytest.raises(specmod.SpecError, match=r"^prefab 'chair': blob 'seat': unknown key 'sizes' \(did you mean 'size'\?\)"):
        store.validate(s)
