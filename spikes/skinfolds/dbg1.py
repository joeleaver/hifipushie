import json, sys
import numpy as np
from hifipushie import store, sdf, images, skin_folds as sf
from hifipushie.spec import expand_mirror, compile_prims
spec = store.load(sys.argv[1])
spec["skin"] = {**spec["skin"], "folds": json.load(open(sys.argv[2]))}
prims = compile_prims(spec)
J = {k: np.asarray(v["pos"], float) for k, v in expand_mirror(spec)["joints"].items() if "pos" in v}
for p in prims:
    if p.kind != "tissue":
        continue
    pr = p.params
    P = pr["pts"]
    kt = sf._keep_tree(pr)
    dk = kt.query(P)[0] * 1000
    db = np.min([np.linalg.norm(P - b[:3], axis=1) - b[3] for b in pr["balls"]], 0) * 1000
    print(f"{p.name:22s} n {len(P)} lip {p.lip:.2f} keep-dist mm {dk.min():.1f}..{dk.max():.1f}  ball clearance mm {db.min():.1f}..{db.max():.1f}  "
          f"G {pr['G'].max() * 1000:.2f} O {pr['O'].max() * 1000:.2f} r0 {pr['r0'] * 1000:.1f} so {pr['so'] * 1000:.1f} k {pr['k']} radius {pr['radius'] * 1000:.1f} "
          f"z {P[:, 2].min():.4f}..{P[:, 2].max():.4f} x {P[:, 0].min():.4f}..{P[:, 0].max():.4f}")
print({k: J[k].round(4).tolist() for k in ("eye.L", "lm_lid_lower.L", "lm_lid_upper.L", "lm_eye_inner.L", "lm_eye_outer.L")})
