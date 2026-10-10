"""m3cost.py <prior npz>...: what the local controls cost as IDENTITY under each prior (faces5 M3 judge). For every hand
slider / baked op / extension field of faceslide.fields() (both sides summed, +1 unit), the MAP identity move that makes
it over its region (|d| > 3% of its max, exterior skin; noise 0.05 mm): the share made and its cost (Mahalanobis, sd)
under GNM's N(0, I) and under each prior file; then Tess's (f3_t1) and Garrett's (fs_gj8) slider values times that,
and their identities' own Mahalanobis under each prior. A wall at 2.5 sd: a slider whose identity cost is past it is
'expressible but improbable'."""
import os
import sys

import numpy as np

import perc
from hifipushie import faceslide, store

NOISE = float(os.environ.get("NOISE", "0.00005"))
HC = [i for i, x in enumerate(perc.ID_NAMES) if x.startswith("head")]
IB = perc.IB[HC]
NC = len(HC)
N = perc.N
priors = {"GNM": np.eye(NC)}
for p in sys.argv[1:]:
    z = np.load(p)
    priors[os.path.basename(p).replace(".npz", "")] = z["cov"][:NC, :NC]
Sinv = {k: np.linalg.inv(S) for k, S in priors.items()}
fields = faceslide.fields()
people = {}
for who, m in (("tess", "f3_t1"), ("garrett", "fs_gj8")):
    h = store.load(m)["base"]["head"]
    people[who] = (h.get("sliders") or {}, perc.head(who)[HC])
rows = []
for k, (dR, dL) in sorted(fields.items()):
    d = (dR + dL)[:N]
    m = np.linalg.norm(d, axis=1)
    if m.max() < 1e-7:
        continue
    reg = (m > 0.03 * m.max()) & perc.EXT
    y = d[reg].ravel()
    B = IB[:, reg].reshape(NC, -1)
    BBt = B @ B.T
    By = B @ y
    row = {"name": k, "mm": float(m.max() * 1e3)}
    for nm, S in priors.items():
        c = S @ np.linalg.solve(BBt @ S + NOISE ** 2 * np.eye(NC), By)
        r = y - B.T @ c
        row[nm] = (float(1 - r @ r / (y @ y)), float(np.sqrt(c @ Sinv[nm] @ c)))
    rows.append(row)
names = list(priors)
print(f"{'field':24s} {'max mm':>6s} " + " ".join(f"{n[:16]:>18s}" for n in names) + "   (share made, cost sd per unit)")
for r in rows:
    print(f"{r['name']:24s} {r['mm']:6.2f} " + " ".join(f"{r[n][0]:7.2f} {r[n][1]:9.1f} " for n in names))
print()
for who, (sl, c) in people.items():
    print(f"{who}: identity Mahalanobis " + ", ".join(f"{n} {np.sqrt(c @ Sinv[n] @ c):.1f}" for n in names)
          + f" (120 comps used; a typical face ~ sqrt(170) = 13)")
    for r in rows:
        v = sl.get(r["name"])
        if v is None or abs(float(v)) < 0.05:
            continue
        print(f"   {r['name']:22s} {float(v):+.2f} -> identity cost " + ", ".join(
            f"{n} {abs(float(v)) * r[n][1]:.1f} sd ({r[n][0]:.2f} made)" for n in names))
