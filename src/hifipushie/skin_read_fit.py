"""`fit`: the skin's parameters from a read, its text, and `apply`. Part of the skin read (skin_read.py has the overview)."""
from __future__ import annotations

import copy
import time

import numpy as np

from . import skin_read
from .skin_read import _lin, _srgb, _unlab, lab
from .skin_read_context import Context, regions, shade_colour
from .skin_read_fold_fit import fold_fit
from .skin_read_params import _get, _path_set, _set, _stubble_opts, _unset
from .skin_read_reads import iris_colour, read

def fit(r: dict, groups=skin_read.DEFAULT_GROUPS, stubble: bool | None = None, log=print, prior_L: float | None = None, lid_prior: bool = True,
        prior_ab=None, prior_tone: dict | None = None, prior_face: dict | None = None, prior_x: dict | None = None,
        iris_prev=None) -> dict:
    """spec["skin"] set from a read: {"skin": the new description, "changes": [(parameter, old, new, why)], "text",
    "residual": the regions' read before / after as the forward model has it}. groups: what may change (GROUPS).
    stubble: whether a beard shadow may be ADDED to a face that has none (default: unless skin.sex says female)."""
    from scipy.optimize import least_squares
    from . import skin_marks
    from . import skin_params
    c: Context = r["ctx"]
    sk0 = copy.deepcopy(c.spec.get("skin") or {})
    sk = copy.deepcopy(sk0)
    R = regions(c)
    anchored = c.anchor["kind"] != "none"
    names = [p for g in groups for p in skin_read.GROUPS.get(g, ()) if (g != "tone" or anchored)]
    # the beard: the stubble layers' opacity scaled zone by zone (a prototype when the face has none)
    sx = sk.get("sex")
    may = (stubble if stubble is not None else (sx is None or float(sx) > 0.5)) and "stubble" in groups and getattr(c, "beard_zones", None) is not None
    st0 = _stubble_opts(sk)
    proto = False
    if "stubble" in groups and st0 is None and may:
        sk.setdefault("hair", {})["stubble"] = dict(skin_read.STUBBLE_PROTO)
        proto = True
    st_on = "stubble" in groups and _stubble_opts(sk) is not None
    bz = skin_marks.BEARD_ZONES if st_on else ()
    # the points the fit runs on, and each region's target
    reg = [k for k, x in r["regions"].items() if x["read"]]
    any_w = np.max([R[k] for k in reg], 0) * (c.w > 0)
    idx = np.flatnonzero(any_w > 0.05)
    if len(idx) > skin_read.FIT_POINTS:   # (small regions whole: lips, lids; the rest thinned)
        small = np.max([R[k] for k in reg if r["regions"][k]["px"] < 6000] or [np.zeros(len(c.w))], 0)[idx] > 0.05
        rest = np.flatnonzero(~small)
        take = np.random.default_rng(0).choice(rest, max(skin_read.FIT_POINTS - int(small.sum()), 1000), replace=False) if len(rest) > skin_read.FIT_POINTS else rest
        idx = np.sort(np.r_[idx[small], idx[take]])
    sub = c.alb.subset(idx)
    Wk = {k: (c.w[idx] * R[k][idx]) for k in reg}
    Wk = {k: w / max(w.sum(), 1e-9) for k, w in Wk.items()}
    U = {z: c.beard_zones[z][idx] for z in bz}

    def model(x, sk_=None):
        s = copy.deepcopy(sk) if sk_ is None else sk_
        for p, v in zip(names, x[:len(names)]):
            _set(s, p, v)
        scale = None
        if bz:
            M = sum(float(x[len(names) + i]) * U[z] for i, z in enumerate(bz))
            scale = {"stubble_shadow": M, "stubble": M, "stubble_grey": M}
        A = sub(s, scale=scale)
        return np.array([lab(Wk[k] @ A) for k in reg]), s

    x0 = np.array([_get(sk, p) for p in names] + [0.0 if proto else 1.0] * len(bz), float)
    lo = np.array([skin_read.BOUNDS[p][0] for p in names] + [0.0] * len(bz))
    hi = np.array([skin_read.BOUNDS[p][1] for p in names] + [2.5] * len(bz))
    x0 = np.clip(x0, lo + 1e-4, hi - 1e-4)
    m0, _ = model(x0)
    base0 = m0   # (a prototype beard starts at scale 0: the face the read was made against)
    target = base0 + np.array([r["regions"][k]["d"] for k in reg])
    sig = []
    for k in reg:
        bv = list((r["regions"][k].get("by_view") or {}).values())
        sp = np.std(bv, 0) if len(bv) > 1 else np.array([2.0, 0.6, 0.6])
        s0 = (skin_read.LIP_SIGMA_L, skin_read.SIGMA[1], skin_read.SIGMA[2]) if k.startswith("lip_") else skin_read.SIGMA
        sig.append(np.hypot(s0, sp) / np.sqrt(min(r["regions"][k]["px"], 2000.0) / 2000.0))
    sig = np.array(sig)

    # A white-balance-only anchor gives the picture's albedo up to ONE unknown factor (its exposure): that factor is a
    # free parameter of the solve (held to 1 only weakly), so the tone is found from the skin's chromaticity (in the
    # pigment model a darker skin is a more saturated one) and no layer is bent to explain a lightness nobody measured.
    free_e = "tone" in groups and anchored and bool(c.anchor.get("level"))
    np_ = len(names) + len(bz)
    # the lightness anchor (context): the plain skin's albedo L* is held to the prior tone's (the start's), loosely
    # when a known white gives the exposure; the exposure itself is then free (prior) or the white's.
    Wp = c.w[idx] * ((c.plain[idx] > 0.5) if getattr(c, "plain", None) is not None else np.max([R[z][idx] for z in skin_read.PLAIN if z in R], 0))
    Wp = Wp / max(Wp.sum(), 1e-9)
    white = c.anchor.get("lightness") == "white" and c.anchor.get("exposure") is not None
    e_mid = float(c.anchor["exposure"]) if white else 0.0
    e_sig = skin_read.WHITE_SIGMA if white else skin_read.EXPOSURE_SIGMA
    L_sig, L_bound = (skin_read.TONE_SIGMA_WHITE, skin_read.TONE_BOUND_WHITE) if white else (skin_read.TONE_SIGMA, skin_read.TONE_BOUND)

    # THE WHOLE FACE (skinfolds2): every skin zone's trusted pixels, stubble apart. Holding the PLAIN zones alone let
    # the eye-zone and lower-face layers run to their limits (Tess: eyelids 2.5, under_eye 2.5, lower_cool 1.9: a mask
    # round the eyes and a darker, yellower lower face at an unchanged "plain" lightness)
    zreg = [k for k in reg if k in skin_read.ZONES]
    Wf = c.w[idx] * (np.max([R[k][idx] for k in zreg], 0) if zreg else 0.0)
    Wf = Wf / max(Wf.sum(), 1e-9)

    def tone_stats(x):
        """(plain skin Lab, whole face Lab, {zone: its Lab - the face's}) of a candidate, the beard's shadow left out."""
        s_ = copy.deepcopy(sk)
        for p_, v_ in zip(names, x[:len(names)]):
            _set(s_, p_, v_)
        A_ = sub(s_, skip=("stubble*",))
        fl = lab(Wf @ A_)
        return lab(Wp @ A_), fl, {k: lab(Wk[k] @ A_) - fl for k in zreg}

    def plain_lab(x):
        return tone_stats(x)[0]

    def plain_L(x):
        return float(plain_lab(x)[0])

    st_start = tone_stats(np.array([_get(sk, p) for p in names], float))
    ab0 = st_start[0][1:] if prior_ab is None else np.asarray(prior_ab, float)
    C_bound = skin_read.TONE_CHROMA_WHITE if white else skin_read.TONE_CHROMA
    if prior_face is None:       # (a later round: still the FIRST round's face)
        prior_face = {"lab": [float(v_) for v_ in st_start[1]], "zones": {k: [float(v_) for v_ in o] for k, o in st_start[2].items()}}
    Lf0 = float(prior_face["lab"][0])

    # SHADE (skinfolds2): a region the picture shows darker than our render predicts is first of all in shade our
    # head does not cast (a deeper-set eye, the jaw turning from a light the fit only roughly knows), not darker
    # skin. Each region's target is the read with a shade s >= 0 taken OUT again, in the pictures' own shade colour
    # (shade_colour: darker AND warmer); s is solved for inside every residual (one number per region, closed form
    # steps), held to nothing but SHADE_SIGMA. Pigment is what remains: colour off the shade line, and lightness
    # where a beard may explain it. Before: Tess's lids (15 L darker than ours under the same light in all three
    # views), jaw and neck (7-10 L) were painted in as eyelid / under-eye / lower-face pigment up to the bounds.
    qs = shade_colour(c)
    Tlin = np.clip(_unlab(target), 1e-5, None)
    # (the PLAIN zones are the lit skin the exposure is levelled on: nearly no shade of their own, or a white's "this
    # skin is darker than you say" would be explained away as shade everywhere)
    s_sig = np.array([0.0 if k.startswith("lip_") else skin_read.SHADE_SIGMA_BEARD if (k.startswith("beard:") and st_on) else
                      skin_read.SHADE_SIGMA_PLAIN if k in skin_read.PLAIN else (skin_read.ATLAS_SHADE_SIGMA if r.get("source") == "atlas" else skin_read.SHADE_SIGMA) for k in reg])
    ZB = skin_read.ATLAS_ZONE_BOUND if r.get("source") == "atlas" else skin_read.ZONE_BOUND

    def shaded(sv, e):
        return lab(Tlin * np.exp(e + sv[:, None] * qs[None, :]))

    def shade_opt(m, e):
        sv = np.zeros(len(reg))
        on = s_sig > 0
        for _ in range(7):
            t0, t1 = shaded(sv, e), shaded(sv + 1e-3, e)
            r_ = (m - t0) / sig
            Jc = -(t1 - t0) / 1e-3 / sig
            ds = -((Jc * r_).sum(1) + sv / np.maximum(s_sig, 1e-9) ** 2) / ((Jc * Jc).sum(1) + 1.0 / np.maximum(s_sig, 1e-9) ** 2)
            sv = np.where(on, np.clip(sv + ds, 0.0, skin_read.SHADE_MAX), 0.0)
        return sv

    def resid(x):
        m, _ = model(x[:np_])
        e = float(x[np_]) if free_e else 0.0
        sv = shade_opt(m, e)
        tg = shaded(sv, e)
        bs = x[len(names):np_]
        hold = []
        if free_e:
            pl, fl, _ = tone_stats(x)
            hold = [[len(reg) ** 0.5 * (x[np_] - e_mid) / e_sig, len(reg) ** 0.5 * (float(pl[0]) - L0) / L_sig,
                     len(reg) ** 0.5 * (float(fl[0]) - Lf0) / L_sig]]
        # SHADE IS LOCAL: a face is never all in shade against its own plain skin. A quarter of the regions that may
        # carry shade must carry none (their lower quartile is held to 0). Without it exposure and shade traded on the
        # synthetic heads: exposure x 0.4-0.5 and every region "20-30 L in shade", which is a colour cast along the
        # shade colour by another name (toneval F2: plain zones 20 L off, 21 regions at the cap).
        fr_ = sv[s_sig > 0.1]
        local = [len(reg) ** 0.5 * (float(np.percentile(fr_, 25)) if len(fr_) >= 4 else 0.0) / skin_read.SHADE_LOCAL]
        return np.concatenate([((m - tg) / sig).ravel(), sv / np.maximum(s_sig, 1e-9) * (s_sig > 0), local,
                               skin_read.PRIOR * len(reg) ** 0.5 * pw * (x[:np_] - x0[:np_]) / (hi - lo)[:np_]] +
                              ([len(bz) ** 0.5 * (bs - bs.mean()) / skin_read.BEARD_EVEN] if len(bz) else []) + hold)

    L0 = float(prior_L) if prior_L is not None else float(st_start[0][0])   # (a later round: still the FIRST tone's lightness)
    pw = np.array([skin_read.PRIOR_TONE if p_.startswith("tone.") else 1.0 for p_ in names] + [1.0] * len(bz))
    if free_e:
        x0, lo, hi = np.r_[x0, e_mid], np.r_[lo, -1.2], np.r_[hi, 1.2]

    t = time.time()
    # (a start on a bound never leaves it in a trust-region reflective solve: begin a little inside)
    xi = np.clip(x0, lo + 0.06 * (hi - lo), hi - 0.06 * (hi - lo))
    if proto:
        xi[len(names):np_] = 0.5
    sol, cost = None, np.inf
    c_start = 0.5 * float((resid(xi) ** 2).sum())
    for _ in range(6):   # (the solve stops early on its step tolerance in this bounded, curved problem: restart it)
        s_ = least_squares(resid, xi, bounds=(lo, hi), diff_step=0.02, x_scale=(hi - lo), max_nfev=30, xtol=1e-5, ftol=1e-6)
        if sol is not None and s_.cost > cost - max(0.03 * (c_start - cost), 0.02):   # (the gain against what CAN change: with lips alone free the other regions hold 99 % of the cost, and 1.5 % of the total never came)
            sol = s_ if s_.cost < cost else sol
            break
        sol, cost = s_, s_.cost
        xi = np.clip(s_.x, lo + 0.01 * (hi - lo), hi - 0.01 * (hi - lo))
    # THE BOUND: the plain skin's lightness never leaves the prior's by more than L_bound; a solve that wants more gets
    # its tone back toward the prior (the other parameters as solved) and says so
    # A MOVE MUST EARN ITS PLACE: a zone / lip parameter whose return to the start costs the fit next to nothing goes
    # back (layers that multiply the tone's blood are nearly inert on a pale, bloodless tone: Tess's eyelids ran to
    # 2.5 and lower_cool to 1.97, their bounds, for 0.1 L of albedo: numbers that say "dark lids" and paint nothing,
    # until someone changes the tone)
    cost = lambda xs_: 0.5 * float((resid(xs_) ** 2).sum())  # noqa: E731
    c_now = cost(sol.x)
    for i_ in sorted((i for i, p_ in enumerate(names) if not p_.startswith("tone.")), key=lambda i: -abs(sol.x[i] - x0[i]) / (hi[i] - lo[i])):
        if abs(sol.x[i_] - x0[i_]) < 0.01 * (hi[i_] - lo[i_]):
            continue
        xt = sol.x.copy()
        xt[i_] = x0[i_]
        c_try = cost(xt)
        if c_try - c_now < skin_read.PRUNE:
            sol.x[:] = xt
            c_now = c_try
    tone_note = zone_note = None
    # THE ZONES' BOUND: no zone's offset from the face's mean leaves the prior's by more than ZONE_BOUND; the zone
    # layers' whole move is scaled back until all are inside (bisection on its share), and said
    zi = [i for i, p_ in enumerate(names) if not p_.startswith(("tone.", "lips."))]

    def zones_out(xs_):
        off = tone_stats(xs_)[2]
        bad = {}
        for k, o in off.items():
            d_ = o - np.asarray(prior_face["zones"].get(k, o), float)
            if abs(d_[0]) > ZB[0] or float(np.hypot(d_[1], d_[2])) > ZB[1]:
                bad[k] = d_
        return bad

    if zi and zreg:
        bad = zones_out(sol.x)
        if bad:
            xs, xp = sol.x.copy(), x0.copy()
            for i_ in zi:
                if prior_x and names[i_] in prior_x:
                    xp[i_] = float(np.clip(prior_x[names[i_]], lo[i_], hi[i_]))
            a_lo, a_hi = 0.0, 1.0
            for _ in range(10):
                a_ = 0.5 * (a_lo + a_hi)
                xs[zi] = xp[zi] + a_ * (sol.x[zi] - xp[zi])
                if zones_out(xs):
                    a_hi = a_
                else:
                    a_lo = a_
            xs[zi] = xp[zi] + a_lo * (sol.x[zi] - xp[zi])
            zone_note = ("the solve put " + ", ".join(f"{k} {d_[0]:+.1f} L* / {float(np.hypot(d_[1], d_[2])):.1f} a*b*" for k, d_ in bad.items()) +
                         f" from where the prior has that zone against the face (bounds {ZB[0]} L*, {ZB[1]} a*b*): "
                         f"the zone layers' move is held to {100 * a_lo:.0f} % of it")
            sol.x[:] = xs
    if free_e:
        L1 = plain_L(sol.x)
        ti = [i for i, p_ in enumerate(names) if p_.startswith("tone.")]

        def inside(xs_):
            pl, fl, _ = tone_stats(xs_)
            return (abs(float(pl[0]) - L0) <= L_bound and float(np.hypot(*(pl[1:] - ab0))) <= C_bound
                    and abs(float(fl[0]) - Lf0) <= (L_bound if white else skin_read.FACE_BOUND)
                    and float(np.hypot(*(fl[1:] - np.asarray(prior_face["lab"][1:], float)))) <= C_bound)
        if ti and not inside(sol.x):
            xs = sol.x.copy()
            # (back toward the PRIOR tone itself: in a later round the start is the last round's tone, which the new
            # read's own points may already put outside the bound: Garrett's round 2 began 5.8 from the prior)
            xp = x0.copy()
            if prior_tone:
                for i_ in ti:
                    xp[i_] = float(np.clip(prior_tone[names[i_]], lo[i_], hi[i_]))
            a_lo, a_hi = 0.0, 1.0
            for _ in range(12):                 # the largest share of the tone's move that stays inside the bound
                a_ = 0.5 * (a_lo + a_hi)
                xs[ti] = xp[ti] + a_ * (sol.x[ti] - xp[ti])
                if not inside(xs):
                    a_hi = a_
                else:
                    a_lo = a_
            xs[ti] = xp[ti] + a_lo * (sol.x[ti] - xp[ti])
            d1, d2 = plain_lab(sol.x) - np.r_[L0, ab0], plain_lab(xs) - np.r_[L0, ab0]
            f1, f2 = tone_stats(sol.x)[1] - np.asarray(prior_face["lab"], float), tone_stats(xs)[1] - np.asarray(prior_face["lab"], float)
            tone_note = (f"the solve wanted the plain skin {d1[0]:+.1f} L* / {d1[1]:+.1f} a* / {d1[2]:+.1f} b* and the whole face "
                         f"{f1[0]:+.1f} / {f1[1]:+.1f} / {f1[2]:+.1f} from the prior; held to "
                         f"{d2[0]:+.1f} / {d2[1]:+.1f} / {d2[2]:+.1f} and {f2[0]:+.1f} / {f2[1]:+.1f} / {f2[2]:+.1f} (bounds: {L_bound} L*, {C_bound} in a*b*: "
                         f"{'a known white' if white else 'a backdrop is a weak white balance, and no exposure anchor'})")
            sol.x[:] = xs
    m1, sk1 = model(sol.x[:np_])
    expo = float(np.exp(sol.x[np_])) if free_e else 1.0
    sv1 = shade_opt(m1, float(sol.x[np_]) if free_e else 0.0)
    sv0 = shade_opt(base0, 0.0)
    target0 = shaded(sv0, 0.0)             # (the start against the read with ITS shade taken out: chi2 like with like)
    target = shaded(sv1, float(sol.x[np_]) if free_e else 0.0)
    st_end = tone_stats(sol.x)
    log(f"skin_read fit: {len(names) + len(bz)} parameters over {len(reg)} regions, status {sol.status}, {time.time() - t:.0f} s; "
        f"chi2 {float((((base0 - target0) / sig) ** 2).sum()):.0f} -> {float((((m1 - target) / sig) ** 2).sum()):.0f}; shade colour q {np.round(qs, 3).tolist()}")
    changes = []
    for p, a, b in zip(names, x0, sol.x[:len(names)]):
        if abs(b - a) > 0.01 * (skin_read.BOUNDS[p][1] - skin_read.BOUNDS[p][0]):
            at = " (at its bound: the picture asks for more than this control gives)" if min(b - skin_read.BOUNDS[p][0], skin_read.BOUNDS[p][1] - b) < 2e-3 * (skin_read.BOUNDS[p][1] - skin_read.BOUNDS[p][0]) and b != a else ""
            changes.append((p, round(float(a), 3), round(float(b), 3), "region colours" + at))
        elif _path_set(sk0, p):
            _set(sk1, p, _get(sk0, p))
        else:
            _unset(sk1, sk0, p)
    if not any(ch[0].startswith("tone.") for ch in changes):   # the tone as it was written (fitzpatrick and all)
        if "tone" in sk0:
            sk1["tone"] = copy.deepcopy(sk0["tone"])
        else:
            sk1.pop("tone", None)
    # the beard's scales -> hair.stubble (zones, density)
    if bz:
        s = sol.x[len(names):np_]
        o = _stubble_opts(sk1)
        zw0 = {z: float((o.get("zones") or {}).get(z, 1.0)) for z in bz}
        v = {z: zw0[z] * float(s[i]) for i, z in enumerate(bz)}
        seen = {z: r["regions"].get(f"beard:{z}", {}).get("read", False) for z in bz}
        top = max([v[z] for z in bz if seen[z]] or [0.0])
        if top < skin_read.BEARD_MIN:
            if not proto:
                changes.append(("hair.stubble", "on", "off", "no beard shadow in the pictures"))
            sk1.get("hair", {}).pop("stubble", None)
        else:
            S = min(top, 1.0)
            zones = {z: round(float(np.clip(v[z] / top, 0, 1.5)), 2) if seen[z] else round(zw0[z], 2) for z in bz}
            from .skin_features_hair import stubble_options
            d0 = stubble_options({"amount": 1.0, **o})["density"]
            o2 = {**o, "zones": {z: w for z, w in zones.items() if abs(w - 1) > 0.03}, "density": round(float(np.clip(d0 * S, 0.02, 1.0)), 3)}
            if not o2["zones"]:
                o2.pop("zones")
            sk1.setdefault("hair", {})["stubble"] = o2
            changes.append(("hair.stubble" + (" (ADDED)" if proto else ""), {"zones": {z: round(zw0[z], 2) for z in bz}, "density": round(d0, 3)} if not proto else None,
                            {"zones": zones, "density": o2["density"]}, "the lower face's shadow by beard zone" +
                            ("; zones not seen kept: " + ", ".join(z for z in bz if not seen[z]) if not all(seen.values()) else "")))
    # freckles
    fr = r["freckles"]
    if "freckles" in groups and fr["read"]:
        new = fr["amount"] if fr["amount"] >= 0.03 else 0.0
        if abs(new - fr["have"]) > 0.02:
            f = sk1.setdefault("features", {})
            old = f.get("freckles")
            if new <= 0:
                f.pop("freckles", None)
            else:
                f["freckles"] = {**old, "amount": new} if isinstance(old, dict) else new
            changes.append(("features.freckles", fr["have"], new, f"dark specks per cm2, picture vs ours: {fr['views']}"))
    # brows: colour and density
    b = r["brows"]
    native = min((v.get("mm_per_px", 0.3) for v in c.views), default=1.0)
    if "brows" in groups and b["read"]:
        hb = (sk1.get("hair") or {}).get("brows", 1.0)
        hb = {"amount": float(hb)} if isinstance(hb, (int, float)) else dict(hb or {})
        from . import paint
        p = skin_params.params({**c.spec, "skin": sk1})
        from .skin_features import hair_default
        col0 = np.asarray(paint.colour(hb["color"]) if "color" in hb else hair_default(p["tone"], p["age"]), float)[:3]
        g = float(hb.get("grey", 0.0))
        shown = col0 + g * (0.55 - col0)
        want = _srgb(np.clip(_lin(shown) * np.asarray(b["colour_ratio"]), 0, 1))
        new = dict(hb)
        if native <= skin_read.BROW_COLOUR_MM and np.abs(lab(_lin(want)) - lab(_lin(shown))).max() > 2.0:
            new["color"] = "#" + "".join(f"{int(round(255 * float(x))):02x}" for x in np.clip(want, 0, 1))
            new["grey"] = 0.0
            changes.append(("hair.brows.color", hb.get("color", "(default)") + (f" grey {g}" if g else ""), new["color"], f"brow hair colour x {b['colour_ratio']}"))
        d0 = float(hb.get("density", 0.8 - 0.12 * p["fem"] + 0.1 * p["masc"]))
        d1 = round(float(np.clip(d0 * b["coverage_ratio"], 0.15, 1.6)), 3)
        if abs(d1 - d0) > 0.05:
            new["density"] = d1
            changes.append(("hair.brows.density", round(d0, 3), d1, f"brow band coverage x {b['coverage_ratio']}"))
        sk1.setdefault("hair", {})["brows"] = new
    # eyeballs
    if "eyeballs" in groups and sk1.get("eyes") is not False and native <= skin_read.IRIS_MM:
        from . import paint
        ey = dict(sk1.get("eyes") or {})
        e = r["eyes"].get("iris_rel") or {}
        if e.get("read"):
            c0 = np.asarray(paint.colour(ey.get("iris", "#5a3a1e")), float)[:3]
            hx0 = "#" + "".join(f"{int(round(255 * float(x))):02x}" for x in c0)
            rt = np.asarray(e["ratio"], float)
            if iris_prev is not None:
                # the SECOND read: our eye picture answers a colour change with less than the whole of it (catchlight, cornea,
                # limbal ring: Tess, blue x1.39 applied, x1.24 still missing). The share it made of the last step, per
                # channel (0.5 .. 1), is taken into this one (a secant step)
                l0, l1 = np.log(np.maximum(np.asarray(iris_prev, float), 1e-4)), np.log(np.maximum(rt, 1e-4))
                gam = np.clip(np.where(np.abs(l0) > 0.05, 1.0 - l1 / np.where(np.abs(l0) > 0.05, l0, 1.0), 1.0), 0.5, 1.0)
                rt = np.exp(l1 / gam)
            hx1 = iris_colour(c0, rt)
            if np.abs(lab(_lin(np.asarray(paint.colour(hx1), float)[:3])) - lab(_lin(c0))).max() > 2.0:
                ey["iris"] = hx1
                changes.append(("eyes.iris", hx0, hx1, f"the picture's iris ring against its sclera's bright part, over ours: x {[round(float(x), 2) for x in e['ratio']]} "
                                                       f"({e['views']} eye(s); INFERRED: the sclera taken as ours, the hue is the picture's)"))
        else:
            changes.append(("eyes.iris", ey.get("iris", "default"), ey.get("iris", "default"),
                            f"NOT READ: no view shows an iris of {skin_read.IRIS_R_PX:g} px radius with sclera beside it: the iris colour is NOT the picture's (set skin.eyes.iris by hand)"))
        if ey:
            sk1["eyes"] = ey
    if "folds" in groups and r.get("folds"):
        changes += fold_fit(sk1, r["folds"], True, lid_prior=lid_prior)
    resid_rows = {k: {"before": [round(float(x), 2) for x in (base0[i] - target0[i])], "after": [round(float(x), 2) for x in (m1[i] - target[i])]}
                  for i, k in enumerate(reg)}
    shade = {k: round(float(sv1[i]), 3) for i, k in enumerate(reg) if sv1[i] >= skin_read.SHADE_SAY}
    out = {"skin": sk1, "changes": changes, "residual": resid_rows, "exposure": round(expo, 3),
           "iris_ratio": (r["eyes"].get("iris_rel") or {}).get("ratio") if "eyeballs" in groups else None,
           "shade": {"q": [round(float(v_), 3) for v_ in qs], "regions": shade,
                     "L": {k: round(float(lab(Tlin[i])[0] - lab(Tlin[i] * np.exp(sv1[i] * qs))[0]), 1) for i, k in enumerate(reg) if sv1[i] >= skin_read.SHADE_SAY}},
           "face": {"prior": [round(float(v_), 2) for v_ in prior_face["lab"]], "fitted": [round(float(v_), 2) for v_ in st_end[1]],
                    "bound": skin_read.FACE_BOUND, "zones": {k: [round(float(v_), 2) for v_ in (o - np.asarray(prior_face["zones"].get(k, o), float))] for k, o in st_end[2].items()},
                    "note": zone_note, "prior_face": prior_face},
           "tone": {"anchor": c.anchor.get("lightness", "prior") if free_e else "not read", "prior_L": round(L0, 2),
                    "prior_ab": [round(float(x), 2) for x in ab0],
                    "fitted_L": round(float(st_end[0][0]), 2) if free_e else round(L0, 2), "bound": L_bound, "note": tone_note}}
    out["text"] = fit_text(out)
    return out


def fit_text(f: dict) -> str:
    L = ["SKIN FIT (what changed, from -> to, and the read behind it):"]
    t = f.get("tone") or {}
    if t.get("anchor") == "not read":
        L.append("  TONE: not read (no white balance in the pictures: no neutral backdrop, no white): lightness and hue stay the model's")
    elif t:
        L.append(f"  TONE LIGHTNESS: anchor = {'a known white in the picture (INFERRED albedo ' + str(skin_read.WHITE_ALBEDO) + ')' if t['anchor'] == 'white' else 'the PRIOR (the stated skin.tone)'}; "
                 f"plain skin L* {t['prior_L']} -> {t['fitted_L']} (bound +-{t['bound']}); the picture's exposure against our render x {f.get('exposure', 1.0)}"
                 + (f"; {t['note']}" if t.get("note") else ""))
    fc = f.get("face")
    if fc:
        worst = sorted(fc["zones"].items(), key=lambda kv: -max(abs(kv[1][0]) / skin_read.ZONE_BOUND[0], float(np.hypot(kv[1][1], kv[1][2])) / skin_read.ZONE_BOUND[1]))[:4]
        L.append(f"  WHOLE FACE (mean albedo of every skin zone, stubble apart): Lab {fc['prior']} -> {fc['fitted']} (bound +-{fc['bound']} L*); "
                 f"zones against the face, moved most from the prior (bounds {skin_read.ZONE_BOUND[0]} L*, {skin_read.ZONE_BOUND[1]} a*b*): " +
                 "; ".join(f"{k} {v}" for k, v in worst) + (f". HELD: {fc['note']}" if fc.get("note") else ""))
    sh = f.get("shade")
    if sh and sh["regions"]:
        L.append(f"  SHADE, NOT PIGMENT (the pictures' own shade colour: exponents {sh['q']} for r g b; these regions read darker than our "
                 "render under the fitted light predicts, along that line: taken as shade our head does not cast, and NOT painted in): " +
                 ", ".join(f"{k} {sh['L'][k]:+.1f} L*" for k in sorted(sh["regions"], key=lambda k_: -sh["regions"][k_])) +
                 ". If it is pigment (a real tan line, dark circles), set that zone's strength yourself; if it is form (deep-set eyes, "
                 "hooding, a bag), it is geometry: block-in / skin.folds")
    for p, a, b, why in f["changes"]:
        L.append(f"  {p}: {a} -> {b}   [{why}]")
    if not f["changes"]:
        L.append("  nothing: the description already matches the read within its tolerance")
    worst = sorted(f["residual"].items(), key=lambda kv: -max(abs(kv[1]["after"][1]), abs(kv[1]["after"][2]), abs(kv[1]["after"][0]) / 4))[:6]
    L.append("  what the fit leaves (ours - picture, Lab, as the forward model has it): " +
             "; ".join(f"{k} {v['after']}" for k, v in worst))
    return "\n".join(L)


def apply(name: str, out: str | None = None, groups=skin_read.DEFAULT_GROUPS, rounds: int = 2, anchor: str = "auto", stubble: bool | None = None,
          brow_shape: bool = True, log=print, tone=None, white=None) -> dict:
    """Read the references, set spec["skin"] from the read, save (onto `out`: a block-in fork of `name`, or `name`
    itself). rounds: read -> fit -> re-render -> read again (the second round corrects what the first could only
    estimate: freckle and beard densities, brow coverage). Returns {"model", "reads": [text per round], "fits",
    "skin", "text"}."""
    from . import store
    from . import blockin_models
    dst = out or name
    if out and out != name:
        blockin_models.fork(name, out, replace=True)
    reads, fits = [], []
    if tone is not None:     # a STATED tone (a Fitzpatrick type 1..6, or skin.tone's own keys): the lightness prior
        spec = store.load(dst)
        spec.setdefault("skin", {})["tone"] = {"fitzpatrick": float(tone)} if isinstance(tone, (int, float)) else dict(tone)
        store.save(dst, spec, "skin_from_reference: the stated tone (the lightness prior)")
    prior_L = prior_ab = prior_face = None
    sk_p = store.load(dst).get("skin") or {}
    prior_tone = {p_: _get(sk_p, p_) for p_ in skin_read.GROUPS["tone"]}
    prior_x = {p_: _get(sk_p, p_) for g_ in ("zones", "eyes") for p_ in skin_read.GROUPS[g_]}
    for k in range(max(int(rounds), 1)):
        r = read(dst, anchor=anchor, log=log, white=white)
        f = fit(r, groups=groups, stubble=stubble, log=log, prior_L=prior_L, prior_ab=prior_ab, prior_tone=prior_tone,
                prior_face=prior_face, prior_x=prior_x, iris_prev=fits[-1].get("iris_ratio") if fits else None)
        prior_L, prior_ab, prior_face = f["tone"]["prior_L"], f["tone"]["prior_ab"], f["face"]["prior_face"]
        reads.append(r["text"]); fits.append(f)
        spec = store.load(dst)
        spec["skin"] = f["skin"]
        if brow_shape and k == 0 and "brows" in groups:
            try:
                from . import blockin_brows
                bf = blockin_brows.fit(dst, spec)
                keep = {kk: spec["skin"]["hair"]["brows"][kk] for kk in ("color", "density", "grey") if kk in (spec["skin"].get("hair") or {}).get("brows", {})}
                spec["skin"].setdefault("hair", {})["brows"] = {**bf["brows"], **keep}
                f["text"] += "\n  " + bf["text"]
            except Exception as e:  # noqa: BLE001
                f["text"] += f"\n  brow placement NOT READ ({str(e)[:160]})"
        store.save(dst, spec, f"skin_from_reference round {k + 1}")
        log(f["text"])
        if not f["changes"]:
            break
    final = read(dst, anchor=anchor, log=log, white=white)
    text = "\n\n".join([f"{dst}: skin from the reference pictures ({len(fits)} round(s))", reads[0]] + [f["text"] for f in fits] +
                       ["AFTER:\n" + final["text"]])
    return {"model": dst, "reads": reads + [final["text"]], "fits": [{k: v for k, v in f.items()} for f in fits],
            "skin": store.load(dst).get("skin"), "text": text}
