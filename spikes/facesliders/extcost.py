"""extcost.py: for each MakeHuman extension at +1, the identity move that makes it best inside its region (free
elsewhere) and that move's PRIOR cost (|c| in sigmas): expressible is not the same as probable. Also ridge versions
(c penalised by lam * |c|^2, lam in mm^2 per sigma^2): how much of the target a probable identity move makes."""
import numpy as np

from hifipushie import faceext

B, sk = faceext.identity_basis()
for k, (grp, plus, minus, _) in faceext.EXT.items():
    d = 0.5 * (faceext.carry(grp, plus) - faceext.carry(grp, minus))
    m = np.linalg.norm(d, axis=1)
    on = (m > faceext.REGION * m.max())[sk]
    Br = B.reshape(B.shape[0], -1, 3)[:, on].reshape(B.shape[0], -1)
    y = d[sk][on].ravel()
    print(f"{k}: target max {m.max() * 1000:.2f} mm over {int(on.sum())} vertices")
    for lam in (0.0, 1e-8, 1e-7, 1e-6):
        c = np.linalg.solve(Br @ Br.T + lam * np.eye(len(Br)), Br @ y)
        made = Br.T @ c
        print(f"   lam {lam:7.0e}: identity makes {1 - np.linalg.norm(y - made) / np.linalg.norm(y):5.2f} of it "
              f"(residual max {np.abs(y - made).reshape(-1, 3).max() * 1000:.2f} mm), |c| {np.linalg.norm(c):6.1f} sigmas")
