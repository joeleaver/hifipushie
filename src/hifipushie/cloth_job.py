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
  bodyLower      hung on a hanger: (k, nV, 3) poses from bodyV to the arms down at the sides, evenly over the stage
                 whose "pose" names it ("lower"); a stage's "pose" true means bodyPoses

job.json
  format, mode ("sim" | "refine"), name, pieces
  fabric           Blender's numbers (blender_cloth) + `physical`: SI numbers any solver can use
                   (density kg/m2, stretch/shear N/m, bend N m, friction, thickness m, interfacing multipliers)
  stages           the schedule, spelled out (`stages()`): each {"name", "frames" (at fps), "gravity" 0/1,
                   "sew" (true | "fixed-free": only pairs between free vertices), "sew_force", "self_collision",
                   "fixed" (vertices held where they are), "body" (collide with it), "hang" (move the pins under the
                   hook and hold them there, rack colliders), "start" (refine: ease from S over `ease` frames)}
  hanger           hung on a hanger (hanger.to_job: segments, arms, rod, rail); its colliders are in.npz hangerV/F
                   (one closed mesh: arms, hook, bar) and railV/F (rail + posts). They sit inside the body while the
                   garment is dressed and collide from the "hanger" stages on (the body gone, nothing pinned)
  pins, hook, rack, pin_spread   the old pinned hang (rack = [[a, b, radius], ...] capsule colliders)
  fps              24
  out              where out.npz goes (a runner may write it beside job.json instead)

out.npz: V (n, 3) the settled positions (the result); Vprev the positions cloth.PREV_APART (6) frames before the end
(the "still moving" measure); optional per-stage snapshots (V1, worn); `log` lines; `timing`.

Backends (garment key "backend", or $HIFIPUSHIE_CLOTH_BACKEND; default "blender"):
  "blender"  blender_cloth.py here (the default; it reads the same folder).
  "zozo"     ZOZO's contact solver (cloth_zozo.py, run by the release's own Python): the cloth solver being developed.
             The release is $HIFIPUSHIE_ZOZO (or $PPF_ROOT), else the asset pack "zozo" (`uv run hifipushie-assets
             fetch zozo`). Local runs take the machine's heavy slot and a memory cap ($HIFIPUSHIE_ZOZO_MEM, default 6G)
             on $HIFIPUSHIE_ZOZO_DEVICE (cuda | rocm | cpu; default cuda with nvidia-smi, rocm with /dev/kfd, else
             cpu). With $HIFIPUSHIE_ZOZO_REMOTE set, that command runs with the job folder as its last argument instead
             and must leave out.npz there (spikes/gpu_cloth/remote.sh with GPU_RUNNER=zozo copies the folder and
             cloth_zozo.py to a GPU box). The garment's `zozo` dict (solver options) goes into job.json. Results are
             keyed on cloth_zozo.py, not blender_cloth.py, and not on where they ran: a pod's result is found locally.
             Defaults for it: placement "smooth", one sim at `resolution` (no coarse -> fine refine).
  "file"     the job folder is written and out.npz is waited for (a person or an agent carries it to a GPU box and
             back). The folder is <HOME>/_cache/cloth/job_<key>/<mode>; `HIFIPUSHIE_CLOTH_WAIT` s (default 2 h).
  "remote"   `$HIFIPUSHIE_CLOTH_REMOTE` is run with the job folder as its last argument (e.g. a script that rsyncs it to
             a pod, runs the runner there and rsyncs out.npz back); it must leave out.npz in the folder.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

FORMAT = 1
FPS = 24

# What the Blender presets stand for, in SI units a physical solver takes. Areal density from fabric weights (shirting
# ~120 g/m2, a coating ~450); stretch = the membrane's tensile stiffness at small strain (woven cloth: 1.5-3e4 N/m
# along the threads; knits far less; at 4000 Newton's VBD shirt stretched 10-29% under its own seams); shear ~ a tenth
# of the woven stretch; bending rigidity B from Kawabata (KES-F / FAST) numbers, 1 gf cm2/cm = 9.81e-5 N m: shirting
# cotton 0.01-0.03 gf cm2/cm (0.02 = 2e-6 N m), jersey ~0.01, linen ~0.05, heavy wool coating 0.1-0.3 (0.2 = 2e-5 N m,
# 10x the shirt), denim ~0.3. (Before 2026-10-03: shirting 5e-6, wool 6e-5; the ZOZO runner ignored them.)
PHYSICAL = {
    "shirting": {"density": 0.12, "stretch": 20000.0, "shear": 2000.0, "bend": 2e-6, "friction": 0.4},
    "jersey": {"density": 0.18, "stretch": 1500.0, "shear": 500.0, "bend": 1e-6, "friction": 0.5},
    "wool_coating": {"density": 0.45, "stretch": 15000.0, "shear": 2500.0, "bend": 2e-5, "friction": 0.5},
    "denim": {"density": 0.40, "stretch": 30000.0, "shear": 4000.0, "bend": 3e-5, "friction": 0.5},
    "linen": {"density": 0.17, "stretch": 25000.0, "shear": 2000.0, "bend": 5e-6, "friction": 0.4},
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
                 "hanger": bool(cfg.get("hanger")), "start": True, "ease": int(cfg.get("refine_ease", 15))}]
    if cfg.get("mode") == "fine_settle":  # method "settle"'s second step (cloth.build): the made pieces prescribed,
        # their flaps closing from open over "press" (in.npz carryPoses), then the drape settling round them
        base = {"gravity": 1, "sew": True, "sew_force": None, "self_collision": True, "fixed": [], "body": True}
        pr = int(cfg.get("press_frames", 0))
        return ([dict(base, name="press", frames=pr, pose=True)] if pr > 0 else []) + [
            dict(base, name="settle", frames=int(cfg.get("frames", 36)))]
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
    hanger = bool(cfg.get("hanger"))
    if hang and hanger and cfg.get("lower"):  # the body's arms come down to its sides with the garment on
        # (in.npz bodyLower: the poses, evenly over the stage), so the sleeves hang beside it on the hanger
        out.append({"name": "lower", "frames": int(cfg.get("lower_frames", 48)), "gravity": 1, "sew": True,
                    "sew_force": None, "self_collision": sc, "fixed": [], "body": True, "pose": "bodyLower"})
    if hang and hanger:  # on a hanger: the body goes, the hanger (inside the garment since the start) collides, gravity
        # settles the garment onto it; nothing pinned
        out.append({"name": "hang", "frames": int(cfg.get("hang_frames", 240)), "gravity": 1, "sew": True,
                    "sew_force": None, "self_collision": sc, "fixed": [], "body": False, "hanger": True})
    elif hang:  # the old pinned hang: pins moved under `hook`, rack capsules
        out.append({"name": "hang", "frames": int(cfg.get("hang_frames", 120)), "gravity": 1, "sew": True,
                    "sew_force": float(cfg.get("hang_sew_force", sew_force)), "self_collision": sc, "fixed": [],
                    "body": False, "hang": True, "rack": True})
    if sc and not (hang and hanger):  # (on a hanger the hang stage self-collides already)
        out.append({"name": "self_settle", "frames": int(cfg.get("settle_frames", 24)), "gravity": 1, "sew": True,
                    "sew_force": 0.0 if hang and not hanger else None, "self_collision": True,
                    "fixed": "pins" if hang and not hanger else [], "body": not hang, "rack": hang and not hanger,
                    "hanger": hang and hanger})
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



BACKENDS = ("blender", "zozo", "file", "remote")
ZOZO_RUNNER = Path(__file__).with_name("cloth_zozo.py")
# the runners a "file"/"remote" result may come from ($HIFIPUSHIE_CLOTH_SOLVER names one; default newton)
RUNNERS = {"zozo": ZOZO_RUNNER,
           "newton": Path(__file__).resolve().parents[2] / "spikes" / "gpu_cloth" / "run_newton.py"}


def backend_of(g: dict) -> str:
    b = g.get("backend") or os.environ.get("HIFIPUSHIE_CLOTH_BACKEND") or "blender"
    if b not in BACKENDS:
        raise ValueError(f"cloth backend is one of {', '.join(BACKENDS)}, got {b!r}")
    return b


def solver_of(backend: str) -> str:
    """The solver that makes a backend's result: "blender", "zozo", or for "file"/"remote" $HIFIPUSHIE_CLOTH_SOLVER
    (default "newton"; text after a ":" tells hand-carried results apart, e.g. "newton:<out.npz>")."""
    if backend in ("blender", "zozo"):
        return backend
    return os.environ.get("HIFIPUSHIE_CLOTH_SOLVER", "newton")


def solver_code(solver: str) -> str:
    """The hash of the code that makes this solver's result, for the sim cache key: its runner file (cloth_zozo.py,
    run_newton.py), never blender_cloth.py, so a 30-minute ZOZO result isn't lost to an edit of the Blender script."""
    f = RUNNERS.get(solver.split(":", 1)[0])
    body = f.read_bytes() if f is not None and f.exists() else b""
    return hashlib.sha1(body + solver.encode()).hexdigest()


def zozo_root() -> Path:
    """The unpacked ZOZO release (the folder holding python/, target/, frontend/)."""
    env = os.environ.get("HIFIPUSHIE_ZOZO") or os.environ.get("PPF_ROOT")
    if env:
        root = Path(env).expanduser()
    else:
        from . import assets
        root = assets.pack("zozo") / "release"
    if not (root / "python" / "bin" / "python3.12").exists():
        raise FileNotFoundError(f"no ZOZO release at {root} (python/bin/python3.12 missing): set HIFIPUSHIE_ZOZO to "
                                "the unpacked release, or run `uv run hifipushie-assets fetch zozo`")
    return root


def zozo_device(root: Path) -> str:
    """$HIFIPUSHIE_ZOZO_DEVICE, else cuda (nvidia-smi on the PATH), rocm (/dev/kfd), cpu."""
    dev = os.environ.get("HIFIPUSHIE_ZOZO_DEVICE")
    if not dev:
        dev = "cuda" if shutil.which("nvidia-smi") else "rocm" if Path("/dev/kfd").exists() else "cpu"
    if not (root / "target" / dev).exists():
        raise FileNotFoundError(f"the ZOZO release at {root} has no {dev} backend (target/{dev})")
    return dev


def zozo_command(job_dir: Path, args: list | None = None) -> tuple[list, dict]:
    """The local ZOZO command for a job folder and its environment: the release's own Python, memory-capped in a
    systemd scope where there is one (a runaway session must not take the desktop down)."""
    root = zozo_root()
    dev = zozo_device(root)
    env = dict(os.environ, CARGO_TARGET_DIR=str(root / "target" / dev), PYTHONPATH=str(root), PYTHONNOUSERSITE="1",
               PYTHONDONTWRITEBYTECODE="1")
    for k in ("PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(k, None)
    cmd = [str(root / "python" / "bin" / "python3.12"), str(ZOZO_RUNNER), str(job_dir), *(args or [])]
    if shutil.which("systemd-run") and os.environ.get("HIFIPUSHIE_ZOZO_SCOPE", "1") != "0":
        cmd = ["systemd-run", "--user", "--scope", "-q", "-p",
               f"MemoryMax={os.environ.get('HIFIPUSHIE_ZOZO_MEM', '6G')}", "-p", "MemorySwapMax=0", *cmd]
    return cmd, env


def _stream(cmd: list, progress, timeout: float, env: dict | None = None, what: str = "cloth job") -> list:
    """Run cmd, passing its "cloth:" lines to progress. Returns its lines; raises on failure or timeout (killed)."""
    t = time.time()
    from . import resources
    p = resources.track(subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env))
    lines = []
    try:
        for line in p.stdout:
            lines.append(line.rstrip())
            if "cloth:" in line:  # (ZOZO's own tqdm bar, written without newlines, can lead the line)
                progress(line[line.rindex("cloth:") + 6:].strip())
            if time.time() - t > timeout:
                raise RuntimeError(f"{what} over {timeout:.0f} s, stopped")
        p.wait(timeout=60)
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
    if p.returncode != 0:
        raise RuntimeError(f"{what} failed (exit {p.returncode}):\n" + "\n".join(lines[-40:]))
    return lines


def run_zozo(job_dir: Path, progress, log=print, timeout: float | None = None) -> tuple:
    """Run a written job with ZOZO: through $HIFIPUSHIE_ZOZO_REMOTE (a GPU box) when set, else here, under the
    machine's heavy slot. Returns (out.npz contents, log lines)."""
    timeout = float(timeout or os.environ.get("HIFIPUSHIE_ZOZO_TIMEOUT", 4 * 3600))
    remote = os.environ.get("HIFIPUSHIE_ZOZO_REMOTE")
    if remote:
        return run_external(job_dir, "remote", progress, timeout, cmd=remote)
    from . import resources
    cmd, env = zozo_command(job_dir)
    progress(f"zozo ({env['CARGO_TARGET_DIR'].rsplit('/', 1)[-1]}): waiting for the heavy-job slot")
    both = lambda m: (log(m), progress(m))  # noqa: E731  (the wait is shown where the sim reports)
    with resources.heavy(f"zozo cloth {job_dir.parent.name}", log=both, kind="cloth_zozo", gpu=True,
                         model=job_dir.parent.name):
        progress("zozo started")
        _stream(cmd, progress, timeout, env, "zozo cloth job")
    return read_out(job_dir / "out.npz")


def read_out(out: Path) -> tuple:
    """An out.npz's arrays and its log lines ("cloth: ...")."""
    if not Path(out).exists():
        raise RuntimeError(f"cloth job: no {out}")
    d = dict(np.load(out, allow_pickle=False))
    lines = [str(x) for x in d.pop("log", np.array([]))] if "log" in d else []
    lines = [ln for ln in lines if not ln.startswith(("progress", "cloth: progress"))]
    d.pop("timing", None)
    return d, [ln if ln.startswith("cloth:") else "cloth: " + ln for ln in lines]


def run_external(job_dir: Path, backend: str, progress, timeout: float = 7200, cmd: str | None = None) -> tuple:
    """Hand the written job to another solver and read its out.npz. Returns (out.npz contents, log lines)."""
    out = job_dir / "out.npz"
    t = time.time()
    if backend == "remote":
        cmd = cmd or os.environ.get("HIFIPUSHIE_CLOTH_REMOTE")
        if not cmd:
            raise RuntimeError('cloth backend "remote" needs $HIFIPUSHIE_CLOTH_REMOTE: a command run with the job folder '
                               "as its last argument that leaves out.npz in it (spikes/gpu_cloth/remote.sh)")
        progress(f"remote: {cmd} {job_dir}")
        _stream(shlex.split(cmd) + [str(job_dir)], progress, timeout, what="remote cloth job")
    else:  # "file": somebody else runs it
        wait = float(os.environ.get("HIFIPUSHIE_CLOTH_WAIT", timeout))
        progress(f"job written to {job_dir}: waiting up to {wait:.0f} s for out.npz")
        while not out.exists():
            if time.time() - t > wait:
                raise RuntimeError(f"cloth job {job_dir}: no out.npz after {wait:.0f} s")
            time.sleep(2.0)
        time.sleep(1.0)  # let the writer finish
    return read_out(out)
