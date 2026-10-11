"""probe.py <model> ...: the mesh's own eye numbers (mm at the model): ring corners, fissure, opening."""
import sys
import numpy as np
from hifipushie import blockin_eyes as be, onemesh, store

for name in sys.argv[1:]:
    base = store.load(name)["base"]
    ht = onemesh.head_template(base)
    if name == sys.argv[1]:
        print("ht keys", sorted(ht.keys()))
        print("head keys", {k: (v if not isinstance(v, (dict, list)) else type(v).__name__) for k, v in base["head"].items()})
    rd = be.Reader(ht)
    V = np.asarray(ht["verts"], float)
    R = V[rd.ring]
    c = np.asarray(max(ht["eyes"], key=lambda q: q[0]), float)
    r = float(ht["eye_r"])
    L = np.asarray(ht["lm68"], float)
    i_in, i_out = np.argmin(R[:, 0]), np.argmax(R[:, 0])
    q = rd.read(ht)
    print(f"{name}: eye_r {r*1000:.2f} centre {np.round(c*1000,1)} ring n {len(R)} x {R[:,0].min()*1000:.1f}..{R[:,0].max()*1000:.1f} "
          f"width {np.ptp(R[:,0])*1000:.1f} fissure3d {np.linalg.norm(R[i_out]-R[i_in])*1000:.1f} | lm42-45 {np.linalg.norm(L[45]-L[42])*1000:.1f} "
          f"dx {abs(L[45,0]-L[42,0])*1000:.1f} | open z {np.ptp(R[:,2])*1000:.1f} up {q['up']:.2f} lo {q['lo']:.2f} ri {q['r_iris_mm']:.2f} "
          f"| pupils {abs(ht['eyes'][0][0]-ht['eyes'][1][0])*1000:.1f} | in-corner y {R[i_in,1]*1000:.1f} out y {R[i_out,1]*1000:.1f} ball front y {(c[1]-r)*1000:.1f}"
          f" | canthal tilt {np.degrees(np.arctan2(R[i_out,2]-R[i_in,2], R[i_out,0]-R[i_in,0])):.1f}")
