"""Creature topology from the model's own skeleton (parts.<p>.topology = "limbs"): edge loops where a cartoon or a
creature bends, the way an artist retopologises a rough sculpt, without any template (no human base mesh: huge
heads, no necks, stubby limbs and tails have no template to come from).

Steps (`build`), per limb root of the part (`anatomy.limb_roots`: a hip, a shoulder):
1. Tube: quad rings along the limb's chain, each shot onto the exact surface from the chain (rays in the ring's
   plane, `RING` round). The first ring IS the root's loop plane (`anatomy.loop_planes`: over the cap, the front
   and back pits: at a hip the groin and the glute fold); each hinge gets a ring on its crease plane and one either
   side `HINGE_PACK` x a step away (topodensity's rule: loops packed where it bends, sparse along the shaft);
   between keys the ring planes turn smoothly from one key's normal to the next. Steps are square quads (a ring's
   perimeter / RING), the end capped by a ring lifted 45 degrees and a fan of quads.
2. Junction: `JUNCTION` more rings outward from the root ring into the body, each point walked across the surface
   (re-projected every sub-step) one step away from the limb and held off the midline (`MID_MARGIN`: a pair of legs
   meeting at the crotch don't cross), each ring evened along itself.
3. Body: the part's own mesh decimated (`body_triangles`), everything inside the outermost junction ring cut away
   (largest piece kept), and the hole's edge zipped to that ring by triangles; the zip's body side relaxed on the
   surface. The rest of the body stays decimated for now (torso / head loops are later runs).
`quality` measures a result: closed quad rings at the anatomy's loop planes, field distance, turned faces.
"""
from __future__ import annotations

import numpy as np

from . import anatomy, kits, retopo, sdf, surface

RING = 16          # vertices round a limb ring
HINGE_PACK = 0.4   # x a step: the extra rings either side of a hinge's crease ring
JUNCTION = 2       # rings from the root loop out into the body
MID_MARGIN = 0.006  # m: junction rings stay this far off the midline (x = 0)
CROTCH = 0.6       # the junction's inner side stays this share of the root ring's distance off the midline
UP_SHARE = 0.5     # the junction's walk: outward from the limb's axis plus this much up it
REACH = 2.5        # x the joint radius: how far a ring's rays look for the surface
CLEAR = 1.35       # x the joint radius: a ring with a longer ray runs out across the body (not the limb's own)
ON_PLANE = 0.4     # x the radius: how far off its loop plane a ring may lie and still count (quality)
ZIP_MARGIN = 0.3   # x a step: the body cut reaches this far past the outermost junction ring
ZIP_RELAX = 2      # rings of body vertices round the zip relaxed on the surface


def _unit(v):
    v = np.asarray(v, float)
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-12)


def _pos(spec, j):
    return np.asarray(spec["joints"][j]["pos"], float)


def limbs(spec: dict, part: str = "body") -> list[dict]:
    """The part's limb roots with their chains and loop planes, both sides: [{"label", "side", "C" (chain points),
    "r" (radii), "planes": [(s along the chain, point, normal, label)]}]."""
    s = kits.expand(spec)
    planes = {p["label"]: p for p in anatomy.loop_planes(s)}
    out = []
    for root in anatomy.limb_roots(s):
        b = s["bones"].get(root["bone"], {})
        if (b.get("part") or "body") != part:
            continue
        C = np.array([_pos(s, j) for j in root["chain"]])
        r = np.array([float(s["joints"][j].get("r", 0.05)) for j in root["chain"]])
        for m, side in ((np.array([1.0, 1, 1]), "L"), (np.array([-1.0, 1, 1]), "R")):
            if side == "R" and not s.get("symmetry", True):
                continue
            keys = []
            for j in root["chain"][:-1]:
                p = planes.get(j)
                if p is not None:
                    keys.append((j.replace(".L", "." + side), np.asarray(p["point"]) * m, _unit(np.asarray(p["normal"]) * m)))
            out.append({"label": root["joint"].replace(".L", "." + side), "side": 1.0 if side == "L" else -1.0,
                        "C": C * m, "r": r, "keys": keys})
    return out


def _arc(C):
    return np.r_[0, np.cumsum(np.linalg.norm(np.diff(C, axis=0), axis=1))]


def _at(C, cum, s):
    """Point and direction on the chain at arc length s (extrapolated past both ends)."""
    i = int(np.clip(np.searchsorted(cum, s, side="right") - 1, 0, len(C) - 2))
    d = _unit(C[i + 1] - C[i])
    return C[i] + (s - cum[i]) * d, d


def _ring(prims, c, n, ref, r, lift=0.0):
    """RING points where rays from c (in the plane of normal n, from ref round) leave the surface."""
    ref = _unit(ref - n * (ref @ n))
    e2 = np.cross(n, ref)
    a = np.linspace(0, 2 * np.pi, RING, endpoint=False)
    dirs = _unit(np.cos(a)[:, None] * ref + np.sin(a)[:, None] * e2 + lift * n)
    P, t = retopo._exit(prims, c, dirs, REACH * r)
    return P, ref


def _onto_line(C, cum, p, n):
    """Arc length where the chain crosses the plane (p, n) (its first bone's line extended)."""
    best = None
    for i in range(len(C) - 1):
        d = C[i + 1] - C[i]
        den = d @ n
        if abs(den) < 1e-9:
            continue
        t = ((p - C[i]) @ n) / den
        s = cum[i] + t * np.linalg.norm(d)
        if best is None or abs(t - 0.5) < abs(best[1] - 0.5):
            best = (s, t)
    return best[0]


def _radius_at(limb, cum, s):
    """The spec's joint radius interpolated along the chain."""
    return float(np.interp(s, cum[:len(limb["r"])], limb["r"]))


def _clear(R, c, r):
    """A ring is the limb's own when every ray left the surface within CLEAR x its radius (not out across the belly)."""
    return bool(np.linalg.norm(R - c, axis=1).max() < CLEAR * r)


def tube(prims, limb: dict, voxel: float):
    """Rings along the limb (lists of RING points, root first), the tip point, each ring's key label (or None), the
    step, and the root's (point, normal). The root ring is the highest cross-section the limb owns (`_clear`): at
    a person's hip that is the loop plane itself; a stub sunk in a belly (Puddles: thigh and knee inside it) leaves
    the body lower, and its root ring goes there, tilted like the loop plane when that tilt is clear too. Keys above
    the root (inside the body) get no ring: the junction's rings stand for them."""
    C = limb["C"]
    rr = float(np.mean(limb["r"]))
    step = 2 * np.pi * rr / RING
    dend = _unit(C[-1] - C[-2])
    tip_t = retopo._exit(prims, C[-1], dend[None], 4 * limb["r"][-1])[1][0]
    Cx = np.r_[C, C[-1:] + dend * tip_t]
    cum = _arc(Cx)
    end = cum[-1] - 0.6 * step
    ref0 = np.array([0, -1.0, 0])
    keys = []
    for lab, p, n in limb["keys"]:
        s = _onto_line(Cx, cum, p, n)
        keys.append((s, p if lab == limb["label"] else _at(Cx, cum, s)[0], n, lab))
    # the root: walk up from the shaft to the highest clear cross-section (bone-normal plane, then the root's tilt)
    nh = keys[0][2]

    def ring_s(s, n):
        c, d = _at(Cx, cum, s)
        n = n if n @ d > 0 else -n
        return _ring(prims, c, n, ref0, rr)[0], c, n
    lo_s, hi_s = keys[0][0], end
    if _clear(ring_s(lo_s, nh)[0], ring_s(lo_s, nh)[1], _radius_at(limb, cum, lo_s)):
        root_s = lo_s
    else:
        for _ in range(12):  # bisect: hi_s clear, lo_s not
            mid = 0.5 * (lo_s + hi_s)
            R, c, _ = ring_s(mid, _at(Cx, cum, mid)[1])
            if _clear(R, c, _radius_at(limb, cum, mid)):
                hi_s = mid
            else:
                lo_s = mid
        root_s = hi_s
    R, c, n = ring_s(root_s, nh)
    root_n = n if _clear(R, c, _radius_at(limb, cum, root_s)) else ring_s(root_s, _at(Cx, cum, root_s)[1])[2]
    root = (root_s, _at(Cx, cum, root_s)[0], root_n, limb["label"])
    keys = [root] + [k for k in keys[1:] if k[0] > root_s + 0.5 * step]
    stations = [(k[0], k) for k in keys]
    for k in keys[1:]:
        stations += [(k[0] - HINGE_PACK * step, None), (k[0] + HINGE_PACK * step, None)]
    taken = sorted(x[0] for x in stations)
    s = root_s + step
    while s < end:
        if min(abs(s - t) for t in taken) > 0.6 * step:
            stations.append((s, None))
        s += step
    stations.append((end, None))
    stations.sort(key=lambda x: x[0])

    def normal(s):
        _, d = _at(Cx, cum, s)
        prv = [k for k in keys if k[0] <= s][-1]
        nxt = [k for k in keys if k[0] > s]
        if nxt:
            w = (s - prv[0]) / max(nxt[0][0] - prv[0], 1e-9)
            return _unit((1 - w) * prv[2] + w * nxt[0][2])
        w = np.clip((s - prv[0]) / max(end - prv[0], 1e-9), 0, 1)
        return _unit((1 - w) * prv[2] + w * d)
    ref = ref0
    rings, labels = [], []
    for s, key in stations:
        n = normal(s)
        if n @ _at(Cx, cum, s)[1] < 0:
            n = -n
        c = key[1] if key is not None else _at(Cx, cum, s)[0]
        R, ref = _ring(prims, c, n, ref, rr)
        rings.append(R)
        labels.append(key[3] if key is not None else None)
    c, d = _at(Cx, cum, end)
    R, _ = _ring(prims, c, d, ref, rr, lift=1.0)
    rings.append(R)
    labels.append(None)
    tip = retopo._exit(prims, c, d[None], 4 * rr)[0][0]
    return rings, tip, labels, step, (root[1], root[2])


def _project(prims, X, voxel, it=8):
    return surface.newton(prims, X, voxel * 0.125, voxel, iterations=it)[0]


def _even(prims, R, voxel):
    """A closed ring respaced at equal arc length (no smoothing: that shrinks a ring back onto the limb), from the
    point nearest its first, back on the surface."""
    Q = np.r_[R, R[:1]]
    cum = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
    t = np.arange(len(R)) / len(R) * cum[-1]
    X = np.stack([np.interp(t, cum, Q[:, k]) for k in range(3)], 1)
    return _project(prims, X, voxel, 6)


def junction(prims, root, n_root, side, step, voxel, count=JUNCTION):
    """Rings walked out from the root ring across the surface, away from the limb: outward from its axis and up it
    (`UP_SHARE`; walking only up the limb runs into a belly's underside), re-projected every sub-step. The inner side
    holds `CROTCH` of the root ring's distance from the midline (a pair of legs keeps a strip of body between them)."""
    rings, P = [], root.copy()
    co = root.mean(0)
    hold_x = max(MID_MARGIN, CROTCH * float((root[:, 0] * side).min()))
    sub = 8
    for _ in range(count):
        for _ in range(sub):
            g = _unit(sdf.gradient(prims, P, 1e-4))
            q = P - co
            rad = _unit(q - np.outer(q @ n_root, n_root))
            t = rad - UP_SHARE * n_root
            t = t - g * (g * t).sum(1, keepdims=True)
            P2 = _project(prims, P + _unit(t) * step / sub, voxel, 4)
            hold = P2[:, 0] * side < hold_x
            P = np.where(hold[:, None], P, P2)
        P = _even(prims, P, voxel)
        rings.append(P.copy())
    return rings


def _boundary_loops(F):
    nxt = {}
    E = {}
    for f in F:
        for k in range(3):
            a, b = int(f[k]), int(f[(k + 1) % 3])
            E[(a, b)] = E.get((a, b), 0) + 1
    for (a, b) in E:
        if (b, a) not in E:
            nxt[a] = b
    loops, seen = [], set()
    for a in nxt:
        if a in seen:
            continue
        loop, v = [], a
        while v not in seen and v in nxt:
            seen.add(v)
            loop.append(v)
            v = nxt[v]
        if len(loop) > 2:
            loops.append(loop)
    return loops


def _clean_cut(F, removed, rounds=20):
    """Faces next to the cut removed until every hole's edge is a simple loop: no vertex with two boundary edges
    leaving it (a bow-tie) and no face with two boundary edges (a spike)."""
    for _ in range(rounds):
        E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
        key = E[:, 0] * (F.max() + 1) + E[:, 1]
        rev = E[:, 1] * (F.max() + 1) + E[:, 0]
        bd = ~np.isin(key, rev)
        out = np.bincount(E[bd, 0], minlength=F.max() + 1)
        per_face = bd.reshape(3, -1).sum(0)
        bad = (out[F] > 1).any(1) | (per_face >= 2)
        if not bad.any():
            break
        F = F[~bad]
    return F


def _largest(V, F):
    import scipy.sparse as sp
    import scipy.sparse.csgraph as cg
    n = len(V)
    A = sp.coo_matrix((np.ones(3 * len(F)), (F.ravel(), np.roll(F, 1, 1).ravel())), shape=(n, n))
    _, lab = cg.connected_components(A, directed=False)
    big = np.bincount(lab[F[:, 0]]).argmax()
    return F[lab[F[:, 0]] == big]


def _zip(O, B, VO, VB, n_ax):
    """Triangles between ring O (ids) and loop B (ids), both ordered the same way round n_ax."""
    n, m = len(O), len(B)
    j0 = int(np.argmin(np.linalg.norm(VB - VO[0], axis=1)))
    B = list(B[j0:]) + list(B[:j0])
    VB = np.r_[VB[j0:], VB[:j0]]
    i = j = 0
    tri = []
    while i < n or j < m:
        a_ok, b_ok = i < n, j < m
        if a_ok and b_ok:
            da = np.linalg.norm(VO[(i + 1) % n] - VB[j % m])
            db = np.linalg.norm(VO[i % n] - VB[(j + 1) % m])
            adv_i = da <= db
        else:
            adv_i = a_ok
        if adv_i:
            tri.append([O[i % n], O[(i + 1) % n], B[j % m]])
            i += 1
        else:
            tri.append([O[i % n], B[(j + 1) % m], B[j % m]])
            j += 1
    return tri


def _turn(P, c, n):
    q = P - c
    a = np.arctan2(q @ np.cross(n, _unit(q[0] - n * (q[0] @ n))), q @ _unit(q[0] - n * (q[0] @ n)))
    dw = (np.diff(np.r_[a, a[:1]]) + np.pi) % (2 * np.pi) - np.pi
    return np.sign(dw.sum())


def _inside(X, O, co, no, step):
    """Points on the limb's side of ring O: past its plane (less a quarter step) and within its outline (its polar
    radius at their angle round the ring, plus ZIP_MARGIN of a step)."""
    e1 = _unit(O[0] - co - no * ((O[0] - co) @ no))
    e2 = np.cross(no, e1)

    def polar(P):
        q = P - co
        return np.arctan2(q @ e2, q @ e1), np.linalg.norm(q - np.outer(q @ no, no), axis=1)
    ao, ro = polar(O)
    k = np.argsort(ao)
    ax, rx = polar(X)
    rr = np.interp(ax, ao[k], ro[k], period=2 * np.pi)
    return ((X - co) @ no > -0.25 * step) & (rx < rr + ZIP_MARGIN * step)


def decimate(V, F, triangles: int):
    import pyfqmr
    s = pyfqmr.Simplify()
    s.setMesh(np.asarray(V, np.float64), np.asarray(F, np.int32))
    s.simplify_mesh(target_count=int(triangles), aggressiveness=7, preserve_border=True, verbose=0)
    v, f, _ = s.getMesh()
    return np.asarray(v, float), np.asarray(f, int)


def build(spec: dict, prims, V, F, voxel: float, body_triangles: int, part: str = "body", log: list | None = None):
    """{"verts", "loops", "sizes", "rings": {label: vertex ids of the key ring}, "planes"} for the part: limb tubes
    and junctions, the body's fine mesh cut inside the outermost junction ring and zipped to it, then decimated with
    those rings as its border (kept exactly: the zip's fan melts into the body's triangles; cut after decimating,
    a one-triangle crotch strip let the two holes meet)."""
    log = log if log is not None else []
    V = np.asarray(V, float)
    F = np.asarray(F, int)
    cut = np.zeros(len(V), bool)
    limbs_ = []
    planes = {}
    for limb in limbs(spec, part):
        rings, tip, labels, step, rootp = tube(prims, limb, voxel)
        r = float(np.mean(limb["r"]))
        planes[limb["label"] + " (slid to the root ring)"] = (rootp[0], rootp[1], r)
        for lab, p, n in limb["keys"]:
            planes[lab] = (p, n, r)
        n_root = rootp[1]
        J = junction(prims, rings[0], n_root, limb["side"], step, voxel)
        O = J[-1]
        co = O.mean(0)
        no = np.linalg.svd(O - co)[2][2]
        no = no if no @ n_root > 0 else -no
        cut |= _inside(V, O, co, no, step) & (V[:, 0] * limb["side"] > 0)
        limbs_.append((limb, J[::-1] + rings, [None] * len(J) + labels, tip, co, no))
        log.append(f"{limb['label']}: {len(rings)} rings of {RING} (keys {', '.join(l for l in labels if l)}), "
                   f"{len(J)} junction rings, step {step * 1000:.0f} mm")
    Fk = _largest(V, _clean_cut(_largest(V, F[~cut[F].any(1)]), cut))
    loops = _boundary_loops(Fk)
    if len(loops) != len(limbs_):
        raise ValueError(f"limbs: the body cut left {len(loops)} holes for {len(limbs_)} limbs")
    # zip each hole to its outermost ring (appended after the body's vertices), on the fine mesh
    Vz, Fz = [V], [Fk]
    nv = len(V)
    for limb, allr, labels, tip, co, no in limbs_:
        lp = np.array(min(loops, key=lambda L: np.linalg.norm(V[L].mean(0) - co)))
        loops = [x for x in loops if x is not lp and not np.array_equal(x, lp)]
        O = allr[0]
        oid = np.arange(nv, nv + RING)
        Vz.append(O)
        nv += RING
        Vall = np.concatenate(Vz)
        # the hole runs against the body's winding; the ring goes the same way round
        if _turn(Vall[lp], co, no) != _turn(O, co, no):
            O_ord = oid[::-1]
        else:
            O_ord = oid
        tri = np.array(_zip(list(O_ord), list(lp), Vall[O_ord], Vall[lp], no))
        Fz.append(tri[:, ::-1] if _wound_in(Vall, tri, prims) else tri)
    Vz, Fz = np.concatenate(Vz), np.concatenate(Fz)
    Vd, Fd = decimate(Vz, Fz, body_triangles)
    # the rings came through as the border, exactly: find them again by position
    from scipy.spatial import cKDTree
    tree = cKDTree(Vd)
    verts, faces = [Vd], [list(map(int, f)) for f in Fd]
    nv = len(Vd)
    fixed = []
    keyrings = {}
    for limb, allr, labels, tip, co, no in limbs_:
        d, oid = tree.query(allr[0])
        if d.max() > 1e-7:
            raise ValueError(f"limbs: {limb['label']}'s junction ring didn't survive the decimation ({d.max():.2g} m)")
        ids = [oid]
        for R in allr[1:]:
            ids.append(np.arange(nv, nv + RING))
            verts.append(R)
            nv += RING
        verts.append(tip[None])
        tip_id = nv
        nv += 1
        fixed += [i for x in ids for i in x] + [tip_id]
        for lab, rid in zip(labels, ids):
            if lab:
                keyrings[lab] = rid.tolist()
        quads = [[a[k], a[(k + 1) % RING], b[(k + 1) % RING], b[k]] for a, b in zip(ids[:-1], ids[1:]) for k in range(RING)]
        last = ids[-1]
        quads += [[last[k], last[k + 1], last[(k + 2) % RING], tip_id] for k in range(0, RING, 2)]
        Vall = np.concatenate(verts)
        if _wound_in(Vall, np.array(quads), prims):
            quads = [q[::-1] for q in quads]
        faces += [list(map(int, q)) for q in quads]
    Vout = np.concatenate(verts)
    L = np.array([v for f in faces for v in f])
    S = np.array([len(f) for f in faces])
    fx = np.zeros(len(Vout), bool)
    fx[fixed] = True
    Vout = _relax_zip(prims, Vout, L, S, fx, voxel)
    Vout = retopo._untangle(Vout, L, S, prims, voxel, fx, log=log)
    log.append(f"limbs: {len(S)} faces ({(S == 4).mean():.0%} quads, {int((S - 2).sum())} triangles), body "
               f"decimated to {len(Fd)} triangles ({int(cut.sum())} fine vertices cut for the limbs)")
    return {"verts": Vout, "loops": L, "sizes": S, "rings": keyrings, "planes": planes}


def _wound_in(V, faces, prims):
    """Most faces' normals against the field's gradient (wound inward)."""
    f = np.asarray(faces)
    c = V[f].mean(1)
    fn = np.cross(V[f[:, 1]] - V[f[:, 0]], V[f[:, 2]] - V[f[:, 0]])
    return bool(((fn * sdf.gradient(prims, c, 1e-4)).sum(1) < 0).mean() > 0.5)


def _relax_zip(prims, V, L, S, fixed, voxel, rounds=20):
    """The body vertices next to the generated rings (ZIP_RELAX rings of them) relaxed along the surface."""
    E = retopo.edges(L, S)
    m = np.zeros(len(V), bool)
    m[fixed] = True
    for _ in range(ZIP_RELAX):
        m[E[m[E[:, 0]], 1]] = True
        m[E[m[E[:, 1]], 0]] = True
    m &= ~fixed
    deg = np.bincount(E.ravel(), minlength=len(V))
    T = retopo.tris(L, S)
    for _ in range(rounds):
        N = retopo._vnormals(V, T)
        lap = retopo._lap(V, E, deg)
        dv = lap - (lap * N).sum(1, keepdims=True) * N
        V = V.copy()
        V[m] = _project(prims, V[m] + 0.5 * dv[m], voxel, 6)
    return V


def quality(V, L, S, spec: dict, prims, part: str = "body", planes: dict | None = None) -> dict:
    """Closed quad rings at the loop planes (planes: {label: (point, normal, r)}, default the anatomy's; build()
    returns its own, the root slid to its ring), per label found / edges / worst distance off the plane in mm; field
    distance at the vertices (mean / p99 mm), turned triangles, quad share."""
    faces, nb, ef = retopo.topology(L, S)
    if planes is None:
        planes = {lab: (p, n, float(np.mean(limb["r"]))) for limb in limbs(spec, part) for lab, p, n in limb["keys"]}
    rc = {}
    for lab, (p, n, r) in planes.items():
        p, n = np.asarray(p, float), np.asarray(n, float)
        d = (V - p) @ n
        dist = np.linalg.norm(V - p, axis=1)
        best = None
        for (a, b) in ef:
            if abs(d[a] + d[b]) / 2 > 0.4 * r or max(dist[a], dist[b]) > REACH * r:
                continue
            ev = V[b] - V[a]
            if abs(ev @ n) > 0.4 * np.linalg.norm(ev):
                continue
            path, closed = retopo._walk(a, b, faces, nb, ef)
            if closed and dist[path].max() < 3 * r:
                dev = float(np.abs(d[path]).max())
                if best is None or dev < best[0]:
                    best = (dev, path)
        # a ring counts when it lies within ON_PLANE x the radius of the plane (a far one is another loop)
        rc[lab] = ({"ring": bool(best[0] < ON_PLANE * r), "edges": len(best[1]), "off_plane_mm": round(best[0] * 1000, 1)}
                   if best else {"ring": False})
    T = retopo.tris(L, S)
    fd = np.abs(sdf.field_at(prims, V, clip=False)) * 1000
    return {"rings": rc, "closed": f"{sum(v['ring'] for v in rc.values())}/{len(rc)}",
            "field_mm": (round(float(fd.mean()), 2), round(float(np.percentile(fd, 99)), 1)),
            "turned": int(retopo.turned(V, T, prims).sum()), "quads": round(float((S == 4).mean()), 2),
            "faces": len(S), "triangles": int((S - 2).sum())}
