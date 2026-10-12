"""sizeof.py <start> <model> ...: the head's SIZE along a block-in (solve_report.size_row's direction: the hockey
mask's similarity scale against the start head, %), what is left of the identity change once that uniform scale is
taken out (shape, surface rms mm), which components carry the size, each call's cameras (distance x focal: the image
scale the camera took), pupils apart and face height (GNM mm), and THE IRIS CHECK: the front picture's limbus in px
against GNM's limbus for the identity says how large the head is, independently of the solve (+- 7 %: GNM's limbus is
6.0 +- 0.44 mm)."""
import json
import sys

import numpy as np

from hifipushie import blockin as bi
from hifipushie import gnm_mm, store
from hifipushie import solve_report as sr

sp = gnm_mm._space()
m = sp["gr"]["hockey_mask"]
g = sr.size_row()["J"]
start = sys.argv[1]
c0 = bi.identity(store.load(start))


def head(c):
    return sp["T"] + np.tensordot(c, sp["IB"][:170], 1)


def measures(c):
    V = head(c)
    L = sp["WL"] @ V
    r = gnm_mm.readers(V)
    return r["pupils_apart"], float(np.linalg.norm(L[27] - L[8]) * 1000), float(abs(L[16][0] - L[0][0]) * 1000)


def sim(c, cref):
    A, B = head(cref)[m], head(c)[m]
    a, b = A - A.mean(0), B - B.mean(0)
    k = float((a * b).sum() / (a * a).sum())
    return k, float(np.sqrt(((b - k * a) ** 2).sum(1).mean()) * 1000)


print(f"start {start}: pupils apart / nasion-chin / face width (GNM mm) " + " / ".join(f"{x:.1f}" for x in measures(c0)))
for name in sys.argv[2:]:
    c = bi.identity(store.load(name))
    k, shape = sim(c, c0)
    pa, fh, fw = measures(c)
    top = np.argsort(-np.abs(g * (c - c0)))[:5]
    rj = json.load(open(store.HOME / name / "human_refs.json"))
    cams = " ".join(f"f/t {cam['f'] / cam['t'][2]:.0f}" for cam in rj["cameras"])
    txt = f"{name}: size {100 * (k - 1):+.1f} % (linear row {100 * float(g @ (c - c0)):+.1f} %); shape left after the scale {shape:.2f} mm rms; pupils {pa:.1f}, nasion-chin {fh:.1f}, width {fw:.1f}; "
    txt += "size carried by " + ", ".join(f"head_{i:03d} {100 * g[i] * (c - c0)[i]:+.1f}%" for i in top) + f"; cameras {cams}"
    try:
        from hifipushie import blockin_eyes as be
        ic = be.iris_check(name)
        if ic.get("photo_mm"):
            sp_ = store.load(name)
            e0 = float((sp_["base"]["head"].get("identity") or {}).get("eyes_000", 0.0))
            # the model's limbus at GNM's MEAN eye (eyes_000 = 0) against the picture's: the head's size the iris implies
            from hifipushie import base as basemod
            if basemod.eye_native(sp_) is not None:
                sp2 = json.loads(json.dumps(sp_))
                sp2["base"]["head"]["identity"].pop("eyes_000", None)
                mean_mm = 2000 * basemod.eye_native(sp2)["limbus"]
                txt += f"; IRIS CHECK: picture {ic['photo_mm']:.2f} mm at the model, GNM's mean limbus here {mean_mm:.2f} mm: the iris says the head is {100 * (mean_mm / ic['photo_mm'] - 1):+.1f} % against this size (+- 7 %; eyes_000 now {e0:+.2f})"
    except Exception as e:  # noqa: BLE001
        txt += f"; iris check failed: {str(e)[:60]}"
    print(txt)
