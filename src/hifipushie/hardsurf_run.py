"""Hard surface from the point cloud: an object's folder and the steps run on it (tools_hardsurf.py calls these).

Folder (store.HOME/hardsurf/<name>, or a path): input.ply (the fused sculpt as given), views.npz (the point cloud's
renders, optional: without them colour comes from the sculpt's vertex colours only), concept.* (optional),
high.ply + frame.json (framed), parts.json (the parts, written by the fitters and by you), parts.glb + build.json,
bake/ (atlas + baked.glb), check.json, rig.glb + rig.json, disagreements.json.

Flow: start -> frame -> look / measure / fit (each fit adds or replaces a part in parts.json) -> build -> check
(nothing floats; overlaps read) -> bake -> rig (optional) -> look beside the concept. Log every place the sculpt
and the concept disagree, with the call you made (`disagree`): the sculpt is evidence, not the spec."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

from .artretopo_mesh import Mesh, write_ply

HERE = Path(__file__).parent
GB = {"build": 3.0, "bake": 6.0, "check": 3.0, "rig": 4.0}


def folder(name: str) -> Path:
    if "/" in name:
        return Path(name)
    from . import store
    return store.HOME / "hardsurf" / name


def blender(script: str, job: dict, gb: float, timeout: float = 3600) -> str:
    """run blender_hardsurf_<script>.py on a job under resources.heavy; raise with the log's tail on failure"""
    import tempfile
    from . import render, resources
    with tempfile.TemporaryDirectory(prefix="hifipushie-hardsurf-") as tmp:
        p = Path(tmp) / "job.json"; p.write_text(json.dumps(job))
        with resources.heavy(f"hardsurf {script}", gb=gb):
            r = resources.run([render.BLENDER, "-b", *render._threads(), "--factory-startup", "--python-exit-code", "1",
                               "--python", str(HERE / f"blender_hardsurf_{script}.py"), "--", str(p)],
                              capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError(f"blender hardsurf {script} failed:\n{r.stdout[-3000:]}\n{r.stderr[-2000:]}")
    return r.stdout


def start(name: str, mesh: str, views: str | None = None, concept: str | None = None) -> dict:
    d = folder(name); d.mkdir(parents=True, exist_ok=True)
    m = Mesh.load(mesh)
    rep = {"vertices": len(m.V), "faces": len(m.F), "open_edges": m.edges_open(), "signed_volume": round(m.signed_volume(), 5)}
    if rep["open_edges"]:
        raise ValueError(f"the sculpt has {rep['open_edges']} open edges: the solid tests need a closed mesh (re-fuse it)")
    if rep["signed_volume"] < 0:
        raise ValueError("the sculpt is wound inside out (negative volume): flip its faces first")
    write_ply(d / "input.ply", m.V, m.F, m.C)
    if views: shutil.copy(views, d / "views.npz")
    if concept: shutil.copy(concept, d / f"concept{Path(concept).suffix}")
    return rep


def frame(name: str, **kw) -> dict:
    """hardsurf_frame.square_up on input.ply -> high.ply + frame.json (with framed_to_views when views.npz is there
    and `fuse_convention` is True: the input is oxidegen's fused mesh)"""
    from . import hardsurf_frame as F
    d = folder(name); fuse = kw.pop("fuse_convention", True)
    m, info = F.square_up(d / "input.ply", **kw)
    write_ply(d / "high.ply", m.V, m.F, m.C)
    if (d / "views.npz").exists() and fuse:
        info["framed_to_views"] = F.views_transform(info, F.fuse_views_transform(d / "views.npz")).tolist()
    (d / "frame.json").write_text(json.dumps(info, indent=1))
    return {k: v for k, v in info.items() if k not in ("framed_to_input", "input_to_framed", "framed_to_views")}


_SOLIDS: dict = {}


def solid(name: str, step: float = 0.003):
    from .hardsurf_solid import Solid
    d = folder(name); key = (str(d), step, (d / "high.ply").stat().st_mtime)
    if key not in _SOLIDS:
        _SOLIDS.clear(); _SOLIDS[key] = Solid(d / "high.ply", step)
    return _SOLIDS[key]


def parts(name: str) -> list[dict]:
    p = folder(name) / "parts.json"
    return json.loads(p.read_text())["parts"] if p.exists() else []


def put_parts(name: str, new: list[dict], replace: bool = True) -> dict:
    """add parts (a part with an existing name replaces it unless replace=False); validated first"""
    from .hardsurf_parts import validate
    for p in new: validate(p)
    cur = {p["name"]: p for p in parts(name)}
    for p in new:
        if p["name"] in cur and not replace: raise ValueError(f"part {p['name']} exists")
        cur[p["name"]] = p
    (folder(name) / "parts.json").write_text(json.dumps({"parts": list(cur.values())}))
    return {"parts": len(cur), "added": [p["name"] for p in new]}


def drop_parts(name: str, names: list[str]) -> dict:
    cur = [p for p in parts(name) if p["name"] not in names]
    (folder(name) / "parts.json").write_text(json.dumps({"parts": cur})); return {"parts": len(cur)}


def build(name: str) -> dict:
    d = folder(name)
    blender("build", {"parts": str(d / "parts.json"), "out": str(d / "parts.glb"), "report": str(d / "build.json"),
                      "sculpt": str(d / "high.ply")}, GB["build"])
    rep = json.loads((d / "build.json").read_text())
    far = {k: v for k, v in rep.get("distance_to_sculpt", {}).items() if v["p95_mm"] > 15}
    rep["far_from_sculpt"] = far       # parts mostly > 15 mm off: invented on purpose (fine) or misplaced (look)
    return rep


def check(name: str, glb: str = "parts.glb", touch: float = 0.004) -> dict:
    d = folder(name)
    blender("check", {"parts": str(d / glb), "report": str(d / "check.json"), "touch": touch}, GB["check"])
    return json.loads((d / "check.json").read_text())


def bake(name: str, res: int = 2048, depth_tol: float = 0.012) -> dict:
    d = folder(name); fr = json.loads((d / "frame.json").read_text())
    if not (d / "views.npz").exists() or "framed_to_views" not in fr:
        raise ValueError("bake projects the point cloud's renders: start with views= (oxidegen's views.npz) and frame again")
    out = blender("bake", {"parts": str(d / "parts.glb"), "sculpt": str(d / "high.ply"), "views": str(d / "views.npz"),
                           "framed_to_views": fr["framed_to_views"], "depth_tol": depth_tol, "res": res,
                           "out": str(d / "bake")}, GB["bake"])
    line = next((l for l in out.splitlines() if l.startswith("PROJECTED")), "")
    return {"baked": str(d / "bake" / "baked.glb"), "projection": line}


def rig(name: str, joints: list[dict], lod_ratio: float = 0.35, renders: bool = True) -> dict:
    d = folder(name)
    src = d / "bake" / "baked.glb" if (d / "bake" / "baked.glb").exists() else d / "parts.glb"
    blender("rig", {"parts": str(src), "out": str(d / "rig.glb"), "report": str(d / "rig.json"), "joints": joints,
                    "lod_ratio": lod_ratio, "renders": str(d / "rig_renders") if renders else None}, GB["rig"])
    return json.loads((d / "rig.json").read_text())


def disagree(name: str, where: str, sculpt_says: str, concept_says: str, call: str) -> dict:
    """log a place the sculpt and the concept disagree, and the call made (kept with the object, read at review)"""
    p = folder(name) / "disagreements.json"
    log = json.loads(p.read_text()) if p.exists() else []
    log.append({"where": where, "sculpt": sculpt_says, "concept": concept_says, "call": call})
    p.write_text(json.dumps(log, indent=1)); return {"logged": len(log)}
