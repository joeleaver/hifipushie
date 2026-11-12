"""Wisps, curls and the halo. Part of hair flow (hair_flow.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import hair_flow
from .hair_tied import DOWN, _ss_t, _transport, _unit, _xyz
from .hair_flow import _wrap
from .hair_flow_tail import _push

# ------------------------------------------------------------------------------------------------ wisps
def _surface(sc, col, P):
    """(distance to the head / body, its outward unit normal) at points P."""
    from .hair import dirs
    P = np.asarray(P, float)
    if col is not None:
        return np.asarray(col.at(P), float), np.asarray(col.grad(P), float)
    az, el, h = sc.coords(P)
    return h, dirs(az, el)


def wisps(sc, tp: dict, ws: dict, line, rng, col, pre: str) -> dict:
    """WISPS (tesshair4; Joe on the sleek low ponytail: "almost right for tess, if you added front wispies"): the short
    soft hair that never reached the tie, as small CLUMPS. A clump is one lock of `hairs` single fine strands (the
    wisp object: part transparent) that share one curve, fan a little, end one by one (a taper) and frizz slightly.
    Its line is rooted in the hair at the hairline (zones: part, front, temple, sideburn, nape) and FALLS ALONG THE
    SKIN: at every step the direction turns to gravity in the surface's tangent plane with a slow sideways curl, it
    may not lift off the surface while it is near it, and where the surface falls away under it (past the cheekbone,
    under the jaw) it hangs. Some (`tuck`) are drawn back toward the tie instead and droop over the ear's top.
    {name: lock} ("xyz" locks with `hairs`).

    Round three's escaped pieces were 1-2 hairs each on their own way, started 14 deg off the surface and bowed in
    random planes: stiff wires standing off the forehead (th_W1)."""
    from .hair import dirs
    from .hair_groom import _line_at, inside
    from .hair_tied import WISP_AT
    cnt = ws["count"] if isinstance(ws["count"], (list, tuple)) else [ws["count"]] * 2
    cnt = [int(c) for c in cnt]  # [right, left]
    where = [("sideburn" if w == "ear" else w) for w in (ws.get("where") or ["temple"])]
    bad = set(where) - set(WISP_AT)
    if bad:
        raise ValueError(f"hair tie wisps.where: unknown {sorted(bad)} (have {', '.join(WISP_AT)})")
    l0, l1 = ws["length"]
    h0, h1 = ws["hairs"]
    soft = float(np.clip(ws["softness"], 0, 1))
    tuck = float(np.clip(ws["tuck"], 0, 1))
    over = float(ws.get("over", 0.008))  # m the gathered hair stands over the scalp: tucked wisps lie on it
    tie_d = dirs(*tp["at"])
    locks = {}
    k = 0
    # VARIETY (tesshair5: "not all long thin strands fanning from the temple"): besides the soft clumps ("soft"),
    #   "baby": the hairline's own short fine hair, 1-4 cm, a few hairs each, rooted ON the line and a little outside
    #       it all the way from the part to the sideburn: half lie back the way the hair was combed and end in it (the
    #       edge thins out instead of stopping), half let go and droop along the skin;
    #   "loose": a few THICK locks (30-70 hairs, 7-13 mm, 9-16 cm) out of the forehead's corner and the temple that
    #       sweep out and hang in front of the ear with one slow curve.
    jobs = [(side, where[j % len(where)], "soft") for side, ns in ((-1, cnt[0]), (1, cnt[1])) for j in range(ns)]
    n_b, n_l = ws.get("baby") or 0, ws.get("loose") or 0
    #   "swoop" (tesshair6): the LOOSENED FRONT LOCK: thick, rooted beside the part, it falls out along the hairline
    #       over the forehead's corner (below the line by `drape`), down past the brow's tail, and is then drawn back
    #       over the temple toward the tie: what a held-back front shows from the FRONT (th_T56's loose locks lay
    #       back over the temple from their roots and hardly showed)
    n_s = ws.get("swoop") or 0
    n_s = [int(c) for c in (n_s if isinstance(n_s, (list, tuple)) else [n_s] * 2)]
    drape = float(np.clip(ws.get("drape", 0.5), 0, 1))
    n_b = [int(c) for c in (n_b if isinstance(n_b, (list, tuple)) else [n_b] * 2)]
    n_l = [int(c) for c in (n_l if isinstance(n_l, (list, tuple)) else [n_l] * 2)]
    bz = [z for z in ("part", "front", "temple", "sideburn") if z in where] or ["front", "temple"]
    for si, side in enumerate((-1, 1)):
        jobs += [(side, "front" if j % 2 == 0 else "temple", "loose") for j in range(n_l[si])]
        jobs += [(side, None, "baby") for j in range(n_b[si])]
        jobs += [(side, "front", "swoop") for j in range(n_s[si])]
    lo_b, hi_b = min(WISP_AT[z][0] for z in bz), max(WISP_AT[z][1] for z in bz)
    if "part" in bz:
        lo_b = 0.0  # (the hairline under the part itself: the notch between the banks)
    for side, zone, kind in jobs:
        if True:
            m = 12 if kind == "baby" else 28
            if kind == "baby":  # anywhere along the line, by its length
                az_w = lo_b + (hi_b - lo_b) * rng.uniform(0, 1)
                zone = next((z for z in bz if WISP_AT[z][0] <= az_w <= WISP_AT[z][1]), "front" if az_w < 44 else "temple")
                az = (side * az_w) % 360
                el = float(_line_at(line, az)) + rng.uniform(-1.5, 2.5)
                want = rng.uniform(-0.003, 0.005)
            else:
                a0, a1 = WISP_AT[zone]
                if kind == "loose":
                    a0, a1 = (20.0, 40.0) if zone == "front" else (40.0, 58.0)
                elif kind == "swoop":
                    a0, a1 = 5.0, 30.0
                az = (side * (a0 + (a1 - a0) * rng.uniform(0, 1))) % 360
                el = float(_line_at(line, az)) + 2.0
                want = 0.006 if kind in ("loose", "swoop") else 0.004
            for _ in range(8):  # rooted IN the hair, 4 mm inside the line (its start hides under the gather)
                if float(inside(sc, line, az, el)) >= want:
                    break
                el += 2.0
            # (a swoop lies ON the gathered hair from its root: under it, the draped front hid it whole, th_T64)
            p = sc.point(az, el, over + 0.003 if kind == "swoop" else 0.002 if kind != "baby" else 0.0008)
            out = dirs(az, el)
            eo = _unit(np.array([out[0], out[1], 0.0]))
            sidev = np.array([float(side), 0.0, 0.0])
            # (not toward a high tie: "back" is then up, and held level they were straight dark blades in front of
            # the ears of a top knot, th_Q5)
            back = kind == "soft" and zone in ("temple", "sideburn") and rng.uniform() < tuck and float(tp["at"][1]) < 30.0
            # (a thick loose lock goes the way the hair was combed, out over the temple and back toward the ear, and
            # droops on the way: hanging straight down the cheek, 50 hairs were a stiff brush beside the eye, th_T51)
            back = back or (kind == "loose" and float(tp["at"][1]) < 30.0)
            comb = kind == "baby" and rng.uniform() < 0.5  # (lies back the way the hair was combed)
            # lengths: short ones at the part and front (they end at the brow / temple, never over the eye), longer
            # beside the face
            zl = {"part": 0.75, "front": 0.75, "temple": 0.9, "sideburn": 1.0, "nape": 0.6}[zone]
            ln = (l0 + (l1 - l0) * rng.uniform(0, 1) ** 1.2) * zl
            if kind == "soft" and zone in ("temple", "sideburn") and not back:
                # (what hangs in front of the ear is short: a fringe; a dozen 10 cm hangers a side were a comb down the
                # cheek in profile, th_T51. The long ones are the tucked and the loose)
                ln *= rng.choice([0.45, 0.45, 0.7, 1.0])
            if kind == "baby":
                ln = rng.uniform(0.012, 0.04) * (0.7 if zone == "part" else 1.0)
            elif kind == "loose":
                ln = rng.uniform(0.09, 0.16) * (1.0 if zone == "temple" else 1.1)
            elif kind == "swoop":
                ln = rng.uniform(0.13, 0.19)
            if back:
                ln = max(ln, 0.07) * 1.2
            ds = ln / (m - 1)
            dist, nrm = _surface(sc, col, p[None])
            nrm = nrm[0]
            g_t = DOWN - (DOWN @ nrm) * nrm
            # the first direction lies ON the skin: out to its own side at the part / front (the hair off a part
            # falls outward over the forehead's corner), down in front of the ear, down the nape
            if zone in ("part", "front"):
                d = sidev * rng.uniform(0.5, 1.2) + _unit(g_t) * rng.uniform(0.3, 0.8)
            elif zone == "nape":
                d = _unit(g_t) + 0.3 * rng.normal(0, 1, 3)
            else:
                # (down in front of the ear, a little back if anything: started forward they ran across the cheek
                # toward the nose, th_T43)
                d = _unit(g_t) + np.array([0.0, -1.0, 0.0]) * rng.uniform(-0.6, 0.12)
            if back:
                to = tie_d - (tie_d @ nrm) * nrm
                to[2] = min(to[2], 0.0)
                d = _unit(to + 1e-9) + 0.5 * _unit(g_t)
            if comb:  # back into the hair, each a little its own way
                to = tie_d - (tie_d @ nrm) * nrm
                if abs(float(_wrap(az))) < 60.0:  # (the front is combed to the back's middle, up over the head)
                    to = np.array([0.0, 1.0, 0.25]) + 0.5 * sidev
                    to = to - (to @ nrm) * nrm
                d = _unit(to + 1e-9) + 0.7 * rng.normal(0, 1, 3)
            d = _unit(d - (d @ nrm) * nrm)
            fall = rng.uniform(5.0, 11.0) * (1.6 if zone in ("part", "front") else 1.0)  # per metre: how fast it turns down
            if comb:
                fall *= 0.25
            elif kind in ("loose", "swoop"):
                fall *= 0.8
            cu0 = rng.normal(0, 1) * 6.0 * (0.4 + soft)  # its slow curl in the surface (rad per metre) ...
            # (at 6-16 rad / m every 4-9 cm, with a 4.5 cm strand wave on top, they were wet ringlets on the face)
            cu1, lam_c, ph_c = rng.uniform(8.0, 18.0) * (0.4 + soft), rng.uniform(0.05, 0.11), rng.uniform(0, 2 * np.pi)
            if kind == "baby":  # (short: it turns faster; a 3 cm hair with a 10 cm curl is a straight bristle)
                cu0, cu1, lam_c = cu0 * 4.0, cu1 * 2.0, lam_c * 0.4
            elif kind in ("loose", "swoop"):  # (one slow curve, not a wriggle)
                cu0, cu1 = cu0 * 0.5, cu1 * 0.35
            gap0 = 0.0015 + 0.002 * rng.uniform(0, 1)
            sweep, drop = rng.uniform(0.5, 1.1), rng.uniform(10.0, 26.0)
            t_back = rng.uniform(0.42, 0.6)  # (a swoop: where along it the tie takes it back)
            if kind == "swoop":
                # (it FALLS out of the part and bows: swept hard along the line it was a ruled plank across the forehead)
                sweep, drop = rng.uniform(0.45, 0.8), 5.0 + 16.0 * drape * rng.uniform(0.7, 1.0)
                fall, cu0, cu1 = fall * 1.5, cu0 * 2.0 + side * rng.uniform(2.0, 6.0), cu1 * 2.0
            P = [p]
            for i in range(m - 1):
                s_ = i * ds
                dist, nrm = _surface(sc, col, P[-1][None])
                dist, nrm = float(dist[0]), nrm[0]
                g_t = DOWN - (DOWN @ nrm) * nrm
                hang = float(np.clip((dist - 0.006) / 0.006, 0, 1))  # off the skin: plain gravity
                pull = hang * DOWN + (1 - hang) * g_t
                az_, el_, _ = sc.coords(P[-1][None])
                swb = kind == "swoop" and s_ / ln > t_back
                if back or swb:  # drawn back toward the tie, drooping on the way; it never arrives
                    oo = dirs(az_[0], el_[0])
                    to = tie_d - (tie_d @ oo) * oo
                    to[2] = min(to[2], 0.0)  # (toward a top knot they climbed the temple as dark blades: back, never up)
                    w_ = 1 - _ss_t((s_ / ln - (0.8 if swb else 0.55)) / (0.2 if swb else 0.45))
                    pull = (1.4 if swb else 0.8) * w_ * _unit(to) + (0.25 + 0.75 * (1 - w_)) * pull
                elif comb:
                    pass
                elif zone in ("part", "front"):
                    # the front's wisps go the way the hair was combed: out along the hairline toward the temple,
                    # drooping below it, and only then down. Falling straight from the part they hung over the eyes
                    # as vertical wires (th_T41)
                    sw = dirs(az_[0] + side * 3.0, el_[0]) - dirs(az_[0], el_[0])
                    sw = _unit(sw - (sw @ nrm) * nrm)
                    w_ = 1 - _ss_t((s_ / ln - 0.6) / 0.4)
                    pull = sweep * w_ * sw + (0.3 + 0.7 * (1 - w_)) * pull
                elif zone in ("temple", "sideburn"):  # beside the face they keep to the hair's side of it
                    sw = dirs(az_[0] + side * 3.0, el_[0]) - dirs(az_[0], el_[0])
                    sw = _unit(sw - (sw @ nrm) * nrm)
                    fa_ = abs(float(_wrap(az_[0])))
                    pull = pull + (0.12 + 0.9 * (1 - _ss_t((fa_ - 38.0) / 20.0))) * sw
                curl = cu0 + cu1 * np.sin(2 * np.pi * s_ / lam_c + ph_c)
                d = _unit(d + fall * ds * pull + curl * ds * np.cross(nrm, d))
                if (back or swb) and d[2] > 0:  # (a tucked one never climbs: its curl took it up the head behind the ear)
                    d = _unit(d * np.array([1.0, 1.0, 0.0]) + 1e-9)
                if dist < 0.008:  # near the skin it lies along it
                    d = _unit(d - max(float(d @ nrm), 0.0) * nrm)
                q = P[-1] + ds * d
                dq, nq = _surface(sc, col, q[None])
                dq, nq = float(dq[0]), nq[0]
                az_, el_, _ = sc.coords(q[None])
                # (only the tucked ones ride over the gathered hair; the rest come out from under it at the hairline:
                # all of them lifted, the far temple's stood 1 cm off the head as a lace fringe)
                gap = gap0 + ((over + 0.002 if kind == "swoop" else over * _ss_t(i / 6.0))
                              if (back or kind == "swoop") and float(inside(sc, line, az_[0] % 360, el_[0])) > 0.004 else 0.0) \
                    + 0.005 * soft * (s_ / ln) ** 2
                if dq < gap:
                    q = q + (gap - dq) * nq
                elif dq < 0.02 and nq[2] > -0.35:  # ... and hugs it: down onto skin that faces up or sideways
                    # (all the way: pulled 60% a step, a wisp running sideways off the part left the forehead's
                    # corner as a horizontal wire into the air)
                    q = q - (dq - gap) * nq
                if zone in ("part", "front") and i > 1 and not swb:  # ... and never further down the forehead than ~2.5 cm
                    aq, eq, hq = sc.coords(q[None])
                    fq = abs(float(_wrap(aq[0])))
                    lo_ = float(_line_at(line, aq[0] % 360)) - drop
                    if fq < 48.0 and eq[0] < lo_:
                        q = sc.point(aq[0], lo_, float(hq[0]))
                d = _unit(q - P[-1])
                P.append(q)
            P = np.asarray(P)
            nh = int(rng.integers(int(h0), int(h1) + 1))
            width = (0.0025 + 0.006 * soft) * rng.uniform(0.6, 1.4) * min(1.0, 0.5 + ln / 0.12)
            if kind == "baby":
                nh, width = int(rng.integers(2, 6)), rng.uniform(0.0015, 0.004)
            elif kind == "loose":
                nh, width = int(rng.integers(18, 45)), rng.uniform(0.006, 0.011)
            elif kind == "swoop":
                nh, width = int(rng.integers(30, 70)), rng.uniform(0.009, 0.015)
            elif zone == "sideburn":  # (it hangs straight down bare skin: 20 hairs there were a dark blade in front of
                # the ear, th_Q5: fewer, wider apart)
                nh, width = max(4, nh // 2), width * 1.4
            locks[f"{pre}w{'b' if kind == 'baby' else 'l' if kind == 'loose' else 's' if kind == 'swoop' else ''}{k}"] = {
                "tier": "tie", "space": "xyz", "pts": _xyz(sc, np.vstack([P[:-1:2], P[-1:]])), "free": 1.0,
                "width": round(float(width), 4), "thickness": 0.0015, "taper": 0.55, "belly": 0.4, "root": 0.45,
                "cup": 0.0, "hairs": nh,
                "strands": {"wisp_fan": round((0.6 + 1.2 * soft) * (0.5 if kind in ("loose", "swoop") else 1.0), 2), "wisp_round": 0.3,
                            "tip_loss": 0.6 if kind in ("loose", "swoop") else 0.75,
                            "wave": round(0.002 + 0.004 * soft, 4), "wavelength": 0.08, "random": 1.0, "flat": 1.0,
                            "curl": 0.0, **(ws.get("strands") or {})}}
            k += 1
    return locks


def curls(sc, tp: dict, ws: dict, line, seed: int, col, pre: str) -> dict:
    """ESCAPED CURLS (tesshair7 round two; Joe since the first round: "front wispies", then softer, curlier, the front
    as separate loose locks, the ear's top clear): fine SEPARATE locks that never reached the tie. Each is 4-9 single
    hairs, 1.5-4 mm wide (thin enough to see through), rooted in the hair a few mm inside the line at the forehead's
    corner, the temple or in front of the ear. It leaves its root WITH the hair (up and out, over the first 1-2.5 cm:
    on a head with volume it comes out of the lifted mass's edge), lets go, and falls on its own: its own length, its
    own fall rate, and its own CURL (a helix round its falling line: radius 3-9 mm, 3-6 cm a turn, either hand),
    clear of the skin by its curl, never over an eye. {name: lock} ("xyz" locks with `hairs`, names <pre>k<k>).

    Not the wisp clumps (hair_flow_wisps.wisps: 14-37 hairs fanned flat ON the skin): under lifted hair those were a grey
    veil over the forehead's corners (th_V75..80)."""
    from .hair import dirs
    from .hair_groom import _line_at
    n = ws.get("curls") or 0
    n = [int(c) for c in (n if isinstance(n, (list, tuple)) else [n] * 2)]  # [right, left]
    if max(n) <= 0:
        return {}
    rng = np.random.default_rng([int(seed), 7717])
    vo = (tp.get("gather") or {}).get("volume") or {}
    lift = max(0.6 * float(vo.get("side") or 0.0), 0.004)
    soft = float(np.clip(ws.get("softness", 0.6), 0, 1))
    l0, l1 = ws.get("length") or (0.04, 0.12)
    zones = (("corner", 18.0, 40.0, 0.65), ("temple", 40.0, 62.0, 0.9), ("ear", 62.0, 82.0, 1.0))
    locks, k = {}, 0
    for si, side in enumerate((-1.0, 1.0)):
        for j in range(n[si]):
            zn, a0, a1, zl = zones[(j + int(rng.integers(0, 3))) % 3 if j >= 3 else j]
            az_w = a0 + (a1 - a0) * rng.uniform(0, 1)
            az = (side * az_w) % 360
            el = float(_line_at(line, az)) + rng.uniform(1.0, 5.0)
            nrm = dirs(az, el)
            p = sc.point(az, el, 0.001)
            ln = (float(l0) + (float(l1) - float(l0)) * rng.uniform(0, 1) ** 1.3) * zl * rng.choice([0.6, 0.8, 1.0, 1.25])
            m = int(np.clip(ln / 0.004, 14, 44))
            ds = ln / m
            outw = side * hair_flow.X - (side * hair_flow.X @ nrm) * nrm  # sideways, away from the face's middle, along the skin
            # (out of the hair only a little: at 0.9 x the normal with a slow fall they were springs standing 4 cm off
            # the temple in the air, th_W01; hers hang close to the face)
            d = _unit(0.35 * nrm + 0.35 * _unit(outw + 1e-9) + 0.2 * rng.normal(0, 1, 3) + 0.5 * DOWN)
            h_len = rng.uniform(0.006, 0.014) * (lift / 0.008) ** 0.5
            fall = rng.uniform(70.0, 150.0)
            core = [p]
            for i in range(m):
                go = float(_ss_t(((i + 1) * ds - 0.5 * h_len) / h_len))
                d = _unit(d + ds * fall * go * DOWN + ds * 6.0 * rng.normal(0, 1, 3))
                if az_w < 50.0 and side * d[0] < 0:  # (not across the face toward the eye)
                    d[0] *= 0.3
                    d = _unit(d)
                core.append(core[-1] + ds * d)
            core = np.asarray(core)
            # (a slow bend, not a ringlet: corkscrews of 2-6 mm at 2.5-5 cm read doll-like, th_W06 / th_62; hers are
            # near-straight escaped strands with a soft bend)
            R = rng.uniform(0.0008, 0.0025) * (0.5 + soft) * min(1.0, ln / 0.06)
            lam = rng.uniform(0.06, 0.11)
            ph, hand = rng.uniform(0, 2 * np.pi), rng.choice([-1.0, 1.0])
            core[1:] = _push(sc, col, core[1:], 0.002 + 0.6 * R)
            for _ in range(2):  # (the push kinks it where it meets the cheek)
                core[1:-1] = 0.25 * core[:-2] + 0.5 * core[1:-1] + 0.25 * core[2:]
            T, E1, E2 = _transport(core)
            sa = np.arange(m + 1) * ds
            env = _ss_t(sa / 0.02) * (0.6 + 0.6 * sa / ln)
            P = core + (R * env * np.cos(2 * np.pi * sa / lam + ph))[:, None] * E1 \
                + (hand * R * env * np.sin(2 * np.pi * sa / lam + ph))[:, None] * E2
            P[1:] = _push(sc, col, P[1:], 0.002)
            a_, e_, _h = sc.coords(P)
            bad = (np.abs(_wrap(a_)) < 42.0) & (np.asarray(e_) < _line_at(line, np.asarray(a_) % 360) - 16.0)
            if bad.any():
                P = P[:int(np.argmax(bad))]
            if len(P) < 8:
                continue
            locks[f"{pre}k{k}"] = {
                "tier": "tie", "space": "xyz", "pts": _xyz(sc, P), "free": 1.0,
                "width": round(float(rng.uniform(0.002, 0.005)), 4), "thickness": 0.0015, "taper": 0.5, "belly": 0.4,
                "root": 0.5, "cup": 0.0, "hairs": int(rng.integers(8, 17)),
                "strands": {"wisp_fan": 1.2, "wisp_round": 0.9, "tip_loss": 0.75, "wave": 0.002, "wavelength": 0.05,
                            "random": 1.0, "flat": 1.0, "curl": 0.0}}
            k += 1
    return locks


def halo(sc, locks: dict, n: int, seed: int, pre: str) -> dict:
    """THE HALO (tesshair7 round two; the coordinator on th_W09, hers: "fine, light, slightly curly loose hairs standing
    off the surface by a few mm, lit from behind: it is what makes hers read as hair and ours as a surface"). n single
    fine hairs (1-2 a lock, names <pre>h<k>) rooted ON the TOP layer of the gathered hair (locks with a small `shade`,
    not the hairline's row): each starts on its lock 15-85 % along it, follows the lock's direction for 3-11 cm while
    standing off it by 2-9 mm in the middle (out of the mass and back), turning on a slow loose curl. A share (18 %)
    rooted on the part's banks CROSSES the line toward the other side and falls there: the part is a soft line with
    hair over it, not a clean notch. They are single-hair locks: drawn fine (part transparent), lighter, no dark root.
    The old halo dial (strands.halo: short broken hairs off EVERY lock) stood a grid of wires over the crown (th_W04)."""
    from .hair_cards_mesh import spine
    if n <= 0:
        return {}
    rng = np.random.default_rng([int(seed), 4417])
    top, bank = [], []
    for k, lk in locks.items():
        if lk.get("space") == "xyz" or lk.get("hairs") or not k.startswith(f"{pre}g1_"):
            continue
        st = lk.get("strands") or {}
        if st.get("bank"):
            bank.append(k)
        elif float(st.get("shade", 0.0)) < 0.2:
            top.append(k)
    if not top:
        return {}
    out = {}
    cache = {}

    def path(k):
        if k not in cache:
            lk = locks[k]
            P = hair_lock_world(sc, lk)
            cache[k] = spine({**lk, "pts": P.tolist()}, 64)[0]
        return cache[k]
    n_b = int(round(0.16 * n)) if bank else 0  # (28 %: with the end-on bank strands a wiry knot at the corner, th_W13)
    for j in range(n):
        crossing = j < n_b
        k = bank[int(rng.integers(len(bank)))] if crossing else top[int(rng.integers(len(top)))]
        S = path(k)
        s_ = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(S, axis=0), axis=1))]
        L = float(s_[-1])
        a0 = (rng.uniform(0.0, 0.12) if crossing else rng.uniform(0.15, 0.85)) * L
        ln = rng.uniform(0.04, 0.13) * (0.5 if crossing else 1.0)
        m = int(np.clip(ln / 0.003, 12, 40))
        ss = np.clip(a0 + np.linspace(0, ln, m + 1), 0, L)
        Q = np.stack([np.interp(ss, s_, S[:, c]) for c in range(3)], 1)
        nrm = _unit(Q - sc.C)
        tq = _unit(np.gradient(Q, axis=0) + 1e-9)
        side = _unit(np.cross(nrm, tq) + 1e-9)
        u = np.linspace(0, 1, m + 1)
        off = rng.uniform(0.002, 0.009) * np.sin(np.pi * u) ** 0.7 + 0.0015
        sw = rng.uniform(-0.006, 0.006) * u ** 1.5  # (it drifts off its lock sideways)
        if crossing:  # over the line to the other side and down it
            sgn = -float(locks[k]["strands"]["bank"])
            sw = sgn * rng.uniform(0.008, 0.02) * _ss_t(u / 0.6) * np.sign((side[0] @ hair_flow.X) or 1.0)
        # (a gentle loose curve: 0.8-2.5 mm at 2-5 cm read as kinky wiggles, th_W10)
        # (seen end-on at the forehead's corner, 0.4-1.3 mm curls knotted into a dark wiry tangle, th_W13 / W14: hers
        # are long gentle arcs there)
        R = rng.uniform(0.0002, 0.0006) * (0.3 if crossing else 1.0)  # (those over the part near-straight)
        ph, lam = rng.uniform(0, 2 * np.pi), rng.uniform(0.04, 0.09)
        cs = np.cos(2 * np.pi * ss / lam + ph)
        P = Q + (off + R * cs)[:, None] * nrm + (sw + R * np.sin(2 * np.pi * ss / lam + ph))[:, None] * side
        out[f"{pre}h{j}"] = {"tier": "tie", "space": "xyz", "pts": _xyz(sc, P), "free": 1.0,
                             "width": round(float(rng.uniform(0.001, 0.0025)), 4), "thickness": 0.001, "taper": 0.5,
                             "belly": 0.4, "root": 0.5, "cup": 0.0, "hairs": int(rng.integers(1, 3)),
                             "strands": {"wisp_fan": 0.6, "wisp_round": 0.9, "tip_loss": 0.6, "wave": 0.0,
                                         "wavelength": 0.05, "random": 1.0, "flat": 1.0, "curl": 0.0}}
    return out


def hair_lock_world(sc, lk):
    from .hair_spec import lock_world
    return lock_world(sc, lk, lk["pts"])
