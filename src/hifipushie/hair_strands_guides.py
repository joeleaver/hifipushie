"""Guides: a lock's guides, the scalp and collision meshes, zones, the scalp's UVs, the under guides. Part of the hair strands (hair_strands.py has the overview)."""
from __future__ import annotations

import hashlib

import numpy as np

from . import hair_strands
from . import hair_cards_mesh
from .hair_strands import _smooth_field, _ss, _unit, is_gather, wisp_physical

def lock_guides(locks: list, C, S: dict, seed: int = 0, n_head: int = 24, n_free: int = 32) -> dict:
    """{"head": G, "free": G}: G = {"counts", "pts", "side", "out", "weight", "lock", "names"} (the guide arrays of
    blender_strands.curves_object; `weight` = each lock's share of the strands, by its section)."""
    from .hair_spec import lock_width
    out = {}
    even_all = float(S.get("even") or 0.0) >= hair_strands.EVEN_ALL
    lam = max(float(S["wavelength"]), 0.01)
    import re
    gl_ = [float(np.linalg.norm(np.diff(np.asarray(lk["pts"], float), axis=0), axis=1).sum()) for lk in locks if is_gather(lk)]
    age_tail = float(np.median(gl_)) if gl_ else 0.0  # m of hair between the scalp and a tie

    def kind(lk):  # "wisp": a lock of `hairs` SINGLE strands (its own object: a lock's share of the count is never
        # under ~8 strands, and 8 side by side on one line are a comb strip, not loose hairs)
        return "wisp" if int(lk.get("hairs") or 0) > 0 else "free" if float(lk.get("free", 0.0)) > 0.5 else "head"

    for key0 in ("head", "free", "wisp"):
        sel = [(i, lk) for i, lk in enumerate(locks) if kind(lk) == key0]
        if not sel:
            continue
        key = "head" if key0 == "head" else "free"  # (single hairs are shaped like hair that has left the head)
        n = n_free if key == "free" else n_head
        if key0 == "wisp":
            n = 48
        elif key == "free" and float(S["wave"]) > 0:  # curls need points: 8 a turn of the tightest swing
            lmax = max(float(np.linalg.norm(np.diff(np.asarray(lk["pts"], float), axis=0), axis=1).sum()) for _, lk in sel)
            n = int(np.clip(np.ceil(8 * lmax / lam), n, 160))
        P_, S_, O_, W_, I_, N_, K_, F_, R_, WS_, WL_, TS_, GR_, D_, CX_, FN_, EX_ = ([] for _ in range(17))
        A0_, A1_, SH_, HK_, SU_ = [], [], [], [], []
        wisp_tips = wisp_physical(S)["tips"]
        for i, lk in sel:
            Sl = {**S, **{k: v for k, v in (lk.get("strands") or {}).items() if k in S}}
            for k_ in ("wisp_fan", "wisp_round", "tip_loss"):
                if k_ in (lk.get("strands") or {}):
                    Sl[k_] = lk["strands"][k_]
            rng = np.random.default_rng([seed, int(hashlib.md5(lk["name"].encode()).hexdigest()[:8], 16)])
            inp = lk["inputs"]
            P, rad, tilt, u, s = hair_cards_mesh.spine(lk, n)
            ang = np.radians(inp.get("Flip", 0.0) + inp.get("Twist", 0.0) * u) + tilt
            T, N, B, _ = hair_cards_mesh.frames(P, C, ang, lk.get("core"))
            W, th = float(inp["Width"]), float(inp["Thickness"])
            lw = np.clip(lock_width(inp, u) * rad, 0.0, 4.0)
            belly = max(float(inp.get("Belly", 0.3)), 0.02)
            # the lock's own taper would bring every strand to one point (a wet paint brush): the section stays
            # open toward the tip and the strands end one by one instead (lens group "Tips")
            floor = (0.4 if key == "free" else 0.4) + 0.3 * float(np.clip(Sl["tip_spread"], 0, 1))
            floor *= float(np.clip((W - 0.012) / 0.02, 0.0, 1.0))  # (a thin wisp keeps its point)
            gather = is_gather(lk)
            if gather:  # hair drawn to a tie ends IN the tie: the lock narrows into it and every strand gets there
                # (kept open and trimmed like loose hair, the gather stood round the tie as a fan of plates and tufts)
                lw = lw * (1 - 0.75 * _ss((u - 0.5) / 0.5))
            else:
                lw = lw + np.clip(floor - lw, 0.0, None) * _ss((u - belly) / 0.3)
            fr = float(lk.get("free", 0.0))
            R = float(Sl["random"])
            # (hair lying on the head barely swings: at 0.3 of the free swing, locks in step drew ridges round the
            # scalp, finger waves that read wet and slicked (Tess, 2026-10-09))
            A = 0.6 * float(Sl["wave"]) * (0.12 + 0.88 * fr) * (1 + R * rng.uniform(-0.4, 0.4))
            # a wisp swings less and slower than a lock (at a lock's wave a few hairs side by side are ramen)
            ws = float(np.clip(W / 0.03, 0.2, 1.0))
            wl = 1.0 + 1.2 * float(np.clip(1.0 - W / 0.02, 0.0, 1.0))
            if even_all:  # dense GUIDES, not wisps: their width is the guide spacing, the waves are the hair's own
                # (damped as wisps, the lengths hung dead straight)
                ws, wl = 1.0, 1.0
            A = min(A * ws, 0.3 * lam * wl)  # (never wider than a third of the wavelength: it would fold over)
            # neighbours wave nearly in step (a tail swings as sheets of hair; every lock on its own phase is pasta)
            # (up to random 0.6; past it locks fall fully out of step and differ in wavelength: curls, where locks
            # in step are a crimped sheet with ridges running round the head)
            Rc = max(R - 0.6, 0.0) / 0.4
            if even_all:  # the locks are dense GUIDES (strands.even 1): a child averages a few of them, so their waves
                # must agree with their neighbours' (random phases cancelled: straight hair). Phase and
                # wavelength are a smooth field of the root (~3 cm), as neighbouring real hairs wave in step
                u1, u2 = _smooth_field(P[0], seed), _smooth_field(P[0], seed + 1)
                wl = wl * (1 + 0.35 * Rc * u2)
                ph = u1 * (R * 1.2 + Rc * (np.pi - 1.2)) + 2 * np.pi * s / (lam * wl)
            else:
                wl = wl * (1 + 0.35 * Rc * rng.uniform(-1, 1))
                ph = rng.uniform(-1, 1) * (R * 1.2 + Rc * (np.pi - 1.2)) + 2 * np.pi * s / (lam * wl)
            wf_ = float(Sl.get("wave_from") or 0.0)  # (m along the lock where the waves start: long hair straight on top,
            # wavy in the lengths below the ear; 0 = from 3 cm, as before)
            env = _ss(s / 0.03) if wf_ <= 0 else _ss((s - wf_) / 0.06)
            P = P + B * (A * env * np.sin(ph))[:, None] + N * (A * env * float(Sl["curl"]) * fr * np.cos(ph))[:, None]
            hw = W / 2 * lw
            thin = W < 0.016
            if key == "free" and not thin:  # a tail's locks share one volume: their strands run into each other's
                hw = hw * 1.5
            fan = float(Sl.get("wisp_fan", hair_strands.WISP_FAN))
            if key == "free" and thin and fan > 0 and not gather:
                # a wisp is a few strands that drift apart below the root, not a ribbon: its section opens toward the
                # tip and goes round (kept at the lock's width, a 4 mm wisp drew as a comb strip of parallel strands:
                # Tess, 2026-10-09)
                hw = hw * (1.0 + fan * _ss((u - 0.15) / 0.85))
            ht = np.maximum(th / 2 * float(Sl["flat"]) * np.maximum(lw, 0.3) ** 0.5, 0.0008)
            if key == "free":  # hair off the head isn't pressed flat: a rounder section (a ribbon twists like bacon)
                # (wisp_round: a clump that lies on the skin is a flat fan, not a round brush standing off it)
                ht = np.maximum(ht, float(Sl.get("wisp_round", 0.9 if (thin and fan > 0) else 0.4)) * hw)
            P_.append(P)
            S_.append(B * hw[:, None])
            O_.append(N * ht[:, None])
            W_.append(W * max(th * float(Sl["flat"]), 0.004 if key == "head" else 0.0015)
                      * (1.0 if key == "head" else (0.9 if fan <= 0 else 0.3) if thin else 2.5))  # (a wisp: few strands)
            # strands.density on a lock (a region): x its strands, ABSOLUTE (not a share: scaling every lock of the head
            # alike would change nothing): an airy top where the strands don't fill the lock's lens
            D_.append(float(np.clip((lk.get("strands") or {}).get("density", 1.0), 0.05, 4.0)) * float(lk.get("edge_density", 1.0)))
            # a fly-away gets as far as its lock is wide (a thin face strand has no 4 cm strays)
            # (nor further than a quarter of its length: short hair had 4 cm spikes)
            F_.append(min(hair_strands.SAFE["flyaway_m"] * (2.0 if key == "free" else 1.0), 0.8 * W, 0.25 * float(s[-1])) * (0.3 if gather else 1.0))
            # (roots_x: a lock that says itself how far its starts spread, e.g. one that runs along the hairline)
            rs_ = max(4.0 if lk.get("at_hairline") else 1.0, float((lk.get("strands") or {}).get("roots_x", 1.0)))
            if "roots_m" in (lk.get("strands") or {}):
                # the stagger in METRES (the edge band: a lock's strands start over its first 1-2 cm whatever its
                # length. As a share of the length, a 25 cm lock from the temple to a HIGH tie started its strands over
                # 8 cm: it left the strip in front of the ear bare, the "shaved" temple of the high ponytail, th_S1)
                rs_ = float(lk["strands"]["roots_m"]) / max(hair_strands.SAFE["roots"] * float(np.clip(S["roots"], 0, 1)) * float(s[-1]), 1e-6)
            elif "roots" in (lk.get("strands") or {}):  # a lock's own `roots` (the dial is one number an object: per
                # lock it scales the lock's share of it): 0 = every strand of this lock starts at the lock's root
                rs_ *= float(np.clip(lk["strands"]["roots"], 0, 1)) / max(float(np.clip(S["roots"], 0, 1)), 1e-6)
            R_.append(rs_)
            own = lk.get("strands") or {}
            # a lock's own tips / clump (the dials are one number an object): as a factor on the object's
            if key0 == "wisp" and "tip_loss" in own:  # the share of its length the shortest hair of a clump loses
                # (a clump tapers because its hairs end one by one)
                TS_.append(float(np.clip(own["tip_loss"], 0, 0.92)) / max(wisp_tips, 1e-3))
            else:
                TS_.append(0.0 if gather else float(np.clip(own["tips"], 0, 1)) / max(float(np.clip(S["tips"], 0, 1)), 1e-3)
                           if "tips" in own else 1.0)
            CX_.append(float(np.clip(own["clump"], 0, 1)) / max(float(np.clip(S["clump"], 0, 1)), 1e-3) - 1.0
                       if "clump" in own else 0.0)
            # (rim: the lens's Edge for this lock, as what it adds to the object's 0.8: > 1 = strands thin out toward
            # the lock's two side rims, a ribbon with soft sides)
            EX_.append(float(np.clip(own["rim"], 0.2, 4.0)) / 0.8 - 1.0 if "rim" in own else 0.0)
            FN_.append(float(np.clip(own.get("fine", 0.0), 0.0, 1.0)))  # (drawn fine: the hairline's thin rim)
            GR_.append(float(np.clip(inp.get("Grey", lk.get("grey", 0.0)), 0.0, 1.0)))  # share of grey hairs
            # the hair's AGE along the lock, m from the scalp (the look's `sun` / `highlights`): a tail's lock starts
            # where the gathered hair ended, not at a new root
            a0_ = age_tail if (age_tail > 0 and re.fullmatch(r"t\d*[ty]\d+", str(lk.get("name", "")))) else 0.0
            A0_.append(a0_)
            A1_.append(a0_ + float(s[-1]))
            HK_.append(float(max(1.0, round(2.0 * float(np.max(hw)) / 0.006))))  # highlight ribbons across the lock, ~6 mm each
            SH_.append(float(np.clip((lk.get("strands") or {}).get("shade", 0.0), 0.0, 1.0)))  # depth in the mass
            SU_.append(float(np.clip((lk.get("strands") or {}).get("sun", 0.0), -0.5, 0.5)))  # where the sun reaches
            WS_.append(ws)
            WL_.append(wl)
            K_.append(max(1, int(round(W / float(np.clip(Sl["clump_size"], 0.002, 0.03))))))
            I_.append(i)
            N_.append(lk["name"])
        if key0 == "wisp":
            W_ = [0.0] * len(sel)  # (no share of the count: `hairs` strands each)
        out[key0] = {"hairs": np.asarray([int(lk.get("hairs") or 0) for _, lk in sel], np.int32),
                     "counts": np.full(len(sel), n, np.int32), "pts": np.concatenate(P_).astype(np.float32),
                    "side": np.concatenate(S_).astype(np.float32), "out": np.concatenate(O_).astype(np.float32),
                    "weight": np.asarray(W_, float), "density": np.asarray(D_, float), "lock": np.asarray(I_, np.int32), "k": np.asarray(K_, np.int32), "fd": np.asarray(F_, np.float32), "rs": np.asarray(R_, np.float32), "ts": np.asarray(TS_, np.float32),
                    "ws": np.asarray(WS_, np.float32), "wl": np.asarray(WL_, np.float32),
                    "gr": np.asarray(GR_, np.float32), "names": np.asarray(N_),
                    "a0": np.asarray(A0_, np.float32), "a1": np.asarray(A1_, np.float32),
                    "hk": np.asarray(HK_, np.float32)}
        if any(SH_):
            out[key0]["sh"] = np.asarray(SH_, np.float32)
        if any(SU_):
            out[key0]["su"] = np.asarray(SU_, np.float32)
        if any(CX_):  # (only when a lock asks: older jobs keep their files, and so their cache keys)
            out[key0]["clx"] = np.asarray(CX_, np.float32)
        if any(EX_):
            out[key0]["ex"] = np.asarray(EX_, np.float32)
        if any(FN_):
            out[key0]["fn"] = np.asarray(FN_, np.float32)
    return out


def scalp_mesh(sc, g: dict, line, S: dict, step: float = 3.0) -> dict:
    """The scalp inside the hairline (a margin outside it) as a triangle mesh with a UV map (u = azimuth / 360,
    v = elevation over its range: a chart Blender's Interpolate and Curves sculpt tools attach hair to) and
    `hp_density`: 0 just outside the hairline, 1 `soft` m inside, thinned along the parting."""
    from .hair_groom import _part, inside
    A = np.arange(0.0, 360.0 + 1e-6, step)  # (the seam column twice: az 0 and 360)
    e0 = float(np.floor(max(line.min() - 12.0, sc.EL[0] + 2)))
    E = np.arange(e0, 88.0 + 1e-6, step)
    AA, EE = np.meshgrid(A, E, indexing="ij")
    d_in = inside(sc, line, AA % 360, EE)
    V = sc.point(AA % 360, EE, 0.0004).reshape(-1, 3)
    soft = max(float(S["soft"]), 0.001)
    dens = _ss((d_in + 0.0015) / soft)
    pw = float(g["parting"].get("width", 0.012))
    # the even layer's own density: no thinning at the part (a part is the comb, never fewer roots: hair-heads, Joe), and
    # none in the first EVEN_EDGE m inside the hairline: there an interpolated child takes the shape of guides rooted
    # behind it and hung over the forehead as a sparse veil; the hairline's own locks carry the edge
    fa_ = np.abs(((AA + 180) % 360) - 180)
    edge_ = hair_strands.EVEN_EDGE + (hair_strands.EVEN_FRONT - hair_strands.EVEN_EDGE) * (1 - _ss((fa_ - 50.0) / 30.0))  # (deeper in over the face)
    dens_even = _ss((d_in - edge_) / 0.015)
    if float(S.get("even") or 0.0) >= hair_strands.EVEN_ALL:  # ALL roots even (the locks are dense guides only): the hairline's own
        # ramp, no inset (the inset was for children of guides 1+ cm away hanging over the face; at a guide spacing of a
        # few mm a child follows its guides' face rule)
        dens_even = dens.copy()
        fd_ = (g.get("loose") or {}).get("fade")
        if fd_:  # a FADE thins the even roots toward the nape hairline too (it thinned only lock strands: the even layer
            # ended in a level blunt row, Garrett E9-E11), as hair_loose's own fade: back of the head, over `width` m
            from .hair_loose import FADE
            fd_ = {**FADE, **(fd_ if isinstance(fd_, dict) else {})}
            backw_ = _ss((fa_ - 100.0) / 30.0)
            if fd_.get("taper"):  # a TAPER thins only at the very line (over its lowest third), as hair_loose's
                ramp_ = _ss(np.clip(d_in / (0.35 * float(fd_["taper"])), 0, 1))
            else:
                ramp_ = _ss(d_in / max(float(fd_["width"]), 1e-3))
            dens_even = dens_even * (1 - backw_ * (1 - (float(fd_["density"]) + (1 - float(fd_["density"])) * ramp_)))
            ff_ = fd_.get("front")
            if ff_:  # the soft FRONT edge (hair_loose fade.front): fewer roots of every layer near the front line too
                frw_ = 1 - _ss((fa_ - 80.0) / 30.0)
                rf_ = _ss(d_in / max(float(ff_.get("width", 0.012)), 1e-3))
                k_ = 1 - frw_ * (1 - (float(ff_.get("density", 0.3)) + (1 - float(ff_.get("density", 0.3))) * rf_))
                dens_even, dens = dens_even * k_, dens * k_
    wh_ = (g.get("loose") or {}).get("whorl")
    if isinstance(wh_, dict) and float(wh_.get("thin") or 0.0) > 0:  # the WHORL's scalp show (hair_loose whorl.thin):
        # fewer roots of every layer at its centre, a Gaussian of thin_radius m
        from .hair_loose import WHORL
        wh_ = {**WHORL, **wh_}
        Wc_ = sc.point(np.array([float(wh_["at"][0]) % 360.0]), np.array([float(wh_["at"][1])]), 0.0004)[0]
        k_ = 1 - float(wh_["thin"]) * np.exp(-0.5 * (np.linalg.norm(V - Wc_, axis=1).reshape(AA.shape)
                                                     / max(float(wh_["thin_radius"]), 1e-3)) ** 2)
        dens_even, dens = dens_even * k_, dens * k_
    # the SPLIT ZONE (strands.even 1): where neighbouring guides comb opposite ways, a child averaging them takes the
    # middle path (over the cheek at a tuck's edge; down the face where the face rule turns hair aside): there a
    # child copies its NEAREST guide; everywhere else it blends three (copies of one guide on short dense hair were
    # bundles of identical strands with gaps: Garrett E2-E3's "pine needles", the coordinator)
    zone = _split_zone(sc, g, AA, EE, d_in, fa_) if float(S.get("even") or 0.0) >= hair_strands.EVEN_ALL else np.zeros_like(d_in)
    dens = dens * (1 - 0.9 * np.clip(_part(sc, g, AA % 360, EE, 0.25 * pw), 0, 1))
    na, ne = AA.shape
    idx = np.arange(na * ne).reshape(na, ne)
    live = d_in > -0.008
    uvv = np.stack([AA / 360.0, (EE - e0) / (90.0 - e0)], -1).reshape(-1, 2)
    a, b, c, d = idx[:-1, :-1], idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:]
    ok = (live[:-1, :-1] | live[1:, :-1] | live[1:, 1:] | live[:-1, 1:]).ravel()
    q = np.stack([a.ravel(), b.ravel(), c.ravel(), d.ravel()], 1)
    # a quad whose corners are 2 cm apart in distance from the head centre is no scalp: the rays stepped from the
    # neck out to the back or a shoulder (a low nape hairline, -60 deg on Tess: the margin row's quads stood out
    # behind the neck as a sheet, and its few hairs were dots and dashes floating there, 2026-10-11)
    rq = np.linalg.norm(V - sc.C, axis=1)[q]
    ok = ok & ((rq.max(1) - rq.min(1)) < 0.02)
    q = q[ok]
    F = np.concatenate([q[:, [0, 1, 2]], q[:, [0, 2, 3]]])
    # the pole: a fan from the top row to one vertex
    pole = len(V)
    V = np.vstack([V, sc.point(0.0, 90.0, 0.0004)[None]])
    uvp = len(uvv)
    top = idx[:, -1]
    fan = np.stack([top[:-1], top[1:], np.full(na - 1, pole)], 1)
    F = np.concatenate([F, fan])
    dens = np.r_[dens.ravel(), 1.0]
    dens_even = np.r_[dens_even.ravel(), 1.0]
    zone = np.r_[zone.ravel(), 0.0]
    uv_corner = np.concatenate([uvv[F[:len(F) - len(fan)]],
                                np.stack([uvv[fan[:, 0]], uvv[fan[:, 1]],
                                          np.stack([(uvv[fan[:, 0], 0] + uvv[fan[:, 1], 0]) / 2,
                                                    np.ones(len(fan))], 1)], 1)])
    del uvp
    from .hair_groom import _part_x
    xp_ = _part_x(g) if (float(S.get("even") or 0.0) > 0 and (g.get("parting") or {}).get("side", "left") != "none") else None
    if xp_ is not None:
        # TWO ISLANDS split along the part (the even layer interpolates with "Part by Mesh Islands"): a child takes its
        # shape only from guides on ITS side of the part. Averaged across the part, guides going left and right made
        # children that fell straight down the middle: a veil over the face (hair-heads)
        cx = V[F].mean(1)[:, 0] - sc.C[0] - xp_
        F = np.where((cx > 0)[:, None], F + len(V), F)
        V = np.vstack([V, V])
        dens = np.r_[dens, dens]
        dens_even = np.r_[dens_even, dens_even]
        zone = np.r_[zone, zone]
        # ... and the right island's UVs one unit over (u + 1): Interpolate finds a guide's island by its surface UV, and
        # with both islands on one chart every guide was on either side: children took guides from across the part,
        # the veil over the face that the split did not remove (hair-heads). scalp_uv(xp=) shifts the roots
        uv_corner = uv_corner.reshape(len(F), 3, 2).copy()
        uv_corner[cx > 0, :, 0] += 1.0
    used = np.unique(F)
    banks = {}
    if xp_ is not None:
        # ... and that was not enough either: Blender's islands still averaged guides across the part (the children
        # rooted ON the part fell straight down the forehead). Each bank is its own object (hair_even = the
        # left bank, x < the part, hair_even_r the right), with its own guides and a mask that is 0 on the other bank
        h_ = len(dens_even) // 2
        banks = {"hp_density_even_l": np.r_[dens_even[:h_], np.zeros(h_)][used].astype(np.float32),
                 "hp_density_even_r": np.r_[np.zeros(h_), dens_even[h_:]][used].astype(np.float32)}
    if zone.any():  # blend outside the split zone, nearest guide in it: each even mask split in two (_n = the zone)
        z_ = zone[used].astype(np.float32)
        base_ = banks or {"hp_density_even": dens_even[used].astype(np.float32)}
        banks = {}
        for k_, v_ in base_.items():
            banks[k_] = v_ * (1 - z_)
            banks[k_ + "_n"] = v_ * z_
    remap = -np.ones(len(V), int)
    remap[used] = np.arange(len(used))
    tri = V[F]
    area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    return {"verts": V[used].astype(np.float32), "faces": remap[F].astype(np.int32),
            "uv": uv_corner.reshape(-1, 2).astype(np.float32), "hp_density": dens[used].astype(np.float32),
            "hp_density_even": dens_even[used].astype(np.float32),  # (overridden by the zone split, below)
            "area": float((area * dens[F].mean(1)).sum()), "e0": e0, "xp": xp_, **banks}


def collide_mesh(sc, step: float = 4.0) -> dict:
    """What strands are kept out of: the head, neck and shoulders as the head centre sees them (the scalp's rays), a
    few thousand triangles. Blender's Shrinkwrap against the body's own mesh (hundreds of thousands) took minutes."""
    A = np.arange(0.0, 360.0, step)
    E = np.arange(sc.EL[0], 90.0 - 1e-6, step)
    AA, EE = np.meshgrid(A, E, indexing="ij")
    V = sc.point(AA, EE, 0.0).reshape(-1, 3)
    na, ne = AA.shape
    idx = np.arange(na * ne).reshape(na, ne)
    a, b = idx[:, :-1], np.roll(idx, -1, 0)[:, :-1]
    c, d = np.roll(idx, -1, 0)[:, 1:], idx[:, 1:]
    q = np.stack([a.ravel(), b.ravel(), c.ravel(), d.ravel()], 1)
    pole = len(V)
    V = np.vstack([V, sc.point(0.0, 90.0, 0.0)[None]])
    top = idx[:, -1]
    fan = np.stack([top, np.roll(top, -1), np.full(na, pole)], 1)
    return {"verts": V.astype(np.float32), "faces": np.concatenate([q[:, [0, 1, 2]], q[:, [0, 2, 3]], fan]).astype(np.int32)}


def _longest(g: dict) -> float:
    """The loose groom's longest length (m), 0 without one."""
    ln = (g.get("loose") or {}).get("length", 0.0)
    return max(float(v) for k, v in ln.items() if k != "top_el") if isinstance(ln, dict) else float(ln or 0.0)


def _split_zone(sc, g: dict, AA, EE, d_in, fa):
    """1 where the comb splits (EVEN children copy their nearest guide there), else 0. LONG loose hair (over 15 cm):
    everywhere: it splits at the part, the tuck, the face rule AND over the shoulders (in front of them or behind):
    blended children of a front and a back guide hung across the neck and chest. Short hair: round the EAR
    when tucked behind it; elsewhere none (blend: a fine combed surface, Garrett E4)."""
    lo = g.get("loose") or {}
    z = np.zeros_like(d_in, dtype=float)
    ln = lo.get("length", 0.0)
    lmax = max(float(v) for k, v in ln.items() if k != "top_el") if isinstance(ln, dict) else float(ln or 0.0)
    if lmax > 0.15:
        return np.ones_like(d_in, dtype=float)
    tk = lo.get("tuck")
    if tk:
        from .hair_groom import ear as _ear
        er = _ear(sc)
        ef, eb = (float(er["front"]), float(er["back"])) if er else (80.0, 105.0)
        top_ = float(er["top"]) if er else sc.C[2] - 0.01
        a0 = float(tk["from"]) if tk.get("from") is not None else ef - 45.0
        zc = sc.point(AA % 360, EE, 0.0)[..., 2]
        z = np.maximum(z, ((fa > a0 - 10.0) & (fa < eb + 20.0) & (zc < top_ + 0.05)).astype(float))
    return z


def _guides_subset(G: dict, sel) -> dict:
    """The guide arrays (curves_object's) of the selected curves: per-curve arrays by `sel`, `pts` by their points."""
    cnt = G["counts"]
    pt = np.repeat(sel, cnt)
    return {k: (v[pt] if k == "pts" else v[sel] if (hasattr(v, "__len__") and len(v) == len(cnt)) else v)
            for k, v in G.items()}


def scalp_uv(sc, P, e0: float, xp: float | None = None):
    """The scalp chart's uv under world points (`xp`: the part's x when the scalp is split into two islands there: the
    right island's chart is u + 1)."""
    az, el, _ = sc.coords(P)
    uv = np.stack([(az % 360) / 360.0, (el - e0) / (90.0 - e0)], -1)
    if xp is not None:
        uv[..., 0] += (np.asarray(P)[..., 0] - sc.C[0] - xp > 0)
    return uv


def _sphere(n: int):
    k = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * k / n)
    th = np.pi * (1 + 5 ** 0.5) * k
    return np.stack([np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)], 1)


def under_guides(sc, g: dict, line, locks: list, S: dict, seed: int = 0, n: int = 10) -> dict | None:
    """The scalp layer's guides: from seeds all over the scalp inside the hairline, each run along the flow of the
    locks over it (the direction of the nearest lock spines, laid in the scalp's tangent plane) for `under_length`,
    rising from the skin to just under those locks. Seeds on the hairline itself are the baby hairs: short."""
    from scipy.spatial import cKDTree
    from .hair import az_el
    from .hair_groom import inside
    if float(S["under"]) <= 0:
        return None
    rng = np.random.default_rng([seed, 77])
    r0 = float(np.median(sc.R))
    D = _sphere(int(4 * np.pi * r0 * r0 / hair_strands.SEED_SPACING ** 2))
    az, el = az_el(D)
    az, el = az + rng.uniform(-1, 1, len(az)), el + rng.uniform(-1, 1, len(az))
    d_in = inside(sc, line, az % 360, el)
    keep = (d_in > -0.001) & (el > sc.EL[0] + 3)
    az, el, d_in = az[keep] % 360, el[keep], d_in[keep]
    if not len(az):
        return None
    L = float(S["under_length"]) * (0.3 + 0.7 * _ss(d_in / 0.02)) * (1 + 0.3 * rng.uniform(-1, 1, len(az)))
    if float(S["baby"]) > 0:  # baby hairs: more seeds on the line, short and a little wild
        ab = rng.uniform(0, 360, int(60 * float(S["baby"])))
        eb = np.interp(ab, np.arange(361.0), np.r_[line, line[:1]]) + rng.uniform(0.0, 1.5, len(ab))
        ok = eb > sc.EL[0] + 3
        az, el = np.r_[az, ab[ok]], np.r_[el, eb[ok]]
        L = np.r_[L, rng.uniform(0.006, 0.016, int(ok.sum()))]
    head = [lk for lk in locks if float(lk.get("free", 0.0)) <= 0.5 or lk.get("tier") == "loose"]  # (loose hair
    # lies on the head before it falls: the scalp layer follows it there)
    tree = None
    if head:
        LP, LT, LG = [], [], []
        for lk in head:
            P, *_ = hair_cards_mesh.spine(lk, 16 if float(lk.get("free", 0.0)) <= 0.5 else 40)
            LP.append(P)
            LT.append(_unit(np.gradient(P, axis=0)))
            LG.append(np.full(len(P), float((lk.get("inputs") or {}).get("Grey", lk.get("grey", 0.0)))))
        LP, LT, LG = np.concatenate(LP), np.concatenate(LT), np.concatenate(LG)
        _, _, LH = sc.coords(LP)
        near = LH < 0.035
        if near.sum() >= 8:
            LP, LT, LH, LG = LP[near], LT[near], LH[near], LG[near]
        tree = cKDTree(LP)
    p = sc.point(az, el, 0.0003)
    gr = np.zeros(len(p), np.float32)
    if tree is not None:  # the scalp layer under a lock is as grey as the lock (greying temples, sideburns)
        _, j0 = tree.query(p)
        gr = LG[j0].astype(np.float32)
    pts = [p]
    h = np.full(len(az), 0.0003)
    for k in range(1, n):
        nrm = sc.normal(az, el)
        if tree is not None:
            d, j = tree.query(p, k=min(6, len(LP)))
            w = 1.0 / (d + 0.003) ** 2
            t = (LT[j] * w[..., None]).sum(1)
            hl = (LH[j] * w).sum(1) / w.sum(1)
        else:
            t = np.tile([0.0, 0.25, -1.0], (len(p), 1))
            hl = np.full(len(p), 0.004)
        t = t - (t * nrm).sum(1, keepdims=True) * nrm
        bad = np.linalg.norm(t, axis=1) < 1e-4
        t[bad] = (np.array([0.0, 0.2, -1.0]) - nrm[bad] * nrm[bad, 2:3])
        t = _unit(t)
        s = k / (n - 1)
        q = p + t * (L / (n - 1))[:, None]
        az, el, _ = sc.coords(q)
        # up from the skin to just under the locks over it, by half its length
        h = np.clip(hl - 0.002, 0.0006, 0.03) * _ss(s / 0.5) + 0.0006
        p = sc.point(az, el, h)
        pts.append(p)
    P = np.stack(pts, 1)  # (seeds, n, 3)
    return {"counts": np.full(len(P), n, np.int32), "pts": P.reshape(-1, 3).astype(np.float32), "gr": gr,
            "names": np.asarray([f"u{i}" for i in range(len(P))])}
