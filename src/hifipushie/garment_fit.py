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
    "neck": ({"square_to": "neck", "t": 0.3}, "the neck"),
    "crotch": (None, "the crotch level"), "floor": (None, "the floor"), "crown": (None, "the top of the head"),
}
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
        "body: [[u,v],[u,v]], body_from: 'seen' | how inferred}], heights: [{name: 'hem', at: v}]}: widths and heights are LISTS; pixels of the "
        "view; seen edges are measured on the picture (garment_fit_marks.py)")
UNDER = ("floor", "crown")  # (in a picture these are the shoe's sole and the hair's top, not the body's: heights skip them)


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
    lms, lfrom = {}, {}
    for k, x in (fit.get("landmarks") or {}).items():
        m = gm.landmark(x)
        if k not in LANDMARKS:
            bad.append(f"fit.landmarks.{k}: unknown landmark: one of {known}")
        elif m is None:
            bad.append(f"fit.landmarks.{k}: v (a pixel row), [u, v], [[u, v], [u, v]] (both sides: their mean row) or "
                       f"{{at: one of those, from: 'seen' | how the covered {k} was placed}}")
        else:
            lms[k], lfrom[k] = m
    widths = []
    for i, w in enumerate(fit.get("widths") or []):
        wn = f"fit.widths[{i}]"
        if not isinstance(w, dict):
            bad.append(f"{wn}: {{at, garment, body, body_from}}, not a {type(w).__name__}")
            continue
        at = w.get("at")
        if at not in LANDMARKS or LANDMARKS.get(at, (None,))[0] is None:
            bad.append(f"{wn}.at {at!r}: a landmark with a width: "
                       f"{', '.join(k for k, v in LANDMARKS.items() if v[0])}")
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
    hts = []
    for i, h in enumerate(fit.get("heights") or []):
        nm, uv = (h or {}).get("name") if isinstance(h, dict) else None, _uv(h.get("at")) if isinstance(h, dict) else None
        if not str(nm or "").strip() or uv is None:
            bad.append(f"fit.heights[{i}]: {{name (e.g. 'hem', 'waistband top'), at: v | [u, v]}}")
        else:
            hts.append(dict(name=nm, v=uv[1], source=h.get("source")))
    body_lms = [k for k in lms if k not in UNDER]
    if hts and len(body_lms) < 2:
        bad.append(f"fit.landmarks: heights need >= 2 body landmarks marked besides the floor / crown (have "
                   f"{', '.join(lms) or 'none'}): e.g. {{waist: v, knee: v, ankle: v}}")
    if bad:
        _refuse(bad)
    if body is False:  # (validate only: another part of the reading was refused)
        return {}, {}, dict(fit)
    body = body() if callable(body) else body
    if body is None:
        raise FitRefused("fit: no body to apply the ratios to (the model needs a base body: body_tape measures it)")
    view = views[vi].get("view", "front")
    out = {}
    for w in widths:
        m = body.at(w["at"], view)
        r = w["ratio"]
        mv = "; ".join(f"{k} edges measured on the picture (moved {x['moved_px'][0]:.0f} / {x['moved_px'][1]:.0f} px"
                       + (f"; {'; '.join(x['notes'])}" if x["notes"] else "") + ")"
                       for k, x in (w.get("measured") or {}).items())
        src = (f"ratio {r:.3f} read on view {vi} ({'garment ' + str(w['px'][0]) + ' px / body ' + str(w['px'][1]) + ' px' if w.get('px') else 'given'}); "
               f"body {w['body']}{' (' + w['note'] + ')' if w['note'] else ''}; applied to the model's {LANDMARKS[w['at']][1]}: "
               "the garment's section taken as the body's scaled by the ratio" + (f"; {mv}" if mv else ""))
        out[w["at"]] = dict(ratio=round(r, 3), ease_mm=round(m["girth_mm"] * (r - 1), 1),
                            body_girth_mm=round(m["girth_mm"], 1), garment_girth_mm=round(m["girth_mm"] * r, 1),
                            body_width_mm=round(m["width_mm"], 1), garment_width_mm=round(m["width_mm"] * r, 1),
                            body=w["body"], garment=w["garment"], source=src, **({"why": w["why"]} if w.get("why") else {}),
                            **({"measured": w["measured"]} if w.get("measured") else {}))
    heights = {}
    if hts:
        use = {k: v for k, v in lms.items() if k in body_lms}  # (never the floor / crown: under a shoe, over hair)
        z = {k: body.at(k, view)["z_mm"] for k in use}
        order = sorted(use, key=lambda k: use[k])
        for h in hts:
            v = h["v"]
            inner = [(a, b) for a, b in zip(order, order[1:]) if use[a] <= v <= use[b]]
            a, b = inner[0] if inner else ((order[0], order[1]) if v < use[order[0]] else (order[-2], order[-1]))
            f = (v - use[a]) / (use[b] - use[a]) if use[b] != use[a] else 0.0
            zz = z[a] + f * (z[b] - z[a])
            sa, sb = gm.sensitivity(v, use[a], use[b], z[a], z[b])
            if zz < 0:
                bad.append(f"fit.heights {h['name']!r}: {-zz:.0f} mm under the model's floor (read from the {a} -> {b} "
                           "span): re-mark it or the landmarks")
                continue
            skipped = [k for k in UNDER if k in lms]
            heights[h["name"]] = dict(z_mm=round(zz, 1), fraction=round(f, 3), between=[a, b],
                                      extrapolated=not inner, landmarks={a: lfrom[a], b: lfrom[b]},
                                      mm_per_10px={a: sa, b: sb},
                                      source=f"{f:.3f} of the way from the {a} to the {b} on view {vi}, on the model's own "
                                             f"{a} ({z[a]:.0f} mm) and {b} ({z[b]:.0f} mm) above the floor"
                                             + (" (EXTRAPOLATED beyond them)" if not inner else "")
                                             + (f"; the {' / '.join(skipped)} not used (in a picture: the shoe's sole / "
                                                "the hair, not the body's)" if skipped else "")
                                             + (f"; {h['source']}" if h.get("source") else ""))
    if bad:
        _refuse(bad)
    read = dict(fit, view=vi)
    return out, heights, read


class DictBody:
    """A body given as numbers {landmark: {girth_mm, width_mm, z_mm}} (tests; a body with no mesh)."""

    def __init__(self, d: dict):
        self.d = d
        self.mesh = None

    def at(self, lm, view="front"):
        if lm not in self.d:
            raise FitRefused(f"the body has no {lm!r}")
        return self.d[lm]


class TapeBody:
    """The model's own body through body_tape: girth, width across the view and height (mm above the floor)."""

    def __init__(self, tape):
        self.tape, self._c = tape, {}
        self.mesh = (tape.V, tape.T)

    def at(self, lm, view="front"):
        key = (lm, view)
        if key in self._c:
            return self._c[key]
        t = self.tape
        item, _ = LANDMARKS[lm]
        floor = t.zmin
        if item is None:
            z = {"floor": t.zmin, "crown": t.zmax}.get(lm)
            z = t.level(lm)[0] if z is None else z
            r = {"girth_mm": 0.0, "width_mm": 0.0, "z_mm": (z - floor) * 1000, "centre": None, "dir": None}
        else:
            from . import body_tape as bt
            m = t.take(dict(item, name=f"fit:{lm}", kind="girth"))
            L = np.asarray(t.lines[f"fit:{lm}"], float)
            sq = item["square_to"]
            if sq == "body":
                n = np.array([0.0, 0.0, 1.0])
            else:
                limb, _, side = sq.partition(".")
                ja, jb = (j + (f".{side}" if side and j not in ("neck", "head") else "") for j in bt.LIMBS[limb])
                n = t.J[jb] - t.J[ja]
            ax = (0, 2) if view not in SIDE_VIEWS else (1, 2)  # (the view's plane: across, up)
            n2 = np.array([n[ax[0]], n[ax[1]]])
            n2 = n2 / (np.linalg.norm(n2) or 1.0)
            d = np.array([n2[1], -n2[0]])  # (across the limb in the view)
            P = L[:, ax]
            w = float(np.ptp(P @ d))
            r = {"girth_mm": m["mm"], "width_mm": w * 1000, "z_mm": (float(L[:, 2].mean()) - floor) * 1000,
                 "centre": P.mean(0).tolist(), "dir": d.tolist()}
        self._c[key] = r
        return r


_BODIES: dict = {}


def body_for(model: str):
    """The model's base body as a TapeBody (garment_plan step 0 applies the fit's ratios to it). The body mesh is kept
    on disk by its base's content (building it is ~20 s; a step-0 call must answer in seconds), the tape in process."""
    import hashlib
    import json
    from . import body_tape as bt, cloth, store
    spec = store.load(model)
    if not spec.get("base"):
        return None
    key = hashlib.sha1(json.dumps(spec["base"], sort_keys=True, default=str).encode()).hexdigest()[:16]
    if (model, key) in _BODIES:
        return _BODIES[(model, key)]
    f = store._dir(model) / "tape" / f"fit_body_{key}.npz"
    try:
        z = np.load(f, allow_pickle=False)
        V, T, J = z["V"], z["T"], {k[2:]: z[k] for k in z.files if k.startswith("J:")}
        hps = str(z["hps"]) or None
    except (OSError, KeyError, ValueError):
        b = cloth.model_body(model, spec, {})
        tape = bt.Tape(b["V"], b["F"], b["J"], hps=b.get("hps"))
        V, T, J, hps = tape.V, np.asarray(tape.T), tape.J, b.get("hps")
        f.parent.mkdir(parents=True, exist_ok=True)
        np.savez(f, V=V, T=T, hps=np.array(hps or ""), **{"J:" + k: v for k, v in J.items()})
    _BODIES[(model, key)] = body = TapeBody(bt.Tape(V, T, J, hps=hps))
    return body


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
