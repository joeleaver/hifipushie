"""mk_arkit.py: spikes/denselm/arkit_expr.npz = the ARKit-named face shapes as GNM EXPRESSION COEFFICIENTS (383 each),
solved once by faceshapes.GnmFace on the GNM-native male class mean (the generator mixes them: smile with teeth, jaw
open, blink, wide, squint, brow down ...). Shapes GNM's basis has no landmarks for come out empty and are left out."""
import sys
from pathlib import Path

import numpy as np

from hifipushie import base as basemod, blockin as bi, faceshapes, humans
from hifipushie.spec import empty_spec

sp = {**empty_spec(), **humans.spec(age=35, sex=1.0, source="human", outfit_kind="none")}
hd = sp["base"]["head"]
for k in bi.STRIP + ("lip_seal", "mouth_gap", "eye_radius", "interior", "scale"):
    hd.pop(k, None)
hd.update({"attach": "native", "gnm_base": 1.0, "dimorphism": 0.0, "eyes": 1.0, "lip_close": True})
bi.set_identity(sp, np.asarray(bi.data()["m_m"], float))
names = [str(n) for n in basemod._gnm_data()["expression_names"]]
gf = faceshapes.GnmFace(sp)
out, kept = [], []
for n in faceshapes.ALL:
    c = gf.shape_coeffs(n)
    if not c:
        continue
    v = np.zeros(len(names), np.float32)
    for k, x in c.items():
        v[names.index(k)] = x
    out.append(v)
    kept.append(n)
    print(n, len(c), float(np.abs(v).max()), flush=True)
p = Path(__file__).with_name("arkit_expr.npz")
np.savez_compressed(p, names=np.array(kept), E=np.array(out), expression_names=np.array(names))
print(p, len(kept))
