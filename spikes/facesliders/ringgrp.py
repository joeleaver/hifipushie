import numpy as np
from hifipushie import base, faceslide
from hifipushie import faceslide_mouth
from hifipushie import base_identity
g = base_identity._gnm_data()
R = faceslide_mouth._lip_rings()
up, lo = np.asarray(g["groups"]["upper_lip"]), np.asarray(g["groups"]["lower_lip"])
for k, r in enumerate(R["rings"][:5]):
    print(k, len(r), "upper", int((up[r] > 0.5).sum()), "lower", int((lo[r] > 0.5).sum()), "neither", int(((up[r] <= 0.5) & (lo[r] <= 0.5)).sum()), "both", int(((up[r] > 0.5) & (lo[r] > 0.5)).sum()))
