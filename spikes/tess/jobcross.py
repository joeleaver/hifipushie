"""jobcross.py <job dir>: cloth edges of a queued job's START that pass through its collider's triangles (bodyV0 /
bodyT; the body's triangles first, then the garment under it), per piece and per collider part (body / under)."""
import json, sys
from collections import Counter
import numpy as np
from scipy.spatial import cKDTree

jd = sys.argv[1]
a = np.load(jd + "/in.npz"); J = json.load(open(jd + "/job.json"))
X, F, pc, names = a["X"], a["F"], a["piece"], J["pieces"]
V = a["bodyV0"] if "bodyV0" in a.files else a["bodyV"]
T = a["bodyT"]
nb = int(sys.argv[2]) if len(sys.argv) > 2 else None
E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
P0, P1 = X[E[:, 0]], X[E[:, 1]]
C = V[T].mean(1)
_, cand = cKDTree(C).query(0.5 * (P0 + P1), k=12)
hits = Counter()
for c in range(cand.shape[1]):
    t = cand[:, c]
    A, B, Cc = V[T[t, 0]], V[T[t, 1]], V[T[t, 2]]
    d = P1 - P0
    e1, e2 = B - A, Cc - A
    h = np.cross(d, e2)
    det = (e1 * h).sum(1)
    ok = np.abs(det) > 1e-14
    inv = np.where(ok, 1 / np.where(ok, det, 1), 0)
    s = P0 - A
    u = (s * h).sum(1) * inv
    q = np.cross(s, e1)
    v = (d * q).sum(1) * inv
    w = (e2 * q).sum(1) * inv
    m = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (w >= 0) & (w <= 1)
    for i in np.where(m)[0]:
        part = "body" if nb is None or t[i] < nb else "under"
        hits[(names[pc[E[i, 0]]], part)] += 1
print("start edges through the collider:", dict(hits))
