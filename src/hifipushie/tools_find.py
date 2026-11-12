"""Finding and running tools: guide (the playbook, a domain's topic, a tool's section), find_tool (a job in plain
words -> the tool, its parameters and an example call; routing in find_route.py) and call_tool."""
from __future__ import annotations

import json
import re
from pathlib import Path

from mcp.server.mcpserver import Context

from . import find_route, skin_route
from .mcp_app import CORE, TOOL_GROUPS, _FUNCS, _TOOLS, mcp
from .tool_common import REPO

@mcp.tool(structured_output=False)
def guide(topic: str = "") -> str:
    """The playbook and reference. topic "" = modelling playbook (read before modelling); a domain: "hair", "cloth",
    "skin", "human", "block_in", "gnm_driving" (a difference you see -> the GNM control),
    "likeness", "terrain", "vegetation", "clutter", "tools" (core tools' reference), "traps" (symptom -> real
    cause), "gates" (describe, measure, look, approve), "tailoring"; or any tool's name (or "tool:<name>") for that tool's full parameters and behaviour. Details: guide(topic="guide")."""
    t = topic.strip().lower()
    if t.startswith("tool:"):  # always a tool's section, even where a topic has the tool's name (skin, human, likeness)
        return _tool_section(topic.strip()[5:].strip())
    if t in GUIDE_TOPICS:
        p = _topic_path(GUIDE_TOPICS[t])
        if not p.exists():
            return (f"guide topic {t!r}: {GUIDE_TOPICS[t]} is not in this checkout (an installed package without "
                    "the repo's docs/)" + (" -- guide(topic=\"cloth_design\") has the tailoring numbers"
                                           if "tailoring" in t else ""))
        txt = p.read_text()
        if t == "cloth":
            txt = _CHAIN_GUIDE + "\n\n" + txt
        return txt
    if topic.strip() in _TOOLS:
        return _tool_section(topic.strip())
    raise ValueError('topic is "" (the modelling playbook), a domain ("' + '", "'.join(k for k in GUIDE_TOPICS if k)
                     + '") or a tool\'s name')


_CHAIN_GUIDE = """# Clothes: the one path

garment_plan (read, parts, style) -> body_tape -> draft_pattern -> chain_garment -> garment_details -> look_chain -> export_garment. There is no other way to start a garment. Every edge, seam,
hem, fold and roll line is a chain at its exact cut length, sewn points are one node, and only bends are free: stiff parts
(band, collar, cuffs, plackets) are built first from the pattern's interfacing and hold their own shape; the soft cloth
hangs from them under gravity; lengths have the last word. Your choices are the DESIGN (the pattern) and the WEAR ("closed",
"open", how far an open collar opens). Nothing else is a setting. A fault is fixed in your draft (draft_pattern, which runs the
flat gate), then chain_garment again. If a length can't hold the tool names the piece and the line.
Judge with look_chain: the whole figure, focus="neck" for the collar close, a piece's name for that piece alone, four sides,
with reference= beside every view; review_view one view per call."""


# guide topics -> files; each domain file ends with "## Tool reference": a "### `tool`" section per tool
GUIDE_TOPICS = {"": "guide.md", "tools": "tools_guide.md", "hair": "hair_guide.md", "cloth": "cloth_guide.md",
                "skin": "skin_guide.md", "human": "human_guide.md", "humans": "human_guide.md",
                "block_in": "blockin_guide.md", "blockin": "blockin_guide.md", "block-in": "blockin_guide.md",
                "likeness": "likeness_guide.md", "terrain": "terrain_guide.md", "vegetation": "vegetation_guide.md",
                "clutter": "clutter_guide.md", "gnm_driving": "gnm_driving_guide.md", "driving": "gnm_driving_guide.md",
                "hair_locks": "hair_locks_guide.md", "hair_background": "hair_background.md",
                "cloth_background": "cloth_background.md", "cloth_tools": "cloth_tools.md",
                "cloth_design": "cloth_design.md", "cloth_construction": "cloth_construction.md",
                "cloth_sim": "cloth_sim.md", "cloth_faults": "cloth_faults.md", "cloth_blocks": "cloth_blocks.md",
                "vegetation_spec": "vegetation_spec.md", "vegetation_styles": "vegetation_styles.md",
                "vegetation_forest": "vegetation_forest.md", "vegetation_small": "vegetation_small.md",
                "vegetation_export": "vegetation_export.md", "vegetation_tools": "vegetation_tools.md",
                "hair_checklist": "hair_checklist.md", "hair_tied": "hair_tied.md", "hair_loose": "hair_loose.md",
                "hair_short": "hair_short.md", "hair_colour": "hair_colour.md", "hair_color": "hair_colour.md",
                "hair_export": "hair_export.md", "hair_tools": "hair_tools.md", "hair_locks_detail": "hair_locks_detail.md",
                "skin_layers": "skin_layers.md", "skin_tools": "skin_tools.md",
                "blockin_solve": "blockin_solve.md", "blockin_steps": "blockin_steps.md",
                "blockin_features": "blockin_features.md", "blockin_tools": "blockin_tools.md",
                "spec": "guide_spec.md", "looking": "guide_looking.md", "blockout": "guide_blockout.md",
                "strokes": "guide_blockout.md", "parts": "guide_blockout.md", "props": "guide_props.md",
                "style": "guide_style.md", "story": "guide_story.md", "paint": "guide_paint.md",
                "game_export": "guide_export.md", "rigging": "guide_rigging.md",
                "human_shape": "human_shape.md", "human_tools": "human_tools.md",
                "likeness_reading": "likeness_reading.md", "likeness_profile": "likeness_profile.md",
                "likeness_references": "likeness_references.md", "likeness_tools": "likeness_tools.md",
                "terrain_world": "terrain_world.md", "terrain_shapes": "terrain_shapes.md",
                "terrain_places": "terrain_places.md", "terrain_streams": "terrain_streams.md",
                "terrain_styles": "terrain_styles.md", "terrain_running": "terrain_running.md",
                "terrain_tools": "terrain_tools.md",
                # repo docs (a source checkout): the rules the tools enforce, and their history
                "traps": "docs/notes/traps.md", "gates": "docs/notes/gates.md",
                "tailoring": "docs/notes/tailoring_principles.md",
                "tailoring_principles": "docs/notes/tailoring_principles.md"}


def _topic_path(f: str) -> Path:
    """A guide topic's file: package files by name, "docs/..." from the source checkout (REPO)."""
    return REPO / f if f.startswith("docs/") else Path(__file__).with_name(f)


def _tool_section(name: str) -> str:
    """A tool's full documentation: its "### `name`" section in whichever guide topic holds it."""
    head = f"### `{name}`"
    for f in dict.fromkeys(GUIDE_TOPICS.values()):
        if f.startswith("docs/"):
            continue  # (repo notes hold no tool sections)
        lines = Path(__file__).with_name(f).read_text().split("\n")
        if head in lines:
            i = lines.index(head)
            j = next((k for k in range(i + 1, len(lines)) if lines[k].startswith(("### ", "## "))), len(lines))
            return "\n".join(lines[i:j]).strip() + f"\n\n(from guide topic {f})"
    raise ValueError(f"no reference section for tool {name!r}")


_STOP = set("a an the to of in on for and or with my it its is are be i we you want need how do does can from by "
             "into at as this that some me make new one any".split()
         # every tool works on a model / character: those words say nothing about which tool (C-row, find_tool)
         + "model character creature thing tool".split()
         # the verb every job starts with says nothing either ("start a human" led with block_in_START: C400)
         + "start begin create build add give".split())


def _stem(w: str) -> str:
    for suf in ("ing", "es", "ed", "s"):
        if w.endswith(suf) and len(w) > len(suf) + 2 and not (suf == "s" and w.endswith("ss")):
            w = w[:-len(suf)]
            break
    # one stem for "silhouette" / "silhouettes", "tree" / "trees", "pose" / "posing": the plural lost its e, the
    # singular kept it, so "a tree" never met a tool that said "trees" (C400)
    return w[:-1] if w.endswith("e") and len(w) > 3 else w


def _words(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 1}


def _group_of(name: str) -> str:
    return next((g for g, s in TOOL_GROUPS.items() if name in s["tools"]), "other")


def _first_sentence(name: str) -> str:
    import inspect
    doc = " ".join(inspect.cleandoc(getattr(_FUNCS.get(name), "__doc__", None) or "").split())
    m = re.match(r"(.+?[.!?])(\s|$)", doc)
    return m.group(1) if m else doc


def _use_when(name: str) -> str:
    """A tool's first sentence: what it is for."""
    first = _first_sentence(name)
    return first if len(first) <= 220 else first[:217] + "..."


def _purpose(name: str) -> set[str]:
    """The words of what a tool is FOR: its first sentence without its brackets (asides, argument lists), 220
    characters of it. They count as much as its name; what its notes mention in passing counts half (C400)."""
    first = _first_sentence(name)
    for _ in range(3):
        first = re.sub(r"\([^()]*\)", " ", first)
    return _words(first[:220])


_MAKING = re.compile(r"\s*(?:please\s+)?(?:make|build|model|sculpt|create|design)\s+(?:me\s+)?(?:a|an|some|one|two)\s+\w", re.I)


def _verb(query: str) -> str:
    """The job's first word that says something: its verb in "look at the garment"."""
    return next((_stem(w) for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in _STOP and len(w) > 1), "")


def _guide_topics() -> dict[str, str]:
    """stem -> the one-word guide topic of that name, for topics that name no tool (props, paint, story ...): the
    guide is found by them and its example call names the topic."""
    names = set().union(*(_words(t.replace("_", " ")) for t in _TOOLS))
    out: dict[str, str] = {}
    for k in GUIDE_TOPICS:
        w = _words(k)
        if k.isalpha() and len(w) == 1 and not w & names:
            out.setdefault(next(iter(w)), k)
    return out


def _params(name: str) -> list[tuple[str, str, bool, str]]:
    """(name, type text, required, default text) for each of a tool's arguments (ctx left out)."""
    import inspect
    out = []
    for p in inspect.signature(_FUNCS[name]).parameters.values():
        if p.name == "ctx":
            continue
        ann = p.annotation if isinstance(p.annotation, str) else getattr(p.annotation, "__name__", str(p.annotation))
        ann = "" if p.annotation is inspect.Parameter.empty else ann
        req = p.default is inspect.Parameter.empty
        out.append((p.name, ann, req, "" if req else json.dumps(p.default, default=str)))
    return out


def _param_text(name: str) -> str:
    ps = _params(name)
    if not ps:
        return "(no arguments)"
    return ", ".join(f"{n}: {a or 'any'}" + ("" if req else f" = {d}") for n, a, req, d in ps)


def _example(name: str) -> str:
    def ph(n, a):
        a = a.split("|")[0].strip()
        return {"int": 0, "float": 0.0, "bool": False}.get(a, [] if a.startswith("list") else
                                                            {} if a.startswith("dict") else "...")
    req = {n: ph(n, a) for n, a, r, _ in _params(name) if r}
    if name in CORE:
        return f"{name}(" + ", ".join(f"{k}={json.dumps(v)}" for k, v in req.items()) + ")"
    return f'call_tool(name="{name}", args={json.dumps(req)})'


_SECTIONS: dict[str, str] = {}


def _section_text(name: str) -> str:
    if name not in _SECTIONS:
        try:
            _SECTIONS[name] = _tool_section(name)
        except ValueError:
            _SECTIONS[name] = ""
    return _SECTIONS[name]


_FIELDS: dict[str, list] = {}


def _tool_fields(name: str) -> list[tuple[float, set[str]]]:
    """A tool's searchable words by field, with each field's weight: name 4, description 2, domain 1, guide 1,
    keywords 4 (the guide's: its topics), purpose 4."""
    import inspect
    from . import head_route
    if name not in _FIELDS:
        g = _group_of(name)
        _FIELDS[name] = [(4.0, _words(name.replace("_", " "))),
                         (2.0, _words(inspect.cleandoc(_FUNCS[name].__doc__ or ""))),
                         (1.0, _words(g + " " + TOOL_GROUPS.get(g, {}).get("about", ""))),
                         (1.0, _words(_section_text(name))),
                         (4.0, _words(head_route.KEYWORDS.get(name, "") + " " + find_route.KEYWORDS.get(name, "")
                                      + (" " + " ".join(_guide_topics()) if name == "guide" else ""))),
                         (4.0, _purpose(name))]
    return _FIELDS[name]


def _tool_scores(q: set[str]) -> dict[str, float]:
    """Word match of the query on every tool: per query word, the best field it appears in (+0.5 if in both the
    description and the guide section), times the word's rarity across tools (idf: "hoodie" outweighs
    "character"). Deterministic, no model."""
    import math
    tools = [t for t in _TOOLS if t != "find_tool"]
    union = {t: set().union(*(ws for _, ws in _tool_fields(t))) for t in tools}
    out = {}
    for t in tools:
        f = _tool_fields(t)
        score = 0.0
        for w in q:
            hits = [wt for wt, ws in f if w in ws]
            if hits:
                df = sum(w in u for u in union.values())
                score += (max(hits) + (0.5 if w in f[1][1] and w in f[3][1] else 0.0)) * math.log((len(tools) + 1) / (df + 0.5))
        out[t] = score
    return out


@mcp.tool(structured_output=False)
def find_tool(query: str = "", limit: int = 5) -> str:
    """Find the tool for a job: ranks every hifipushie tool (native or not) by word match on its name and docs, and
    gives each one's purpose, parameters and an example call (non-core tools run through call_tool). query: what you
    want to do, e.g. "fit a garment" ("" lists every tool by domain); limit: how many. The order of the answer:
    guide(topic="find_tool")."""
    if not query.strip():
        groups = [(g, s["about"], [t for t in s["tools"] if t in _TOOLS]) for g, s in TOOL_GROUPS.items()]
        rest = sorted(t for t in _TOOLS if _group_of(t) == "other")
        if rest:
            groups.append(("other", "not in a domain yet", rest))
        return ("Every tool by domain (core = native; the rest via call_tool(name, args)). "
                "find_tool(\"<job>\") gives parameters + an example call; guide(topic=\"<tool>\") the full text.\n"
                + "\n".join(f"{g} ({about}): {', '.join(ts)}" for g, about, ts in groups if ts))
    from . import head_route
    q = _words(query.lower().replace("make-up", "makeup").replace("make up", "makeup"))
    raw = _tool_scores(q)
    scores = head_route.pin_block_in(query, skin_route.find_bias(q, raw))
    # The domain comes from the job's subject words, never from a stray word match; in a domain its steps lead in
    # order (the process, not a shortcut), outside one the word matches stand as they are (find_route.py, C400).
    g, order, note = find_route.route(q, _verb(query), scores, raw, TOOL_GROUPS, _group_of,
                                      lambda t: _tool_fields(t)[0][1],
                                      lambda t: set().union(*(ws for wt, ws in _tool_fields(t) if wt >= 4)), _words,
                                      making=bool(_MAKING.match(query)))
    named = query.strip().lower().replace(" ", "_")  # a query that IS a tool's name gets that tool first
    if named in _TOOLS and named != "find_tool":
        order = [named] + [t for t in order if t != named]
    order = [t for t in order if t in _TOOLS][:max(1, int(limit))]
    if not order:
        return (f"no tool matches {query!r}: guide() has the \"Which path\" table; find_tool(\"\") lists every tool "
                "by domain.")
    flow = TOOL_GROUPS[g]["workflow"] + f' (guide(topic="{g}")).\n' if g and TOOL_GROUPS[g].get("workflow") else ""
    topic = next((k for w, k in _guide_topics().items() if w in q), None)
    out = []
    for i, t in enumerate(order, 1):
        how = "native" if t in CORE else "via call_tool"
        eg = f'guide(topic="{topic}")' if t == "guide" and topic else _example(t)
        out.append(f"{i}. {t} [{_group_of(t)}, {how}] use when: {_use_when(t)}\n"
                   f"   params: {_param_text(t)}\n   e.g. {eg}")
    return (flow + (note + "\n" if note else "") + "\n".join(out)
            + '\nnext: run the best match (non-core: call_tool(name, args)); guide(topic="<tool>") '
            "has its full parameters and behaviour.")


_CALL_TOOLS: dict[str, object] = {}  # name -> the SDK Tool built for a non-native tool (validation + context)


def _tool_obj(name: str):
    """The SDK Tool for `name`: the native one, or one built once from the same wrapped function."""
    t = mcp._tool_manager._tools.get(name)
    if t is None:
        if name not in _CALL_TOOLS:
            from mcp.server.mcpserver.tools import Tool
            _CALL_TOOLS[name] = Tool.from_function(_TOOLS[name][1], name=name, structured_output=False)
        t = _CALL_TOOLS[name]
    return t


@mcp.tool(structured_output=False)
async def call_tool(name: str, args: dict | None = None, ctx: Context | None = None):
    """Run any hifipushie tool by name, native or not, exactly as a native call (images included). args: that tool's
    arguments as an object. find_tool("<job>") names the tool, its parameters and an example call; guide(topic=<tool>)
    has its full text. Unknown, missing or mistyped args: an error naming the parameters it expects."""
    import difflib
    from pydantic import ValidationError
    if name not in _TOOLS or name == "call_tool":
        near = difflib.get_close_matches(name, list(_TOOLS), n=3)
        raise ValueError(f"no tool {name!r}" + (f" (did you mean {', '.join(near)}?)" if near else "")
                         + f'; find_tool("{name.replace("_", " ")}") searches every tool')
    args = dict(args or {})
    expected = f"{name} expects: {_param_text(name)}"
    names = {p[0] for p in _params(name)}
    unknown = sorted(set(args) - names)
    missing = [p[0] for p in _params(name) if p[2] and p[0] not in args]
    if unknown or missing:
        raise ValueError(f"call_tool({name!r}): " + "; ".join(
            ([f"unknown argument(s) {', '.join(unknown)}"] if unknown else [])
            + ([f"missing required {', '.join(missing)}"] if missing else [])) + f". {expected}")
    tool = _tool_obj(name)
    try:
        tool.fn_metadata.validate_arguments(args)
    except ValidationError as e:
        bad = "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors())
        raise ValueError(f"call_tool({name!r}): bad argument(s): {bad}. {expected}") from None
    return await tool.run(args, ctx)
