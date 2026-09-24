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
                  "size": [rx,ry,rz] (semi-axes), "rot"?: [deg x,y,z], "blend"?, "op"?, "layer"?}}  ellipsoid
  kits:   {name: {"type": "hand" | "face", ...}}   parametric parts that expand into joints/bones/blobs
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
"""

mcp = MCPServer("hifipushie", instructions=INSTRUCTIONS)


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
def guide() -> str:
    """The hifipushie playbook: how to work in stages (plan, blockout, secondary forms, detail), rules for
    strokes and parts, how to judge renders and diagnose artifacts. Read it before modelling."""
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
    from . import assemble, kits, materials, strokes
    from . import realism
    return ("REALISM\n" + realism.__doc__ + "\n\nREPETITION AND SOLIDS\n" + assemble.__doc__ + "\n" + SOLIDS + "\n\n" + kits.__doc__ + "\n\nSTROKES\n" + strokes.__doc__ + "\n\nPAINT\n" + paintmod.__doc__
            + "\n\nMATERIALS\n" + materials.__doc__
            + "\n\nPLANS\n" + planmod.__doc__)


@mcp.tool(structured_output=False)
def put_model(name: str, spec: dict, note: str = "") -> str:
    """Create a model or replace its whole spec. Missing keys get defaults. Returns a summary."""
    full = {**empty_spec(), **_spec_arg(spec)}
    v = store.save(name, full, note or "put_model")
    return f"saved {name} v{v}\n" + summarize(full)


@mcp.tool(structured_output=False)
def edit_model(name: str, ops: list[dict], note: str = "") -> str:
    """Apply a batch of edits atomically. Ops:
    {"op":"set","kind":"joints|bones|blobs|kits|strokes|paint|parts","name":n,"value":{...}}  merge fields, creates if new; a null field removes it
    {"op":"delete","kind":...,"name":n}
    {"op":"rename","kind":...,"name":n,"to":m}  joint/bone renames update references
    {"op":"move","joints":[names],"delta":[dx,dy,dz]}   shift a group of joints (e.g. a whole leg)
    {"op":"scale_r","joints":[names],"factor":f}         thicken/thin at those joints
    {"op":"global","value":{"blend":0.04}}
    Edit only ".L" and centre elements; ".R" follows automatically."""
    spec = store.apply_ops(store.load(name), ops)
    v = store.save(name, spec, note or f"{len(ops)} ops")
    return f"saved {name} v{v}\n" + summarize(spec)


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
    hide_parts / only_parts: leave those parts out / show only those (no rebuild): the body under clothes, the
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
    Painted looks (paint=True, shading "clay" or "flat", no strokes/clip/close-up) are rendered from the model's
    Blender scene (synced first: see `sync`) in EEVEE with real lights; paint_layer then shows that layer's
    mask glowing orange on grey clay. The geometric views (raking, curvature, strokes, clip, close-ups) show
    plain clay per part.
    instances=True marks every placed prefab instance on the orthographic views: a dot at its origin, an arrow
    along its front (the prefab's local -Y: build prefabs facing -Y, like creatures) and its name. With a top
    view (and a clip) it's the floor plan with which way each piece of furniture faces.
    save: also write the contact sheet to this PNG path (to show someone who can't see tool images)."""
    cams = [] if camera is None else (camera if isinstance(camera, list) else [camera])
    cams = [_resolve_camera(name, c) for c in cams]
    geometric = strokes or instances or clip or (focus is not None and zoom > 1) or shading not in ("clay", "flat")
    if paint and not geometric and store.load(name).get("paint"):
        from . import scene
        r = scene.sync(name)
        sheet, secs = scene.look(name, views or ([] if cams else render.DEFAULT_VIEWS), cams, size, None,
                                 paint_layer, hide_parts, only_parts, flat=shading == "flat")
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
            against: str = "auto"):
    """Compare model silhouettes to the references. Per view: IoU, a diff image
    (grey = match, red = model has extra, blue = model is missing) and band tables of edge errors
    in world units, which tell you which joint/blob to move and by how much.
    fit: "auto" searches the reference scale/offset for best overlap, so only shape differences remain
    (absolute size is ignored); "height"/"width" instead match that dimension, bottom-aligned.
    against: "refs" (set_reference images), "plan" (the model's plan, placed exactly: no rescaling), or "auto"
    (the plan if there is one)."""
    store.build(name, resolution)
    out = []
    for v, (ref, world) in _refs(name, views, against).items():
        iou, diff, report = cmp.compare(store.silhouette(name, v), ref, fit, world=world)
        out += [_png(diff), f"[{v}] {report}"]
    return out


@mcp.tool(structured_output=False)
def fit(name: str, views: list[str] | None = None, only: list[str] | None = None,
        lock: list[str] | None = None, params: list[str] | None = None, iterations: int = 20,
        max_step: float = 0.02, stiffness: float = 0.05, align: str = "auto", resolution: int = 160,
        against: str = "auto"):
    """Auto-fit the model to its reference silhouettes and save the result as a new version.
    Moves joints, joint/bone radii, blob offsets and blob sizes (params: any of "pos", "r", "offset",
    "size") to minimise the distance between model and reference outlines. Only what the given views can
    see changes: a side-only fit leaves X alone. Details (subtract ops, layer>=1 blobs) stay fixed unless
    named in `only`; `only`/`lock` take joint, bone and blob names. max_step caps any move per iteration (m);
    stiffness is a spring toward the starting values (higher = more conservative).
    Block out the body plan by hand first: fitting is local and can't fix a missing or misplaced limb.
    against: "refs", "plan" (fit the blockout onto the plan's outlines, placed exactly; joints tied to plan
    landmarks keep their planned height) or "auto" (the plan if there is one). Returns the diff images, IoU before/after and every change; `revert` undoes it."""
    refs = _refs(name, views, against)
    spec = store.load(name)
    pin = []
    if any(w is not None for _, w in refs.values()):  # fitting to the plan: its landmarks fix joint heights
        pin = [("joints", lm["joint"], "pos", 2) for lm in (spec["plan"].get("landmarks") or {}).values()
               if lm.get("joint") in spec["joints"]]
    res = fitmod.fit(spec, refs, align, tuple(params or fitmod.GROUPS), only, tuple(lock or ()),
                     iterations, max_step, stiffness, resolution, pin)
    ver = store.save(name, res.spec, "fit " + " ".join(
        f"{v} {res.iou_before[v]:.3f}->{res.iou_after[v]:.3f}" for v in refs))
    out = []
    for v, im in fitmod.diff_images(res).items():
        out += [_png(im), f"[{v}] IoU {res.iou_before[v]:.3f} -> {res.iou_after[v]:.3f}"]
    out.append(f"saved {name} v{ver}\n" + "\n".join(res.log) + "\n\nchanges:\n" + "\n".join(res.changes or ["(none)"]))
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
def check(name: str, resolution: int = 160, save: str | None = None):
    """Check the model against its plan: per view, the plan against the model's silhouette (grey = both,
    blue = plan only: the model is missing it, red = the model sticks out); IoU and edge-error bands in world units (placed exactly, no rescaling); landmark joints vs
    their planned heights; planned sections vs measured width and depth. Run it after every stage.
    Always also audits realism: missing story, identical copies at even spacing, things square to the axes,
    identical parts, big perfectly flat faces, paint without wear or dirt (works without a plan too).
    And walks a person through every doorway (box cuts with targets reaching the floor, 1.6 m+ tall): a door
    swung across the opening, furniture in the way, a step too high; names what blocks it."""
    from . import realism
    spec = store.load(name)
    warn = realism.audit(spec)
    realism_txt = ("\n\nREALISM (too perfect to be real?):\n" + "\n".join(f"- {w}" for w in warn)) if warn else \
        "\n\nREALISM: no perfection warnings"
    doors = meas.check_doorways(spec)
    if doors:
        realism_txt += "\n\nDOORWAYS (a person 1.8 m tall, 0.5 m wide walked 1 m through each):\n" + "\n".join(doors)
    plan = spec.get("plan")
    if not plan:
        return "no plan to check against (set_plan)." + realism_txt
    store.build(name, resolution)
    refs = _refs(name, None, "plan")
    lines, outlines = [], {}
    for v, (ref, world) in refs.items():
        sil = store.silhouette(name, v)
        outlines[v] = (sil["mask"], sil["u"], sil["v"])
        _, _, report = cmp.compare(sil, ref, world=world, bands=10)
        lines.append(f"[{v}] " + report.replace("alignment: fit=world (exact); ", ""))
    lines += planmod.check_numbers(spec, plan)
    return [_out(planmod.sheet(plan, list(refs), outlines=outlines), save), "\n".join(lines) + realism_txt]


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
def sync(name: str, resolution: int = 256) -> str:
    """Bring the model's Blender scene (workspace/<model>/scene.blend) in line with the spec, after taking back
    what a person changed in it (moved/turned/scaled instances, exposed paint numbers: see `pull`). One object
    per part and per prefab (collection instances), paint as shader nodes, AO and sky baked by Cycles (each
    asset shades only itself; props never shade the building). Only what changed is redone: moving a prop is
    ~2 s, a paint change rebuilds materials (~30-60 s), new geometry is meshed and measured. Open the .blend in
    Blender to look around and edit; the next sync or look brings the edits back."""
    from . import scene
    r = scene.sync(name, resolution)
    return (f"{r['blend']} synced in {sum(r['seconds'].values()):.1f}s ({', '.join(f'{k} {v}s' for k, v in r['seconds'].items())})\n"
            + "\n".join(r["log"]))


@mcp.tool(structured_output=False)
def pull(name: str) -> str:
    """Take back what a person changed in the model's Blender scene, without re-syncing it: instances they moved,
    turned or scaled become instance edits (the story's weather offsets taken back out), and exposed paint
    numbers (a layer's opacity and colour, mask ranges, noise scale, near distances; nodes named hp:...) come
    back into the spec. Only values changed from what the last sync wrote count. Reports instances that now cut
    into something (scene.clear_of slides one out)."""
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
                 hide: list[str] | None = None, save: str | None = None):
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
    few and small round parts enough; every part gets at least max(300, triangles/100)). Per part in
    spec["parts"][p]: "triangle_weight" (x its share), "texel_density" (x its texels per metre), "texel_focus":
    [{"at": point | joint | blob, "radius": m, "density": w}] (islands there get w x more: a character's face),
    "atlas": name (its own atlas and material, e.g. "interior").
    Atlases: texel_density (texels per metre, e.g. 512) opens as many atlases as that needs at `texture`^2 at most
    (a prefab's parts stay on one), each the smallest power of two that holds its parts; the log says if any
    part falls short. Without it, atlases=n splits the parts over n atlases of `texture`^2 by texture load.
    preview: render the exported GLB with Cycles (as an engine would load it) to check the textures; hide:
    parts, instances or prefabs left out of it (e.g. roof and walls, to see an interior).
    Takes one to a few minutes at 2048 for a prop or creature (texture=1024 for quick checks), ~25 min for a
    furnished building; progress in workspace/<model>/progress.log."""
    from . import asset
    info = asset.export(name, Path(out_dir).expanduser(), triangles, texture, resolution, atlases, texel_density,
                        instancing)
    sizes = ", ".join(f"{a['size']}^2" for a in info["atlases"].values())
    text = (f"wrote {info['glb']}: {info['triangles_placed']} triangles drawn ({info['triangles']} in the file), "
            f"atlases {sizes}, height range +-{info['height_range_m'] * 1000:.1f} mm, {info['seconds']}s\n"
            + "\n".join(info["log"])
            + "\nmaps: " + ", ".join(Path(v).name for a in info["atlases"].values() for v in a["maps"].values()))
    if not preview:
        return text
    im = asset.preview(Path(info["glb"]), render.DEFAULT_VIEWS, hide=hide)
    return [_out(im, save), text]


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
