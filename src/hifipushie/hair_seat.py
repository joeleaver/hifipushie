"""Seating a groom: fitting it to a head, carrying it to another, reseating locks, the tie style. Part of hair
(hair.py has the overview)."""
from __future__ import annotations

import copy
import json
import re

import numpy as np

from . import store
from . import hair_head
from . import hair
from .hair import HairError
from .hair_groom import ear, head_ref
from .hair_head import Scalp

def fit_to_head(g: dict, sc: Scalp) -> dict:
    """groom.fit = head_ref() of the head the groom was made on: every length / volume / offset in metres scales by
    this head's size over that one, and traced hairline heights (front_points [az, z]) move with the head's centre and
    scale about it. Without `fit` the groom is used as written (metres). A groom carried from a 14% bigger head kept
    its absolute lengths and volumes and read as a mop on the smaller one (Garrett, 2026-10-09)."""
    ref = g.get("fit")
    if not ref:
        return g
    k = float(np.median(sc.R)) / float(ref["r"])
    k_tie = float(np.median(sc.R)) / float(ref["abs_r"]) if ref.get("abs_r") else 1.0
    if abs(k - 1.0) < 2e-4 and abs(k_tie - 1.0) < 2e-4 and np.allclose(sc.C, ref["c"], rtol=0, atol=2e-5):
        return g  # (head_ref rounds to 0.01 mm)
    import copy as _copy
    g = _copy.deepcopy(g)

    def scale(d, path, k=k, unitless=hair._UNITLESS):
        node = d
        for key in path[:-1]:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                return
        if not isinstance(node, dict) or path[-1] not in node or node[path[-1]] is None:
            return
        v = node[path[-1]]
        if isinstance(v, dict):
            node[path[-1]] = {a: (b * k if isinstance(b, (int, float)) and not isinstance(b, bool) and a not in unitless
                                  else b) for a, b in v.items()}
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            node[path[-1]] = v * k
        elif isinstance(v, list) and all(isinstance(x, (int, float)) for x in v):
            node[path[-1]] = [x * k for x in v]

    for path in hair._METRE_KEYS:
        scale(g, path)
    if abs(k_tie - 1.0) >= 2e-4:
        for path, unitless in hair._TIE_KEYS.items():
            scale(g, path, k_tie, unitless)
    fp = (g.get("hairline") or {}).get("front_points")
    if fp:
        c0, c1 = float(ref["c"][2]), float(sc.C[2])
        g["hairline"]["front_points"] = [[a, c1 + (z - c0) * k] for a, z in fp]
    g.pop("fit", None)
    return g


def carry(src: str, src_spec: dict | None = None, sc: Scalp | None = None) -> dict:
    """A copy of model `src`'s hair to wear on another head: groom.fit stamped with `src`'s head when the groom has
    none. Grooms are written on one head: traced hairline heights (front_points [az, z]) are world metres and the
    grown locks are [az, el, h] about that head's scalp centre. Worn as written on another head, the locks moved
    with the new centre and the hairline stayed put: ts_t28's groom on Tess's solved head (centre 4.4 mm lower)
    stood the hairline 4 mm up the brow over roots 4 mm lower, a bare V with scalp streaks (2026-10-10)."""
    import copy as _copy
    sp = store.load(src) if src_spec is None else src_spec
    h = _copy.deepcopy(sp.get("hair") or {})
    g = h.get("groom")
    if g is not None and (not g.get("fit") or not g["fit"].get("abs_r")):
        sc = sc if sc is not None else hair_head.scalp(src, sp)
        # abs_r: the head the tie's absolute metres (_TIE_KEYS) were grown at; kept once stamped (they stay relative
        # to that head through later carries)
        g["fit"] = {**(g.get("fit") or head_ref(sc)), "abs_r": round(float(np.median(sc.R)), 5)}
    return h


def _ear_warp(sa: Scalp, sb: Scalp):
    """(az, el) on head A -> (az, el) on head B that carries A's ear onto B's (both sides): hair that passed over the
    top of A's ear passes over B's. Without it, tp_h3's ear (its top 0.15 R higher than tess_a1's) stood in the way of
    W18's hair and lifted it into a ledge at the temples. Identity where an ear isn't found."""
    ea, eb = ear(sa), ear(sb)
    if not ea or not eb:
        return lambda a, e: (a, e)
    ca, cb = np.asarray(ea["cells"], float), np.asarray(eb["cells"], float)
    a_mid, b_mid = 0.5 * (ea["front"] + ea["back"]), 0.5 * (eb["front"] + eb["back"])
    half = 0.5 * max(ea["back"] - ea["front"], eb["back"] - eb["front"]) + 10.0
    ta, la, tb, lb = ca[:, 1].max(), ca[:, 1].min(), cb[:, 1].max(), cb[:, 1].min()
    mid_a = 0.5 * (a_mid + b_mid)

    def warp(a, e):  # (elevation only: the ears' azimuths differ by a degree or two)
        a, e = np.asarray(a, float), np.asarray(e, float)
        g = np.interp(e, [la, ta, ta + hair.SEAT_EAR_FADE[0]], [lb - la, tb - ta, 0.0])
        de = np.zeros_like(e)
        for mid in (mid_a, 360.0 - mid_a):
            dz = np.abs((a - mid + 180.0) % 360.0 - 180.0)
            w = np.clip(1.0 - (dz - half) / hair.SEAT_EAR_FADE[1], 0.0, 1.0)
            de += w * w * (3 - 2 * w) * g
        return a, np.clip(e + de, -89.0, 89.0)
    return warp


def seat_locks(src_spec: dict, sa: Scalp, sb: Scalp) -> dict:
    """The source's GROWN locks worn on another head, every lock kept (the same wisps, curls, tail locks and their
    lengths, which a regrow re-rolls: tie_hair(carry_from) on a new head gave other wisps their long lengths and the
    approved face-framing ones came out short, hair-cards 2026-10-14). Near the scalp a point keeps its address on the
    scalp (az, el) at its height x k (k = the new scalp's median radius over the old one's), so the hair sits on the
    new skull's own shape; points far off the scalp move with the head as a whole (C_new + k (P - C_old)); widths,
    thicknesses and the strands' metre dials scale by k."""
    from . import hair_spec
    import copy as _copy
    k = float(np.median(sb.R)) / float(np.median(sa.R))
    out = {}
    warp = _ear_warp(sa, sb)

    def move(P):
        P = np.asarray(P, float).reshape(-1, 3)
        a, e, hh = sa.coords(P)
        a2, e2 = warp(a, e)
        near = sb.point(a2, e2, hh * k)
        far = np.asarray(sb.C, float) + k * (P - np.asarray(sa.C, float))
        w = np.clip((hh - hair.SEAT_NEAR) / (hair.SEAT_FAR - hair.SEAT_NEAR), 0.0, 1.0)
        w = (w * w * (3 - 2 * w))[:, None]
        return (1 - w) * near + w * far

    for n, lk in (hair_spec.hair_of(src_spec).get("locks") or {}).items():
        lk = _copy.deepcopy(lk)
        lk["pts"] = hair_spec.lock_address(sb, lk, move(hair_spec.lock_world(sa, lk, lk["pts"])))
        if lk.get("core"):
            lk["core"] = hair_spec.lock_address(sb, lk, move(hair_spec.lock_world(sa, lk, lk["core"])))
        if lk.get("handles"):
            hs = []
            for hd in lk["handles"]:
                if hd:
                    ab = hair_spec.lock_address(sb, lk, move(hair_spec.lock_world(sa, lk, [hd[:3], hd[3:]])))
                    hs.append(ab[0] + ab[1])
                else:
                    hs.append(hd)
            lk["handles"] = hs
        for key in ("width", "thickness", "cup"):
            if isinstance(lk.get(key), (int, float)):
                lk[key] = round(float(lk[key]) * k, 5)
        if isinstance(lk.get("radius"), list):
            lk["radius"] = [round(float(r) * k, 5) for r in lk["radius"]]
        st = lk.get("strands")
        if isinstance(st, dict):
            for key in hair.SEAT_STRAND_M:
                if isinstance(st.get(key), (int, float)):
                    st[key] = round(float(st[key]) * k, 5)
        out[n] = lk
    return out


def reseat(name: str, src: str, note: str = "") -> dict:
    """Wear model `src`'s APPROVED hair on `name`'s head as it is, lock for lock (seat_locks), instead of regrowing it
    from its style (tie_hair carry_from: same words, but a new head re-rolls which lock gets which length, and the
    approved look is lost). The groom (style words, look, strand dials, hairline) comes along via carry, so later
    riffs regrow from the same words on this head. Returns {"version", "locks", "k"}."""
    from . import hair_spec
    sp = store.load(src)
    spec = store.load(name)
    sa, sb = hair_head.scalp(src, sp), hair_head.scalp(name, spec)
    h = carry(src, sp, sa)
    h["locks"] = seat_locks(sp, sa, sb)
    h.pop("removed", None)
    from . import hair_route
    h["head"] = hair_route.head_key(sb)
    spec["hair"] = h
    if (sp.get("parts") or {}).get("hair"):
        spec.setdefault("parts", {})["hair"] = json.loads(json.dumps(sp["parts"]["hair"]))
    hair_spec.validate(spec)
    v = store.save(name, spec, note or f"hair: {src}'s locks re-seated")
    return {"version": v, "locks": len(h["locks"]), "k": round(float(np.median(sb.R) / np.median(sa.R)), 4)}


def tie_style(name: str, style: dict | None = None, carry_from: str | None = None, look: dict | None = None,
              note: str = "") -> dict:
    """A tied-back hairstyle on model `name` from a STYLE (hair_flow.TIED: tie height + side, tightness, lift, part,
    ears, tail, escaped, neatness, half): `style` is merged into the model's groom.tied (a riff names only what
    changes; no tied style yet = hair_flow's defaults, an ordinary low ponytail), the hair becomes a strand groom and
    is regrown. `carry_from`: first wear that model's hair (hairline, look, strand dials, its tied style; hair.carry
    scales it to this head). Any groom.tie / loose the model had is replaced by what the style makes."""
    from . import hair_spec
    from . import hair_flow
    spec = store.load(name)
    if carry_from:
        src = store.load(carry_from)
        hc_ = carry(carry_from, src)
        hc_.pop("locks", None)
        hc_.pop("removed", None)
        spec["hair"] = hc_
        if (src.get("parts") or {}).get("hair"):
            spec.setdefault("parts", {})["hair"] = copy.deepcopy(src["parts"]["hair"])
    h = spec.setdefault("hair", {})
    if h.get("style") not in ("strands", "cards"):
        h["style"] = "strands"
    g = h.setdefault("groom", {})
    for k in ("tie", "loose"):
        g.pop(k, None)
    g["tied"] = hair_spec.merge_patch(g.get("tied") or {}, style or {})
    (g.get("parting") or {}).pop("side", None)
    if look:
        h["look"] = hair_spec.merge_patch(h.get("look") or {}, look)
    try:
        made = hair_flow.style(g["tied"])
    except ValueError as e:
        raise HairError(str(e)) from None
    store._dir(name).mkdir(parents=True, exist_ok=True)
    hair_spec.validate(spec)
    store.save(name, spec, note or "hair: tied style")
    r = hair_spec.groom(name, replace=True, note=note or "hair: tied style")
    kinds: dict = {}
    for n in store.load(name)["hair"]["locks"]:
        m = re.match(r"t\d*([a-z]+)", n)
        k_ = m.group(1) if m else "l" if re.fullmatch(r"l\d+", n) else n
        kinds[k_] = kinds.get(k_, 0) + 1
    return {**r, "tied": g["tied"], "made": made,
            "kinds": {{"g": "gather", "t": "tail", "e": "escaped hairs", "w": "wisps", "wb": "baby hairs", "wl": "loose locks", "ws": "swoop locks",
                       "y": "tail strays", "band": "band", "l": "loose"}.get(k, k): v
                      for k, v in kinds.items()}}
