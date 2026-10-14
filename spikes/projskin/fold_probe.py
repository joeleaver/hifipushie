"""fold_probe.py: gnm_fold.mesh_delta on GNM's mean head: locality, the read before / after, a blink."""
import numpy as np
from hifipushie import gnm_fold as gf, gnm_controls as gc
V = gf.vertices() / 1000.0
print("before:", gf.read_text(gf.read(V * 1000)))
for cfg in ({"crease": 6.5, "overhang": 0.6}, {"crease": 7.0, "overhang": 2.5}, {"crease": [5.5, 7.0, 6.0], "overhang": [0.3, 1.0, 3.0]}):
    d = gf.mesh_delta(V, None, cfg)
    mv = np.linalg.norm(d, axis=1) > 0
    t = gf.topo()
    ring = t["ring"]; rm = np.minimum(ring, ring[t["mir"]])
    print(cfg, "moved", int(mv.sum()), "max mm", round(1000 * float(np.linalg.norm(d, axis=1).max()), 2), "rings moved", sorted(set(rm[mv].tolist())),
          "after:", gf.read_text(gf.read((V + d) * 1000)))
