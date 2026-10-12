"""consumers.py <model>: the tools that read the head, run on a native model (no renders)."""
import sys, traceback
from hifipushie import server, store, blockin as bi, base as B
m = sys.argv[1]
def run(name, fn):
    try:
        r = fn()
        print("OK ", name, "::", str(r)[-420:].replace("\n", " | "))
    except Exception as e:
        print("FAIL", name, "::", type(e).__name__, str(e)[:300]); traceback.print_exc(limit=3)
run("measure_human", lambda: server.measure_human(m, picture=False))
sp = store.load(m)
run("eye_native", lambda: {k: (round(v, 5) if isinstance(v, float) else "..") for k, v in (B.eye_native(sp) or {}).items()})
run("drawn_iris mm", lambda: round(2000 * B.drawn_iris(sp), 2))
from hifipushie import rig as rigmod
run("rig_bones", lambda: [(b["name"].split(":")[-1], [round(float(x), 3) for x in b["head"]]) for b in rigmod.rig_bones(sp) if b["name"].split(":")[-1] in ("Neck", "Head", "HeadTop_End", "LeftEye")])
from hifipushie.spec import expand_mirror
s = expand_mirror(sp)
run("joints", lambda: {k: [round(float(x), 3) for x in s["joints"][k]["pos"]] for k in ("neck", "head", "eye.L", "lm_chin") if k in s["joints"]})
