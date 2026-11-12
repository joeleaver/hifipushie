from hifipushie import base
from hifipushie import base_identity
g = base_identity._gnm_data()
for k, v in g.items():
    print(k, getattr(v, "shape", type(v)), getattr(v, "dtype", ""))
import numpy as np
from hifipushie import assets
z = np.load(assets.path("gnm", base.GNM))
for k in z.files: print("npz", k, z[k].shape, z[k].dtype)
