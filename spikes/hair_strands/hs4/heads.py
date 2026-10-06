"""heads.py [names]: the test heads for loose hair (humans.spec, saved + synced once each)."""
import sys, time
from hifipushie import humans, store, scene

HEADS = {
    "hu_w30": dict(age=30, sex=0.0, tone=2, seed=8),
    "hu_w28d": dict(age=28, sex=0.0, tone=6, seed=21, race={"african": 1.0, "asian": 0.0, "caucasian": 0.0}),
    "hu_m35a": dict(age=35, sex=1.0, tone=3, seed=14, race={"african": 0.0, "asian": 1.0, "caucasian": 0.0}),
    "hu_w26a": dict(age=26, sex=0.0, tone=3, seed=5, race={"african": 0.0, "asian": 1.0, "caucasian": 0.0}),
    "hu_m30": dict(age=30, sex=1.0, tone=4, seed=3),
    "hu_g7": dict(age=7, sex=0.0, tone=2, seed=11),
}
for n in sys.argv[1:] or HEADS:
    kw = dict(HEADS[n]); race = kw.pop("race", None)
    t = time.time()
    sp = humans.spec(**kw)
    if race:
        sp["base"]["body"]["race"] = race
    store.save(n, sp, "hair4 test head")
    print(n, "saved", round(time.time() - t), flush=True)
    r = scene.sync(n)
    print(n, "synced", round(time.time() - t), str(r)[-300:], flush=True)
