"""lk.py <name> <out tag> [views csv] [size] [json kwargs]: a clay look saved to $T/out/<tag>.png."""
import json, os, sys
from hifipushie import server

name, tag = sys.argv[1], sys.argv[2]
views = sys.argv[3].split(",") if len(sys.argv) > 3 else ["front", "side"]
size = int(sys.argv[4]) if len(sys.argv) > 4 else 448
kw = json.loads(sys.argv[5]) if len(sys.argv) > 5 else {}
r = server.look(name, views=views, size=size, **kw)
for x in r:
    if isinstance(x, str):
        print(x[:2000])
    else:
        p = os.path.join(os.environ["T"], "out", tag + ".png")
        open(p, "wb").write(x.data)
        print("saved", p)
