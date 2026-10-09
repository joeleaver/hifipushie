"""lkr.py <name> [targets 0|1] [top]: the likeness checklist report (text to $T/out/<name>_likeness.txt)."""
import os, sys
from hifipushie import server

name = sys.argv[1]
if len(sys.argv) > 2 and sys.argv[2] == "1":
    t = server.likeness(name, targets=True)
    open(os.path.join(os.environ["T"], "out", name + "_targets.txt"), "w").write(t)
    print(t[:3000])
r = server.likeness(name, top=int(sys.argv[3]) if len(sys.argv) > 3 else 8)
txt = next(x for x in r if isinstance(x, str))
open(os.path.join(os.environ["T"], "out", name + "_likeness.txt"), "w").write(txt)
print(txt)
