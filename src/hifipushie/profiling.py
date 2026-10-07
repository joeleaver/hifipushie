"""Where a heavy job's time goes: named wall-time spans and counters, per process, merged across pool workers.

    with profiling.span("bake/surface"):      # inclusive wall time + calls
        ...
    profiling.count("field.solid", len(p))  # also credited to the innermost open span: "field.solid @ bake/surface"

Workers run their jobs through `pool_map`, which resets the worker's record before each job and hands it back with
the job's start/end, so the parent can say per stage: wall time, busy share of the workers (utilisation), idle
worker-seconds, the straggler tail (the last job's end after the first worker ran out of work), and per job times.
`table` prints it. Leaf spans (`leaf=True`: the field's own evaluation) don't become the span that counts are
credited to, so "field.solid @ bake/surface" says which stage asked for the evaluations.

HIFIPUSHIE_CPROFILE=<dir>: every pooled job also runs under cProfile and dumps <dir>/<stage>_<n>.prof (merge them with
`cprofile_top`)."""
from __future__ import annotations

import contextlib
import os
import time

_S: dict = {}  # span -> [seconds, calls]
_C: dict = {}  # counter -> n
_STACK: list = []


def reset():
    _S.clear()
    _C.clear()
    _STACK.clear()


@contextlib.contextmanager
def span(name, leaf=False):
    if not leaf:
        _STACK.append(name)
    t = time.perf_counter()
    try:
        yield
    finally:
        s = _S.setdefault(name, [0.0, 0])
        s[0] += time.perf_counter() - t
        s[1] += 1
        if not leaf:
            _STACK.pop()


def timed(name, leaf=False):
    """Decorator form of `span`."""
    def deco(fn):
        def f(*a, **k):
            with span(name, leaf):
                return fn(*a, **k)
        f.__wrapped__, f.__name__, f.__doc__ = fn, fn.__name__, fn.__doc__
        return f
    return deco


def count(name, n=1):
    _C[name] = _C.get(name, 0) + int(n)
    if _STACK:
        k = f"{name} @ {_STACK[-1]}"
        _C[k] = _C.get(k, 0) + int(n)


def snapshot(reset_after=False) -> dict:
    out = {"spans": {k: list(v) for k, v in _S.items()}, "counts": dict(_C)}
    if reset_after:
        reset()
    return out


def merge(dst: dict, src: dict) -> dict:
    for k, (s, n) in src.get("spans", {}).items():
        d = dst.setdefault("spans", {}).setdefault(k, [0.0, 0])
        d[0] += s
        d[1] += n
    for k, n in src.get("counts", {}).items():
        dst.setdefault("counts", {})[k] = dst.setdefault("counts", {}).get(k, 0) + n
    return dst


def _call(args):
    """Runs one pooled job in a worker: its record reset first, returned with its start/end."""
    fn, item, stage, n = args
    reset()
    t0 = time.time()
    prof_dir = os.environ.get("HIFIPUSHIE_CPROFILE")
    if prof_dir:
        import cProfile
        pr = cProfile.Profile()
        r = pr.runcall(fn, item)
        os.makedirs(prof_dir, exist_ok=True)
        pr.dump_stats(os.path.join(prof_dir, f"{stage.replace(' ', '_').replace('/', '_')}_{n}.prof"))
    else:
        r = fn(item)
    return r, snapshot(), t0, time.time(), os.getpid()


class Report:
    """The whole job's record: stages (pool maps and serial parent steps) in order, plus merged worker spans."""

    def __init__(self):
        self.stages = []  # dicts
        self.workers = {}  # stage -> merged spans/counts of its pooled jobs
        self.parent0 = None
        reset()

    @contextlib.contextmanager
    def stage(self, name):
        """A serial step in the parent (its own spans go into the parent's record)."""
        t = time.time()
        try:
            yield
        finally:
            self.stages.append({"stage": name, "wall_s": round(time.time() - t, 2), "workers": 1})

    def pool_map(self, ex, fn, items, stage, key=None):
        """ex.map(fn, items) with each job timed in its worker; returns the results in order."""
        items = list(items)
        t = time.time()
        res, jobs = [], []
        for idx, (r, snap, t0, t1, pid) in enumerate(ex.map(_call, [(fn, it, stage, m) for m, it in enumerate(items)])):
            res.append(r)
            if idx % 16 == 0:
                from .resources import check_cancel
                check_cancel(stage)
            merge(self.workers.setdefault(stage, {}), snap)
            jobs.append((t0, t1, key(items[idx]) if key else idx))
        self._record(stage, time.time() - t, getattr(ex, "_max_workers", 1), jobs)
        return res

    def run_jobs(self, ex, jobs, on_done, stage):
        """Jobs that make more jobs, on one pool: jobs = [(fn, arg, label)]; on_done(fn, arg, result) returns the jobs
        it unlocks (a tile's bake pieces once the tile is meshed, its GLB once its pieces are baked), so no stage
        waits on another's stragglers. Timed per job; one record for the whole and one per job function."""
        from concurrent.futures import FIRST_COMPLETED, wait
        t = time.time()
        n = getattr(ex, "_max_workers", 1)
        per_fn, pending, count = {}, {}, [0]

        def go(fn, arg, label):
            f = ex.submit(_call, (fn, arg, f"{stage}: {fn.__name__}", count[0]))
            pending[f] = (fn, arg, label)
            count[0] += 1
        for j in jobs:
            go(*j)
        from .resources import check_cancel
        while pending:
            done, _ = wait(list(pending), return_when=FIRST_COMPLETED, timeout=1.0)
            check_cancel(stage)  # a cancelled tool call stops here (its guarded pool is killed too)
            for f in done:
                fn, arg, label = pending.pop(f)
                r, snap, t0, t1, pid = f.result()
                name = f"{stage}: {fn.__name__}"
                merge(self.workers.setdefault(name, {}), snap)
                per_fn.setdefault(name, []).append((t0, t1, label))
                for j in on_done(fn, arg, r) or ():
                    go(*j)
        wall = time.time() - t
        self._record(stage, wall, n, [j for js in per_fn.values() for j in js])
        for name, js in per_fn.items():  # (each job function's share of the same wall)
            self._record("  " + name.split(": ", 1)[1], wall, n, js)

    def _record(self, stage, wall, n, jobs):
        busy = sum(b - a for a, b, _ in jobs)
        ends = sorted(b for _, b, _ in jobs)
        # the straggler tail: from when a worker first had nothing left to do (the (n-1)-th last job end, once all
        # jobs are handed out) to the end
        tail = (ends[-1] - ends[-min(n, len(ends))]) if len(ends) > 1 else 0.0
        per = sorted(((b - a), str(lab)) for a, b, lab in jobs)
        rec = {"stage": stage, "wall_s": round(wall, 2), "workers": n, "jobs": len(jobs),
               "busy_s": round(busy, 2), "utilisation": round(busy / max(wall * n, 1e-9), 3),
               "idle_worker_s": round(max(wall * n - busy, 0.0), 1), "tail_s": round(tail, 2),
               "job_max_s": round(per[-1][0], 2) if per else 0.0,
               "job_median_s": round(per[len(per) // 2][0], 2) if per else 0.0}
        if per:
            rec["slowest"] = [[lab, round(d, 2)] for d, lab in per[::-1][:5]]
        if stage.startswith("  "):
            rec["part_of_above"] = True
        self.stages.append(rec)

    def as_dict(self) -> dict:
        par = snapshot()
        rnd = lambda sp: {k: [round(s, 2), n] for k, (s, n) in sorted(sp.items(), key=lambda kv: -kv[1][0])}
        return {"stages": self.stages,
                "worker_spans": {st: rnd(w.get("spans", {})) for st, w in self.workers.items()},
                "worker_counts": {st: dict(sorted(w.get("counts", {}).items(), key=lambda kv: -kv[1]))
                                  for st, w in self.workers.items()},
                "parent_spans": {k: [round(s, 2), n] for k, (s, n) in sorted(par["spans"].items(),
                                                                               key=lambda kv: -kv[1][0])},
                "parent_counts": dict(sorted(par["counts"].items(), key=lambda kv: -kv[1]))}


def table(d: dict, top=40) -> str:
    """A text table of `Report.as_dict()`."""
    L = [f"{'stage':38s} {'wall s':>8s} {'workers':>7s} {'jobs':>5s} {'busy s':>9s} {'util':>5s} {'tail s':>7s} "
         f"{'max job':>8s} {'median':>7s}"]
    tot = sum(s["wall_s"] for s in d["stages"] if not s.get("part_of_above"))
    for s in d["stages"]:
        L.append(f"{s['stage'][:38]:38s} {s['wall_s']:8.1f} {s['workers']:7d} {s.get('jobs', 1):5d} "
                 f"{s.get('busy_s', s['wall_s']):9.1f} {s.get('utilisation', 1.0):5.2f} {s.get('tail_s', 0):7.1f} "
                 f"{s.get('job_max_s', s['wall_s']):8.1f} {s.get('job_median_s', s['wall_s']):7.1f}")
        if s.get("slowest"):
            L.append(f"{'':40s}slowest: " + ", ".join(f"{k} {v:.0f}s" for k, v in s["slowest"]))
    L.append(f"{'sum of stages':38s} {tot:8.1f}")
    blocks = [(f"workers, {st} (spans summed over its jobs, inclusive)", sp, d["worker_counts"].get(st, {}))
              for st, sp in d["worker_spans"].items()] + [("parent", d["parent_spans"], d["parent_counts"])]
    for title, sp, cn in blocks:
        if not sp and not cn:
            continue
        L.append(f"\n{title}:")
        for k, (s, n) in list(sp.items())[:top]:
            if s >= 0.05:
                L.append(f"  {k[:60]:60s} {s:10.1f} s {n:8d} calls")
        for k, n in list(cn.items())[:top]:
            L.append(f"  {k[:60]:60s} {n:16,d}")
    return "\n".join(L)


def cprofile_top(prof_dir, pattern="*.prof", n=30, sort="tottime") -> str:
    """The merged cProfile of every dump matching `pattern` in prof_dir, top n by `sort`."""
    import glob
    import io
    import pstats
    files = sorted(glob.glob(os.path.join(prof_dir, pattern)))
    if not files:
        return "(no profiles)"
    buf = io.StringIO()
    st = pstats.Stats(files[0], stream=buf)
    for f in files[1:]:
        st.add(f)
    st.strip_dirs().sort_stats(sort).print_stats(n)
    return buf.getvalue()
