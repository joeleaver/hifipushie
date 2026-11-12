"""Warps: the template carried onto a spec's skeleton, the face warp, carry and smoothing away. Part of retopo (retopo.py has the overview)."""
from __future__ import annotations

import numpy as np

from .spec import resolve_point
from . import retopo
from .retopo import (
    _frame, _lap, _model_name, _palm_roots, _seg_dist, _segments, _target_radii, _template_radii, _twist, _unit,
)

# ---------------------------------------------------------------------------------------------------- warps
def _skeleton_warp(P, Jt, s, prims, sigma=0.8, girth=None):
    """Template vertices carried by the skeleton. Radii per angle follow the model's surface (rays onto prims), or,
    with girth ({segment start joint: scale}, for the base mesh: there is no surface yet), the template's own
    scaled (read at the template's own angle: no frame offset). Each bone's rotation by forward kinematics
    (`_body_rotations`; the hand's past the wrist by `_hand_rotations`), a bone ending at a rigid fit twisting into
    it along its length; vertices blend the bones' transforms by distance (sigma x the distance to the nearest bone),
    related bones (a shared joint or fit) over that width, others over FAR_SIGMA of it (base bodies; a wrap keeps
    the full width for all).
    Returns (warped, segments, dominant segment per vertex, apply, model joints)."""
    Jt = dict(Jt)
    Jm = {}
    for k in Jt:  # the model may use the template's names (a base mesh) or the kits' (hand_f<n>_<k>)
        for n in (k, _model_name(k)):
            if n in s["joints"]:
                Jm[k] = resolve_point(s, n)
                break
    for side in "LR":  # the palm: wrist to the middle knuckle (the template's second finger, the model's second
        # or only finger)
        mk = next((n for n in (f"finger2_0.{side}", f"hand_f2_0.{side}", f"hand_f1_0.{side}") if n in s["joints"]), None)
        if f"finger2_0.{side}" in Jt and mk:
            Jt[f"hand_end.{side}"] = Jt[f"finger2_0.{side}"]
            Jm[f"hand_end.{side}"] = resolve_point(s, mk)
        elif f"wrist.{side}" in Jt and f"elbow.{side}" in Jt and f"wrist.{side}" in Jm:
            for J in (Jt, Jm):
                w, e = J[f"wrist.{side}"], J[f"elbow.{side}"]
                J[f"hand_end.{side}"] = w + _unit(w - e) * 0.45 * np.linalg.norm(w - e)
    segs = [sg for sg in _segments(Jt) if sg[0] in Jm and sg[1] in Jm]
    near = np.stack([_seg_dist(P, Jt[a], Jt[b]) for a, b in segs], 1).argmin(1)
    hand = retopo._hand_rotations(Jt, Jm, segs)
    body, fits = retopo._body_rotations(Jt, Jm, segs)
    xf, xh = [], {}
    for k, (a, b) in enumerate(segs):
        a0, b0, a1, b1 = Jt[a], Jt[b], Jm[a], Jm[b]
        u0, u1 = _unit(b0 - a0), _unit(b1 - a1)
        if girth is not None:
            R0 = np.stack([_template_radii(P, a0, b0, near == k, t0) for t0 in retopo.STATIONS])
            R1 = R0 * float(girth.get(a, 1.0))
        elif b.startswith(("hand_end", "toe")):
            prox = [sg for sg in segs if sg[1] == a][0]
            pk = segs.index(prox)
            rw0 = np.median(_template_radii(P, Jt[prox[0]], Jt[prox[1]], near == pk, 0.9))
            rw1 = np.median(_target_radii(prims, Jm[prox[0]], Jm[prox[1]], 0.9))
            R0, R1 = np.full((len(retopo.STATIONS), retopo.NB), rw0), np.full((len(retopo.STATIONS), retopo.NB), rw1)
        else:
            R0 = np.stack([_template_radii(P, a0, b0, near == k, t0) for t0 in retopo.STATIONS])
            R1 = np.stack([_target_radii(prims, a1, b1, t0) for t0 in retopo.STATIONS])
        x1, y1 = _frame(u1)
        x0, y0 = _frame(u0)
        g = dict(a0=a0, u0=u0, a1=a1, u1=u1, sax=np.linalg.norm(b1 - a1) / np.linalg.norm(b0 - a0),
                 L0=np.linalg.norm(b0 - a0), R0=R0, R1=R1, x0=x0, y0=y0, tw=0.0)
        Rb = body[(a, b)]
        # a bone ending where a rigid fit starts (forearm -> palm, spine -> chest) twists along its length from its
        # own (parent-carried) roll to the fit's, so neither joint carries the whole turn
        tw = _twist(Rb, fits[b], u0, u1) if b in fits else 0.0
        for R, into, t_ in ((Rb, None, tw), (hand.get((a, b)), k, 0.0)):
            if R is None:
                continue
            xr = R @ x0
            # R1 is looked up at the point's angle in the target's frame (ang + off; + the twist along the bone),
            # as _target_radii measures it. A girth R1 is the template's own (its frame): no offset, or the radii
            # are read round the bone by the frames' twist (fingers stretched by up to ~15 mm; bodies up to 13 mm
            # asymmetric, as _frame isn't mirror-symmetric)
            off = 0.0 if girth is not None else np.arctan2(xr @ y1, xr @ x1)
            h = dict(g, R=R, off=off, tw=t_)
            if into is None:
                xf.append(h)
            else:
                xh[into] = h
    centres = (np.arange(retopo.NB) + 0.5) / retopo.NB * 2 * np.pi - np.pi
    # where the hand moves as one piece (the FK transforms in xh) instead of by the general per-bone warp: past
    # the template's wrist (ramped over HAND_BLEND along the forearm) and only where the arm's own bones carry the
    # point (the thigh beside a hanging hand keeps the warp: the body stays as it was outside the hands)
    arms = []
    for side in "LR":
        e, w = f"elbow.{side}", f"wrist.{side}"
        mine = [k for k, sg in enumerate(segs) if k in xh and sg[0].endswith(f".{side}")]
        if mine and e in Jt and w in Jt:
            chain = mine + [k for k, sg in enumerate(segs) if sg == (e, w)]
            arms.append((mine, chain, Jt[w], _unit(Jt[w] - Jt[e])))

    def smooth(x):
        x = np.clip(x, 0, 1)
        return x * x * (3 - 2 * x)

    def carry(g, X):
        q = X - g["a0"]
        t = q @ g["u0"]
        rad = q - np.outer(t, g["u0"])
        ang = np.arctan2(rad @ g["y0"], rad @ g["x0"])
        tc = np.clip(t / g["L0"], 0, 1)
        tgt = np.zeros(len(X))
        src = np.zeros(len(X))
        for i in range(len(retopo.STATIONS) - 1):
            lo, hi = retopo.STATIONS[i], retopo.STATIONS[i + 1]
            m = (tc >= lo) & (tc <= hi)
            w = (tc[m] - lo) / (hi - lo)
            ai = (ang[m] + g["off"] + g["tw"] * tc[m] + np.pi) % (2 * np.pi) - np.pi
            tgt[m] = (1 - w) * np.interp(ai, centres, g["R1"][i], period=2 * np.pi) + \
                w * np.interp(ai, centres, g["R1"][i + 1], period=2 * np.pi)
            src[m] = (1 - w) * np.interp(ang[m], centres, g["R0"][i], period=2 * np.pi) + \
                w * np.interp(ang[m], centres, g["R0"][i + 1], period=2 * np.pi)
        rs = np.clip(tgt / np.maximum(src, 1e-3), 0.3, 4.0)
        v = (np.outer(t * g["sax"], g["u0"]) + rad * rs[:, None]) @ g["R"].T
        if g["tw"]:  # the twist along the bone (0 at its start, all of it at its end), about the target axis
            u, phi = g["u1"], g["tw"] * tc
            c, s = np.cos(phi)[:, None], np.sin(phi)[:, None]
            v = v * c + np.cross(u, v) * s + np.outer(v @ u, u) * (1 - c)
        return g["a1"] + v

    # blend only across a joint's own region: bones that share a joint (or a rigid fit: pelvis and hips, the chest,
    # a palm) blend over the full width; any other pair only where their distances are nearly equal. A wide blend
    # between unrelated bones pulled the neck's base with the upper arms, a clavicle with the forearm, an inner
    # thigh with the other leg. The width is chosen by how related each bone is to the softly nearest ones, so the
    # weights stay continuous where the nearest bone changes. Base bodies only: a model's wrap (no girth) is a first
    # guess before projection and its untangling did ~7% worse (more turned faces on goblin/troll) with it
    far = retopo.FAR_SIGMA if girth is not None else 1.0
    # related: a shared joint, or one bone starts at a fit whose root joint (pelvis, chest, wrist) the other has (the
    # thighs relate to the spine, not to each other; the digits to the palm and forearm, not to each other)
    root = {**{j: g for j, g in retopo.FIT_OF.items()}, **{j: f"wrist.{j[-1]}" for s_ in "LR" for j in _palm_roots(s_)}}
    near_ = np.array([[bool(set(p) & set(q)) or root.get(p[0]) in q or root.get(q[0]) in p for q in segs]
                      for p in segs], float)

    def apply(X):
        Dx = np.stack([_seg_dist(X, Jt[a], Jt[b]) for a, b in segs], 1)
        d0 = Dx.min(1, keepdims=True)
        rel = (Dx - d0) / np.maximum(d0, 0.01)
        pk = np.exp(-(rel / retopo.NEAR_SOFT) ** 2)
        sig = sigma * (far + (1 - far) * (pk / pk.sum(1, keepdims=True)) @ near_)
        W = np.exp(-(rel / sig) ** 2)
        W /= W.sum(1, keepdims=True)
        out = np.zeros_like(X)
        for k, g in enumerate(xf):
            out += W[:, k:k + 1] * carry(g, X)
        for mine, chain, w0, ax in arms:
            h = smooth((X - w0) @ ax / retopo.HAND_BLEND) * smooth((W[:, chain].sum(1) - 0.5) / 0.4)
            sel = h > 0
            if not sel.any():
                continue
            # past the wrist: the hand's own bones only (palm and digits, their FK transforms), blended tighter than
            # the body's (HAND_SIGMA) so a re-posed finger bends at its joints. With joints that keep the template's
            # hand pose every one of these transforms is the same rigid motion: the hand moves as one. (The forearm
            # stays out: its minimal arc rolls differently, 4 mm off at the base of the thumb.)
            Xs, D = X[sel], Dx[sel][:, mine]
            dh = D.min(1, keepdims=True)
            Wh = np.exp(-((D - dh) / (retopo.HAND_SIGMA * np.maximum(dh, 0.004))) ** 2)
            Wh /= Wh.sum(1, keepdims=True)
            moved = sum(Wh[:, j:j + 1] * carry(xh[k], Xs) for j, k in enumerate(mine))
            out[sel] += h[sel, None] * (moved - out[sel])
        return out, W

    out, W = apply(P)
    return out, segs, W.argmax(1), apply, Jm


def _face_warp(out, apply, face, s, log, extra=(), names=None):
    """Gaussian RBF: template landmarks (warped by the skeleton) onto the face kit's (or `names`: a base head's
    landmark joints); skull anchors stay."""
    src, dst = [], []
    for name, pt in face["landmarks"].items():
        mn = (names or retopo.FACE_MODEL).get(name)
        if name == "eye.L" and len(extra):  # the eye loops' targets place the eyes (eyeball centres don't agree
            # with them: a goblin's bulging eye sits far forward of a human's)
            continue
        pairs = [(pt, mn)]
        if name.endswith(".L"):
            pairs.append(([-pt[0], pt[1], pt[2]], mn.replace(".L", ".R") if mn else None))
        for p_, m_ in pairs:
            if m_ is None:
                continue
            if m_ in s["joints"]:
                tgt = resolve_point(s, m_)
            elif m_ in s["blobs"]:
                bl = s["blobs"][m_]
                tgt = resolve_point(s, bl.get("at", [0, 0, 0])) + np.array(bl.get("offset", [0, 0, 0]), float)
            else:
                continue
            src.append(p_)
            dst.append(tgt)
    if not src:
        return out
    ws, _ = apply(np.array(src, float))
    disp = np.array(dst) - ws
    if len(extra):  # cut loops' targets (eyes, ears): (warped template points, model points)
        ws = np.r_[ws, np.array([p for p, _ in extra])]
        disp = np.r_[disp, np.array([q - p for p, q in extra])]
        dst = list(dst) + [q for _, q in extra]
    wa, _ = apply(np.array(list(face["anchors"].values()), float))
    C = np.r_[ws, wa]
    Dd = np.r_[disp, np.zeros_like(wa)]
    sig = max(0.6 * np.linalg.norm(ws[0] - ws[1]) if len(ws) > 1 else 0.05, 0.03)
    Phi = np.exp(-(np.linalg.norm(C[:, None] - C[None], axis=2) / sig) ** 2) + 1e-6 * np.eye(len(C))
    wts = np.linalg.solve(Phi, Dd)
    phi = np.exp(-(np.linalg.norm(out[:, None] - C[None], axis=2) / sig) ** 2)
    log.append(f"face: {len(src)} landmarks, largest move {np.linalg.norm(disp, axis=1).max() * 1000:.0f} mm")
    return out + phi @ wts


def _carry(out, loop, dst):
    """Move a loop of the warped template to dst, the surface round it following (Shepard-weighted loop moves,
    fading over about the loop's size)."""
    src = out[loop]
    disp = dst - src
    size = np.linalg.norm(src - src.mean(0), axis=1).max()
    d = np.linalg.norm(out[:, None] - src[None], axis=2)
    w = 1.0 / (d + 1e-4) ** 2
    shep = (w @ disp) / w.sum(1, keepdims=True)
    out = out + np.exp(-(d.min(1) / size) ** 2)[:, None] * shep
    out[loop] = dst
    return out


def _smooth_away(V, E, mask, rounds=40):
    """Smooth a region into a plain form, the rest fixed (toes over a club foot)."""
    deg = np.bincount(E.ravel(), minlength=len(V))
    V = V.copy()
    for _ in range(rounds):
        V[mask] += 0.6 * _lap(V, E, deg)[mask]
    return V
