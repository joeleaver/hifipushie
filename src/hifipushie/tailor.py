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
- waist: 70% of the way from the pelvis joint to the chest joint (skeletal: near the natural waist; FreeSewing's is the
  narrowest section: Garrett's 15 mm, Tess's 50 mm above ours). hips: at the hip joints' height + 2 cm (OUR level: the
  greater trochanter's; NOT FreeSewing's hips, which is the top of the hip bone: measure_defs adapts). seat: the fullest
  section from 12 cm under that to it.
- highHip / waistToHighHip: the girth at the iliac crest (ANSUR II iliocristale height) and the waist's height over it;
  the crest is ILIAC_CREST_OVER_CROTCH x stature above the crotch (FreeSewing's hips / waistToHips, via measure_defs).
- highBust: the narrowest torso section in the 4 cm under the armpit (FreeSewing: just under the arms,
  above the bust; it was = chest).
- biceps: the fullest upper-arm section square to the arm (25-60% of shoulder -> elbow); wrist: square to the forearm.
- hpsToWaistBack, hpsToBust: over the surface; shoulderToElbow, shoulderToWrist: shoulder point -> elbow -> wrist.
- waistToArmpit/Hips/Seat/Floor/Knee, crotch: vertical distances.
"""
from __future__ import annotations

import os

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


def _leg_girths(V: np.ndarray, T: np.ndarray, J: dict, at: dict, zmin: float) -> dict:
    """The left leg's girths (m), FreeSewing's names: upperLeg (5 cm under the crotch), knee (at the joint), calf (the
    fullest level between knee and ankle), ankle (the slimmest above the ankle joint), heel (round heel and instep:
    what a trouser hem must pass; a plane through the ankle tilted 45 deg)."""
    Z = np.array([0, 0, 1.0])
    kn, an = np.asarray(J["knee.L"], float), np.asarray(J["ankle.L"], float)

    def leg(z):
        Ls = [L for L in slice_loops(V, T, [0, 0, z], Z) if L[:, 0].mean() > 0.02 and
              np.hypot(L[:, 0].mean() - kn[0], L[:, 1].mean() - kn[1]) < 0.2]
        return max((girth(L, Z) for L in Ls), default=0.0)
    out = {}
    if "crotch_z" in at:
        out["upperLeg"] = leg(float(at["crotch_z"]) - 0.05)
    out["knee"] = leg(float(kn[2]))
    zs = np.arange(an[2] + 0.02, kn[2] - 0.04, 0.01)
    gs = np.array([leg(float(z)) for z in zs])
    if len(gs):
        k = int(np.argmax(gs))
        out["calf"] = float(gs[k])
        lo = gs[:k + 1][gs[:k + 1] > 0]
        if len(lo):
            out["ankle"] = float(lo.min())
    n = np.array([0.0, 1.0, 1.0]) / np.sqrt(2.0)  # heel (back, low) -> instep (front, up) lies in this plane
    Ls = [L for L in slice_loops(V, T, an, n) if L[:, 0].mean() > 0.02 and np.linalg.norm(L.mean(0) - an) < 0.12]
    if Ls:
        out["heel"] = max(girth(L, n) for L in Ls)
    return {k: v for k, v in out.items() if v > 0}


def _side_neck(V, T, L) -> tuple:
    """The side neck point (hps) on the neck loop `L`: where the shoulder's crest (the trapezius ridge) meets the
    neck, not the loop's widest point. On a deep neck section (GNM: 14 cm front to back, the throat under the jaw
    in it) the widest point sits on the sternocleidomastoid 2-4 cm in front of the ridge, and every back tape from
    it first crossed the neck's top: gp_h6c read hps -> armpit down the back 258 mm for a 187 mm drop (su_gc 228 /
    180), so the jacket's underarm was drafted 3 cm low. The ridge's y is read in a section along y 1 cm outside the
    widest point (the top of the shoulder there, below the loop's height); the hps is the loop's outer crossing of
    that y. Falls back to the widest point when the section misses. Returns (hps, the crest's height or None)."""
    L = np.asarray(L, float)
    w = L[np.argmax(L[:, 0])]
    x = float(w[0]) + 0.01
    try:
        S = section(V, T, [x, w[1], w[2]], [1.0, 0, 0], [x, w[1], w[2] - 0.03])
    except Exception:
        S = None
    if S is None:
        return w, None
    S = S[(S[:, 2] < w[2]) & (np.abs(S[:, 1] - w[1]) < 0.12)]
    if not len(S):
        return w, None
    yc, zc = float(S[np.argmax(S[:, 2]), 1]), float(S[:, 2].max())
    yc = float(np.clip(yc, L[:, 1].min() + 1e-4, L[:, 1].max() - 1e-4))
    # the loop's crossings of y = yc on the left side (x > 0), the outermost one
    best = None
    for i in range(len(L)):
        a, b = L[i], L[(i + 1) % len(L)]
        if (a[1] - yc) * (b[1] - yc) > 0 or a[1] == b[1]:
            continue
        p = a + (b - a) * (yc - a[1]) / (b[1] - a[1])
        if p[0] > 0 and (best is None or p[0] > best[0]):
            best = p
    return (w, None) if best is None else (best, zc)


# shoulderSlope's definition (fit round 13, opt-in): "line" (default since 2026-10-06: a fit through the top of the
# shoulder in the joint's plane, from 2 cm outside hps to the shoulder point) | "chord" (FreeSewing's measurement: hps ->
# the shoulder point, the drop every draft that places the neck point at hps needs). On Garrett the line reads 10.9 deg,
# the chord 22.5, the front-view top of the shoulder ~17 (x 100 -> 220 mm off CF): the drafts (Simon's shirt, the jacket
# block) put the shoulder point 28-32 mm below hps where the body's is 65, and both garments stood 15-45 mm off the
# shoulder line (fit round 13 shoulderprof.py)
SHOULDER_SLOPE = "line"
# the iliac crest's height over the crotch, x stature: ANSUR II medians (crotch height 0.4813 / 0.4802, iliocristale
# height 0.6038 / 0.6110 of stature: men 18-40 0.1225, women 18-30 0.1308; measure audit ansur_levels.py). One number for
# both (the tape doesn't know the body's sex): +-0.004 x stature = +-7 mm
ILIAC_CREST_OVER_CROTCH = 0.125
NECK_BASE_TILT = 32.0  # deg: the base-of-neck tape falls this much toward the front (ANSUR II: cervicale ~79 mm (men) /
# 66 (women) above suprasternale over a ~110-120 mm deep neck base)
NECK_BASE_GIRTH = 1.06  # the base ring is the lowest tilted section within this much of the narrowest one
# (ANSUR II neck base / neck circumference p5 1.05 men, 1.08 women: past it the section runs out onto the shoulders)


def _neck_base(V, T, neck_j, nd, neck_girth, tilt=NECK_BASE_TILT, ratio=NECK_BASE_GIRTH):
    """The base-of-neck line (ANSUR II 5.2.29: a tape laid round the base of the neck, over the anterior neck point,
    lower in front) as the lowest section of a plane tilted `tilt` deg from square to the neck (front down) that is
    still the neck's own loop: one closed loop round the neck's axis with girth <= ratio x the narrowest such loop.
    Returns (ring, plane normal) or (None, None)."""
    nd = np.asarray(nd, float)
    side = np.cross(nd, [0.0, -1.0, 0.0])  # the body's left (+x for an upright neck)
    side /= np.linalg.norm(side)
    a = np.radians(tilt)
    # rotate nd about the side axis so the plane's front edge drops (normal tips forward: -y)
    n = nd * np.cos(a) + np.cross(side, nd) * np.sin(a)
    if n[1] > 0:
        n = nd * np.cos(a) - np.cross(side, nd) * np.sin(a)
    rows = []
    for h in np.arange(0.04, -0.12, -0.004):
        o_ = np.asarray(neck_j, float) + nd * h
        try:
            L_ = section(V, T, o_, n, o_)
        except Exception:
            L_ = None
        rows.append((L_, girth(L_, n)) if L_ is not None and _encloses(L_, o_, n) else (None, np.inf))
    g_ = np.array([g for _, g in rows])
    if not np.isfinite(g_).any():
        return None, None
    # from the neck's narrowest tilted section down, while the girth stays within `ratio` of it (a tilted plane's
    # section is longer than the square one 2 cm up: it is compared with its own narrowest, not with neck_girth)
    i = int(np.argmin(g_))
    best = rows[i][0]
    while i + 1 < len(rows) and g_[i + 1] <= ratio * g_[int(np.argmin(g_))]:
        i += 1
        best = rows[i][0]
    return (best, n) if best is not None else (None, None)


NECK_BASE_DROP = None  # opt-in (e.g. 0.0445) x stature: solve the tilt for this drop. WIP, dress-garrett r: the base ring's centre back above its centre front (ANSUR II cervicale -
# suprasternale p50 79 mm men of 1770 (0.0446), ~66 women (0.041); men p5-p95 61-98). At a fixed 32 deg tilt the ring
# fell 99 mm on dg_garrett and 122 on dg_mh (its centre back 110 mm over the shoulder point, p95 100): the GNM neck
# runs into the trapezius at the back, so the ring is deeper than the standard's 110-120 mm


def _neck_base_level(V, T, neck_j, nd, neck_girth, stature, drop=None):
    """_neck_base with its tilt solved so the ring's centre back stands `drop` x stature above its centre front: the
    drop read at a few tilts (from square to the neck, which leans forward ~10 deg) and interpolated. (ring, normal)."""
    drop = NECK_BASE_DROP if drop is None else drop
    if not drop:
        return _neck_base(V, T, neck_j, nd, neck_girth)
    want, rows = drop * stature, []
    for t in (12.0, 20.0, 28.0, 36.0):
        R_, n_ = _neck_base(V, T, neck_j, nd, neck_girth, tilt=t)
        if R_ is not None:
            rows.append((t, float(R_[np.argmax(R_[:, 1]), 2] - R_[np.argmin(R_[:, 1]), 2]), R_, n_))
    if not rows:
        return None, None
    ts, ds = np.array([r[0] for r in rows]), np.array([r[1] for r in rows])
    if len(rows) < 2 or np.any(np.diff(ds) <= 0):
        k = int(np.argmin(np.abs(ds - want)))
        return rows[k][2], rows[k][3]
    t = float(np.interp(want, ds, ts))
    R_, n_ = _neck_base(V, T, neck_j, nd, neck_girth, tilt=t)
    return (R_, n_) if R_ is not None else (rows[int(np.argmin(np.abs(ds - want)))][2], rows[int(np.argmin(np.abs(ds - want)))][3])


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
    # neckHeight: how long the neck is up its axis, the run of sections within 8% of its narrowest girth (above it
    # the plane cuts the jaw, below it the trapezius; cloth.Body.neck_rows reads it the same way). A shirt's stand
    # can be no taller than this less a finger's room under the jaw (garment_kb kinds.shirt.collar)
    gs = []
    for h in np.arange(-0.04, 0.125, 0.005):
        o_ = neck_j + nd * h
        L_ = section(V, T, o_, nd, o_)
        if L_ is not None and _encloses(L_, o_, nd):
            gs.append((float(h), float(girth(L_, nd))))
    if gs:
        hs_, g_ = np.array([a for a, _ in gs]), np.array([b for _, b in gs])
        i0, lo_, hi_ = int(np.argmin(g_)), int(np.argmin(g_)), int(np.argmin(g_))
        while lo_ > 0 and g_[lo_ - 1] <= 1.08 * g_[i0]:
            lo_ -= 1
        while hi_ < len(g_) - 1 and g_[hi_ + 1] <= 1.08 * g_[i0]:
            hi_ += 1
        top_ = float(hs_[hi_] + 0.005)
        # where a face's landmarks say where the jaw is, the neck ends under it (on a grafted head the sections up
        # the neck's axis held one girth to 12 cm and never met the jaw)
        jaw = [np.asarray(J[k], float) for k in J if k == "lm_chin" or k.startswith("lm_jaw_")]
        if jaw:
            top_ = min(top_, min(float((p - neck_j) @ nd) for p in jaw))
        mm["neckHeight"] = max(top_ - float(hs_[lo_]), 0.0)
    # hps = the side neck point by the measurement standards' definition (ANSUR II 5.2.43 trapezius point, ISO 8559-1
    # side neck point): where the trapezius' front border crosses the BASE-of-neck line, the lateral point of the
    # base-of-neck tape (5.2.29). With no muscles to palpate it is the base ring's outermost point. The two earlier
    # definitions sat on the loop 2 cm UP the neck: its widest point (on the sternocleidomastoid, in front) and the
    # shoulder crest's crossing of it (`_side_neck`, 40 mm further back and 16 mm in on dg_garrett: shoulder length
    # hps -> shoulder point 187 mm, ANSUR II men of his stature p95 166; every hps tape moved ~35 mm, back shorter,
    # front longer, and the jacket's fronts swung open).
    # DEFAULT "widest" (coordinator, 2026-10-15 s: back to the last known good). j8 (the one jacket that hung right) was
    # drafted on the widest point of the loop up the neck; every session after the switch to "base" chased a knock-on
    # fault (length, balance, armhole, neckline, start strain past ZOZO's limiter). HP_HPS=base (the ANSUR definition,
    # with the ring neckline "ring", the tilt solve NECK_BASE_DROP) and HP_HPS=crest are OPT-IN RESEARCH, parked with
    # open questions in docs/notes/cloth.md "## HPS research (parked)".
    hmode = os.environ.get("HP_HPS", "widest")
    zc_ = None
    base_, bn_ = _neck_base_level(V, T, neck_j, nd, mm["neck"], float(np.ptp(V[:, 2]))) if hmode == "base" else (None, None)
    if base_ is not None:
        loops["neck_base"] = base_
        mm["neckBase"] = girth(base_, bn_)
        at["hps.L"] = base_[np.argmax(base_[:, 0])]
        # the ring's centre back (the cervicale's level) and centre front (the suprasternal notch): a neckline sewn on
        # the base of the neck runs through these and the hps (dress-garrett r: drafted from the loop 2 cm up the
        # neck, the front was cut 13 mm deep and the back 15 mm low, the start over ZOZO's strain limit at the neck)
        at["cb_neck_base"] = base_[np.argmax(base_[:, 1])]
        at["cf_neck_base"] = base_[np.argmin(base_[:, 1])]
    elif hmode == "widest":
        at["hps.L"] = L[np.argmax(L[:, 0])]
    else:
        at["hps.L"], zc_ = _side_neck(V, T, L)
    if zc_ is not None:
        at["neck_base_z"] = zc_  # the shoulder's crest beside the neck: tapes from the hps start below it
    at["neck_side.L"] = L[np.argmax(L[:, 0])]  # the loop's widest point (the neck's half width; was the hps)
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
    # the slope of the shoulder LINE itself (the top of the shoulder from just outside the neck to the shoulder
    # point), not of the chord from hps: hps is taken on the neck's side 2 cm up the neck, above the shoulder line's
    # own start, and its chord read 28 deg on a body whose shoulder lies at 17 (FreeSewing's standard: 13). A draft
    # with shoulders 10 deg too steep has cloth to spare at the neck and none at the shoulder's end
    ins = [(x, t_) for x in np.arange(hps[0] + 0.02, top[0] - 0.004, 0.005) if (t_ := top_at(x)) is not None]
    if len(ins) >= 3:
        xs_ = np.array([t_[0] for _, t_ in ins] + [top[0]])
        zs_ = np.array([t_[2] for _, t_ in ins] + [top[2]])
        at["shoulder_slope_chord"] = mm["shoulderSlope"]
        at["shoulder_slope_line"] = float(np.degrees(np.arctan(-np.polyfit(xs_, zs_, 1)[0])))
        if SHOULDER_SLOPE == "line":
            mm["shoulderSlope"] = at["shoulder_slope_line"]
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
    # depths (front to back, the y extent of the section), as ANSUR II's chestdepth / waistdepth: their difference is
    # the abdomen's own measure (cloth.ALTERATIONS large_abdomen), free of the hps (the front - back tapes from it moved
    # with the hps landmark: dg_mh +76 crest, -50 base, 2026-10-15)
    mm["chestDepth"] = float(np.ptp(np.asarray(loops["chest"])[:, 1]))
    if L is not None:
        mm["waistDepth"] = float(np.ptp(np.asarray(L)[:, 1]))
    zh = hip[2] + 0.02
    L = torso(zh)
    mm["hips"], at["hips_z"], loops["hips"] = girth(L, Z), float(zh), L
    best = max(((girth(L, Z), z, L) for z in np.arange(zh - 0.12, zh + 0.001, 0.005)
                if (L := torso(z)) is not None and L[:, 0].min() < -0.02 < 0.02 < L[:, 0].max()),
               key=lambda t: t[0])
    mm["seat"], at["seat_z"], loops["seat"] = best
    # plumbGirth: what a garment hanging STRAIGHT from the chest must clear, the tape round the hull of the union of
    # the torso sections seat .. chest (a tube can't follow the waist's hollow; the seat or the chest's depth governs).
    # pattern_jacket's plumb silhouette sizes its girth below the chest from it (fit round 26, C94: the chest's full
    # ease carried to the hem left Garrett's jacket +116 over this, ~+55 surplus after the shirt and a cloth layer)
    U_ = [L_ for z in np.linspace(at["seat_z"], at["chest_z"], 18) if (L_ := torso(z)) is not None]
    if U_:
        mm["plumbGirth"] = girth(np.concatenate(U_), Z)
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

    def down(z1, x0, x1, sign, start=None):
        """A tape down the back (sign +1) or front (-1) from hps (or `start`) to height z1, drifting from x0 to x1."""
        top_ = hps if start is None else np.asarray(start, float)
        pts = [top_]
        # (from the crest beside the neck down: above it a slice at the hps's x is the neck itself, and on a deep
        # neck (GNM's, the throat in it) the tape ran round the neck's front or back before it went down)
        z0 = min(hps[2] - 0.01, at.get("neck_base_z", hps[2]) - 0.005) if start is None else top_[2] - 0.01
        for z in np.arange(z0, z1 - 1e-6, -0.01):
            L = torso(z)
            if L is None:
                continue
            xt = x0 + (x1 - x0) * (top_[2] - z) / max(top_[2] - z1, 1e-6)
            near = L[np.abs(L[:, 0] - xt) < 0.015]
            if len(near):
                pts.append(near[np.argmax(sign * near[:, 1])])
        P = np.array(pts)
        # a tape is TAUT: it bridges the hollows (the lumbar curve, under the shoulder blades, between pecs and
        # belly) and doesn't follow each slice's own bumps. Hugging the surface, hps to the waist down the back read
        # 545 mm on a body whose taut tape is ~485: FreeSewing's armhole depth (that length - waist to armpit) came
        # out 6 cm too deep, on shirts and jackets alike (a bomber's armhole: the body of the garment lifts with the
        # arms and rolls across the upper back)
        if len(P) >= 3:
            q = np.c_[-P[:, 2], sign * P[:, 1]]  # along the tape (down), outward
            keep = [0]
            for i in range(1, len(q)):
                while len(keep) >= 2:
                    a_, b_ = q[keep[-2]], q[keep[-1]]
                    if (b_[0] - a_[0]) * (q[i][1] - a_[1]) - (b_[1] - a_[1]) * (q[i][0] - a_[0]) >= 0:
                        keep.pop()  # the middle point lies under the line: the tape lifts off it
                    else:
                        break
                keep.append(i)
            P = P[keep]
        return P
    tape = down(W, hps[0], hps[0], 1)
    mm["hpsToWaistBack"] = length(tape)
    loops["hpsToWaistBack"] = tape
    # nape (the neck loop's centre back) to the waist down the centre back: a garment's LENGTH is drafted from it,
    # the way tailors take "nape to waist", so where the hps is defined never moves the hem (the side-neck hps cut
    # the hps tape 38 mm on gp_h6c and the jacket was drafted 32 mm short: it rode up and its fronts swung round the
    # sides, dress-garrett j12, 2026-10-15)
    cbn = np.asarray(at["cb_neck"], float)
    tape = down(W, float(cbn[0]), float(cbn[0]), 1, start=cbn)
    mm["napeToWaistBack"] = length(tape)
    loops["napeToWaistBack"] = tape
    if "cb_neck_base" in at:
        # the same tapes from the base ring's centre back and centre front, and the hps's own front tape: the draft
        # reads the back neck's rise (hpsToWaistBack - napeBaseToWaistBack) and the front neck's depth
        # (hpsToWaistFront - cfBaseToWaistFront) from them, as a pattern maker measures them on the body
        cbb, cfb = (np.asarray(at[k], float) for k in ("cb_neck_base", "cf_neck_base"))
        tape = down(W, float(cbb[0]), float(cbb[0]), 1, start=cbb)
        mm["napeBaseToWaistBack"], loops["napeBaseToWaistBack"] = length(tape), tape
        tape = down(W, float(cfb[0]), float(cfb[0]), -1, start=cfb)
        mm["cfBaseToWaistFront"], loops["cfBaseToWaistFront"] = length(tape), tape
        tape = down(W, hps[0], hps[0], -1)
        mm["hpsToWaistFront"], loops["hpsToWaistFront"] = length(tape), tape
        # the ring's centre front below the hps (the throat is near vertical there: its drop is the front neck's depth;
        # the hps-minus-cf tapes differ by the chest's prominence too, 85 mm on Garrett against a 48.5 mm drop)
        mm["neckBaseFrontDrop"] = float(hps[2]) - float(cfb[2])
    C = loops["chest"]
    bust = C[np.argmin(np.abs(C[:, 0] - 0.095) + 0.5 * C[:, 1])]  # front of the chest, 9.5 cm out
    at["bust.L"] = bust
    tape = np.r_[down(bust[2], hps[0], bust[0], -1), bust[None]]
    mm["hpsToBust"] = length(tape)
    loops["hpsToBust"] = tape
    # highBust (FreeSewing: round the chest just under the arms, above the bust), just under the armpit. It was = chest, so a bodice's bust dart (chest - highBust) was never drafted (measure audit, M3)
    # The pit itself bridges onto the arm (a hull over the arm's inner side: the section AT the armpit's level read 983
    # on Garrett against his 968 chest), so it is the narrowest torso section in the 4 cm under the armpit
    hb_ = [girth(L_, Z) for z in np.arange(arm_z, arm_z - 0.0401, -0.005) if (L_ := torso(z)) is not None]
    mm["highBust"] = min(hb_) if hb_ else mm["chest"]
    # front and back lengths from hps down to the seat over the surface, a hand's width from centre: a belly makes
    # the front longer than the back (patterns draft them equal: the large-abdomen alteration adds the difference)
    zs_ = at["seat_z"]
    tf = down(zs_, hps[0], 0.06, -1)
    tb = down(zs_, hps[0], 0.06, 1)
    mm["hpsToSeatFront"], mm["hpsToSeatBack"] = length(tf), length(tb)
    loops["hpsToSeatFront"], loops["hpsToSeatBack"] = tf, tb
    zmin = float(V[:, 2].min())
    mm["waistToArmpit"] = arm_z - W
    # the same back tape stopped at the armpit's level: where an underarm lands down the back, measured as the pattern
    # is (the back's curve makes HPS-to-waist 18% longer than the vertical on Tess: an armpit placed from the waist
    # by waistToArmpit landed ~4 cm low in the world, dress-tess)
    ta_ = down(arm_z, hps[0], hps[0], 1)
    mm["hpsToArmpitBack"] = length(ta_)
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
            # the iliac crest (ANSUR II iliocristale height) from the crotch: no bone to palpate on a mesh; the crotch
            # is the mesh's own robust level. Clamped under the waist (a crest above the tape's waist reads 0)
            zi = min(zc + ILIAC_CREST_OVER_CROTCH * float(np.ptp(V[:, 2])), W)
            L_ = torso(zi)
            if L_ is not None:
                at["high_hip_z"] = float(zi)
                mm["highHip"], mm["waistToHighHip"] = girth(L_, Z), W - zi
    except Exception:  # a body the scan can't read keeps the estimate (pattern_blocks.trouser)
        pass
    try:
        mm.update(_leg_girths(V, T, J, at, zmin))
    except Exception:  # (a body without legs the scan can read: trouser drafts fall back to their proportions)
        pass
    mm["height"] = float(V[:, 2].max() - zmin)
    out = {k: (round(v * 1000.0, 1) if k != "shoulderSlope" else round(v, 2)) for k, v in mm.items()}
    return {"mm": out, "at": {k: (np.asarray(v).tolist() if not np.isscalar(v) else float(v)) for k, v in at.items()},
            "loops": loops}
