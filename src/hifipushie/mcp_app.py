"""The MCP app: the server object and its instructions, the tool decorator (a tool's exception reaches the caller as
its text), the registry of every tool with its domain (TOOL_GROUPS), and native registration of the core.
Tools are defined in tools_<domain>.py; server.py gathers them and starts the server."""
from __future__ import annotations

from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import skin_route

INSTRUCTIONS = """\
hifipushie models characters, creatures, props and environments as a skeleton (joints + bones) with SDF blobs hung
on it, smooth-blended into one surface, meshed and rendered for you to look at; hair, cloth, realistic humans,
terrain, plants and clutter have their own tools.
Call `guide` once before modelling: the playbook (stages, the spec format, strokes, parts, paint, what goes wrong).
find_tool("<job>") finds any tool; guide(topic=<tool name>) gives any tool's full parameters.

Conventions: metres, Blender axes: Z up, the creature FACES -Y, its left side is +X. Names ending ".L" are mirrored
to ".R" across X: store only the centre line and the left side.
Spec keys (every field in the guide and kit_reference): joints {name: {pos, r}}, bones {name: {a, b, r_a, r_b, ...}}
(round cones), blobs {name: {at, size, rot, offset, shape, ...}} (ellipsoids, blades), kits (hand, face, foot),
anatomy, parts, strokes (sculpting on the surface), paint (colour layers and masks), prefabs/instances, story and
weather, plan, base (realistic humans start here, not from blobs), hair, cloth, skin.
Workflow: plan (set_plan) -> blockout (put_model, fit) -> secondary forms (strokes) -> detail -> history (story) ->
paint; check and look after each stage. Every change is checkpointed (history / revert).

Tools: a small core is native; every other tool (plan, scene, export, human, likeness, hair, cloth, terrain,
plants, clutter) runs through call_tool(name, args): find_tool("what you want to do") names the tool with its
parameters and an example call; find_tool("") lists every tool by domain. Domains have a guide topic (hair,
cloth, skin, human, block_in, likeness, terrain, vegetation, clutter): read it before working there.
A person's head from pictures: the artist block-in (guide topic block_in) is the default.
Clothes: garment_plan (read, parts, style plan) -> body_tape -> garment_toile (step 4: the garment's 3D surface on the
body; drape first: then 5 mark, 6 cut and flatten, whose flat gate is draft_pattern's)
-> chain_garment (the only way a garment is built: the pattern's own lengths, in the planned state) -> garment_details ->
look_chain beside the reference -> export_garment. garment_record shows every step. Never tune anything; a fault is fixed
where its step says. guide(topic="cloth").
Judge every result beside its reference before forwarding it; reviews are review_view, ONE view per call. Tool texts
end with "next:": do what it says. Traps: guide(topic="traps"). Terrain tools may return questions for the designer:
ask them, don't answer them yourself.
"""

mcp = MCPServer("hifipushie", instructions=INSTRUCTIONS)


def _error_text(e: BaseException) -> str:
    """What the caller needs to fix a failed call: the exception's type and message, and for anything that
    isn't a ValueError (our anticipated spec/argument errors) where it was raised."""
    text = f"{type(e).__name__}: {e}"
    fn = getattr(e, "filename", None)
    if isinstance(e, FileNotFoundError) and fn and not Path(str(fn)).expanduser().is_absolute():
        # (a blind modeller gave "refs/painting.png" from its own folder: paths are read where the server runs)
        return (f"{text}. A path is read from the modelling server's own folder ({Path.cwd()}), not yours: give the "
                "file's full path (starting with /).")
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
                            from . import head_route
                            return head_route.with_next(fn, a, k, fn(*a, **k))
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
            if _reg is not None:  # another registry (tests): registered at once
                register(run)
                return fn
            # Only the core is registered natively (`_register_core`); every tool is reachable by call_tool.
            _TOOLS[fn.__name__] = (register, run)
            _FUNCS[fn.__name__] = fn
            if _STARTED:  # a tool defined after start-up (a plugin module, a test's extra tools): native at once
                _register(fn.__name__)
            return fn  # module-level name stays the plain function (tests and scripts call it directly)
        return deco
    return tool


mcp.tool = _tool_with_errors()

# A small native core + find_tool + call_tool. MCP clients don't refresh their tool list mid-session (a trial agent
# called enable_toolset("cloth,human") and never saw the tools), and 100+ schemas cost context on every turn. So the
# server registers only CORE natively; find_tool searches every tool and call_tool runs any of them (C-row in
# docs/notes/codified.md). TOOL_GROUPS is grouping metadata only (find_tool's domains); every tool is in exactly one.
# A domain may say what it makes (`subject` words) and where a job in it starts (`steps` in order, or one `entry`
# tool): find_route.py reads a job's domain from the subject words alone, never from a stray word match (C400).
_TOOLS: dict[str, tuple] = {}  # name -> (register, wrapped coroutine), filled by the decorator


_FUNCS: dict[str, object] = {}  # name -> the plain function (find_tool reads its docstring and signature)


TOOL_GROUPS: dict[str, dict] = {
    "core": {"about": "native tools: models, specs, look, check, measure, history, the guide, find / call any tool",
             "tools": ["guide", "find_tool", "call_tool", "list_models", "get_model", "kit_reference", "put_model",
                       "edit_model", "look", "check", "measure", "history", "revert", "review_view"]},
    "plan": {"about": "plans, reference images, compare, silhouette fit, clearance, style check",
             "tools": ["set_plan", "set_reference", "compare", "fit", "clearance", "style_check"]},
    "concept": {"about": "match a concept image: fit its camera, render from it pixel-aligned, same-box feature tiles "
                         "for review_view, how parts join the body (stalk or base)",
                "tools": ["fit_concept_camera", "look_matched", "feature_tiles", "join_report", "fit_matched"]},
    "reshape": {"about": "reshape what is already there, as a modeller's hands do: work two masses into one flowing "
                         "mass, take hold of clay in a flat view and move it, cut clay away along a line (a flat "
                         "face) or take one shape out of another (a boolean: a mouth, a socket), bend a mass along a path, make a flap that "
                         "folds over (an ear)",
                "tools": ["fuse", "grab", "trim", "carve", "flap", "bend"]},
    "features": {"about": "sculpt from reference pictures: read a picture's views, patches and form lines, name its "
                          "features as marks on it (the feature map), build the masses from their marks, measure a "
                          "model feature by feature",
                 "subject": "feature features turnaround",
                 "tools": ["read_reference", "look_beside", "mark_features", "build_masses", "build_forms", "feature_report", "review_part", "study_part"]},
    "scene": {"about": "the Blender scene (sync, pull) and the heavy-job queue",
              "tools": ["sync", "pull", "heavy_status", "heavy_queue"]},
    "export": {"about": "OBJ export, game-ready assets (GLB/FBX, PBR maps), the export rig, judging a GLB",
               "tools": ["export", "export_asset", "rig", "judge_asset"]},
    "texrepaint": {"subject": "texrepaint repaint retexture decal hallucination",
                   "about": "redo a generated texture (concept -> point cloud -> retopo bakes) like a texture artist: "
                            "regions and materials, the concept as authority, 4K maps, graphics redrawn as decals",
                   "workflow": "texrepaint_start -> texrepaint_regions -> texrepaint_paint (texrepaint_look to point at "
                               "kept details) -> texrepaint_face + texrepaint_decal (graphics) -> texrepaint_render",
                   "steps": ["texrepaint_start", "texrepaint_regions", "texrepaint_paint", "texrepaint_face",
                             "texrepaint_decal", "texrepaint_render"],
                   "tools": ["texrepaint_start", "texrepaint_regions", "texrepaint_paint", "texrepaint_look",
                             "texrepaint_face", "texrepaint_decal", "texrepaint_render"]},
    "human": {"subject": "human humanoid man woman boy girl actor actress", "entry": "human",
              "about": "realistic humans: the base body, the artist block-in of a head from pictures (the default), "
                       "measurements, fits, skin",
              "tools": ["human", "measure_human", "fit_human", "nudge_human", "human_reference", "block_in_start",
                        "block_in_look", "block_in_step", "block_in_solve", "block_in_expression", "set_expression", "lid_read", "eye_ruler", "face_ruler", "lip_read", "gnm_controls"]},
    "skin": {"about": "a human's skin: description, measured from the reference pictures, close looks beside them",
             "subject": skin_route.FIND_WORDS, "workflow": skin_route.ROUTE, "steps": skin_route.STEPS,
             "tools": ["skin", "skin_from_reference", "brow_read", "look_skin", "skin_reference", "skin_project"]},
    "likeness": {"about": "matching a real person's face and look from reference pictures",
                 "tools": ["likeness", "fit_likeness", "likeness_points", "character_read", "project_reference",
                           "texture_from_reference", "reference_brief", "check_references"]},
    "hair": {"subject": "hair hairstyle haircut beard moustache mustache ponytail braid fringe",
             "about": "hair: strand grooms, tied styles, stylised locks, look, reference, export",
             "workflow": "Hair: describe it in words -> hair_from_reference (the start) -> tie_hair (tied) or groom_hair "
                         "(loose, short) -> look_hair -> export_asset ships the character (export_hair: the hair alone)",
             "steps": ["hair_from_reference", "tie_hair", "groom_hair", "look_hair", "export_hair"],
             "tools": ["groom_hair", "tie_hair", "look_hair", "hair_reference", "hair_from_reference", "export_hair"]},
    "cloth": {"subject": "clothes clothing cloth garment outfit costume dress sew drape tailor fabric shirt blouse tee hoodie "
                         "sweater jacket trousers jeans skirt cloak robe",
              "workflow": "Clothes: garment_plan (read, parts, style) -> body_tape -> garment_toile (step 4, the 3D surface on the body) -> garment_mark (step 5, the seams on it) -> garment_cut (step 6, cut and flattened: the flat pattern) -> draft_pattern (your own FreeSewing design + its flat gate) -> chain_garment (the only way a garment "
                          "is built) -> garment_details -> look_chain beside the reference -> garment_appearance -> export_garment; garment_record shows every step",
              # the workflow's order (find_tool ranks a matched domain's early steps first)
              "steps": ["garment_plan", "body_tape", "garment_toile", "garment_mark", "garment_cut", "draft_pattern", "chain_garment", "garment_details", "look_chain", "garment_appearance", "export_garment"],
              "about": "garments: design, pattern, the pattern gate, alterations, the chain build (the only start), references",
              "tools": ["garment_plan", "body_tape", "garment_toile", "garment_mark", "garment_cut", "draft_pattern", "pattern_parts", "pattern_check", "chain_garment", "garment_details",
                        "look_chain", "garment_appearance", "export_garment", "garment_record"]},
    "terrain": {"subject": "terrain landscape mountain valley river hill island lake coast canyon heightmap",
                "entry": "set_terrain", "about": "terrain and game levels (height fields in a level designer's words)",
                "tools": ["set_terrain", "check_terrain", "look_terrain", "export_terrain", "terrain_history"]},
    "plants": {"subject": "plant tree shrub grass flower fern forest vegetation foliage", "entry": "grow_plant",
               "about": "trees and plants (grown, measured, exported), stands of them, wind",
               "tools": ["grow_plant", "edit_plant", "get_plant", "look_plant", "look_plants", "plant_form",
                         "plant_reference", "export_plant", "wind_plant", "sync_plant", "plant_history",
                         "grow_stand", "look_stand", "export_stand"]},
    "hardsurf": {"subject": "hardsurface hardsurf vehicle kart machine lathe",
                 "workflow": "Hard surface from the point cloud (a fused concept sculpt -> clean fitted parts): "
                             "hardsurf_start -> hardsurf_frame -> read (hardsurf_look, hardsurf_vote) -> hardsurf_fit each "
                             "part (turned / sweep / outline_tube / ring / trace / part) -> hardsurf_build -> hardsurf_check "
                             "-> hardsurf_bake -> hardsurf_rig (rigid joints) ; hardsurf_disagree for every call",
                 "steps": ["hardsurf_start", "hardsurf_frame", "hardsurf_fit", "hardsurf_build", "hardsurf_check",
                           "hardsurf_bake", "hardsurf_rig"],
                 "about": "props, vehicles, furniture, buildings from a fused point-cloud sculpt: fit primitives "
                          "(never press), bake colour from the point cloud's renders, rigid rig with numeric tests",
                 "tools": ["hardsurf_start", "hardsurf_frame", "hardsurf_look", "hardsurf_vote", "hardsurf_fit",
                           "hardsurf_build", "hardsurf_check", "hardsurf_bake", "hardsurf_rig", "hardsurf_disagree"]},
    "retopo": {"subject": "retopo retopology retopologise retopologize topology cage fused pointcloud",
               "workflow": "Artist retopo (a fused concept sculpt -> a game character): retopo_start -> study "
                           "(retopo_look, retopo_slices, retopo_measure) -> eyes / props (retopo_fit, "
                           "retopo_fit_cylinder, retopo_primitives) -> retopo_cage (your cage as code) -> retopo_press -> "
                           "retopo_bake -> retopo_fill -> retopo_assemble -> retopo_armature -> retopo_rom -> retopo_lod -> "
                           "retopo_report",
               "steps": ["retopo_start", "retopo_slices", "retopo_cage", "retopo_press", "retopo_bake", "retopo_fill",
                         "retopo_assemble", "retopo_armature", "retopo_rom", "retopo_lod", "retopo_report"],
               "about": "artist-style retopology of a fused concept sculpt (oxidegen make_point_cloud): your own cage of "
                        "loops, pressed, baked, rigged and range-of-motion checked",
               "tools": ["retopo_start", "retopo_look", "retopo_slices", "retopo_measure", "retopo_check", "retopo_fit", "retopo_fit_cylinder", "retopo_primitives", "retopo_cage", "retopo_press", "retopo_bake", "retopo_fill", "retopo_assemble", "retopo_compare", "retopo_armature", "retopo_rom", "retopo_lod", "retopo_report"]},
    "clutter": {"subject": "clutter rock boulder pebble log driftwood litter debris", "entry": "make_clutter",
                "about": "ground clutter kits (rocks, logs, leaves ...) for terrain",
                "tools": ["make_clutter", "look_clutter", "clutter_kit"]},
}
CORE: list[str] = TOOL_GROUPS["core"]["tools"]
_STARTED = False  # set once the core is registered


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


def _register(t: str):
    """Register one tool with the MCP server: its docstring dedented, its schema compacted."""
    import inspect
    register, run = _TOOLS[t]
    register(run)
    tool = mcp._tool_manager._tools[t]
    tool.description = inspect.cleandoc(tool.description)
    tool.parameters = _compact_schema(tool.parameters)


def enable_all() -> list[str]:
    """Every tool native (in-process users of the registry: the oxidegen artist and its worker)."""
    added = [t for t in _TOOLS if t not in mcp._tool_manager._tools]
    for t in added:
        _register(t)
    return added


def _register_core():
    """Called once all tools are defined: register the core natively; the rest stay reachable via call_tool."""
    global _STARTED
    for t in CORE:
        _register(t)
    _STARTED = True
