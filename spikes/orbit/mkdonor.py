"""mkdonor.py: the lid donors' GNM identities (two sampled GNM heads Joe judged to read right dressed: gnmcrease's
gk_s376 / gk_s540, samples #376 / #540 of N(0, I)) -> src/hifipushie/blockin_lid.npz (s376, s540: (170,))."""
import numpy as np

from hifipushie import blockin as bi, blockin_lid, store

np.savez(blockin_lid.DATA, **{k: bi.identity(store.load("gk_" + k)).astype(np.float32) for k in ("s376", "s540")})
print("wrote", blockin_lid.DATA)
