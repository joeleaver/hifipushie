"""hifipushie MCP server: skeleton-and-blob creature modeling with clay-render feedback."""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import numpy as np
from mcp.server.mcpserver import Image, MCPServer
from PIL import Image as PILImage

from . import compare as cmp
from . import fit as fitmod
from . import measure as meas
from . import render, store
from .spec import empty_spec, summarize

INSTRUCTIONS = """\
hifipushie models characters and creatures as a skeleton (joints + bones) with SDF blobs hung on it,
smooth-blended into one surface, meshed, and rendered as clay for you to look at.

Conventions: metres, Blender axes. Z up, the creature FACES -Y, its left side is +X.
Names ending ".L" are auto-mirrored to ".R" across X, so store only the centre line and the left side.

Spec:
  joints: {name: {"pos": [x,y,z], "r": radius}}            joints don't render alone
  bones:  {name: {"a": joint, "b": joint, "r_a"?, "r_b"?, "flat"?: [width_scale, height_scale],
                  "blend"?, "op"?: "add"|"subtract", "layer"?: int, "group"?: str, "join"?: m}}   round cone
  blobs:  {name: {"at": joint | [x,y,z] | {"bone": name, "t": 0..1}, "offset"?: [x,y,z] (world axes),
                  "size": [rx,ry,rz] (semi-axes), "rot"?: [deg x,y,z], "blend"?, "op"?, "layer"?}}  ellipsoid
  kits:   {name: {"type": "hand" | "face", ...}}   parametric parts that expand into joints/bones/blobs
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

Workflow: put_model (block out the whole body plan) -> look -> edit_model in small batches -> look ...
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


def _refs(name: str, views: list[str] | None) -> dict:
    """Reference masks by view (all configured views when views is None)."""
    cfg_p = store.refs_dir(name) / "refs.json"
    cfg = json.loads(cfg_p.read_text()) if cfg_p.exists() else {}
    views = views or list(cfg)
    if not views:
        raise ValueError("no references set; use set_reference first")
    for v in views:
        if v not in cfg:
            raise ValueError(f"no reference for view {v!r}")
    return {v: cmp.reference_mask(cfg[v]["path"], cfg[v]["flip"], cfg[v]["threshold"]) for v in views}


def _spec_arg(spec) -> dict:
    return json.loads(spec) if isinstance(spec, str) else spec


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
    """Parameters and defaults for the kits (hand, face) and for strokes (clay, crease, flatten)."""
    from . import kits, strokes
    return kits.__doc__ + "\n\nSTROKES\n" + strokes.__doc__


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
         matcap: str = "clay_studio.exr", strokes: bool = False, shading: str = "clay"):
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
    an evenly tinted area is blobby; crisp forms show as bright lines)."""
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
        paths = _stroke_paths(store.load(name), frames)
        imgs = [render.draw_strokes(im, f, paths) for im, f in zip(imgs, frames)]
    sheet = render.contact_sheet(imgs, frames, grid)
    lo, hi = full_bounds
    dims = [round(h - l, 3) for l, h in zip(lo, hi)]
    info = (f"{name}: {meta['verts']} verts, voxel {meta['voxel']:.4f}, built in {meta['seconds']}s | "
            f"size X{dims[0]} Y{dims[1]} Z{dims[2]}")
    return [_png(sheet), info]


def _curvature_mesh(name: str, mesh: Path, voxel: float, bounds) -> Path:
    """The built mesh plus per-vertex curvature colours (Laplacian of the exact field)."""
    from . import sdf
    from .spec import compile_prims
    z = dict(np.load(mesh))
    prims = compile_prims(store.load(name))
    v = z["verts"].astype(np.float64)
    h = 0.75 * voxel
    lap = -6 * sdf.field_at(prims, v)
    for k in range(3):
        e = np.zeros(3)
        e[k] = h
        lap += sdf.field_at(prims, v + e) + sdf.field_at(prims, v - e)
    lap /= h * h
    size = float(np.max(np.asarray(bounds[1]) - np.asarray(bounds[0])))
    z["colors"] = render.curvature_colours(lap, size, voxel)
    out = mesh.with_name(mesh.stem + "_curv.npz")
    np.savez(out, **z)
    return out


def _stroke_paths(spec: dict, frames: list[dict]) -> list[dict]:
    """Every stroke's seated path (mirrored ones too), with per-view visibility: a point counts as hidden
    when the ray from just off the finished surface toward the camera enters the body."""
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
        stem, _, rep = base.rpartition("_r")
        src = next((k for k in stored if k in (bname, base + ".L", base, stem, stem + ".L")), None)
        st = stored.get(src, {})
        op = "flatten" if bl["shape"] == "flatten" else ("clay" if np.min(bl["depth"]) >= 0 and np.max(bl["depth"]) > 0 else "crease")
        count = int((st.get("repeat") or {}).get("count", 1))
        label = None
        if not bname.endswith(".R"):
            label = src if count == 1 else (f"{src} x{count}" if rep == "0" else None)
        P = np.asarray(bl["pts"], float) + np.asarray(bl.get("at", [0, 0, 0]), float)
        N = np.asarray(bl["nrm"], float)
        if len(N) != len(P):
            N = np.broadcast_to(N[0], P.shape)
        span = float(np.ptp(P, axis=0).max()) + 0.5
        vis = {}
        for f in frames:
            dv = np.asarray(f["dir"], float)
            dv /= np.linalg.norm(dv)
            lift = 0.01 + 0.02 * np.abs(np.asarray(bl.get("depth", [0.0]), float)).max()
            ts = np.linspace(0.0, span, 200)
            rays = (P + N * lift)[:, None, :] + ts[None, :, None] * dv
            vis[f["name"]] = ~(sdf.field_at(prims, rays) < 0).any(axis=1)
        out.append({"label": label, "op": op, "pts": P, "vis": vis})
    return out


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
def compare(name: str, views: list[str] | None = None, fit: str = "auto", resolution: int = 160):
    """Compare model silhouettes to the references. Per view: IoU, a diff image
    (grey = match, red = model has extra, blue = model is missing) and band tables of edge errors
    in world units, which tell you which joint/blob to move and by how much.
    fit: "auto" searches the reference scale/offset for best overlap, so only shape differences remain
    (absolute size is ignored); "height"/"width" instead match that dimension, bottom-aligned."""
    store.build(name, resolution)
    out = []
    for v, ref in _refs(name, views).items():
        iou, diff, report = cmp.compare(store.silhouette(name, v), ref, fit)
        out += [_png(diff), f"[{v}] {report}"]
    return out


@mcp.tool(structured_output=False)
def fit(name: str, views: list[str] | None = None, only: list[str] | None = None,
        lock: list[str] | None = None, params: list[str] | None = None, iterations: int = 20,
        max_step: float = 0.02, stiffness: float = 0.05, align: str = "auto", resolution: int = 160):
    """Auto-fit the model to its reference silhouettes and save the result as a new version.
    Moves joints, joint/bone radii, blob offsets and blob sizes (params: any of "pos", "r", "offset",
    "size") to minimise the distance between model and reference outlines. Only what the given views can
    see changes: a side-only fit leaves X alone. Details (subtract ops, layer>=1 blobs) stay fixed unless
    named in `only`; `only`/`lock` take joint, bone and blob names. max_step caps any move per iteration (m);
    stiffness is a spring toward the starting values (higher = more conservative).
    Block out the body plan by hand first: fitting is local and can't fix a missing or misplaced limb.
    Returns the diff images, IoU before/after and every change; `revert` undoes it."""
    refs = _refs(name, views)
    res = fitmod.fit(store.load(name), refs, align, tuple(params or fitmod.GROUPS), only, tuple(lock or ()),
                     iterations, max_step, stiffness, resolution)
    ver = store.save(name, res.spec, "fit " + " ".join(
        f"{v} {res.iou_before[v]:.3f}->{res.iou_after[v]:.3f}" for v in refs))
    out = []
    for v, im in fitmod.diff_images(res).items():
        out += [_png(im), f"[{v}] IoU {res.iou_before[v]:.3f} -> {res.iou_after[v]:.3f}"]
    out.append(f"saved {name} v{ver}\n" + "\n".join(res.log) + "\n\nchanges:\n" + "\n".join(res.changes or ["(none)"]))
    return out


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
