"""brokendbg.py <model> <garment> <res>: place at that mesh size; on a broken start, the biggest triangles' piece, uv and
corner positions."""
import sys
import numpy as np
from hifipushie import cloth, cloth_workflow

name, g, res = sys.argv[1], sys.argv[2], float(sys.argv[3])
c = cloth_workflow.Ctx(name, g)
Bp = c.Bp
M = cloth.mesh(Bp, res)
orig = cloth._piece_crossings


def spy(X, M_):
    F = M_["F"]
    cen = X[F].mean(1)
    rad = np.max(np.linalg.norm(X[F] - cen[:, None], axis=2), axis=1)
    for t in np.argsort(-rad)[:5]:
        print(f"{M_['names'][M_['piece'][F[t, 0]]]} tri {t} across {rad[t] * 2000:.0f} mm uv "
              f"{np.round(M_['uv'][F[t]], 3).tolist()} X {np.round(X[F[t]], 3).tolist()}")
    return orig(X, M_)


cloth._piece_crossings = spy
body_p = c.body.straight_arms()[0]
try:
    cloth.place(Bp, M, body_p, smooth=True)
    print("placed ok")
except Exception as e:
    print("ERR", e)
