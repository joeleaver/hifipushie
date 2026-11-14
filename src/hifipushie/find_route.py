"""FIND ROUTE: which domain a job is in, and what find_tool's answer leads with (C400).

Why: find_tool took the domain from its single best word match and put that domain's workflow steps on top. A job
outside every workflow ("pose the character with an arm raised", "judge the result") matched a word somewhere in a
garment tool's long text and came back as the five garment steps, the tool that did match pushed off the list.
"compare my model to the reference picture" came back as five hair tools. A domain without a workflow had no first
tool ("make a tree" led with plant_form). Measured on tests/test_find_jobs.py's plain jobs: 21 of 35 found.

The rule, the same for every domain:
- A domain says what it makes: its `subject` words in mcp_app.TOOL_GROUPS. A job is in the domain whose subject words
  it uses; two domains with as many each is no domain. Nothing is read off the scores.
- In a domain the answer leads with the tool the job's verb names ("look at the garment" -> look_chain: the job's
  first word, when it isn't a subject word, matched on tool NAMES only: a purpose sentence that says "fit or drape"
  must not jump the build ahead of the plan), then the domain's steps in order (`steps`, or its one `entry` tool),
  then the domain's other matches, then every other match.
- A tool that is FOR the job (a word of the job in its name, purpose sentence or keywords) comes before every tool
  that only mentions the job's words in its notes, whatever their scores: three passing mentions (export_garment's
  bend check: "arm", "raised", "posed") outscored the one tool that poses (rig).
- In no domain: the word matches in that order, no workflow. When no tool is for the job ("make a chair" matched only
  a mention in `check`), the playbook leads: its "Which path" table is where an unknown subject starts.
- A domain's own pin still leads (head_route.pin_block_in, skin_route.find_bias): a tool they scored above its match.
- "Make / build / model / sculpt / create a <thing>" in no domain is the modeller's job: put_model and the playbook lead,
  the word matches follow (C436). KEYWORDS: plain words for a job that a tool's own name and purpose do not carry.
"""
from __future__ import annotations

WEAK = ('no tool is named for this job: guide() has the "Which path" table (a creature or a prop is a spec, put_model; '
        "people, hair, clothes, terrain and plants have their own tools). Passing word matches follow.")


MAKE = ('no domain makes this by name: a creature, a character or a prop is a spec (put_model; guide() has the "Which path" '
        'table, guide(topic="props") the hard-surface forms). A person, hair, clothes, terrain and plants have their own '
        "tools. Word matches follow.")

# Plain words for a job that a tool's name and first sentence do not carry. Each is a miss measured on freshly worded
# jobs (2026-11-12: 33 of 49 found, tests/test_find_jobs.py FRESH); kept specific, since a keyword makes its tool
# "for the job" ahead of every passing mention. The head route keeps its own (head_route.KEYWORDS).
KEYWORDS = {
    "check": "problems faults errors",
    "get_model": "spec json saved show",
    "edit_model": "longer shorter taller thicker thinner wider narrower resize",
    "style_check": "art style stylised stylized",
    "export_asset": "lod lods lower detail distance bake textures",
    "human": "person man woman old young",
    "fit_human": "taller broader slimmer heavier",
    "set_expression": "eyebrow eyebrows frown wink",
    "reference_brief": "photos needed shots",
    "lid_read": "eyelid eyelids",
}


SAME_VERB = {"render": "look", "view": "look", "see": "look", "preview": "look"}  # ("render the hair" asks for look_hair)
# "export the dressed character": the whole character's export, not a garment's (pin_dressed_export)
OUT_WORDS = {"export", "glb", "fbx", "file"}
WHOLE_WORDS = {"character", "person", "figure", "npc", "hero", "body", "model"}
WORN_WORDS = {"dressed", "clothed", "clothes", "clothing", "outfit", "garments", "wearing"}


def pin_dressed_export(query: str, scores: dict) -> dict:
    """The CHARACTER with its clothes out as a file is export_asset's job: an out word + a whole-character word + a
    worn word pins it. The clothes' subject words made it a clothes job, and export_garment (one garment's file, a
    step before) led with the pattern steps behind it. "export the shirt" names no character and stays the garment's."""
    import re
    w = set(re.findall(r"[a-z]+", query.lower()))
    if w & OUT_WORDS and w & WHOLE_WORDS and w & WORN_WORDS and scores:
        return {**scores, "export_asset": 1.01 * max(scores.values()) + 1.0}
    return scores


def subjects(groups: dict, words) -> dict[str, set]:
    """Each domain's subject words as stems: a string is split and stemmed by `words`, a set is stems already."""
    return {g: (words(s["subject"]) if isinstance(s["subject"], str) else set(s["subject"]))
            for g, s in groups.items() if s.get("subject")}


def subject_of(q: set, subj: dict) -> str | None:
    """The one domain whose subject words the job uses most; None for no domain or a tie."""
    votes = {g: len(q & s) for g, s in subj.items() if q & s}
    top = [g for g, v in votes.items() if v == max(votes.values())]
    return top[0] if len(top) == 1 else None


def first_steps(group: dict) -> list:
    return list(group.get("steps") or ([group["entry"]] if group.get("entry") else []))


def _once(tools: list) -> list:
    return list(dict.fromkeys(tools))


def route(q: set, verb: str, scores: dict, raw: dict, groups: dict, group_of, named, strong, words,
          making: bool = False) -> tuple:
    """(the job's domain or None, tools in the answer's order, note). scores: the word match after the domains' pins; raw: before
    them; named(tool) / strong(tool): the words of its name / of its name, purpose sentence and keywords."""
    for_job = {t for t in scores if scores[t] > 0 and q & strong(t)}
    by_score = sorted((t for t in scores if scores[t] > 0), key=lambda t: (t not in for_job, -scores[t], t))
    pinned = sorted((t for t in by_score if scores[t] > raw.get(t, 0.0)), key=lambda t: -scores[t])[:1]
    subj = subjects(groups, words)
    g = subject_of(q, subj)
    if g is None:
        if making and not pinned:  # "make a <thing>" that no domain names is the modeller's, whatever its stray words
            # match ("make a stylised owl from this picture" came back as three hair tools: "picture")
            return None, _once(["put_model", "guide"] + by_score), MAKE
        if by_score and not pinned and not for_job:
            return None, _once(["guide"] + by_score), WEAK
        return None, _once(pinned + by_score), ""
    mine = [t for t in by_score if group_of(t) == g]
    asked = [t for t in mine if verb and verb not in subj[g] and {verb, SAME_VERB.get(verb, verb)} & named(t)][:1]
    rest = [t for t in by_score if group_of(t) != g]
    return g, _once(pinned + asked + first_steps(groups[g]) + mine + rest), ""
