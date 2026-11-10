"""FIND ROUTE: which domain a job is in, and what find_tool's answer leads with (C400).

Why: find_tool took the domain from its single best word match and put that domain's workflow steps on top. A job
outside every workflow ("pose the character with an arm raised", "judge the result") matched a word somewhere in a
garment tool's long text and came back as the five garment steps, the tool that did match pushed off the list.
"compare my model to the reference picture" came back as five hair tools. A domain without a workflow had no first
tool ("make a tree" led with plant_form). Measured on tests/test_find_jobs.py's plain jobs: 21 of 35 found.

The rule, the same for every domain:
- A domain says what it makes: its `subject` words in server.TOOL_GROUPS. A job is in the domain whose subject words
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
"""
from __future__ import annotations

WEAK = ('no tool is named for this job: guide() has the "Which path" table (a creature or a prop is a spec, put_model; '
        "people, hair, clothes, terrain and plants have their own tools). Passing word matches follow.")


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


def route(q: set, verb: str, scores: dict, raw: dict, groups: dict, group_of, named, strong, words) -> tuple:
    """(the job's domain or None, tools in the answer's order, note). scores: the word match after the domains' pins; raw: before
    them; named(tool) / strong(tool): the words of its name / of its name, purpose sentence and keywords."""
    for_job = {t for t in scores if scores[t] > 0 and q & strong(t)}
    by_score = sorted((t for t in scores if scores[t] > 0), key=lambda t: (t not in for_job, -scores[t], t))
    pinned = sorted((t for t in by_score if scores[t] > raw.get(t, 0.0)), key=lambda t: -scores[t])[:1]
    subj = subjects(groups, words)
    g = subject_of(q, subj)
    if g is None:
        if by_score and not pinned and not for_job:
            return None, _once(["guide"] + by_score), WEAK
        return None, _once(pinned + by_score), ""
    mine = [t for t in by_score if group_of(t) == g]
    asked = [t for t in mine if verb and verb not in subj[g] and verb in named(t)][:1]
    rest = [t for t in by_score if group_of(t) != g]
    return g, _once(pinned + asked + first_steps(groups[g]) + mine + rest), ""
