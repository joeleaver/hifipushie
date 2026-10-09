"""Make-up as layers over the skin's own (skin.makeup), in the order an artist puts it on, each placed by the rules
make-up artists use on the face's own landmarks (seated on the surface), each with a finish (roughness, specular,
metallic) and a strength. The skin's relief (pores, lines) stays on top of all of it, so it reads as product on skin,
not paint (references: workspace/skin_refs ref_13, ref_34..39; guide(topic="skin") "Make-up").

skin.makeup = {"look": "natural" | "everyday" | "evening" (a preset: the items below, any of them overridden),
               item: amount | {"amount", "color", "finish", ...}, ...}

  foundation  {"amount": coverage, "finish": "matte" | "natural" | "dewy", "color"}: evens the face's colour zones,
              mottling and spots toward one tone (the fine marks show through 1 - 0.75 x coverage).
  concealer   amount (+ "color"): lighter, a touch peach, under the eyes and at the inner corners, the nose's wings.
  bronzer     {"amount", "color"}: warmth where the sun falls: the forehead's edges, cheekbones, the nose's bridge.
  contour     {"amount", "color", "nose": 0..1}: a cool shadow tone in the cheek's hollow under the cheekbone, from
              the ear toward the mouth's corner, stopping under the outer eye; the temples and under the jaw; the
              nose's sides with "nose".
  blush       {"amount", "color", "place": "apples" | "lifted" | "draped"}: on the apples of the cheeks swept up and
              out toward the temples (apples), higher along the cheekbone (lifted), or round from the cheek to the
              temple (draped); soft-edged, the skin's own blood colour on any tone unless "color".
  highlight   {"amount"}: paler and glossier on the cheekbone's top, the nose's bridge, the cupid's bow, the brow bone
              and the inner eye corner.
  eyeshadow   {"amount", "color" (the lid), "crease" (colour), "outer" (colour: the outer V), "finish": "matte" |
              "satin" | "shimmer" | "metallic", "reach": 1 (how far up toward the brow)}: the lid from the lash line
              to the crease, a deeper shade blended along the crease and out toward the brow's tail, the darkest in
              the outer V where crease meets lash line, the brow bone left light.
  eyeliner    {"amount", "color", "width": m (0.0012, at the outer end), "wing": m (0), "lower": 0..1}: along the
              upper lash line, thin at the inner corner and thicker outward; the wing continues the lower lash line's
              angle up toward the brow's tail; "lower" lines the outer two thirds of the lower lash line, softly.
  mascara     amount: darker, denser lash lines.
  brows       {"amount", "color"}: the brows filled in under the hairs.
  lipstick    {"amount", "color", "finish": "matte" | "satin" | "gloss" | "balm", "liner": 0..1, "liner_color",
              "overline": m (0)}: the vermilion to its border (a liner traces the border, slightly darker; "overline"
              takes it just outside); "balm" is a sheer tint with a wet shine.
  nails       {"color", "finish": "gloss" | "matte"}: polish.
"""
from __future__ import annotations

import numpy as np

from .spec import SpecError

ITEMS = ("foundation", "concealer", "bronzer", "contour", "blush", "highlight", "eyeshadow", "eyeliner", "mascara", "brows",
         "lipstick", "nails")
FINISH = {"matte": 0.62, "natural": 0.48, "satin": 0.4, "dewy": 0.33, "shimmer": 0.32, "metallic": 0.28, "gloss": 0.1,
          "balm": 0.16}
LOOKS = {
    # the "no-make-up make-up": a sheer even base where needed, a little concealer, brushed brows, mascara, a tinted balm
    "natural": {"foundation": {"amount": 0.3, "finish": "natural"}, "concealer": 0.35, "blush": {"amount": 0.35},
                "brows": 0.2, "mascara": 0.6, "lipstick": {"amount": 0.35, "finish": "balm"}},
    "everyday": {"foundation": {"amount": 0.55, "finish": "natural"}, "concealer": 0.45, "bronzer": 0.3,
                 "contour": 0.35, "blush": {"amount": 0.55}, "highlight": 0.3,
                 "eyeshadow": {"amount": 0.55, "color": "#a07a66", "crease": "#7a5848"},
                 "eyeliner": {"amount": 0.8, "width": 0.0009}, "mascara": 0.9, "brows": 0.4,
                 "lipstick": {"amount": 0.75, "color": "#b0505a", "finish": "satin"}},
    "evening": {"foundation": {"amount": 0.75, "finish": "matte"}, "concealer": 0.55, "bronzer": 0.35,
                "contour": 0.6, "blush": {"amount": 0.5, "place": "lifted"}, "highlight": 0.6,
                "eyeshadow": {"amount": 0.9, "color": "#8a6a5e", "crease": "#4e352e", "outer": "#2a1c19", "finish": "shimmer",
                              "reach": 1.15},
                "eyeliner": {"amount": 1.0, "width": 0.0015, "wing": 0.007, "lower": 0.4}, "mascara": 1.2, "brows": 0.6,
                "lipstick": {"amount": 1.0, "color": "#8e1f30", "finish": "matte", "liner": 0.6}},
}
EXTRA = {"blush": ("place",), "contour": ("nose",), "eyeshadow": ("reach", "crease", "outer"),
         "eyeliner": ("width", "wing", "lower"), "lipstick": ("liner", "liner_color", "overline")}


def resolve(mk: dict) -> dict:
    """The look's preset with the given items laid over it (an item's object merged key by key)."""
    mk = dict(mk or {})
    look = mk.pop("look", None)
    if look is None:
        return mk
    if look not in LOOKS:
        raise SpecError(f"skin makeup: look is one of {', '.join(LOOKS)}")
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in LOOKS[look].items()}
    for k, v in mk.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        elif isinstance(v, dict) and isinstance(out.get(k), (int, float)):
            out[k] = {"amount": out[k], **v}
        else:
            out[k] = v
    return out


class _Seat:
    """Points seated on the head's surface: a ray along +y (from in front) through (x, z) to the first skin it meets;
    the face's landmarks + offsets in interocular units become points ON the skin, wherever its forms put it."""

    def __init__(self, spec, part, J):
        self.ok = False
        try:
            from scipy.spatial import cKDTree
            from . import skin_marks
            V, N, _ = skin_marks.head_mesh(spec, part, J)
            V, N = np.asarray(V, float), np.asarray(N, float)
            keep = N[:, 1] < 0.35       # what faces the front or the sides
            self.V = V[keep]
            self.tree = cKDTree(self.V[:, [0, 2]])
            self.ok = True
        except Exception:  # noqa: BLE001  (no mesh: a hand-made skeleton without a head surface; landmarks as they are)
            pass

    def __call__(self, p):
        p = np.asarray(p, float)
        if not self.ok:
            return p
        idx = self.tree.query_ball_point([p[0], p[2]], 0.0015)
        if not idx:
            idx = [self.tree.query([p[0], p[2]])[1]]
        cand = self.V[idx]
        # the frontmost surface along the ray (the near cheek, not the far side of the head): smallest y, within
        # 2 cm in front of or behind the guess when one is near it
        near = cand[np.abs(cand[:, 1] - p[1]) < 0.02]
        c = (near if len(near) else cand)
        return c[np.argmin(c[:, 1])]


def build(spec, p, J, layer, T, ctx) -> None:
    from .skin_features import _hex, _opt, _zones, hair_default
    from .skin import interocular
    mk = resolve(p["makeup"])
    bad = set(mk) - set(ITEMS)
    if bad:
        raise SpecError(f"skin makeup: unknown {sorted(bad)} (have look, {', '.join(ITEMS)})")
    if not mk:
        return
    t = p["tone"]
    dark = t["melanin"]

    def item(name):
        o = _opt(mk.get(name), f"makeup.{name}", ("color", "finish", *EXTRA.get(name, ())))
        if o and "finish" in o and o["finish"] not in FINISH:
            raise SpecError(f"skin makeup.{name}: finish is one of {', '.join(FINISH)}")
        return o

    def where(o, default):
        return [{"mask": _zones(o.get("where") or default)}]

    if ctx["face"]:
        io = interocular(J)
        seat = _Seat(spec, p["part"], J)
        L = lambda n: np.asarray(J[n], float)  # noqa: E731

        def pt(base, off=(0, 0, 0)):
            """A point from a landmark (".L" side) + offset (interocular units), seated on the skin."""
            q = (L(base) if isinstance(base, str) else np.asarray(base, float)) + io * np.asarray(off, float)
            return seat(q)

        def both(points, radii, soft=0.8, line=True, scale=1.0):
            """A tapered line (or spots) through the ".L" points and its mirror: mask entries."""
            r = [round(float(x) * io * scale, 6) for x in radii]
            out = []
            for sx in (1, -1):
                P = [[round(float(c[0] * sx), 6), round(float(c[1]), 6), round(float(c[2]), 6)] for c in points]
                if sx == -1:
                    P = [seat(np.array(c)).round(6).tolist() for c in P]
                e = {"spot": {"at": P, "radius": r if line else [[x] * 3 for x in r], "soft": soft, **({"line": True} if line else {})}}
                out.append({**e, **({"blend": "max"} if out else {})})
            return out

        eo, ei = L("lm_eye_outer.L"), L("lm_eye_inner.L")
        lu, lui, luo = L("lm_lid_upper.L"), L("lm_lid_upper_in.L") if "lm_lid_upper_in.L" in J else L("lm_lid_upper.L"), \
            L("lm_lid_upper_out.L") if "lm_lid_upper_out.L" in J else L("lm_lid_upper.L")
        llo = L("lm_lid_lower_out.L") if "lm_lid_lower_out.L" in J else L("lm_lid_lower.L")
        bo, bm, bi = L("lm_brow_outer.L"), L("lm_brow_mid.L"), L("lm_brow_inner.L")
        nos, mc = L("lm_nostril.L"), L("lm_mouth_corner.L")
        pupil_x = L("eye.L")[0] if "eye.L" in J else 0.5 * (eo[0] + ei[0])
        gap = max(bm[2] - lu[2], 0.2 * io)                 # lid margin to brow
        crease_h = 0.42 * gap                               # the lid fold above the lash line

        o = item("foundation")
        if o:
            a = float(np.clip(o["amount"], 0, 1))
            col = _hex(o["color"]) if "color" in o else T(blood=0.9)
            layer("makeup_foundation", o.get("mask"), pre=True, color=col, opacity=0.8 * a, roughness=FINISH[o.get("finish", "natural")],
                  mask=where(o, ["face", "neck"]) + [{"zone": "lips", "blend": "subtract"}, {"mask": _zones(["eyelid", "eye_corner"], 0.7), "blend": "subtract", "weight": 0.5}])
        o = item("concealer")
        if o:
            col = _hex(o["color"]) if "color" in o else [round(min(c * f, 1), 4) for c, f in zip(T(melanin=0.8, blood=0.75), (1.03, 1.0, 0.95))]
            m = both([pt("lm_eye_inner.L", (0.0, -0.02, -0.08)), pt("lm_lid_lower.L", (0.0, -0.02, -0.14)), pt("lm_eye_outer.L", (0.05, 0.0, -0.12))],
                     [0.1, 0.14, 0.07], soft=0.95)
            layer("makeup_concealer", o.get("mask"), pre=True, color=col, opacity=0.55 * o["amount"],
                  mask=[{"mask": m}, {"zone": {"name": "nose_wing", "grow": 0.8}, "blend": "max", "weight": 0.5}, {"blur": round(0.05 * io, 5)}])
        o = item("bronzer")
        if o:
            col = _hex(o["color"]) if "color" in o else T(melanin=2.2, blood=1.2, yellow=0.2)
            m = both([pt("lm_brow_outer.L", (0.15, 0.1, 0.55)), pt("lm_brow_outer.L", (0.25, 0.25, 0.1))], [0.3, 0.22], soft=1.0)
            m += [{**e, "blend": "max"} for e in both([pt("lm_eye_outer.L", (0.15, 0.1, -0.4)), pt("lm_brow_outer.L", (0.15, 0.2, -0.2))], [0.2, 0.15], soft=1.0)]
            m += [{"mask": _zones(["nose_bridge"], 0.8), "blend": "max", "weight": 0.5}]
            layer("makeup_bronzer", o.get("mask"), pre=True, color=col, opacity=0.35 * o["amount"], mask=m + [{"blur": round(0.06 * io, 5)}])
        o = item("contour")
        if o:
            col = _hex(o["color"]) if "color" in o else T(melanin=1.9, blood=0.85, grey=0.25)
            # the hollow under the cheekbone: from in front of the ear's tragus down toward the mouth's corner, stopping
            # under the outer eye (never into the nasolabial fold)
            E = pt("lm_jaw_0.L", (-0.12, -0.1, -0.12))
            Q = pt(np.array([eo[0] + 0.03 * io, eo[1], nos[2] - 0.05 * io]))
            Mid = pt(0.5 * (E + Q) + io * np.array([0.0, 0.0, -0.04]))
            m = both([E, Mid, Q], [0.2, 0.16, 0.08], soft=1.0)
            m += [{**e, "blend": "max", "weight": 0.7} for e in both([pt("lm_brow_outer.L", (0.25, 0.25, 0.45)), pt("lm_brow_outer.L", (0.3, 0.35, 0.05))], [0.18, 0.12], soft=1.0)]
            m += [{"mask": _zones(["jaw"], 0.8), "blend": "max", "weight": 0.45}]
            nose_k = float(o.get("nose", 0.0))
            if nose_k > 0:
                m += [{**e, "blend": "max", "weight": round(nose_k, 3)} for e in
                      both([pt("lm_brow_inner.L", (-0.04, 0.0, -0.1)), pt("lm_nose_bridge", (0.12, 0.0, -0.35)), pt("lm_nose_tip", (0.11, 0.0, 0.12))], [0.05, 0.05, 0.04], soft=1.0)]
            layer("makeup_contour", o.get("mask"), pre=True, color=col, opacity=0.4 * o["amount"],
                  mask=([{"mask": _zones(o["where"])}] if o.get("where") else m) + [{"blur": round(0.05 * io, 5)}])
        o = item("blush")
        if o:
            # the skin's own pigment shifted toward blood (a given colour mixed half-way with that): on dark skin a pink
            # paint reads as a patch, more blood in the same melanin as a flush
            own = T(blood=4.5 + 2.0 * dark, oxygenation=0.9, melanin=1.0)
            col = [round(0.5 * a + 0.5 * b, 4) for a, b in zip(_hex(o["color"]), own)] if "color" in o else own
            place = o.get("place", "apples")
            if place not in ("apples", "lifted", "draped"):
                raise SpecError("skin makeup.blush: place is apples, lifted or draped")
            apple = np.array([pupil_x + 0.12 * io, 0.0, L("lm_lid_lower.L")[2] - 0.5 * io])
            apple[1] = L("lm_lid_lower.L")[1]
            temple = np.array([bo[0] + 0.05 * io, bo[1], eo[2] + 0.12 * io])
            if place == "apples":
                pts, rr = [pt(apple), pt(0.6 * apple + 0.4 * temple), pt(0.25 * apple + 0.75 * temple)], [0.3, 0.22, 0.12]
            elif place == "lifted":
                a2 = apple + io * np.array([0.12, 0.0, 0.15])
                pts, rr = [pt(a2), pt(0.5 * a2 + 0.5 * temple), pt(temple)], [0.22, 0.2, 0.12]
            else:
                pts, rr = [pt(apple), pt(0.5 * apple + 0.5 * temple), pt(temple), pt(temple + io * np.array([0.0, 0.1, 0.35]))], [0.26, 0.24, 0.2, 0.12]
            layer("makeup_blush", o.get("mask"), pre=True, color=col, opacity=round(0.32 * o["amount"], 4),
                  mask=[{"mask": both(pts, rr, soft=1.0)}, {"blur": round(0.07 * io, 5)}])
        o = item("highlight")
        if o:
            m = both([pt("lm_eye_outer.L", (0.02, 0.0, -0.32)), pt("lm_eye_outer.L", (0.22, 0.1, -0.2))], [0.09, 0.06], soft=1.0)
            m += [{"mask": _zones(["nose_bridge"], 0.5), "blend": "max", "weight": 0.7}, {"mask": _zones(["philtrum"], 0.6), "blend": "max", "weight": 0.6}]
            m += [{**e, "blend": "max", "weight": 0.6} for e in both([pt("lm_brow_mid.L", (0.08, 0.0, -0.12)), pt("lm_brow_outer.L", (-0.02, 0.0, -0.1))], [0.05, 0.04], soft=1.0)]
            m += [{**e, "blend": "max", "weight": 0.7} for e in both([pt("lm_eye_inner.L", (-0.03, 0.0, 0.0))], [0.04], soft=1.0, line=False)]
            layer("makeup_highlight", o.get("mask"), pre=True, color=T(melanin=0.5, blood=0.7), opacity=0.35 * o["amount"],
                  roughness=0.24, specular=0.65, mask=m + [{"blur": round(0.025 * io, 5)}])
        o = item("eyeshadow")
        if o:
            col = _hex(o.get("color", "#8b6b5c"))
            crease = _hex(o["crease"]) if "crease" in o else [round(c * 0.72, 4) for c in col]
            outer = _hex(o["outer"]) if "outer" in o else [round(c * 0.55, 4) for c in crease]
            fin = o.get("finish", "matte")
            reach = float(o.get("reach", 1.0))
            extra = {"metallic": 0.6} if fin == "metallic" else ({"specular": 0.7} if fin == "shimmer" else {})
            ch = crease_h * reach
            up = lambda q, h: q + np.array([0.0, 0.0, h])  # noqa: E731
            # the lid: lash line to crease
            lid = [pt(up(ei, 0.35 * ch)), pt(up(lui, 0.5 * ch)), pt(up(lu, 0.5 * ch)), pt(up(luo, 0.5 * ch)), pt(up(eo, 0.45 * ch))]
            layer("makeup_eyeshadow", o.get("mask"), pre=True, color=col, opacity=0.75 * o["amount"], roughness=FINISH[fin], **extra,
                  mask=[{"mask": both(lid, [x / io for x in (0.35 * ch, 0.55 * ch, 0.6 * ch, 0.6 * ch, 0.5 * ch)], soft=0.7)}, {"blur": round(0.012 * io, 5)}])
            # the crease: a deeper shade along the fold, blended up and out toward the brow's tail
            cr = [pt(up(lui, ch)), pt(up(lu, 1.05 * ch)), pt(up(luo, 1.0 * ch)), pt(up(eo, 0.95 * ch) + io * np.array([0.12, 0.0, 0.0]))]
            layer("makeup_eyeshadow_crease", o.get("mask"), pre=True, color=crease, opacity=0.6 * o["amount"], roughness=FINISH["matte"],
                  mask=[{"mask": both(cr, [x / io for x in (0.25 * ch, 0.38 * ch, 0.42 * ch, 0.35 * ch)], soft=1.0)}, {"blur": round(0.03 * io, 5)}])
            # the outer V: crease and lash line meeting at the outer corner, darkest
            v = [pt(eo + io * np.array([0.02, 0.0, 0.02])), pt(up(eo, 0.7 * ch) + io * np.array([0.04, 0.0, 0.0])), pt(up(luo, 0.95 * ch))]
            layer("makeup_eyeshadow_outer", o.get("mask"), pre=True, color=outer, opacity=0.65 * o["amount"], roughness=FINISH["matte"],
                  mask=[{"mask": both(v, [x / io for x in (0.2 * ch, 0.3 * ch, 0.2 * ch)], soft=1.0)}, {"blur": round(0.02 * io, 5)}])
        o = item("eyeliner")
        if o:
            col = _hex(o.get("color", "#120e0d"))
            w = float(o.get("width", 0.0012))
            wing = float(o.get("wing", 0.0))
            # along the upper lash line, on the lid just above the lashes' roots: thin inside, thicker out
            lash = [ei, lui, lu, luo, eo]
            P = [pt(q + np.array([0.0, -0.0003, 0.0004 + 0.25 * w * k / 4])) for k, q in enumerate(lash)]
            R = [0.25 * w, 0.45 * w, 0.6 * w, 0.8 * w, 0.85 * w]
            m = both(P, [x / io for x in R], soft=0.5)
            if wing > 0:
                d = eo - llo
                d = d / max(np.linalg.norm(d), 1e-9)              # the lower lash line's own angle, carried on
                tb = (bo - eo) / max(np.linalg.norm(bo - eo), 1e-9)   # toward the brow's tail
                dw = d + 0.35 * tb
                dw = dw / np.linalg.norm(dw)
                W = [pt(eo + np.array([0.0, 0.0, 0.0004])), pt(eo + 0.5 * wing * dw), pt(eo + wing * dw)]
                m += [{**e, "blend": "max"} for e in both(W, [x / io for x in (0.85 * w, 0.55 * w, 0.18 * w)], soft=0.45)]
            low = float(o.get("lower", 0.0))
            if low > 0:
                lo = [L("lm_lid_lower.L"), llo, eo]
                Pl = [pt(q + np.array([0.0, -0.0003, -0.0004])) for q in lo]
                m += [{**e, "blend": "max", "weight": round(low, 3)} for e in both(Pl, [x / io for x in (0.25 * w, 0.4 * w, 0.55 * w)], soft=0.8)]
            layer("makeup_eyeliner", o.get("mask"), color=col, opacity=round(0.95 * min(o["amount"], 1), 4), roughness=0.4, mask=m)
        o = item("mascara")
        if o:
            layer("makeup_mascara", o.get("mask"), color=_hex(o.get("color", "#0d0b0a")), opacity=0.9 * min(o["amount"], 1),
                  mask=[{"zone": {"name": "lash_upper", "grow": 1.2 + 0.3 * min(o["amount"], 1.5)}},
                        {"zone": {"name": "lash_lower", "grow": 1.1}, "blend": "max", "weight": 0.5}])
        o = item("brows")
        if o:
            col = _hex(o["color"]) if "color" in o else hair_default(t, min(p["age"], 40))
            layer("makeup_brows", o.get("mask"), pre=True, color=col, opacity=0.55 * o["amount"], roughness=0.55,
                  mask=[{"mask": _zones(["brow"], 0.85)}, {"blur": round(0.01 * io, 5)}])
        o = item("lipstick")
        if o:
            fin = o.get("finish", "satin")
            own = T(melanin=1.5, blood=7.5)
            col = _hex(o["color"]) if "color" in o else [round(0.6 * c + 0.4 * d, 4) for c, d in zip(own, _hex("#c45a6a"))]
            sheer = fin == "balm"
            extra = {"specular": 0.75} if fin in ("gloss", "balm") else {}
            grow = 0.9 + float(o.get("overline", 0.0)) / 0.0012
            layer("makeup_lipstick", o.get("mask"), pre=True, color=col, opacity=min((0.45 if sheer else 0.95) * o["amount"], 1.0),
                  roughness=FINISH[fin], **extra, mask=[{"zone": {"name": "lips", "grow": round(grow, 3)}}])
            liner = float(o.get("liner", 0.0))
            if liner > 0:
                lc = _hex(o["liner_color"]) if "liner_color" in o else [round(c * 0.7, 4) for c in col]
                layer("makeup_lip_liner", o.get("mask"), color=lc, opacity=round(0.75 * min(liner, 1), 4), roughness=FINISH[fin],
                      mask=[{"zone": {"name": "lips", "grow": round(grow + 0.8, 3)}}, {"zone": {"name": "lips", "grow": round(max(grow - 1.2, 0.1), 3)}, "blend": "subtract"}])
    if ctx["hands"]:
        o = item("nails")
        if o:
            fin = o.get("finish", "gloss")
            layer("makeup_nails", o.get("mask"), pre=True, color=_hex(o.get("color", "#a8232d")), opacity=min(o["amount"], 1.0),
                  roughness=FINISH.get(fin, 0.12), specular=0.7, mask=_zones(["nails"]))


def reference() -> str:
    return "MAKEUP (skin.makeup):\n" + __doc__.split("\n\n", 1)[1].strip()
