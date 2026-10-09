"""Age as soft-tissue ops on a GNM head (base.head.shape; each off unless given, the head bit-identical without them).
An older face is not a different skull: the bone stays and the tissue over it thins, slides down and folds. So none
of these touches the identity; each moves skin along its own normal (or down), by millimetres, addressed from the 68
landmarks, mirrored by construction, and the landmarks ride. The skin pipeline's painted wrinkles are placed from the
same landmarks (skin.LINES "nasolabial", "marionette"): the crease here runs on that line, so paint and form agree.

  "nasolabial": m | {"depth": m, "length": 0..1.3 (1), "width": m (0.0032), "bulge": 0..1 (0.5)}
        the fold from beside the nostril's wing down past the mouth's corner: a crease `depth` deep on skin.LINES'
        own line, the cheek's fat standing over it on the cheek side (bulge x depth), nothing on the lip side.
  "prejowl": m | {"depth": m, "jowl": m (0.6 x depth), "radius": m (0.009)}
        the pre-jowl sulcus (a dent on the jaw's border between chin and jowl, under the mouth's corner) and the
        jowl behind it (the lower cheek's tissue come down over the border: out and down).
  "lid_fold": m | {"amount": m, "lateral": 0..1 (0.7)}
        upper-lid skin come down over the lid (dermatochalasis), mostly at the outer half: the fold between lid
        crease and brow drops; the lid's margin hardly moves (that is `hood`).
  "eye_bag": m | {"amount": m, "crease": share of amount (0.5), "height": x (1)}
        a soft bag under the lower lid (orbital fat behind thin lid skin): the skin from just under the lid's margin
        down ~0.2 eye widths stands out by `amount` (along the normal), and the lid-cheek junction under it dents by
        crease x amount (the lower-lid crease); the margin itself stays. Per eye from its corners and lower-lid points.
  "lip_bow": m | {"depth": m, "tubercle": m}
        the upper lip's Cupid's bow: the vermilion border's peaks (lm 50 / 52) up and its dip (51) down by half the
        depth each (+ = a deeper V; - flattens it), and the tubercle: the upper lip's middle (62) down and forward by
        `tubercle`, the lower lip held.
  "lip_roll": m | {"upper": m, "lower": m}
        everted, fuller lips as VOLUME (not height): each vermilion rolled forward by up to this, peaking in its upper
        part on the upper lip (it catches light on top and shades under it) and its middle on the lower lip (a shadow
        beneath it), full over the middle and tucked at the corners; the skin just past the vermilion's edges follows.
  "cheek_flat": m | {"amount": m, "descend": 0..1 (0.35)}
        the mid cheek flattened: the tissue under the orbit (infraorbital + the front of the cheekbone) thins in by
        `amount` and slides down by descend x amount (the malar fat's descent; the tear trough shows).
  "lips_thin": 0..1 | {"amount": 0..1, "back": m (0)}
        thinner lips: the vermilion's height reduced by this share toward the lips' seam (the skin above and below
        follows, fading over ~8 mm); `back` = the lips less proud.
"""
from __future__ import annotations

import numpy as np

KEYS = ("nasolabial", "prejowl", "lid_fold", "eye_bag", "lip_bow", "lip_roll", "cheek_flat", "lips_thin")
FOLD_WIDTH = 0.0032   # m: half-width of the nasolabial crease
SULCUS_RADIUS = 0.009  # m
LIP_FADE = 0.008      # m: how far above / below the vermilion the skin follows thinner lips


def _sstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _opt(v, key):
    return dict(v) if isinstance(v, dict) else {key: float(v)}


def wanted(shape: dict) -> bool:
    return any(shape.get(k) for k in KEYS)


def nasolabial_line(lm: np.ndarray, side: int, length: float = 1.0, n: int = 80) -> np.ndarray:
    """The fold's line on one side (side +1 = the subject's left, +x) as n points: skin.LINES["nasolabial.L"]'s own
    anchors and offsets (interocular units, from the lid landmarks' centres), cut or run on by `length`."""
    from .skin import LINES
    io = float(np.linalg.norm(lm[36:42].mean(0) - lm[42:48].mean(0)))
    idx = {"lm_nostril.L": 35 if side > 0 else 31, "lm_mouth_corner.L": 54 if side > 0 else 48}
    P = np.array([lm[idx[a]] + io * np.array([side * o[0], o[1], o[2]]) for a, o in LINES["nasolabial.L"][0]])
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    u = np.r_[0, np.cumsum(seg)] / seg.sum()
    uu = np.linspace(0, float(length), n)
    out = np.c_[[np.interp(np.minimum(uu, 1.0), u, P[:, c]) for c in range(3)]].T
    over = np.maximum(uu - 1.0, 0)[:, None]
    return out + over * seg.sum() * (P[-1] - P[-2]) / seg[-1]


def apply(W: np.ndarray, lm: np.ndarray, shape: dict, faces: list, groups: dict, mx: float, s: float,
          exterior: np.ndarray | None = None) -> tuple:
    """(W, lm) with the age ops of `shape` laid on. W = the placed skin vertices (world: z up, the face toward -y),
    lm = the 68 landmarks, groups = GNM's region weights on those vertices, mx = the mid-plane's x, s = head scale."""
    from scipy.spatial import cKDTree
    from . import retopo
    k = s / 1.12
    T = np.array([(f[0], f[i], f[i + 1]) for f in faces for i in range(1, len(f) - 1)])
    N = retopo._vnormals(W, T)
    if exterior is not None and (~exterior).any() and exterior.any():   # inner lip rolls, the lids' insides: the
        N = N.copy()                                                     # outer skin's normal beside them
        N[~exterior] = N[exterior][cKDTree(W[exterior]).query(W[~exterior])[1]]
    E = np.array(sorted({(min(f[i], f[(i + 1) % len(f)]), max(f[i], f[(i + 1) % len(f)])) for f in faces
                         for i in range(len(f))}))
    deg = np.bincount(E.ravel(), minlength=len(W))
    front = N[:, 1] < 0.35                       # skin that faces forward or sideways (not the back of the head)
    D = np.zeros_like(W)
    ax = np.abs(W[:, 0] - mx)
    down = np.array([0.0, 0.0, -1.0])
    if shape.get("nasolabial"):
        o = _opt(shape["nasolabial"], "depth")
        depth, wd = float(o.get("depth", 0.0)) * k, float(o.get("width", FOLD_WIDTH)) * k
        bulge = float(o.get("bulge", 0.5))
        for side in (-1, 1):
            L = nasolabial_line(lm, side, float(o.get("length", 1.0)))
            L = W[front][cKDTree(W[front]).query(L)[1]]   # onto the skin (the line's anchors carry depth offsets)
            tr = cKDTree(L)
            d, j = tr.query(W)
            u = j / (len(L) - 1)
            taper = _sstep(u / 0.12) * _sstep((1 - u) / 0.35)
            lateral = (W[:, 0] - L[j, 0]) * side          # > 0: the cheek's side of the line
            crease = -depth * taper * np.exp(-(d / wd) ** 2)
            pad = bulge * depth * taper * np.exp(-((d - 3.0 * wd) / (2.6 * wd)) ** 2) * _sstep(lateral / (1.5 * wd))
            near = front & (d < 12 * wd) & ((W[:, 0] - mx) * side > 0)
            D[near] += ((crease + pad)[:, None] * N)[near]
    if shape.get("prejowl"):
        o = _opt(shape["prejowl"], "depth")
        depth = float(o.get("depth", 0.0)) * k
        jowl = float(o.get("jowl", 0.6 * float(o.get("depth", 0.0)))) * k
        r = float(o.get("radius", SULCUS_RADIUS)) * k
        for side, (i_s, i_j, i_m) in ((-1, (6, 5, 48)), (1, (10, 11, 54))):
            c = lm[i_s] + np.array([0.0, 0.0, 0.004 * k])
            c = W[front][np.argmin(np.linalg.norm(W[front] - c, axis=1))]
            D += (-depth * np.exp(-(np.linalg.norm(W - c, axis=1) / r) ** 2))[:, None] * N * front[:, None]
            cj = 0.6 * lm[i_j] + 0.4 * lm[i_j - side] + np.array([0.0, 0.0, 0.007 * k])
            cj = W[front][np.argmin(np.linalg.norm(W[front] - cj, axis=1))]
            g = jowl * np.exp(-(np.linalg.norm(W - cj, axis=1) / (1.5 * r)) ** 2) * front
            D += g[:, None] * (0.6 * N + 0.4 * down)
    if shape.get("lid_fold"):
        o = _opt(shape["lid_fold"], "amount")
        a, lat = float(o.get("amount", 0.0)) * k, float(o.get("lateral", 0.7))
        for up, corners, brow, lower in (((37, 38), (36, 39), (18, 19, 20), (40, 41)),
                                         ((43, 44), (42, 45), (23, 24, 25), (46, 47))):
            U, Bw = lm[list(up)].mean(0), lm[list(brow)].mean(0)
            c0, c1 = lm[corners[0]], lm[corners[1]]
            ex = (c1 - c0) / np.linalg.norm(c1 - c0)
            if abs(c1[0] - mx) < abs(c0[0] - mx):       # ex points to the OUTER corner
                ex = -ex
            wid = float(np.linalg.norm(c1 - c0))
            dz = float(Bw[2] - U[2])
            c = U + 0.6 * (Bw - U) + 0.12 * wid * ex
            q = W - c
            uu = q @ ex
            g = np.exp(-(uu / (0.7 * wid)) ** 2 - (q[:, 2] / (0.42 * dz)) ** 2 - (q[:, 1] / (1.3 * wid)) ** 2)
            g = g * (1 - lat + lat * _sstep(uu / wid + 0.5)) * _sstep((W[:, 2] - U[2] - 0.0005 * k) / (0.35 * dz))
            D += (a * g)[:, None] * np.array([0.0, -0.45, -1.0])
    if shape.get("eye_bag"):
        o = _opt(shape["eye_bag"], "amount")
        a, cr = float(o.get("amount", 0.0)) * k, float(o.get("crease", 0.5))
        for lower, corners in (((40, 41), (36, 39)), ((46, 47), (42, 45))):
            Lw = lm[list(lower)].mean(0)
            c0, c1 = lm[corners[0]], lm[corners[1]]
            ex = (c1 - c0) / np.linalg.norm(c1 - c0)
            wid = float(np.linalg.norm(c1 - c0))
            ctr = 0.5 * (c0 + c1)
            q = W - np.array([ctr[0], Lw[1], Lw[2]])
            uu, h, dep = q @ ex, -q[:, 2], q[:, 1]                    # along the eye, down from the lid, depth
            near = _sstep((-N[:, 1] - 0.2) / 0.4) * (np.abs(dep) < 0.02 * k)   # the face's front surface there
            below = _sstep((h - 0.0006 * k) / (0.0015 * k))           # the lid's margin and above stay
            hb = 0.2 * wid * float(o.get("height", 1.0))              # the bag's height under the margin
            along = np.exp(-(uu / (0.42 * wid)) ** 2)
            bag = along * below * np.exp(-((h - 0.5 * hb) / (0.45 * hb)) ** 2) * near
            crease = along * np.exp(-((h - 1.25 * hb) / (0.3 * hb)) ** 2) * near
            D += (a * (bag - cr * crease))[:, None] * N
    if shape.get("lip_bow"):
        o = _opt(shape["lip_bow"], "depth")
        dep, tub = float(o.get("depth", 0.0)) * k, float(o.get("tubercle", 0.0)) * k
        mw = float(np.linalg.norm(lm[54] - lm[48]))
        fr = _sstep((-N[:, 1] - 0.1) / 0.4)                       # the face's front only (not the lips' insides)
        if dep:   # the vermilion border's V: the peaks (50 / 52) up, the dip (51) down, half each
            for i, sg, rad in ((50, 1.0, 0.09), (52, 1.0, 0.09), (51, -1.0, 0.06)):
                q = W - lm[i]
                g = np.exp(-(q[:, 0] / (rad * mw)) ** 2 - (q[:, 2] / (0.09 * mw)) ** 2 - (q[:, 1] / (0.12 * mw)) ** 2)
                D[:, 2] += 0.5 * dep * sg * g * fr
        if tub:   # the tubercle: the upper lip's middle (62) comes down and forward, the lower lip stays
            c = lm[62]
            q = W - c
            above = _sstep((W[:, 2] - lm[66][2]) / max(0.5 * float(lm[62][2] - lm[66][2]), 0.0008 * k))
            g = np.exp(-(q[:, 0] / (0.14 * mw)) ** 2 - (q[:, 2] / (0.08 * mw)) ** 2 - (q[:, 1] / (0.15 * mw)) ** 2) * above
            D += (tub * g)[:, None] * np.array([0.0, -0.5, -1.0])
    if shape.get("lip_roll"):
        o = _opt(shape["lip_roll"], "upper")
        mw = float(np.linalg.norm(lm[54] - lm[48]))
        mxm = 0.5 * float(lm[48][0] + lm[54][0])
        fr = _sstep((-N[:, 1] - 0.1) / 0.4)
        x = W[:, 0]

        def line(ids):
            P_ = lm[list(ids)]
            o_ = np.argsort(P_[:, 0])
            return np.interp(x, P_[o_, 0], P_[o_, 2])
        along = np.exp(-((x - mxm) / (0.42 * mw)) ** 4)          # full over the middle, tucked at the corners
        front = np.abs(W[:, 1] - float(lm[62][1])) < 0.015 * k
        for key, top_ids, bot_ids, peak in (("upper", (48, 49, 50, 51, 52, 53, 54), (48, 60, 61, 62, 63, 64, 54), 0.62),
                                            ("lower", (48, 60, 67, 66, 65, 64, 54), (48, 59, 58, 57, 56, 55, 54), 0.45)):
            a = 1.8 * float(o.get(key, 0.0)) * k                    # (the shared smoothing takes ~half of a narrow bump)
            if not a:
                continue
            zt, zb = line(top_ids), line(bot_ids)
            t = (zt - W[:, 2]) / np.maximum(zt - zb, 1e-4)          # 0 at the vermilion's top edge, 1 at its bottom
            pad = 0.35
            tt = (t + pad) / (1 + 2 * pad)
            bump = np.clip(np.sin(np.pi * np.clip(tt, 0, 1)), 0, None) ** 1.5
            bump = bump * np.exp(-((tt - peak) / 0.45) ** 2)
            D += (a * bump * along * fr * front)[:, None] * np.array([0.0, -1.0, 0.15 if key == "upper" else -0.15])
    if shape.get("cheek_flat"):
        o = _opt(shape["cheek_flat"], "amount")
        a, desc = float(o.get("amount", 0.0)) * k, float(o.get("descend", 0.35))
        w = np.clip(groups["left_infraorbital_region"] + groups["right_infraorbital_region"]
                    + 0.6 * (groups["left_zygomatic_region"] + groups["right_zygomatic_region"]), 0, 1).astype(float)
        for _ in range(8):
            w = w + 0.5 * retopo._lap(w[:, None], E, deg)[:, 0]
        dl = np.min([np.linalg.norm(W - lm[i], axis=1) for i in range(36, 48)], axis=0)
        w = w * _sstep((dl - 0.004 * k) / (0.007 * k)) * (1 - np.clip(groups["nose_region"], 0, 1)) * front
        w = w * _sstep((ax - 0.012 * k) / (0.01 * k))    # the front of the cheek, not the nose's side
        D += (a * w)[:, None] * (-N + desc * down)
    Dl = np.zeros_like(W)
    if shape.get("lips_thin"):
        o = _opt(shape["lips_thin"], "amount")
        a, back = float(np.clip(o.get("amount", 0.0), 0, 0.8)), float(o.get("back", 0.0)) * k
        seam = np.array([lm[48], 0.5 * (lm[61] + lm[67]), 0.5 * (lm[62] + lm[66]), 0.5 * (lm[63] + lm[65]), lm[54]])
        upper = lm[48:55]
        lower = lm[[48, 59, 58, 57, 56, 55, 54]]
        x = W[:, 0]
        srt = lambda P: P[np.argsort(P[:, 0])]
        seam, upper, lower = srt(seam), srt(upper), srt(lower)
        zs, ys = np.interp(x, seam[:, 0], seam[:, 2]), np.interp(x, seam[:, 0], seam[:, 1])
        Hu = np.maximum(np.interp(x, upper[:, 0], upper[:, 2]) - zs, 0.0)
        Hl = np.maximum(zs - np.interp(x, lower[:, 0], lower[:, 2]), 0.0)
        h = W[:, 2] - zs
        fade = LIP_FADE * k
        up_ = h >= 0
        H = np.where(up_, Hu, Hl)
        hh = np.abs(h)
        dz = np.where(hh <= H, a * hh, a * H * np.exp(-(hh - H) / fade))
        gate = (_sstep((x - seam[0, 0]) / (0.004 * k)) * _sstep((seam[-1, 0] - x) / (0.004 * k))
                * np.exp(-(np.maximum(np.abs(W[:, 1] - ys) - 0.012 * k, 0) / (0.006 * k)) ** 2) * (hh < H + 4 * fade))
        Dl[:, 2] = -np.sign(h) * dz * gate
        if back:
            Dl[:, 1] = back * gate * np.exp(-(np.maximum(hh - H, 0) / (0.5 * fade)) ** 2)
    for _ in range(3):
        D = D + 0.5 * retopo._lap(D, E, deg)
    if shape.get("lips_thin"):
        Dl = Dl + 0.5 * retopo._lap(Dl, E, deg)
        D = D + Dl
    lm = lm + D[cKDTree(W).query(lm)[1]]
    return W + D, lm
