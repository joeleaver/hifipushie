import numpy as np
import fitlib, fits, fits2, mm, rs, tmesh
from oracle_mesh import TrueMesh
import sys
s = sys.argv[1]
Vt = fits.truth(s)["V"]
me = TrueMesh(Vt, seed=1)
idx, sg = fits2.mesh_idx(s, step=3)
c = np.zeros(rs.K_FIT)
e = tmesh.align(me, rs.head(c))
print("start", me.start, "icp mm", e * 1000, rs.row(rs.score(rs.head(c), Vt)))
for it in range(25):
    A, y = tmesh.rows(me, c, idx, np.full(len(idx), float(sys.argv[2])), realign=(sys.argv[3] == "1"))
    c = np.linalg.solve(A.T @ A + np.eye(rs.K_FIT), A.T @ y)
    if it % 3 == 0:
        a, ok, q, nq = tmesh.offsets(me, rs.head(c), idx)
        print(it, rs.row(rs.score(rs.head(c), Vt)), f"sig {np.sqrt((c**2).mean()):.2f} resid {np.abs(a[ok]).mean()*1000:.2f} ok {ok.mean():.2f} scale {me.T[0]:.3f}")
