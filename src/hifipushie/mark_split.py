"""STEP 5's cut on the toile mesh (mark.py has the step): ONE mesh for the whole toile, a region label per face; a mark
is a scalar field g on the toile whose zero set is the seam line, applied to one named region. `split` inserts a vertex
on every edge of that region the zero set crosses (an EXACT clip: no edge paths, no staircase), re-triangulates every
face touching an inserted vertex (the neighbours too, so no T-junction is left), and labels the region's faces by the
sign of g. `regions` gives the region's connected parts when faces of opposite sign are not neighbours (a mask leaves a
face outside the mark joined to every neighbour). Pieces stay in one mesh, so a seam is the edges two labels share."""
from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

SNAP_T = 0.05      # a crossing this near an edge's end moves to the vertex (no sliver triangles)
MIN_SHARE = 0.02   # a part of a split region under this share of its area is an island: joined back across the mark


def areas(V, F):
    return 0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1)


def face_edges(F):
    """(unique sorted edges (k, 2), for each face its 3 edge ids (m, 3))."""
    E = np.sort(np.stack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1).reshape(-1, 2), axis=1)
    u, inv = np.unique(E, axis=0, return_inverse=True)
    return u, inv.reshape(-1, 3)


def edge_faces(F):
    """(edges (k, 2), faces per edge (k, 2), -1 where an edge has one face)."""
    E, fe = face_edges(F)
    ef = -np.ones((len(E), 2), int)
    flat = fe.ravel()
    fid = np.repeat(np.arange(len(F)), 3)
    o = np.argsort(flat, kind="stable")
    first = np.r_[True, flat[o][1:] != flat[o][:-1]]
    ef[flat[o][first], 0] = fid[o][first]
    ef[flat[o][~first], 1] = fid[o][~first]
    return E, ef


def _fan(ring, V):
    """A convex polygon's triangles from the apex that leaves none degenerate."""
    best, out = -1.0, None
    for a in range(len(ring)):
        tri = [(ring[a], ring[(a + k) % len(ring)], ring[(a + k + 1) % len(ring)]) for k in range(1, len(ring) - 1)]
        T = np.array(tri)
        m = areas(V, T).min()
        if m > best:
            best, out = m, tri
    return out


def split(V, F, lab, region, g, mask=None):
    """(V, F, lab, sign per face, mask per face): region's faces (mask True) cut exactly on g's zero set."""
    g = np.array(g, float)
    inreg = (lab == region) & (np.ones(len(F), bool) if mask is None else mask)
    E, fe = face_edges(F)
    for _ in range(2):  # snap near-end crossings to the vertex
        cand = np.unique(fe[inreg])
        a, b = E[cand, 0], E[cand, 1]
        x = g[a] * g[b] < 0
        t = np.where(x, g[a] / np.where(x, g[a] - g[b], 1), 0.5)
        g[a[x & (t < SNAP_T)]] = 0.0
        g[b[x & (t > 1 - SNAP_T)]] = 0.0
    cand = np.unique(fe[inreg])
    a, b = E[cand, 0], E[cand, 1]
    x = g[a] * g[b] < 0
    cut_e = cand[x]
    t = g[a[x]] / (g[a[x]] - g[b[x]])
    newv = len(V) + np.arange(len(cut_e))
    V = np.r_[V, V[a[x]] + t[:, None] * (V[b[x]] - V[a[x]])]
    g = np.r_[g, np.zeros(len(cut_e))]
    on = -np.ones(len(E), int)
    on[cut_e] = newv
    touched = np.where((on[fe] >= 0).any(1))[0]
    keep = np.setdiff1d(np.arange(len(F)), touched)
    nF, nlab, nmask = [F[keep]], [lab[keep]], [inreg[keep]]
    for f in touched:
        ring = []
        for k in range(3):
            ring.append(F[f, k])
            if on[fe[f, k]] >= 0:
                ring.append(on[fe[f, k]])
        zs = [i for i, v in enumerate(ring) if g[v] == 0]
        if inreg[f] and len(zs) == 2 and (zs[1] - zs[0]) not in (1, len(ring) - 1):
            i, j = zs
            parts = [ring[i:j + 1], ring[j:] + ring[:i + 1]]
        else:
            parts = [ring]
        for p in parts:
            tris = [tuple(p)] if len(p) == 3 else _fan(p, V)
            nF.append(np.array(tris, int))
            nlab.append(np.full(len(tris), lab[f]))
            nmask.append(np.full(len(tris), inreg[f]))
    F2 = np.concatenate(nF)
    lab2, m2 = np.concatenate(nlab), np.concatenate(nmask)
    ok = areas(V, F2) > 1e-14
    F2, lab2, m2 = F2[ok], lab2[ok], m2[ok]
    sg = np.sign(g[F2].sum(1))
    return V, F2, lab2, sg, m2, int(len(cut_e))


def regions(V, F, faces, sg, mask):
    """Connected parts of `faces` (indices) where neighbours of opposite sign (both under the mark) are apart; islands
    (< MIN_SHARE of the area) joined back to the part they touch most. (part id per face in `faces`, area per part)."""
    sub = F[faces]
    E, ef = edge_faces(sub)
    two = ef[:, 1] >= 0
    f0, f1 = ef[two, 0], ef[two, 1]
    s, m = sg[faces], mask[faces]
    apart = m[f0] & m[f1] & (s[f0] * s[f1] < 0)
    n = len(faces)

    def comps(join):
        A = coo_matrix((np.ones(int(join.sum())), (f0[join], f1[join])), shape=(n, n))
        return connected_components(A, directed=False)[1]
    c = comps(~apart)
    ar = np.bincount(c, weights=areas(V, sub))
    for _ in range(4):
        small = np.where(ar < MIN_SHARE * ar.sum())[0]
        if not len(small):
            break
        join = ~apart | (np.isin(c[f0], small) | np.isin(c[f1], small))
        c = comps(join)
        ar = np.bincount(c, weights=areas(V, sub))
    return c, ar


def chains(E):
    """Edges (k, 2) as vertex chains, broken where a vertex has other than two edges (a closed loop comes back to its
    start)."""
    from collections import defaultdict
    nb = defaultdict(list)
    for i, (a, b) in enumerate(E):
        nb[int(a)].append((int(b), i))
        nb[int(b)].append((int(a), i))
    used = np.zeros(len(E), bool)
    out = []
    for s in [v for v in nb if len(nb[v]) != 2] + list(nb):
        for w, i in nb[s]:
            if used[i]:
                continue
            used[i] = True
            ch, cur = [s, w], w
            while len(nb[cur]) == 2 and cur != s:
                nxt = [(x, j) for x, j in nb[cur] if not used[j]]
                if not nxt:
                    break
                cur, j = nxt[0]
                used[j] = True
                ch.append(cur)
            out.append(ch)
    return out


def seam_runs(F, lab, names):
    """{(piece a, piece b) sorted by label: [vertex chains]} where two pieces share edges, and {piece: [chains]} of the
    edges only one face uses (the free edges: hem, neckline, opening, sleeve ends)."""
    E, ef = edge_faces(F)
    two = ef[:, 1] >= 0
    la = lab[ef[:, 0]]
    lb = np.where(two, lab[np.maximum(ef[:, 1], 0)], -1)
    pairs, free = {}, {}
    sh = two & (la != lb)
    for a, b in sorted({tuple(sorted((int(x), int(y)))) for x, y in zip(la[sh], lb[sh])}):
        m = sh & (((la == a) & (lb == b)) | ((la == b) & (lb == a)))
        pairs[(names[a], names[b])] = chains(E[m])
    for p in np.unique(la[~two]):
        free[names[int(p)]] = chains(E[~two & (la == p)])
    return pairs, free
