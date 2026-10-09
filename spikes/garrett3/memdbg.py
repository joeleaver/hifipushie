"""memdbg.py <model> [hair]: where the stage's sync spends its memory: a watcher thread prints RSS + the main thread's
stack every few seconds while scene.sync runs."""
import faulthandler
import os
import sys
import threading
import time
import traceback

import stage


def rss():
    for line in open("/proc/self/status"):
        if line.startswith("VmRSS"):
            return int(line.split()[1]) / 1e6
    return 0.0


def watch(main_id, every=4.0):
    last = 0.0
    while True:
        time.sleep(every)
        r = rss()
        if r > last + 0.7:
            last = r
            fr = sys._current_frames().get(main_id)
            st = traceback.extract_stack(fr)[-7:] if fr else []
            print(f"[{time.strftime('%H:%M:%S')}] rss {r:.1f} GB  " + " < ".join(f"{os.path.basename(s.filename)}:{s.lineno}:{s.name}" for s in reversed(st)), flush=True)


threading.Thread(target=watch, args=(threading.main_thread().ident,), daemon=True).start()
t = time.time()
print(stage.ensure(sys.argv[1], with_hair=len(sys.argv) > 2), f"{time.time() - t:.0f} s")
