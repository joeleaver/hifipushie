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


def meminfo() -> dict:
    """/proc/meminfo in GB ({"total", "available"})."""
    out = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            out[k] = int(v.split()[0]) / 2**20
    except OSError:
        return {"total": 16.0, "available": 8.0}
    return {"total": out.get("MemTotal", 16.0), "available": out.get("MemAvailable", 8.0)}


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
    n = min(n, max(1, (os.cpu_count() or 2) - 2))
    if cap:
        n = min(n, cap)
    if jobs:
        n = min(n, jobs)
    return max(1, n)


@contextlib.contextmanager
def heavy(name: str, log=print):
    """Hold one of the machine's heavy-job slots (a file lock shared by every process and agent) while a heavy
    job runs; waits for a free slot."""
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
    try:
        yield
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


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
