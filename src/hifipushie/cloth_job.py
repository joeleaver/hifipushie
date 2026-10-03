"""The cloth sim as a solver-neutral job: a folder another solver (a GPU box, `spikes/gpu_cloth/run_newton.py`) can run
and hand back, applied by cloth.build exactly like a Blender result.

A job folder holds `job.json` + `in.npz` and gets `out.npz` back:

in.npz (metres, Z up, the model's frame)
  X      (n, 3)  start positions (placed round the body isometrically to the pattern; mode "refine": the fine mesh's
                 placement, its rest shape in Blender)
  S      (n, 3)  refine only: where the cloth starts (the coarse drape carried onto the fine mesh)
  uv     (n, 2)  the flat pattern (metres): the rest shape. Pieces are disjoint islands of it
  F      (m, 3)  triangles (one mesh of all pieces)
  piece  (n,)    piece index per vertex (names in job["pieces"])
  sew    (k, 2)  vertex pairs sewn shut (seams); stitch (j, 2) pairs sewn the same way (buttons to holes)
  stiff  (n,)    0..1 interfacing per vertex (stiffer bending, shear and stretch)
  bodyV, bodyT   the collider (the body; for a hung garment only while it is dressed)
  bodyV0, bodyPoses   placement "smooth": the body the garment starts on (straight arms) and the poses (k, nV, 3)
                 it moves through, evenly over the "pose" stage, ending at bodyV

job.json
  format, mode ("sim" | "refine"), name, pieces
  fabric           Blender's numbers (blender_cloth) + `physical`: SI numbers any solver can use
                   (density kg/m2, stretch/shear N/m, bend N m, friction, thickness m, interfacing multipliers)
  stages           the schedule, spelled out (`stages()`): each {"name", "frames" (at fps), "gravity" 0/1,
                   "sew" (true | "fixed-free": only pairs between free vertices), "sew_force", "self_collision",
                   "fixed" (vertices held where they are), "body" (collide with it), "hang" (move the pins under the
                   hook and hold them there, rack colliders), "start" (refine: ease from S over `ease` frames)}
  pins, hook, rack, pin_spread   hung garments (rack = [[a, b, radius], ...] capsule colliders)
  fps              24
  out              where out.npz goes (a runner may write it beside job.json instead)

out.npz: V (n, 3) the settled positions (the result); optional per-stage snapshots (V1, worn); `log` lines; `timing`.

Backends (garment key "backend", or $HIFIPUSHIE_CLOTH_BACKEND; default "blender"):
  "blender"  blender_cloth.py here (the default; it reads the same folder).
  "file"     the job folder is written and out.npz is waited for (a person or an agent carries it to a GPU box and
             back). The folder is <HOME>/_cache/cloth/job_<key>/<mode>; `HIFIPUSHIE_CLOTH_WAIT` s (default 2 h).
  "remote"   `$HIFIPUSHIE_CLOTH_REMOTE` is run with the job folder as its last argument (e.g. a script that rsyncs it to
             a pod, runs the runner there and rsyncs out.npz back); it must leave out.npz in the folder.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from pathlib import Path

import numpy as np

FORMAT = 1
FPS = 24

# What the Blender presets stand for, in SI units a physical solver takes. Areal density from fabric weights (shirting
# ~120 g/m2, a coating ~450); stretch = the membrane's tensile stiffness at small strain (woven cloth: 1.5-3e4 N/m
# along the threads; knits far less; at 4000 Newton's VBD shirt stretched 10-29% under its own seams); shear ~ a tenth
# of the woven stretch; bending rigidity from KES-style numbers (shirting ~0.05 gf cm2/cm = 5e-6 N m, a coating ~10x).
PHYSICAL = {
    "shirting": {"density": 0.12, "stretch": 20000.0, "shear": 2000.0, "bend": 5e-6, "friction": 0.4},
    "jersey": {"density": 0.18, "stretch": 1500.0, "shear": 500.0, "bend": 2e-6, "friction": 0.5},
    "wool_coating": {"density": 0.45, "stretch": 15000.0, "shear": 2500.0, "bend": 6e-5, "friction": 0.5},
    "denim": {"density": 0.40, "stretch": 30000.0, "shear": 4000.0, "bend": 3e-5, "friction": 0.5},
    "linen": {"density": 0.17, "stretch": 25000.0, "shear": 2000.0, "bend": 1e-5, "friction": 0.4},
}


def physical(fab: dict) -> dict:
    """SI fabric numbers for a fabric (cloth.fabric's dict): the preset's PHYSICAL, overridden by fab["physical"]."""
    base = dict(PHYSICAL.get(fab.get("name"), PHYSICAL["shirting"]))
    base.update(fab.get("physical") or {})
    base.setdefault("thickness", float(fab.get("thickness", 0.0005)))
    # interfacing: fused interfacing makes a piece bend ~10x harder and stops it stretching (the Blender preset's
    # multipliers are for its own springs)
    base.setdefault("interfacing_bend", 40.0)
    base.setdefault("interfacing_stretch", 6.0)
    return base


def stages(cfg: dict) -> list:
    """The schedule blender_cloth.sim / refine runs for this job, spelled out for other solvers."""
    if cfg.get("mode") == "refine":
        pins = cfg.get("pins") or []
        return [{"name": "refine", "frames": int(cfg.get("refine_frames", 40)), "gravity": 1, "sew": True,
                 "sew_force": 0.0 if pins else None, "self_collision": bool(cfg.get("self_collision", True)),
                 "fixed": "pins" if pins else [], "body": bool(cfg.get("body", True)), "rack": bool(pins),
                 "start": True, "ease": int(cfg.get("refine_ease", 15))}]
    sc = bool(cfg.get("self_collision", True))
    sew_self = bool(cfg.get("self_collision_sew", True)) and sc
    sew_force = float(cfg.get("sew_force", 6.0))
    st = cfg.get("state", "worn")
    hang = isinstance(st, dict) and "hang" in st
    out = []
    asm = cfg.get("assemble")
    f1 = int(cfg.get("sew_frames", 90))
    if asm:
        out.append({"name": "assemble", "frames": f1, "gravity": 0, "sew": "fixed-free", "sew_force": sew_force,
                    "self_collision": sew_self, "fixed": "assemble.fixed", "body": True,
                    "note": "the bodice sewn alone; the fixed vertices go back to their start after it"})
    out.append({"name": "sew", "frames": f1, "gravity": 0, "sew": True, "sew_force": sew_force,
                "self_collision": sew_self, "fixed": "assemble.hold" if asm else [], "body": True})
    if cfg.get("placement") == "smooth":  # dressed on straight arms: the body bends its elbows back (bodyV0 ->
        # bodyPoses, the last = bodyV) before gravity, the cloth carried by contact
        out.append({"name": "pose", "frames": int(cfg.get("pose_frames", 36)), "gravity": 0, "sew": True,
                    "sew_force": sew_force, "self_collision": sew_self, "fixed": [], "body": True, "pose": True})
    out.append({"name": "settle", "frames": int(cfg.get("worn_frames", 40)) if hang else int(cfg.get("frames", 90)),
                "gravity": 1, "sew": True, "sew_force": None, "self_collision": sc, "fixed": [], "body": True})
    if hang:
        out.append({"name": "hang", "frames": int(cfg.get("hang_frames", 120)), "gravity": 1, "sew": True,
                    "sew_force": float(cfg.get("hang_sew_force", sew_force)), "self_collision": sc, "fixed": [],
                    "body": False, "hang": True, "rack": True})
    if sc:
        out.append({"name": "self_settle", "frames": int(cfg.get("settle_frames", 24)), "gravity": 1, "sew": True,
                    "sew_force": 0.0 if hang else None, "self_collision": True, "fixed": "pins" if hang else [],
                    "body": not hang, "rack": hang})
    return out


def write(job_dir: Path, cfg: dict, arrays: dict, names: list | None = None) -> Path:
    """job.json + in.npz in job_dir (the Blender runner reads the same folder: its own keys are kept as they were)."""
    job_dir.mkdir(parents=True, exist_ok=True)
    np.savez(job_dir / "in.npz", **arrays)
    cfg = dict(cfg, out=str(job_dir / "out.npz"), format=FORMAT, fps=FPS)
    cfg.setdefault("mode", "sim")
    if names is not None:
        cfg["pieces"] = list(names)
    if "fabric" in cfg:
        cfg["fabric"] = dict(cfg["fabric"], physical=physical(cfg["fabric"]))
    cfg["stages"] = stages(cfg)
    (job_dir / "job.json").write_text(json.dumps(cfg, indent=1, default=_jsonable))
    (job_dir / "out.npz").unlink(missing_ok=True)
    return job_dir


def _jsonable(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def backend_of(g: dict) -> str:
    b = g.get("backend") or os.environ.get("HIFIPUSHIE_CLOTH_BACKEND") or "blender"
    if b not in ("blender", "file", "remote"):
        raise ValueError(f'cloth backend is "blender", "file" or "remote", got {b!r}')
    return b


def run_external(job_dir: Path, backend: str, progress, timeout: float = 7200) -> tuple:
    """Hand the written job to another solver and read its out.npz. Returns (out.npz contents, log lines)."""
    out = job_dir / "out.npz"
    t = time.time()
    if backend == "remote":
        cmd = os.environ.get("HIFIPUSHIE_CLOTH_REMOTE")
        if not cmd:
            raise RuntimeError('cloth backend "remote" needs $HIFIPUSHIE_CLOTH_REMOTE: a command run with the job folder '
                               "as its last argument that leaves out.npz in it (spikes/gpu_cloth/remote.sh)")
        progress(f"remote: {cmd} {job_dir}")
        p = subprocess.Popen(shlex.split(cmd) + [str(job_dir)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True)
        lines = []
        for line in p.stdout:
            lines.append(line.rstrip())
            if line.startswith("cloth:"):
                progress(line[6:].strip())
            if time.time() - t > timeout:
                p.kill()
                raise RuntimeError(f"remote cloth job over {timeout:.0f} s, stopped")
        p.wait()
        if p.returncode != 0 or not out.exists():
            raise RuntimeError("remote cloth job failed:\n" + "\n".join(lines[-40:]))
    else:  # "file": somebody else runs it
        wait = float(os.environ.get("HIFIPUSHIE_CLOTH_WAIT", timeout))
        progress(f"job written to {job_dir}: waiting up to {wait:.0f} s for out.npz")
        while not out.exists():
            if time.time() - t > wait:
                raise RuntimeError(f"cloth job {job_dir}: no out.npz after {wait:.0f} s")
            time.sleep(2.0)
        time.sleep(1.0)  # let the writer finish
    d = dict(np.load(out, allow_pickle=False))
    lines = [str(x) for x in d.pop("log", np.array([]))] if "log" in d else []
    d.pop("timing", None)
    return d, [ln if ln.startswith("cloth:") else "cloth: " + ln for ln in lines]
