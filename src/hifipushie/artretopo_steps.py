"""Artist retopo: the Blender steps, each its own tool, each a headless Blender job under resources.heavy:
press -> bake -> fill (Python) -> assemble -> compare; rig -> rom; lod. The folder layout is artretopo_run's
docstring; the contact sheets are artretopo_sheets."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from . import artretopo_fill as fill_mod
from . import artretopo_sheets as sheets
from .artretopo_mesh import Mesh
from .artretopo_run import folder, need

HERE = Path(__file__).parent
GB = {"press": 3.0, "bake": 6.0, "assemble": 3.0, "compare": 3.0, "rig": 4.0, "posecheck": 4.0, "look": 2.0}


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


def _body_high(d: Path) -> str:
    return "high_body.ply" if (d / "high_body.ply").exists() else "high.ply"


# ---- press
def press(name: str, levels: int = 1, relax: int = 6, after: int = 1, part: str | None = None) -> dict:
    """the body (part None), or a separate part's own cage (pressed onto the whole sculpt, no LOD1)"""
    d = folder(name)
    cn, on = (f"part_{part}_cage", f"part_{part}_low") if part else ("cage", "low")
    need(d, f"{cn}.ply")
    job = {"dir": str(d), "cage": cn, "out": on, "high": "high.ply" if part else _body_high(d), "levels": levels,
           "relax": relax, "after": after, **framing(d)}
    job["scale"] = round(job["scale"] / 1.15 * 1.1, 4)
    if part:
        from .artretopo_mesh import Mesh as _M
        lo, hi = _M.load(d / f"{cn}.ply").bounds(); job["centre"] = ((lo + hi) / 2).round(4).tolist()
        job["scale"] = round(float(max(hi - lo)) * 1.6, 4)
    blender("press", job, GB["press"])
    out = json.loads((d / ("press.json" if not part else f"{on}_press.json")).read_text())
    vs = ("front", "side", "back", "3q"); pre = "wire" if not part else f"wire_{on}"
    sheet = d / ("wire_sheet.jpg" if not part else f"wire_{on}_sheet.jpg")
    sheets.grid(sheet, [d / f"{pre}_{t}_{v}.png" for t in ("cage", "low") for v in vs],
                cols=4, tile=420, labels=[f"{t} {v}" for t in ("cage", "low") for v in vs])
    out["sheet"] = str(sheet)
    return out


# ---- bake, fill, assemble, compare
def bake(name: str, res: int = 2048, extrusion: float = 0.012, reach: float = 0.03, thin_extrusion: float = 0.004,
         thin_reach: float = 0.015) -> dict:
    d = folder(name); need(d, "low.ply", "low_seams.json")
    blender("bake", {"dir": str(d), "high": _body_high(d), "res": res, "extrusion": extrusion, "reach": reach,
                     "thin_extrusion": thin_extrusion, "thin_reach": thin_reach}, GB["bake"], timeout=5400)
    out = json.loads((d / "bake.json").read_text())
    tags = ["low"] + (["lod1"] if (d / "lod1_color.png").exists() else []) + out.get("props", [])
    sheets.grid(d / "bake_sheet.jpg", [d / ("color.png" if t == "low" else f"{t}_color.png") for t in tags[:2]]
                + [d / ("normal.png" if t == "low" else f"{t}_normal.png") for t in tags[:2]], cols=2, tile=512,
                labels=[f"{t} colour" for t in tags[:2]] + [f"{t} normal" for t in tags[:2]])
    return out


def fill(name: str) -> list[dict]:
    d = folder(name); need(d, "color.png", "low_cover.png")
    return fill_mod.repair_all(str(d))


def assemble(name: str) -> dict:
    d = folder(name); need(d, "low_uv.glb")
    blender("assemble", {"dir": str(d)}, GB["assemble"])
    return {"final": str(d / "final.glb")}


def compare(name: str, result: str = "final.glb", views: list | None = None, head=None) -> Path:
    """the sculpt and the result rendered alike: whole figure 3/4, back, head (default) or your own views
    [{name, view: [dx, dy, dz], target: [x, y, z], scale}]"""
    d = folder(name); need(d, result)
    fr = framing(d)
    if head:
        fr["head"] = list(head)
    std = views is None
    views = views or [{"name": "body", "view": [-0.8, -1, 0.4], "target": fr["centre"], "scale": fr["scale"]},
                      {"name": "head", "view": [-0.6, -1, 0.25], "target": fr["head"], "scale": fr["head_scale"]},
                      {"name": "back", "view": [0.7, 1, 0.3], "target": fr["centre"], "scale": round(fr["scale"] * 0.87, 4)}]
    blender("compare", {"dir": str(d), "result": result, "views": views}, GB["compare"])
    if std:
        sheets.final_cmp(d); return d / "final_cmp.jpg"
    out = d / "compare_sheet.jpg"
    sheets.grid(out, [d / f"fin_{v['name']}_{t}.png" for v in views for t in ("high", "final")], 2, 500,
                [f"{v['name']} {t}" for v in views for t in ("sculpt", "result")])
    return out


# ---- rig, range of motion, LOD1
JOINTS = ("hips", "spine", "spine1", "spine2", "neck", "head", "head_top", "clavicle", "shoulder", "elbow", "wrist",
          "hand_end", "hip", "knee", "ankle", "toe", "toe_end")


def rig(name: str, joints: dict, helpers=("Arm", "ForeArm", "Leg"), helper_smooth: int = 6, jaw_smooth: int = 4) -> dict:
    d = folder(name); need(d, "low.ply")
    if not ((d / "final.glb").exists() or (d / "low_uv.glb").exists()):
        raise ValueError("rig needs the baked mesh: run retopo_bake (and retopo_assemble) first")
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
    blender("rig", {"dir": str(d), "joints": joints, "helpers": list(helpers), "helper_smooth": helper_smooth,
                    "jaw_smooth": jaw_smooth}, GB["rig"], timeout=3600)
    return json.loads((d / "rig.json").read_text())["info"]


def rom(name: str, poses: list | None = None, clavicle: float = 0.3, close: dict | None = None,
        close_ups: bool = True) -> dict:
    """poses: standard names and / or {name: [[bone, [axis], degrees] | [bone, "aim", [direction]], ...]}"""
    d = folder(name); need(d, "rigged.blend", "rig.json")
    job = {"dir": str(d), "clavicle": clavicle, "close_ups": close_ups}
    if poses:
        job["poses"] = poses
    if close:
        job["close"] = close
    for f in list(d.glob("close_*.png")) + list(d.glob("close_*.jpg")):
        f.unlink()
    blender("posecheck", job, GB["posecheck"], timeout=5400)
    out = json.loads((d / "rom.json").read_text())
    sheets.rom_sheet(d, list(out["poses"]))
    sheets.close_sheet(d)
    lines = [f"{k} {v}" for k, v in out["poses"].items()]
    if out.get("lod1"):
        lines.append(f"LOD1 faces {out['lod1'].get('faces')} groups {out['lod1'].get('groups')}")
    (d / "rom_final.txt").write_text("\n".join(lines) + "\n")
    return out


def lod(name: str) -> dict:
    d = folder(name); need(d, "rigged.blend", "rig.json")
    blender("posecheck", {"dir": str(d), "mode": "lod"}, GB["posecheck"])
    return json.loads((d / "lod1.json").read_text())


def check_low(name: str) -> dict:
    """the pressed mesh's numbers again: folds (and where), volume, faces"""
    d = folder(name); need(d, "low.ply", "press.json")
    m = Mesh.load(d / "low.ply")
    out = json.loads((d / "press.json").read_text())
    out.update({"low_volume": round(m.signed_volume(), 5), "low_open_edges": m.edges_open()})
    return out
