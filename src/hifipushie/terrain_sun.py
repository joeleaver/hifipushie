"""The sun for a terrain view. Forms read only in side light: a pyramid's arêtes and a cliff's buttresses vanish when
the sun is behind the eye (every face lit alike) and go black against it. "auto" picks, per view, the sun that shows
the ground the view sees best: rays from the eye across the frame find what is visible and how much of the image each
piece fills, and each candidate sun (side light, 45-135 deg off the line of sight, 10-40 deg high) is scored by the
contrast it makes there (between neighbours along each ray: ribs, gullies, arêtes; and overall), with cast shadows,
less when too much of the view is in shadow. A designer's sun is kept, with a note when it's flat or against the eye.

`views[].sun` (or the spec's `"sun"` for every view): "auto" (default), a compass side ("sw") or bearing in degrees
(where the sun is), {"from": side | deg, "height": deg}, or "morning" / "noon" / "evening" (northern hemisphere)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

TIMES = {"morning": (100, 14), "noon": (180, 55), "midday": (180, 55), "evening": (260, 14), "dusk": (275, 7),
         "dawn": (85, 7), "afternoon": (225, 32)}


def _bearing_of(word):
    from .terrain import compass
    if isinstance(word, (int, float)):
        return float(word) % 360
    v = compass(word)
    if v is None:
        raise ValueError(f"sun: {word!r} isn't a compass side, a bearing or one of {sorted(TIMES)} / 'auto'")
    return math.degrees(math.atan2(v[0], v[1])) % 360


def parse(sun):
    """(bearing, height) in degrees, or None for auto."""
    if sun is None or sun == "auto":
        return None
    if isinstance(sun, str) and sun.lower() in TIMES:
        return TIMES[sun.lower()]
    if isinstance(sun, dict):
        t = sun.get("time")
        if t:
            b, h = TIMES[str(t).lower()]
            return (_bearing_of(sun["from"]) if "from" in sun else b), float(sun.get("height", h))
        return _bearing_of(sun.get("from", 225)), float(sun.get("height", 25))
    return _bearing_of(sun), 25.0


def side(b):
    return ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][
        int(round(b / 45)) % 8]


def _vec(b, h):
    b, h = math.radians(b), math.radians(h)
    return np.array([math.cos(h) * math.sin(b), math.cos(h) * math.cos(b), math.sin(h)])


def _seen(T, eye, look, fov, aspect=700 / 1200, rays=81):
    """What the view sees: ground points along rays across the frame, with the share of the image each fills (its
    vertical angle in view), and each point's ray index and order along the ray."""
    ex, ey, ez = eye
    dv = np.array(look[:2]) - np.array(eye[:2])
    va = math.atan2(dv[0], dv[1])
    pitch = math.atan2(look[2] - ez, max(np.linalg.norm(dv), 1.0))
    hf = math.radians(fov) / 2
    vf = math.atan(math.tan(hf) * aspect)
    diag = math.hypot(np.ptp(T.xs), np.ptp(T.ys))
    ds = np.arange(T.cell, diag, T.cell)
    pts, wts, rid, order = [], [], [], []
    for k, a in enumerate(va + np.linspace(-hf, hf, rays)):
        xy = np.c_[ex + ds * math.sin(a), ey + ds * math.cos(a)]
        inside = ((xy[:, 0] >= T.xs[0]) & (xy[:, 0] <= T.xs[-1]) & (xy[:, 1] >= T.ys[0]) & (xy[:, 1] <= T.ys[-1]))
        if not inside.any():
            continue
        n = int(np.nonzero(inside)[0].max()) + 1
        xy, d = xy[:n], ds[:n]
        ang = np.arctan2(T.sample(xy) - ez, d)
        prev = np.maximum.accumulate(np.r_[-np.pi / 2, ang[:-1]])
        lo, hi = np.clip(prev, pitch - vf, pitch + vf), np.clip(ang, pitch - vf, pitch + vf)
        w = np.where(inside[:n] & (ang > prev), np.maximum(hi - lo, 0), 0)
        keep = w > 0
        pts.append(xy[keep]); wts.append(w[keep]); rid.append(np.full(keep.sum(), k)); order.append(np.nonzero(keep)[0])
    if not pts:
        return None
    return np.concatenate(pts), np.concatenate(wts), np.concatenate(rid), np.concatenate(order), math.degrees(va) % 360


def _shade(T, xy, gx, gy, s, lit_only=False):
    n = np.c_[-gx, -gy, np.ones(len(xy))]
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    lam = np.clip(n @ s, 0, 1)
    # cast shadow: march toward the sun (geometric steps out to the frame's size)
    z0 = T.sample(xy) + 0.5
    horiz = math.hypot(s[0], s[1])
    tan = s[2] / max(horiz, 1e-6)
    far = math.hypot(np.ptp(T.xs), np.ptp(T.ys))
    lit = np.ones(len(xy), bool)
    for d in np.geomspace(T.cell, far, 48):
        p = xy + d * np.array([s[0], s[1]]) / max(horiz, 1e-6)
        ok = (p[:, 0] >= T.xs[0]) & (p[:, 0] <= T.xs[-1]) & (p[:, 1] >= T.ys[0]) & (p[:, 1] <= T.ys[-1])
        if not ok.any():
            break
        hit = ok & (T.sample(p) > z0 + d * tan)
        lit &= ~hit
    return lam * lit, lit


def choose(T, eye, look, fov):
    """(bearing, height, note) of the sun that shows this view's relief best."""
    seen = _seen(T, eye, look, fov)
    if seen is None:
        return 225.0, 25.0, "nothing of the ground in view: default sun"
    xy, w, rid, order, va = seen
    if len(xy) > 6000:  # thin evenly along each ray (keeps neighbours for the local contrast)
        keep = np.arange(len(xy)) % math.ceil(len(xy) / 6000) == 0
        xy, w, rid, order = xy[keep], w[keep], rid[keep], order[keep]
    gy, gx = np.gradient(T.H, T.cell)
    coords = [(xy[:, 1] - T.ys[0]) / T.cell, (xy[:, 0] - T.xs[0]) / T.cell]
    px, py = (ndimage.map_coordinates(g, coords, order=1, mode="nearest") for g in (gx, gy))
    nb = (rid[1:] == rid[:-1])  # neighbours along the same ray
    wn = np.minimum(w[1:], w[:-1]) * nb
    best = None
    for off in (-135, -112, -90, -68, -45, 45, 68, 90, 112, 135):
        b = (va + off) % 360
        for h in (12, 20, 30, 40):
            sh, lit = _shade(T, xy, px, py, _vec(b, h))
            W = w.sum()
            mean = (sh * w).sum() / W
            std = math.sqrt(((sh - mean) ** 2 * w).sum() / W)
            local = (np.abs(np.diff(sh)) * wn).sum() / max(wn.sum(), 1e-9)
            dark = ((sh < 0.08) * w).sum() / W  # cast shadow or turned away from the sun
            score = (local * 4 + std) * (1 - 1.5 * max(0.0, dark - 0.3)) * (0.85 + 0.15 * math.sin(math.radians(abs(off))))
            if best is None or score > best[0]:
                best = (score, b, h, dark)
    _, b, h, dark = best
    return b, float(h), (f"sun from the {side(b)} ({b:.0f} deg), {h:.0f} deg high: auto, "
                         f"{abs((b - va + 180) % 360 - 180):.0f} deg off the line of sight, {100 * dark:.0f}% of the view in shadow")


def for_view(T, v, eye, look):
    """(bearing, height, note) for a view: the designer's, else the spec's, else auto."""
    want = v.get("sun", T.spec.get("sun", "auto"))
    fixed = parse(want)
    if fixed is None:
        return choose(T, eye, look, v.get("fov", 60))
    b, h = fixed
    va = math.degrees(math.atan2(look[0] - eye[0], look[1] - eye[1])) % 360
    off = abs((b - va + 180) % 360 - 180)  # 0: the sun ahead (against the eye); 180: behind it
    note = f"sun from the {side(b)} ({b:.0f} deg), {h:.0f} deg high: as asked"
    if off > 135 and h < 60:
        note += ": FLAT LIGHT, the sun is behind the eye (faces lit alike: ridges and buttresses won't read)"
    elif off < 30 and h < 40:
        note += ": against the light (the sun ahead: faces toward the eye in shadow)"
    return b, h, note
