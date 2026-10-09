"""Per-macro error of a fit's head against the true head's macros (population sigmas), over the truth subjects.
run.sh macro_table.py "<method prefix>" ...   (methods from MM/out/fits.json; "mean" = saying 0)"""
import json
import sys

import numpy as np

import fits
import mm
import rs
from hifipushie import humanmacro as hm

res = json.loads((mm.MM / "out" / "fits.json").read_text())
want = sys.argv[1:]
cols = {}
truth = {}
for m, r in res.items():
    if not any(m.startswith(w) for w in want) or m.startswith("--"):
        continue
    e = {}
    for s, sc in r.items():
        if not isinstance(sc, dict) or "c" not in sc:
            continue
        if s not in truth:
            truth[s] = hm.read(V=fits.truth(s)["V"])
        z = hm.read(V=rs.head(np.array(sc["c"])))
        for k in hm.NAMES:
            e.setdefault(k, []).append((z[k], truth[s][k]))
    cols[m] = {k: np.array(v) for k, v in e.items()}
names = list(cols)
print("macro error rms (sigmas) | correlation with the true macro, over the truth subjects that have the method")
print(f"{'macro':18s} {'truth rms':>9s} | " + " | ".join(f"{n[:22]:>22s}" for n in names))
out = {}
for k in hm.NAMES:
    row = []
    for n in names:
        a = cols[n][k]
        er = np.sqrt(((a[:, 0] - a[:, 1]) ** 2).mean())
        cc = np.corrcoef(a[:, 0], a[:, 1])[0, 1] if a[:, 0].std() > 1e-9 else float("nan")
        row.append(f"{er:10.2f}  r {cc:5.2f}   ")
        out.setdefault(n, {})[k] = (float(er), float(cc))
    t = np.sqrt((cols[names[0]][k][:, 1] ** 2).mean())
    print(f"{k:18s} {t:9.2f} | " + " | ".join(row))
print(f"{'ALL (rms)':18s} {'':9s} | " + " | ".join(f"{np.sqrt(np.mean([v[0] ** 2 for v in out[n].values()])):10.2f}             " for n in names))
(mm.MM / "out" / "macro_table.json").write_text(json.dumps(out, indent=1))
