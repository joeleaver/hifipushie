"""sexdir.py <atlas npz> [age]: is sex in GNM's identity prior, and do the atlas's couplings survive conditioning on it?
- The male - female head difference at that age (headfit's MakeHuman age / sex fields, interoculars -> m at GNM's
  interocular) projected onto the 120 head components: u (sigmas). |u| = how far apart GNM puts the sexes.
- B: each attribute's linear model in the components (from the atlas). The attributes the sex direction moves (in
  attribute sds per sex difference).
- The couplings with the sex axis conditioned out (covariance B (I - u u^T / |u|^2) B^T): within-sex correlations,
  against the pooled ones, for the strongest pairs."""
import sys

import numpy as np

from hifipushie import base as basemod
from hifipushie import headfit, humanmacro

z = np.load(sys.argv[1], allow_pickle=True)
C, A, names = z["c"], z["A"], [str(x) for x in z["names"]]
age = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
g = basemod._gnm_data()
nm = [str(x) for x in g["identity_names"]]
comps = [i for i, x in enumerate(nm) if x.startswith("head")][:humanmacro.K]
IB = np.asarray(g["vertex_identity_basis"])[comps].astype(float)
f = headfit.fields()
ages = f["ages"]
i = int(np.clip(np.searchsorted(ages, age) - 1, 0, len(ages) - 2))
t = (age - ages[i]) / (ages[i + 1] - ages[i])
T = f["age_sex"].astype(float)
d = (1 - t) * (T[i, 1] - T[i, 0]) + t * (T[i + 1, 1] - T[i + 1, 0])   # male - female, interoculars
J0 = g["template_joint_positions"]
io = float(abs(J0[2][0] - J0[3][0]))
d = d * io
valid = np.asarray(f.get("valid", np.ones(len(d), bool)), bool) & (np.asarray(g["groups"]["hockey_mask"]) > 0.5)
M = IB[:, valid].reshape(len(comps), -1).T
# (ridge: the identity's own prior, N(0, 1), against the field at ~1 mm a coordinate: a plain least squares put the
# sexes 117 sigmas apart by fitting MakeHuman's field detail with GNM's smallest components)
SIG = 0.001
u = np.linalg.solve(M.T @ M / SIG ** 2 + np.eye(M.shape[1]), M.T @ d[valid].ravel() / SIG ** 2)
fit = np.linalg.norm(M @ u - d[valid].ravel()) / np.linalg.norm(d[valid].ravel())
print(f"age {age}: male - female = {np.linalg.norm(u):.2f} sigmas in GNM's head space (residual {fit:.2f} of the field "
      f"not expressible); top components {np.argsort(-np.abs(u))[:6].tolist()} {np.round(u[np.argsort(-np.abs(u))[:6]], 2).tolist()}")
X = np.c_[np.ones(len(C)), C]
ok = np.isfinite(A).all(1)
Bf = np.linalg.lstsq(X[ok], A[ok], rcond=None)[0]
B = Bf[1:].T  # (m, 120)
sd = np.sqrt((B ** 2).sum(1))
mv = B @ u / np.maximum(sd, 1e-12)
print("\nwhat the sex difference moves (attribute sds, male - female):")
for j in np.argsort(-np.abs(mv))[:14]:
    print(f"  {names[j]:18s} {mv[j]:+.2f}")
uh = u / np.linalg.norm(u)
P = np.eye(len(u)) - np.outer(uh, uh)
Cp = B @ B.T
Cw = B @ P @ B.T
corr = lambda S: S / np.sqrt(np.outer(np.diag(S), np.diag(S)))  # noqa: E731
Rp, Rw = corr(Cp), corr(Cw)
pairs = [("eye_depth", "brow_ridge"), ("eye_depth", "bridge_height"), ("eye_setback", "brow_ridge"),
         ("brow_ridge", "fold_overhang"), ("jaw_width", "chin_width"), ("face_width", "jaw_width"),
         ("face_length", "nose_length"), ("lip_fullness", "upper_vermilion"), ("nose_projection", "nose_upturn"),
         ("eye_height", "lid_aperture"), ("face_width", "cheekbone_width"), ("brow_ridge", "jaw_width")]
print("\ncoupling       pooled -> within-sex")
for a, b in pairs:
    if a in names and b in names:
        ia, ib = names.index(a), names.index(b)
        print(f"  {a:16s} ~ {b:16s} {Rp[ia, ib]:+.2f} -> {Rw[ia, ib]:+.2f}")
np.savez(sys.argv[1].replace(".npz", f"_sex{int(age)}.npz"), u=u, B=B, a0=Bf[0], names=np.array(names))
