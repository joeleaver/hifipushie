"""sexaxis.py <atlas npz> <ansur dir> <out npz>: the sex axis in GNM's identity space, from ANSUR II's male - female
differences on the measures it shares with GNM (bizygomatic breadth, face height, head breadth / length,
interpupillary, ear length). GNM's prior is one pooled population (its couplings match ANSUR POOLED, not within-sex:
ansur_check.py), so model it as two equal halves: means +-delta/2 in the components, within-sex covariance
I - delta delta^T / 4. delta = the identity move that makes the ANSUR differences (conditional mean, solved for the
least delta). Prints GNM's within-sex correlations against ANSUR's within-sex ones, and the attributes delta moves."""
import csv
import sys
from pathlib import Path

import numpy as np

z = np.load(sys.argv[1], allow_pickle=True)
C, A, names = z["c"], z["A"], [str(x) for x in z["names"]]
col = lambda k: A[:, names.index(k)]  # noqa: E731
io = col("head_size")
meas = {"bizygomatic": col("cheekbone_width") * io, "face_height": col("face_length") * io,
        "head_breadth": col("cranium_width") * io, "head_length": col("head_depth") * io, "interpupillary": io,
        "ear_length": col("ear_size") * io}
acol = {"bizygomatic": ("bizygomaticbreadth", 1.0), "face_height": ("mentonsellionlength", 1.0),
        "head_breadth": ("headbreadth", 1.0), "head_length": ("headlength", 1.0),
        "interpupillary": ("interpupillarybreadth", 0.1), "ear_length": ("earlength", 1.0)}


def load(sex):
    with open(Path(sys.argv[2]) / f"ANSUR_II_{sex}_Public.csv", newline="", encoding="latin-1") as f:
        rows = list(csv.DictReader(f))
    low = {k.lower(): k for k in rows[0]}
    return {m: np.array([float(x[low[c]]) * s for x in rows]) for m, (c, s) in acol.items()}


men, women = load("MALE"), load("FEMALE")
keys = list(meas)
X = np.c_[np.ones(len(C)), C]
Bm = np.array([np.linalg.lstsq(X, meas[k], rcond=None)[0][1:] for k in keys])  # (6, 120) mm per sigma
diff = np.array([men[k].mean() - women[k].mean() for k in keys])
delta = Bm.T @ np.linalg.solve(Bm @ Bm.T, diff)
print(f"delta (male - female) = {np.linalg.norm(delta):.2f} sigmas in GNM's components; top {np.argsort(-np.abs(delta))[:6].tolist()}")
print("  reproduces (mm):", dict(zip(keys, np.round(Bm @ delta, 1))), "asked", dict(zip(keys, np.round(diff, 1))))
if np.linalg.norm(delta) >= 2:
    print("  (|delta| >= 2: the two-halves model can't hold it: within-sex covariance not positive definite)")
Sw = np.eye(len(delta)) - np.outer(delta, delta) / 4
corr = lambda S: S / np.sqrt(np.outer(np.diag(S), np.diag(S)))  # noqa: E731
Rp, Rw = corr(Bm @ Bm.T), corr(Bm @ Sw @ Bm.T)
print("\ncorrelation: GNM pooled -> GNM within-sex | ANSUR within-sex (men, women)")
for i, a in enumerate(keys):
    for j in range(i + 1, len(keys)):
        b = keys[j]
        rm = np.corrcoef(men[a], men[b])[0, 1]
        rw = np.corrcoef(women[a], women[b])[0, 1]
        print(f"  {a:15s} ~ {b:15s} {Rp[i, j]:+.2f} -> {Rw[i, j]:+.2f} | {rm:+.2f} {rw:+.2f}")
# what delta moves among all the atlas's attributes (in their sds)
Ba = np.array([np.linalg.lstsq(X[np.isfinite(A[:, j])], A[np.isfinite(A[:, j]), j], rcond=None)[0][1:] for j in range(A.shape[1])])
sd = np.sqrt((Ba ** 2).sum(1))
mv = Ba @ delta / np.maximum(sd, 1e-12)
print("\nwhat the sex axis moves (attribute sds, male - female):")
for j in np.argsort(-np.abs(mv))[:16]:
    print(f"  {names[j]:18s} {mv[j]:+.2f}")
np.savez(sys.argv[3], delta=delta, keys=np.array(keys), diff=diff)
