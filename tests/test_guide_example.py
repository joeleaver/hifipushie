"""guide(topic="example"): two whole specs an agent can reach and build (the area re-review: no worked example; the
fox was in examples/, which no guide named and no tool loads)."""
import json
import re
from pathlib import Path

from hifipushie import server, spec_keys, store

ROOT = Path(__file__).resolve().parent.parent


def _specs():
    text = server.guide("example")
    return text, [json.loads(b) for b in re.findall(r"```json\n(.*?)\n```", text, re.S)]


def test_the_topic_returns_two_specs_that_validate_as_written():
    text, specs = _specs()
    assert len(specs) == 2 and len(text) < 6000 and "put_model(name, <the spec>)" in text
    for s in specs:
        assert spec_keys.unknown(s) == []
        store.validate(s)  # (every check a spec passes before it is saved: it compiles)
    assert server.guide("examples") == text


def test_the_specs_are_the_examples_files_so_neither_drifts():
    _, (fox, chair) = _specs()
    assert fox == json.loads((ROOT / "examples/fox.json").read_text())
    assert chair == json.loads((ROOT / "examples/chair.json").read_text())
    assert len(fox["joints"]) == 17 and len(chair["bones"]) == 3  # (the counts the headings give)


def test_an_agent_is_told_the_topic_exists():
    assert '"example"' in server.guide.__doc__
    assert 'guide(topic="example")' in server.guide("put_model") and "`example`" in server.guide("")
