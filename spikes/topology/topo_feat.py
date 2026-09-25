"""Sized QuadriFlow with joint loops as feature constraints: ring check, errors, posed renders with the rings."""
import os
import subprocess
import sys
import time

import numpy as np
from scipy.spatial import cKDTree

import topo_eval as E
import topo_loops as T

TRI = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
OFFS = tuple(float(x) for x in os.environ.get("OFFSETS", "0").split(","))
TAG = os.environ.get("TAG", "feat")
OUT = E.SP / f"{TAG}_{TRI}"
OUT.mkdir(exist_ok=True)


def qf(V, F, faces, size, feats):
    src = OUT / "high_cut.obj"
    E.write_obj(src, V, F)
    env = dict(os.environ)
    np.savetxt(OUT / "sizing.txt", size, fmt="%.5f")
    env["QF_SIZING"] = str(OUT / "sizing.txt")
    env["QF_LAMBDA"] = "10"
    if feats:
        T.write_features(OUT / "features.txt", feats)
        env["QF_FEATURES"] = str(OUT / "features.txt")
    out = OUT / f"qf_{faces}.obj"
    r = subprocess.run([str(E.QF), "-i", str(src), "-o", str(out), "-f", str(faces), "-seed", "0", "-adaptive"],
                       env=env, capture_output=True, text=True, timeout=1800)
    if r.returncode or not out.exists():
        raise RuntimeError(r.stdout[-2000:] + r.stderr[-2000:])
    print("  " + " | ".join(l for l in r.stdout.splitlines() if "feature" in l))
    return E.read_obj(out)


planes = T.joint_planes(offsets=OFFS)
t = time.time()
V, F, feats = T.slice_mesh(E.HV, E.HF, planes)
print(f"sliced {len(E.HF)} -> {len(F)} faces, {time.time() - t:.1f}s")
size0 = E.sizing(k=0.5, curv_rounds=6)
size = size0[cKDTree(E.HV).query(V)[1]]
t = time.time()
m = qf(V, F, TRI // 2, size, feats)
m = qf(V, F, int(TRI // 2 * TRI / len(E.tris(*m))), size, feats)
print(f"qf with loops {time.time() - t:.1f}s")
crease = T.joint_planes()
QV, QL, QS = m
rc = T.ring_check(QV, QL, QS, crease)
Tq = E.tris(QV, QL, QS)
e = E.errors(QV, Tq)
label = (f"{TAG} offsets {OFFS}: {len(Tq)} tris, {(QS == 4).sum()}/{len(QS)} quads; mean/p95 mm all {e['all'][0]}/"
         f"{e['all'][1]} (max {e['all'][2]}) rest {e['rest'][0]} head {e['head'][0]} hands {e['hands'][0]} | " + T.fmt(rc))
print(label)
rings = [v["path"] for v in rc.values() if v["ring"]]
E.sheet([(label, E.posed_row(TAG, QV, QL, QS, OUT, rings=rings))], OUT / "compare.png")
np.savez(OUT / "result.npz", verts=QV, loops=QL, sizes=QS)
