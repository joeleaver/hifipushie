"""ONE HUMAN MESH, built once, offline: GNM's head topology stitched onto MakeHuman's body topology at the neck.

    HIFIPUSHIE_ASSETS=... uv run python spikes/onemesh/make_asset.py            # writes src/hifipushie/human_mesh.npz
    ... make_asset.py --obj neutral.obj          # also the neutral as an OBJ (vertex order = the asset's) for Blender
    ... make_asset.py --edits-from edited.obj    # moved vertices of an edited copy -> spikes/onemesh/edits.json

What it makes (src/hifipushie/onemesh.py reads it; nothing here runs at build time of a character):
- topology: MakeHuman's body below one of its own neck loops (C, 42 vertices) + GNM's skin above one of its own neck
  rings (A, 110 vertices, RING rings up from its bib's open edge) + GNM's eyes, teeth, gums, tongue and mouth sock,
  joined by three rows of quads: A (110) -> 82 -> 58 -> C (42). A row of quads between a finer and a coarser loop is
  made of plain quads (1 edge : 1 edge) and reduction units (4 edges : 2 edges; 4 quads round one new vertex), spread
  evenly and laid out as a palindrome from the front centre, so the mesh stays mirror-symmetric and every bridge
  vertex has 3-5 edges; the new vertices are relaxed on MakeHuman's own neck surface.
- every GNM skin vertex and bridge vertex BOUND to a point of MakeHuman's reference surface (3 body vertex ids +
  barycentric weights; register.py): at runtime any MakeHuman body shape (age with growth, sex, weight, muscle, height,
  race, chest...) moves the head with it, exactly at the stitch and smoothed over the rest (lids, lips, nostrils, ears
  and the mouth sock ride), so there is no head scale, no neck tube and no cross-fade.
- GNM identity / expression components stay GNM's own (read from its pack at runtime, by `gnm_id`), faded to 0 over
  FADE rings above A.
- MakeHuman's hand-made skin weights: by index on the body, carried through the same binding onto the head (so the
  neck's falloff and the jaw are MakeHuman's), eyes / teeth / tongue to their bones.
- one UV layout: MakeHuman's body layout (left), GNM's skin layout (top right), a slot each for the eyes, upper
  teeth, lower teeth and tongue along the bottom; the bridge's faces continue GNM's skin island down to C.
- hand corrections (edits.json beside this file): {"move": {"<vertex id>": [dx, dy, dz]}, "spin": [[a, b], ...]}
  (an edge between two quads turned to the other diagonal of their hexagon). Applied last, every build.
The build is deterministic; it prints the asset's sha256 (tests/test_onemesh.py holds it)."""
from __future__ import annotations

import collections
import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import factorized
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
import register as R  # noqa: E402

from hifipushie import assets, base, makehuman  # noqa: E402

RING = 13  # GNM's neck ring the head is cut at (rings counted up from its bib's open edge; ~3 cm over C)
C_RING = 10  # GNM's ring that lay where C is (the bridge continues GNM's uv grid down to it)
MH_UP = 1   # MakeHuman's loop C: this many loops above the highest one clear of the chin by 2.5 cm (base._neck_loops):
# that one lies on the trapezius' slope at the nape; one up, the bridge is on the neck's column all round
FADE = 7   # rings above A over which GNM's identity / expression components come in
STIFF = 5  # rings above A held hard onto MakeHuman's surface (the stitch must follow the body exactly)
_g = [0.1, 0.25, 0.4]
WGRID = [(a_, b_, c_, 1 - a_ - b_ - c_) for a_ in _g for b_ in _g for c_ in _g if 0.08 <= 1 - a_ - b_ - c_ <= 0.45]
SHEAR = float(__import__("os").environ.get("OM_SHEAR", 0.85))  # (0.6 with 3 rows; 0.85 with 5: worst aspect 7.8 -> 5.5)
GAP = 0.026   # m: ring A above loop C, along the surface, after the slide
SLIDE = 8     # rings above A re-spaced with it
ROW_AT = [0.0, 0.16, 0.34, 0.53, 0.75, 1.0]  # where the loops lie between A and C: row heights follow the quads' widths (3.3 mm
# at A .. 8.6 mm at C), so quads stay near square
COUNTS = [110, 94, 78, 66, 54, 42]  # vertices per loop: A, four new rings, C (2026-10-08; worst corner cos 0.31; was 110, 82, 58, 42: a ripple of
# pits round a toddler's neck at ring A where three rows took the density down 2.6x). Each row's reductions (4 edges : 2) number
# (fine - coarse) / 2, an EVEN number, so a palindrome has no reduction on the back centre line (two rows with one
# there left a 2-edge vertex), and are spread between plain quads by `patterns` (side by side they made 6-edge
# vertices and slivers)
EDITS = Path(__file__).with_name("edits.json")
OUT = Path(makehuman.__file__).with_name("human_mesh.npz")
PARTS = ["skin", "mouth_sock", "eye.L", "eye.R", "teeth_upper", "teeth_lower", "tongue"]
BODY_UV = (0.72, 0.0, 0.28)  # scale, u offset, v offset of MakeHuman's layout in ours (its body fills the left 77%)
HEAD_UV = (0.44, 0.56, 0.56)  # GNM's skin layout (with the mouth sock)
PART_UV = {2: (0.24, 0.0, 0.0), 3: (0.24, 0.0, 0.0), 4: (0.24, 0.25, 0.0), 5: (0.24, 0.5, 0.0), 6: (0.24, 0.75, 0.0)}
# GNM's eyes, teeth and tongue each have their own texture space (the two eyes share one): a slot each along the bottom


def mh_uvs():
    """MakeHuman's body faces' uvs per corner, in makehuman._raw()'s face order."""
    vt, out, g = [], [], None
    for line in open(makehuman.root() / "3dobjs" / "base.obj"):
        if line.startswith("vt "):
            vt.append([float(x) for x in line.split()[1:3]])
        elif line.startswith("g "):
            g = line.split()[1]
        elif line.startswith("f ") and g == "body":
            out.append([int(t.split("/")[1]) - 1 for t in line.split()[1:]])
    return np.array(vt)[np.array(out)]


def ordered_loop(verts, adj):
    vs = set(verts)
    lp, prev = [verts[0]], None
    while True:
        nx = [w for w in adj[lp[-1]] if w in vs and w != prev]
        prev = lp[-1]
        if len(lp) > 1 and lp[0] in nx and len(lp) == len(vs):
            break
        nx = [w for w in nx if w not in lp[1:]] if len(lp) > 1 else nx
        nx = [w for w in nx if w != lp[0]] or nx
        lp.append(nx[0])
        if len(lp) > len(vs):
            raise ValueError("not a simple loop")
    return lp


def start_front(lp, X, centre):
    """The loop rotated to start at its front centre vertex (the figure faces -Y) and running toward +X first."""
    c = [i for i, v in enumerate(lp) if centre(v)]
    if len(c) != 2:
        raise ValueError(f"a neck loop with {len(c)} centre-line vertices")
    i0 = min(c, key=lambda i: X[lp[i], 1])
    lp = lp[i0:] + lp[:i0]
    if X[lp[1], 0] < 0:
        lp = [lp[0]] + lp[1:][::-1]
    return lp


def arc(X):
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(np.r_[X, X[:1]], axis=0), axis=1))]
    return d[:-1] / d[-1]


def at(X, t):
    """A closed polyline's point at arc parameter t (0..1 from its first vertex)."""
    ts = np.r_[arc(X), 1.0]
    Y = np.r_[X, X[:1]]
    return np.column_stack([np.interp(t % 1.0, ts, Y[:, k]) for k in range(Y.shape[1])])


def row(fine, coarse, pattern, new_id):
    """Quads between a fine loop and a coarse one (same start, same direction): [(quad, ...)], the reduction units'
    new vertices [(id, fine index it hangs under, coarse index, share along that coarse edge)] and each coarse
    vertex's fine partner. Units: P = (f0, f1, c1, c0); R = 3 fine edges onto 1 coarse one through two new vertices
    q1, q2 under f1, f2: (f0, f1, q1, c0), (f1, f2, q2, q1), (f2, f3, c1, q2), (q1, q2, c1, c0). (A unit of 4 edges
    onto 2 round ONE new vertex was tried first: its middle fine vertex is a 180 degree corner of a quad.)"""
    nf, nc = len(fine), len(coarse)
    assert 3 * pattern.count("R") + pattern.count("P") == nf and pattern.count("R") + pattern.count("P") == nc
    assert pattern == pattern[::-1], "a row's pattern must be a palindrome (mirror symmetry)"
    quads, news, partner = [], [], {}
    i = j = 0
    for u in pattern:
        f = [fine[(i + k) % nf] for k in range(4)]
        c = [coarse[(j + k) % nc] for k in range(2)]
        partner[j % nc] = i % nf
        if u == "P":
            quads.append((f[0], f[1], c[1], c[0]))
            i, j = i + 1, j + 1
        else:
            q1, q2 = new_id + len(news), new_id + len(news) + 1
            news += [(q1, (i + 1) % nf, j % nc, 1 / 3), (q2, (i + 2) % nf, j % nc, 2 / 3)]
            quads += [(f[0], f[1], q1, c[0]), (f[1], f[2], q2, q1), (f[2], f[3], c[1], q2), (q1, q2, c[1], c[0])]
            i, j = i + 3, j + 1
    return quads, news, partner


def patterns(counts):
    """One palindromic pattern per row, reductions spread evenly; the phases searched for the fewest vertices off
    4 edges (none under 3 or over 5)."""
    import itertools

    def half(nf, nc, ph):
        nr = (nf - nc) // 4  # reductions in half a row
        n_units = nf // 2 - 2 * nr
        at_ = {int((i + ph) * n_units / nr) for i in range(nr)}
        if len(at_) != nr:
            return None
        return "".join("R" if k in at_ else "P" for k in range(n_units))

    def valences(pats):
        ids, k = [], 0
        for c in counts:
            ids.append(list(range(k, k + c)))
            k += c
        val = collections.Counter()
        for i, pt in enumerate(pats):
            qs, news, _ = row(ids[i], ids[i + 1], pt, k)
            k += len(news)
            for q in qs:
                for j in range(4):
                    val[(min(q[j], q[(j + 1) % 4]), max(q[j], q[(j + 1) % 4]))] = 1
        deg = collections.Counter()
        for a, b in val:
            deg[a] += 1
            deg[b] += 1
        for v in ids[0] + ids[-1]:  # the loops' own edges into the head / the body
            deg[v] += 1
        return collections.Counter(deg.values())
    best = None
    phases = [0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9]
    for ph in itertools.product(phases, repeat=len(counts) - 1):
        hs = [half(counts[i], counts[i + 1], ph[i]) for i in range(len(ph))]
        if any(h is None for h in hs):
            continue
        pats = [h + h[::-1] for h in hs]
        v = valences(pats)
        bad = sum(c for d, c in v.items() if d < 3 or d > 5)
        key = (bad, v.get(5, 0) + v.get(3, 0), ph)
        if best is None or key < best[0]:
            best = (key, pats, v)
    return best[1], best[2]


def spin(faces, a, b):
    """The edge (a, b) between two quads turned onto the hexagon's next diagonal."""
    idx = [k for k, f in enumerate(faces) if a in f and b in f and len(f) == 4]
    if len(idx) != 2:
        raise ValueError(f"edits: edge {a}-{b} is not between two quads")
    q1, q2 = faces[idx[0]], faces[idx[1]]

    def from_edge(q, u, v):  # q rotated to start (u, v, ...)
        k = q.index(u)
        q = q[k:] + q[:k]
        return q if q[1] == v else None
    r1 = from_edge(q1, a, b) or from_edge(q1, b, a)
    u, v = r1[0], r1[1]
    r2 = from_edge(q2, v, u)
    if r2 is None:
        raise ValueError(f"edits: quads at {a}-{b} are wound against each other")
    y1, y2, x1, x2 = r1[2], r1[3], r2[2], r2[3]  # hexagon: u, x1?, ... : q1 = (u, v, y1, y2), q2 = (v, u, x1, x2)
    faces[idx[0]] = [x1, x2, v, y1]
    faces[idx[1]] = [y1, y2, u, x1]


def build(log=print):
    r = R.register(log)
    g = base._gnm_data()
    z = np.load(assets.path("gnm", base.GNM))
    b, to_world = r["body"], r["to_world"]
    P = np.asarray(b["P"], float)
    Fm = np.asarray(b["L"]).reshape(-1, 4)
    mir_g = np.asarray(z["mirror_indices"])
    quads = np.asarray(r["quads"])
    ng = len(mir_g)

    # the registered head, symmetrised (MakeHuman is symmetric; the registration is within 0.2 mm of it)
    Xw = to_world(r["Xg"] + r["d"])
    Xw = 0.5 * (Xw + Xw[mir_g] * [-1, 1, 1])
    Gn = to_world(r["Xg"])  # GNM's mean itself in the same frame: what `toward` 0 gives back
    Gn = 0.5 * (Gn + Gn[mir_g] * [-1, 1, 1])
    onc = np.flatnonzero(mir_g == np.arange(ng))
    Xw[onc, 0] = 0.0
    Gn[onc, 0] = 0.0

    # GNM's components and the rings up from the bib
    e = np.r_[quads[:, [0, 1]], quads[:, [1, 2]], quads[:, [2, 3]], quads[:, [3, 0]]]
    from scipy.sparse.csgraph import connected_components
    _, comp = connected_components(sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (ng, ng)), directed=False)
    skin_c = comp == comp[np.flatnonzero(r["skin"])[0]]
    adj = collections.defaultdict(set)
    cnt = collections.Counter()
    for q in quads:
        for k in range(4):
            u, v = int(q[k]), int(q[(k + 1) % 4])
            adj[u].add(v)
            adj[v].add(u)
            cnt[(min(u, v), max(u, v))] += 1
    bnd = sorted({v for (u, w), c in cnt.items() if c == 1 for v in (u, w) if skin_c[u]})
    lev = np.full(ng, -1)
    lev[bnd] = 0
    dq = collections.deque(bnd)
    while dq:
        v = dq.popleft()
        for w in adj[v]:
            if lev[w] < 0:
                lev[w] = lev[v] + 1
                dq.append(w)
    keep_g = ~skin_c | (lev >= RING)
    A = start_front(ordered_loop([int(v) for v in np.flatnonzero(skin_c & (lev == RING))], adj), Xw, lambda v: mir_g[v] == v)
    # GNM's columns down the neck (ring k vertex j under ring k + 1 vertex j): the uv grid the bridge continues
    cols = {RING: A}
    for k in range(RING - 1, C_RING - 1, -1):
        cols[k] = [next(w for w in adj[v] if lev[w] == k) for v in cols[k + 1]]

    # MakeHuman: its neck loop and what lies above it
    loops_m, top = base._neck_loops(b)
    madj = collections.defaultdict(set)
    for q in Fm:
        for k in range(4):
            madj[int(q[k])].add(int(q[(k + 1) % 4]))
            madj[int(q[(k + 1) % 4])].add(int(q[k]))
    def above_of(loop):
        ls, ab = set(loop), {int(top)}
        dq_ = collections.deque(ab)
        while dq_:
            v = dq_.popleft()
            for w in madj[v]:
                if w not in ab and w not in ls:
                    ab.add(w)
                    dq_.append(w)
        return ab
    C = [int(v) for v in loops_m[0]]
    for _ in range(MH_UP):
        ab = above_of(C)
        # the far side of the strip of quads standing on the loop (its neighbours "above" are not all one loop where
        # the mesh has a pole beside it: that set zigzagged at the back of the neck)
        cs_, nxt = set(C), set()
        for q in Fm:
            on = [int(v) for v in q if int(v) in cs_]
            if len(on) == 2 and any(int(v) in ab for v in q):
                nxt |= {int(v) for v in q if int(v) not in cs_}
        C = ordered_loop(sorted(nxt), madj)
        assert len(C) == COUNTS[-1], f"MakeHuman's next neck loop has {len(C)} vertices"
    C = start_front(C, P, lambda v: abs(P[v, 0]) < 1e-6)
    above = above_of(C)

    # GNM's lower neck rings SLID along their own columns on the surface (what an artist does to a loop that isn't
    # parallel to the one it must meet): ring A ends GAP above C all round (it was 1 cm at the sides, 3 cm front and
    # back: squashed and tall bridge quads), the rings up to RING + SLIDE evenly spaced above it. Shapes don't change
    # (the points stay on MakeHuman's surface), only where the neck's vertices sit.
    Tm_ = np.r_[Fm[:, [0, 1, 2]], Fm[:, [0, 2, 3]]]
    zc = float(P[C][:, 2].mean())
    near_ = np.flatnonzero((np.abs(P[Tm_][:, :, 2] - zc) < 0.14).all(1) & (np.abs(P[Tm_][:, :, 0]) < 0.14).all(1))
    cen_ = P[Tm_[near_]].mean(1)
    tree_ = cKDTree(cen_)

    def bind_(Xq):
        _, cand = tree_.query(Xq, k=16)
        bt, bb, best = np.zeros((len(Xq), 3), int), np.zeros((len(Xq), 3)), np.full(len(Xq), np.inf)
        for kk in range(16):
            t = Tm_[near_[cand[:, kk]]]
            p_, w_ = R.closest_on_tris(Xq, P[t[:, 0]], P[t[:, 1]], P[t[:, 2]])
            dd = np.linalg.norm(p_ - Xq, axis=1)
            take = dd < best
            best[take], bt[take], bb[take] = dd[take], t[take], w_[take]
        return bt, bb
    up = {RING: A}
    for k in range(RING, RING + SLIDE):
        up[k + 1] = [next(w for w in adj[v] if lev[w] == k + 1 and w not in up[k]) for v in up[k]]
    lo_ring = min(cols)
    XC_ = P[C]
    segC = np.r_[XC_, XC_[:1]]
    dens = np.concatenate([np.linspace(segC[i], segC[i + 1], 12, endpoint=False) for i in range(len(XC_))])
    ctree = cKDTree(dens)
    Xw0 = Xw.copy()
    r_tri, r_bar, r_val = r["tri"].copy(), r["bary"].copy(), r["valid"].copy()
    moved_ = []
    for j in range(len(A)):
        chain = [cols[k][j] for k in range(lo_ring, RING)] + [up[k][j] for k in range(RING, RING + SLIDE + 1)]
        Xc = Xw0[chain]
        fine = np.concatenate([np.linspace(Xc[i], Xc[i + 1], 20, endpoint=False) for i in range(len(Xc) - 1)] + [Xc[-1:]])
        sl = np.r_[0, np.cumsum(np.linalg.norm(np.diff(fine, axis=0), axis=1))]
        s_c = sl[int(np.argmin(ctree.query(fine)[0]))]  # where this column crosses C
        s_top = sl[-1]
        s_a = min(s_c + GAP, s_top - 0.004 * SLIDE)
        ss = np.linspace(s_a, s_top, SLIDE + 1)
        new = np.column_stack([np.interp(ss, sl, fine[:, a_]) for a_ in range(3)])
        for i_, v in enumerate([up[k][j] for k in range(RING, RING + SLIDE + 1)]):
            Xw[v] = new[i_]
            moved_.append(v)
    moved_ = np.array(sorted(set(moved_)))
    Xw[moved_] = 0.5 * (Xw[moved_] + Xw[mir_g[moved_]] * [-1, 1, 1])
    bt_, bb_ = bind_(Xw[moved_])
    Xw[moved_] = (bb_[:, :, None] * P[bt_]).sum(1)
    Xw[moved_] = 0.5 * (Xw[moved_] + Xw[mir_g[moved_]] * [-1, 1, 1])
    Xw[onc, 0] = 0.0
    bt_, bb_ = bind_(Xw[moved_])
    r_tri[moved_], r_bar[moved_], r_val[moved_] = bt_, bb_, True
    Gn[moved_] += Xw[moved_] - Xw0[moved_]
    r = {**r, "tri": r_tri, "bary": r_bar, "valid": r_val}
    log(f"slid {len(moved_)} neck vertices (rings {RING}..{RING + SLIDE}) by up to {np.linalg.norm(Xw - Xw0, axis=1).max() * 1000:.1f} mm "
        f"along their columns: ring A is {GAP * 1000:.0f} mm above C all round")
    keep_m = np.ones(len(P), bool)
    keep_m[sorted(above)] = False
    log(f"MakeHuman: {keep_m.sum()} of {len(P)} vertices kept (loop C {len(C)}); GNM: {keep_g.sum()} of {ng} kept "
        f"(ring A {len(A)} at ring {RING})")

    # fused numbering: MakeHuman's kept vertices, GNM's kept vertices, ring B, the reduction vertices
    m2f = np.full(len(P), -1)
    m2f[keep_m] = np.arange(keep_m.sum())
    g2f = np.full(ng, -1)
    g2f[keep_g] = keep_m.sum() + np.arange(keep_g.sum())
    n0 = int(keep_m.sum() + keep_g.sum())
    Af, Cf = [int(g2f[v]) for v in A], [int(m2f[v]) for v in C]
    assert [len(Af), len(Cf)] == [COUNTS[0], COUNTS[-1]]
    pats, vals = patterns(COUNTS)
    log(f"bridge rows {[p_ for p_ in pats]}; vertices by edge count {dict(sorted(vals.items()))}")
    nrow = len(pats)
    rings = [Af]
    k = n0
    for c in COUNTS[1:-1]:
        rings.append(list(range(k, k + c)))
        k += c
    rings.append(Cf)
    n_ring = k
    # positions between A and C at the arc parameter of the fine vertex each new vertex sits under; (column, ring)
    # in GNM's uv grid of the dropped rings
    XA, XC = Xw[A], P[C]
    axis_c = 0.5 * (XA.mean(0) + XC.mean(0))

    def ang(X):  # each loop vertex's place round the neck, 0..1 from the front centre: its INDEX round the loop.
        # The rows join vertices by index, so a new loop evenly spaced in this parameter has no shear. (The turn
        # about a vertical axis, and arc length pinned at the sides, put C's 42 vertices 2 places off the new
        # loops' at the back of the neck: quads folded there.)
        return np.arange(len(X)) / len(X)

    def at(X, t):  # a loop's point at turn t
        ts_ = np.r_[ang(X), 1.0]
        Y = np.r_[X, X[:1]]
        return np.column_stack([np.interp(np.asarray(t) % 1.0, ts_, Y[:, k_]) for k_ in range(3)])
    tA = ang(XA)
    Tm = np.r_[Fm[:, [0, 1, 2]], Fm[:, [0, 2, 3]]]
    zmid = 0.5 * (XA[:, 2].mean() + XC[:, 2].mean())
    near = np.flatnonzero((np.abs(P[Tm][:, :, 2] - zmid) < 0.1).all(1) & (np.abs(P[Tm][:, :, 0]) < 0.12).all(1))
    cen = P[Tm[near]].mean(1)

    def project(Xq):
        _, cand = cKDTree(cen).query(Xq, k=16)
        bt, bb, best = np.zeros((len(Xq), 3), int), np.zeros((len(Xq), 3)), np.full(len(Xq), np.inf)
        for kk in range(16):
            t = Tm[near[cand[:, kk]]]
            p, w = R.closest_on_tris(Xq, P[t[:, 0]], P[t[:, 1]], P[t[:, 2]])
            dd = np.linalg.norm(p - Xq, axis=1)
            take = dd < best
            best[take], bt[take], bb[take] = dd[take], t[take], w[take]
        return bt, bb, best

    def on_surface(Xq):
        bt, bb, _ = project(Xq)
        return (bb[:, :, None] * P[bt]).sum(1)
    td = np.linspace(0, 1, 1441)[:-1]
    bridge_q, Xnew, col_of = [], {}, {v: (float(j), float(RING)) for j, v in enumerate(Af)}
    col_at = lambda t: np.interp(np.asarray(t) % 1.0, np.r_[tA, 1.0], np.arange(len(A) + 1.0)) % len(A)  # noqa: E731
    tC = ang(XC)
    for j, v in enumerate(Cf):
        col_of[v] = (float(col_at(tC[j])), float(C_RING))
    news_all, curves, ring_of, t_of, t_prev = [], {}, {}, {}, tA
    for i, pt in enumerate(pats):
        qs, news, part = row(rings[i], rings[i + 1], pt, k)
        k += len(news)
        bridge_q += qs
        news_all.append(news)
        if i + 1 < nrow:  # a new loop: the curve ROW_AT of the way from A to C, on the surface, its vertices evenly
            # spaced along it from the front centre (inherited from the finer loop's vertices they were 1 and 2
            # edges apart by turns, and every quad sheared)
            f1 = ROW_AT[i + 1]
            curve = on_surface((1 - f1) * at(XA, td) + f1 * at(XC, td))
            sl = np.r_[0, np.cumsum(np.linalg.norm(np.diff(np.r_[curve, curve[:1]], axis=0), axis=1))]
            nn = len(rings[i + 1])
            tt = np.arange(nn) / nn  # (evenly spaced in the index parameter; by arc length they left C's own spacing)
            # ... but only SHEAR of the way there: evenly spaced, the quads shear between reductions; under the finer
            # loop's own vertices, they are 1 and 2 edges wide by turns
            inh = np.array([t_prev[part[j]] for j in range(nn)])
            tt = SHEAR * tt + (1 - SHEAR) * inh
            t_prev = tt
            for j, v in enumerate(rings[i + 1]):
                t_of[v] = tt[j]
            pos = on_surface((1 - f1) * at(XA, tt) + f1 * at(XC, tt))
            curves[i + 1] = (curve, f1)
            for j, v in enumerate(rings[i + 1]):
                Xnew[v] = pos[j]
                ring_of[v] = i + 1
    n = k
    # each reduction's own vertex: the middle of the four it joins, on the surface
    Xall = {v: x for v, x in zip(Af, XA)} | {v: x for v, x in zip(Cf, XC)} | Xnew
    nbr = collections.defaultdict(set)
    for q in bridge_q:
        for j in range(4):
            nbr[q[j]].add(q[(j + 1) % 4])
            nbr[q[(j + 1) % 4]].add(q[j])
    for v, i_ in ring_of.items():
        col_of[v] = (float(col_at(t_of[v])), RING - (RING - C_RING) * curves[i_][1])
    for i, news in enumerate(news_all):  # a reduction's two vertices: halfway down from the fine vertex each hangs
        # under to its place a third / two thirds along the coarse edge
        for pv, fi, cj, sh in news:
            fv, c0, c1 = rings[i][fi], rings[i + 1][cj], rings[i + 1][(cj + 1) % len(rings[i + 1])]
            lo = (1 - sh) * Xall[c0] + sh * Xall[c1]
            Xall[pv] = on_surface((0.5 * Xall[fv] + 0.5 * lo)[None])[0]
            d0 = (col_of[c1][0] - col_of[c0][0] + len(A) / 2) % len(A) - len(A) / 2
            cl = (col_of[c0][0] + sh * d0) % len(A)
            dm = (cl - col_of[fv][0] + len(A) / 2) % len(A) - len(A) / 2
            col_of[pv] = (float((col_of[fv][0] + 0.5 * dm) % len(A)), 0.5 * (col_of[fv][1] + col_of[c0][1]))
    Xbr = np.array([Xall[v] for v in range(n0, n)])
    mb = cKDTree(Xbr).query(Xbr * [-1, 1, 1])[1]
    assert (mb[mb] == np.arange(len(Xbr))).all(), "the bridge's vertices don't pair up left / right"
    Xbr = 0.5 * (Xbr + Xbr[mb] * [-1, 1, 1])
    btri, bbar, best = project(Xbr)
    rgt = Xbr[:, 0] < -1e-9
    mm0 = cKDTree(P).query(P * [-1, 1, 1])[1]
    btri[rgt], bbar[rgt] = mm0[btri[mb[rgt]]], bbar[mb[rgt]]
    Xbr = (bbar[:, :, None] * P[btri]).sum(1)
    Xbr[mb == np.arange(len(Xbr)), 0] = 0.0
    log(f"bridge: {n - n0} new vertices, moved {best.max() * 1000:.2f} mm at most onto the surface")

    # faces, parts, uvs
    mf = np.flatnonzero(keep_m[Fm].all(1))
    Gq = np.flatnonzero(keep_g[quads].all(1))
    faces = [[int(v) for v in m2f[Fm[k]]] for k in mf] + [[int(v) for v in g2f[quads[k]]] for k in Gq]
    nb0 = len(faces)
    bridge = [list(q) for q in bridge_q]
    # winding: outward (away from the neck's axis)
    X = np.zeros((n, 3))
    X[m2f[keep_m]] = P[keep_m]
    X[g2f[keep_g]] = Xw[keep_g]
    X[n0:] = Xbr
    q = np.array(bridge[0])
    nrm = np.cross(X[q[1]] - X[q[0]], X[q[2]] - X[q[0]])
    if nrm @ (X[q].mean(0) - XC.mean(0)) < 0:
        bridge = [f[::-1] for f in bridge]
    faces += bridge
    names = [str(s) for s in z["mesh_component_names"]]
    G = r["groups"]
    part_g = np.zeros(ng, int)
    part_g[G["mouth_sock"]] = 1
    part_g[G["left_eye"]] = 2 if Xw[G["left_eye"], 0].mean() > 0 else 3
    part_g[G["right_eye"]] = 3 if Xw[G["left_eye"], 0].mean() > 0 else 2
    part_g[G["upper_teeth_and_gums"]] = 4
    part_g[G["lower_teeth_and_gums"]] = 5
    part_g[G["tongue"]] = 6
    part_v = np.zeros(n, int)
    part_v[g2f[keep_g]] = part_g[keep_g]
    part_f = np.array([int(max(part_v[f])) if min(part_v[f]) > 0 or max(part_v[f]) == 1 and min(part_v[f]) == 1 else int(min(part_v[f]))
                       for f in faces])
    uv = np.zeros((len(faces), 4, 2), np.float32)
    s, ou, ov = BODY_UV
    uv[:len(mf)] = mh_uvs()[mf] * s + [ou, ov]
    s, ou, ov = HEAD_UV
    guv = np.asarray(z["quad_uvs"], float)
    uv[len(mf):nb0] = guv[Gq] * s + [ou, ov]
    for pid, (ps, pu, pv_) in PART_UV.items():
        sel = np.flatnonzero(part_f[len(mf):nb0] == pid)
        uv[len(mf) + sel] = guv[Gq[sel]] * ps + [pu, pv_]
    # the bridge continues GNM's island: its uv grid over the dropped rings RING-3 .. RING (column, ring)
    vuv = collections.defaultdict(list)
    for qd, u in zip(quads, guv):
        for v, t in zip(qd, u):
            if not any(np.allclose(t, x, atol=1e-6) for x in vuv[int(v)]):
                vuv[int(v)].append(np.array(t))
    nA = len(A)
    seam = [j for j in range(nA) if len(vuv[A[j]]) > 1]
    if len(seam) != 1:
        raise ValueError(f"GNM's neck ring crosses {len(seam)} uv seams (one, at the back, expected)")
    sj = seam[0]

    def grid_uv(jf, rho, side):
        """uv at fractional column jf (0..nA from the front centre) and ring rho; side -1 / +1 picks the seam's."""
        out = []
        for rk in (int(np.floor(rho)), int(np.floor(rho)) + 1):
            rk = min(max(rk, C_RING), RING)
            ring = cols[rk]
            j0 = int(np.floor(jf)) % nA
            j1 = (j0 + 1) % nA
            f = jf - np.floor(jf)

            def one(j, toward_j):
                c = vuv[ring[j]]
                if len(c) == 1:
                    return c[0]
                o = vuv[ring[toward_j]][0] if len(vuv[ring[toward_j]]) == 1 else None
                if o is None:
                    o = vuv[ring[(j + side) % nA]][0]
                return min(c, key=lambda x: np.linalg.norm(x - o))
            a_, b_ = one(j0, j1 if j0 != sj else (j0 + side) % nA), one(j1, j0 if j1 != sj else (j1 + side) % nA)
            if j0 == sj and f == 0:
                a_ = one(j0, (j0 + side) % nA)
            out.append((1 - f) * a_ + f * b_)
        fr = np.clip(rho - np.floor(rho), 0, 1) if C_RING <= rho < RING else 0.0
        return (1 - fr) * out[0] + fr * out[1]
    for k, f in enumerate(bridge):
        js = np.array([col_of[v][0] for v in f])
        # which side of the back seam the face lies on (its columns other than the seam's own)
        off = [(x - sj + nA / 2) % nA - nA / 2 for x in js]
        side = 1 if np.mean([o for o in off if abs(o) > 1e-9] or [1]) > 0 else -1
        for c, v in enumerate(f):
            jf, rho = col_of[v]
            if abs((jf - sj + nA / 2) % nA - nA / 2) < 1e-9:
                jf = float(sj)
            uv[nb0 + k, c] = grid_uv(jf, rho, side) * s + [ou, ov]

    # bindings: (3 MakeHuman body vertex ids, weights) for GNM's registered skin and the bridge
    bind_tri = np.full((n, 3), -1)
    bind_w = np.zeros((n, 3))
    val = r["valid"] & keep_g
    # symmetric bindings: the right side takes the left's, mirrored (MakeHuman's own mirror map)
    mm = cKDTree(P).query(P * [-1, 1, 1])[1]
    tri, bar = r["tri"].copy(), r["bary"].copy()
    right = val & (Xw[:, 0] < -1e-9) & val[mir_g]
    tri[right], bar[right] = mm[tri[mir_g[right]]], bar[mir_g[right]]
    bind_tri[g2f[val]], bind_w[g2f[val]] = tri[val], bar[val]
    bind_tri[n0:], bind_w[n0:] = btri, bbar

    # hand corrections
    offset = np.zeros((n, 3))
    edits = json.loads(EDITS.read_text()) if EDITS.exists() else {}
    for a, c in edits.get("spin", []):
        spin(faces, int(a), int(c))
    for k, dv in (edits.get("move") or {}).items():
        offset[int(k)] = dv
    if edits:
        log(f"edits: {len(edits.get('move') or {})} moved vertices, {len(edits.get('spin') or [])} spun edges")

    # skin weights over MakeHuman's bones
    wts = makehuman.weights()
    bones = sorted(wts)
    vid = np.asarray(b["vid"])
    inv = np.full(int(vid.max()) + 1, -1)
    inv[vid] = np.arange(len(vid))
    Wm = np.zeros((len(P), len(bones)))
    for k, bn in enumerate(bones):
        ids, w = wts[bn]
        ok = (ids <= vid.max()) & (inv[np.minimum(ids, vid.max())] >= 0)
        Wm[inv[ids[ok]], k] = w[ok]
    Wm /= np.maximum(Wm.sum(1, keepdims=True), 1e-12)
    Wf = np.zeros((n, len(bones)))
    Wf[m2f[keep_m]] = Wm[keep_m]
    bound = bind_tri[:, 0] >= 0
    Wf[bound] = (bind_w[bound][:, :, None] * Wm[bind_tri[bound]]).sum(1)
    # GNM skin the registration doesn't reach (ears, lids' insides, sockets, the sock): the bound skin's, smoothed over
    hs = np.flatnonzero(skin_c & keep_g)
    solve, wdat = head_solver(quads, hs, val, lev, G, ng)
    use = np.flatnonzero(Wf[g2f[hs]].sum(0) > 1e-9)
    Wh = np.column_stack([solve(wdat * Wf[g2f[hs], k]) for k in use])
    Wh = np.clip(Wh, 0, None)
    Wf[np.ix_(g2f[hs], use)] = Wh
    bi = {bn: k for k, bn in enumerate(bones)}
    for pid, bn in ((2, "eye.L"), (3, "eye.R"), (4, "head"), (5, "jaw"), (6, "tongue01")):
        Wf[part_v == pid] = 0
        Wf[part_v == pid, bi[bn if bn in bi else "head"]] = 1.0
    Wf /= np.maximum(Wf.sum(1, keepdims=True), 1e-12)
    order = np.argsort(-Wf, axis=1)[:, :8]
    w8 = np.take_along_axis(Wf, order, 1)
    w8 /= w8.sum(1, keepdims=True)

    # the neutral, and what identity / expression components may move (0 at A .. 1 FADE rings up; 1 off the skin)
    neutral = X.copy()
    gmean = np.zeros((n, 3))
    gmean[g2f[keep_g]] = Gn[keep_g] - Xw[keep_g]  # + this x (1 - toward): back toward GNM's own mean head
    t = np.clip((lev - RING) / FADE, 0, 1)
    fade_g = np.where(skin_c, t * t * (3 - 2 * t), 1.0)
    fade = np.zeros(n)
    fade[g2f[keep_g]] = fade_g[keep_g]
    lev_f = np.full(n, -1)
    lev_f[g2f[hs]] = lev[hs] - RING
    mirror = np.arange(n)
    mirror[m2f[keep_m]] = m2f[mm[keep_m]]
    mirror[g2f[keep_g]] = g2f[mir_g[keep_g]]
    tree = cKDTree(neutral)
    far = np.flatnonzero(mirror == np.arange(n))
    mirror[far] = tree.query(neutral[far] * [-1, 1, 1])[1]
    gid = np.full(n, -1)
    gid[g2f[keep_g]] = np.flatnonzero(keep_g)
    mid = np.full(n, -1)
    mid[m2f[keep_m]] = np.flatnonzero(keep_m)
    lips = np.zeros(n, bool)
    lips[g2f[keep_g]] = (G["upper_lip"] | G["lower_lip"])[keep_g]
    # per GNM vertex (all 17,821: the runtime shapes the whole GNM head, onemesh.bound, and takes the kept ones)
    Jg = np.asarray(z["template_joint_positions"], float)
    ej = to_world((Jg[2:4] - r["Jm"]) / r["io_g"])
    for i_, nm in enumerate(("left_eye", "right_eye")):
        ej[i_] += (Xw[G[nm]] - to_world(r["Xg"][G[nm]])).mean(0)
    ej = 0.5 * (ej + ej[::-1] * [-1, 1, 1])
    gval = r["valid"].copy()
    gtri, gbar = r["tri"].copy(), r["bary"].copy()
    rt = gval & (Xw[:, 0] < -1e-9) & gval[mir_g]
    gtri[rt], gbar[rt] = mm[gtri[mir_g[rt]]], gbar[mir_g[rt]]
    out = {"faces": np.array(faces, np.int32), "part": part_f.astype(np.int8), "parts": np.array(PARTS),
           "uv": uv, "neutral": neutral.astype(np.float32), "gmean": gmean.astype(np.float32),
           "offset": offset.astype(np.float32), "mh_id": mid.astype(np.int32), "gnm_id": gid.astype(np.int32),
           "bind_tri": bind_tri.astype(np.int32), "bind_w": bind_w.astype(np.float32), "fade": fade.astype(np.float32),
           "ring": lev_f.astype(np.int16), "lips": lips, "mirror": mirror.astype(np.int32),
           "bones": np.array(bones), "w_idx": order.astype(np.int16), "w": w8.astype(np.float32),
           "loop_a": np.array(Af, np.int32), "loop_c": np.array(Cf, np.int32), "bridge": np.array([n0, n_ring, n, nb0], np.int32),
           "reference": np.array(json.dumps(dict(sorted(__import__("hifipushie").headfit.table()["reference"].items())))),
           "io": np.array([r["io"], r["io_g"]]), "eye_mid": np.asarray(r["Jm"], float),
           "g_neutral": Xw.astype(np.float32), "g_mean": (Gn - Xw).astype(np.float32), "g_valid": gval,
           "g_tri": np.where(gval[:, None], gtri, 0).astype(np.int32), "g_bary": np.where(gval[:, None], gbar, 0).astype(np.float32),
           "g_lev": np.where(skin_c, lev, -1).astype(np.int16), "g_fade": np.where(keep_g, fade_g, 0.0).astype(np.float32),
           "g_part": part_g.astype(np.int8), "g_eye_j": ej.astype(np.float32), "g2f": g2f.astype(np.int32), "m2f": m2f.astype(np.int32),
           "meta": np.array(json.dumps({"RING": RING, "FADE": FADE, "STIFF": STIFF, "LAM": R.LAM, "LIPS": R.LIPS}))}
    return out


def head_solver(quads, hs, valid, lev, G, ng):
    """The smoothing solve over GNM's kept skin (make_field's): data weights 1 on bound vertices (lips 0.2), far
    higher over the STIFF rings above the stitch; returns (solve(rhs) on the hs subset, the data weights)."""
    loc = np.full(ng, -1)
    loc[hs] = np.arange(len(hs))
    Q = loc[quads[(loc[quads] >= 0).all(1)]]
    e = np.r_[Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]]
    m = len(hs)
    A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (m, m)).tocsr()
    A = ((A + A.T) > 0).astype(float)
    deg = np.asarray(A.sum(1)).ravel()
    L = sp.diags(np.where(deg > 0, 1.0, 0.0)) - sp.diags(1 / np.maximum(deg, 1)) @ A
    w = valid[hs] * np.where((G["upper_lip"] | G["lower_lip"])[hs], R.LIPS, 1.0)
    st = np.clip(1 - (lev[hs] - RING) / STIFF, 0, 1)
    w = w * (1 + 400 * st * st)
    solve = factorized((sp.diags(w) + R.LAM * (L.T @ L) + 1e-9 * sp.identity(m)).tocsc())
    return solve, w


def digest(out: dict) -> str:
    h = hashlib.sha256()
    for k in sorted(out):
        h.update(k.encode())
        h.update(np.ascontiguousarray(out[k]).tobytes())
    return h.hexdigest()


def write_obj(out, path):
    with open(path, "w") as f:
        for v in out["neutral"] + out["offset"]:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        k = 1
        for q, u, p in zip(out["faces"], out["uv"], out["part"]):
            for t in u:
                f.write(f"vt {t[0]:.5f} {t[1]:.5f}\n")
            f.write("f " + " ".join(f"{v + 1}/{k + c}" for c, v in enumerate(q)) + "\n")
            k += 4


def main():
    args = sys.argv[1:]
    if "--edits-from" in args:
        cur = np.load(OUT)
        V = np.array([[float(x) for x in ln.split()[1:4]] for ln in open(args[args.index("--edits-from") + 1]) if ln.startswith("v ")])
        if len(V) != len(cur["neutral"]):
            raise SystemExit(f"the edited OBJ has {len(V)} vertices, the asset {len(cur['neutral'])}: keep the vertex order (Blender: OBJ import/export without 'merge')")
        d = V - cur["neutral"]
        edits = json.loads(EDITS.read_text()) if EDITS.exists() else {}
        mv = {str(int(i)): [round(float(x), 6) for x in d[i]] for i in np.flatnonzero(np.linalg.norm(d, axis=1) > 2e-5)}
        edits["move"] = mv
        EDITS.write_text(json.dumps(edits, indent=1, sort_keys=True))
        print(f"{len(mv)} moved vertices written to {EDITS}; run make_asset.py again to bake them in")
        return
    out = build()
    np.savez_compressed(OUT, **out)
    print("wrote", OUT, OUT.stat().st_size // 1024, "kB;", len(out["neutral"]), "vertices,", len(out["faces"]), "quads")
    print("sha256 of the arrays:", digest(out))
    if "--obj" in args:
        write_obj(out, args[args.index("--obj") + 1])


if __name__ == "__main__":
    main()
