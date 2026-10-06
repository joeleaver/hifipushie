"""A whole human from a description: "a 3-year-old girl", "a man of 70, heavy".

`spec(age, sex, ...)` writes an ordinary model spec: a MakeHuman body of that age and sex with the measured growth
(makehuman.py + anthro.py: stature, head-to-body proportion), a GNM head that follows it (headfit.py), eyes, simple
neutral clothes as shell parts sized from the body's own joints, and a skin (skin.py). Everything in it is plain
spec, to edit like any other model. `describe(spec)` measures the body against the references (anthro.table).

Clothes ("outfit"): "tee_shorts" (default from 2 years), "onesie" (default under 2: a baby's bodysuit over a nappy),
"underwear" (briefs + a crop top), "none". Figures are dressed by default. The clothes are cloth with their own volume
(base.garment: closed over the body's dips, hanging from the chest and belly as a tube), not shells of the skin, which
read as body paint (navel, muscles and nipples printed through). An adult woman has a bust by default (`bust_default`,
MakeHuman's breast targets), lifted when dressed as a bra lifts it; `face` gives each seed its own features.
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
    a0, a1 = sh, J["wrist.L"] + 0.6 * (J["wrist.L"] - elbow)  # the arm, on to the fingertips
    ab = a1 - a0
    Pa = np.c_[np.abs(P[:, 0]), P[:, 1:]]
    ta = np.clip(((Pa - a0) @ ab) / float(ab @ ab), 0, 1)
    arm_d = np.linalg.norm(Pa - (a0 + ta[:, None] * ab), axis=1)

    def breadth(z0, z1):
        """The torso's half breadth between two heights, the arms and hands left out."""
        m = (P[:, 2] > z0) & (P[:, 2] < z1) & ((arm_d > 0.05 * H) | (ta < 0.1))
        return float(np.abs(P[m][:, 0]).max())

    def box(name, part, z0, z1, x=xw, **kw):
        blobs[name] = {"at": r([0, yc, 0.5 * (z0 + z1)]), "shape": "box", "size": r([x, yd, 0.5 * (z1 - z0)]), "part": part, **kw}

    def sleeves(part, t):
        joints[f"{part}_sleeve.L"] = {"pos": r(sh + t * arm), "r": 0.01}
        bones[f"{part}_sleeve.L"] = {"a": "shoulder.L", "b": f"{part}_sleeve.L", "r_a": round(0.062 * H, 4), "r_b": round(0.05 * H, 4),
                                     "part": part}
    neck_z = float(neck[2] - 0.004 * H / 0.75) if neck[2] - sh[2] < 0.03 * H else float(sh[2] + 0.55 * (neck[2] - sh[2]))
    top_z = neck_z + 0.012 * H
    from . import headfit
    tpl_ = basemod.source(base)
    chin = (float(tpl_["chin_lm"]) if tpl_.get("chin_lm") is not None else
            float(P[headfit.table()["lm68"][8], 2]) if len(P) == headfit.table()["vertices"] else top_z + 0.1 * H)
    box_top = min(top_z + 0.03 * H, chin - 0.01 * H)  # (under the chin: a toddler's lies on the chest, and the cloth's
    # region took a shell of it)
    def neck_hole(part):  # a round neckline: the cloth cut away round the neck's base
        nr = float(np.abs(P[(np.abs(P[:, 2] - neck_z) < 0.006 * H) & (np.abs(P[:, 0]) < 0.7 * sh[0])][:, 0]).max())
        blobs[f"{part}_neck"] = {"at": r([0, float(neck[1]) - 0.2 * nr, top_z + 0.02 * H]), "size": r([1.18 * nr, 1.3 * nr, 0.05 * H]),
                                 "part": part, "op": "subtract", "blend": 0.002}
    hem = crotch + 0.03 * H
    k = H / 1.7  # lengths below are an adult's, scaled to the body
    cloth = lambda **kw: {"close": 40, "ease": round(0.004 * k, 4), "tube_ease": round(0.012 * k, 4), **kw}  # noqa: E731
    if kind == "tee_shorts":
        # cloth with its own volume (base.garment): closed over the body's dips, hanging from the chest and belly as a
        # tube down to the hem (no navel, no muscles, the bust bridged), the shorts' legs tubes from the thigh
        parts["tee"] = {"shell": "body", "offset": round(0.005 * k, 4), "color": c["tee"], "roughness": 0.85, "blend": 0.004,
                        "garment": cloth(hang=0.7, tube={"top": round(float(sh[2]) - 0.075 * k, 4), "bottom": round(hem - 0.04 * k, 4),
                                                         "folds": 0.6, "band": round(0.08 * k, 4), "arms": "taper"})}
        parts["shorts"] = {"shell": "body", "offset": round(0.003 * k, 4), "color": c["shorts"], "roughness": 0.9,
                           "garment": cloth(close=20, ease=round(0.001 * k, 4), tube_ease=round(0.008 * k, 4), legs={"folds": 0.5, "band": round(0.08 * k, 4)})}
        box("tee_torso", "tee", hem, box_top, x=float(sh[0] + 0.012 * H), round=round(0.02 * H, 4))
        # (hips wider than the shoulders: the torso's box cut the tee's sides off there, a notch in the hem)
        box("tee_hips", "tee", hem, hem + 0.13 * H, x=breadth(hem, hem + 0.1 * H) + 0.014 * H, round=round(0.02 * H, 4))
        neck_hole("tee")
        sleeves("tee", 0.55)
        box("shorts_region", "shorts", hip[2] - 0.5 * thigh, crotch + 0.105 * H,
            x=breadth(hip[2] - 0.5 * thigh, crotch + 0.105 * H) + 0.025 * H, round=round(0.012 * H, 4))
    elif kind == "onesie":
        # a bodysuit over a nappy: the cloth closed over the belly, room round the seat
        parts["onesie"] = {"shell": "body", "offset": round(0.006 * k, 4), "color": c["onesie"], "roughness": 0.9, "blend": 0.004,
                           "garment": cloth(close=60)}
        xb = breadth(crotch, crotch + 0.14 * H)
        low = P[(P[:, 2] > crotch) & (P[:, 2] < crotch + 0.14 * H) & (np.abs(P[:, 0]) < xb)]
        box("onesie_torso", "onesie", crotch - 0.035 * H, box_top, x=max(float(sh[0] + 0.012 * H), xb + 0.03 * H), round=round(0.02 * H, 4))
        neck_hole("onesie")
        sleeves("onesie", 0.5)
        # the nappy under it: bulk round the seat, from the crotch to the navel
        blobs["onesie_nappy"] = {"at": r([0, float(0.5 * (low[:, 1].min() + low[:, 1].max())), crotch + 0.07 * H]), "size": r([xb + 0.006 * H, 0.5 * float(np.ptp(low[:, 1])) + 0.01 * H, 0.08 * H]),
                                 "part": "onesie", "layer": 1, "blend": round(0.02 * H, 4)}
    else:  # underwear: briefs and a crop top / bra, close to the body
        for p in ("top", "briefs"):
            parts[p] = {"shell": "body", "offset": round(0.003 * k, 4), "color": c[p], "roughness": 0.85,
                        "garment": cloth(close=12 if p == "top" else 6, ease=round(0.001 * k, 4))}
        box("briefs_region", "briefs", hip[2] - 0.14 * thigh, crotch + 0.09 * H)
        box("top_region", "top", crotch + 0.62 * (sh[2] - crotch), top_z - 0.03 * H, x=float(sh[0] * 0.93))
    return {"parts": parts, "blobs": blobs, "bones": bones, "joints": joints}


def spec(age: float = 30, sex: float | str = 0.5, weight: float = 0.5, muscle: float | None = None,
         height: float | None = None, seed: int | None = None, outfit_kind: str | None = None, tone: dict | float | None = None,
         skin: dict | bool | None = None, colors: dict | None = None, head: dict | None = None,
         bust: float | None = None, firmness: float | None = None, source: str = "makehuman",
         style: str | dict | None = None) -> dict:
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
    if kind != "none":
        body["nipples"] = 0.0  # (flat under cloth)
    b = bust_default(age, sx, kind != "none")
    if bust is not None or firmness is not None or b:
        b = b or {"bust": 0.5, "firmness": 0.5}
        body["bust"] = round(float(bust) if bust is not None else b["bust"], 3)
        body["firmness"] = round(float(firmness) if firmness is not None else b["firmness"], 3)
    if height:
        body["height"] = float(height)
    hd = {**face(age, sx, seed), **(head or {})}
    if source == "human":  # one human mesh (onemesh.py): the head is the body's own, nothing to graft or follow
        body["source"] = "human"
        hd = {k: v for k, v in hd.items() if k not in ("source", "follow_body")}
    elif source != "makehuman":
        raise ValueError('human: source is "makehuman" (a GNM head grafted onto the body) or "human" (one mesh)')
    base = {"body": body, "eyes": "eyes", "cornea": True, "head": hd}
    sheet = None
    if style:  # a style sheet (styles/human_*.json) or base.style keys: the one mesh reshaped, clothes placed on the result
        if source != "human":
            raise ValueError('human: style needs source="human" (the style sliders reshape the one mesh)')
        if isinstance(style, str):
            from . import stylesheet
            sheet = style
            base["style"] = dict(((stylesheet.load(style).get("spec") or {}).get("base") or {}).get("style") or {})
        else:
            base["style"] = dict(style)
    from . import base as basemod
    P = np.asarray(basemod.source(base)["P"], float)
    H = float(P[:, 2].max() - P[:, 2].min())
    base["look_at"] = [0.0, -4.0, round(0.93 * H, 3)]
    o = outfit(base, kind, colors)
    out = {"symmetry": True, "blend": 0.035, "base": base, **({"style": {"sheet": sheet}} if sheet else {}),
           "parts": {"body": {}, "eyes": {"color": "#e8e0d6"}, **o["parts"]},
           "joints": o["joints"], "bones": o["bones"], "blobs": o["blobs"]}
    if skin is not False:
        t = {"fitzpatrick": float(tone)} if isinstance(tone, (int, float)) else dict(tone or {"fitzpatrick": 3})
        out["skin"] = {"tone": t, "age": age, "sex": sx, **(skin if isinstance(skin, dict) else {})}
    return out


def face(age: float, sex: float, seed: int) -> dict:
    """A person's head settings (base.head): a GNM head that follows the body (its age, sex, weight, size), the
    seed's own identity at a spread that leaves women and children theirs (wide spreads masculinise a bald head),
    and, drawn from the seed, what tells people apart at a glance: nose, lips, cheeks, chin, jaw, brow and eye size
    (headfit features), leaning the way of the person's sex and age (a child's round cheeks and full mouth; a
    woman's lighter jaw and brow, more so with age, when the skull's sex shows most). Lids open as in a relaxed
    face (the eye's height ~0.2 of the pupils' distance; GNM's neutral lids are lower), a trace of a smile."""
    rng = np.random.default_rng(1000 + int(seed))
    fem, child = float(np.clip(1 - sex, 0, 1)), float(np.clip((12 - age) / 8, 0, 1))
    old = float(np.clip((age - 45) / 30, 0, 1))
    u = lambda a: float(rng.uniform(-a, a))  # noqa: E731
    f = {"nose": u(0.7) - 0.25 * fem - 0.2 * child, "lips": u(0.5) + 0.5 * child + 0.3 * fem * old,
         "cheeks": u(0.4) + 0.6 * child + 0.15 * fem, "chin": u(0.6) - 0.3 * fem * (0.5 + old),
         "jaw": u(0.5) - 0.5 * fem * (0.4 + old) - 0.2 * child, "brow_ridge": u(0.4) - 0.5 * fem * (0.4 + old),
         "eyes": u(0.35) + 0.25 * child + 0.15 * fem}
    lid = 0.0026 + u(0.0006)
    return {"source": "gnm", "follow_body": True, "seed": int(seed), "spread": round(0.6 - 0.15 * max(fem, child), 3),
            "features": {k: round(float(np.clip(v, -1.5, 1.5)), 2) for k, v in f.items()},
            "expression": {"left_eye_region_000": 0.6, "right_eye_region_000": 0.6}, "mouth_gap": 0.001,
            "pose": {"lid_upper": round(-lid, 4), "lid_lower": -0.0008, "smile": round(0.001 + u(0.001), 4),
                     "brow_inner": round(0.0004 + u(0.0006), 4)}}


def bust_default(age: float, sex: float, supported: bool = True) -> dict | None:
    """An adult woman's chest by default (base.body bust / firmness, MakeHuman's breast targets). MakeHuman's own
    average cup stands ~18 mm ahead of the breast bone (AA); the default here ~32 mm (A/B), growing in from 11 to
    17 years, softer with age, and lifted when dressed (`supported`: what a bra does). None for children and men."""
    f = float(np.clip((0.6 - sex) / 0.2, 0, 1)) * float(np.clip((age - 11) / 6, 0, 1))
    if f <= 0:
        return None
    firm = float(np.interp(age, [16, 30, 50, 75], [0.7, 0.65, 0.5, 0.4])) + (0.2 if supported else 0.0)
    return {"bust": 0.5 + 0.2 * f, "firmness": min(firm, 0.95)}


def measures(sp: dict) -> dict:
    """anthro.measure of a spec's base body (m)."""
    from . import anthro, base as basemod, headfit
    tpl = basemod.source(sp["base"])
    P = np.asarray(tpl["P"], float)
    chin = (float(P[headfit.table()["lm68"][8], 2]) if tpl.get("name") == "makehuman" else
            float(tpl["chin_mh"]) if tpl.get("chin_mh") is not None else float(tpl.get("chin_z")))
    return anthro.measure(P, tpl["J"], chin)


def describe(sp: dict) -> str:
    """The person's body measured against the references for its age and sex (ours | reference (ratio), cm)."""
    from . import anthro
    body = sp["base"].get("body") or {}
    age, sx = float(body.get("age", 25)), float(body.get("sex", 1.0))
    m = measures(sp)
    bust = (f"\nbust: {m['bust_projection'] * 1000:.0f} mm ahead of the breast bone, girth {m['bust_circ'] * 100:.0f} cm (base.body bust "
            f"{body.get('bust')}, firmness {body.get('firmness')}; ~10-20 mm a flat chest, 30-40 an A/B cup, 50-60 a C/D)"
            if body.get("bust") is not None and "bust_projection" in m else "")
    return (f"{stage(age)}, {age:g} y, sex {sx:g} (0 female .. 1 male): " + anthro.table([("", age, sx, m)]).strip() + bust
            + "\n(ours | reference (ratio), cm. References: WHO medians for stature, Snyder 1977 means for the rest; "
              "biacromial here is between the shoulder JOINTS, ~10-15% inside the bone points the reference tapes)")
