"""Tubes between loops: the neck tube that joins a grafted head to the body, garment tubes and `garment`. Part of base (base.py has the overview)."""
from __future__ import annotations

import hashlib
import json

import numpy as np
from scipy.spatial import cKDTree

from . import retopo
from .base import LOW_LOOP, SEAM, TUBE_BAND, VERSION, _CACHE
from .base_imls import _catmull_clark, _normals_and_h, _sd_body, _unit

def _push(W, tpl, pushes):
    """Big soft volume changes on the base mesh itself: base["push"] = [{"at": [x, y, z], "radius": m, "amount": m},
    ...] moves vertices along their normals by amount x a smooth bump (1 at the centre, 0 at radius); a centre with
    x > 0 is mirrored. A belly or love handles: blobs with big blends or deep clay strokes reach past where the base's
    field is exact (a few cm off its surface) and came out as plates."""
    T = retopo.tris(tpl["L"], tpl["S"])
    N = retopo._vnormals(W, T)
    D = np.zeros_like(W)
    for p in pushes:
        c, r, a = np.array(p["at"], float), float(p["radius"]), float(p["amount"])
        for cc in ([c, c * [-1, 1, 1]] if abs(c[0]) > 1e-6 else [c]):
            x = np.clip(np.linalg.norm(W - cc, axis=1) / r, 0, 1)
            D += (a * (1 - x * x) ** 2)[:, None] * N
    return W + D


def _soften(W, tpl, s, amount):
    """Muscle definition smoothed away (Taubin, so the volume stays): the template is a heroic physique (abs, pecs,
    big deltoids); amount ~ 1 softens it to an ordinary body, 2 to a soft one. Hands, feet and the head are left
    alone (fading over a few cm from the wrists, ankles and neck)."""
    E = retopo.edges(tpl["L"], tpl["S"])
    deg = np.bincount(E.ravel(), minlength=len(W))
    J = s["joints"]
    w = np.ones(len(W))
    for side in "LR":  # past the wrist along the forearm (the hand), and below the ankle (the foot)
        e, wr = np.array(J[f"elbow.{side}"]["pos"]), np.array(J[f"wrist.{side}"]["pos"])
        ax = _unit(wr - e)
        near = np.linalg.norm(W - wr, axis=1) < 0.25
        w *= np.where(near, np.clip(((wr - W) @ ax + 0.01) / 0.05, 0, 1), 1.0)
        an = np.array(J[f"ankle.{side}"]["pos"])
        near = (np.abs(W[:, 0] - an[0]) < 0.12) & (W[:, 2] < an[2] + 0.1)
        w *= np.where(near, np.clip((W[:, 2] - an[2] - 0.01) / 0.05, 0, 1), 1.0)
    neck = np.array(J["neck"]["pos"])
    w *= np.clip((neck[2] + 0.04 - W[:, 2]) / 0.06, 0, 1)
    w = w[:, None]
    X = W.copy()
    for _ in range(int(round(10 * amount))):
        for lam in (0.5, -0.53):
            X = X + lam * w * retopo._lap(X, E, deg)
    return X


def _neck_loops(tpl):
    """The template's closed edge loops round the neck under its chin (loops there tilt: low at the throat, high at
    the nape), highest first: ([loops], the head's top vertex)."""
    key = ("neck_loops", tpl["name"], len(tpl["P"]), float(tpl["P"][:, 2].max()))
    if key not in _CACHE:
        P = tpl["P"]
        faces, nb, ef = retopo.topology(tpl["L"], tpl["S"])
        eye = np.array(tpl["face"]["landmarks"]["eye.L"])
        chin_z = tpl.get("chin_z", eye[2] - 0.15)
        near = set(np.flatnonzero((P[:, 2] > chin_z - 0.14) & (P[:, 2] < chin_z + 0.05) & (np.abs(P[:, 0]) < 0.14)))
        top = int(np.argmax(P[:, 2]))
        found, loose = [], []
        for path in retopo._loops_round(P, faces, nb, ef, near, 200):
            Q = P[path]
            ang = np.arctan2(Q[:, 1] - Q[:, 1].mean(), Q[:, 0])
            wn = np.sum((np.diff(np.r_[ang, ang[:1]]) + np.pi) % (2 * np.pi) - np.pi) / (2 * np.pi)
            if abs(round(wn)) != 1:
                continue
            if Q[:, 2].max() > chin_z - 0.025 or np.abs(Q[:, 0]).max() > 0.12:
                if Q[:, 2].max() <= chin_z - 0.012 and np.abs(Q[:, 0]).max() <= 0.16:
                    loose.append((float(Q[:, 2].max()), path))
                continue
            found.append((float(Q[:, 2].max()), path))
        if not found:  # a short, stooped neck (MakeHuman's old bodies): no loop clears the chin by 2.5 cm; take the
            found = loose  # ones under it at all (an old male body raised IndexError here)
        if not found:
            raise ValueError("base: no closed loop round the body's neck under its chin to graft the head onto "
                             "(try another body age / weight)")
        found.sort(key=lambda f: -f[0])
        _CACHE[key] = ([f[1] for f in found], top)
    return _CACHE[key]


def _neck_tube(W, faces, tpl, s, head, step=0.006):
    """Everything above the neck loop dropped; the loop extruded along the neck -> head axis in rings `step` apart up
    past the head's top and capped (quads; subdivided with the rest). Each ring vertex tapers (smoothstep) from the
    loop's radius to the grafted head's neck radius at its angle, reaching it at the graft plane: a straight tube
    read as a collar with an edge at each end."""
    loops, top = _neck_loops(tpl)
    pc, pn, band = head["plane"]
    # the highest loop wholly LOW_LOOP under the overlap with the head: a loop reaching into it (a bigger head's plane
    # sits lower) left the taper no room, and the seam showed as a ridge with flecks
    loop = next((lp for lp in loops if ((W[lp] - pc) @ pn).max() < -(SEAM + LOW_LOOP)), loops[-1])
    J = s["joints"]
    n = _unit(np.array(J["head"]["pos"], float) - np.array(J["neck"]["pos"], float))
    ring0 = W[loop]
    c0 = ring0.mean(0)
    e1 = _unit(np.cross(n, [0, 1.0, 0]) if abs(n[1]) < 0.9 else np.cross(n, [1.0, 0, 0]))
    e2 = np.cross(n, e1)
    q0 = ring0 - c0 - np.outer((ring0 - c0) @ n, n)
    th = np.arctan2(q0 @ e2, q0 @ e1)
    r0 = np.linalg.norm(q0, axis=1)
    hp = float((pc - c0) @ n)  # the plane's height over the loop's centre, along the axis
    H = head["verts"]
    bins = 36
    x_th = (th + np.pi) / (2 * np.pi) * bins - 0.5
    d = q0 / np.maximum(r0, 1e-9)[:, None]
    foot0 = c0 + np.outer((ring0 - c0) @ n, n)  # each loop vertex's axis point

    def head_r(u):
        """The head's neck radius per loop vertex (its angle about the axis) in a slice at u along the plane's
        normal: its vertices within a few mm, median per angle bin."""
        sl = H[np.abs((H - pc) @ pn - u) < 0.004]
        qs = sl - c0 - np.outer((sl - c0) @ n, n)
        ang = np.arctan2(qs @ e2, qs @ e1)
        rad = np.linalg.norm(qs, axis=1)
        k = ((ang + np.pi) / (2 * np.pi) * bins).astype(int) % bins
        rb = np.array([np.median(rad[k == i]) if (k == i).sum() else np.nan for i in range(bins)])
        ok = np.isfinite(rb)
        rb = np.interp(np.arange(bins), np.flatnonzero(ok), rb[ok], period=bins)
        return np.interp(x_th, np.arange(bins), rb, period=bins)
    # through the whole overlap with the head (u in -SEAM..+SEAM about the plane) the tube follows the head's own
    # neck, slice by slice: matched only at the plane, the tube stood up to 1 cm proud of the head's narrowing neck
    # just above it and the blended points made flecks; below the overlap a cubic Hermite from the loop's radius and
    # slope
    us = np.linspace(-SEAM, SEAM, 9)
    R = np.array([head_r(u) for u in us])  # (levels, loop)
    npn = float(n @ pn)
    h_start = ((pc - foot0 - R[0][:, None] * d) @ pn - SEAM) / npn  # the height where each vertex enters the overlap
    s1 = (R[1] - R[0]) / ((us[1] - us[0]) / npn)  # the head's slope there, per metre of height
    height = float((W[top] - c0) @ n) + 0.02
    # the body's slope under the loop (radius change per metre of height), so the tube leaves the loop along the
    # neck's own surface: starting straight up it left a crease round the neck's base
    below = ring0 - 0.012 * n
    rest = np.setdiff1d(np.arange(len(W)), loop)
    Wb = W[rest][cKDTree(W[rest]).query(below)[1]]
    qb = Wb - c0 - np.outer((Wb - c0) @ n, n)
    s0 = np.clip((r0 - np.linalg.norm(qb, axis=1)) / np.maximum((ring0 - Wb) @ n, 1e-3), -1.5, 1.5)
    L = np.maximum(h_start, 1e-3)
    m0, m1 = L * s0, L * s1
    if head.get("room"):  # (heads that follow their body, headfit.py) a MONOTONE taper: where the body's neck is
        # centimetres wider than the head's (MakeHuman's heavy and old bodies) the end slopes overshot, and the tube
        # swelled out before it came in: a stand-up collar with a groove inside it (Fritsch-Carlson limits)
        dr = R[0] - r0
        m0 = np.where(m0 * dr <= 0, 0.0, np.sign(dr) * np.minimum(np.abs(m0), 3 * np.abs(dr)))
        m1 = np.where(m1 * dr <= 0, 0.0, np.sign(dr) * np.minimum(np.abs(m1), 3 * np.abs(dr)))
    rings = []
    for kk in range(int(height / step) + 1):
        hh = kk * step
        t = np.clip(hh / L, 0, 1)
        h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
        r = h00 * r0 + h10 * m0 + h01 * R[0] + h11 * m1
        over = hh > L  # in the overlap: the head's radius at this vertex's u
        if over.any():
            u = (hh - L[over]) * npn - SEAM
            j = np.clip(np.searchsorted(us, u) - 1, 0, len(us) - 2)
            f = np.clip((u - us[j]) / (us[j + 1] - us[j]), 0, 1)
            cols = np.flatnonzero(over)
            r[over] = (1 - f) * R[j, cols] + f * R[j + 1, cols]
        rings.append(foot0 + hh * n + r[:, None] * d)
    tip = rings[-1].mean(0) + step * n
    V, fl, _, remap = retopo._stitch(W, faces, {"neck": (list(loop), top, (rings, tip))})
    src = np.full(len(V), -1)  # each vertex's index in the mesh that came in (-1: the tube's own)
    keep = np.flatnonzero(remap >= 0)
    src[remap[keep]] = keep
    return V, fl, src


def _wlap(X, E, w):
    """Laplacian with edge weights w."""
    acc = np.zeros_like(X)
    tot = np.zeros(len(X))
    np.add.at(acc, E[:, 0], w[:, None] * X[E[:, 1]])
    np.add.at(acc, E[:, 1], w[:, None] * X[E[:, 0]])
    np.add.at(tot, E[:, 0], w)
    np.add.at(tot, E[:, 1], w)
    return acc / np.maximum(tot, 1e-12)[:, None] - X


def _seg_dist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / max(float(ab @ ab), 1e-12), 0, 1)
    return np.linalg.norm(P - (a + t[:, None] * ab), axis=1), t


def _garment_tube(X, keep, o, u, L, tb: dict, hang: float, ease: float, info: dict, B=None):
    """Cloth as a tube round an axis (from o along u, the way the cloth hangs, L long): per 1 cm slice across the axis
    the convex hull of the (closed, eased) cloth's points `keep`, radius per angle, hanging from the wider slice
    above (under the chest and belly, over the seat; a trouser leg from the thigh), smoothed, with drape folds where
    it hangs free of the body (tb["folds"], default 1; tb["seed"]). Its first TUBE_BAND hands over to the cloth made
    from the body by weight (_tube_weight, `info`); the far end is cut by the part's region. Returns an IMLS point
    set (a quad grid, capped with rings) or None."""
    from scipy.spatial import ConvexHull
    from scipy.ndimage import gaussian_filter
    u = _unit(np.asarray(u, float))
    e1 = _unit(np.cross(u, [0, 1.0, 0]) if abs(u[1]) < 0.9 else np.cross(u, [1.0, 0, 0]))
    e2 = np.cross(u, e1)
    nth, ds = 96, 0.01
    th = np.linspace(-np.pi, np.pi, nth, endpoint=False)
    ss = np.arange(0.0, L + 1e-9, ds)
    R = np.full((len(ss), nth), np.nan)
    P = X[keep] - o
    sp = P @ u
    Q = np.c_[P @ e1, P @ e2]
    dirs = np.c_[np.cos(th), np.sin(th)]
    # each slice's own centre (the hull's centroid, smoothed along the axis): a joint axis can run near the limb's
    # side (the femur from the hip joint), and rays from outside a slice's hull miss it
    hulls = []
    for sv in ss:
        sl = Q[np.abs(sp - sv) < 1.2 * ds]
        hulls.append(sl[ConvexHull(sl).vertices] if len(sl) >= 8 else None)
    C = np.array([h.mean(0) if h is not None else [np.nan, np.nan] for h in hulls])
    okc = np.isfinite(C[:, 0])
    if okc.sum() < 3:
        return None
    for j in range(2):
        C[:, j] = np.interp(np.arange(len(ss)), np.flatnonzero(okc), C[okc, j])
    C = gaussian_filter(C, (4.0, 0), mode="nearest")
    def radii(hulls):
        """Each slice's hull radius along each angle (about the smoothed centres); None if too few slices."""
        R = np.full((len(ss), nth), np.nan)
        for i, hull in enumerate(hulls):
            if hull is None:
                continue
            A = hull - C[i]
            E = np.roll(A, -1, axis=0) - A
            for k, dv in enumerate(dirs):  # the hull's radius along each angle
                den = dv[0] * E[:, 1] - dv[1] * E[:, 0]
                ok = np.abs(den) > 1e-12
                tt = (A[:, 0] * E[:, 1] - A[:, 1] * E[:, 0])[ok] / den[ok]
                uu = (A[:, 0] * dv[1] - A[:, 1] * dv[0])[ok] / den[ok]
                good = (tt > 0) & (uu >= -1e-9) & (uu <= 1 + 1e-9)
                if good.any():
                    R[i, k] = tt[good].max()
        rows = np.flatnonzero(np.isfinite(R).all(1))
        if len(rows) < 3:
            return None
        for i in range(len(ss)):  # slices with too few points: the nearest one's
            if not np.isfinite(R[i]).all():
                R[i] = R[rows[np.argmin(np.abs(rows - i))]]
        return R
    R = radii(hulls)
    if R is None:
        return None
    Rb = gaussian_filter(R, (4.0, 1.5), mode=("nearest", "wrap"))  # the body's own hull, before hanging
    for i in range(1, len(ss)):  # hanging: cloth falls from the wider slice above
        R[i] = np.maximum(R[i], (1 - hang) * R[i] + hang * R[i - 1])
    R = gaussian_filter(R, (4.0, 1.5), mode=("nearest", "wrap")) + ease
    tp = float(tb.get("taper", 0.0))
    if tp:  # the looseness taken in toward the hem (a shirt tapering to the hips instead of falling as a tube): over
        # the last taper_len above `hem` (distance along the tube, default its end) the cloth closes in on the body's
        # own hull by `taper` of its gap, and the hem sits near the body (a hanging hem cut by the region was a roll)
        hem = float(tb.get("hem", L))
        tl = float(tb.get("taper_len", 0.25))
        f = tp * _smooth01((ss - (hem - tl)) / tl)
        Rn = Rb
        if B is not None:  # the body's own hull (the cloth's already hangs from the belly)
            Pb = B[keep] - o
            spb, Qb = Pb @ u, np.c_[Pb @ e1, Pb @ e2]
            hb = []
            for sv in ss:
                sl = Qb[np.abs(spb - sv) < 1.2 * ds]
                hb.append(sl[ConvexHull(sl).vertices] if len(sl) >= 8 else None)
            Rbody = radii(hb)
            if Rbody is not None:
                Rn = gaussian_filter(Rbody, (4.0, 1.5), mode=("nearest", "wrap"))
        R = R - f[:, None] * np.clip(R - Rn - ease, 0, None)
    fold = float(tb.get("folds", 1.0))
    if fold:  # drape folds where the cloth hangs free of the body: long ridges down the axis, deeper the looser
        rng = np.random.default_rng(int(tb.get("seed", 7)))
        F = gaussian_filter(rng.standard_normal(R.shape), (7.0, 1.6), mode=("nearest", "wrap"))
        F /= F.std() + 1e-12
        R += fold * 0.35 * np.clip(R - Rb - ease, 0, 0.03) * F
    ring = lambda i, f=1.0: (o + ss[i] * u + C[i, 0] * e1 + C[i, 1] * e2
                             + f * R[i][:, None] * (np.outer(np.cos(th), e1) + np.outer(np.sin(th), e2)))
    V = np.concatenate([ring(i) for i in range(len(ss))])
    idx = np.arange(len(ss) * nth).reshape(len(ss), nth)
    # the quads wind outward with the angle running e1 -> e2 and s along u (e1 x e2 = u): reversed
    faces = [[int(idx[i, k]), int(idx[i + 1, k]), int(idx[i + 1, (k + 1) % nth]), int(idx[i, (k + 1) % nth])]
             for i in range(len(ss) - 1) for k in range(nth)]
    nc = 16  # caps: concentric rings (a fan's long edges made a wide kernel, and the IMLS grew sheets)
    for row, top in ((0, True), (len(ss) - 1, False)):
        prev = idx[row]
        for j in range(1, nc):
            rg = np.arange(len(V), len(V) + nth)
            V = np.r_[V, ring(row, 1 - j / nc)]
            for k in range(nth):
                q = [int(prev[k]), int(prev[(k + 1) % nth]), int(rg[(k + 1) % nth]), int(rg[k])]
                faces.append(q if top else q[::-1])
            prev = rg
        cv = len(V)
        V = np.r_[V, [o + ss[row] * u + C[row, 0] * e1 + C[row, 1] * e2]]
        for k in range(nth):
            t3 = [cv, int(prev[k]), int(prev[(k + 1) % nth])]
            faces.append(t3 if top else t3[::-1])
    N, h = _normals_and_h(V, faces)
    c = V[:len(ss) * nth].mean(0)
    if ((V[:len(ss) * nth] - c) * N[:len(ss) * nth]).sum(1).mean() < 0:  # (orientation guard)
        faces = [f[::-1] for f in faces]
        N, h = _normals_and_h(V, faces)
    return {"verts": V, "normals": N, "h": h, "hmax": float(h.max()), "tree": cKDTree(V), "wt": None, "seam": None,
            "head": None, "far_fit": True, "blend_info": {"o": o, "u": u, **info}}


def _tube_weight(X, m):
    """How much of the field at X is a tube's (the rest is the cloth made from the body): 0 at the tube's start,
    easing to 1 over TUBE_BAND along it, times its side (a trouser leg: x on its own side) and away from the arms
    (the torso). A smooth union of the two swelled ~k/6 where they crossed: a ridge round the chest."""
    w = _smooth01(((X - m["o"]) @ m["u"]) / m.get("band", TUBE_BAND))
    if m.get("side"):
        w = w * _smooth01(m["side"] * X[:, 0] / 0.03 + 0.5)
    if m.get("arms"):
        dax = np.linalg.norm(np.cross(X - m["o"], m["u"]), axis=1)
        for a, b in m["arms"]:
            d, t = _seg_dist(X, a, b)
            k = 0.75 - 0.4 * t if m.get("taper") else 0.75
            w = w * np.where(t > 0.08, _smooth01((d - k * dax) / 0.04 + 0.5), 1.0)
    return w


def _smooth01(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def _tubes(X, J, g: dict, hang: float, B=None) -> list:
    """The garment's tubes: g["tube"] (a shirt's torso: down from 7 cm under the shoulders to 15 cm under the hips,
    arms left out) and g["legs"] (trouser legs: along hip -> knee from `start` (default 0.25) of the way, `length`
    (default 0.9 of hip -> knee)), each {} or with folds/seed/top/bottom/start/length."""
    out = []
    ease = float(g.get("tube_ease", 0.004))
    arm = np.zeros(len(X), bool)
    # tube "arms": "taper" = what counts as arm narrows toward the wrist (0.75 -> 0.35 of the distance to the axis): a
    # hand hanging by the hip claimed the hip's side, the tube was narrow there and its hem had a notch
    near = (lambda t: 0.75 - 0.4 * np.clip(t, 0, 1)) if (g.get("tube") or {}).get("arms") == "taper" else (lambda t: 0.75)
    arms = [(J[f"shoulder.{sd}"], J[f"wrist.{sd}"]) for sd in "LR" if f"shoulder.{sd}" in J and f"wrist.{sd}" in J]
    if g.get("tube") is not None and "pelvis" in J and "chest" in J:
        tb = g["tube"] or {}
        pel = J["pelvis"]
        c = np.array([pel[0], 0.5 * (pel[1] + J["chest"][1])])
        for a, b in arms:
            d, t = _seg_dist(X, a, b)
            arm |= (t > 0.08) & (d < near(t) * np.linalg.norm(X[:, :2] - c, axis=1))
        zt = float(tb.get("top", J["shoulder.L"][2] - 0.07 if "shoulder.L" in J else J["chest"][2] + 0.1))
        zb = float(tb.get("bottom", J["hip.L"][2] - 0.15 if "hip.L" in J else pel[2] - 0.15))
        t = _garment_tube(X, ~arm, np.array([c[0], c[1], zt]), [0, 0, -1.0], zt - zb, tb, hang or 0.8, ease,
                          {"arms": arms, "band": float(tb.get("band", TUBE_BAND)), "taper": tb.get("arms") == "taper"}, B)
        if t is not None:
            out.append(t)
    if g.get("legs") is not None and "hip.L" in J and "knee.L" in J:
        lg = g["legs"] or {}
        for sd, sign in (("L", 1.0), ("R", -1.0)):
            hp, kn = J[f"hip.{sd}"], J[f"knee.{sd}"]
            ln = float(np.linalg.norm(kn - hp))
            u = (kn - hp) / ln
            o = hp + float(lg.get("start", 0.25)) * ln * u
            keep = sign * X[:, 0] > 0.01
            s = (X - o) @ u
            keep &= (s > -0.05) & (np.linalg.norm(np.cross(X - o, u), axis=1) < 0.2)
            t = _garment_tube(X, keep, o, u, float(lg.get("length", 0.9)) * ln, lg, hang or 0.5, ease,
                              {"side": sign, "band": float(lg.get("band", TUBE_BAND))}, B)
            if t is not None:
                out.append(t)
    return out


def garment(key: str, g: dict, offset: float, joints: dict) -> dict:
    """A garment part's surface ({"garment": {...}} on a shell part): the base body (its unsubdivided quads) pushed
    out by `offset`, then closed and eased, as an IMLS point set (a "base" primitive of that part, cut to the part's
    region blobs like any shell). A shell follows every dip of the body (shrinkwrap); cloth spans them:
      close: outward-only smoothing rounds (default 30): the cloth bridges the dips between the chest and the
        belly, the spine's groove, the armpit, never going inside body + offset;
      hang: 0..1, cloth falls from the widest point of the torso instead of following it back in (under the chest
        and the belly), straight down at 1;
      ease: m, extra looseness along the closed surface's normals (default 0.006);
      ease_at: [{"at": [x, y, z] | joint, "radius", "amount"}]: more (or less) room in places (a baggy back, a
        loose sleeve), smooth bumps along the normals;
      tube: {} or {"bottom": z, "top": z, "folds", "seed", "band": m (the hand-over's length, default 0.08: shorter on a child)}: a shirt's or jacket's torso as a tube hanging from the
        chest and belly over the seat and the crotch; legs: {} or {"start", "length", "folds", "seed"}: trouser legs
        as tubes along hip -> knee (`_tubes`); tube_ease: m.
    Returns a list of IMLS point sets (one primitive each; with tubes, one set mixing them by weight).
    Folds are strokes on the part (op "crease"/"clay", part: the garment)."""
    if key not in _CACHE:
        raise KeyError("garment: the base surface isn't built (compile the spec's base first)")
    W0, faces = _CACHE[key]["quads"]
    W0 = np.asarray(W0, float)
    gk = ("garment", key, json.dumps(g, sort_keys=True, default=str), round(float(offset), 5), VERSION)
    if gk in _CACHE:
        return _CACHE[gk]
    E = np.array(sorted({(min(f[k], f[(k + 1) % len(f)]), max(f[k], f[(k + 1) % len(f)])) for f in faces
                         for k in range(len(f))}))
    N0, _ = _normals_and_h(W0, faces)
    X = W0 + offset * N0
    hang = float(g.get("hang", 0.0))
    J = {k: np.array(v["pos"], float) for k, v in joints.items() if isinstance(v, dict) and "pos" in v}
    ax = None
    if hang and "pelvis" in J and "chest" in J:  # the torso's axis, and which vertices are the torso
        pa, pb = J["pelvis"], J["neck"] if "neck" in J else J["chest"]
        ax = (pa, pb)
        sh = max((abs(J[k][0]) for k in ("shoulder.L", "hip.L") if k in J), default=0.2)
        tors = (W0[:, 2] > J.get("hip.L", pa)[2] - 0.12) & (W0[:, 2] < pb[2]) & (np.abs(W0[:, 0] - pa[0]) < 0.8 * sh)
        dz = W0[E[:, 1], 2] - W0[E[:, 0], 2]
        ln = np.maximum(np.linalg.norm(W0[E[:, 1]] - W0[E[:, 0]], axis=1), 1e-9)
        vert = (np.abs(dz) > 0.6 * ln) & tors[E[:, 0]] & tors[E[:, 1]]
        up = np.where(dz[vert] > 0, E[vert, 1], E[vert, 0])  # (upper, lower) pairs
        lo = np.where(dz[vert] > 0, E[vert, 0], E[vert, 1])
    w = np.ones(len(E))
    for it in range(int(g.get("close", 30))):
        X = X + 0.5 * _wlap(X, E, w)
        if ax is not None and it % 3 == 2:  # hanging: a vertex under a wider one moves out to (hang x) its radius
            c = ax[0][:2]
            R = X[:, :2] - c
            r = np.linalg.norm(R, axis=1)
            want = np.zeros(len(X))
            np.maximum.at(want, lo, r[up])
            grow = np.clip(hang * (want - r), 0, None) * 0.5
            X[:, :2] += R / np.maximum(r, 1e-9)[:, None] * grow[:, None]
        u = ((X - W0) * N0).sum(1)  # never inside the body + offset
        X = X + np.maximum(offset - u, 0)[:, None] * N0
    N1, _ = _normals_and_h(X, faces)
    X = X + float(g.get("ease", 0.006)) * N1
    for b in g.get("ease_at") or []:
        at = J[b["at"]] if isinstance(b["at"], str) else np.array(b["at"], float)
        d = np.linalg.norm(X - at, axis=1) / float(b["radius"])
        X = X + (float(b["amount"]) * np.exp(-2 * d ** 2) * (d < 1.5))[:, None] * N1
    V, F = X, faces
    Vb = W0
    for _ in range(1):
        V, F2 = _catmull_clark(V, F)
        Vb, _ = _catmull_clark(Vb, F)
        F = F2
    Nb, _ = _normals_and_h(Vb, F)
    u = ((V - Vb) * Nb).sum(1)  # the subdivided cloth still clear of the subdivided body
    V = V + np.maximum(offset - u, 0)[:, None] * Nb
    surf = _CACHE[key]
    if surf.get("graft") is not None:  # and clear of the real body: a grafted head's neck is wider at its base than
        # the template's own, and poked through the shirt beside the collar
        N, _ = _normals_and_h(V, F)
        near = np.linalg.norm(V - surf["graft"]["plane"][0], axis=1) < 0.25
        for _ in range(3):
            d = _sd_body(V[near], surf)
            V[near] += np.maximum(offset - d, 0)[:, None] * N[near]
    N, h = _normals_and_h(V, F)
    out = [{"verts": V, "normals": N, "h": h, "hmax": float(h.max()), "tree": cKDTree(V), "wt": None, "seam": None,
            "head": None, "far_fit": True}]
    tubes = _tubes(V, J, g, hang, Vb + offset * Nb) if J else []  # (from the subdivided cloth: slices of the coarse one missed points)
    if tubes:  # a torso hanging over the crotch and seat, trouser legs: tubes, handed over to the cloth from the
        # body by weight (_tube_weight)
        out = [{"mix": [out[0], *tubes], "weights": [t["blend_info"] for t in tubes],
                "verts": np.concatenate([out[0]["verts"]] + [t["verts"] for t in tubes]),
                "hmax": max([out[0]["hmax"]] + [t["hmax"] for t in tubes]), "head": None}]
    for k, o in enumerate(out):
        o["key"] = hashlib.sha1(repr((gk, k)).encode()).hexdigest()
    _CACHE[gk] = out
    return out
