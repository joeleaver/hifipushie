"""The eyes: the eye's base and its layers. Part of the skin features (skin_features.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import skin_features
from .spec import SpecError
from .skin_features import _hex, _zones

def eye_base(spec: dict) -> tuple[str, dict] | None:
    """(the eyes part, its base channels) when skin.eyes paints them: the tear film as a clear coat over the matte
    iris and sclera (coat 1, roughness 0.03 x (2 - gloss); IOR 1.5 ~ the cornea's 1.376 and the film's 1.337 under
    Blender's coat): the sharp catchlight a photographed eye has. Values the part's own definition gives win."""
    e = (spec.get("skin") or {}).get("eyes")
    b = spec.get("base") or {}
    if e is False or not spec.get("skin") or not b.get("eyes"):
        return None
    e = e if isinstance(e, dict) else {}
    g = float(e.get("gloss", 1.0))
    if g <= 0:
        return None
    return b["eyes"], {"coat": round(min(g, 1.0), 3), "coat_roughness": round(0.03 * (2 - min(g, 1.0)), 4)}


def _eyes(spec, p, J, out, layer, T, ctx) -> None:
    """EYES (skin.eyes; on by default where the base has eyeballs; false turns it off and leaves the model's own eye
    paint): the eyeball is a painted picture laid on its front (skin_swatch.eye_image: an iris of radial fibres, a
    collarette, a limbal ring, a soft pupil; a sclera pinker toward its edge with fine vessels), under a wet film;
    shadowed where the lids lie on it; on the skin, the pink wet caruncle at the inner corner and the waterline of the
    lower lid. Lashes are geometry (base.lashes, lashes.py) over the lid margins darkened (skin.hair.lashes).
    {"iris": colour (the iris toward its rim), "iris_inner": colour (the zone round the pupil, when it differs: hazel,
    central heterochromia; "iris_inner_to": where it hands over, share of the radius, 0.55), "iris_size": m (the visible iris' diameter: adults 11-12.5 mm, 11.7 on average; unset on a GNM
    head with GNM's own eyeball: its limbus for the identity, base.head.identity.eyes_000), "pupil": 0..1
    of the iris' radius (0.36; bright daylight 0.2-0.3; unset on GNM's eyeball: its own pupil, 0.5 at rest, moved by
    base.head.expression.pupils_000: +1 = 0.67, -1 = 0.33), "veins": 0..1, "sclera": colour, "limbal": 0..1 (0.72: the
    dark ring at the iris' edge, darker and wider in the young), "limbal_width": share of the radius (0.2),
    "iris_contrast": the fibres' contrast (1), "gloss": 0..1 (1: the tear film, a clear coat over a matte iris and
    sclera: the sharp catchlight on the cornea), "occlusion": 0..1 (1: the lids' shadow on the ball, all round the
    lid contact and deepest under the upper lid; MetaHuman's eye-occlusion shell as paint), "tear": 0..1 (the
    meniscus: the bright wet line where the lower lid meets the ball), "waterline": 0..1, "caruncle": 0..1.2 (unset:
    a soft pink spot; a number: the inner corner's pocket filled wet dark red from GNM's inner-corner landmark to the
    eyeball, the way a photographed canthus reads: the eye then reaches its anatomical inner corner), "canthus": 0..1.2
    (unset / 0: off; the LATERAL corner: a soft warm shadow on the eyeball's outer end and the lid junction's wet
    red, against the white wedge running to a point that GNM's sharp outer corner shows; ~0.8), "crease":
    {"amount": 0..1 (0.6), "path": [[u, v], ...] (mm from the iris centre in the eye's frame, u toward the outer
    corner, v up: eye_ruler.crease_path reads it off the picture), "width": mm (0.5), "color", "shade": 0..1 (0.4:
    a soft band over the line, the fold's underside)}: the fold LINE as a thin shadow in the skin (multiply), where
    the lid's soft valley gives no line of its own}."""
    e = spec.get("skin", {}).get("eyes")
    if e is False or not ctx["eyes"] or "eye_front.L" not in J:
        return
    e = e if isinstance(e, dict) else {}
    bad = set(e) - set(skin_features.EYE_KEYS)
    if bad:
        raise SpecError(f"skin eyes: unknown keys {sorted(bad)} (have {', '.join(skin_features.EYE_KEYS)})")
    from . import paint as _paint
    from . import skin_swatch
    from .skin_zones import interocular
    io = interocular(J)
    part = (_paint._expanded(spec)["blobs"]["eye.L"]).get("part", "body")
    iris = _hex(e.get("iris", "#5a3a1e"))
    old = ctx["old"]
    scl = _hex(e["sclera"]) if "sclera" in e else [round(x, 4) for x in (0.92 - 0.05 * old, 0.89 - 0.06 * old, 0.85 - 0.09 * old)]
    veins = float(e.get("veins", 0.4 + 0.4 * old))
    span = 2.1
    from . import base_implied
    eg = base_implied.eye_native(spec)  # (gnmnative) GNM's own eye: the iris at its limbus, the pupil as its geometry has it
    # (the identity's eyes_* components and the expression's pupils_000: dilation is a pose value)
    path = skin_swatch.eye_image(iris, float(e.get("pupil", eg["pupil"] if eg else 0.36)), veins, tuple(scl), p["seed"], span,
                                 limbal=float(e.get("limbal", 0.72)), contrast=float(e.get("iris_contrast", 1.0)),
                                 limbal_width=float(e.get("limbal_width", 0.2)),
                                 inner=_hex(e["iris_inner"]) if e.get("iris_inner") else None, inner_to=float(e.get("iris_inner_to", 0.55)))
    gloss = float(e.get("gloss", 1.0))
    occ = float(e.get("occlusion", skin_features.EYE_OCCLUSION))
    for sd in (".L", ".R"):
        c, f = J[f"eye{sd}"], J[f"eye_front{sd}"]
        r = float(np.linalg.norm(f - c))
        d = (f - c) / max(r, 1e-9)
        size = float(e.get("iris_size", 2 * eg["limbus"] if eg else 0.0118 * r / 0.0123)) * span
        nm = sd.replace(".", "_")
        out[f"skin:eye{nm}"] = {"part": part, "color": "image",
                                # under the film (the part's coat, eye_base) the iris and sclera are matte; without a
                                # film the old glassy surface
                                "roughness": round(0.04 + 0.36 * min(gloss, 1.0), 3), "specular": 0.6 - 0.2 * min(gloss, 1.0),
                                "image": {"file": str(path), "at": [round(float(x), 5) for x in f], "dir": [round(float(x), 4) for x in d],
                                          "size": [round(size, 5), round(size, 5)], "depth": round(1.2 * r, 5), "facing": 0.05}}
        # the lids' shadow on the ball (an eye-occlusion shell's job in a game head): deepest under the upper lid,
        # and a narrow soft band all round where the lids lie on the ball (the corners darkest)
        if occ > 0:
            # (one layer: each layer costs shader; the band all round is the max over the upper lid's shadow)
            # (r27: opacity 0.6 -> 0.25 and a greyer shadow (was [0.6, 0.43, 0.41]): with the picture's own warm edge the
            # true visible sclera baked (0.85, 0.79, 0.79) of the paint, both eyes alike; the L/R "asymmetry" was the
            # measure taking iris texels. Fast path (assembly/eyevar.py): mid sclera -> (0.94, 0.90, 0.90) L, (0.95, 0.92, 0.92) R)
            out[f"skin:eye_shade{nm}"] = {"part": part, "color": [0.7, 0.64, 0.62], "mix": "multiply",
                                          "opacity": round(min(0.25 * occ, 1.0), 3),
                                          # (r26: both terms keyed to the distance from the lids, unsigned: the ball lies
                                          # INSIDE the head's field, so "near base" was 1 over the whole visible sclera,
                                          # baked x(0.76, 0.66, 0.65), and the height-keyed upper shadow darkened the eye
                                          # whose lids sit higher: L 49 vs R 68 against the paint's ~90)
                                          "mask": [{"mask": [{"axis": {"dir": [0, 0, 1], "at": f"eye{sd}", "from": round(0.1 * r, 5),
                                                                       "to": round(0.55 * r, 5)}},
                                                             {"spot": {"at": f"eye{sd}", "radius": round(1.6 * r, 5), "soft": 0.2}},
                                                             {"near": ["base"], "side": "both", "within": round(0.04 * r, 5),
                                                              "soft": round(0.16 * r, 5)}],
                                                    "weight": 0.85},
                                                   {"near": ["base"], "side": "both", "within": round(0.02 * r, 5),
                                                    "soft": round(0.09 * r, 5), "blend": "max"}]}
        # the tear line: the strip of tear film standing where the lower lid meets the ball, a thin WET line: it reads by
        # its gloss, not by a pale colour (r16: [.97 .86 .84] at .4 over ~.05 r drew a pale pink-grey strip along Tess's
        # lower lid, "the eyeball reads as a fitted shell"; found by hiding objects / zeroing layers one at a time in the
        # stage scene: only eyes.tear 0 removed it). Now ~.25 mm (the meniscus' height), the sclera's own neutral, faint.
        if float(e.get("tear", 1.0)) > 0:
            out[f"skin:eye_tear{nm}"] = {"part": part, "color": [0.88, 0.86, 0.85], "opacity": round(0.15 * float(e.get("tear", 1.0)), 3),
                                         "roughness": 0.02, "specular": 1.0,
                                         "mask": [{"near": ["base"], "side": "both", "within": round(0.005 * r, 5), "soft": round(0.012 * r, 5)},
                                                  {"axis": {"dir": [0, 0, -1], "at": f"eye{sd}", "from": round(0.05 * r, 5), "to": round(0.2 * r, 5)}}]}
    # on the skin: the caruncle (the pink, wet corner by the nose) and the lower lid's waterline
    car = e.get("caruncle")
    if car is None:   # (the old soft pink spot)
        pts = [{"at": f"lm_eye_inner{sd}", "offset": [round(sx * 0.012 * io, 5), round(-0.02 * io, 5), 0.0]} for sd, sx in ((".L", 1), (".R", -1))]
        layer("caruncle", pre=True, color=T(blood=5.0, melanin=0.7), opacity=0.7, roughness=0.18,
              mask=[{"spot": {"at": pts, "radius": round(0.036 * io, 5), "soft": 0.6}}])
    elif float(car) > 0:
        # (eyeruler) GNM's lids end in a pocket between the opening's medial end and the lm68 inner corner (1.9 mm): the
        # caruncle and the corner's wet red. Painted as skin, the eye read ~2 mm short at the inner corner against a
        # photo (a detector puts the canthus at the pocket's tip, as GNM's landmark does). So the pocket is filled with
        # a darker wet red, from the landmark out to the eyeball: a capsule along the corner -> eye line.
        a = float(car)
        segs = []
        for sd in (".L", ".R"):
            i_ = np.asarray(J[f"lm_eye_inner{sd}"], float)
            sx = 1.0 if sd == ".L" else -1.0   # (the pocket runs sideways from the landmark, a little back into the head)
            segs.append([[round(float(x), 5) for x in i_ + np.array([sx * t, 0.25 * t, 0.0])] for t in (0.0003, 0.0013, 0.0023)])
        from .skin_zones import _sp
        m = [dict(_sp(sg, [0.0007, 0.0011, 0.0010], soft=0.35, line=True), **({"blend": "max"} if k else {})) for k, sg in enumerate(segs)]
        layer("caruncle", pre=True, color=T(blood=6.0, melanin=0.8), opacity=round(min(0.85 * a, 1.0), 3), roughness=0.15, mask=m)
        # THE INNER CANTHUS' TIP (mouth_eye_bias -> skin): in a photo the inner corner ends in a dark POINT (the pocket's
        # shadow where the lids meet past the caruncle), not a rounded white / pink end: a thin dark wedge from the
        # pocket's medial end on toward the nose, tapering to nothing over ~CANTHUS_TIP; drawn in the caruncle's wet
        # multiply (one layer: the shader budget), darker there
        tips = []
        for sd in (".L", ".R"):
            i_ = np.asarray(J[f"lm_eye_inner{sd}"], float)
            sx = 1.0 if sd == ".L" else -1.0
            tips.append(dict(_sp([i_ + np.array([sx * 0.0008, 0.0, 0.0]), i_, i_ + np.array([-sx * skin_features.CANTHUS_TIP, 0.0, -0.0002])],
                                 [0.00045, 0.0003, 0.00006], soft=0.5, line=True), blend="max"))
        layer("caruncle_wet", pre=True, color=[0.64, 0.49, 0.47], mix="multiply", opacity=round(min(0.75 * a, 1.0), 3), mask=m + tips)
        # ... and on the eyeball's nose-side end: the caruncle's flesh and the plica stand in FRONT of the sclera there
        # (a photographed inner corner is 3-4 mm of pink before any white); GNM's pocket alone is a slit
        for sd, sx in ((".L", 1.0), (".R", -1.0)):
            i_ = np.asarray(J[f"lm_eye_inner{sd}"], float)
            c_, f_ = np.asarray(J[f"eye{sd}"], float), np.asarray(J[f"eye_front{sd}"], float)
            r_ = float(np.linalg.norm(f_ - c_))
            q_ = i_ + np.array([sx * 0.0016, 0.0, 0.0002]) - c_       # (the spot sits ON the ball: its nose-side end lies
            q_ = c_ + r_ * q_ / max(float(np.linalg.norm(q_)), 1e-9)   # 2-3 mm behind the lids' corner)
            out[f"skin:eye_caruncle{sd.replace('.', '_')}"] = {
                "part": part, "color": [0.63, 0.43, 0.39], "opacity": round(min(0.75 * a, 1.0), 3), "roughness": 0.2,
                "mask": [_sp([q_], [0.003], soft=0.8)]}
    cn = float(e.get("canthus") or 0.0)
    if cn > 0:
        # (garrettnative, 2026-10-12) THE LATERAL CANTHUS: GNM's lids meet in a sharp V over a 14.6 mm sphere and the
        # sclera is plain white to the corner, so every GNM head shows a white wedge running to a point at the outer
        # corner (gnmnative's ladder: on GNM's raw mesh too; shading, not shape). In a face that corner is in the
        # lids' shadow and the conjunctiva there is pink, not white. So: on the eyeball's outer end a soft warm
        # shadow (multiply; strongest at the corner, gone by the limbus), and on the skin the corner's own wet red
        # at the lid margins' junction (as "caruncle" does at the nose side, much smaller).
        from .skin_zones import _sp
        for sd, sx in ((".L", 1.0), (".R", -1.0)):
            o_ = np.asarray(J[f"lm_eye_outer{sd}"], float)
            c_, f_ = np.asarray(J[f"eye{sd}"], float), np.asarray(J[f"eye_front{sd}"], float)
            r_ = float(np.linalg.norm(f_ - c_))
            q_ = o_ - c_
            q_ = c_ + r_ * q_ / max(float(np.linalg.norm(q_)), 1e-9)    # the corner's place ON the ball
            out[f"skin:eye_canthus{sd.replace('.', '_')}"] = {
                "part": part, "color": [0.58, 0.40, 0.36], "mix": "multiply", "opacity": round(min(0.8 * cn, 1.0), 3),
                "mask": [_sp([q_], [0.0048], soft=0.85)]}
        pts = [np.asarray(J[f"lm_eye_outer{sd}"], float) + np.array([-sx * 0.0006, 0.0, 0.0]) for sd, sx in ((".L", 1.0), (".R", -1.0))]
        layer("canthus", pre=True, color=T(blood=4.5, melanin=1.6), opacity=round(min(0.6 * cn, 1.0), 3), roughness=0.2,
              mask=[_sp(pts, [0.0016] * len(pts), soft=0.7)])
    cr = e.get("crease")
    if isinstance(cr, dict) and float(cr.get("amount", 0.6)) > 0 and cr.get("path"):
        # the fold LINE as the skin's own shadow (eyeruler; Joe: darkness the fold's shape does not give comes from the
        # skin's cosmetics, never a geometry layer): a thin multiply line along a path given in the eye's frame (mm
        # from the iris centre: eye_ruler reads it off the picture), laid from the front like the brows' picture
        f_, c_ = np.asarray(J["eye_front.L"], float), np.asarray(J["eye.L"], float)
        d_ = (f_ - c_) / max(float(np.linalg.norm(f_ - c_)), 1e-9)
        cpath = skin_swatch.crease_image(cr["path"], float(cr.get("width", 0.5)),
                                         colour=tuple(_hex(cr["color"])) if "color" in cr else (0.5, 0.36, 0.32),
                                         shade=float(cr.get("shade", 0.4)))
        img = {"file": str(cpath), "at": [round(float(x), 5) for x in f_ + np.array([0.0, 0.0, 0.003])],
               "dir": [round(float(x), 4) for x in d_], "size": [0.04, 0.03], "depth": 0.02, "facing": -0.3, "mirror": True,
               "mirror_image": True}
        # (the picture itself as the colour, multiplied in: a mask is sampled per vertex and loses a 0.5 mm line)
        layer("lid_crease_line", color="image", image=img, mix="multiply", opacity=round(min(float(cr.get("amount", 0.6)), 1.0), 3))
    if float(e.get("waterline", 1.0)) > 0:   # 0..1 (1): the pink wet rim; on a lid whose rim faces the camera it reads as lid
        layer("waterline", pre=True, color=T(blood=3.5, melanin=0.6), opacity=round(0.5 * float(e.get("waterline", 1.0)), 3),
              roughness=0.15, mask=_zones(["lash_lower"], 0.7))
    from . import lidfold
    fc = lidfold.config(spec)
    if fc:  # the lid's fold (lidfold.py): its crease's own tone, along the fold's own invagination (paint's `near` on
        # a fold prim: the distance across its crease line, scaled by its depth). Skin deep in a tight fold catches
        # no light and its blood shows: a photographed crease is a soft brown-red line. (The field's cavity can't do
        # it: curvature is measured with a 0.75-voxel stencil, which steps over a 0.8 mm groove.)
        w = float(fc["crease_width"]) * 0.001
        # A SHADOW, not a hue: neutral multiplies (the skin's own colour darker, its saturation kept), darkest in a thin
        # line, then a soft gradient up the fold's underside and none below (a red-brown tone read as a painted scar)
        fold = ["lid_fold.L", "lid_fold.R"]
        layer("lid_crease", pre=True, color=[0.76, 0.82, 0.86], mix="multiply",  # (a hair cool: the groove's own
              # subsurface glow reddens it ~3 deg against the photo's crease)
              opacity=round(float(np.clip(0.35 + 0.3 * fc["crease_depth"], 0, 0.9)), 3),
              mask=[{"near": fold, "within": round(0.2 * w, 6), "soft": round(0.8 * w, 6)}])
        layer("lid_fold_shadow", pre=True, color=[0.9, 0.91, 0.92], mix="multiply", opacity=0.85,
              mask=[{"near": fold, "side": "up", "within": 0.0, "soft": round(1.8 * float(fc["fold_width"]) * 0.001, 6)}])
