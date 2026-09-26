"""Loops where the skin blends: per joint, a harmonic field on the surface (1 where the rig weights are all the
limb's, 0 where they're none of it); its level curves are closed loops around the limb across the blend zone.
They're cut into the high mesh and kept by the patched QuadriFlow (QF_FEATURE_IDS)."""
import os
import subprocess
import sys
import time

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import spsolve
from scipy.spatial import cKDTree

import topo_eval as E
import topo_loops as T

# joint label -> the rig bone whose chain (it and everything below it) is "the limb" there
CHAINS = {"L shoulder": "LeftArm", "R shoulder": "RightArm", "L elbow": "LeftForeArm", "R elbow": "RightForeArm",
          "L knee": "LeftLeg", "R knee": "RightLeg", "L hip": "LeftUpLeg", "R hip": "RightUpLeg"}


def chain_weight(J, W, root):
    names = [b["name"].split(":")[-1] for b in E.bones]
    r = names.index(root)
    inside = {r}
    for i, b in enumerate(E.bones):  # parents come first
        if b["parent"] in inside:
            inside.add(i)
    return (W * np.isin(J, list(inside))).sum(1)


def harmonic(F, n, fixed, values):
    e = E.edges_of(F)
    A = sparse.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
    A = (A + A.T).tocsr()
    L = sparse.diags(np.asarray(A.sum(1)).ravel()) - A
    free = np.flatnonzero(~fixed)
    x = np.zeros(n)
    x[fixed] = values
    x[free] = spsolve(L[free][:, free].tocsc(), -L[free][:, fixed] @ values)
    return x


def fields(V, F, labels, lo=0.03, hi=0.97):
    """{label: harmonic field per vertex} from the rig weights of the limb's chain."""
    t = time.time()
    J, W = E.rig.rig_weights(E.spec, E.bones, V, F)
    print(f"rig weights {time.time() - t:.1f}s")
    out = {}
    for lab in labels:
        w = chain_weight(J, W, CHAINS[lab])
        fixed = (w <= lo) | (w >= hi)
        out[lab] = harmonic(F, len(V), fixed, (w[fixed] >= hi).astype(float))
    return out


def slice_level(V, F, s, level, carry):
    """Cut the mesh along s == level; carry: per-vertex arrays interpolated onto new vertices. Returns V, F,
    carry, and the mask of vertices on the curve."""
    d = s - level
    e_len = np.median(np.linalg.norm(V[F[:, 0]] - V[F[:, 1]], axis=1))
    g = np.zeros(len(V))  # |grad s| per vertex, to snap vertices whose level distance is a small fraction of an edge
    ee = E.edges_of(F)
    np.maximum.at(g, ee[:, 0], np.abs(s[ee[:, 0]] - s[ee[:, 1]]))
    np.maximum.at(g, ee[:, 1], np.abs(s[ee[:, 0]] - s[ee[:, 1]]))
    snap = np.abs(d) < 0.05 * g
    d = d.copy()
    d[snap] = 0
    cache, new, newc = {}, [], {k: [] for k in carry}

    def cut(a, b):
        k = (min(a, b), max(a, b))
        if k not in cache:
            t = d[a] / (d[a] - d[b])
            cache[k] = len(V) + len(new)
            new.append(V[a] + t * (V[b] - V[a]))
            for key, arr in carry.items():
                newc[key].append(arr[a] + t * (arr[b] - arr[a]))
        return cache[k]

    out = []
    for f in F:
        cuts = [k for k in range(3) if d[f[k]] * d[f[(k + 1) % 3]] < 0]
        if not cuts:
            out.append(f)
        elif len(cuts) == 2:
            sv = [x for x in range(3) if x in (cuts[0], (cuts[0] + 1) % 3) and x in (cuts[1], (cuts[1] + 1) % 3)][0]
            a, b, c = f[sv], f[(sv + 1) % 3], f[(sv + 2) % 3]
            m1, m2 = cut(a, b), cut(c, a)
            out += [(a, m1, m2), (m1, b, c), (m1, c, m2)]
        else:
            k = cuts[0]
            a, b, c = f[k], f[(k + 1) % 3], f[(k + 2) % 3]
            m = cut(a, b)
            out += [(a, m, c), (m, b, c)]
    on = np.r_[snap, np.ones(len(new), bool)]
    V = np.r_[V, np.array(new).reshape(-1, 3)]
    carry = {k: np.r_[arr, np.array(newc[k])] if len(newc[k]) else arr for k, arr in carry.items()}
    return V, np.array(out), carry, on


def main_loop(V, F, on, near_point=None):
    """The biggest closed component of on-curve edges (vertices)."""
    e = E.edges_of(F)
    e = e[on[e[:, 0]] & on[e[:, 1]]]
    g = sparse.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(V), len(V)))
    _, comp = connected_components(g, directed=False)
    vs = np.unique(e)
    best = None
    for c in np.unique(comp[vs]):
        m = vs[comp[vs] == c]
        ec = e[comp[e[:, 0]] == c]
        closed = (np.bincount(ec.ravel(), minlength=len(V))[m] == 2).all()
        if closed and (best is None or len(m) > len(best)):
            best = m
    return best


def cut_loops(V, F, flds, levels):
    """Cut every (label, level) curve; returns V, F, feature id per vertex, [(label, level)] by id, fields on V."""
    ids = -np.ones(len(V), int)
    carry = dict(flds)
    names = []
    for lab in flds:
        for lv in levels:
            V, F, carry, on = slice_level(V, F, carry[lab], lv, carry)
            ids = np.r_[ids, -np.ones(len(V) - len(ids), int)]
            loop = main_loop(V, F, on)
            if loop is None:
                print(f"{lab} {lv}: no closed curve")
                continue
            ids[loop] = len(names)
            names.append((lab, lv))
            print(f"{lab} {lv}: loop of {len(loop)} verts")
    idv = ids
    return V, F, idv, names, carry


def ring_check_scalar(V, L, S, sfields, level=0.5, tol=0.3):
    """Per label: the closed edge loop nearest the level curve of s (s per quad vertex), within [level +- tol]."""
    faces, nb, ef = T.quad_topology(L, S)
    out = {}
    for lab, s in sfields.items():
        best, longest, seen = None, 0, set()
        for (a, b) in ef:
            if abs(s[a] - level) > 0.15 or abs(s[b] - level) > 0.15 or abs(s[a] - s[b]) > 0.08 or (a, b) in seen:
                continue
            path, closed = T.walk(a, b, faces, nb, ef)
            for k in range(len(path) - 1):
                seen.add((min(path[k], path[k + 1]), max(path[k], path[k + 1])))
            if closed and np.abs(s[path] - level).max() < tol:
                dev = np.abs(s[path] - level).max()
                if best is None or dev < best[0]:
                    best = (dev, path)
            elif not closed:
                longest = max(longest, len(path))
        out[lab] = ({"ring": True, "dev": round(float(best[0]), 3), "edges": len(best[1]), "path": best[1]} if best
                    else {"ring": False, "longest_open_walk": longest})
    return out


def fmt(rc):
    return "; ".join(f"{k}: " + (f"ring of {v['edges']} (field off level {v['dev']})" if v["ring"]
                                 else f"NO ring (longest walk {v['longest_open_walk']})") for k, v in rc.items())


if __name__ == "__main__":
    TRI = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    labels = os.environ.get("JOINTS", "L shoulder,R shoulder,L elbow,R elbow,L knee,R knee").split(",")
    levels = tuple(float(x) for x in os.environ.get("LEVELS", "0.5").split(","))
    TAG = os.environ.get("TAG", "iso")
    OUT = E.SP / f"{TAG}_{TRI}"
    OUT.mkdir(exist_ok=True)
    lo, hi = (float(x) for x in os.environ.get("LOHI", "0.1,0.9").split(","))
    flds = fields(E.HV, E.HF, labels, lo, hi)
    V, F, idv, names, carried = cut_loops(E.HV, E.HF, flds, levels)
    size = E.sizing(k=0.5, curv_rounds=6)[cKDTree(E.HV).query(V)[1]]

    def qf(faces, feats=True):
        E.write_obj(OUT / "high_cut.obj", V, F)
        np.savetxt(OUT / "sizing.txt", size, fmt="%.5f")
        np.savetxt(OUT / "ids.txt", idv, fmt="%d")
        env = dict(os.environ, QF_SIZING=str(OUT / "sizing.txt"), QF_LAMBDA="10")
        if feats:
            env["QF_FEATURE_IDS"] = str(OUT / "ids.txt")
        out = OUT / f"qf_{faces}.obj"
        r = subprocess.run([str(E.QF), "-i", str(OUT / "high_cut.obj"), "-o", str(out), "-f", str(faces), "-seed", "0",
                            "-adaptive"], env=env, capture_output=True, text=True, timeout=int(os.environ.get("QF_TIMEOUT", 900)))
        if r.returncode or not out.exists():
            raise RuntimeError(r.stdout[-2000:] + r.stderr[-2000:])
        print("  " + " | ".join(l for l in r.stdout.splitlines() if "feature" in l))
        return E.read_obj(out)

    rows = []
    for feats in (False, True):
        m = qf(TRI // 2, feats)
        QV, QL, QS = qf(int(TRI // 2 * TRI / len(E.tris(*m))), feats)
        nn = cKDTree(V).query(QV)[1]
        rc = ring_check_scalar(QV, QL, QS, {lab: carried[lab][nn] for lab in labels})
        Tq = E.tris(QV, QL, QS)
        e = E.errors(QV, Tq)
        label = (f"{'loops as features' if feats else 'no features'} levels {levels}: {len(Tq)} tris; mean mm all "
                 f"{e['all'][0]} (max {e['all'][2]}) head {e['head'][0]} hands {e['hands'][0]} | " + fmt(rc))
        print(label, flush=True)
        rings = [v["path"] for v in rc.values() if v["ring"]]
        rows.append((label, E.posed_row(f"{TAG}_{int(feats)}", QV, QL, QS, OUT, rings=rings)))
        np.savez(OUT / f"result_{int(feats)}.npz", verts=QV, loops=QL, sizes=QS)
    E.sheet(rows, OUT / "compare.png")
