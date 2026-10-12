"""glbcheck.py <file.glb>: the face shapes a GLB carries, per mesh: targets, which move it, and the mouth's checks
(jawOpen: the teeth mesh's lower row drops and its upper row stays; tongueOut: the tongue comes forward)."""
import sys

import numpy as np

from hifipushie import faceshapes

g = faceshapes.read_glb(sys.argv[1])
for mesh, d in g.items():
    names = d["names"]
    P = {n: np.asarray(t["POSITION"]) for n, t in zip(names, d["targets"])}
    mv = {n: float(np.linalg.norm(p, axis=1).max()) for n, p in P.items()}
    moved = [n for n, v in mv.items() if v > 1e-6]
    print(f"MESH {mesh}: {d['count']} vertices, {len(names)} targets, {len(moved)} move it; "
          + ", ".join(f"{n} {1000 * mv[n]:.1f} mm" for n in ("jawOpen", "tongueOut", "eyeBlinkLeft", "mouthSmileLeft", "eyeLookUpLeft") if n in mv))
    if "teeth" in mesh and "jawOpen" in P:
        d_ = np.linalg.norm(P["jawOpen"], axis=1)
        print(f"   teeth jawOpen: {float((d_ < 1e-4).mean()) * 100:.0f} % of vertices still (the upper row), "
              f"{float((d_ > 0.004).mean()) * 100:.0f} % move > 4 mm (the lower row); glTF y (up) mean of the movers {1000 * P['jawOpen'][d_ > 0.004][:, 1].mean():.1f} mm")
    if "tongue" in mesh and "tongueOut" in P:
        print(f"   tongue tongueOut: max forward (glTF z) {1000 * P['tongueOut'][:, 2].max():.1f} mm, jawOpen max {1000 * mv['jawOpen']:.1f} mm")
