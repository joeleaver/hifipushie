"""jawsq.py: what humanmacro's jaw_square -0.8 does, free (the population direction) and held (every other macro held):
the jaw measures before -> after (io units) on GNM's mean head."""
import numpy as np

from hifipushie import humanmacro as hm

c0 = np.zeros(hm.K)
r0 = hm.read(c0)
for held in (False, True):
    c1 = hm.apply(c0, {"jaw_square": -0.8}, held=held)
    r1 = hm.read(c1)
    print("held" if held else "free", {k: (round(float(r0[k]), 3), round(float(r1[k]), 3)) for k in
                                       ("jaw_square", "jaw_width", "face_width", "chin_width", "cheekbone_width")})
