"""The machine-wide heavy-job queue (`resources.heavy`): admission by memory budget in FIFO order, small jobs passing a
blocked one a bounded number of times, one GPU job at a time, dead owners swept, cancellation releasing the grant,
pool workers not holding the state files, the old code's slot respected. Every test runs in its own state dir
($HIFIPUSHIE_HEAVY_DIR) with a 10 GB budget: never the real queue. Fast (~1 min), several processes.

    uv run pytest tests/test_heavy.py -q"""
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from hifipushie import resources

JOB = Path(__file__).with_name("heavy_job.py")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HIFIPUSHIE_HEAVY_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HIFIPUSHIE_HEAVY_GB", "10")
    monkeypatch.setenv("HIFIPUSHIE_HEAVY_FREECHECK", "0")
    monkeypatch.setenv("HIFIPUSHIE_HEAVY_POLL", "0.1")
    monkeypatch.setenv("HIFIPUSHIE_HEAVY_PEAKS", str(tmp_path / "peaks.json"))
    monkeypatch.delenv("HIFIPUSHIE_HEAVY_SLOTS", raising=False)
    procs = []

    class E:
        dir = tmp_path
        events = tmp_path / "events"

        def start(self, name, gb, gpu=False, fork=False):
            args = [sys.executable, str(JOB), name, str(gb), "1" if gpu else "0", str(self.events)]
            p = subprocess.Popen(args + (["fork"] if fork else []), env=dict(os.environ))
            procs.append(p)
            return p

        def release(self, name):
            (tmp_path / f"release_{name}").touch()

        def started(self):
            return [ln.split()[1] for ln in self.lines() if ln.startswith("start")]

        def lines(self):
            return self.events.read_text().splitlines() if self.events.exists() else []

        def wait(self, cond, what, timeout=20):
            t = time.time()
            while time.time() - t < timeout:
                if cond():
                    return
                time.sleep(0.05)
            raise AssertionError(f"timed out waiting for {what}: {resources.status_text()}")

        def waiting(self):
            return [j["name"] for j in resources.status()["waiting"]]

        def running(self):
            return [j["name"] for j in resources.status()["running"]]

    yield E()
    for p in procs:
        if p.poll() is None:
            p.kill()
            p.wait()


def test_fifo_order(env):
    env.start("H", 6)
    env.wait(lambda: "H" in env.started(), "H to start")
    for n in "ABC":  # each 6 GB: one at a time, in the order they queued
        env.start(n, 6)
        env.wait(lambda: n in env.waiting(), f"{n} to queue")
    assert env.waiting() == ["A", "B", "C"]
    for n in "HAB":
        env.release(n)
        nxt = "ABC"["HAB".index(n)]
        env.wait(lambda: nxt in env.started(), f"{nxt} to start")
    env.release("C")
    env.wait(lambda: len([ln for ln in env.lines() if ln.startswith("end")]) == 4, "all to end")
    assert env.started() == ["H", "A", "B", "C"]
    t = {ln.split()[0] + ln.split()[1]: float(ln.split()[2]) for ln in env.lines()}
    for a, b in ("HA", "AB", "BC"):
        assert t["end" + a] <= t["start" + b]  # never two 6 GB jobs at once in 10 GB
    assert "waiting for memory" in (env.dir / "log_A").read_text()
    assert "held by H" in (env.dir / "log_A").read_text()


def test_jobs_that_fit_run_together(env):
    env.start("A", 4)
    env.start("B", 4)
    env.wait(lambda: set(env.started()) == {"A", "B"}, "both to run at once")
    s = resources.status()
    assert s["declared_gb"] == 8 and not s["waiting"]
    env.release("A"), env.release("B")


def test_small_jobs_pass_a_blocked_job_a_bounded_number_of_times(env):
    env.start("H", 6)
    env.wait(lambda: "H" in env.started(), "H")
    env.start("Big", 8)
    env.wait(lambda: "Big" in env.waiting(), "Big to queue")
    for i in range(resources.PASS_LIMIT):  # small (1 GB <= 25% of 10) and fits beside H: passes Big
        n = f"S{i}"
        env.release(n)  # (finishes as soon as it starts)
        env.start(n, 1)
        env.wait(lambda: any(ln.startswith(f"end {n}") for ln in env.lines()), f"{n} to pass and finish")
    env.release("Last")
    env.start("Last", 1)
    env.wait(lambda: "Last" in env.waiting(), "Last to queue")
    time.sleep(1.0)
    assert "Last" not in env.started()  # Big has been passed PASS_LIMIT times: nothing passes it now
    s = {j["name"]: j for j in resources.status()["waiting"]}
    assert s["Big"]["passed"] == resources.PASS_LIMIT and s["Last"]["why"] == "behind"
    env.release("H")
    env.wait(lambda: {"Big", "Last"} <= set(env.started()), "Big, and Last beside it, once H is done")
    env.release("Big")


def test_one_gpu_job_at_a_time(env):
    env.start("G1", 1, gpu=True)
    env.wait(lambda: "G1" in env.started(), "G1")
    env.start("G2", 1, gpu=True)
    env.wait(lambda: "G2" in env.waiting(), "G2 to wait")
    env.start("N", 1)
    env.wait(lambda: "N" in env.started(), "a CPU job beside the GPU job")
    assert resources.status()["waiting"][0]["why"] == "gpu"
    assert "waiting for the GPU" in (env.dir / "log_G2").read_text()
    env.release("G1")
    env.wait(lambda: "G2" in env.started(), "G2 after G1")
    env.release("G2"), env.release("N")


def test_dead_holder_and_dead_waiter_are_swept(env):
    h = env.start("H", 8)
    env.wait(lambda: "H" in env.started(), "H")
    w = env.start("W", 8)
    env.wait(lambda: "W" in env.waiting(), "W")
    x = env.start("X", 8)
    env.wait(lambda: "X" in env.waiting(), "X")
    w.send_signal(signal.SIGKILL), w.wait()
    env.wait(lambda: env.waiting() == ["X"], "the dead waiter swept")
    h.send_signal(signal.SIGKILL), h.wait()
    env.wait(lambda: "X" in env.started(), "X after the holder was killed")
    env.release("X")


def test_pool_workers_hold_no_state_and_killing_the_parent_frees_it(env):
    p = env.start("F", 8, fork=True)
    env.wait(lambda: (env.dir / "pids_F").exists(), "the pool's pids")
    state = str(env.dir / "state")
    pids = [int(x) for x in (env.dir / "pids_F").read_text().split()]
    for pid in pids:
        fds = os.listdir(f"/proc/{pid}/fd")
        targets = [os.readlink(f"/proc/{pid}/fd/{f}") for f in fds if os.path.exists(f"/proc/{pid}/fd/{f}")]
        assert not [t for t in targets if t.startswith(state)], f"worker {pid} holds {targets}"
    env.start("Next", 8)
    env.wait(lambda: "Next" in env.waiting(), "Next")
    p.send_signal(signal.SIGKILL), p.wait()  # its workers may live on a moment: they mustn't keep the grant
    env.wait(lambda: "Next" in env.started(), "Next once the parent is dead", timeout=10)
    env.release("Next")


def test_cancel_while_running_kills_the_pool_and_releases(env):
    from concurrent.futures import ProcessPoolExecutor
    from multiprocessing import get_context
    ev, out = threading.Event(), {}

    def job():
        with resources.cancel_scope(ev):
            try:
                with resources.heavy("cancelme", gb=1, kind="test", log=lambda m: None):
                    ex = ProcessPoolExecutor(1, mp_context=get_context("fork"))
                    with resources.guarded(ex, "test pool") as ex:
                        f = ex.submit(time.sleep, 60)
                        out["pid"] = next(iter(ex._processes))
                        f.result()
                out["r"] = "finished"
            except resources.Cancelled as e:
                out["r"] = f"cancelled: {e}"

    th = threading.Thread(target=job)
    th.start()
    env.wait(lambda: "cancelme" in env.running() and "pid" in out, "the job to run")
    t = time.time()
    ev.set()
    th.join(15)
    assert not th.is_alive() and out["r"].startswith("cancelled"), out
    assert time.time() - t < 10
    assert not env.running()
    time.sleep(0.5)
    assert not os.path.exists(f"/proc/{out['pid']}") or "Z" in Path(f"/proc/{out['pid']}/stat").read_text().split()[2]


def test_cancel_while_running_a_plain_loop(env):
    ev, out = threading.Event(), {}

    def job():
        with resources.cancel_scope(ev):
            try:
                with resources.heavy("loop", gb=1, kind="test", log=lambda m: None):
                    while True:
                        time.sleep(0.01)  # (no cancel checks at all: Cancelled is raised in this thread)
            except resources.Cancelled:
                out["r"] = "cancelled"

    th = threading.Thread(target=job)
    th.start()
    env.wait(lambda: "loop" in env.running(), "loop")
    ev.set()
    th.join(10)
    assert out.get("r") == "cancelled" and not env.running()


def test_cancel_while_waiting_leaves_the_queue(env):
    env.start("H", 8)
    env.wait(lambda: "H" in env.started(), "H")
    ev, out = threading.Event(), {}

    def job():
        with resources.cancel_scope(ev):
            try:
                with resources.heavy("waiter", gb=8, kind="test", log=lambda m: None):
                    out["r"] = "ran"
            except resources.Cancelled:
                out["r"] = "cancelled"

    th = threading.Thread(target=job)
    th.start()
    env.wait(lambda: "waiter" in env.waiting(), "waiter to queue")
    ev.set()
    th.join(5)
    assert out.get("r") == "cancelled" and not env.waiting()
    env.release("H")


def test_old_code_slot_is_respected_both_ways(env):
    import fcntl
    lock = env.dir / "state" / "heavy0.lock"
    resources.heavy_dir()
    old = subprocess.Popen([sys.executable, "-c", (
        "import fcntl,sys,time; f=open(sys.argv[1],'a+'); fcntl.flock(f,fcntl.LOCK_EX); f.seek(0); f.truncate();"
        "f.write('424242 old export\\n'); f.flush(); time.sleep(60)"), str(lock)])
    try:
        env.wait(lambda: resources.status()["legacy"] is not None, "the old job to show")
        env.start("New", 1)  # 12 GB counted for the old job > the 10 GB budget: waits
        env.wait(lambda: "New" in env.waiting(), "New to wait behind the old job")
        assert "old hifipushie code" in resources.status_text()
    finally:
        old.kill(), old.wait()
    env.wait(lambda: "New" in env.started(), "New after the old job")
    with open(lock, "a+") as fh:  # the old code's LOCK_EX can't be had while a new job runs
        with pytest.raises(BlockingIOError):
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    env.release("New")


def test_old_code_holder_holds_the_gpu(env, monkeypatch):
    """An old-code job holding heavy0.lock may be a ZOZO sim: a GPU job waits for it even when memory fits; a CPU job
    beside it still runs (2026-10-07: two ZOZO sims on the GPU at once, one crashed)."""
    monkeypatch.setenv("HIFIPUSHIE_HEAVY_GB", "40")  # the old job's 12 GB + both new jobs fit in memory
    lock = env.dir / "state" / "heavy0.lock"
    resources.heavy_dir()
    old = subprocess.Popen([sys.executable, "-c", (
        "import fcntl,sys,time; f=open(sys.argv[1],'a+'); fcntl.flock(f,fcntl.LOCK_EX); f.seek(0); f.truncate();"
        "f.write('424242 zozo cloth su_41\\n'); f.flush(); time.sleep(60)"), str(lock)])
    try:
        env.wait(lambda: resources.status()["legacy"] is not None, "the old job to show")
        env.start("Gpu", 2, gpu=True)
        env.wait(lambda: "Gpu" in env.waiting(), "the GPU job to wait")
        env.start("Cpu", 2)
        env.wait(lambda: "Cpu" in env.started(), "a CPU job beside the old one")
        assert resources.status()["waiting"][0]["why"] == "gpu"
        assert "GPU: zozo cloth su_41" in resources.status_text()
        env.wait(lambda: (env.dir / "log_Gpu").exists() and "waiting for the GPU" in (env.dir / "log_Gpu").read_text()
                 and "zozo cloth su_41" in (env.dir / "log_Gpu").read_text(), "the wait to name the old job")
        assert "Gpu" not in env.started()
    finally:
        old.kill(), old.wait()
    env.wait(lambda: "Gpu" in env.started(), "the GPU job once the old one is gone")
    env.release("Gpu"), env.release("Cpu")


def test_unknown_kind_holds_the_gpu(env):
    ev = threading.Event()

    def hold():
        with resources.heavy("mystery job", gb=1, log=lambda m: None):  # no kind: could be anything
            ev.wait(20)

    th = threading.Thread(target=hold)
    th.start()
    try:
        env.wait(lambda: "mystery job" in env.running(), "the unknown job to run")
        env.start("Gpu", 1, gpu=True)
        env.wait(lambda: "Gpu" in env.waiting(), "the GPU job to wait")
        time.sleep(0.5)
        assert "Gpu" not in env.started() and resources.status()["waiting"][0]["why"] == "gpu"
    finally:
        ev.set()
        th.join(10)
    env.wait(lambda: "Gpu" in env.started(), "the GPU job after it")
    env.release("Gpu")


def test_workers_sized_from_the_grant(env, monkeypatch):
    with resources.heavy("sized", gb=3, kind="test", log=lambda m: None):
        assert resources.granted_gb() == 3
        assert resources.workers(1.0) <= 2
    assert resources.granted_gb() is None


def test_estimates_only_rise(env):
    base = resources.KIND_GB["export_asset"]
    assert resources.estimate("export_asset", "x") == base
    resources._record_peak("export_asset", "big", base + 3)
    resources._record_peak("export_asset", "small", 0.5)
    assert resources.estimate("export_asset", "big") == base + 3
    assert resources.estimate("export_asset", "small") == base


def test_server_cancel_sets_the_event(env):
    import anyio
    from hifipushie import server
    seen = {}

    def register_capture(*a, **k):
        def reg(fn):
            seen["run"] = fn
        return reg

    def slow_tool():
        t = time.time()
        while time.time() - t < 10:
            if resources.cancelled():
                seen["cancelled"] = True
                return
            time.sleep(0.02)

    server._tool_with_errors(register_capture)()(slow_tool)

    async def go():
        with anyio.move_on_after(0.3):
            await seen["run"]()
    anyio.run(go)
    t = time.time()
    while "cancelled" not in seen and time.time() - t < 5:
        time.sleep(0.02)
    assert seen.get("cancelled")


def test_nested_heavy_passes_through(env):
    with resources.heavy("outer", gb=6, kind="test", log=lambda m: None):
        with resources.heavy("inner", gb=6, kind="test", log=lambda m: None):  # would deadlock if it queued
            assert len(resources.status()["running"]) == 1
