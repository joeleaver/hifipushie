"""rings.py: edge rings (the strips a new edge loop would cut) through vertical edges on the left eye's pupil column
above the upper lid: each ring's length, closedness, extent, and the heights it spans at the pupil column."""
import numpy as np
from collections import defaultdict
from hifipushie import base

g = base._gnm_data()
V = g["template_vertex_positions"]; Q = g["quads"]
lm = lambda i: sum(w * V[int(v)] for v, w in zip(g["lm68"][i][0::2], g["lm68"][i][1::2]))
mz = 0.5 * (lm(43) + lm(44))
ef = defaultdict(list)  # edge -> quads
for qi, q in enumerate(Q):
    for k in range(4):
        ef[tuple(sorted((q[k], q[(k + 1) % 4])))].append((qi, k))


def walk(e0):
    """the edge ring from e0, both ways: list of edges, closed?"""
    out = [e0]; closed = False
    for direction in (0, 1):
        e = e0; prevq = None
        qs = ef[e]
        if len(qs) <= direction: break
        qi, k = qs[direction]
        while True:
            q = Q[qi]
            opp = tuple(sorted((q[(k + 2) % 4], q[(k + 3) % 4])))
            if opp == e0: closed = True; break
            (out.append if direction == 0 else (lambda x: out.insert(0, x)))(opp)
            nq = [x for x in ef[opp] if x[0] != qi]
            if len(nq) != 1 or len(out) > 3000: break
            qi, k = nq[0]
            e = opp
        if closed: break
    return out, closed


# vertical edges near the pupil column x = mz[0], y from margin to brow
x0 = mz[0]
cands = []
for e in ef:
    a, b = V[e[0]], V[e[1]]
    if not (g["groups"]["skin_exterior"][list(e)] > 0.5).all(): continue
    if abs(0.5 * (a[0] + b[0]) - x0) < 0.0015 and abs(a[0] - b[0]) < 0.0012 and a[2] > 0.09:
        lo, hi = sorted((a[1], b[1]))
        if mz[1] + 0.001 < 0.5 * (lo + hi) < mz[1] + 0.02:
            cands.append((lo - mz[1], hi - mz[1], e))
cands.sort()
for lo, hi, e in cands:
    r, closed = walk(e)
    P = V[np.array(r).ravel()]
    print(f"span {1000*lo:5.2f}-{1000*hi:5.2f} mm  ring {len(r)} edges closed={closed} x {1000*P[:,0].min():.0f}..{1000*P[:,0].max():.0f} y {1000*(P[:,1].min()-mz[1]):.0f}..{1000*(P[:,1].max()-mz[1]):.0f} z {1000*P[:,2].min():.0f}..{1000*P[:,2].max():.0f}")
print("SEEDS")
for lo, hi, e in cands:
    if 0.005 < lo < 0.0095:
        r, closed = walk(e)
        print(1000 * lo, 1000 * hi, tuple(int(x) for x in e), len(r))
