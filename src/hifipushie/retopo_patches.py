"""Loops and patches: base, ear and eye loops, tubes and arc tubes, the cut plan, patches, the stitch. Part of retopo (retopo.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import sdf
from .spec import resolve_point
from .retopo import _frame, _tip_side, _unit, _walk, topology
from .retopo_warp import _carry

# ---------------------------------------------------------------------------------------------------- loops
def _base_loop(P, faces, nb, ef, base, axis, tipv, max_tip=400, near=0.03):
    """The closed loop round a digit nearest its base: across the axis, all the way round (every 45 degree
    sector), cutting off at most max_tip vertices on the tip's side."""
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
        path, closed = _walk(a, b, faces, nb, ef)
        for k in range(len(path)):
            seen.add((path[k], path[(k + 1) % len(path)]))
        if not closed or not 6 <= len(path) <= 16:
            continue
        q = P[path] - base
        s = float(np.mean(q @ axis))
        r = q - q.mean(0)
        r -= np.outer(r @ axis, axis)
        x = r[0] / np.linalg.norm(r[0])
        ang = np.degrees(np.arctan2(r @ np.cross(axis, x), r @ x)) % 360
        if len(set((ang // 45).astype(int))) < 8 or len(_tip_side(path, nb, tipv)) > max_tip:
            continue
        if best is None or s < best[0]:
            best = (s, path)
    return None if best is None else best[1]


def _loops_round(P, faces, nb, ef, near, limit):
    """Closed loops through the `near` vertices: yields paths."""
    seen = set()
    for (a, b) in ef:
        if a not in near or (a, b) in seen:
            continue
        path, closed = _walk(a, b, faces, nb, ef, limit=limit)
        for k in range(len(path)):
            seen.add((path[k], path[(k + 1) % len(path)]))
            seen.add((path[(k + 1) % len(path)], path[k]))
        if closed and len(path) >= 6:
            yield path


def _ear_loop(P, faces, nb, ef, tip_pt, reach=0.07, max_cut=800):
    """The outermost closed loop round the template's ear (cutting off the most vertices, at most max_cut, all on
    the ear's side): where the ear leaves the skull. Returns (loop, tip vertex)."""
    tipv = int(np.argmin(np.linalg.norm(P - tip_pt, axis=1)))
    best = None
    for path in _loops_round(P, faces, nb, ef, set(np.flatnonzero(np.linalg.norm(P - tip_pt, axis=1) < reach)), 120):
        if not (np.sign(P[path, 0]) == np.sign(tip_pt[0])).all() or tipv in path:
            continue
        cut = len(_tip_side(path, nb, tipv))
        if cut <= max_cut and (best is None or cut > best[0]):
            best = (cut, path)
    return (None, None) if best is None else (best[1], tipv)


def _eye_loop(P, faces, nb, ef, eye, r_target, reach=0.06):
    """The closed loop round the template's eye (winding once round the y axis through it) whose mean radius is
    nearest r_target, the frontmost of equals (the socket tunnel's loops wind too). Returns (loop, inner vertex)."""
    q = P - eye
    near = set(np.flatnonzero((np.hypot(q[:, 0], q[:, 2]) < reach) & (q[:, 1] < 0.03)))
    best = None
    for path in _loops_round(P, faces, nb, ef, near, 200):
        Q = q[path]
        ang = np.arctan2(Q[:, 2], Q[:, 0])
        wn = np.sum((np.diff(np.r_[ang, ang[:1]]) + np.pi) % (2 * np.pi) - np.pi) / (2 * np.pi)
        if abs(round(wn)) != 1:
            continue
        key = (abs(np.hypot(Q[:, 0], Q[:, 2]).mean() - r_target), Q[:, 1].mean())
        if best is None or key < best[0]:
            best = (key, path)
    if best is None:
        return None, None
    inside = [v for v in near if np.hypot(q[v, 0], q[v, 2]) < 0.3 * r_target and v not in best[1]]
    return best[1], (int(inside[np.argmin([q[v, 1] for v in inside])]) if inside else None)


# ---------------------------------------------------------------------------------------------------- patches
def _shoot(prims, c, u, r_guess):
    """First exit along c + t u (c inside), t up to 4 r_guess."""
    t = np.linspace(0, 4 * r_guess, 160)
    f = sdf.field_at(prims, c[None] + t[:, None] * u[None], clip=False)
    k = np.flatnonzero(f > 0)
    if f[0] > 0 or not len(k):
        return c + r_guess * u
    k = k[0]
    t0, t1, f0, f1 = t[k - 1], t[k], f[k - 1], f[k]
    return c + (t0 + (t1 - t0) * f0 / (f0 - f1)) * u


def _exit(prims, c, dirs, reach, steps=240):
    """Where rays from c (inside) first leave the surface: (points, distances)."""
    t = np.linspace(0, reach, steps)
    f = sdf.field_at(prims, c[None, None] + t[None, :, None] * dirs[:, None], margin=0.02)
    out = f > 0
    k = np.maximum(np.where(out.any(1), out.argmax(1), steps - 1), 1)
    i = np.arange(len(dirs))
    f0, f1 = f[i, k - 1], f[i, k]
    tt = t[k - 1] + (t[k] - t[k - 1]) * np.clip(f0 / np.where(f0 - f1 == 0, -1, f0 - f1), 0, 1)
    return c + tt[:, None] * dirs, tt


def _chain_point(C, s):
    seg = np.linalg.norm(np.diff(C, axis=0), axis=1)
    cum = np.r_[0, np.cumsum(seg)]
    s = np.clip(s, 0, cum[-1])
    i = min(np.searchsorted(cum, s, side="right") - 1, len(seg) - 1)
    d = (C[i + 1] - C[i]) / seg[i]
    return C[i] + (s - cum[i]) * d, d, cum


def _ring_arc(prims, c, d, ref, n, sign, r_guess, rays=96):
    """n points round the cross-section (plane through c, normal d) at equal arc length from direction ref: flat
    sections keep their thin edges (equal angles bunch points on the flat faces and leave the rim bare)."""
    e2 = np.cross(d, ref)
    a = sign * np.linspace(0, 2 * np.pi, rays, endpoint=False)
    P = np.array([_shoot(prims, c, np.cos(x) * ref + np.sin(x) * e2, r_guess) for x in a])
    Q = np.r_[P, P[:1]]
    cum = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
    t = np.arange(n) / n * cum[-1]
    return np.stack([np.interp(t, cum, Q[:, k]) for k in range(3)], 1)


def _clear_start(C, own, full, r_guess, s_max, tol=3e-4):
    """First arc length along chain C whose cross-section on the part's own primitives lies on the whole field's
    surface (clear of the skull and its fillet)."""
    for s in np.linspace(0.0, s_max, 12):
        p, d, _ = _chain_point(C, s)
        ref, e2 = _frame(d)
        a = np.linspace(0, 2 * np.pi, 24, endpoint=False)
        ring = np.array([_shoot(own, p, np.cos(x) * ref + np.sin(x) * e2, r_guess) for x in a])
        if np.abs(sdf.field_at(full, ring, clip=False)).max() < tol:
            return s
    return s_max


def _loop_frame(pts, d):
    q = pts - pts.mean(0)
    q -= np.outer(q @ d, d)
    ref = q[0] / np.linalg.norm(q[0])
    ang = np.arctan2(q @ np.cross(d, ref), q @ ref)
    dw = (np.diff(np.r_[ang, ang[:1]]) + np.pi) % (2 * np.pi) - np.pi
    return ref, ang, (1.0 if np.median(dw) > 0 else -1.0)


def _tube(loop_pts, C, prims, r_guess, spacing, knuckles=True, tang=None, turn=None):
    """A digit: rings (the loop's count, its angles carried along chain C) from a finger radius past the knuckle
    to the tip, spacing apart, extra rings either side of each knuckle, a 45 degree ring and a fan at the tip."""
    cum = _chain_point(C, 0)[2]
    s0 = min(1.5 * r_guess, 0.3 * cum[-1])
    p0, d0, _ = _chain_point(C, s0)
    ref, ang, _ = _loop_frame(loop_pts, d0)
    if tang is not None:  # the steps round from the template's own clean digit (a warped loop can fold: its angles ran
        # backwards and turned the tube inside out)
        ang = ang[0] + (np.asarray(tang) - tang[0])
    if turn is not None:
        dw = (np.diff(ang) + np.pi) % (2 * np.pi) - np.pi
        if np.sign(np.median(dw)) != turn:
            ang = ang[0] - (ang - ang[0])
    stations = list(np.arange(s0 + spacing, cum[-1] - 0.3 * spacing, spacing))
    if knuckles:
        stations += [x for kn in cum[1:-1] if kn > s0 + 0.5 * spacing for x in (kn - 0.3 * spacing, kn + 0.3 * spacing)]
    stations = sorted(stations)
    stations = [s for i, s in enumerate(stations) if i == 0 or s - stations[i - 1] > 0.25 * spacing] + [cum[-1]]

    def ring(p, d, ref, lift=0.0):
        e2 = np.cross(d, ref)
        dirs = np.cos(ang)[:, None] * ref + np.sin(ang)[:, None] * e2
        out = np.array([_shoot(prims, p, _unit(u + lift * d), r_guess) for u in dirs])
        if not lift:  # again from the section's own centre: a chain near the skin (a base's finger joints lie by
            # the back of the finger) shot rays out through the near side and turned the tube inside out
            c = out.mean(0)
            c = p + (c - p) - d * ((c - p) @ d)
            if float(sdf.field_at(prims, c[None], margin=0.05)[0]) < 0:
                out = np.array([_shoot(prims, c, _unit(u), r_guess) for u in dirs])
        return out
    rings = [ring(p0, d0, ref)]
    for s in stations:
        p, d, _ = _chain_point(C, s)
        ref = _unit(ref - d * (ref @ d))
        rings.append(ring(p, d, ref))
    d = _unit(C[-1] - C[-2])
    rings.append(ring(C[-1], d, ref, 1.0))
    return rings, _shoot(prims, C[-1], d, r_guess)


def _arc_tube(loop_pts, C, prims, r_guess, s0, min_step=0.4):
    """A flat appendage (a blade ear): equal-arc rings, each a ring's perimeter / count further on (square quads,
    at least min_step x the first spacing), from s0 to the tip."""
    p0, d0, cum = _chain_point(C, s0)
    ref, _, sign = _loop_frame(loop_pts, d0)
    n = len(loop_pts)
    per = lambda R: np.linalg.norm(np.diff(np.r_[R, R[:1]], axis=0), axis=1).sum()
    rings = [_ring_arc(prims, p0, d0, ref, n, sign, r_guess)]
    sp0 = per(rings[0]) / n
    s = s0
    while True:
        s += max(per(rings[-1]) / n, min_step * sp0)
        if s > cum[-1] - 0.3 * sp0:
            break
        p, d, _ = _chain_point(C, s)
        ref = _unit(ref - d * (ref @ d))
        rings.append(_ring_arc(prims, p, d, ref, n, sign, r_guess))
    return rings, _shoot(prims, C[-1], _unit(C[-1] - C[-2]), r_guess)


def _eye_margins(c, rot, prims, reach, the, phi_max=1.3, n_samp=200):
    """Per azimuth round the lids (frame rot at c, looking along local -y), the angle off the axis where the first
    exit of rays from c drops from lid to eyeball (the lid edge), median-smoothed round the eye; zeros if shut."""
    pm = np.zeros(len(the))
    ph = np.linspace(phi_max, 0.0, n_samp)
    for i, t in enumerate(the):
        loc = np.stack([np.sin(ph) * np.cos(t), -np.cos(ph), np.sin(ph) * np.sin(t)], -1)
        _, R = _exit(prims, c, loc @ rot.T, reach)
        jump = np.diff(R)
        m = int(np.argmin(jump))
        pm[i] = 0.5 * (ph[m] + ph[m + 1]) if jump[m] < -0.05 * R[m] else np.nan  # no step: the lids meet here
    ok = np.isfinite(pm)
    if ok.sum() < 3:
        return np.zeros(len(the))
    idx = np.arange(len(the))
    pm = np.interp(idx, idx[ok], pm[ok], period=len(the))
    return np.median(np.stack([np.roll(pm, k) for k in range(-2, 3)]), 0)


def _eye_rings(loop_pts, c, rot, prims, reach, voxel, n_samp=200):
    """An eye from a loop round it (on the lids, within their cone): rings over the lid down to its edge, a ring on
    the eyeball under the edge, the eyeball in to its pole. All by rays from the lids' centre c (frame rot,
    looking along local -y: the opening's walls are radial, so near the eye the surface is star-shaped from c);
    along each spoke (a loop vertex's azimuth) the first exit drops from lid to eyeball at the margin. Margins are
    median-smoothed round the eye (one spoke caught the brow's edge and spiked)."""
    n = len(loop_pts)
    q = (loop_pts - c) @ rot
    phi0 = np.arccos(np.clip(-q[:, 1] / np.linalg.norm(q, axis=1), -1, 1))
    th = np.arctan2(q[:, 2], q[:, 0])

    def world(phi, the):
        return np.stack([np.sin(phi) * np.cos(the), -np.cos(phi) * np.ones_like(the), np.sin(phi) * np.sin(the)],
                        -1) @ rot.T

    def ring(phi):
        return _exit(prims, c, world(phi, th), reach)[0]
    pm = _eye_margins(c, rot, prims, reach, th)
    shut = not pm.any()
    dphi = 0.012  # either side of the margin (margins are found to 1.3 / 200 rad)
    sp = np.linalg.norm(np.diff(np.r_[loop_pts, loop_pts[:1]], axis=0), axis=1).sum() / n
    edge = ring(pm + dphi)
    n_lid = max(1, int(round(np.linalg.norm(edge - loop_pts, axis=1).mean() / sp)))
    rings = [loop_pts.copy()] + [ring(phi0 + (pm + dphi - phi0) * k / n_lid) for k in range(1, n_lid)] + [edge]
    if not shut:
        ball = ring(np.maximum(pm - dphi, 0))
        n_ball = int(round(np.linalg.norm(ball - _exit(prims, c, world(np.zeros(1), np.zeros(1)), reach)[0],
                                          axis=1).mean() / sp))
        rings += [ring(np.maximum(pm - dphi, 0) * (1 - k / (n_ball + 1))) for k in range(n_ball + 1)]
    return rings, _exit(prims, c, world(np.zeros(1), np.zeros(1)), reach)[0][0]


def _ear_chain(s, side):
    """The model's ear: bones named ear* on one side, chained from the midline out. (points, bone names, radius)."""
    bs = {n: b for n, b in s["bones"].items() if n.startswith("ear") and n.endswith("." + side)}
    if not bs:
        return None
    pos = lambda j: np.asarray(resolve_point(s, j), float)
    first = min((b["a"] for b in bs.values()), key=lambda j: abs(pos(j)[0]))
    C, j, left = [pos(first)], first, dict(bs)
    while True:
        nxt = [(n, b) for n, b in left.items() if j in (b["a"], b["b"])]
        if not nxt:
            break
        n, b = nxt[0]
        j = b["b"] if b["a"] == j else b["a"]
        C.append(pos(j))
        del left[n]
    r = max(float(s["joints"][e].get("r", 0.01)) for b in bs.values() for e in (b["a"], b["b"]))
    return np.array(C), set(bs), r


def _plan_cuts(W, tpl, s, prims):
    """Cut loops on the template: {key: {"loop", "inner" (a vertex inside), "kind" (digit/ear/eye), and for ears and
    eyes "target": where the loop goes on the model}}, from the skeleton-warped template W."""
    P, face = tpl["P"], tpl["face"]
    faces, nb, ef = topology(tpl["L"], tpl["S"])
    names = {p.name for p in prims}
    out = {}
    for side, sg in (("L", 1.0), ("R", -1.0)):
        for tn, mn in [(f"finger{k}", f"hand_f{k}") for k in range(1, 5)] + [("thumb", "hand_th")]:
            if f"{tn}_0.{side}" not in tpl["J"]:
                continue
            ch = np.array([tpl["J"][f"{tn}_{j}.{side}"] for j in range(4)])
            ax = _unit(ch[-1] - ch[0])
            near_tip = np.flatnonzero(np.linalg.norm(P - ch[-1], axis=1) < 0.03)
            tip = int(near_tip[np.argmax((P[near_tip] - ch[0]) @ ax)])
            loop = _base_loop(P, faces, nb, ef, ch[0], ax, tip)
            if loop is not None:
                # which way round the rings must run for the tube's quads to face out: _stitch winds them against
                # the kept face along loop[0] -> loop[1] (outward needs the angle to rise when that edge isn't kept)
                drop = _tip_side(loop, nb, tip) - set(loop)
                fwd = any(f[k] == loop[0] and f[(k + 1) % len(f)] == loop[1] for f in faces
                          if not any(v in drop for v in f) for k in range(len(f)))
                out[f"{tn}.{side}"] = {"loop": loop, "inner": tip, "kind": "digit", "model": mn, "side": side,
                                       "tang": _loop_frame(P[loop], ax)[1], "turn": -1.0 if fwd else 1.0}
        if "ear_tip" in face:
            loop, tipv = _ear_loop(P, faces, nb, ef, np.array(face["ear_tip"]) * [sg, 1, 1])
            if loop is not None:
                cut = {"loop": loop, "inner": tipv, "kind": "ear"}
                chain = _ear_chain(s, side)
                if chain is not None:
                    C, bn, r = chain
                    own = [p for p in prims if p.name in bn]
                    s0 = _clear_start(C, own, prims, r, 0.5 * np.linalg.norm(C[-1] - C[0]))
                    p0, d0, _ = _chain_point(C, s0)
                    ref, _, sign = _loop_frame(W[loop], d0)
                    cut.update(chain=(C, own, r, s0), target=_ring_arc(own, p0, d0, ref, len(loop), sign, r))
                out[f"ear.{side}"] = cut
        if "eye_cut" in face and f"face_lids.{side}" in names:
            loop, inner = _eye_loop(P, faces, nb, ef, np.array(face["landmarks"]["eye.L"]) * [sg, 1, 1],
                                    face["eye_cut"])
            if loop is not None and inner is not None:
                lp = next(p for p in prims if p.name == f"face_lids.{side}")
                c, rot, ro = lp.params["c"], lp.params["rot"], lp.params["ro"]
                q = (W[loop] - c) @ rot
                th = np.arctan2(q[:, 2], q[:, 0])
                dw = (np.diff(np.r_[th, th[:1]]) + np.pi) % (2 * np.pi) - np.pi
                the = th[0] + np.sign(np.median(dw)) * np.arange(len(loop)) / len(loop) * 2 * np.pi
                # the loop follows the lid edge's shape, eye_phi (radians off the lids' axis) outside it: at a fixed
                # angle it crossed a wide almond opening at the corners
                pm = _eye_margins(c, rot, prims, 3 * ro, the)
                phi = np.minimum(pm + face.get("eye_phi", 0.4), 1.3)
                loc = np.stack([np.sin(phi) * np.cos(the), -np.cos(phi), np.sin(phi) * np.sin(the)], -1)
                out[f"eye.{side}"] = {"loop": loop, "inner": inner, "kind": "eye", "lids": (c, rot, ro),
                                      "target": _exit(prims, c, loc @ rot.T, 4 * ro)[0]}
    return out


def _patches(W, cuts, s, prims, voxel, log):
    """The model's own patch per cut (loops with a target carried there first, moving W): {key: (loop, inner,
    (rings, tip) or None for a cap)}."""
    for cut in cuts.values():
        if "target" in cut:
            W[:] = _carry(W, cut["loop"], cut["target"])
    out = {}
    for key, cut in cuts.items():
        loop, patch = cut["loop"], None
        if cut["kind"] == "digit":
            mn, side = cut["model"], cut["side"]
            if f"{mn}_0.{side}" in s["joints"]:
                C = np.array([resolve_point(s, f"{mn}_{j}.{side}") for j in range(4)])
                own = [p for p in prims if p.name.startswith(mn + "_") and p.name.endswith("." + side)]
                r = float(s["joints"][f"{mn}_1.{side}"].get("r", 0.01))
                ft = float(sdf.field_at(own or prims, C[-1:], margin=0.05)[0])
                if ft > -0.6 * r:  # a tip joint on the skin (a base's): back inside by a tip radius, or the last
                    # rings shot from the surface and the fingertips came out as bulbs
                    C[-1] = C[-1] - _unit(C[-1] - C[-2]) * (ft + 0.8 * r)
                patch = _tube(W[loop], C, own or prims, r, 2 * np.pi * r / len(loop), tang=cut.get("tang"), turn=cut.get("turn"))
                # the loop carried to just before the first ring: the skeleton warp can leave a digit's base loop
                # on its neighbour (a base's close-set fingers: the index tube twisted across from the middle one)
                d0 = _unit(C[1] - C[0])
                dst = np.asarray(patch[0][0]) - d0 * (0.8 * r)
                if cut.get("carry") and np.linalg.norm(W[loop].mean(0) - dst.mean(0)) > 0.5 * r:
                    W[:] = _carry(W, loop, dst)
        elif cut["kind"] == "ear" and "chain" in cut:
            C, own, r, s0 = cut["chain"]
            patch = _arc_tube(W[loop], C, own, r, s0)
        elif cut["kind"] == "eye":
            c, rot, ro = cut["lids"]
            patch = _eye_rings(W[loop], c, rot, prims, 3 * ro, voxel)  # noqa
        out[key] = (loop, cut["inner"], patch)
        log.append(f"{key}: loop of {len(loop)}, " + ("capped" if patch is None else f"{len(patch[0])} rings"))
    return out


def _stitch(V, faces, cuts):
    """Remove each loop's inside, add its patch's rings (the first replaces the loop) or a cap. Returns (V, faces,
    origin per vertex: 0 template, 1 generated ring (fixed), 2 generated free (cap centres), old -> new index)."""
    nb = {}
    for f in faces:
        for k in range(len(f)):
            nb.setdefault(f[k], set()).update((f[k - 1], f[(k + 1) % len(f)]))
    drop = set()
    for loop, inner, _ in cuts.values():
        drop |= _tip_side(loop, nb, inner) - set(loop)
    kept = [f for f in faces if not any(v in drop for v in f)]
    directed = {(f[k], f[(k + 1) % len(f)]) for f in kept for k in range(len(f))}
    n0 = len(V)
    V = list(np.asarray(V))
    origin = [0] * n0
    new = []
    for loop, _, patch in cuts.values():
        n = len(loop)
        # the kept faces run along the loop: patch faces run against them (a vote over the loop's edges: another
        # cut's dropped tip side can take the face on loop[0] -> loop[1], and the whole tube came out inside out)
        fwd = sum((loop[k], loop[(k + 1) % n]) in directed for k in range(n)) >= \
            sum((loop[(k + 1) % n], loop[k]) in directed for k in range(n))

        def quad(a, b, c, d):
            return [b, a, d, c] if fwd else [a, b, c, d]

        def fan(ring, t):
            for i in range(0, n - 1, 2):
                a, b, c = ring[i], ring[i + 1], ring[(i + 2) % n]
                new.append([c, b, a, t] if fwd else [a, b, c, t])
            if n % 2:
                new.append([ring[0], ring[-1], t] if fwd else [ring[-1], ring[0], t])
        if patch is None:
            V.append(np.mean([V[i] for i in loop], 0))
            origin.append(2)
            fan(loop, len(V) - 1)
            continue
        rings, tip = patch
        for i, v in enumerate(loop):
            V[v] = rings[0][i]
            origin[v] = 1
        prev = list(loop)
        for R in rings[1:]:
            ids = list(range(len(V), len(V) + n))
            V.extend(R)
            origin.extend([1] * n)
            for i in range(n):
                new.append(quad(prev[i], prev[(i + 1) % n], ids[(i + 1) % n], ids[i]))
            prev = ids
        V.append(tip)
        origin.append(1)
        fan(prev, len(V) - 1)
    faces = kept + new
    used = sorted({v for f in faces for v in f})
    remap = np.full(len(V), -1)
    remap[used] = np.arange(len(used))
    return (np.array([V[v] for v in used]), [[int(remap[v]) for v in f] for f in faces],
            np.array([origin[v] for v in used]), remap[:n0])
