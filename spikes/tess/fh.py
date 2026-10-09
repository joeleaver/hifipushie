"""fh.py <name> <tag> <set json> [free csv] [release csv] [save 0|1]: fit_human, report printed, picture to $T/out/<tag>.png."""
import json, os, sys
from hifipushie import server

name, tag, st = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
free = sys.argv[4].split(",") if len(sys.argv) > 4 and sys.argv[4] else None
rel = sys.argv[5].split(",") if len(sys.argv) > 5 and sys.argv[5] else None
save = (sys.argv[6] != "0") if len(sys.argv) > 6 else True
r = server.fit_human(name, st, free=free, release=rel, save=save, note=f"tess: fit {st}", figure=False)
for x in r:
    if isinstance(x, str):
        print(x)
    else:
        open(os.path.join(os.environ["T"], "out", tag + ".png"), "wb").write(x.data)
