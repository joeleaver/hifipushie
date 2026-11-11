"""The modelling core, native in every session: list / get / put / edit a model, look, check, measure, history,
revert, and review_view (one independent look per call)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from . import compare as cmp
from . import measure as meas
from . import paint as paintmod
from . import plan as planmod
from . import render, store, surface
from .spec import empty_spec, summarize
from .mcp_app import mcp
from .tool_common import REPO, _out, _parts_note, _sil_parts, _silhouettes, _spec_arg

@mcp.tool(structured_output=False)
def list_models() -> str:
    """List saved models."""
    return json.dumps(store.list_models())


@mcp.tool(structured_output=False)
def get_model(name: str) -> str:
    """Return a model's stored spec (JSON) plus a measurement summary."""
    spec = store.load(name)
    return summarize(spec) + "\n\n" + json.dumps(spec, indent=1)


SOLIDS = """Soft primary forms (blobs): "shape": "super" (size [rx, ry, rz], "squareness" 2 = ellipsoid rising
toward a box, or "exponents" [nx, ny, nz]): a soft block with no band where a plane meets an edge. "shape": "loft"
("sections": [{"z", "half_width", "half_depth", "squareness": 2, "offset_y": 0}, ...] up its local z, z rising;
"top" / "bottom": {"z", "round": 3}): ONE seamless mass through cross-sections, e.g. a head and body as one pear,
where blended blobs leave a groove at every overlap; fit(init_loft=...) measures its sections off the outlines.
"shape": "sheet" ("spine": [[x, y, z], ...] root to tip, "curve": "spline" | "bezier" (3n + 1 controls);
"stations": [{"t": 0..1, "half_width", "half_thickness", "cup": m, "twist": deg}, ...]; "width_axis" (default: the
spine plane's normal); "root" / "tip": end rounding m): ONE seamless thick sheet folding along a curve without
twisting: a floppy ear folded through 100 degrees, a leaf, flap, cape, tongue (blades hinged or chained show seams
and knuckles). Refused when the spine bends tighter than the sheet is thick. fit moves spine points ("pos") and
station widths ("size").
Hard-surface pieces (blobs): "shape": "box" | "cylinder" (size [rx, ry, half-height], along its local
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
def put_model(name: str, spec: dict, note: str = "", joins: list[str] | None = None) -> str:
    """Make a creature, a character or a prop as a spec of joints, bones and blobs, or replace a model's whole spec
    (missing keys get defaults). The stored plan is kept unless the spec
    gives one ("plan": null drops it). joins: parts / elements whose join to the body is reported (join_report; a
    WARNING under 0.75 = a stalk). Returns a summary. Details: guide(topic="put_model")."""
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
    return _saved(name, v, full, kept) + _join_lines(name, joins)


@mcp.tool(structured_output=False)
def edit_model(name: str, ops: list[dict], note: str = "", joins: list[str] | None = None) -> str:
    """Change a model in place: move joints, set, delete or rename bones, blobs, strokes and any other named
    entry, scale radii, as one batch of edits applied atomically. ops: {"op": "set", "kind": <any top-level key with named entries:
    joints|bones|blobs|kits|strokes|paint|parts|...>, "name", "value"} (merge; null field removes), {"op":
    "set_key", "key", "value"}, {"op": "delete"|"rename", "kind", "name", "to"?}, {"op": "move", "joints", "delta"},
    {"op": "scale_r", "joints", "factor"}, {"op": "global", "value"}. Edit ".L" and centre only. joins: as
    put_model. Details: guide(topic="edit_model")."""
    spec = store.edit(store.load(name), ops)  # errors name the op: "op 3 (set blobs tooth.L): ..."
    v = store.save(name, spec, note or f"{len(ops)} ops")
    return _saved(name, v, spec) + _join_lines(name, joins)


@mcp.tool(structured_output=False)
def look(name: str, views: list[str] | None = None, size: int = 448, grid: bool = False,
         focus: list[float] | None = None, zoom: float = 1.0, resolution: int = 160,
         matcap: str = "clay_studio.exr", strokes: bool = False, shading: str = "clay", paint: bool = True,
         paint_layer: str | None = None, hide_parts: list[str] | None = None, only_parts: list[str] | None = None,
         clip: dict | list[dict] | None = None, camera: dict | list[dict] | None = None, instances: bool = False,
         save: str | None = None, shapes: dict | str | None = None):
    """See the model from any side or close up: build and render a contact sheet (clay, or painted from the Blender
    scene). views (front, side, top,
    three_quarter, back, ...), focus=[x,y,z] + zoom for close-ups, resolution (160 quick, 256-320 detail), shading
    "clay"|"raking"|"curvature"|"flat", strokes=True overlays stroke paths, paint / paint_layer (one mask),
    hide_parts / only_parts, clip (plane cuts), camera (perspective eyes), instances, save (PNG path), shapes (a
    face-kit model posed in face-shape weights as the export makes them: {"jawOpen": 0.8, ...}, "rest" or a preset;
    paint=False is meshed exactly as the export). Details: guide(topic="look")."""
    posed = None
    if shapes is not None:  # face shapes: the model meshed and posed as export_asset does it (facepose.py)
        if strokes or instances or shading == "curvature":
            raise ValueError("shapes: not with strokes, instances or curvature shading")
        from . import facepose
        posed = facepose.pose(name, shapes)  # (at the export's resolution, whatever the look's)
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
        sp = None
        if posed is not None:
            from . import facepose
            sp = facepose.scene_moves(posed[1], store._dir(name) / "build" / "face_scene_moves.npz")
        sheet, secs = scene.look(name, views or ([] if cams else (render.DEFAULT_VIEWS[:1] if closeup else render.DEFAULT_VIEWS)),
                                 cams, size, None, paint_layer, hide_parts, only_parts, flat=shading == "flat",
                                 clip=clip, focus=focus if closeup else None, zoom=zoom, hide_hair=hide_hair,
                                 shape_pose=sp)
        if save:
            sheet.save(save)
        notes = [l for l in r["log"] if "cuts into" in l or "from the scene" in l or "scene:" in l]
        if paint_layer:
            c = scene.look.coverage
            notes.insert(0, f"{paint_layer} covers " + ("NOTHING in view: misaddressed?" if c < 0.0005 else
                                                        f"{c:.1%} of the surface in view"))
        info = (f"{name}: scene look (EEVEE, painted) in {secs}s, sync {sum(r['seconds'].values()):.1f}s"
                + (f" | {'; '.join(notes)}" if notes else ""))
        if posed is not None:
            from . import facepose
            sv = scene.slit_voxel(name)
            info += " | " + facepose.note(store.load(name), posed[1]["weights"], posed[1]["seconds"], sv)
        for f, c in zip([render.camera_frame(c, i) for i, c in enumerate(cams)], cams):
            info += (f" | {f['name']}: eye ({', '.join(f'{x:.2f}' for x in f['eye'])}) -> target "
                     f"({', '.join(f'{x:.2f}' for x in f['center'])}), fov {f['fov']:.0f}" + c.get("_note", ""))
        return [_out(sheet, save), info + (f" | saved {save}" if save else "")]
    paint = paint and bool(store.load(name).get("paint"))  # geometric views: clay per part (noted)
    cam_frames = [render.camera_frame(c, i) for i, c in enumerate(cams)]
    names_ = views or ([] if cams else render.DEFAULT_VIEWS)
    planes = store.clip_planes(clip)
    if posed is not None:
        with np.load(posed[0]) as z_:
            vv = z_["verts"]
        full_bounds = [vv.min(0).tolist(), vv.max(0).tolist()]
        meta = {"mesh": str(posed[0]), "verts": len(vv), "voxel": 0.0, "seconds": posed[1]["seconds"],
                "bounds": full_bounds}
        frames = (render.view_frames(store.extent(name), names_ or render.DEFAULT_VIEWS[:1], focus, zoom)[:len(names_)]
                  if focus is not None and zoom > 1 else None)
    elif focus is not None and zoom > 1:
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
    if posed is not None:
        from . import facepose
        info += " | " + facepose.note(store.load(name), posed[1]["weights"], posed[1]["seconds"])
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


def _join_lines(name: str, joins) -> str:
    if not joins:
        return ""
    from . import joins as joinsmod
    return "\n" + joinsmod.report(name, joins)


def _resolve_camera(name: str, cam: dict) -> dict:
    """Fill in a camera's 2D eye (a person standing there: floor + eye_height) and 2D target (level gaze).
    {"fitted": label}: the camera fit_concept_camera fitted to a concept (matched.look_camera)."""
    if isinstance(cam, dict) and "fitted" in cam:
        from . import matched
        return {**matched.look_camera(matched.load_camera(name, str(cam["fitted"]))),
                **{k: v for k, v in cam.items() if k != "fitted"}}
    if not isinstance(cam, dict) or "eye" not in cam or "target" not in cam:
        raise ValueError('camera needs {"eye": [x, y, z] or [x, y], "target": [x, y, z] or [x, y], "fov"?: deg} '
                         'or {"fitted": "<label>"} (fit_concept_camera)')
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
    """How thick, wide and deep a form is: cross-section sizes from the exact field. along = a bone or bone chain (widths/heights from the axis at
    `samples` stations: pinches, bulges) or "x"|"y"|"z" (world slices between lo and hi, every separate part).
    Details: guide(topic="measure")."""
    return meas.measure(store.load(name), along, samples, lo, hi)


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
def history(name: str) -> str:
    """List saved versions of a model."""
    return "\n".join(f"v{h['version']}  {h['time']}  {h['note']}" for h in store.history(name))


@mcp.tool(structured_output=False)
def revert(name: str, version: int) -> str:
    """Undo: restore an earlier version (saved as a new version, so nothing is lost)."""
    spec = store.version_spec(name, version)
    v = store.save(name, spec, f"revert to v{version}")
    return f"{name} v{v} = v{version}\n" + summarize(spec)


# ---------------------------------------------------------------- the garment gates as tools (codified M1-M8)
# Each tool's text ends with the next step the gate rules require, generated from its result.
def _render_dir(name: str) -> Path:
    d = store.HOME / "_looks" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _has_reference(name: str, spec: dict) -> bool:
    """A reference to judge against: set_reference images, a plan with views, a garment concept / reading, or a
    head's reference pictures."""
    if (store.refs_dir(name) / "refs.json").exists() or ((spec.get("plan") or {}).get("views")):
        return True
    for g in (spec.get("cloth") or {}).values():
        if isinstance(g, dict) and (g.get("concept") or (g.get("design") or {}).get("concept") or g.get("reference")):
            return True
    return bool((spec.get("base") or {}).get("refs") or spec.get("references") or spec.get("blockin"))


DETAIL_WORDS = ("neck", "collar", "band", "cuff", "hem", "pocket", "button", "seam", "placket", "lapel", "stitch")


def framing_refusal(region: str, result: str) -> None:
    """A detail judged on a whole figure is refused (tee trials t4 / t5: a neck close-up reference against a full-figure
    render, the neck ~40 px across; the reviewer failed it "too small to judge" and its MAJORs sent the agent on 4 blind
    rounds). Whole figure: the subject (everything off the corner's background colour) spans >= 85 % of the image's
    height with background above it (a close-up is cut by the frame's top edge)."""
    if not any(w in region.lower() for w in DETAIL_WORDS):
        return
    im = np.asarray(PILImage.open(result).convert("RGB"), float)
    bg = im[2, 2]
    fg = np.abs(im - bg).sum(2) > 30
    rows = np.where(fg.any(1))[0]
    if len(rows) and (rows[-1] - rows[0]) >= 0.85 * im.shape[0] and rows[0] > 0.02 * im.shape[0]:
        raise ValueError(f"review_view: the region ({region!r}) is a detail but the result shows the whole figure; the "
                         "reviewer can't judge it at that size. Render the region close up (look_chain focus=\"neck\" | "
                         "shoulders | chest | hem | sleeve), pass one view of it, and crop the reference to the same region")


@mcp.tool(structured_output=False)
def review_view(region: str, reference: str, result: str, context: str = "", stage: str = "", not_stages: str = "",
                dry: bool = False, out_dir: str | None = None, checklist: str | None = None):
    """An independent blind review of ONE view: one region, one reference crop | one result crop (gates.md LOOK).
    Refuses contact sheets, captions, and numbers / claims in region or context. Runs a fresh reviewer with no context
    (bin/review) -> faults MAJOR / MINOR + VERDICT; dry=True returns the pair image + prompt for an independent agent
    instead. stage / not_stages scope it; out_dir. NO REFERENCE: reference="" judges the result alone against a fixed
    checklist (default "hang": how clothes hang; reviewgate.CHECKLISTS), e.g. one look_chain view. Details:
    guide(topic="review_view")."""
    import subprocess
    import tempfile
    from . import next_steps, reviewgate
    noref = not (reference or "").strip()
    if noref:
        # (lesson 2 of trials t3-t7: a trial without a reference image got no independent look at all; the fixed
        # "how clothes hang" list is the reference then)
        checklist = checklist or "hang"
        reviewgate.checklist_prompt(checklist)  # (ValueError naming the lists)
    elif checklist:
        raise ValueError("review_view: checklist is the no-reference look (reference=\"\"); with a reference the "
                         "reviewer judges against it")
    for p in ([result] if noref else [reference, result]):
        if not Path(p).exists():
            raise ValueError(f"no image {p}")
    reviewgate.refuse_inputs([result] if noref else [reference, result], [region], context)  # (raises InputRefused)
    framing_refusal(region, result)
    tool = REPO / "bin" / "review"
    if not tool.exists():
        raise RuntimeError(f"bin/review not found at {tool} (a source checkout of hifipushie has it)")
    out = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="review_", dir=_render_dir("_reviews")))
    cmd = [str(tool), str(out), f"{region}={result}" if noref else f"{region}={reference}:{result}"]
    if noref:
        cmd += ["--checklist", checklist]
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
