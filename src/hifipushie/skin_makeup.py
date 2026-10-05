"""Make-up as layers over the skin's own (skin.makeup), in the order it is put on. Each product changes colour AND
finish (roughness, specular, metallic), like the real thing; the skin's relief (pores, lines) stays on top of it.

Every item is a number (its amount / coverage, 0..1) or an object {"amount", "color": sRGB (default: from the skin's
own tone), "finish", "where": [zones], "mask": [paint mask entries], ...}:
  foundation  {"amount": coverage, "finish": "matte" | "natural" | "dewy", "color"}: evens the face's colour zones,
              mottling and spots toward one tone; matte is rougher (powder), dewy smoother.
  concealer   amount: lighter under the eyes.
  contour     {"amount", "color"}: a darker tone under the cheekbones, along the jaw and the sides of the nose.
  blush       {"amount", "color"}: on the cheekbones / apples of the cheeks, soft-edged.
  highlight   {"amount"}: paler and smoother on cheekbone tops, nose bridge, cupid's bow.
  eyeshadow   {"amount", "color", "finish": "matte" | "shimmer" | "metallic", "reach": 1.0}: lid to crease.
  eyeliner    {"amount", "color", "width": m (0.0012), "wing": m (0)}: along the upper lash line, with a wing.
  mascara     amount: darker, thicker lash lines.
  brows       {"amount", "color"}: the brows filled in.
  lipstick    {"amount", "color", "finish": "matte" | "satin" | "gloss"}.
  nails       {"color", "finish": "gloss" | "matte"}: polish.
"""
from __future__ import annotations

import numpy as np

from .spec import SpecError

ITEMS = ("foundation", "concealer", "contour", "blush", "highlight", "eyeshadow", "eyeliner", "mascara", "brows",
         "lipstick", "nails")
FINISH = {"matte": 0.62, "natural": 0.48, "satin": 0.4, "dewy": 0.33, "shimmer": 0.32, "metallic": 0.28, "gloss": 0.12}


def build(spec, p, J, layer, T, ctx) -> None:
    from .skin_features import _hex, _opt, _zones, hair_default
    from .skin import interocular
    mk = p["makeup"]
    bad = set(mk) - set(ITEMS)
    if bad:
        raise SpecError(f"skin makeup: unknown {sorted(bad)} (have {', '.join(ITEMS)})")
    if not mk:
        return
    t = p["tone"]
    dark = t["melanin"]

    def item(name, extra=()):
        o = _opt(mk.get(name), f"makeup.{name}", ("color", "finish", *extra))
        if o and "finish" in o and o["finish"] not in FINISH:
            raise SpecError(f"skin makeup.{name}: finish is one of {', '.join(FINISH)}")
        return o

    def where(o, default):
        return [{"mask": _zones(o.get("where") or default)}]

    if ctx["face"]:
        io = interocular(J)
        o = item("foundation")
        if o:
            a = float(np.clip(o["amount"], 0, 1))
            col = _hex(o["color"]) if "color" in o else T(blood=0.9)
            layer("makeup_foundation", o.get("mask"), pre=True, color=col, opacity=0.8 * a, roughness=FINISH[o.get("finish", "natural")],
                  mask=where(o, ["face", "neck"]) + [{"zone": "lips", "blend": "subtract"}, {"mask": _zones(["eyelid", "eye_corner"], 0.7), "blend": "subtract", "weight": 0.5}])
        o = item("concealer")
        if o:
            layer("makeup_concealer", o.get("mask"), pre=True, color=_hex(o["color"]) if "color" in o else T(melanin=0.8, blood=0.75),
                  opacity=0.6 * o["amount"], mask=where(o, ["under_eye", "eye_corner"]))
        o = item("contour")
        if o:
            col = _hex(o["color"]) if "color" in o else T(melanin=1.9, blood=0.9, grey=0.15)
            pts = []
            for s, sx in ((".L", 1), (".R", -1)):
                pts.append([{"at": f"lm_jaw_1{s}", "offset": [round(-0.12 * sx * io, 5), round(-0.25 * io, 5), round(0.3 * io, 5)]},
                            {"at": f"lm_mouth_corner{s}", "offset": [round(0.45 * sx * io, 5), round(0.15 * io, 5), round(0.25 * io, 5)]}])
            m = [{"spot": {"at": q, "radius": [round(0.2 * io, 5), round(0.11 * io, 5)], "soft": 0.95, "line": True}, **({"blend": "max"} if i else {})}
                 for i, q in enumerate(pts)]
            m += [{"mask": _zones(["jaw"], 0.8), "blend": "max", "weight": 0.5}, {"mask": _zones(["nose_wing"], 0.9), "blend": "max", "weight": 0.35},
                  {"mask": _zones(["temple"]), "blend": "max", "weight": 0.4}]
            layer("makeup_contour", o.get("mask"), pre=True, color=col, opacity=0.42 * o["amount"], mask=[{"mask": _zones(o["where"])}] if o.get("where") else m)
        o = item("blush")
        if o:
            # blush shifts the skin's own pigment toward blood (a given colour is mixed half-way with that): on dark skin a
            # pink paint reads as a patch, more blood in the same melanin reads as a flush
            own = T(blood=4.5 + 2.0 * dark, oxygenation=0.9, melanin=1.0)
            col = [round(0.5 * a + 0.5 * b, 4) for a, b in zip(_hex(o["color"]), own)] if "color" in o else own
            layer("makeup_blush", o.get("mask"), pre=True, color=col, opacity=0.36 * o["amount"],
                  mask=[{"mask": _zones(o.get("where") or ["cheekbone", "cheek"], 1.3)}, {"levels": [0.15, 1.0, 0.45]}, {"blur": 0.006}])
        o = item("highlight")
        if o:
            layer("makeup_highlight", o.get("mask"), pre=True, color=T(melanin=0.5, blood=0.7), opacity=0.35 * o["amount"],
                  roughness=0.26, specular=0.6, mask=[{"mask": _zones(o.get("where") or ["cheekbone", "nose_bridge", "philtrum"], 0.6)}])
        o = item("eyeshadow", ("reach",))
        if o:
            col = _hex(o.get("color", "#6b4a3a"))
            fin = o.get("finish", "matte")
            reach = float(o.get("reach", 1.0))
            extra = {"metallic": 0.7} if fin == "metallic" else ({"specular": 0.7} if fin == "shimmer" else {})
            layer("makeup_eyeshadow", o.get("mask"), pre=True, color=col, opacity=0.8 * o["amount"], roughness=FINISH[fin], **extra,
                  mask=[{"mask": _zones(o.get("where") or ["eyelid"], 1.15 * reach)}])
            layer("makeup_eyeshadow_blend", o.get("mask"), pre=True, color=col, opacity=0.22 * o["amount"],
                  mask=[{"mask": _zones(o.get("where") or ["eyelid"], 1.4 * reach)}])
        o = item("eyeliner", ("width", "wing"))
        if o:
            col = _hex(o.get("color", "#120e0d"))
            w = float(o.get("width", 0.0012))
            wing = float(o.get("wing", 0.0))
            k = w / 0.0012
            lines = [{"zone": {"name": "lash_upper", "grow": round(0.8 * k, 3)}}]  # along the upper lid's margin
            if wing > 0:
                for sd, sx in ((".L", 1), (".R", -1)):
                    P = [{"at": f"lm_eye_outer{sd}", "offset": [0, round(-0.025 * io, 5), round(0.012 * io, 5)]},
                         {"at": f"lm_eye_outer{sd}", "offset": [round(sx * 0.75 * wing, 5), round(-0.02 * io + 0.45 * wing, 5), round(0.012 * io + 0.55 * wing, 5)]}]
                    lines.append({"spot": {"at": P, "radius": [round(1.1 * w, 6), round(0.35 * w, 6)], "soft": 0.5, "line": True}, "blend": "max"})
            layer("makeup_eyeliner", o.get("mask"), color=col, opacity=0.95 * min(o["amount"], 1), roughness=0.4, mask=lines)
        o = item("mascara")
        if o:
            layer("makeup_mascara", o.get("mask"), color=_hex(o.get("color", "#0d0b0a")), opacity=0.9 * min(o["amount"], 1),
                  mask=[{"zone": {"name": "lash_upper", "grow": 1.5}}, {"zone": {"name": "lash_lower", "grow": 1.2}, "blend": "max", "weight": 0.6}])
        o = item("brows")
        if o:
            col = _hex(o["color"]) if "color" in o else hair_default(t, min(p["age"], 40))
            layer("makeup_brows", o.get("mask"), pre=True, color=col, opacity=0.6 * o["amount"], roughness=0.55, mask=_zones(["brow"], 0.95))
        o = item("lipstick")
        if o:
            fin = o.get("finish", "satin")
            extra = {"specular": 0.75} if fin == "gloss" else {}
            layer("makeup_lipstick", o.get("mask"), pre=True, color=_hex(o.get("color", "#9c2b35")), opacity=min(0.95 * o["amount"], 1.0),
                  roughness=FINISH[fin], **extra, mask=[{"zone": {"name": "lips", "grow": 0.9}}])
    if ctx["hands"]:
        o = item("nails")
        if o:
            fin = o.get("finish", "gloss")
            layer("makeup_nails", o.get("mask"), pre=True, color=_hex(o.get("color", "#a8232d")), opacity=min(o["amount"], 1.0),
                  roughness=FINISH.get(fin, 0.12), specular=0.7, mask=_zones(["nails"]))


def reference() -> str:
    return "MAKEUP (skin.makeup):\n" + __doc__.split("\n\n", 1)[1].strip()
