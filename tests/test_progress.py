"""Progress lines for long pooled jobs (the island's tile export was silent for 21 minutes before its first tile).
uv run python tests/test_progress.py"""
import re
import time
from concurrent.futures import ThreadPoolExecutor

from hifipushie import profiling


def _sleep(x):
    time.sleep(0.02 * (x % 3 + 1))
    return x * x


def _more(x):
    time.sleep(0.01)
    return -x


def test_pool_map_progress():
    lines = []
    rep = profiling.Report(progress=lines.append, every=0.05)
    with rep.stage("setup (parent)"):
        pass
    with ThreadPoolExecutor(4) as ex:
        got = rep.pool_map(ex, _sleep, list(range(40)), "marching cubes")
    assert got == [x * x for x in range(40)]  # (in order)
    assert lines[0].endswith("setup (parent) ...") and lines[0].startswith("[0:00]"), lines
    assert any("marching cubes: 40 jobs on 4 workers" in l for l in lines), lines
    ticks = [l for l in lines if re.search(r"marching cubes: \d+ / 40 done", l)]
    assert len(ticks) >= 3 and "40 / 40 done" in ticks[-1], ticks
    assert any("ETA" in l for l in ticks[:-1]), ticks


def test_run_jobs_progress():
    lines = []
    rep = profiling.Report(progress=lines.append, every=0.05)

    def done(fn, arg, r):
        return [(_more, arg, f"more {arg}")] if fn is _sleep else []
    with ThreadPoolExecutor(4) as ex:
        rep.run_jobs(ex, [(_sleep, i, str(i)) for i in range(20)], done, "tiles")
    last = [l for l in lines if "tiles:" in l][-1]
    assert "20 / 20 done" in last and "_more 20 done, 0 left" in last, lines


def test_no_progress_sink_is_quiet():
    rep = profiling.Report()
    with ThreadPoolExecutor(2) as ex:
        assert rep.pool_map(ex, _sleep, [1, 2, 3], "x") == [1, 4, 9]


def test_tool_takes_a_context():
    from mcp.server.mcpserver.utilities.context_injection import find_context_parameter
    from hifipushie import server
    assert find_context_parameter(server.export_terrain) == "ctx"


if __name__ == "__main__":
    test_pool_map_progress()
    test_run_jobs_progress()
    test_no_progress_sink_is_quiet()
    test_tool_takes_a_context()
    print("ok")
