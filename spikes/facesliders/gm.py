"""gm.py: Garrett through the photo's camera (likeness_pair.matched, clay lit by the photo's fitted light): the eye and
lip measures by the same detector on the photo and on the model, for faceslide.fit. `measure(name, base)` ->
(photo, model) dicts of means over both eyes + mouth items."""
import time

import numpy as np

from hifipushie import likeness_eyes as le
from hifipushie import likeness_pair as lp

ITEMS = lp.ITEMS + ("upper_lip", "lower_lip", "cupid_bow", "lip_ratio")


def _eyes(side, mmpx):
    m = le.measures(side.P, mmpx)
    return {k: float(np.mean(v)) for k, v in m.items()}


def measure(name, base):
    m = lp.matched(name, base, items=ITEMS, face_id=False)
    ph = {**_eyes(m["ph"]["side"], m["ph"]["mmpx"]), **{k: r["photo"] for k, r in m["items"].items()}}
    md = {**_eyes(m["md"]["side"], m["md"]["mmpx"]), **{k: r["model"] for k, r in m["items"].items()}}
    return ph, md, m


if __name__ == "__main__":
    import sys

    from hifipushie import store
    t = time.time()
    ph, md, _ = measure(sys.argv[1], store.load(sys.argv[1])["base"])
    print("seconds", round(time.time() - t, 1))
    for k in ph:
        print(f"{k:16s} photo {ph[k]}  model {md.get(k)}")
