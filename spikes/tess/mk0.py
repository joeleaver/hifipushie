"""mk0.py <name> [json overrides for human()]: make a one-mesh woman for Tess, measure her, save the head picture."""
import json, os, sys, time
from hifipushie import server

name = sys.argv[1]
kw = dict(age=22, sex="female", weight=0.35, height=1.65, outfit="underwear", source="human", tone=2,
          note="tess: one-mesh woman, first pass")
if len(sys.argv) > 2:
    kw.update(json.loads(sys.argv[2]))
t = time.time()
print(server.human(name, **kw))
r = server.measure_human(name)
for x in r:
    if isinstance(x, str):
        print(x)
    else:
        open(os.path.join(os.environ["T"], "out", f"{name}_measure.png"), "wb").write(x.data)
print(f"{time.time() - t:.0f} s")
