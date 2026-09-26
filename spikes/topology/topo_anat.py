"""Loops from the anatomy: its loop planes (armholes, hips from landmarks; hinge creases) cut into the body and kept
by the patched QuadriFlow (QF_FEATURES), sized; ring check at every plane, errors, posed renders with the rings."""
import os
import subprocess
import sys
import time

import numpy as np
from scipy.spatial import cKDTree

import topo_eval as E
import topo_loops as T
from hifipushie import anatomy, kits

TRI = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
TAG = os.environ.get("TAG", "anat")
SKIP = set(filter(None, os.environ.get("SKIP", "").split(",")))
OUT = E.SP / f"{TAG}_{TRI}"
OUT.mkdir(exist_ok=True)

s = kits.expand(E.spec)
planes = []
for p in anatomy.loop_planes(s):
    if p["label"] in SKIP:
        continue
    planes.append((p["label"], p["point"], p["normal"], p["r"]))
    m = np.array([-1.0, 1, 1])
    planes.append((p["label"].replace(".L", ".R"), p["point"] * m, p["normal"] * m, p["r"]))
def closed_cut(V, F, p, n, R):
    """Does the plane's cut, within R of p, make one closed loop (the component nearest p)?"""
    d = (V - p) @ n
    s = np.signbit(d)
    ed = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    fid = np.r_[np.arange(len(F)), np.arange(len(F)), np.arange(len(F))]
    x = s[ed[:, 0]] != s[ed[:, 1]]
    a, b = ed[x, 0], ed[x, 1]
    t = d[a] / (d[a] - d[b])
    P = V[a] + t[:, None] * (V[b] - V[a])
    inside = np.linalg.norm(P - p, axis=1) < R
    key = np.sort(np.c_[a, b], 1)
    uk, idx = np.unique(key, axis=0, return_inverse=True)
    face = fid[x]
    from collections import defaultdict
    per = defaultdict(list)
    for k, f, ins in zip(idx.ravel(), face, inside):
        if ins:
            per[f].append(k)
    from scipy import sparse
    from scipy.sparse.csgraph import connected_components
    pairs = np.array([v for v in per.values() if len(v) == 2])
    if not len(pairs):
        return False
    g = sparse.coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(uk), len(uk)))
    _, comp = connected_components(g, directed=False)
    used = np.unique(pairs)
    Pk = np.zeros((len(uk), 3)); Pk[idx.ravel()] = P
    c = comp[used[np.argmin(np.linalg.norm(Pk[used] - p, axis=1))]]
    deg = np.bincount(pairs[comp[pairs[:, 0]] == c].ravel(), minlength=len(uk))
    return bool((deg[used[comp[used] == c]] == 2).all())


roots = {p["label"] for p in anatomy.loop_planes(s)} - {h for r in anatomy.limb_roots(s) for h in r["chain"][1:]}
moved = []
for lab, p, n, r in planes:
    if lab.replace(".R", ".L") in roots:  # slide down the limb to the first closed ring
        for k in range(0, 21):
            q = p + n * 0.1 * k * r
            if closed_cut(E.HV, E.HF, q, n, 2.2 * r):
                print(f"{lab}: closed {0.1 * k:.1f} r down the limb")
                p = q
                break
        else:
            print(f"{lab}: no closed ring within 2 r")
    moved.append((lab, p, n, r))
planes = moved
V, F, feats = T.slice_mesh(E.HV, E.HF, planes, closed_only=True)
print("featured:", [f[0] for f in feats])
size = E.sizing(k=0.5, curv_rounds=6)[cKDTree(E.HV).query(V)[1]]


def qf(faces):
    E.write_obj(OUT / "high_cut.obj", V, F)
    np.savetxt(OUT / "sizing.txt", size, fmt="%.5f")
    T.write_features(OUT / "features.txt", feats)
    env = dict(os.environ, QF_SIZING=str(OUT / "sizing.txt"), QF_LAMBDA="10", QF_FEATURES=str(OUT / "features.txt"))
    out = OUT / f"qf_{faces}.obj"
    t = time.time()
    r = subprocess.run([str(E.QF), "-i", str(OUT / "high_cut.obj"), "-o", str(out), "-f", str(faces), "-seed", "0",
                        "-adaptive"], env=env, capture_output=True, text=True, timeout=600)
    if r.returncode or not out.exists():
        raise RuntimeError(r.stdout[-2000:] + r.stderr[-2000:])
    print(f"  qf {faces} in {time.time() - t:.0f}s")
    return E.read_obj(out)


m = qf(TRI // 2)
QV, QL, QS = qf(int(TRI // 2 * TRI / len(E.tris(*m))))
rc = T.ring_check(QV, QL, QS, planes)
Tq = E.tris(QV, QL, QS)
e = E.errors(QV, Tq)
rings = sum(v["ring"] for v in rc.values())
label = (f"{E.NAME}: {len(Tq)} tris; mean mm all {e['all'][0]} (max {e['all'][2]}) head {e['head'][0]} hands "
         f"{e['hands'][0]} | rings {rings}/{len(rc)}: " + T.fmt(rc))
print(label)
E.sheet([(label[:260], E.posed_row(TAG, QV, QL, QS, OUT, rings=[v["path"] for v in rc.values() if v["ring"]]))],
        OUT / "compare.png")
np.savez(OUT / "result.npz", verts=QV, loops=QL, sizes=QS)
