"""Scene and export tools: the live Blender scene (sync, pull), the machine's heavy-job queue, GLB export, the
game asset, the rig, and judging an exported asset."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import render, store
from .mcp_app import mcp
from .tool_common import _out

@mcp.tool(structured_output=False)
def rig(name: str, pose: dict | str | None = None, resolution: int = 160, size: int = 640, save: str | None = None,
        drive_twist: bool = True, glb: str | None = None, focus: str | None = None, zoom: float = 1.0,
        views: list[str] | None = None, shapes: dict | None = None, engine: bool = True):
    """The export rig (Mixamo skeleton for humanoids, named chains otherwise): fits it, skins the model and renders a
    test pose with a weights audit (lines ending "<- BAD"), twist and layer reports. pose ("seated", {} = rest, or
    {bone: [axis|"roll", deg]}), glb (judge an exported GLB instead), focus/zoom, views, shapes, drive_twist,
    engine, save. Details: guide(topic="rig")."""
    from . import rig as rigmod
    from . import rig_model, rig_report, rig_skin, rig_twist
    spec = store.load(name)
    try:
        bones = rig_report.rig_bones(spec)
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
        J, W = rig_skin.skin_mesh(spec, bones, V, F, z["part"], [str(n) for n in z["part_names"]])
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
        turns = rig_twist.resolve_turns(bones, {(k if k in names else rigmod.PREFIX + k): (v[0], v[1])
                                             for k, v in pose.items()})
    else:
        turns = rig_twist.test_pose(bones)
    P = rig_model.pose(bones, V, J, W, rig_twist.drive_twist(bones, turns) if drive_twist else turns) if turns else V
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
        driven = rig_twist.drive_twist(bones, turns) if (turns and drive_twist) else turns
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
        note += rig_audit.fused_limbs(spec, rig_report.rig_bones(spec))
    except Exception:
        pass
    from . import rig_template
    if not glb and rig_template.weights_note(spec):
        note.append(rig_template.weights_note(spec))
    text = note + text
    text += rig_report.report(spec, bones, V, F, J, W)
    flesh = None
    try:  # kit characters: skin belongs to the bone whose modelled flesh it is (a belly beside a hanging arm)
        if len(bones) == len(rig_report.rig_bones(spec)):
            flesh = rig_audit.flesh_distances(spec, rig_report.rig_bones(spec), V)
    except Exception:
        flesh = None
    text += rig_audit.audit_text(rig_audit.audit(bones, V, F, J, W, skip=skip, flesh=flesh))
    sit = rig_audit.seated(bones)
    if sit and len(lnames) > 1:  # clothes over clothes over skin: do they stay in order when the character sits
        Ps = rig_model.pose(bones, V, J, W, rig_twist.drive_twist(bones, sit))
        text += rig_audit.layers_text(rig_audit.layers(V, Fs, lpart, lnames, Ps, skip=lskip))
    return [_out(img, save), "\n".join(text)]


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
        from . import hair_look
        log: list = []
        changes = scene.pull(name, log)
        r = hair_look.sync(name)
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
