"""One tile's mesh: the grid, marching cubes, border keys, decimation, and cleaning specks, pinches and
non-manifold edges. Part of the terrain mesh (terrain_mesh.py has the overview)."""
from __future__ import annotations

import math

import numpy as np

from . import profiling
from .profiling import span as _span

# ---------------------------------------------------------------- tiles

# the lattice's z planes sit this fraction of a voxel off round heights: flat floors at round heights (sea level, a
# cave floor at 5.5 m) lay exactly on lattice planes, every corner there was a zero, and marching cubes left
# non-manifold slivers (the seam check caught them). x and y stay on the tile borders.
ZOFF = 0.137

class Grid:
    """The world's tile grid and the meshing lattice per LOD."""

    def __init__(self, T, cfg):
        (x0, y0), (x1, y1) = T.spec["extent"]
        self.origin = np.array(cfg.get("origin") or [x0, y0], float)
        self.tile = float(cfg["tile"])
        self.voxel = float(cfg["voxel"])
        self.lods = int(cfg["lods"])
        vmax = self.voxel
        if abs(self.tile / vmax - round(self.tile / vmax)) > 1e-9:
            raise ValueError(f"tile {self.tile} m isn't a whole number of voxels ({vmax} m)")
        # the meshed world: the extent from the origin, trimmed to whole voxels
        self.lo = self.origin
        span = np.array([x1, y1]) - self.origin
        self.span = np.floor(span / vmax + 1e-9) * vmax
        self.hi = self.origin + self.span
        self.trimmed = bool(np.any(np.abs(self.span - span) > 1e-6))
        self.ni, self.nj = int(math.ceil(self.span[0] / self.tile - 1e-9)), int(math.ceil(self.span[1] / self.tile - 1e-9))

    def v(self, k):
        return self.voxel * 2 ** k

    def cells(self, i, j, k):
        """Global lattice index range [a0, a1] x [b0, b1] (inclusive) of tile (i, j) at LOD k."""
        v = self.v(k)
        n = int(round(self.tile / v))
        NX, NY = int(round(self.span[0] / v)), int(round(self.span[1] / v))
        return (i * n, min((i + 1) * n, NX)), (j * n, min((j + 1) * n, NY)), n, (NX, NY)

    def bounds(self, i, j):
        lo = self.origin + np.array([i, j]) * self.tile
        return lo, np.minimum(lo + self.tile, self.hi)


def _tile_mc(field, G: Grid, i, j, k, vols):
    """Marching cubes of one tile at LOD k on the global lattice. Returns global lattice-index vertex coordinates
    (float64), faces, and the tile's lattice ranges."""
    from skimage import measure
    v = G.v(k)
    (a0, a1), (b0, b1), n, (NX, NY) = G.cells(i, j, k)
    ia = np.arange(a0, a1 + 1)
    ib = np.arange(b0, b1 + 1)
    X, Y = np.meshgrid(G.origin[0] + ia * v, G.origin[1] + ib * v, indexing="ij")
    # the tile's height range: its columns and one column round it, plus the volumes reaching it
    m = 1
    xe = G.origin[0] + np.arange(max(a0 - m, 0), min(a1 + m, NX) + 1) * v
    ye = G.origin[1] + np.arange(max(b0 - m, 0), min(b1 + m, NY) + 1) * v
    XE, YE = np.meshgrid(xe, ye, indexing="ij")
    h, sce = field.column(XE.ravel(), YE.ravel())
    if hasattr(field, "zlow"):  # (a cliff shell: as deep as it goes under these columns, see CliffField.zlow)
        zlo, zhi = float(np.min(field.zlow(XE.ravel(), YE.ravel()))), h.max()
    else:
        zlo, zhi = float(np.min(h - getattr(field, "zpad", 0.0) / np.maximum(sce, 0.15))), h.max()
    lo = np.array([X.min() - v, Y.min() - v, -1e9])
    hi = np.array([X.max() + v, Y.max() + v, 1e9])
    for vol in vols:
        if vol.touches(lo, hi):
            zlo, zhi = min(zlo, vol.lo[2] - getattr(field, "vol_pad", 0.0)), max(zhi, vol.hi[2])
    pad = 2 + int(math.ceil((field.rock["reach"] if field.rock else 0.0) / v))  # (rock relief moves the surface)
    c0, c1 = int(math.floor(zlo / v)) - pad, int(math.ceil(zhi / v)) + pad
    ic = np.arange(c0, c1 + 1)
    hcol, scol = field.column(X.ravel(), Y.ravel())
    Z = (ic + ZOFF) * v
    F = (Z[None, :] - hcol[:, None]) * scol[:, None]
    P = np.stack(np.broadcast_arrays(X.ravel()[:, None], Y.ravel()[:, None], Z[None, :]), -1).reshape(-1, 3)
    F = F.ravel()
    S_ = np.repeat(scol, len(ic))
    with _span("mc/lattice field"):
        for q in range(0, len(P), 400_000):  # (in pieces: a whole tile's lattice at once peaked at ~2 GB a worker)
            F[q:q + 400_000] = field.solid(P[q:q + 400_000], F[q:q + 400_000].copy(), S_[q:q + 400_000])
    eps = 1e-3 * v
    # (clamped to a few voxels: a far value (a cliff shell's 1e3 "air") pulled crossings onto the lattice node itself in
    # float32, and the border vertex lost its edge; only the sign decides which edges are crossed)
    F = np.clip(np.where(np.abs(F) < eps, np.where(F < 0, -eps, eps), F), -3 * v, 3 * v)
    F = F.reshape(len(ia), len(ib), len(ic))
    if F.min() > 0 or F.max() < 0:
        return None
    with _span("mc/skimage"):
        verts, faces, _, _ = measure.marching_cubes(F, 0.0, spacing=(1.0, 1.0, 1.0), method="lewiner",
                                                    allow_degenerate=False, gradient_direction="ascent")
    faces = faces[:, ::-1].astype(np.int64)  # outward for our inside-negative field
    idx = verts.astype(np.float64) + np.array([a0, b0, c0], float)
    return idx, faces, (a0, a1, b0, b1)


def _border_keys(idx, rng, n_tile, NX, NY):
    """For vertices on the tile's border planes: a key naming their lattice edge (axis, lower corner), and which
    axes are fixed (on a tile border or the world's edge)."""
    a0, a1, b0, b1 = rng
    onx = (idx[:, 0] == a0) | (idx[:, 0] == a1)
    ony = (idx[:, 1] == b0) | (idx[:, 1] == b1)
    on = onx | ony
    keys = {}
    for vi in np.flatnonzero(on):
        c = idx[vi]
        frac = np.abs(c - np.round(c)) > 1e-6
        if frac.sum() != 1:
            raise RuntimeError(f"border vertex {c} isn't on one lattice edge")
        ax = int(np.flatnonzero(frac)[0])
        lower = np.round(c).astype(np.int64)
        lower[ax] = int(math.floor(c[ax]))
        keys[vi] = (ax, int(lower[0]), int(lower[1]), int(lower[2]))
    return keys


def _key_geometry(keys, G, k):
    """Lattice edge endpoints (world) and fixed axes for canonical border vertices."""
    v = G.v(k)
    K = np.array(keys, np.int64)
    ax = K[:, 0]
    lo = K[:, 1:].astype(float)
    hi = lo.copy()
    hi[np.arange(len(K)), ax] += 1
    to_w = lambda a: np.c_[G.origin[0] + a[:, 0] * v, G.origin[1] + a[:, 1] * v, (a[:, 2] + ZOFF) * v]
    n = int(round(G.tile / v))
    NX, NY = int(round(G.span[0] / v)), int(round(G.span[1] / v))
    fixed = np.zeros((len(K), 3), bool)
    fixed[:, 0] = (ax != 0) & ((K[:, 1] % n == 0) | (K[:, 1] == NX))
    fixed[:, 1] = (ax != 1) & ((K[:, 2] % n == 0) | (K[:, 2] == NY))
    return to_w(lo), to_w(hi), fixed


def _boundary_edges(faces):
    """Directed edges used by one face only (a mesh's open border), as (a, b) in face order."""
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    key = np.minimum(e[:, 0], e[:, 1]) * (int(e.max()) + 1) + np.maximum(e[:, 0], e[:, 1])
    u, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
    return e[cnt[inv] == 1]


PRE = 32  # x a coarse LOD's budget: what its dense-mesh fallback reaches in one pyfqmr pass before the budget search
# (replayed on the alps block's 12 fallbacks: 85 -> 37 s, faces <= the old ones in every case, summed error p99
# 6.2 -> 5.7 m; 4x and 8x were faster still but their meshes sat further off the rock at the same count)
def _decimate(P, faces, err, budget, field, border_ok=None, pre=None):
    """Fewest triangles (pyfqmr, open borders locked) whose surface stays within `err` of the field (99th percentile
    at face centres and edge midpoints, over what the undecimated mesh already misses), capped at `budget`.
    (pyfqmr's own lossless mode barely removed anything with the border locked.)
    border_ok(v): False when a vertex on a tile's border plane isn't one of the canonical border vertices. pyfqmr
    locks vertices on OPEN edges only: two border vertices joined by an interior edge (a shell's front and back
    meeting in the border plane) may collapse into a new point on the plane, and the export then died after every
    tile was baked ("border vertices moved in decimation", alps blocks). Such a result counts as a fold.
    pre: a face count to reach in one pyfqmr pass first (from a dense mesh), the tolerance staying the dense mesh's:
    counting down from a 265k-face mesh ran pyfqmr on all of it 20-60 times a LOD (10-28 s, the alps block's
    stragglers); the same search from PRE x the budget takes 2-5 s, to the same budget and tolerance."""
    import pyfqmr
    n_open = len(_boundary_edges(faces))

    def valid(v, f):  # manifold, no new holes (dropping a fin's twin faces can open one), the border kept
        return _manifold(f) and len(_boundary_edges(f)) == n_open and (border_ok is None or border_ok(v))

    def run(n, base=None):
        # pyfqmr sometimes folds a thin part (a cave mouth, an arch's soffit) whatever the count: other settings of
        # its aggressiveness usually don't
        Pb, Fb = base if base is not None else (P, faces)
        out = None
        for agg in (7, 5, 9, 6, 8):
            profiling.count("decimate.pyfqmr runs")
            with _span("decimate.pyfqmr", leaf=True):
                s = pyfqmr.Simplify()
                s.setMesh(Pb, Fb)
                s.simplify_mesh(target_count=int(n), aggressiveness=agg, max_iterations=300, preserve_border=True,
                                verbose=False)
                v, f, _ = s.getMesh()
                out = _drop_twins(np.asarray(v, float), np.asarray(f, np.int64))
                if len(out[1]) and not _manifold(out[1]):  # (two sheets pinched onto one edge: unpinched)
                    sp = _split_nonmanifold(*out)
                    if sp is not None:
                        profiling.count("decimate: pinched sheets split")
                        out = sp
            with _span("decimate.valid", leaf=True):
                ok = valid(*out)
            if ok and len(out[1]) <= 1.15 * n + 64:  # (a low aggressiveness can stall far above n)
                return out
        return out


    def error(v, f):
        if not valid(v, f):  # pyfqmr can fold a thin part into a fin (two faces on one directed edge)
            return np.inf
        c = np.r_[v[f].mean(1), (v[f[:, 0]] + v[f[:, 1]]) / 2]
        with _span("decimate.error"):
            if hasattr(field, "front"):
                # a cliff shell is judged where it can be seen: every face whose centre is not deep inside the rock
                # (front >= -thr), by the visible rock's own field. The buried back's values aren't metres (slice_a's
                # cave tile: |field| p99 0.59 at the dense mesh's own face centres, all of it 5-25 m under the ground):
                # counted, they were the tolerance. Judged only on faces with every corner on the rock (until
                # 2026-10-07), a face pulled out in front of it (corners off, centre in the open air) wasn't judged
                # at all: the back's faces came out through thin rock at LOD 1-2 (the island's Kaze stacks, Pencil
                # Bay: white triangles 10-20 m across)
                thr = max(0.3, 2 * err)
                fc = field.front(c)
                seen = fc >= -thr
                if seen.sum() >= 16:
                    return float(np.percentile(np.abs(fc[seen]), 99))
            return float(np.percentile(np.abs(field.value(c)), 99))

    tol = err + error(P, faces)
    if pre is not None and len(faces) > 1.5 * pre and len(faces) > budget:
        cand = run(pre)
        if valid(*cand) and len(cand[1]) < len(faces) and error(*cand) <= tol:
            profiling.count("decimate: a dense mesh taken down in one pass first")
            P, faces = cand
    if len(faces) <= budget:
        best, hi = (P, faces), len(faces)
    else:
        # the budget caps it: the first unfolded result at or under it (a fold at the budget itself used to hand back
        # the undecimated mesh: LOD2 came out bigger than LOD1)
        n = int(budget)
        best = None
        last = None
        while n >= 16:
            cand = run(n)
            if valid(*cand) and len(cand[1]) <= budget:
                best = cand
                break
            # pyfqmr stalled (a lower target gave the same mesh: it stops where its flip and border checks block every
            # collapse, far above the target from a dense mesh): every lower count would too. The steps below, each
            # from the last mesh, get past it in a second; counting down to 16 took ~100 runs (80-110 s a LOD, the
            # alps block's straggler tiles)
            if last is not None and len(cand[1]) == last:
                profiling.count("decimate: pyfqmr stalled above the budget")
                break
            last = len(cand[1])
            n = int(n * 0.8)
        if best is None:  # in one pass every count folded something: in steps, each from the last good mesh
            cur = (P, faces)
            while len(cur[1]) > budget:
                cand = run(max(int(len(cur[1]) / 1.6), int(budget)), cur)
                if not valid(*cand) or len(cand[1]) >= len(cur[1]):
                    break
                cur = cand
            return cur
        hi = n
        if error(*best) > tol:
            return best
    # down from the best mesh so far, each step from the last one that held (a log search over the dense mesh ran
    # pyfqmr on all of it 7 times a tile: most of the export's CPU time); a step that breaks the tolerance is retried
    # at a gentler ratio before stopping
    for ratio in (0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5):
        n = int(len(best[1]) * ratio)
        if n < 16:
            break
        cand = run(n, best)
        if len(cand[1]) < len(best[1]) and error(*cand) <= tol:
            best = cand
            continue
        for gentler in (0.75, 0.88):
            cand = run(int(len(best[1]) * gentler), best)
            if len(cand[1]) < len(best[1]) and error(*cand) <= tol:
                best = cand
                break
        break
    return best


def _exposed_back(v, f, fv, vis, field, thr):
    """m2 of a cliff shell's faces off the visible rock (buried) whose centre stands out in front of it, in the air."""
    hid = np.flatnonzero(~vis & (fv[f].max(1) > -thr))  # (faces near the front: the deep back can't reach the air)
    if not len(hid):
        return 0.0
    out = hid[field.front(v[f[hid]].mean(1)) > thr]
    if not len(out):
        return 0.0
    a = np.linalg.norm(np.cross(v[f[out, 1]] - v[f[out, 0]], v[f[out, 2]] - v[f[out, 0]]), axis=1) / 2
    return float(a.sum())


def _drop_twins(v, f):
    """pyfqmr sometimes folds a thin part into a fin: the same triangle twice, back to back. Both go (the faces round
    them close up), and vertices left unused are dropped."""
    key = np.sort(f, axis=1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    keep = cnt[inv.ravel()] == 1
    if keep.all():
        return v, f
    f = f[keep]
    used = np.unique(f)
    remap = np.full(len(v), -1, np.int64)
    remap[used] = np.arange(len(used))
    return v[used], remap[f]


PINCH_GAP = 0.005  # m each copy of a pinched vertex steps into its own sheet (`_unpinch`)


SPECK_FACES = 16  # a closed piece this small split off by `_unpinch` is dropped (`_drop_closed_specks`)


def _split_nonmanifold(v, f):
    """`_unpinch` until no edge has more than two faces: a pinch whose faces were paired across the sheets (the other
    of the two ways round) stays shared after a pass, and the next pass pairs it the other way. None if it can't.
    Closed specks the split leaves (`_drop_closed_specks`) go."""
    for k in range(4):
        if _manifold(f):
            return _drop_closed_specks(v, f) if k else (v, f)
        got = _unpinch(v, f, k % 2)
        if got is None:
            return None
        v, f = got
    return _drop_closed_specks(v, f) if _manifold(f) else None


def _drop_closed_specks(v, f):
    """Closed pieces of at most SPECK_FACES faces dropped (vertices left unused too). Unpinching a pyfqmr pinch can cut
    a tiny closed bubble (a tetrahedron, 4 faces) off the sheet it sat on, a few mm from it: the island's tile 3,16
    exported one 6 m over the heightmap at [224.7, 1057.8, 1.4] and the floating check failed (pushieworld note 122).
    A closed piece has no border edges: the tile's border and the sheet round it are untouched."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    if len(f) < 2:
        return v, f
    nf = len(f)
    rows = np.repeat(np.arange(nf), 3)
    A = coo_matrix((np.ones(3 * nf), (rows, f.ravel())), shape=(nf, len(v))).tocsr()
    nc, lab = connected_components(A @ A.T, directed=False)
    if nc < 2:
        return v, f
    size = np.bincount(lab)
    if size.max() < 8 * SPECK_FACES:  # (only beside a real sheet: a mesh of nothing but small pieces is left as it is)
        return v, f
    small = np.flatnonzero(size <= SPECK_FACES)
    if not len(small):
        return v, f
    drop = np.zeros(nf, bool)
    n = len(v)
    for c in small:
        fc = f[lab == c]
        e = np.concatenate([fc[:, [0, 1]], fc[:, [1, 2]], fc[:, [2, 0]]])
        und = np.minimum(e[:, 0], e[:, 1]) * n + np.maximum(e[:, 0], e[:, 1])
        if np.all(np.unique(und, return_counts=True)[1] == 2):  # (closed)
            drop[lab == c] = True
    if not drop.any():
        return v, f
    f = f[~drop]
    used = np.unique(f)
    remap = np.full(len(v), -1, np.int64)
    remap[used] = np.arange(len(used))
    return v[used], remap[f]


def _unpinch(v, f, offset=0):
    """pyfqmr's other fold where two sheets of a shell lie within a voxel (a cave's wall and the rock kept round it, or
    the shell's back, close under crown_tube): it collapses them onto one shared edge (4 faces on it) or vertex. The
    geometry is fine, only the topology pinches: each such edge's faces are paired round it (sorted by angle, a pair
    taking it in opposite directions) and every vertex on one is copied once per fan of faces joined through its
    edges, so the two sheets touch without sharing anything. (v, f) manifold, or None when the faces round an edge
    don't alternate in direction or a pinch is on an open edge (a tile's border: its vertices are canonical).
    Rejected as a fold instead, every count folded somewhere and the island's 16,25 kept its dense mesh at every LOD
    (250k triangles for budgets of 12,000 / 3,000 / 800: pushieworld note 117)."""
    n = len(v)
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    fid = np.tile(np.arange(len(f)), 3)
    und = np.minimum(e[:, 0], e[:, 1]) * n + np.maximum(e[:, 0], e[:, 1])
    u, inv, cnt = np.unique(und, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    bad = np.flatnonzero(cnt > 2)
    if not len(bad):
        return v, f
    if np.any(cnt[bad] % 2):  # (an odd count: not two sheets)
        return None
    opn = np.c_[u[cnt == 1] // n, u[cnt == 1] % n]
    if len(opn) and np.isin(np.c_[u[bad] // n, u[bad] % n], opn).any():  # (a pinch on the tile's border)
        return None
    # faces joined across each edge: manifold edges join their two faces, a pinched edge its pairs
    join = {}  # (face, undirected edge) -> the face across it
    order = np.argsort(inv, kind="stable")
    starts = np.r_[0, np.cumsum(cnt)]
    for q in range(len(u)):
        rows = order[starts[q]:starts[q + 1]]
        fs = fid[rows]
        if len(rows) == 2:
            join[(fs[0], u[q])] = fs[1]
            join[(fs[1], u[q])] = fs[0]
            continue
        if len(rows) == 1:
            continue
        a, b = e[rows[0]]
        a, b = min(a, b), max(a, b)
        ax = v[b] - v[a]
        ax = ax / max(np.linalg.norm(ax), 1e-12)
        ref = None
        ang, dirs = [], []
        for r, fi in zip(rows, fs):
            c = int(np.setdiff1d(f[fi], [a, b])[0])
            w = v[c] - v[a]
            w = w - ax * (w @ ax)
            if ref is None:
                ref = w / max(np.linalg.norm(w), 1e-12)
            ang.append(math.atan2(np.cross(ref, w) @ ax, ref @ w))
            dirs.append(1 if e[r, 0] == a else -1)
        srt = np.argsort(ang)
        d_ = np.asarray(dirs)[srt]
        if np.any(d_[1:] == d_[:-1]) or d_[0] == d_[-1]:
            return None
        fs = fs[srt]
        fs = np.roll(fs, -offset)
        for k in range(0, len(fs), 2):
            join[(fs[k], u[q])] = fs[k + 1]
            join[(fs[k + 1], u[q])] = fs[k]
    pinched = np.unique(np.c_[u[bad] // n, u[bad] % n])
    v2, f2 = list(v), f.copy()
    for p in pinched:
        fan = np.flatnonzero((f == p).any(1))
        seen, comps = set(), []
        for s in fan:
            if s in seen:
                continue
            comp, stack = [], [s]
            seen.add(s)
            while stack:
                x = stack.pop()
                comp.append(x)
                for o in f[x]:
                    if o == p:
                        continue
                    key = (x, min(p, o) * n + max(p, o))
                    y = join.get(key)
                    if y is not None and y not in seen:
                        seen.add(y)
                        stack.append(y)
            comps.append(comp)
        if len(comps) < 2:
            continue
        for ci, comp in enumerate(comps):
            # (each copy stepped PINCH_GAP into its own fan: at one position the export's GLBs, welded by position
            # when read back, were the same pinched edge again)
            ix = np.array(comp)
            nb = np.setdiff1d(f[ix], [p])
            dv = v[nb].mean(0) - v[p]
            q = v[p] + PINCH_GAP * dv / max(np.linalg.norm(dv), 1e-12)
            if ci == 0:
                v2[p] = q
                continue
            v2.append(q)
            f2[ix] = np.where(f2[ix] == p, len(v2) - 1, f2[ix])
    return np.asarray(v2, float), f2


def _manifold(f):
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    n = int(f.max()) + 1
    if len(np.unique(e[:, 0] * n + e[:, 1])) < len(e):
        return False
    und = np.minimum(e[:, 0], e[:, 1]) * n + np.maximum(e[:, 0], e[:, 1])
    return bool(np.unique(und, return_counts=True)[1].max() <= 2)


def _face_normals(P, F):
    n = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)
