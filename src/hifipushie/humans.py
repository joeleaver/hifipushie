"""A whole human from a description: "a 3-year-old girl", "a man of 70, heavy".

`spec(age, sex, ...)` writes an ordinary model spec: a MakeHuman body of that age and sex with the measured growth
(makehuman.py + anthro.py: stature, head-to-body proportion), a GNM head that follows it (headfit.py), eyes, simple
neutral clothes as shell parts sized from the body's own joints, and a skin (skin.py). Everything in it is plain
spec, to edit like any other model. `describe(spec)` measures the body against the references (anthro.table).

Clothes ("outfit"): "tee_shorts" (default from 2 years), "onesie" (default under 2: a baby's bodysuit over a nappy's
bulk), "underwear" (briefs + a crop top), "none". Figures are dressed by default.
"""
from __future__ import annotations

import numpy as np

STAGES = ((1.5, "baby"), (4, "toddler"), (9, "child"), (13, "pre-teen"), (20, "teen"), (60, "adult"), (200, "elder"))
OUTFITS = ("tee_shorts", "onesie", "underwear", "none")
COLORS = {"tee": "#8fa3b5", "shorts": "#5b6470", "onesie": "#d9d2c0", "top": "#b8b0a4", "briefs": "#b8b0a4"}


def stage(age: float) -> str:
    return next(n for a, n in STAGES if age < a)


def _joints(base: dict) -> dict:
    from . import base as basemod
    return {k: np.array(v["pos"], float) for k, v in basemod.template_joints(base).items()}


def outfit(base: dict, kind: str, colors: dict | None = None) -> dict:
    """{"parts", "blobs", "bones", "joints"} of simple clothes for a base body: shell parts over the skin, their
    regions (boxes and sleeve cones) placed from the body's own joints, so they fit any age."""
    if kind not in OUTFITS:
        raise ValueError(f"outfit: one of {', '.join(OUTFITS)}")
    if kind == "none":
        return {"parts": {}, "blobs": {}, "bones": {}, "joints": {}}
    from . import base as basemod
    J = _joints(base)
    P = np.asarray(basemod.source(base)["P"], float)
    H = float(P[:, 2].max() - P[:, 2].min())
    sh, hip, knee, neck, elbow = J["shoulder.L"], J["hip.L"], J["knee.L"], J["neck"], J["elbow.L"]
    mid = P[(np.abs(P[:, 0]) < 0.006 * H / 0.75) & (P[:, 2] < J["pelvis"][2] + 0.02 * H)]
    crotch = float(mid[:, 2].min())
    c = {**COLORS, **(colors or {})}
    r = lambda v: [round(float(x), 4) for x in v]  # noqa: E731
    # the torso's half depth, and where its sides are at the waist
    tor = P[(P[:, 2] > crotch) & (P[:, 2] < sh[2]) & (np.abs(P[:, 0]) < sh[0])]
    yc = float(0.5 * (tor[:, 1].min() + tor[:, 1].max()))
    yd = float(0.5 * np.ptp(tor[:, 1])) + 0.05 * H
    xw = float(min(0.5 * (hip[0] + J["wrist.L"][0]) * 0.9, sh[0] + 0.02 * H))
    thigh = hip[2] - knee[2]
    arm = elbow - sh
    parts, blobs, bones, joints = {}, {}, {}, {}

    def box(name, part, z0, z1, x=xw, **kw):
        blobs[name] = {"at": r([0, yc, 0.5 * (z0 + z1)]), "shape": "box", "size": r([x, yd, 0.5 * (z1 - z0)]), "part": part, **kw}

    def sleeves(part, t):
        joints[f"{part}_sleeve.L"] = {"pos": r(sh + t * arm), "r": 0.01}
        bones[f"{part}_sleeve.L"] = {"a": "shoulder.L", "b": f"{part}_sleeve.L", "r_a": round(0.062 * H, 4), "r_b": round(0.05 * H, 4),
                                     "part": part}
    neck_z = float(neck[2] - 0.004 * H / 0.75) if neck[2] - sh[2] < 0.03 * H else float(sh[2] + 0.55 * (neck[2] - sh[2]))
    top_z = neck_z + 0.012 * H
    from . import headfit
    chin = float(P[headfit.table()["lm68"][8], 2]) if len(P) == headfit.table()["vertices"] else top_z + 0.1 * H
    box_top = min(top_z + 0.03 * H, chin - 0.01 * H)  # (under the chin: a toddler's lies on the chest, and the cloth's
    # region took a shell of it)
    def neck_hole(part):  # a round neckline: the cloth cut away round the neck's base
        nr = float(np.abs(P[(np.abs(P[:, 2] - neck_z) < 0.006 * H) & (np.abs(P[:, 0]) < 0.7 * sh[0])][:, 0]).max())
        blobs[f"{part}_neck"] = {"at": r([0, float(neck[1]) - 0.2 * nr, top_z + 0.02 * H]), "size": r([1.18 * nr, 1.3 * nr, 0.05 * H]),
                                 "part": part, "op": "subtract", "blend": 0.002}
    hem = crotch + 0.03 * H
    if kind == "tee_shorts":
        # plain shells (the body's surface pushed out): the garment option's closing and hanging made studs and ruffs
        # at the fine rings of the chest's and armpits' topology on small bodies
        parts["tee"] = {"shell": "body", "offset": round(0.004 + 0.005 * H, 4), "color": c["tee"], "roughness": 0.85, "blend": 0.004}
        parts["shorts"] = {"shell": "body", "offset": round(0.003 + 0.003 * H, 4), "color": c["shorts"], "roughness": 0.9}
        box("tee_torso", "tee", hem, box_top, x=float(sh[0] + 0.012 * H), round=round(0.02 * H, 4))
        neck_hole("tee")
        sleeves("tee", 0.55)
        box("shorts_region", "shorts", hip[2] - 0.5 * thigh, crotch + 0.105 * H, round=round(0.012 * H, 4))
    elif kind == "onesie":
        parts["onesie"] = {"shell": "body", "offset": round(0.006 * H / 0.75, 4), "color": c["onesie"], "roughness": 0.9, "blend": 0.004}
        box("onesie_torso", "onesie", crotch - 0.035 * H, box_top, x=float(sh[0] + 0.012 * H), round=round(0.02 * H, 4))
        neck_hole("onesie")
        sleeves("onesie", 0.5)
    else:  # underwear
        for p in ("top", "briefs"):
            parts[p] = {"shell": "body", "offset": 0.003, "color": c[p], "roughness": 0.85}
        box("briefs_region", "briefs", hip[2] - 0.14 * thigh, crotch + 0.09 * H)
        box("top_region", "top", crotch + 0.62 * (sh[2] - crotch), top_z - 0.03 * H, x=float(sh[0] * 0.93))
    return {"parts": parts, "blobs": blobs, "bones": bones, "joints": joints}


def spec(age: float = 30, sex: float | str = 0.5, weight: float = 0.5, muscle: float | None = None,
         height: float | None = None, seed: int | None = None, outfit_kind: str | None = None, tone: dict | float | None = None,
         skin: dict | bool | None = None, colors: dict | None = None, head: dict | None = None) -> dict:
    """A model spec for a person. sex: 0 / "female" .. 1 / "male" (children under ~10 differ little by it);
    height (m) overrides the measured median; seed picks the face (a different person per seed); tone = a
    Fitzpatrick number 1..6 or skin.tone's dict; skin = false for clay only, or skin keys to merge."""
    sx = {"female": 0.0, "f": 0.0, "girl": 0.0, "woman": 0.0, "male": 1.0, "m": 1.0, "boy": 1.0, "man": 1.0}.get(sex, sex) if isinstance(sex, str) else sex
    if not isinstance(sx, (int, float)):
        raise ValueError('human: sex is 0 (female) .. 1 (male), or "female" / "male"')
    age, sx = float(age), float(sx)
    if not 0 <= age <= 100:
        raise ValueError("human: age in years, 0..100")
    seed = int(seed if seed is not None else 1 + (int(age * 7) + int(sx * 3) * 5) % 40)
    young = age < 13
    body = {"source": "makehuman", "age": age, "sex": sx, "weight": weight,
            "muscle": float(muscle) if muscle is not None else (0.35 if young else 0.5)}
    kind = outfit_kind or ("onesie" if age < 2 else "tee_shorts")
    if young or kind in ("tee_shorts", "onesie"):
        body["nipples"] = 0.0  # (smoothed into the chest: the clothes are shells of the body, and they printed through)
    if height:
        body["height"] = float(height)
    # a face: the seed's own features at a spread that leaves children and women theirs (wide spreads masculinise),
    # lips together, lids a little open
    hd = {"source": "gnm", "follow_body": True, "seed": seed, "spread": 0.35 if (young or sx < 0.5) else 0.5,
          "expression": {"left_eye_region_000": 0.6, "right_eye_region_000": 0.6}, **(head or {})}
    base = {"body": body, "eyes": "eyes", "cornea": True, "head": hd}
    from . import base as basemod
    P = np.asarray(basemod.source(base)["P"], float)
    H = float(P[:, 2].max() - P[:, 2].min())
    base["look_at"] = [0.0, -4.0, round(0.93 * H, 3)]
    o = outfit(base, kind, colors)
    out = {"symmetry": True, "blend": 0.035, "base": base,
           "parts": {"body": {}, "eyes": {"color": "#e8e0d6"}, **o["parts"]},
           "joints": o["joints"], "bones": o["bones"], "blobs": o["blobs"]}
    if skin is not False:
        t = {"fitzpatrick": float(tone)} if isinstance(tone, (int, float)) else dict(tone or {"fitzpatrick": 3})
        out["skin"] = {"tone": t, "age": age, "sex": sx, **(skin if isinstance(skin, dict) else {})}
    return out


def measures(sp: dict) -> dict:
    """anthro.measure of a spec's base body (m)."""
    from . import anthro, base as basemod, headfit
    tpl = basemod.source(sp["base"])
    P = np.asarray(tpl["P"], float)
    chin = float(P[headfit.table()["lm68"][8], 2]) if tpl.get("name") == "makehuman" else float(tpl.get("chin_z"))
    return anthro.measure(P, tpl["J"], chin)


def describe(sp: dict) -> str:
    """The person's body measured against the references for its age and sex (ours | reference (ratio), cm)."""
    from . import anthro
    body = sp["base"].get("body") or {}
    age, sx = float(body.get("age", 25)), float(body.get("sex", 1.0))
    return (f"{stage(age)}, {age:g} y, sex {sx:g} (0 female .. 1 male): " + anthro.table([("", age, sx, measures(sp))]).strip()
            + "\n(ours | reference (ratio), cm. References: WHO medians for stature, Snyder 1977 means for the rest; "
              "biacromial here is between the shoulder JOINTS, ~10-15% inside the bone points the reference tapes)")
