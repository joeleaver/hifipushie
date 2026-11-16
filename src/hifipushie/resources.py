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

Settings: $HIFIPUSHIE_MEM_GB caps what pools may use without a grant (default half of RAM).

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at resources.NAME: C422). resources_queue: the heavy-job queue: peaks measured on earlier runs (`estimate`),
the jobs on disk, the plan that says who runs next, the text a waiting job prints, admission and release, and the
status and queue views. resources_guard: the memory guard: `guarded` runs a pool and stops it before the machine runs
out; `peak_memory` measures a job and its children.
"""
from __future__ import annotations

import contextlib
import ctypes
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from . import moved

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
EXPORT_HUMAN_GB = 24.0  # (Garrett export v7e, 2026-10-19) a human character's export (skin bake, hair, cloth, LODs)
# peaks near this: declared lower, it was OOM-killed sharing the slice with another export. asset_budget.export_gb uses it.
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


def _holds_gpu(j: dict) -> bool:
    """Does a running job (or the old code's holder) hold the GPU? A job that says so, and any job we can't tell:
    the old code's holder of heavy0.lock and jobs of unknown kind (2026-10-07: an old-code ZOZO sim held only
    heavy0.lock, was counted as memory but not as the GPU, and a new ZOZO sim was admitted beside it: one crashed)."""
    return bool(j.get("gpu") or j.get("legacy") or j.get("kind") in (None, "heavy"))


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
    from . import resources_guard, resources_queue
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
    if gb is None and kind is None:  # (machine-memory rule, codified 2026-10-19) a heavy job states its real peak
        raise ValueError(f"heavy job {name!r}: declare its peak (gb=<real GB>) or a measured kind (kind=, one of "
                         f"{', '.join(sorted(KIND_GB))}); an undeclared job is counted at a guess and OOMs the box")
    kind = kind or "heavy"
    gb = float(resources_queue.estimate(kind, model) if gb is None else gb)
    d = heavy_dir()
    info = resources_queue._job_info(name, kind, model, min(gb, heavy_budget_gb()), gpu)
    lfd, fence, waited, _ = resources_queue._acquire(d, info, log)
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
        resources_queue._release(d, info, lfd, fence)

    job["release"] = release
    _tls.job, _tls.depth = job, 1
    stop = threading.Event()
    me = os.getpid()
    alone = _jobs_open() == 1  # this process runs no other heavy job: its memory is this job's
    base = resources_guard._pss_gb(me)
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
                peak[0] = max(peak[0], resources_queue._use_gb(me) - base)

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
                    resources_queue._record_peak(kind, model, peak[0])
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
    from . import resources_queue
    d = heavy_dir()
    info = resources_queue._job_info(name + " (GPU)", "gpu", None, 0.0, True)
    lfd, fence, waited, _ = resources_queue._acquire(d, info, log)
    try:
        yield
    finally:
        resources_queue._release(d, info, lfd, fence)


def last_wait() -> tuple | None:
    """(seconds waited, last wait message) of this thread's last heavy job, for a tool's reply."""
    return getattr(_tls, "last_wait", None)


WHY = {"memory": "waiting for memory", "gpu": "waiting for the GPU", "behind": "behind older jobs",
       "admitting": "starting"}


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


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("resources_queue", "resources_guard")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
