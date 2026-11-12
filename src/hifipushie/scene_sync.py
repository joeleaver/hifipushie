"""`sync` and `pull`: what comes back from Blender (parameters, decals, painted masks), clashes, part hashes,
`look`. Part of the live Blender scene (scene.py has the overview)."""
from __future__ import annotations

import hashlib
import json
import tempfile
import time
from pathlib import Path

import numpy as np

from . import assemble, render, sdf, store
from . import assemble_expand
from . import asset_split
from .spec import SpecError
from . import scene
from .scene import _blender_live, blend_path, live_session
from .scene_objects import objects, part_voxel

def pull(name: str, log: list | None = None) -> dict:
    """Instance edits a person made in the scene, applied to the spec: from their running Blender when it has the
    scene open (`live_session`), else from the saved file. Returns {instance: new placement}."""
    log = [] if log is None else log
    bp = blend_path(name)
    if not bp.exists():
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "pull.json"
        job = {"mode": "pull", "blend": str(bp), "out": str(out)}
        if live_session(name):  # the person's running Blender: their unsaved moves and tweaks, as they are
            _blender_live(job)
            log.append("pulled from the live Blender session")
        else:
            scene._blender(job)
        got = json.loads(out.read_text())
        spec = store.load(name)
        changes = _pull_params(spec, got["params"], log)
        changes.update(_pull_painted(spec, got.get("painted") or {}, log))
        changes.update(_pull_decals(spec, got.get("decals") or {}, log))
        if got.get("cloth"):  # garments a person re-coloured or sculpted in the scene (cloth.pull_garments)
            from . import cloth
            changes.update(cloth.pull_garments(spec, name, got["cloth"], log))
        hair_changed = False
        if got.get("hair"):  # locks a person moved, re-shaped or re-numbered (hair.pull_locks)
            from . import hair_look
            hc = hair_look.pull_locks(spec, name, got["hair"], log)
            changes.update(hc)
            hair_changed = bool(hc)
    moved = got["moved"]
    if not moved:
        if changes:
            store.save(name, spec, "from the Blender scene: " + ", ".join(changes))
        _restamp_hair(name, hair_changed, log)
        return changes
    pls = assemble_expand.placements(spec)
    for inst, m in moved.items():
        d = (spec.get("instances") or {}).get(inst)
        fw = (pls.get(inst) or {}).get("from_wall")
        if d is None and fw:  # a wall's door: its swing goes back into the opening's "open"; the rest is the wall's
            wn, k, kind = fw[:3]
            M = np.asarray(m)
            if kind == "door":
                rz = float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))
                a = ((rz - fw[3]) * fw[4] + 180.0) % 360.0 - 180.0
                spec["walls"][wn]["openings"][k]["open"] = round(max(a, 0.0), 1)
                changes[inst] = {"open": round(max(a, 0.0), 1)}
                log.append(f"{inst}: wall {wn!r} opening {k} now open {max(a, 0.0):.0f} deg (from the scene)")
            else:
                log.append(f"{inst}: moved in the scene, but it's placed by wall {wn!r}: move the opening in the spec")
            continue
        if d is None:
            log.append(f"{inst}: moved in the scene, but it's the mirror of a '.L' instance: move that one")
            continue
        M = np.asarray(m)
        L = M[:3, :3]
        sc = float(np.cbrt(np.linalg.det(L)))
        rot_user = np.asarray(assemble._euler_of(L / sc))
        # the weather moved it from the spec's placement by these offsets; take them back out
        at0 = list(d.get("at", [0, 0, 0]))
        at0 = at0 + [0.0] * (3 - len(at0))  # "on" instances may give [x, y]
        d_at = np.asarray(pls[inst]["at"], float) - np.asarray(at0, float)
        d_rot = np.asarray(pls[inst]["rot"], float) - np.asarray(d.get("rot", [0, 0, 0]), float)
        new = {"at": assemble._r(M[:3, 3] - d_at), "rot": [round(float(v), 3) for v in rot_user - d_rot]}
        if abs(sc - float(d.get("scale", 1.0))) > 1e-4:
            new["scale"] = round(sc, 4)
        spec["instances"][inst] = {**d, **new}
        if "on" in d:  # slid along its support: it stays "on" it; lifted, lowered or moved off it: where it was put
            off = abs(float(M[2, 3]) - float(pls[inst]["at"][2])) > 0.01
            if not off:
                try:
                    assemble_expand.expand(spec)
                except SpecError:
                    off = True
            if off:
                new["at"] = assemble._r(M[:3, 3] - np.append(d_at[:2], 0.0))
                spec["instances"][inst] = {k: v for k, v in {**d, **new}.items() if k not in ("on", "lift")}
                log.append(f"{inst}: no longer set down \"on\" {d['on']} (moved off it in the scene)")
            else:  # still on it: only x, y are the person's; z stays found
                new["at"] = new["at"][:2]
                spec["instances"][inst] = {**d, **new}
        changes[inst] = new
        log.append(f"{inst}: {json.dumps(new)} (from the scene)")
    store.save(name, spec, "from the Blender scene: " + ", ".join(changes))
    _restamp_hair(name, hair_changed, log)
    for inst in moved:  # a person's move can land an instance inside something: say so
        hit = clashes(spec, inst)
        if hit:
            log.append(f"{inst} now cuts into " + ", ".join(f"{n} ({d * 1000:.0f} mm)" for d, n in hit[:4])
                       + ": move it in the scene, or `scene_sync.clear_of(name, instance)` slides it out")
    return changes


def _restamp_hair(name: str, changed: bool, log: list) -> None:
    """After hair locks came back from a person's live Blender, sync them straight back so each scene lock carries
    the hash of its new spec version: left stamped with the old one, the next edit to the same lock read as
    "stale" and was dropped (found hand-shaping dg_hh). Headless pulls leave the file alone (the next sync does it)."""
    if changed and live_session(name):
        from . import hair_look
        hair_look.sync(name)
        log.append("hair: the edited locks re-stamped in the live session")


def _clash_setup(spec: dict, inst: str, voxel: float, tol: float):
    """The instance's inside (grid points over its box, and how deep each is) and everything else's prims."""
    from .spec import compile_prims, geometry
    prims = compile_prims(geometry(spec))
    own = [p for p in prims if p.instance == inst]
    if not own:
        return None
    adds = [p for p in own if p.op == "add"]
    lo, hi = np.min([p.lo for p in adds], 0), np.max([p.hi for p in adds], 0)
    ax = [np.arange(a, b + voxel, voxel) for a, b in zip(lo, hi)]
    P = np.stack(np.meshgrid(*ax, indexing="ij"), -1).reshape(-1, 3)
    fo = sdf.field_at(own, P)
    inside = fo < -tol
    return P[inside], -fo[inside], [p for p in prims if p.instance != inst]


def _clash_at(P, depth_own, rest, tol: float, shift=np.zeros(3), names: bool = True) -> list:
    """Clashes of the instance's inside points moved by `shift` with the rest: [(depth, element)], deepest first
    (names=False: just [(depth, None)] if it clashes, for searches)."""
    Q = P + shift
    if not len(Q):
        return []
    near = [p for p in rest if p.op == "add" and np.all(p.hi >= Q.min(0)) and np.all(p.lo <= Q.max(0))]
    if not near:
        return []
    depth = np.minimum(depth_own, -sdf.field_at(near, Q))
    deep = np.flatnonzero(depth > tol)
    if not names:
        return [(float(depth.max()), None)] if len(deep) else []
    out = {}
    for i in deep[np.argsort(depth[deep])[-300:]]:  # name each clash by the other element nearest the point
        el = min(near, key=lambda p: float(sdf.SDF[p.kind](Q[i:i + 1], p.params)[0]))
        out[el.name] = max(out.get(el.name, 0.0), float(depth[i]))
    return sorted(((d, n) for n, d in out.items()), reverse=True)


def clashes(spec: dict, inst: str, voxel: float = 0.005, tol: float = 0.003) -> list:
    """Where an instance cuts into anything else: on a grid over its box, points inside both its own field and
    the rest's; depth = how far inside both. Returns [(depth m, the other element)], deepest first, over tol."""
    st = _clash_setup(spec, inst, voxel, tol)
    return [] if st is None else _clash_at(*st, tol)


def clear_of(name: str, inst: str, step: float = 0.005, reach: float = 0.25, log: list | None = None) -> dict | None:
    """Slide an instance the least distance sideways (8 directions in the ground plane, `step` apart) until it cuts
    into nothing, keeping its rotation. Its inside is sampled once and tested shifted. Saves and returns the new
    instance, or None if it was clear already or nothing within reach works."""
    log = [] if log is None else log
    spec = store.load(name)
    tol = 0.003
    st = _clash_setup(spec, inst, 0.01, tol)  # searched on a 1 cm grid, the answer checked at 5 mm
    fine = _clash_setup(spec, inst, 0.005, tol)
    if st is None or not _clash_at(*fine, tol, names=False):
        return None
    d0 = spec["instances"][inst]
    for r in np.arange(step, reach + 1e-9, step):
        for a in np.radians(np.arange(0, 360, 45)):
            t = r * np.array([np.cos(a), np.sin(a), 0.0])
            if not _clash_at(*st, tol, t, names=False) and not _clash_at(*fine, tol, t, names=False):
                at = np.asarray(d0.get("at", [0, 0, 0]), float) + t
                spec["instances"][inst] = {**d0, "at": [round(float(x), 3) for x in at]}
                store.save(name, spec, f"{inst} slid {r * 1000:.0f} mm clear of what it cut into")
                log.append(f"{inst}: at {spec['instances'][inst]['at']} ({r * 1000:.0f} mm)")
                return spec["instances"][inst]
    return None


def _at(spec, path):
    x = spec
    for k in path:
        x = x[k]
    return x


def _pull_params(spec: dict, params: dict, log: list) -> dict:
    """Paint numbers changed in the scene's materials, written into the spec (by their json path)."""
    from . import paint
    changes = {}
    for key, vals in params.items():
        path = json.loads(key)
        try:
            cur = _at(spec, path)
        except (KeyError, IndexError, TypeError):
            if path[-1] == "opacity":
                cur = 1.0
            else:
                continue
        if isinstance(cur, (str, list)) and path[-1] == "color":
            cur_rgb = paint.colour(cur)
            new = next((v for v in vals if np.abs(np.asarray(v) - cur_rgb).max() > 2e-3), None)
            if new is None:
                continue
            val = "#" + "".join(f"{int(round(min(max(c, 0), 1) * 255)):02x}" for c in new)
        else:
            new = next((v for v in vals if abs(float(v) - float(cur)) > 1e-4), None)
            if new is None:
                continue
            val = round(float(new), 4)
        x = spec
        for k in path[:-1]:
            x = x[k]
        x[path[-1]] = val
        changes[".".join(str(k) for k in path[1:])] = val
        log.append(f"paint {'.'.join(str(k) for k in path[1:])}: {cur} -> {val} (from the scene)")
    return changes


def decal_gizmos(spec: dict, log: list) -> list:
    """Every image decal's gizmo for the scene (images_gizmo.gizmo): {"name", "path" (json path to the image entry),
    "matrix", "verts", "edges"}."""
    from . import images
    from . import images_frame, images_gizmo
    from .spec import expand_mirror
    ents = images_gizmo.decal_entries(spec)
    if not ents:
        return []
    s = expand_mirror(spec)
    groups: dict = {}  # entries placed alike (a picture, its relief and its brushwork) share one gizmo
    for path, img, ly, parts in ents:
        key = json.dumps([{k: img.get(k) for k in sorted(images.PLACE_KEYS)}, parts], sort_keys=True, default=str)
        groups.setdefault(key, []).append((path, img, ly, parts))
    out = []
    for g in groups.values():
        path, img, ly, parts = g[0]
        try:
            fr = images_frame.frame(spec, img, s, parts=parts)
        except Exception as e:  # noqa: BLE001 (a decal that can't be placed has no gizmo; save validates them)
            log.append(f"decal {ly}: no gizmo ({e})")
            continue
        out.append({"name": "decal:" + "+".join(".".join(str(k) for k in p[1:-1]) for p, *_ in g),
                    "path": json.dumps([p for p, *_ in g]), **images_gizmo.gizmo(fr)})
    return out


def _pull_decals(spec: dict, decals: dict, log: list) -> dict:
    """Decal gizmos a person moved, turned or scaled in the scene, written into their image entries
    (images_gizmo.from_gizmo)."""
    from . import images_frame, images_gizmo
    changes = {}
    for key, m in decals.items():
        paths = json.loads(key)
        paths = [paths] if paths and not isinstance(paths[0], list) else paths  # (one entry, or several placed alike)
        # each worked out against the spec as it was pulled: the placement keys the gizmo's entries shared
        found = []
        for path in paths:
            label = ".".join(str(k) for k in path[1:-1])
            try:
                found.append((path, label, _at(spec, path), spec["paint"][path[1]].get("part", "body")))
            except (KeyError, IndexError, TypeError, AttributeError):
                log.append(f"decal {label}: moved in the scene, but the spec has no such image any more")
        for path, label, img, parts in found:
            try:
                new, notes = images_gizmo.from_gizmo(spec, img, parts, m["was"], m["now"])
                if new is not None:
                    images_frame.frame(spec, new, parts=parts, what=f"decal {label}")  # still a placement that works?
            except SpecError as e:
                log.append(f"decal {label}: its gizmo's new placement doesn't work, left as it was ({e}); move it "
                           f"back in the scene, or the next sync puts it back")
                continue
            for n in notes:
                log.append(f"decal {label}: {n}")
            if new is None:
                continue
            _at(spec, path[:-1])[path[-1]] = new
            diff = {k: new.get(k) for k in sorted(set(new) | set(img)) if new.get(k) != img.get(k)}
            changes[f"{label}.image"] = diff
            log.append(f"decal {label}: {json.dumps(diff)} (from the scene)")
    return changes


def _pull_painted(spec: dict, painted: dict, log: list) -> dict:
    """Masks a person painted in the scene (the objects' "hp_paint:<layer>" colour attributes, each file every
    object's points for one layer), stored as point clouds and put into their layers."""
    from . import paint
    from . import paint_masks
    changes = {}
    for ly, f in painted.items():
        if ly not in (spec.get("paint") or {}):
            log.append(f"hp_paint:{ly} was painted in the scene, but the spec has no paint layer {ly!r}: add one "
                       f"(with \"painted\": \"new\") and paint again")
            continue
        with np.load(f) as z:
            pid = paint_masks.save_painted(z["pos"], z["nrm"], z["val"], z["spacing"])
        if paint_masks.hand_painted(spec).get(ly, (None,))[0] == pid:  # pulled already (the scene not synced since)
            continue
        paint_masks.set_painted(spec, ly, pid)
        changes[f"{ly}.painted"] = pid
        with np.load(paint.painted_path(pid)) as z:
            n, on = len(z["val"]), int((z["val"] > 0.5).sum())
        log.append(f"paint {ly}: hand-painted mask {pid} ({on} points over half, {n} kept) from the scene")
    return changes


def sync(name: str, resolution: int = 256) -> dict:
    """Pull a person's edits, then bring scene.blend in line with the spec. Returns timings and the log.
    Moving a prop re-measures at most that prop (nothing depends on where props stand)."""
    t = time.time()
    log: list = []
    pulled = pull(name, log)
    t1 = time.time()
    objs, insts, prog = objects(name, resolution, log)
    t2 = time.time()
    spec = store.load(name)
    from .base_implied import part_defs
    defs = part_defs(spec)
    bases = {}
    from . import skin_params
    sk = skin_params.part_base(spec)  # the skin part starts from its tone and shading; the part's own keys win
    from .skin_features_eyes import eye_base
    ek = eye_base(spec)  # the eyes' tear film (a clear coat), likewise
    for o in objs:
        d = defs.get(o["part"]) or {}
        if ek and o["part"] == ek[0]:
            d = {**ek[1], **d}
        from .paint import style_rgb
        if sk and o["part"] == sk[0]:
            d = {**{k: v for k, v in sk[1].items() if not k.startswith("_")}, **d}
            if "color" not in (defs.get(o["part"]) or {}):
                o = {**o, "color": sk[1]["color"]}
        rgb = style_rgb(o["color"][:3], (spec.get("style") or {}).get("paint") or {})
        bases[o["part"]] = {"color": [float(x) for x in rgb], "roughness": float(d.get("roughness", 0.6)),
                            "metallic": float(d.get("metallic", 0.0)), "specular": float(d.get("specular", 0.5)),
                            **{k: float(d[k]) for k in ("transmission", "alpha", "ior", "subsurface",
                                                         "subsurface_scale", "coat", "coat_roughness", "sheen",
                                                         "sheen_roughness", "thickness") if k in d},
                            **({"subsurface_radius": [float(x) for x in d["subsurface_radius"]]}
                               if "subsurface_radius" in d else {})}
    ph = part_hashes(prog, bases)
    job = {"mode": "sync", "blend": str(blend_path(name)), "objects": objs, "instances": insts,
           "program": prog, "bases": bases, "prog_hash": ph, "decals": decal_gizmos(spec, log)}
    if spec.get("hair"):  # the hair's curve locks (hair.py) ride along
        from . import hair_job
        job["hair"] = hair_job.job(name, spec)
    if spec.get("cloth") is not None:  # simulated garments (cloth.py): sewn and settled on the body, as meshes
        from . import cloth
        job["cloth"] = cloth.scene_job(name, spec, log)
    from . import lashes  # eyelash ribbons on a human head's lid margins (lashes.py); None removes them
    job["lashes"] = lashes.scene_job(name, spec, store._dir(name) / "scene_cache")
    if job["lashes"]:
        log.append(f"lashes: {job['lashes']['tris']} triangles")
    live = live_session(name)
    out = _blender_live(job) if live else scene._blender(job)
    if live:
        log.append("synced into the live Blender session (and saved it to scene.blend)")
    made = next((json.loads(line[7:]) for line in out.splitlines() if line.startswith("@@made")), [])
    rebuilt = next((json.loads(line[10:]) for line in out.splitlines() if line.startswith("@@rebuilt")), [])
    log.append(f"scene: {len(made)} objects replaced ({', '.join(made[:8])}{'...' if len(made) > 8 else ''})"
               + (f"; materials rebuilt: {', '.join(rebuilt)}" if rebuilt else ""))
    return {"blend": str(blend_path(name)), "pulled": pulled, "log": log,
            "seconds": {"pull": round(t1 - t, 1), "mesh": round(t2 - t1, 1), "blender": round(time.time() - t2, 1)}}


def part_hashes(prog: dict | None, bases: dict) -> dict:
    """Per part, what its material is built from: the layers on it, its packed inputs, its base channels, the
    noise quantiles and the node-building code. A part's material is rebuilt only when its own hash changes (one
    hash for all rebuilt every part on any paint edit: ~30-60 s on the cabin, plus shader compiles)."""
    code = hashlib.sha1(scene.SCRIPT.read_bytes()).hexdigest()
    out = {}
    for part, base in bases.items():
        layers = [ly for ly in (prog or {}).get("layers", []) if part in ly["parts"] or "*" in ly["parts"]]
        out[part] = hashlib.sha1(json.dumps([layers, ((prog or {}).get("pre") or {}).get(part),
                                             (prog or {}).get("packing", {}).get(part, {}),
                                             (prog or {}).get("quantiles"), base, code], sort_keys=True,
                                            default=str).encode()).hexdigest()[:12]
    return out


def look(name: str, views: list[str] | None = None, cameras: list[dict] | None = None, size: int = 640,
         save: str | None = None, show_layer: str | None = None, hide_parts: list[str] | None = None,
         only_parts: list[str] | None = None, flat: bool = False, clip=None, focus=None, zoom: float = 1.0,
         lighting: dict | None = None, hide_hair: bool = False, shape_pose=None):
    """Render the saved scene with EEVEE: named views (as look) and/or perspective cameras {"eye": [x,y,z],
    "target", "fov"}. show_layer: one paint layer's mask, orange on grey clay. hide_parts / only_parts: leave
    parts out (prefab parts too, in every instance; hide_hair: the hair's locks and caps); with only_parts the views frame what's shown. flat: unlit
    base colour. clip (as look): everything beyond the planes is left out of the render (the materials turn
    transparent there) and the cut solids get flat caps, their part's colour darkened. focus + zoom: the named
    views framed on that point, zoom times closer (painted close-ups at the scene's mesh resolution).
    lighting: {"lights": [{"dir", "energy", "color", "angle"}], "world": {"color", "strength"}, "look", "exposure", "view"}
    (default: the spec's style look preset, spec["style"]["look"], else one neutral sun under a grey-blue sky).
    shape_pose: facepose.scene_moves' file: the face posed in face shapes, this render only."""
    from PIL import Image
    from .spec import compile_prims, geometry
    bp = blend_path(name)
    spec = store.load(name)
    prims = [p for p in compile_prims(geometry(spec)) if p.op == "add"]
    allp = sorted({p.part for p in prims})
    bad = [p for p in (hide_parts or []) + (only_parts or []) if p not in allp]
    if bad:
        raise ValueError(f"no part(s) {bad}; parts: {allp}")
    hide = [p for p in allp if (only_parts and p not in only_parts) or p in (hide_parts or [])]
    frames = []
    if views:
        shown = [p for p in prims if p.part not in hide] or prims  # bounds for the ortho views
        lo, hi = np.min([p.lo for p in shown], 0), np.max([p.hi for p in shown], 0)
        lo, hi = lo - 0.06 * (hi - lo), hi + 0.06 * (hi - lo)
        frames += render.view_frames(np.array([[(lo, hi)[(i >> k) & 1][k] for k in range(3)] for i in range(8)]), views,
                                     focus, zoom if focus is not None else 1.0)
    for i, c in enumerate(cameras or []):
        frames.append(render.camera_frame(c, i))
    with tempfile.TemporaryDirectory() as tmp:
        for f in frames:
            f["out"] = str(Path(tmp) / f"{f['name']}.png")
        t = time.time()
        # 16 EEVEE samples look the same as the default 64 (mean 0.3/255 apart on cabin5) in half the time; glass
        # refracting the room behind it wants more
        glass = any((d or {}).get("transmission") or (d or {}).get("alpha", 1) < 1 for d in (spec.get("parts") or {}).values())
        from . import asset_gates
        asset_gates.game_light_view(lighting if lighting is not None else (spec.get("style") or {}).get("look"), f"look {name}")
        job = {"mode": "render", "blend": str(bp), "views": frames, "size": size, "hide": hide, "flat": flat,
               "hide_hair": hide_hair, **({"shape_pose": str(shape_pose)} if shape_pose else {}),
               "samples": 32 if glass else 16,
               "lighting": lighting if lighting is not None else (spec.get("style") or {}).get("look")}
        planes = store.clip_planes(clip)
        if planes:  # cut in the render only; caps where solids are cut, so walls read as walls
            job["clip"] = [[np.asarray(p, float).tolist(), np.asarray(n, float).tolist()] for p, n in planes]
            streams = {ps[0].part: ps for ps in sdf.streams(compile_prims(geometry(spec)))}
            shown = [pn for pn in streams if pn not in hide]
            defs = spec.get("parts") or {}
            from .paint import style_rgb
            colour = {pn: style_rgb(store.part_colour(pn, defs, i)[:3], (spec.get("style") or {}).get("paint") or {}) * 0.55
                      for i, pn in enumerate(streams)}
            allp_ = [p for p in compile_prims(geometry(spec)) if p.op == "add"]
            fb = np.array([np.min([p.lo for p in allp_], 0), np.max([p.hi for p in allp_], 0)])
            voxel = float((fb[1] - fb[0]).max()) / 900
            V, F, C, N = store.cap_arrays(streams, shown, defs, colour, planes, fb, voxel)
            if V:
                cp = Path(tmp) / "caps.npz"
                np.savez(cp, verts=np.concatenate(V).astype(np.float32), faces=np.concatenate(F).astype(np.int32),
                         colors=np.concatenate(C).astype(np.float32))
                job["caps"] = str(cp)
        if show_layer:  # that layer's mask alone (needs the program: compile it again)
            from . import paint, paintnodes
            names = list(paint.layers(spec))
            if not any(n == show_layer or n.startswith(show_layer + ":") for n in names):
                raise ValueError(f"no paint layer {show_layer!r}; layers: {', '.join(names)}")
            defs = spec.get("parts") or {}
            job.update(show_layer=show_layer, program=paintnodes.compile(spec),
                       bases={p: {"color": [0.5] * 3, "roughness": 0.6, "metallic": 0.0, "specular": 0.5}
                              for p in list(defs) + ["body"]})
        scene._blender(job)
        imgs = [Image.open(f["out"]) for f in frames]
    cover = None
    if show_layer:  # the mask glows orange: the share of the surface in view where it's on (alpha: surface)
        lit = seen = 0
        bg = Image.new("RGBA", imgs[0].size, (140, 150, 165, 255))
        for i, im in enumerate(imgs):
            a = np.asarray(im.convert("RGBA"), np.float64)
            surf = a[..., 3] > 127
            seen += surf.sum()
            lit += (surf & (a[..., 0] - a[..., 2] > 30)).sum()  # AgX desaturates the orange: r - b peaks ~85
            imgs[i] = Image.alpha_composite(bg, im.convert("RGBA"))
        cover = lit / max(seen, 1)
    imgs = [im.convert("RGB") for im in imgs]
    sheet = render.contact_sheet(imgs, frames)
    if save:
        sheet.save(save)
    look.coverage = cover
    look.images = list(zip([f["name"] for f in frames], imgs))  # the panels alone (colour sampling, comparisons)
    return sheet, round(time.time() - t, 1)


def slit_voxel(name: str, resolution: int = 256) -> float | None:
    """The voxel sync meshes the face kit's slit part at (None: no face kit mouth)."""
    from . import faceshapes_apply
    spec = store.load(name)
    try:
        face = faceshapes_apply.face_of(spec)
    except Exception:
        return None
    ctx = asset_split.split(spec, resolution, True, [], min_share=1)
    ps = ctx["streams"].get(face.slit_part)
    if not ps:
        return None
    pv, _ = part_voxel(ps, float(np.round(ctx["voxel"], 3)))
    own = ((spec.get("parts") or {}).get(face.slit_part) or {}).get("voxel")
    return min(pv, float(own)) if own else pv
