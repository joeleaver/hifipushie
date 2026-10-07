"""A stand-in heavy job for tests/test_heavy.py, run as its own process:
    heavy_job.py NAME GB GPU(0|1) EVENTS_FILE [fork]
Takes `resources.heavy` (the test's state dir comes from $HIFIPUSHIE_HEAVY_DIR), appends "start NAME t" to
EVENTS_FILE, holds until <EVENTS_FILE dir>/release_NAME exists, appends "end NAME t". With "fork": starts a fork
pool of 2 workers inside the job and writes their pids to <dir>/pids_NAME first."""
import fcntl
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path

from hifipushie import resources


def note(path, text):
    with open(path, "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.write(f"{text} {time.time():.4f}\n")


def _sleep(s):
    time.sleep(s)
    return os.getpid()


def main():
    name, gb, gpu, events = sys.argv[1], float(sys.argv[2]), sys.argv[3] == "1", Path(sys.argv[4])
    fork = len(sys.argv) > 5 and sys.argv[5] == "fork"
    with resources.heavy(name, log=lambda m: note(events.parent / f"log_{name}", m), gb=gb, gpu=gpu, kind="test"):
        note(events, f"start {name}")
        ex = None
        if fork:
            ex = ProcessPoolExecutor(2, mp_context=get_context("fork"))
            futs = [ex.submit(_sleep, 0.2) for _ in range(2)]
            pids = sorted({p.pid for p in ex._processes.values()})
            [f.result() for f in futs]
            (events.parent / f"pids_{name}").write_text(" ".join(map(str, pids)))
        rel = events.parent / f"release_{name}"
        while not rel.exists():
            time.sleep(0.05)
        note(events, f"end {name}")
        if ex is not None:
            ex.shutdown()


if __name__ == "__main__":
    main()
