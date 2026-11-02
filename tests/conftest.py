"""The suite's rails, so a run can be trusted (docs/state/test_suite.md; the gate itself is bin/suite).

- No leaks: os.environ and the cwd are put back after every test and every module, whatever the test did
  (artist.py sets HIFIPUSHIE_ASSETS; one test leaving it at a temp dir failed most of the tests after it).
- No hangs: each phase of a test (setup, call, teardown) has a time limit, stdlib only: SIGALRM raises SuiteTimeout
  in the main thread, again every 10 s if something swallows it. It is a BaseException because tool wrappers catch
  Exception. A hang inside C code never returns to Python to see the signal, so faulthandler is the backstop: past the
  limit + HARD_GRACE it prints every stack and ends the whole run (exit 1, no summary: bin/suite reports it as aborted).
  Limits: 60 s; `slow` tests 900 s; @pytest.mark.timeout(s) names its own; $HIFIPUSHIE_TEST_TIMEOUT replaces the 60.
- Two tiers: tests/slow_tests.txt lists the node ids of the slow tier (measured; see its header). A list instead of
  decorators: no churn in test files other branches are editing. pyproject's addopts deselect them, also when you name
  a file: `pytest -m "" tests/test_x.py` runs all of it.
- @pytest.mark.network skips when PyPI can't be reached (one 3 s probe per run)."""
import faulthandler
import os
import signal
import socket
from pathlib import Path

import pytest

DEFAULT_LIMIT = 60.0
SLOW_LIMIT = 900.0
HARD_GRACE = 120.0
REPEAT = 10.0
SLOW_LIST = Path(__file__).parent / "slow_tests.txt"


class SuiteTimeout(BaseException):
    """A test phase ran past its limit."""


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


class _Limit:
    """SIGALRM + the faulthandler backstop for one phase of one test. Only the main thread can take a signal."""

    def __init__(self, seconds: float, what: str):
        self.seconds, self.what = seconds, what

    def __enter__(self):
        def fire(signum, frame):
            raise SuiteTimeout(f"{self.what} ran past {self.seconds:.0f} s (tests/conftest.py)")
        self.old = signal.signal(signal.SIGALRM, fire)
        signal.setitimer(signal.ITIMER_REAL, self.seconds, REPEAT)
        faulthandler.dump_traceback_later(self.seconds + HARD_GRACE, exit=True, file=_hard_file)

    def __exit__(self, *exc):
        signal.setitimer(signal.ITIMER_REAL, 0)
        faulthandler.cancel_dump_traceback_later()
        signal.signal(signal.SIGALRM, self.old)
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
