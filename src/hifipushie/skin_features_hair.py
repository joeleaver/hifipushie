"""Hair on the skin: brows and lashes, stubble and its map. Part of the skin features (skin_features.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import skin_features
from .spec import SpecError
from .skin_features import _has, _hex, _opt, _shade, _zones, hair_default

def _hair(p, J, layer, T, ctx) -> None:
    h = p["hair"]
    bad = set(h) - set(skin_features.HAIR)
    if bad:
        raise SpecError(f"skin hair: unknown {sorted(bad)} (have {', '.join(skin_features.HAIR)})")
    from .skin_zones import interocular
    from . import skin_swatch
    t, age, seed = p["tone"], p["age"], p["seed"]
    base_r = ctx["base_r"]
    dflt = hair_default(t, age)
    if ctx["face"]:
        io = interocular(J)
        o = _opt(h.get("brows", 1.0), "hair.brows", ("color", "density", "thickness", "length", "grey", "drop", "soft", "arch",
                                                     "tilt", "fall", "lift", "apart", "taper", "tail", "shadow", "head",
                                                     "head_density", "clump", "opacity", "feather", "strands"))
        if o:
            col = _hex(o["color"]) if "color" in o else dflt
            g = float(o.get("grey", 0.0))
            col = [round(c + g * (0.55 - c), 4) for c in col]
            fem, masc = ctx.get("fem", 0.0), ctx.get("masc", 0.0)
            dens = float(np.clip(o.get("density", 0.8 - 0.12 * fem + 0.1 * masc) * o["amount"], 0.05, 1.6))
            thick = float(o.get("thickness", 1.0 - 0.32 * fem + 0.12 * masc)) * (1 - 0.2 * ctx["child"])
            # the brow is a drawn picture of hairs (skin_swatch.brow_image), laid from the brow's landmarks
            a_, m_, b_ = J["lm_brow_inner.L"], J["lm_brow_mid.L"], J["lm_brow_outer.L"]
            span = float(np.linalg.norm(b_ - a_))
            width = 1.22 * span
            path, (wmm, hmm) = skin_swatch.brow_image(dens, thick, float(o.get("length", 0.006)) * 1000, width * 1000, seed,
                                                       fall=float(o.get("fall", 1.0)), taper=float(o.get("taper", 0.82)),
                                                       tail=float(o.get("tail", 1.0)), head=float(o.get("head", 0.0)),
                                                       head_density=float(o.get("head_density", 0.05)),
                                                       clump=float(o.get("clump", 0.0)),
                                                       feather=float(o.get("feather", 0.0)) * 1000,   # m -> mm: the lower edge's fade
                                                       strands=float(o.get("strands", 0.0)))   # fine hairs of their own tone, tips on top
            c = 0.5 * (a_ + b_)
            c[2] = (a_[2] + 2 * m_[2] + b_[2]) / 4 - 0.02 * io
            c[1] = m_[1]
            c[2] -= float(o.get("drop", 0.0))   # a heavy brow sits on the orbital rim, its lower edge at the lid's fold
            li, lo_ = (float(x) for x in (o.get("lift") or (0.0, 0.0)))  # m: the inner head / the tail up (+) or down
            c[2] += 0.5 * (li + lo_)
            c[0] += float(o.get("apart", 0.0))  # m: both brows away from the mid-line (+: the heads less pinched)
            d = np.array([0.42, -1.0, 0.12])
            d /= np.linalg.norm(d)
            slope = float(np.degrees(np.arctan2(b_[2] - a_[2], np.linalg.norm((b_ - a_)[:2])))) * float(o.get("arch", 1.0))
            slope += float(o.get("tilt", 0.0))  # deg: the whole brow turned, its tail up (+) or down (-)
            slope += float(np.degrees(np.arctan2(lo_ - li, width)))  # (lift: the two ends placed on their own)
            soft = float(o.get("soft", 0.0))    # 0..1: hairs read less one by one (fine, greying brows: a soft mass)
            img = {"file": str(path), "at": [round(float(x), 5) for x in c], "dir": [round(float(x), 4) for x in d],
                   "size": [round(width, 5), round(width * hmm / wmm, 5)], "rotate": round(slope, 2), "depth": 0.03,
                   "mirror": True, "mirror_image": True, "channel": "alpha"}  # (unmirrored, the other brow's hairs ran
            # toward the nose: "the left eyebrow is backwards")
            # the shadow under the hairs sits where the hairs are: a brow moved off its landmarks (drop, lift, tilt,
            # apart) left the landmark zone's shadow behind as a grey band over the new brow (Tess, 2026-10-09)
            moved = any(o.get(k) for k in ("drop", "lift", "tilt", "apart"))
            ctx["brow_area"] = [{"image": img}] if moved else None   # (makeup under the brows follows the hairs too)
            layer("brow_shadow", pre=True, color=_shade(col, 1.6) if sum(col) < 0.6 else col,
                  # shadow: x the skin-level shadow under the hairs. It is uniform over the landmark zone: a strong one fills the
                  # gaps between hairs (flat inside) and the sparse head (a blunt front): r5 / r6 brows read as a "solid
                  # sticker", skincheck brow inside spread ~half the photo's, front / middle ~.9 vs ~.45 (2026-10-16)
                  opacity=min((0.3 * min(dens, 1) + 0.06 + 0.45 * soft) * float(o.get("shadow", 1.0)), 0.9),
                  # with a fading head (brows.head) the landmark zone's even shadow drew a blunt grey stencil under the sparse
                  # inner hairs (Garrett r10): the shadow then follows the hairs' own density, blurred ~1.5 mm
                  mask=[{"image": dict(img, file=str(skin_swatch.blurred(path, 1.5 * 1024 / (width * 1000))))}]
                  if float(o.get("head", 0.0)) > 0 else [{"image": img}] if moved else _zones(["brow"], 0.9 * thick))
            # matte: a drawn picture of hairs shinier than the skin read as a grey, glossy bar with a hot highlight under a
            # studio catchlight (Tess s14: brow L 58-62 vs the photo's 34-36 although its colour was #2a1c12)
            # opacity: the hairs' cover (.95 default); lower = see-through, the skin between and under the hairs reads (r10: "near-black block")
            layer("brow_hairs", color=col, opacity=round(float(o.get("opacity", 0.95)) * (1 - 0.45 * soft), 3), roughness=0.68, specular=0.22, height=0.00012, image=img)
        o = _opt(h.get("lashes", 0.7 if ctx["eyes"] else None), "hair.lashes", ("color", "width", "lower"))
        if o:
            col = _hex(o["color"]) if "color" in o else _shade(dflt, 0.45)
            op = 0.9 * min(o["amount"] * (1 + 0.45 * ctx.get("fem", 0.0)) + 0.2, 1)
            cu = ctx.get("lash_curves")
            if cu:  # with lash geometry (lashes.py): only the roots' tone, a tight line along the lash line itself (the
                # margin zone's broad band painted the waterline and the lid's edge dark: the detector read the opening
                # 1.4 mm smaller than the clay's on Garrett)
                from .skin_zones import _sp
                tubes = []
                # THE VISIBLE EYE (mouth_eye_bias -> skin, 2026-10-15): a photographed eye's width is its white plus the
                # lash line's dark frame, and that frame runs ON past the outer canthus (the lashes' roots, the lid
                # margins meeting, their shadow): ours stopped at the last lash and the eye read ~25 % short. So the
                # upper line is fullest over its outer third and goes on ~FRAME_PAST mm past the outer end along its own
                # tangent, tapering to a point; the lower line is darker than before (0.55 -> LOWER_FRAME)
                # width: x the line's radius (r4 measure: the RIM 0..1 mm outside the opening reads 3..27 L lighter than the
                # photo's on every head; the waterline alone moved it ~1.5 L: the dark frame has to reach that band)
                wd = float(o.get("width", 1.0))
                for lid, rad, wgt in (("upper", 0.0008 * wd, 1.0), ("lower", 0.0005 * wd, skin_features.LOWER_FRAME * float(o.get("lower", 1.0)))):
                    for c in cu[lid]:
                        c = np.asarray(c, float)
                        n = len(c)
                        if n < 3:
                            continue
                        out_end = abs(c[-1][0]) > abs(c[0][0])   # (the outer end: farther from the mid-line)
                        if not out_end:
                            c = c[::-1]
                        t = np.linspace(0.0, 1.0, n)
                        taper = 0.35 + 0.65 * np.sin(np.linspace(0.15, np.pi - 0.35, n)) ** 0.5
                        if lid == "upper":
                            taper = np.maximum(taper, np.clip((t - 0.55) / 0.3, 0, 1) * 1.15)   # fullest over the outer third
                            tan = c[-1] - c[-3]
                            tan /= max(float(np.linalg.norm(tan)), 1e-9)
                            ext = [c[-1] + tan * skin_features.FRAME_PAST * k / 3 for k in (1, 2, 3)]
                            c = np.vstack([c, ext])
                            taper = np.concatenate([taper, [0.8, 0.5, 0.15]])
                        tubes.append({"mask": [_sp(c, rad * taper, soft=0.6, line=True)], "vertex": True,  # (per vertex: shader stack)
                                      **({"blend": "max"} if tubes else {}),
                                      **({"weight": wgt} if wgt < 1 else {})})
                layer("lashes", color=col, opacity=op, roughness=0.42, mask=tubes)
            else:
                layer("lashes", color=col, opacity=op, roughness=0.4,
                      mask=_zones(["lash_upper"]) + [{"zone": "lash_lower", "blend": "max", "weight": 0.5}])
        o = _opt(h.get("stubble"), "hair.stubble", ("color", "length", "size", "shadow", "shadow_color", "shadow_breakup", "grey", "grey_color",
                                                     "style", "density", "patchy", "trim", "cheeks", "cheek_line", "neckline", "engine", "zones", "count",
                                                     "contrast"))
        if o and o.get("engine", "map") == "map" and "lm_jaw_1.L" in J:
            _stubble_map(ctx["spec"], p, J, o, layer, T, ctx)
            o = None
        if o:
            a = float(o["amount"])
            col = _hex(o["color"]) if "color" in o else dflt
            zs = o.get("where") or ["beard"]
            # where the beard grows: full on chin, lip and jaw, thinning up the cheek, none on the lips
            area = [{"vertex": True, "mask": _zones(zs)}, {"zone": "lips", "blend": "subtract"}]
            # hair under the skin: on light skin a cool grey-blue cast, on dark skin just darker
            cast = [round(float(c), 4) for c in (np.array(T(grey=0.75, melanin=1.0)) * (0.55 + 0.25 * t["melanin"]) + 0.2 * np.array(col))]
            sz_, shd, gr = float(o.get("size", 1.0)), float(o.get("shadow", 1.0)), float(o.get("grey", 0.0))
            cast = _hex(o["shadow_color"]) if "shadow_color" in o else cast
            layer("stubble_shadow", o.get("mask"), pre=True, color=cast, opacity=round(min(0.42 * min(a, 1.2) * shd, 0.95), 3),
                  mask=area + [{"noise": {"scale": 0.012, "range": [0.15, 0.6], "seed": seed + 100},
                                "weight": float(o.get("shadow_breakup", 0.45 if "shadow" not in o else 0.2))}])  # (breakup: 0 = an even field)
            layer("stubble", o.get("mask"), color=col, opacity=0.9 * min(0.5 + 0.5 * a, 1), roughness=min(base_r + 0.12, 0.9),
                  height=round(0.00007 * (1 + float(o.get("length", 0.0)) / 0.001), 7),
                  mask=[{"tile": {"swatch": "stubble", **({"size": round(0.012 * sz_, 5)} if sz_ != 1.0 else {}),
                                  "range": [round(0.45 - 0.35 * min(a, 1), 3), round(0.75 - 0.35 * min(a, 1), 3)]}}, {"mask": area}])
            if gr > 0:   # salt and pepper: a share of the hairs white (their own dots, another size so they never coincide)
                layer("stubble_grey", o.get("mask"), color=_hex(o.get("grey_color", "#cfcbc4")), opacity=round(0.9 * min(gr, 1.0), 3),
                      roughness=min(base_r + 0.05, 0.9), height=round(0.00007 * (1 + float(o.get("length", 0.0)) / 0.001), 7),
                      mask=[{"tile": {"swatch": "stubble", "size": round(0.012 * sz_ * 1.37, 5), "vary": False,
                                      "range": [round(0.45 - 0.35 * min(gr, 1), 3), round(0.75 - 0.35 * min(gr, 1), 3)]}}, {"mask": area}])
    o = _opt(h.get("scalp"), "hair.scalp", ("color", "hairline")) if ctx["face"] and "head" in J else None
    if o:
        from .skin_zones import interocular
        io = interocular(J)
        a = float(o["amount"])
        col = _hex(o["color"]) if "color" in o else dflt
        hl = float(o.get("hairline", 0.5))
        # the hair-bearing scalp: the cranium behind a hairline that crosses the forehead and drops in front of the ears
        hd = J["head"]
        # one ellipsoid bigger than the skull (the head joint sits at brow height, the cranium ~1.5 interoculars
        # round it): where it leaves the skull is the hairline (~35 deg up the forehead at 0.5), the nape's edge and
        # the line over the ears; two side spots bring it down in front of and behind each ear.
        cy = round((0.8 + 0.6 * (0.5 - hl)) * io, 5)
        top = [{"at": "head", "offset": [0, cy, round(1.1 * io, 5)]}]
        sides = [{"at": "head", "offset": [round(sx * 1.1 * io, 5), round(0.3 * io, 5), round(-0.05 * io, 5)]} for sx in (1, -1)]
        area = [{"spot": {"at": top + sides, "radius": [[round(1.9 * io, 5), round(2.2 * io, 5), round(2.1 * io, 5)]] +
                          [[round(0.5 * io, 5), round(0.75 * io, 5), round(0.9 * io, 5)]] * 2, "soft": 0.06}},
                {"vertex": True, "mask": _zones(["ear"], 0.9), "blend": "subtract"},
                {"breakup": {"amount": 0.12, "scale": 0.006, "sharpness": 0.5, "seed": seed + 105}}]
        cast = [round(float(c), 4) for c in (0.45 * np.array(T(grey=0.7)) * (0.5 + 0.25 * t["melanin"]) + 0.55 * np.array(col))]  # cropped hair is mostly its own colour
        # matt: cut hair scatters, it doesn't shine like the oiled skin of a bald head (left glossy it read as a grey cap)
        layer("scalp_shadow", o.get("mask"), pre=True, color=cast, opacity=min(0.75 * a, 0.9), roughness=0.85, specular=0.12, mask=area)
        layer("scalp_stubble", o.get("mask"), color=col, opacity=0.9 * min(0.5 + 0.5 * a, 1), roughness=min(base_r + 0.15, 0.9), height=0.00008,
              mask=[{"tile": {"swatch": "stubble", "size": 0.009, "range": [round(0.4 - 0.32 * min(a, 1), 3), round(0.7 - 0.32 * min(a, 1), 3)]}},
                    {"vertex": True, "mask": area}])
    o = _opt(h.get("body"), "hair.body", ("color",))
    if o:
        col = _hex(o["color"]) if "color" in o else dflt
        zs = o.get("where") or [z for z in ("forearm", "chest", "back_of_hand") if _has(z, ctx)]
        if zs:
            rot = False
            if ctx["arms"] and any(z.startswith("forearm") for z in zs):
                d = J["wrist.L"] - J["elbow.L"]
                rot = abs(d[2]) < 0.6 * np.linalg.norm(d)  # hairs lie along the limb
            lo = 0.55 - 0.35 * min(o["amount"], 1.2)
            layer("body_hair", o.get("mask"), color=col, opacity=0.75,
                  mask=[{"tile": {"swatch": "hairs", "rotate": bool(rot), "range": [round(lo, 3), round(lo + 0.35, 3)], "vary": False}}, {"vertex": True, "mask": _zones(zs)}])


def stubble_options(o: dict, age: float = 35) -> dict:
    """hair.stubble's options resolved against its style (skin_marks.STUBBLE_STYLES)."""
    from . import skin_marks
    st = o.get("style", "short")
    if st not in skin_marks.STUBBLE_STYLES:
        raise SpecError(f"skin hair.stubble: style is one of {', '.join(skin_marks.STUBBLE_STYLES)}")
    base = dict(skin_marks.STUBBLE_STYLES[st])
    a = float(o["amount"])
    zw = o.get("zones") or {}
    if not isinstance(zw, dict) or set(zw) - set(skin_marks.BEARD_ZONES):
        raise SpecError(f"skin hair.stubble: zones is {{zone: weight}} over {', '.join(skin_marks.BEARD_ZONES)}")
    zw = {k: round(float(np.clip(v, 0, 1.5)), 3) for k, v in zw.items() if abs(float(v) - 1.0) > 1e-6}
    # count: hairs per area x (1 = ~80 / cm2 where full). density is a 0..1 share of that and saturates at 1 where the beard
    # is full, so it can't make a dense beard denser: Garrett's photo stubble covers ~.5 of the chin / jaw pixels, ours .2-.25
    # at density 1 (2026-10-16). Left out of the options at 1 so existing maps keep their cache keys.
    cnt = float(np.clip(o.get("count", 1.0), 0.25, 4.0))
    return {**({"zones": zw} if zw else {}), **({"count": round(cnt, 3)} if abs(cnt - 1.0) > 1e-6 else {}),
            "length": float(o.get("length", base["length"])), "density": float(np.clip(o.get("density", base["density"]) * min(a, 1.0), 0.02, 1.0)),
            "grey": float(np.clip(o.get("grey", 0.0), 0, 1)), "patchy": float(np.clip(o.get("patchy", base["patchy"]), 0, 1)),
            "trim": float(np.clip(o.get("trim", base["trim"]), 0, 1)), "cheeks": float(np.clip(o.get("cheeks", base["cheeks"]), 0, 1)),
            "cheek_line": float(o.get("cheek_line", 0.0)), "neckline": float(o.get("neckline", 0.0)),
            "size": float(o.get("size", 1.0)), "seed": int(o.get("seed", 0)), "shadow": float(o.get("shadow", base["shadow"]))}


def _stubble_map(spec, p, J, o, layer, T, ctx) -> None:
    """Stubble as a unique map on the head (skin_marks_beard.stubble_map): the shadow of hair in the skin (per vertex,
    from the dark roots' count) + dark and white hairs as cut strokes along the growth direction, with relief."""
    from . import skin_marks_beard
    t = p["tone"]
    a = float(o["amount"])
    q = stubble_options(o, p["age"])
    path, place, _ = skin_marks_beard.stubble_map(spec, p["part"], J, q)
    col = _hex(o["color"]) if "color" in o else hair_default(t, p["age"])
    im = lambda ch: {"image": {"file": path, **place, "channel": ch}}  # noqa: E731
    lips = {"zone": {"name": "lips", "grow": 0.6}, "blend": "subtract"}   # (a crisp border: no bald halo round the lips)
    # hair seen through the skin: on light skin a cool blue-grey cast (the dark shaft under a scattering layer), on dark
    # skin just darker; the hair's own colour mixed in as it grows out
    # (a freshly shaved jaw: the cool cast; a few days' growth: the cut hairs at the surface warm it to a grey-brown, the
    # colour measured on Garrett's photo under the matched light: Lab ~45/4/13 at ~0.8 coverage)
    grow = float(np.clip(q["length"] / 0.001, 0, 1))
    # a fresh shave: dark hair under a scattering layer reads blue-grey, never olive (a greyed skin colour read as a
    # "dirty grey-green wash" to the blind reader): the skin darkened and pushed toward a cool blue-violet grey
    cool = np.array(T(grey=0.6, melanin=1.1)) * (0.58 + 0.22 * t["melanin"]) + np.array([0.08, 0.105, 0.125]) * (1 - t["melanin"])   # (neutral blue-grey: more blue read lilac)
    warm = np.array(T(grey=0.25, melanin=2.3, blood=1.05)) * (0.62 + 0.25 * t["melanin"])   # (warm grey: less read as green)
    cast = (1 - 0.35 * grow) * cool + 0.35 * grow * warm + 0.06 * grow * (np.array(col) - 0.3)   # the sub-skin shadow stays cool: the hairs carry the warmth
    lum = float(cast @ np.array([0.2126, 0.7152, 0.0722]))
    cast = lum + skin_features.CAST_SAT * (cast - lum)   # (beard minus cheek: a and b fall 3-14 on the refs, ~1 on ours before)
    cast = [round(float(c), 4) for c in np.clip(skin_features.CAST_DEPTH * cast, 0, 1)]
    cast = _hex(o["shadow_color"]) if "shadow_color" in o else cast
    # (per pixel, not pre-composited per vertex: the shadow map carries the under-skin shafts, ~0.2 mm across)
    layer("stubble_shadow", o.get("mask"), color=cast, opacity=round(min(skin_features.SHADOW_GAIN * min(a, 1.3) * q["shadow"], 0.95), 3),
          mask=[im("b"), lips])
    hgt = round(float(np.clip(0.00003 + 0.012 * q["length"], 0.00003, 0.00012)), 7)   # a hair stands ~0.1 mm proud
    r = min(ctx["base_r"] + 0.1, 0.9)
    # contrast: x the hairs' cover (1). A few days' grey stubble seen from a metre is a fine grey-brown HAZE: single hairs are
    # sub-texel, so each pixel is a low-contrast mix of skin and hair; opaque hairs read as white specks (grey) or black
    # pepper (dark) (Garrett r12). The haze's tone is then the shadow (shadow_color, shadow) under many faint hairs (count)
    k_ = float(np.clip(o.get("contrast", 1.0), 0.05, 1.0))
    layer("stubble", o.get("mask"), color=col, opacity=round(0.97 * k_, 3), roughness=r, specular=0.35, height=hgt, mask=[im("r"), lips])
    if q["grey"] > 0:
        # (white hairs near-white and opaque: #aaa39a at 0.85 was ~+14 L over the skin, "salt & pepper has no white in
        # it" (5th blind read; ref_28's white hairs are the brightest thing on the jaw). The shadow under the dark ones
        # now carries the darkening (shafts under the skin), so near-white no longer reads as ash, skin3)
        # (then "uniform bright chalk scratches", skin3's 6th read: real grey hair is translucent and a little yellow,
        # #d9d4cb at .95 -> #c8c0b2 at .8)
        layer("stubble_grey", o.get("mask"), color=_hex(o.get("grey_color", "#c8c0b2")), opacity=round(0.8 * k_, 3), roughness=r, specular=0.4,
              height=hgt, mask=[im("g"), lips])
