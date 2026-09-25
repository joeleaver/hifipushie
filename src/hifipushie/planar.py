"""Flat regions of a triangle mesh, in numpy (no Blender): export_asset dissolves them to ngons before the collapse
decimation, so it spends nothing on flat walls. Runs per part in parallel in our own process (`flatten`), before
Blender starts: regions never span two parts (parts share no vertices)."""

from __future__ import annotations

import numpy as np


def _components(n, a, b):
    """Connected component label per node (min node index) of the graph with edges (a, b): hooking plus pointer
    jumping, a few passes over the edges instead of a Python BFS."""
    lab = np.arange(n)
    while True:
        la, lb = lab[a], lab[b]
        hi, lo = np.maximum(la, lb), np.minimum(la, lb)
        diff = hi != lo
        if not diff.any():
            return lab
        np.minimum.at(lab, hi[diff], lo[diff])
        while True:
            nxt = lab[lab]
            if (nxt == lab).all():
                break
            lab = nxt


def _neighbours(indptr, nbr, f):
    """(source, neighbour) pairs of the faces `f` in a CSR adjacency."""
    cnt = indptr[f + 1] - indptr[f]
    src = np.repeat(f, cnt)
    off = np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    return src, nbr[np.repeat(indptr[f], cnt) + off]


def planar_regions(V, F, plane_tol, angle_deg=0.5, min_faces=8, rounds=40):
    """Region label per face (-1: none) for groups of connected faces that lie on one plane: every face's normal
    within `angle_deg` of its region's SEED face and its centre within `plane_tol` of the seed's plane. Testing
    against the seed rather than neighbour to neighbour keeps gently curved organic surfaces from chaining into
    one region. Regions are disks (V - E + F = 1: ones with holes, like a wall round a window, are split), so each
    dissolves to one simple ngon."""
    nf = len(F)
    e1, e2 = V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]
    nrm = np.cross(e1, e2)
    area = np.linalg.norm(nrm, axis=1)
    tiny = area < 1e-12
    nrm = nrm / np.maximum(area, 1e-30)[:, None]
    cen = V[F].mean(1)
    cos_t = np.cos(np.radians(angle_deg))

    # manifold edges (exactly two faces) as face pairs
    he = F[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2)
    key = np.minimum(he[:, 0], he[:, 1]).astype(np.int64) * len(V) + np.maximum(he[:, 0], he[:, 1])
    order = np.argsort(key, kind="stable")
    ks = key[order]
    first = np.r_[True, ks[1:] != ks[:-1]]
    run = np.diff(np.r_[np.flatnonzero(first), len(ks)])
    start = np.flatnonzero(first)[run == 2]
    fa, fb = order[start] // 3, order[start + 1] // 3

    def fits(f, n0, c0):
        """Faces `f` against reference normals/centres: parallel (degenerate faces skip that) and in plane."""
        par = (nrm[f] * n0).sum(1) > cos_t
        return (par | tiny[f]) & (np.abs(((cen[f] - c0) * n0).sum(1)) < plane_tol)

    ok = fits(fa, nrm[fb], cen[fb]) & fits(fb, nrm[fa], cen[fa])
    ok &= ~(tiny[fa] & tiny[fb])
    a, b = np.r_[fa[ok], fb[ok]], np.r_[fb[ok], fa[ok]]
    o = np.argsort(a, kind="stable")
    a, b = a[o], b[o]
    indptr = np.searchsorted(a, np.arange(nf + 1))

    label = np.full(nf, -1)
    pool = np.zeros(nf, bool)
    pool[a] = True
    nreg = 0
    for _ in range(rounds):
        sel = pool[a] & pool[b]
        comp = _components(nf, a[sel], b[sel])
        size = np.bincount(comp[pool], minlength=nf)
        big = pool & (size[comp] >= min_faces) & ~tiny
        if not big.any():
            break
        # seed per component: the face nearest its area-weighted mean normal (the dominant plane)
        fi = np.flatnonzero(big)
        mn = np.zeros((nf, 3))
        np.add.at(mn, comp[fi], nrm[fi] * area[fi, None])
        score = (nrm[fi] * mn[comp[fi]]).sum(1)
        o = np.lexsort((-score, comp[fi]))
        seeds = fi[o][np.r_[True, comp[fi][o][1:] != comp[fi][o][:-1]]]
        rid = nreg + np.arange(len(seeds))
        sn, sc = nrm[seeds], cen[seeds]
        label[seeds] = rid
        pool[seeds] = False
        front = seeds
        while len(front):
            src, nb = _neighbours(indptr, b, front)
            m = pool[nb] & (comp[nb] == comp[src])
            src, nb = src[m], nb[m]
            r = label[src] - nreg
            m = fits(nb, sn[r], sc[r])
            nb, r = nb[m], r[m]
            nb, i = np.unique(nb, return_index=True)
            label[nb] = r[i] + nreg
            pool[nb] = False
            front = nb
        nreg += len(seeds)

    # disks only: split regions whose Euler characteristic isn't 1 across their longest extent, re-split pieces
    for _ in range(8):
        label = _relabel(label, fa, fb)
        chi = _euler(F, label, fa, fb)
        bad = np.flatnonzero(chi != 1)
        if not len(bad):
            break
        fi = np.flatnonzero(np.isin(label, bad))
        lr = label[fi]
        cnt = np.bincount(lr)[lr][:, None]
        mid = np.zeros((label.max() + 1, 3))
        np.add.at(mid, lr, cen[fi])
        d = cen[fi] - mid[lr] / cnt
        cov = np.zeros((label.max() + 1, 3, 3))
        np.add.at(cov, lr, d[:, :, None] * d[:, None, :])
        axis = np.linalg.eigh(cov)[1][:, :, -1]
        side = (d * axis[lr]).sum(1) > 0
        label[fi[side]] += label.max() + 1
    else:
        label = _relabel(label, fa, fb)
        label[np.isin(label, np.flatnonzero(_euler(F, label, fa, fb) != 1))] = -1
    size = np.bincount(label[label >= 0], minlength=max(label.max() + 1, 1))
    label[(label >= 0) & (size[np.maximum(label, 0)] < min_faces)] = -1
    return _relabel(label, fa, fb)


def _relabel(label, fa, fb):
    """Split every region into its connected pieces and number them 0..n-1 (-1 stays)."""
    m = (label[fa] == label[fb]) & (label[fa] >= 0)
    comp = _components(len(label), fa[m], fb[m])
    comp[label < 0] = -1
    u, inv = np.unique(comp, return_inverse=True)
    return inv - (1 if u[0] == -1 else 0)


def _euler(F, label, fa, fb):
    """V - E + F of every region (1 for a disk). Edges: three per face less the ones two of its faces share."""
    n = label.max() + 1
    if n <= 0:
        return np.zeros(0, int)
    fi = np.flatnonzero(label >= 0)
    lr = label[fi]
    nfc = np.bincount(lr, minlength=n)
    inner = np.bincount(label[fa][(label[fa] == label[fb]) & (label[fa] >= 0)], minlength=n)
    k = np.sort((np.repeat(lr, 3).astype(np.int64) * (F.max() + 1) + F[fi].ravel()))
    nv = np.bincount(k[np.r_[True, k[1:] != k[:-1]]] // (F.max() + 1), minlength=n)
    return nv - (3 * nfc - inner) + nfc


def _loops(F, label):
    """Each region's boundary as one vertex loop, wound like its faces: (region per loop, loop start, loop length,
    vertices), for the regions whose boundary is one simple loop (every boundary vertex left once) enclosing at
    least one interior vertex (a strip of faces with none gains nothing from being dissolved)."""
    n = label.max() + 1
    fi = np.flatnonzero(label >= 0)
    hs = F[fi][:, [0, 1, 2]].ravel()
    ht = F[fi][:, [1, 2, 0]].ravel()
    hr = np.repeat(label[fi], 3).astype(np.int64)
    nv = F.max() + 1
    fwd = (hr * nv + hs) * nv + ht
    twin = (hr * nv + ht) * nv + hs
    fs = np.sort(fwd)
    pos = np.minimum(np.searchsorted(fs, twin), len(fs) - 1)
    bd = fs[pos] != twin  # boundary: the reverse half-edge isn't in the region
    bs, bt, br = hs[bd], ht[bd], hr[bd]
    # the region's vertices, and whether each boundary vertex is left exactly once
    kv = np.sort(hr * nv + hs)
    nvert = np.bincount(kv[np.r_[True, kv[1:] != kv[:-1]]] // nv, minlength=n)
    start = br * nv + bs
    o = np.argsort(start, kind="stable")
    bs, bt, br, start = bs[o], bt[o], br[o], start[o]
    dup = np.r_[start[1:] == start[:-1], False] | np.r_[False, start[1:] == start[:-1]]
    ok = np.ones(n, bool)
    ok[br[dup]] = False
    nb = np.bincount(br, minlength=n)
    ok &= nvert > nb  # an interior vertex
    # successor of each boundary half-edge: the one leaving its end vertex in the same region
    succ = np.searchsorted(start, br * nv + bt)
    succ = np.minimum(succ, len(start) - 1)
    bad = start[succ] != br * nv + bt
    ok[br[bad]] = False
    succ[bad] = np.flatnonzero(bad)
    # list ranking by pointer doubling: steps from each half-edge to the one before its region's head
    m = len(start)
    head = np.full(n, m)
    np.minimum.at(head, br, np.arange(m))
    nxt = succ.copy()
    end = nxt == head[br]
    nxt[end] = np.flatnonzero(end)
    dist = (~end).astype(np.int64)
    for _ in range(int(np.ceil(np.log2(max(nb.max(), 2)))) + 1):
        dist += dist[nxt]
        nxt = nxt[nxt]
    ok[br[(nxt[nxt] != nxt) | (dist[head[br]] + 1 != nb[br])]] = False  # more than one loop
    keep = ok[br]
    o = np.lexsort((-dist[keep], br[keep]))
    verts = bs[keep][o]
    regs = np.flatnonzero(ok & (nb > 0))
    length = nb[regs]
    return regs, np.r_[0, np.cumsum(length)[:-1]], length, verts


def flatten(V: np.ndarray, F: np.ndarray, plane_tol: float):
    """Planar regions of (V, F) dissolved to one ngon each: (vertices, loop vertex indices, loop sizes, which input
    faces were dissolved). Faces not in a region stay triangles; unused vertices are dropped."""
    V = np.asarray(V, np.float64)
    F = np.asarray(F, np.int64)
    gone = np.zeros(len(F), bool)
    label = planar_regions(V, F, plane_tol) if plane_tol > 0 and len(F) else np.full(len(F), -1)
    regs = np.zeros(0, np.int64)
    if label.max(initial=-1) >= 0:
        regs, _, length, lverts = _loops(F, label)
    if len(regs):
        gone = np.isin(label, regs)
        kept = np.flatnonzero(~gone)
        loops = np.r_[F[kept].ravel(), lverts]
        sizes = np.r_[np.full(len(kept), 3), length]
    else:
        loops, sizes = F.ravel(), np.full(len(F), 3)
    used = np.unique(loops)
    remap = np.full(len(V), -1, np.int64)
    remap[used] = np.arange(len(used))
    return V[used], remap[loops], sizes, gone


def _flatten_job(args):
    V, F, plane_tol = args
    return flatten(V, F, plane_tol)
