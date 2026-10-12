"""mmdiff.py <model a> <model b> [more ...]: two heads as SHAPES. Identity: |c|, largest component, |c_a - c_b|, the
largest component differences; gnm_mm's measures (GNM's own millimetres, the identity alone) for each and b - a in mm and
population sd, largest first; humanmacro's macros (sd) that differ most; the shipped heads' own measures off the 68
landmarks (humanfit.face_measures: with the body's head scale and style) the same way."""
import sys
import numpy as np
from hifipushie import blockin as bi, face_ruler as fr, gnm_mm, humanfit, humanmacro, store

names = sys.argv[1:]
C = {m: bi.identity(store.load(m)) for m in names}
for m in names:
    c = C[m]
    i = int(np.abs(c).argmax())
    print(f"{m}: |c| {np.linalg.norm(c):.2f}, largest component head_{i:03d} {c[i]:+.2f} sd, comps past 2.5 sd: {int((np.abs(c) > 2.5).sum())}")
a, b = names[0], names[1]
d = C[b] - C[a]
print(f"|c_{b} - c_{a}| = {np.linalg.norm(d):.2f}; cos(c_a, c_b) = {C[a] @ C[b] / np.linalg.norm(C[a]) / np.linalg.norm(C[b]):+.2f}")
D = bi.data()
mm_ = np.asarray(D["m_m"], float)
print(f"from the male class mean: |{a} - mean| {np.linalg.norm(C[a] - mm_):.2f}, |{b} - mean| {np.linalg.norm(C[b] - mm_):.2f}, "
      f"cos of the two departures {(C[a] - mm_) @ (C[b] - mm_) / np.linalg.norm(C[a] - mm_) / np.linalg.norm(C[b] - mm_):+.2f}")
H = {m: fr.gnm_head(C[m]) for m in names}
sd = gnm_mm.sd()
print(f"\ngnm_mm measures (GNM's mm, identity alone): {b} - {a}, largest in sd first")
print(f"{'measure':22s} " + " ".join(f"{m:>12s}" for m in names) + f"   {'b - a mm':>9s} {'sd':>6s}")
rows = sorted(sd, key=lambda n: -abs(H[b]["measures"][n] - H[a]["measures"][n]) / sd[n])
for n in rows:
    g = H[b]["measures"][n] - H[a]["measures"][n]
    print(f"{n:22s} " + " ".join(f"{H[m]['measures'][n]:12.1f}" for m in names) + f"   {g:+9.1f} {g / sd[n]:+6.2f}")
print(f"\nmacros (humanmacro, sd): {b} - {a}, the 16 largest")
Z = {m: humanmacro.read(C[m]) for m in names}
for n in sorted(Z[a], key=lambda n: -abs(Z[b][n] - Z[a][n]))[:16]:
    print(f"{n:22s} " + " ".join(f"{Z[m][n]:+12.2f}" for m in names) + f"   {Z[b][n] - Z[a][n]:+9.2f}")
print("\nthe shipped heads' face measures (68 landmarks, mm, with head scale and style): b - a")
F = {m: humanfit.face_measures(np.asarray(humanfit.state(store.load(m)["base"])["L"], float)) for m in names}
for n in sorted(F[a], key=lambda n: -abs(F[b][n] - F[a][n])):
    print(f"{n:22s} " + " ".join(f"{F[m][n]:12.1f}" for m in names) + f"   {F[b][n] - F[a][n]:+9.1f}")
