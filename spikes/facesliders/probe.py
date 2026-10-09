"""probe.py: GNM's topology round the left eye: the skin's boundary loop at the eye, then topological rings outward
(quad distance), each ring's vertex count, closedness and height above the margin at the pupil column (template)."""
import numpy as np
from hifipushie import base

g = base._gnm_data()
V = g["template_vertex_positions"]; Q = g["quads"]
print("V", V.shape, "Q", Q.shape, "groups", list(g["groups"]))
skin = g["skin"]
lm = lambda i: sum(w * V[int(v)] for v, w in zip(g["lm68"][i][0::2], g["lm68"][i][1::2]))
print("lm 43,44 (left upper lid?)", lm(43), lm(44), "lm 37", lm(37), "brow 24", lm(24))
# edges of skin quads
Qs = Q[skin[Q].all(1)]
E = np.sort(np.stack([Qs, np.roll(Qs, -1, 1)], -1).reshape(-1, 2), 1)
u, c = np.unique(E, axis=0, return_counts=True)
bd = u[c == 1]
print("skin boundary edges", len(bd))
from collections import defaultdict
adj = defaultdict(set)
for a, b in bd: adj[a].add(b); adj[b].add(a)
seen = set(); loops = []
for s in adj:
    if s in seen: continue
    comp = [s]; seen.add(s); st = [s]
    while st:
        x = st.pop()
        for y in adj[x]:
            if y not in seen: seen.add(y); comp.append(y); st.append(y)
    loops.append(comp)
for L in loops:
    P = V[L]; print("boundary loop", len(L), "centre", P.mean(0).round(4))
ex = g["groups"]["skin_exterior"] > 0.5
Qe = Q[ex[Q].all(1)]
E = np.sort(np.stack([Qe, np.roll(Qe, -1, 1)], -1).reshape(-1, 2), 1)
u, c = np.unique(E, axis=0, return_counts=True)
bd = u[c == 1]
adj = defaultdict(set)
for a, b in bd: adj[a].add(b); adj[b].add(a)
seen = set(); loops = []
for s in adj:
    if s in seen: continue
    comp = [s]; seen.add(s); st = [s]
    while st:
        x = st.pop()
        for y in adj[x]:
            if y not in seen: seen.add(y); comp.append(y); st.append(y)
    loops.append(comp)
for L in loops:
    print("exterior boundary loop", len(L), "centre", V[L].mean(0).round(4))
# left eye margin: the loop whose centre x>0 near the eye
eyeL = [L for L in loops if abs(V[L].mean(0)[0] - 0.031) < 0.01 and abs(V[L].mean(0)[1] - 0.304) < 0.01][0]
# vertex adjacency over exterior quads
vadj = defaultdict(set)
for q in Qe:
    for k in range(4): vadj[q[k]].add(q[(k + 1) % 4]); vadj[q[(k + 1) % 4]].add(q[k])
ring = set(eyeL); allr = set(eyeL); rings = [sorted(ring)]
for k in range(12):
    nxt = set()
    for v in ring: nxt |= vadj[v]
    nxt -= allr; allr |= nxt; ring = nxt; rings.append(sorted(ring))
x0 = 0.5 * (lm(43)[0] + lm(44)[0]); mz = 0.5 * (lm(43) + lm(44))
for k, r in enumerate(rings):
    P = V[r]; up = P[(P[:, 1] > mz[1] - 0.002)]
    col = up[np.argsort(np.abs(up[:, 0] - x0))[:1]]
    print(k, "n", len(r), "height above lid mid (mm) at pupil col", np.round(1000 * (col[:, 1] - mz[1]), 2), "x", np.round(1000*col[:,0],1))
np.save("/mnt/data/hifipushie/facesliders/out/rings_L.npy", np.array([np.array(r) for r in rings], dtype=object), allow_pickle=True)
