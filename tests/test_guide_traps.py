"""guide(topic="traps") and "gates" are short, packaged and written for an agent (the area re-review: every agent
was sent to the developer's own notes, 13k and 20k characters about machines and past rounds, absent from an install)."""
import re
from pathlib import Path

import pytest

from hifipushie import mcp_app, server, tools_find


@pytest.mark.parametrize("topic, head, most", [("traps", "# Traps", 4500), ("gates", "# Gates", 2600)])
def test_the_topic_is_packaged_short_and_about_the_tools(topic, head, most):
    f = tools_find.GUIDE_TOPICS[topic]
    assert not f.startswith("docs/") and Path(tools_find.__file__).with_name(f).exists()
    text = server.guide(topic)
    assert text.startswith(head) and len(text) < most
    for word in ("Garrett", "Tess", "NICO", "/mnt/", "bin/", "workspace/", "docs/notes"):  # (the developer's world)
        assert word not in text, word
    named = set(re.findall(r"`([a-z_]+)`", text))
    assert named and not [t for t in named if t not in mcp_app._TOOLS and t != "layer"], named
    for t in re.findall(r'guide\(topic="(\w+)"\)', text):
        assert t in tools_find.GUIDE_TOPICS, t


def test_the_two_topics_point_at_each_other_and_say_who_approves():
    traps, gates = server.guide("traps"), server.guide("gates")
    assert 'guide(topic="gates")' in traps and 'guide(topic="traps")' in gates
    assert all(s in gates for s in ("DESCRIBE", "MEASURE", "LOOK", "APPROVE", "`review_view`", "a person does this"))
    assert "REFUSE an unknown" in traps and "WARNING" in traps  # (what the tools now say about a key that does nothing)


def test_the_guide_tool_names_the_modellers_own_topics():
    doc = server.guide.__doc__
    for topic in ("spec", "blockout", "props", "looking", "style", "story", "paint", "example", "traps", "gates"):
        assert f'"{topic}"' in doc and topic in tools_find.GUIDE_TOPICS, topic
