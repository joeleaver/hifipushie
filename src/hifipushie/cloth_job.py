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

import contextlib
import contextvars
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

# Submitting a sim to a RENTED solver (the GPU fleet, a rented box) costs money, so it is opt-in at the call site
# (dress-garrett 2026-10-15: model_body(simulate=True) from a measuring script built a layered garment's under
# garment and submitted it, twice). Allowed only inside `submitting()` (cloth.dress's worker, export's
# garments(simulate=True)) or with HP_SUBMIT_SIMS=1 in the environment; anything else raises SimNotSubmitted, the job
# folder already written. Free remotes (have.sh: the broker's pulled results; nobox.sh) are never gated.
_SUBMIT = contextvars.ContextVar("hp_submit_sims", default=False)
FREE_REMOTES = ("have.sh", "nobox.sh")


class SimNotSubmitted(RuntimeError):
    """A rented sim was asked for without an explicit opt-in (submitting() / HP_SUBMIT_SIMS=1)."""


@contextlib.contextmanager
def submitting():
    """Allow rented sims inside this block (the call site's explicit opt-in)."""
    tok = _SUBMIT.set(True)
    try:
        yield
    finally:
        _SUBMIT.reset(tok)


def may_submit() -> bool:
    return bool(_SUBMIT.get()) or os.environ.get("HP_SUBMIT_SIMS") == "1"


def _paid(remote: str) -> bool:
    return Path(shlex.split(remote)[0]).name not in FREE_REMOTES + tuple(
        x for x in os.environ.get("HP_FREE_REMOTES", "").split(":") if x)

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


def job_config(cfg: dict, names: list | None = None) -> dict:
    """job.json as write() writes it, without its "out" path."""
    cfg = dict(cfg, format=FORMAT, fps=FPS)
    cfg.setdefault("mode", "sim")
    if names is not None:
        cfg["pieces"] = list(names)
    if "fabric" in cfg:
        cfg["fabric"] = dict(cfg["fabric"], physical=physical(cfg["fabric"]))
    cfg["stages"] = stages(cfg)
    return cfg


def input_hash(cfg: dict, arrays: dict) -> str:
    """The hash of a job's actual inputs: job.json (as job_config gives it; "out" never counts) and in.npz's arrays
    (name, dtype, shape, bytes). Two jobs with this hash are the same sim, whatever their cache keys."""
    c = {k: v for k, v in cfg.items() if k != "out"}
    h = hashlib.sha1(json.dumps(json.loads(json.dumps(c, default=_jsonable)), sort_keys=True).encode())
    for k in sorted(arrays):
        a = np.ascontiguousarray(arrays[k])
        h.update(f"|{k}|{a.dtype.str}|{a.shape}|".encode())
        h.update(a.tobytes())
    return h.hexdigest()[:20]


def write(job_dir: Path, cfg: dict, arrays: dict, names: list | None = None) -> Path:
    """job.json + in.npz in job_dir (the Blender runner reads the same folder: its own keys are kept as they were)."""
    job_dir.mkdir(parents=True, exist_ok=True)
    np.savez(job_dir / "in.npz", **arrays)
    cfg = dict(job_config(cfg, names), out=str(job_dir / "out.npz"))
    (job_dir / "job.json").write_text(json.dumps(cfg, indent=1, default=_jsonable))
    (job_dir / "out.npz").unlink(missing_ok=True)
    return job_dir


def job_input_hash(job_dir: Path) -> str | None:
    """input_hash of a written job folder (job.json + in.npz), None when either is missing or unreadable."""
    try:
        cfg = json.loads((job_dir / "job.json").read_text())
        with np.load(job_dir / "in.npz", allow_pickle=False) as z:
            arrays = {k: z[k] for k in z.files}
    except Exception:
        return None
    return input_hash(cfg, arrays)


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
               PYTHONDONTWRITEBYTECODE="1",
               # ZOZO's "is a solver running" scans the whole host by default: another job's solver (a GPU claim held
               # elsewhere, a peer worktree's run) refused ours. The machine's queue (resources.heavy gpu=True) is the
               # exclusion; ZOZO only checks its own run's descendants
               PPF_SOLVER_SCAN_DESCENDANTS="1")
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


SOLVER_NAME = "ppf-contact"  # ZOZO's solver process (its frontend's SOLVER_PROCESS_NAME)


def _proc(pid: int) -> tuple[str, list, int] | None:
    """(comm, argv, parent pid) of a live, non-zombie process, or None."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        comm = stat[stat.index("(") + 1:stat.rindex(")")]
        fields = stat[stat.rindex(")") + 2:].split()
        if fields[0] == "Z":
            return None
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        return comm, [a.decode(errors="replace") for a in argv if a], int(fields[1])
    except (OSError, ValueError, IndexError):
        return None


def stray_solvers(mark: str = "hp_job_") -> list[dict]:
    """ZOZO solver processes of OUR jobs (a `--path` under a session dir named `mark`...) whose runner is gone: no
    ancestor runs cloth_zozo.py. A stopped session (a usage limit, a killed shell) leaves its solver on the GPU,
    reparented, and ZOZO's frontend then refuses every later run ("Solver is already running": it scans the whole
    host for a live solver process; there is no lock file). A solver whose cloth_zozo.py runner is alive is never
    listed, whoever's it is."""
    out = []
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        info = _proc(int(p.name))
        if info is None or SOLVER_NAME not in info[0]:
            continue
        comm, argv, ppid = info
        path = next((argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "--path"), "")
        if mark not in path:
            continue
        anc, seen, held = ppid, set(), False
        while anc > 1 and anc not in seen:
            seen.add(anc)
            a = _proc(anc)
            if a is None:
                break
            if any(x.endswith("cloth_zozo.py") for x in a[1]):
                held = True
                break
            anc = a[2]
        if not held:
            out.append({"pid": int(p.name), "session": path, "parent": ppid})
    return out


def clear_strays(log=print, mark: str = "hp_job_", wait: float = 10.0) -> list[dict]:
    """Stop `stray_solvers` (SIGTERM, then SIGKILL after `wait` s); returns what was stopped."""
    import signal
    strays = stray_solvers(mark)
    for s in strays:
        log(f"zozo: a solver left by a stopped run (pid {s['pid']}, {s['session']}): stopped")
        try:
            os.kill(s["pid"], signal.SIGTERM)
        except OSError:
            pass
    t = time.time()
    while strays and time.time() - t < wait and any(_proc(s["pid"]) for s in strays):
        time.sleep(0.2)
    for s in strays:
        if _proc(s["pid"]):
            try:
                os.kill(s["pid"], signal.SIGKILL)
            except OSError:
                pass
    return strays


def run_zozo(job_dir: Path, progress, log=print, timeout: float | None = None) -> tuple:
    """Run a written job with ZOZO: through $HIFIPUSHIE_ZOZO_REMOTE (a GPU box) when set, else here, under the
    machine's heavy slot. Returns (out.npz contents, log lines)."""
    timeout = float(timeout or os.environ.get("HIFIPUSHIE_ZOZO_TIMEOUT", 4 * 3600))
    remote = os.environ.get("HIFIPUSHIE_ZOZO_REMOTE")
    if not remote and os.environ.get("HIFIPUSHIE_GPU") == "bundle":  # oxidegen's GPU fleet (bundle jobs), the default remote
        remote = str(Path(__file__).resolve().parents[2] / "spikes" / "gpu_cloth" / "bundle.sh")
    if remote:
        if _paid(remote) and not may_submit():
            raise SimNotSubmitted(f"cloth job {job_dir}: not submitted to the rented solver ({Path(shlex.split(remote)[0]).name}):"
                                  " no opt-in at the call site (run it under cloth_job.submitting(), or HP_SUBMIT_SIMS=1;"
                                  " measuring / drafting never submits). The job folder is written.")
        if _paid(remote) and os.environ.get("HP_SKIP_PREFLIGHT") != "1":
            # (dress-garrett 2026-10-15: j15 was paid for and failed at frame 0 on a start the strain check refuses)
            jd_ = Path(job_dir)
            try:
                arr_ = dict(np.load(jd_ / "in.npz", allow_pickle=False))
                cfg_ = json.loads((jd_ / "job.json").read_text())
            except Exception:
                arr_ = None
            if arr_ is not None:
                pf_ = preflight(arr_, cfg_)
                if not pf_["ok"]:
                    raise SimNotSubmitted(f"cloth job {job_dir}: not submitted, its start fails the preflight (body "
                                          f"{pf_['body_mm']:.2f} mm / {pf_['body_pairs']} pairs, self "
                                          f"{(pf_['self'] or {}).get('ok')}, strain {pf_['strain']}): fix the start "
                                          "(HP_SKIP_PREFLIGHT=1 overrides)")
        return run_external(job_dir, "remote", progress, timeout, cmd=remote)
    from . import resources
    cmd, env = zozo_command(job_dir)
    progress(f"zozo ({env['CARGO_TARGET_DIR'].rsplit('/', 1)[-1]}): waiting for the heavy-job slot")
    both = lambda m: (log(m), progress(m))  # noqa: E731  (the wait is shown where the sim reports)
    with resources.heavy(f"zozo cloth {job_dir.parent.name}", log=both, kind="cloth_zozo", gpu=True,
                         model=job_dir.parent.name):
        progress("zozo started")
        clear_strays(both)  # (a stopped session's solver would make ZOZO refuse: "Solver is already running")
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


def _pt_tri(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Distance from points p to triangles abc, row-wise (exact: the face, else its nearest edge)."""
    ab, ac = b - a, c - a
    n = np.cross(ab, ac)
    nn = np.maximum(np.einsum("ij,ij->i", n, n), 1e-30)
    t = np.einsum("ij,ij->i", p - a, n) / nn
    q = p - t[:, None] * n
    v2 = q - a
    d00, d01, d11 = (np.einsum("ij,ij->i", x, y) for x, y in ((ab, ab), (ab, ac), (ac, ac)))
    d20, d21 = np.einsum("ij,ij->i", v2, ab), np.einsum("ij,ij->i", v2, ac)
    den = np.where(np.abs(d00 * d11 - d01 * d01) > 1e-30, d00 * d11 - d01 * d01, 1e-30)
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    inside = (v >= 0) & (w >= 0) & (v + w <= 1)

    def seg(a_, b_):
        d = b_ - a_
        s = np.clip(np.einsum("ij,ij->i", p - a_, d) / np.maximum(np.einsum("ij,ij->i", d, d), 1e-30), 0, 1)
        return np.linalg.norm(p - (a_ + s[:, None] * d), axis=1)
    return np.where(inside, np.abs(t) * np.sqrt(nn), np.minimum(np.minimum(seg(a, b), seg(b, c)), seg(c, a)))


def self_proximity(X: np.ndarray, F: np.ndarray, piece: np.ndarray, below: float,
                   skip: np.ndarray | None = None) -> list:
    """A start's cloth against ITSELF, within each piece: (distance, vertex, face) for every vertex closer than `below`
    to a triangle of its own piece that doesn't contain it, nearest first. dress-garrett 2026-10-15: shirt s7 failed at
    frame 0 ("ccd failed (toi 0)") with the back's left armhole folded at the start, a vertex 0.22 mm from its own
    piece's cloth (rest fine, 15.6 mm), inside the contact gap; the body-clearance preflight passed it. Cross-piece
    contacts (lapped fronts, collar on stand) are normal in a start and not counted. `skip`: vertices not checked
    (carried made pieces, pinned as constructed)."""
    from scipy.spatial import cKDTree
    X, F, piece = np.asarray(X, float), np.asarray(F), np.asarray(piece)
    cen = X[F].mean(1)
    rad = float(np.linalg.norm(X[F] - cen[:, None], axis=2).max())
    vs = np.arange(len(X)) if skip is None else np.where(~np.asarray(skip, bool))[0]
    L = cKDTree(cen).query_ball_point(X[vs], rad + below)
    I = np.array([(v, f) for v, fs in zip(vs, L) for f in fs], np.int64).reshape(-1, 2)
    if not len(I):
        return []
    I = I[(F[I[:, 1]] != I[:, :1]).all(1) & (piece[F[I[:, 1], 0]] == piece[I[:, 0]])]
    d = _pt_tri(X[I[:, 0]], *(X[F[I[:, 1], k]] for k in range(3)))
    m = d < below
    o = np.argsort(d[m])
    return [(float(d[m][i]), int(I[m][i, 0]), int(I[m][i, 1])) for i in o]


def start_self_check(arrays: dict, gap: float = 1e-3, crush: float = 0.25) -> dict:
    """A job's start checked against itself, before any money is spent: a same-piece vertex inside the cloth contact
    gap of its own sheet, CRUSHED in plane (the vertex's one-ring facing the same way as the triangle it nearly
    touches), and (reported, NOT a fault) edges squeezed under `crush` x their pattern length: dg_j8's undercollar
    started at 0.13 x and ran, s7's back at 0.14 x failed, so squeeze alone doesn't decide. Designed folds are not faults: vertices on (or
    next to) a fold row, and folded-over sheets (a crease brings the cloth back facing the other way: lapel roll
    lines at 0.04 mm ran fine in dg_j8). Calibrated on dress-garrett's starts: shirt s7 (frame-0 failure) has its back's
    armhole vertex 0.22 mm off its own sheet facing +0.42; the two shirts and the jackets (j8, j12, j13) that ran have
    none. Returns {"ok", "pairs": [(mm, vertex, face, facing)], "edges":
    [(ratio, a, b)]}."""
    X, F, P = np.asarray(arrays["X"], float), np.asarray(arrays["F"]), np.asarray(arrays["piece"])
    skip = np.zeros(len(X), bool)
    if "carryIdx" in arrays:
        skip[np.asarray(arrays["carryIdx"], int)] = True
    if "releaseIdx" in arrays:
        skip[np.asarray(arrays["releaseIdx"], int)] = False
    if "fold" in arrays:
        fo = np.asarray(arrays["fold"]) > 0
        fo[F[fo[F].any(1)].ravel()] = True  # one ring round each fold row
        skip |= fo
    else:
        fo = np.zeros(len(X), bool)
    # a seam closing on itself is not a crush: a sewn vertex at its partner's side of the seam (a one-piece tube's
    # underarm seam, placed closed: dress-tess's knit sweater starts s30 / s31 ran with 186 / 194 such pairs at 0.0 mm,
    # every one a sleeve vertex against a face one ring from its own sew partner, ~235 mm away in the pattern)
    sw_ = [np.asarray(arrays[k], int).reshape(-1, 2) for k in ("sew", "stitch") if k in arrays]
    sw_ = np.concatenate(sw_) if sw_ else np.zeros((0, 2), int)
    mate = {}
    for a_, b_ in sw_:
        mate.setdefault(int(a_), set()).add(int(b_))
        mate.setdefault(int(b_), set()).add(int(a_))
    ring = {}
    if mate:
        for t in F:
            for i in t:
                if int(i) in mate:
                    ring.setdefault(int(i), set()).update(map(int, t))

    def across_own_seam(v, f):
        near_ = set()
        for u in ring.get(v, {v}):
            for m_ in mate.get(u, ()):
                near_ |= ring.get(m_, {m_})
        return bool(near_ & set(map(int, F[f])))

    pairs = []
    for d, v, f in self_proximity(X, F, P, gap, skip):
        if fo[F[f]].any():
            continue
        if mate and across_own_seam(int(v), int(f)):
            continue
        t = F[f]
        nt = np.cross(X[t[1]] - X[t[0]], X[t[2]] - X[t[0]])
        inc = F[(F == v).any(1)]
        nv = np.cross(X[inc[:, 1]] - X[inc[:, 0]], X[inc[:, 2]] - X[inc[:, 0]]).sum(0)
        c = float(nt @ nv / max(np.linalg.norm(nt) * np.linalg.norm(nv), 1e-30))
        if c > 0:
            pairs.append((1000 * d, v, f, round(c, 2)))
    edges = []
    if "uv" in arrays:
        uv = np.asarray(arrays["uv"], float)
        E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
        E = E[~(skip[E[:, 0]] & skip[E[:, 1]])]
        r = np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1) / np.maximum(np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1), 1e-9)
        o = np.argsort(r)
        edges = [(float(r[i]), int(E[i, 0]), int(E[i, 1])) for i in o if r[i] < crush]
    return {"ok": not pairs, "pairs": pairs, "edges": edges}


def start_strain_check(arrays: dict, cfg: dict | None = None) -> dict:
    """A smooth-placement start against ZOZO's strain limiter, set up exactly as cloth_zozo.py sets it (rest = the flat
    pattern, made / carried pieces rest as made / placed; draped triangles past the limit get a local limit only while
    they are at most `start_over` (3%) of the cloth). A face that STARTS at or past its own limit makes the limiter's
    line search return 0 (strain_toi.kernel) unless the first Newton step happens to take it back under: frame 0
    "### ccd failed (toi: 0)" + "strain limiting toi: 0". dress-garrett 2026-10-15: the base-hps jacket j15 (3.47% of
    its triangles over 5%, so no local limit: 217 faces past it) and the base-hps shirt probe (3.04%) failed so; j8
    (2.27%, 0 past) and shirts s5 / s6 (2.6%, local limit on) ran. Faces past even the local limit's 100% cap (s5 / s6
    ran with 26-28, s8 failed with 31) are reported, not failed: alone they don't decide. Returns {"ok", "over",
    "over_frac", "local", "past": faces past their limit with the local limit applied, "capped": faces past the cap,
    "worst": [(stretch, face, piece)]}. Non-smooth jobs (rest = the start) are always ok."""
    from . import cloth_zozo as cz
    cfg = cfg or {}
    if cfg.get("placement") != "smooth" or cfg.get("rest", "flat") != "flat" or cfg.get("mode") == "fine_settle":
        return {"ok": True, "skipped": True}
    X, F, pid, uv = (np.asarray(arrays[k]) for k in ("X", "F", "piece", "uv"))
    X = X.astype(float)
    pieces = list(cfg.get("pieces") or [])
    flat3 = np.c_[np.asarray(uv, float), np.zeros(len(uv))]
    made = np.isin(pid, [pieces.index(n) for n in cfg.get("made", []) if n in pieces])
    flat3[made] = np.asarray(arrays["rest"] if "rest" in arrays else X, float)[made]
    lifted = made.copy()
    if "releaseIdx" in arrays:
        lifted[np.asarray(arrays["releaseIdx"], np.int64)] = True
    if "carryIdx" in arrays:
        ci = np.asarray(arrays["carryIdx"], np.int64)
        flat3[ci] = X[ci]
    lim = float(cfg.get("strain_limit", 0.05))
    sig = cz._start_stretch(flat3, X, F)
    over = (sig > 1.0 + lim) & ~lifted[F].all(1)
    frac = float(over.mean()) if len(F) else 0.0
    local = 0 < frac <= float(cfg.get("start_over", 0.03))
    if local:
        lifted[np.unique(F[over])] = True
    fm = lifted[F].all(1) | over
    need = float(sig[fm].max()) - 1.0 if fm.any() else 0.0
    tgt = min(1.0, 1.3 * need + 0.02) if need > 0.8 * lim else None
    lv = cz.vertex_limits(pid, pieces, lim, lifted, tgt, np.zeros(len(pid), bool), lim, cfg.get("declared"))
    past = sig - 1.0 >= lv[F].min(1)
    capped = int((sig - 1.0 >= 1.0).sum())
    o = np.argsort(-sig)[:5]
    worst = [(round(float(sig[i]), 3), int(i), pieces[int(pid[F[i, 0]])] if pieces else int(pid[F[i, 0]])) for i in o]
    # past the garment's limit with no local limit = certain frame-0 failure; with it, only faces past the cap remain
    ok = not (over.any() and not local)
    return {"ok": ok, "over": int(over.sum()), "over_frac": round(frac, 4), "local": local, "past": int(past.sum()),
            "capped": capped, "worst": worst}


def preflight(arrays: dict, cfg: dict | None = None) -> dict:
    """A job's start checked before it is submitted (dress-garrett 2026-10-15; was the scratch preflight.py): free
    cloth edges against the collider's edges, closer than the body contact offset (2 mm for a first sim: dg_j4 1.71 mm
    failed at frame 0, dg_j5 0.26 mm crawled 14 s a frame; 1 mm for a fine settle, which starts from a sim's rest lying
    at the offset), then `start_self_check` for FIRST sims only. A fine settle starts from a sim's REST, cloth folded
    on itself at the contact gap: the fine settles that ran (6fbc9b50, 7813e7ca, 0c06de36) all read 39-55 crushed pairs
    at 0.3-0.8 mm, so the self check skips them (it refused j14's shirt fine settle). Carried made pieces (pinned as
    constructed) are not checked, released flaps are. Then `start_strain_check` (the start against the strain limiter: j15's
    frame-0 failure). Returns {"ok", "body_mm", "body_pairs", "self": None (skipped) or start_self_check's dict,
    "strain": start_strain_check's dict}."""
    from scipy.spatial import cKDTree
    from .cloth import _seg_seg
    cfg = cfg or {}
    fine = cfg.get("mode") == "fine_settle"
    X, F = np.asarray(arrays["X"], float), np.asarray(arrays["F"])
    bV = np.asarray(arrays["bodyV0"] if "bodyV0" in arrays else arrays["bodyV"], float)
    bT = np.asarray(arrays["bodyT"])
    edges_ = lambda T: np.unique(np.sort(np.r_[T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]], 1), axis=0)
    E, bE = edges_(F), edges_(bT)
    ex = np.zeros(len(X), bool)
    if "carryIdx" in arrays:
        ex[np.asarray(arrays["carryIdx"], int)] = True
    if "releaseIdx" in arrays:
        ex[np.asarray(arrays["releaseIdx"], int)] = False
    E = E[~ex[E].all(1)]
    L = cKDTree(bV[bE].mean(1)).query_ball_point(X[E].mean(1), 0.03)
    I = np.array([(i, k) for i, ks in enumerate(L) for k in ks], np.int64).reshape(-1, 2)
    body_mm, body_pairs = float("inf"), 0
    if len(I):
        _, _, dd = _seg_seg(X[E[I[:, 0], 0]], X[E[I[:, 0], 1]], bV[bE[I[:, 1], 0]], bV[bE[I[:, 1], 1]])
        body_mm, body_pairs = 1000 * float(dd.min()), int((dd < (0.001 if fine else 0.002)).sum())
    sc = None if fine else start_self_check(arrays, float((cfg.get("zozo") or {}).get("contact_gap", 1e-3)))
    st = start_strain_check(arrays, cfg) if all(k in arrays for k in ("uv", "piece")) else {"ok": True, "skipped": True}
    return {"ok": body_pairs == 0 and (sc is None or sc["ok"]) and st["ok"], "body_mm": body_mm,
            "body_pairs": body_pairs, "self": sc, "strain": st}
