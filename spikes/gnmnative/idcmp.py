"""idcmp.py <new>=<current> ...: how far a rebuilt head's identity is from the current one: |c|, the largest
component, |c_new - c_cur|, the face's surface rms (GNM mm, hockey mask) and the eye region's."""
import sys

import numpy as np

from hifipushie import blockin as bi
from hifipushie import gnm_mm, store

sp = gnm_mm._space()
face = sp["gr"]["hockey_mask"]
eye = sp["gr"]["left_orbital_region"] | sp["gr"]["right_orbital_region"]
for a in sys.argv[1:]:
    n, o = a.split("=")
    cn, co = bi.identity(store.load(n)), bi.identity(store.load(o))
    D = np.tensordot(cn - co, sp["IB"][:170], 1) * 1000
    print(f"{n} vs {o}: |c| {np.linalg.norm(cn):.2f} (largest {np.abs(cn).max():.2f} sd) vs {np.linalg.norm(co):.2f} ({np.abs(co).max():.2f}); "
          f"|dc| {np.linalg.norm(cn - co):.2f}; face surface rms {np.sqrt((D[face] ** 2).sum(1).mean()):.2f} mm, eye region {np.sqrt((D[eye] ** 2).sum(1).mean()):.2f} mm")
