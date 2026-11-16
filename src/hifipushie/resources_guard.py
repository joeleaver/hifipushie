"""The memory guard: `guarded` runs a pool and stops it before the machine runs out; `peak_memory` measures a job and its children. Part of the machine-resources module (resources.py has the overview and every constant)."""
from __future__ import annotations

import contextlib
import os
import threading
from pathlib import Path

from .resources import Cancelled, current_cancel, meminfo, reserve_gb

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
