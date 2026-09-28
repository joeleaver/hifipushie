"""Digits as generated tubes stitched to the wrapped template: the template's finger is cut at a closed edge loop
near its base, and rings (the loop's vertex count, angles carried along the chain) are laid along the model's digit
chain, extra rings either side of each knuckle, placed by rays from the axis onto that digit's own primitives (so
touching fingers keep their own sides), closed by a 45 degree ring and a quad fan at the tip. Template digits the
model doesn't have are capped at their loop."""
import numpy as np

from hifipushie import sdf, surface


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


def ear_loop(P, faces, nb, ef, tip_pt, reach=0.07, max_cut=800):
    """The outermost closed edge loop round the template's ear (the one cutting off the most vertices, at most
    max_cut, all on the ear's side of the midline): where the ear leaves the skull."""
    tipv = int(np.argmin(np.linalg.norm(P - tip_pt, axis=1)))
    near = set(np.flatnonzero(np.linalg.norm(P - tip_pt, axis=1) < reach))
    best, seen = None, set()
    for (a, b) in ef:
        if a not in near or (a, b) in seen:
            continue
        path, closed = walk(a, b, faces, nb, ef, limit=120)
        for k in range(len(path)):
            seen.add((path[k], path[(k + 1) % len(path)]))
            seen.add((path[(k + 1) % len(path)], path[k]))
        if not closed or len(path) < 6 or not (np.sign(P[path, 0]) == np.sign(tip_pt[0])).all():
            continue
        cut = len(tip_side(path, nb, tipv))
        if cut <= max_cut and tipv not in path and (best is None or cut > best[0]):
            best = (cut, path)
    return None if best is None else best[1]


def eye_loop(P, faces, nb, ef, eye, r_target, reach=0.06):
    """The closed edge loop round the template's eye (winding once round the y axis through its centre, on the
    face's front: the socket tunnel's loops wind too) whose mean radius is nearest r_target. Returns (loop, a
    vertex inside it)."""
    q = P - eye
    near = set(np.flatnonzero((np.hypot(q[:, 0], q[:, 2]) < reach) & (q[:, 1] < 0.03)))
    best, seen = None, set()
    for (a, b) in ef:
        if a not in near or (a, b) in seen:
            continue
        path, closed = walk(a, b, faces, nb, ef, limit=200)
        for k in range(len(path)):
            seen.add((path[k], path[(k + 1) % len(path)]))
            seen.add((path[(k + 1) % len(path)], path[k]))
        if not closed:
            continue
        Q = q[path]
        ang = np.arctan2(Q[:, 2], Q[:, 0])
        wn = np.sum((np.diff(np.r_[ang, ang[:1]]) + np.pi) % (2 * np.pi) - np.pi) / (2 * np.pi)
        if abs(round(wn)) != 1:
            continue
        r = np.hypot(Q[:, 0], Q[:, 2]).mean()
        front = Q[:, 1].mean()
        key = (abs(r - r_target), front)
        if best is None or key < best[0]:
            best = (key, path)
    if best is None:
        return None, None
    loop = best[1]
    inside = [v for v in near if np.hypot(q[v, 0], q[v, 2]) < 0.3 * r_target and v not in loop]
    return loop, int(inside[np.argmin([q[v, 1] for v in inside])]) if inside else None


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


def ring_arc(prims, c, d, ref, n, sign, r_guess, rays=96):
    """n points round the cross-section (plane through c, normal d) at equal arc length, the first in direction ref,
    running with sign (+1: counter-clockwise about d). Flat sections (a blade ear) keep their thin edges: equal
    angles bunch points on the flat faces and leave the rim bare."""
    e2 = np.cross(d, ref)
    a = sign * np.linspace(0, 2 * np.pi, rays, endpoint=False)
    dirs = np.cos(a)[:, None] * ref + np.sin(a)[:, None] * e2
    P = np.array([_shoot(prims, c, u, r_guess) for u in dirs])
    seg = np.linalg.norm(np.diff(np.r_[P, P[:1]], axis=0), axis=1)
    cum = np.r_[0, np.cumsum(seg)]
    t = np.arange(n) / n * cum[-1]
    Q = np.r_[P, P[:1]]
    return np.stack([np.interp(t, cum, Q[:, k]) for k in range(3)], 1)


def clear_start(C, own, full, r_guess, s_min, s_max, tol=3e-4):
    """First arc length along chain C whose cross-section on the digit's own primitives lies on the whole field's
    surface (clear of the palm or skull and its fillet)."""
    for s in np.linspace(s_min, s_max, 12):
        p, d, _ = chain_point(C, s)
        ref = np.cross(d, [0, 0, 1.0]) if abs(d[2]) < 0.9 else np.cross(d, [1.0, 0, 0])
        ref /= np.linalg.norm(ref)
        e2 = np.cross(d, ref)
        a = np.linspace(0, 2 * np.pi, 24, endpoint=False)
        ring = np.array([_shoot(own, p, np.cos(x) * ref + np.sin(x) * e2, r_guess) for x in a])
        if np.abs(sdf.field_at(full, ring, clip=False)).max() < tol:
            return s
    return s_max


def tube(loop_pts, C, prims, r_guess, spacing, s0=None, arc=False):
    """Rings from the loop (its own positions first) along chain C to the tip: [ring arrays], tip point.
    arc: rings at equal arc length (flat sections); spacing then follows each ring's own perimeter."""
    c0 = loop_pts.mean(0)
    seg = np.linalg.norm(np.diff(C, axis=0), axis=1)
    cum = np.r_[0, np.cumsum(seg)]
    # the loop moves onto the finger, a finger radius past the knuckle (where it leaves the palm): wherever the wrap
    # left it (on the palm's edge) long quads bridged the gap
    if s0 is None:
        s0 = min(1.5 * r_guess, 0.3 * cum[-1])
    p0, d0, _ = chain_point(C, s0)
    q = loop_pts - c0
    q -= np.outer(q @ d0, d0)
    ref = q[0] / np.linalg.norm(q[0])
    e2 = np.cross(d0, ref)
    ang = np.arctan2(q @ e2, q @ ref)
    if arc:
        return _arc_tube(C, cum, prims, s0, ref, d0, ang, len(loop_pts), r_guess)
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


def _arc_tube(C, cum, prims, s0, ref, d0, ang, n, r_guess):
    dw = (np.diff(np.r_[ang, ang[:1]]) + np.pi) % (2 * np.pi) - np.pi
    sign = 1.0 if np.median(dw) > 0 else -1.0
    rings = [ring_arc(prims, chain_point(C, s0)[0], d0, ref, n, sign, r_guess)]
    per = lambda R: np.linalg.norm(np.diff(np.r_[R, R[:1]], axis=0), axis=1).sum()
    sp0 = per(rings[0]) / n
    s, end = s0, cum[-1]
    while True:
        s += max(per(rings[-1]) / n, 0.4 * sp0)
        if s > end - 0.3 * sp0:
            break
        p, d, _ = chain_point(C, s)
        ref = ref - d * (ref @ d)
        ref /= np.linalg.norm(ref)
        rings.append(ring_arc(prims, p, d, ref, n, sign, r_guess))
    d = (C[-1] - C[-2]) / np.linalg.norm(C[-1] - C[-2])
    tip = _shoot(prims, C[-1], d, r_guess)
    return rings, tip


def _exit(prims, c, dirs, reach, steps=240):
    """Where rays from c (inside) first leave the surface: (points, distances)."""
    t = np.linspace(0, reach, steps)
    f = sdf.field_at(prims, c[None, None] + t[None, :, None] * dirs[:, None], margin=0.02)
    out = f > 0
    k = np.where(out.any(1), out.argmax(1), steps - 1)
    k = np.maximum(k, 1)
    i = np.arange(len(dirs))
    f0, f1 = f[i, k - 1], f[i, k]
    tt = t[k - 1] + (t[k] - t[k - 1]) * np.clip(f0 / np.where(f0 - f1 == 0, -1, f0 - f1), 0, 1)
    return c + tt[:, None] * dirs, tt


def eye_patch(loop_pts, c, rot, prims, reach, voxel=0.002, n_samp=160, phi_max=1.3):
    """An eye region as rings from a cut loop on the face inward, by rays from the eye centre c (the lids blob's
    centre and frame rot, looking along local -y: its opening walls are radial, so the surface is star-shaped from
    c): each loop vertex is a spoke at its own azimuth; along it, the lid's outer surface down to the margin (where
    the first exit drops from lid to eyeball), a ring on the lid's edge, one on the eyeball at the edge, the eyeball
    in to its pole. Rings are spaced by arc length so quads stay near square. Returns (rings, pole point)."""
    n = len(loop_pts)
    q = (loop_pts - c) @ rot  # local
    fw = np.array([0, -1.0, 0])
    phi0 = np.arccos(np.clip((q @ fw) / np.linalg.norm(q, axis=1), -1, 1))
    th = np.arctan2(q[:, 2], q[:, 0])

    def world(phi, the):
        loc = np.stack([np.sin(phi) * np.cos(the), -np.cos(phi), np.sin(phi) * np.sin(the)], -1)
        return loc @ rot.T

    spokes, margins = [], []
    for i in range(n):  # rays only within the lids' cone: further out the head isn't star-shaped from c
        ph = np.linspace(min(phi0[i], phi_max), 0.0, n_samp)
        P, R = _exit(prims, c, world(ph, np.full(n_samp, th[i])), reach)
        jump = np.diff(R)
        m = int(np.argmin(jump))  # the biggest drop: lid edge -> eyeball
        spokes.append((ph, P, R))
        margins.append(m if jump[m] < -0.05 * R[m] else None)
    if any(m is None for m in margins):  # shut eye: the lids meet at the pole
        margins = [len(sp_[0]) - 2 for sp_ in spokes]
    per = np.linalg.norm(np.diff(np.r_[loop_pts, loop_pts[:1]], axis=0), axis=1).sum()
    sp = per / n
    E = np.array([P[m] for (ph, P, R), m in zip(spokes, margins)])      # lid edge
    lid_len = np.linalg.norm(E - loop_pts, axis=1).mean()
    n_lid = max(1, int(round(lid_len / sp)))
    rings = [loop_pts.copy()]
    for k in range(1, n_lid):  # loop -> lid edge: straight across, dropped onto the surface
        t = k / n_lid
        X = (1 - t) * loop_pts + t * E
        rings.append(surface.newton(prims, X, voxel * 0.125, voxel, iterations=12)[0])
    rings.append(E)
    arcs = [np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))] for ph, P, R in spokes]
    ball_len = np.mean([seg[-1] - seg[m + 1] for seg, m in zip(arcs, margins)])
    n_ball = int(round(ball_len / sp))
    for k in range(0, n_ball + 1):  # the eyeball: from its edge under the lid margin in to the pole
        ring = []
        for (ph, P, R), seg, m in zip(spokes, arcs, margins):
            s0, s1 = seg[m + 1], seg[-1]
            s_ = s0 + (s1 - s0) * k / (n_ball + 1)
            ring.append([np.interp(s_, seg, P[:, j]) for j in range(3)])
        rings.append(np.array(ring))
    pole = _exit(prims, c, world(np.array([0.0]), np.array([0.0])), reach)[0][0]
    return rings, pole


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
    n_orig = len(V)
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
    stitch.n_template = sum(1 for v in used if v < n_orig)  # template vertices come first
    V = np.array([V[v] for v in used])
    faces = [[remap[v] for v in f] for f in faces]
    return V, faces
