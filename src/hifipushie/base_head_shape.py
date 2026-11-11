"""Shape edits on a GNM head: the nose tip, chin, jawline, lean, ears, hood and planes. Part of base (base.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import retopo
from .base_identity import _lm_of, _local_smooth, region_weight

HOLLOW_RADIUS = 0.016  # m: a hollow cheek's reach
JAW_RADIUS = 0.009     # m: a bony jaw corner's reach (crisp: a soft one is a jowl)
JAW_TUCK_RADIUS = 0.014  # m: the tucked under-jaw's reach
HOOD_FORWARD = 0.4  # a hooded lid's fold comes down and this share of that forward, over the lid
HOOD_REACH = 0.5    # its fold's height: this share of the lid-to-brow distance (and its centre 0.45 of the way up)


def _nose_tip(W, lm, spec, s):
    """base.head.shape.nose_tip = deg | {"up": deg, "reach": share}: the nose's BASE line tilted: the tip and columella
    turned about the line through the two alar bases (lm 31 / 35, where the wings meet the cheek), so with `up` > 0 the
    tip rises against the alar base (a base line that climbs toward the tip instead of a tip hanging below the
    wings like a beak), < 0 lowers it. The turn grows from nothing at the alar bases' plane to full half way to the
    tip, and fades over `reach` x the nose's length away from the tip (the upper bridge stays), nothing on the lip.
    (A turn about the mid dorsum, tried first, only swung the whole base forward: the tip lies BELOW that pivot.)
    Landmarks ride."""
    sp = spec if isinstance(spec, dict) else {"up": spec}
    a = np.radians(float(sp.get("up", 0.0)))
    if abs(a) < 1e-9:
        return W, lm
    piv = 0.5 * (lm[31] + lm[35])
    tip = lm[30]
    r = float(sp.get("reach", 0.5)) * float(np.linalg.norm(lm[30] - lm[27]))
    zsub = float(lm[33][2])
    span = max(float(piv[1] - tip[1]), 1e-6)

    def turn(X, ang):
        q = X - piv
        y, z = q[:, 1], q[:, 2]
        return np.c_[q[:, 0], y * np.cos(ang) - z * np.sin(ang), y * np.sin(ang) + z * np.cos(ang)] + piv
    up = abs(a) if (turn(lm[[30]], abs(a)) - lm[[30]])[0, 2] > 0 else -abs(a)  # the turn that lifts the tip
    ang = up if a > 0 else -up

    def w(X):
        g_ = np.exp(-(np.linalg.norm(X - tip, axis=1) / r) ** 2)
        lip = _sstep((X[:, 2] - (zsub - 0.003 * s)) / (0.005 * s))   # nothing on the lip under the nose
        front = _sstep((piv[1] - X[:, 1]) / (0.5 * span))             # 0 at the alar bases' plane, 1 half way to the tip
        return (g_ * lip * front)[:, None]
    wW, wl = w(W), w(lm)
    W = W + wW * (turn(W, ang) - W)
    lm = lm + wl * (turn(lm, ang) - lm)
    return W, lm


def _mesh_edges(faces, n):
    E = np.array(sorted({(min(f[i], f[(i + 1) % len(f)]), max(f[i], f[(i + 1) % len(f)])) for f in faces
                         for i in range(len(f))}))
    return E, np.bincount(E.ravel(), minlength=n)


def _round_tip(W, lm, amount, s, faces):
    """shape.nose_tip.round (0..1+): the nose's tip blunted: shrinking smoothing weighted round the tip (lm 30) and up
    the supratip (toward lm 29), so a point with a notch above it becomes a rounded end running straight into the
    dorsum; the nostril rims (near lm 31-35 off the mid line) keep their weight low. Landmarks 29-30 ride."""
    from scipy.spatial import cKDTree
    k = s / 1.12
    c1, c2 = lm[30], 0.5 * (lm[30] + lm[29])
    d = np.minimum(np.linalg.norm(W - c1, axis=1), np.linalg.norm(W - c2, axis=1) * 1.15)
    wv = np.exp(-(d / (0.011 * k)) ** 2)
    E, deg = _mesh_edges(faces, len(W))
    W1 = _local_smooth(W, E, deg, wv, int(round(14 * float(amount))))
    tr = cKDTree(W)
    lm = lm.copy()
    for i in (29, 30):
        lm[i] = lm[i] + (W1 - W)[tr.query(lm[i])[1]]
    return W1, lm


def _chin(W, lm, spec, mx, s):
    """base.head.shape.chin = {"width", "square", "project", "height", "cleft", "cleft_length"} (m; square 0..1): the
    chin's own form, as smooth displacement fields from its landmarks (lm 8 the bottom, lm 7 / 9 the mental corners,
    lm 57 the lower lip): `width` = the two mental corners that much further apart (the flat of a broad chin);
    `square` = the bottom line levelled (the middle of a V raised, the corners lowered, toward one level);
    `project` = the chin's front forward; `height` = the chin's bottom lower; `cleft` = a mid-line groove this deep on
    the chin's front, `cleft_length` long (default 14 mm), from just over the bottom edge upward. Landmarks ride.
    Symmetric by construction."""
    sp = dict(spec)
    k = s / 1.12
    c = lm[8].copy()
    c[0] = mx
    cor = 0.5 * (np.abs(lm[7][0] - mx) + np.abs(lm[9][0] - mx))
    zc = 0.5 * (lm[7][2] + lm[9][2])
    yc = 0.5 * (lm[7][1] + lm[9][1])

    def field(X):
        D = np.zeros_like(X)
        ax = np.abs(X[:, 0] - mx)
        sg = np.sign(X[:, 0] - mx)
        zone = np.exp(-(np.linalg.norm((X - c) * [0.0, 1.0, 1.0], axis=1) / (0.03 * k)) ** 2) * _sstep((0.05 * k - ax) / (0.02 * k))
        wd = float(sp.get("width", 0.0)) * k
        if wd:  # the corners apart: x grows with |x| up to the corner, then holds
            D[:, 0] += sg * 0.5 * wd * np.clip(ax / max(cor, 1e-6), 0, 1) * np.exp(-(np.maximum(ax - cor, 0) / (0.02 * k)) ** 2) * zone
        sq = float(sp.get("square", 0.0))
        if sq:  # level bottom: middle up, corners down, by half the V's depth each
            dv = max(float(zc - c[2]), 0.0)
            mid = np.exp(-(ax / (0.6 * cor)) ** 2)
            crn = np.exp(-((ax - cor) / (0.6 * cor)) ** 2)
            low = np.exp(-((X[:, 2] - c[2]) / (0.016 * k)) ** 2) * np.exp(-((X[:, 1] - c[1]) / (0.03 * k)) ** 2)
            D[:, 2] += sq * 0.5 * dv * (mid - crn) * low
        pj = float(sp.get("project", 0.0)) * k
        if pj:
            D[:, 1] -= pj * np.exp(-(np.linalg.norm(X - (c + [0, 0, 0.012 * k]), axis=1) / (0.02 * k)) ** 2)
        ht = float(sp.get("height", 0.0)) * k
        if ht:
            D[:, 2] -= ht * np.exp(-(np.linalg.norm(X - c, axis=1) / (0.024 * k)) ** 2)
        un = float(sp.get("under", 0.0)) * k
        if un:  # `under`: the submental skin lifted, from behind the chin's bottom edge back to the throat, so the
            # line from chin to throat runs back level before it turns down into the neck
            back = (X[:, 1] - c[1]) / (0.045 * k)
            wu = _sstep(back / 0.25) * np.exp(-(np.maximum(back - 0.55, 0) / 0.45) ** 2)
            wu = wu * np.exp(-(ax / (0.032 * k)) ** 2) * np.exp(-(np.maximum(X[:, 2] - c[2] - 0.004 * k, 0) / (0.008 * k)) ** 2)
            wu = wu * np.exp(-(np.maximum(c[2] - 0.045 * k - X[:, 2], 0) / (0.015 * k)) ** 2)
            D[:, 2] += un * wu
        cl = float(sp.get("cleft", 0.0)) * k
        if cl:
            ln = float(sp.get("cleft_length", 0.014)) * k
            zm = c[2] + 0.004 * k + 0.5 * ln
            front = _sstep((yc + 0.012 * k - X[:, 1]) / (0.01 * k))  # the chin's front only
            cw = float(sp.get("cleft_width", 0.0028)) * k
            along = np.exp(-((X[:, 2] - zm) / (0.6 * ln)) ** 2) * front
            D[:, 1] += cl * np.exp(-(ax / cw) ** 2) * along
            lb = float(sp.get("cleft_lobes", 0.0)) * k
            if lb:  # the two pads of a cleft chin: a groove alone is a scratch on a round chin; a cleft reads because
                # the chin's front is TWO rounded lobes with the groove between them
                D[:, 1] -= lb * np.exp(-((ax - 2.6 * cw) / (2.0 * cw)) ** 2) * along
        return D
    return W + field(W), lm + field(lm)


JAWLINE_RADIUS = 0.034   # m: how far from the old jaw line the skin still follows its move
JAWLINE_SIGMA = 0.014    # m: along the line, each point follows the stretch of jaw line nearest it
JAWLINE_TUCK = 0.016     # m: depth of the band under the new border / behind the new ramus that is drawn in
JAWLINE_SMOOTH = 2       # rounds of smoothing of the move over the mesh


def _jawline(W, lm, ear, spec, mx, s, faces=None):
    """base.head.shape.jawline = {"below_lobe", "forward", "out", "tuck", "radius", "top"} (m): the mandible built as
    an L in profile, by construction: the jaw LINE itself is moved, with the skin on both sides of it.
    GNM's jaw contour (lm 2..7 a side) runs from in front of the ear lobe straight to the chin: one diagonal, its
    'angle' at the lobe's own height. Per side that line is carried onto a new one of the same parametrisation (by
    arc length): from under the ear lobe down a near-vertical ramus to the angle (`below_lobe` m under the lobe's
    lowest point, `forward` m in front of it, `out` m wider), then straight along the lower border to the chin's
    corner (lm 7 / 9, which stays). Every skin vertex follows the stretch of the old line nearest it (Gaussian
    `JAWLINE_SIGMA` along the line), fading with its distance from the line (`radius`), so the crest of the jaw, the
    cheek above it and the step into the neck under it all go with it; nothing moves on the ear or the throat's
    middle. `tuck` then draws the skin just outside the new line in toward the neck's axis (a clearer step). Landmarks
    ride. Mirrored: each side its own line."""
    from scipy.spatial import cKDTree
    sp = dict(spec)
    k = s / 1.12
    below = float(sp.get("below_lobe", 0.045)) * k
    fwd = float(sp.get("forward", 0.004)) * k
    out = float(sp.get("out", 0.0)) * k
    tuck = float(sp.get("tuck", 0.0)) * k
    R = float(sp.get("radius", JAWLINE_RADIUS)) * k
    sig = float(sp.get("sharp", JAWLINE_SIGMA)) * k  # smaller = a sharper turn at the angle
    W = W.copy()
    lm = lm.copy()
    W0 = W.copy()
    dear = cKDTree(W[ear]).query(W)[0] if ear.any() else np.full(len(W), 1.0)
    off_ear = _sstep((dear - 0.001 * k) / (0.007 * k))
    lat = _sstep((np.abs(W[:, 0] - mx) - 0.012 * k) / (0.02 * k))
    inside_ref = np.array([lm[33][1], lm[33][2]])
    for sx in (-1.0, 1.0):
        side = np.sign(W[:, 0] - mx) == sx
        ear_s = ear & side
        if not ear_s.any():
            continue
        lobe = W[ear_s][np.argmin(W[ear_s][:, 2])]
        ids = [2, 3, 4, 5, 6, 7] if np.sign(lm[3][0] - mx) == sx else [14, 13, 12, 11, 10, 9]
        O = np.array([lm[i] for i in ids])
        seg = np.linalg.norm(np.diff(O, axis=0), axis=1)
        u = np.r_[0, np.cumsum(seg)] / seg.sum()
        uu = np.linspace(0, 1, 60)
        Od = np.c_[[np.interp(uu, u, O[:, c]) for c in range(3)]].T
        # the new line: top (the old line's top, eased toward under the lobe by `top`), the angle, the chin's corner
        top = O[0] + float(sp.get("top", 0.5)) * np.array([0.0, lobe[1] - O[0][1], 0.0])
        g = np.array([lobe[0] + sx * out, lobe[1] - fwd, lobe[2] - below])
        end = O[-1]
        l1, l2 = np.linalg.norm(g - top), np.linalg.norm(end - g)
        uc = l1 / (l1 + l2)
        Nd = np.where((uu <= uc)[:, None], top + (uu / uc)[:, None] * (g - top),
                      g + ((uu - uc) / (1 - uc))[:, None] * (end - g))
        D = (Nd - Od) * _sstep(uu / 0.18)[:, None]  # nothing moves at the line's top (tiny faces by the lobe folded)
        d2 = ((W[:, None, :] - Od[None]) ** 2).sum(2)
        dmin = np.sqrt(d2.min(1))
        wg = np.exp(-(d2 - d2.min(1, keepdims=True)) / sig ** 2)
        disp = (wg[:, :, None] * D[None]).sum(1) / wg.sum(1, keepdims=True)
        fall = np.exp(-(dmin / R) ** 2) * side * off_ear * lat
        W = W + fall[:, None] * disp
        if tuck:
            poly = np.array([top[1:], g[1:], end[1:]])
            P = W[:, 1:]
            best_d = np.full(len(W), np.inf)
            best_s = np.zeros(len(W))
            best_t = np.zeros(len(W))
            for j in range(2):
                a, b = poly[j], poly[j + 1]
                ab = b - a
                t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
                q = a + t[:, None] * ab
                d = np.linalg.norm(P - q, axis=1)
                nrm = np.array([ab[1], -ab[0]])
                if (inside_ref - a) @ nrm > 0:
                    nrm = -nrm                                  # pointing out of the jaw
                sgn = np.sign((P - q) @ nrm)
                upd = d < best_d
                best_d[upd], best_s[upd], best_t[upd] = d[upd], sgn[upd], ((j + t) / 2)[upd]
            dout = np.where(best_s > 0, best_d, 0.0)
            band = np.clip(dout / (0.003 * k), 0, 1) * np.exp(-(dout / (JAWLINE_TUCK * k)) ** 2)
            along = _sstep(best_t / 0.1) * (1 - _sstep((best_t - 0.8) / 0.2))
            near_side = _sstep((np.abs(W[:, 0] - mx) - 0.02 * k) / (0.02 * k))
            W[:, 0] = W[:, 0] - sx * band * along * near_side * side * off_ear * tuck
        nk = float(sp.get("neck", 0.0)) * k
        if nk:  # the neck's sides under the corner drawn in: the step seen from the front (not a groove at the edge)
            zc = g[2] - 0.032 * k
            wn = np.exp(-((W[:, 2] - zc) / (0.02 * k)) ** 2) * np.exp(-((W[:, 1] - g[1]) / (0.035 * k)) ** 2)
            wn = wn * _sstep((np.abs(W[:, 0] - mx) - 0.02 * k) / (0.02 * k)) * side * off_ear
            W[:, 0] = W[:, 0] - sx * wn * nk
    if faces is not None and int(sp.get("smooth", JAWLINE_SMOOTH)):
        E = np.array(sorted({(min(f[i], f[(i + 1) % len(f)]), max(f[i], f[(i + 1) % len(f)])) for f in faces
                             for i in range(len(f))}))
        deg = np.bincount(E.ravel(), minlength=len(W))
        Dm = W - W0
        for _ in range(int(sp.get("smooth", JAWLINE_SMOOTH))):
            Dm = Dm + 0.5 * retopo._lap(Dm, E, deg)
        W = W0 + Dm
    tr = cKDTree(W0)
    for i in range(0, 17):
        lm[i] = lm[i] + (W - W0)[tr.query(lm[i])[1]]
    return W, lm

LEAN_RADIUS = 0.03    # m: how far from the jaw's border the thinning reaches
LEAN_KEEP = 0.004     # m: the border itself (this near the line) keeps its place: the bone doesn't thin


def _lean(W, lm, ear, spec, mx, s, faces):
    """base.head.shape.lean = m | {"under_jaw", "jowl", "submental", "radius", "smooth"} (m): soft tissue THINNED over
    the bone, which is not the weight slider run backwards (fat goes everywhere and takes the skull's width with it)
    and not a hollow (a dent under the cheekbone). The mandible's border (the jaw contour, lm 2..14) and the chin keep
    their place; the skin moves IN along its own normal in three bands measured from that border: `under_jaw` = the
    band below and behind it (the submandibular fullness that hides a border into the neck: thinned, the border stands
    as an edge with the neck stepping in under it), `submental` = the same under the chin (default = under_jaw),
    `jowl` = the lower cheek just above the border, outside the mouth's corners (the pouch that hangs over the border
    with age and weight). Each band rises from nothing at the border (LEAN_KEEP) to full ~12 mm away and fades over
    `radius`; the move is smoothed over the mesh. Nothing moves on the ears, lips, or above the mouth line.
    Landmarks ride. Mirrored by construction (each vertex against the whole contour)."""
    from scipy.spatial import cKDTree
    sp = spec if isinstance(spec, dict) else {"under_jaw": spec}
    k = s / 1.12
    und = float(sp.get("under_jaw", 0.0)) * k
    sub = float(sp.get("submental", sp.get("under_jaw", 0.0))) * k
    jow = float(sp.get("jowl", 0.0)) * k
    R = float(sp.get("radius", LEAN_RADIUS)) * k
    O = np.array([lm[i] for i in range(2, 15)])
    seg = np.linalg.norm(np.diff(O, axis=0), axis=1)
    u = np.r_[0, np.cumsum(seg)] / seg.sum()
    uu = np.linspace(0, 1, 160)
    Od = np.c_[[np.interp(uu, u, O[:, c]) for c in range(3)]].T
    d, j = cKDTree(Od).query(W)
    q = Od[j]
    T = np.array([(f[0], f[i], f[i + 1]) for f in faces for i in range(1, len(f) - 1)])
    N = retopo._vnormals(W, T)
    h = q[:, 2] - W[:, 2]                                   # > 0: below the border
    rise = _sstep((d - LEAN_KEEP * k) / (0.008 * k)) * np.exp(-(np.maximum(d - 0.012 * k, 0) / R) ** 2)
    below = _sstep(h / (0.004 * k))
    above = _sstep(-h / (0.004 * k))
    ax = np.abs(W[:, 0] - mx)
    mid = np.exp(-(ax / (0.022 * k)) ** 2)                  # under the chin
    mouth_w = 0.5 * abs(lm[54][0] - lm[48][0])
    dear = cKDTree(W[ear]).query(W)[0] if ear.any() else np.full(len(W), 1.0)
    off_ear = _sstep((dear - 0.002 * k) / (0.008 * k))
    w_under = rise * below * (und * (1 - mid) + sub * mid)
    zmouth = 0.5 * (lm[48][2] + lm[54][2])
    w_jowl = (jow * rise * above * _sstep((ax - mouth_w - 0.004 * k) / (0.008 * k))
              * _sstep((zmouth + 0.004 * k - W[:, 2]) / (0.01 * k)))
    amt = (w_under + w_jowl) * off_ear
    Dm = -amt[:, None] * N
    E = np.array(sorted({(min(f[i], f[(i + 1) % len(f)]), max(f[i], f[(i + 1) % len(f)])) for f in faces
                         for i in range(len(f))}))
    deg = np.bincount(E.ravel(), minlength=len(W))
    for _ in range(int(sp.get("smooth", 4))):
        Dm = Dm + 0.5 * retopo._lap(Dm, E, deg)
    lm = lm + Dm[cKDTree(W).query(lm)[1]]
    return W + Dm, lm


EAR_BLEND = 0.004  # m: the band at an ear's root over which its turn fades in (the skin round it is untouched)
EAR_ROOT = 0.003   # m: ear vertices this near the rest of the skin are its attachment


def _ears(W, ear, spec, mx, s):
    """base.head.shape.ears = {"out": deg, "size": factor, "blend": m}: each auricle turned RIGIDLY about its
    attachment line, so the helix rim swings out from the head and the root stays put. The line runs from the lobe's
    attachment (the lowest attached vertex) up to the top of the ear's FRONT attachment (where the helix leaves the
    temple): it passes by the lobe, so the lobe hardly moves and the top swings out most, as on a head whose ears
    stand out. The turn fades in over EAR_BLEND from the root only (nothing but the ear's own vertices move: no web
    of cheek or mastoid skin); `size` (default 1) scales the auricle about the lobe's attachment the same rigid way.
    Mirrored by construction (each side its own line)."""
    from scipy.spatial import cKDTree
    out = np.radians(float(spec.get("out", 0.0)))
    size = float(spec.get("size", 1.0))
    k = s / 1.12
    W = W.copy()
    rest = cKDTree(W[~ear])
    for sg in (-1.0, 1.0):
        idx = np.flatnonzero(ear & (np.sign(W[:, 0] - mx) == sg))
        if len(idx) < 10:
            continue
        P = W[idx]
        d_root = rest.query(P)[0]
        root = P[d_root < max(EAR_ROOT * k, np.percentile(d_root, 10))]
        low = root[np.argmin(root[:, 2])]
        front = root[root[:, 1] <= np.median(root[:, 1])]      # (the head faces -y)
        top = front[np.argmax(front[:, 2])]
        ax = (top - low) / np.linalg.norm(top - low)

        def rot(v, a, ax=ax):
            return v * np.cos(a) + np.cross(ax, v) * np.sin(a) + ax * (v @ ax)[..., None] * (1 - np.cos(a))
        d0 = float(np.percentile(d_root, 12))                  # the attached ring itself stays (its edges to the head keep their length)
        w = _sstep((d_root - d0) / (float(spec.get("blend", EAR_BLEND)) * k))[:, None]
        a = out if ((w * (rot(P - low, out) - (P - low)))[:, 0] * sg).sum() > 0 else -out  # the rim goes outward
        Q = low + rot(P - low, a) * size
        W[idx] = P + w * (Q - P)
    return W


def _hood(W, lm, hood, exterior=None):
    """base.head.shape.hood = m | {"amount", "forward", "reach", "lateral", "extent", "crease", "show", "crease_width"}: hooded upper lids. The skin between the upper lid
    and the brow (the fold) comes down by `amount` and forward over the lid; the lid's margin comes down with it by
    the fold's own falloff (~45%), the lower lid and the eyeball's seat don't move (a gate at the corners' height),
    and the lid landmarks ride, so the visible opening is lower as on a hooded eye. Per eye from its own landmarks.
    `lateral` 0..1 (0): the hood weighted to the OUTER part of the eye (lateral hooding, the common ageing form: the
    fold hangs over the outer third and the outer corner, the inner lid still shows): the fold's weight ramps from
    1 - lateral at the inner corner to full past the outer one, its centre shifts out by 0.2 x lateral x the eye's
    width, and the gate that holds the lower lid drops by `lateral` x half the opening outside the outer corner, so
    the fold can come down to and over the corner's own height there. `extent` (1): the fold's width along the eye.
    `crease` m (0): the fold's edge as geometry, a soft S across the lid along the margin's own arch: the tarsal
    platform's top tucked back and the skin just above it brought forward, so the fold's edge stands over the
    platform and shades a soft line at `show` (4 mm) above the lash line (the pretarsal show; on a hooded lid the true
    supratarsal crease, ~7-8 mm up, is hidden under the fold). It runs from just lateral of the inner corner and fades
    out before the outer corner (under the hood), the show 0.75 x at its ends; `crease_width` (1.8 mm) is the S's
    half width (wider than the head's mesh spacing), the depth is capped at 0.4 x that so the surface can't fold over
    itself."""
    h = hood if isinstance(hood, dict) else {"amount": hood}
    a = float(h["amount"])
    fw = float(h.get("forward", HOOD_FORWARD))
    reach = float(h.get("reach", HOOD_REACH))
    lat = float(h.get("lateral", 0.0))
    ext = float(h.get("extent", 1.0))
    cr_w = float(h.get("crease_width", 0.0018))     # m: the S's half width
    cr = min(float(h.get("crease", 0.0)), 0.4 * cr_w)  # m: depth, capped (no fold-over)
    show = float(h.get("show", 0.004))               # m: the visible platform under the fold's edge
    mx = float(lm[27][0])
    DW, DL = np.zeros_like(W), np.zeros_like(lm)
    for up, corners, brow, lower in (((37, 38), (36, 39), (18, 19, 20), (40, 41)),
                                     ((43, 44), (42, 45), (23, 24, 25), (46, 47))):
        U, Bw = lm[list(up)].mean(0), lm[list(brow)].mean(0)
        c0, c1 = lm[corners[0]], lm[corners[1]]
        ex = (c1 - c0) / np.linalg.norm(c1 - c0)
        dz = float(Bw[2] - U[2])
        wid = float(np.linalg.norm(c1 - c0))
        out_ = ex if abs(c1[0] - mx) > abs(c0[0] - mx) else -ex   # toward the outer corner
        c = U + 0.45 * (Bw - U) + 0.2 * lat * wid * out_
        sx, sz = 0.65 * wid * ext, reach * dz
        zc = 0.5 * (c0[2] + c1[2])
        op = max(float(U[2] - lm[list(lower)].mean(0)[2]), 1e-4)
        mv = np.array([0.0, -fw, -1.0]) * a

        def f(X):
            q = X - c
            u = q @ ex
            g_ = np.exp(-(u / sx) ** 2 - (q[:, 2] / sz) ** 2 - (q[:, 1] / (2 * sx)) ** 2)
            if not lat:
                return g_ * _sstep((X[:, 2] - zc) / (0.6 * op))
            uo = (X - U) @ out_ / wid                              # 0 at the lid's middle, +0.5 at the outer corner
            g_ = g_ * (1 - lat + lat * _sstep(uo + 0.5))
            drop = lat * 0.5 * op * _sstep((uo - 0.3) / 0.4)       # the gate lowered past the outer corner
            return g_ * _sstep((X[:, 2] - zc + drop) / (0.6 * op))
        DW += f(W)[:, None] * mv
        DL += f(lm)[:, None] * mv
        if cr:   # the fold's edge over the tarsal platform: a soft S along the margin's arch (see the docstring)
            um = 0.5 * (c0 + c1)
            zm, ze = float(U[2]), 0.5 * float(c0[2] + c1[2])      # the margin's height: middle, corners (a parabola)
            nf = np.array([0.0, -1.0, 0.3]) / np.linalg.norm([0.0, -1.0, 0.3])   # the lid's outward direction
            sgn = 1.0 if (out_ @ ex) > 0 else -1.0

            def fc(X):
                u = sgn * ((X - um) @ ex) / (0.5 * wid)          # -1 inner corner .. +1 outer corner
                hh = X[:, 2] - (ze + (zm - ze) * (1 - np.clip(u, -1.2, 1.2) ** 2))   # height over the margin
                e = show * (1 - 0.25 * np.clip(u, -1, 1) ** 2)
                along = _sstep((u + 0.9) / 0.3) * _sstep((0.85 - u) / 0.3)
                depth = (np.abs(X[:, 1] - U[1]) < 0.6 * wid) & (True if exterior is None else exterior)   # outer skin only
                prof = np.exp(-((hh - e + cr_w) / cr_w) ** 2) - 0.6 * np.exp(-((hh - e - cr_w) / cr_w) ** 2)
                return cr * prof * along * depth
            DW += -fc(W)[:, None] * nf
    return W + DW, lm + DL


def _sstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


PLANES_KEEP = {("nose_region",): 10, ("upper_lip_region", "lower_lip_region", "chin_region"): 30}  # features _planes
# leaves alone (group names: feather rounds); the lips and chin fade out wide: feathered at 10 the kept muzzle met the
# pushed cheek in a crease (a smile fold beside the mouth)
def _planes(V: np.ndarray, pts: np.ndarray, n: float, g: dict, hold: float = 0.8, keep: float = 1.0) -> tuple:
    """A head's front and side planes meeting at a tighter corner (a stylised head: the forehead slab turning
    sharply into the side plane at the temple, on down the cheekbone to the jaw corner). Per 2 mm height band, the
    face's horizontal section is taken as an ellipse (half width a at the jaw contour's depth, depth b from there to
    the cheek's front off the midline) and every point in front of the jaw contour is moved radially (in the
    ellipse's normalised coordinates) onto the superellipse of exponent n (2 = unchanged, 3 = boxy): nothing moves
    straight ahead (nose, mouth) or straight out at the side, the most at the corner between. GNM frame (Y up,
    Z forward). pts (eye joints) move with it. Returns (V, pts).
    The nose, lips and chin (PLANES_KEEP, feathered) are held by `keep` (0..1): the radial push acts on their own
    sides too (off the straight-ahead axis), which boxed the nose's section and sliced its front flat; the planes
    are the broad face's (temple, cheekbone, jaw corner), not the features'."""
    lm = _lm_of(g, V)
    skin = g["skin"] & ~(g["groups"]["ears"] > 0.5)
    zc = 0.5 * (lm[0][2] + lm[16][2])  # the jaw contour's depth at the ear: the side of the face
    xc = 0.5 * (lm[0][0] + lm[16][0])
    S = V[skin]
    ys = np.arange(lm[8][1] - 0.03, S[:, 1].max() + 0.004, 0.002)
    a, b = np.full(len(ys), np.nan), np.full(len(ys), np.nan)
    for i, y in enumerate(ys):
        m = np.abs(S[:, 1] - y) < 0.003
        side = m & (np.abs(S[:, 2] - zc) < 0.008)
        if side.sum() > 3:
            a[i] = np.percentile(np.abs(S[side, 0] - xc), 90)
        u = np.abs(S[:, 0] - xc)
        front = m & (u > 0.02) & (u < 0.036)
        if front.sum() > 3:
            b[i] = S[front, 2].max() - zc
    ok = ~np.isnan(a) & ~np.isnan(b) & (b > 0.01)
    if ok.sum() < 5:
        return V, pts
    from scipy.ndimage import gaussian_filter1d
    a = gaussian_filter1d(np.interp(ys, ys[ok], a[ok]), 4)  # ~8 mm
    b = gaussian_filter1d(np.interp(ys, ys[ok], b[ok]), 4)

    eyes = np.asarray(pts, float)

    def move(X, wmask=None):
        A, B = np.interp(X[:, 1], ys, a), np.interp(X[:, 1], ys, b)
        U, W = (X[:, 0] - xc) / A, (X[:, 2] - zc) / B
        phi = np.arctan2(np.abs(U), W)
        rs = (np.abs(np.cos(phi)) ** n + np.abs(np.sin(phi)) ** n) ** (-1.0 / n)
        # in front of the jaw contour only; from under the jaw corner (the neck stays) up over the forehead
        w = _sstep((X[:, 2] - zc + 0.012) / 0.024) * _sstep((X[:, 1] - lm[8][1] + 0.004) / 0.022)
        # the eyes and their lids mostly held (moved out with the corner, the interocular grew 7%: wide-set eyes)
        de = np.min([np.linalg.norm(X - e, axis=1) for e in eyes], axis=0)
        w = w * (1 - hold * np.exp(-(de / 0.022) ** 2))
        if wmask is not None:
            w = w * wmask
        k = 1 + w * (rs - 1)
        Y = X.copy()
        Y[:, 0] = xc + (X[:, 0] - xc) * k
        Y[:, 2] = zc + (X[:, 2] - zc) * k
        return Y
    ears = g["groups"]["ears"]
    kw = np.max([region_weight(list(gs), f) for gs, f in PLANES_KEEP.items()], axis=0)
    wm = (1.0 - np.clip(ears, 0, 1)) * (1.0 - keep * kw)
    return move(V, wm), move(np.asarray(pts, float))
