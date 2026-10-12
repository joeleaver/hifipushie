"""info.py <model>: joints, head dict, lid lines: what the fold geometry can hang on."""
import sys, time, numpy as np
from hifipushie import store, base as B, lashes, skin
from hifipushie.spec import expand_mirror, compile_prims
name = sys.argv[1]
spec = store.load(name)
t = time.time()
s = expand_mirror(spec)
J = {k: np.asarray(v["pos"], float) for k, v in s["joints"].items() if "pos" in v}
print(sorted(k for k in J if k.startswith(("lm_", "eye", "ver", "lip"))))
print("io", skin.interocular(J))
h = B.head_of(s, s["base"])
print({k: (type(v).__name__, getattr(v, "shape", None)) for k, v in h.items()})
for k in ("eyes", "eye_r", "eyeballs", "eye"):
    print(k, h.get(k))
for L in lashes.lid_lines(h):
    print({k: (v.shape if hasattr(v, "shape") and v.ndim else v) for k, v in L.items()})
prims = compile_prims(spec)
print(len(prims), [(p.name, p.kind, p.op, p.part) for p in prims][:40], time.time() - t)
