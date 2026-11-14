"""The locks: `grow`, loose hair grown strand by strand from the scalp, and their lengths. Part of loose hair (hair_loose.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import hair_loose
from .hair_loose import _ss, _unit, params
from .hair_loose_body import Collider

# ------------------------------------------------------------------------------------------------ the locks
def _lengths(length, W):
    from .hair import REGIONS
    if isinstance(length, dict):
        d = {"front": 0.2, "top": 0.2, "sides": 0.2, "back": 0.2, "nape": 0.2}
        # (regions left out take the default, not the mean of those given)
        return sum(W[:, i] * float(length.get(r, d[r])) for i, r in enumerate(REGIONS))
    return np.full(len(W), float(length))


def grow(sc, g: dict, line, rng, col: Collider | None = None) -> dict:
    """{name: lock} for groom.loose."""
    from .hair import az_el
    from .hair_groom import _line_at, _part_x, _poisson, inside, weights
    p = params(g["loose"])
    sp = float(p["spacing"])
    # roots from `inset` m inside the hairline (default 4 mm). A short cut wants them ON the line (0.0005): 4 mm in, the
    # strip in front of the first roots was bare scalp-tinted skin, a dark band under a wall of hair (hair-heads, Garrett)
    ins_ = float(p.get("inset") if p.get("inset") is not None else 0.004)
    ok = lambda a, e: (inside(sc, line, a, e) > ins_) & (e > sc.EL[0] + 4)  # noqa: E731
    if p.get("below") is not None:  # only the hair rooted below a level (m from the head centre): the rest is tied (half up)
        ok0, zb = ok, float(p["below"])
        ok = lambda a, e: ok0(a, e) & ((sc.point(a, e, 0.0)[..., 2] - sc.C[2]) < zb)  # noqa: E731
    r0 = float(np.median(sc.R))
    az, el = _poisson(sc, rng, lambda a, e: np.full(len(a), sp), ok, n_try=int(np.clip(400 * r0 * r0 / sp ** 2, 4000, 40000)))
    m = len(az)
    if not m:
        return {}
    d_in = inside(sc, line, az, el)
    W = weights(az, el, d_in, float(p.get("blend") or 1.0))
    W_ = W
    if isinstance(p["length"], dict) and p["length"].get("top_el"):  # the top's length only on the head's TOP: from
        # el e0 to e1 deg it comes in, below that share takes the sides' length (the "top" region's weight is full from
        # 42 deg, so a long top hung down the upper sides as a bowl: Garrett G33-G40)
        e0_, e1_ = (float(x) for x in p["length"]["top_el"])
        up_ = _ss((el - e0_) / max(e1_ - e0_, 1e-3))
        W_ = W.copy()
        W_[:, 2] = W[:, 2] + W[:, 1] * (1 - up_)
        W_[:, 1] = W[:, 1] * up_
    L = _lengths(p["length"], W_) * (1 - float(p["uneven"]) * rng.uniform(0, 0.3, m))
    P0 = sc.point(az, el, 0.0005)
    nrm = sc.normal(az, el)
    xp = _part_x(g)
    fa = np.abs(((az + 180) % 360) - 180)
    # the combing direction at the roots: gravity laid in the scalp, plus, on the top and front (where gravity has
    # no direction or points over the face), away from the parting and back over the crown
    upw = _ss((nrm[:, 2] - 0.25) / 0.5)
    frontw = (1 - _ss((fa - 60) / 40)) * (1 - _ss((d_in - 0.03) / 0.05))
    tw = np.maximum(upw, frontw)
    x = P0[:, 0] - sc.C[0]
    away = np.sign(x - xp) if xp is not None else np.sign(x) * 0.0
    away = np.where(away == 0, 1.0, away) if xp is not None else away
    away_w = away.copy() if hasattr(away, "copy") else away
    pc = p.get("part_soft")
    if xp is not None and pc:
        # A SOFT PART (rule 5, hair-heads: a centre part's "bald stripe"): next to the part the roots are NOT combed away from it
        # (every root combed sideways off the line opened a bare V that widened toward the forehead); the away comb
        # comes in over `width` m, and a `cross` share of the roots within it is combed over to the other side
        pc = {"width": 0.015, "cross": 0.25} if pc is True else {"width": 0.015, "cross": 0.25, **pc}
        dx = np.abs(x - xp)
        near = dx < float(pc["width"])
        away_w = away * _ss(dx / max(float(pc["width"]), 1e-3))
        flip = near & (rng.uniform(size=m) < float(pc["cross"]))
        away_w = np.where(flip, -away * 0.6, away_w)
    back = float(p["back"])
    if xp is None and back <= 0:
        back = 1.0  # (no parting: the top has to go somewhere)
    comb = hair_loose.DOWN[None] * (1 - 0.8 * frontw[:, None]) + tw[:, None] * (
        (1 - 0.6 * back) * away_w[:, None] * np.array([1.0, 0, 0]) + back * np.array([0, 1.0, -0.15]))
    if xp is not None and pc:  # (what is not combed away at the part goes back over the head, not down the forehead)
        comb = comb + tw[:, None] * (0.8 * (1 - np.abs(away_w)))[:, None] * np.array([0, 1.0, -0.15])
    from .hair import REGIONS
    if p.get("flow"):  # a combing direction per region, by the region weights (what a traced flow gives)
        bad = set(p["flow"]) - set(REGIONS)
        if bad:
            raise ValueError(f"hair loose flow: unknown regions {sorted(bad)} (have {', '.join(REGIONS)})")
        for i_, r_ in enumerate(REGIONS):
            if r_ in p["flow"]:
                w_ = W[:, i_:i_ + 1]
                f_ = p["flow"][r_]
                if isinstance(f_, dict):  # {"from": [az, el], "bias": [x, y, z]}: combed AWAY from a scalp point (hair
                    # grows out of the crown: forward in the middle, forward-and-out over the temples, down the sides;
                    # one world direction for the whole top hung the top's temple hair forward over receded corners,
                    # Garrett G16 / G17), plus an optional world bias, laid in the scalp
                    a0, e0 = f_["from"]
                    Pc = sc.point(np.array([float(a0) % 360.0]), np.array([float(e0)]), 0.0005)[0]
                    v_ = P0 - Pc
                    v_ = _unit(v_ - (v_ * nrm).sum(1, keepdims=True) * nrm)
                    v_ = v_ + np.asarray(f_.get("bias", [0.0, 0.0, 0.0]), float)[None]
                    comb = comb * (1 - w_) + w_ * _unit(v_)
                else:
                    comb = comb * (1 - w_) + w_ * _unit(np.asarray(f_, float))[None]

    wh = p.get("whorl")
    if wh:  # the CROWN WHORL: a spiral out of one point, faded into the comb over `radius` (Garrett's back photo, the
        # blind review: "the crown has no whorl")
        a0, e0 = float(wh["at"][0]), float(wh["at"][1])
        Wc = sc.point(np.array([a0 % 360.0]), np.array([e0]), 0.0005)[0]
        rv = P0 - Wc
        rv = rv - (rv * nrm).sum(1, keepdims=True) * nrm  # (in the scalp's tangent plane)
        dist = np.linalg.norm(rv, axis=1)
        rh = rv / np.maximum(dist, 1e-9)[:, None]
        th = np.radians(float(wh["spiral"]))
        if float(wh.get("core") or 0.0) > 0:  # the hair GROWS RADIALLY from the whorl: a spiral within `core` m opening
            # into a straight radial spread out to `radius` (the whole top: region combs fighting a small whorl made
            # a second whorl and a seam where they parted, Garrett G8)
            th = th * (1 - _ss(dist / float(wh["core"])))[:, None]
        # (clockwise seen from above: on top of the head the normal points up, n x r turns r anticlockwise)
        spv = np.cos(th) * rh - float(wh["turn"]) * np.sin(th) * np.cross(nrm, rh)
        ww = (1 - _ss(dist / max(float(wh["radius"]), 1e-3)))[:, None]
        comb = comb * (1 - ww) + ww * spv

    ct = p.get("comb_trace")
    if ct and len(ct.get("samples") or []):  # the COMB TRACED from a reference (see "comb_trace" in the doc at the top)
        S_ = np.asarray([list(s_)[:7] + [1.0] * (7 - len(s_)) for s_ in ct["samples"]], float)
        sg_ = max(float(ct["sigma"]), 0.5)
        da_ = ((((az[:, None] - S_[None, :, 0]) + 180.0) % 360.0) - 180.0) * np.cos(np.radians(el))[:, None]
        g_ = np.exp(-0.5 * (da_ ** 2 + (el[:, None] - S_[None, :, 1]) ** 2) / sg_ ** 2) * np.sqrt(np.maximum(S_[None, :, 6], 0))
        v_ = g_ @ _unit(S_[:, 2:5])
        v_ = _unit(v_ - (v_ * nrm).sum(1, keepdims=True) * nrm)
        rw_ = sum(W[:, i_] * float(ct["regions"].get(r_, 0.0)) for i_, r_ in enumerate(REGIONS)) / np.maximum(W.sum(1), 1e-9)
        wt_ = (float(ct["amount"]) * rw_ * (1 - np.exp(-g_.sum(1) / max(float(ct["full"]), 1e-3))))[:, None]
        comb = comb * (1 - wt_) + wt_ * v_ * np.maximum(np.linalg.norm(comb, axis=1, keepdims=True), 1e-9)

    def by_region(v, default):  # a number, or {region: number}; regions left out take `default`
        # (NOT the mean of those given: {"front": .6} silently put .6 on sides, back and nape, Garrett G60-G63)
        if isinstance(v, dict):
            base = float(default)
            return sum(W[:, i_] * float(v.get(r_, base)) for i_, r_ in enumerate(REGIONS)) / np.maximum(W.sum(1), 1e-9)
        return np.full(m, float(v))
    fr = p["fringe"]
    is_fr = np.zeros(m, bool)
    curtain_ = False
    if fr:
        is_fr = (fa < float(fr["span"])) & (d_in < float(fr["depth"]))
        if fr["sweep"] == "away":  # CURTAIN BANGS: each side swept down and away from the parting, framing the face
            curtain_ = True
            sgn_ = np.sign(P0[:, 0] - sc.C[0] - (xp or 0.0))
            sgn_ = np.where(sgn_ == 0, 1.0, sgn_)
            # (out to the side first: down and forward, they hung as a thin veil over the forehead, hair-garrett lt r5)
            comb[is_fr] = np.stack([sgn_[is_fr] * 1.6, np.full(int(is_fr.sum()), -0.5), np.full(int(is_fr.sum()), -0.7)], 1)
        else:
            swp = float(fr["sweep"])
            comb[is_fr] = np.array([swp * 1.2, -1.0, -0.8])
        L[is_fr] = float(fr["length"]) * (1 - 0.5 * float(p["uneven"]) * rng.uniform(0, 0.3, int(is_fr.sum())))
        # curtain 0..1: the fringe is longer toward its outer edges (curtain bangs reach the cheekbones at the sides)
        L[is_fr] *= 1 + float(fr["curtain"]) * np.clip(fa[is_fr] / max(float(fr["span"]), 1.0), 0, 1)
        L[is_fr] += d_in[is_fr] * 0.9  # (rooted further back, it has further to go to the same edge)
    tk = p.get("tuck")
    wt = np.zeros(m)
    er = None
    if tk:  # TUCKED behind the ear: hair rooted over and in front of the ear is combed back behind it
        from .hair_groom import ear as _ear
        er = _ear(sc)
        ef, eb = (float(er["front"]), float(er["back"])) if er else (80.0, 105.0)
        azs = ((az + 180) % 360) - 180  # (+ = the person's left)
        sidem = (azs > 0) if tk["side"] == "left" else (azs < 0) if tk["side"] == "right" else np.ones(m, bool)
        a0_ = float(tk["from"]) if tk.get("from") is not None else ef - 45.0
        wt = float(tk["amount"]) * sidem * _ss((fa - a0_) / 20.0) * (1 - _ss((fa - (eb + 5.0)) / 10.0)) * ~is_fr
        comb = comb * (1 - wt[:, None]) + wt[:, None] * _unit(np.array([0.0, 0.85, -0.5]))[None]
    fd = p.get("fade")
    fdens = np.ones(m)
    tap = np.ones(m)
    if fd and fd.get("taper"):  # a TAPER: length and lift ramp down over `taper` m above the nape line, a soft edge
        backw = _ss((fa - float(fd.get("taper_from") or 100.0)) / 30.0)
        de_ = d_in + float(fd["rough"]) * rng.normal(0, 1, m)
        t_ = _ss(np.clip(de_ / max(float(fd["taper"]), 1e-3), 0, 1))
        fl_ = float(fd["floor"])
        tap = 1 - backw * (1 - (fl_ + (1 - fl_) * t_))
        # (never under 9 mm: a lock under 8 mm is not grown, and the old fade's 4 mm locks left a bald band, G52r/G53r)
        L = np.maximum(L * tap, np.minimum(L, 0.009))
        fdens = 1 - backw * (1 - float(fd["density"])) * (1 - _ss(np.clip(de_ / (0.35 * float(fd["taper"])), 0, 1)))
    elif fd:  # a FADE at the nape: the back's locks shorten and thin out toward the nape hairline (a barber's fade)
        backw = _ss((fa - 100.0) / 30.0)
        ramp = _ss(d_in / max(float(fd["width"]), 1e-3))
        L = L * (1 - backw) + backw * (float(fd["length"]) + (L - float(fd["length"])) * ramp)
        fdens = 1 - backw * (1 - (float(fd["density"]) + (1 - float(fd["density"])) * ramp))
    if fd:
        ff = fd.get("front")
        if ff:  # a soft FRONT edge: {"width": m, "density": 0..1}: fewer strands rooted within `width` of the front
            # hairline (in front of fa 100 deg), so the tips combed over it lie on sparse roots, not a dense wall (Garrett)
            frw = 1 - _ss((fa - 80.0) / 30.0)
            rf = _ss(d_in / max(float(ff.get("width", 0.012)), 1e-3))
            fdens = fdens * (1 - frw * (1 - (float(ff.get("density", 0.3)) + (1 - float(ff.get("density", 0.3))) * rf)))
            if ff.get("reach") is not None:  # forward-combed front: tips end about `reach` m past the line
                rch = float(ff["reach"]) * rng.uniform(0.3, 1.7, m)  # (one reach for all: a cut edge, a bowl's lip)
                # "row": m (optional): the reach cut only on the locks rooted within `row` of the line (the hairline
                # row); the front behind it keeps its own length, so it has length to stand off from (Garrett: reach
                # .002 on the whole front left no front height, 6 mm vs the photo's 14.5)
                rw_ = frw if ff.get("row") is None else frw * (1 - _ss(d_in / max(float(ff["row"]), 1e-4)))
                L = L * (1 - rw_) + rw_ * np.minimum(L, d_in + rch)
    if wh and float(wh.get("thin") or 0.0) > 0:  # the WHORL's scalp show: fewer roots at its centre
        Wc_ = sc.point(np.array([float(wh["at"][0]) % 360.0]), np.array([float(wh["at"][1])]), 0.0005)[0]
        dw_ = np.linalg.norm(P0 - Wc_, axis=1)
        fdens = fdens * (1 - float(wh["thin"]) * np.exp(-0.5 * (dw_ / max(float(wh["thin_radius"]), 1e-3)) ** 2))
    sw = p.get("swoop")
    wsw = np.zeros(m)
    if sw:  # a front lock lifting off the forehead and curving up and back (over to one side): a weight that is 1
        # at the hairline at `at` deg and fades over `span` deg and `depth` m into the scalp
        fs = np.abs(((az - float(sw["at"]) + 180) % 360) - 180)
        wsw = (1 - _ss(fs / float(sw["span"]))) * (1 - _ss(d_in / float(sw["depth"]))) * ~is_fr
        comb = comb * (1 - wsw[:, None]) + wsw[:, None] * _unit(np.array([0.9 * float(sw["sweep"]), 0.55, 0.85]))[None]
        L = L + float(sw["length"]) * wsw
    tang = comb - (comb * nrm).sum(1, keepdims=True) * nrm
    bad = np.linalg.norm(tang, axis=1) < 1e-3
    tang[bad] = np.cross(nrm[bad], [1.0, 0, 0])
    tang = _unit(tang)
    messy_ = by_region(p["messy"], 0.15)  # (a number, or per region: a crop tousled on top, combed down at the back)
    turn = rng.uniform(-1, 1, m) * messy_ * np.pi / 2 * (1 - wsw)  # (a swoop is combed: its locks in step)
    tang = _unit(tang * np.cos(turn)[:, None] + np.cross(nrm, tang) * np.sin(turn)[:, None])
    out_r = np.clip(by_region(p["out"], 0.0), 0, 1)
    out = float(out_r.mean())
    outi = np.clip(out_r + messy_ * rng.uniform(-0.3, 0.3, m), 0, 1)
    outi[is_fr] = np.minimum(outi[is_fr], 0.25)
    lay_v = p.get("lay", 0.0)
    if isinstance(lay_v, dict) and "top" in lay_v:
        # "top"'s region weight is full from 42 deg of elevation, i.e. on the upper SIDES of the head too: laid there,
        # the sides lost 6.7 mm of width (Garrett). The top's lay counts only where the scalp is the head's top
        # (LAY_EL); below it that share of the weight takes the sides' lay.
        base_ = 0.0  # (regions left out: the default, not the mean of those given)
        up_ = _ss((el - hair_loose.LAY_EL[0]) / (hair_loose.LAY_EL[1] - hair_loose.LAY_EL[0]))
        vals_ = [float(lay_v.get(r_, base_)) for r_ in REGIONS]
        it_, is_ = REGIONS.index("top"), REGIONS.index("sides")
        lay = sum(W[:, i_] * vals_[i_] for i_ in range(len(REGIONS)) if i_ != it_)
        lay = (lay + W[:, it_] * (up_ * vals_[it_] + (1 - up_) * vals_[is_])) / np.maximum(W.sum(1), 1e-9)
        lay = np.clip(lay, 0, 1)
    else:
        lay = np.clip(by_region(lay_v, 0.0), 0, 1)
    lay[is_fr] = 0.0
    if sw:
        # the lift is UP and back, not along the scalp's normal (on the forehead that points forward: a cowlick
        # poking out past the brow in profile); the lock keeps a little lay so its wave rolls back over the head
        outi = outi * (1 - wsw)
        lay = lay * (1 - wsw) + float(sw["lay"]) * wsw
    d = _unit(tang * (1 - outi)[:, None] + nrm * (outi + 0.12 * (1 - lay))[:, None])
    if sw:
        d = _unit(d + (float(sw["rise"]) * 2.0 * wsw)[:, None] * _unit(np.array([0.0, 0.45, 1.0]))[None])
    stiff = np.clip(by_region(p["stiff"], 0.3), 0, 1)
    if fr:
        stiff[is_fr] = float(fr["stiff"])
    if sw:
        stiff = stiff * (1 - wsw) + float(sw["stiff"]) * wsw
    kg = (1 - stiff) ** 3 * 400.0  # how fast the direction falls, per metre
    bd = p.get("bend")
    hasb = np.zeros(m, bool)
    if bd:  # the BEND profile: rise straight for `rise` m, then turn by `angle` toward the comb and lie over
        rise_b = np.clip(by_region(bd["rise"], 0.0), 0.0, 0.05) * ~is_fr * (wsw < 0.05)
        if float(bd.get("from") or 0.0) > 0:  # the rise comes in from the hairline over `from` m: the hairline row lies,
            # the roots behind it rise and their lie covers it (seen from the front, a rising row reads as bristles)
            # (2026-10-16, G73-G76: a SHORT rise near the line, ramped toward 0, still bent by the full angle: the
            # hairline row hooked. The ramp now gates the bend itself: no bend where it is under GATE, those lie
            # as plain locks of their region; the rise ramps in from there)
            w_b = _ss(d_in / float(bd["from"]))
            rise_b = np.where(w_b >= hair_loose.BEND_GATE, rise_b * w_b, 0.0)
        hasb = rise_b > 0.001
        up_b = np.clip(by_region(bd["up"], hair_loose.BEND["up"]), 0.0, 1.0)[:, None]
        u_b = _unit(nrm * up_b + tang * (1 - up_b))  # the rise direction
        tw_ = bd.get("toward")
        if tw_ is None:
            tw_b = tang
        elif isinstance(tw_, dict):  # per region; regions left out lie along their comb (G75: one toward for all
            # turned the top's bend locks sideways too, profile lay 31 -> 74)
            tw_b = sum(W[:, i_:i_ + 1] * (_unit(np.asarray(tw_[r_], float))[None] if r_ in tw_ else tang)
                       for i_, r_ in enumerate(REGIONS)) / np.maximum(W.sum(1), 1e-9)[:, None]
        else:
            tw_b = np.broadcast_to(_unit(np.asarray(tw_, float)), tang.shape)
        v_b = tw_b - (tw_b * u_b).sum(1, keepdims=True) * u_b  # the comb (or `toward`), square to the rise
        v_b = np.where((np.linalg.norm(v_b, axis=1) < 1e-6)[:, None], np.cross(u_b, [1.0, 0, 0]), v_b)
        v_b = _unit(v_b)
        ang_b = np.radians(np.clip(by_region(bd["angle"], hair_loose.BEND["angle"]), 0.0, 170.0))[:, None]
        lie_b = _unit(np.cos(ang_b) * u_b + np.sin(ang_b) * v_b)  # the direction after the bend
        lay_b = np.clip(by_region(bd["lay"], hair_loose.BEND["lay"]), 0.0, 1.0)
        arc_b = max(float(bd["arc"]), 1e-4)
        d[hasb] = u_b[hasb]
    # layers: locks rooted higher (and further from the hairline) lie over the ones under them
    rank = np.clip((el - line.min()) / max(90.0 - line.min(), 1.0), 0, 1)
    layer = 0.7 * rank + 0.3 * rng.uniform(0, 1, m)
    # lift: one number, or per region (a short cut stands off the skull by region: a lifted top over clipped sides)
    lift = np.clip(by_region(p["lift"], hair_loose.LOOSE["lift"]), 0.0, 0.05) * tap
    # body: one number, or per region (fuller at the sides than on top)
    target = lift + np.clip(by_region(p["body"], hair_loose.LOOSE["body"]), 0.0, 0.06) * layer
    target[is_fr] = 0.004 + 0.006 * layer[is_fr]
    # the lift's profile along the lock (defaults: full lift within 3 cm, kept to the tip; body only on the way down)
    ramp_ = np.clip(by_region(p["lift_ramp"], 0.03), 0.002, 0.2)
    fall_ = np.clip(by_region(p["lift_fall"], 0.0), 0.0, 1.0)
    along_ = np.clip(by_region(p["body_along"], 0.0), 0.0, 1.0)
    if fr:
        fall_[is_fr], along_[is_fr] = 0.0, 0.0
    tr_ = p.get("trace")
    tr_w = np.zeros(m)
    if tr_ and len(tr_["samples"]):  # the traced outline: per-lock weight by root region, samples as unit vectors
        tS = np.asarray(tr_["samples"], float)
        from .hair import dirs as _dirs
        tV = _dirs(tS[:, 0], tS[:, 1])
        tH = tS[:, 2]
        tsig = np.radians(float(tr_["sigma"]))
        tr_w = np.clip(sum(W[:, i_] * float(tr_["regions"].get(r_, 0.0)) for i_, r_ in enumerate(REGIONS))
                       / np.maximum(W.sum(1), 1e-9), 0.0, 1.0)
        tr_under = float(tr_["under"])
        tr_rise = max(float(tr_["rise"]), 1e-3)
        # forward: a number (lean toward the face, world -y) or a world direction [x, y, z] (its length = the amount):
        # a front swept ACROSS to one side reads lying across in the front view; a lean toward the face reads vertical
        # ({"left": .., "right": ..}: per side of the head by the root's azimuth, blended over 10 deg either side of
        # the centre: a side sweep rises over the dome on one side and falls on the other)
        def _fvec(f_):
            f_ = f_ or 0.0
            return np.asarray(f_, float) if np.ndim(f_) else float(f_) * np.array([0.0, -1.0, 0.0])
        _fw = tr_.get("forward") or 0.0
        if isinstance(_fw, dict):
            bw_ = float(tr_.get("forward_blend") or 10.0)  # deg either side of the centre (10: a fan / swirl at az 0)
            wl_ = _ss(np.clip((((az + 180) % 360) - 180 + bw_) / (2 * bw_), 0, 1))[:, None]
            tr_fv = wl_ * _fvec(_fw.get("left")) + (1 - wl_) * _fvec(_fw.get("right"))
        else:
            tr_fv = np.broadcast_to(_fvec(_fw), (m, 3))
        tr_fw = float(np.abs(tr_fv).max())
        if float(tr_.get("from") or 0.0) > 0:  # the hairline row lies: the hold comes in over `from` m behind the line
            tr_w = tr_w * _ss(d_in / float(tr_["from"]))

        def traced(a_, e_):  # -> (h m, cover 0..1) at scalp directions
            V_ = _dirs(a_, e_)
            out_h, out_c = np.zeros(len(V_)), np.zeros(len(V_))
            for c0 in range(0, len(V_), 20000):
                cs = np.clip(V_[c0:c0 + 20000] @ tV.T, -1, 1)
                k_ = np.exp(-0.5 * (np.arccos(cs) / tsig) ** 2)
                sk = k_.sum(1)
                out_h[c0:c0 + 20000] = (k_ * tH[None]).sum(1) / np.maximum(sk, 1e-9)
                out_c[c0:c0 + 20000] = 1 - np.exp(-sk)
            return out_h, out_c
    n = 44
    ds = L / (n - 1)
    P = np.zeros((m, n, 3))
    P[:, 0] = P0
    ends = float(p["ends"])
    rest = np.zeros(m, bool)
    # face: one number, or {"left": .., "right": ..} (the person's own sides: one long curtain falling over a cheek while
    # the other side is tucked, hair-heads): per lock by the side its root is on
    if isinstance(p["face"], dict):
        azs_ = ((az + 180) % 360) - 180
        face_l = np.where(azs_ >= 0, float(p["face"].get("left", 1.0)), float(p["face"].get("right", 1.0)))
    else:
        face_l = np.full(m, float(p["face"]))
    face_l = np.clip(face_l, 0, 1.6)  # (over 1: further back than the cheek, to the ear at ~1.5)
    # ... and only for hair long enough to reach the face: the rule steers face-framing LENGTHS; short front hair that
    # ends at the hairline (a crop's forward-lying front) was turned aside into a swirl (Garrett G3). Off below
    # FACE_MIN_LEN, full from FACE_MIN_LEN + 2 cm
    face_l = face_l * _ss((L - hair_loose.FACE_MIN_LEN) / 0.02)
    face = float(face_l.max())
    side0 = np.where(away != 0, away, np.where(rng.uniform(size=m) < 0.5, -1.0, 1.0))
    axis_xy = sc.C[:2] + np.array([0.0, 0.02])
    for k in range(1, n):
        s = ds * k
        t = k / (n - 1)
        d = _unit(d + (kg * ds)[:, None] * hair_loose.DOWN)
        lay_k = lay
        if hasb.any():  # bend locks: no lay on the way up, their own lay after the bend
            pre_b = hasb & (s - ds < rise_b + arc_b)
            lay_k = np.where(pre_b, 0.0, np.where(hasb, lay_b, lay))
        if lay_k.any():  # laid: the direction's outward part (off the head, about its centre) is combed away
            rn_ = _unit(P[:, k - 1] - sc.C)
            d = _unit(d - (lay_k * np.maximum((d * rn_).sum(1), 0.0))[:, None] * rn_)
        if hasb.any() and pre_b.any():  # rising, then turning over `arc` m (no gravity on the way up)
            b_ = _ss((s - 0.5 * ds - rise_b) / arc_b)[:, None]
            d[pre_b] = _unit(u_b * (1 - b_) + lie_b * b_)[pre_b]
        if rest.any():  # lying on a shoulder: hair slides off it to the front or the back, never out along the arm
            # (long hair fanned out over both arms to the elbows)
            sx = np.sign(P[:, k - 1, 0] - sc.C[0])
            outw = rest & (d[:, 0] * sx > 0)
            d[outw, 0] *= 0.1
            sy = np.where(P[:, k - 1, 1] - sc.C[1] > 0.0, 1.0, -1.0)
            d[rest, 1] += 0.7 * sy[rest]
            d = _unit(d)
        if ends and t > 0.7:
            rad = np.zeros((m, 3))
            rad[:, :2] = P[:, k - 1, :2] - axis_xy
            d = _unit(d - ends * 0.35 * _ss((t - 0.7) / 0.3) * _unit(rad) * ~is_fr[:, None])
        q = P[:, k - 1] + d * ds[:, None]
        # the mass builds up as locks come down over the ones rooted under them (not at their own roots: lifted
        # there, the top stood up in tufts along the parting)
        lift_s = lift * _ss(s / ramp_) * (1 - fall_ * _ss((s - ramp_) / np.maximum(L - ramp_, 0.01)))
        down_ = _ss((P0[:, 2] - q[:, 2]) / 0.07)
        clear = 0.0015 + lift_s + (target - lift) * (np.maximum(down_, along_ * _ss(s / np.maximum(L, 0.01))) if along_.any()
                                                     else down_)
        if face > 0:  # off the face: a point hanging in front of it, under the hairline, is turned out to its side
            a_, e_ = az_el(q - sc.C)
            sg = np.where(np.abs(q[:, 0] - sc.C[0]) > 0.004, np.sign(q[:, 0] - sc.C[0]), side0)
            f_ = np.abs(((a_ + 180) % 360) - 180)
            lim = face_l * hair_loose.FACE_AZ * _ss((_line_at(line, a_) - e_) / 12.0) * _ss((e_ + 75) / 15)
            # (a fringe hangs over the forehead on purpose; CURTAIN bangs frame the face: they keep to its sides)
            mv = (f_ < lim) & ~(is_fr & (not curtain_))
            if mv.any():
                rot = np.radians((lim - f_) * sg)[mv]  # (az grows toward +x: the head's left)
                v = q[mv] - sc.C
                c_, s_ = np.cos(rot), np.sin(rot)
                q[mv] = sc.C + np.stack([v[:, 0] * c_ - v[:, 1] * s_, v[:, 0] * s_ + v[:, 1] * c_, v[:, 2]], 1)
        if tk is not None and wt.any():  # tucked: between the ear's top and its lobe the hair passes BEHIND the ear
            a_, e_ = az_el(q - sc.C)
            as_ = ((a_ + 180) % 360) - 180
            f_ = np.abs(as_)
            top_ = float(er["top"]) if er else sc.C[2] - 0.01
            lobe_ = float(er["lobe"]) if er else sc.C[2] - 0.06
            band = (q[:, 2] > lobe_ - 0.015) & (q[:, 2] < top_ + 0.025)
            lim = (eb + 10.0) * band
            mv = (wt > 0.05) & (f_ < lim) & (f_ > 20.0)
            if mv.any():
                rot = np.radians((lim - f_) * wt * np.sign(as_))[mv]  # (+ az = toward the back on the left side)
                v = q[mv] - sc.C
                c_, s_ = np.cos(rot), np.sin(rot)
                q[mv] = sc.C + np.stack([v[:, 0] * c_ - v[:, 1] * s_, v[:, 0] * s_ + v[:, 1] * c_, v[:, 2]], 1)
        if col is not None:
            low = q[:, 2] < sc.C[2] - 0.12
            rest = low & (col.at(q) < clear + 0.002) & (col.grad(q)[:, 2] > 0.45) & ~is_fr
            # over the SCALP the clearance is the scalp's own (out along its rays); the body's field only where
            # something else is still inside it (an ear) or off the scalp (neck, shoulders). The collider's gradient
            # over the back of the head tilts ~10 deg up, and on short hair (0.5 mm steps) the push outweighed the
            # step: crop locks there climbed the scalp, a rosette / bare whorl seen from behind (Garrett, every round
            # since hair-garrett; 19 of 66 back-centre locks rose, none without the collider)
            a_, e_, h_ = sc.coords(q)
            from .hair import dirs
            over = (e_ > sc.EL[0] + 3) & ~low
            qs = q + (np.maximum(clear - h_, 0) * over)[:, None] * dirs(a_, e_)
            # (the body sits ~1 mm outside the scalp rays everywhere: only a real intrusion, an ear, hands over to it)
            need = ~over | (col.at(qs) < 0.3 * clear - 0.001)
            if need.any():
                qs[need] = col.push(qs[need], clear[need] if np.ndim(clear) else clear)
            q = qs
        else:
            a_, e_, h_ = sc.coords(q)
            from .hair import dirs
            q = q + (np.maximum(clear - h_, 0) * (e_ > sc.EL[0] + 3))[:, None] * dirs(a_, e_)
        if tr_w.any():  # held at the traced outline's height (layered under it), reached over `rise` from the root
            it = np.nonzero(tr_w > 0.01)[0]
            from .hair import dirs as _dirs
            a_, e_, h_ = sc.coords(q[it])
            ht, cv = traced(a_, e_)
            ht = ht * (tr_under + (1 - tr_under) * layer[it]) * _ss((s[it] if np.ndim(s) else s) / tr_rise)
            ht = np.maximum(ht, clear[it] if np.ndim(clear) else clear)
            nd_ = _dirs(a_, e_)
            if tr_fw > 0:  # forward: the front's hold reaches its height moving FORWARD over the hairline (a projected
                # forelock), not straight up off the scalp (a rise the front view sees as vertical strokes)
                fv_ = tr_fv[it]
                fwd_ = fv_ - (nd_ * fv_).sum(1)[:, None] * nd_
                nd_ = _unit(nd_ + (np.linalg.norm(fv_, axis=1) * W[it, 0])[:, None] * _unit(fwd_))
            q[it] = q[it] + ((tr_w[it] * cv) * (ht - h_))[:, None] * nd_
        d = _unit(q - P[:, k - 1])
        P[:, k] = P[:, k - 1] + d * ds[:, None]
    locks = {}
    from .hair_grow import _grey
    gq = g.get("grey") or {}
    GR = sum(W[:, i_] * float(gq.get(r_, 0.0)) for i_, r_ in enumerate(REGIONS)) / np.maximum(W.sum(1), 1e-9)
    w0 = float(p["width"]) * sp
    order = np.argsort(-el)
    for j, i in enumerate(order):
        Q = P[i]
        lvl = (fr or {}).get("level") if is_fr[i] else p.get("level")
        if lvl is not None:  # a straight cut: the lock ends where it crosses the level (a little uneven)
            z = Q[:, 2] - sc.C[2] - float(lvl) - float(p["uneven"]) * rng.uniform(-0.006, 0.006)
            below = np.nonzero(z < 0)[0]
            below = below[below > 3]
            if len(below):
                b = int(below[0])
                f = z[b - 1] / max(z[b - 1] - z[b], 1e-9)
                Q = np.vstack([Q[:b], Q[b - 1] + f * (Q[b] - Q[b - 1])])
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
        if s[-1] < 0.008:
            continue
        # (a bend lock: points every 4 mm, so the bend is a bend and not a chord)
        npt = int(np.clip(round(s[-1] / (0.004 if hasb[i] else 0.02)) + 3, 5, 16))
        si = np.linspace(0, s[-1], npt)
        Q = np.stack([np.interp(si, s, Q[:, c]) for c in range(3)], 1)
        # a lock standing out of the head fans as it goes (an afro's surface is further apart than its roots)
        rr = np.linalg.norm(Q - sc.C, axis=1)
        fan = np.clip(rr / max(rr[0], 1e-6), 1.0, 2.5) if out > 0.5 else None
        short = s[-1] < 0.05
        lk = {"tier": "loose", "space": "xyz", "pts": [[round(float(v), 4) for v in q] for q in Q - sc.C],
              "free": 1.0, "width": round(float(w0 * (1 + 0.3 * float(p["uneven"]) * rng.uniform(-1, 1))), 4),
              "thickness": float(p["thickness"]) * (0.6 if is_fr[i] and not curtain_ else 1.0), "taper": 0.2 if lvl is not None else 0.35,
              "belly": 0.4, "root": 0.7, "cup": 0.0}
        if fan is not None:
            lk["radius"] = [round(float(v), 3) for v in fan]
        if short:
            lk["strands"] = {"tip_spread": 0.6}
        if sw and wsw[i] > 0.3:  # one lock with body: broader, thicker, strands kept together to the tip, no wave
            k_ = 1 + (float(sw["body"]) - 1) * float(wsw[i])
            lk["width"] = round(lk["width"] * k_, 4)
            lk["thickness"] = round(lk["thickness"] * k_, 4)
            lk["strands"] = {"tip_spread": 0.15, "wave": 0.0, "random": 0.1}
            lk["swoop"] = round(float(wsw[i]), 3)  # (game cards: the swoop gets its own lock cards, hair.cards_job)
        if fdens[i] < 0.995:  # the fade: fewer strands toward the nape hairline
            lk["strands"] = {**(lk.get("strands") or {}), "density": round(float(fdens[i]), 3)}
        gy = max(_grey(g, float(az[i]), float(el[i]), line), float(GR[i]))  # greying temples / sideburns / regions
        if gy > 0.01:
            lk["grey"] = round(gy, 3)
        locks[("lf" if is_fr[i] else "l") + str(j)] = lk
    return locks
