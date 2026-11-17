"""Artist retopo: the character's folder and the steps run on it (the MCP tools in tools_retopo.py call these).

A character lives in `<HIFIPUSHIE_HOME>/retopo/<name>/` (or any folder given as `name` with a "/"):
  high.ply            the fused sculpt (z up, facing -y, mirror x = 0), with vertex colours      (start)
  concept.*           the concept image                                                           (start)
  props.json          eyes and props rebuilt as primitives + the cut shapes                       (props)
  high_body.ply       the sculpt with the props cut out (rays, press and bake land on it)        (props)
  cage.py, cage_v<N>.py   the artist's cage code (every version kept: the decision log's evidence)  (cage)
  cage.ply + cage_{pinned,seams,groups}.json                                                     (cage)
  low.ply, lod1.ply, low_*.json, wire_*.png                                                      (press)
  color.png, normal.png, *_cover / island / invented / thin masks, low_uv.glb, final.glb, fin_*.png (bake)
  joints.json, rigged.glb, rom.json, rom_*.png, close_*.png, rom_sheet.jpg, close_rom.jpg         (rig)
Every Blender step runs headless under resources.heavy (one job per step; renders take the GPU lock)."""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np

from . import artretopo_check as check
from .artretopo_cage import X, Y, Z, Cage, az
from .artretopo_mesh import Mesh, write_ply
from .artretopo_sculpt import Sculpt, fit_sphere

HERE = Path(__file__).parent


def folder(name: str) -> Path:
    if "/" in name:
        return Path(name)
    from . import store
    return store.HOME / "retopo" / name


def need(d: Path, *files):
    for f in files:
        if not (d / f).exists():
            raise ValueError(f"{d.name}: {f} is missing; run the step that makes it first (guide(topic=\"retopo\"))")


# ---- start
def start(name: str, mesh: str, concept: str | None = None) -> dict:
    """copy the fused mesh (PLY; a GLB/OBJ is refused: give oxidegen's mesh_ply) and the concept into the folder;
    check the input"""
    d = folder(name); d.mkdir(parents=True, exist_ok=True)
    src = Path(mesh)
    if src.suffix.lower() != ".ply":
        raise ValueError("mesh: give the fused sculpt as PLY (oxidegen make_point_cloud's mesh_ply file)")
    if src.resolve() != (d / "high.ply").resolve():
        shutil.copy(src, d / "high.ply")
    if concept:
        c = Path(concept); shutil.copy(c, d / ("concept" + c.suffix.lower()))
    rep = check.check_input(Mesh.load(d / "high.ply"))
    (d / "input_check.json").write_text(json.dumps(rep, indent=1))
    return rep


# ---- props: eyes and accessories rebuilt as primitives, cut from the sculpt
def _shape_mask(P, sh) -> np.ndarray:
    """points inside a cut shape: sphere {c, R} or cylinder {axis, c, R, span: [lo, hi] along the axis}; optional
    "bounds": {"x"|"y"|"z": [lo, hi]} limits it to a box"""
    P = np.asarray(P, float); c = np.asarray(sh["c"], float)
    if sh["type"] == "sphere":
        m = np.linalg.norm(P - c, axis=1) < sh["R"]
    elif sh["type"] == "cylinder":
        ax = "xyz".index(sh["axis"]); other = [k for k in range(3) if k != ax]
        r = np.linalg.norm(P[:, other] - c[other], axis=1)
        lo, hi = sh.get("span", [-1e9, 1e9])
        m = (r < sh["R"]) & (P[:, ax] >= lo) & (P[:, ax] < hi)
    else:
        raise ValueError(f"cut shape type {sh['type']!r}: sphere or cylinder")
    for a, (lo, hi) in (sh.get("bounds") or {}).items():
        k = "xyz".index(a); m &= (P[:, k] >= lo) & (P[:, k] < hi)
    return m


def props(name: str, eyes=None, items=None, cut=None, margin: float = 0.006) -> dict:
    """eyes: [{c, R}] spheres (from fit_sphere); items: [{type: cylinder|sphere, axis, c, R, length, bone}] the props
    (bone "Head" or "Jaw": a prop held in the teeth rides the jaw); cut: extra cut shapes (default: every eye and item
    grown by margin). Writes props.json and high_body.ply (the biggest part left after the cut)."""
    d = folder(name); need(d, "high.ply")
    eyes = eyes or []; items = items or []
    shapes = list(cut) if cut else (
        [{"type": "sphere", "c": e["c"], "R": e["R"] + margin} for e in eyes]
        + [{"type": "cylinder", "axis": it["axis"], "c": it["c"], "R": it["R"] + margin,
            "span": [it["c"]["xyz".index(it["axis"])] - it["length"] / 2 - margin,
                     it["c"]["xyz".index(it["axis"])] + it["length"] / 2 + margin]} if it["type"] == "cylinder"
           else {"type": "sphere", "c": it["c"], "R": it["R"] + margin} for it in items])
    m = Mesh.load(d / "high.ply")
    centres = m.tri.mean(1)
    kill = np.zeros(len(centres), bool)
    for sh in shapes:
        kill |= _shape_mask(centres, sh)
    body = m.submesh(~kill)
    lab = body.components(); big = np.bincount(lab).argmax(); parts = len(np.unique(lab))
    body = body.submesh(lab == big)
    write_ply(d / "high_body.ply", body.V, body.F, body.C)
    J = {"eyes": eyes, "props": items, "cut": shapes}
    (d / "props.json").write_text(json.dumps(J, indent=1))
    return {"removed_triangles": int(kill.sum()), "parts_after_cut": parts, "kept_triangles": len(body.F),
            "eyes": len(eyes), "props": len(items)}


# ---- the cage
CAGE_SCOPE_DOC = "c (Cage), s (the body sculpt), full (the whole sculpt), props (props.json), az, X, Y, Z, np, math, fit_sphere"


def cage(name: str, code: str) -> dict:
    """run the artist's cage code (Python; in scope: CAGE_SCOPE_DOC) and save the cage; refuse a broken one"""
    d = folder(name); need(d, "high.ply")
    full = Sculpt(d / "high.ply")
    body = Sculpt(d / "high_body.ply") if (d / "high_body.ply").exists() else full
    c = Cage(full, body)
    P = json.loads((d / "props.json").read_text()) if (d / "props.json").exists() else {"eyes": [], "props": []}
    n = 1 + max([int(p.stem[6:]) for p in d.glob("cage_v*.py") if p.stem[6:].isdigit()] or [0])
    (d / f"cage_v{n}.py").write_text(code); (d / "cage.py").write_text(code)
    scope = {"c": c, "s": body, "full": full, "props": P, "az": az, "X": X, "Y": Y, "Z": Z, "np": np, "math": math,
             "fit_sphere": fit_sphere}
    exec(compile(code, str(d / f"cage_v{n}.py"), "exec"), scope)
    V, F = c.save(str(d / "cage.ply"))
    rep = check.check_cage(V, F)
    rep.update({"version": n, "pinned": len(c.pinned & {i for q in c.F for i in q}), "seam_edges": len(c.seams),
                "groups": {k: len(v) for k, v in c.groups.items()}})
    (d / "cage_check.json").write_text(json.dumps(rep, indent=1))
    return rep
