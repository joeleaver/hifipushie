"""Garment kits: a shirt's neckline, collar and front opening (kit type "neckline").

    kits: {"polo": {"type": "neckline", "shirt": "shirt", "part": "collar",
                    "neck": "neck", "head": "head",  # the neck's axis runs neck -> head
                    "flare": 0.006,    # the neckline sits where the neck has widened this much below its narrowest
                    "height": 0.0,     # then moved this far along the axis (+ up)
                    "ease": 0.004,     # gap between the neck's skin and the collar stand
                    "collar": {"stand": 0.028, "stand_front": 0.7 x stand, "fall": stand + 0.008, "points": 0.02,
                               "point": 0.45, "thickness": 0.003, "lean": 0.004, "lift": 0.006, "sink": 0.006,
                               "min_angle": 10} | false,
                    "placket": {"width": 0.026, "buttons": 3, "spacing": 0.05, "first": 0.018,
                                "length": first + (buttons - 1) x spacing + 0.025,
                                "open": 2, "spread": null, "drop": null, "thickness": 0.003,
                                "button": 0.0055, "buttons_part": part} | false}}
The neckline is measured on the body: round the neck, where it flares into the shoulders (low at the front notch,
high at the sides), never dipping behind the sides (a collar rides up the nape). The kit works on any shirt part with
a body under it (garment or plain shell); give the shirt no neck cut of its own.

What it makes (all ordinary blobs, shape "sweep": sdf.sd_sweep):
- `<kit>_hole`: a cut in the shirt part along the neckline (everything above the neckline's surface inside it),
  `<kit>_v`: the front opening cut down to the first closed button, as wide as `spread` (half) at the top, so the
  body shows through it;
- `<kit>`: the collar, a band round the neck from the nape to both front ends (the opening's top corners): the stand
  rises `stand` from the neckline (`stand_front` at the ends), the fall is folded over it `fall` long (+ `points` at
  the ends, reaching forward past them by `point` x its length: the collar points) and hangs as far down toward the
  shirt as it clears it (+ `lift` at the points), found per point round the neck from the shirt's own field;
- `<kit>_strip_l` / `<kit>_strip_r`: the placket's two strips, the wearer's left over the right (men's), each along
  its edge of the opening above the first closed button and down the centre below it, seated on the shirt;
- `<kit>_button<i>` (part `buttons_part`): the closed ones on the centre line, the undone ones on the right strip.
`open` = buttons undone from the top (the opening spreads into a V and the collar's ends follow it: `spread`
defaults to 0.01 + 0.02 x open, `drop` (how far the ends sink below the neckline's plane) to 0.012 x open).
A collarless shirt ("collar": false) still gets the neckline cut (and a placket if asked): a henley or a crew neck.
"""

from __future__ import annotations

import copy

import numpy as np

from .kits import KitError, _euler, _joint, _r, _rot_about, _unit


def _prims(spec: dict, part: str):
    from .spec import compile_prims
    ps = [p for p in compile_prims(spec) if p.part == part]
    if not ps:
        raise KitError(f"neckline: no part {part!r} to seat on")
    return ps


def _march(prims, origin: np.ndarray, dirs: np.ndarray, span: float, what: str, strict: bool = True) -> np.ndarray:
    """Distance along each ray (origin inside) to where the field first turns positive: rays from inside the neck."""
    from . import sdf
    ts = np.linspace(0.0, span, int(span / 0.001) + 1)
    O = np.broadcast_to(origin, dirs.shape) if origin.ndim == 1 else origin
    pts = O[:, None, :] + ts[None, :, None] * dirs[:, None, :]
    f = sdf.field_at(prims, pts.reshape(-1, 3)).reshape(len(dirs), len(ts))
    out = np.empty(len(dirs))
    for i in range(len(dirs)):
        hit = np.flatnonzero(f[i] > 0)
        if not len(hit) or hit[0] == 0:
            if not strict:
                out[i] = np.inf
                continue
            raise KitError(f"neckline: {what}: the ray from {_r(O[i])} along {_r(dirs[i])} never leaves the body "
                           f"(or starts outside it): move `height`")
        a, b = ts[hit[0] - 1], ts[hit[0]]
        fa, fb = f[i, hit[0] - 1], f[i, hit[0]]
        out[i] = a + (b - a) * (-fa) / max(fb - fa, 1e-9)
    return out


def _front_hits(prims, x: np.ndarray, z: np.ndarray, y0: float = -0.6) -> tuple[np.ndarray, np.ndarray]:
    """Points on the surface seen from the front (rays along +y at x, z) and their normals."""
    from . import sdf
    ts = np.linspace(0.0, 0.8, 1601)
    pts = np.stack([np.repeat(x[:, None], len(ts), 1), y0 + np.repeat(ts[None], len(x), 0),
                    np.repeat(z[:, None], len(ts), 1)], -1)
    f = sdf.field_at(prims, pts.reshape(-1, 3)).reshape(len(x), len(ts))
    S = np.empty((len(x), 3))
    for i in range(len(x)):
        hit = np.flatnonzero(f[i] < 0)
        if not len(hit) or hit[0] == 0:
            raise KitError(f"neckline: no shirt in front at x={x[i]:.3f} z={z[i]:.3f}")
        a, b = ts[hit[0] - 1], ts[hit[0]]
        fa, fb = f[i, hit[0] - 1], f[i, hit[0]]
        S[i] = [x[i], y0 + a + (b - a) * fa / max(fa - fb, 1e-9), z[i]]
    g = sdf.gradient(prims, S, 5e-4)
    return S, g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)


def _resample(P: np.ndarray, step: float) -> np.ndarray:
    d = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(d)])
    n = max(int(np.ceil(s[-1] / step)), 2)
    u = np.linspace(0, s[-1], n + 1)
    return np.stack([np.interp(u, s, P[:, k]) for k in range(3)], 1)


def _smooth(A: np.ndarray, sigma: float, keep_ends: bool = True) -> np.ndarray:
    """Gaussian along the rows (sigma in samples), ends held."""
    if sigma <= 0:
        return A
    k = np.arange(-int(3 * sigma), int(3 * sigma) + 1)
    w = np.exp(-0.5 * (k / sigma) ** 2)
    w /= w.sum()
    pad = np.concatenate([np.repeat(A[:1], len(k) // 2, 0), A, np.repeat(A[-1:], len(k) // 2, 0)])
    out = np.stack([np.convolve(pad[:, j], w, mode="valid") for j in range(A.shape[1])], 1) if A.ndim == 2 else \
        np.convolve(pad, w, mode="valid")
    if keep_ends:
        out[0], out[-1] = A[0], A[-1]
    return out


def _tangents(P: np.ndarray) -> np.ndarray:
    T = np.gradient(P, axis=0)
    return T / np.linalg.norm(T, axis=1, keepdims=True)


def _l(A) -> list:
    return [[round(float(v), 5) for v in row] for row in np.asarray(A)]


def neckline(base: dict, name: str, k: dict, o) -> None:
    shirt = k.get("shirt", "shirt")
    part = k.get("part", shirt)
    N0, _ = _joint(base, name, k.get("neck", "neck"))
    H, _ = _joint(base, name, k.get("head", "head"))
    ax = _unit(H - N0)
    ease = float(k.get("ease", 0.004))
    col = k.get("collar", {})
    col = {} if col is True else col
    pk = k.get("placket", {})
    pk = {} if pk is True else pk
    t = float((col or {}).get("thickness", 0.003)) / 2

    # the placket's numbers first: the opening's width sets where the collar ends
    nb = int(pk.get("buttons", 3)) if pk is not False else 0
    nopen = min(int(pk.get("open", 2)), nb) if pk is not False else 0
    spread = float(pk.get("spread", 0.01 + 0.02 * nopen)) if pk is not False else 0.0
    drop = float(pk.get("drop", 0.012 * nopen)) if pk is not False else 0.0

    body = _prims(base, k.get("body", "body"))
    # ---- the neckline: where the neck flares into the shoulders, found per direction round the neck's axis from
    # the nape (theta = pi) to the front (0): the neck's radius r(h) at each height h along the axis; going down from
    # its narrowest, the neckline is where it has grown by `flare` (the base of the neck: high at the sides on the
    # trapezius, low at the front at the notch), dropping by `drop` more toward the open front ends
    e_f = _unit(np.array([0.0, -1.0, 0.0]) - ax * (-ax[1]))
    e_s = _unit(np.cross(ax, e_f))
    if e_s[0] < 0:
        e_s = -e_s
    th = np.linspace(np.pi, 0.0, 91)
    dirs = np.cos(th)[:, None] * e_f + np.sin(th)[:, None] * e_s
    hs_ = np.arange(float(k.get("low", -0.14)), float(k.get("high", 0.06)) + 1e-9, 0.002)
    R = np.array([_march(body, N0 + ax * h, dirs, 0.35, "neck", strict=False) for h in hs_])  # (heights, theta)
    flare = float(k.get("flare", 0.006))
    w = np.clip(1 - th / np.radians(70), 0, 1)
    dz = drop * w * w * (3 - 2 * w)
    hn = np.empty(len(th))
    top = hs_ >= float(k.get("narrow_from", -0.07))  # the narrowest neck is looked for above this
    for i in range(len(th)):
        r = R[:, i]
        imin = int(np.flatnonzero(top)[0] + np.nanargmin(np.where(np.isfinite(r[top]), r[top], np.inf)))
        rmin = r[imin]
        j = imin
        while j > 0 and np.isfinite(r[j - 1]) and r[j - 1] < rmin + flare:
            j -= 1
        if j == 0:
            raise KitError(f"kit {name!r}: the neck doesn't flare within `low` (theta {np.degrees(th[i]):.0f})")
        f = (rmin + flare - r[j]) / max(r[j - 1] - r[j], 1e-9)
        hn[i] = hs_[j] - f * (hs_[j] - hs_[j - 1])
    # behind the sides a collar rides up the neck instead of dipping to the nape (C7 sits lower than the trapezius
    # either side): the neckline never falls behind its highest point coming round from the front
    hn = np.maximum.accumulate(hn[::-1])[::-1]
    hn = _smooth(hn[:, None], 4.0, keep_ends=False)[:, 0] + float(k.get("height", 0.0)) - dz
    rn = np.array([np.interp(hn[i], hs_, np.where(np.isfinite(R[:, i]), R[:, i], 1.0)) for i in range(len(th))])
    rn = _smooth(rn[:, None], 2.0, keep_ends=False)[:, 0]
    rim = N0[None] + ax[None] * hn[:, None] + dirs * (rn + ease + t)[:, None]
    # cut at the opening: the rim ends where it's `spread` off the centre line (never closer than 3 mm)
    x = rim[:, 0]
    xe = max(spread, 0.003)
    if x.min() > xe:
        raise KitError(f"kit {name!r}: the neckline never comes within {xe} m of the centre line")
    im = int(np.argmax(x))
    j = im + int(np.flatnonzero(x[im:] < xe)[0])  # the first sample past the end (coming round from the back)
    f = (x[j - 1] - xe) / max(x[j - 1] - x[j], 1e-9)
    E = rim[j - 1] + f * (rim[j] - rim[j - 1])
    rim = np.concatenate([rim[:j], E[None]])
    rim[0, 0] = 0.0
    rim = _resample(rim, 0.004)
    T = _tangents(rim)
    T[0] = [1.0, 0.0, 0.0] if T[0, 0] > 0 else T[0]
    U = ax[None] - (T @ ax)[:, None] * T
    U /= np.linalg.norm(U, axis=1, keepdims=True)
    Nn = np.cross(T, U)
    Nn *= np.sign((Nn * (rim - N0[None] - ((rim - N0[None]) @ ax)[:, None] * ax[None])).sum(1))[:, None]
    M = len(rim)
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(rim, axis=0), axis=1))])
    fr = s / s[-1]  # 0 at the nape, 1 at the front end

    kb = float(k.get("blend", 0.002))
    sh = _prims(base, shirt)
    # ---- the hole in the shirt: everything above the neckline out to the shirt's own outside there (measured
    # outward from the rim, 2 mm up), so the collar's fall lies on intact shirt, not on a cut shelf
    from . import sdf
    ns = np.linspace(0.0, 0.06, 121)
    Q = (rim + 0.002 * U)[:, None, :] + ns[None, :, None] * Nn[:, None, :]
    fq = sdf.field_at(sh, Q.reshape(-1, 3)).reshape(M, len(ns))
    n1 = np.full(M, 0.006)
    for i in range(M):
        ins = np.flatnonzero(fq[i] < 0)
        if len(ins):  # the shirt's outer face: the end of the first run inside it
            run = ins[0] + int(np.argmax(np.diff(np.concatenate([ins, [10 ** 6]])) > 1))
            n1[i] = max(ns[min(run + 1, len(ns) - 1)], 0.006)
    n1 = _smooth(n1[:, None], 2.0, keep_ends=False)[:, 0] + float(k.get("cut", 0.002))
    o.blob(f"{name}_hole", shape="sweep", path=_l(rim), N=_l(Nn), U=_l(U), profile="band", mirror=True, open_start=True,
           values={"n0": -0.15, "n1": [round(float(v), 5) for v in n1], "u0": -0.002, "u1": 0.15, "round": 0.0},
           op="subtract", part=shirt, blend=kb)

    # ---- the placket and the opening, seated on the shirt as it is without the kit
    Ez = E[2]
    top_z = Ez  # the opening's top corners are the collar's ends
    if pk is not False:
        width = float(pk.get("width", 0.026))
        sp = float(pk.get("spacing", 0.05))
        first = float(pk.get("first", 0.018))
        length = float(pk.get("length", first + (max(nb, 1) - 1) * sp + 0.025))
        th_s = float(pk.get("thickness", 0.003))
        bz = top_z - first - sp * np.arange(nb)  # button heights (along z, on the chest)
        # the opening's bottom: just above the first closed button (the top strip has crossed over to the centre
        # line by the button)
        zv = bz[nopen] + 0.014 if nopen < nb else top_z - length + 0.01
        if nopen == 0:
            zv = top_z - 0.004
        zb = top_z - length
        # the opening's edge: x = spread at the top to 0 at the first closed button
        def edge(z):  # the strips fall open: apart most of the way down, meeting just above the closed button
            u = (z - zv) / max(top_z - zv, 1e-6)
            if u <= 0:
                return 0.0
            return xe * (1 - (1 - u) ** 2) if u < 1 else xe * u  # wider above the neckline: the neck front

        # the V cut: along the centre line from above the neckline down to its bottom, as wide as the edges
        zs = np.linspace(top_z + 0.05, zv, 30)
        C, Cn = _front_hits(sh, np.zeros_like(zs), zs)
        Cp = _smooth(C, 1.5)
        Tc = _tangents(Cp)
        Uc = Cn - (Cn * Tc).sum(1)[:, None] * Tc
        Uc /= np.linalg.norm(Uc, axis=1, keepdims=True)
        Nc = np.cross(Uc, Tc)
        Nc *= np.sign(Nc[:, 0])[:, None]
        wv = np.array([edge(z) for z in zs])
        o.blob(f"{name}_v", shape="sweep", path=_l(Cp), N=_l(Nc), U=_l(Uc), profile="band", mirror=True,
               values={"n0": [-float(v) for v in wv], "n1": [float(v) for v in wv], "u0": -0.05, "u1": 0.05,
                       "round": 0.0}, op="subtract", part=shirt, blend=kb)

        # the strips: the wearer's left (+x) on top, running down its edge, crossing to the centre below
        # the first closed button; the right one under it, mirrored
        for side, sgn, tt in (("l", 1.0, th_s * 1.25), ("r", -1.0, th_s)):
            zz = np.linspace(top_z + 0.004, zb, 40)
            cross = np.clip((zv - zz) / 0.012, 0, 1)
            cross = cross * cross * (3 - 2 * cross)
            xc = sgn * (np.array([edge(z) for z in zz]) + width / 2) * (1 - cross)
            S, Sn = _front_hits(sh, xc, zz)
            S = _smooth(S, 1.0)
            Ts = _tangents(S)
            Us = Sn - (Sn * Ts).sum(1)[:, None] * Ts
            Us /= np.linalg.norm(Us, axis=1, keepdims=True)
            Ns = np.cross(Us, Ts)
            Ns *= np.sign(Ns[:, 0] + 1e-9)[:, None]
            o.blob(f"{name}_strip_{side}", shape="sweep", path=_l(S), N=_l(Ns), U=_l(Us), profile="band",
                   values={"n0": -width / 2, "n1": width / 2, "u0": -0.02, "u1": tt,
                           "round": min(tt * 0.7, 0.002)}, part=part, blend=0.0)
            if side == "l":
                strip_l = (S, Us, tt)
            else:
                strip_r = (S, Us, tt)
        br = float(pk.get("button", 0.0055))
        bpart = pk.get("buttons_part", k.get("buttons_part", part))
        for i, z in enumerate(bz):
            S, Us, tt = strip_l if i >= nopen else strip_r
            jz = int(np.argmin(np.abs(S[:, 2] - z)))
            c = S[jz] + Us[jz] * (tt + 0.001)
            zax = Us[jz]
            xax = _unit(np.cross([0.0, 0.0, 1.0], zax)) if abs(zax[2]) < 0.95 else np.array([1.0, 0, 0])
            R = np.stack([xax, np.cross(zax, xax), zax], 1)
            o.blob(f"{name}_button{i}", shape="cylinder", at=_r(c), size=_r([br, br, 0.0015]), rot=_euler(R),
                   round=0.0012, part=bpart)

    if col is False:
        return
    # ---- the collar
    hs_b = float(col.get("stand", 0.028))
    hs_f = float(col.get("stand_front", 0.7 * hs_b))
    fall = float(col.get("fall", hs_b + 0.008))
    pts_ = float(col.get("points", 0.02))
    lean = float(col.get("lean", 0.004))
    lift = float(col.get("lift", 0.006))
    sink = float(col.get("sink", 0.006))
    front = np.clip((fr - 0.55) / 0.45, 0, 1)
    front = front * front * (3 - 2 * front)
    hs = hs_b + (hs_f - hs_b) * front
    fl = fall + pts_ * front
    # how far the fall swings out: the least angle off the stand at which it clears the shirt (with the hole cut)
    cut = copy.deepcopy(base)
    cut["blobs"] = {**cut.get("blobs", {}), **{n: b for n, b in o.blobs.items() if b.get("op") == "subtract"}}
    shc = _prims(cut, shirt)
    phis = np.radians(np.arange(float(col.get("min_angle", 10.0)), 121.0, 1.5))
    vs = np.linspace(0.3, 1.0, 8)
    need = t + 0.0008 + lift * front
    fx0 = lean + t
    Q = []
    for i in range(M):
        n_ = fx0 + vs[None, :] * fl[i] * np.sin(phis)[:, None]
        u_ = hs[i] - vs[None, :] * fl[i] * np.cos(phis)[:, None]
        Q.append(rim[i] + n_[..., None] * Nn[i] + u_[..., None] * U[i])
    Q = np.array(Q)  # (M, phis, vs, 3)
    fq = sdf.field_at(shc, Q.reshape(-1, 3)).reshape(M, len(phis), len(vs))
    ok = fq.min(2) >= need[:, None]
    phi = np.array([phis[np.flatnonzero(r)[0]] if r.any() else phis[-1] for r in ok])
    # no kinks round the neck: the largest nearby, smoothed
    win = 1
    phi = np.array([phi[max(0, i - win):i + win + 1].max() for i in range(M)])
    phi = _smooth(phi[:, None], 2.0, keep_ends=False)[:, 0]
    # where the shoulders slope away under it (the sides), the fall runs on until it reaches the shirt, up to 1.6 x
    # its length: a short fall hovered over the cut and showed the skin in the hole under it
    ds_ = np.linspace(1.0, 1.6, 25)
    Q = np.array([rim[i] + (fx0 + ds_[:, None] * fl[i] * np.sin(phi[i])) * Nn[i]
                  + (hs[i] - ds_[:, None] * fl[i] * np.cos(phi[i])) * U[i] for i in range(M)])
    fq = sdf.field_at(shc, Q.reshape(-1, 3)).reshape(M, len(ds_))
    reach = np.array([ds_[np.flatnonzero(r < need[i] + 0.002)[0]] if (r < need[i] + 0.002).any() else 1.6
                      for i, r in enumerate(fq)])
    grow = _smooth(np.maximum(reach, 1.0)[:, None], 2.0, keep_ends=False)[:, 0]
    fl = fl * (1 + (grow - 1) * (1 - front))  # not the points: they stand off the chest on purpose (`lift`)
    o.blob(name, shape="sweep", path=_l(rim), N=_l(Nn), U=_l(U), profile="collar", mirror=True, open_start=True,
           values={"t": t, "stand": [round(float(v), 5) for v in hs], "lean": lean,
                   "fall": [round(float(v), 5) for v in fl], "phi": [round(float(v), 4) for v in phi],
                   "sink": sink, "point": float(col.get("point", 0.45))},
           part=part, blend=0.0)
    o.joint(f"{name}_front.L", E, 0.01)
