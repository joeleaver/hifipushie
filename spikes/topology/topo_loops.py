"""Feature loops for QuadriFlow: joint planes sliced into the high mesh, kept as edge loops by the patched build
(QF_FEATURES); and a ring check on quad meshes (does an edge loop close around the limb at the joint?)."""
import json
from pathlib import Path

import numpy as np
from scipy.sparse.csgraph import connected_components
from scipy import sparse
from scipy.spatial import cKDTree

import topo_eval as E

JOINTS = {"L elbow": ("LeftArm", "LeftForeArm", "LeftHand"), "R elbow": ("RightArm", "RightForeArm", "RightHand"),
          "L knee": ("LeftUpLeg", "LeftLeg", "LeftFoot"), "R knee": ("RightUpLeg", "RightLeg", "RightFoot")}


def unit(v):
    return v / np.linalg.norm(v)


def heads():
    return {b["name"].split(":")[-1]: np.asarray(b["head"], float) for b in E.bones}


def limb_radius(p, n):
    """Median distance from p to where rays in the plane (normal n) leave the body."""
    a = unit(np.cross(n, [0, 0, 1.0] if abs(n[2]) < 0.9 else [1.0, 0, 0]))
    b = np.cross(n, a)
    ang = np.linspace(0, 2 * np.pi, 24, endpoint=False)
    dirs = np.cos(ang)[:, None] * a + np.sin(ang)[:, None] * b
    t = np.linspace(0, 0.3, 300)
    f = E.sdf.field_at(E.prims, p + t[None, :, None] * dirs[:, None, :], margin=0.02)
    out = [t[np.flatnonzero(row > 0)[0]] if (row > 0).any() else 0.3 for row in f]
    return float(np.median(out))


def joint_planes(names=tuple(JOINTS), offsets=(0.0,)):
    """(label, point, normal, radius of the limb there): the crease plane bisects the two bones; offsets (in limb
    radii) add parallel planes along the bisector's normal."""
    H = heads()
    out = []
    for lab in names:
        a, j, c = (H[x] for x in JOINTS[lab])
        n = unit(unit(j - a) + unit(c - j))
        r = limb_radius(j, n)
        for o in offsets:
            out.append((f"{lab}{'' if o == 0 else f' {o:+g}'}", j + o * r * n, n, r))
    return out


def slice_mesh(V, F, planes, reach=2.2, closed_only=False):
    """Cut each plane into the mesh where it crosses within reach x the limb radius of its point; returns
    (V, F, [(label, p, n, R)]) with R the radius that holds just the loop around the limb (the component of the
    cut nearest the point)."""
    V = V.copy()
    F = F.copy()
    feats = []
    for lab, p, n, r in planes:
        R = reach * r
        d = (V - p) @ n
        dist = np.linalg.norm(V - p, axis=1)
        el = np.median(np.linalg.norm(V[F[:, 0]] - V[F[:, 1]], axis=1))
        snap = (dist < R) & (np.abs(d) < 0.2 * el)
        V[snap] -= d[snap, None] * n
        d[snap] = 0
        cache = {}

        def cut(a, b):
            k = (min(a, b), max(a, b))
            if k not in cache:
                t = d[a] / (d[a] - d[b])
                cache[k] = len(V) + len(new)
                new.append(V[a] + t * (V[b] - V[a]))
            return cache[k]

        new = []
        e_cut = lambda a, b: d[a] * d[b] < 0 and np.linalg.norm(
            V[a] + d[a] / (d[a] - d[b]) * (V[b] - V[a]) - p) < R
        out = []
        for f in F:
            cuts = [k for k in range(3) if e_cut(f[k], f[(k + 1) % 3])]
            if not cuts:
                out.append(f)
                continue
            if len(cuts) == 2:  # the lone vertex is the one shared by both cut edges
                s =[x for x in range(3) if x in (cuts[0], (cuts[0] + 1) % 3) and x in (cuts[1], (cuts[1] + 1) % 3)][0]
                a, b, c = f[s], f[(s + 1) % 3], f[(s + 2) % 3]
                m1, m2 = cut(a, b), cut(c, a)
                out += [(a, m1, m2), (m1, b, c), (m1, c, m2)]
            else:  # one cut edge: split through the opposite vertex
                k = cuts[0]
                a, b, c = f[k], f[(k + 1) % 3], f[(k + 2) % 3]
                m = cut(a, b)
                out += [(a, m, c), (m, b, c)]
        V = np.r_[V, np.array(new).reshape(-1, 3)]
        F = np.array(out)
        # the loop: on-plane edges near p, the connected component nearest p
        d = (V - p) @ n
        on = (np.abs(d) < 1e-9) & (np.linalg.norm(V - p, axis=1) < R)
        e = E.edges_of(F)
        e = e[on[e[:, 0]] & on[e[:, 1]]]
        if not len(e):
            print(f"{lab}: plane cut nothing")
            continue
        g = sparse.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(V), len(V)))
        _, comp = connected_components(g, directed=False)
        vs = np.unique(e)
        best = comp[vs[np.argmin(np.linalg.norm(V[vs] - p, axis=1))]]
        mine = vs[comp[vs] == best]
        Rc = 1.03 * np.linalg.norm(V[mine] - p, axis=1).max()
        others = vs[(comp[vs] != best) & (np.linalg.norm(V[vs] - p, axis=1) < Rc)]
        deg = np.bincount(e[comp[e[:, 0]] == best].ravel(), minlength=len(V))[mine]
        print(f"{lab}: loop of {len(mine)} verts, closed={bool((deg == 2).all())}, R {Rc * 1000:.0f} mm"
              + (f", {len(others)} other on-plane verts inside R" if len(others) else ""))
        if closed_only and not (deg == 2).all():
            continue
        feats.append((lab, p, n, Rc))
    return V, F, feats


def write_features(path, feats):
    np.savetxt(path, [np.r_[p, n, R] for _, p, n, R in feats], fmt="%.9f")


# ---- ring check ----
def quad_topology(L, S):
    st = np.r_[0, np.cumsum(S)[:-1]]
    faces = [L[s:s + k] for s, k in zip(st, S)]
    nb, ef = {}, {}
    for fi, f in enumerate(faces):
        for k in range(len(f)):
            a, b = int(f[k]), int(f[(k + 1) % len(f)])
            nb.setdefault(a, set()).add(b)
            nb.setdefault(b, set()).add(a)
            ef.setdefault((min(a, b), max(a, b)), []).append(fi)
    return faces, nb, ef


def walk(u, v, faces, nb, ef, limit=600):
    """Follow the edge loop through (u, v) until it closes, hits a pole (valence != 4) or a triangle."""
    path = [u, v]
    while len(path) < limit:
        if len(nb[v]) != 4:
            return path, False
        ws = set()
        for fi in ef[(min(u, v), max(u, v))]:
            f = [int(x) for x in faces[fi]]
            if len(f) != 4:
                return path, False
            i = f.index(v)
            ws.add(f[(i + 1) % 4] if f[(i - 1) % 4] == u else f[(i - 1) % 4])
        rest = nb[v] - {u} - ws
        if len(rest) != 1:
            return path, False
        u, v = v, rest.pop()
        if v == path[0]:
            return path, True
        path.append(v)
    return path, False


def ring_check(V, L, S, planes):
    """Per joint: the best closed edge loop around the limb near the crease plane (max distance of its vertices
    from the plane, in limb radii and mm), or the longest open walk if none closes."""
    faces, nb, ef = quad_topology(L, S)
    out = {}
    for lab, p, n, r in planes:
        d = (V - p) @ n
        dist = np.linalg.norm(V - p, axis=1)
        best, longest = None, 0
        seen = set()
        for (a, b) in ef:
            if abs(d[a] + d[b]) / 2 > 0.4 * r or max(dist[a], dist[b]) > 2.2 * r:
                continue
            ev = V[b] - V[a]
            if abs(ev @ n) > 0.4 * np.linalg.norm(ev) or (a, b) in seen:
                continue
            path, closed = walk(a, b, faces, nb, ef)
            for k in range(len(path) - 1):
                seen.add((min(path[k], path[k + 1]), max(path[k], path[k + 1])))
            if closed and dist[path].max() < 3 * r:
                dev = np.abs(d[path]).max()
                if best is None or dev < best[0]:
                    best = (dev, path)
            elif not closed:
                longest = max(longest, len(path))
        if best:
            out[lab] = {"ring": True, "off_plane_r": round(best[0] / r, 2), "off_plane_mm": round(best[0] * 1000, 1),
                        "edges": len(best[1]), "path": best[1]}
        else:
            out[lab] = {"ring": False, "longest_open_walk": longest}
    return out


def fmt(rc):
    return "; ".join(f"{k}: " + (f"ring of {v['edges']}, off plane {v['off_plane_mm']} mm ({v['off_plane_r']} r)"
                                 if v["ring"] else f"NO ring (longest walk {v['longest_open_walk']})")
                     for k, v in rc.items())
