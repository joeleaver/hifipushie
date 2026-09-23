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
from . import plan as planmod
from . import render, store
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
Without a plan: put_model -> look -> edit_model in small batches -> look ...
If you have reference art, set_reference per view then compare. Once the body plan is right, fit
auto-adjusts joints, radii and blobs to the reference outlines; use compare's band tables for what fit can't
do (missing parts, wrong topology).
Renders can mislead about thickness; measure gives cross-section widths along a bone chain or world axis.
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


@mcp.tool(structured_output=False)
def kit_reference() -> str:
    """Parameters and defaults for the kits (hand, face), strokes (clay, crease, flatten) and plans."""
    from . import kits, strokes
    return kits.__doc__ + "\n\nSTROKES\n" + strokes.__doc__ + "\n\nPLANS\n" + planmod.__doc__


@mcp.tool(structured_output=False)
def put_model(name: str, spec: dict, note: str = "") -> str:
    """Create a model or replace its whole spec. Missing keys get defaults. Returns a summary."""
    full = {**empty_spec(), **_spec_arg(spec)}
    v = store.save(name, full, note or "put_model")
    return f"saved {name} v{v}\n" + summarize(full)


@mcp.tool(structured_output=False)
def edit_model(name: str, ops: list[dict], note: str = "") -> str:
    """Apply a batch of edits atomically. Ops:
    {"op":"set","kind":"joints|bones|blobs|kits|strokes","name":n,"value":{...}}  merge fields, creates if new; a null field removes it
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
         matcap: str = "clay_studio.exr", strokes: bool = False, shading: str = "clay", save: str | None = None):
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
    an evenly tinted area is blobby; crisp forms show as bright lines).
    save: also write the contact sheet to this PNG path (to show someone who can't see tool images)."""
    if focus is not None and zoom > 1:
        full_bounds = store.extent(name)  # sets the view scale, as in a full look
        frames = render.view_frames(full_bounds, views or render.DEFAULT_VIEWS, focus, zoom)
        half = 0.8 * frames[0]["scale"]
        f = np.asarray(focus, float)
        meta = store.build(name, resolution, box=(f - half, f + half))
    else:
        meta = store.build(name, resolution)
        frames = render.view_frames(np.array(meta["bounds"]), views or render.DEFAULT_VIEWS, focus, zoom)
        full_bounds = meta["bounds"]
    mesh = Path(meta["mesh"])
    if shading == "raking":
        matcap = str(render.raking_matcap(store.HOME / "raking_matcap.png"))
    elif shading == "curvature":
        mesh = _curvature_mesh(name, mesh, meta["voxel"], full_bounds)
    elif shading != "clay":
        raise ValueError('shading must be "clay", "raking" or "curvature"')
    imgs = render.render_views(mesh, frames, size, matcap)
    if strokes:
        paths = _stroke_paths(store.load(name), frames, Path(meta["mesh"]), meta["voxel"], size)
        imgs = [render.draw_strokes(im, f, paths) for im, f in zip(imgs, frames)]
    sheet = render.contact_sheet(imgs, frames, grid)
    lo, hi = full_bounds
    dims = [round(h - l, 3) for l, h in zip(lo, hi)]
    info = (f"{name}: {meta['verts']} verts, voxel {meta['voxel']:.4f}, built in {meta['seconds']}s | "
            f"size X{dims[0]} Y{dims[1]} Z{dims[2]}")
    return [_out(sheet, save), info + (f" | saved {save}" if save else "")]


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
    h = 0.75 * voxel
    stencil = np.array([[0, 0, 0], [h, 0, 0], [-h, 0, 0], [0, h, 0], [0, -h, 0], [0, 0, h], [0, 0, -h]])
    lap = np.zeros(len(z["verts"]))
    for i, pn in enumerate(names):
        sel = np.flatnonzero(part == i)
        f = sdf.field_at(streams[pn], z["verts"][sel].astype(np.float64)[:, None, :] + stencil[None])
        lap[sel] = (f[:, 1:].sum(1) - 6 * f[:, 0]) / (h * h)
    size = float(np.max(np.asarray(bounds[1]) - np.asarray(bounds[0])))
    z["colors"] = render.curvature_colours(lap, size, voxel)
    np.savez(out, **z)
    return out


def _stroke_paths(spec: dict, frames: list[dict], mesh=None, voxel: float = 0.0, size: int = 448) -> list[dict]:
    """Every stroke's seated path (mirrored ones too), with per-view visibility: a point is hidden when the
    built mesh is nearer the camera there (by more than the stroke's own height and a little slack)."""
    from . import sdf
    from .spec import compile_prims, expand_mirror
    s = expand_mirror(spec)
    prims = compile_prims(spec)
    stored = spec.get("strokes") or {}
    out = []
    for bname, bl in s["blobs"].items():
        if bl.get("shape") not in ("displace", "flatten"):
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
    their planned heights; planned sections vs measured width and depth. Run it after every stage."""
    spec = store.load(name)
    plan = spec.get("plan")
    if not plan:
        raise ValueError("this model has no plan; use set_plan first")
    store.build(name, resolution)
    refs = _refs(name, None, "plan")
    lines, outlines = [], {}
    for v, (ref, world) in refs.items():
        sil = store.silhouette(name, v)
        outlines[v] = (sil["mask"], sil["u"], sil["v"])
        _, _, report = cmp.compare(sil, ref, world=world, bands=10)
        lines.append(f"[{v}] " + report.replace("alignment: fit=world (exact); ", ""))
    lines += planmod.check_numbers(spec, plan)
    return [_out(planmod.sheet(plan, list(refs), outlines=outlines), save), "\n".join(lines)]


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
def export(name: str, path: str, resolution: int = 256) -> str:
    """Build at the given resolution and write an OBJ (Z up, metres). Import it into Blender with
    bpy.ops.wm.obj_import(filepath=..., forward_axis='Y', up_axis='Z')."""
    meta = store.build(name, resolution)
    p = store.export_obj(name, Path(path).expanduser())
    return f"wrote {p} ({meta['verts']} verts, {meta['faces']} faces)"


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
