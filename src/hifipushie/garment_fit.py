"""Step 0's FIT, read as RATIOS within the picture and applied to the model's own body (C335).

Why ratios: the picture's person is not the model (t s0-1: the concept's legs ~20 % shorter against the torso than
Garrett's); a mm read off the picture, or an ease guessed from it, doesn't transfer, a ratio within the picture does:
the garment's width over the body's width at the same landmark, a garment edge's height as a fraction between two body
landmarks. The tool applies them to the model's own tape (body_tape): ease and heights in mm, each with its ratio and
where it came from. Nothing here is garment-specific: any landmark the picture shows, any edge the garment has.

FORM (garment_plan step "read", key "fit"):
  {view: a step-0 view, by name ("front") or index,
   landmarks: {landmark: v | [u, v]}   where each body landmark sits on that picture (needed for heights; >= 2)
   widths: [{at: landmark, garment: [[u,v],[u,v]] its two edges straight across, body: [[u,v],[u,v]] the body's edges
             there, body_from: "seen" | how the covered body's edges were inferred (e.g. "the leg inside the trouser:
             the knee's own width from the shoe"), garment_from?: "seen" (default) | how a covered garment edge was
             inferred, ratio?: garment / body (only with garment_from inferred, in place of the marks),
             why?: a garment narrower than the body (knit worn tight)}]
   heights: [{name, at: v | [u, v], source?}]  the garment's edges and levels (hem, waistband top, crotch, cuff ...)}
  a landmark: v | [u, v] | [[u, v], [u, v]] (both sides: their mean row) | {at: one of those, from: how a covered one
  was placed}; each height says how many mm it moves per 10 px of each landmark it hangs on (garment_fit_marks.py).
SEEN edges are measured on the picture: each end moved to the picture's own edge near the mark (garment_fit_marks.py).
LANDMARK CARD + CHECKS (C338): the model's landmarks drawn (step0_landmarks.png) and in words (FIND), with every fit
refusal; a width sits at its landmark's row or AT one of the garment's heights (a hem, a cuff: the body's section at
that height on the model, same part as the nearest landmark); a landmark further than DRIFT from where its neighbours
put it with the model's proportions is refused unless {at, from, why} (the worst out first, then again).
PARTS (C339, garment_fit_heights.py): a height is read between landmarks of its own part (`on`): the torso straight
up, a leg or an arm ALONG the limb (a sleeve end lands at the same place on the model's arm whatever its pose).
FLOOR / CROWN: marked or not, heights never hang on them: in a picture they are a shoe's sole and a hat's / the hair's
top, not the body's; a height beyond the outermost body landmark is extrapolated from the nearest body span (C336).
LANDMARKS: below. A torso level's width is the torso section's across the view; a limb's is its section square to the
limb, across it in the view; the girth is body_tape's at the same place. Ease = body girth x (ratio - 1): the garment's
section taken as the body's scaled by the ratio (stated in every source). Heights: the fraction between the two marked
landmarks either side (extrapolated beyond the outermost two, said so) on the model's own landmark heights.
OUTPUT (step 0's record): fit {landmark: {ratio, ease_mm, body_girth_mm, garment_girth_mm, body_width_mm,
  garment_width_mm, body: seen|inferred, garment: seen|inferred, source}}, heights {name: {z_mm (above the floor),
  fraction, between, source}}, fit_read (the marks as given). Refusals name the item and what to write instead.
"""
from __future__ import annotations

import math

import numpy as np

# landmark: (body_tape girth item or None = a height only, how it is taken)
LANDMARKS = {
    "chest": ({"square_to": "body", "at": "chest"}, "the torso at the chest level"),
    "armpit": ({"square_to": "body", "at": "armpit"}, "the torso at the armpit level"),
    "waist": ({"square_to": "body", "at": "waist"}, "the torso at the natural waist level"),
    "high_hip": ({"square_to": "body", "at": "high_hip"}, "the torso at the high hip (iliac crest)"),
    "hips": ({"square_to": "body", "at": "hips"}, "the torso at the hip joints + 2 cm"),
    "seat": ({"square_to": "body", "at": "seat"}, "the torso at the seat (fullest under the hips)"),
    "mid_thigh": ({"square_to": "thigh.L", "t": 0.5}, "one thigh, halfway hip -> knee"),
    "knee": ({"square_to": "shin.L", "t": 0.02}, "one leg at the knee joint"),
    "calf": ({"square_to": "shin.L", "fullest": [0.1, 0.5]}, "one leg at the fullest calf"),
    "ankle": ({"square_to": "shin.L", "t": 0.9}, "one leg just above the ankle joint"),
    "upper_arm": ({"square_to": "arm.L", "t": 0.5}, "one arm halfway shoulder -> elbow"),
    "elbow": ({"square_to": "forearm.L", "t": 0.02}, "one arm at the elbow joint"),
    "wrist": ({"square_to": "forearm.L", "t": 0.92}, "one arm just above the wrist joint"),
    "neck": ({"square_to": "neck", "t": 0.1}, "the base of the neck (higher, the section runs into the jaw: t s0-4)"),
    "shoulder": (None, "the shoulder point (where the shoulder turns down into the arm)"),
    "eyes": (None, "the eyes' height"),
    "crotch": (None, "the crotch level"), "floor": (None, "the floor"), "crown": (None, "the top of the head"),
}
# where each landmark IS, as you'd find it on a picture of any person (t s0-3: the model's "waist" and "ankle" were not
# the points the agent marked: the belt, the ankle bone; heights came out 4-9 cm off). The model's height for a
# landmark is its section line, drawn on the landmark card (garment_fit_look.card) beside these words.
FIND = {
    "chest": "the fullest chest, across the nipples",
    "armpit": "the armpit: where the arm leaves the torso",
    "waist": "the NATURAL waist: the narrowest torso, a few cm above the navel (not a belt or waistband: those are "
             "garment heights)",
    "high_hip": "the top of the hip bone (iliac crest), a hand's width under the natural waist",
    "hips": "the hip joints: the widest bony hip, level with the bump at the top of the thigh",
    "seat": "the fullest buttocks (side view), about halfway between the hips and the crotch",
    "crotch": "where the legs part",
    "mid_thigh": "halfway between the hip joint and the middle of the kneecap",
    "knee": "the middle of the kneecap",
    "calf": "the fullest calf",
    "ankle": "the narrowest leg just above the ankle bones",
    "upper_arm": "halfway between the shoulder point and the elbow",
    "elbow": "the point of the elbow",
    "wrist": "the wrist bone (where a watch sits)",
    "neck": "the base of the neck: where a shirt collar sits, where the neck meets the shoulders at the side",
    "shoulder": "the shoulder point: where the top of the shoulder turns down into the arm (a set-in sleeve's seam)",
    "eyes": "the centre of the eyes (a collar, hood or hat top is read between the neck and here)",
    "floor": "the floor (never used for heights: under a shoe)",
    "crown": "the top of the head (never used for heights: under hair or a hat)",
}
DRIFT = (0.15, 30.0)  # (a landmark this far from where its neighbours put it with the model's proportions, as a fraction
# of their span AND in mm on the model: refused unless it says why. Neighbours, not a fit over all: the picture's person
# has other proportions over long spans; t s0-2 0 flags, t s0-3 (belt as waist, guessed seat / crotch / calf) 4)
SIDE_VIEWS = ("side",)


class FitRefused(ValueError):
    pass


def view_index(views: list, v, where: str, bad: list):
    """A view by index or by its name (views[i]["view"]); None (and a refusal in bad) when neither."""
    names = [x.get("view") for x in views if isinstance(x, dict)]
    if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < len(views):
        return v
    if isinstance(v, str) and names.count(v) == 1:
        return names.index(v)
    listed = ", ".join(f"{i} or \"{n}\"" for i, n in enumerate(names))
    why = "two views have that name: give the index" if isinstance(v, str) and names.count(v) > 1 else "no such view"
    bad.append(f"{where}: view {v!r}: {why}; the views are {listed}")
    return None


def _uv(x):
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return [None, float(x)]
    if isinstance(x, (list, tuple)) and len(x) == 2 and all(isinstance(c, (int, float)) for c in x):
        return [float(x[0]), float(x[1])]
    return None


def _pair(x):
    return [[float(c) for c in p] for p in x] if isinstance(x, list) and len(x) == 2 and all(
        _uv(p) and _uv(p)[0] is not None for p in x) else None


FORM = ("fit {view: 'front', landmarks: {chest: v, waist: v | [u, v] | [[u, v], [u, v]] (both sides: their mean row) | "
        "{at: v, from: 'how inferred' (a covered landmark)}, wrist: v}, widths: [{at: 'chest', garment: [[u,v],[u,v]], "
        "body: [[u,v],[u,v]], body_from: 'seen' | how inferred}, {at: 'hem' (a garment edge: one of its heights), ...}], "
        "heights: [{name: 'hem', at: v, on: 'torso' (default) | 'leg' | 'arm' (read ALONG that limb, pose-free)}]}: widths "
        "and heights are LISTS; pixels of the view; a width sits AT its "
        "landmark's or height's row; seen edges are measured on the picture; landmarks are the points the landmark card "
        "draws (a landmark off from where its neighbours put it on the model is refused, unless {at, from, why})")
UNDER = ("floor", "crown")  # (in a picture these are the shoe's sole and the hair's top, not the body's: heights skip them)


def landmark_help(model: str, garment: str, body, words: bool = True) -> str:
    """The landmark card's path (the model's landmarks drawn) and where each landmark is, in words."""
    try:
        from . import garment_fit_look as gfl
        b = body() if callable(body) else body
        c = gfl.card(model, garment, b) if b is not None else None
    except Exception as e:  # (no body to draw: the words still help)
        c, b = None, f"{type(e).__name__}: {e}"
    L = [f"  the model's landmarks (look before marking: the same points on the picture): {c}" if c else
         "  (no landmark card: the model has no base body)"]
    if words:
        L += [f"    {k}: {FIND[k]}" for k in LANDMARKS if k in FIND]
    return "\n".join(L)


def _refuse(bad):
    raise FitRefused("\n  ".join(bad) + f"\n  the form: {FORM}")


def check(fit, views: list, body=None) -> tuple[dict, dict, dict]:
    """(fit, heights, fit_read) from the reading; FitRefused names every fault. body: a Body, or a callable giving one
    (only called once the form is right); False: validate the form only."""
    from . import garment_fit_marks as gm
    bad = []
    if isinstance(fit, dict) and fit and all(isinstance(e, dict) and "ease_mm" in e for e in fit.values()):
        _refuse(["fit: ease is no longer guessed in mm: mark it on the picture and the tool applies the ratios to the "
                 "model's body"])
    if not isinstance(fit, dict) or not (fit.get("widths") or fit.get("heights")):
        _refuse([f"fit: at least one width (garment and body edges at a landmark) or height; landmarks: "
                 f"{', '.join(LANDMARKS)}"])
    for k, typ, what in (("widths", list, "a list [{at, garment, body, body_from}, ...]"),
                         ("heights", list, "a list [{name, at}, ...]"), ("landmarks", dict, "{landmark: mark}")):
        if fit.get(k) is not None and not isinstance(fit[k], typ):
            bad.append(f"fit.{k}: {what}, not a {type(fit[k]).__name__}")
    if bad:
        _refuse(bad)
    vi = view_index(views, fit.get("view", 0), "fit", bad)
    image = views[vi].get("image") if vi is not None and isinstance(views[vi], dict) else None
    known = ", ".join(LANDMARKS)
    lms, lfrom, lwhy = {}, {}, {}
    for k, x in (fit.get("landmarks") or {}).items():
        m = gm.landmark(x)
        if k not in LANDMARKS:
            bad.append(f"fit.landmarks.{k}: unknown landmark: one of {known}")
        elif m is None:
            bad.append(f"fit.landmarks.{k}: v (a pixel row), [u, v], [[u, v], [u, v]] (both sides: their mean row) or "
                       f"{{at: one of those, from: 'seen' | how the covered {k} was placed}}; the {k} is "
                       f"{FIND.get(k, k)}")
        else:
            lms[k], lfrom[k], lwhy[k] = m
    hts = []  # (before the widths: a width may be read at a garment height, a hem or a cuff)
    for i, h in enumerate(fit.get("heights") or []):
        nm, uv = (h or {}).get("name") if isinstance(h, dict) else None, _uv(h.get("at")) if isinstance(h, dict) else None
        if not str(nm or "").strip() or uv is None:
            bad.append(f"fit.heights[{i}]: {{name (e.g. 'hem', 'waistband top'), at: v | [u, v]}}")
        elif nm in LANDMARKS:
            bad.append(f"fit.heights[{i}]: {nm!r} is a body landmark's name: name the garment's edge (e.g. 'hem')")
        else:
            hts.append(dict(name=nm, v=uv[1], source=h.get("source"), on=h.get("on")))
    hrow = {h["name"]: h["v"] for h in hts}
    try:
        tol = max(8.0, 0.01 * gm.gray(image).shape[0]) if image else 8.0
    except OSError:
        tol = 8.0
    widths = []
    for i, w in enumerate(fit.get("widths") or []):
        wn = f"fit.widths[{i}]"
        if not isinstance(w, dict):
            bad.append(f"{wn}: {{at, garment, body, body_from}}, not a {type(w).__name__}")
            continue
        at = w.get("at")
        if at not in hrow and (at not in LANDMARKS or LANDMARKS.get(at, (None,))[0] is None):
            bad.append(f"{wn}.at {at!r}: a landmark with a width ({', '.join(k for k, v in LANDMARKS.items() if v[0])}) "
                       f"or one of this garment's heights ({', '.join(hrow) or 'none given'}): a width at a garment edge "
                       "(a hem, a cuff) is read AT that edge's height")
            continue
        gfrom, bfrom = str(w.get("garment_from") or "seen").strip(), str(w.get("body_from") or "").strip()
        g, b = _pair(w.get("garment")), _pair(w.get("body"))
        if gfrom != "seen" and w.get("ratio") is not None:
            r = w["ratio"]
            if not isinstance(r, (int, float)) or r <= 0:
                bad.append(f"{wn}.ratio: a number > 0 (the garment's width over the body's at {at})")
                continue
            widths.append(dict(at=at, ratio=float(r), body="inferred", garment="inferred", note=gfrom, why=w.get("why")))
        else:
            if g is None:
                bad.append(f"{wn}.garment: its two edges [[u, v], [u, v]] straight across at the {at}; covered: "
                           f"garment_from = how it is inferred + ratio")
            if b is None:
                bad.append(f"{wn}.body: the body's two edges [[u, v], [u, v]] at the {at} (where it's covered, inferred "
                           "inside the garment and body_from says how)")
            if not bfrom:
                bad.append(f"{wn}.body_from: 'seen', or how the covered body's edges were inferred")
            if g is None or b is None or not bfrom:
                continue
            row, ref = float(np.mean([p[1] for p in g])), lms.get(at, hrow.get(at))
            if ref is not None and abs(row - ref) > tol:  # (t s0-3: an "ankle" width read 45 px above the ankle)
                what = f"the {at} is marked at row {ref:.0f}" if at in lms else f"the height {at!r} is at row {ref:.0f}"
                bad.append(f"{wn}: read at row {row:.0f}, but {what} ({abs(row - ref):.0f} px apart, {tol:.0f} allowed): "
                           "mark it at that row, or read it at a garment edge: name a height of this garment as its `at`")
                continue
            meas = {}  # (seen edges moved to the picture's own edges: C336)
            for key, pair, seen in (("garment", g, gfrom == "seen"), ("body", b, bfrom == "seen")):
                if seen and image:
                    q, moved, notes = gm.measure(image, pair)
                    meas[key] = dict(marked=pair, measured=q, moved_px=moved, notes=notes)
                    if key == "garment":
                        g = q
                    else:
                        b = q
            gw, bw = math.dist(*g), math.dist(*b)
            if bw < 1:
                bad.append(f"{wn}.body: its two edges are the same point")
                continue
            widths.append(dict(at=at, ratio=gw / bw, body="seen" if bfrom == "seen" else "inferred",
                               garment="seen" if gfrom == "seen" else "inferred", note=None if bfrom == "seen" else bfrom,
                               why=w.get("why"), px=[round(gw, 1), round(bw, 1)], measured=meas))
        if widths and widths[-1]["at"] == at and widths[-1]["ratio"] < 1 and not str(w.get("why") or "").strip():
            bad.append(f"{wn}: the garment is narrower than the body at the {at} ({widths[-1]['ratio']:.2f}): re-mark the "
                       "body's edges inside the garment, or say why (e.g. 'knit, worn tight')")
    body_lms = [k for k in lms if k not in UNDER]
    if hts and len(body_lms) < 2:
        bad.append(f"fit.landmarks: heights need >= 2 body landmarks marked besides the floor / crown (have "
                   f"{', '.join(lms) or 'none'}): e.g. {{waist: v, knee: v, ankle: v}}")
    if body is False:  # (validate only: another part of the reading was refused)
        if bad:
            _refuse(bad)
        return {}, {}, dict(fit)
    body = body() if callable(body) else body
    if body is None:
        bad.append("fit: no body to apply the ratios to (the model needs a base body: body_tape measures it)")
        _refuse(bad)
    view = views[vi].get("view", "front") if vi is not None else "front"
    use = {}  # (never the floor / crown: under a shoe, over hair; a landmark the model can't be measured at: named)
    for k, v in lms.items():
        if k not in body_lms:
            continue
        try:
            body.at(k, view)
            use[k] = v
        except Exception as e:  # (t s0-4: the neck raised a TapeError, not a refusal)
            bad.append(f"fit.landmarks.{k}: the model can't be measured at its {k} ({e}): leave it out and use the "
                       "nearest other landmark")
    from . import garment_fit_heights as gfh
    from .garment_fit_marks import drift
    stand = gfh.standing(use)  # (the arm is posed differently in a picture: never in the neighbour check)
    z = {k: body.at(k, view)["z_mm"] for k in stand}
    keep, off = {k: v for k, v in stand.items() if not lwhy.get(k)}, []  # (kept with a why: off on purpose, judges none;
    # then the worst one out, and again: one wrong mark skews its neighbours' predictions)
    while True:
        worst = max(((k, v) for k, v in drift(keep, z, gfh.MIN_SPAN).items() if abs(v[0]) > DRIFT[0] and abs(v[1]) > DRIFT[1]
                     ), key=lambda kv: abs(kv[1][1]), default=None)  # (by mm: a short span inflates fractions)
        if worst is None:
            break
        off.append(worst)
        keep.pop(worst[0])
    for k, (fr, mm, (na, nb), inner) in off:  # (t s0-3: a belt marked as the waist, the ankle bone as the ankle)
        if True:  # (with the form's faults: one answer, C338)
            bad.append(f"fit.landmarks.{k}: marked {abs(mm):.0f} mm {'lower' if mm > 0 else 'higher'} than the {na} and "
                       f"{nb} put it on this model ({abs(fr):.2f} of {'the ' + na + ' -> ' + nb + ' span' if inner else 'its distance from the ' + na}; {DRIFT[0]} and {DRIFT[1]:.0f} mm "
                       f"allowed): the {k} is "
                       f"{FIND.get(k, k)}. Re-mark it (or a neighbour), or keep it with {{at, from, why}}")
    if bad:
        _refuse(bad)
    heights = gfh.read(hts, use, lfrom, body, view, vi, [k for k in UNDER if k in lms], bad) if hts else {}
    out = {}
    for w in widths:
        if w["at"] in heights:  # (a width at a garment edge: the body's section at that edge, on its part)
            m, where = gfh.section(body, heights[w["at"]], view)
            part = f"section at the {w['at']} ({where}, on the {heights[w['at']]['on']})"
        elif w["at"] in hrow:
            continue  # (its height was refused: said in bad)
        else:
            m = body.at(w["at"], view)
            part = LANDMARKS[w["at"]][1]
        r = w["ratio"]
        mv = "; ".join(f"{k} edges measured on the picture (moved {x['moved_px'][0]:.0f} / {x['moved_px'][1]:.0f} px"
                       + (f"; {'; '.join(x['notes'])}" if x["notes"] else "") + ")"
                       for k, x in (w.get("measured") or {}).items())
        src = (f"ratio {r:.3f} read on view {vi} ({'garment ' + str(w['px'][0]) + ' px / body ' + str(w['px'][1]) + ' px' if w.get('px') else 'given'}); "
               f"body {w['body']}{' (' + w['note'] + ')' if w['note'] else ''}; applied to the model's {part}: "
               "the garment's section taken as the body's scaled by the ratio" + (f"; {mv}" if mv else ""))
        out[w["at"]] = dict(ratio=round(r, 3), ease_mm=round(m["girth_mm"] * (r - 1), 1),
                            body_girth_mm=round(m["girth_mm"], 1), garment_girth_mm=round(m["girth_mm"] * r, 1),
                            body_width_mm=round(m["width_mm"], 1), garment_width_mm=round(m["width_mm"] * r, 1),
                            body=w["body"], garment=w["garment"], source=src, **({"why": w["why"]} if w.get("why") else {}),
                            **({"measured": w["measured"]} if w.get("measured") else {}),
                            **({"section": {k: heights[w["at"]].get(k) for k in ("on", "z_mm", "along")}}
                               if w["at"] in heights else {}))
    if bad:
        _refuse(bad)
    read = dict(fit, view=vi)
    return out, heights, read


def text(fit: dict, heights: dict) -> list:
    L = [f"  fit {k}: ratio {e['ratio']} (body {e['body']}, garment {e['garment']}) -> ease {e['ease_mm']:+.0f} mm "
         f"(girth {e['body_girth_mm']:.0f} -> {e['garment_girth_mm']:.0f} mm; width {e['body_width_mm']:.0f} -> "
         f"{e['garment_width_mm']:.0f} mm)" + "".join(
             f"; {w} edges moved to the picture's {x['moved_px'][0]:.0f} / {x['moved_px'][1]:.0f} px"
             + (f" ({'; '.join(x['notes'])})" if x["notes"] else "")
             for w, x in (e.get("measured") or {}).items() if max(x["moved_px"]) >= 1 or x["notes"])
         for k, e in fit.items()]
    for k, h in heights.items():
        lm = h.get("landmarks") or {}
        sens = ", ".join(f"{s:.0f} mm per 10 px of the {n} ({'seen' if lm.get(n, 'seen') == 'seen' else 'INFERRED: ' + lm[n]})"
                         for n, s in (h.get("mm_per_10px") or {}).items())
        L.append(f"  height {k}: {h['z_mm']:.0f} mm above the floor ({h['fraction']} of {h['between'][0]} -> "
                 f"{h['between'][1]}{', EXTRAPOLATED' if h['extrapolated'] else ''})" + (f"; moves {sens}" if sens else ""))
    return L


from .garment_fit_body import ALIAS, DictBody, TapeBody, body_for  # noqa: E402,F401  (re-exported: callers use gf.*)
