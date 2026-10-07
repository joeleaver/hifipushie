"""Machine resources for heavy jobs: worker counts sized by free memory, a cross-process lock so heavy jobs
(tiled terrain exports, asset exports) run one at a time on the machine, and a memory guard that stops a pool
before the desktop runs out (2026-09-29: two terrain exports with 16 x ~2 GB workers plus other agents' jobs
OOM-killed the user's session twice).

Settings: $HIFIPUSHIE_MEM_GB caps what heavy jobs may use (default half of RAM); $HIFIPUSHIE_HEAVY_SLOTS is how
many heavy jobs may run at once (default 1)."""
from __future__ import annotations

import contextlib
import fcntl
import os
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
    """How many worker processes of ~per_worker_gb fit in the memory budget now (at least 1)."""
    n = int(budget_gb() // max(per_worker_gb, 0.1))
    n = min(n, max(1, cpus() - 2))
    if cap:
        n = min(n, cap)
    if jobs:
        n = min(n, jobs)
    return max(1, n)


_HEAVY_DEPTH = 0


@contextlib.contextmanager
def heavy(name: str, log=print):
    """Hold one of the machine's heavy-job slots (a file lock shared by every process and agent) while a heavy
    job runs; waits for a free slot."""
    global _HEAVY_DEPTH
    if _HEAVY_DEPTH > 0:  # this process holds a slot already (a batch of looks under one wait): no second one
        _HEAVY_DEPTH += 1
        try:
            yield
        finally:
            _HEAVY_DEPTH -= 1
        return
    slots = max(1, int(os.environ.get("HIFIPUSHIE_HEAVY_SLOTS", 1)))
    d = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "hifipushie"
    d.mkdir(parents=True, exist_ok=True)
    t0, waited, f = time.time(), False, None
    while f is None:
        for i in range(slots):
            fh = open(d / f"heavy{i}.lock", "a+")
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fh.seek(0), fh.truncate(), fh.write(f"{os.getpid()} {name}\n"), fh.flush()
                f = fh
                break
            except BlockingIOError:
                fh.close()
        if f is None:
            if not waited:
                log(f"{name}: waiting for another heavy job to finish (memory)")
                waited = True
            time.sleep(2)
    if waited:
        log(f"{name}: started after {time.time() - t0:.0f} s wait")
    _HEAVY_DEPTH = 1
    try:
        yield
    finally:
        _HEAVY_DEPTH = 0
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def blas_threads(n: int = 1) -> list:
    """Set the thread count of every OpenBLAS already loaded in this process (numpy's and scipy's copies), e.g. in a
    pool worker: forked workers inherit the parent's 4 BLAS threads, and every small matmul (points @ a 3x3 rotation)
    then spun 4 threads: a 15-worker terrain export ran ~60 busy threads on 24 CPUs, each worker's cpu time 5x its
    wall time for no gain. Returns the libraries set."""
    import ctypes
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
    and raise MemoryGuardError (a failed job instead of the kernel's OOM killer taking the user's apps)."""
    stop, tripped = threading.Event(), []

    def watch():
        while not stop.wait(0.5):
            m = meminfo()
            if m["available"] < 0.5 * reserve_gb():
                tripped.append(m["available"])
                for p in list(getattr(ex, "_processes", {}).values()):
                    with contextlib.suppress(Exception):
                        p.kill()
                return

    th = threading.Thread(target=watch, daemon=True)
    th.start()
    try:
        with ex:
            yield ex
    except Exception:
        if tripped:
            raise MemoryGuardError(f"{name}: stopped, free memory fell to {tripped[0]:.1f} GB (reserve "
                                   f"{reserve_gb():.1f} GB); lower the workers or the resolution") from None
        raise
    finally:
        stop.set()
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
