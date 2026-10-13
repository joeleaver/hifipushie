"""mkrange.py: the body range, GNM class-mean heads, attach native: models hb_r_<name> (no clothes, no skin)."""
import numpy as np
from hifipushie import blockin as bi, humans, onemesh, store
from hifipushie.spec import empty_spec
RANGE = {"woman": dict(age=30, sex=0.0), "man": dict(age=30, sex=1.0), "heavy": dict(age=40, sex=1.0, weight=0.9),
         "veryslim": dict(age=25, sex=0.0, weight=0.05), "muscular": dict(age=30, sex=1.0, muscle=0.95),
         "tall": dict(age=30, sex=1.0, height=1.95), "short": dict(age=30, sex=0.0, height=1.50), "old": dict(age=75, sex=1.0),
         "teen": dict(age=14, sex=0.0), "child": dict(age=8, sex=1.0)}
D = bi.data()
for name, kw in RANGE.items():
    sp = {**empty_spec(), **humans.spec(source="human", outfit_kind="none", skin=False, **kw)}
    c = np.asarray(D["m_m"] if kw["sex"] >= 0.5 else D["m_f"])[:170]
    hd = sp["base"]["head"]
    for k in ("seed", "spread", "features", "interior", "mouth"):
        hd.pop(k, None)
    hd.update(identity={f"head_{i:03d}": round(float(x), 4) for i, x in enumerate(c)}, attach="native", lip_close=True)
    hd.pop("gnm_base", None); hd.pop("dimorphism", None)
    for k in ("hair", "cloth"):
        sp.pop(k, None)
    v = store.save(f"hb_r_{name}", sp, "headbody body range")
    r = onemesh.attach_report(sp["base"])
    print(f"== hb_r_{name} v{v} {kw}\n{r['text']}")
