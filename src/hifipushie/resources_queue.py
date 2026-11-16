"""The heavy-job queue: peaks measured on earlier runs (`estimate`), the jobs on disk, the plan that says who runs next, the text a waiting job prints, admission and release, and the status and queue views. Part of the machine-resources module (resources.py has the overview and every constant)."""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import random
import threading
import time
from pathlib import Path

from . import resources
from .resources import (
    Cancelled, _close_fd, _holds_gpu, _open_fd, current_cancel, heavy_budget_gb, heavy_dir, meminfo, reserve_gb,
)

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
    base = resources.KIND_GB.get(kind, resources.KIND_GB["heavy"])
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
                "name": txt[1] if len(txt) > 1 else "(old hifipushie code)", "gb": resources.LEGACY_GB, "legacy": True}
    finally:
        os.close(fd)


def _descendants(pid: int) -> list[int]:
    from . import resources_guard
    out, todo = [], [pid]
    while todo:
        c = resources_guard._children(todo.pop())
        out += c
        todo += c
    return out


def _use_gb(pid: int) -> float:
    from . import resources_guard
    return resources_guard._pss_gb(pid) + sum(resources_guard._pss_gb(c) for c in _descendants(pid))


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
            ok = fits and gb <= resources.SMALL * budget and all(b.get("passed", 0) < resources.PASS_LIMIT for b in blockers)
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
    with resources._LOCK:
        resources._SEQ[0] += 1
        seq = resources._SEQ[0]
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
            time.sleep(float(os.environ.get("HIFIPUSHIE_HEAVY_POLL", resources.POLL)) * (0.8 + 0.4 * random.random()))
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
        lines.append(f"  running (old hifipushie code, counted {resources.LEGACY_GB:.0f} GB): {s['legacy']['name']} "
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
        run.append({"kind": "unknown (older hifipushie)", "label": _label(s["legacy"]["name"]), "gb": resources.LEGACY_GB,
                    "gpu": True, "minutes": None, "yours": False})
    wait, ahead = [], 0.0
    for i, j in enumerate(s["waiting"]):
        wait.append({"position": i + 1, "kind": j.get("kind"), "label": _label(j["name"]), "gb": round(j["gb"], 1),
                     "gpu": bool(j.get("gpu")), "why": j["why"], "gb_ahead": round(ahead, 1),
                     "minutes": round((now - j.get("since", now)) / 60, 1), "yours": j.get("tag") == tag})
        ahead += j["gb"]
    return {"budget_gb": s["budget_gb"], "declared_gb": s["declared_gb"],
            "gpu": next((r["label"] for r in run if r["gpu"]), None), "running": run, "waiting": wait}


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
                     f"{', GPU' if w['gpu'] else ''}, {resources.WHY.get(w['why'], w['why'])}, {w['gb_ahead']:.0f} GB ahead, "
                     f"waited {w['minutes']:.0f} min" + ("  <- yours" if w["yours"] else ""))
    mine = [w for w in q["waiting"] if w["yours"]]
    if mine:
        w = mine[0]
        lines.append(f"yours: {_ordinal(w['position'])} in queue, {w['gb_ahead']:.0f} GB ahead "
                     f"({resources.WHY.get(w['why'], w['why'])})")
    if not q["running"] and not q["waiting"]:
        lines.append("  nothing running or waiting")
    return "\n".join(lines)
