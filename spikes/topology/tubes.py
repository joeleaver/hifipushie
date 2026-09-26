"""Digits as generated tubes stitched to the wrapped template: the template's finger is cut at a closed edge loop
near its base, and rings (the loop's vertex count, angles carried along the chain) are laid along the model's digit
chain, extra rings either side of each knuckle, placed by rays from the axis onto that digit's own primitives (so
touching fingers keep their own sides), closed by a 45 degree ring and a quad fan at the tip. Template digits the
model doesn't have are capped at their loop."""
import numpy as np

from hifipushie import sdf


def quad_topology(L, S):
    st = np.r_[0, np.cumsum(S)[:-1]]
    faces = [list(map(int, L[s:s + k])) for s, k in zip(st, S)]
    nb, ef = {}, {}
    for fi, f in enumerate(faces):
        for k in range(len(f)):
            a, b = f[k], f[(k + 1) % len(f)]
            nb.setdefault(a, set()).add(b)
            nb.setdefault(b, set()).add(a)
            ef.setdefault((min(a, b), max(a, b)), []).append(fi)
    return faces, nb, ef


def walk(u, v, faces, nb, ef, limit=64):
    path = [u, v]
    while len(path) < limit:
        if len(nb[v]) != 4:
            return path, False
        ws = set()
        for fi in ef[(min(u, v), max(u, v))]:
            f = faces[fi]
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


def base_loop(P, faces, nb, ef, base, axis, tipv, max_tip=400, near=0.03):
    """The closed edge loop around a digit nearest its base: across the axis, its vertices all the way round it
    (every 45 degree sector), cutting off at most max_tip vertices on the tip's side."""
    best, seen = None, set()
    L = np.linalg.norm(P[tipv] - base)
    for (a, b) in ef:
        pa = P[a] - base
        sa = pa @ axis
        if not (0.08 * L < sa < 0.7 * L) or np.linalg.norm(pa - sa * axis) > near:
            continue
        e = P[b] - P[a]
        if abs(e @ axis) > 0.35 * np.linalg.norm(e) or (a, b) in seen:
            continue
        path, closed = walk(a, b, faces, nb, ef)
        for k in range(len(path)):
            seen.add((path[k], path[(k + 1) % len(path)]))
        if not closed or not 6 <= len(path) <= 16:
            continue
        q = P[path] - base
        s = float(np.mean(q @ axis))
        c = q.mean(0)
        r = q - c
        r -= np.outer(r @ axis, axis)
        x = r[0] / np.linalg.norm(r[0])
        ang = np.degrees(np.arctan2(r @ np.cross(axis, x), r @ x)) % 360
        if len(set((ang // 45).astype(int))) < 8:
            continue
        cut = tip_side(path, nb, tipv)
        if len(cut) > max_tip:
            continue
        if best is None or s < best[0]:
            best = (s, path)
    return None if best is None else best[1]


def tip_side(loop, nb, tip):
    """Vertices reached from the tip without crossing the loop."""
    seen, stack, stop = {tip}, [tip], set(loop)
    while stack:
        v = stack.pop()
        for w in nb[v]:
            if w not in seen and w not in stop:
                seen.add(w)
                stack.append(w)
    return seen


def _shoot(prims, c, u, r_guess):
    t = np.linspace(0, 4 * r_guess, 160)
    f = sdf.field_at(prims, c[None] + t[:, None] * u[None], clip=False)
    k = np.flatnonzero(f > 0)
    if f[0] > 0 or not len(k):
        return c + r_guess * u
    k = k[0]
    t0, t1, f0, f1 = t[k - 1], t[k], f[k - 1], f[k]
    return c + (t0 + (t1 - t0) * f0 / (f0 - f1)) * u


def chain_point(C, s):
    """Point and direction at arc length s along a polyline C (clamped)."""
    seg = np.linalg.norm(np.diff(C, axis=0), axis=1)
    cum = np.r_[0, np.cumsum(seg)]
    s = np.clip(s, 0, cum[-1])
    i = min(np.searchsorted(cum, s, side="right") - 1, len(seg) - 1)
    d = (C[i + 1] - C[i]) / seg[i]
    return C[i] + (s - cum[i]) * d, d, cum


def tube(loop_pts, C, prims, r_guess, spacing):
    """Rings from the loop (its own positions first) along chain C to the tip: [ring arrays], tip point."""
    c0 = loop_pts.mean(0)
    seg = np.linalg.norm(np.diff(C, axis=0), axis=1)
    cum = np.r_[0, np.cumsum(seg)]
    # the loop moves onto the finger, a finger radius past the knuckle (where it leaves the palm): wherever the wrap
    # left it (on the palm's edge) long quads bridged the gap
    s0 = min(1.5 * r_guess, 0.3 * cum[-1])
    p0, d0, _ = chain_point(C, s0)
    q = loop_pts - c0
    q -= np.outer(q @ d0, d0)
    ref = q[0] / np.linalg.norm(q[0])
    e2 = np.cross(d0, ref)
    ang = np.arctan2(q @ e2, q @ ref)
    stations = list(np.arange(s0 + spacing, cum[-1] - 0.3 * spacing, spacing))
    for kn in cum[1:-1]:  # extra rings either side of each knuckle
        if kn > s0 + 0.5 * spacing:
            stations += [kn - 0.3 * spacing, kn + 0.3 * spacing]
    stations = sorted(stations)
    stations = [s for i, s in enumerate(stations) if i == 0 or s - stations[i - 1] > 0.25 * spacing]
    stations.append(cum[-1])
    dirs = np.cos(ang)[:, None] * ref + np.sin(ang)[:, None] * e2
    rings = [np.array([_shoot(prims, p0, u, r_guess) for u in dirs])]
    for s in stations:
        p, d, _ = chain_point(C, s)
        ref = ref - d * (ref @ d)  # carried along the chain
        ref /= np.linalg.norm(ref)
        e2 = np.cross(d, ref)
        dirs = np.cos(ang)[:, None] * ref + np.sin(ang)[:, None] * e2
        rings.append(np.array([_shoot(prims, p, u, r_guess) for u in dirs]))
    end, d = C[-1], (C[-1] - C[-2]) / np.linalg.norm(C[-1] - C[-2])
    e2 = np.cross(d, ref)
    dirs = np.cos(ang)[:, None] * ref + np.sin(ang)[:, None] * e2
    rings.append(np.array([_shoot(prims, end, (u + d) / np.sqrt(2), r_guess) for u in dirs]))
    tip = _shoot(prims, end, d, r_guess)
    return rings, tip


def stitch(V, faces, loops, digits):
    """Remove each loop's tip side, add tubes (or caps). loops: {name: (loop, tip_vertex)}; digits: {name: (rings,
    tip) or None (cap)}. Returns V, faces."""
    nb = {}
    for f in faces:
        for k in range(len(f)):
            nb.setdefault(f[k], set()).update((f[k - 1], f[(k + 1) % len(f)]))
    drop = set()
    for name, (loop, tipv) in loops.items():
        drop |= tip_side(loop, nb, tipv) - set(loop)
    kept = [f for f in faces if not any(v in drop for v in f)]
    # orientation: the kept face on the palm side of loop edge (a, b) runs a->b or b->a
    directed = {(f[k], f[(k + 1) % len(f)]) for f in kept for k in range(len(f))}
    V = list(map(np.asarray, V))
    new = []
    for name, (loop, _) in loops.items():
        n = len(loop)
        fwd = (loop[0], loop[1]) in directed  # palm face uses loop order: tube faces must run against it
        order = lambda a, b, c, d: (b, a, d, c) if fwd else (a, b, c, d)
        dg = digits.get(name)
        prev = list(loop)
        if dg is None:  # cap: a fan of quads to the loop's centre
            c = len(V)
            V.append(np.mean([V[i] for i in loop], 0))
            for i in range(0, n - 1, 2):
                a, b, cc = loop[i], loop[i + 1], loop[(i + 2) % n]
                new.append(list((cc, b, a, c) if fwd else (a, b, cc, c)))
            if n % 2:
                new.append(list((loop[0], loop[-1], c) if fwd else (loop[-1], loop[0], c)))
            continue
        rings, tip = dg
        for i, v in enumerate(loop):  # the loop becomes the tube's first ring
            V[v] = rings[0][i]
        for R in rings[1:]:
            ids = list(range(len(V), len(V) + n))
            V.extend(R)
            for i in range(n):
                a, b = prev[i], prev[(i + 1) % n]
                c, d = ids[(i + 1) % n], ids[i]
                new.append(list(order(a, b, c, d)))
            prev = ids
        t = len(V)
        V.append(tip)
        for i in range(0, n - 1, 2):
            a, b, c = prev[i], prev[i + 1], prev[(i + 2) % n]
            new.append(list((c, b, a, t) if fwd else (a, b, c, t)))
        if n % 2:
            new.append(list((prev[0], prev[-1], t) if fwd else (prev[-1], prev[0], t)))
    faces = kept + new
    # drop unused vertices
    used = sorted({v for f in faces for v in f})
    remap = {v: i for i, v in enumerate(used)}
    V = np.array([V[v] for v in used])
    faces = [[remap[v] for v in f] for f in faces]
    return V, faces
