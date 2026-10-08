"""Likeness, part 3: references we ASK FOR (a brief) and references we're HANDED (a check).

Joe: "We don't have any way of predicting what kind of reference photos we'll get, unless hifipushie is the one
responsible for generating them. But when we are, we can try to get the best ones we can."

- `reference_brief(kind="head" | "figure")`: the shot list the likeness checklist wants, what makes each shot usable,
  and the prompt wording for an image generator (one common identity block + a per-shot line, so the person stays the
  same across views). Shape shared with the clothing checklist's brief (cloth_reference.reference_brief): {"subject",
  "common": {"prompt", "negative"}, "shots": [{"id", "view": {"yaw", "pitch", "framing"}, "light", "purpose": [item
  ids], "must_show": [...], "prompt"}], "text"}.
- `check_references(views)`: what a set of pictures lacks or does badly: views present (the detector's head pose),
  lens (a fitted camera's focal, when there is one), expression (the detector's blendshapes), light evenness,
  ears / hairline covered, identity consistency between views (proportions that don't change with the head's turn).
  Returns {"supported": [{"id", "by", "why"}], "unsupported": [{"id", "why", "shot"}], "pictures": [...], "text"}.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

COMMON = ("Studio reference photograph of the same adult person{subject}, for a 3D artist: neutral relaxed expression, "
          "mouth closed, lips together, eyes open looking level at the horizon, head level (no tilt), long lens (about "
          "100 mm, full-frame equivalent) at eye height from about 2 m, sharp focus on the whole face, plain mid-grey "
          "seamless background, hair pulled back off the forehead and behind the ears, no glasses, no hat, no jewellery, "
          "no make-up change, neck and jaw line uncovered (open collar or bare shoulders). Same person, same lighting, "
          "same scale and same camera height in every view of this set.")
NEGATIVE = ("smile, open mouth, raised or furrowed brows, squint, wide-angle distortion, close-up selfie, tilted or "
            "nodding head, dramatic or coloured light, hard shadows across the face (except the side-light pass), hair "
            "over the ears or forehead, glasses, hat, jewellery, collar over the jaw, beard hiding the jaw line, "
            "painterly or stylised rendering, a different person between views")
LIGHT = {"even": "Soft, even, frontal light (a large softbox or overcast daylight from just above the camera), little "
                 "shadow anywhere on the face.",
         "raking": "One soft key light 60 degrees to the subject's left and a little above, no fill: the side-light pass, "
                   "the face's planes, hollows and folds shown by shading; everything else as the other shots."}


def _items(stages=None, views=None) -> list:
    from . import likeness
    out = []
    for it in likeness.checklist():
        if stages and it["stage"] not in stages:
            continue
        if views and not set(views) & set(it["views"]):
            continue
        out.append(it["id"])
    return out


def reference_brief(kind: str = "head", subject: str = "") -> dict:
    """The shot list for a likeness (kind "head") or a whole person ("figure": adds full-body A-pose front and side for
    the body's proportions), with what each shot must show and generator prompts that keep the identity."""
    from . import likeness
    sub = f" ({subject})" if subject else ""
    common = COMMON.format(subject=sub)
    shape_ids = [it["id"] for it in likeness.checklist() if it["measure"]["kind"] == "shape"]
    jaw_ids = [it["id"] for it in likeness.checklist() if it["measure"]["kind"] == "jaw"]
    shots = [
        {"id": "front", "view": {"yaw": 0, "pitch": 0, "framing": "bust"}, "light": "even",
         "purpose": _items(views=["front"]),
         "must_show": ["the face square to the camera: both ears' edges equally visible, pupils level",
                       "both ears whole and the hairline (hair pulled back)", "the jaw's outline and the neck under it",
                       "the head filling about half the picture's height (a bust: head and top of the shoulders)"],
         "line": "Front view, the face square to the camera, head and shoulders."},
        {"id": "profile_left", "view": {"yaw": 90, "pitch": 0, "framing": "bust"}, "light": "even",
         "purpose": _items(views=["profile"]) + jaw_ids,
         "must_show": ["a TRUE profile: the far eye and brow hidden behind the nose's bridge",
                       "the whole near ear, the jaw's corner and lower border, the neck under the jaw (no collar)",
                       "the nose's tip, the columella and the lips' profile against the plain background"],
         "line": "True left profile, the subject's left side to the camera, the far eye hidden, head and shoulders."},
        {"id": "three_quarter_left", "view": {"yaw": 45, "pitch": 0, "framing": "bust"}, "light": "even",
         "purpose": _items(views=["three_quarter"]) + jaw_ids,
         "must_show": ["the head turned 45 degrees: the far eye still whole, the nose's tip inside the far cheek's line",
                       "the near jaw's corner, lower border and the neck under it"],
         "line": "Three-quarter view, the head turned 45 degrees to show its left side, the far eye still visible."},
        {"id": "front_raking", "view": {"yaw": 0, "pitch": 0, "framing": "bust"}, "light": "raking",
         "purpose": shape_ids,
         "must_show": ["exactly the front shot's pose, framing and expression, only the light changed"],
         "line": "Front view again, identical pose, lit by one side light from the subject's left."},
        {"id": "three_quarter_raking", "view": {"yaw": 45, "pitch": 0, "framing": "bust"}, "light": "raking",
         "purpose": shape_ids + jaw_ids, "optional": True,
         "must_show": ["exactly the three-quarter shot's pose, only the light changed"],
         "line": "Three-quarter view again, identical pose, lit by one side light from the subject's left."},
        {"id": "back", "view": {"yaw": 180, "pitch": 0, "framing": "bust"}, "light": "even", "optional": True,
         "purpose": [], "must_show": ["the back of the head and neck, hair as worn"],
         "line": "Back view, the back of the head and shoulders."},
        {"id": "top", "view": {"yaw": 0, "pitch": -80, "framing": "head"}, "light": "even", "optional": True,
         "purpose": [], "must_show": ["the head from above: the skull's plan shape, the hair's parting"],
         "line": "Top view, camera above the head looking down."},
    ]
    if kind == "figure":
        shots += [
            {"id": "figure_front", "view": {"yaw": 0, "pitch": 0, "framing": "full"}, "light": "even",
             "purpose": ["stature", "heads", "biacromial", "hip_breadth"],
             "must_show": ["the whole figure, head to feet, in an A-pose (arms 30-45 degrees out, palms forward, feet "
                           "hip-width)", "camera at chest height from far away (long lens): no perspective taper"],
             "line": "Full-body front view in an A-pose, arms 40 degrees out from the body, head to feet."},
            {"id": "figure_side", "view": {"yaw": 90, "pitch": 0, "framing": "full"}, "light": "even",
             "purpose": ["sitting_height", "trochanter_height", "foot_length"],
             "must_show": ["the whole figure in profile, arms relaxed at the sides, standing straight"],
             "line": "Full-body left side view, standing straight, arms relaxed, head to feet."}]
    for s in shots:
        s["prompt"] = f"{common} {s['line']} {LIGHT[s['light']]}"
    text = [f"REFERENCE BRIEF ({kind}){sub}: shoot or generate these; optional ones help but aren't needed.",
            f"common to every shot: {common}", f"avoid: {NEGATIVE}"]
    for s in shots:
        text.append(f"- {s['id']}{' (optional)' if s.get('optional') else ''}: yaw {s['view']['yaw']}, {s['view']['framing']}, "
                    f"{s['light']} light; serves {len(s['purpose'])} checklist items; must show: " + "; ".join(s["must_show"]))
        text.append(f"    prompt: {s['prompt']}")
    return {"subject": subject, "kind": kind, "common": {"prompt": common, "negative": NEGATIVE},
            "shots": shots, "text": "\n".join(text)}


# ---- checking a set of pictures ------------------------------------------------------------------------------------

def _photo(image: str, cam=None, points=None, yaw_hint=None) -> dict:
    """A picture read like likeness.photo_sides, without a model: the detector on the face (found first on the whole
    picture, then again on a crop round it), its blendshapes and head pose."""
    from PIL import Image
    from . import likeness as lk
    img = Image.open(image).convert("RGB")
    if points:
        box = lk._box(points, img.size)
    else:
        P0 = lk.detect([img])[0]
        if P0 is None:  # a small face in a big picture (a full figure): look in overlapping tiles
            W, H = img.size
            for frac in (0.5, 0.33):
                s = int(min(W, H) * frac) if frac < 0.5 else int(max(W, H) * frac)
                s = max(min(s, W, H), 64)
                for y in range(0, max(H - s, 0) + 1, max(s // 2, 1)):
                    for x in range(0, max(W - s, 0) + 1, max(s // 2, 1)):
                        P0 = lk.detect_region(img, (x, y, x + s, y + s))
                        if P0 is not None:
                            break
                    if P0 is not None:
                        break
                if P0 is not None:
                    break
        if P0 is None:
            return {"image": image, "img": img, "side": lk.Side(None, None), "info": {}, "kind": "unknown", "box": None,
                    "mmpx": None}
        box = lk._box({i: p for i, p in enumerate(P0[lk.MP68])}, img.size)
    info = lk.detect_region(img, box, info=True) or {}
    P = info.get("P")
    yaw = lk.head_yaw(info.get("M"))
    kind = lk.view_kind(yaw_hint if yaw_hint is not None else (yaw if yaw is not None else 0.0))
    side = lk.Side(P, None)
    mmpx = None
    if cam is not None:
        mmpx = float(cam["t"][2] / cam["f"] * 1000.0)
    elif P is not None:  # a typical adult's inner-eye-corner gap (Farkas: ~32 mm) as the scale
        try:
            mmpx = 32.0 / max(np.linalg.norm(side.pt(133) - side.pt(362)), 1e-6)
        except lk.Unmeasurable:
            mmpx = None
    return {"image": image, "img": img, "side": side, "info": info, "kind": kind, "box": box, "mmpx": mmpx,
            "view": {"image": image}, "cam": cam or {"f": 0.0, "size": list(img.size), "t": [0, 0, 1]}, "yaw": yaw}


def _light(ph) -> dict:
    """How even the light on the face is: p90 / p10 of the skin's linear luminance, and left / right cheek."""
    from . import likeness_shape as ls
    s = ph["side"]
    if s.P is None:
        return {}
    box = ph["box"]
    crop = ph["img"].crop(tuple(int(round(v)) for v in box))
    k = 1.0
    to_px = lambda P: (np.asarray(P, float) - [int(round(box[0])), int(round(box[1]))]) * k  # noqa: E731
    H, W = crop.size[1], crop.size[0]
    m = ls.skin_mask(s, (H, W), to_px, 1.0 / max(ph["mmpx"] or 1.0, 1e-6))
    if m.sum() < 200:
        return {}
    Y = ls._lin(crop)
    p10, p90 = np.percentile(Y[m], [10, 90])
    xx = np.mgrid[0:H, 0:W][1]
    cx = to_px(s.pt(168)[None])[0][0]
    l, r = Y[m & (xx < cx)], Y[m & (xx >= cx)]
    return {"contrast": float(p90 / max(p10, 1e-6)),
            "left_right": float(max(l.mean(), r.mean()) / max(min(l.mean(), r.mean()), 1e-6)) if len(l) and len(r) else None}


PROPS = (("lower_over_middle", ([2], [152]), ([168], [2])), ("mouth_in_lower", ([2], [13, 14]), ([2], [152])),
         ("eyes_to_mouth_over_mouth_to_chin", ([33, 133, 362, 263], [13, 14]), ([13, 14], [152])))


def _props(side) -> dict:
    """Vertical proportions (along the face's own axis): nearly unchanged by the head's turn, so a set's pictures of
    one person should agree on them."""
    from . import likeness as lk
    out = {}
    try:
        ex, ey = side.frame()
        for nm, (a0, a1), (b0, b1) in PROPS:
            num = (side.pt(a1) - side.pt(a0)) @ ey
            den = (side.pt(b1) - side.pt(b0)) @ ey
            out[nm] = float(num / den) if abs(den) > 1e-6 else None
    except lk.Unmeasurable:
        pass
    return out


def check_references(views: list, name: str | None = None) -> dict:
    """What a set of reference pictures supports. views: [{"image", "yaw"?: deg hint, ...}] or image paths; with
    `name`, the model's fitted cameras (human_refs.json) give the lens and scale for pictures they cover."""
    from . import likeness as lk
    cams = {}
    if name:
        try:
            refs = lk._refs(name)
            cams = {v["image"]: (c, v["points"]) for v in refs["views"] for c in [refs["cameras"][refs["views"].index(v)]]}
        except ValueError:
            cams = {}
    vs = [v if isinstance(v, dict) else {"image": v} for v in views]
    pics = []
    for v in vs:
        cam, pts = cams.get(v["image"], (None, None))
        ph = _photo(v["image"], cam, pts, v.get("yaw"))
        notes = lk.picture_notes(ph) if ph["side"].P is not None else {"problems": ["no face found"], "image": Path(v["image"]).name, "view": "unknown"}
        if cam is None:
            notes["problems"] = [p for p in notes["problems"] if not p.startswith("short lens")]
            notes["lens_mm"] = None
            notes["problems"].append("lens unknown until the camera is fitted (human_reference)")
        lt = _light(ph)
        notes["light"] = lt
        if lt.get("contrast") and lt["contrast"] > 4.0:
            notes["problems"].append(f"uneven light on the face (bright / dark skin {lt['contrast']:.1f}x): fine for the "
                                     "side-light pass only")
        if lt.get("left_right") and lt["left_right"] > 1.5:
            notes["problems"].append(f"one cheek {lt['left_right']:.1f}x brighter than the other: a side light")
        notes["props"] = _props(ph["side"])
        pics.append((ph, notes))
    kinds = [ph["kind"] for ph, _ in pics]
    # identity consistency: the vertical proportions agree between pictures of one person
    inconsist = []
    keys = {k for _, n in pics for k, v in n["props"].items() if v}
    for k in sorted(keys):
        vals = [(n["image"], n["props"][k]) for _, n in pics if n["props"].get(k)]
        if len(vals) >= 2:
            a = np.array([v for _, v in vals])
            if a.max() / a.min() > 1.08:
                inconsist.append(f"{k}: " + ", ".join(f"{im} {v:.2f}" for im, v in vals))
    brief = {s["id"]: s for s in reference_brief("head")["shots"]}
    sup, uns = [], []
    expr = any(any("smile" in p or "mouth open" in p for p in n["problems"]) for _, n in pics)
    ears_hidden = all(any("ears hidden" in p for p in n["problems"]) for _, n in pics) if pics else True
    hair_fore = all(any("forehead" in p for p in n["problems"]) for _, n in pics) if pics else True
    for it in lk.checklist():
        by = [i for i, k in enumerate(kinds) if lk._allowed(it, k, kinds)[0]]
        shot = ("profile_left" if "profile" in it["views"] else "front_raking" if it["measure"]["kind"] == "shape"
                else "three_quarter_left" if it["measure"]["kind"] == "jaw" else "front")
        why = None
        if not by:
            why = f"no {' or '.join(it['views'])} picture"
        elif it["region"] == "ears" and ears_hidden:
            why = "ears hidden in every picture"
        elif it["region"] == "forehead" and hair_fore:
            why = "hair over the forehead in every picture"
        elif expr and it["region"] in ("mouth",):
            why = "the expression moves the mouth (smile / open)"
        elif it["measure"]["kind"] == "jaw":
            why = None if by else "no turned picture"
        if why:
            uns.append({"id": it["id"], "name": it["name"], "why": why, "shot": shot})
        else:
            inferred = all(lk._allowed(it, kinds[i], kinds)[1] for i in by)
            sup.append({"id": it["id"], "name": it["name"], "by": by,
                        "why": ("inferred from a three-quarter view" if inferred else "")
                        + ("; needs a traced jaw (likeness_points)" if it["measure"]["kind"] == "jaw" else "")
                        + ("; judge by eye" if it["measure"]["kind"] == "judge" else "")})
    lines = [f"REFERENCE CHECK: {len(pics)} pictures ({', '.join(kinds)}); {len(sup)} checklist items supported, "
             f"{len(uns)} not."]
    for ph, n in pics:
        lines.append(f"- {n['image']}: {ph['kind']}" + (f", head yaw {ph['yaw']:.0f}" if ph.get("yaw") is not None else "")
                     + (f", lens ~{n['lens_mm']:.0f} mm" if n.get("lens_mm") else "")
                     + (f", light contrast {n['light'].get('contrast', 0):.1f}x" if n.get("light") else "")
                     + ": " + ("; ".join(n["problems"]) or "no problems found"))
    if inconsist:
        lines.append("IDENTITY: the pictures disagree on proportions that don't change with the head's turn (not one "
                     "person, or a generator drifting): " + " | ".join(inconsist))
    missing = sorted({u["shot"] for u in uns})
    for u in uns:
        lines.append(f"  not supported: {u['name']} ({u['why']}) -> shot '{u['shot']}'")
    inf = [s["name"] for s in sup if "inferred" in s["why"]]
    if inf:
        lines.append("  inferred only (tolerance x1.5): " + ", ".join(inf))
    if missing:
        lines.append("ASK FOR (reference_brief shots): " + ", ".join(missing))
    return {"supported": sup, "unsupported": uns, "pictures": [n for _, n in pics], "identity": inconsist,
            "ask_for": missing, "text": "\n".join(lines)}
