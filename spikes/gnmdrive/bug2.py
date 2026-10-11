import sys

import numpy as np

import drive

case = sys.argv[1]
d, st, cB = drive._load(case)
c1 = drive.apply(st["c"], {"ear_out!": 0.0})
for f in ("head", "brows"):
    rows, rl = drive._rows([st["c"], c1, cB], ["BEFORE", "TRIAL", "TARGET"], cB, f)
    print(f, [float(np.abs(np.asarray(a).astype(float) - np.asarray(b).astype(float)).mean()) for a, b in zip(rows[0], rows[1])])
rows, rl = drive._rows([st["c"], c1, cB], ["BEFORE", "TRIAL", "TARGET"], cB, "brows")
print("again brows", [float(np.abs(np.asarray(a).astype(float) - np.asarray(b).astype(float)).mean()) for a, b in zip(rows[0], rows[1])])
