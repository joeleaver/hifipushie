"""mmcmp.py <model> ...: the chin / lower face, the eyes and a few others on each model's GNM identity (mm, GNM's frame;
macros in population sd), side by side; |c| and the largest component."""
import sys
import numpy as np
from hifipushie import blockin as bi, gnm_mm, humanmacro as hm, solve_report as sr, store
ms = sys.argv[1:]
sp = gnm_mm._space()
rows = ("pogonion_forward", "chin_forward", "chin_length", "lower_face_height", "chin_width", "chin_point", "mentolabial_depth",
        "jaw_width", "gonial_width", "under_chin", "mouth_width", "nose_length", "tip_forward", "eyes_forward", "brow_ridge_forward",
        "forehead_forward", "cheekbone_width", "pupils_apart")
mac = ("jaw_square", "jaw_angle", "chin_cleft", "cheek_fullness", "brow_ridge", "orbital_rim", "eye_depth")
C = [bi.identity(store.load(m)) for m in ms]
print(f"{'':20s}" + "".join(f"{m[-10:]:>11s}" for m in ms))
print(f"{'|c| / largest':20s}" + "".join(f"{np.linalg.norm(c):6.1f}/{np.abs(c).max():4.2f}" for c in C))
R = []
for c in C:
    V = sp["T"] + np.tensordot(c, sp["IB"], 1)
    R.append({**gnm_mm.readers(V), **sr.chin_readers(V), **{k: v for k, v in hm.read(c[:hm.K]).items()}})
for n in rows + mac:
    print(f"{n:20s}" + "".join(f"{r[n]:11.1f}" for r in R) + ("  sd" if n in mac else "  mm"))
