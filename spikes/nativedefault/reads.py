"""reads.py <model> [iris=<out model>]: the eye and lip READS of a block-in model after its solves (nothing forced):
the IRIS line (blockin_eyes.iris_check: the picture's limbus vs GNM's limbus for the identity), the eye ruler's table
(server.eye_ruler), the lid read and the lip read (server.lid_read / lip_read, read only), |c| and the largest
component. iris=<out>: apply the iris read as block_in_step {"iris_mm": mm} (the identity's eyes_000) into <out>,
unless the picture's iris is unreadable or the step is past 3 sd."""
import sys

import numpy as np

from hifipushie import blockin as bi
from hifipushie import blockin_eyes as be
from hifipushie import server, store

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
c = bi.identity(store.load(m))
print(f"== {m}: |c| {np.linalg.norm(c):.2f}, largest component {np.abs(c).max():.2f} sd; other GNM components {bi.identity_extra(store.load(m))}")
ic = be.iris_check(m)
print(ic["text"])
for nm, fn in (("EYE RULER", lambda: server.eye_ruler(m, save=f"/mnt/data/hifipushie/nativedefault/out/er_{m}.png")),
               ("LID READ", lambda: server.lid_read(m)), ("LIP READ", lambda: server.lip_read(m))):
    try:
        r = fn()
        txt = r[-1] if isinstance(r, list) else r
        print(f"-- {nm}\n{txt if isinstance(txt, str) else getattr(txt, 'text', txt)}")
    except Exception as e:  # noqa: BLE001
        print(f"-- {nm}: failed: {type(e).__name__}: {str(e)[:300]}")
if kw.get("iris"):
    if ic.get("photo_mm") and ic.get("eyes_000") is not None and abs(ic["ratio"] - 1) > 0.02:
        rep = bi.step(m, {"iris_mm": round(ic["photo_mm"], 2)}, out=kw["iris"], seen=f"the picture's limbus {ic['photo_mm']:.2f} mm, GNM's {ic['model_mm']:.2f}",
                      why="the iris read sets GNM's limbus component (eyes_000)")
        sp = store.load(kw["iris"])
        print(f"-- IRIS STEP -> {kw['iris']}: eyes_000 {sp['base']['head']['identity'].get('eyes_000')}; " + be.iris_check(kw["iris"])["text"][:160])
    else:
        print("-- IRIS STEP: not applied (unreadable, within 2 %, or past 3 sd)")
