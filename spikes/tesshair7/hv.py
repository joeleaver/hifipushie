"""hv.py <script> [args] [-- <script> [args]] ...: several scripts ONE AFTER ANOTHER in one process holding the
machine-wide heavy slot (resources.heavy): a round's small steps (tie_hair, a lock plot, a measure) ride with its
render instead of queueing for the light slots (2026-10-13: ten solver chains ahead, 20+ min for a 1 s plot).
A failing script stops the chain (exit 1)."""
import os
import runpy
import sys
import time
import traceback

from hifipushie import resources

jobs, cur = [], []
for a in sys.argv[1:]:
    if a == "--":
        jobs.append(cur)
        cur = []
    else:
        cur.append(a)
if cur:
    jobs.append(cur)
W = os.environ.get("W", ".")
import contextlib

# (round two, the coordinator: light steps go through bin/slot and WAIT; they do not ride in the heavy slot. HV_LIGHT=1
# = this chain is a light job (run it through runl.sh): no heavy slot is taken here; a script that renders takes it itself)
with (contextlib.nullcontext() if os.environ.get("HV_LIGHT") else
      resources.heavy("tesshair7 " + " ".join(os.path.basename(j[0]) for j in jobs)[:60], gb=float(os.environ.get("HV_GB", 8)))):
    for j in jobs:
        s = j[0]
        if not os.path.isabs(s):
            for d in ("tesshair7", "tesshair6", "tesshair5", "tesshair4", "tesshair3", "tesshair2", "tesshair"):
                if os.path.exists(f"{W}/spikes/{d}/{s}"):
                    s = f"{W}/spikes/{d}/{s}"
                    break
        t = time.time()
        sys.argv = [s] + j[1:]
        print(f"== {os.path.basename(s)} {' '.join(j[1:])[:150]}", flush=True)
        try:
            runpy.run_path(s, run_name="__main__")
        except SystemExit as e:
            if e.code not in (0, None):
                print("FAILED", s, e.code, flush=True)
                sys.exit(1)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            print("FAILED", s, flush=True)
            sys.exit(1)
        print(f"   ({time.time() - t:.0f} s)", flush=True)
