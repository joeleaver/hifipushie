"""A tailor's tape on a body mesh: the measurements a made-to-measure draft needs, taken the way a tailor takes them.

`measure(V, faces, J)` -> {"mm": {FreeSewing-named measurements, mm (shoulderSlope in degrees)}, "at": landmarks (m),
"loops": the tape lines (m, for drawing)}. Girths are the convex hull of the body's cross-section (a tape bridges
hollows); lengths run over the surface (sections through the two end points). The body faces -Y, Z up, its left +X
(the model convention); arms hang away from the torso (MakeHuman's A pose) so the torso's sections are its own loops.

Definitions (FreeSewing's measurement names; https://freesewing.dev/reference/measurements):
- neck: round the neck's base, square to the neck, 2 cm above the neck joint (where a shirt collar sits).
- hps (high point of shoulder): the neck loop's outermost point. Shoulder point: the top of the shoulder over
  the shoulder joint. shoulderSlope: the hps -> shoulder point line below horizontal (degrees).
- shoulderToShoulder: shoulder point to shoulder point over the back (the back half of the section at their height).
- armpit: the highest torso section the arm has left. chest: the fullest torso section 2-12 cm under the armpit.
- waist: 70% of the way from the pelvis joint to the chest joint (skeletal: the natural waist). hips: at the hip joints' height + 2 cm (FreeSewing's
  hips are where trousers sit, ~13 cm under the waist). seat: the fullest section from 12 cm under that to it.
- biceps: the fullest upper-arm section square to the arm (25-60% of shoulder -> elbow); wrist: square to the forearm.
- hpsToWaistBack, hpsToBust: over the surface; shoulderToElbow, shoulderToWrist: shoulder point -> elbow -> wrist.
- waistToArmpit/Hips/Seat/Floor/Knee, crotch: vertical distances.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import ConvexHull


def triangles(faces) -> np.ndarray:
    """Quads/polygons as a fan of triangles."""
    T = []
    for f in faces:
        for k in range(1, len(f) - 1):
            T.append((f[0], f[k], f[k + 1]))
    return np.asarray(T, dtype=np.int64)


def slice_loops(V: np.ndarray, T: np.ndarray, o, n) -> list[np.ndarray]:
    """The mesh's cross-section by the plane through o with normal n: ordered polylines (closed loops where the mesh
    is closed; an open mesh can give open chains)."""
    o, n = np.asarray(o, float), np.asarray(n, float) / np.linalg.norm(n)
    d = (V - o) @ n
    s = np.sign(d[T])
    s[s == 0] = 1
    cross = ~((s[:, 0] == s[:, 1]) & (s[:, 1] == s[:, 2]))
    Tc = T[cross]
    if not len(Tc):
        return []
    pts: dict = {}
    nbr: dict = {}
    for tri in Tc:
        ks = []
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            if (d[a] >= 0) != (d[b] >= 0):
                k = (min(a, b), max(a, b))
                if k not in pts:
                    t = d[a] / (d[a] - d[b])
                    pts[k] = V[a] + t * (V[b] - V[a])
                ks.append(k)
        if len(ks) == 2:
            nbr.setdefault(ks[0], []).append(ks[1])
            nbr.setdefault(ks[1], []).append(ks[0])
    seen = set()
    loops = []
    for start in nbr:
        if start in seen:
            continue
        # walk to one end (open chains) then along
        chain_end, prev = start, None
        while True:
            nx = [k for k in nbr[chain_end] if k != prev]
            if len(nbr[chain_end]) < 2 or not nx or nx[0] == start:
                break
            prev, chain_end = chain_end, nx[0]
            if chain_end == start:
                break
        cur, prev, seq = chain_end, None, []
        while cur is not None and cur not in seen:
            seen.add(cur)
            seq.append(pts[cur])
            nx = [k for k in nbr[cur] if k != prev and k not in seen]
            prev, cur = cur, (nx[0] if nx else None)
        if len(seq) >= 3:
            loops.append(np.array(seq))
    return loops


def _frame(n):
    n = np.asarray(n, float) / np.linalg.norm(n)
    a = np.array([0, 0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0, 0])
    u = np.cross(n, a)
    u /= np.linalg.norm(u)
    return u, np.cross(n, u)


def girth(loop: np.ndarray, n) -> float:
    """Tape length round a section: its convex hull's perimeter in the plane."""
    u, v = _frame(n)
    P2 = np.c_[loop @ u, loop @ v]
    if len(P2) < 3:
        return 0.0
    return float(ConvexHull(P2).area)  # 2D: "area" is the perimeter


def _encloses(L: np.ndarray, q, n) -> bool:
    u, v = _frame(n)
    P2 = np.c_[L @ u, L @ v]
    q = np.array([np.asarray(q) @ u, np.asarray(q) @ v])
    ang = np.arctan2(P2[:, 1] - q[1], P2[:, 0] - q[0])
    return abs(np.sum(np.angle(np.exp(1j * np.diff(np.r_[ang, ang[:1]]))))) / (2 * np.pi) > 0.5


def section(V, T, o, n, near) -> np.ndarray | None:
    """The section loop through the plane (o, n) that passes nearest the point `near` (or encloses it)."""
    loops = slice_loops(V, T, o, n)
    if not loops:
        return None
    near = np.asarray(near, float)
    # enclosing loops first, then the nearest
    return min(loops, key=lambda L: (0 if _encloses(L, near, n) else 1, np.min(np.linalg.norm(L - near, axis=1))))


def arc(loop: np.ndarray, a, b, side) -> np.ndarray:
    """The part of a closed loop between its points nearest a and b, on the side where side(points) is larger."""
    ia = int(np.argmin(np.linalg.norm(loop - a, axis=1)))
    ib = int(np.argmin(np.linalg.norm(loop - b, axis=1)))
    n = len(loop)
    if ia == ib:
        return loop[[ia]]
    i1 = [(ia + k) % n for k in range((ib - ia) % n + 1)]
    i2 = [(ib + k) % n for k in range((ia - ib) % n + 1)][::-1]
    c1, c2 = loop[i1], loop[i2]
    return c1 if side(c1[len(c1) // 2:len(c1) // 2 + 1])[0] >= side(c2[len(c2) // 2:len(c2) // 2 + 1])[0] else c2


def length(P: np.ndarray) -> float:
    return float(np.sum(np.linalg.norm(np.diff(P, axis=0), axis=1))) if len(P) > 1 else 0.0


def measure(V: np.ndarray, faces, J: dict) -> dict:
    V = np.asarray(V, float)
    T = triangles(faces) if not isinstance(faces, np.ndarray) or faces.shape[1] != 3 else faces
    Z = np.array([0, 0, 1.0])
    at, loops, mm = {}, {}, {}
    pelvis, chest_j, neck_j, head_j = (np.asarray(J[k], float) for k in ("pelvis", "chest", "neck", "head"))
    sh, el, wr = (np.asarray(J[k], float) for k in ("shoulder.L", "elbow.L", "wrist.L"))
    hip = np.asarray(J["hip.L"], float)
    axis_at = lambda z: np.array([0.0, float(np.interp(z, [pelvis[2], chest_j[2], neck_j[2]],
                                                       [pelvis[1], chest_j[1], neck_j[1]])), z])

    def torso(z):
        return section(V, T, axis_at(z), Z, axis_at(z))

    # neck: square to the neck, 2 cm up it
    nd = head_j - neck_j
    nd /= np.linalg.norm(nd)
    no = neck_j + 0.02 * nd
    L = section(V, T, no, nd, no)
    mm["neck"] = girth(L, nd)
    loops["neck"] = L
    at["hps.L"] = L[np.argmax(L[:, 0])]
    at["cf_neck"] = L[np.argmin(L[:, 1])]
    at["cb_neck"] = L[np.argmax(L[:, 1])]
    # shoulder point: top of the shoulder 1.5 cm out from the joint (a section across the body there)
    # The shoulder point is where the shoulder line turns down into the arm (the acromion's edge), not the top over
    # the joint: the joint sits 2-3 cm inside it. (Taken at the joint's x, sleeves were drafted 3 cm long and placed
    # 3 cm up the shoulder, the armhole seam rode on top of the shoulder and 3-4 cm of every shoulder seam bunched up
    # at the neck: a knot at the neck point and a ridge of yoke behind the collar.) Scanning out from 4 cm inside the
    # joint, it is the last top-of-shoulder point before the top's slope exceeds the shoulder line's own by 10 deg.
    def top_at(x):
        S_ = section(V, T, [x, sh[1], sh[2]], [1.0, 0, 0], [x, sh[1], sh[2] + 0.06])
        if S_ is None:
            return None
        return S_[np.argmax(S_[:, 2] - 4 * np.abs(S_[:, 1] - sh[1]))]
    step = 0.005
    tops = [(x, top_at(x)) for x in np.arange(sh[0] - 0.04, sh[0] + 0.08 + 1e-9, step)]
    tops = [(x, t_) for x, t_ in tops if t_ is not None]
    top = top_at(sh[0])
    if len(tops) >= 6:
        zt = np.array([t_[2] for _, t_ in tops])
        xt = np.array([x for x, _ in tops])
        slope = np.degrees(np.arctan2(-np.diff(zt), np.diff(xt)))  # slope[i]: from tops[i] to tops[i + 1]
        line = float(np.median(slope[xt[1:] <= sh[0] + 1e-9])) if (xt[1:] <= sh[0] + 1e-9).any() else float(slope[0])
        over = np.where((slope > line + 10.0) & (xt[:-1] >= sh[0] - 1e-9))[0]  # (never inside the joint)
        if len(over):
            top = tops[int(over[0])][1]
    at["shoulder.L"] = top
    hps = at["hps.L"]
    mm["shoulderSlope"] = float(np.degrees(np.arctan2(hps[2] - top[2], top[0] - hps[0])))
    # shoulder to shoulder: a taut tape across the back between the shoulder points. It lies in a plane through both
    # that dips toward the back (over the shoulder blades), the shortest of the tilts tried; the level section at the
    # shoulders' height runs far back round the base of the neck (21% longer than the chord here)
    best, back = None, None
    for tilt in (0.0, 15.0, 30.0, 45.0, 60.0):
        n_ = np.array([0.0, -np.sin(np.radians(tilt)), np.cos(np.radians(tilt))])
        Bs = section(V, T, top, n_, axis_at(top[2]) + [0, 0.05, 0])
        if Bs is None:
            continue
        try:
            a_ = arc(Bs, top, top * [-1, 1, 1], lambda P: P[:, 1])
        except Exception:
            continue
        if len(a_) >= 3 and (best is None or length(a_) < best):
            best, back = length(a_), a_
    if back is None:
        B = section(V, T, top, Z, axis_at(top[2]) + [0, 0.05, 0])
        back = arc(B, top, top * [-1, 1, 1], lambda P: P[:, 1])
    mm["shoulderToShoulder"] = length(back)
    loops["shoulders"] = back
    # armpit: scan down from the shoulder joint for the first section that leaves the arm out
    zs = np.arange(sh[2], sh[2] - 0.25, -0.004)
    arm_z = None
    for z in zs:
        t = (z - sh[2]) / (el[2] - sh[2])
        if t <= 0.05:
            continue
        p = sh + t * (el - sh)  # the arm's axis at this height
        L = torso(z)
        if L is not None and not _encloses(L, p, Z):  # the torso's section no longer takes in the arm
            arm_z = z
            break
    if arm_z is None:
        raise ValueError("tailor: no torso section clear of the arm under the shoulder (arms against the body?)")
    at["armpit_z"] = float(arm_z)
    # chest: the fullest torso section 2-12 cm under the armpit
    best = max(((girth(L, Z), z, L) for z in np.arange(arm_z - 0.02, arm_z - 0.12, -0.005)
                if (L := torso(z)) is not None), key=lambda t: t[0])
    mm["chest"], at["chest_z"], loops["chest"] = best
    # waist: the narrowest 10-20 cm above the pelvis joint
    # skeletal, so a belly doesn't move it (the narrowest section rose 4 cm on a heavy body: a shorter shirt)
    zw = pelvis[2] + 0.7 * (chest_j[2] - pelvis[2])
    L = torso(zw)
    at["waist_z"], loops["waist"], mm["waist"] = float(zw), L, girth(L, Z)
    zh = hip[2] + 0.02
    L = torso(zh)
    mm["hips"], at["hips_z"], loops["hips"] = girth(L, Z), float(zh), L
    best = max(((girth(L, Z), z, L) for z in np.arange(zh - 0.12, zh + 0.001, 0.005)
                if (L := torso(z)) is not None and L[:, 0].min() < -0.02 < 0.02 < L[:, 0].max()),
               key=lambda t: t[0])
    mm["seat"], at["seat_z"], loops["seat"] = best
    # arms
    ad = el - sh
    ad /= np.linalg.norm(ad)
    # (a section that runs into the torso, a heavy arm against its side, isn't the arm's: left out)
    arm_r = 0.4 * np.linalg.norm(el - sh)
    cands = [(girth(L, ad), t, L) for t in np.linspace(0.25, 0.75, 21)
             if (L := section(V, T, sh + t * (el - sh), ad, sh + t * (el - sh))) is not None
             and np.max(np.linalg.norm(L - (sh + t * (el - sh)), axis=1)) < arm_r]
    if not cands:
        raise ValueError("tailor: every upper-arm section runs into the torso (arms against the body?): no biceps")
    best = max(cands, key=lambda q: q[0])
    mm["biceps"], loops["biceps"] = best[0], best[2]
    fd = wr - el
    fd /= np.linalg.norm(fd)
    wo = wr - 0.01 * fd
    L = section(V, T, wo, fd, wo)
    mm["wrist"], loops["wrist"] = girth(L, fd), L
    mm["shoulderToElbow"] = float(np.linalg.norm(el - top))
    mm["shoulderToWrist"] = float(np.linalg.norm(el - top) + np.linalg.norm(wr - el))
    at["elbow.L"], at["wrist.L"] = el, wr
    # surface lengths: hps down the back to the waist (a section along x = hps.x), hps to the bust point
    W = at["waist_z"]

    def down(z1, x0, x1, sign):
        """A tape down the back (sign +1) or front (-1) from hps to height z1, drifting from x0 to x1."""
        pts = [hps]
        for z in np.arange(hps[2] - 0.01, z1 - 1e-6, -0.01):
            L = torso(z)
            if L is None:
                continue
            xt = x0 + (x1 - x0) * (hps[2] - z) / max(hps[2] - z1, 1e-6)
            near = L[np.abs(L[:, 0] - xt) < 0.015]
            if len(near):
                pts.append(near[np.argmax(sign * near[:, 1])])
        return np.array(pts)
    tape = down(W, hps[0], hps[0], 1)
    mm["hpsToWaistBack"] = length(tape)
    loops["hpsToWaistBack"] = tape
    C = loops["chest"]
    bust = C[np.argmin(np.abs(C[:, 0] - 0.095) + 0.5 * C[:, 1])]  # front of the chest, 9.5 cm out
    at["bust.L"] = bust
    tape = np.r_[down(bust[2], hps[0], bust[0], -1), bust[None]]
    mm["hpsToBust"] = length(tape)
    loops["hpsToBust"] = tape
    mm["highBust"] = mm["chest"]
    # front and back lengths from hps down to the seat over the surface, a hand's width from centre: a belly makes
    # the front longer than the back (patterns draft them equal: the large-abdomen alteration adds the difference)
    zs_ = at["seat_z"]
    tf = down(zs_, hps[0], 0.06, -1)
    tb = down(zs_, hps[0], 0.06, 1)
    mm["hpsToSeatFront"], mm["hpsToSeatBack"] = length(tf), length(tb)
    loops["hpsToSeatFront"], loops["hpsToSeatBack"] = tf, tb
    zmin = float(V[:, 2].min())
    mm["waistToArmpit"] = arm_z - W
    mm["waistToHips"] = W - zh
    mm["waistToSeat"] = W - at["seat_z"]
    mm["waistToFloor"] = W - zmin
    if "knee.L" in J:
        mm["waistToKnee"] = W - float(J["knee.L"][2])
    # the crotch: the highest level where the body's section no longer holds the centre line (two legs): the body
    # rise a trouser draft needs (FreeSewing: waistToUpperLeg; inseam = crotch to floor)
    try:
        cy = float(np.mean(loops["seat"][:, 1]))
        zc = None
        for z in np.arange(at["seat_z"], at["seat_z"] - 0.30, -0.004):
            Ls = slice_loops(V, T, [0, 0, z], Z)
            if Ls and not any(_encloses(L_, np.array([0.0, cy, z]), Z) for L_ in Ls):
                zc = float(z) + 0.002
                break
        if zc is not None:
            at["crotch_z"] = zc
            mm["waistToUpperLeg"] = W - zc
            mm["inseam"] = zc - zmin
    except Exception:  # a body the scan can't read keeps the estimate (pattern_blocks.trouser)
        pass
    mm["height"] = float(V[:, 2].max() - zmin)
    out = {k: (round(v * 1000.0, 1) if k != "shoulderSlope" else round(v, 2)) for k, v in mm.items()}
    return {"mm": out, "at": {k: (np.asarray(v).tolist() if not np.isscalar(v) else float(v)) for k, v in at.items()},
            "loops": loops}
