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


def _oval(side, mmpx):
    """The jaw contour like with like: the detector's face-oval points below the eyes, x and y (mm, picture axes),
    relative to the midpoint of the eyes' inner corners."""
    from hifipushie.likeness import OVAL
    P = np.asarray(side.P, float)
    o = 0.5 * (P[133] + P[362])
    out = {}
    for i in OVAL:
        if P[i][1] > o[1] + 10 / mmpx:  # under the eyes
            out[f"ox{i}"] = float((P[i][0] - o[0]) * mmpx)
            out[f"oy{i}"] = float((P[i][1] - o[1]) * mmpx)
    return out


def measure(name, base):
    m = lp.matched(name, base, items=ITEMS, face_id=False)
    ph = {**_eyes(m["ph"]["side"], m["ph"]["mmpx"]), **{k: r["photo"] for k, r in m["items"].items()},
          **_oval(m["ph"]["side"], m["ph"]["mmpx"])}
    md = {**_eyes(m["md"]["side"], m["md"]["mmpx"]), **{k: r["model"] for k, r in m["items"].items()},
          **_oval(m["md"]["side"], m["md"]["mmpx"])}
    try:  # the nose's dorsal widths by shading (faceslide.nose_widths): the photo, and the render lit by its light
        from hifipushie import faceslide
        ph.update(faceslide.nose_widths(m["ph"]["img"], m["ph"]["side"].P, m["ph"]["mmpx"]))
        ren = (m.get("render") or m["clay"])
        k = ren.size[0] / (m["box"][2] - m["box"][0])
        Pm = (np.asarray(m["md"]["side"].P, float) - np.asarray(m["box"][:2])) * k
        md.update(faceslide.nose_widths(ren, Pm, m["md"]["mmpx"] / k))
    except Exception as e:  # noqa: BLE001
        print("nose widths:", e)
    return ph, md, m


if __name__ == "__main__":
    import sys

    from hifipushie import store
    t = time.time()
    ph, md, _ = measure(sys.argv[1], store.load(sys.argv[1])["base"])
    print("seconds", round(time.time() - t, 1))
    for k in ph:
        print(f"{k:16s} photo {ph[k]}  model {md.get(k)}")
