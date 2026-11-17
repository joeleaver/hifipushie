"""Artist retopo: the Blender steps (press, bake + repair + assemble, rig + ROM), each a headless Blender job under
resources.heavy, plus their contact sheets. The folder layout is artretopo_run's docstring."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from . import artretopo_fill as fill
from . import artretopo_sheets as sheets
from .artretopo_mesh import Mesh
from .artretopo_run import folder, need

HERE = Path(__file__).parent
GB = {"press": 3.0, "bake": 6.0, "assemble": 3.0, "rig": 4.0, "look": 2.0}


def blender(script: str, job: dict, gb: float, timeout: float = 3600, gpu: bool = False) -> str:
    """run blender_artretopo_<script>.py on a job; raise with the tail of its log on failure"""
    from . import render, resources
    with tempfile.TemporaryDirectory(prefix="hifipushie-artretopo-") as tmp:
        p = Path(tmp) / "job.json"; p.write_text(json.dumps(job))
        with resources.heavy(f"artretopo {script}", gb=gb, gpu=gpu):
            r = resources.run([render.BLENDER, "-b", *render._threads(), "--factory-startup", "--python-exit-code", "1",
                               "--python", str(HERE / f"blender_artretopo_{script}.py"), "--", str(p)],
                              capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError(f"blender {script} failed:\n{r.stdout[-3000:]}\n{r.stderr[-2000:]}")
    return r.stdout


def framing(d: Path) -> dict:
    """whole-figure centre / scale and a head close-up from the sculpt's bounds (the head: the top third's centroid)"""
    m = Mesh.load(d / "high.ply"); lo, hi = m.bounds(); H = float(hi[2] - lo[2])
    top = m.V[m.V[:, 2] > hi[2] - 0.35 * H]
    head = [0.0, float(np.percentile(top[:, 1], 30)), float(top[:, 2].mean())]
    return {"centre": ((lo + hi) / 2).round(4).tolist(), "scale": round(1.15 * H, 4), "head": [round(x, 4) for x in head],
            "head_scale": round(0.42 * H, 4)}


def press(name: str, levels: int = 1, relax: int = 6, after: int = 1) -> dict:
    d = folder(name); need(d, "cage.ply")
    high = "high_body.ply" if (d / "high_body.ply").exists() else "high.ply"
    job = {"dir": str(d), "high": high, "levels": levels, "relax": relax, "after": after, **framing(d)}
    job["scale"] = round(job["scale"] / 1.15 * 1.1, 4)
    blender("press", job, GB["press"])
    out = json.loads((d / "press.json").read_text())
    sheets.grid(d / "wire_sheet.jpg", [d / f"wire_{t}_{v}.png" for t in ("cage", "low") for v in ("front", "side", "back", "3q")],
                cols=4, tile=420, labels=[f"{t} {v}" for t in ("cage", "low") for v in ("front", "side", "back", "3q")])
    return out


def bake(name: str, res: int = 2048, extrusion: float = 0.012, reach: float = 0.03, head=None) -> dict:
    d = folder(name); need(d, "low.ply", "low_seams.json")
    high = "high_body.ply" if (d / "high_body.ply").exists() else "high.ply"
    blender("bake", {"dir": str(d), "high": high, "res": res, "extrusion": extrusion, "reach": reach}, GB["bake"], timeout=5400)
    out = json.loads((d / "bake.json").read_text())
    out["repair"] = fill.repair_all(str(d))
    fr = framing(d)
    if head:
        fr["head"] = list(head)
    blender("assemble", {"dir": str(d), **fr}, GB["assemble"])
    sheets.final_cmp(d)
    return out


JOINTS = ("hips", "spine", "spine1", "spine2", "neck", "head", "head_top", "clavicle", "shoulder", "elbow", "wrist",
          "hand_end", "hip", "knee", "ankle", "toe", "toe_end")


def rig(name: str, joints: dict, helpers=("Arm", "ForeArm", "Leg"), clavicle: float = 0.3, poses=None) -> dict:
    d = folder(name); need(d, "low.ply")
    if not ((d / "final.glb").exists() or (d / "low_uv.glb").exists()):
        raise ValueError("rig needs the baked mesh: run retopo_bake first")
    miss = [j for j in JOINTS if j not in joints]
    if miss:
        raise ValueError(f"joints missing: {miss} (paired joints are given for the LEFT side, +x; 'jaw' + 'jaw_tip' "
                         "add a jaw bone)")
    if ("jaw" in joints) != ("jaw_tip" in joints):
        raise ValueError("give both 'jaw' and 'jaw_tip' (or neither)")
    for j in ("clavicle", "shoulder", "elbow", "wrist", "hand_end", "hip", "knee", "ankle", "toe", "toe_end"):
        if joints[j][0] <= 0:
            raise ValueError(f"joint {j} is at x = {joints[j][0]}: paired joints are given for the LEFT side (+x)")
    (d / "joints.json").write_text(json.dumps(joints, indent=1))
    job = {"dir": str(d), "joints": joints, "helpers": list(helpers), "clavicle": clavicle, "helper_smooth": 6,
           "jaw_smooth": 4}
    if poses:
        job["poses"] = list(poses)
    blender("rig", job, GB["rig"], timeout=5400)
    rom = json.loads((d / "rom.json").read_text())
    sheets.rom_sheet(d, list(rom["poses"]))
    sheets.close_sheet(d)
    lines = [f"{k} {v}" for k, v in rom["poses"].items()]
    if rom.get("lod1"):
        lines.append(f"LOD1 faces {rom['lod1']['faces']} groups {rom['lod1']['groups']}")
    (d / "rom_final.txt").write_text("\n".join(lines) + "\n")
    return rom
