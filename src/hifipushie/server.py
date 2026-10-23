"""hifipushie MCP server: skeleton-and-blob creature modeling with clay-render feedback."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
from pathlib import Path

import numpy as np
from mcp.server.mcpserver import Context, Image, MCPServer
from PIL import Image as PILImage

from . import compare as cmp
from . import fit as fitmod
from . import measure as meas
from . import paint as paintmod
from . import plan as planmod
from . import render, store, surface
from .spec import empty_spec, summarize

INSTRUCTIONS = """\
hifipushie models characters, creatures, props and environments as a skeleton (joints + bones) with SDF blobs hung
on it, smooth-blended into one surface, meshed and rendered for you to look at; hair, cloth, realistic humans,
terrain, plants and clutter have their own tools.
Call `guide` once before modelling: the playbook (stages, the spec format, strokes, parts, paint, what goes wrong).
guide(topic="tools") lists the toolsets; guide(topic=<tool name>) gives any tool's full parameters.

Conventions: metres, Blender axes: Z up, the creature FACES -Y, its left side is +X. Names ending ".L" are mirrored
to ".R" across X: store only the centre line and the left side.
Spec keys (every field in the guide and kit_reference): joints {name: {pos, r}}, bones {name: {a, b, r_a, r_b, ...}}
(round cones), blobs {name: {at, size, rot, offset, shape, ...}} (ellipsoids, blades), kits (hand, face, foot),
anatomy, parts, strokes (sculpting on the surface), paint (colour layers and masks), prefabs/instances, story and
weather, plan, base (realistic humans start here, not from blobs), hair, cloth, skin.
Workflow: plan (set_plan) -> blockout (put_model, fit) -> secondary forms (strokes) -> detail -> history (story) ->
paint; check and look after each stage. Every change is checkpointed (history / revert).

Toolsets: the core is always on; enable_toolset(name) adds one of plan, scene, export, human, likeness, hair,
cloth, terrain, plants, clutter (enable_toolset("") lists them and what is on). Domains have a guide topic (hair,
cloth, cloth_reference, skin, human, block_in, likeness, terrain, vegetation, clutter): read it before working there.
A person's head from pictures: the artist block-in (guide topic block_in) is the default.
Clothes come from the pattern: design -> pattern_check (the flat gate; sims refuse without its PASS) -> fit_garment
(on the form, no sim) -> judge clay + diag beside the reference -> a sim only as a wrinkle source -> game mesh. Never
tune the solver, never close or hand-finish after a sim (measured: strain p99 4.7 % -> 66-74 %).
Judge every result beside its reference before forwarding it; reviews are review_view, ONE view per call. Tool texts
end with "next:": do what it says. Traps: guide(topic="traps"). Terrain tools may return questions for the designer:
ask them, don't answer them yourself.
"""

mcp = MCPServer("hifipushie", instructions=INSTRUCTIONS)


def _error_text(e: BaseException) -> str:
    """What the caller needs to fix a failed call: the exception's type and message, and for anything that
    isn't a ValueError (our anticipated spec/argument errors) where it was raised."""
    text = f"{type(e).__name__}: {e}"
    if not isinstance(e, ValueError):
        import traceback
        tb = traceback.extract_tb(e.__traceback__)
        if tb:
            f = tb[-1]
            text += f" (at {Path(f.filename).name}:{f.lineno} in {f.name})"
    return text


_MCP_TOOL = mcp.tool  # the SDK's own decorator (mcp.tool is replaced below)


def _tool_with_errors(_reg=None):
    """mcp.tool, but a tool's exception reaches the caller as its text. The SDK turns anything but ToolError
    into a bare "Error executing tool x", which left agents bisecting op batches to find a SpecError."""
    import functools
    import inspect
    from mcp.server.mcpserver.exceptions import ToolError

    def tool(*args, **kw):
        register = (_reg or _MCP_TOOL)(*args, **kw)

        def deco(fn):
            if inspect.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def run(*a, **k):
                    try:
                        return await fn(*a, **k)
                    except ToolError:
                        raise
                    except Exception as e:
                        raise ToolError(_error_text(e)) from e
            else:
                def call(ev, a, k):
                    from . import resources
                    with resources.cancel_scope(ev):
                        try:
                            return fn(*a, **k)
                        except ToolError:
                            raise
                        except Exception as e:
                            raise ToolError(_error_text(e)) from e

                # A sync tool runs on a worker thread under a cancel event: when the call is cancelled or the client
                # goes away, the event is set and the tool's heavy job stops and releases its memory grant
                # (`resources.cancel_scope`); before, the thread ran on and held the machine's slot for an hour.
                @functools.wraps(fn)
                async def run(*a, **k):
                    import threading
                    import anyio.to_thread
                    ev = threading.Event()
                    try:
                        return await anyio.to_thread.run_sync(call, ev, a, k, abandon_on_cancel=True)
                    finally:
                        ev.set()  # (after a normal return the thread is done: a no-op)
            if _reg is not None:  # another registry (tests): registered at once, as before toolsets
                register(run)
                return fn
            # Registered later, by toolset (`_register_toolsets` / enable_toolset): the server starts with the core.
            _TOOLS[fn.__name__] = (register, run)
            if _STARTED:  # a tool defined after start-up (a plugin module, a test's extra tools): on at once
                _register(fn.__name__)
            return fn  # module-level name stays the plain function (tests and scripts call it directly)
        return deco
    return tool


mcp.tool = _tool_with_errors()

# Toolsets: every tool belongs to exactly one. The server registers "core" plus what HIFIPUSHIE_TOOLSETS names
# ("core" (the default), "all", or a comma list like "hair,cloth"); enable_toolset adds a set at run time and sends
# notifications/tools/list_changed. Tool definitions cost context on every turn (75 tools were ~36k tokens).
_TOOLS: dict[str, tuple] = {}  # name -> (register, wrapped coroutine), filled by the decorator
TOOLSETS: dict[str, dict] = {
    "core": {"about": "models, specs, look, check, measure, history, the guide",
             "tools": ["guide", "enable_toolset", "list_models", "get_model", "kit_reference", "put_model",
                       "edit_model", "look", "check", "measure", "history", "revert", "review_view"]},
    "plan": {"about": "plans, reference images, compare, silhouette fit, clearance, style check",
             "tools": ["set_plan", "set_reference", "compare", "fit", "clearance", "style_check"]},
    "scene": {"about": "the Blender scene (sync, pull) and the heavy-job queue",
              "tools": ["sync", "pull", "heavy_status", "heavy_queue"]},
    "export": {"about": "OBJ export, game-ready assets (GLB/FBX, PBR maps), the export rig, judging a GLB",
               "tools": ["export", "export_asset", "rig", "judge_asset"]},
    "human": {"about": "realistic humans: the base body, the artist block-in of a head from pictures (the default), "
                       "measurements, fits, skin",
              "tools": ["human", "measure_human", "fit_human", "nudge_human", "human_reference", "block_in_start",
                        "block_in_look", "block_in_step", "block_in_solve", "block_in_expression", "lid_read", "eye_ruler", "face_ruler", "lip_read", "brow_read", "gnm_controls", "skin",
                        "look_skin", "skin_reference", "skin_from_reference", "skin_project"]},
    "likeness": {"about": "matching a real person's face and look from reference pictures",
                 "tools": ["likeness", "fit_likeness", "likeness_points", "character_read", "project_reference",
                           "texture_from_reference", "reference_brief", "check_references"]},
    "hair": {"about": "hair as curve locks: groom, look, reference, export", "also": ["scene"],
             "tools": ["groom_hair", "tie_hair", "look_hair", "hair_reference", "hair_from_reference", "export_hair"]},
    "cloth": {"about": "garments: design, pattern, the pattern gate, alterations, fit on the form, dress (sim), "
                       "references", "also": ["scene"],
              "tools": ["design_garment", "look_pattern", "alter_pattern", "pattern_check", "fit_garment", "style_garment", "release_garment", "arrange_garment",
                        "check_garment", "dress", "look_cloth", "garment_reference",
                        "garment_from_reference", "check_garment_reference", "garment_reference_brief"]},
    "terrain": {"about": "terrain and game levels (height fields in a level designer's words)",
                "tools": ["set_terrain", "check_terrain", "look_terrain", "export_terrain", "terrain_history"]},
    "plants": {"about": "trees and plants (grown, measured, exported), stands of them, wind",
               "tools": ["grow_plant", "edit_plant", "get_plant", "look_plant", "look_plants", "plant_form",
                         "plant_reference", "export_plant", "wind_plant", "sync_plant", "plant_history",
                         "grow_stand", "look_stand", "export_stand"]},
    "clutter": {"about": "ground clutter kits (rocks, logs, leaves ...) for terrain",
                "tools": ["make_clutter", "look_clutter", "clutter_kit"]},
}
_ENABLED: set[str] = set()
_STARTED = False  # set once the module's tools are registered by toolset


def _compact_schema(s, props: bool = False):
    """A tool's input schema without pydantic's per-field "title"s and `additionalProperties: true`, and with optional
    `X | None` as plain X (an omitted argument is the None default): a third of the schema text, the same arguments.
    Only the advertised schema changes: arguments are still validated by the function's own model (None is fine)."""
    if isinstance(s, list):
        return [_compact_schema(v) for v in s]
    if not isinstance(s, dict):
        return s
    if props:  # {param name: schema}: names are kept, whatever they are
        return {k: _compact_schema(v) for k, v in s.items()}
    out = {k: _compact_schema(v, props=(k in ("properties", "$defs"))) for k, v in s.items()
           if k != "title" and not (k == "additionalProperties" and v is True)}  # (true is JSON schema's default)
    alts = out.get("anyOf")
    if isinstance(alts, list) and {"type": "null"} in alts:
        rest = [a for a in alts if a != {"type": "null"}]
        del out["anyOf"]
        if len(rest) == 1:
            out.update(rest[0])
        else:
            out["anyOf"] = rest
        if "default" in out and out["default"] is None:
            del out["default"]
    return out


def _toolset_names(spec: str) -> list[str]:
    """The toolsets a HIFIPUSHIE_TOOLSETS value names, with their "also"s; "all" = every set."""
    names = [s.strip().lower() for s in (spec or "core").split(",") if s.strip()]
    if "all" in names:
        return list(TOOLSETS)
    out = ["core"]
    for n in names:
        if n not in TOOLSETS:
            raise ValueError(f"no toolset {n!r} (toolsets: {', '.join(TOOLSETS)})")
        for m in [n, *TOOLSETS[n].get("also", [])]:
            if m not in out:
                out.append(m)
    return out


def _register(t: str):
    """Register one tool with the MCP server: its docstring dedented, its schema compacted."""
    import inspect
    register, run = _TOOLS[t]
    register(run)
    tool = mcp._tool_manager._tools[t]
    tool.description = inspect.cleandoc(tool.description)
    tool.parameters = _compact_schema(tool.parameters)


def _enable(names: list[str]) -> list[str]:
    """Register these toolsets' tools; returns the tool names added."""
    added = []
    for n in names:
        if n in _ENABLED:
            continue
        for t in TOOLSETS[n]["tools"]:
            _register(t)
            added.append(t)
        _ENABLED.add(n)
    return added


def enable_all() -> list[str]:
    """Every toolset on (in-process users of the registry: the oxidegen artist and its worker)."""
    return _enable(list(TOOLSETS))


def _register_toolsets():
    """Called once all tools are defined: core + HIFIPUSHIE_TOOLSETS (default core); HIFIPUSHIE_CALL_TOOL=1 adds
    call_tool, for hosts that neither show list_changed tools nor allow a restart with more sets."""
    import os
    global _STARTED
    _enable(_toolset_names(os.environ.get("HIFIPUSHIE_TOOLSETS", "core")))
    if os.environ.get("HIFIPUSHIE_CALL_TOOL", "").strip() not in ("", "0"):
        _register("call_tool")
    in_sets = {t for s in TOOLSETS.values() for t in s["tools"]} | {"call_tool"}
    for t in [t for t in _TOOLS if t not in in_sets]:  # a new tool nobody put in a toolset: on, never lost
        _register(t)
    _STARTED = True


# Advertise tools.listChanged (the SDK's default options say false, and clients may ignore the notification then).
def _init_options(notification_options=None, *a, _orig=mcp._lowlevel_server.create_initialization_options, **k):
    from mcp.server.lowlevel.server import NotificationOptions
    return _orig(notification_options or NotificationOptions(tools_changed=True), *a, **k)


mcp._lowlevel_server.create_initialization_options = _init_options


def _png(im: PILImage.Image) -> Image:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return Image(data=buf.getvalue(), format="png")


def _refs(name: str, views: list[str] | None, against: str = "auto") -> dict:
    """Reference silhouettes by view: {view: (mask, world placement or None)}. against="plan" uses the model's
    plan (placed exactly in world units), "refs" the images from set_reference, "auto" the plan if there is one."""
    plan = store.load(name).get("plan")
    if against == "plan" or (against == "auto" and plan and plan.get("views")):
        if not plan:
            raise ValueError("this model has no plan; use set_plan first")
        views = views or [v for v in ("front", "side", "top") if planmod.bounds(plan, v) is not None]
        return {v: planmod.reference(plan, v) for v in views}
    if against not in ("auto", "refs"):
        raise ValueError('against must be "auto", "plan" or "refs"')
    cfg_p = store.refs_dir(name) / "refs.json"
    cfg = json.loads(cfg_p.read_text()) if cfg_p.exists() else {}
    views = views or list(cfg)
    if not views:
        raise ValueError("no references set; use set_reference first")
    for v in views:
        if v not in cfg:
            raise ValueError(f"no reference for view {v!r}")
    return {v: (cmp.reference_mask(cfg[v]["path"], cfg[v]["flip"], cfg[v]["threshold"]), None) for v in views}


def _sil_parts(spec: dict, only_parts: list[str] | None, hide_parts: list[str] | None) -> frozenset | None:
    """The parts a silhouette counts (check/compare/fit): only_parts, all but hide_parts, else the plan's
    "parts", else every part (None)."""
    if not only_parts and not hide_parts:
        only_parts = (spec.get("plan") or {}).get("parts")
        if not only_parts:
            return None
    from .spec import compile_prims
    have = {p.part for p in compile_prims(spec)}
    for pn in [*(only_parts or []), *(hide_parts or [])]:
        if pn not in have:
            raise ValueError(f"no part {pn!r} (parts: {', '.join(sorted(have))})")
    keep = set(only_parts) if only_parts else set(have)
    keep -= set(hide_parts or [])
    if not keep:
        raise ValueError("no parts left to count in the silhouette")
    return None if keep == have else frozenset(keep)


def _silhouettes(name: str, spec: dict, resolution: int, parts: frozenset | None) -> dict:
    """{view: silhouette} of the whole model (the build's), or of just those parts (evaluated here)."""
    if parts is None:
        store.build(name, resolution)
        return {v: store.silhouette(name, v) for v in ("front", "side", "top")}
    from . import sdf
    from .spec import compile_prims
    return sdf.silhouettes(sdf.evaluate([p for p in compile_prims(spec) if p.part in parts], resolution))


def _parts_note(parts: frozenset | None) -> str:
    return f"silhouettes count parts: {', '.join(sorted(parts))}\n" if parts else ""


def _out(im: PILImage.Image, save: str | None) -> Image:
    """The image for the tool result, also written to `save` (a path) when given."""
    if save:
        path = Path(save).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        im.save(path)
    return _png(im)


def _spec_arg(spec) -> dict:
    return json.loads(spec) if isinstance(spec, str) else spec


@mcp.tool(structured_output=False)
def guide(topic: str = "") -> str:
    """The playbook and reference. topic "" = modelling playbook (read before modelling); a domain: "hair", "cloth",
    "cloth_reference", "skin", "human", "block_in", "gnm_driving" (a difference you see -> the GNM control),
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
        return p.read_text()
    if topic.strip() in _TOOLS:
        return _tool_section(topic.strip())
    raise ValueError('topic is "" (the modelling playbook), a domain ("' + '", "'.join(k for k in GUIDE_TOPICS if k)
                     + '") or a tool\'s name')


# guide topics -> files; each domain file ends with "## Tool reference": a "### `tool`" section per tool
GUIDE_TOPICS = {"": "guide.md", "tools": "tools_guide.md", "hair": "hair_guide.md", "cloth": "cloth_guide.md",
                "cloth_reference": "cloth_reference_guide.md", "cloth reference": "cloth_reference_guide.md",
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


@mcp.tool(structured_output=False)
async def enable_toolset(name: str = "", ctx: Context | None = None) -> str:
    """Add a toolset's tools to this session (the server may start with only the core). name: a toolset or a comma
    list, "all"; "" lists the toolsets, what each holds and which are on. The new tools appear after the client
    refreshes its tool list (notifications/tools/list_changed); if they don't, restart with HIFIPUSHIE_TOOLSETS."""
    if not name.strip():
        return "\n".join(f"{n} ({'on' if n in _ENABLED else 'off'}): {s['about']}. Tools: {', '.join(s['tools'])}"
                         for n, s in TOOLSETS.items())
    sets = _toolset_names(name)
    added = _enable(sets)
    if added and ctx is not None:
        # Both eras: 2026-07-28+ clients get it on their subscriptions/listen stream (the bus); older ones as a
        # plain notification on the session (the SDK drops that one at the modern era).
        await ctx.notify_tools_changed()
        await ctx.session.send_tool_list_changed()
    return (f"enabled {', '.join(sets)}: added {', '.join(added)}" if added
            else f"already enabled: {', '.join(sets)}")


@mcp.tool(structured_output=False)
async def call_tool(name: str, args: dict | None = None):
    """Run any hifipushie tool by name, enabled or not (registered only with HIFIPUSHIE_CALL_TOOL=1, for hosts that
    ignore list_changed). args: that tool's arguments. enable_toolset("") lists the tools; guide(topic=<tool>) has
    each one's parameters."""
    if name not in _TOOLS or name == "call_tool":
        raise ValueError(f"no tool {name!r}")
    return await _TOOLS[name][1](**(args or {}))


@mcp.tool(structured_output=False)
def list_models() -> str:
    """List saved models."""
    return json.dumps(store.list_models())


@mcp.tool(structured_output=False)
def get_model(name: str) -> str:
    """Return a model's stored spec (JSON) plus a measurement summary."""
    spec = store.load(name)
    return summarize(spec) + "\n\n" + json.dumps(spec, indent=1)


SOLIDS = """Hard-surface pieces (blobs): "shape": "box" | "cylinder" (size [rx, ry, half-height], along its local
z; "rot" to turn it) with "round": edge radius; any bone or blob may be "hollow": t (only a wall t thick inside its
surface: pots, cups, pipes, a boat hull). "ends": "flat" on a bone cuts it square at its joints (sawn logs, beams, dowels; {"flat": r} rounds
the edge by r) instead of the round caps. "bow" on a bone: [sideways, up] metres (or one number, up) of sag at
mid-length, a bent log or a sagging beam. "lumpy" on any bone or blob: {"amount": m, "scale": m (8 x amount),
"seed"} noise on the surface itself (knots, axe marks, uneven stone); keep amount well under scale. "chips":
{"depth": m, "scale": m (6 x depth), "amount": 0..1 (0.15), "where": "edges" (default: corners and edges,
where things get knocked) | "all" (dents and gouges anywhere), "seed"} knocks chunks out of the surface:
chipped stone and brick, worn step edges, gouged wood. A subtract or intersect element with "targets": [names or tags] cuts
only those elements (a pot's opening, a window through the wall logs, a drawer's recess) instead of everything
in its part and layer. Walls thinner than ~2 voxels break up at the build resolution: judge them in close-ups."""


@mcp.tool(structured_output=False)
def kit_reference() -> str:
    """Parameters and defaults for the kits (hand, face), strokes, paint, materials, solids/repetition, garments, face
    shapes, realism and plans. Details: guide(topic="kit_reference")."""
    from . import assemble, faceshapes, garments, kits, materials, strokes
    from . import realism
    return ("REALISM\n" + realism.__doc__ + "\n\nREPETITION AND SOLIDS\n" + assemble.__doc__ + "\n" + SOLIDS + "\n\n" + kits.__doc__ + "\n\nGARMENTS\n" + garments.__doc__ + "\n\nSTROKES\n" + strokes.__doc__ + "\n\nPAINT\n" + paintmod.__doc__
            + "\n\nMATERIALS\n" + materials.__doc__ + "\n\nFACE SHAPES\n" + faceshapes.__doc__
            + "\n\nPLANS\n" + planmod.__doc__)


def _saved(name: str, v: int, spec: dict, extra: str = "") -> str:
    """The reply to a save: version, notes, warnings (things that saved but likely aren't what was meant), summary."""
    warn = "".join(f"WARNING: {w}\n" for w in paintmod.side_warnings(spec))
    b = spec.get("base") or {}
    hd = b.get("head") if isinstance(b.get("head"), dict) else None
    if hd and (hd.get("shape") or hd.get("simplify") or b.get("style")):
        # (GNM's own mouth needs the lips where GNM puts them: a style that pushed them falls back, and says so)
        try:
            from . import base as basemod, spec as specmod
            note = basemod.mouth_note(b, basemod.head_of({"joints": specmod.expand_mirror(spec)["joints"]}, b))
            if note:
                warn += f"WARNING: {note}\n"
        except Exception:  # noqa: BLE001  (a report line must never fail a save)
            pass
    return f"saved {name} v{v}\n" + extra + warn + summarize(spec)


@mcp.tool(structured_output=False)
def put_model(name: str, spec: dict, note: str = "") -> str:
    """Create a model or replace its whole spec (missing keys get defaults). The stored plan is kept unless the spec
    gives one ("plan": null drops it). Returns a summary. Details: guide(topic="put_model")."""
    full = {**empty_spec(), **_spec_arg(spec)}
    kept = ""
    if "plan" not in full:
        try:
            old = store.load(name).get("plan")
        except ValueError:  # a new model
            old = None
        if old is not None:
            full["plan"] = old
            kept = "kept the stored plan (pass \"plan\": null to drop it)\n"
    elif full["plan"] is None:
        del full["plan"]
    v = store.save(name, full, note or "put_model")
    return _saved(name, v, full, kept)


@mcp.tool(structured_output=False)
def edit_model(name: str, ops: list[dict], note: str = "") -> str:
    """Apply a batch of edits atomically. ops: {"op": "set", "kind": <any top-level key with named entries:
    joints|bones|blobs|kits|strokes|paint|parts|...>, "name", "value"} (merge; null field removes), {"op":
    "set_key", "key", "value"}, {"op": "delete"|"rename", "kind", "name", "to"?}, {"op": "move", "joints", "delta"},
    {"op": "scale_r", "joints", "factor"}, {"op": "global", "value"}. Edit ".L" and centre only. Details:
    guide(topic="edit_model")."""
    spec = store.edit(store.load(name), ops)  # errors name the op: "op 3 (set blobs tooth.L): ..."
    v = store.save(name, spec, note or f"{len(ops)} ops")
    return _saved(name, v, spec)


@mcp.tool(structured_output=False)
def look(name: str, views: list[str] | None = None, size: int = 448, grid: bool = False,
         focus: list[float] | None = None, zoom: float = 1.0, resolution: int = 160,
         matcap: str = "clay_studio.exr", strokes: bool = False, shading: str = "clay", paint: bool = True,
         paint_layer: str | None = None, hide_parts: list[str] | None = None, only_parts: list[str] | None = None,
         clip: dict | list[dict] | None = None, camera: dict | list[dict] | None = None, instances: bool = False,
         save: str | None = None):
    """Build and render a contact sheet (clay, or painted from the Blender scene). views (front, side, top,
    three_quarter, back, ...), focus=[x,y,z] + zoom for close-ups, resolution (160 quick, 256-320 detail), shading
    "clay"|"raking"|"curvature"|"flat", strokes=True overlays stroke paths, paint / paint_layer (one mask),
    hide_parts / only_parts, clip (plane cuts), camera (perspective eyes), instances, save (PNG path). Details:
    guide(topic="look")."""
    cams = [] if camera is None else (camera if isinstance(camera, list) else [camera])
    cams = [_resolve_camera(name, c) for c in cams]
    # "hair" is a pseudo-part (the locks aren't spec parts): hide_parts=["hair"] leaves them out of a painted look;
    # clay and geometric views draw no locks anyway, so there it just drops out
    if hide_parts and "hair" in hide_parts:
        if not store.load(name).get("hair"):
            raise ValueError(f"{name} has no hair to hide")
        hide_parts = [p for p in hide_parts if p != "hair"]
        hide_hair = True
    else:
        hide_hair = False
    if cams:  # say what blocks a camera's view before a render is spent on it
        from .spec import compile_prims
        seen = [p for p in compile_prims(store.load(name))
                if (not only_parts or p.part in only_parts) and p.part not in (hide_parts or [])]
        for c in cams:
            why = meas.sight(seen, c["eye"], c["target"]) if seen else ""
            if why:
                c["_note"] = c.get("_note", "") + f" | NOT SEEN: {why}"
    geometric =strokes or instances or shading not in ("clay", "flat")  # clip and close-ups render painted too
    if paint and not geometric and store.load(name).get("paint"):
        from . import scene
        r = scene.sync(name)
        closeup = focus is not None and zoom > 1
        sheet, secs = scene.look(name, views or ([] if cams else (render.DEFAULT_VIEWS[:1] if closeup else render.DEFAULT_VIEWS)),
                                 cams, size, None, paint_layer, hide_parts, only_parts, flat=shading == "flat",
                                 clip=clip, focus=focus if closeup else None, zoom=zoom, hide_hair=hide_hair)
        if save:
            sheet.save(save)
        notes = [l for l in r["log"] if "cuts into" in l or "from the scene" in l or "scene:" in l]
        if paint_layer:
            c = scene.look.coverage
            notes.insert(0, f"{paint_layer} covers " + ("NOTHING in view: misaddressed?" if c < 0.0005 else
                                                        f"{c:.1%} of the surface in view"))
        info = (f"{name}: scene look (EEVEE, painted) in {secs}s, sync {sum(r['seconds'].values()):.1f}s"
                + (f" | {'; '.join(notes)}" if notes else ""))
        for f, c in zip([render.camera_frame(c, i) for i, c in enumerate(cams)], cams):
            info += (f" | {f['name']}: eye ({', '.join(f'{x:.2f}' for x in f['eye'])}) -> target "
                     f"({', '.join(f'{x:.2f}' for x in f['center'])}), fov {f['fov']:.0f}" + c.get("_note", ""))
        return [_out(sheet, save), info + (f" | saved {save}" if save else "")]
    paint = paint and bool(store.load(name).get("paint"))  # geometric views: clay per part (noted)
    cam_frames = [render.camera_frame(c, i) for i, c in enumerate(cams)]
    names_ = views or ([] if cams else render.DEFAULT_VIEWS)
    planes = store.clip_planes(clip)
    if focus is not None and zoom > 1:
        full_bounds = store.extent(name)  # sets the view scale, as in a full look
        frames = render.view_frames(full_bounds, names_ or render.DEFAULT_VIEWS[:1], focus, zoom)
        half = 0.8 * frames[0]["scale"]
        frames = frames[:len(names_)]
        f = np.asarray(focus, float)
        meta = store.build(name, resolution, box=(f - half, f + half))
    else:
        meta = store.build(name, resolution)
        full_bounds = meta["bounds"]
        frames = None
    mesh = Path(meta["mesh"])
    if shading == "raking":
        matcap = str(render.raking_matcap(store.HOME / "raking_matcap.png"))
    elif shading == "curvature":
        mesh = _curvature_mesh(name, mesh, meta["voxel"], full_bounds)
    elif shading not in ("clay", "flat"):
        raise ValueError('shading must be "clay", "raking", "curvature" or "flat"')
    keep = None
    if hide_parts or only_parts:
        with np.load(meta["mesh"]) as z:
            built = [str(n) for n in z["part_names"]]
        allp = sorted(set(built) | set(meta.get("empty_parts", [])))
        bad = [p for p in (hide_parts or []) + (only_parts or []) if p not in allp]
        if bad:
            raise ValueError(f"no part(s) {bad}; parts: {allp}")
        keep = [p for p in built if (not only_parts or p in only_parts) and p not in (hide_parts or [])]
    extra, shown = [], ""
    frusta = cam_frames if cam_frames and not names_ else None  # only cameras: paint only what they can see
    if keep is not None or planes or frusta:
        mesh = store.view_mesh(mesh, keep, planes, frusta)
        with np.load(mesh) as z:
            nshown, fb = len(z["verts"]), z["frame_bounds"]
        shown = f" | showing {nshown} verts" + (f" of parts {', '.join(keep)}" if keep is not None else "")
        shown += " (in the cameras' view)" if frusta else ""
        if planes:
            caps = store.section_caps(name, mesh, planes, keep, meta["voxel"])
            extra = [caps] if caps else []
            shown += ", clipped" + ("" if caps else " (no solid cut: no caps)")
    if frames is None:  # with only_parts, frame what's shown
        frames = render.view_frames(fb if only_parts else np.array(full_bounds), names_, focus, zoom)
    painted = " | clay per part (paint shows in painted looks: no strokes, clip or close-up)" if paint else ""
    frames = frames + cam_frames
    imgs = render.render_views(mesh, frames, size, matcap, flat=shading == "flat", extra=extra)
    if strokes:
        ortho = [f for f in frames if "eye" not in f]
        paths = _stroke_paths(store.load(name), ortho, mesh if shown else Path(meta["mesh"]), meta["voxel"], size,
                              keep)
        imgs = [im if "eye" in f else render.draw_strokes(im, f, paths) for im, f in zip(imgs, frames)]
    if instances:
        from . import assemble
        marks = []
        for inst, pl in assemble.placements(store.load(name)).items():
            M = assemble.world_of(pl)
            fr = M[:3, :3] @ [0.0, -1.0, 0.0]
            marks.append({"label": inst, "at": M[:3, 3], "front": fr / (np.linalg.norm(fr) or 1)})
        imgs = [im if "eye" in f else render.draw_instances(im, f, marks) for im, f in zip(imgs, frames)]
    sheet = render.contact_sheet(imgs, frames, grid)
    lo, hi = full_bounds
    dims = [round(h - l, 3) for l, h in zip(lo, hi)]
    info = (f"{name}: {meta['verts']} verts, voxel {meta['voxel']:.4f}, built in {meta['seconds']}s | "
            f"size X{dims[0]} Y{dims[1]} Z{dims[2]}")
    for f, c in zip(cam_frames, cams):
        info += (f" | {f['name']}: eye ({', '.join(f'{x:.2f}' for x in f['eye'])}) -> target "
                 f"({', '.join(f'{x:.2f}' for x in f['center'])}), fov {f['fov']:.0f}" + c.get("_note", ""))
    sp_ = store.load(name)
    nxt = ""
    if sp_.get("base") or sp_.get("cloth") or sp_.get("skin"):  # (a character: judged against its reference)
        from . import next_steps
        nxt = "\n" + next_steps.after_look("head / character" if sp_.get("base") else "model",
                                           _has_reference(name, sp_))
    return [_out(sheet, save), info + shown + painted + (f" | saved {save}" if save else "") + nxt]


def _resolve_camera(name: str, cam: dict) -> dict:
    """Fill in a camera's 2D eye (a person standing there: floor + eye_height) and 2D target (level gaze)."""
    if not isinstance(cam, dict) or "eye" not in cam or "target" not in cam:
        raise ValueError('camera needs {"eye": [x, y, z] or [x, y], "target": [x, y, z] or [x, y], "fov"?: deg}')
    cam = dict(cam)
    eye, target = [float(x) for x in cam["eye"]], [float(x) for x in cam["target"]]
    if len(eye) == 2:
        x, y, floor, moved = meas.stand_spot(store.load(name), *eye)
        if floor is None:
            floor, cam["_note"] = 0.0, " (no floor there: eye height above z = 0)"
        else:
            cam["_note"] = f" (standing on the floor at z = {floor:.2f}" + (f"; {moved})" if moved else ")")
            eye[:2] = [x, y]
        eye.append(floor + float(cam.get("eye_height", 1.6)))
    if len(target) == 2:
        target.append(eye[2])
    if len(eye) != 3 or len(target) != 3:
        raise ValueError("camera eye and target are [x, y, z] or [x, y]")
    cam["eye"], cam["target"] = eye, target
    return cam


def _curvature_mesh(name: str, mesh: Path, voxel: float, bounds) -> Path:
    """The built mesh plus per-vertex curvature colours (Laplacian of the exact field, each part's vertices
    against that part alone, all 7 samples in one evaluation). Cached next to the mesh until it's rebuilt."""
    from . import sdf
    from .spec import compile_prims
    out = mesh.with_name(mesh.stem + "_curv.npz")
    if out.exists() and out.stat().st_mtime >= mesh.stat().st_mtime:
        return out
    z = dict(np.load(mesh))
    streams = {ps[0].part: ps for ps in sdf.streams(compile_prims(store.load(name)))}
    names = [str(n) for n in z.get("part_names", ["body"])]
    part = z["part"] if "part" in z else np.zeros(len(z["verts"]), int)
    lap = np.zeros(len(z["verts"]))
    for i, pn in enumerate(names):
        sel = np.flatnonzero(part == i)
        lap[sel] = surface.laplacian(streams[pn], z["verts"][sel].astype(np.float64), voxel)
    size = float(np.max(np.asarray(bounds[1]) - np.asarray(bounds[0])))
    z["colors"] = render.curvature_colours(lap, size, voxel)
    np.savez(out, **z)
    return out


def _stroke_paths(spec: dict, frames: list[dict], mesh=None, voxel: float = 0.0, size: int = 448,
                  parts: list[str] | None = None) -> list[dict]:
    """Every stroke's seated path (mirrored ones too), with per-view visibility: a point is hidden when the
    built mesh is nearer the camera there (by more than the stroke's own height and a little slack).
    parts: only strokes on these parts (the others are hidden in this look)."""
    from . import sdf
    from .spec import compile_prims, expand_mirror
    s = expand_mirror(spec)
    prims = compile_prims(spec)
    stored = spec.get("strokes") or {}
    out = []
    for bname, bl in s["blobs"].items():
        if bl.get("shape") not in ("displace", "flatten") or (parts is not None and
                                                                bl.get("part", "body") not in parts):
            continue
        base = bname[:-2] if bname.endswith((".L", ".R")) else bname
        copy = re.fullmatch(r"(.+)_([rs])(\d+)", base)  # a repeat (_r<i>) or scatter (_s<i>) copy
        stem = copy.group(1) if copy else base
        src = next((k for k in (base + ".L", base, stem + ".L", stem) if k in stored and
                    (k in (base, base + ".L") or copy)), None)
        st = stored.get(src, {})
        op = "flatten" if bl["shape"] == "flatten" else ("clay" if np.min(bl["depth"]) >= 0 and np.max(bl["depth"]) > 0 else "crease")
        count = int((st.get("repeat") or st.get("scatter") or {}).get("count", 1))
        label = None
        if not bname.endswith(".R") and src:
            first = copy is None or copy.group(3) == "0"
            label = (src if count == 1 else f"{src} x{count}") if first else None
        P = np.asarray(bl["pts"], float) + np.asarray(bl.get("at", [0, 0, 0]), float)
        N = np.asarray(bl["nrm"], float)
        if len(N) != len(P):
            N = np.broadcast_to(N[0], P.shape)
        height = float(np.abs(np.asarray(bl.get("depth", [0.0]), float)).max())
        out.append({"label": label, "op": op, "pts": P, "height": height, "vis": {}})
    if out and mesh is not None:  # depth-test against the built mesh, splatted into a z-buffer per view
        z = np.load(mesh)
        verts = z["verts"].astype(np.float64)
        tol = 2.5 * voxel
        for f in frames:
            zbuf, depth_of = _zbuffer(verts, f, size)
            for o in out:
                xy = np.clip(render.project(f, o["pts"], size).round().astype(int), 0, size - 1)
                slack = tol + o["height"]
                o["vis"][f["name"]] = depth_of(o["pts"]) >= zbuf[xy[:, 1], xy[:, 0]] - slack
    for o in out:
        o.pop("start", None)
        o.pop("height", None)
    return out


def _zbuffer(verts: np.ndarray, frame: dict, size: int):
    """Nearest-surface depth per pixel of a view, from the mesh's vertices (dense enough at build
    resolutions to cover every pixel once dilated a little), and the depth function it uses."""
    from scipy import ndimage
    d = np.asarray(frame["dir"], float)
    d /= np.linalg.norm(d)
    c = np.asarray(frame["center"], float)

    def depth_of(pts):
        return (np.asarray(pts, float) - c) @ d  # larger = nearer the camera

    xy = render.project(frame, verts, size).round().astype(int)
    ok = np.all((xy >= 0) & (xy < size), axis=1)
    zbuf = np.full((size, size), -np.inf)
    np.maximum.at(zbuf, (xy[ok, 1], xy[ok, 0]), depth_of(verts[ok]))
    return ndimage.maximum_filter(zbuf, size=3), depth_of


@mcp.tool(structured_output=False)
def measure(name: str, along: str | list[str], samples: int = 11, lo: float | None = None,
            hi: float | None = None) -> str:
    """Cross-section sizes from the exact field. along = a bone or bone chain (widths/heights from the axis at
    `samples` stations: pinches, bulges) or "x"|"y"|"z" (world slices between lo and hi, every separate part).
    Details: guide(topic="measure")."""
    return meas.measure(store.load(name), along, samples, lo, hi)


@mcp.tool(structured_output=False)
def clearance(name: str, region: list[list[float]] | None = None, path: list[list[float]] | None = None,
              floor: float | None = None, height: float = 1.8, radius: float = 0.25, step: float = 0.2,
              spacing: float | None = None) -> str:
    """Can a person walk here? From the exact field: region [[x0,y0],[x1,y1]] gives a top-view walkability map; path
    [[x,y],...] gives floor, headroom and clear width along it with a verdict. floor, height, radius, step, spacing.
    Details: guide(topic="clearance")."""
    return meas.clearance(store.load(name), region, path, floor, height, radius, step, spacing)


@mcp.tool(structured_output=False)
def set_reference(name: str, view: str, image_path: str, flip: bool = False, threshold: float = 40.0):
    """Attach a reference image for view "front"|"side"|"top" (silhouette from alpha, else from the corner colour by
    threshold; flip=True if a side reference faces right). Returns the extracted mask. Details:
    guide(topic="set_reference")."""
    if view not in ("front", "side", "top"):
        raise ValueError("view must be front, side or top")
    d = store.refs_dir(name)
    src = Path(image_path).expanduser()
    dst = d / f"{view}{src.suffix.lower()}"
    shutil.copy(src, dst)
    cfg_p = d / "refs.json"
    cfg = json.loads(cfg_p.read_text()) if cfg_p.exists() else {}
    cfg[view] = {"path": str(dst), "flip": flip, "threshold": threshold}
    cfg_p.write_text(json.dumps(cfg, indent=1))
    mask = cmp.reference_mask(str(dst), flip, threshold)
    im = PILImage.fromarray((mask * 255).astype("uint8"))
    im.thumbnail((384, 384))
    return [_png(im), f"reference {view} set ({mask.shape[1]}x{mask.shape[0]}, {mask.mean():.1%} foreground)"]


@mcp.tool(structured_output=False)
def compare(name: str, views: list[str] | None = None, fit: str = "auto", resolution: int = 160,
            against: str = "auto", only_parts: list[str] | None = None, hide_parts: list[str] | None = None):
    """Compare model silhouettes to references (set_reference images or the plan): IoU, diff image and edge-error band
    tables per view. fit "auto"|"height"|"width" (scale search), against "auto"|"refs"|"plan", only_parts /
    hide_parts. Details: guide(topic="compare")."""
    spec = store.load(name)
    parts = _sil_parts(spec, only_parts, hide_parts)
    sils = _silhouettes(name, spec, resolution, parts)
    out = []
    for v, (ref, world) in _refs(name, views, against).items():
        iou, diff, report = cmp.compare(sils[v], ref, fit, world=world)
        out += [_png(diff), f"[{v}] {_parts_note(parts)}{report}"]
    return out


@mcp.tool(structured_output=False)
def fit(name: str, views: list[str] | None = None, only: list[str] | None = None,
        lock: list[str] | None = None, params: list[str] | None = None, iterations: int = 20,
        max_step: float = 0.02, stiffness: float = 0.05, align: str = "auto", resolution: int = 160,
        against: str = "auto", only_parts: list[str] | None = None, hide_parts: list[str] | None = None):
    """Auto-fit joints, radii and blobs (params "pos"|"r"|"offset"|"size") to the reference or plan silhouettes and
    save as a new version. only / lock (element names), max_step, stiffness, iterations, against, only_parts /
    hide_parts. Block out by hand first; revert undoes. Details: guide(topic="fit")."""
    refs = _refs(name, views, against)
    spec = store.load(name)
    pin = []
    if any(w is not None for _, w in refs.values()):  # fitting to the plan: its landmarks fix joint heights
        pin = [("joints", lm["joint"], "pos", 2) for lm in (spec["plan"].get("landmarks") or {}).values()
               if lm.get("joint") in spec["joints"]]
    parts = _sil_parts(spec, only_parts, hide_parts)
    res = fitmod.fit(spec, refs, align, tuple(params or fitmod.GROUPS), only, tuple(lock or ()),
                     iterations, max_step, stiffness, resolution, pin, parts)
    ver = store.save(name, res.spec, "fit " + " ".join(
        f"{v} {res.iou_before[v]:.3f}->{res.iou_after[v]:.3f}" for v in refs))
    out = []
    for v, im in fitmod.diff_images(res).items():
        out += [_png(im), f"[{v}] IoU {res.iou_before[v]:.3f} -> {res.iou_after[v]:.3f}"]
    out.append(f"saved {name} v{ver}\n" + _parts_note(parts) + "\n".join(res.log) + "\n\nchanges:\n" + "\n".join(res.changes or ["(none)"]))
    return out


@mcp.tool(structured_output=False)
def set_plan(name: str, plan: dict, note: str = "", save: str | None = None):
    """Set or replace a model's plan (the 2D blockout: per-view shapes in world units, landmarks, sections); creates
    the model if needed and returns the plan drawn with rulers. plan = {"views": {view: {"shapes"}}, "landmarks",
    "sections"}; save writes the sheet. Details: guide(topic="set_plan")."""
    plan = _spec_arg(plan)
    planmod.validate(plan)
    try:
        spec = store.load(name)
    except ValueError:
        spec = empty_spec()
    spec = {**spec, "plan": plan}
    v = store.save(name, spec, note or "set_plan")
    views = [x for x in ("front", "side", "top") if planmod.bounds(plan, x) is not None]
    return [_out(planmod.sheet(plan, views), save), f"saved {name} v{v} with a plan ({', '.join(views)})"]


@mcp.tool(structured_output=False)
def check(name: str, resolution: int = 160, save: str | None = None, only_parts: list[str] | None = None,
          hide_parts: list[str] | None = None):
    """Check the model against its plan after every stage: silhouette diff per view (IoU, edge-error bands in world
    units), landmark heights, sections; plus the realism audit, doorway walk-through and props cutting into things.
    only_parts / hide_parts choose the parts counted; save writes the sheet. Details: guide(topic="check")."""
    from . import realism
    spec = store.load(name)
    warn = realism.audit(spec)
    realism_txt = ("\n\nREALISM (too perfect to be real?):\n" + "\n".join(f"- {w}" for w in warn)) if warn else \
        "\n\nREALISM: no perfection warnings"
    if spec.get("scatter"):
        import hashlib
        from . import assemble
        assemble.expand(spec)
        notes = assemble.NOTES.get(hashlib.sha1(json.dumps(spec, sort_keys=True, default=float).encode()).hexdigest())
        if notes:
            realism_txt += "\n\nSCATTER:\n" + "\n".join(f"- {n}" for n in notes)
    cl = meas.prop_clashes(spec)
    if cl:
        realism_txt += "\n\nCLASHES (props cutting into something):\n" + "\n".join(f"- {c}" for c in cl)
    doors = meas.check_doorways(spec)
    if doors:
        realism_txt += "\n\nDOORWAYS (a person 1.8 m tall, 0.5 m wide walked 1 m through each):\n" + "\n".join(doors)
    plan = spec.get("plan")
    if not plan:
        return "no plan to check against (set_plan)." + realism_txt
    parts = _sil_parts(spec, only_parts, hide_parts)
    tagged = planmod.shape_parts(plan)  # shapes standing for one part each (chains, a cage): compared on their own
    if tagged:
        from .spec import compile_prims
        have = {p.part for p in compile_prims(spec)}
        if tagged - have:
            raise ValueError(f"plan shapes name parts the model hasn't: {sorted(tagged - have)} (parts: {sorted(have)})")
        tagged &= set(parts) if parts else have
        rest = frozenset((set(parts) if parts else have) - tagged)
        main_plan = planmod.subplan(plan, None)
    else:
        rest, main_plan = parts, plan
    views = [v for v in ("front", "side", "top") if planmod.bounds(plan, v) is not None]
    main_views = [v for v in views if planmod.bounds(main_plan, v) is not None]
    sils = _silhouettes(name, spec, resolution, rest or None) if main_views and (rest or not tagged) else {}
    shown = sils if not tagged else _silhouettes(name, spec, resolution, parts)
    lines, outlines = ([_parts_note(parts).strip()] if parts else []), {}
    for v in views:
        outlines[v] = (shown[v]["mask"], shown[v]["u"], shown[v]["v"])
    for v in main_views if sils else []:
        ref, world = planmod.reference(main_plan, v)
        _, _, report = cmp.compare(sils[v], ref, world=world, bands=10)
        who = f" (parts {', '.join(sorted(rest))})" if tagged else ""
        lines.append(f"[{v}]{who} " + report.replace("alignment: fit=world (exact); ", ""))
    close = float(plan.get("close", 0.03))
    for p in sorted(tagged):
        pplan = planmod.subplan(plan, p)
        psil = _silhouettes(name, spec, resolution, frozenset([p]))
        for v in views:
            if planmod.bounds(pplan, v) is None:
                continue
            ref, world = planmod.reference(pplan, v)
            _, _, report = cmp.compare(_closed(psil[v], close), ref, world=world, bands=10)
            lines.append(f"[{v}: part {p}, gaps closed {close:g} m] " + report.replace("alignment: fit=world (exact); ", ""))
    lines += planmod.check_numbers(spec, plan)
    if not views:
        return "\n".join(lines) + realism_txt
    return [_out(planmod.sheet(plan, views, outlines=outlines), save), "\n".join(lines) + realism_txt]


def _closed(sil: dict, radius: float) -> dict:
    """A silhouette with gaps up to 2 x radius closed (a chain curtain, a wire cage read as their envelope)."""
    from scipy import ndimage
    m = sil["mask"]
    px = (sil["u"][1] - sil["u"][0]) / max(m.shape[1] - 1, 1)
    r = max(int(np.ceil(radius / px)), 1)
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    disk = xx * xx + yy * yy <= r * r
    padded = np.pad(m, r + 1)
    closed = ndimage.binary_closing(padded, structure=disk)[r + 1:-r - 1, r + 1:-r - 1]
    return {**sil, "mask": closed}


@mcp.tool(structured_output=False)
def rig(name: str, pose: dict | str | None = None, resolution: int = 160, size: int = 640, save: str | None = None,
        drive_twist: bool = True, glb: str | None = None, focus: str | None = None, zoom: float = 1.0,
        views: list[str] | None = None, shapes: dict | None = None, engine: bool = True):
    """The export rig (Mixamo skeleton for humanoids, named chains otherwise): fits it, skins the model and renders a
    test pose with a weights audit (lines ending "<- BAD"), twist and layer reports. pose ("seated", {} = rest, or
    {bone: [axis|"roll", deg]}), glb (judge an exported GLB instead), focus/zoom, views, shapes, drive_twist,
    engine, save. Details: guide(topic="rig")."""
    from . import rig as rigmod
    spec = store.load(name)
    try:
        bones = rigmod.rig_bones(spec)
    except ValueError as e:
        return str(e)
    from . import rig_audit
    extra = {}
    if glb:  # the export itself: its mesh, joints and weights
        g = rig_audit.read_glb(Path(glb).expanduser())
        bones = g["bones"]
        V, Fs, J, W, lpart, lnames = rig_audit.joined(g["meshes"], shapes)
        lskip = [k for k, m in g["meshes"].items() if len(np.unique(m["J"][m["W"] > 1e-6])) <= 1]
        rep, F = rig_audit.weld(V, Fs)  # (seam-split vertices as one surface, for normals and the audit)
        skip = rig_audit.bound(g["meshes"])
        note = [f"judging {Path(glb).name}: {len(V)} vertices, {len(Fs)} triangles, the export's own joints and weights"]
    else:
        meta = store.build(name, resolution)
        z = np.load(meta["mesh"])
        V, F = z["verts"].astype(np.float64), z["faces"]
        Fs, rep, skip = F, np.arange(len(V)), None
        J, W = rigmod.skin_mesh(spec, bones, V, F, z["part"], [str(n) for n in z["part_names"]])
        extra = {k: z[k] for k in ("part", "part_names", "part_colors")}
        lpart, lnames = z["part"], [str(n) for n in z["part_names"]]
        lskip = [pn for pn in lnames if ((spec.get("parts") or {}).get(pn) or {}).get("rig_bone")]
        note = []
        _, girth, _, _ = rig_audit.owners(bones, V)
        thin = [girth[i] for i, b in enumerate(bones) if i in girth and "Hand" in b["name"]
                and b["name"][-1:].isdigit()]
        if thin and meta["voxel"] > 0.5 * float(np.median(thin)):
            note.append(f"WARNING: this look's voxel is {meta['voxel'] * 1e3:.1f} mm and the fingers are "
                        f"~{2e3 * float(np.median(thin)):.0f} mm thick: they are fused or lumpy in this build AT REST. "
                        "Don't judge hands here: export and pass glb=<the .glb> (the real mesh and weights)")
    names = [b["name"] for b in bones]
    if pose == "seated":
        turns = rig_audit.seated(bones)
        if not turns:
            return "pose: \"seated\" needs a humanoid rig (UpLeg and Leg joints)"
    elif isinstance(pose, str):
        return f"pose: {pose!r} is not a pose (\"seated\", or {{rig bone: [[axis] or \"roll\", degrees]}})"
    elif pose is not None and not pose:
        turns = {}
    elif pose:
        bad = [k for k in pose if k not in names and rigmod.PREFIX + k not in names]
        if bad:
            return f"pose: no rig bone {bad} (have {', '.join(names)})"
        turns = rigmod.resolve_turns(bones, {(k if k in names else rigmod.PREFIX + k): (v[0], v[1])
                                             for k, v in pose.items()})
    else:
        turns = rigmod.test_pose(bones)
    P = rigmod.pose(bones, V, J, W, rigmod.drive_twist(bones, turns) if drive_twist else turns) if turns else V
    fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    N = np.zeros_like(P)
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    N = N[rep]
    N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-12
    at = None
    if focus:
        fb = focus if focus in names else rigmod.PREFIX + focus
        if fb not in names:
            return f"focus: no rig bone {focus!r}"
        i = names.index(fb)
        kids = [b["head"] for b in bones if b["parent"] == i and not b.get("twist")]
        at = 0.5 * (bones[i]["head"] + (np.mean(kids, 0) if kids else bones[i]["head"]))
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "posed.npz"
        np.savez(f, verts=P.astype(np.float32), faces=Fs, normals=N.astype(np.float32), **extra)
        frames = render.view_frames(P, views or ["front", "side"], focus=at, zoom=zoom)
        img = render.contact_sheet(render.render_views(f, frames, size, "clay_studio.exr"), frames)
    if glb and engine and Path(glb).expanduser().with_suffix(".json").exists():
        # the export as an engine draws it (its maps, its normal map, its own skinning in Blender's importer) over
        # the clay: a 15k face reads lumpy in clay (7.5 mm facets) and smooth with its normal map
        from PIL import Image as _Im
        from . import asset
        driven = rigmod.drive_twist(bones, turns) if (turns and drive_twist) else turns
        one = dict(shapes or {})
        one["turns"] = {k: [*(float(x) for x in v[0]), float(v[1])] for k, v in driven.items()}
        try:
            top = asset.preview(Path(glb).expanduser(), views or ["front", "side"], size=size, focus=at, zoom=zoom,
                                poses=[one], lighting=(spec.get("style") or {}).get("look"))[0]
            both = _Im.new("RGB", (max(top.width, img.width), top.height + img.height), (28, 29, 33))
            both.paste(top, (0, 0))
            both.paste(img, (0, top.height))
            img = both
            note.append("top row: the GLB as an engine draws it (maps + normal map); bottom row: its mesh in clay")
        except Exception as e:  # Blender missing, a GLB without maps: the clay row alone
            note.append(f"(no engine row: {str(e)[:200]})")
    used = np.bincount(J[W > 0.01], minlength=len(bones))
    empty = [b["name"] for b, u in zip(bones, used) if not u and not b["end"] and not b.get("noweight")]
    text = [f"{len(bones)} rig bones ({(spec.get('rig') or {}).get('type', 'humanoid')}; "
            f"{sum(1 for b in bones if b.get('twist'))} of them twist bones, after the base set); posed: "
            + (", ".join(f"{k} {v[1]:+g} deg" for k, v in turns.items()) or "nothing (REST)")
            + ("" if drive_twist else "; twist bones NOT driven")]
    text += [f"  {b['name']} <- {b.get('src', '?')}" + (" (end)" if b["end"] else "")
             + (f", child of {bones[b['parent']]['name']}" if b["parent"] >= 0 else " (root)")
             + (f"; {b['twist']['mode']}s {b['twist']['driver']}'s roll x {b['twist']['share']:+g}"
                if b.get("twist") else "") for b in bones]
    if empty:
        text.append("bones that got no skin: " + ", ".join(empty))
    try:
        note += rig_audit.fused_limbs(spec, rigmod.rig_bones(spec))
    except Exception:
        pass
    from . import rig_template
    if not glb and rig_template.weights_note(spec):
        note.append(rig_template.weights_note(spec))
    text = note + text
    text += rigmod.report(spec, bones, V, F, J, W)
    flesh = None
    try:  # kit characters: skin belongs to the bone whose modelled flesh it is (a belly beside a hanging arm)
        if len(bones) == len(rigmod.rig_bones(spec)):
            flesh = rig_audit.flesh_distances(spec, rigmod.rig_bones(spec), V)
    except Exception:
        flesh = None
    text += rig_audit.audit_text(rig_audit.audit(bones, V, F, J, W, skip=skip, flesh=flesh))
    sit = rig_audit.seated(bones)
    if sit and len(lnames) > 1:  # clothes over clothes over skin: do they stay in order when the character sits
        Ps = rigmod.pose(bones, V, J, W, rigmod.drive_twist(bones, sit))
        text += rig_audit.layers_text(rig_audit.layers(V, Fs, lpart, lnames, Ps, skip=lskip))
    return [_out(img, save), "\n".join(text)]


@mcp.tool(structured_output=False)
def style_check(name: str, colours: bool = True, save: str | None = None) -> str:
    """Measure a model against its style sheet's rules (spec.style.sheet): face ratios, eye opening and, with
    colours=True, skin colour lit vs shadow from a render (save keeps it). PASS/FAIL per rule. Details:
    guide(topic="style_check")."""
    from . import scene, stylesheet
    rows = stylesheet.check(name)
    if colours:
        scene.sync(name)
        rows += stylesheet.colour_check(name, save=save)
    lines = []
    for r in rows:
        if "samples" in r:
            lines.append("samples: " + "; ".join(f"{k} {v['hex']} hsv {v['hsv']}" for k, v in r["samples"].items()))
        else:
            lines.append(f"{'PASS' if r['ok'] else 'FAIL'} {r['rule']} = {r['value']} (target {r['target']}): {r['why']}")
    return "\n".join(lines)


@mcp.tool(structured_output=False)
def history(name: str) -> str:
    """List saved versions of a model."""
    return "\n".join(f"v{h['version']}  {h['time']}  {h['note']}" for h in store.history(name))


@mcp.tool(structured_output=False)
def revert(name: str, version: int) -> str:
    """Restore an earlier version (saved as a new version, so nothing is lost)."""
    spec = store.version_spec(name, version)
    v = store.save(name, spec, f"revert to v{version}")
    return f"{name} v{v} = v{version}\n" + summarize(spec)


@mcp.tool(structured_output=False)
def sync(name: str, resolution: int = 256, hair_only: bool = False, cloth_only: bool = False) -> str:
    """Bring the model's Blender scene (scene.blend) in line with the spec, after pulling back a person's edits; only
    what changed is redone; runs inside a live Blender session when one has it open. hair_only / cloth_only: just
    the hair locks / garments. Details: guide(topic="sync")."""
    from . import scene
    if cloth_only:
        from . import cloth
        log: list = []
        changes = scene.pull(name, log)
        r = cloth.sync(name, log)
        return (f"garments synced into {scene.blend_path(name)}: {', '.join(r['garments']) or 'none simulated'} "
                f"({len(r['made'])} objects replaced) in {r['seconds']}s"
                + (f"\npulled first: {json.dumps(changes)}" if changes else "") + ("\n" + "\n".join(log) if log else ""))
    if hair_only:
        from . import hair
        log: list = []
        changes = scene.pull(name, log)
        r = hair.sync(name)
        return (f"hair synced into {scene.blend_path(name)}: {r['made']} locks in {r['seconds']}s"
                + (f"\npulled first: {json.dumps(changes)}" if changes else "") + ("\n" + "\n".join(log) if log else ""))
    r = scene.sync(name, resolution)
    return (f"{r['blend']} synced in {sum(r['seconds'].values()):.1f}s ({', '.join(f'{k} {v}s' for k, v in r['seconds'].items())})\n"
            + "\n".join(r["log"]))


@mcp.tool(structured_output=False)
def pull(name: str) -> str:
    """Take back what a person changed in the model's Blender scene (moved instances, exposed paint numbers, garment
    colour and sculpt) without re-syncing; reports instances now cutting into something. Details:
    guide(topic="pull")."""
    from . import scene
    log = []
    changes = scene.pull(name, log)
    return (json.dumps(changes) if changes else "nothing changed in the scene") + ("\n" + "\n".join(log) if log else "")


@mcp.tool(structured_output=False)
def export(name: str, path: str, resolution: int = 256) -> str:
    """Build at `resolution` and write an OBJ to `path` (Z up, metres). Details: guide(topic="export")."""
    meta = store.build(name, resolution)
    p = store.export_obj(name, Path(path).expanduser())
    return f"wrote {p} ({meta['verts']} verts, {meta['faces']} faces)"


@mcp.tool(structured_output=False)
def export_asset(name: str, out_dir: str, triangles: int | None = None, texture: int = 2048, resolution: int = 256,
                 atlases: int = 1, texel_density: float | None = None, instancing: bool = True, preview: bool = True,
                 hide: list[str] | None = None, save: str | None = None, rig: bool | dict = False, fbx: bool = False,
                 face_shapes: bool | list[str] = False, asset_name: str | None = None,
                 lods: bool | list[float] = False, cloth_triangles: int | None = None, role: str | None = None,
                 correctives: bool = True):
    """Game-ready export into out_dir: low poly per part, UV atlases and PBR maps, GLB (+ fbx=True). Key options:
    role (hero / main_npc / secondary_npc / crowd: budgets from budgets.json; explicit arguments win), triangles,
    texture / texel_density, lods, rig=True (Mixamo for humanoids; correctives: knee / elbow / shoulder morphs),
    face_shapes (ARKit), cloth_triangles, preview (the GLB rendered as a game draws it), hide, asset_name. Minutes;
    progress in progress.log. Details: guide(topic="export_asset")."""
    from . import asset
    info = asset.export(name, Path(out_dir).expanduser(), triangles, texture, resolution, atlases, texel_density,
                        instancing, rig, fbx, face_shapes or None, asset_name=asset_name, lods=lods or None,
                        cloth_triangles=cloth_triangles, role=role, correctives=correctives)
    sizes = ", ".join(f"{a['size']}^2" for a in info["atlases"].values())
    text = (f"wrote {info['glb']}: {info['triangles_placed']} triangles drawn ({info['triangles']} in the file), "
            f"atlases {sizes}, height range +-{info['height_range_m'] * 1000:.1f} mm, {info['seconds']}s\n"
            + "\n".join(info["log"])
            + "\nmaps: " + ", ".join(Path(v).name for a in info["atlases"].values() for v in a["maps"].values()))
    from . import resources
    w = resources.last_wait()
    if w and w[0] > 5:
        text += f"\nwaited {w[0]:.0f} s for heavy-job memory ({w[1] or 'queue'})"
    if not preview:
        return text
    im = asset.preview(Path(info["glb"]), render.DEFAULT_VIEWS, hide=hide,
                       lighting=(store.load(name).get("style") or {}).get("look"))
    return [_out(im, save), text]


# ---------------------------------------------------------------- hair

HAIR_TRACE = """A trace is reference-image pixels (u right, v down) of the picture you're matching:
  {"image": path (or pass image_path), "landmarks": {lm joint: [u, v], ...} (8-10 face points: eye corners, brow
   middles, nose tip, mouth corners, chin; the model's lm_* joints), "part": [[u, v], ...] (the parting from its front
   end back), "hairline": [[u, v], ...] (temple to temple across the forehead), "hair": [[u, v], ...] (closed outline of
   the visible hair above clip_y), "clip_y": v (below it ear, sideburn and beard aren't traced), "clumps": [{"name",
   "line": [[u, v], ...] root -> tip along the strands, "width": px across the clump}], "crop"?: [x0, y0, x1, y1] (the
   square the matched views show; default: round the hair and landmarks), "views"?: {name: {the same keys for
   another view of the character: another figure in the same picture (same lens), or a turnaround's side/back with
   its own "image"; landmarks, hair, hairline, clip_y and crop needed}}}. Every view gets its own matched row and
   outline numbers in look_hair.
Clump names: one starting "part_side" is the short clump falling from the part toward the near ear; one whose root is
across the head from the part is the sweep's fall down the far side; the rest are the rows sweeping from the part,
front first."""


def _hair_counts(spec: dict) -> str:
    locks = (spec.get("hair") or {}).get("locks") or {}
    tiers: dict = {}
    for lk in locks.values():
        t = lk.get("tier", "?") + ("(hand)" if lk.get("hand") else "")
        tiers[t] = tiers.get(t, 0) + 1
    return f"{len(locks)} locks: " + ", ".join(f"{k} {v}" for k, v in sorted(tiers.items()))


def _hair_gates(look) -> str:
    """The numbers a hair look measures, each with what it should be."""
    from . import hair
    lines = []
    g = getattr(look, "gate", None) or {}
    if g:
        worst = {v: max((x for k, x in r.items() if k in ("left", "right")), default=0.0)
                 for v, r in g.items() if isinstance(r, dict)}
        notch = {v: max((x for k, x in r.items() if k.endswith("_notch")), default=0.0)
                 for v, r in g.items() if isinstance(r, dict)}
        at = {v: r.get("at") for v, r in g.items() if isinstance(r, dict)}
        lines.append(f"silhouette gate {'PASS' if g.get('pass') else 'FAIL'}: worst dent in the outline (mm, <= 1.5; brows"
                     f" + 2 cm up to near the top, 12 mm scale) " + ", ".join(f"{v} {d} at z {at[v]}" for v, d in worst.items())
                     + "; clump steps at the outline (mm, 2-5 reads as clumps) "
                     + ", ".join(f"{v} {d}" for v, d in notch.items()))
    ms = getattr(look, "mass_share", None) or {}
    if ms:
        bad = [v for v, x in ms.items() if x > 0.10]
        lines.append("bare volume share of the visible hair (< 0.10; the volume is filler, never a surface): "
                     + ", ".join(f"{v} {x}" for v, x in ms.items()) + (f"  OVER in {', '.join(bad)}" if bad else ""))
    bw = getattr(look, "bare_where", None) or {}
    bw = {v: r for v, r in bw.items() if r and ms.get(v, 0) > 0.10}
    if bw:
        lines.append("  where the bare volume shows (share of the view's hair, by head region; 'hairline' = within 15 mm "
                     "of it): " + "; ".join(f"{v}: " + ", ".join(f"{k} {x}" for k, x in list(r.items())[:4])
                                             for v, r in bw.items()))
    lm = getattr(look, "lit_mass", None) or {}
    if lm:
        lines.append("lit bare volume (reads as a helmet, < 0.03): " + ", ".join(f"{v} {x}" for v, x in lm.items()))
    fo = getattr(look, "folds", None)
    if fo:
        worst = sorted(fo.items(), key=lambda kv: -kv[1][0])
        lines.append(f"folded locks ({len(fo)}; the spine turns within the lock's own width, bend x half width >= "
                     f"1: the inner edge runs backwards and the lens crumples into flakes there; ease the path or narrow the lock): " + ", ".join(
                         f"{n} {r} at {u}" for n, (r, u) in worst[:12]) + (" ..." if len(fo) > 12 else ""))
    fi = getattr(look, "fins", None)
    if fi:
        lines.append(f"fins ({len(fi)}; a lock edge standing over the layer by more than the lock's own thickness + "
                     f"{hair.FIN_MM:g} mm, [mm over, u along it]; narrow the lock, lower its lie or lay it along the "
                     f"volume's curve): " + ", ".join(f"{n} {v[0]} at {v[1]}" for n, v in list(fi.items())[:12])
                     + (" ..." if len(fi) > 12 else ""))
    re_ = getattr(look, "root_ends", None)
    if re_:
        lines.append(f"blunt root ends ({len(re_)}; the lock's width in mm where it rises out of the layer, > "
                     f"{hair.ROOT_END_MM:g}: the cut end shows as a crescent fin at a parting or scales along a "
                     f"hairline; lower the clump's `root` (0.1) and raise `climb` (0.025 m)): " + ", ".join(
                         f"{n} {w}" for n, w in list(re_.items())[:12]) + (" ..." if len(re_) > 12 else ""))
    fits = getattr(look, "fits", None) or ({"matched": look.fit} if getattr(look, "fit", None) else {})
    for view, f in fits.items():
        if not f:
            continue
        lines.append(f"against the traced reference ({view} camera): " + ", ".join(
            f"{k} {v}" for k, v in f.items() if k not in ("clumps", "regions", "front_edge", "front_flow")))
        ff = f.get("front_flow")
        if ff:
            lines.append(f"  strand direction just inside the hairline, read off both images (deg to the hairline: 0 runs "
                         f"along it like a headband, +-90 straight out of it; per stretch from the trace's first "
                         f"hairline point to its last, [reference, ours]): " + ", ".join(
                             str(b) if b else "-" for b in ff["bins"]) + f"; mean error {ff['err_deg']} deg")
        fe = f.get("front_edge")
        if fe:
            bad = fe["rough_mm"] > 1.0 or fe["tooth_mm"] > 3.0 or fe["holes"] > 0.05
            lines.append(f"  hairline edge along the traced line ({'JAGGED' if bad else 'clean'}; the edge against the "
                         f"skin as rendered: rough_mm rms <= 1, tooth_mm worst tip/notch <= 3, holes = skin just inside "
                         f"the edge <= 0.05, turn_deg_cm = zigzag; off_mm + = ours further onto the skin than the "
                         f"trace): " + ", ".join(f"{k} {v}" for k, v in fe.items()))
        if f.get("regions"):
            lines.append("  outline per region, mm (err = ours - reference, + = ours sticks out; ref_hair / our_hair = "
                         "the outline over the bare head; ref_hair < 0: the bare head is already outside the "
                         "reference, hair can't fix it): " + "; ".join(
                             f"{r} err {v['err']:+} (worst {v['worst']:+}) ref_hair {v['ref_hair']} our_hair "
                             f"{v['our_hair']}" for r, v in f["regions"].items()))
        if f.get("clumps"):
            lines.append("  traced clump -> nearest model clump, direction error deg, mean distance px: " + "; ".join(
                f"{k} -> {v[0]} {v[1]} deg {v[2]} px" for k, v in f["clumps"].items()))
    return "\n".join(lines)


@mcp.tool(structured_output=False)
def groom_hair(name: str, groom: dict | None = None, replace: bool = False, stage: str | None = None,
               note: str = "", style: str | None = None, strands: dict | None = None, look: dict | None = None,
               fuller: dict | None = None, trim: dict | list | None = None):
    """Grow the hair's curve locks from spec.hair.groom and save. groom: a patch (hairline, parting, volume, length,
    flow, tiers, drawn clumps, tie, loose ...); replace regrows all; stage "mass"|"locks"; style
    "locks"|"strands"|"cards"; strands / look: strand dials and material; fuller {region: m} and trim reshape
    existing locks. Then look_hair. Details: guide(topic="groom_hair")."""
    from . import hair
    if style is not None or strands or look:
        sp = store.load(name)
        h = sp.setdefault("hair", {})
        if style is not None:
            if style not in hair.STYLES:
                raise ValueError(f"style is one of {', '.join(hair.STYLES)}")
            h["style"] = style
        if strands:
            h["strands"] = hair.merge_patch(h.get("strands") or {}, _spec_arg(strands))
        if look:
            h["look"] = hair.merge_patch(h.get("look") or {}, _spec_arg(look))
        hair.validate(sp)
        store.save(name, sp, note or "hair: style / strands / look")
    shaped = ""
    if fuller or trim:
        sp = store.load(name)
        sc = hair.scalp(name, sp)
        if fuller:
            fill = (sp.get("hair") or {}).get("style", "locks") != "locks"
            sp, rep = hair.lift(sp, sc, _spec_arg(fuller), fill=fill)
            shaped += (f"fuller: {rep['locks']} locks lifted up to {rep['max_lift_mm']} mm"
                       + (" and thickened to fill" if fill else "") + f"; volume {rep['volume']}\n")
        for t_ in ([] if not trim else trim if isinstance(trim, list) else [trim]):
            t_ = _spec_arg(t_)
            sp, rep = hair.trim(sp, sc, float(t_["below"]), tuple(t_.get("where", ("sides", "back", "nape"))))
            shaped += f"trim {t_}: {rep['cut']} locks cut, {rep['untouched']} untouched, too short to cut {rep['too_short']}\n"
        v = store.save(name, sp, note or "hair: fuller / trim")
        if not (groom or replace or stage):
            return shaped + f"saved {name} v{v}\n{_hair_counts(sp)}"
    r = hair.groom(name, replace=replace, note=note, patch=_spec_arg(groom) if groom else None, stage=stage)
    spec = store.load(name)
    return (shaped + f"saved {name} v{r['version']}: grew " + (", ".join(f"{t} {n}" for t, n in r["grown"].items()) or "nothing")
            + f"; kept {len(r['kept'])} hand/edited locks" + (f" ({', '.join(r['kept'][:12])}{'...' if len(r['kept']) > 12 else ''})" if r["kept"] else "")
            + (f"; {len(r['not_regrown'])} names not regrown (deleted in Blender: hair.removed; replace=True "
               f"forgets them)" if r["not_regrown"] else "")
            + f"\n{_hair_counts(spec)}; stage {(spec.get('hair') or {}).get('stage', 'locks')}")


@mcp.tool(structured_output=False)
def tie_hair(name: str, style: dict | None = None, carry_from: str | None = None, look: dict | None = None,
             note: str = "", reseat: bool = False):
    """A tied-back hairstyle (ponytail, bun, plait, half up) from a few words: style {tie: nape|low|mid|high|top,
    side, tightness 0..1, volume 0..1 (body: the hair stands up from the roots / the part and arcs over; 0 = a cap),
    part: centre|left|right|none, ears, tail {kind, length, fullness, wave, tousle, to}, wisps 0..1, front, hairline
    0..1, escaped, neatness 0..1, half}; a riff names only what changes. carry_from: wear another model's hair first.
    look: the colour {variation, sun (sun-lightened lengths), highlights, grey_amount: all 0..1}. Then
    look_hair(views="around"). reseat=True + carry_from: an approved groom onto a new head lock for lock. Details:
    guide(topic="tie_hair")."""
    from . import hair
    if reseat:
        if not carry_from or style or look:
            raise ValueError("reseat=True wears carry_from's grown locks as they are: give carry_from and no style / look "
                             "(riff afterwards with tie_hair(name, style=...), which regrows)")
        r = hair.reseat(name, carry_from, note=note)
        return (f"saved {name} v{r['version']}: {r['locks']} locks of {carry_from} re-seated (head x{r['k']:.3f})\n"
                f"{_hair_counts(store.load(name))}\nnext: look_hair(name, views=['around']) beside {carry_from}'s "
                f"approved renders at the same views of the head")
    r = hair.tie_style(name, _spec_arg(style) if style else None, carry_from=carry_from,
                       look=_spec_arg(look) if look else None, note=note)
    m = r["made"]["tie"]
    ga, tl = m["gather"], m.get("tail") or {}
    spec = store.load(name)
    return (f"saved {name} v{r['version']}: " + ", ".join(f"{k} {v}" for k, v in r["kinds"].items())
            + f"\nstyle (groom.tied): {json.dumps(r['tied'])}"
            + f"\nmade: tie at az {m['at'][0]} el {m['at'][1]} ({m['out'] * 1000:.0f} mm off the scalp); the hair stands "
              + (f"{(ga.get('volume') or {}).get('crown', 0) * 1000:.0f} mm off the crown and {(ga.get('volume') or {}).get('side', 0) * 1000:.0f} mm "
                 f"off the sides (volume: it rises within ~{2000 * (ga.get('volume') or {}).get('rise', 0):.0f} mm of the root, arc "
                 f"{(ga.get('volume') or {}).get('arc', 0):.2f})" if ga.get("volume") else f"{ga['puff'] * 1000:.0f} mm off the head")
              + f", lifts {ga['root_lift'] * 1000:.1f} mm at the roots, may hang "
              f"{ga['overhang']:.0f} deg over the hairline at the temples; parting {r['made']['parting']['side']}"
            + (f"; tail {tl['length'] * 100:.0f} cm, {tl['fullness'] * 1000:.0f} mm full, "
               + ("a bun" if tl.get("coil") else "a plait" if tl.get("plait") else "hanging") if tl else "; no tail")
            + (f"; wisps {m['wisps']['count']} a side ({', '.join(m['wisps']['where'])})"
               + (f" + {m['wisps']['loose']} thick loose locks" if m['wisps'].get('loose') else "")
               + (f" + {m['wisps']['baby']} baby hairs" if m['wisps'].get('baby') else "") if m.get("wisps") else "")
            + f"; hairline edge {ga.get('edge', 0):.2f} (0 hard .. 1 soft)"
            + f"\n{_hair_counts(spec)}\nnext: look_hair(name, views=['around']) (every side, with the bust: tied hair is "
              "tuned through the front and is wrong from behind first); change one word of the style to riff")


@mcp.tool(structured_output=False)
def look_hair(name: str, views: list[str] | None = None, size: int = 480, clay: bool = True, layout: bool = False,
              reference: str | None = None, save: str | None = None, only: list[str] | None = None,
              tier: str | None = None, debug: str | None = None, engine: str = "eevee",
              stage: str | None = None, measure: dict | None = None):
    """Fast hair renders (EEVEE, 4-30 s) with gates: outline dents, bare volume, fit to a traced reference. views
    (+ "ref0".. = the reference pictures' fitted cameras), clay, layout (top sketch), reference, only (lock names),
    tier (game cards) + debug, engine "cycles", size, save, stage (a model with the same head whose scene is used),
    measure {"view": "ref2", "mask": png, "tie": [x, y], "colour": true} (outline / tail / colour against that
    picture). Needs `sync` once (of the model or its stage). Details: guide(topic="look_hair")."""
    from . import hair
    views = list(views) if views else ["front", "three_quarter", "side", "back", "top"]
    if "around" in views:  # every side, with the bust (hair that hangs): the angles a front-tuned groom is wrong from
        i = views.index("around")
        views[i:i + 1] = ["bust_front", "bust_three_quarter", "bust_side", "bust_back_quarter", "bust_back", "bust_side_r"]
    only_layout = views == ["layout"]
    if "layout" in views:
        layout = True
        views = [v for v in views if v != "layout"]
    measure = _spec_arg(measure) if measure else None
    if measure and measure.get("view") and measure["view"] not in views:
        views.append(measure["view"])
    bad = [v for v in views if v not in hair.VIEWS and not re.fullmatch(r"ref\d+", str(v))]
    if bad:
        raise ValueError(f"unknown views {bad} (have {', '.join(hair.VIEWS)}, layout, ref0.. = the reference "
                         f"pictures' fitted cameras)")
    spec = store.load(name)
    if not (spec.get("hair") or {}):
        raise ValueError(f"{name} has no hair: groom_hair(name, groom={{...}}) grows it")
    out = []
    text = _hair_counts(spec)
    if tier is not None:
        if tier not in hair.CARD_TIERS:
            raise ValueError(f"tier is one of {', '.join(hair.CARD_TIERS)}")
        spec = {**spec, "hair": {**spec["hair"], "style": "cards"}}
    if not only_layout:
        sheet, secs, fr = hair.look(name, views=tuple(views), size=size, reference=reference, spec=spec, clay=clay,
                                    only=only, budget=tier, debug=debug, engine=engine, stage=stage)
        st = next((ln[10:] for ln in fr if ln.startswith("@@strands")), None)
        if st:
            text += f"\nstrands: {st}"
        out.append(_out(sheet, save))
        gates = _hair_gates(hair.look)
        if (spec.get("hair") or {}).get("stage") == "mass":  # the volume is the surface on purpose at this stage
            gates = "\n".join(ln for ln in gates.splitlines() if "bare volume" not in ln)
            gates += "\nstage mass: judge the silhouette (outline dents, IoU / outline px); bare-volume shares count " \
                     "once the locks are on (stage \"locks\")"
        text = f"rendered in {secs}s; {text}\n" + gates
        if measure:
            bad = set(measure) - {"view", "mask", "tie", "colour"}
            if bad or not measure.get("view"):
                raise ValueError(f"measure: {{'view': 'ref<i>', 'mask': png, 'tie': [x, y], 'colour': bool}}"
                                 + (f" (unknown {sorted(bad)})" if bad else ""))
            m = hair.measure_ref(name, measure["view"], mask=measure.get("mask"), tie=measure.get("tie"),
                                 colour=bool(measure.get("colour", True)), stage=stage)
            o = m.get("outline")
            if o:
                text += (f"\nagainst the picture ({m['view']}, {m['mm_per_px']} mm a px): IoU {o['iou']}, area x{o['area']}"
                         + (f", outline {o['chamfer_mm']} mm apart" if "chamfer_mm" in o else ""))
                if "below" in o:
                    text += (f"\n  below the tie: {100 * o['below']:+.0f}% of hers; length {o['ours']['length_mm']} mm (hers "
                             f"{o['hers']['length_mm']}), width {o['ours']['width_mm']} mm (hers {o['hers']['width_mm']}), "
                             f"reach {o['ours']['back_mm']} mm (hers {o['hers']['back_mm']}). One draw moves these ~10%: "
                             f"judge over 3-4 groom seeds")
            c = m.get("colour") or {}
            if c.get("ours") and c.get("picture"):
                text += f"\n  colour over dense hair ({engine}), ours | picture (L*, chroma, hue):"
                for b in ("mean", "shadow", "mid", "highlight"):
                    a_, b_ = c["ours"][b], c["picture"][b]
                    text += f"\n    {b}: {a_['L']} / {a_['chroma']} / {a_['hue']}  |  {b_['L']} / {b_['chroma']} / {b_['hue']}"
                text += ("\n  (EEVEE: look.eevee_gain / eevee_sat; Cycles: look.cycles_fit, cycles_width for cover, "
                         "cycles_sat for chroma)")
    hy = hair.hierarchy(spec, hair.scalp(name, spec))
    if hy:
        flag = ("  near-uniform: vary the widths (a few big shapes, some medium, a few small)"
                if hy["width_cv"] < 0.2 or max(hy["big"], hy["medium"], hy["small"]) > 0.8 else "")
        text += (f"\nsize hierarchy by area (artists aim near big 0.6 / medium 0.3 / small 0.1): big {hy['big']}, "
                 f"medium {hy['medium']}, small {hy['small']}; width spread (cv) {hy['width_cv']}, widest "
                 f"{hy['widest_mm']} mm" + flag)
    if layout:
        lay = hair.layout(name, spec=spec)
        lp = None
        if save:
            p = Path(save).expanduser()
            lp = str(p.with_name(p.stem + "_layout" + (p.suffix or ".png"))) if not only_layout else save
        out.append(_out(lay, lp))
    return [*out, text]


@mcp.tool(structured_output=False)
def export_hair(name: str, out_dir: str, tiers: list[str] | None = None, groom: bool = True, check: bool = True,
                save: str | None = None):
    """The hair alone, game-ready, from a strand groom: a GLB per tier (hero/main/npc/far cards, one atlas) into
    out_dir; groom=True also writes Alembic/USD strands; check=True judges the re-imported cards. tiers, save.
    Details: guide(topic="export_hair")."""
    from . import hair
    spec = store.load(name)
    if (spec.get("hair") or {}).get("style") != "strands":
        raise ValueError(f"{name}'s hair style is {(spec.get('hair') or {}).get('style', 'locks')!r}: export_hair cuts "
                         f"cards from a strand groom (groom_hair(name, style=\"strands\")); solid locks go out with "
                         f"export_asset")
    tiers = list(tiers) if tiers else ["main", "npc", "far"]
    bad = [t for t in tiers if t not in hair.CARD_TIERS]
    if bad:
        raise ValueError(f"unknown tiers {bad} (have {', '.join(hair.CARD_TIERS)})")
    rep = hair.export_hair(name, Path(out_dir).expanduser(), tiers=tuple(tiers), groom=groom, check=check, sheet=save)
    lines = [f"{t}: {r['triangles']} triangles, {r['bytes'] // 1024} KB, {r['glb']}" for t, r in rep["tiers"].items()]
    if rep.get("groom"):
        lines.append(f"groom: {rep['groom'].get('alembic')}, {rep['groom'].get('usd')}")
    if rep.get("checks_text"):
        lines.append(rep["checks_text"])
    out = []
    if save and check:
        from PIL import Image as _I
        out.append(_png(_I.open(save)))
    return [*out, "\n".join(lines)]


@mcp.tool(structured_output=False)
def hair_from_reference(name: str, out: str = "", read_only: bool = False, authority: int | None = None,
                        compare: dict | None = None, seed: int = 0) -> str:
    """The HAIR READER: measure the hair on the model's fitted reference pictures (stand-off by region, halo, edge
    roughness, wisps, hairline height / softness / baby hairs, parting, colour with grey by region from ONE authority
    view) and set a START groom / strands / look from it (measured vs set, INFERRED where a picture can't show it).
    read_only: the read alone. out: groom a copy. authority: the colour view (default the most frontal). compare
    {view index: render png through that fitted camera}: the same read on our renders, ours | picture.
    Details: guide(topic="hair_from_reference")."""
    from . import hair_read
    if compare:
        c = hair_read.compare(name, {int(k): v for k, v in _spec_arg(compare).items()}, authority=authority)
        st = hair_read.colour_step(c, (store.load(name).get("hair") or {}).get("look") or {})
        return c["text"] + ("\ncolour step (authority view): " + st["why"] if st.get("why") else "")
    if read_only:
        r = hair_read.read(name, authority=authority, log=lambda s: None)
        return r["text"] + "\n" + hair_read.start(r, store.load(name))["text"] + "\n(read only: nothing saved)"
    return hair_read.apply(name, out=out or None, authority=authority, seed=seed, log=lambda s: None)["text"]


@mcp.tool(structured_output=False)
def hair_reference(name: str, trace: dict | None = None, image_path: str | None = None, apply: bool = False,
                   widen: float = 1.8, save: str | None = None):
    """Match the hair to a reference picture: store a trace (landmarks, part, hairline, hair outline, clumps in image
    px), fit the camera to the face; apply=True carries the trace onto the groom (widen scales clump widths).
    image_path, save. Details: guide(topic="hair_reference")."""
    from PIL import Image as PI
    from . import hair
    d = store._dir(name)
    if not (d / "spec.json").exists():
        raise ValueError(f"no model {name!r}")
    if trace is not None:
        tr = _spec_arg(trace)
    else:
        tr = hair.ref_trace(name)
        if tr is None:
            raise ValueError("no stored trace: pass trace={...}\n" + HAIR_TRACE)
    if image_path:
        tr["image"] = str(Path(image_path).expanduser())
    if not tr.get("image") or not Path(tr["image"]).exists():
        raise ValueError(f"the reference image {tr.get('image')!r} doesn't exist (give image_path)")
    for k in ("part", "hairline", "hair"):
        if k in tr and (not isinstance(tr[k], list) or any(len(p) != 2 for p in tr[k])):
            raise ValueError(f"trace {k!r} is a list of [u, v] pixels")
    for c in tr.get("clumps") or []:
        if not isinstance(c, dict) or len(c.get("line") or []) < 2:
            raise ValueError('each trace clump is {"name", "line": [[u, v], ...] root -> tip, "width": px}')
    with PI.open(tr["image"]) as im:
        tr["image_size"] = [im.width, im.height]
    spec = store.load(name)
    sc = hair.scalp(name, spec)
    lms = tr.get("landmarks") or {}
    unknown = [n for n in lms if n not in sc.lm]
    if unknown:
        raise ValueError(f"unknown landmarks {unknown}; the model's: {', '.join(sorted(sc.lm))}")
    if not tr.get("crop"):
        P = np.array([*lms.values(), *(tr.get("hair") or []), *(tr.get("hairline") or [])], float)
        if not len(P):
            raise ValueError("give trace crop [x0, y0, x1, y1] or some landmarks / a hair outline")
        lo, hi = P.min(0), P.max(0)
        c, half = (lo + hi) / 2, (hi - lo).max() * 0.6
        tr["crop"] = [int(c[0] - half), int(c[1] - half), int(c[0] + half), int(c[1] + half)]
    (d / "ref_trace.json").write_text(json.dumps(tr, indent=1))
    text = []
    if len(lms) >= 6:
        cam = hair.fit_camera(name, lms, tr["image_size"], tr["crop"], spec)
        cam["reference"] = tr["image"]
        (d / "ref_camera.json").write_text(json.dumps(cam, indent=1))
        e = cam["error_px"]
        text.append(f"camera fitted on {len(e)} landmarks: error px mean {np.mean(list(e.values())):.1f}, max "
                    f"{max(e.values()):.1f} ({', '.join(f'{k} {v}' for k, v in e.items())}); fov {cam['fov']:.1f} deg, "
                    f"{1000 * np.linalg.norm(np.asarray(cam['eye']) - sc.C) / cam['focal_px']:.2f} mm per reference px")
    elif lms:
        raise ValueError(f"fitting the camera needs at least 6 landmarks (got {len(lms)}); the model's: "
                         f"{', '.join(sorted(sc.lm))}")
    else:
        text.append("no landmarks: the trace is stored, no camera fitted")
    cams = {}
    for v, t in (tr.get("views") or {}).items():  # more matched views: another figure or picture
        vl = t.get("landmarks") or {}
        unknown = [n for n in vl if n not in sc.lm]
        if unknown or len(vl) < 6:
            raise ValueError(f"trace view {v!r}: needs >= 6 known landmarks (unknown {unknown}, got {len(vl)})")
        if not t.get("crop"):
            raise ValueError(f"trace view {v!r}: give its crop [x0, y0, x1, y1]")
        img = t.get("image") or tr["image"]
        with PI.open(img) as im:
            size = [im.width, im.height]
        prim = hair.ref_camera(name) if not t.get("image") or t["image"] == tr["image"] else None
        # another figure in the same picture: the same lens (focal); its own picture: a focal of its own
        c = hair.fit_camera(name, vl, size, t["crop"], spec, view=v, save=False,
                            focal=prim["focal_px"] if prim else None)
        c["reference"] = img
        cams[v] = c
        e = c["error_px"]
        text.append(f"view {v}: camera fitted on {len(e)} landmarks: error px mean {np.mean(list(e.values())):.1f}, "
                    f"max {max(e.values()):.1f}; {1000 * np.linalg.norm(np.asarray(c['eye']) - sc.C) / c['focal_px']:.2f}"
                    f" mm per reference px")
    if cams or (d / "ref_cameras.json").exists():
        (d / "ref_cameras.json").write_text(json.dumps(cams, indent=1))
    if apply:
        if hair.ref_camera(name) is None:
            raise ValueError("apply needs a fitted camera (landmarks in the trace)")
        patch = hair.from_trace(name, spec, widen=widen)
        h = spec.setdefault("hair", {})
        h["groom"] = hair.merge_patch(h.get("groom") or {}, patch["groom"])
        v = store.save(name, spec, "hair: groom from the traced reference")
        dr = patch["groom"]["drawn"]
        text.append(f"saved v{v}: groom parting.line ({len(patch['groom']['parting']['line'])} points, side "
                    f"{patch['groom']['parting']['side']}), hairline.front_points, {len(dr)} drawn clumps "
                    f"({', '.join(c['name'] for c in dr)}). Next: groom_hair, then look_hair.")
    return [_out(hair.trace_image(name), save), "\n".join(text)]


# ---------------------------------------------------------------- cloth

def _cloth_status(st: dict) -> str:
    s = st["state"]
    tail = f" ({st['lines'][-1]})" if st.get("lines") else ""
    if s == "running":
        return f"running {st.get('seconds', 0)}s{tail}"
    if s == "failed":
        return f"FAILED: {st.get('error')}"
    return s + tail


@mcp.tool(structured_output=False)
def dress(name: str, garment: str | None = None, spec: dict | None = None, state: str | dict | None = None,
          quality: str | None = None, replace: bool = False, wait: float = 50.0, note: str = "", force: bool = False):
    """Put a garment on the model and simulate it (drafted, sewn, settled, cleaned up). spec: the garment patch
    (pattern, fabric, color, closures, ...; replace=True); state "worn"|"draped"|"hung"; quality "draft"|"final";
    wait (s); force skips the stage 1-3 gate. Call again to poll. Details: guide(topic="dress")."""
    from . import cloth
    if spec is not None or state is not None or quality is not None:
        if garment is None:
            raise ValueError("name the garment to change: dress(name, garment=..., spec={...})")
        full = store.load(name)
        gs = full.setdefault("cloth", {})
        from .hair import merge_patch
        g = {} if replace else dict(gs.get(garment) or {})
        if spec is not None:
            g = merge_patch(g, _spec_arg(spec))
        if state is not None:
            g["state"] = state
        if quality is not None:
            g["quality"] = quality
        gs[garment] = g
        v = store.save(name, full, note or f"dress {garment}")
        head = f"saved {name} v{v}\n"
    else:
        head = ""
        if garment is not None and garment not in (store.load(name).get("cloth") or {}):
            raise ValueError(f"no garment {garment!r}: give its spec (dress(name, garment, spec={{...}}))")
    if not force:  # the workflow's gate: no sim over a pattern that fails its own construction checks
        from . import cloth_workflow
        spec_g = store.load(name)
        blocked = []
        for gn in ([garment] if garment else list(spec_g.get("cloth") or {})):
            if cloth.cached(name, spec_g, gn) is not None:
                continue  # already simulated: nothing new starts
            fails = cloth_workflow.gate(name, gn, spec_g)
            if fails:
                blocked.append(f"{gn}: NOT simulated, {len(fails)} construction failures (check_garment for the "
                               "full stages; dress(..., force=True) simulates anyway):\n" + "\n".join(f"  {x}" for x in fails))
        if blocked:
            return head + "\n".join(blocked)
    # the PATTERN GATE (codified C11 / M2): no sim starts without a PASS record for this exact pattern + body. The sim
    # job refuses too (cloth_job.require_pattern_gate), but there it surfaced as a FAILED background job; here the
    # refusal names what to run. force does NOT skip it (the logged override is HIFIPUSHIE_SIM_WITHOUT_PATTERN_GATE).
    from . import cloth_check as cc_, next_steps
    if not os.environ.get(cc_.GATE_ENV_OVERRIDE, "").strip():
        spec_g = store.load(name)
        refused = {}
        for gn in ([garment] if garment else list(spec_g.get("cloth") or {})):
            if cloth.cached(name, spec_g, gn) is not None:
                continue
            st = cc_.gate_status(name, gn, spec_g)
            if not st["passed"]:
                refused[gn] = st["why"]
                continue
            uf = cc_.under_fit_status(name, gn, spec_g)  # (C85: never an outer garment over an unfitted under one)
            if not uf["passed"]:
                refused[gn] = f"its under garment doesn't fit yet: {uf['why']} (fit_garment(\"{name}\", \"{uf['under']}\"))"
        if refused:
            return head + next_steps.after_dress_refused(refused, name)
    sts = cloth.dress(name, [garment] if garment else None, wait=float(wait))
    out = []
    spec_now = store.load(name)
    for gn, st in sts.items():
        if st["state"] == "done":
            res = cloth.cached(name, spec_now, gn)
            out.append(cloth.report(gn, res) if res is not None else f"{gn}: done")
        else:
            out.append(f"{gn}: {_cloth_status(st)}")
    return head + "\n".join(out) + ("\nnext: look_cloth(name) for renders (strain map, close-ups with focus=...)"
                                    if all(s["state"] == "done" for s in sts.values()) else
                                    "\ncall dress(name) or look_cloth(name) again for progress")


@mcp.tool(structured_output=False)
def look_cloth(name: str, garments: list[str] | None = None, views: list[str] | None = None, strain: bool = True,
               size: int = 640, focus: str | list[float] | None = None, zoom: float = 0.4, textured: bool = False,
               body: bool = True, save: str | None = None, result: str | None = None, props: list[str] | None = None,
               diag: list | bool | None = None):
    """Renders of the simulated garments on the body: clay + strain map, and by DEFAULT the diag views (panels+seams+
    turned; strain+layers; diag=False none), with the per-garment report. garments, views, strain, focus ([x,y,z] |
    "garment:piece") + zoom, textured, body, size, save; result = a cloth job's out.npz; props = parts drawn with the
    body ([] none). Details: guide(topic="look_cloth")."""
    from . import cloth, next_steps
    vs = tuple(views or ("front", "side", "back", "three"))
    sheet, text = cloth.look(name, garments, views=vs, strain=strain, size=size, focus=focus, zoom=zoom, body=body,
                             textured=textured, result=result, props=props)
    if sheet is None:
        return text
    from . import cloth_workflow
    spec_now = store.load(name)
    extra = []
    gnames = garments or list(spec_now.get("cloth") or {})
    for gn in gnames:  # stage 5: the numeric targets
        try:
            r = cloth_workflow.run(name, gn, ("sim",), images=False, spec=spec_now)
            extra.append(f"targets {gn} (stage 5):\n" + cloth_workflow.text(r))
        except Exception as e:
            extra.append(f"targets {gn}: could not measure: {e}")
    out = [_out(sheet, save)]
    if _diag_rows(diag) and focus is None and result is None:  # (close-ups and carried results: clay only)
        done = [(gn, cloth.cached(name, spec_now, gn)) for gn in gnames]
        done = [(gn, r) for gn, r in done if r is not None and r.get("mesh") is not None]
        if done:
            ims, d = _garment_sheets(name, "cloth", done[0][1]["body"], [(gn, r["V"], r["mesh"]) for gn, r in done],
                                     vs, min(size, 560), clay=False, diag=diag)
            out += [_out(im, _save_suffix(save, tag)) for tag, im in ims]
            extra.append(f"diag single views (one per review_view call): {d}")
    extra.append(next_steps.after_look("garment", _has_reference(name, spec_now)))
    return out + [text + "\n\n" + "\n".join(extra)]


def _merge_patch(base, patch):
    """patch merged into base: objects key by key, null deletes, anything else replaces."""
    if not isinstance(patch, dict) or not isinstance(base, dict):
        return patch
    out = dict(base)
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = _merge_patch(out.get(k), v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


@mcp.tool(structured_output=False)
def skin(name: str, skin: dict | None = None, replace: bool = False, note: str = "") -> str:
    """Describe a human's skin (spec["skin"]: tone, age, features, wrinkles, hair, scars, tattoos, makeup, zones, only)
    as a patch (replace=True starts over); it expands into "skin:<layer>" paint and shading. skin_reference lists
    every key. Then look_skin. Details: guide(topic="skin")."""
    from . import paint
    from . import skin as skinmod
    spec = store.load(name)
    patch = _spec_arg(skin) if skin is not None else {}
    cur = {} if replace else (spec.get("skin") or {})
    new = _merge_patch(cur, patch)
    new_spec = {**spec, "skin": new}
    p = skinmod.params(new_spec)
    layers = [k[5:] for k in paint.layers(new_spec) if k.startswith("skin:")]
    v = store.save(name, new_spec, note=note or "skin")
    hx = lambda c: "#" + "".join(f"{int(round(x * 255)):02x}" for x in c)  # noqa: E731
    if not skinmod.shaded(new_spec):  # skin.only without "shading": some layers, the part's own shading untouched
        return (f"saved {name} v{v}: skin only {p['only']}: the skin part's shading and everything else are left as "
                f"they are\n{len(layers)} layers: {', '.join(layers)}\n"
                "sync + look (or look(paint_layer=\"skin:<layer>\")) to see them")
    base = skinmod.part_base(new_spec)[1]
    t = new.get("tone")
    return (f"saved {name} v{v}: skin on part {p['part']!r}, melanin {p['tone']['melanin']:.2f} blood {p['tone']['blood']:.2f} "
            f"undertone {p['tone']['undertone']:+.1f}, age {p['age']:.0f}\n"
            f"base {hx(base['color'])}, cheeks {hx(skinmod.tone_rgb(t, blood=2.7))}, lips {hx(skinmod.tone_rgb(t, melanin=0.7, blood=10, epidermis=0.45))}, "
            f"palms {hx(skinmod.tone_rgb(t, melanin=0.25, blood=1.7))}; roughness {base['roughness']:.2f}, subsurface "
            f"{base['subsurface_scale'] * 1000:.1f} mm, coat {base['coat']:.2f}\n"
            f"{len(layers)} layers: {', '.join(layers)}\n"
            f"look_skin(\"{name}\") renders close-ups and measures them; look(paint_layer=\"skin:<layer>\") or "
            f"look_skin(layer=...) shows one layer's mask" + _head_hint(new_spec))


def _head_hint(spec: dict) -> str:
    b = spec.get("base") or {}
    h = b.get("head") or {}
    if (b.get("body") or {}).get("source") != "makehuman" or h.get("source", "gnm") != "gnm" or "follow_body" in h:
        return ""
    return ("\nHINT: this head doesn't follow its body: base.head.follow_body is unset, so the face keeps one adult shape "
            "and its own size whatever the body's age and sex. For a new character set base.head.follow_body: true "
            "(guide(topic=\"skin\"), stage 0); leave it for a character whose head is already approved.")


@mcp.tool(structured_output=False)
def human(name: str, age: float = 30, sex: float | str = 0.5, weight: float = 0.5, muscle: float | None = None,
          height: float | None = None, seed: int | None = None, outfit: str | None = None,
          tone: float | dict | None = None, skin: dict | bool | None = None, head: dict | None = None,
          bust: float | None = None, firmness: float | None = None, note: str = "", source: str = "makehuman",
          style: str | dict | None = None) -> str:
    """A whole person from a description, saved as a model: human("mia", age=3, sex="female"). Measured proportions for
    age; dressed. Params: age, sex, weight, muscle, height, seed (the face), outfit, tone, skin, head, bust,
    firmness, source ("makehuman" | "human" = one mesh), style (one-mesh style sheet or sliders). Details:
    guide(topic="human")."""
    from . import humans
    sp = humans.spec(age=age, sex=sex, weight=weight, muscle=muscle, height=height, seed=seed, outfit_kind=outfit,
                     tone=tone, skin=_spec_arg(skin) if isinstance(skin, str) else skin, head=_spec_arg(head) if head else None,
                     bust=bust, firmness=firmness, source=source, style=_spec_arg(style) if isinstance(style, str) and style.strip().startswith("{") else style)
    full = {**empty_spec(), **sp}
    v = store.save(name, full, note or f"human: {humans.stage(float(age))}, {age:g} y")
    return (f"saved {name} v{v}: {humans.describe(full)}\n"
            f"parts: {', '.join(full['parts'])}. look(\"{name}\") for the figure, look_skin(\"{name}\") for the skin; "
            f"guide(topic=\"skin\") stage 0 says what the body and head keys do.")


def _human_base(name: str) -> tuple:
    sp = store.load(name)
    b = sp.get("base") or {}
    if (b.get("body") or {}).get("source") != "human":
        raise ValueError(f'{name}: not a one-mesh human (base.body.source "human"). Make one with human(name, ..., source="human"); '
                         "the measuring and fitting tools read the one mesh's own landmarks.")
    return sp, b


def _human_figure(name: str, spec_after: dict | None) -> PILImage.Image | None:
    """The whole DRESSED figure before | after (front + side), through `look`: an edit is judged on the person, not on
    the eye that was edited. A result that wasn't saved is built under a scratch name and removed."""
    try:
        ims = []
        for label, nm in (("before", name), ("after", None)):
            if nm is None:
                if spec_after is None:
                    break
                nm = name + "__try"
                store.save(nm, spec_after, "scratch: a fit's result for its whole-figure picture")
            r = look(nm, views=["front", "side"], size=360, resolution=220)
            im = PILImage.open(io.BytesIO(next(x for x in r if not isinstance(x, str)).data)).convert("RGB")
            from PIL import ImageDraw
            ImageDraw.Draw(im).text((44, 26), f"whole figure, {label}", fill=(255, 255, 160))
            ims.append(im)
        out = PILImage.new("RGB", (sum(i.width for i in ims), max(i.height for i in ims)), (30, 32, 36))
        x = 0
        for im in ims:
            out.paste(im, (x, 0))
            x += im.width
        return out
    except Exception as e:  # noqa: BLE001  (the picture must not lose the fit's report)
        return None
    finally:
        shutil.rmtree(store.HOME / (name + "__try"), ignore_errors=True)


def _human_apply(name: str, sp: dict, new_base: dict, rep: dict, note: str, force: bool, save: bool, st0, focus=None,
                 figure: bool = True) -> list:
    from . import humanfit
    ok = rep["integrity"]["ok"]
    fig = _human_figure(name, {**sp, "base": new_base}) if figure else None
    text = humanfit.report_text(rep)
    saved = ""
    if save and (ok or force):
        v = store.save(name, {**sp, "base": new_base}, note)
        saved = f"saved {name} v{v}" + ("" if ok else " (FORCED over a broken mesh)") + f". revert(\"{name}\", {v - 1}) undoes it."
    elif save:
        saved = "NOT SAVED: the mesh would be broken (the lines above). Ask for less, release fewer measures, or force=True."
    else:
        saved = "not saved (save=False): a dry run."
    im = humanfit.head_sheet(st0, humanfit.state(new_base), focus=focus)
    if fig is not None:
        both = PILImage.new("RGB", (max(im.width, fig.width), im.height + fig.height), (30, 32, 36))
        both.paste(im, (0, 0))
        both.paste(fig, (0, im.height))
        im = both
    return [_png(im), text + "\n" + saved + "\n(The picture: head before | after | where vertices moved"
            + ("; under it the whole dressed figure before | after. Judge the person, not the part you edited.)" if fig is not None
               else ". look(name) shows the whole dressed figure: look at it before going on.)")]


@mcp.tool(structured_output=False)
def measure_human(name: str, since: int | None = None, picture: bool = True):
    """Measure a one-mesh human: named body (cm) and face (mm) measures, ratios, integrity gates and a head picture.
    since = an earlier version: what changed (UNINTENDED flags). Measure before each change. Details:
    guide(topic="measure_human")."""
    from . import humanfit
    sp, b = _human_base(name)
    st = humanfit.state(b)
    text = humanfit.verdict(humanfit.integrity(b, st)) + "\n" + humanfit.table(st["measures"])
    from . import onemesh
    text += "\n" + onemesh.attach_report(b)["text"]  # (headbody) head size, heads tall, the neck at the seam ring
    st0 = None
    if since is not None:
        old = json.loads((store.HOME / name / "history" / f"{int(since):04d}.json").read_text())
        old = old.get("spec", old)
        st0 = humanfit.state(old["base"])
        text += f"\nsince v{since}:\n" + humanfit.effects_text(humanfit.side_effects(st0, st, set()), top=30)
    text += "\nlandmarks for nudge_human: " + ", ".join(humanfit.LANDMARKS) + ", eye.L, eye.R"
    if not picture:
        return text
    return [_png(humanfit.head_sheet(st0, st) if st0 is not None else humanfit.head_sheet(st)), text]


@mcp.tool(structured_output=False)
def fit_human(name: str, set: dict | str, free: list[str] | None = None, release: list[str] | None = None,
              force: bool = False, save: bool = True, note: str = "", figure: bool = True):
    """Set measures on a one-mesh human and let a minimal-change solver find the sliders: set = {"nose_width": 34 |
    "+2" | "x0.95", "a/b": ratio}. free (["identity"] | "body"), release, force, figure, save, note. Replies
    INTEGRITY, UNINTENDED, before | after; a broken result isn't saved. Details: guide(topic="fit_human")."""
    from . import humanfit
    sp, b = _human_base(name)
    want = _spec_arg(set) if isinstance(set, str) else dict(set)
    st0 = humanfit.state(b)
    nb, rep = humanfit.solve(b, want, free=tuple(free or ("identity",)), force=force, release=tuple(release or ()))
    pts = sorted({i for k in want for p in k.split("/") if p.strip() in humanfit.FACE for i in humanfit._points(p.strip())})
    focus = st0["L"][pts].mean(0) if pts else None
    return _human_apply(name, sp, nb, rep, note or f"fit_human {json.dumps(want)}", force, save, st0, focus, figure)


@mcp.tool(structured_output=False)
def nudge_human(name: str, landmark: str, move: list[float] | None = None, to: list[float] | None = None,
                radius: float = 0.015, force: bool = False, save: bool = True, note: str = "", figure: bool = True):
    """Move ONE face landmark by `move` [x,y,z] m or `to` a point; others held, mirror follows; what the sliders can't
    do becomes a local correction (radius) and is reported. Same reply as fit_human. Details:
    guide(topic="nudge_human")."""
    from . import humanfit
    sp, b = _human_base(name)
    st0 = humanfit.state(b)
    nb, rep = humanfit.nudge(b, landmark, move=move, to=to, radius=radius, force=force)
    return _human_apply(name, sp, nb, rep, note or f"nudge_human {landmark}", force, save, st0,
                        st0["L"][humanfit.point_index(landmark)], figure)


@mcp.tool(structured_output=False)
def human_reference(name: str, views: list[dict] | str, fit: bool = True, free: list[str] | None = None,
                    force: bool = False, save: bool = True, note: str = "", figure: bool = True,
                    read: dict | str | None = None, method: str = "map", measure: bool = False):
    """Match a one-mesh human's face to reference images by named points: views = [{"image", "size", "yaw", "points":
    {landmark: [u, v]}}]; a camera per view, shared identity. method "map" (detector + priors, default) | "points";
    read (a character read in macro sigmas), measure, fit, free, force, figure, save. Details:
    guide(topic="human_reference")."""
    from . import humanfit
    sp, b = _human_base(name)
    vs = json.loads(views) if isinstance(views, str) else views
    st0 = humanfit.state(b)
    if method == "map":
        from . import humanfit_map
        rd = json.loads(read) if isinstance(read, str) else read
        nb, rep = humanfit_map.fit(b, vs, read=rd, force=force, free=tuple(free or ("identity",)) if fit else (), measure=measure)
    else:
        nb, rep = humanfit.fit_views(b, vs, free=tuple(free or ("identity",)) if fit else (), force=force)
    (store.HOME / name / "human_refs.json").write_text(json.dumps({"views": vs, "cameras": rep["cameras"]}, indent=1))
    out = _human_apply(name, sp, nb, rep, note or "human_reference fit", force, save and fit, st0, None, figure)
    if rep.get("method") == "map":
        extra = "\n".join(f"view {i}: {v['evidence']}, lens ~{v['lens_mm']:.0f} mm" + (" (its lm0..lm67 points ignored: detector re-read)" if v["ignored_lm68"] else "") + (f" DROPPED from the identity: {v['rms_mm']} mm rms against the other pictures (not one projection / another face / wrong yaw?)" if v.get("dropped") else "")
                          for i, v in enumerate(rep["views"]))
        if rep.get("read"):
            extra += "\nread: " + ", ".join(f"{k} asked {v['asked']:+.1f} got {v['got']:+.2f}" for k, v in rep["read"].items())
        if rep.get("measured"):
            m_ = rep["measured"]
            extra += (f"\nMEASURED on view {m_['view']} ({m_['used']}; RENDERS ONLY: not validated on photographs): "
                      + ", ".join(f"{k} {v[0]:+.1f}+-{v[1]:.1f}" for k, v in sorted(m_["macros"].items(), key=lambda t: -abs(t[1][0]))[:12]))
        out[-1] = (out[-1] + "\n" + extra + "\nmacros (population sigmas):\n" + rep.get("macros", "")
                   + "\n(method map: the detector's point table is validated on RENDERS of heads of known shape only, not yet on "
                   "photographs. The result is the most probable head for this evidence: soft; structure comes after.)")
    return out


def _blockin_sheet(name: str, save: str | None, views: list | None = None, table: bool = True,
                   before: str | None = None) -> list:
    """The block-in look as tool output: [the sheet, the target table]."""
    from . import blockin as bi
    out = save or str(store.HOME / "human_renders" / f"blockin_{name}.png")
    r = bi.look(name, out, views=views, before=before)
    text = f"sheet: {r['out']} (" + ", ".join(f"view {v['view']} eye shift {v['shift_px']} px" for v in r["views"]) + ")"
    if table:
        text += "\n" + bi.table_text(bi.table(name))
    return [_png(PILImage.open(r["out"])), text]


@mcp.tool(structured_output=False)
def block_in_start(name: str, refs: str | list[dict], sex: str | float | None = None, age: float | None = None,
                   body: dict | None = None, gnm_base: float | None = None, ethnicity: str | dict | None = None,
                   cameras: str = "keep", replace: bool = False, save: str | None = None, expression: bool = False,
                   attach: str = "native", carry: bool = False):
    """THE DEFAULT START for a person's head from pictures: their body, GNM's class mean for the sex on a GNM-NATIVE
    head (true base, GNM's eyeball / mouth, its own size; the body fitted), nothing of ours on its surface (the reply
    names what was dropped), the cameras, the first look + table. refs = a one-mesh human with fitted references, or
    a views list; sex, age, body, ethnicity (a GNM class or a blend {class: weight}; default the pooled mean),
    cameras, attach, carry, replace, save, expression. Details: guide(topic="block_in_start")."""
    from . import blockin as bi
    e = bi.start(name, _spec_arg(refs) if isinstance(refs, str) and refs.strip().startswith("[") else refs, sex=sex,
                 age=age, body=body, gnm_base=gnm_base, ethnicity=ethnicity, cameras=cameras, replace=replace,
                 expression=expression, attach=attach, carry=carry)
    s = e["start"]
    out = _blockin_sheet(name, save)
    head = ("GNM-NATIVE head (true base, GNM's eyeball / mouth / teeth, GNM's own size; the body fitted)" if s["attach"] == "native"
            else f"body-carried head, gnm_base {s['gnm_base']:.2f}")
    txt = (f"started {name}: {s['sex']} class mean{' (' + s['ethnicity'] + ')' if s['ethnicity'] else ''}, age {s['age']:g}, "
           f"{head}, cameras {s['cameras']}, |c| {e['c_norm']:.2f}\n")
    txt += ("DROPPED from the refs model (not GNM's, not this person's read): " + "; ".join(s["dropped"]) + "\n" if s["dropped"]
            else "DROPPED from the refs model: nothing (it had no strokes, folds, wrinkle relief or head sliders)\n")
    if s.get("carry"):
        txt += "carry=True: the refs model's strokes / skin.folds / skin.wrinkles were KEPT (they are on this head's surface)\n"
    if s.get("left"):
        txt += "LEFT as the refs model had it (ours, not GNM's): " + "; ".join(s["left"]) + "\n"
    if s["attach"] == "native":
        from . import onemesh
        txt += onemesh.attach_report(store.load(name)["base"])["text"] + "\n"
    out[1] = (txt + out[1]
              + "\nNEXT: block_in_solve (the joint step; its first call lays the cameras on this head), 3-4 calls until |dc| < 2; "
                "then squint at the sheet and name the single biggest difference in masses and planes.")
    return out


@mcp.tool(structured_output=False)
def block_in_look(name: str, views: list[int] | None = None, table: bool = True, save: str | None = None,
                  before: str | None = None, focus: str | None = None, read: str = "", keep: bool | None = None):
    """The block-in sheet: per picture photo | clay under its light | overlay | outline difference | squints, at the
    eyes, + the target table. focus = a feature (eyes, nose, mouth, chin_jaw, cheeks, ears): ZOOM IN crops + raking
    light + its own rows. read / keep log your ZOOM OUT verdict on the step that made name. views, table, save,
    before. Details: guide(topic="block_in_look")."""
    from . import blockin as bi
    note = ""
    if read or keep is not None:
        bi.note(name, read, keep)
        note = f"logged on the step that made {name}: zoom-out read" + ("" if keep is None else f", kept={keep}") + "\n"
    if focus:
        out = save or str(store.HOME / "human_renders" / f"blockin_{name}_{focus}.png")
        r = bi.focus(name, focus, out, views=views, before=before)
        text = note + f"focus sheet {focus}: {r['out']} (" + "; ".join(f"view {v['view']}: {v['registered']}, shift {v['shift_px']} px" for v in r["views"]) + ")"
        if table:
            text += "\n" + bi.table_text(bi.feature_table(name, focus))
            if focus == "eyes":
                text += "\n" + bi.lid_text(bi.lid_read(name))
        return [_png(PILImage.open(r["out"])), text]
    out = _blockin_sheet(name, save, views=views, table=table, before=before)
    out[1] = note + out[1]
    return out


@mcp.tool(structured_output=False)
def block_in_step(name: str, moves: dict, out: str | None = None, seen: str = "", why: str = "",
                  cameras: list[int] | None = None, look: bool = True, save: str | None = None,
                  feature: str | None = None):
    """One block-in round: a NEW model (out, default the next number) = name moved ({"chin_height": 0.5,
    "eye_spacing!": 0.3, "nd:radix_width": 1, "head_scale": 1.05, "lid_upper": -0.001}); seen / why logged; feature =
    the feature zoomed in on (its before | after crops come back too); cameras; look; save. Details:
    guide(topic="block_in_step")."""
    from . import blockin as bi
    mv = _spec_arg(moves) if isinstance(moves, str) else dict(moves or {})
    if "attach" in mv:   # (nativedefault) the head switched to GNM-native, its cameras carried: a step of its own
        if mv != {"attach": "native"}:
            raise ValueError('block_in_step: {"attach": "native"} is a step of its own (the head switched to GNM-native, the '
                             "cameras carried); the other way is a new block_in_start(attach=\"body\")")
        r = bi.native_step(name, out=out, seen=seen)
        to = r["entry"]["to"]
        text = (f"{to} (from {name}): the head is GNM-NATIVE now (true base, GNM's own size, the body fitted). CAMERAS CARRIED "
                f"onto its new size and place (x{r['scale']:.3f}, the face moved {1000 * r['shift']:.0f} mm): the next block_in_solve "
                'lays them on this head first (cameras="refit" for that call). '
                + ("DROPPED (no meaning on a native head): " + "; ".join(r["dropped"]) if r["dropped"] else "no head key dropped")
                + ". Hair and clothes made on the old head must be remade.")
        if not look:
            return text
        sh = _blockin_sheet(to, save, before=None)
        return [sh[0], text + "\n" + sh[1]]
    rep = bi.step(name, mv, out=out, seen=seen, why=why, cameras=cameras, feature=feature)
    text = bi.step_text(rep)
    if not look:
        return text
    to = rep["entry"]["to"]
    res = []
    if feature:
        fo = str(Path(save).with_name(Path(save).stem + f"_{feature}.png")) if save else \
            str(store.HOME / "human_renders" / f"blockin_{to}_{feature}.png")
        r = bi.focus(to, feature, fo, before=name)
        res.append(_png(PILImage.open(r["out"])))
        text += f"\nZOOM IN sheet ({feature}, before | after): {r['out']}\n" + bi.table_text(bi.feature_table(to, feature))
    sh = _blockin_sheet(to, save, before=name)
    return [*res, sh[0], text + "\nZOOM OUT (the whole face):\n" + sh[1]
            + f"\nlog your zoom-out verdict: block_in_look(\"{to}\", read=..., keep=...)"]


@mcp.tool(structured_output=False)
def block_in_expression(name: str, out: str | None = None, views: list[int] | None = None, clear: bool = False,
                        eyes: bool = False, seen: str = "", why: str = "", look: bool = True, save: str | None = None):
    """Each picture's OWN expression (a smile, a squint), fitted on this head with the identity and camera held (GNM
    lower-face expression comps, small prior), stored per view in the references and applied in every
    block-in look / focus / table / lid read, never to the model: the neutral identity is then judged against the
    picture as it smiles. A new model (out), shape unchanged; views (default: detector views), clear=True removes them;
    eyes=True adds eye-region comps (a squinting picture; they can fight the lid pose).
    Fit once the big forms are in; refit after large identity moves. Details: guide(topic="block_in_expression")."""
    from . import blockin as bi
    rep = bi.expression_step(name, out=out, views=views, clear=clear, eyes=eyes, seen=seen, why=why)
    text = bi.expression_text(rep)
    if not look:
        return text
    to = rep["entry"]["to"]
    sh = _blockin_sheet(to, save, before=name)
    return [sh[0], text + "\nZOOM OUT (before = neutral clay, after = with the picture's expression):\n" + sh[1]]


@mcp.tool(structured_output=False)
def gnm_controls(query: str = "", control: str = "", families: list[str] | None = None, top: int = 12,
                 sort: str = "score", per_family: int = 0, sign: int = 0, zones: bool = False, phrase: str = "",
                 ruler: str = "") -> str:
    """GNM's controls. phrase = a difference you SEE ("the muzzle stands forward in profile", "pupils further apart")
    -> the driving manual's entries (control, sign, size, drags; guide topic gnm_driving): start there. query="mm" =
    the 27 mm measures (mm:<measure> moves). ruler="modelA,modelB" = those measures, B - A, largest first, each
    with the mm: move that closes it. query = a feature ("alar crease", "jowl") -> controls ranked by mm per prior
    cost x locality; control = one described; zones=True; families, sort, per_family, sign. Act: block_in_step
    {"mm:<measure>": mm}, {"gnm:<control>": x} or {"sculpt:<zone>": mm}. Details: guide(topic="gnm_controls")."""
    from . import gnm_controls as gcm
    if ruler:
        from . import blockin as bi, gnm_mm
        a, b = [x.strip() for x in ruler.split(",")][:2]
        return (f"ruler: {b} - {a} (GNM identity; take the largest gaps in sd first; mm: moves add up exactly)\n"
                + gnm_mm.gaps_text(bi.ruler(a, b)))
    if phrase:
        from . import gnm_manual
        return gnm_manual.text(gnm_manual.suggest(phrase, top=3))
    if query.strip().lower() in ("mm", "measures", "ruler"):
        from . import gnm_mm
        s = gnm_mm.sd()
        return ("The millimetre measures (block_in_step {\"mm:<measure>\": mm}: that measure alone, the others held "
                "in mm). Read the gap on the sheet (px x mm per px), type it. Population sd in mm:\n"
                + "\n".join(f"mm:{n} (sd {s[n]:.1f} mm, read in {gnm_mm.SEE[n][0]}): + = {gnm_mm.SEE[n][1]}"
                            for n in gnm_mm.NAMES)
                + "\nThe forward measures " + " -> ".join(gnm_mm.CHAIN) + " are a chain: a link carries everything "
                  "below it (the lower lip alone +2: lower_lip_forward +2 with chin_forward -2).")
    if zones:
        z = gcm.zones()
        return "\n".join(f"{k}: {d} ({len(z[k])} vertices)" for k, (d, _) in gcm.ZONES.items())
    if control:
        return gcm.text(gcm.describe(control))
    if not query:
        return ("gnm_controls: give query= (a feature) or control= (a name) or zones=True. Families: "
                + ", ".join(f"{f} ({len(gcm.names(f))})" for f in gcm.FAMILIES))
    return gcm.text(gcm.query(query, families=families, top=top, sort=sort, sign=sign, per_family=per_family))


@mcp.tool(structured_output=False)
def lid_read(name: str, match: bool | str = False, out: str | None = None, seen: str = "", save: str | None = None,
             expression: bool = False, donor: str | None = None, fold: str | None = None):
    """Lid margins against the iris (MRD-style, iris radii) and the fold line on the front picture vs the model.
    match=True: THE EYE STEP (a block-in step; set the ORBIT first: face_ruler), identity only: the opening (the eye
    ruler's margins and corners in mm), then the lid as ONE structure on GNM's lid rings: a crisp fold on the
    picture's fold line, brows held (fold="crisp", the default; fold="donor" / donor="s376": toward a donor head's
    lid; fold="none": the opening only), with the eyeball guard; nothing painted. expression=True: GNM's eye-region expression too. match="pose": the
    older lid_upper / lid_lower offsets. out, save (focus=eyes sheet), seen. Details: guide(topic="lid_read")."""
    from . import blockin as bi
    if not match:
        return bi.lid_text(bi.lid_read(name))
    if match == "pose":
        rep = bi.lid_match(name, out=out, seen=seen)
        to = rep["entry"]["to"]
        sh = _blockin_sheet(to, save, before=name)
        return [sh[0], bi.step_text(rep) + "\n" + bi.lid_text(bi.lid_read(to)) + "\n" + sh[1]]
    from . import blockin_eyes as be
    lines = []
    rep = be.eye_step(name, out=out, seen=seen, log=lines.append, expression=expression, donor=donor, fold=fold)
    to = rep["entry"]["to"]
    path = save or str(store.HOME / "human_renders" / f"blockin_{to}_eyes.png")
    bi.focus(to, "eyes", path, before=name)
    e = rep["eyes"]
    txt = (bi.step_text(rep) + "\n" + "\n".join(lines) + "\n" + be.text(e) + "\n" + bi.lid_text(bi.lid_read(to))
           + f"\nfocus=eyes sheet (before | after, raking light): {path}")
    c0_, c1_ = bi.identity(store.load(name)), bi.identity(store.load(to))   # NOTHING FORCED is the solve's rule, not yet
    big = int((abs(c1_) > 3.0).sum())                                       # this step's: say it when the step breaks it
    if big or float(((c1_ - c0_) ** 2).sum()) ** 0.5 > 8.0:
        txt = (f"WARNING: FORCED: the eye step moved the identity |dc| {float(((c1_ - c0_) ** 2).sum()) ** 0.5:.1f} "
               f"(|c| {float((c0_ ** 2).sum()) ** 0.5:.1f} -> {float((c1_ ** 2).sum()) ** 0.5:.1f}; a typical head ~13), "
               f"{big} component(s) past 3 sd (largest {float(abs(c1_).max()):.1f}). Do not keep it: step from {name} "
               'again with fold="none" (the opening only) or leave the lids to block_in_solve.\n' + txt)
    return [_png(PILImage.open(path)), txt]


@mcp.tool(structured_output=False)
def brow_read(name: str, match: bool = False, out: str | None = None):
    """The dressed brow HAIR (skin.hair.brows) against the front picture's, through its fitted camera: lower edge /
    middle line miss in mm at the model, and the picture's iris (limbus, mm at the model; its colour) against the
    drawn one. match=True: skin.hair.brows' placement (drop, tilt, apart, fall, thickness, taper) fitted to the
    picture's hair band and written to `out` (default: the model itself). Paint only. Details: guide(topic="brow_read")."""
    from . import blockin_brows as bb, blockin_eyes as be
    try:
        iris = be.iris_check(name)["text"]
    except Exception as e:  # noqa: BLE001  (no readable iris: the brows still read)
        iris = f"IRIS: not read ({e})"
    if not match:
        return bb.check(name)["text"] + "\n" + iris
    r = bb.apply(name, out=out)
    return (r["text"] + f"\nwritten to {r['model']} (skin.hair.brows; look_skin view \"brows\" / \"eye\" to judge it "
            "dressed)\n" + iris)


@mcp.tool(structured_output=False)
def eye_ruler(name: str, model: str | None = None, save: str | None = None):
    """THE EYE RULER: the front picture's eyes read by their edges (iris as a circle through the limbus, lid margins at 7
    columns, canthi, fold line, brow edge) against the model's mesh through the picture's fitted camera, in mm at the
    model, with each difference's tolerance (the reader's measured error) and the move that closes it. model: another
    model read against `name`'s picture. Returns the picture's eyes with the read and the model's lid outline drawn
    over them (save: the path) and the table. Sizes read by eye are 30-50 % off: read this before and after an eye
    step. Details: guide(topic="eye_ruler")."""
    from . import eye_ruler as er
    c = er.compare(name, model)
    path = save or str(store.HOME / "human_renders" / f"eye_ruler_{model or name}.png")
    im = er.overlay(c["image"], c["eyes"], c["mesh"], c["mm"])
    im.save(path)
    return [_png(im), c["text"] + f"\noverlay (picture; green = its margins, red = its canthi, blue = the model's ring / margins / "
                                  f"inner-corner landmark laid over by iris centre): {path}"]


@mcp.tool(structured_output=False)
def block_in_solve(name: str, out: str | None = None, share: float = 1.0, seen: str = "", save: str | None = None,
                   cameras: str = "free", anchors: str = "differential", parse: str = "auto", hold: str = "default",
                   expression: str = "default", chin_points: str = "auto", size: str = "held",
                   neck: str | float = "prior", dense: str = "default", detector: str = "default", hair_edge: str = "default"):
    """ONE JOINT STEP: face_ruler's solve over every reference view (outlines, irises, limbus, lids, lips, anchors;
    GNM's prior on the whole identity) applied as a block-in step, the solve's cameras kept. Use it FIRST from
    block_in_start's head, 3-4 calls until |dc| < 2. The reply says what MOVED WITH NO READ. cameras, size, neck
    (default "prior": ANSUR's girth), dense, detector, hair_edge, hold, expression, chin_points, anchors, parse, out,
    share, seen, save. A known lens (lens_mm / EXIF) keeps its distance. Details: guide(topic="block_in_solve")."""
    from . import blockin as bi
    if parse not in ("auto", "on", "off"):
        raise ValueError('block_in_solve: parse = "auto" | "on" | "off"')
    if hold not in ("default", "auto", "none") or expression not in ("default", "view", "shared", "lower", "none"):
        raise ValueError('block_in_solve: hold = "auto" | "none"; expression = "view" | "shared" | "none"')
    if chin_points not in ("auto", "on", "off"):
        raise ValueError('block_in_solve: chin_points = "auto" | "on" | "off"')
    if dense not in ("default", "on", "off") or detector not in ("default", "mesh", "anchors") or hair_edge not in ("default", "on", "off"):
        raise ValueError('block_in_solve: dense = "on" | "off"; detector = "mesh" | "anchors"; hair_edge = "on" | "off" (each also "default")')
    rep = bi.solve_step(name, out=out, share=share, seen=seen, cameras=cameras, anchors=anchors,
                        parse={"auto": "auto", "on": True, "off": False}[parse],
                        hold={"default": bi.SOLVE_HOLD, "auto": "auto", "none": None}[hold],
                        expression={"default": bi.SOLVE_EXPRESSION, "view": "view", "shared": "shared", "lower": "lower", "none": False}[expression],
                        chin={"chin_lm": {"auto": "auto", "on": "xy", "off": "none"}[chin_points],
                              "size": {"held": True, "free": False, "iris": "iris", "iris_pin": "iris_pin"}[size],
                              "neck": {"prior": True, "held": "held", "free": False}[neck] if isinstance(neck, str) else float(neck)},
                        dense={"default": None, "on": True, "off": False}[dense], mp={"default": None, "mesh": True, "anchors": False}[detector],
                        hair_edge={"default": None, "on": True, "off": False}[hair_edge])
    to, so = rep["entry"]["to"], rep["solve"]
    sh = _blockin_sheet(to, save, before=name)
    warn = ""
    if so["n"].get("outline", 0) < 120:
        warn += (f"WARNING: a weak solve: {so['n'].get('outline', 0)} outline reads (it wants ~150+ over 2-3 views). The anchors "
                 "and the prior carry it: expect the class mean's face where nothing was read.\n")
    for x in so.get("notes") or []:          # a VIEW without an outline (the total above hid a hair-covered front picture)
        if x.startswith(("NO OUTLINE:", "STRONG PERSPECTIVE:", "INFERRED (the camera's distance")):
            warn += "WARNING: " + x + "\n"
    if so["relax"] > 1.0:
        warn += (f"WARNING: INCONSISTENT PICTURES: at their own sigmas the solve wanted a component past 3 sd, so every read was "
                 f"down-weighted (sigma x{so['relax']:.2f}) until none did. The references disagree with each other or with any "
                 "one head by that much (paintings, expressions, a wrong camera): the result is a compromise, judge it on "
                 "the judging sheet against the head you had.\n")
    for x in so.get("notes") or []:          # a view's stated kind against its fitted camera
        if x.startswith("VIEW:"):
            warn += "WARNING: " + x + "\n"
    notes = "".join(f"  {x}\n" for x in so.get("notes") or [] if not x.startswith(("VIEW:", "NO OUTLINE:", "STRONG PERSPECTIVE:", "INFERRED (the camera's distance")))
    rp = (so.get("report") or {}).get("text") or ""
    if so.get("neck"):
        n_ = so["neck"]
        rp += ("\n" if rp else "") + (
            f"NECK: girth {1e3 * n_['before']:.0f} -> {1e3 * n_['after']:.0f} mm at its narrowest; "
            + {"held": f"HELD at {1e3 * (n_['target'] or 0):.0f}; no read",
               "prior": f"under the anthropometric PRIOR {1e3 * n_['ansur']:.0f} +- {1e3 * n_['ansur_sd']:.0f}; no direct read (INFERRED)",
               "free": "FREE (neck=\"free\"): moved with no read"}[n_["mode"]]
            + f" (ANSUR II for this sex and stature: {1e3 * n_['ansur']:.0f} +- {1e3 * n_['ansur_sd']:.0f})")
        h_ = so["head_size"]
        rp += (f"\nHEAD SIZE: a GNM-native head: GNM's own size x {h_['size']:.3f} "
               + (f"(the stature's allometry at {h_['stature']:.3f} m)" if h_["allometric"] else "(base.head.size, given)")
               + "; the solve's size hold keeps the identity's size at the start head's on top of that")
    if so.get("held"):
        rp += ("\n" if rp else "") + "HELD at the start head's value (no read looks at them): " + ", ".join(so["held"])
    for pc, d in (so.get("expression") or {}).items():
        big = [f"{fr_say(k)} {v[0]:+.2f}" for k, v in d.items() if abs(v[0]) >= max(0.15, 2 * v[1])]
        rp += ("\n" if rp else "") + (f"expression read in the {pc} picture (1 = GNM's full prototype; taken out of the identity): "
                                      + (", ".join(big) if big else "neutral"))
    return [sh[0], warn + f"joint solve: {so['n']} reads; |dc| {so['dc']:.2f}, |c| {so['c']:.2f}, largest component {so['max_sd']:.2f} sd; "
                   f"cameras' whole move since the start (shift mm, shift mm, scale %, roll, yaw, pitch deg, distance % per view; a prior, not a clip: see the CAMERA lines): {so['cameras']}"
                   f" (this call: {so['camera_step']})\n" + notes + (rp + "\n" if rp else "")
                   + bi.step_text(rep) + "\n" + sh[1]]


def fr_say(k: str) -> str:
    from . import face_ruler as fr
    return fr.EXPR_SAY.get(k, k)


@mcp.tool(structured_output=False)
def face_ruler(name: str, save: str | None = None):
    """THE FACE RULER: the block-in model against its reference pictures in MILLIMETRES: first the ORBIT (eye depth:
    set it before any lid work), then gnm_mm's 27 measures, picture - model, largest first, each with the reader's
    error and the `mm:` move that closes it (block_in_step). Read from skin OUTLINES, iris centres and the side views'
    limbus through the fitted cameras (yaw left free), not by eye and not from detector landmarks. NOT READ = these
    pictures do not show it. Start a block-in from this table. Returns the pictures with the reads drawn (save: the
    path) and the table. Details: guide(topic="face_ruler")."""
    from . import face_ruler as fr
    c = fr.compare(name)
    path = save or str(store.HOME / "human_renders" / f"face_ruler_{name}.png")
    im = fr.overlay(c)
    im.save(path)
    return [_png(im), c["text"] + f"\noverlay (green = the model's outline through each fitted camera, yellow = where "
                                  f"the picture's skin outline was read against it, magenta / cyan = iris centres picture / model): {path}"]


@mcp.tool(structured_output=False)
def lip_read(name: str, match: bool = False, out: str | None = None, seen: str = "", save: str | None = None):
    """The lips on the front picture vs the model: vermilion border miss (mm), seam miss, Cupid's bow (picture /
    model), the neutral's contact gaps and how it is closed. match=True: THE LIPS STEP (a block-in step): one solve
    over the identity + GNM's lower-face expression for the picture's borders and seam, the neutral closed by GNM's
    expression (no seal), the rest of the face held. out, save (focus=mouth sheet), seen. Details:
    guide(topic="lip_read")."""
    from . import blockin as bi, blockin_lips as bl
    if not match:
        return bl.read_text(bl.lip_read(name))
    lines = []
    rep = bl.lips_step(name, out=out, seen=seen, log=lines.append)
    to = rep["entry"]["to"]
    path = save or str(store.HOME / "human_renders" / f"blockin_{to}_mouth.png")
    bi.focus(to, "mouth", path, before=name)
    txt = (bi.step_text(rep) + "\n" + "\n".join(lines) + "\n" + bl.text(rep["lips"]) + "\n" + bl.read_text(bl.lip_read(to))
           + f"\nfocus=mouth sheet (before | after, raking light): {path}")
    return [_png(PILImage.open(path)), txt]


@mcp.tool(structured_output=False)
def likeness(name: str, targets: bool = False, top: int = 8):
    """The likeness checklist (~50 facial features) on a one-mesh human vs its fitted reference pictures: ranked
    misses, coverage, focus panels. targets=True measures the references alone and stores the target sheet and stage
    plan. top = how many panels. Measures only. Details: guide(topic="likeness")."""
    from . import likeness as lk
    if targets:
        sh = lk.measure_reference(name)
        return lk.sheet_text(sh) + "\n\nstage plan (fit_likeness, big to small):\n" + lk.stage_plan(name)
    txt, out, _ = lk.report(name, top=top)
    return [_png(PILImage.open(out)), txt + f"\nfocus sheet: {out}"]


@mcp.tool(structured_output=False)
def fit_likeness(name: str, stage: str, force: bool = False, save: bool = True):
    """ONE stage of the likeness fit (proportions, widths, eyes, brows, nose, mouth, chin_jaw, ears, profile): misses
    solved minimal-change, earlier stages pinned, integrity-guarded. Run likeness(targets=True) first; approve each
    stage's panels. force, save. Details: guide(topic="fit_likeness")."""
    from . import likeness as lk
    pn = str(store.HOME / "human_renders" / f"lk_{name}_stage_{stage}.png")
    if stage == "profile":   # the nose and chin on a turned view's contours alone (likeness_points 'profile' / 'nose')
        base, cmp, log = lk.fit_profile(name, force=force, save=save)
        rows = [r for r in cmp["rows"] if r.get("kind") == "contour" and r["score"] >= 0]
        lk.focus_sheet(cmp, pn, rows=rows, cols=3)
        return [_png(PILImage.open(pn)), "\n".join(log) + "\n" + lk.table_text({**cmp, "rows": rows}) + f"\npanels: {pn}"]
    rep = lk.fit_stage(name, stage, force=force, save=save, panels=pn)
    out = [rep["text"] + f"\npanels: {pn}"]
    if Path(pn).exists():
        out.insert(0, _png(PILImage.open(pn)))
    return out


@mcp.tool(structured_output=False)
def project_reference(name: str, view: int = 0, save: str = ""):
    """Project fitted reference picture `view` onto the head through its camera and show it from other angles: where it
    smears or slides, the geometry is wrong there. save writes the sheet. Details: guide(topic="project_reference")."""
    from . import likeness_read as lr
    pn = save or str(store.HOME / "human_renders" / f"lk_{name}_projected.png")
    r = lr.project_reference(name, pn, view=view)
    return [_png(PILImage.open(pn)), f"reference {view} projected on {name}; share of each view's head that carries the picture: {r['seen']}\n{pn}"]


@mcp.tool(structured_output=False)
def texture_from_reference(name: str, views: list[int] | None = None, opacity: float = 0.9, delight: bool = True,
                           match: str = "tone", remove: bool = False) -> str:
    """Lay the fitted reference pictures over the head's skin as de-lit paint decals ("ref_texture_<view>"). views,
    opacity, delight, match "tone"|"level"|"", remove=True takes them out. Redo after head shape changes. Details:
    guide(topic="texture_from_reference")."""
    from . import likeness_texture as lt
    r = lt.apply(name, views=views, opacity=opacity, delight=delight, match=match or None, remove=remove)
    st = lt.stale(store.load(name))
    return r["text"] + (f"\nSTALE (made on another head shape, make again): {st}" if st else "")


@mcp.tool(structured_output=False)
def character_read(name: str, tag: str = "", read: dict | None = None, view: str = "", render: bool = False,
                   author: str = "llm"):
    """Stage 0 of likeness: the character read. No read: the form to fill. tag="reference" + read stores the
    reference's read (author="user" for the user's words); render=True gives a sheet for blind reads; tag + read +
    view stores one; tag alone diffs reference vs model. Details: guide(topic="character_read")."""
    from . import likeness_read as lr
    if render:
        pn = str(store.HOME / "human_renders" / f"lk_{name}_read_views.png")
        r = lr.render_views(name, pn)
        return [_png(PILImage.open(pn)), f"views {r['views']}: {pn}\n\n" + lr.form()]
    if read is not None:
        lr.set_read(name, tag or "reference", read, view=view or None, author=author)
        qs = lr.questions(name) if (tag or "reference") == "reference" else []
        return f"stored read '{tag or 'reference'}'" + (f" view {view}" if view else f" by {author}") + \
            ("\nQUESTIONS for the user (their read and the reader's differ; theirs is used):\n" + "\n".join(qs) if qs else "")
    if tag and tag != "reference":
        return lr.diff(name, tag)
    return lr.form()


@mcp.tool(structured_output=False)
def likeness_points(name: str, image: str, points: dict | None = None, lines: dict | None = None, by: str = "",
                    replace: bool = False) -> str:
    """Hand-placed points and lines on a reference picture (full-image px) for what the detector misses: points
    (gonion.R, ear_lobe.R, menton, ...) and lines (jaw.R, neck.R, profile, nose). Merged unless replace; by = who
    placed them. Details: guide(topic="likeness_points")."""
    from . import likeness_shape as ls
    d = ls.set_points(name, image, points, lines, by=by, replace=replace)
    v = next(x for x in d["views"] if x["image"] == image)
    return f"stored for {Path(image).name}: points {sorted(v['points'])}, lines " + \
        ", ".join(f"{k} ({len(q)} points)" for k, q in v["lines"].items())


@mcp.tool(structured_output=False)
def reference_brief(kind: str = "head", subject: str = "") -> str:
    """The shot list and generator prompts for likeness references (kind "head" | "figure", subject). Details:
    guide(topic="reference_brief")."""
    from . import likeness_brief as lb
    return lb.reference_brief(kind, subject)["text"]


@mcp.tool(structured_output=False)
def check_references(images: list[str], name: str | None = None) -> str:
    """What a set of reference pictures can support for the likeness checklist (views, lens, expression, light,
    ears/hairline, identity consistency) and which shots to ask for. name: the model's fitted cameras. Details:
    guide(topic="check_references")."""
    from . import likeness_brief as lb
    return lb.check_references(images, name)["text"]


@mcp.tool(structured_output=False)
def skin_from_reference(name: str, out: str = "", groups: list[str] | None = None, rounds: int = 2, read_only: bool = False,
                        stubble: bool | None = None, anchor: str = "auto", tone: float | dict | None = None,
                        white: list[dict] | None = None, project: bool = False, layers: bool = True) -> str:
    """Set the skin from the model's fitted reference pictures, used as a MEASUREMENT (the photo's pixels never ship):
    project=True first makes the de-lit atlas (skin_project, as a measurement); with an atlas on the model the read
    uses it, and layers=True stores the skin as a STACK OF LAYER MAPS decomposed from it (pigment, redness, periorbital,
    brows, lips, beard, shade: skin.stack). Without an atlas: the per-picture read of tone, zones, lips, beard, brows,
    freckles, folds. read_only=True: the read alone. out: save to a copy. Details: guide(topic="skin_from_reference")."""
    from . import skin_layers, skin_project as spj, skin_read, store
    dst = out or name
    pre = ""
    if project and not read_only:
        a = spj.apply(name, out=out or None, opacity=0.0, log=lambda s: None)
        pre = a["text"] + "\n\n"
        name = dst
    if read_only:
        return skin_read.read(name, anchor=anchor, log=lambda s: None, white=white)["text"]
    has_atlas = skin_read.atlas_source(store.load(name)) is not None
    g = tuple(groups) if groups else (tuple(x for x in skin_read.DEFAULT_GROUPS if x not in ("eyes", "folds")) if has_atlas else skin_read.DEFAULT_GROUPS)
    r = skin_read.apply(name, out=(out or None) if not project else None, groups=g, rounds=rounds,
                        anchor=anchor, stubble=stubble, log=lambda s: None, tone=tone, white=white)
    text = pre + r["text"]
    if layers and has_atlas:
        text += "\n\n" + skin_layers.apply(dst, log=lambda s: None)["text"]
    return text


@mcp.tool(structured_output=False)
def skin_project(name: str, out: str = "", views: list[int] | None = None, remove: bool = False, report_only: bool = False,
                 delight: bool = True, ears: bool = False, mirror: bool = True, tone: str = "model", opacity: float = 0.0,
                 detail_depth: float = 0.00012, parse: str = "mediapipe", eyes: bool = False, stubble: str = "picture") -> str:
    """The fitted reference pictures as a de-lit ATLAS in the head's own texture space (the measurement
    skin_from_reference fits the skin's layer stack to): projected, DE-LIT into albedo, the unseen filled, fine lines as
    relief; saved as skin.projection. opacity 0 (default): nothing of the photo is laid as colour; 1 = "photo skin" (the
    ceiling / a judging overlay). The reply says what was left out and what is ambiguous. out: save to a copy; remove=True takes it out. Details: guide(topic="skin_project")."""
    from . import skin_project as spj
    kw = dict(views=views, delight=delight, ears=ears, mirror=mirror, tone=tone, parse=parse or None, log=lambda s: None)
    if remove:
        return spj.apply(name, out=out or None, remove=True)["text"]
    if report_only:
        return spj.make(name, **kw)["text"]
    return spj.apply(name, out=out or None, opacity=opacity, detail_depth=detail_depth, eyes=eyes, stubble=stubble, **kw)["text"]


@mcp.tool(structured_output=False)
def skin_reference() -> str:
    """Everything the `skin` description takes: zones, tone model, features, wrinkles, hair, scars, tattoos and
    make-up, with keys and defaults. Details: guide(topic="skin_reference")."""
    from . import skin as skinmod
    from . import skin_makeup
    return skinmod.reference() + "\n\n" + skin_makeup.reference()


@mcp.tool(structured_output=False)
def look_skin(name: str, views: list[str] | None = None, size: int = 768, light: str | None = None,
              flat: bool = False, layer: str | None = None, engine: str = "eevee", save: str | None = None):
    """Fast bare-skin close-ups with measurements vs real-skin photos. views (face, three_quarter, cheek, eye, mouth,
    ear, hand, ...), light "studio"|"soft"|"back"|"rake" (low side light: relief), flat (unlit colour), layer (one mask), engine "eevee"|"cycles",
    size, save. Details: guide(topic="look_skin")."""
    from . import skin_look
    sheet, text, _ = skin_look.look(name, views=tuple(views) if views else skin_look.DEFAULT, size=size, light=light,
                                    flat=flat, layer=layer, engine=engine)
    return [_out(sheet, save), text]


def _save_suffix(save: str | None, tag: str) -> str | None:
    if not save:
        return None
    p = Path(save)
    return str(p.with_name(f"{p.stem}_{tag}{p.suffix or '.png'}"))


@mcp.tool(structured_output=False)
def garment_reference(kind: str | None = None, detail: str | None = None, principles: str | None = None) -> str:
    """The clothing knowledge base: kind (one garment kind), detail (one detail's choices), or principles
    ("blocks"|"operations"|"derivations"|<category>|"rules"|"all"); no args = the index. Details:
    guide(topic="garment_reference")."""
    from . import garment_design
    K = garment_design.kb()
    if principles:
        P = K["principles"]
        if principles == "all":
            return json.dumps(P, indent=1)
        if principles in P and not principles.startswith("_"):
            return json.dumps({principles: P[principles], "three_principles": P["three_principles"]}, indent=1)
        if principles in P["derivations"]:
            return json.dumps({principles: P["derivations"][principles], "operations": P["operations"]}, indent=1)
        raise ValueError(f"principles is blocks, operations, derivations, rules, all, or a derivation: "
                         f"{', '.join(k for k in P['derivations'] if not k.startswith('_'))}")
    if kind:
        if kind not in K["kinds"]:
            raise ValueError(f"no kind {kind!r} (have {', '.join(k for k in K['kinds'] if not k.startswith('_'))})")
        srcs = [d for d, v in K["designs"].items() if not d.startswith("_") and kind in v.get("kinds", [v.get("kind")])]
        return json.dumps({"kind": kind, **K["kinds"][kind], "draft_sources": srcs}, indent=1)
    if detail:
        if detail not in K["details"]:
            raise ValueError(f"no detail {detail!r} (have {', '.join(k for k in K['details'] if not k.startswith('_'))})")
        return json.dumps(K["details"][detail], indent=1)
    L = ["kinds: " + ", ".join(f"{k} (fits {'/'.join(v.get('fit', {})) or '-'})" for k, v in K["kinds"].items() if not k.startswith("_")),
         "details: " + "; ".join(f"{d}: {', '.join(c for c in v if not c.startswith('_'))}" for d, v in K["details"].items()
                                 if not d.startswith("_")),
         "fabrics: " + ", ".join(f"{k} ({v.get('gsm')} g/m2, {v.get('stretch')})" for k, v in K["fabrics"].items() if not k.startswith("_")),
         "draft sources: " + "; ".join(f"{d} -> {v['kind']} (can: {', '.join(f'{x}=' + '/'.join(c) for x, c in v['can'].items())})"
                                       for d, v in K["designs"].items() if not d.startswith("_")),
         "targets: " + ", ".join(k for k in K["targets"] if not k.startswith("_")),
         "principles (designing a new garment = block + operations; garment_reference(principles=...)): blocks "
         + ", ".join(K["principles"]["blocks"]) + "; operations " + ", ".join(K["principles"]["operations"])
         + "; derivations " + ", ".join(k for k in K["principles"]["derivations"] if not k.startswith("_")),
         "lessons: " + " | ".join(x["lesson"] for x in K["lessons"])]
    return "\n".join(L)


@mcp.tool(structured_output=False)
def garment_from_reference(name: str, garments: dict, views: list[dict] | str, answers: dict | None = None,
                           save: bool = True) -> str:
    """Read reference art of an outfit into design-sheet patches and a target table. garments {name: kind}, views
    [{image, kind, points, crops}]; without answers: the form; with answers: the patch (not applied) stored in
    cloth_refs.json. save. Details: guide(topic="garment_from_reference")."""
    from . import cloth_reference as cr
    vs = json.loads(views) if isinstance(views, str) else views
    out = cr.read(name, garments, vs, answers, save=(store.HOME / name / "cloth_refs.json") if (save and answers) else None)
    return out["text"]


@mcp.tool(structured_output=False)
def check_garment_reference(name: str, garments: list[str] | None = None, save: str | None = None, top: int = 9):
    """Judge the cached garment sims against the reference reading (cloth_refs.json): ranked misses and a focus sheet.
    garments, top, save. Details: guide(topic="check_garment_reference")."""
    from . import cloth_reference as cr
    import tempfile
    path = store.HOME / name / "cloth_refs.json"
    if not path.exists():
        return f"no reading for {name}: run garment_from_reference first"
    tmp = Path(save) if save else Path(tempfile.mkdtemp()) / "cloth_ref_focus.png"
    out = cr.check(name, garments, path, panels=tmp, top=top)
    return [_out(PILImage.open(out["panels"]), save), out["text"]]


@mcp.tool(structured_output=False)
def garment_reference_brief(garments: dict, subject: str = "a man", outfit: str = "", name: str | None = None,
                            views: list[dict] | None = None) -> str:
    """The shot list (and prompts) for garment reference images; garments {name: kind}, subject, outfit, name (a model
    for the wear state); views = validate a set of pictures instead. Details:
    guide(topic="garment_reference_brief")."""
    from . import cloth_reference as cr
    if views:
        return cr.check_references(views, garments)["text"]
    refs = (store.HOME / name / "cloth_refs.json") if name else None
    b = cr.reference_brief(garments, subject=subject, outfit=outfit, model=name,
                           refs=refs if refs is not None and refs.exists() else None)
    return (b["text"] + "\n\nPROMPTS:\n" + "\n\n".join(f"[{s['id']}] {s['prompt']}" for s in b["shots"])
            + "\n\nNEGATIVE: " + b["common"]["negative"])


@mcp.tool(structured_output=False)
def design_garment(name: str, garment: str, design: dict | None = None, spec: dict | None = None,
                   replace: bool = False, note: str = "") -> str:
    """Clothing stage 1: the design sheet in spec.cloth[garment].design (kind, from or block + ops, fit, fabric,
    details, pattern, notes), merged (replace=True replaces). spec: other garment keys. Returns the resolved sheet,
    failures first. Next: look_pattern. Details: guide(topic="design_garment")."""
    from . import cloth_workflow
    from .hair import merge_patch
    full = store.load(name)
    gs = full.setdefault("cloth", {})
    g = {} if replace else dict(gs.get(garment) or {})
    if design is not None:
        g["design"] = merge_patch(dict(g.get("design") or {}), _spec_arg(design))
    if spec is not None:
        g = merge_patch(g, _spec_arg(spec))
    if not g.get("design"):
        raise ValueError("give the design sheet: design={'kind': ..., 'from': ..., 'details': {...}}")
    gs[garment] = g
    v = store.save(name, full, note or f"design {garment}")
    r = cloth_workflow.run(name, garment, ("design",), images=False)
    return f"saved {name} v{v}\n" + cloth_workflow.text(r) + "\nnext: look_pattern(name, garment)"


@mcp.tool(structured_output=False)
def look_pattern(name: str, garment: str, save: str | None = None):
    """Clothing stage 2: the garment drafted to the body as a flat pattern sheet, with the checks (choices evidenced,
    seam ease, notches, ease vs body), failures first. save. Next: check_garment. Details:
    guide(topic="look_pattern")."""
    from . import cloth_workflow
    res = cloth_workflow.run(name, garment, ("design", "pattern"), images=True)
    ims = [im for r in res for _, im in r["images"]]
    txt = cloth_workflow.text(res)
    if not ims:
        return txt
    return [_out(ims[0], save), txt]


@mcp.tool(structured_output=False)
def check_garment(name: str, garment: str, stages: list[str] | None = None, images: bool = True,
                  save: str | None = None):
    """Clothing workflow checks, failures first. stages (default all): "design", "pattern", "construction", "place",
    "sim". images (pattern sheet, placed start), save. Details: guide(topic="check_garment")."""
    from . import cloth_workflow
    res = cloth_workflow.run(name, garment, tuple(stages or cloth_workflow.STAGES), images=images)
    out = []
    for r in res:
        for tag, im in r["images"]:
            out.append(_out(im, _save_suffix(save, tag)))
    out.append(cloth_workflow.text(res))
    return out if len(out) > 1 else out[0]


# ---------------------------------------------------------------- the garment gates as tools (codified M1-M8)
# The order a garment follows (next_steps.py): pattern -> pattern_check (flat) -> fit_garment (on the form) -> judge
# (clay + diag beside the reference, one view per review_view) -> optional sim, a wrinkle source only -> game mesh.
# Each tool's text ends with the next step the gate rules require, generated from its result.

# diagnostic rows every garment look renders unless told otherwise (gates.md LOOK, codified C13): construction first
# (panel colours, seam / fold lines, turned flaps), then strain + layer pierce
DIAG_DEFAULT = (("panels", "seams", "turned"), ("strain", "layers"))


def _diag_rows(diag) -> list:
    """The diag argument -> rows of modes. None / True: DIAG_DEFAULT; False / []: none; ["strain", ...]: one row;
    [["panels"], ["strain"]]: those rows."""
    if diag is None or diag is True:
        return [list(r) for r in DIAG_DEFAULT]
    if not diag:
        return []
    if all(isinstance(x, str) for x in diag):
        return [list(diag)]
    return [list(r) for r in diag]


def _render_dir(name: str) -> Path:
    d = store.HOME / "_looks" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _garment_box(Xs: list):
    X = np.concatenate([np.asarray(x, float) for x in Xs])
    lo, hi = X.min(0) - 0.08, X.max(0) + 0.08
    c, half = (lo + hi) / 2, np.maximum((hi - lo) / 2, 0.5)
    return c - half, c + half


def _hstack(paths: list) -> PILImage.Image:
    ims = [PILImage.open(p).convert("RGB") for p in paths]
    h = max(im.height for im in ims)
    ims = [im.resize((max(1, int(im.width * h / im.height)), h)) for im in ims]
    out = PILImage.new("RGB", (sum(im.width for im in ims), h), "white")
    x = 0
    for im in ims:
        out.paste(im, (x, 0))
        x += im.width
    return out


def _garment_sheets(name: str, tag: str, body, garments: list, views, size: int, clay: bool, diag) -> tuple:
    """Clay strip and diag sheet of garments [(name, V, mesh dict)] on the body. Returns ([(label, PIL image)],
    the single-view PNGs' folder). Takes the GPU (resources.heavy)."""
    from . import cloth, diag_render, resources
    rows = _diag_rows(diag)
    views = tuple(views or ("front", "three", "side", "back"))
    box = _garment_box([V for _, V, _ in garments])
    d = _render_dir(name)
    objs = [{"name": "body", "V": body.V, "F": body.T, "color": "#c9b8a6"}]
    cols = ["#5b7fa6", "#8a6f4e", "#4e8a6f", "#7a4e8a"]
    for i, (gn, V, M) in enumerate(garments):
        objs.append({"name": gn, "V": np.asarray(V, float), "F": M["F"], "mesh": M, "layer": i,
                     "color": cols[i % len(cols)]})
    out = []
    with resources.heavy(f"mcp {tag} {name}", gb=4, gpu=True):
        if clay:
            pngs = cloth.render(objs, str(d / f"{tag}_clay"), views=views, resolution=size, box=box)
            out.append(("clay", _hstack(pngs)))
        if rows:
            p = diag_render.sheet([(" + ".join(r), objs, {"diag": r}) for r in rows], d / f"{tag}_diag.png", None,
                                  views=views, resolution=size, box=box, aspect=0.62)
            out.append(("diag", PILImage.open(p).convert("RGB")))
        if clay:  # (C100) each garment in its OWN colour (+ woven stripe) under the game light: the colour is judged
            # here, never on the clay strip's fixed identification colours
            pngs = cloth.render(own_colour_objects(name, objs), str(d / f"{tag}_own"), views=views, resolution=size,
                                box=box, textured=True)
            out.append(("own colour", _hstack(pngs)))
    return out, d


def own_colour_objects(name: str, objs: list) -> list:
    """(C100) render objects with each garment's SPEC colour, roughness, sheen and stripe (garment keys color /
    roughness / sheen / stripe {pitch_mm, contrast, duty, dir}) and its pattern uv (the stripe runs on it); the body
    keeps its own. A garment without a spec colour keeps the object's."""
    from . import cloth
    try:
        gs = store.load(name).get("cloth") or {}
    except Exception:  # noqa: BLE001 (no spec: the objects as given)
        gs = {}
    out = []
    for o in objs:
        g = cloth.expanded(gs[o["name"]]) if isinstance(gs.get(o["name"]), dict) else None
        o = dict(o)
        if g:
            o["color"] = g.get("color", o.get("color"))
            for k in ("roughness", "sheen"):
                if g.get(k) is not None:
                    o[k] = float(g[k])
            if isinstance(g.get("stripe"), dict):
                o["stripe"] = dict(g["stripe"])
            if o.get("mesh") is not None and o["mesh"].get("uv") is not None:
                o["uv"] = np.asarray(o["mesh"]["uv"], float)
        out.append(o)
    return out


def _has_reference(name: str, spec: dict) -> bool:
    """A reference to judge against: set_reference images, a plan with views, a garment concept / reading, or a
    head's reference pictures."""
    if (store.refs_dir(name) / "refs.json").exists() or ((spec.get("plan") or {}).get("views")):
        return True
    for g in (spec.get("cloth") or {}).values():
        if isinstance(g, dict) and (g.get("concept") or (g.get("design") or {}).get("concept") or g.get("reference")):
            return True
    return bool((spec.get("base") or {}).get("refs") or spec.get("references") or spec.get("blockin"))


def _gate_rows_text(rec: dict) -> str:
    order = {"FAIL": 0, "UNMEASURED": 1, "PASS": 2, "INFO": 3, "SIM": 4}
    w = rec.get("waived") or {}
    lines = [f"pattern gate {rec.get('model')}:{rec.get('garment')}: {rec['status']}"
             + (" (no reference reading given: refs=...)" if not rec.get("refs", True) else "")]
    for r in sorted(rec.get("rows") or [], key=lambda r: order.get(r["status"], 5)):
        st = "WAIVED" if w.get(r["id"]) else r["status"]
        val = "" if r.get("ours") is None else f" ours {r['ours']}"
        val += "" if r.get("ref") is None else f" ref {r['ref']}"
        lines.append(f"  {st:<10} {r['id']}{val}" + (f": {r['why']}" if r.get("why") and st != "PASS" else ""))
    return "\n".join(lines)


@mcp.tool(structured_output=False)
def pattern_check(name: str, garment: str, refs: str | dict | None = None, waive: dict | None = None,
                  views: list[str] | None = None, size: int = 480, diag: list | bool | None = None,
                  save: str | None = None):
    """THE PATTERN GATE, flat, no sim: measures every checklist item on the drafted + placed pattern, writes the record
    every sim needs (dress refuses without a PASS). Returns the flat pattern sheet, the diag views of the pattern
    on the dress form as the gate read it (default panels+seams+turned; strain+layers; diag=False none), the per-item
    table and the next step.
    refs (reference reading), waive {id: reason}, views, size, save. Details: guide(topic="pattern_check")."""
    from . import cloth_check as cc, next_steps, pattern_sheet
    keep: dict = {}
    rec = cc.pattern_gate(name, garment, refs=refs, waive=waive, log=lambda *_: None, keep=keep)
    res = keep["res"]
    Bp = res["pieces_full"]
    kind = rec.get("kind") or ""
    out = [_out(pattern_sheet.render(Bp, f"{name}:{garment} flat pattern",
                                     seam_rows=cc.seams(Bp, kind)), _save_suffix(save, "flat"))]
    if _diag_rows(diag):
        ims, _ = _garment_sheets(name, f"pattern_{garment}", res["body"], [(garment, res["A"], res["mesh"])],
                                 views, size, clay=False, diag=diag)
        out += [_out(im, _save_suffix(save, tag)) for tag, im in ims]
    out.append(_gate_rows_text(rec) + "\n" + next_steps.after_pattern_check(rec, name, garment))
    return out


@mcp.tool(structured_output=False)
def fit_garment(name: str, garment: str, views: list[str] | None = None, size: int = 560, clay: bool = True,
                diag: list | bool | None = None, force: bool = False, save: str | None = None, styled: bool = True):
    """The garment assembled from its pattern on the body (the dress form), NO sim: clay + diag (default
    panels+seams+turned; strain+layers), strain p99 and layer pierce, and the next step. Refuses until pattern_check
    PASSes (force=True looks anyway, said in the text). Then styled as its kind is worn (C146; styled=False: closed).
    views, size, clay, diag, save. Details:
    guide(topic="fit_garment")."""
    from . import cloth, cloth_check as cc, diag_render, next_steps
    spec = store.load(name)
    if garment not in (spec.get("cloth") or {}):
        raise ValueError(f"no garment {garment!r} (have {', '.join(spec.get('cloth') or {}) or 'none'})")
    from . import pattern_form
    # (fit round 33) the fit IS the gate's placement: its own keys are checked (a layered garment's body is its under
    # garment's form fit, which the sim path's lookup never matched)
    res = pattern_form.on_form(name, garment, spec)
    st = cc.gate_status(name, garment, spec, res=res)
    if not st["passed"] and not force:
        return (f"{garment}: not fitted: {st['why']}\nnext: pattern_check(\"{name}\", \"{garment}\") and fix its rows "
                "first; the form judges a pattern that passed flat (force=True only to look)")
    uf = cc.under_fit_status(name, garment, spec)  # (C85: the under garment fits on its own first)
    if not uf["passed"] and not force and not uf.get("provisional"):
        return (f"{garment}: not fitted: its under garment doesn't fit yet: {uf['why']}\nnext: fit_garment(\"{name}\", "
                f"\"{uf['under']}\") and fix it until its own fit PASSes (tucked, its fullness soft against the body); "
                "never fit an outer garment over an under garment that doesn't fit (force=True only to look)")
    X = res["A"]
    # HOW IT IS WORN, set by hand (C146): the wear's style ops (garment_kb kinds.<kind>.wear.<tie|no_tie>.style) run on
    # the closed fit; a garment that declares its own worn_open (the old fold / pin route) or "style": false skips it
    style_txt = ""
    gx = cloth.expanded(spec["cloth"][garment])
    # (C174: a garment worn open is fitted open (C171) and styled by its kind's "open" wear: the fronts below the break)
    if styled and gx.get("style", True) is not False and (res.get("form_under") is None or gx.get("worn_open")):
        from . import garment_pull as gpl
        Xs, sinfo = gpl.worn_style(res["mesh"], np.asarray(X, float), (np.asarray(res["body"].V, float),
                                   np.asarray(res["body"].T, int)), gx)
        if sinfo is not None:
            X = res["A"] = Xs
            style_txt = "  worn (C146: the wear's style ops on the closed fit): " + "; ".join(
                f"{next(iter(o))} {json.dumps(next(iter(o.values())), default=str)[:90]}" for o in sinfo) + "\n"
            if "collar" in res["mesh"]["names"] and "collar:leftTopEdge" in res["mesh"]["points"]:
                try:
                    style_txt += "  open collar reads (item | target | ours):\n" + "".join(
                        f"    {r['status']} {r['id']} | {r['target']} | {r['ours']}\n" for r in gpl.open_collar_rows(res["mesh"], X))
                except (KeyError, ValueError) as e:
                    style_txt += f"  open collar reads: n/a ({e})\n"
    try:  # THE NECK-SHOULDER LUMP (garrett collar r2): the shoulder seam's crest and the body cloth's bump by the neck point
        from . import garment_pull as gpl
        bvf = (np.asarray(res["body"].V, float), np.asarray(res["body"].T, int))
        nl = gpl.neck_lump_rows(res["mesh"], np.asarray(X, float), bvf)
        if nl:
            style_txt += "  neck-shoulder lump reads (item | target | ours):\n" + "".join(
                f"    {r['status']} {r['id']} | {r['target']} | {r['ours']}\n" for r in nl)
    except (KeyError, ValueError, AttributeError) as e:
        style_txt += f"  neck-shoulder lump reads: n/a ({e})\n"
    validated = cc.form_validated()  # the gate's one form switch (override or pattern_form's passing record)
    how = "assembled on the dress form (pattern_form)"
    under = None
    if res.get("form_under") is not None:
        # on_form's under garment: "A" = its assembled vertices (pressed as the sims press it), "mesh"; the name is
        # the garment key "over"
        u = res["form_under"]
        under = (cloth.expanded(spec["cloth"][garment]).get("over") or "under", u["A"], u["mesh"])
    vis_txt = ""
    if not uf["passed"] and uf.get("provisional") and res.get("form_under") is not None:
        # (C85, fit round 24) the under garment failed only rows about cloth that may be hidden: judged on what shows
        vr = cc.rejudge_under_visible(name, garment, spec, res)
        if not vr["passed"] and not force:
            return (f"{garment}: not fitted: its under garment doesn't fit where it SHOWS under {garment}: {vr['why']}\n"
                    f"next: fit_garment(\"{name}\", \"{uf['under']}\") and fix it until those rows PASS (force=True only "
                    "to look)")
        vis_txt = f"  under garment judged on what shows (C85 visible scope): {vr['why']}\n"
        if vr["passed"]:
            uf = dict(uf, passed=True)
    M = res["mesh"]
    s = diag_render.face_strain(X, M["F"], M["uv"])
    s = s[cc.drawn_faces(res)]  # (a tucked garment: the cloth under the trousers line is not judged)
    p99 = float(np.percentile(s, 99) * 100) if len(s) else None
    pierce = None
    if under is not None:
        from . import garment_game
        pierce = int(garment_game.pierce_faces(under[1], under[2]["F"], X, M["F"]))
    fit_txt = ""
    if under is None:  # (C85: a garment fitted alone writes its own fit record; an outer garment waits for it)
        worn_under = any(cloth.expanded(g_).get("over") == garment for k_, g_ in (spec.get("cloth") or {}).items()
                         if k_ != garment)
        rows = cc.fit_rows(res, X, p99, worn_under, g=spec["cloth"][garment], model=name, garment=garment)
        cc.write_fit_record(name, garment, st["keys"], rows)
        fit_txt = "  own fit (C85): " + "; ".join(f"{r['status']} {r['id']} {r.get('ours')}" for r in rows) + "\n"
    elif not uf["passed"]:
        fit_txt = f"  FORCED: the under garment's own fit has not passed ({uf['why']})\n"
    gs = ([under] if under else []) + [(garment, X, M)]
    ims, d = _garment_sheets(name, f"fit_{garment}", res["body"], gs, views, size, clay=clay, diag=diag)
    txt = (f"{name}:{garment}: {how}{'' if st['passed'] else ' -- FORCED: the pattern gate has not passed'}\n"
           f"  face strain vs the flat pattern: p99 {p99:.1f} %, max {float(s.max() * 100):.1f} % "
           f"(gate <= {next_steps.STRAIN_P99_MAX:g} %)\n"
           f"  layer pierce: {'n/a (no under garment)' if pierce is None else f'{pierce} faces'}\n"
           f"  single views for review_view: {d}\n" + style_txt + fit_txt + vis_txt)
    return [_out(im, _save_suffix(save, tag)) for tag, im in ims] + [
        txt + next_steps.after_fit(name, garment, p99, pierce, validated,
                                   worn_open=bool(cloth.expanded(spec["cloth"][garment]).get("worn_open")))]


@mcp.tool(structured_output=False)
def release_garment(name: str, garment: str, release: list[str] | None = None, submit: bool = False):
    """WORN OPEN = the closed fit + ONE release sim (Joe 2026-10-20): fits the garment CLOSED on the dress form, then
    writes one short cloth job STARTED from that fit (rest = the flat pattern, the closure in `release` (default
    ["front"]) not sewn, the under garment pressed under as a collider, neck pieces held, 2 s of gravity + 1 s settle)
    and preflights it. submit=True runs it (rented when HIFIPUSHIE_GPU=bundle: counts against the $5/day; refused
    without the pattern gate's PASS). Returns the start report, the preflight and, after a run, how far each piece
    moved from the fit. Details: cloth_release's docstring; docs/state/cloth_release.md."""
    from . import cloth_job, cloth_release, cloth_check as cc
    spec = store.load(name)
    if garment not in (spec.get("cloth") or {}):
        raise ValueError(f"no garment {garment!r} (have {', '.join(spec.get('cloth') or {}) or 'none'})")
    st = cc.gate_status(name, garment, spec)
    if not st["passed"]:
        return (f"{garment}: not released: {st['why']}\nnext: pattern_check(\"{name}\", \"{garment}\") first; the release "
                "sim needs the pattern gate's PASS like every sim")
    r = cloth_release.from_form(name, garment, spec, release=tuple(release or ("front",)))
    jd = cloth_release.write(store.HOME / "_cache" / "release" / f"{name}_{garment}" / "sim", r["cfg"], r["arrays"],
                             r["res"]["mesh"]["names"], r["gate"])
    pre = cloth_release.preflight(jd)
    lines = [f"{name}:{garment}: release job {jd}", f"  start: {json.dumps(r['info'], default=str)}",
             f"  preflight ok {pre['ok']}: body {pre['body_mm']:.2f} mm / {pre['body_pairs']} pairs, strain "
             f"{json.dumps({k: v for k, v in pre['strain'].items() if k != 'worst'}, default=str)}"]
    if not pre["ok"]:
        return "\n".join(lines + ["next: the start fails the preflight: fix the fit (strain over the limit = the "
                                  "pattern too small there; pairs = layers through each other), not the solver"])
    if not submit:
        return "\n".join(lines + [f"next: release_garment(\"{name}\", \"{garment}\", submit=True) runs it (one sim)"])
    with cloth_job.submitting():
        d, log_ = cloth_release.run(jd, progress=lambda *_: None, log=lambda *_: None)
    mv = cloth_release.moved(r["res"]["mesh"], r["arrays"]["X"], d["V"])
    still = float(np.abs(d["V"] - d["Vprev"]).max() * 1000) if "Vprev" in d else None
    lines += [f"  moved from the fit (mm per piece): {json.dumps(mv)}", f"  still moving (last 6 frames): {still} mm"]
    return "\n".join(lines + ["next: judge the released result beside the reference (clay + diag, one view per "
                              "review_view); a front that hangs crossed over is a DRAFT balance fault: fix the pattern"])


@mcp.tool(structured_output=False)
def arrange_garment(name: str, garment: str, pins: list[dict], keep: bool = False, pull: float | None = None,
                    release: list[str] | None = None, hold_ring_mm: float = 0.0, submit: bool = False):
    """ARRANGE a worn garment BY HAND (Joe 2026-10-20: as a man settles his coat after sitting): an openness or pose
    physics alone won't give is placed, never drafted or fitted in. The release job (release_garment) plus SOFT pins:
    each pin {"at": "piece:point" | "piece:a..b" (the piece's border between two named points), and "to": [x, y, z]
    | "by": [dx, dy, dz] (+ "by_end" for an edge: blended along it) | "targets": [[x, y, z] per vertex], "name"?}
    pulled to its target over 1 s of gravity (the under garment, real friction), held 1 s, then let go for a 1 s
    settle. Reports per pin how near it got, the SPRINGBACK once let go and the stretch near the pins vs the rest.
    Springback over 10 mm: rerun with keep=True (light pins kept: the result is recorded "placed by hand").
    pull: the pins' spring (default cloth_release.ARRANGE_PULL); hold_ring_mm: also hold the bodice that close to
    the held neck pieces (their seam can't part). submit=True runs it (rented when HIFIPUSHIE_GPU=bundle).
    Details: cloth_release's docstring ("ARRANGE"); docs/state/cloth_release.md."""
    from . import cloth_job, cloth_release, cloth_check as cc
    spec = store.load(name)
    if garment not in (spec.get("cloth") or {}):
        raise ValueError(f"no garment {garment!r} (have {', '.join(spec.get('cloth') or {}) or 'none'})")
    if not pins:
        raise ValueError("pins: at least one {\"at\": ..., \"to\" | \"by\" | \"targets\": ...}")
    st = cc.gate_status(name, garment, spec)
    if not st["passed"]:
        return (f"{garment}: not arranged: {st['why']}\nnext: pattern_check(\"{name}\", \"{garment}\") first; the "
                "arrangement is a sim and needs the pattern gate's PASS like every sim")
    arr_opt = {"keep": bool(keep), **({"pull": float(pull)} if pull is not None else {})}
    r = cloth_release.from_form(name, garment, spec, release=tuple(release or ("front",)), pins=pins,
                                arrange=arr_opt, hold_ring=float(hold_ring_mm) / 1000)
    jd = cloth_release.write(store.HOME / "_cache" / "arrange" / f"{name}_{garment}" / "sim", r["cfg"], r["arrays"],
                             r["res"]["mesh"]["names"], r["gate"])
    pre = cloth_release.preflight(jd)
    lines = [f"{name}:{garment}: arrangement job {jd}", f"  pins: {json.dumps(r['info']['arrange'])}",
             f"  preflight ok {pre['ok']}: body {pre['body_mm']:.2f} mm / {pre['body_pairs']} pairs"]
    if not pre["ok"]:
        return "\n".join(lines + ["next: the start fails the preflight: fix the fit, not the solver"])
    if not submit:
        return "\n".join(lines + [f"next: arrange_garment(..., submit=True) runs it (one sim)"])
    with cloth_job.submitting():
        d, _ = cloth_release.run(jd, progress=lambda *_: None, log=lambda *_: None)
    M = r["res"]["mesh"]
    rep = cloth_release.arranged(M, r["arrays"], d, keep=bool(keep), X_ref=r["arrays"]["X"])
    W, wi = cloth_release.weld_seams(M, d["V"])
    np.savez(jd.parent / "arranged.npz", V=W, Vsim=d["V"], Vheld=d.get("Vheld", d["V"]))
    lines += [f"  arranged: {json.dumps(rep)}", f"  seams after the weld: {json.dumps(wi['after'])}; open: "
              f"{json.dumps(wi['open'][:6])}", f"  result: {jd.parent / 'arranged.npz'} (V welded)"]
    nxt = ("the pins spring back: arrange_garment(..., keep=True) keeps light pins (\"placed by hand\")"
           if rep["status"] == "springs back" else "judge the arranged result beside the reference (clay + diag, one "
           "view per review); check no front through front, no lift, the lapel rolling to its break")
    return "\n".join(lines + [f"next: {nxt}"])


@mcp.tool(structured_output=False)
def style_garment(name: str, garment: str, ops: list[dict], free: list[str] | None = None,
                  hold_below: str | None = None, views: list[str] | None = None, size: int = 560, clay: bool = True,
                  diag: list | bool | None = None, force: bool = False, save: str | None = None):
    """STYLE a worn garment by hand, as people do (C142 / C143): the garment fitted on the form (no sim), then a
    SEQUENCE of ops, each as far as the cloth goes without stretching: {"pull": {"handles": [{"at": "piece:point" |
    "piece:a..b" | [...], "dir": [x,y,z] | side | out | up | down | easy | {"side": 1, "up": 0.3}, "side_from"?,
    "patch"?}]}}, {"turn": {"turns": [{"at", "about": [a, b], "deg", "toward"?}]}}, {"smooth": {"pieces": [...]}},
    {"relax": {}}, {"hold": {"pieces", "within_deg", "of"}}. Earlier grips / holds stay. free (default: the gripped pieces), hold_below ("closure:front").
    Details: guide(topic="style_garment")."""
    from . import cloth_check as cc, garment_pull as gpl, pattern_form
    spec = store.load(name)
    if garment not in (spec.get("cloth") or {}):
        raise ValueError(f"no garment {garment!r} (have {', '.join(spec.get('cloth') or {}) or 'none'})")
    ops = _spec_arg(ops)
    if not ops or not all(isinstance(o, dict) and len(o) == 1 and next(iter(o)) in
                          ("pull", "turn", "smooth", "relax", "hold", "push") for o in ops):
        raise ValueError('ops: a list of {"pull": {"handles": [...]}} | {"turn": {"turns": [...]}} | '
                         '{"smooth": {"pieces": [...]}} | {"relax": {}} | {"hold": {"pieces": [...], "within_deg"?}}')
    st = cc.gate_status(name, garment, spec)
    if not st["passed"] and not force:
        return (f"{garment}: not styled: {st['why']}\nnext: pattern_check(\"{name}\", \"{garment}\") and fix its rows "
                "first; styling starts from the form fit of a pattern that passed flat (force=True only to look)")
    res = pattern_form.on_form(name, garment, spec)
    X_fit, M, body = np.asarray(res["A"], float), res["mesh"], res["body"]
    pid = np.asarray(M["piece"])
    if free is None:
        at = [h["at"] for o in ops for h in (o.get("pull") or {}).get("handles", [])] + \
             [t["at"] for o in ops for t in (o.get("turn") or {}).get("turns", [])]
        free = sorted({M["names"][int(pid[v])] for a in at for v in gpl.vertices(M, a)} |
                      {p for o in ops for p in (o.get("smooth") or {}).get("pieces", [])} |
                      {p for o in ops for p in (o.get("hold") or {}).get("pieces", [])})
    held = gpl.hold_mask(M, X_fit, free, hold_below)
    bvf = (np.asarray(body.V, float), np.asarray(body.T, int))
    Xn, infos = gpl.style(M, X_fit, held, ops, body=bvf)
    lines = [f"{name}:{garment}: styled on the form{'' if st['passed'] else ' -- FORCED: the pattern gate has not passed'}",
             f"  free: {', '.join(free)}; held below {hold_below or '-'} ({int(held.sum())} of {len(X_fit)} vertices held)"]
    stops = []
    for k, op in enumerate(infos):
        (kind, inf), = op.items()
        if kind == "pull":
            stops.append(inf["stopped"])
            lines.append(f"  {k + 1} pull: moved (mm) {json.dumps(inf['moved_mm'])} in {inf['steps']} steps of "
                         f"{inf['step_mm']:g} mm, stopped by {inf['stopped']}; threads p99 start {inf['stretch_p99_start']} "
                         f"/ least {inf['stretch_p99_least']} / end {inf['stretch_p99_end']} % (tol {inf['tol_pct']:g} % "
                         f"over the least), shear p99 {inf['shear_p99_deg'][0]} -> {inf['shear_p99_deg'][1]} deg (lock "
                         f"{inf['shear_lock_deg']}); gripped {json.dumps(inf['gripped'])}")
        elif kind == "turn":
            lines.append(f"  {k + 1} turn: {json.dumps(inf['turns'])}; threads p99 {inf['stretch_p99_start']} -> "
                         f"{inf['stretch_p99_end']} %, shear p99 {inf['shear_p99_deg'][0]} -> {inf['shear_p99_deg'][1]} deg")
        elif kind == "relax":
            lines.append(f"  {k + 1} relax: threads p99 {inf['stretch_p99'][0]} -> {inf['stretch_p99'][1]} %")
        elif kind == "hold":
            lines.append(f"  {k + 1} hold: {inf['held']} vertices kept where they are for the later ops")
        else:
            lines.append(f"  {k + 1} smooth {', '.join(inf.get('pieces') or [inf.get('border', '')])}: {inf['rounds']} rounds, "
                         + (f"roughness p95 {inf['rough_p95_mm'][0]} -> {inf['rough_p95_mm'][1]} mm" if "rough_p95_mm" in inf
                            else f"kink {inf['kink_deg'][0]} -> {inf['kink_deg'][1]} deg")
                         + f", threads p99 {inf['stretch_p99'][0]} -> {inf['stretch_p99'][1]} %")
    crum = {p: [round(float(np.percentile(gpl.crumple(M, X_fit, p), 95)), 3),
                round(float(np.percentile(c, 95)), 3)] for p in free if len(c := gpl.crumple(M, Xn, p))}
    pts = sorted({h["at"] for o in ops for h in (o.get("pull") or {}).get("handles", [])
                  if isinstance(h["at"], str) and ".." not in h["at"]})
    tips = {p: {"fit": gpl.tip_read(M, X_fit, p), "styled": gpl.tip_read(M, Xn, p), "folded": gpl.folded(M, Xn, p)}
            for p in pts}
    out_dir = store.HOME / "_cache" / "style" / f"{name}_{garment}"
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez(out_dir / "styled.npz", V=Xn, V_fit=X_fit)
    lines += [f"  crumple p95, fit -> styled (mm; layered flaps read ~2 in the fit): {json.dumps(crum)}",
              f"  pulled points' tips (crumple / stretch max / twist; folded faces near): {json.dumps(tips)}",
              f"  result: {out_dir / 'styled.npz'} (V; V_fit = the form fit)"]
    if clay or diag is not False:
        ims, d = _garment_sheets(name, f"style_{garment}", body, [(garment, Xn, M)], views, size, clay=clay, diag=diag)
        lines.append(f"  single views for review_view: {d}")
    else:  # (no renders asked: no GPU lock)
        ims = []
    if "max_move" in stops:
        nxt = ("a pull ran to max_move: something it should pull against is free (hold more: free / hold_below / a "
               "turn first), or raise its max_move")
    elif any(t["folded"] > 1 for t in tips.values()):
        nxt = "cloth folds over near a pulled point: grab a bigger patch (handle \"patch\") or pull another way"
    else:
        nxt = ("judge clay + diag beside the reference, one view per review_view; too far or not far enough = change "
               "the direction or what is held, never pin a handle at a coordinate; ripples left = a smooth op")
    return [_out(im, _save_suffix(save, tag)) for tag, im in ims] + ["\n".join(lines) + f"\nnext: {nxt}"]


@mcp.tool(structured_output=False)
def alter_pattern(name: str, garment: str, ops: list[dict], replace: bool = False, note: str = ""):
    """A pattern maker's alteration on the flat pattern (garment key "alter", applied in order): slash_spread, turn,
    move, scale, slit, trim, and where this build has them "true" (a corner trued to 90 deg) and "match" (walk the
    seam: an edge made the length of the edges it's sewn to). Drafted before saving (a bad op saves nothing);
    replace=True replaces the list. Returns the flat sheet, the walked seams and the next step. note. Details:
    guide(topic="alter_pattern")."""
    from . import cloth, cloth_check as cc, next_steps, pattern_sheet
    full = store.load(name)
    gs = full.get("cloth") or {}
    if garment not in gs:
        raise ValueError(f"no garment {garment!r} (have {', '.join(gs) or 'none'})")
    ops = _spec_arg(ops)
    if not isinstance(ops, list) or not all(isinstance(o, dict) and o.get("op") for o in ops):
        raise ValueError('ops is a list of {"op": ..., "piece": ..., ...}')
    g = dict(gs[garment])
    g["alter"] = list(ops) if replace else list(g.get("alter") or []) + list(ops)
    trial = json.loads(json.dumps(full))
    trial["cloth"][garment] = g
    res = cloth.build(cloth._garment_for_sim(g), cloth.model_body(name, trial, g, simulate=False),
                      f"{name}:{garment}", log=lambda *_: None, place_only=True)  # raises on a bad op: nothing saved
    full["cloth"][garment] = g
    v = store.save(name, full, note or f"alter {garment}: " + ", ".join(o["op"] for o in ops))
    Bp = res["pieces_full"]
    kind = cloth.expanded(g).get("design", {}).get("kind") or ""
    rows = cc.seams(Bp, kind)
    lines = [f"saved {name} v{v}: {len(g['alter'])} alteration(s) on {garment}", "walked seams (A | B, mm, ease):"]
    for r in rows:
        lines.append(f"  {'ok ' if r['ok'] else 'BAD'} {r['a']} | {r['b']}: {r['len_a_mm']} / {r['len_b_mm']} "
                     f"({r['ease'] * 100:+.1f} %, {r['kind']})"
                     + (f" notches off {r['notches_off']}" if r["notches_off"] else ""))
    # truing, read as the gate's "truing" row reads it (garment key truing_corners = design corners)
    bad = [j for j in cc.junctions(Bp, corners=tuple(g.get("truing_corners") or ())) if not j["ok"]]
    lines.append(f"truing: {len(bad)} seam end(s) turn > {cc.TRUE_DEG:g} deg"
                 + (": " + "; ".join(f"{j['at']} {j['turn_deg']} deg ({' | '.join(j['seam'])})" for j in bad[:5])
                    if bad else ""))
    im = pattern_sheet.render(Bp, f"{name}:{garment} flat pattern", seam_rows=rows)
    return [_out(im, None), "\n".join(lines) + "\n" + next_steps.after_alter(rows, name, garment)]


REPO = Path(__file__).resolve().parents[2]  # (bin/review, docs/notes: present in a source checkout)


@mcp.tool(structured_output=False)
def review_view(region: str, reference: str, result: str, context: str = "", stage: str = "", not_stages: str = "",
                dry: bool = False, out_dir: str | None = None):
    """An independent blind review of ONE view: one region, one reference crop | one result crop (gates.md LOOK).
    Refuses contact sheets, captions, and numbers / claims in region or context. Runs a fresh reviewer with no context
    (bin/review) -> faults MAJOR / MINOR + VERDICT; dry=True returns the pair image + prompt for an independent agent
    instead. stage / not_stages scope it; out_dir. Details: guide(topic="review_view")."""
    import subprocess
    import tempfile
    from . import next_steps, reviewgate
    for p in (reference, result):
        if not Path(p).exists():
            raise ValueError(f"no image {p}")
    reviewgate.refuse_inputs([reference, result], [region], context)  # (raises InputRefused: the rules broken)
    tool = REPO / "bin" / "review"
    if not tool.exists():
        raise RuntimeError(f"bin/review not found at {tool} (a source checkout of hifipushie has it)")
    out = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="review_", dir=_render_dir("_reviews")))
    cmd = [str(tool), str(out), f"{region}={reference}:{result}"]
    for flag, v in (("--context", context), ("--stage", stage), ("--not", not_stages)):
        if v:
            cmd += [flag, v]
    if dry:
        cmd.append("--dry")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1000)
    if r.returncode == 5:
        raise ValueError(r.stderr.strip() or r.stdout.strip())
    pair = _out(PILImage.open(out / "pair_0.png"), None)
    if dry:
        prompt = (out / "prompt.md").read_text()
        return [pair, f"{prompt}\n\n(pair: {out / 'pair_0.png'})\n" + next_steps.after_review(None, True)]
    text = (out / "review.md").read_text() if (out / "review.md").exists() else r.stdout
    verdict = "PASS" if r.returncode == 0 else "FAIL" if r.returncode == 3 else None
    return [pair, text.strip() + "\n" + next_steps.after_review(verdict, False)]


@mcp.tool(structured_output=False)
def judge_asset(glb: str, head: str | None = None, tag: str | None = None, against: str | None = None,
                only: list[str] | None = None) -> str:
    """bin/judge as a tool: the GLB re-imported and rendered at the validated standard shots (game rig; photo-lit
    face features with head=), feature crops, the render self-checks, and the measures absolute / vs another GLB's
    run (against = the approved build) / vs the head's photos. Refuses to report when a self-check fails. only: crop
    name filters; tag. Heavy (GPU, minutes). Details: guide(topic="judge_asset")."""
    from . import judge
    ref = judge.shots(against, head=head) if against else None
    run = judge.shots(glb, head=head, tag=tag, boxes_from=ref)  # (the same crop boxes as the reference run)
    rep = judge.report(run, ref, head=head, only=only)
    crops = sorted(k for k, v in json.loads((run / "crops.json").read_text()).items() if "file" in v)
    nxt = ("next: judge_asset numbers are measures, not a verdict: review the crops ONE per review_view call, "
           "reference crop beside each" + ("" if against else "; give against=<approved GLB> to measure the change")
           + (f"; blind A/B with controls: bin/judge ab {ref} {run} <out dir> (--dry: one trio per reviewer turn)"
              if ref else ""))
    return (judge.format_report(rep) + f"\n\nrun {run}: {len(crops)} crops in {run / 'crops'}\n" + nxt)


# ---------------------------------------------------------------- terrain

@mcp.tool(structured_output=False)
def set_terrain(name: str, spec: dict | None = None, patch: dict | None = None, note: str = "") -> str:
    """Create (spec) or change (patch, merged; null deletes) a terrain in a level designer's words; builds it and
    returns the report, or questions for the designer as JSON (relay them, don't answer them). Details:
    guide(topic="set_terrain")."""
    from . import terrain_tools as tt
    if spec is None and patch is None:
        raise ValueError("give spec (the whole spec) or patch (changes to merge into it)")
    if spec is not None:
        new = _spec_arg(spec)
    else:
        try:
            base = tt.load(name)
        except ValueError:
            base = {}
        new = tt.merge(base, _spec_arg(patch))
    if "extent" not in new:
        raise ValueError('a terrain needs "extent": [[x0, y0], [x1, y1]] (see guide(topic="terrain"))')
    from . import terrain
    terrain.normalise(new)  # cheap checks (units, named sections) before saving
    if new.get("styles"):
        from . import terrain_style
        terrain_style.resolve(new)  # (style names, keys, sheet overrides: zones are checked when the styles are written)
    prev = tt.load(name) if (tt._dir(name) / "spec.json").exists() else None
    if prev is not None and prev == new:  # (an empty or no-op patch made a new version each time)
        return f"terrain {name}: nothing changed (still v{len(tt.history(name))})\n" + tt.report(name)
    v = tt.save(name, new, note or ("set_terrain" if spec is not None else "patch"))
    try:
        rep = tt.report(name)
    except Exception:  # a spec that doesn't build isn't kept: the version and spec.json go back as they were
        tt.unsave(name, v, prev)
        raise
    return f"saved terrain {name} v{v}\n" + rep


@mcp.tool(structured_output=False)
def check_terrain(name: str) -> str:
    """The terrain's report measured on the built ground (kind, peaks, rivers, basins, walls, passes, sites, routes,
    cover, intent checks, WARNINGS); questions come back as JSON. Details: guide(topic="check_terrain")."""
    from . import terrain_tools as tt
    return tt.report(name)


@mcp.tool(structured_output=False)
def look_terrain(name: str, map: bool = True, masks: bool = False, views: list[dict] | None = None,
                 spec_views: bool = False, size: int = 1100, tiles: bool = False, haze: float | None = 5000.0,
                 light: str | None = None, styles: bool = False):
    """Terrain images: map (hillshade + annotations), masks, perspective views [{name, eye, lift, look, fov, sun}] or
    spec_views, tiles (render the exported tiles), haze, light, styles (swatch sheet), size. Details:
    guide(topic="look_terrain")."""
    from . import terrain, terrain_tools as tt
    from .terrain_world import Questions
    try:
        T = tt.build(name)
    except Questions as q:
        return tt.questions_data(q)
    d = tt._dir(name)
    ver = len(tt.history(name))  # files carry the version they show (a later look doesn't overwrite them)
    out, notes = [], []
    if map:
        im = terrain.map_image(T, px=size)
        out.append(_out(im, str(d / f"map_v{ver}.png")))
        notes.append(f"map: {d / f'map_v{ver}.png'}")
    if masks:
        sheet = terrain.mask_sheet(T)
        if sheet is None:
            notes.append("no cover layers, so no masks")
        else:
            out.append(_out(sheet, str(d / f"masks_v{ver}.png")))
            notes.append(f"masks: {d / f'masks_v{ver}.png'}")
    if styles:
        from . import terrain_style
        sts = terrain_style.resolve(T.spec)
        sheets = [s["sheet"] for s in sts] + ([] if any(s["name"] == "realistic" for s in sts)
                                              else [terrain_style.sheet("realistic")])
        refs = terrain_style.refs_of(T)
        lays = [nm for nm in ("grass", "rock", "sand") if nm in refs]
        p = terrain_style.swatch_sheet(sheets, refs, lays, d / f"styles_v{ver}.png")
        out.append(_out(PILImage.open(p), None))
        notes.append(f"styles sheet: {p}")
        p = terrain_style.season_sheet(sheets, refs, lays, d / f"styles_seasons_v{ver}.png")
        out.append(_out(PILImage.open(p), None))
        notes.append(f"seasons sheet (spring, summer, autumn, winter, snow by the snow numbers): {p}")
        gl = [nm for nm in ("grass", "earth") if nm in refs]
        p = terrain_style.ground_view(sheets, refs, d / f"styles_ground_v{ver}.png", layers=tuple(gl))
        out.append(_out(PILImage.open(p), None))
        notes.append(f"ground as the game shows it (flat cel light, mipmaps, anti-tiling, layer edges; eye level and "
                     f"25 m up): {p}")
        for nm in lays:
            q = terrain_style.transition_strip(sheets, refs, nm, d / f"styles_strip_{nm}_v{ver}.png")
            out.append(_out(PILImage.open(q), None))
            notes.append(f"transition ({nm}, {' -> '.join(st['name'] for st in sheets)}): {q}")
    vs = list(views or []) + (list(T.spec.get("views") or []) if spec_views else [])
    if vs:
        for i, v in enumerate(vs):
            v.setdefault("name", f"view{i + 1}")
            if not re.fullmatch(r"[A-Za-z0-9_\-]+", v["name"]):
                raise ValueError(f"view name {v['name']!r}: letters, digits, _ and - only")
        for v in vs:
            v["name"] = f"{v['name']}_v{ver}"
        if tiles:
            from . import terrain_mesh
            td = d / "tiles"
            if not (td / "manifest.json").exists():
                raise ValueError(f"no tiles for {name!r}: run export_terrain({name!r}, tiles=True) first")
            for v in vs:
                v["out"] = str(d / "views" / f"{v['name']}_tiles.png")
                if isinstance(v.get("eye"), list) and len(v["eye"]) == 2:
                    v["eye"] = [*v["eye"], float(T.height(np.array(v["eye"], float))) + v.get("lift", 1.7)]
                v.setdefault("look", v["eye"])
            (d / "views").mkdir(parents=True, exist_ok=True)
            for pth in terrain_mesh.render_tiles(T, td, vs, haze=haze, light=light,
                                                 textured="styles" if styles else True):
                out.append(_out(PILImage.open(pth), None))
                notes.append(f"view: {pth}")
            notes += json.loads((td / "render_job.json").read_text()).get("notes", [])
            return out + ["\n".join(notes)]
        for pth in terrain.render(T, d / "views", vs):
            out.append(_out(PILImage.open(pth), None))
            notes.append(f"view: {pth}")
        notes += T.view_notes
    return out + ["\n".join(notes)]


def _progress_log(ctx, path: Path):
    """A log for a long job run by a tool: each line appended to `path` (tail it while it runs) and sent to the client
    as an MCP progress notification (when the call carries a progress token; never fails the job)."""
    import re
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    n = [0]

    def log(*a):
        line = " ".join(str(x) for x in a)
        with open(path, "a") as f:
            f.write(line + "\n")
        if ctx is None:
            return
        n[0] += 1
        m = re.search(r"(\d+) / (\d+) done", line)
        try:
            import anyio.from_thread
            first = line.splitlines()[0][:300] if line else ""
            if m:
                anyio.from_thread.run(ctx.report_progress, float(m.group(1)), float(m.group(2)), first)
            else:
                anyio.from_thread.run(ctx.report_progress, float(n[0]), None, first)
        except Exception:
            pass
    return log


@mcp.tool(structured_output=False)
def export_terrain(name: str, size: int | None = None, engine: str | None = None, out_dir: str | None = None,
                   tiles: bool = False, styles_only: bool = False, ctx: Context | None = None) -> str:
    """Write the terrain for an engine: heightmaps, masks, splat weights, trees.csv, meta.json (size, engine
    "unity"/..., out_dir); tiles=True writes seamless glTF mesh tiles with LODs and a manifest instead; styles_only
    writes only the style textures. Details: guide(topic="export_terrain")."""
    from . import terrain_tools as tt
    from .terrain_world import Questions
    try:
        T = tt.build(name)
    except Questions as q:
        return tt.questions_data(q)
    cfg = T.spec.get("export") or {}
    if styles_only:
        from . import terrain_style
        out = Path(out_dir).expanduser() if out_dir else tt._dir(name) / "tiles"
        sec = terrain_style.export_styles(T, out)
        return f"styles written to {out} (styles.json + manifest.json's \"styles\" if it exists)\n" + \
            terrain_style.summary(sec)
    if tiles:
        from . import terrain_mesh
        out = Path(out_dir).expanduser() if out_dir else tt._dir(name) / "tiles"
        try:
            r = terrain_mesh.export_tiles(T, out, log=_progress_log(ctx, out / "export_log.txt"))
        except terrain_mesh.TilesCheckFailed as e:
            # (the export is written and complete: the report, with what failed on top, not a traceback)
            r = e.result
        return terrain_mesh.summary(r)
    path = T.export(Path(out_dir).expanduser() if out_dir else tt._dir(name) / "export",
                    size=size or cfg.get("size"), engine=engine or cfg.get("engine"))
    meta = json.loads((path / "meta.json").read_text())
    files = sorted(str(p.relative_to(path)) for p in path.rglob("*") if p.is_file())
    return (f"exported {name} to {path}: {meta['size'][0]} x {meta['size'][1]}, heights {meta['height_range'][0]:.1f} "
            f"to {meta['height_range'][1]:.1f} m; Unity terrain size {[round(v, 1) for v in meta['unity']['terrain_size']]} "
            f"at {[round(v, 1) for v in meta['unity']['position']]}\nfiles: " + ", ".join(files))


@mcp.tool(structured_output=False)
def terrain_history(name: str, revert_to: int | None = None) -> str:
    """List a terrain's versions or restore one (revert_to; saved as new). name "" lists terrains. Details:
    guide(topic="terrain_history")."""
    from . import terrain_tools as tt
    if not name:
        return json.dumps(tt.list_terrains())
    if revert_to is not None:
        v = tt.save(name, tt.version_spec(name, revert_to), f"revert to v{revert_to}")
        return f"terrain {name} v{v} = v{revert_to}\n" + tt.report(name)
    return "\n".join(f"v{h['version']}  {h['time']}  {h['note']}" for h in tt.history(name))


# ---------------------------------------------------------------- vegetation

@mcp.tool(structured_output=False)
def grow_plant(name: str, spec: dict | None = None, patch: dict | None = None, note: str = "",
               copy_from: str | None = None) -> str:
    """Create (spec) or change (patch, merged; lists replace whole) a plant in botanical words (species, age, seed,
    height, habit, environment, guides, prune, leaves, bark, season, style) and grow it; returns the report.
    copy_from starts from another plant. name only: the stored report; "" lists plants and species. Details:
    guide(topic="grow_plant")."""
    from . import veg_tools as vt
    from . import vegetation
    if not name:
        return json.dumps({"plants": vt.list_plants(), "species": {k: vegetation.preset(k).get("about", "") for k in vegetation.species()}}, indent=1)
    if spec is None and patch is None and not copy_from:
        return vt.report(name)
    exists = (vt._dir(name) / "plant.json").exists()
    prev = vt.load(name) if exists else None
    stats = vt.grown(name)["stats"] if exists else None
    if copy_from:
        base = vt.load(copy_from)
        new = vt.merge(base, _spec_arg(patch)) if patch is not None else base
    else:
        new = _spec_arg(spec) if spec is not None else vt.merge(prev or {}, _spec_arg(patch))
    if prev is not None and prev == new:
        return f"plant {name}: nothing changed (still v{len(vt.history(name))})\n" + vt.report(name)
    v = vt.save(name, new, note=note or (f"copy of {copy_from}" if copy_from else "grow_plant" if spec is not None else "patch"))
    ch = vt.change_note(name, prev if not copy_from else vt.load(copy_from), stats)
    return f"saved plant {name} v{v}" + (f" (a copy of {copy_from})" if copy_from else "") + "\n" + (ch + "\n" if ch else "") + vt.report(name)


@mcp.tool(structured_output=False)
def edit_plant(name: str, ops: list[dict], note: str = "") -> str:
    """Direct the plant like an artist; it regrows around each edit. ops: guide / remove_guide / take_limb, prune /
    remove_prune / clear_prunes, cut (pollard, coppice), dead / clear_dead, envelope, force / clear_forces, set
    {path, value}. Details: guide(topic="edit_plant")."""
    from . import veg_tools as vt
    before, prev = vt.grown(name)["stats"], vt.load(name)
    v = vt.edit(name, ops, note)
    return f"plant {name} v{v}\n" + vt.change_note(name, prev, before) + "\n" + vt.report(name)


@mcp.tool(structured_output=False)
def look_plant(name: str, views: list | None = None, azimuth: float = 0.0, size: int = 640,
               foliage: str | None = None, sheet: bool = False, triangles: int | None = None):
    """Plant images (Blender, 5-40 s): views clay, bare, leaf, far, near, close, under, ground, or a camera; azimuth,
    size, foliage "cards"|"mesh", triangles (as exported), sheet=True (reference sheet). Details:
    guide(topic="look_plant")."""
    from . import veg_tools as vt
    got = vt.look(name, tuple(views or ("clay", "leaf", "far")), azimuth, size, foliage, sheet, triangles)
    out = [_out(PILImage.open(p), None) for _, p in got]
    rep = vt.report(name)
    T = vt.grown(name)
    if triangles and not T.get("clump") and not sheet:  # the budgeted plant's own cards against the ground
        g_, w_ = vt.ground_lines(T, triangles)
        rep += "\n" + "\n".join(g_ + w_)
    out.append(rep + "\n" + "\n".join(f"{k}: {p}" for k, p in got))
    return out


@mcp.tool(structured_output=False)
def look_plants(names: list[str], at: list | None = None, spacing: float | None = None, views: list | None = None,
                azimuth: float = 0.0, size: int = 640, foliage: str | None = None, triangles: int | None = None):
    """Several plants together in one picture: names (or "set#*"), at [[x,y]] or spacing, views, azimuth, size,
    foliage, triangles. Details: guide(topic="look_plants")."""
    from . import veg_tools as vt
    names = [m for n in names for m in (vt.set_names(n[:-2]) if n.endswith("#*") else [n])]
    got = vt.look_group(names, at, spacing, tuple(views or ("far",)), azimuth, size, foliage, triangles)
    out = [_out(PILImage.open(p), None) for _, p in got]
    out.append("\n".join(f"{k}: {p}" for k, p in got))
    return out


@mcp.tool(structured_output=False)
def grow_stand(name: str, spec: dict | None = None, patch: dict | None = None) -> str:
    """A forest stand: a few grown trees per species and role stood many times, with a floor. spec or patch (species,
    age, spacing, size, variants, edge, rows, clearings, paths, floor, lod, haze, light). Returns the forester's
    numbers. name only: the stored stand. Details: guide(topic="grow_stand")."""
    from . import veg_stand
    if spec is not None or patch:
        veg_stand.save(name, spec, patch)
    st = veg_stand.grow(veg_stand.load(name))
    return f"stand {name}\n" + veg_stand.report(st)


@mcp.tool(structured_output=False)
def look_stand(name: str, views: list | None = None, size: int = 720, max_full: int = 25):
    """Pictures of a stand (2-8 min): views inside, aisle, edge, above, canopy or a camera; size, max_full (trees at
    full detail). Details: guide(topic="look_stand")."""
    from . import veg_stand
    from . import veg_tools as vt
    st = veg_stand.grow(veg_stand.load(name))
    stem = str(veg_stand.home() / name / "look")
    r = veg_stand.look(st, tuple(views or ("inside",)), stem, size=size, max_full=max_full)
    out = [_out(PILImage.open(p), None) for _, p in r["files"]]
    out.append("\n".join(f"{k}: {p}" for k, p in r["files"]) + f"\ndrawn: {r['near']} trees at full detail, {r['mid']} mid, {r['far']} far "
               f"({r['meshed']} meshes, {r['triangles_instanced']} triangles instanced), floor {r['floor']}; mesh {r['mesh_s']} s, Blender {r['blender_s']} s\n"
               + veg_stand.report(st, [j["eye"] for j in veg_stand.view_jobs(st, tuple(views or ("inside",)))]))
    return out


@mcp.tool(structured_output=False)
def export_stand(name: str, out_dir: str | None = None, triangles: int | None = None, lods: int = 3, impostor: bool = True) -> str:
    """Export a stand as a forest kit: a GLB per variant (lods, impostor, wind, collision), floor meshes, layout.json.
    out_dir, triangles. Heavy job. Details: guide(topic="export_stand")."""
    from . import veg_stand
    st = veg_stand.grow(veg_stand.load(name))
    out = out_dir or str(veg_stand.home() / name / "export")
    c = veg_stand.export(st, out, triangles, lods, impostor)
    return (f"exported {len(c['variants'])} variants for {c['trees']} trees to {out}\n"
            + "\n".join(f"  {v['name']}: " + "; ".join(f"LOD{q['lod']} {q['triangles']}" for q in v["lods"]) for v in c["variants"])
            + "\nfiles: " + ", ".join(Path(f).name for f in c["files"]))


@mcp.tool(structured_output=False)
def plant_form(name: str = "", species: str = "", cases: list[dict] | None = None, fit: dict | None = None,
               iters: int = 30, seeds: int = 2) -> str:
    """A tree's form across ages and settings, measured as foresters do (height, crown ratio, dbh ...), cases with
    target bands; fit {habit path: [lo, hi]} searches for the least miss (iters, seeds) and saves. Details:
    guide(topic="plant_form")."""
    from . import vegetation
    from . import veg_tools as vt
    spec = vt.load(name) if name else {"species": species}
    if not name and not species:
        raise ValueError("give a plant's name or species=<preset>")
    age = float(vegetation.resolve(spec)["age"])
    if not cases:
        cases = [{"name": f"open, {round(age * k)} y", "age": round(age * k)} for k in (0.2, 0.45, 1.0, 2.0)]
        cases += [{"name": f"stand edge, {round(age)} y", "age": age, "environment": {"setting": "edge", "spacing": 4.0, "open_side": [-1, 0]}},
                  {"name": f"stand interior, {round(age)} y", "age": age, "environment": {"setting": "forest", "spacing": 4.0}}]
    msg = ""
    sd = tuple(range(1, int(seeds) + 1))
    if fit:
        r = vegetation.fit_form(spec, cases, fit, iters=int(iters), seeds=sd)
        if name:
            v = vt.save(name, patch={"habit": r["habit"]}, note="fit to form targets")
            msg = f"fitted v{v}: "
        msg += f"miss {r['miss']} with habit {json.dumps(r['habit'])}\n"
        cs = r["cases"]
    else:
        cs = vegetation.form_cases(spec, cases, sd)
    L = []
    for c in cs:
        m = c["measures"]
        cells = []
        for k in vegetation.FORM_KEYS:
            t = c.get(k)
            cells.append(f"{k} {m[k]:g}" + ("" if t is None else (f" (in {t})" if t[0] <= m[k] <= t[1] else f" MISS {t}")))
        L.append(f"{c.get('name', str(c['age']) + ' y')}: " + ", ".join(cells) + f"; living limbs {m['limbs']:g}; over seeds width +-{c['spread']['width_over_height'] / 2:.2f}, crown +-{c['spread']['crown_ratio'] / 2:.2f}")
    return msg + "\n".join(L) + f"\ntotal miss {vegetation.form_miss(cs):.2f} (0 = every target met)"


@mcp.tool(structured_output=False)
def get_plant(name: str = "", species: str = "") -> str:
    """A plant's own spec, what it resolves to (every value in force), usual ranges and growth steps; read before
    overriding. species alone: that preset resolved. Details: guide(topic="get_plant")."""
    from . import veg_tools as vt
    if not name and not species:
        raise ValueError("give a plant's name, or species=<preset> to see a preset")
    return json.dumps(vt.describe(name or None, species or None), indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))


@mcp.tool(structured_output=False)
def plant_reference(name: str, image_path: str, crop: list[int] | None = None, foot: int | None = None,
                    polygon: list[list[float]] | None = None, tol: float = 30.0, horizon: int | None = None,
                    bare: bool = False, credit: str = "", fit: dict | None = None, fit_iters: int = 40) -> str:
    """Give the plant a reference photo (polygon, or crop + foot + tol + horizon; bare for winter) and measure the
    outline against it; fit {habit path: [lo, hi]} searches habit numbers (fit_iters). credit. Details:
    guide(topic="plant_reference")."""
    from . import veg_tools as vt
    from . import vegetation
    mask = {"polygon": polygon} if polygon else {"crop": crop, "foot": foot, "tol": tol, "horizon": horizon}
    if not polygon and (crop is None or foot is None):
        raise ValueError("give polygon (a traced outline), or crop [x0, y0, x1, y1] + foot (the trunk's x)")
    ref = vt.set_reference(name, image_path, mask, bare, credit)
    msg = ""
    if fit:
        R = vegetation.reference_mask(ref["image"], **ref["mask"])
        dirs = vegetation.photo_branch_directions(ref["image"], ref["mask"]) if bare else None
        r = vegetation.fit_habit(vt.load(name), R, fit, bare=bare, iters=int(fit_iters), directions=dirs)
        v = vt.save(name, patch={"habit": r["habit"]}, note="fit to reference")
        msg = f"fitted v{v}: outline IoU {r['iou']} with habit {json.dumps(r['habit'])}\n"
    return msg + vt.report(name)


@mcp.tool(structured_output=False)
def export_plant(name: str, out_dir: str | None = None, triangles: int | None = None, set: bool = False,
                 lods: int = 1, impostor: bool | str = False, seasons: list[str] | None = None, wet: bool = False,
                 lod_files: bool = False, grade: str = "full") -> str:
    """Export the plant as a GLB (wood + foliage cards, wind channels, collision): triangles (LOD 0 budget), lods,
    impostor (octahedral | "cross"), seasons, wet, lod_files, set (one file for a set), grade "groundcover"; swards
    export as tiles. Details: guide(topic="export_plant")."""
    from . import veg_tools as vt
    from . import veg_export as _ve
    vt_contract = lambda: _ve.CONTRACT
    if set:
        c = vt.export_set(name, out_dir, triangles, lods=lods, seasons=tuple(seasons or ("summer",)), wet=wet)
        return (f"exported {c['path']} ({c['bytes'] / 1e6:.1f} MB): {len(c['plants'])} plants, {c['total']} triangles in all (LOD 0), "
                f"one bark + one foliage material\n" + "\n".join(
                    f"  {q['name']}: {q['height_m']} m, " + "; ".join(f"LOD{l_['lod']} {l_['triangles']}" for l_ in q["lods"]) + " triangles"
                    + (f", {q['floating']:.0%} of the cards floating" if q.get("floating", 0) > 0.2 else "")
                    for q in c["plants"]))
    if vt.grown(name).get("sward"):
        c = vt.export(name, out_dir, seasons=tuple(seasons or ()))
        return (f"exported the sward {name} into {Path(c['path']).parent} (contract {vt_contract()}): "
                + "; ".join(f"LOD{l_['lod']} {l_['triangles']} triangles ({l_['triangles_per_m2']:.0f} per m2, {l_['blades']} blades)" for l_ in c["lods"])
                + f"\na {c['sward']['tile_m']:g} m TILE: lay tiles edge to edge, quarter turns; fade into the terrain's grass texture "
                  f"{c['sward']['fade']['start']}-{c['sward']['fade']['end']} m (recipe + root / tip colours in the seasons json `sward`)\n"
                + "files: " + ", ".join(Path(f).name for f in c["files"]))
    if grade == "groundcover":
        c = vt.export(name, out_dir, seasons=tuple(seasons or ()), grade="groundcover")
        return (f"exported the groundcover grade of {name} into {Path(c['path']).parent} (contract {vt_contract()}): "
                + "; ".join(f"LOD{l_['lod']} {l_['triangles']} triangles ({l_['planes']} cards)" for l_ in c["lods"])
                + f"; clump {c['H']:.2f} m tall, {2 * c['R']:.2f} m across; atlas {c['atlas'][0]} x {c['atlas'][1]} per season\n"
                + "files: " + ", ".join(Path(f).name for f in c["files"])
                + "\nENGINE: import the PNGs without mipmaps, or with them + the mip-scaled alpha (material extras.alpha_mips); "
                  "turn mesh LOD generation off for these files")
    c = vt.export(name, out_dir, triangles, lods=lods, seasons=tuple(seasons or ("summer",)), wet=wet, impostor_lod=impostor,
                  lod_files=lod_files)
    gl = []
    for mesh, g_ in (c.get("ground") or {}).items():
        if g_["under"]:
            gl.append(f"WARNING: {mesh}: {g_['under']} of {g_['vertices']} vertices are under the ground (deepest {g_['max_mm']} mm, "
                      f"median {g_['p50_mm']} mm)")
    ground = ("\nground: in the file, " + ("nothing but the trunk's foot is under it" if not gl else "geometry is under it")
              + "".join("\n" + l_ for l_ in gl)) if c.get("ground") else ""
    ground += ("\nfor engines without MSFT_lod / KHR_materials_variants (Godot 4.7 keeps only LOD 0 of the combined file, drops "
               "nodes outside the scene and drops variants): use the _LOD<k>.glb files (lod_files=True)"
               + (f", {Path(c['collision_file']).name} (its node is named ...-colonly: Godot makes a static body of it)" if c.get("collision_file") else "")
               + (f", {Path(c['seasons_file']).name} (contract version {vt_contract()} + the slot list, then each season's material parameters per slot; `hidden` = don't draw)" if c.get("seasons_file") else ""))
    if impostor == "cross":
        ground += ("\nimpostor: two crossed quads, albedo + normal map per season, lit by the engine like the mesh LODs; ENGINE: its material must not receive "
                   "shadows (Godot: disable_receive_shadows), or the two quads shadow each other into a dark wedge")
    elif impostor:
        ground += ("\nimpostor: hemi-octahedral (one quad + an 8 x 8 atlas of views over the upper hemisphere, object-space normals + depth): it NEEDS "
                   "the engine's impostor shader (recipe in the impostor material's extras.hifipushie_impostor and the seasons json `impostor`; "
                   "Godot: spikes/godot_veg/impostor_octa.gdshader, extra_cull_margin = size / 2); no shadows received on it. "
                   "Import the impostor atlases WITH mipmaps (Godot: mipmaps/generate=true; the normal atlas as plain RGBA, "
                   "not a normal map: its alpha is the depth): without mips a far impostor costs ~40x more GPU time")
    if c.get("style"):
        from . import veg_style
        ground += "\n" + "\n".join(veg_style.lines(c["style"]) + veg_style.warnings(c["style"]))
    return (f"exported {c['path']} ({c['bytes'] / 1e6:.1f} MB), {c['total']} triangles"
            + (f" for a budget of {triangles}" if triangles else "") + f": wood {c['wood_triangles']} triangles"
            + (f" (wood thinner than {c['wood_min_radius_m'] * 1000:.0f} mm left out)" if c["wood_min_radius_m"] else "")
            + f", foliage {c['foliage_triangles']} triangles"
            + (f" ({c['twigs_kept']:.0%} of the twigs, drawn larger)" if c["twigs_kept"] < 1 else "")
            + (f", atlas {c['atlas_px']} px" if "atlas_px" in c else "")
            + ("\nLODs: " + "; ".join(
                f"LOD{l_['lod']} {l_['triangles']} triangles" + (" (impostor)" if l_.get("impostor") else "")
                + (f", under {l_['switch_below_screen_height']:.0%} of the screen's height" if l_.get("switch_below_screen_height") else "")
                for l_ in c["lods"]) if len(c["lods"]) > 1 else "")
            + (f"\nvariants: {', '.join(c['variants'])}" if c["variants"] else "")
            + f"\nwind: TEXCOORD_1 (trunk, branch), TEXCOORD_2 (phase, flutter), _WIND; collision: {c['collision_capsules']} capsules"
              f" + a {c['collision_triangles']}-triangle mesh"
            + ground
            + (f"\nfiles: {', '.join(Path(f).name for f in c['files'])}" if len(c["files"]) > 1 else "")
            + (f"\nWARNING: {c['over']} triangles over the budget: the wood alone needs {c['wood_triangles']} "
               f"(a trunk and its main limbs can't go lower); raise the budget" if c["over"] else "")
            + (f"\nWARNING: {c['floating']:.0%} of the cards have no drawn wood near them (they will float): raise the budget"
               if c.get("floating", 0) > 0.2 else "")
            + ("\nWood you marked (dead wood, drawn guides) is kept down to a quarter of that girth." if triangles else "")
            + (f"\nLook at it before using it: look_plant(name, views=['leaf', 'far'], triangles={triangles}); "
               f"wind_plant(name) renders it swaying" if triangles else ""))


def _wind_disp(d: dict, height: float) -> str:
    """The clip's motion in metres, with what it should be."""
    if not d:
        return ""
    f = lambda k: f"{d[k]['mean_m'] * 100:.1f} cm mean / {d[k]['max_m'] * 100:.1f} cm most" if k in d else "none found"
    out = (f"moved, measured on the vertices: foot {f('foot')}; trunk top {f('trunk_top')}; limb ends {f('limb_ends')}; "
           f"leaf tips {f('leaf_tips')}")
    if "limbs_in_step" in d:
        out += f"; limbs in step {d['limbs_in_step']} (1 = all swing together, a board; 0.2-0.7 reads as a tree)"
    warn = []
    if d.get("foot", {}).get("max_m", 0) > 0.01:
        warn.append("WARNING: the foot moves (trunk channel not 0 at the ground)")
    if height and d.get("trunk_top", {}).get("max_m", 0) > 0.06 * height:
        warn.append("WARNING: the trunk's top swings more than 6% of the height: rubber; lower strength")
    if d.get("limb_ends", {}).get("max_m", 1) < 0.01:
        warn.append("WARNING: limb ends move under 1 cm: the tree stands frozen; raise strength")
    return out + ("\n" + "\n".join(warn) if warn else "") + "\n"


@mcp.tool(structured_output=False)
def wind_plant(name: str, triangles: int | None = 20000, seconds: float = 4.0, strength: float = 1.0,
               wind_from: float = 270.0, azimuth: float = 0.0):
    """Sway the exported plant from its own wind channels as a game would: a six-frame strip + mp4. triangles, seconds,
    strength (0.3 breeze .. 2 gale), wind_from (bearing), azimuth. Details: guide(topic="wind_plant")."""
    from . import veg_tools as vt
    r = vt.wind(name, triangles, seconds, 12, strength, wind_from, azimuth)
    imp = [o for o in r["import"]["objects"] if o.get("type") == "MESH"]
    txt = (f"wind: {r['n']} frames at 12 fps -> {r.get('mp4', '(no ffmpeg: frames in ' + r['frames'] + ')')}\nstrip: {r['strip']}\n"
           f"{r['moved_share']:.0%} of the picture changes against frame 0 (mean over the clip)\n"
           + _wind_disp(r["import"].get("displacement") or {}, r.get("height", 0.0)) +
           f"Blender {r['import']['blender']} import of {Path(r['glb']).name}: " + "; ".join(
               f"{o['name']} {o['triangles']} triangles, uv sets {len(o['uv_layers'])}, attributes {o['attributes'] or 'none'}"
               + (f", _WIND vs uv differ by {o['wind_custom_vs_uv_max_diff']}" if "wind_custom_vs_uv_max_diff" in o else "")
               for o in imp))
    return [_out(PILImage.open(r["strip"]), None), txt]


@mcp.tool(structured_output=False)
def sync_plant(name: str, pull_only: bool = False) -> str:
    """Round-trip the plant through plant.blend: guide/limb curve edits come back into the spec, then the file is
    rewritten (pull_only skips that). Details: guide(topic="sync_plant")."""
    from . import veg_tools as vt
    before, prev = vt.grown(name)["stats"], vt.load(name)
    if pull_only:
        came, head = vt.pull(name), ""
    else:
        r = vt.sync(name)
        came = r["pulled"]
        head = (f"wrote {r['blend']} ({r['guides']} guide curves, {r['limbs']} limb curves"
                + (", the running Blender reloaded it" if r["live"] else "") + ")\n")
    if not came:
        return head + "nothing was changed in Blender since the last sync"
    return head + "from Blender:\n" + "\n".join(f"  {c}" for c in came) + "\n" + vt.change_note(name, prev, before) + "\n" + vt.report(name)


@mcp.tool(structured_output=False)
def plant_history(name: str, revert_to: int | None = None) -> str:
    """List a plant's versions, or restore one (revert_to; saved as a new version). Details:
    guide(topic="plant_history")."""
    from . import veg_tools as vt
    if revert_to is not None:
        v = vt.revert(name, revert_to)
        return f"plant {name} v{v} = v{revert_to}\n" + vt.report(name)
    return "\n".join(f"v{h['version']}  {h['note']}" for h in vt.history(name))


@mcp.tool(structured_output=False)
def heavy_status() -> str:
    """Who holds the machine's heavy-job memory and who waits (every session): running jobs with GB, pid, start,
    directory; the queue in serving order and why each waits. Details: guide(topic="heavy_status")."""
    from . import resources
    return resources.status_text()


@mcp.tool(structured_output=False)
def heavy_queue() -> str:
    """The heavy-job queue without host details: running and waiting jobs (kind, GB, minutes, why it waits), your
    session's marked "<- yours". Fast; changes nothing. Details: guide(topic="heavy_queue")."""
    from . import resources
    return resources.queue_text()


@mcp.tool(structured_output=False)
def make_clutter(kind: str = "", style: str = "realistic", out_dir: str | None = None, seed: int = 1, variants: int | None = None,
                 form: dict | None = None, paint: dict | None = None, color: list | None = None, moss: float | None = None,
                 lods: list | None = None, look: bool = False):
    """Make a terrain clutter asset (boulder, river_rock, cobbles, slab, driftwood, bush, litter; "" lists them) in a
    style (realistic|blobby|anime|cartoon|pixar): GLB variants with LODs, one atlas, a seasons json. form / paint /
    color / moss overrides, seed, variants, lods, out_dir, look=True for a sheet. Details:
    guide(topic="make_clutter")."""
    from . import clutter as ck
    if not kind:
        return json.dumps({"kinds": {k: json.loads((ck.HERE / "clutter_presets" / f"{k}.json").read_text()).get("about", "") for k in ck.presets()},
                           "styles": {s_: ck.style_sheet(s_).get("about", "") for s_ in ck.styles()}}, indent=1)
    spec = {"kind": kind, "style": style, "seed": seed}
    for k_, v_ in (("variants", variants), ("form", form), ("paint", paint), ("color", color), ("moss", moss), ("lods", lods)):
        if v_ is not None:
            spec[k_] = v_
    st = ck.style_sheet(style)["name"]
    sh = ck.SHORT.get(st, st)
    out = Path(out_dir) if out_dir else store.HOME / "clutter" / f"{sh}_{kind}"
    J = ck.export(spec, out, stem=f"ck_{kind}_{sh}")
    text = f"wrote {out}\n" + ck.report(J)
    if not look:
        return text
    png = out / "look.png"
    ck.look(out, str(png))
    return [Image(data=png.read_bytes(), format="png"), text]


@mcp.tool(structured_output=False)
def look_clutter(folders: list[str], season: str = "summer", clay: bool = False, scale: float = 1.0, save: str | None = None):
    """A sheet of exported clutter folders at 2.5 / 10 / 40 m with LODs. season, clay, scale, save. Details:
    guide(topic="look_clutter")."""
    from . import clutter as ck
    png = Path(save) if save else Path(folders[0]) / f"look_{season}.png"
    ck.look(folders, str(png), scale=scale, clay=clay, season=season)
    return [Image(data=png.read_bytes(), format="png"), f"saved {png}"]


@mcp.tool(structured_output=False)
def clutter_kit(out_dir: str, kinds: list[str] | None = None, styles: list[str] | None = None) -> str:
    """Export every clutter kind in every style into out_dir plus clutter.json (kind -> folder per style). kinds,
    styles. Details: guide(topic="clutter_kit")."""
    from . import clutter as ck
    lines = []
    K = ck.kit(out_dir, kinds, styles, progress=lines.append)
    M = json.loads((Path(out_dir) / "clutter.json").read_text())
    miss = {k: v["missing"] for k, v in M["kinds"].items() if v["missing"]}
    return f"{len(K)} folders in {out_dir}; manifest clutter.json" + (f"; missing: {miss}" if miss else "") + "\n" + "\n".join(lines)


_register_toolsets()


def main():
    mcp.run()


def import_main():
    """hifipushie-import FILE [NAME]: save a spec JSON file (e.g. examples/goblin.json) as a model."""
    import sys
    args = sys.argv[1:]
    if not 1 <= len(args) <= 2 or args[0] in ("-h", "--help"):
        sys.exit("usage: hifipushie-import FILE.json [NAME]   (NAME defaults to the file's name)")
    src = Path(args[0])
    name = args[1] if len(args) > 1 else src.stem
    print(put_model(name, json.loads(src.read_text()), f"imported from {src.name}").split("\n")[0],
          f"-> {store.HOME / name}")


if __name__ == "__main__":
    main()
