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
FINISH = {"matte": 0.62, "natural": 0.48, "satin": 0.4, "dewy": 0.33, "shimmer": 0.42, "metallic": 0.28, "gloss": 0.1,
          "balm": 0.16}
LOOKS = {
    # the "no-make-up make-up": a sheer even base where needed, a little concealer, brushed brows, mascara, a tinted balm
    "natural": {"foundation": {"amount": 0.3, "finish": "natural"}, "concealer": 0.35, "blush": {"amount": 0.25},
                "brows": 0.2, "mascara": 0.6, "lipstick": {"amount": 0.35, "finish": "balm"}},
    "everyday": {"foundation": {"amount": 0.55, "finish": "natural"}, "concealer": 0.45, "bronzer": 0.3,
                 "contour": 0.35, "blush": {"amount": 0.55}, "highlight": 0.3,
                 "eyeshadow": {"amount": 0.55, "color": "#a07a66", "crease": "#7a5848"},
                 "eyeliner": {"amount": 0.8, "width": 0.0009}, "mascara": 0.9, "brows": 0.4,
                 "lipstick": {"amount": 0.75, "color": "#b0505a", "finish": "satin"}},
    "evening": {"foundation": {"amount": 0.75, "finish": "matte"}, "concealer": 0.55, "bronzer": 0.35,
                "contour": 0.6, "blush": {"amount": 0.5, "place": "lifted"}, "highlight": 0.6,
                "eyeshadow": {"amount": 1.2, "color": "#8c5e46", "crease": "#6a4030", "outer": "#3e2418", "finish": "shimmer",
                              "reach": 1.15},
                "eyeliner": {"amount": 1.0, "width": 0.0015, "wing": 0.004, "lower": 0.4}, "mascara": 1.2, "brows": 0.6,
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


def wing_root(J: dict, blobs: dict, S: str, eo, V=None) -> np.ndarray:
    """The visible outer corner of an eye (the canthus): where the lids meet on the eyeball. Given the head's surface
    points V, the most lateral skin in front that lies on the ball (within 1.5 mm of its surface); else toward
    lm_eye_outer from the ball's centre, just outside its surface. (lm_eye_outer is no guide alone: it sat 2.7 mm past
    the corner on skin2's evening head and 1.5 mm inside it on Tess's.)"""
    c = np.asarray(J.get(f"eye{S}", eo), float)
    size = (blobs.get(f"eye{S}") or {}).get("size")
    r = float(np.max(size)) if isinstance(size, (list, tuple)) else 0.012
    sx = 1.0 if S == ".L" else -1.0
    if V is not None and len(V):
        V = np.asarray(V, float)
        on = (np.abs(np.linalg.norm(V - c, axis=1) - r) < 0.0015) & ((c[1] - V[:, 1]) > 0.2 * r)
        on &= np.abs(V[:, 2] - c[2]) < 0.6 * r
        if on.sum() >= 3:
            Q = V[on]
            top = np.argsort(-sx * Q[:, 0])[:3]
            return Q[top].mean(0)
    v = np.asarray(eo, float) - c
    dist = float(np.linalg.norm(v))
    if dist <= r + 0.0004:
        return np.asarray(eo, float)
    return c + v / dist * (r + 0.0004)

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

    def __call__(self, p, near: bool = False):
        """near: the skin nearest the guess along the ray (round the eye, where lid, brow and lashes overlap along
        the ray); else the frontmost skin along it (the near cheek, not the far side of the head)."""
        p = np.asarray(p, float)
        if not self.ok:
            return p
        idx = self.tree.query_ball_point([p[0], p[2]], 0.0015)
        if not idx:
            idx = [self.tree.query([p[0], p[2]])[1]]
        cand = self.V[idx]
        if near:
            return cand[np.argmin(np.abs(cand[:, 1] - p[1]))]
        close = cand[np.abs(cand[:, 1] - p[1]) < 0.02]
        c = (close if len(close) else cand)
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
        cur = {"S": ".L", "sx": 1.0}   # the side being built: landmarks of that side, offsets' x mirrored

        def L(n):
            return np.asarray(J[n[:-2] + cur["S"] if n.endswith(".L") else n], float)

        def X(v):
            """A vector given for the left side (x out), turned to the side being built."""
            v = np.asarray(v, float)
            return np.array([v[0] * cur["sx"], v[1], v[2]])

        def pt(base, off=(0, 0, 0), near=False):
            """A point from a landmark (".L" name: the side being built) + offset (interocular units, x outward),
            seated on the skin."""
            q = (L(base) if isinstance(base, str) else np.asarray(base, float)) + io * X(off)
            return seat(q, near)

        def both(fn, radii, soft=0.8, line=True):
            """A tapered line (or spots) on each side: fn() gives the side's points (built from its own landmarks:
            faces aren't symmetric, and a mirrored left-side line floated off the right eye as dots)."""
            r = [round(float(x) * io, 6) for x in radii]
            out = []
            for S, sx in ((".L", 1.0), (".R", -1.0)):
                cur.update(S=S, sx=sx)
                P = [[round(float(c), 6) for c in q] for q in fn()]
                e = {"spot": {"at": P, "radius": r if line else [[x] * 3 for x in r], "soft": soft, **({"line": True} if line else {})}}
                out.append({**e, **({"blend": "max"} if out else {})})
            cur.update(S=".L", sx=1.0)
            return out

        def has(n):
            return n in J

        def eye():
            """The side's eye: corners, upper / lower margin points, brow, crease height."""
            eo, ei = L("lm_eye_outer.L"), L("lm_eye_inner.L")
            lu = L("lm_lid_upper.L")
            lui = L("lm_lid_upper_in.L") if has("lm_lid_upper_in.L") else 0.5 * (ei + lu)
            luo = L("lm_lid_upper_out.L") if has("lm_lid_upper_out.L") else 0.5 * (eo + lu)
            ll = L("lm_lid_lower.L")
            llo = L("lm_lid_lower_out.L") if has("lm_lid_lower_out.L") else 0.5 * (eo + ll)
            bo, bm = L("lm_brow_outer.L"), L("lm_brow_mid.L")
            ch = 0.3 * max(bm[2] - lu[2], 0.2 * io)   # the lid fold above the lash line (~6-9 mm on an open eye)
            return eo, ei, lu, lui, luo, ll, llo, bo, bm, ch

        up = lambda q, h: q + np.array([0.0, 0.0, h])  # noqa: E731

        def brow_area(grow):
            """Where the brows are: the brow hairs' own picture, softened, when the brow was moved off its landmarks
            (drop / lift / tilt / apart: on Tess the landmark zone left a pale patch of bare skin over her lowered
            brows, in the foundation), else the landmark zone."""
            if ctx.get("brow_area"):
                return ctx["brow_area"] + [{"blur": round(0.02 * io * grow, 5)}]
            return _zones(["brow"], grow)

        o = item("foundation")
        if o:
            a = float(np.clip(o["amount"], 0, 1))
            col = _hex(o["color"]) if "color" in o else T(blood=0.9)
            layer("makeup_foundation", o.get("mask"), pre=True, color=col, opacity=0.8 * a, roughness=FINISH[o.get("finish", "natural")],
                  mask=where(o, ["face", "neck"]) + [{"zone": "lips", "blend": "subtract"}, {"mask": _zones(["eyelid", "eye_corner"], 0.7), "blend": "subtract", "weight": 0.5},
                                                          {"mask": brow_area(1.1), "blend": "subtract", "weight": 0.8}])   # (over the brows it left a pale halo)
        o = item("concealer")
        if o:
            col = _hex(o["color"]) if "color" in o else [round(min(c * f, 1), 4) for c, f in zip(T(melanin=0.8, blood=0.75), (1.03, 1.0, 0.95))]
            m = both(lambda: [pt("lm_eye_inner.L", (0.0, -0.02, -0.08)), pt("lm_lid_lower.L", (0.0, -0.02, -0.14)), pt("lm_eye_outer.L", (0.05, 0.0, -0.12))],
                     [0.1, 0.14, 0.07], soft=0.95)
            layer("makeup_concealer", o.get("mask"), pre=True, color=col, opacity=0.55 * o["amount"],
                  mask=[{"mask": m}, {"zone": {"name": "nose_wing", "grow": 0.8}, "blend": "max", "weight": 0.5}, {"blur": round(0.05 * io, 5)}])
        o = item("bronzer")
        if o:
            col = _hex(o["color"]) if "color" in o else T(melanin=2.2, blood=1.2, yellow=0.2)
            m = both(lambda: [pt("lm_brow_outer.L", (0.15, 0.1, 0.55)), pt("lm_brow_outer.L", (0.25, 0.25, 0.1))], [0.3, 0.22], soft=1.0)
            m += [{**e, "blend": "max"} for e in both(lambda: [pt("lm_eye_outer.L", (0.15, 0.1, -0.4)), pt("lm_brow_outer.L", (0.15, 0.2, -0.2))], [0.2, 0.15], soft=1.0)]
            m += [{"mask": _zones(["nose_bridge"], 0.8), "blend": "max", "weight": 0.5}]
            layer("makeup_bronzer", o.get("mask"), pre=True, color=col, opacity=0.35 * o["amount"], mask=m + [{"blur": round(0.06 * io, 5)}])
        o = item("contour")
        if o:
            col = _hex(o["color"]) if "color" in o else T(melanin=2.4, blood=0.8, grey=0.35)

            def hollow():
                # under the cheekbone: from in front of the ear's tragus toward the mouth's corner, stopping under the
                # outer eye (never into the nasolabial fold)
                eo, nos = L("lm_eye_outer.L"), L("lm_nostril.L")
                E = pt("lm_jaw_0.L", (-0.12, -0.1, -0.12))
                Q = pt(np.array([eo[0], eo[1], nos[2]]) + io * X([0.03, 0.0, -0.05]))
                return [E, pt(0.5 * (E + Q) + io * np.array([0.0, 0.0, -0.04])), Q]
            m = both(hollow, [0.2, 0.16, 0.08], soft=1.0)
            m += [{**e, "blend": "max", "weight": 0.7} for e in both(lambda: [pt("lm_brow_outer.L", (0.25, 0.25, 0.45)), pt("lm_brow_outer.L", (0.3, 0.35, 0.05))], [0.18, 0.12], soft=1.0)]
            m += [{"mask": _zones(["jaw"], 0.8), "blend": "max", "weight": 0.45}]
            nose_k = float(o.get("nose", 0.0))
            if nose_k > 0:
                m += [{**e, "blend": "max", "weight": round(nose_k, 3)} for e in
                      both(lambda: [pt("lm_brow_inner.L", (-0.04, 0.0, -0.1)), pt("lm_nose_bridge", (0.12, 0.0, -0.35)), pt("lm_nose_tip", (0.11, 0.0, 0.12))], [0.05, 0.05, 0.04], soft=1.0)]
            layer("makeup_contour", o.get("mask"), pre=True, color=col, opacity=0.6 * o["amount"],
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

            def cheek():
                ll, bo, eo = L("lm_lid_lower.L"), L("lm_brow_outer.L"), L("lm_eye_outer.L")
                pupil = L("eye.L") if has("eye.L") else 0.5 * (eo + L("lm_eye_inner.L"))
                apple = np.array([pupil[0], ll[1], ll[2] - 0.5 * io]) + io * X([0.12, 0, 0])   # under the outer iris
                temple = np.array([bo[0], bo[1], eo[2] + 0.12 * io]) + io * X([0.05, 0, 0])
                if place == "apples":
                    return [pt(apple), pt(0.55 * apple + 0.45 * temple), pt(0.15 * apple + 0.85 * temple)]   # a sweep, not a patch
                if place == "lifted":
                    a2 = apple + io * X([0.12, 0.0, 0.15])
                    return [pt(a2), pt(0.5 * a2 + 0.5 * temple), pt(temple)]
                return [pt(apple), pt(0.5 * apple + 0.5 * temple), pt(temple), pt(temple + io * np.array([0.0, 0.1, 0.35]))]
            rr = {"apples": [0.2, 0.18, 0.11], "lifted": [0.22, 0.2, 0.12], "draped": [0.26, 0.24, 0.2, 0.12]}[place]
            layer("makeup_blush", o.get("mask"), pre=True, color=col, opacity=round(0.5 * o["amount"], 4),
                  mask=[{"mask": both(cheek, rr, soft=1.0)}, {"blur": round(0.07 * io, 5)}])
        o = item("highlight")
        if o:
            m = both(lambda: [pt("lm_eye_outer.L", (0.02, 0.0, -0.32)), pt("lm_eye_outer.L", (0.22, 0.1, -0.2))], [0.09, 0.06], soft=1.0)
            m += [{"mask": _zones(["nose_bridge"], 0.5), "blend": "max", "weight": 0.7}, {"mask": _zones(["philtrum"], 0.6), "blend": "max", "weight": 0.6}]
            m += [{**e, "blend": "max", "weight": 0.3} for e in both(lambda: [pt("lm_brow_mid.L", (0.08, 0.0, -0.12)), pt("lm_brow_outer.L", (-0.02, 0.0, -0.1))], [0.05, 0.04], soft=1.0)]
            layer("makeup_highlight", o.get("mask"), pre=True, color=T(melanin=0.5, blood=0.7), opacity=0.35 * o["amount"],
                  roughness=0.24, specular=0.65, mask=m + [{"blur": round(0.025 * io, 5)}])
        o = item("eyeshadow")
        if o:
            col = _hex(o.get("color", "#8b6b5c"))
            crease = _hex(o["crease"]) if "crease" in o else [round(c * 0.72, 4) for c in col]
            outer = _hex(o["outer"]) if "outer" in o else [round(c * 0.55, 4) for c in crease]
            fin = o.get("finish", "matte")
            reach = float(o.get("reach", 1.0))
            # (shimmer: a coloured sheen, not a mirror: at specular 0.55 / roughness 0.32 the lid's convex top caught the
            # light as a pale silvery arc over the evening eye, skin3)
            extra = {"metallic": 0.6} if fin == "metallic" else ({"specular": 0.38} if fin == "shimmer" else {})

            def lid():   # the whole mobile lid, from the lash line up to the crease (skin3: it covered the lower third
                # only, and the bare lid between it and a thin crease line read as a pale arc floating over the eye)
                eo, ei, lu, lui, luo, _, _, _, _, ch = eye()
                ch *= reach
                return [pt(up(ei, 0.3 * ch), near=True), pt(up(lui, 0.45 * ch), near=True), pt(up(lu, 0.5 * ch), near=True),
                        pt(up(luo, 0.5 * ch), near=True), pt(up(eo, 0.4 * ch), near=True)]

            def fold():  # a deeper shade along the crease, blended out toward the brow's tail
                eo, ei, lu, lui, luo, _, _, _, _, ch = eye()
                ch *= reach
                return [pt(up(lui, 0.95 * ch), near=True), pt(up(lu, ch), near=True), pt(up(luo, 0.95 * ch), near=True),
                        pt(up(eo, 0.8 * ch) + io * X([0.1, 0.0, 0.0]), near=True)]

            def vee():   # the outer V: crease and lash line meeting at the outer corner, darkest
                eo, ei, lu, lui, luo, _, _, _, _, ch = eye()
                ch *= reach
                return [pt(eo + io * X([0.01, 0.0, 0.01]), near=True), pt(up(eo, 0.6 * ch) + io * X([0.03, 0.0, 0.0]), near=True),
                        pt(up(luo, 0.9 * ch), near=True)]
            chm = eye()[-1] * reach / io
            layer("makeup_eyeshadow", o.get("mask"), pre=True, color=col, opacity=0.8 * o["amount"], roughness=FINISH[fin], **extra,
                  mask=[{"mask": both(lid, [chm * k for k in (0.42, 0.66, 0.72, 0.72, 0.6)], soft=0.85)}, {"blur": round(0.012 * io, 5)}])
            layer("makeup_eyeshadow_crease", o.get("mask"), pre=True, color=crease, opacity=0.6 * o["amount"], roughness=FINISH["matte"],
                  mask=[{"mask": both(fold, [chm * k for k in (0.3, 0.45, 0.5, 0.42)], soft=1.0)}, {"blur": round(0.04 * io, 5)}])
            layer("makeup_eyeshadow_outer", o.get("mask"), pre=True, color=outer, opacity=0.65 * o["amount"], roughness=FINISH["matte"],
                  mask=[{"mask": both(vee, [chm * k for k in (0.18, 0.26, 0.18)], soft=1.0)}, {"blur": round(0.015 * io, 5)}])
        o = item("eyeliner")
        if o:
            col = _hex(o.get("color", "#120e0d"))
            w = float(o.get("width", 0.0012))
            wing = float(o.get("wing", 0.0))

            # along the lashes' roots: the lid margin's own zone (the lash line, as the mascara takes it), grown with
            # the width, and grown more over the outer half (thin inside, thicker out). (Lines through the eye corner
            # landmarks left dots: lm_eye_inner / outer sit a few mm past the lids' visible corners on these heads.)
            k = w / 0.0012
            outer_half = both(lambda: [pt(eye()[4], near=True), pt(eye()[0], near=True)], [0.16, 0.12], soft=1.0)
            m = [{"zone": {"name": "lash_upper", "grow": round(1.0 + 0.45 * k, 3)}},
                 {"mask": [{"zone": {"name": "lash_upper", "grow": round(1.0 + 1.1 * k, 3)}}, {"mask": outer_half}], "blend": "max"}]
            if wing > 0:
                # the wing: a filled triangle whose lower edge continues the lower lash line out of the visible outer
                # corner (the canthus: where the lids meet on the eyeball, ~1.5-3 mm inside lm_eye_outer on these
                # heads) and whose upper edge runs back from the tip to the upper lash line's outer third; a fan of
                # tapering spot chains from the tip, each spot deep along the face's forward axis (it reaches the skin
                # wherever the lid and temple turn back), per side from that side's own landmarks.
                # (skin2's chain started on the upper lid 3 mm above the corner: a thorn flicking up off the eye in
                # every blind read. Tried and dropped before: a tube through seated points, a picture laid from the
                # front (a shard on the lid fold), a geodesic sticker from the lash line (it didn't leave the corner).)
                from . import paint as _paint
                eb = _paint._expanded(spec).get("blobs") or {}
                for S, sx in ((".L", 1.0), (".R", -1.0)):
                    cur.update(S=S, sx=sx)
                    eo, llo, luo = eye()[0], eye()[6], eye()[4]
                    C = wing_root(J, eb, S, eo, seat.V if seat.ok else None)
                    d = C - llo   # the lower lash line's outer third through the corner, extended
                    d = np.array([d[0], 0.0, d[2]])
                    d = d / max(np.linalg.norm(d), 1e-9)
                    tip = C + wing * d
                    U = luo + np.array([0.0, 0.0, 0.25 * w])          # the upper lash line's outer third (over the liner)
                    for j in range(9):
                        g = j / 8   # (5 chains left skin-coloured slivers between them)
                        base = C + g * (U - C)
                        L_ = float(np.linalg.norm((tip - base)[[0, 2]]))
                        pts, rad = [], []
                        f_ = 0.0
                        while True:   # spots no further apart than 40 % of their radius: no beads toward the fine tip
                            q = base + f_ * (tip - base)
                            r = 0.42 * w * (1 - f_) ** 0.8 + 0.00007
                            pts.append([round(float(c), 6) for c in q])
                            rad.append([round(r, 6), 0.004, round(r, 6)])
                            if f_ >= 1.0:
                                break
                            f_ = min(f_ + max(0.4 * r, 0.00004) / max(L_, 1e-6), 1.0)
                        m += [{"spot": {"at": pts, "radius": rad, "soft": 0.3}, "blend": "max"}]
                cur.update(S=".L", sx=1.0)
            low = float(o.get("lower", 0.0))
            if low > 0:
                m += [{**e, "blend": "max", "weight": round(low, 3)} for e in
                      both(lambda: [q + np.array([0.0, -0.0002, -0.0002]) for q in (eye()[5], eye()[6], eye()[0])],
                           [x * w / io for x in (0.2, 0.32, 0.45)], soft=0.8)]
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
                  mask=[{"mask": brow_area(0.85)}, {"blur": round(0.01 * io, 5)}])
        o = item("lipstick")
        if o:
            fin = o.get("finish", "satin")
            own = T(melanin=1.5, blood=7.5)
            col = _hex(o["color"]) if "color" in o else [round(0.6 * c + 0.4 * d, 4) for c, d in zip(own, _hex("#c45a6a"))]
            sheer = fin == "balm"
            extra = {"specular": 0.75} if fin in ("gloss", "balm") else {}
            grow = 0.45 + float(o.get("overline", 0.0)) / 0.0012
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
