import numpy as np
from collections import Counter
from hifipushie import gnmloops, assets, base
z = np.load(assets.path("gnm", base.GNM)); Q = np.asarray(z["quads"], int); V = z["template_vertex_positions"]
R = gnmloops._rings(Q)
for i, r in enumerate(R):
    c = Counter(q for q, _ in r)
    dup = [q for q, n in c.items() if n > 1]
    print(i, len(r), "self-crossings", len(dup), [np.round(1000 * V[Q[q]].mean(0)).tolist() for q in dup][:4])
for i in range(3):
    for j in range(i + 1, 3):
        s = set(q for q, _ in R[i]) & set(q for q, _ in R[j])
        print(i, j, "shared", len(s), [np.round(1000 * V[Q[q]].mean(0)).tolist() for q in s][:4])
