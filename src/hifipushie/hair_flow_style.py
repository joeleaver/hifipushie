"""The style: its parameters and `style`. Part of hair flow (hair_flow.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import hair_flow
from .hair_tied import _ss_t

def _deep(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = _deep(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def style_params(tied: dict) -> dict:
    bad = set(tied) - set(hair_flow.TIED)
    if bad:
        raise ValueError(f"hair tied: unknown keys {sorted(bad)} (have {', '.join(sorted(hair_flow.TIED))})")
    p = {**hair_flow.TIED, **tied}
    tl = p["tail"]
    if tl is False or tl is None:
        tl = {"kind": "none"}
    if isinstance(tl, str):
        tl = {"kind": tl}
    bad = set(tl) - set(hair_flow.TAIL)
    if bad:
        raise ValueError(f"hair tied tail: unknown keys {sorted(bad)} (have {', '.join(sorted(hair_flow.TAIL))})")
    p["tail"] = {**hair_flow.TAIL, **tl}
    if p["tail"]["kind"] not in ("tail", "bun", "plait", "none"):
        raise ValueError(f"hair tied tail.kind {p['tail']['kind']!r}: one of tail, bun, plait, none")
    if not isinstance(p["tie"], (int, float)) and p["tie"] not in hair_flow.HEIGHTS:
        raise ValueError(f"hair tied tie {p['tie']!r}: one of {', '.join(hair_flow.HEIGHTS)} or degrees")
    if not isinstance(p["side"], (int, float)) and p["side"] not in hair_flow.SIDES:
        raise ValueError(f"hair tied side {p['side']!r}: one of centre, left, right or degrees")
    if p["part"] not in ("centre", "center", "left", "right", "none"):
        raise ValueError(f"hair tied part {p['part']!r}: one of centre, left, right, none")
    if p["ears"] not in ("tucked", "covered"):
        raise ValueError(f"hair tied ears {p['ears']!r}: tucked or covered")
    return p


def style(tied: dict) -> dict:
    """{"tie": .., "parting": .., "strands": .., "loose": ..?}: what a `groom.tied` style makes (hair_tied's tie, the
    groom's parting, strand dials under the spec's own, loose hair for half up)."""
    p = style_params(tied)
    el = float(p["tie"]) if isinstance(p["tie"], (int, float)) else hair_flow.HEIGHTS[p["tie"]]
    off = float(p["side"]) if isinstance(p["side"], (int, float)) else hair_flow.SIDES[p["side"]]
    az = (180.0 - off) % 360.0
    T = float(np.clip(p["tightness"], 0, 1))
    lo = 1.0 - T
    lift = lo if p["lift"] is None else float(np.clip(p["lift"], 0, 1))
    N = float(np.clip(p["neatness"], 0, 1))
    me = 1.0 - N
    hs = float(np.clip(0.8 - 0.3 * N if p["hairline"] is None else p["hairline"], 0, 1))
    tl = p["tail"]
    wave = float(np.clip(tl["wave"], 0, 1))
    fu = float(np.clip(tl["fullness"], 0, 1))
    # (by the wave: a straight sleek tail is brushed. At 0.25 + 0.5 x wave a sleek high ponytail ended in chopped
    # chunks at five heights, th_S1)
    to_ = float(np.clip(0.05 + 0.75 * wave if tl.get("tousle") is None else tl["tousle"], 0, 1))
    full = 0.018 + 0.042 * fu
    gather = {"mode": "flow", "spacing": 0.02, "uneven": round(0.2 + 0.6 * me, 3),
              "puff": round(0.002 + 0.016 * lift, 4), "root_lift": round(0.0015 + 0.008 * lift, 4),
              "body": round(0.005 + 0.005 * lo, 4), "sag": round(2.6 * lo, 3), "overhang": round(22.0 * lo, 2),
              "ears": 14.0 if p["ears"] == "covered" else 0.0, "part_length": round(0.035 + 0.06 * lo, 4),  # (the groom's parting below: the same length)
              "hairline_strands": {"density": 1.6, "roots": 0.3}, "feather": 1.0,
              "edge": round(hs, 3), "zig": round(0.0045 * hs, 4),  # (x 1.6 with volume, below)
              "strands": {"wave": round(0.004 + 0.008 * lo, 4), "wavelength": 0.07, "random": 0.8, "flat": 1.5,
                          "flyaway": 0.0}}
    vol = p["volume"]
    up = float(_ss_t((el - 5.0) / 25.0))  # the tie is ABOVE most of the roots: a high ponytail, a top knot, a man bun
    vol_given = vol is not None
    if vol is None:
        # (round two, NO REGRESSIONS: hair pulled UP to a tie does not fall from its roots, and layers there were
        # radial ridges round the hairline with scalp specks at the crown (th_V9a3 / b3); half up left a bare pit
        # behind the crown (th_V9a5). By default those styles are what they were before the word)
        vol = 0.0 if p["half"] else lift * (1.0 - up)
    if isinstance(vol, (int, float)) and not isinstance(vol, bool):
        vol = {"amount": float(vol)}
    bad = set(vol) - set(hair_flow.VOLUME)
    if bad:
        raise ValueError(f"hair tied volume: unknown keys {sorted(bad)} (have {', '.join(sorted(hair_flow.VOLUME))})")
    vol = {**hair_flow.VOLUME, **vol}
    V = float(np.clip(vol["amount"], 0, 1))
    if V > 0.02:
        v_root = float(np.clip(vol["root"], 0, 1))
        gather["volume"] = {
            "crown": round(hair_flow.VOLUME_M[0] * V * float(vol["crown"]), 4), "side": round(hair_flow.VOLUME_M[1] * V * float(vol["sides"]), 4),
            "nape": round(hair_flow.VOLUME_M[2] * V * float(vol["nape"]), 4), "rise": round(0.03 - 0.022 * v_root, 4),
            # (asked for on an up-style: a smooth pouf: no fall, one shell, no separate locks)
            "arc": round(float(np.clip(V * (1.0 - up) if vol["arc"] is None else vol["arc"], 0, 1)), 3),
            "layers": round(float(np.clip((0.7 * (1.0 - up)) if vol["layers"] is None else vol["layers"], 0, 1)), 3),
            # (0.4 at full: at 1 each lock's height swelled and sank along it and at the crown's silhouette the stacked
            # waves were dark wavy wires, th_W06)
            "locks": round(float(np.clip((0.4 * min(V / 0.3, 1.0) * (1.0 - up)) if vol["locks"] is None else vol["locks"], 0, 1)), 3),
            "cross": round(float(np.clip(min(V / 0.3, 1.0) if vol["cross"] is None else vol["cross"], 0, 1)), 3),
            "hold": round(float(np.clip(lo if vol["hold"] is None else vol["hold"], 0, 1)), 3)}
        # (the dome is the volume's now: lift's few mm of puff under it would only add to the top layer)
        gather["puff"] = round(gather["puff"] * (1.0 - min(V / 0.3, 1.0)), 4)
        # (hair with body is looser hair: its strands wave a little more on the head)
        gather["strands"]["wave"] = round(gather["strands"]["wave"] + 0.006 * V, 4)
        gather["zig"] = round(gather["zig"] * (1.0 + 0.6 * min(V / 0.3, 1.0)), 4)
    frn = p["front"]
    if isinstance(frn, (int, float)) and not isinstance(frn, bool):
        frn = {"looseness": float(frn), "drape": float(frn)}
    frn = frn or {}
    bad = set(frn) - {"looseness", "drape", "locks"}
    if bad:
        raise ValueError(f"hair tied front: unknown keys {sorted(bad)} (have looseness, drape, locks)")
    f_lo = float(np.clip(frn.get("looseness") or 0.0, 0, 1))
    f_dr = float(np.clip(f_lo if frn.get("drape") is None else frn["drape"], 0, 1))
    f_n = int(round(3 * f_lo)) if frn.get("locks") is None else int(frn["locks"])
    if f_lo > 0 or f_dr > 0:
        gather["front"] = {"loose": round(f_lo * T, 3), "drape": round(f_dr, 3)}  # (x T: loose only against a tight head)
    v_g = gather.get("volume") or {}
    # (a full head arrives at the tie standing off the scalp: the hair bridges from the dome to the band; + 12 mm at
    # most: at 4.4 cm off the scalp the hair rooted round the tie left a bare pit behind it, th_V9a5 half up)
    tie = {"at": [round(az, 1), el], "out": round(0.022 + 0.012 * lo + min(1.2 * float(v_g.get("side", 0.0)) * float(v_g.get("hold", 0.0)), 0.012 if (p["half"] or el > 5.0) else 0.02), 4),
           "escape": 0, "gather": gather}
    kind = tl["kind"]
    if kind == "none":
        tie["tail"] = False
    else:
        tail_ = {"length": float(tl["length"]), "fullness": round(full, 4), "locks": int(round(26 + 30 * fu)),
                 "uneven": round(0.3 + 0.7 * me, 3), "taper": 0.3,
                 "strands": {"wave": round(0.03 * wave, 4), "wavelength": 0.16, "random": 0.7, "clump": 0.35, "flat": 2.5,
                             "clump_size": 0.008, "tips": 1.0, "tip_spread": 0.1}}
        if kind == "bun":
            tail_.update({"coil": 2.2, "coil_radius": round(0.02 + 0.02 * tl["fullness"], 4), "length": max(float(tl["length"]), 0.2)})
        elif kind == "plait":
            tail_.update({"plait": True, "stiff": 0.3, "fullness": round(0.6 * full, 4)})
        else:
            # a tail hangs: it stands out of a high tight tie a little longer than out of a low loose one
            # ... and it has VOLUME (tesshair4): the radius set along it (bulge), every lock its own wave, locks a
            # little apart toward their ends, an uneven end; the strands of a lock end over its last third and its
            # section stays open (thin locks that taper = strings, th_W1; all strands to the end = planks)
            tail_.update({"hang": True, "sun_out": 1, "stiff": round(0.2 + 0.1 * float(np.clip((el + 10) / 60, 0, 1)) + 0.04 * T, 3),
                          "spread": round(0.25 + 0.45 * fu, 3), "sway": round(0.012 * wave, 4),
                          "sway_length": 0.21, "flick": round(0.01 * wave + 0.006 * fu, 4),
                          "bulge": 1.0, "lock_wave": round(0.001 + 0.012 * wave, 4),
                          "lock_wavelength": round(0.12 - 0.025 * wave, 4), "air": round(0.002 + 0.004 * fu, 4),
                          "uneven": round(max(0.3 + 0.7 * me, 0.35 + 0.3 * fu), 3), "taper": round(0.3 - 0.15 * fu + 0.25 * to_, 3),
                          # (tesshair6: the tousle is SOFT: no flick of its own, open ends, locks loosened out of
                          # the bundle, strays up to 16 cm; as pointed wisps that flicked out it was stiff straw)
                          "ragged": round(0.25 + 0.6 * to_, 3), "strays": int(round((14 + 90 * to_) * (0.5 + fu))),
                          "stray_length": [0.04, round(0.08 + 0.1 * to_, 3)], "soft": round(float(np.clip(0.1 + 1.27 * to_, 0, 1)), 3),
                          # (- 0.15: in step, a tail's locks read as wide ribbons from behind, th_W06 .. W11)
                          "in_step": round(0.55 - 0.3 * to_, 3),
                          "strands": {"wave": round(0.006 * wave, 4), "wavelength": 0.16, "random": 1.0,
                                      # (tousled ends are POINTED wisps: strands gather toward their tips (free.
                                      # clump_shape) and do not open again; open, each lock ended as a flat 2 cm
                                      # chunk, a chopped broom from behind, th_T52)
                                      # (tesshair6: that was the straw. Soft clumps that stay OPEN to their ends,
                                      # the end ragged by lock lengths and strands ending one by one; and drawn
                                      # FINE (part transparent) at twice the count: air between hairs, not locks)
                                      "clump": round((0.3 - 0.15 * fu) * (1 - 0.6 * to_), 3), "flat": 2.5, "clump_size": 0.006,
                                      "tips": 0.9, "tip_spread": round(0.6 + 0.3 * to_, 3), "fine": round(0.35 + 0.3 * to_, 3),
                                      # (more strands than its share: thin, a full tail is strings with the backdrop
                                      # between them)
                                      "density": round(1.4 + 1.2 * to_, 2)}})
            if tl["to"] == "shoulder":  # brought forward over the shoulder on the tie's side (the left when centred)
                sd = 1.0 if off >= 0 else -1.0
                tail_["dir"] = [round(0.75 * sd, 3), -0.35, -0.55]
            elif tl["to"] != "back":
                raise ValueError(f"hair tied tail.to {tl['to']!r}: back or shoulder")
        tie["tail"] = tail_
    wsp = p["wisps"]
    if wsp is None:
        wsp = round(float(np.clip(1.25 * (me - 0.1), 0, 1)), 3)
    if isinstance(wsp, (int, float)) and not isinstance(wsp, bool):
        wsp = {"amount": float(wsp)}
    if wsp:
        bad = set(wsp) - set(hair_flow.WISP_STYLE)
        if bad:
            raise ValueError(f"hair tied wisps: unknown keys {sorted(bad)} (have {', '.join(sorted(hair_flow.WISP_STYLE))})")
        wsp = {**hair_flow.WISP_STYLE, **wsp}
        am, so = float(np.clip(wsp["amount"], 0, 1)), float(np.clip(wsp["softness"], 0, 1))
        n_w = int(round(24 * am))
        if n_w > 0:
            # (a loose front: its wisps are thicker and longer and fewer are tucked: from the front they must READ
            # against skin, and 6-20 fine hairs a clump were a faint fuzz there)
            # (under hair with VOLUME the clumps that lie on the skin are SEEN, the lifted mass no longer covers
            # them: 36 clumps of 14-37 half-transparent hairs on the forehead's corners were a grey veil, th_V75..80.
            # Fewer, thinner there; the escaping hair is the curls')
            vk = min(V / 0.3, 1.0) if V > 0.02 else 0.0
            tie["wisps"] = {"count": int(round(n_w * (1 + 0.5 * f_lo) * (1 - 0.55 * vk))), "where": list(wsp["where"]),
                            "length": [float(wsp["length"][0]), float(wsp["length"][1]) * (1 + 0.4 * f_lo)],
                            "softness": so, "hairs": [int(round((6 + 8 * f_lo) * (1 - 0.4 * vk))),
                                                      int(round((14 + 14 * so + 22 * f_lo) * (1 - 0.55 * vk)))],
                            "curls": int(round(9 * am)) if wsp["curls"] is None else int(wsp["curls"]),
                            # the halo: fine hairs standing off the top layer (and over the part): with volume
                            "halo": int(round(420 * vk * (1.0 - up))) if wsp["halo"] is None else int(wsp["halo"]),
                            "tuck": round(0.45 - 0.2 * f_lo, 3), "over": round(0.004 + 0.006 * lift, 4),
                            # (none by default toward a high tie: the lock cannot lie back over the temple, it
                            # hangs down the cheek as a strap, th_S5)
                            "loose": (int(round(2.5 * am)) if el < 30.0 else 0) if wsp["loose"] is None else int(wsp["loose"])}
    if hs > 0:  # the hairline's own baby hairs belong to the EDGE, not to the wisps: a neat head has them too
        w0 = tie.get("wisps") or {"count": 0, "where": list(hair_flow.WISP_STYLE["where"]), "length": list(hair_flow.WISP_STYLE["length"]),
                                  "softness": 0.6, "hairs": [6, 20], "tuck": 0.3, "over": 0.006}
        tie["wisps"] = {**w0, "baby": int(round(70 * hs))}
    if f_n > 0 and el < 30.0:  # (toward a high tie a lock cannot lie back over the temple: none)
        w0 = tie.get("wisps") or {"count": 0, "where": list(hair_flow.WISP_STYLE["where"]), "length": list(hair_flow.WISP_STYLE["length"]),
                                  "softness": 0.6, "hairs": [6, 20], "tuck": 0.3, "over": 0.006}
        tie["wisps"] = {**w0, "swoop": f_n, "drape": round(f_dr, 3)}
    es = p["escaped"]
    if es is None:
        es = 0
    if isinstance(es, (int, float)):
        es = {"count": int(es)}
    if es and es.get("count"):
        tie["escaped"] = {"where": ["ear", "temple", "nape", "ear"], "length": [0.04, 0.12], "curve": 0.3, **es}
    out = {"parting": {"side": "none"} if p["part"] == "none" else
           {"side": "centre" if p["part"] == "center" else p["part"], "offset": 0.03, "length": round(0.035 + 0.06 * lo, 4),
            "width": 0.004 if V <= 0.02 else 0.0025, "depth": 0.2},
           # (+ by the volume: hair that stands off the head is not combed flat; its strands wander, a few leave it)
           "strands": {**hair_flow.STRANDS, "loose": round(0.15 + 0.6 * me + 0.35 * V, 3), "frizz": round(0.08 + 0.25 * me + 0.1 * V, 3),
                       "flyaway": round(0.03 + 0.25 * me + 0.25 * V, 3), "halo": round(0.45 * me + 0.12 * V, 3), "baby": round(0.5 + 2.5 * me, 2),
                       "clump": 0.2,
                       # (under hair with volume the scalp's tint is SEEN at the forehead's corners (the mass stands
                       # up behind the line instead of lying over it): its 2 cm ramp was a grey veil over skin,
                       # th_V75..79 (isolated: not the scalp layer's strands, not the edge band). Full by 7 mm)
                       "soft": round(0.022 - 0.006 * min(V / 0.3, 1.0), 4),  # (7 mm was a hard dark edge at the temples, th_W04)
                       # (the tail: a full one is airier and frizzier whatever the head's neatness; its sub clumps
                       # swing out of step by `wave`)
                       # (tousle is NOT strand wander: at loose 0.45 every strand of the tail wriggled on its own, a
                       # crimped wet mop, th_T51; the tousle is in the locks: ragged, strays, flyaways)
                       "free": {"loose": round(0.1 + 0.25 * me + 0.2 * fu, 3),
                                "frizz": round(0.1 + 0.3 * me + 0.3 * fu + 0.2 * to_, 3),
                                "flyaway": round(0.15 + 0.7 * me + 0.25 * fu + 0.1 * to_, 3), "stray": round(0.6 + 0.3 * to_, 3),
                                # (sub clumps each on their own swing were pasta inside the locks: nearly in step)
                                "wave": round(0.008 * wave, 4), "wavelength": 0.1, "random": 0.35,
                                "clump_shape": 0.6, "tip_spread": 0.6},
                       # (thickness 1.0 against the head's 0.7: at the head's strand width a clump of 6-28 hairs was a faint
                       # fuzz in EEVEE and nearly gone in Cycles, th_T47)
                       "wisp": {"loose": 0.25, "frizz": 0.2, "wave": round(0.004 + 0.004 * f_lo, 4), "wavelength": 0.08,
                                "random": 1.0, "thickness": round(1.0 + 0.4 * f_lo, 2)}}}
    if p["half"]:
        gather["above"] = 0.012
        out["loose"] = {"length": float(p["length"]), "below": 0.03, "lift": 0.004, "face": 1.0}
    d = p.get("detail") or {}
    bad = set(d) - {"tie", "strands", "parting", "loose"}
    if bad:
        raise ValueError(f"hair tied detail: unknown keys {sorted(bad)} (have tie, strands, parting, loose)")
    out["tie"] = _deep(tie, d.get("tie") or {})
    for k_ in ("strands", "parting", "loose"):
        if d.get(k_):
            out[k_] = _deep(out.get(k_) or {}, d[k_])
    return out
