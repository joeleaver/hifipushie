import numpy as np
from hifipushie import base, faceslide
g = base._gnm_data()
R = faceslide._lip_rings()
up, lo = np.asarray(g["groups"]["upper_lip"]), np.asarray(g["groups"]["lower_lip"])
for k, r in enumerate(R["rings"][:5]):
    print(k, len(r), "upper", int((up[r] > 0.5).sum()), "lower", int((lo[r] > 0.5).sum()), "neither", int(((up[r] <= 0.5) & (lo[r] <= 0.5)).sum()), "both", int(((up[r] > 0.5) & (lo[r] > 0.5)).sum()))
