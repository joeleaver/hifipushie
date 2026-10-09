from hifipushie import base
g = base._gnm_data()
for k, v in g.items():
    print(k, getattr(v, "shape", type(v)), getattr(v, "dtype", ""))
import numpy as np
from hifipushie import assets
z = np.load(assets.path("gnm", base.GNM))
for k in z.files: print("npz", k, z[k].shape, z[k].dtype)
