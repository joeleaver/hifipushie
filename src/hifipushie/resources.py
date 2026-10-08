"""Machine resources for heavy jobs: admission of heavy jobs by a memory budget in fair FIFO order (shared by every
process, session and agent on the machine), one GPU job at a time, worker counts sized from a job's granted
memory, cancellation of heavy jobs whose caller went away, and a memory guard that stops a pool before the desktop
runs out (2026-09-29: two terrain exports with 16 x ~2 GB workers plus other agents' jobs OOM-killed the user's
session twice).

Heavy jobs (`heavy`): each declares an estimated peak (GB, `gb=`, else `estimate(kind, model)`: a default per kind,
raised by peaks measured on earlier runs) and whether it needs the GPU. A job is admitted when the declared peaks of
the running jobs plus its own fit under the budget ($HIFIPUSHIE_HEAVY_GB, default total RAM - max(8 GB, a third):
~40 GB on a 60 GB box) and, while other jobs run, what is really free (MemAvailable - reserve - what the running jobs
declared but don't use yet) covers it. A lone job is always admitted (its pools then size by free memory). Order:
FIFO by when a job started waiting. A waiting job that doesn't fit blocks every younger job, except SMALL ones (<=
`SMALL` of the budget) that fit now: they may pass, but each blocked job can be passed at most `PASS_LIMIT` times,
then nothing passes it (no starvation). GPU jobs (`gpu=True`, or `gpu()` inside a job) run one at a time, in FIFO
order among themselves; a job waiting for the GPU doesn't block others' memory. $HIFIPUSHIE_HEAVY_SLOTS (optional)
caps how many heavy jobs run at once (1 = the old one-slot behaviour).

State lives in $HIFIPUSHIE_HEAVY_DIR (default $XDG_RUNTIME_DIR/hifipushie): jobs/<id>.json (who, what, GB, state) and
jobs/<id>.lock (flocked by the owner for as long as it lives: a lock we can take = a dead owner, swept), all changes
under queue.lock. heavy0.lock is the old code's slot: every running job holds it SHARED, so a process still on the
old code (LOCK_EX) waits while any new job runs, and an old job holding it counts as `LEGACY_GB`.
These fds are never inherited: closed in forked children (pool workers), O_CLOEXEC for exec.

Cancellation: the MCP server runs each tool call under `cancel_scope(event)` and sets the event when the call is
cancelled or the client goes away. A waiting job then leaves the queue; a running one has its tracked subprocesses
(`track`, `run`) killed, its guarded pools (`guarded`) killed, and `Cancelled` raised in its thread, so the slot is
released. Long loops can also call `check_cancel()` between stages.

Settings: $HIFIPUSHIE_MEM_GB caps what pools may use without a grant (default half of RAM)."""
from __future__ import annotations

import contextlib
import ctypes
import fcntl
import json
import os
import random
import signal
import subprocess
import threading
import time
from pathlib import Path


def _cgroup_mem_gb() -> tuple[float | None, float | None]:
    """The container's memory limit and current use in GB (cgroup v2, else v1), or None where there's no limit:
    inside a container /proc/meminfo shows the HOST (a hosted sculpt box saw 503 GB), not what we may use."""
    for limit_p, used_p in (("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
                            ("/sys/fs/cgroup/memory/memory.limit_in_bytes", "/sys/fs/cgroup/memory/memory.usage_in_bytes")):
        try:
            raw = Path(limit_p).read_text().strip()
        except OSError:
            continue
        if raw == "max" or not raw.isdigit() or int(raw) >= 1 << 60:  # v1 reports "no limit" as a huge number
            return None, None
        try:
            used = int(Path(used_p).read_text().strip()) / 2**30
        except (OSError, ValueError):
            used = None
        return int(raw) / 2**30, used
    return None, None


def meminfo() -> dict:
    """Memory in GB ({"total", "available"}): /proc/meminfo, capped by the container's limit when there is one."""
    out = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            out[k] = int(v.split()[0]) / 2**20
    except OSError:
        return {"total": 16.0, "available": 8.0}
    total, avail = out.get("MemTotal", 16.0), out.get("MemAvailable", 8.0)
    limit, used = _cgroup_mem_gb()
    if limit is not None:
        total = min(total, limit)
        avail = min(avail, limit - (used or 0.0))
    return {"total": total, "available": max(0.0, avail)}


def cpus() -> int:
    """CPUs this process may use: the affinity mask and the container's CPU quota (cgroup v2 cpu.max / v1 cfs quota),
    not os.cpu_count(), which inside a container is the HOST's (a hosted sculpt box saw 96)."""
    n = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 2)
    for quota_p, period_p in (("/sys/fs/cgroup/cpu.max", None),
                              ("/sys/fs/cgroup/cpu/cpu.cfs_quota_us", "/sys/fs/cgroup/cpu/cpu.cfs_period_us")):
        try:
            parts = Path(quota_p).read_text().split()
            quota, period = parts[0], (parts[1] if period_p is None else Path(period_p).read_text().strip())
        except (OSError, IndexError):
            continue
        if quota not in ("max", "-1") and int(period) > 0:
            n = min(n, max(1, int(quota) // int(period)))
        break
    return max(1, n)


def reserve_gb() -> float:
    """Memory left for the desktop and everything else, never handed to workers."""
    return max(6.0, 0.12 * meminfo()["total"])


def budget_gb() -> float:
    m = meminfo()
    cap = float(os.environ.get("HIFIPUSHIE_MEM_GB", 0) or 0.5 * m["total"])
    return max(0.0, min(cap, m["available"] - reserve_gb()))


def workers(per_worker_gb: float, cap: int | None = None, jobs: int | None = None) -> int:
    """How many worker processes of ~per_worker_gb fit (at least 1): in the memory this thread's heavy job was
    GRANTED (its declared peak, less ~1 GB for the parent) when it holds one, and never more than free memory allows
    now. Sizing by free memory alone is how two jobs that both saw "free" memory took the desktop down."""
    n = int(budget_gb() // max(per_worker_gb, 0.1))
    g = granted_gb()
    if g is not None:
        n = min(n, int(max(g - 1.0, per_worker_gb) // max(per_worker_gb, 0.1)))
    n = min(n, max(1, cpus() - 2))
    if cap:
        n = min(n, cap)
    if jobs:
        n = min(n, jobs)
    return max(1, n)


# ---------------------------------------------------------------------------------------------------------------
# Heavy jobs: admission by memory budget, FIFO, GPU, cancellation

# Conservative defaults (GB) per kind, from measured peaks (CLAUDE.md): a terrain island 5.2, pebble ~9 (16 workers
# x ~1 GB), the alps block ~17; ZOZO runs capped at 6 GB (+ its Python); a character's export_asset a few GB.
# Jobs with pools get workers from what they're granted, so the default also sets how fast they run.
KIND_GB = {"export_asset": 6.0, "terrain_tiles": 16.0, "cloth_blender": 4.0, "cloth_zozo": 7.0, "hair_cycles": 6.0,
           "stand_export": 6.0, "gpu": 0.0, "heavy": 8.0}
SMALL = 0.25        # share of the budget under which a job may pass a waiting job that doesn't fit
PASS_LIMIT = 3      # how many times a waiting job may be passed by small jobs
LEGACY_GB = 12.0    # what a job on the old code (holding heavy0.lock exclusively) is counted as
POLL = 1.0          # s between looks at the queue while waiting
SAMPLE = 3.0        # s between memory samples of a running job

_tls = threading.local()
_LOCK = threading.Lock()          # this process's bookkeeping
_OPEN: dict[int, object] = {}     # fd -> owner: every fd we hold in the state dir (closed in forked children)
_CHILD = False                    # a forked child of a process that held heavy state: heavy() passes through
_SEQ = [0]


class Cancelled(Exception):
    """The heavy job's caller cancelled (or went away): the job stops and releases its memory grant."""


def heavy_dir() -> Path:
    d = os.environ.get("HIFIPUSHIE_HEAVY_DIR")
    d = Path(d) if d else Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "hifipushie"
    (d / "jobs").mkdir(parents=True, exist_ok=True)
    return d


def heavy_budget_gb() -> float:
    env = os.environ.get("HIFIPUSHIE_HEAVY_GB")
    if env:
        return float(env)
    t = meminfo()["total"]
    return max(2.0, t - max(8.0, t / 3))


def _peaks_path() -> Path:
    p = os.environ.get("HIFIPUSHIE_HEAVY_PEAKS")
    return Path(p) if p else Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "hifipushie" / "heavy_peaks.json"


def _peaks() -> dict:
    try:
        return json.loads(_peaks_path().read_text())
    except (OSError, ValueError):
        return {}


def estimate(kind: str, model: str | None = None) -> float:
    """Declared peak for a job of this kind (and model): the kind's default, raised to the largest peak measured on
    recent runs of this model (else of this kind). Measurements only RAISE the estimate: a pooled job sized from its
    grant would otherwise measure less each run and shrink its own estimate run after run."""
    base = KIND_GB.get(kind, KIND_GB["heavy"])
    rec = _peaks().get(kind) or {}
    seen = rec.get(model or "") or rec.get("_all") or []
    return round(max([base] + [float(x) for x in seen[-8:]]), 1)


def _record_peak(kind: str, model: str | None, gb: float):
    p = _peaks_path()
    with contextlib.suppress(OSError, ValueError):
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            fh.seek(0)
            try:
                d = json.loads(fh.read() or "{}")
            except ValueError:
                d = {}
            rec = d.setdefault(kind, {})
            for key in {"_all", model or "_all"}:
                rec[key] = (rec.get(key, []) + [round(gb, 2)])[-8:]
            fh.seek(0), fh.truncate(), fh.write(json.dumps(d, indent=1)), fh.flush()


def _open_fd(path: Path, flags=os.O_RDWR | os.O_CREAT) -> int:
    fd = os.open(path, flags | os.O_CLOEXEC, 0o644)
    with _LOCK:
        _OPEN[fd] = path
    return fd


def _close_fd(fd: int):
    with _LOCK:
        _OPEN.pop(fd, None)
    with contextlib.suppress(OSError):
        os.close(fd)


def _after_fork_child():
    """In a forked child (a pool worker): drop every fd of the heavy state WITHOUT unlocking (flock belongs to the
    open file description the parent still holds; LOCK_UN here would release the parent's job). Without this every
    pool worker kept heavy0.lock, and killing the parent didn't free the slot."""
    global _CHILD
    if _OPEN:
        _CHILD = True
    for fd in list(_OPEN):
        with contextlib.suppress(OSError):
            os.close(fd)
    _OPEN.clear()


os.register_at_fork(after_in_child=_after_fork_child)


@contextlib.contextmanager
def _queue_lock(d: Path):
    fd = _open_fd(d / "queue.lock")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        _close_fd(fd)  # closing releases the flock


def _write_json(path: Path, data: dict):
    tmp = path.with_suffix(f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)


def _alive(lock: Path) -> bool:
    """Is the owner of a job's .lock alive (it holds the flock)? Only called under the queue lock."""
    try:
        fd = os.open(lock, os.O_RDWR | os.O_CLOEXEC)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return False
    except BlockingIOError:
        return True
    finally:
        os.close(fd)


def _jobs(d: Path) -> list[dict]:
    """Live jobs (waiting and running), oldest first; dead owners' files swept. Under the queue lock."""
    out = []
    for lk in sorted((d / "jobs").glob("*.lock")):
        js = lk.with_suffix(".json")
        if not _alive(lk):
            for p in (lk, js):
                with contextlib.suppress(OSError):
                    p.unlink()
            continue
        try:
            j = json.loads(js.read_text())
        except (OSError, ValueError):
            continue  # being written: it holds no claim yet
        j["_path"] = str(js)
        out.append(j)
    return out


def _legacy(d: Path) -> dict | None:
    """A job on the old code holding heavy0.lock exclusively, or None."""
    p = d / "heavy0.lock"
    try:
        fd = os.open(p, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o644)
    except OSError:
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        return None
    except BlockingIOError:
        txt = Path(p).read_text().strip().split("\n")[0].split(" ", 1)
        return {"pid": int(txt[0]) if txt and txt[0].isdigit() else None,
                "name": txt[1] if len(txt) > 1 else "(old hifipushie code)", "gb": LEGACY_GB, "legacy": True}
    finally:
        os.close(fd)


def _descendants(pid: int) -> list[int]:
    out, todo = [], [pid]
    while todo:
        c = _children(todo.pop())
        out += c
        todo += c
    return out


def _use_gb(pid: int) -> float:
    return _pss_gb(pid) + sum(_pss_gb(c) for c in _descendants(pid))


def _holds_gpu(j: dict) -> bool:
    """Does a running job (or the old code's holder) hold the GPU? A job that says so, and any job we can't tell:
    the old code's holder of heavy0.lock and jobs of unknown kind (2026-10-07: an old-code ZOZO sim held only
    heavy0.lock, was counted as memory but not as the GPU, and a new ZOZO sim was admitted beside it: one crashed)."""
    return bool(j.get("gpu") or j.get("legacy") or j.get("kind") in (None, "heavy"))


def _plan(d: Path, jobs: list[dict], legacy: dict | None) -> dict:
    """Who may run now. Simulates the queue in FIFO order: {id: "run" | reason} for every waiting job."""
    budget = heavy_budget_gb()
    running = [j for j in jobs if j["state"] == "running"]
    waiting = [j for j in jobs if j["state"] == "waiting"]
    used = sum(j["gb"] for j in running) + (legacy["gb"] if legacy else 0.0)
    avail = budget - used
    max_jobs = int(os.environ.get("HIFIPUSHIE_HEAVY_SLOTS", 0) or 0)
    n_run = len(running) + (1 if legacy else 0)
    gpu_busy = any(_holds_gpu(j) for j in running) or legacy is not None
    real = None
    if n_run and os.environ.get("HIFIPUSHIE_HEAVY_FREECHECK", "1") != "0":
        unclaimed = 0.0
        for pid in {j["pid"] for j in running}:
            decl = sum(j["gb"] for j in running if j["pid"] == pid)
            unclaimed += max(0.0, decl - _use_gb(pid))
        real = meminfo()["available"] - reserve_gb() - unclaimed
    out, blockers = {}, []
    for j in waiting:
        gb = min(j["gb"], budget)
        if j.get("gpu") and gpu_busy:
            out[j["id"]] = "gpu"
            continue
        fits = gb <= avail + 1e-9 and (not max_jobs or n_run < max_jobs) and (not n_run or real is None or gb <= real)
        if gb <= 0 and (not max_jobs or n_run < max_jobs):
            ok = True  # a GPU-only claim inside a running job takes no memory
        elif not blockers:
            ok = fits
        else:
            ok = fits and gb <= SMALL * budget and all(b.get("passed", 0) < PASS_LIMIT for b in blockers)
        if j.get("gpu"):
            gpu_busy = True  # older GPU jobs keep their turn on the GPU
        if ok:
            out[j["id"]] = ("run", [b["id"] for b in blockers])
            avail -= gb
            if real is not None:
                real -= gb
            if gb > 0:
                n_run += 1
        else:
            out[j["id"]] = "memory" if not fits else "behind"
            if not fits and gb > 0:
                blockers.append(j)
    return out


def _fmt_job(j: dict, pid: bool = True) -> str:
    since = time.strftime("%H:%M", time.localtime(j.get("since", time.time())))
    gpu = ", GPU" if j.get("gpu") else ""
    if "id" not in j:  # the old code's holder
        return f"{_label(j['name'])} (old hifipushie code" + (f", pid {j.get('pid')})" if pid else ")")
    p = f"pid {j.get('pid')}, " if pid else ""
    return f"{_label(j['name'])} ({p}{j.get('gb', 0):.0f} GB{gpu}, since {since})"


def _label(name: str) -> str:
    """A job's name with no host path in it (a word with a "/" keeps its last part)."""
    return " ".join(w.rstrip("/").rsplit("/", 1)[-1] if "/" in w else w for w in str(name).split()) or "job"


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _wait_text(me: dict, jobs: list[dict], legacy: dict | None, reason: str) -> str:
    """What a waiting job reports (its tool's log / progress): no paths, no pids (it reaches other machines'
    departments through the artist's progress line)."""
    running = [j for j in jobs if j["state"] == "running"] + ([legacy] if legacy else [])
    ahead = [j for j in jobs if j["state"] == "waiting" and j["id"] < me["id"]]
    used = sum(j["gb"] for j in running)
    held = "; ".join(_fmt_job(j, pid=False) for j in running) or "nobody"
    if reason == "gpu":
        why = "waiting for the GPU"
        held = "; ".join(_fmt_job(j, pid=False) for j in running if _holds_gpu(j)) or held
    elif reason == "memory":
        why = f"waiting for memory: needs {me['gb']:.0f} GB, {used:.0f} of {heavy_budget_gb():.0f} GB declared by running jobs"
    else:
        why = "waiting behind older jobs"
    pos = f"{_ordinal(len(ahead) + 1)} in queue, {sum(j['gb'] for j in ahead):.0f} GB ahead of you"
    return f"{_label(me['name'])}: {why}; held by {held}; {pos}"


def caller_tag() -> str:
    """Who is asking, without saying where: a short hash of the session ($HIFIPUSHIE_SESSION, else the workspace
    $HIFIPUSHIE_HOME: an oxidegen artist session's own), else of this process. A job records the tag of the
    process that queued it, so `queue_view` can mark the caller's own jobs."""
    import hashlib
    key = os.environ.get("HIFIPUSHIE_SESSION") or os.environ.get("HIFIPUSHIE_HOME") or f"pid{os.getpid()}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def _job_info(name, kind, model, gb, gpu, state="waiting") -> dict:
    with _LOCK:
        _SEQ[0] += 1
        seq = _SEQ[0]
    return {"id": f"{time.time_ns():020d}-{os.getpid()}-{threading.get_ident() % 100000}-{seq}", "name": name,
            "kind": kind, "model": model, "gb": float(gb), "gpu": bool(gpu), "pid": os.getpid(),
            "cwd": os.getcwd(), "session": os.environ.get("HIFIPUSHIE_SESSION") or os.environ.get("CLAUDE_SESSION_ID"),
            "since": time.time(), "state": state, "passed": 0, "tag": caller_tag()}


def _acquire(d: Path, info: dict, log) -> tuple:
    """Wait in the queue until admitted. Returns (lock fd, fence fd or None, seconds waited, last wait text)."""
    jdir = d / "jobs"
    lock_p, json_p = jdir / f"{info['id']}.lock", jdir / f"{info['id']}.json"
    with _queue_lock(d):
        lfd = _open_fd(lock_p, os.O_RDWR | os.O_CREAT | os.O_EXCL)
        fcntl.flock(lfd, fcntl.LOCK_EX)
        _write_json(json_p, info)
    t0, last, last_t, fence, last_text = time.time(), None, 0.0, None, None
    try:
        while True:
            ev = current_cancel()
            if ev is not None and ev.is_set():
                raise Cancelled(f"{info['name']}: cancelled while waiting for the heavy slot")
            with _queue_lock(d):
                jobs = _jobs(d)
                legacy = _legacy(d)
                plan = _plan(d, jobs, legacy)
                p = plan.get(info["id"])
                if isinstance(p, tuple):
                    for b in jobs:
                        if b["id"] in p[1]:
                            b["passed"] = b.get("passed", 0) + 1
                            path = Path(b.pop("_path"))
                            _write_json(path, b)
                    info.update(state="running", started=time.time(), waited=round(time.time() - t0, 1))
                    _write_json(json_p, info)
                    if legacy is None:
                        fence = _open_fd(d / "heavy0.lock")
                        try:
                            fcntl.flock(fence, fcntl.LOCK_SH | fcntl.LOCK_NB)
                        except BlockingIOError:
                            _close_fd(fence)
                            fence = None
                    break
                text = _wait_text(info, jobs, legacy, p or "behind")
            core = text.rsplit("; ", 1)[0]
            if core != last or time.time() - last_t > (30 if text != last_text else 300):
                log(text)
                last, last_t, last_text = core, time.time(), text
            time.sleep(float(os.environ.get("HIFIPUSHIE_HEAVY_POLL", POLL)) * (0.8 + 0.4 * random.random()))
    except BaseException:
        with _queue_lock(d):
            for pth in (json_p, lock_p):
                with contextlib.suppress(OSError):
                    pth.unlink()
            _close_fd(lfd)
        raise
    return lfd, fence, time.time() - t0, last


def _release(d: Path, info: dict, lfd: int, fence: int | None):
    with _queue_lock(d):
        for pth in (d / "jobs" / f"{info['id']}.json", d / "jobs" / f"{info['id']}.lock"):
            with contextlib.suppress(OSError):
                pth.unlink()
        if fence is not None:
            _close_fd(fence)
        _close_fd(lfd)


# ---- cancellation ----

def current_cancel() -> threading.Event | None:
    return getattr(_tls, "cancel", None)


@contextlib.contextmanager
def cancel_scope(event: threading.Event):
    """Run a block (a tool call) whose heavy jobs stop when `event` is set."""
    old = getattr(_tls, "cancel", None)
    _tls.cancel = event
    try:
        yield event
    finally:
        _tls.cancel = old
        job = getattr(_tls, "job", None)
        if job is not None and old is None:  # a grant the job's own exit didn't release (cancelled mid-cleanup)
            with contextlib.suppress(Exception):
                job["release"]()
            _tls.job, _tls.depth = None, 0


def cancelled() -> bool:
    ev = current_cancel()
    return bool(ev is not None and ev.is_set())


def check_cancel(what: str = "job"):
    if cancelled():
        raise Cancelled(f"{what}: cancelled")


def _kill_group(p):
    with contextlib.suppress(Exception):
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGKILL) if getattr(p, "_hp_group", False) else p.kill()
            except ProcessLookupError:
                pass


def track(p):
    """Kill this subprocess if the heavy job it runs under is cancelled. Returns p."""
    job = getattr(_tls, "job", None)
    if job is not None:
        with _LOCK:
            job["procs"].append(p)
        if job["cancel"] is not None and job["cancel"].is_set():
            _kill_group(p)
    return p


def run(cmd, **kw) -> subprocess.CompletedProcess:
    """subprocess.run in its own process group, killed (with everything it started) if the heavy job is cancelled."""
    timeout = kw.pop("timeout", None)
    check = kw.pop("check", False)
    if kw.pop("capture_output", False):
        kw["stdout"], kw["stderr"] = subprocess.PIPE, subprocess.PIPE
    inp = kw.pop("input", None)
    if inp is not None:
        kw["stdin"] = subprocess.PIPE
    kw.setdefault("start_new_session", True)
    p = subprocess.Popen(cmd, **kw)
    p._hp_group = kw["start_new_session"]
    track(p)
    try:
        out, err = p.communicate(inp, timeout=timeout)
    except BaseException:
        _kill_group(p)
        p.wait()
        raise
    r = subprocess.CompletedProcess(p.args, p.returncode, out, err)
    if check:
        r.check_returncode()
    check_cancel(str(cmd[0]) if isinstance(cmd, (list, tuple)) else "subprocess")
    return r


def _raise_in(tid: int):
    ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(tid), ctypes.py_object(Cancelled))


def _clear_in(tid: int):
    ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(tid), None)


def granted_gb() -> float | None:
    """GB granted to the heavy job this thread runs (None outside one)."""
    job = getattr(_tls, "job", None)
    return job["gb"] if job else None


@contextlib.contextmanager
def heavy(name: str, log=print, gb: float | None = None, kind: str | None = None, gpu: bool = False,
          model: str | None = None):
    """Run a heavy job: wait in the machine-wide queue until its declared peak (`gb`, else `estimate(kind,
    model)`) fits the memory budget (and the GPU is free, `gpu=True`), then hold that grant while the block runs.
    Waiting is reported through `log` ("waiting for memory: ...; held by ...; N ahead of you"). Nested calls in the
    same thread pass through (a nested gpu=True claims the GPU alone). Raises Cancelled if the caller cancels."""
    depth = getattr(_tls, "depth", 0)
    if _CHILD or depth > 0:
        outer = getattr(_tls, "job", None)
        if gpu and not _CHILD and outer is not None and not outer["gpu"]:
            with gpu_claim(name, log=log):
                yield
            return
        _tls.depth = depth + 1
        try:
            yield
        finally:
            _tls.depth = depth
        return
    kind = kind or "heavy"
    gb = float(estimate(kind, model) if gb is None else gb)
    d = heavy_dir()
    info = _job_info(name, kind, model, min(gb, heavy_budget_gb()), gpu)
    lfd, fence, waited, _ = _acquire(d, info, log)
    if waited > 2:
        log(f"{name}: started after {waited:.0f} s wait")
    _tls.last_wait = (waited, _)
    ev = current_cancel()
    job = {"gb": info["gb"], "gpu": gpu, "procs": [], "cancel": ev, "tid": threading.get_ident(), "done": False,
           "raised": False, "released": False}

    def release():  # idempotent: also the backstop in cancel_scope
        with _LOCK:
            if job["released"]:
                return
            job["released"] = True
        _release(d, info, lfd, fence)

    job["release"] = release
    _tls.job, _tls.depth = job, 1
    stop = threading.Event()
    me = os.getpid()
    alone = _jobs_open() == 1  # this process runs no other heavy job: its memory is this job's
    base = _pss_gb(me)
    peak = [0.0]

    def watch():
        nxt = 0.0
        while not stop.wait(0.25):
            if ev is not None and ev.is_set():
                with _LOCK:
                    procs = list(job["procs"])
                for p in procs:
                    _kill_group(p)
                with _LOCK:
                    if not job["done"] and not job["raised"]:
                        job["raised"] = True
                        _raise_in(job["tid"])
                return
            if time.time() >= nxt:
                nxt = time.time() + SAMPLE
                peak[0] = max(peak[0], _use_gb(me) - base)

    th = threading.Thread(target=watch, daemon=True)
    th.start()
    ok = False
    try:
        yield
        ok = True
    finally:
        try:
            with _LOCK:
                job["done"] = True
                if job["raised"]:
                    _clear_in(job["tid"])  # a pending Cancelled not delivered yet must not fire later in this thread
        except Cancelled:  # delivered just now, inside this finally: nothing else can come (raised once)
            job["done"] = True
        stop.set()
        _tls.job, _tls.depth = None, 0
        try:
            release()
        finally:
            with contextlib.suppress(Exception):
                if ok and alone and _jobs_open() == 0 and peak[0] > 0.2:
                    _record_peak(kind, model, peak[0])
                    if peak[0] > 1.25 * info["gb"]:
                        log(f"WARNING {name}: used {peak[0]:.1f} GB, declared {info['gb']:.1f} GB "
                            f"(estimates raised for next time)")


def _jobs_open() -> int:
    """Heavy jobs (running or waiting) this process holds."""
    with _LOCK:
        return sum(1 for p in _OPEN.values() if str(p).endswith(".lock") and Path(p).parent.name == "jobs")


@contextlib.contextmanager
def gpu_claim(name: str, log=print):
    """Hold the machine's GPU (one GPU job at a time) without claiming memory: for a GPU stage inside a heavy job."""
    d = heavy_dir()
    info = _job_info(name + " (GPU)", "gpu", None, 0.0, True)
    lfd, fence, waited, _ = _acquire(d, info, log)
    try:
        yield
    finally:
        _release(d, info, lfd, fence)


def last_wait() -> tuple | None:
    """(seconds waited, last wait message) of this thread's last heavy job, for a tool's reply."""
    return getattr(_tls, "last_wait", None)


def status() -> dict:
    """The heavy-job queue as it stands: budget, declared use, running jobs, waiting jobs (oldest first, with why)."""
    d = heavy_dir()
    with _queue_lock(d):
        jobs = _jobs(d)
        legacy = _legacy(d)
        plan = _plan(d, jobs, legacy)
    clean = lambda j: {k: v for k, v in j.items() if not k.startswith("_")}  # noqa: E731
    running = [clean(j) for j in jobs if j["state"] == "running"]
    waiting = []
    for j in jobs:
        if j["state"] == "waiting":
            r = plan.get(j["id"])
            waiting.append(dict(clean(j), why="admitting" if isinstance(r, tuple) else r))
    return {"budget_gb": round(heavy_budget_gb(), 1),
            "declared_gb": round(sum(j["gb"] for j in running) + (legacy["gb"] if legacy else 0), 1),
            "available_gb": round(meminfo()["available"], 1), "running": running, "waiting": waiting,
            "legacy": legacy, "gpu": next((clean(j) for j in running if _holds_gpu(j)), legacy)}


def status_text() -> str:
    s = status()
    lines = [f"heavy jobs: {s['declared_gb']:.0f} of {s['budget_gb']:.0f} GB declared, {s['available_gb']:.0f} GB "
             f"free now; GPU: {s['gpu']['name'] if s['gpu'] else 'free'}"]
    if s["legacy"]:
        lines.append(f"  running (old hifipushie code, counted {LEGACY_GB:.0f} GB): {s['legacy']['name']} "
                     f"(pid {s['legacy']['pid']}): that session should update hifipushie / restart its MCP server")
    for j in s["running"]:
        lines.append(f"  running: {_fmt_job(j)} [{j['kind']}] {j.get('cwd', '')}")
    for i, j in enumerate(s["waiting"]):
        lines.append(f"  waiting {i + 1}: {_fmt_job(j)} [{j['kind']}] for {j['why']}; passed {j.get('passed', 0)}x; "
                     f"{j.get('cwd', '')}")
    if not s["running"] and not s["waiting"] and not s["legacy"]:
        lines.append("  nothing running or waiting")
    return "\n".join(lines)


def queue_view(tag: str | None = None) -> dict:
    """The heavy-job queue with nothing about the host in it (no paths, session dirs, pids, cwd): for callers on
    other machines (the oxidegen sculpt artist). Running jobs: kind, label, GB declared, GPU, minutes running.
    Waiting jobs in the order they're served: position, kind, label, GB, why, GB of the jobs ahead, minutes waited,
    and `yours` = queued by the caller (`tag`, default `caller_tag()`: the same session / workspace)."""
    tag = caller_tag() if tag is None else tag
    s = status()
    now = time.time()
    run = [{"kind": j.get("kind"), "label": _label(j["name"]), "gb": round(j["gb"], 1), "gpu": _holds_gpu(j),
            "minutes": round((now - j.get("started", j.get("since", now))) / 60, 1), "yours": j.get("tag") == tag}
           for j in s["running"]]
    if s["legacy"]:
        run.append({"kind": "unknown (older hifipushie)", "label": _label(s["legacy"]["name"]), "gb": LEGACY_GB,
                    "gpu": True, "minutes": None, "yours": False})
    wait, ahead = [], 0.0
    for i, j in enumerate(s["waiting"]):
        wait.append({"position": i + 1, "kind": j.get("kind"), "label": _label(j["name"]), "gb": round(j["gb"], 1),
                     "gpu": bool(j.get("gpu")), "why": j["why"], "gb_ahead": round(ahead, 1),
                     "minutes": round((now - j.get("since", now)) / 60, 1), "yours": j.get("tag") == tag})
        ahead += j["gb"]
    return {"budget_gb": s["budget_gb"], "declared_gb": s["declared_gb"],
            "gpu": next((r["label"] for r in run if r["gpu"]), None), "running": run, "waiting": wait}


WHY = {"memory": "waiting for memory", "gpu": "waiting for the GPU", "behind": "behind older jobs",
       "admitting": "starting"}


def queue_text(tag: str | None = None) -> str:
    q = queue_view(tag)
    lines = [f"heavy jobs on this machine: {q['declared_gb']:.0f} of {q['budget_gb']:.0f} GB declared; "
             f"GPU: {q['gpu'] or 'free'}"]
    for r in q["running"]:
        t = f", {r['minutes']:.0f} min" if r["minutes"] is not None else ""
        lines.append(f"  running: {r['label']} [{r['kind']}] {r['gb']:.0f} GB{', GPU' if r['gpu'] else ''}{t}"
                     + ("  <- yours" if r["yours"] else ""))
    for w in q["waiting"]:
        lines.append(f"  {_ordinal(w['position'])} in queue: {w['label']} [{w['kind']}] {w['gb']:.0f} GB"
                     f"{', GPU' if w['gpu'] else ''}, {WHY.get(w['why'], w['why'])}, {w['gb_ahead']:.0f} GB ahead, "
                     f"waited {w['minutes']:.0f} min" + ("  <- yours" if w["yours"] else ""))
    mine = [w for w in q["waiting"] if w["yours"]]
    if mine:
        w = mine[0]
        lines.append(f"yours: {_ordinal(w['position'])} in queue, {w['gb_ahead']:.0f} GB ahead "
                     f"({WHY.get(w['why'], w['why'])})")
    if not q["running"] and not q["waiting"]:
        lines.append("  nothing running or waiting")
    return "\n".join(lines)


def blas_threads(n: int = 1) -> list:
    """Set the thread count of every OpenBLAS already loaded in this process (numpy's and scipy's copies), e.g. in a
    pool worker: forked workers inherit the parent's 4 BLAS threads, and every small matmul (points @ a 3x3 rotation)
    then spun 4 threads: a 15-worker terrain export ran ~60 busy threads on 24 CPUs, each worker's cpu time 5x its
    wall time for no gain. Returns the libraries set."""
    done = []
    try:
        libs = sorted({ln.split()[-1] for ln in open("/proc/self/maps") if "openblas" in ln.lower() and ".so" in ln})
    except OSError:
        return done
    for path in libs:
        try:
            lib = ctypes.CDLL(path)
        except OSError:
            continue
        for sym in ("scipy_openblas_set_num_threads64_", "scipy_openblas_set_num_threads", "openblas_set_num_threads64_",
                    "openblas_set_num_threads"):
            if hasattr(lib, sym):
                getattr(lib, sym)(int(n))
                done.append(path)
                break
    return done


def _worker_init(n=1):
    blas_threads(n)


class MemoryGuardError(MemoryError):
    pass


@contextlib.contextmanager
def guarded(ex, name: str = "job", log=print):
    """Watch free memory while a ProcessPoolExecutor runs; if it falls under the reserve, kill the pool's workers
    and raise MemoryGuardError (a failed job instead of the kernel's OOM killer taking the user's apps). If the
    caller's tool call is cancelled (`cancel_scope`), the workers are killed too and Cancelled is raised."""
    stop, tripped, cancel = threading.Event(), [], []
    ev = current_cancel()

    def kill():
        for p in list((getattr(ex, "_processes", None) or {}).values()):
            with contextlib.suppress(Exception):
                p.kill()

    def watch():
        while not stop.wait(0.5):
            if ev is not None and ev.is_set():
                cancel.append(True)
                kill()
                with contextlib.suppress(Exception):
                    ex.shutdown(wait=False, cancel_futures=True)
                return
            m = meminfo()
            if m["available"] < 0.5 * reserve_gb():
                tripped.append(m["available"])
                kill()
                return

    th = threading.Thread(target=watch, daemon=True)
    th.start()
    try:
        with ex:
            yield ex
    except BaseException:
        stop.set()
        if cancel or (ev is not None and ev.is_set()):
            kill()
            raise Cancelled(f"{name}: cancelled, pool stopped") from None
        if tripped:
            raise MemoryGuardError(f"{name}: stopped, free memory fell to {tripped[0]:.1f} GB (reserve "
                                   f"{reserve_gb():.1f} GB); lower the workers or the resolution") from None
        raise
    finally:
        stop.set()
    if cancel:
        raise Cancelled(f"{name}: cancelled, pool stopped")
    if tripped:
        raise MemoryGuardError(f"{name}: stopped, free memory fell to {tripped[0]:.1f} GB")


def _pss_gb(pid: int) -> float:
    try:
        for ln in Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines():
            if ln.startswith("Pss:"):
                return int(ln.split()[1]) / 2**20
    except OSError:
        pass
    return 0.0


def _children(pid: int) -> list:
    out = []
    try:
        for t in os.listdir(f"/proc/{pid}/task"):
            out += [int(c) for c in Path(f"/proc/{pid}/task/{t}/children").read_text().split()]
    except OSError:
        pass
    return out


@contextlib.contextmanager
def peak_memory(every: float = 0.5):
    """Samples this process and its worker processes (PSS: shared pages split between them) while the block runs;
    yields a dict that ends up holding the peaks in GB: job (all processes), worker (the largest one), parent, and
    the machine's lowest MemAvailable. A heavy job's report should say what it used."""
    peak = {"job_gb": 0.0, "worker_gb": 0.0, "parent_gb": 0.0, "min_available_gb": meminfo()["available"]}
    stop = threading.Event()
    me = os.getpid()

    def watch():
        while not stop.wait(every):
            ps = [_pss_gb(c) for c in _children(me)]
            p0 = _pss_gb(me)
            peak["parent_gb"] = max(peak["parent_gb"], p0)
            peak["job_gb"] = max(peak["job_gb"], p0 + sum(ps))
            peak["worker_gb"] = max([peak["worker_gb"]] + ps)
            peak["min_available_gb"] = min(peak["min_available_gb"], meminfo()["available"])

    th = threading.Thread(target=watch, daemon=True)
    th.start()
    try:
        yield peak
    finally:
        stop.set()
        for k in peak:
            peak[k] = round(peak[k], 2)
