"""Style on the one human mesh: macro sliders that reshape the SAME topology (onemesh.py), so a feature-animation,
cartoon, anime or low-poly character keeps the rig, weights, uvs, landmarks and face shapes of the realistic one.

A style is an artistic decision, a bundle (style sheets, stylesheet.py: `styles/human_*.json`); these are the shape
sliders such a bundle sets, under `base.style.human`:

  head (applied on GNM's vertices before the head is placed, faded out at the neck's stitch like the identity):
    head_size      x the head about the top of the neck (1.25 = a feature-animation head, 1.6 = chibi)
    cranium        x the skull above the brows (a big forehead / brain case)
    eye_spacing    + interoculars each eye moves outward;  eye_height: + interoculars each eye moves up (anime: -0.1)
    face_flat      0..1: the front of the face pressed toward a plane (anime; a cel terminator runs clean over it)
    nose           0..1: the nose taken back toward the face (1 = a point);  nose_width: x across
    jaw            0..1: the lower face narrowed toward the chin (a V);  chin: 0..1 the chin narrowed to a point
    cheeks         -1..1: the cheeks fuller (+) or flatter (-)
    mouth          x the mouth's width;  mouth_height: + interoculars up
    exaggerate     x the identity's distance from the mean (1.3 = a caricature of the same person)
  (eye SIZE is base.style.eyes / base.head.eyes, feature simplification base.style.simplify, planes base.style.shape:
  they existed before and work here)
  body (through the base's own skeleton warp: joints move, girths scale, everything bound to them follows):
    legs, arms, torso  x length;  shoulders, hips: x breadth;  hands, feet: x size
    limbs          x thickness of arms and legs;  waist, chest: x girth of the torso's two halves
  NOT sliders yet, tried and failed (round 0): `neck` thickness (the base's girth on the neck -> head bone squeezes the
  HEAD: it needs a head-space op between the stitch and the jaw); `face_flat` past 0.25 (pressing toward a plane
  collapses lids and lips: an anime face wants its features projected onto a smooth proxy, and its own eye part).

Every slider has a RANGE validated on renders (RANGES): outside it the mesh folds or the stitch shows; values are
clamped unless base.style.human.force is set, and `clamped` says what was cut.
"""
from __future__ import annotations

import numpy as np

RANGES = {"head_size": (0.8, 1.8), "cranium": (0.9, 1.35), "eye_spacing": (-0.12, 0.2), "eye_height": (-0.2, 0.12),
          "face_flat": (0.0, 0.25), "nose": (0.0, 0.9), "nose_width": (0.6, 1.3), "jaw": (-0.3, 0.6), "chin": (0.0, 0.7),
          "cheeks": (-0.6, 0.8), "mouth": (0.55, 1.3), "mouth_height": (-0.12, 0.12), "exaggerate": (0.0, 1.8),
          "legs": (0.6, 1.35), "arms": (0.7, 1.25), "torso": (0.75, 1.2), "shoulders": (0.7, 1.35), "hips": (0.7, 1.3),
          "hands": (0.7, 1.5), "feet": (0.7, 1.6), "limbs": (0.6, 1.5), "waist": (0.7, 1.4),
          "chest": (0.75, 1.35)}
NEUTRAL = {k: (0.0 if k in ("eye_spacing", "eye_height", "face_flat", "nose", "jaw", "chin", "cheeks", "mouth_height") else 1.0)
           for k in RANGES}
HEAD = ("head_size", "cranium", "eye_spacing", "eye_height", "face_flat", "nose", "nose_width", "jaw", "chin", "cheeks",
        "mouth", "mouth_height")
BODY = ("legs", "arms", "torso", "shoulders", "hips", "hands", "feet", "limbs", "waist", "chest")


def sliders(base: dict) -> tuple:
    """(values with defaults, {slider: (asked, used)} for what was clamped)."""
    st = dict(((base.get("style") or {}).get("human")) or {})
    force = bool(st.pop("force", False))
    bad = set(st) - set(RANGES)
    if bad:
        raise ValueError(f"base.style.human: unknown {sorted(bad)} (have {', '.join(RANGES)})")
    out, clamped = dict(NEUTRAL), {}
    for k, v in st.items():
        v = float(v)
        lo, hi = RANGES[k]
        u = v if force else float(np.clip(v, lo, hi))
        if u != v:
            clamped[k] = (v, u)
        out[k] = u
    return out, clamped


def active(base: dict, keys) -> dict:
    s, _ = sliders(base)
    return {k: s[k] for k in keys if abs(s[k] - NEUTRAL[k]) > 1e-9}


def _ss(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def head_ops(V, J, st: dict, g: dict, fade, lm_rows) -> tuple:
    """GNM-frame vertices (x left, y up, z forward) and joints after the head sliders. fade: per vertex, 0 at the
    stitch .. 1 on the head; lm_rows: the 68 landmarks as (vertex, weight) rows."""
    V, J = np.array(V, float), np.array(J, float)
    lm = np.array([sum(float(w) * V[int(v)] for v, w in zip(r[0::2], r[1::2])) for r in lm_rows])
    io = float(abs(J[2][0] - J[3][0]))
    f = np.asarray(fade, float)
    G = {k: np.clip(np.asarray(v, float), 0, 1) for k, v in g["groups"].items()}
    eye_y = float(0.5 * (J[2][1] + J[3][1]))
    chin, nose_b = lm[8], lm[33]
    mid_x = float(0.5 * (J[2][0] + J[3][0]))
    moves = []  # (weight per vertex, function of points) so the joints ride the same fields

    def apply(fn, pts=(2, 3)):
        nonlocal V, J
        V = fn(V, True)
        J[list(pts)] = fn(J[list(pts)], False)
    if st.get("cranium", 1.0) != 1.0:
        k = st["cranium"]
        brow_y = float(lm[[19, 24], 1].mean())
        c = np.array([mid_x, brow_y, float(V[f > 0.99][:, 2].mean())])

        def fn(X, isv):
            w = _ss((X[:, 1] - (brow_y - 0.5 * io)) / (2.0 * io)) * (f if isv else 0.0)
            return c + (X - c) * (1 + (k - 1) * np.asarray(w)[:, None])
        apply(fn)
    for key, axis in (("eye_spacing", 0), ("eye_height", 1)):
        if st.get(key, 0.0):
            d = st[key] * io
            cen = J[2:4].copy()

            def fn(X, isv, d=d, axis=axis, cen=cen):
                out = X.copy()
                for j in (0, 1):
                    w = np.exp(-(np.linalg.norm(X - cen[j], axis=1) / (0.42 * io)) ** 2)
                    sgn = (1.0 if cen[j][0] > mid_x else -1.0) if axis == 0 else 1.0
                    out[:, axis] += sgn * d * w
                return out
            apply(fn)
    if st.get("face_flat", 0.0):
        a = st["face_flat"]
        mask = _feather(G["hockey_mask"], g, 14) ** 1.5 * f
        zp = float(np.percentile(V[mask > 0.5][:, 2], 35))  # the plane the face is pressed toward (cheek depth)

        def fn(X, isv):
            if not isv:
                return X
            out = X.copy()
            out[:, 2] = zp + (X[:, 2] - zp) * (1 - a * mask * np.where(X[:, 2] > zp, 1.0, 0.25))
            return out
        apply(fn)
    if st.get("nose", 0.0) or st.get("nose_width", 1.0) != 1.0:
        a, kw = st.get("nose", 0.0), st.get("nose_width", 1.0)
        wn = _feather(G["nose_region"], g, 8)
        zb = float(nose_b[2] - 0.12 * io)

        def fn(X, isv):
            if not isv:
                return X
            out = X.copy()
            out[:, 2] = np.where(X[:, 2] > zb, zb + (X[:, 2] - zb) * (1 - a * wn), X[:, 2])
            out[:, 0] = mid_x + (X[:, 0] - mid_x) * (1 + (kw - 1) * wn)
            return out
        apply(fn)
    if st.get("jaw", 0.0) or st.get("chin", 0.0):
        a, c_ = st.get("jaw", 0.0), st.get("chin", 0.0)
        y_top, y_bot = eye_y - 0.35 * io, float(chin[1])

        def fn(X, isv):
            if not isv:
                return X
            t = _ss((y_top - X[:, 1]) / max(y_top - y_bot, 1e-6))  # 0 at the cheekbones .. 1 at the chin
            below = _ss((X[:, 1] - (y_bot - 0.9 * io)) / (0.5 * io))  # and back to nothing down the neck
            front = _ss((X[:, 2] - (chin[2] - 2.2 * io)) / (0.8 * io))
            w = np.clip(0.6 * a * t + 0.5 * c_ * t ** 3, -0.4, 0.62) * below * front * f
            out = X.copy()
            out[:, 0] = mid_x + (X[:, 0] - mid_x) * (1 - w)
            return out
        apply(fn)
    if st.get("cheeks", 0.0):
        a = st["cheeks"] * 0.12 * io
        wc = _feather(np.clip(G["left_cheek_region"] + G["right_cheek_region"] + 0.6 * (G["left_zygomatic_region"] + G["right_zygomatic_region"]), 0, 1), g, 16)
        N = _normals(V, g)
        V = V + (a * wc * f)[:, None] * N
    if st.get("mouth", 1.0) != 1.0 or st.get("mouth_height", 0.0):
        k, dy = st.get("mouth", 1.0), st.get("mouth_height", 0.0) * io
        mc = 0.5 * (lm[62] + lm[66])

        def fn(X, isv):
            if not isv:
                return X
            w = np.exp(-(np.linalg.norm((X - mc) * [1, 1.6, 0.6], axis=1) / (0.55 * io)) ** 2) * f
            out = X.copy()
            out[:, 0] = mc[0] + (X[:, 0] - mc[0]) * (1 + (k - 1) * w)
            out[:, 1] += dy * w
            return out
        apply(fn)
    if st.get("head_size", 1.0) != 1.0:  # last: everything above scaled about the top of the neck
        k = st["head_size"]
        ring = (f > 0.4) & (f < 0.6)
        pv = V[ring].mean(0) if ring.any() else V[f > 0.99].min(0)

        V = pv + (V - pv) * (1 + (k - 1) * f[:, None])
        J[1:4] = pv + (J[1:4] - pv) * k
    return V, J


def _feather(w, g, rounds):
    """A vertex group smoothed over the mesh (hard-edged regions leave steps)."""
    import scipy.sparse as sp
    key = "_adj"
    if key not in g:
        q = np.asarray(g["quads"])
        e = np.r_[q[:, [0, 1]], q[:, [1, 2]], q[:, [2, 3]], q[:, [3, 0]]]
        n = len(g["template_vertex_positions"])
        A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (n, n)).tocsr()
        A = ((A + A.T) > 0).astype(float)
        deg = np.maximum(np.asarray(A.sum(1)).ravel(), 1)
        g[key] = sp.diags(1 / deg) @ A
    w = np.asarray(w, float)
    for _ in range(int(rounds)):
        w = 0.5 * w + 0.5 * (g[key] @ w)
    return w


def _normals(V, g):
    q = np.asarray(g["quads"])
    n = np.cross(V[q[:, 2]] - V[q[:, 0]], V[q[:, 3]] - V[q[:, 1]])
    out = np.zeros_like(V)
    for k in range(4):
        np.add.at(out, q[:, k], n)
    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)


def body_targets(J: dict, st: dict) -> tuple:
    """(joints after the body sliders, girth {segment start joint: scale}) for the base's skeleton warp."""
    J2 = {k: np.array(v, float) for k, v in J.items()}
    g = lambda k: float(st.get(k, 1.0))  # noqa: E731
    sides = (".L", ".R")

    def shift(names, d):
        for n in names:
            if n in J2:
                J2[n] = J2[n] + d
    arm = lambda s: [f"elbow{s}", f"wrist{s}"] + [n for n in J2 if n.endswith(s) and (n.startswith("finger") or n.startswith("thumb"))]  # noqa: E731
    leg = lambda s: [f"knee{s}", f"ankle{s}", f"toe{s}"]  # noqa: E731
    upper = ["chest", "neck", "head"] + [n for s in sides for n in [f"shoulder{s}"] + arm(s)]
    if g("torso") != 1.0:  # the trunk longer or shorter above the pelvis
        k = g("torso")
        p0 = J2["pelvis"].copy()
        d_chest = (k - 1) * (J2["chest"] - p0) * [0, 0, 1]
        d_neck = (k - 1) * (J2["neck"] - p0) * [0, 0, 1]
        shift(["chest"], d_chest)
        shift([n for n in upper if n != "chest"], d_neck)
    for s in sides:
        sg = 1.0 if s == ".L" else -1.0
        if g("shoulders") != 1.0 and f"shoulder{s}" in J2:
            d = np.array([(g("shoulders") - 1) * J2[f"shoulder{s}"][0], 0, 0])
            shift([f"shoulder{s}"] + arm(s), d)
        if g("hips") != 1.0 and f"hip{s}" in J2:
            d = np.array([(g("hips") - 1) * J2[f"hip{s}"][0], 0, 0])
            shift([f"hip{s}"] + leg(s), d)
        if g("arms") != 1.0 and f"shoulder{s}" in J2:
            k, r = g("arms"), J2[f"shoulder{s}"].copy()
            w_old = J2[f"wrist{s}"].copy()
            for n in (f"elbow{s}", f"wrist{s}"):
                J2[n] = r + k * (J2[n] - r)
            shift([n for n in arm(s) if n not in (f"elbow{s}", f"wrist{s}")], J2[f"wrist{s}"] - w_old)
        if g("hands") != 1.0 and f"wrist{s}" in J2:
            k, r = g("hands"), J2[f"wrist{s}"].copy()
            for n in arm(s)[2:]:
                J2[n] = r + k * (J2[n] - r)
        if g("legs") != 1.0 and f"hip{s}" in J2:
            k, r = g("legs"), J2[f"hip{s}"].copy()
            for n in leg(s):
                J2[n] = r + k * (J2[n] - r)
        if g("feet") != 1.0 and f"ankle{s}" in J2 and f"toe{s}" in J2:
            J2[f"toe{s}"] = J2[f"ankle{s}"] + g("feet") * (J2[f"toe{s}"] - J2[f"ankle{s}"])
        del sg
    lo = min(J2[n][2] for n in J2 if n.startswith("ankle") or n.startswith("toe")) - min(
        np.array(J[n], float)[2] for n in J if n.startswith("ankle") or n.startswith("toe"))
    for n in J2:  # the feet stay on the ground
        J2[n] = J2[n] - [0, 0, lo]
    girth = {}
    for s in sides:
        for a in ("shoulder", "elbow", "hip", "knee"):
            girth[f"{a}{s}"] = g("limbs")
        girth[f"wrist{s}"] = g("hands")
        girth[f"ankle{s}"] = g("feet")
        for n in J2:
            if n.endswith(s) and (n.startswith("finger") or n.startswith("thumb")):
                girth[n] = g("hands")
    girth["pelvis"], girth["chest"] = g("waist"), g("chest")
    girth = {k: v for k, v in girth.items() if abs(v - 1.0) > 1e-9}
    return J2, girth
