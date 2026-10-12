"""p2_neck.py: GNM's neck rings (count, height under the chin, girth) and how GNM's ring meets each body's neck."""
import sys
import numpy as np
from hifipushie import base as B, onemesh, store
from p1_measure import gnm_eval, lm, Vt, Jt, g, SKIN

a = onemesh.asset()
lev = a["g_lev"].astype(int)
meta = onemesh._reference()["meta"]
print("meta", meta, "bridge", a["bridge"], "loop_a", len(a["loop_a"]), "loop_c", len(a["loop_c"]))
off = a["offset"].astype(float)
g2f = a["g2f"][:len(lev)]
print("asset offset on GNM verts: max by ring", {k: round(1000 * float(np.linalg.norm(off[g2f[(lev == k) & (g2f >= 0)]], axis=1).max()), 2) for k in range(13, 26)})
print("offset max overall mm (mh, bridge, gnm):", 1000 * np.linalg.norm(off, axis=1).max())
slid = np.linalg.norm(a["g_neutral"] - 0, axis=1)
quads = np.asarray(g["quads"])
adj = {}
for q in quads:
    for i in range(4):
        adj.setdefault(int(q[i]), set()).add(int(q[(i + 1) % 4])); adj.setdefault(int(q[(i + 1) % 4]), set()).add(int(q[i]))

def ring_loop(k):
    ids = [int(v) for v in np.flatnonzero(lev == k)]
    s = set(ids); loop = [ids[0]]; prev = None
    while True:
        nx = [w for w in adj[loop[-1]] if w in s and w != prev and (len(loop) < 3 or w != loop[0] or True)]
        nx = [w for w in nx if w not in loop[1:]]
        if not nx or (nx[0] == loop[0] and len(loop) > 2): break
        cand = [w for w in nx if w != loop[0]] or nx
        if cand[0] == loop[0]: break
        prev = loop[-1]; loop.append(cand[0])
        if len(loop) > len(ids): break
    return loop

def girth(V, k):
    lp = ring_loop(k)
    X = V[lp]
    return float(np.linalg.norm(X - np.roll(X, -1, 0), axis=1).sum()), len(lp), int((lev == k).sum())

chin = lm(Vt, 8)
print("GNM template: ring, n verts, loop ok, girth mm, mean y under chin mm (front y / back y), z front/back")
for k in list(range(0, 31, 1)):
    m = lev == k
    if not m.any(): continue
    X = Vt[m]
    gi, nl, n = girth(Vt, k)
    fr, bk = X[np.argmax(X[:, 2])], X[np.argmin(X[:, 2])]
    print(f" ring {k:2d} n {n:3d} loop {nl:3d} girth {1000*gi:6.1f}  y-chin mean {1000*(X[:,1].mean()-chin[1]):6.1f} front {1000*(fr[1]-chin[1]):6.1f} back {1000*(bk[1]-chin[1]):6.1f}  halfwidth x {1000*np.abs(X[:,0]).max():5.1f}")
R = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])
for mname in sys.argv[1:]:
    base = store.load(mname)["base"]
    params = onemesh.body_params(base)
    bd = onemesh.bound(params)
    V, J = gnm_eval(base["head"].get("identity") or {})
    W = V @ R.T   # world axes, GNM's size, origin GNM's
    print(f"== {mname}")
    for k in (13, 15, 17, 19, 21, 23):
        m = lev == k
        gb = np.linalg.norm(bd["B"][ring_loop(k)] - np.roll(bd["B"][ring_loop(k)], -1, 0), axis=1).sum()
        gg = girth(V, k)[0]
        t = bd["B"][m].mean(0) - W[m].mean(0)
        D = bd["B"][m] - (W[m] + t)
        print(f" ring {k}: body's girth {1000*gb:.0f} mm, GNM's own {1000*gg:.0f} ({100*(gg/gb-1):+.1f} %), after the best shift: rms {1000*np.sqrt((D**2).sum(1).mean()):.1f} max {1000*np.linalg.norm(D,axis=1).max():.1f} mm; shift puts GNM eye mid at z {1000*(0.5*(J[2]+J[3])@R.T + t)[2]:.0f} (body's eye z {1000*bd['eyes'][:,2].mean():.0f}), top at {1000*(W[SKIN][:,2].max()+t[2]):.0f}, y of eyes {1000*(0.5*(J[2]+J[3])@R.T + t)[1]:.0f} vs {1000*bd['eyes'][:,1].mean():.0f}")
