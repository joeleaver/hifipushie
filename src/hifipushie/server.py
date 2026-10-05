"""hifipushie MCP server: skeleton-and-blob creature modeling with clay-render feedback."""

from __future__ import annotations

import io
import json
import re
import shutil
from pathlib import Path

import numpy as np
from mcp.server.mcpserver import Image, MCPServer
from PIL import Image as PILImage

from . import compare as cmp
from . import fit as fitmod
from . import measure as meas
from . import paint as paintmod
from . import plan as planmod
from . import render, store, surface
from .spec import empty_spec, summarize

INSTRUCTIONS = """\
hifipushie models characters and creatures as a skeleton (joints + bones) with SDF blobs hung on it,
smooth-blended into one surface, meshed, and rendered as clay for you to look at.
Call `guide` once before modelling: it's the playbook (stages, stroke rules, parts, what goes wrong).

Conventions: metres, Blender axes. Z up, the creature FACES -Y, its left side is +X.
Names ending ".L" are auto-mirrored to ".R" across X, so store only the centre line and the left side.

Spec:
  joints: {name: {"pos": [x,y,z], "r": radius}}            joints don't render alone
  bones:  {name: {"a": joint, "b": joint, "r_a"?, "r_b"?, "flat"?: [width_scale, height_scale],
                  "blend"?, "op"?: "add"|"subtract", "layer"?: int, "group"?: str, "join"?: m}}   round cone
  blobs:  {name: {"at": joint | [x,y,z] | {"bone": name, "t": 0..1}, "offset"?: [x,y,z] (world axes),
                  "size": [rx,ry,rz] (semi-axes), "rot"?: [deg x,y,z], "blend"?, "op"?, "layer"?}}  ellipsoid;
          "shape": "blade": a thin rounded sheet (ears, leaves, fins, feathers), size [half width, half length
          (along local y), half thickness], "taper" 0..1 (narrower tip), "cup" m (edges lift to +z: an ear's
          hollow), "bend" m (the +y tip lifts to +z)
  kits:   {name: {"type": "hand" | "face", ...}}   parametric parts that expand into joints/bones/blobs
  anatomy: {} turns on modelling lore by joint type (found from the skeleton): every limb root (shoulder, hip, a
          quadruped's legs) gets a cap over the joint (deltoid, glute flare), the pit's folds (pec/lat beside the
          body) or a round mass behind (glute, triceps, for a limb leaving the body's end), and the joint's bones
          slim to bone size there, so limbs aren't balls plugged into the body. Per joint: {"shoulder.L": {"bulk",
          "cap", "front", "back", "insert", "narrow", "blend", "off"}}. Model limbs clear of the torso for rigging.
  parts:  {name: {"shell"?: base part, "offset"?, "color"?}}; any element takes "part": name (default "body").
          Each part is a separate mesh (and material later): eyes, teeth, clothing. A shell part is its base
          pushed out by offset, cut to its own layer-0 adds (a garment's region); strokes on it make folds.
  joints may be {"on": surface address (as for strokes), "lift", "shift", "r"}: seated on the surface
          (a tusk rooted on the lip, a horn on the skull), following it when the model changes.
  strokes: {name: {"op": "clay" | "crease" | "flatten", "path": [surface points], "width", "depth", ...}}
          sculpting on the surface itself (see below)
  paint:   {name: {"color": [r,g,b] | "#rrggbb", "opacity"?, "part"?, masks...}} colour layers applied in order
          over each part's clay colour; masks (multiplied): path (surface addresses, like strokes), near
          (elements or a kit), facing (normal direction), axis (world or along a bone), cavity, noise, ao,
          thickness, cells; or a "mask" stack with blend modes, breakup, levels, blur. "height" adds relief.
          Paint never changes geometry, so repainting is quick (see below).
  prefabs + instances: reusable pieces placed with a transform; "array" on a bone or blob repeats it (logs,
          planks, legs), with jitter; "tags" name groups; box/cylinder shapes, "hollow", cuts with "targets".
          kit_reference (REPETITION AND SOLIDS) documents them. Props and environments work too.
  top level: "blend" (default smooth-union radius, ~0.02-0.05 for a 1m creature), "symmetry".
Combination order: by layer, adds before subtracts within a layer. Use layer 1 for things that must sit
on top of carved areas (eyeballs in sockets). Bones/blobs sharing a "group" (e.g. the segments of a tail
or tentacle) are joined among themselves first, with a small "join" blend (0 = hard min; ~1/3 of the
radius rounds a bend without bulging), then blended into the body once: chains of fully blended
segments otherwise bulge at every joint.

Realistic humans: start from spec["base"] (a MakeHuman body + a GNM head, shaped by parameters), not from blobs
and kits; guide section 4d. The skeleton-and-blobs approach below is for creatures, cartoons and props.
Kits: prefer them to hand-placing fingers and facial features. {"type": "hand", "wrist": "wrist.L"} under
"hand.L" makes a mirrored hand (fingers, spread, curl, thumb). A "face" kit on the head joint places eyes
with lids, brows, nose, lips and cheeks by rough position and seats each onto the head's actual surface,
so depths come out right and follow edits to the skull. Every parameter has a proportioned default;
kit_reference lists them. get_model shows the generated names (face_eye.L, hand_f2_3.L, ...), which you
can measure along, hang blobs on, or focus on. fit leaves kit output alone but it follows its anchors.
Strokes are how you sculpt once the forms are blocked out: each one displaces the existing skin along a
path addressed on the surface ({"bone": "forearm.L", "t": 0.3, "side": [0,-1,0]} = out from that bone
toward the front; {"at": joint, "offset", "dir"} = raycast), with a width, a depth and a profile (how hard
its edge is). clay = muscle masses, fat pads, ridges; crease = folds, wrinkles, grooves; flatten = planes.
"repeat" lays out a set (wrinkles, ribs) from one entry. They follow the surface and move with the bones.
Keep them broad and shallow relative to the part (a few mm on a 3 cm arm); widths under ~2 voxels alias.
kit_reference documents them fully.
Paint colours the finished surface (vertex colours, exported in the OBJ): base colour, countershading
(facing), markings along surface paths (with repeat/scatter for stripes and spots), regions around elements
(near: "hand.L", "face_eye.L"), dirt in creases (cavity), mottling (noise), and procedural weathering from
the surface itself: a "mask" stack combines generators (ao, cavity, thickness, facing, noise with warp/stretch,
voronoi cells, paths...) with blend modes, and "breakup" turns them into edge wear, grime and dust. A layer's
"height" adds fine relief (pores, scales, cracks) to the exported normal/height maps. ".L" layers mirror. Painted
looks render the model's Blender scene (EEVEE, paint as shader nodes, per pixel); judge with look(shading="flat")
(unlit colour) and look(paint_layer=...) to see one layer's mask (orange on grey clay): a layer that lights up
nowhere is misaddressed. kit_reference documents it fully, with recipes.
The Blender scene (workspace/<model>/scene.blend, `sync`) is the model's live, editable form: a person can open
it, move props and tweak exposed paint numbers, and `pull` / the next sync / look brings those edits back into
the spec. AO and sky there are per asset: a prop shades only itself, the building only itself.
export_asset makes the game-ready version: low poly + UV atlases (per-part texel density, texel_focus for
faces, triangle_weight) + PBR maps (basecolor, normal, roughness,
metallic, specular, ao, orm, height) and a GLB: normal and height texel by texel from the exact model, paint and AO
baked by Cycles from the Blender scene; paint layers carry roughness/metallic/specular too. Check its Cycles preview (and close-ups of the face) before calling it done.
Close-ups (look with focus + zoom) rebuild just that region at full resolution: use them to judge
faces and hands.

Workflow, in stages; after each, run check (and look) and fix before moving on. Going back is fine.
  1. Plan: set_plan with front and side outlines (2D ellipses/capsules/polys in world units), landmark heights
     (chin, shoulders, navel, crotch, knees... in head heights) and a few sections (width x depth at the
     chest, waist, hips, thigh). Look at the returned sheet and get the proportions right here, where it's
     cheap. With reference art, trace the plan from it.
  2. Blockout: put_model with the skeleton and big masses; tie landmarks to joints; then fit (against the
     plan) and check until silhouettes, landmarks and sections agree.
  3. Secondary forms: strokes for muscle masses, fat pads and planes; judge with look shading="raking" /
     "curvature" and strokes=True; check again (strokes shouldn't break the silhouette).
  4. Detail: creases, wrinkles, repeats and scatters, in close-ups.
  5. History: the spec's "story" (age, climate, use, directions, events), turned into geometry: weather ops
     (sag, lean, settle, jitter), lumpy, chips, things out of place. Nothing real is pristine; check audits it.
  6. Paint: base colours per part, then broad zones (countershading, limbs), then markings, then dirt/mottling,
     weathering from the story (facing the weather side, sky-exposed vs sheltered, wear paths).
Without a plan: put_model -> look -> edit_model in small batches -> look ...
If you have reference art, set_reference per view then compare. Once the body plan is right, fit
auto-adjusts joints, radii and blobs to the reference outlines; use compare's band tables for what fit can't
do (missing parts, wrong topology).
Renders can mislead about thickness; measure gives cross-section widths along a bone chain or world axis.
look can hide parts, clip with a plane (floor plans, cross-sections) and add perspective cameras (inside a
room); clearance checks walkable floor, headroom and door widths of environments.
Every change is checkpointed; history/revert let you experiment freely.

Hair is curve locks in the Blender scene, not part of the field: read guide(topic="hair"), then groom_hair (grow locks
from spec.hair.groom) -> look_hair (renders + gates: outline dents, bare volume, fit to a traced reference) -> groom_hair /
edit_model kind "hair.locks" ... ; hair_reference matches a reference picture (camera from face landmarks, traced part,
hairline and clumps carried onto the head); sync(hair_only=True) puts the locks in scene.blend, pull brings hand edits back.

Clothes are sewn, not sculpted: spec["cloth"] garments are drafted to the body's measurements (FreeSewing designs or
your own pattern pieces), sewn and settled by Blender's cloth sim, cleaned up, with seams/stitching/hems from the
pattern. Work in a maker's stages (guide(topic="cloth")): design_garment (the design sheet: kind, fabric, fit, every
construction choice; garment_reference lists them) -> look_pattern (the flat pattern sheet + checks: seams, ease, each
choice evidenced) -> check_garment (construction plan, arrangement on the body) -> dress (quality "draft" first; it
refuses to simulate over construction failures) -> look_cloth (renders, strain map, report, numeric targets) -> final.
Fix faults in the pattern, never in the solver. States worn / draped (tablecloths, blankets) / hung;
sync(cloth_only=True) puts garments in scene.blend, pull brings colour and sculpt edits back.

Terrain (landscapes and game levels) is separate: a height field described in a level designer's words (a basin, a
pass, a village site, a road, forest here, "this must be visible from there"). Read guide(topic="terrain"), then
set_terrain -> check_terrain / look_terrain -> set_terrain(patch=...) ... -> export_terrain. When the world's kind is one
the tool doesn't know, it returns questions for the designer: ask them, don't answer them yourself.
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


def _tool_with_errors(_register=mcp.tool):
    """mcp.tool, but a tool's exception reaches the caller as its text. The SDK turns anything but ToolError
    into a bare "Error executing tool x", which left agents bisecting op batches to find a SpecError."""
    import functools
    import inspect
    from mcp.server.mcpserver.exceptions import ToolError

    def tool(*args, **kw):
        register = _register(*args, **kw)

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
                @functools.wraps(fn)
                def run(*a, **k):
                    try:
                        return fn(*a, **k)
                    except ToolError:
                        raise
                    except Exception as e:
                        raise ToolError(_error_text(e)) from e
            register(run)
            return fn  # module-level name stays the plain function (tests and scripts call it directly)
        return deco
    return tool


mcp.tool = _tool_with_errors()


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
    """The hifipushie playbook: how to work in stages (plan, blockout, secondary forms, detail), rules for
    strokes and parts, how to judge renders and diagnose artifacts. Read it before modelling.
    topic="terrain": the terrain vocabulary (landscapes and game levels in a level designer's words: world kinds,
    basins, passes, canyons, sites, routes, walls, cover, intent checks), for set_terrain and the other terrain tools.
    topic="hair": stylised hair as sculpted locks, the way artists groom it (silhouette, big shapes, clumps, breakup),
    with groom_hair, look_hair, hair_reference and sync(hair_only=True).
    topic="cloth": garments the way pattern makers and garment artists make them, in stages (design sheet, flat
    pattern and its checks, construction plan, arrangement, draft, final), with design_garment, look_pattern,
    check_garment, garment_reference, dress, look_cloth and sync(cloth_only=True).
    topic="skin": human skin the way character artists texture it, in stages (base tone, colour zones, large
    features, fine features, micro detail, cosmetics, shading check), with skin, look_skin and skin_reference.
    topic="vegetation": trees the way vegetation artists make them (a species' habit, age and setting grown, then
    limbs drawn and pruned, judged against a photo, foliage and bark, export), with grow_plant, edit_plant,
    look_plant, plant_reference, export_plant and plant_history."""
    if topic.strip().lower() == "terrain":
        return (Path(__file__).with_name("terrain_guide.md")).read_text()
    if topic.strip().lower() == "hair":
        return (Path(__file__).with_name("hair_guide.md")).read_text()
    if topic.strip().lower() == "vegetation":
        return (Path(__file__).with_name("vegetation_guide.md")).read_text()
    if topic.strip().lower() == "cloth":
        return (Path(__file__).with_name("cloth_guide.md")).read_text()
    if topic.strip().lower() == "skin":
        return (Path(__file__).with_name("skin_guide.md")).read_text()
    if topic:
        raise ValueError('topic is "" (the modelling playbook), "hair", "cloth", "skin", "terrain" or "vegetation"')
    return (Path(__file__).with_name("guide.md")).read_text()


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
    """Parameters and defaults for the kits (hand, face), strokes (clay, crease, flatten), paint and plans."""
    from . import assemble, faceshapes, garments, kits, materials, strokes
    from . import realism
    return ("REALISM\n" + realism.__doc__ + "\n\nREPETITION AND SOLIDS\n" + assemble.__doc__ + "\n" + SOLIDS + "\n\n" + kits.__doc__ + "\n\nGARMENTS\n" + garments.__doc__ + "\n\nSTROKES\n" + strokes.__doc__ + "\n\nPAINT\n" + paintmod.__doc__
            + "\n\nMATERIALS\n" + materials.__doc__ + "\n\nFACE SHAPES\n" + faceshapes.__doc__
            + "\n\nPLANS\n" + planmod.__doc__)


def _saved(name: str, v: int, spec: dict, extra: str = "") -> str:
    """The reply to a save: version, notes, warnings (things that saved but likely aren't what was meant), summary."""
    warn = "".join(f"WARNING: {w}\n" for w in paintmod.side_warnings(spec))
    return f"saved {name} v{v}\n" + extra + warn + summarize(spec)


@mcp.tool(structured_output=False)
def put_model(name: str, spec: dict, note: str = "") -> str:
    """Create a model or replace its whole spec. Missing keys get defaults. The stored plan (set_plan) is kept
    unless the new spec gives one, or "plan": null to drop it. Returns a summary."""
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
    """Apply a batch of edits atomically. Ops:
    {"op":"set","kind":"joints|bones|blobs|kits|strokes|paint|parts|anatomy|prefabs|instances|...","name":n,"value":{...}}
        merge fields, creates if new; a null field removes it. kind is any top-level key holding named entries.
    {"op":"set_key","key":"story|style|rig|weather|...","value":v}  replace a whole top-level key; null removes it
    {"op":"delete","kind":...,"name":n}
    {"op":"rename","kind":...,"name":n,"to":m}  joint/bone renames update references
    {"op":"move","joints":[names],"delta":[dx,dy,dz]}   shift a group of joints (e.g. a whole leg)
    {"op":"scale_r","joints":[names],"factor":f}         thicken/thin at those joints
    {"op":"global","value":{"blend":0.04}}
    Edit only ".L" and centre elements; ".R" follows automatically."""
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
    """Build the mesh and return a clay contact sheet.
    views: any of front, side, top, three_quarter (default set), back, left, three_quarter_back, below.
    All panels share one scale; front/side/top get rulers in world units (grid=True adds grid lines).
    focus=[x,y,z] + zoom>1 for close-ups (e.g. the face). resolution = voxels across the longest axis
    (160 is quick; 256-320 for detail). In a close-up, resolution counts across the region around the
    focus instead, so small features (lids, lips, fingers) get proportionally finer voxels; parts outside
    that region are left out. strokes=True draws every stroke's path on the views (orange clay, blue crease,
    green flatten, named at their start; hidden parts left out): check placement before judging form.
    shading: "clay" (soft studio matcap), "raking" (one low light from the left: shows shallow forms, planes
    and dents the clay hides), "curvature" (warm = convex, cool = concave, grey = flat, stronger = tighter:
    an evenly tinted area is blobby; crisp forms show as bright lines), "flat" (unlit colour: judge paint).
    paint: show the spec's paint layers (default); False shows plain clay per part.
    paint_layer: show that one layer's mask in false colour instead (purple 0, teal 0.5, yellow 1), to see
    where a mask stack lands before judging colours.
    hide_parts / only_parts: leave those parts out / show only those (no rebuild; "hair" hides the hair's locks): the body under clothes, the
    inside of a house without its roof, one part alone. With only_parts the views frame the parts shown.
    clip: cut the model with a plane and drop what's beyond it, e.g. {"z": 2.2} drops everything above
    z = 2.2 (a plan view of a house: use views=["top"]; a torso cross-section), {"-y": 0} drops everything
    with y < 0 (the front half, seen from the front), {"x": 0} the +X half; any plane: {"point": [x,y,z],
    "normal": [x,y,z]} drops the side the normal points into; a list applies several. Cut solids get flat
    caps in their part's colour, darkened, so walls read as walls. Views keep the uncut model's framing.
    camera: a perspective panel from inside or around the model: {"eye": [x,y,z], "target": [x,y,z],
    "fov"?: degrees across (default 70), "name"?}. eye [x, y] stands a person there: on the lowest floor with
    1.8 m of headroom, eye 1.6 m above it ("eye_height" to change); target [x, y] looks level at eye height.
    A list gives several panels. Alone it replaces the default views (views adds orthographic ones back).
    Perspective panels have no rulers (sizes change with depth) and no stroke overlay.
    Painted looks (paint=True, shading "clay" or "flat", no strokes; clip and close-ups too) are rendered from the model's
    Blender scene (synced first: see `sync`) in EEVEE with real lights; paint_layer then shows that layer's
    mask glowing orange on grey clay. Painted clips leave out what's beyond the plane (it casts no shadow either)
    and cap the cut solids; painted close-ups frame the scene's own meshes. The geometric views (raking,
    curvature, strokes, instances) show plain clay per part; shading="clay" with paint=False gives clay clips and
    close-ups at the build resolution.
    instances=True marks every placed prefab instance on the orthographic views: a dot at its origin, an arrow
    along its front (the prefab's local -Y: build prefabs facing -Y, like creatures) and its name. With a top
    view (and a clip) it's the floor plan with which way each piece of furniture faces.
    save: also write the contact sheet to this PNG path (to show someone who can't see tool images)."""
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
    return [_out(sheet, save), info + shown + painted + (f" | saved {save}" if save else "")]


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
    """Cross-section sizes as numbers, from the exact field (independent of build resolution).
    along = a bone name or a list of bones (a chain, e.g. a tail or leg): planes perpendicular to each bone
    at `samples` evenly spaced t, giving the distance from the axis to the surface on each side (w-/w+ along
    the bone's width axis, h-/h+ along its height axis; compare with joint radii) and the connected section
    area. Use it to find pinches, bulges and lumps along a limb.
    along = "x" | "y" | "z": planes across that world axis (optionally only between lo and hi), listing every
    separate part in each slice with its ranges on the other two axes, e.g. "y" gives body width and
    height from nose to tail, "z" shows where the legs merge into the body."""
    return meas.measure(store.load(name), along, samples, lo, hi)


@mcp.tool(structured_output=False)
def clearance(name: str, region: list[list[float]] | None = None, path: list[list[float]] | None = None,
              floor: float | None = None, height: float = 1.8, radius: float = 0.25, step: float = 0.2,
              spacing: float | None = None) -> str:
    """Can a person walk here? Walkability of an environment from the exact field (vertical and horizontal rays;
    independent of build resolution). Give one of:
    region = [[x0, y0], [x1, y1]]: a top-view character map over that floor area ('.' a person fits, ',' floor
    and headroom but within `radius` of a wall or object, 'h' headroom below `height`, '#' blocked: wall,
    furniture, or less than half the height free, ' ' no floor at that level) plus walkable area, floor
    flatness (spread, largest step between neighbouring cells) and least headroom. `spacing` defaults to ~60
    columns across.
    path = [[x, y], ...]: along the polyline every 5 cm, floor height, headroom and clear width (rays left and
    right of the direction of travel at five heights above the floor), a table every 25 cm plus the narrowest
    point and a verdict: does a person `height` tall and 2 x `radius` wide pass (doors: walk a path through).
    floor: the level to stand on (z); default the most common height with `height` of free space above it.
    step: floor bumps up to this count as floor (thresholds, rugs); more is an obstacle or a step."""
    return meas.clearance(store.load(name), region, path, floor, height, radius, step, spacing)


@mcp.tool(structured_output=False)
def set_reference(name: str, view: str, image_path: str, flip: bool = False, threshold: float = 40.0):
    """Attach a reference image for view "front", "side" or "top". The silhouette comes from the alpha
    channel if present, else from difference against the corner background colour (threshold).
    Our side view shows the creature facing LEFT; set flip=True if the reference faces right.
    Returns the extracted mask so you can check it."""
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
    """Compare model silhouettes to the references. Per view: IoU, a diff image
    (grey = match, red = model has extra, blue = model is missing) and band tables of edge errors
    in world units, which tell you which joint/blob to move and by how much.
    fit: "auto" searches the reference scale/offset for best overlap, so only shape differences remain
    (absolute size is ignored); "height"/"width" instead match that dimension, bottom-aligned.
    against: "refs" (set_reference images), "plan" (the model's plan, placed exactly: no rescaling), or "auto"
    (the plan if there is one). only_parts / hide_parts: which parts the silhouette counts (the body without the
    prop it holds); default: the plan's "parts", else all."""
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
    """Auto-fit the model to its reference silhouettes and save the result as a new version.
    Moves joints, joint/bone radii, blob offsets and blob sizes (params: any of "pos", "r", "offset",
    "size") to minimise the distance between model and reference outlines. Only what the given views can
    see changes: a side-only fit leaves X alone. Details (subtract ops, layer>=1 blobs) stay fixed unless
    named in `only`; `only`/`lock` take joint, bone and blob names. max_step caps any move per iteration (m);
    stiffness is a spring toward the starting values (higher = more conservative).
    Block out the body plan by hand first: fitting is local and can't fix a missing or misplaced limb.
    against: "refs", "plan" (fit the blockout onto the plan's outlines, placed exactly; joints tied to plan
    landmarks keep their planned height) or "auto" (the plan if there is one). only_parts / hide_parts: which parts
    the silhouettes count, and whose elements may move (default: the plan's "parts", else all). Returns the diff images, IoU before/after and every change; `revert` undoes it."""
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
    """Set (or replace) a model's plan: the 2D blockout you model against. Creates the model if it doesn't
    exist. Returns the plan drawn with rulers, so you can check proportions before modelling anything.
    plan = {"views": {"front"|"side"|"top": {"shapes": {name: shape}}}, "landmarks": {name: {"z", "joint"?}},
            "sections": {name: {"z", "near": [x, y], "width", "depth"}}}
    shape = {"ellipse": [cu, cv, ru, rv], "rot"?} | {"capsule": [u0, v0, u1, v1], "r": r | [r0, r1]} |
            {"poly": [[u, v], ...], "smooth"?: true}, plus "op": "subtract" to cut out. u, v are the view's
    world axes (front X,Z; side Y,Z with the creature facing -Y; top X,Y); ".L" shapes mirror in front/top.
    kit_reference has the details."""
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
    """Check the model against its plan: per view, the plan against the model's silhouette (grey = both,
    blue = plan only: the model is missing it, red = the model sticks out); IoU and edge-error bands in world units (placed exactly, no rescaling); landmark joints vs
    their planned heights; planned sections vs measured width and depth. Run it after every stage.
    Always also audits realism: missing story, identical copies at even spacing, things square to the axes,
    identical parts, big perfectly flat faces, paint without wear or dirt (works without a plan too).
    And walks a person through every doorway (box cuts with targets reaching the floor, 1.6 m+ tall): a door
    swung across the opening, furniture in the way, a step too high; names what blocks it. And lists props
    (instances) cutting into anything else, how deep and into what (a chair pushed into a table leg).
    only_parts / hide_parts: which parts the silhouettes count (judge the body, not the prop it holds); default:
    the plan's "parts" (a list of part names), else all."""
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
def rig(name: str, pose: dict | None = None, resolution: int = 160, size: int = 640, save: str | None = None):
    """The export rig, a separate step over the modelling skeleton (spec bones stay for modelling): fits it,
    skins the model and renders a test pose (front and side), so weights are judged before export_asset(rig=True).
    Humanoids (pelvis, chest, neck, head, shoulder/elbow/wrist, hip/knee/ankle .L/.R) get Mixamo's skeleton and
    names (mixamorig:Hips ... LeftHandIndex4, fingers from the hand kit): Mixamo animations, Unity Humanoid and
    Unreal's IK retargeter map it as is. spec["rig"] = {"joints": {"LeftShoulder": joint or [x, y, z], ...}} moves
    a rig joint; {"type": "chains", "root": joint, "chains": {"spine": {"joints": [...]}, "tail": {"from": "spine",
    "joints": [...]}, "leg_front.L": {...}}} gives any creature clean named chains ("<chain>_01"...). pose:
    {rig bone: [[axis x, y, z], degrees]} instead of the default test pose. Rest pose = as modelled."""
    from . import rig as rigmod
    spec = store.load(name)
    try:
        bones = rigmod.rig_bones(spec)
    except ValueError as e:
        return str(e)
    meta = store.build(name, resolution)
    z = np.load(meta["mesh"])
    V, F = z["verts"].astype(np.float64), z["faces"]
    pv, pnames = z["part"], [str(n) for n in z["part_names"]]  # per part, as export_asset skins them
    J, W = np.zeros((len(V), 4), int), np.zeros((len(V), 4))
    fp = pv[F[:, 0]]
    meshes = {}
    for i, pn in enumerate(pnames):
        sel = np.flatnonzero(pv == i)
        if len(sel):
            rm = np.full(len(V), -1)
            rm[sel] = np.arange(len(sel))
            meshes[pn] = (V[sel], rm[F[fp == i]], sel)
    for pn, (Jp, Wp) in rigmod.skin_parts(spec, bones, {k: v[:2] for k, v in meshes.items()}).items():
        J[meshes[pn][2]], W[meshes[pn][2]] = Jp, Wp
    turns = {k: (v[0], v[1]) for k, v in pose.items()} if pose else rigmod.test_pose(bones)
    P = rigmod.pose(bones, V, J, W, turns)
    fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    N = np.zeros_like(P)
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-12
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "posed.npz"
        np.savez(f, verts=P.astype(np.float32), faces=F, normals=N.astype(np.float32),
                 **{k: z[k] for k in ("part", "part_names", "part_colors")})
        frames = render.view_frames(P, ["front", "side"])
        img = render.contact_sheet(render.render_views(f, frames, size, "clay_studio.exr"), frames)
    used = np.bincount(J[W > 0.01], minlength=len(bones))
    empty = [b["name"] for b, u in zip(bones, used) if not u and not b["end"] and not b.get("noweight")]
    text = [f"{len(bones)} rig bones ({(spec.get('rig') or {}).get('type', 'humanoid')}); posed: "
            + ", ".join(f"{k} {v[1]:+g} deg" for k, v in turns.items())]
    text += [f"  {b['name']} <- {b.get('src', '?')}" + (" (end)" if b["end"] else "")
             + (f", child of {bones[b['parent']]['name']}" if b["parent"] >= 0 else " (root)") for b in bones]
    if empty:
        text.append("bones that got no skin: " + ", ".join(empty))
    return [_out(img, save), "\n".join(text)]


@mcp.tool(structured_output=False)
def style_check(name: str, colours: bool = True, save: str | None = None) -> str:
    """Measure a model against its style sheet's rules (spec.style.sheet; sheets: stylised_realist, ...). A sheet is a
    reusable bundle of a style's decisions: base head fit/pose defaults, part settings (skin subsurface), paint
    layers on the landmark joints, the look preset (lights) and the rules it was written from; the model's own spec
    wins key by key (null deletes a sheet key). Rules measured: face ratios on the posed head (chin over philtrum,
    nose and mouth widths), the eye opening (height/width, iris share, how much of the iris each lid covers) and,
    with colours=True, skin saturation/hue lit vs shadow sampled from a front render in the style's look (syncs the
    scene first; save= keeps that render). Each line: PASS/FAIL, value, target, why."""
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
    """Bring the model's Blender scene (workspace/<model>/scene.blend) in line with the spec, after taking back
    what a person changed in it (moved/turned/scaled instances, exposed paint numbers: see `pull`). One object
    per part and per prefab (collection instances), paint as shader nodes, AO and sky baked by Cycles (each
    asset shades only itself; props never shade the building). Only what changed is redone: moving a prop is
    ~2 s, a paint change rebuilds only the parts it touches (a few s), new geometry is meshed and measured. Open the
    .blend in Blender to look around and edit; the next sync or look brings the edits back.
    Live: when the person's running Blender has this scene.blend open with the Blender MCP add-on's server started
    (port 9876, or $BLENDER_MCP_PORT), sync and pull run inside that session: changes appear in their viewport as
    they're made, their unsaved moves and tweaks come back, and the session is saved to scene.blend afterwards.
    hair_only: only the hair's curve locks (after pulling what a person changed in the scene; seconds): enough after
    groom_hair or lock edits when the body hasn't changed. look_hair doesn't need it (it renders the spec's hair).
    Garments (spec["cloth"]) go in as meshes in the collection "cloth" with their pattern uv, sewing-detail maps and a
    colour node a person can change; only simulated ones (dress) go in, a sync never starts a sim. cloth_only: just
    the garments (seconds). A person's sculpt of a garment in Blender comes back with pull as offsets on that sim."""
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
    """Take back what a person changed in the model's Blender scene, without re-syncing it: instances they moved,
    turned or scaled become instance edits (the story's weather offsets taken back out), and exposed paint
    numbers (a layer's opacity and colour, mask ranges, noise scale, near distances; nodes named hp:...) come
    back into the spec, and garments: their colour node, roughness, and their shape (a sculpt/clean-up in Blender,
    kept as per-vertex offsets on top of that sim: cloth.<g>.sculpt). Only values changed from what the last sync wrote count. Reports instances that now cut
    into something (scene.clear_of slides one out). Reads the person's running Blender when it has the scene open
    (unsaved edits too), else the saved file."""
    from . import scene
    log = []
    changes = scene.pull(name, log)
    return (json.dumps(changes) if changes else "nothing changed in the scene") + ("\n" + "\n".join(log) if log else "")


@mcp.tool(structured_output=False)
def export(name: str, path: str, resolution: int = 256) -> str:
    """Build at the given resolution and write an OBJ (Z up, metres). Import it into Blender with
    bpy.ops.wm.obj_import(filepath=..., forward_axis='Y', up_axis='Z')."""
    meta = store.build(name, resolution)
    p = store.export_obj(name, Path(path).expanduser())
    return f"wrote {p} ({meta['verts']} verts, {meta['faces']} faces)"


@mcp.tool(structured_output=False)
def export_asset(name: str, out_dir: str, triangles: int = 15000, texture: int = 2048, resolution: int = 256,
                 atlases: int = 1, texel_density: float | None = None, instancing: bool = True, preview: bool = True,
                 hide: list[str] | None = None, save: str | None = None, rig: bool = False, fbx: bool = False,
                 face_shapes: bool | list[str] = False):
    """Export a game-ready asset: a low-poly mesh (about `triangles` drawn, one mesh per part), UV atlases and PBR
    textures baked from the exact model: basecolor, normal (tangent space, MikkTSpace, OpenGL/glTF green-up),
    roughness, metallic, specular, ao, orm (R ao, G roughness, B metallic, glTF packing) and height (16-bit; low
    poly + height = the sculpt; its range is in the json). Writes <name>.glb (glTF 2.0: Y up, facing +Z, metres,
    one material per atlas with KHR_materials_specular), the PNGs and <name>.json (conventions, per part:
    triangles, mm per texel, islands; per prefab: instances and savings; timings) into out_dir.
    Every texel is projected onto the exact surface, so sculpted detail the low poly drops lands in the normal
    and height maps. The paint maps (basecolor, roughness, metallic, specular) and the AO map are baked by Cycles
    from the model's Blender scene (synced first), per pixel from its shader nodes; AO is each asset's own (a
    prop never shadows the building or another prop: the engine lights them). Roughness, metallic and specular
    come from paint layers and part settings (kit_reference, PAINT).
    Instancing (default on): every prefab (even with one instance: a movable asset) is exported once (mesh "<prefab>", parts "<prefab>/<part>",
    meshed in its own box at up to `resolution` voxels across it) with a glTF node per instance (extras.prefab),
    and baked once, at its first instance (paint, AO, sky as it stands there). prefabs.<p>.export = "unique" bakes
    its instances into the scene instead (when paint must differ per copy). `triangles` counts drawn triangles.
    Budgets: triangles go where one joint decimation of all parts puts them (geometric error, so flat walls get
    few and small round parts enough; every part gets at least max(300, triangles/100) per copy, or its parts.<p>.min_triangles: lower it for many-instance prefabs like chain links). Per part in
    spec["parts"][p]: "triangle_weight" (x its share), "texel_density" (x its texels per metre), "texel_focus":
    [{"at": point | joint | blob, "radius": m, "density": w}] (islands there get w x more: a character's face),
    "atlas": name (its own atlas and material, e.g. "interior"), "uv": "planar" (a swappable flat surface: a clock's
    dial, a sign, a screen: its own material with upright 0..1 planar UVs, so an engine swaps its texture by one
    property; the json's parts.<p>.material names that material).
    Atlases: texel_density (texels per metre, e.g. 512) opens as many atlases as that needs at `texture`^2 at most
    (a prefab's parts stay on one), each the smallest power of two that holds its parts; the log says if any
    part falls short. Without it, atlases=n splits the parts over n atlases of `texture`^2 by texture load.
    preview: render the exported GLB with Cycles (as an engine would load it) to check the textures; hide:
    parts, instances or prefabs left out of it (e.g. roof and walls, to see an interior).
    rig: an armature from the skeleton (a joint per additive bone, rooted at "pelvis"/"hips" or the skeleton's
    middle) and the parts skinned to it (4 weights per vertex from each bone's own cone and the blobs on it,
    blended within the nearest bone's family): characters. Decimated triangles bend less cleanly than modelled
    edge loops at elbows and knees; judge it with the `rig` tool first. fbx: also <name>.fbx (Blender converts the
    GLB: skeleton, skin, embedded textures, no leaf bones, Y-primary bone axis), for Unity/Unreal import.
    face_shapes: True (all) or a list of ARKit blendshape names: morph targets for lipsync and expressions on a
    character with the face kit and a mouth that can open (kits.face.mouth.interior: slit, mouth bag, teeth,
    tongue), or a GNM base head (base.head.interior + mouth_gap >= 0.002: shapes from GNM's expression basis). True
    = all 52 ARKit names (mouth and jaw, lids, brows, cheeks, nose, and eyeLook*, which turn the eyeballs' own part)
    plus the corrective jawOpen_mouthClose, which a player sets to min(jawOpen, mouthClose) each frame: mouthClose
    alone only seals the lips (Audio2Face drives it with the jaw shut). On every part that moves (the head's part,
    teeth, tongue, eyeballs), the same vertices as the neutral (mouth closed), each shape its full extent at weight
    1, additive; names in glTF mesh.extras.targetNames, FBX blend shapes, and the json's face_shapes. Tune amounts /
    the jaw in
    spec["face_shapes"] (kit_reference FACE SHAPES). The slit's part is meshed fine enough to keep the slit open.
    Takes one to a few minutes at 2048 for a prop or creature (texture=1024 for quick checks), ~25 min for a
    furnished building; progress in workspace/<model>/progress.log."""
    from . import asset
    info = asset.export(name, Path(out_dir).expanduser(), triangles, texture, resolution, atlases, texel_density,
                        instancing, rig, fbx, face_shapes or None)
    sizes = ", ".join(f"{a['size']}^2" for a in info["atlases"].values())
    text = (f"wrote {info['glb']}: {info['triangles_placed']} triangles drawn ({info['triangles']} in the file), "
            f"atlases {sizes}, height range +-{info['height_range_m'] * 1000:.1f} mm, {info['seconds']}s\n"
            + "\n".join(info["log"])
            + "\nmaps: " + ", ".join(Path(v).name for a in info["atlases"].values() for v in a["maps"].values()))
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
               note: str = ""):
    """Grow the hair's locks from spec["hair"]["groom"] (the designer's words and numbers) and save them.
    Hair is curve locks (Bezier curves swept with a cupped lens profile) in the model's Blender scene, not part of
    the SDF body; guide(topic="hair") is the workflow. Needs a head with face landmarks (a `base` head) or a
    groom "centre" joint.
    groom: a patch merged into the stored groom first (objects merge key by key, null deletes), e.g.
      {"volume": {"top": 0.04}, "parting": {"side": "left", "offset": 0.03}, "drawn": [...]}.
      Keys: hairline (front, temples, sideburns, nape, ear, front_points), parting (side, offset, length, line, flat,
      full, depth), volume (front, top, crown, sides, back, nape: m of hair over the scalp; ramp, across, crest: x of the top's crest, taper: {from, to, floor} short tapered sides and back), length
      (per region, m), flow (per region: {"back"|"down"|"up"|"away"|...: weight}), tiers ({tier: {width, thickness,
      spacing, where, length, taper, belly, root, ...} | false}: strip = shingled side/back strips, gap = covers
      bare volume, big/crown = the generated top, fill, edge), drawn (big clumps drawn by hand: [{"name", "top":
      [[x, y] m from the head centre seen from above, root first] | "azel": [[az, el] deg], "width", "thickness"?,
      "taper"?, "lie"?, "root"? (width at the root: 0.1 grows out of the layer), "climb"? (m the root takes to rise),
      "to_hairline"? (inset m or {inset, reach}: the edge laid on the hairline), "split"?}]; name rows stem+number so
      an under-layer clump fills between neighbours; patch one by name: {"drawn": {"sweep2": {...}, "qf*": {...},
      "old": null}}), hairline_edge ({inset, reach} for every clump near the hairline), volume.edge_sink,
      parting.front, grey, noise, seed.
    stage: "mass" shows only the groom's volume as one shell (judge the silhouette first), "locks" the locks.
    Locks edited by hand (in Blender and pulled, or by edit_model) carry "hand": true and are kept; locks deleted in
    Blender (hair.removed) aren't grown again; replace=True regrows everything and forgets both.
    Edit single locks with edit_model: {"op": "set", "kind": "hair.locks", "name": lock, "value": {"width": 0.07}};
    the material with {"op": "set", "kind": "hair", "name": "look", "value": {"lit": "#5a3a2c"}}.
    Then look_hair. Returns the counts per tier."""
    from . import hair
    r = hair.groom(name, replace=replace, note=note, patch=_spec_arg(groom) if groom else None, stage=stage)
    spec = store.load(name)
    return (f"saved {name} v{r['version']}: grew " + (", ".join(f"{t} {n}" for t, n in r["grown"].items()) or "nothing")
            + f"; kept {len(r['kept'])} hand/edited locks" + (f" ({', '.join(r['kept'][:12])}{'...' if len(r['kept']) > 12 else ''})" if r["kept"] else "")
            + (f"; {len(r['not_regrown'])} names not regrown (deleted in Blender: hair.removed; replace=True "
               f"forgets them)" if r["not_regrown"] else "")
            + f"\n{_hair_counts(spec)}; stage {(spec.get('hair') or {}).get('stage', 'locks')}")


@mcp.tool(structured_output=False)
def look_hair(name: str, views: list[str] | None = None, size: int = 480, clay: bool = True, layout: bool = False,
              reference: str | None = None, save: str | None = None, only: list[str] | None = None):
    """A fast look at the hair (4-30 s): the head cropped from the model's Blender scene with the hair from the spec,
    rendered in EEVEE. Rows: the material, the same in clay (shape without colour: judge clumps there), and with a
    matched reference camera (hair_reference) the matched render, its clay, the reference, a 50% blend and the traced
    lines over the render (reference yellow, model cyan). A thumbnail shows how it reads small.
    views: any of front, three_quarter, three_quarter_r, side, back, top, close, close_back (default front,
    three_quarter, side, back, top). layout=True adds the groom seen from above as a sketch: hairline, parting, every
    lock's spine (drawn clumps black with names, others by tier), roots and tips; views=["layout"] gives only that
    (no render). reference: an image to show beside the views (default: the traced reference). only: lock names or
    patterns (["sweep*", "pside0"]) shown alone on the underlayer, to see which locks make a busy patch (the gates
    then measure that subset).
    Returns the images and the measured gates: the outline's dents (front, 3/4: a pinched temple reads as a divot),
    the bare-volume share per view (the volume showing between locks reads as a helmet), and with a trace the fit to
    the reference (part start px / direction deg, hairline px, silhouette IoU, outline px, clump directions).
    Needs the scene once: `sync` the model first."""
    from . import hair
    views = list(views) if views else ["front", "three_quarter", "side", "back", "top"]
    only_layout = views == ["layout"]
    if "layout" in views:
        layout = True
        views = [v for v in views if v != "layout"]
    bad = [v for v in views if v not in hair.VIEWS]
    if bad:
        raise ValueError(f"unknown views {bad} (have {', '.join(hair.VIEWS)}, layout)")
    spec = store.load(name)
    if not (spec.get("hair") or {}):
        raise ValueError(f"{name} has no hair: groom_hair(name, groom={{...}}) grows it")
    out = []
    text = _hair_counts(spec)
    if not only_layout:
        sheet, secs, _ = hair.look(name, views=tuple(views), size=size, reference=reference, spec=spec, clay=clay,
                                   only=only)
        out.append(_out(sheet, save))
        gates = _hair_gates(hair.look)
        if (spec.get("hair") or {}).get("stage") == "mass":  # the volume is the surface on purpose at this stage
            gates = "\n".join(ln for ln in gates.splitlines() if "bare volume" not in ln)
            gates += "\nstage mass: judge the silhouette (outline dents, IoU / outline px); bare-volume shares count " \
                     "once the locks are on (stage \"locks\")"
        text = f"rendered in {secs}s; {text}\n" + gates
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
def hair_reference(name: str, trace: dict | None = None, image_path: str | None = None, apply: bool = False,
                   widen: float = 1.8, save: str | None = None):
    """Match the hair to a reference picture: store its trace, fit the reference's camera to the model's face, and
    optionally carry the traced groom onto the head. From then on every look_hair adds a matched row and fit numbers.
    trace (or the stored one when omitted): see below; trace it by reading pixels off the image (zoomed crops with
    a grid help). image_path sets/overrides trace["image"].
    The camera (pose + focal length) is solved by least squares from trace["landmarks"] (the model's lm_* joints ->
    their pixels); expect a few px of error per landmark, more means a mislabelled point.
    apply=True: the trace carried through the camera onto the head becomes the groom's parting line, hairline
    front_points and drawn clumps (rays onto the groom's volume; hidden roots carried back to the part; rows behind
    the traced ones; widths = traced px x mm/px x widen, since clumps overlap) and is merged into spec.hair.groom.
    Then groom_hair to grow the locks, and look_hair.
    Returns the trace drawn on the reference (landmarks green, the fitted camera's reprojection cyan) and the errors.
    A trace is reference-image pixels (u right, v down) of the picture you're matching:
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
    """Put a garment on the model and simulate it: drafted to the body's measurements, sewn, settled by Blender's
    cloth, cleaned up (guide(topic="cloth") is the workflow). Garments live in spec["cloth"][garment].
    spec: the garment (merged into the stored one key by key, null deletes; replace=True replaces it), e.g.
      {"pattern": {"from": "simon", "ease": {"chest": 0.12}, "length": 0.15}, "fabric": "shirting", "color": "#8fb3d9"}
      Keys: pattern (from: a design in cloth_designs.json: simon (shirt), carlton (coat); ease per girth, length,
      sleeve_length, options, measurements (a fixed size instead of made to measure), alterations), or own pieces +
      seams (a tablecloth is one piece wrapped "flat"), fabric (preset: shirting, jersey, linen, denim, wool_coating,
      or {"preset", overrides}), color, roughness, state, quality, resolution (final triangle size, 0.01), coarse
      (the blocking sim's, 0.02), cleanup ({smooth, weld, clear, keep} or false), detail (seam/stitch/hem maps:
      {seam, topstitch, stitch, hem, buttons, thread} or false).
    state: "worn" (default: sewn on the body and settled), "draped" (laid flat and dropped on the model's surface: a
      tablecloth, a blanket; {"drape": {"over": "model" | "body"}}), or "hung" (dressed first, a hanger put inside
      it under the shoulders with its hook through the neck opening, the body taken away: it settles onto the hanger,
      nothing pinned; {"hang": {"hanger": {"kind": "wood" | "wire", "width", "bar", "slope", "clear", "rise"},
      "rail": {"length", "radius", "posts"} | false}}). The report's "hanger" line says what carries it.
    quality: "draft" (one coarse 2 cm sim, ~1 min: judge fit and big shape) or "final" (default: the coarse sim, then
      refined at 1 cm and cleaned up, ~3-5 min).
    backend (spec key): "blender" (default, local) or "zozo" (ZOZO's contact solver: intersection-free, strain
      limited; one sim at `resolution`, placement "smooth"; on this machine's GPU, ~2 s/frame at 2 cm, or on a GPU box
      via $HIFIPUSHIE_ZOZO_REMOTE; `zozo` = solver options). Judge ZOZO at "resolution": 0.02 locally.
    The sim runs in the background (one at a time on the machine); this waits up to `wait` s and returns either the
    report (when done) or the progress. Call dress(name) again (no spec) or look_cloth to see where it is: a sim
    already running or cached isn't started again. Returns the save, then per garment: status, report.
    Before a sim starts, the workflow's stages 1-3 are checked (design sheet, pattern, construction: the same as
    check_garment); hard failures stop it (the spec is still saved) unless force=True. A day of solver tuning once
    chased what were construction faults: fix the pattern first."""
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
               body: bool = True, save: str | None = None, result: str | None = None):
    """Look at the model's simulated garments (10-40 s): clay renders on the body (views from front, side, back,
    three (3/4 front), three_back, side_r; default front, side, back, three) and a strain map row (blue slack, green
    fine, yellow at the fabric's limit, red twice it), with each garment's report: the verdict (CORRUPT = tangled or
    crumpled cloth, TOO SMALL = negative ease, STRAINED = past the fabric's limit on the body), ease per girth from
    the pattern and on the body, integrity (crossings, crumpled pieces, where), surface numbers (crinkle, fold
    depth: sim -> after the clean-up) and the clean-up.
    focus: [x, y, z] or "garment:piece" (e.g. "shirt:collar") for a close-up `zoom` m across. textured: EEVEE with
    the sewing detail maps (seam grooves, topstitching, hems, buttons) instead of clay; use it with focus.
    A garment still simulating reports its progress instead (dress starts sims).
    result: a cloth job's out.npz (e.g. from a GPU box) applied to the one garment named instead of its cached sim
    (clean-up, report and renders as usual; not cached)."""
    from . import cloth
    sheet, text = cloth.look(name, garments, views=tuple(views or ("front", "side", "back", "three")), strain=strain,
                             size=size, focus=focus, zoom=zoom, body=body, textured=textured, result=result)
    if sheet is None:
        return text
    from . import cloth_workflow
    spec_now = store.load(name)
    extra = []
    for gn in (garments or list(spec_now.get("cloth") or {})):  # stage 5: the numeric targets
        try:
            r = cloth_workflow.run(name, gn, ("sim",), images=False, spec=spec_now)
            extra.append(f"targets {gn} (stage 5):\n" + cloth_workflow.text(r))
        except Exception as e:
            extra.append(f"targets {gn}: could not measure: {e}")
    return [_out(sheet, save), text + "\n\n" + "\n".join(extra)]


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
    """Describe a human's skin (spec["skin"]) and save it: the description expands into ordinary paint layers
    ("skin:<layer>", under the model's own paint) and the skin part's shading. guide(topic="skin") is the artist's
    workflow in stages; skin_reference lists every key, default and zone. For a model built on a `base` (MakeHuman /
    template body, GNM head): zones are placed from its joints and lm_* face landmarks.
    skin: a patch merged into the stored description (objects key by key, null deletes; replace=True starts over):
      {"tone": {"fitzpatrick": 1..6 | "melanin": 0..1, "blood": 0..1, "undertone": -1 cool .. 1 warm},
       "age": years, "variation": 1, "detail": 1, "oil": 0..1, "thin": 0..1, "sun": 0..1,
       "features": {"freckles": 0.6, "moles": {"at": [...]}, "age_spots", "blemishes", "veins", "flush", "sunburn",
                    "tan": {"amount", "mask": [...]}},
       "wrinkles": {"amount": 1, "forehead": ..., "crows_feet": ...},          (default: from age)
       "hair": {"brows": {"color", "density", "thickness"}, "lashes", "stubble": 0.7, "body": 0.5},
       "scars": [{"kind": "cut" | "surgical" | "keloid" | "burn" | "pockmarks", "path": [points] | "zone": name, "age": 0..1}],
       "tattoos": [{"image": {"file" | "text": {...}, "at", "size", "dir", "wrap"}, "age": years}],
       "makeup": {"foundation": {"amount", "finish"}, "blush", "contour", "highlight", "eyeshadow": {"color", "finish"},
                  "eyeliner": {"wing"}, "mascara", "brows", "lipstick": {"color", "finish": "matte" | "satin" | "gloss"}, "nails"},
       "zones": {built-in zone layer: strength}, "lips": {...}, "shading": {...}, "part": "body"}
    Any layer of the model's own paint can use the same anatomy: {"zone": "cheekbone.L"} in edit_model paint ops.
    Then look_skin (fast cropped close-ups + measurements), or sync + look for the whole model.
    Returns the tone's colours and the layers the description made."""
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
    base = skinmod.part_base(new_spec)[1]
    hx = lambda c: "#" + "".join(f"{int(round(x * 255)):02x}" for x in c)  # noqa: E731
    t = new.get("tone")
    return (f"saved {name} v{v}: skin on part {p['part']!r}, melanin {p['tone']['melanin']:.2f} blood {p['tone']['blood']:.2f} "
            f"undertone {p['tone']['undertone']:+.1f}, age {p['age']:.0f}\n"
            f"base {hx(base['color'])}, cheeks {hx(skinmod.tone_rgb(t, blood=2.7))}, lips {hx(skinmod.tone_rgb(t, melanin=0.7, blood=10, epidermis=0.45))}, "
            f"palms {hx(skinmod.tone_rgb(t, melanin=0.25, blood=1.7))}; roughness {base['roughness']:.2f}, subsurface "
            f"{base['subsurface_scale'] * 1000:.1f} mm, coat {base['coat']:.2f}\n"
            f"{len(layers)} layers: {', '.join(layers)}\n"
            f"look_skin(\"{name}\") renders close-ups and measures them; look(paint_layer=\"skin:<layer>\") or "
            f"look_skin(layer=...) shows one layer's mask")


@mcp.tool(structured_output=False)
def skin_reference() -> str:
    """Everything the `skin` description takes: the anatomical zones (also usable by any paint layer as
    {"zone": name}), the tone model, features, wrinkles, hair, scars, tattoos and make-up with their keys and
    defaults."""
    from . import skin as skinmod
    from . import skin_makeup
    return skinmod.reference() + "\n\n" + skin_makeup.reference()


@mcp.tool(structured_output=False)
def look_skin(name: str, views: list[str] | None = None, size: int = 768, light: str | None = None,
              flat: bool = False, layer: str | None = None, engine: str = "eevee", save: str | None = None):
    """Close looks at the skin, fast: bare-skin crops of the model (head and shoulders; forearm and hand: without
    clothes or hair, ~1 mm mesh, kept between calls) rendered under fixed lights, with measurements of the face next
    to what photographs of real skin measure (contrast per feature size in lightness and colour, colour zones,
    highlight size and breakup, micro contrast) and hints. The first look of a region meshes it (~2 min); after a
    skin or paint edit ~20-40 s.
    views: any of bust, face, three_quarter, side, cheek (macro), eye, mouth, forehead, ear (back-lit: light through
    the ear), hand, palm, forearm (default face, three_quarter, cheek, eye, mouth, ear).
    light: "studio" (a key from the model's right + a weak fill), "soft" (broad frontal: colour without highlights),
    "back" (back-lit); default per view. flat=True: the unlit colour. layer: one layer's mask, orange on grey clay
    ("freckles" = "skin:freckles"; or any paint layer's name).
    engine: "eevee" (fast) or "cycles" (path traced, slower: real subsurface scattering: the shading check for
    shadow edges and back-lit ears).
    Judge in this order: flat colour at bust distance (tone, zones), then the lit bust, then the close-ups."""
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
    """The clothing knowledge base (garment_kb.json): garment kinds (fit ease bands, default details, sewing order),
    detail choices (collar, cuff, sleeve_placket, front_closure, placket, waistband, fly, skirt_closure, pockets, hem,
    yoke, darts, pleats, back_vent, belt, lining, shoulder, topstitch) with what each is made of, its seams, fold
    lines, interfacing, the dimensions a tailor works to and the evidence checks that prove it's in a pattern; fabrics
    with physical numbers; what each draft source (simon, carlton, skirt_block) can and can't make; the numeric
    targets a simulated garment is judged by. kind: one kind's entry; detail: one detail kind's choices. No args: the
    index.
    principles: how to DESIGN a garment that has no ready-made draft (block + operations): "blocks" (the basic
    patterns and the rules they are drafted by), "operations" (dart moves, slash and spread, style lines, extensions,
    facings, collars from the neckline, sleeves into the armhole: what each does and what it keeps matched),
    "derivations" (per garment category: which block, which operations, why; or one name, e.g. "blazer"), "rules"
    (ease, balance, grain, shaping, seams, proportions), "all"."""
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
def design_garment(name: str, garment: str, design: dict | None = None, spec: dict | None = None,
                   replace: bool = False, note: str = "") -> str:
    """Stage 1 of the clothing workflow (guide(topic="cloth")): the design sheet, decided before any drafting, as a
    pattern maker does. Stored in spec["cloth"][garment]["design"] (merged key by key, null deletes; replace=True
    replaces the garment). design: {"kind": shirt | blouse | tee | hoodie | jacket | coat | trousers | shorts | skirt |
    dress | flat, "from": a draft source that can make it (simon, carlton, skirt_block; or DESIGN it: "block":
    bodice | knit | trouser | skirt, "block_options": {...}, "ops": [pattern operations] (garment_reference(principles=
    "operations" | "derivations"): a garment with no ready-made draft is a block + operations); or leave out and give own
    pieces + seams in spec), "fit": the kind's fit (slim, regular, a_line...), "fabric": a fabric (cotton_shirting,
    oxford, linen, cotton_twill, denim, wool_suiting, wool_coating, jersey, rib_knit, french_terry) or a solver preset,
    "details": {collar: shirt_collar | band | convertible | notched_lapel | shawl | hood | rib_neckband | ...,
    cuff: barrel | french | rib | hemmed | ..., sleeve_placket, front_closure, placket, waistband, skirt_closure, hem,
    darts, ...: a choice or {"type": choice, "options": {raw draft options}}}, "pattern": {draft words: ease, length,
    options...}, "notes"}. Left-out details take the kind's defaults (garment_reference(kind=...)).
    spec: other garment keys (color, state, quality, backend, resolution...), merged the same way.
    Returns the resolved sheet (every choice, where it came from, the dimensions to work to) with hard failures first:
    a choice the source can't make, a choice that needs another (a barrel cuff needs a sleeve placket). Next:
    look_pattern."""
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
    """Stage 2 of the clothing workflow: the garment drafted to the body and laid out flat on a pattern sheet (every
    piece at one scale with its name, role, size, grain arrow, notches, buttons/buttonholes, fold lines (blue dashed,
    with angle), interfacing (hatched), each seam in its own colour numbered on both sides S3a/S3b, a 10 cm bar, the
    seam list with each seam's ease), plus the checks before any sim, failures first: every design-sheet choice
    evidenced in the pieces and seam table (a turned collar has a fold line, a barrel cuff is closed and interfaced,
    the fall covers the stand...), every seam's ease in its band (sleeve cap by kind, bands, plain seams), notches
    aligned, ease against the body per girth inside the fit's band, every piece sewn to something, the details'
    dimensions. Fix failures in the design sheet (design_garment) or the garment's pattern options before going on.
    Next: check_garment(stages=["construction", "place"])."""
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
    """Run the clothing workflow's checks (guide(topic="cloth")), failures first. stages (default all, in order):
    "design" (the sheet), "pattern" (the draft vs the sheet and the body), "construction" (sewing order, layers and
    lap, fold/press lines with angles, interfacing and what rests as made, the sim's stage schedule; fails when
    something that must roll is frozen as made), "place" (the pieces arranged round the body before any sim: pieces
    through each other, pushed off the body, start stretch past the solver's strain limit, layer gaps; renders the
    start), "sim" (after dress: the verdict plus the numeric targets: layer gaps, collar cover and points, hem level,
    waistband height, sleeves on a hanger, crest radius, strain; each judged at the quality it belongs to).
    images: the pattern sheet and the placed start as images (save=path writes them with _pattern/_place suffixes)."""
    from . import cloth_workflow
    res = cloth_workflow.run(name, garment, tuple(stages or cloth_workflow.STAGES), images=images)
    out = []
    for r in res:
        for tag, im in r["images"]:
            out.append(_out(im, _save_suffix(save, tag)))
    out.append(cloth_workflow.text(res))
    return out if len(out) > 1 else out[0]


# ---------------------------------------------------------------- terrain

@mcp.tool(structured_output=False)
def set_terrain(name: str, spec: dict | None = None, patch: dict | None = None, note: str = "") -> str:
    """Create or change a terrain (a landscape or game level described in a designer's words: guide(topic="terrain")
    has the vocabulary). `spec` replaces the whole spec; `patch` merges into the stored one (objects merge key by key,
    null deletes: {"sites": {"camp": {"radius": 30}}, "cover": {"old": null}}). Every version is kept
    (terrain_history). Builds it and returns the report (in the spec's units, WARNINGS last), or, when its kind needs
    the designer to decide something, the questions as JSON: relay them, don't answer them."""
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
    """The terrain's report, measured on the built ground: the world kind and its compression, peaks as built,
    rivers and their banks, basins and walls (how much of each edge is unclimbable, climbable spots), passes, sites
    (cut/fill), routes (grades, switchbacks, crossings: fords or bridges), cover shares, intent checks (sight lines,
    skyline, flood heights, grades), drainage, WARNINGS last. Questions for the designer come back as JSON."""
    from . import terrain_tools as tt
    return tt.report(name)


@mcp.tool(structured_output=False)
def look_terrain(name: str, map: bool = True, masks: bool = False, views: list[dict] | None = None,
                 spec_views: bool = False, size: int = 1100, tiles: bool = False, haze: float | None = 5000.0,
                 light: str | None = None):
    """Images of a terrain. map: north-up hillshade with cover colours, contours, rivers, ridges, routes, sites,
    walls (red where climbable), names and a scale bar. masks: each cover mask alone (white = dense). views:
    perspective renders (Cycles, with trees and water; ~30 s + ~10 s a view): [{"name", "eye": address | [x, y, z],
    "lift": m, "look": address, "fov": deg, "sun": "auto" | side | {"from", "height"} | "morning"}] (auto: a raking
    sun per view); spec_views=True renders the spec's own "views". tiles=True renders the views from the 3D mesh
    tiles of the last export_terrain(name, tiles=True) instead (the way an engine shows them: baked maps, tiling rock
    detail, arches and caves, the ground's character, trees, the sites' props as stand-ins for scale, a raking sun and
    aerial haze: `haze` m for 63%, None off; `light`: "clear" = a deep blue clear sky and a strong sun, as in a sunny
    photo, default the hazy sky); a view may add "lamp": watts (a headlamp, inside caves). Files are also
    written to workspace/terrain/<name>/. Read the images, not just the report."""
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
            for pth in terrain_mesh.render_tiles(T, td, vs, haze=haze, light=light):
                out.append(_out(PILImage.open(pth), None))
                notes.append(f"view: {pth}")
            notes += json.loads((td / "render_job.json").read_text()).get("notes", [])
            return out + ["\n".join(notes)]
        for pth in terrain.render(T, d / "views", vs):
            out.append(_out(PILImage.open(pth), None))
            notes.append(f"view: {pth}")
        notes += T.view_notes
    return out + ["\n".join(notes)]


@mcp.tool(structured_output=False)
def export_terrain(name: str, size: int | None = None, engine: str | None = None, out_dir: str | None = None,
                   tiles: bool = False) -> str:
    """Write the terrain for an engine (default workspace/terrain/<name>/export/): height (.npy float32 absolute,
    16-bit .png and Unity .raw offset to 0), masks per cover layer plus water, roads, sites, playable and walls,
    splat weights for the ground layers, trees.csv, and meta.json (heights, the Unity terrain size and position,
    sites with their planes, passes, routes, rivers with water surface and width, fords, lakes). size: an engine
    grid (Unity 257/513/1025/2049, Unreal 505/1009/2017); engine="unity" picks 2^n+1 if no size. Defaults from the
    spec's "export". tiles=True writes 3D mesh tiles instead (default workspace/terrain/<name>/tiles/): the ground
    and its volumes (arches, caves, overhangs) as seamless glTF tiles with LODs, skirts, collision, heightmap and
    splat tiles and a manifest.json, tuned by the spec's "export": {"tiles": {...}}; a seam check runs on every
    export and fails loudly."""
    from . import terrain_tools as tt
    from .terrain_world import Questions
    try:
        T = tt.build(name)
    except Questions as q:
        return tt.questions_data(q)
    cfg = T.spec.get("export") or {}
    if tiles:
        from . import terrain_mesh
        r = terrain_mesh.export_tiles(T, Path(out_dir).expanduser() if out_dir else tt._dir(name) / "tiles")
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
    """List a terrain's versions, or restore one (saved as a new version, so nothing is lost). With no name
    ("" ), lists the terrains."""
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
    """Create or change a plant and grow it (guide(topic="vegetation") has the vocabulary and the stages). `spec`
    replaces the whole spec; `patch` merges into the stored one (objects merge key by key, null deletes:
    {"age": 60, "habit": {"apical": [0.6, 0.5]}, "environment": {"wind": {"from": "w", "strength": 0.5}}}).
    A spec is botanical words: {"species": preset, "age": years, "seed", "height": m, "habit": {...overrides...},
    "environment": {...}, "guides": {...}, "prune": [...], "envelope": {...}, "forces": [...], "leaves": {...},
    "bark": {...}, "season", "decay"}. The same spec always grows the same plant. Every version is kept
    (plant_history). Returns the report: size, form measured on its own silhouettes, limbs, foliage, guides, the
    reference match if it has one, WARNINGS last, and (for a patch) every changed value old -> new with what the tree
    did. In a patch, lists REPLACE (give the whole per-order list; `"prune": null` removes every prune: use
    edit_plant to add or remove one). copy_from: start `name` as a copy of another plant (+ patch): variants of one
    description, e.g. {"seed": 2, "age": 14}. Use get_plant first to see the values you are about to override.
    With no arguments but a name: the report of the stored plant; name "" lists the plants and the species presets."""
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
    """Direct the plant the way an artist does between growth years; it regrows around every edit. ops, in order:
    {"op": "guide", "name", "path": [[x, y, z], ...] (m), "from_year", "until_year", "vigour"}: a drawn axis at any
    branch order (it starts from the nearest wood at from_year, lies exactly on the path, is never shed or bent, and
    branches grow from it; a path from [0, 0, 0] at year 0 is the trunk). {"op": "remove_guide", "name"}.
    {"op": "take_limb", "limb": "SW1", "name"?, "path"?}: a GROWN main limb (the report names them) becomes a guide of
    the same place and shape, which you can then redraw; the rest of the tree regrows around it (it may change).
    The same with "on": another guide's name (or "trunk") makes it leave THAT axis. Paths are splined through
    their points ("straight": true keeps corners).
    {"op": "prune", "box": [[lo], [hi]] | "sphere": [[c], r] | "above": z | "below": z (limbs LEAVING the trunk under
    z) | "under": z (nothing but the trunk hangs under z)}: a clean cut on the finished tree, nothing else changes;
    with "from_year" it is cut from that year on and the tree answers it (regrows elsewhere).
    {"op": "remove_prune", "index"}, {"op": "clear_prunes"}.
    {"op": "cut", "year": N, <a volume as for prune>, "every": years, "until_year", "sprouts": n}: the wood in the
    volume is cut AT that year (and again every `every` years) and the stubs sprout `sprouts` new shoots each: a
    pollard ("above": 2.5, "every": 6), a coppice ("above": 0.3), a lopped limb or a storm break (a box, sprouts 0-2).
    {"op": "clear_cuts"}. {"op": "dead", "limb": name | id | guide (or a volume), "min_radius", "from": m along it},
    {"op": "clear_dead"}. {"op": "envelope", "shape": ellipsoid | cone | column | dome, "radius", "top", "base",
    "soft"} (a soft crown shape; no other keys = remove). {"op": "force", "dir": [x, y, z], "strength", "orders"},
    {"op": "clear_forces"}. {"op": "set", "path": "habit.apical.0" | "age" | "leaves.length"..., "value"}.
    Returns the report after regrowing, with what changed in size."""
    from . import veg_tools as vt
    before, prev = vt.grown(name)["stats"], vt.load(name)
    v = vt.edit(name, ops, note)
    return f"plant {name} v{v}\n" + vt.change_note(name, prev, before) + "\n" + vt.report(name)


@mcp.tool(structured_output=False)
def look_plant(name: str, views: list | None = None, azimuth: float = 0.0, size: int = 640,
               foliage: str | None = None, sheet: bool = False, triangles: int | None = None):
    """Images of a plant (Blender, 5-40 s). views, any of: "clay" (the bare skeleton as clay: judge the structure
    here first), "bare" (in colour, no leaves), "leaf" (in leaf; these three are side views from `azimuth`, 0 = looking
    along +y), "far" (at eye height from far enough that the tree is half the picture: how it reads in a scene), "near"
    (standing by it, 2-5 m, looking up: trunk, bark, forks), "close" (foliage: leaves and twigs), or a camera of your
    own {"name", "eye": [x, y, z], "look": [x, y, z], "fov": deg, "clay": bool}. Default clay + leaf + far. The ground
    is flat grass unless the spec has environment.ground {"slope": deg, "toward": [x, y], "water": z} (a hillside
    falling that way; a water level z m against the foot). clay and bare show a pole banded every metre (every fifth
    band red) beside the plant. triangles=N shows the plant as export_plant(triangles=N) writes it (thin wood left
    out, fewer and larger cards): judge the budgeted plant before exporting it. Files carry the view, azimuth and
    version in their names. foliage: "cards" (the twig
    atlas on cut cards: what a game draws; default) or "mesh" (real leaf meshes: close-ups, video).
    sheet=True returns the reference sheet instead (photo | outlines over each other | every view, with the numbers);
    it needs plant_reference first. Files are also written to workspace/plants/<name>/. Read the images."""
    from . import veg_tools as vt
    got = vt.look(name, tuple(views or ("clay", "leaf", "far")), azimuth, size, foliage, sheet, triangles)
    out = [_out(PILImage.open(p), None) for _, p in got]
    out.append(vt.report(name) + "\n" + "\n".join(f"{k}: {p}" for k, p in got))
    return out


@mcp.tool(structured_output=False)
def look_plants(names: list[str], at: list | None = None, spacing: float | None = None, views: list | None = None,
                azimuth: float = 0.0, size: int = 640, foliage: str | None = None):
    """Several plants standing together in one picture (a stand, a hedge line, a tree with its neighbours): do they
    belong together, do their sizes relate? at: [[x, y], ...] m per plant, or spacing m apart on a loose ring
    (default 0.35 x the tallest). views: "far" (default), "near", "clay", "top", or a camera {"eye", "look", "fov"}.
    The first plant's environment (ground slope) sets the scene. The same plant may be named more than once.
    A plant with a `set` (grow_plant patch {"set": {"count": 5}}): "oak#*" names its whole set, "oak#2" one of it."""
    from . import veg_tools as vt
    names = [m for n in names for m in (vt.set_names(n[:-2]) if n.endswith("#*") else [n])]
    got = vt.look_group(names, at, spacing, tuple(views or ("far",)), azimuth, size, foliage)
    out = [_out(PILImage.open(p), None) for _, p in got]
    out.append("\n".join(f"{k}: {p}" for k, p in got))
    return out


@mcp.tool(structured_output=False)
def get_plant(name: str = "", species: str = "") -> str:
    """A plant's spec as stored ("own"), what it RESOLVES to once its species preset and the defaults are under it
    ("resolved": every habit, leaf, twig and bark value actually in force), what each number usually is
    ("habit_ranges", "leaf_twig_ranges") and how many growth steps its age makes. Read this before overriding
    anything: an override replaces the resolved value, and per-order lists are replaced whole. With `species` and
    no name: that preset resolved (to see what a species gives before using it)."""
    from . import veg_tools as vt
    if not name and not species:
        raise ValueError("give a plant's name, or species=<preset> to see a preset")
    return json.dumps(vt.describe(name or None, species or None), indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))


@mcp.tool(structured_output=False)
def plant_reference(name: str, image_path: str, crop: list[int] | None = None, foot: int | None = None,
                    polygon: list[list[float]] | None = None, tol: float = 30.0, horizon: int | None = None,
                    bare: bool = False, credit: str = "", fit: dict | None = None, fit_iters: int = 40) -> str:
    """Give the plant a reference photo and measure against it. The silhouette is taken from the photo either by
    `polygon` (the tree's outline traced on the photo in image pixels, closed: use this when the tree fills the frame
    or stands against other trees) or by `crop` [x0, y0, x1, y1] + `foot` (the trunk's x in px): pixels more than
    `tol` from the sky colour at the crop's edges are tree; below `horizon` (image y where ground or far trees
    start) only the trunk counts. bare=True for a winter photo (compared without leaves). Returns outline IoU,
    width/height, bole and widest height, ours vs the photo's.
    fit = {habit path: [lo, hi]} searches those habit numbers for the best match (~1-2 min; e.g. {"apical.0":
    [0.45, 0.65], "angle.0": [40, 80], "vigour": [3, 6], "sag": [0.2, 2]}; integer bounds stay integers) and saves them
    into the plant's habit; it also charges limbs drooped under the crown's base, so it can't cheat the outline."""
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
def export_plant(name: str, out_dir: str | None = None, triangles: int | None = None, set: bool = False) -> str:
    """Export the plant as a GLB (workspace/plants/<name>/export/<name>.glb unless out_dir): a `wood` mesh (bark
    colour, normal and roughness as tiling textures on the branch uv) and a `foliage` mesh (every twig's card; the
    twig atlas with alpha MASK, double sided, COLOR_0 = a per-twig tint; the atlas's mask texture is listed in the
    material's extras). triangles: a budget for the whole plant (a game tree: 10-40k; without it everything grown is
    written, often 100-400k): the thinnest wood is left out and branches get fewer sides, twigs are thinned and the
    rest drawn larger. One LOD for now: LODs, wind data and seasons are not exported yet. Returns triangle counts.
    set=True writes the plant's `set` as ONE file (<name>_set.glb): a node per plant in a row, the bark and foliage
    materials and textures shared (a forest kit); `triangles` is then each plant's own budget."""
    from . import veg_tools as vt
    if set:
        c = vt.export_set(name, out_dir, triangles)
        return (f"exported {c['path']} ({c['bytes'] / 1e6:.1f} MB): {len(c['plants'])} plants, {c['total']} triangles in all, "
                f"one bark + one foliage material\n" + "\n".join(
                    f"  {q['name']}: {q['height_m']} m, wood {q['wood_triangles']} + foliage {q['foliage_triangles']} triangles"
                    for q in c["plants"]) + "\nNot in this file yet: LODs, wind channels, season variants, a collision proxy.")
    c = vt.export(name, out_dir, triangles)
    return (f"exported {c['path']} ({c['bytes'] / 1e6:.1f} MB), {c['total']} triangles"
            + (f" for a budget of {triangles}" if triangles else "") + f": wood {c['wood_triangles']} triangles"
            + (f" (wood thinner than {c['wood_min_radius_m'] * 1000:.0f} mm left out)" if c["wood_min_radius_m"] else "")
            + f", foliage {c['foliage_triangles']} triangles"
            + (f" ({c['twigs_kept']:.0%} of the twigs, drawn larger)" if c["twigs_kept"] < 1 else "")
            + (f", atlas {c['atlas_px']} px" if "atlas_px" in c else "")
            + (f"\nWARNING: {c['over']} triangles over the budget: the wood alone needs {c['wood_triangles']} "
               f"(a trunk and its main limbs can't go lower); raise the budget" if c["over"] else "")
            + (f"\nWARNING: {c['floating']:.0%} of the cards have no drawn wood near them (they will float): raise the budget"
               if c.get("floating", 0) > 0.2 else "")
            + ("\nWood you marked (dead wood, drawn guides) is kept down to a quarter of that girth." if triangles else "")
            + (f"\nLook at it before using it: look_plant(name, views=['leaf', 'far'], triangles={triangles})" if triangles else "")
            + "\nNot in this file yet: LODs, wind channels, season variants, a collision proxy.")


@mcp.tool(structured_output=False)
def sync_plant(name: str, pull_only: bool = False) -> str:
    """The plant as a Blender file a person (or you, through a Blender session) can edit by hand:
    workspace/plants/<name>/plant.blend holds the plant with its guides (orange, collection "guides") and its named
    main limbs (blue, "limbs") as Bezier curves. First every edit made there comes back into the spec: a guide curve
    moved or given more points = that guide redrawn; a limb curve moved = that limb taken over as a guide with the
    new shape; a curve added to "guides" = a new guide; a guide curve deleted = removed. Then (unless pull_only) the
    file is written again from the spec. A running Blender with the file open is read live and reloaded. Only
    what moved from what the last sync wrote counts: syncing twice changes nothing. Returns what came back and the
    report."""
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
    """List a plant's versions (plant_history(name)), or restore one: plant_history(name, revert_to=3) saves version
    3's spec again as a new version, so nothing is lost."""
    from . import veg_tools as vt
    if revert_to is not None:
        v = vt.revert(name, revert_to)
        return f"plant {name} v{v} = v{revert_to}\n" + vt.report(name)
    return "\n".join(f"v{h['version']}  {h['note']}" for h in vt.history(name))


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
