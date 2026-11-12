"""The tail and escaped pieces. Part of hair flow (hair_flow.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import hair_flow
from .hair_tied import DOWN, _clear, _ss_t, _transport, _unit, _xyz

# ------------------------------------------------------------------------------------------------ the tail
def tail_dir(tp: dict, tl: dict):
    """The direction a tail leaves its tie in: `dir`, else out of the head, a high tie a little up, a low one down."""
    from .hair import dirs
    if tl.get("dir") is not None:
        return _unit(np.asarray(tl["dir"], float))
    az, el = tp["at"]
    return _unit(dirs(az, el) + hair_flow.Z * 0.8 * (float(el) / 90.0 - 0.06))


def _push(sc, col, P, gap):
    P = np.asarray(P, float)
    if col is not None:
        return col.push(P, gap)
    return _clear(sc, P, gap)


def tail(sc, tp: dict, tl: dict, rng, col, pre: str, P0) -> dict:
    """A tail that hangs: {name: lock} ("xyz" locks with the bundle's own mean line as `core`)."""
    d0 = tail_dir(tp, tl)
    n = int(tl["locks"])
    L, full, un = float(tl["length"]), float(tl["fullness"]), float(tl["uneven"])
    e1 = np.cross(d0, hair_flow.Z)
    e1 = _unit(e1 if np.linalg.norm(e1) > 0.2 else np.cross(d0, hair_flow.X))
    e2 = np.cross(d0, e1)
    r_tie = min(0.012, full * 0.4)
    kk = (1 - float(tl["stiff"])) ** 2 * 45.0 * (1 + 0.3 * rng.uniform(-1, 1, n))  # the direction's fall, per metre
    ks = np.arange(n)
    th, rho = ks * 2.39996, np.sqrt((ks + 0.5) / n)
    rad = np.cos(th)[:, None] * e1 + np.sin(th)[:, None] * e2
    ln = 1 - un * rng.uniform(0, 0.6, n)
    if float(tl.get("bulge", 0.0)) > 0:  # (a lock 40% short ends as a blunt chunk in the middle of a full tail)
        ln = 1 - un * rng.uniform(0, 1, n) ** 1.5 * 0.4
    rag = float(np.clip(tl.get("ragged", 0.0), 0, 1))
    # soft (tesshair6): the tousle as IRREGULARITY OF SOFT LOCKS. Round five's tousle made every lock a pointed wisp
    # that flicked out (stiff straw kicking backwards, th_T56); a tousled tail is the brushed one's hang (th_T48) with
    # some locks loosened out of the bundle, lengths that differ, open soft ends and long single hairs round it
    soft = float(np.clip(tl.get("soft", 0.0), 0, 1))
    if rag > 0:
        # a RAGGED end: the locks end anywhere over the last third (the outer ones no shorter than the inner: the
        # outline itself must be uneven), each narrowing to a point; `uneven` alone moved a few locks a little and
        # the end stayed one straight cut (th_T48 from behind)
        # (soft: over the last half, and more of them long than short: a soft ragged end, no straight cut)
        ln = np.minimum(ln, 1 - rag * (0.35 + 0.2 * soft) * rng.uniform(0, 1, n) ** (1 + 0.6 * soft))
    ns = 20
    bulge = float(tl.get("bulge", 0.0))
    lwave = float(tl.get("lock_wave", 0.0))
    if lwave > 0:  # (a wave needs points: ~8 a wavelength)
        ns = int(np.clip(2 * np.ceil(4 * L / max(float(tl.get("lock_wavelength", 0.08)), 0.02)), 20, 48))
    ds = L * ln / ns
    d = d0[None] + float(tl["spread"]) * rho[:, None] * rad
    from .hair import dirs
    out = dirs(*tp["at"])
    inw = np.minimum(d @ out - float(d0 @ out), 0.0)  # (no lock leaves the tie INTO the head: it lay over the crown)
    d = _unit(d - 0.8 * inw[:, None] * out[None])
    gap = 0.004 + 0.5 * full * rng.uniform(0, 1, n)  # (lying on a shoulder the bundle keeps its thickness)
    P = P0 + (r_tie * rho)[:, None] * rad
    pts = [P]
    for _ in range(ns):
        d = _unit(d + (kk * ds)[:, None] * DOWN)
        q = _push(sc, col, P + ds[:, None] * d, gap)
        d = _unit(q - P)
        P = P + ds[:, None] * d
        pts.append(P)
    Q = np.stack(pts, 1)  # (n, ns + 1, 3)
    sk = np.linspace(0, 1, ns + 1)[None] * (L * ln)[:, None]  # each lock's length along itself
    # the bundle's own line (the mean of the locks that reach each length) and its radius -> scaled to `fullness`
    S = np.linspace(0, L, 28)
    reach = S[None] <= (L * ln)[:, None] + 1e-9
    R = np.stack([np.stack([np.interp(S, sk[i], Q[i, :, j]) for j in range(3)], 1) for i in range(n)])
    cnt = np.maximum(reach.sum(0), 1)
    K = (R * reach[..., None]).sum(0) / cnt[:, None]
    last = int(np.nonzero(reach.sum(0) >= min(3, n))[0][-1])
    K[last + 1:] = K[last] + (S[last + 1:] - S[last])[:, None] * _unit(K[last] - K[max(last - 1, 0)])
    off = R - K[None]
    rms = np.sqrt(((off ** 2).sum(-1) * reach).sum(0) / cnt)
    scale = float(np.clip(full / max(1.41 * float(rms[:last + 1].max()), 1e-4), 0.4, 3.0))
    scs = None
    if bulge > 0:
        # VOLUME as the bundle's own property (tesshair4; Joe: "poofed up the ponytail a bit"): the radius is SET
        # along the tail instead of one factor on whatever the fall gave (a cone that closes to parallel strings):
        # out of the band it opens at once (the bulge: full by ~5 cm), stays full, and draws in a little to the end
        tb = float(np.clip(0.05 / max(L, 1e-6), 0.12, 0.4))
        tS = S / max(L, 1e-6)
        prof = (0.25 + 0.75 * _ss_t(tS / tb) ** 0.7) * (1 - float(tl["taper"]) * np.clip((tS - tb) / (1 - tb), 0, 1) ** 2)
        prof = prof * (1 + 0.12 * np.exp(-((tS - 1.6 * tb) / (0.9 * tb)) ** 2))
        if rag > 0:  # (... and opens as a FAN out of the band, full by ~9 cm: full at 5 with a swell right after, the
            # bundle stood over the tie as a lump and hid it from behind)
            # (soft: full by 6.5 cm and a little fuller below: at 9 cm with pointed locks the tail read short and thin)
            tb = float(np.clip((0.09 - 0.025 * soft) / max(L, 1e-6), 0.2, 0.5))
            prof = (0.18 + 0.82 * _ss_t(tS / tb) ** 0.9) * (1 - float(tl["taper"]) * np.clip((tS - tb) / (1 - tb), 0, 1) ** 2)
            prof = prof * (1 + 0.1 * soft * np.exp(-((tS - 0.6) / 0.25) ** 2))
        want = full / 1.41 * prof
        scs = np.clip(want / np.maximum(rms, 1e-4), 0.3, 4.0)
        scs[last + 1:] = scs[last]
        for _ in range(3):
            scs[1:-1] = 0.25 * scs[:-2] + 0.5 * scs[1:-1] + 0.25 * scs[2:]
    T, E1, E2 = _transport(K)
    sway, lam = float(tl.get("sway", 0.0)), max(float(tl.get("sway_length", 0.16)), 0.02)
    ph0 = rng.uniform(0, 2 * np.pi)
    fl = float(tl.get("flick", 0.0))
    core = None
    locks = {}
    Kc = K.copy()
    if sway > 0:  # the whole bundle swings: one slow S, every lock with it
        env = _ss_t(S / 0.05)
        Kc = K + (sway * env * np.sin(2 * np.pi * S / lam + ph0))[:, None] * E1 \
            + (0.5 * sway * env * np.sin(2 * np.pi * S / (lam * 1.37) + ph0 + 1.3))[:, None] * E2
    core = _xyz(sc, Kc[::2])
    step_ = float(np.clip(tl.get("in_step", 0.0), 0, 1))
    wq = None
    if step_ > 0:  # (the direction across the bundle the shared wave's phase runs in, and its phase)
        wq = rng.uniform(0, 2 * np.pi, 2)
        wq = (float(np.cos(wq[0])), float(np.sin(wq[0])), float(wq[1]))
    soft_rng = np.random.default_rng(int(rng.integers(0, 2 ** 31)) if soft > 0 else 0)  # (its own stream: soft 0 = as before)
    up_k = hair_flow.Z[None] - (T @ hair_flow.Z)[:, None] * T  # "up" across the bundle's own line
    up_k = _unit(up_k + 1e-9)
    kept = []
    for i in range(n):
        tt = sk[i] / L
        Ki = np.stack([np.interp(sk[i], S, K[:, j]) for j in range(3)], 1)
        Kci = np.stack([np.interp(sk[i], S, Kc[:, j]) for j in range(3)], 1)
        o = Q[i] - Ki
        if rag > 0:
            # nothing rises over the tie: a lock's offset ABOVE the bundle's line comes in over the first 12 cm (the
            # tail leaves the band as a fan that opens downward and to the sides; the band shows from behind)
            upi = np.stack([np.interp(sk[i], S, up_k[:, j]) for j in range(3)], 1)
            o = o - (np.maximum((o * upi).sum(1), 0.0) * 0.6 * (1 - _ss_t(sk[i] / 0.12)))[:, None] * upi
        if scs is not None:
            f = np.interp(sk[i], S, scs)
        else:
            f = (1 + (scale - 1) * _ss_t(sk[i] / 0.04)) * (1 - float(tl["taper"]) * tt ** 2)
        Pk = Kci + o * f[:, None]
        Pk = Pk + (un * 0.012 + float(tl.get("air", 0.0))) * rng.normal(0, 1, 3)[None] * (tt ** 1.5)[:, None]  # (each lock a little its own way)
        loosened = soft > 0 and soft_rng.uniform() < 0.3 * soft + 0.1
        if loosened:
            # a loosened lock: out of the bundle to one side (its own, across the tail's line) more and more toward
            # its end, sagging a little: what makes an outline irregular without a single stiff piece
            oi = _unit(o[-1] - (o[-1] @ T[-1]) * T[-1] + 1e-6 * soft_rng.normal(0, 1, 3))
            dr = _unit(oi + 0.8 * soft_rng.normal(0, 1, 3))
            Pk = Pk + ((0.01 + 0.022 * soft) * soft_rng.uniform(0.5, 1.3) * tt ** 1.6)[:, None] * dr[None] \
                + (0.012 * soft * tt ** 2)[:, None] * DOWN[None]
        if lwave > 0:
            # every lock waves ON ITS OWN: its own amplitude, wavelength, phase and plane (slowly turning: a loose
            # wave is a lazy helix, not a zigzag in one plane). The strand dials' wave keeps neighbours in step (a
            # tail that swings as one sheet); a poof is locks out of step with air between them
            e1i = np.stack([np.interp(sk[i], S, E1[:, j]) for j in range(3)], 1)
            e2i = np.stack([np.interp(sk[i], S, E2[:, j]) for j in range(3)], 1)
            lam_i = max(float(tl.get("lock_wavelength", 0.08)), 0.02) * rng.uniform(0.75, 1.3)
            a_i = lwave * rng.uniform(0.45, 1.35) * (1.35 if loosened else 1.0)
            psi = rng.uniform(0, 2 * np.pi) + rng.uniform(-1.2, 1.2) * tt
            ph_i = 2 * np.pi * sk[i] / lam_i + rng.uniform(0, 2 * np.pi)
            if wq is not None:
                # neighbours wave TOGETHER: one wave runs through the bundle (its phase by where the lock sits in the
                # section, its plane shared), each lock off it by (1 - in_step). Every lock on its own phase, plane
                # and length, a full tail was a bunch of ropes from behind (th_T48); hers moves as soft sheets
                lam_i = max(float(tl.get("lock_wavelength", 0.08)), 0.02) * (1 + (1 - step_) * (lam_i / max(float(tl.get("lock_wavelength", 0.08)), 0.02) - 1))
                x_, y_ = rho[i] * np.cos(th[i]), rho[i] * np.sin(th[i])
                ph_s = 2 * np.pi * sk[i] / lam_i + wq[2] + 2.2 * (wq[0] * x_ + wq[1] * y_)
                ph_i = ph_s + (1 - step_) * (ph_i - 2 * np.pi * sk[i] / lam_i)
                psi = step_ * (np.arctan2(wq[1], wq[0]) + 0.6 * tt) + (1 - step_) * psi
            wv = a_i * _ss_t(sk[i] / 0.05) * (0.7 + 0.5 * tt)
            Pk = Pk + (wv * np.sin(ph_i))[:, None] * (np.cos(psi)[:, None] * e1i + np.sin(psi)[:, None] * e2i) \
                + ((0.45 + 0.4 * step_) * wv * np.cos(ph_i))[:, None] * (-np.sin(psi)[:, None] * e1i + np.cos(psi)[:, None] * e2i)
            # (in step the swing is nearly round, a lazy helix: one shared plane showed its waves from one side and a
            # straight broom from the other, th_T52)
        if fl > 0:  # the lock's end turns out of the bundle (and a little up): a flicked tip, each its own
            Pk = Pk + (fl * rng.uniform(0.3, 1.0) * (0.3 + rho[i]) * _ss_t((sk[i] / (L * ln[i]) - 0.6) / 0.4) ** 2)[:, None] \
                * (_unit(o + 1e-9) + [0.0, 0.0, 0.35])
        Pk[1:] = _push(sc, col, Pk[1:], 0.004)
        Pk[0] = P0 + 0.5 * (Pk[0] - P0)
        kept.append(Pk)
        w = full * 2.2 / np.sqrt(max(n, 1)) * (1 + un * rng.uniform(-0.25, 0.35))
        if bulge > 0:  # wide locks that stay open to their ends (thin ones that taper to a point are strings: th_W1)
            # (and into each other: at 3 x full / sqrt(n) with air between them a full tail was a bunch of ropes)
            # (soft: wider still, 6 x: neighbours' strands interleave and the tail is one mass of hair, not ribbons)
            w = max(full * (4.5 + 1.5 * soft) / np.sqrt(max(n, 1)), 0.022) * (1 + un * rng.uniform(-0.25, 0.35))
        fine = bulge > 0 or lwave > 0
        locks[f"{pre}t{i}"] = {"tier": "tie", "space": "xyz", "pts": _xyz(sc, Pk if fine else Pk[::2] if ns % 2 == 0 else Pk),
                              "core": core, "free": 1.0, "width": round(float(max(w, 0.012)), 4), "thickness": 0.005,
                              "taper": (0.35 + 0.2 * rag * (1 - soft)) if bulge > 0 else 0.9, "belly": 0.4, "root": 0.5, "cup": 0.0,
                              # (a lock that keeps one flat side out all the way down is a plank: each turns on its way;
                              # in step they turn less: a ribbon wound 200 deg is a rope)
                              **({"twist": round(float(rng.uniform(60, 220) * (1 - 0.6 * step_) * rng.choice([-1, 1])), 1),
                                  "flip": round(float(rng.uniform(-90, 90)), 1)} if bulge > 0 else {}),
                              **({"strands": {**tl["strands"], **({"sun": round(float(rho[i]) - 0.5, 3)} if tl.get("sun_out") else {})}}
                                 if tl.get("strands") else {})}
    # STRAYS: single hairs and thin wisps that leave the tail's outline (hers: all round it, and out of its end). Each
    # rides a lock for a stretch, then lets go: out of the bundle, on its own slow curl, falling a little
    for j in range(int(tl.get("strays") or 0)):
        i = int(rng.integers(0, n))
        Pk = kept[i]
        m_ = len(Pk)
        a_ = int(rng.uniform(0.08, 0.75) * (m_ - 1))
        seg_ = float(np.linalg.norm(Pk[min(a_ + 1, m_ - 1)] - Pk[a_])) or L / m_
        sl0, sl1 = tl.get("stray_length") or (0.03, 0.09)
        ln_ = rng.uniform(float(sl0), float(sl1))
        thin_lock = soft > 0 and rng.uniform() < 0.22  # (not only single hairs: a few thin soft locks leave it too)
        k_ = int(np.clip(round(ln_ / seg_), 4, 40))
        ride = int(rng.integers(1, 4))
        Ki = np.stack([np.interp(sk[i][a_], S, K[:, c_]) for c_ in range(3)])
        outw = _unit(Pk[a_] - Ki + 1e-6 * rng.normal(0, 1, 3))
        d_ = _unit(Pk[min(a_ + 1, m_ - 1)] - Pk[a_] + 1e-9)
        ax = _unit(rng.normal(0, 1, 3))
        cu_ = rng.uniform(4.0, 16.0) * (1 + 0.8 * soft)  # rad / m (soft: curlier; a long stray with a slow bend is a wire)
        cu_w, cu_p = rng.uniform(25.0, 60.0), rng.uniform(0, 2 * np.pi)  # (... and its curl comes and goes along it)
        go = rng.uniform(0.25, 0.9)
        B = [Pk[a_] + 0.5 * w * rng.uniform(-0.4, 0.4) * outw]
        for q_ in range(k_):
            if q_ < ride and a_ + q_ + 1 < m_:
                d_ = _unit(Pk[a_ + q_ + 1] - Pk[a_ + q_])
            else:
                # (out of the bundle only a little a step, and falling: pushed out hard they were straight wires
                # standing 8 cm off the tail, th_T52)
                cq = cu_ * (1.0 + soft * np.sin(cu_w * q_ * seg_ + cu_p)) if soft > 0 else cu_
                d_ = _unit(d_ + seg_ * (go * (3.5 - 1.5 * soft) * outw + cq * np.cross(ax, d_) + 5.0 * DOWN))
            B.append(B[-1] + seg_ * d_)
        B = np.asarray(B)
        B[1:] = _push(sc, col, B[1:], 0.004)
        locks[f"{pre}y{j}"] = {"tier": "tie", "space": "xyz", "pts": _xyz(sc, B), "free": 1.0,
                                "width": round(float(rng.uniform(0.004, 0.009) if thin_lock else rng.uniform(0.001, 0.004)), 4),
                                "thickness": 0.002, "taper": 0.5,
                                "belly": 0.35, "root": 0.6, "cup": 0.0,
                                "hairs": int(rng.integers(7, 16)) if thin_lock else int(rng.integers(1, 5)),
                                "strands": {"wisp_fan": 1.5, "wisp_round": 0.8, "tip_loss": 0.5,
                                            "wave": round(0.004 + 0.005 * soft, 4), "wavelength": 0.07 - 0.025 * soft,
                                            "random": 1.0, "flat": 1.0, "curl": 0.0}}
    return locks


# ------------------------------------------------------------------------------------------------ escaped pieces
def escaped(sc, tp: dict, es: dict, line, rng, col, pre: str) -> dict:
    """Pieces that never reached the tie: each a few SINGLE hairs that share one fall and fray apart toward their
    ends (parallel hairs are a comb strip, lone ones wires): {name: lock} ("xyz" locks with `hairs`)."""
    from .hair import dirs
    from .hair_groom import _line_at, inside
    from .hair_tied import ESCAPED_AT, ESCAPED_STRANDS
    cnt = es["count"] if isinstance(es["count"], (list, tuple)) else [es["count"]] * 2
    cnt = [int(c) for c in cnt]  # [right, left]
    where = [w for w in (es.get("where") or ["temple"])]
    bad = set(where) - set(ESCAPED_AT)
    if bad:
        raise ValueError(f"hair tie escaped.where: unknown {sorted(bad)} (have {', '.join(ESCAPED_AT)})")
    l0, l1 = es["length"]
    h0, h1 = es["hairs"] if isinstance(es["hairs"], (list, tuple)) else (1, es["hairs"])
    cv = float(es["curve"])
    locks = {}
    k = 0
    for side, ns in ((-1, cnt[0]), (1, cnt[1])):
        for j in range(ns):
            zone = where[j % len(where)]
            a0, a1 = ESCAPED_AT[zone]
            az = (side * rng.uniform(a0, a1)) % 360
            el = float(_line_at(line, az)) + 3.0
            for _ in range(8):  # rooted IN the hair, a good 6 mm inside the line
                if float(inside(sc, line, az, el)) >= 0.006:
                    break
                el += 3.0
            p = sc.point(az, el, 0.003)
            out = dirs(az, el)
            ln = l0 + (l1 - l0) * rng.uniform(0, 1) ** 1.3
            # out of the hairline a little (forward of the ear at the face), then down: beside the cheek, on the neck
            tie_d = dirs(*tp["at"])
            to = tie_d - (tie_d @ out) * out
            to[2] = min(to[2], 0.0)  # (toward a HIGH tie they stood up and out of the temples like antennae)
            to = _unit(to + 1e-9)
            d0 = _unit(out * 0.25 + (DOWN if zone == "nape" else 0.45 * to + 0.35 * DOWN))
            eo = _unit(np.array([out[0], out[1], 0.0]))
            esd = np.array([-eo[1], eo[0], 0.0])
            u = np.linspace(0, 1, 17)
            nh = int(rng.integers(int(h0), int(h1) + 1))
            for q_ in range(nh):
                # its hairs: one root, but each FALLS on its own (its own first direction, stiffness and length), bows
                # in its own plane and waves on its own: sharing one fall they were a bundle of parallel wires
                # standing off the temple like whiskers (Tess, 2026-10-11)
                d = _unit(d0 + 0.45 * rng.normal(0, 1, 3) * np.array([1.0, 1.0, 0.5]))
                fall = rng.uniform(0.25, 0.75)
                lq = ln * rng.uniform(0.45, 1.0)
                B = [p + 0.002 * rng.normal(0, 1, 3)]
                for _ in range(10):
                    d = _unit(d + fall * DOWN)
                    B.append(_push(sc, col, (B[-1] + d * lq / 10)[None], 0.004)[0])
                B = np.asarray(B)
                sl = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(B, axis=0), axis=1))]
                Bq = np.stack([np.interp(u * sl[-1], sl, B[:, c_]) for c_ in range(3)], 1)
                a2 = rng.uniform(0, 2 * np.pi)
                e2 = np.cos(a2) * eo + np.sin(a2) * esd + 0.3 * rng.uniform(-1, 1) * hair_flow.Z
                bow = cv * lq * rng.uniform(0.2, 1.0)
                kq, phq = rng.uniform(0.6, 1.6), rng.uniform(0, 2 * np.pi)
                amp = cv * lq * rng.uniform(0.1, 0.4)
                Pq = Bq + (bow * np.sin(np.pi * u ** 0.8))[:, None] * e2 \
                    + (amp * u * np.sin(2 * np.pi * kq * u + phq))[:, None] * np.cross(e2, hair_flow.Z)
                Pq[1:] = _push(sc, col, Pq[1:], 0.003)
                locks[f"{pre}e{k}_{q_}"] = {
                    "tier": "tie", "space": "xyz", "pts": _xyz(sc, Pq), "free": 1.0,
                    "width": round(float(rng.uniform(0.001, 0.003)), 4), "thickness": 0.002, "taper": 0.5,
                    "belly": 0.35, "root": 0.6, "cup": 0.0, "hairs": int(rng.integers(1, 3)),
                    "strands": {**ESCAPED_STRANDS, "wave": float(es["wave"]), "wavelength": float(es["wavelength"]),
                                **(es.get("strands") or {})}}
            k += 1
    return locks
