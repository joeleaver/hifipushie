"""The suite's rails, so a run can be trusted (docs/state/test_suite.md; the gate itself is bin/suite).

- No leaks: os.environ and the cwd are put back after every test and every module, whatever the test did
  (artist.py sets HIFIPUSHIE_ASSETS; one test leaving it at a temp dir failed most of the tests after it).
- No hangs: each phase of a test (setup, call, teardown) has a time limit, stdlib only: SIGALRM raises SuiteTimeout
  in the main thread, again every 10 s if something swallows it. A hang inside C code never returns to Python to see the signal, so faulthandler is the backstop: past
  3 x the limit + 120 s it prints every stack and ends the whole run (exit 1, no summary: bin/suite reports it aborted).
  Limits: 60 s; `slow` tests 900 s; @pytest.mark.timeout(s) names its own; $HIFIPUSHIE_TEST_TIMEOUT replaces the 60.
  They are limits on time the test had a CPU (_Limit). $HIFIPUSHIE_TEST_CPULOG appends each phase's CPU seconds to a
  file: that is the measure for tests/slow_tests.txt, wall time under load isn't.
- Two tiers: tests/slow_tests.txt lists the node ids of the slow tier (measured; see its header). A list instead of
  decorators: no churn in test files other branches are editing. pyproject's addopts deselect them, also when you name
  a file: `pytest -m "" tests/test_x.py` runs all of it.
- @pytest.mark.network skips when PyPI can't be reached (one 3 s probe per run)."""
import faulthandler
import os
import signal
import socket
import subprocess
import time
from pathlib import Path

import pytest

# A worktree has no workspace/_templates: the third-party packs from the main checkout's, unless the run names its own.
def _main_checkout() -> Path:
    git = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], capture_output=True,
                         text=True, cwd=Path(__file__).parent)
    return Path(git.stdout.strip()).parent if git.returncode == 0 else Path(__file__).parent.parent


ASSETS = _main_checkout() / "workspace" / "_templates"
if not os.environ.get("HIFIPUSHIE_ASSETS") and ASSETS.is_dir():
    os.environ["HIFIPUSHIE_ASSETS"] = str(ASSETS)

DEFAULT_LIMIT = 60.0
SLOW_LIMIT = 900.0
HARD_FACTOR = 3.0
HARD_GRACE = 120.0
REPEAT = 10.0
SLOW_LIST = Path(__file__).parent / "slow_tests.txt"


class SuiteTimeout(pytest.fail.Exception):
    """A test phase ran past its limit. pytest's own Failed: not an Exception, so no tool wrapper eats it, and pytest's
    setup bookkeeping handles it (a plain BaseException in a fixture left SetupState broken: false errors after it)."""


# -- no leaks -------------------------------------------------------------------------------------------------------
def _put_back(env: dict, cwd: str) -> None:
    for k in set(os.environ) - set(env):
        del os.environ[k]
    for k, v in env.items():
        if os.environ.get(k) != v:
            os.environ[k] = v
    try:
        if os.getcwd() == cwd:
            return
    except OSError:  # (the test chdir'd into a temp dir that is gone now)
        pass
    os.chdir(cwd)


@pytest.fixture(autouse=True, scope="module")
def _module_restores_state():
    """Outside every module-scoped fixture: what they set stays for the module, and ends with it."""
    env, cwd = dict(os.environ), os.getcwd()
    yield
    _put_back(env, cwd)


@pytest.fixture(autouse=True)
def _test_restores_state():
    env, cwd = dict(os.environ), os.getcwd()
    yield
    _put_back(env, cwd)


# -- two tiers ------------------------------------------------------------------------------------------------------
def _slow_ids() -> set:
    if not SLOW_LIST.exists():
        return set()
    lines = (ln.split("#")[0].strip() for ln in SLOW_LIST.read_text().splitlines())
    return {ln for ln in lines if ln}


def pytest_collection_modifyitems(config, items):
    slow = _slow_ids()
    for item in items:
        # (a parametrized test is listed by its bare name: all its cases are one cost class)
        if item.nodeid in slow or item.nodeid.split("[")[0] in slow:
            item.add_marker(pytest.mark.slow)


# -- no hangs -------------------------------------------------------------------------------------------------------
_hard_file = None


def pytest_configure(config):
    """The real stderr, for the backstop's stacks: under pytest's capture fd 2 is a temp file nobody reads."""
    global _hard_file
    capman = config.pluginmanager.getplugin("capturemanager")
    if capman is None:
        _hard_file = os.fdopen(os.dup(2), "w")
        return
    with capman.global_and_fixture_disabled():
        _hard_file = os.fdopen(os.dup(2), "w")


def _limit(item) -> float:
    m = item.get_closest_marker("timeout")
    if m is not None and m.args:
        return float(m.args[0])
    if item.get_closest_marker("slow") is not None:
        return SLOW_LIMIT
    return float(os.environ.get("HIFIPUSHIE_TEST_TIMEOUT") or DEFAULT_LIMIT)


def _run_delay() -> float:
    """Seconds this thread has been runnable but waiting for a CPU."""
    try:
        return float(Path("/proc/self/schedstat").read_text().split()[1]) / 1e9
    except (OSError, IndexError, ValueError):
        return 0.0


def _cpu() -> float:
    t = os.times()
    return t.user + t.system + t.children_user + t.children_system


class _Limit:
    """SIGALRM + the faulthandler backstop for one phase of one test. Only the main thread can take a signal.
    The limit is on time the test had the machine: on a loaded laptop (load 120, the slice's CPU weight 20: 5 % of a
    core seen) wall time means nothing, so the limit scales with the load average and time spent waiting for a CPU
    isn't charged. A real hang waits on a lock, not for a CPU, so it is still caught."""

    def __init__(self, seconds: float, what: str):
        load = os.getloadavg()[0] / (os.cpu_count() or 1)
        self.seconds, self.what = seconds * min(max(load, 1.0), 10.0), what
        self.limit = seconds

    def _arm(self, seconds: float) -> None:
        signal.setitimer(signal.ITIMER_REAL, seconds, REPEAT)
        faulthandler.dump_traceback_later(HARD_FACTOR * seconds + HARD_GRACE, exit=True, file=_hard_file)

    def __enter__(self):
        def fire(signum, frame):
            spent = time.monotonic() - self.t0 - (_run_delay() - self.d0)
            if spent < self.seconds:
                self._arm(self.seconds - spent + 0.1)
                return
            raise SuiteTimeout(f"{self.what} ran past its {self.limit:.0f} s (tests/conftest.py)")
        self.old = signal.signal(signal.SIGALRM, fire)
        self.t0, self.d0, self.c0 = time.monotonic(), _run_delay(), _cpu()
        self._arm(self.seconds)

    def __exit__(self, *exc):
        signal.setitimer(signal.ITIMER_REAL, 0)
        faulthandler.cancel_dump_traceback_later()
        signal.signal(signal.SIGALRM, self.old)
        log = os.environ.get("HIFIPUSHIE_TEST_CPULOG")
        if log:
            with open(log, "a") as fh:
                fh.write(f"{_cpu() - self.c0:.2f} {time.monotonic() - self.t0:.2f} "
                         f"{'T' if exc[0] is SuiteTimeout else '-'} {self.what}\n")
        return False


def _phase(item, name):
    return _Limit(_limit(item), f"{item.nodeid} ({name})")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    with _phase(item, "setup"):
        return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    with _phase(item, "call"):
        return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item):
    with _phase(item, "teardown"):
        return (yield)


# -- network --------------------------------------------------------------------------------------------------------
_online = None


def online() -> bool:
    global _online
    if _online is None:
        try:
            socket.create_connection(("pypi.org", 443), timeout=3).close()
            _online = True
        except OSError:
            _online = False
    return _online


@pytest.fixture(autouse=True)
def _network_skips_offline(request):
    if request.node.get_closest_marker("network") is not None and not online():
        pytest.skip("offline: PyPI unreachable")
