"""Face shapes posed in a look, and a character's rest expression (face_shapes.rest).

look(shapes={"jawOpen": 0.8, ...}) shows a face-kit model posed in ARKit weights in seconds, with no export: the
model is meshed as export_asset meshes it (the slit's part at face.voxels(), so the lips' inner faces are real;
cached by geometry), and the export's own code (faceshapes.apply: the neutral's close, the seal, every shape's
displacement) runs on that mesh. Only the vertices near the face are worked on. Correctives are set as the export's
notes tell an engine to (faceshapes.playback: jawOpen_mouthSmile = min(jawOpen, mouthSmile)); one given by hand is
kept and said. Weights are absolute, as an engine sets them: a rest expression is not added to them;
shapes="rest" shows it. The difference from the GLB is the export's decimation only (the low poly samples the same
displacement field; the seal is measured on whichever mesh it runs on).

The painted look carries the posed mesh's moves onto the scene's own (coarser) meshes: each scene vertex takes the
move of the nearest posed point of its own part (blender_scene.render, job["shape_pose"]). Where the scene meshes the
slit's part coarser than the export, the lips are not separate surfaces there and can stretch: said in the info line.

Rest expression: spec face_shapes.rest = {ARKit name: weight} (a grin, a scowl). It is carried, not baked: the
export's meshes keep the true neutral (mouth closed) and their glTF mesh.weights (the default morph weights every
glTF loader applies, Playweft's pw-gltf included) are the rest weights, correctives filled in; mesh.extras.
restExpression names them for an engine to return to after a clip. Baking (rest mesh = the expression, shapes
re-based) was measured worse (`compare_rest`): correctives are min() of ABSOLUTE weights, and a closed mouth, a
blink over the grin or a viseme needs weights below the rest, i.e. negative ones that engines clamp to 0.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np

from . import faceshapes
from . import spec as specmod
from . import store

NEAR = 1.0  # x the reach apply() uses (3 face widths + 2 head radii): vertices past it are not worked on
ZERO = 1e-6


def rest_of(spec: dict) -> dict:
    """face_shapes.rest validated: {ARKit name: weight in [0, 1]} ({} when none)."""
    rest = (spec.get("face_shapes") or {}).get("rest")
    if not rest:
        return {}
    if not isinstance(rest, dict):
        raise specmod.SpecError('face_shapes.rest is {ARKit name: weight}, e.g. {"mouthSmileLeft": 0.4, ...}')
    return weights(rest, "face_shapes.rest")


NOTES: list = []  # what the last weights() call said (a corrective set off its formula)


def weights(shapes: dict, where: str = "shapes") -> dict:
    """ARKit weights (+ correctives, filled in by their formula) for a pose. A corrective given by hand is kept,
    and said (NOTES): an engine following the rig notes sets it by its formula instead."""
    shapes = dict(shapes)
    given = {c: float(shapes.pop(c)) for c in list(shapes) if c in faceshapes.CORRECTIVES}
    try:
        w = faceshapes.expression(shapes)
    except ValueError as e:
        raise specmod.SpecError(f"{where}: {e}") from None
    out = faceshapes.playback(w)
    present = faceshapes.names_of([n for n in w])
    out = {k: v for k, v in out.items() if k in w or k in present}
    bad = {c: (v, out.get(c, 0.0)) for c, v in given.items() if abs(v - out.get(c, 0.0)) > 0.01}
    NOTES[:] = [f"{where}: {c} {v:.2f} kept as given; its formula {faceshapes.CORRECTIVES[c][0]}("
                f"{', '.join(faceshapes.CORRECTIVES[c][1:])}) gives {f:.2f}, which an engine following the rig notes "
                "sets" for c, (v, f) in bad.items()]
    out.update({c: v for c, v in given.items() if c in present})
    return out


def resolve(spec: dict, shapes) -> dict:
    """A look's shapes argument: {name: weight}, "rest" (face_shapes.rest) or a preset name."""
    if shapes == "rest":
        r = rest_of(spec)
        if not r:
            raise specmod.SpecError('shapes="rest": the model has no face_shapes.rest')
        return r
    if isinstance(shapes, str):
        try:
            return weights(faceshapes.expression(shapes))
        except ValueError as e:
            raise specmod.SpecError(str(e)) from None
    if not isinstance(shapes, dict):
        raise specmod.SpecError('shapes is {ARKit name: weight}, "rest" or a preset name')
    return weights(shapes)


def _key(spec: dict, resolution: int, voxels: dict) -> str:
    from . import base as basemod
    return hashlib.sha1((json.dumps(specmod.expand_mirror(specmod.geometry(spec)), sort_keys=True, default=float)
                         + f"@{resolution}/{store.BUILD_VERSION}/{json.dumps(voxels, sort_keys=True)}"
                         + (f"/base{basemod.VERSION}" if spec.get("base") else "")).encode()).hexdigest()[:12]


def fine_mesh(name: str, spec: dict, resolution: int, log: list) -> Path:
    """The model meshed as export_asset meshes it for face shapes (asset.split with the face's voxels), cached."""
    from . import asset
    face = faceshapes.face_of(spec)
    vox = face.voxels()
    key = _key(spec, resolution, vox)
    bd = store._dir(name) / "build"
    bd.mkdir(exist_ok=True)
    path, meta = bd / "face_fine.npz", bd / "face_fine.json"
    if path.exists() and meta.exists() and json.loads(meta.read_text()).get("key") == key:
        log.append("face mesh: cached")
        return path
    t = time.time()
    ctx = asset.split(spec, resolution, True, log, min_share=1, voxels=vox)
    asset.mesh_parts(ctx, path)
    meta.write_text(json.dumps({"key": key, "voxels": vox}))
    log.append(f"face mesh: meshed as the export does ({', '.join(f'{k} {v * 1000:.2f} mm' for k, v in vox.items())})"
               f" in {time.time() - t:.1f}s (cached until the geometry changes)")
    return path


def _region(name: str, spec: dict, resolution: int, names: list, log: list) -> dict:
    """The fine mesh's face region as apply() parts, the shapes `names` on it (neutral + seal cached by geometry)."""
    face = faceshapes.face_of(spec)
    fp = fine_mesh(name, spec, resolution, log)
    z = dict(np.load(fp))
    V, F, P = z["verts"].astype(np.float64), z["faces"], z["part"]
    pnames = [str(n) for n in z["part_names"]]
    near_v = np.linalg.norm(V - face.M, axis=1) < NEAR * (3 * face.width + 2 * face.R)
    fpart = P[F[:, 0]]
    parts, rows = {}, {}
    for i, pn in enumerate(pnames):
        tri = F[(fpart == i) & near_v[F].all(1)]
        if not len(tri):
            continue
        ids = np.unique(tri)
        remap = np.full(len(V), -1, np.int64)
        remap[ids] = np.arange(len(ids))
        parts[pn] = {"verts": V[ids], "corner_vert": remap[tri].ravel()}
        rows[pn] = ids
    np_ = fp.with_name("face_neutral.npz")
    key = json.loads(fp.with_name("face_fine.json").read_text())["key"]
    neutrals = {}
    if np_.exists():
        with np.load(np_) as zn:
            if str(zn["key"]) == key:
                neutrals = {k: zn[k] for k in zn.files if k != "key"}
    fresh = not neutrals
    faceshapes.apply(spec, parts, names or ["jawOpen"], log, quick=True, neutrals=neutrals)
    if fresh:  # (no shape: the neutral alone, which apply() sets with any shape)
        np.savez(np_, key=np.array(key), **neutrals)
    return {"V": V, "F": F, "P": P, "pnames": pnames, "parts": parts, "rows": rows}


def _posed(R: dict, w: dict) -> dict:
    """{part: the region's posed verts} at weights w."""
    return {pn: np.asarray(p["verts"], np.float64) + sum((w.get(nm, 0.0) * np.asarray(sh[0], np.float64)
                                                          for nm, sh in (p.get("shapes") or {}).items()), 0.0)
            for pn, p in R["parts"].items()}


def pose(name: str, shapes, resolution: int = 256, log: list | None = None) -> tuple[Path, dict]:
    """Mesh + pose: writes build/face_posed.npz (verts, faces, normals, part, part_names, part_colors) and returns
    (path, {"weights", "moved": {part: (rows of the mesh, their move)}, "rest": meshed verts, "seconds"})."""
    log = [] if log is None else log
    t = time.time()
    spec = store.load(name)
    w = resolve(spec, shapes)
    R = _region(name, spec, resolution, [n for n in w if n not in faceshapes.CORRECTIVES], log)
    V, F, P, pnames = R["V"], R["F"], R["P"], R["pnames"]
    X = V.copy()
    moved = {}
    for pn, Xp in _posed(R, w).items():
        d = Xp - V[R["rows"][pn]]
        if (np.linalg.norm(d, axis=1) > ZERO).any():
            X[R["rows"][pn]] = Xp
            moved[pn] = (R["rows"][pn], d)  # (the whole region: still points hold the scene's far vertices)
    defs = spec.get("parts") or {}
    out = store._dir(name) / "build" / "face_posed.npz"
    np.savez(out, verts=X.astype(np.float32), faces=F, normals=faceshapes.vertex_normals(X, F).astype(np.float32),
             part=P, part_names=np.array(pnames),
             part_colors=np.concatenate([np.tile(store.part_colour(pn, defs, i), ((P == i).sum(), 1))
                                         for i, pn in enumerate(pnames)]))
    return out, {"weights": w, "moved": moved, "seconds": round(time.time() - t, 1), "rest": V}


def scene_moves(info: dict, path: Path) -> Path:
    """The posed points' moves for the painted look (blender_scene.render's job["shape_pose"]): per part, the
    meshed (rest) points in a box round those that move (a quarter of its size past them) and their moves; the
    still ones hold the scene's vertices out there."""
    V = info["rest"]
    arrs = {}
    for pn, (ids, d) in info["moved"].items():
        mv = np.linalg.norm(d, axis=1) > ZERO
        lo, hi = V[ids[mv]].min(0), V[ids[mv]].max(0)
        pad = 0.25 * float((hi - lo).max())
        lo, hi = lo - pad, hi + pad
        inb = np.all((V[ids] >= lo) & (V[ids] <= hi), 1)
        arrs[f"{pn}|at"] = V[ids[inb]].astype(np.float32)
        arrs[f"{pn}|d"] = d[inb].astype(np.float32)
        arrs[f"{pn}|box"] = np.array([lo, hi], np.float32)
    np.savez(path, **arrs)
    return path


def note(spec: dict, w: dict, secs: float, scene_voxel: float | None = None) -> str:
    face = faceshapes.face_of(spec)
    s = (f"posed in face shapes ({secs}s): " + ", ".join(f"{k} {v:.2f}" for k, v in w.items() if v)
         + " (absolute weights, correctives by formula unless given)" + "".join(" | " + n for n in NOTES))
    if scene_voxel is not None:
        need = face.voxels().get(face.slit_part)
        if need and scene_voxel > need * 1.05:
            s += (f" | the painted scene meshes {face.slit_part} at {scene_voxel * 1000:.1f} mm, the export at "
                  f"{need * 1000:.2f}: the lips are not separate there and can stretch; the clay look "
                  "(paint=False) is meshed as the export is")
    return s


def compare_rest(name: str, rest: dict, targets: dict, resolution: int = 256) -> dict:
    """Evidence for carrying the rest instead of baking it: for each target pose (absolute ARKit weights), the
    largest vertex error (mm) a baked rest gives (rest mesh = rest pose, engine weights = target - rest, clamped
    to [0, 1] as engines do, correctives by formula on those engine weights) against the true pose."""
    spec = store.load(name)
    r = weights(rest)
    allw = dict.fromkeys(r, 0.0)
    for t in targets.values():
        allw.update(dict.fromkeys(weights(t), 0.0))
    R = _region(name, spec, resolution, [n for n in allw if n not in faceshapes.CORRECTIVES], [])
    base = _posed(R, r)
    res = {}
    for tn, t in targets.items():
        tw = weights(t)
        true = _posed(R, tw)
        eng = {k: min(1.0, max(0.0, tw.get(k, 0.0) - r.get(k, 0.0)))
               for k in set(tw) | set(r) if k not in faceshapes.CORRECTIVES}
        ew = faceshapes.playback(eng)
        rest0 = _posed(R, {})
        baked = {pn: base[pn] + (_posed(R, ew)[pn] - rest0[pn]) for pn in R["parts"]}
        res[tn] = round(max(float(np.linalg.norm(true[pn] - baked[pn], axis=1).max()) for pn in R["parts"]) * 1000, 2)
    return res
