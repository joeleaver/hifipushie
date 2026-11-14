"""terrain.unnamed_keys: a key no terrain code names is ignored, and the terrain report says so (C456)."""
import json
from pathlib import Path

from hifipushie import terrain

ROOT = Path(__file__).resolve().parent.parent


def _spec():
    return {"extent": [[0, 0], [2000, 2000]], "world": "alpine", "story": "a test",
            "peaks": {"north": {"at": [500, 1500], "h": 900, "radius": 400}},
            "sites": [{"name": "hut", "at": [900, 900], "radius": 20}],
            "cover": {"wood": {"type": "forest", "in": "low", "density": 0.6}},
            "rivers": {"beck": {"source": "north", "mouth": [1000, 0]}}}


def test_a_spec_of_known_keys_has_nothing_to_say():
    assert terrain.unnamed_keys(_spec()) == []


def test_a_typo_in_an_entry_is_said_with_the_key_that_was_meant():
    s = _spec()
    s["peaks"]["north"]["raduis"] = 300
    s["sites"][0]["shoulderr"] = 5
    s["cover"]["wood"]["_note"] = "private keys (a leading underscore) are the writer's own"
    lines = terrain.unnamed_keys(s)
    assert len(lines) == 2
    assert lines[0].startswith("peaks 'north': key 'raduis' is named nowhere in the terrain code, so it is IGNORED (did you mean 'radius'?)")
    assert "Usual keys here: at, h, radius" in lines[0]
    assert lines[1].startswith("sites 'hut': key 'shoulderr'") and "(did you mean 'shoulder'?)" in lines[1]


def test_a_mistyped_section_is_said_too_and_rivers_keep_their_own_check():
    s = _spec()
    s["peeks"] = {"south": {"at": [500, 300], "h": 700}}
    s["rivers"]["beck"]["fallz"] = [0.5]  # (terrain_skeleton warns about a river's unknown key against RIVER_KEYS)
    lines = terrain.unnamed_keys(s)
    assert len(lines) == 1 and lines[0].startswith("the terrain spec: key 'peeks' is named nowhere") and "'peaks'" in lines[0]


def test_every_hint_is_a_word_the_code_names_and_every_section_has_hints():
    """The hints decide nothing, but a hint the code never names would send an agent to a key that is ignored too."""
    words = terrain.code_words()
    assert len(words) > 5000 and "raduis" not in words and "peeks" not in words
    for sec, hints in terrain.KEY_HINTS.items():
        assert not [k for k in hints if k not in words], sec
    assert set(terrain.KEY_HINTS) - {""} == set(terrain.NAMED) - {"rivers"}
    assert terrain.RIVER_KEYS <= words


def test_the_report_carries_the_lines():
    src = (ROOT / "src/hifipushie/terrain_tools.py").read_text()
    i = src.index("def report(name: str)")
    j = src.find("\ndef ", i + 10)
    body = src[i:j if j > 0 else len(src)]
    assert "terrain.unnamed_keys(load(name))" in body and body.index("unnamed_keys") < body.index("T.report()")
