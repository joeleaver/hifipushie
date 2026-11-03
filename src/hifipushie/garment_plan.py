"""Steps 0, 1, 2 of the garment record (docs/state/garment_steps.md, tooling run T4): the reading, the parts inventory and
the style plan, for ANY garment. The agent is the intelligence (it looks at the picture and knows construction); this
module is the structure it writes into, the validation that refuses an incomplete or inconsistent write BY NAME, and the
look drawn over the reference (garment_plan_look.py). Nothing here is shirt-specific: a hussar jacket fits the same form.

Coordinates on a picture: pixels, u right, v down. Every target carries its source (a named convention, a reading of a
view, a table). Lengths are never chosen here: a seam names the body measurement(s) its length depends on (by name,
step 3 measures them) or a style proportion read off the reference.

STEP 0 "read": {kind, views, cloth, fit, notes?}   (garment_read.py)
  kind   a short name (<= 5 words, no lists): construction goes in step 1, the worn state in step 2 (C335)
  views  [{image, view: front|back|side|three|detail|other, shows?, scale?: {mm_per_px, from}}]; a view is named
         anywhere in steps 0-2 by its name ("front") or its index
  cloth  {name: {fabric?: garment_kb fabric | gsm, thickness_mm, bending_length_mm, stretch: woven|knit, source;
          stiffness: drapey|soft|medium|crisp|stiff|rigid; colour: [r,g,b] | {at: [[u,v],..], view}; print?: {kind,
          repeat_mm, colours?, source}; grain: text}}   (a fabric name fills the numbers from garment_kb.json)
  fit    RATIOS read on the picture, applied to the model's body (garment_fit.py is the spec): {view, landmarks:
          {landmark: v | {at, from: how inferred}}, widths: [{at, garment: [[u,v],[u,v]], body: [[u,v],[u,v]], body_from: seen | how inferred}],
          heights: [{name, at: v}]} -> the record's fit {landmark: {ratio, ease_mm, ...}} and heights {name: {z_mm}}
STEP 1 "parts": {pieces, details, closures, seams, over?, define?}
  define   {measurement name: girth|arc|length|height}: a seam length's body name body_tape doesn't take by FreeSewing name
            (body_tape.TAKES); any other name is refused with the closest valid ones
  over     [garment names of this model it is worn over] (T9: built on their approved builds; chain_layers)
  pieces   {name: {what, cloth (a step-0 cloth), seen: seen|occluded|inferred, from (convention; needed unless seen),
            build: full|simplified|omit, why (unless full), stiff: bool, layer: int (0 = next to the body / the garment
            under it), where?: {view, outline: [[u,v],..]} (needed when seen), hang?: fitted|draped (T13: hangs free
            below where it is held; its fall judged on the hang), held?: [its edges built on the body] (draped only),
            edges: {edge: [i0, i1]} spans of its outline's points that TILE it (each segment in one edge), or [names]
            for a piece with no outline (garment_parts_edges.py, C343)}}
  details  {name: {what, on: [pieces], cloth? (braid, zip tape...), follows?: ["piece:edge"] (a trim along edges), count?, seen, from?, build, why?, where?: {view, at: [[u,v],..] | outline | outlines}}}
  closures {name: {what, pieces: [pieces it joins; one for a band closing on itself], details?: [details]}}
  seams    [{a: "piece:edge", b: "piece:edge" (declared edges), kind?: seam|fold|set_in|topstitch|bound, length: {body:
            [measurement names]} | {style: {ratio | value_mm, of?, source}}, why?}] (a body length is checked against
            its edge as drawn at the step-0 scale; why keeps one the check refuses)
STEP 2 "style": {state, bends, pose, rows, layers?, drape?}
  drape  {piece: {falls: down|up, source}}  (T13: a step-1 hang "draped" piece's start: a hood worn up falls up; chain_drape)
  layers {mode: visible|full, why}  (worn over another garment: visible (default) keeps the garment under where it is seen;
          full fits all of it inside, for a reason: chain_press.py, T12)
  state  {closure: {state: open|closed|partly, detail?, source}}   (EVERY inventory closure, none other)
  bends  [{id, on (piece | piece:edge | detail | closure), target: {value, unit, of (a ratio's base)} | {is}, source}]
  pose   {name, source}
  rows   [{id, what, target: {value, unit, tol?, of?} | {is}, source, note?, view?, at?: [[u,v],..]}]  (what the photo
          judges: the structure gate's targets). what = a structure_rows.KINDS kind (refused otherwise, with the list); a
          ratio is OF the kind's base (its name or a row id of it); a numeric bend names its kind in "what" too (C286)
  traces [{id, what, view, points [[u,v],..], corners [indices], source}] + body_marks [{view, at: {landmark: [u,v]},
          source}]  (T15, C299: the reference's key edges traced on a view, what = a structure_outline.KINDS edge; step 6
          compares the build's outline in that view with them in mm: structure_outline.py is the spec)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import garment_record as gr, structure_rows as sr

STEPS = {"read": "0", "parts": "1", "style": "2", "0": "0", "1": "1", "2": "2"}
VIEWS = ("front", "back", "side", "three", "detail", "other")
SEEN = ("seen", "occluded", "inferred")
BUILD = ("full", "simplified", "omit")
STIFFNESS = ("drapey", "soft", "medium", "crisp", "stiff", "rigid")
STATES = ("open", "closed", "partly")
SEAM_KINDS = ("seam", "fold", "set_in", "topstitch", "bound")
UNITS = ("mm", "deg", "ratio", "count", "px", "cm")
NAME = re.compile(r"[A-Za-z0-9_.\-]+")


class PlanRefused(ValueError):
    """A step's plan is incomplete or inconsistent: every fault named."""


def _kb_fabrics() -> dict:
    return {k: v for k, v in json.loads(Path(__file__).with_name("garment_kb.json").read_text())["fabrics"].items()
            if not k.startswith("_")}


def _mid(v):
    return round((v[0] + v[1]) / 2, 3) if isinstance(v, list) else v


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _uv_list(x) -> bool:
    return isinstance(x, list) and len(x) > 0 and all(isinstance(p, (list, tuple)) and len(p) == 2 and all(map(_num, p))
                                                      for p in x)


def _target(t, where: str, bad: list):
    if not isinstance(t, dict) or not (("value" in t and t.get("unit") in UNITS and _num(t["value"])) or "is" in t):
        bad.append(f"{where}: target needs {{value, unit ({'|'.join(UNITS)})}} or {{is: <state>}}, got {t!r}")
    elif t.get("unit") == "ratio" and not str(t.get("of") or "").strip():
        bad.append(f"{where}: a ratio target names what it is OF (of: 'neck width at the collar', a row id...)")


def _src(d: dict, where: str, bad: list):
    if not str(d.get("source") or "").strip():
        bad.append(f"{where}: no source (name what it comes from: a view and what was read there, a convention, a table)")


# ---------------------------------------------------------------- step 0: garment_read.py (the reading; its fit: garment_fit.py)
from .garment_read import KIND_WORDS, check_read, choices, views_by_name  # noqa: E402,F401


# ---------------------------------------------------------------- step 1
UV_KEYS = ("at", "outline", "outlines", "points")


def _size(views, i):
    try:
        from PIL import Image
        with Image.open(views[i]["image"]) as im:
            return im.size
    except (OSError, IndexError, KeyError, TypeError, ValueError):
        return None


def pixel_errors(p, views) -> list:
    """Coordinates are PIXELS of the named view: [[u, v], ..] all within 0..1 on an image wider than 2 px are refused (t8:
    0-1 values were accepted and drawn at the image corner)."""
    views, out, sizes = views if isinstance(views, list) else [], [], {}

    def uvs(x):
        if isinstance(x, dict):
            return [q for v in x.values() for q in uvs(v)]
        if isinstance(x, (list, tuple)) and len(x) == 2 and all(map(_num, x)):
            return [x]
        return [q for v in x for q in uvs(v)] if isinstance(x, (list, tuple)) else []

    def walk(x, w, view):
        if isinstance(x, list):
            for i, y in enumerate(x):
                walk(y, f"{w}[{i}]", view)
            return
        if not isinstance(x, dict):
            return
        view = x.get("view", view) if isinstance(x.get("view", view), int) else view
        for k, y in x.items():
            pts = uvs(y) if k in UV_KEYS else []
            if pts:
                if view not in sizes:
                    sizes[view] = _size(views, view)
                sz = sizes[view]
                if sz and sz[0] > 2 and all(0 <= float(c) <= 1 for q in pts for c in q):
                    out.append(f"{w}.{k}: {[list(q) for q in pts[:2]]}...: [u, v] are PIXELS of view {view}'s image "
                               f"({sz[0]} x {sz[1]} px, u right, v down from its top-left), not 0-1 fractions: multiply "
                               f"u by {sz[0]} and v by {sz[1]}")
            elif k not in UV_KEYS:
                walk(y, f"{w}.{k}" if w else k, view)
    walk(p, "", 0)
    return out


def _where(d: dict, w: str, nviews: int, bad: list, key: str = "outline"):
    x = d.get("where")
    if x is None:
        return
    if not isinstance(x, dict) or not isinstance(x.get("view", 0), int) or not 0 <= x.get("view", 0) < nviews:
        bad.append(f"{w}.where: {{view: a step-0 view index, outline | at: [[u, v], ...]}}")
    elif not (_uv_list(x.get("outline")) or _uv_list(x.get("at")) or (
            isinstance(x.get("outlines"), list) and x["outlines"] and all(map(_uv_list, x["outlines"])))):
        bad.append(f"{w}.where: outline, outlines (one per instance: frogs, braid lines) or at, as [[u, v], ...] "
                   "pixels on that view")


def _seen(d: dict, w: str, nviews: int, bad: list):
    if d.get("seen") not in SEEN:
        bad.append(f"{w}.seen: one of {', '.join(SEEN)}")
    elif d["seen"] != "seen" and not str(d.get("from") or "").strip():
        bad.append(f"{w}: {d['seen']}: from = the convention it is inferred from (e.g. 'a shirt back is one piece with a yoke')")
    elif d["seen"] == "seen" and d.get("where") is None:
        bad.append(f"{w}: seen: where = {{view, outline | at}} on the picture it is seen in")
    if d.get("build") not in BUILD:
        bad.append(f"{w}.build: one of {', '.join(BUILD)}")
    elif d["build"] != "full" and not str(d.get("why") or "").strip():
        bad.append(f"{w}: build {d['build']}: why (e.g. 'under the closed jacket, never seen')")
    _where(d, w, nviews, bad)


def _list(x, w: str, what: str, bad: list) -> list:
    """A list field: a bare string is refused as such (t s1-1: "collar" came back spelled 'c, o, l, l, a, r')."""
    if x is None:
        return []
    if isinstance(x, list):
        return x
    bad.append(f"{w}: a LIST of {what}, e.g. [{x!r}]" if isinstance(x, str) else f"{w}: a list of {what}")
    return []


def form(sid: str) -> str:
    """The step's full form, from this module's docstring (a blind agent can't read the source: t s1-1)."""
    doc = __doc__ or ""
    i = doc.find(f"STEP {sid} ")
    j = doc.find("STEP ", i + 6) if i >= 0 else -1
    return "  the form:\n" + (doc[i:j if j > 0 else None].rstrip() if i >= 0 else "")


def check_parts(p: dict, read: dict, body=None) -> dict:
    bad, p = [], json.loads(json.dumps(p))
    nv, cloths = len(read.get("views") or []), set(read.get("cloth") or {})
    pieces, details = p.get("pieces") or {}, p.get("details") or {}
    closures, seams = p.get("closures") or {}, p.get("seams")
    if not isinstance(pieces, dict) or not pieces:
        bad.append("pieces: {name: {...}} every piece of the garment (panels, collar parts, sleeves, cuffs, facings...)")
        pieces = {}
    for n, x in pieces.items():
        w = f"pieces.{n}"
        if not NAME.fullmatch(n) or not isinstance(x, dict):
            bad.append(f"{w}: a name of letters, digits, _ . - and a dict")
            continue
        if not str(x.get("what") or "").strip():
            bad.append(f"{w}.what: what the piece is")
        if x.get("cloth") not in cloths:
            bad.append(f"{w}.cloth {x.get('cloth')!r}: not a step-0 cloth ({', '.join(sorted(cloths))})")
        if not isinstance(x.get("stiff"), bool):
            bad.append(f"{w}.stiff: true (holds its shape: collar, band, cuff, braided front) or false")
        if not isinstance(x.get("layer"), int):
            bad.append(f"{w}.layer: an int (0 = next to the body or the garment under it; a facing over a front is 1...)")
        _seen(x, w, nv, bad)
    for n, x in (details.items() if isinstance(details, dict) else []):
        w = f"details.{n}"
        if not isinstance(x, dict):
            bad.append(f"{w}: a dict")
            continue
        if not str(x.get("what") or "").strip():
            bad.append(f"{w}.what: what it is (button, braid, frogging, zip, tab, pocket, epaulette...)")
        on = _list(x.get("on"), f"{w}.on", "the pieces it sits on", bad)
        miss = [q for q in on if q not in pieces]
        if (not on or miss) and not isinstance(x.get("on"), str):
            bad.append(f"{w}.on: the pieces it sits on; not in the inventory: {', '.join(map(str, miss)) or '(none given)'}")
        if x.get("cloth") is not None and x["cloth"] not in cloths:
            bad.append(f"{w}.cloth {x['cloth']!r}: not a step-0 cloth ({', '.join(sorted(cloths))})")
        fl = _list(x.get("follows"), f"{w}.follows", "'piece:edge'", bad)
        badf = [e for e in fl if not (isinstance(e, str) and ":" in e and e.split(":")[0] in pieces)]
        if not isinstance(fl, list) or badf:
            bad.append(f"{w}.follows: the 'piece:edge' list a trim runs along; not in the inventory: {', '.join(map(str, badf))}")
        if x.get("count") is not None and not (isinstance(x["count"], int) and x["count"] > 0):
            bad.append(f"{w}.count: a positive int")
        _seen(x, w, nv, bad)
    for n, x in (closures.items() if isinstance(closures, dict) else []):
        w = f"closures.{n}"
        ps = _list((x or {}).get("pieces"), f"{w}.pieces", "the pieces it joins", bad)
        dts = _list((x or {}).get("details"), f"{w}.details", "its details", bad)
        miss = [q for q in ps if q not in pieces] + [d for d in dts if d not in details]
        if not ps or miss:
            bad.append(f"{w}: pieces = the pieces it joins (one: a band closing on itself), details = its buttons / "
                       f"zip...; not in the inventory: {', '.join(map(str, miss)) or '(no pieces)'}")
    if not isinstance(seams, list) or not seams:
        bad.append("seams: [{a: 'piece:edge', b: 'piece:edge', length: {body: [...]} | {style: {...}}}]")
        seams = []
    joined, needs = set(), set()
    for i, s in enumerate(seams):
        w = f"seams[{i}]"
        ends = [s.get(k) for k in ("a", "b")] if isinstance(s, dict) else []
        for e in ends:
            pc = str(e).split(":")[0]
            if not (isinstance(e, str) and ":" in e) or pc not in pieces:
                bad.append(f"{w}: {e!r}: 'piece:edge' with a piece in the inventory (have {', '.join(sorted(pieces))})")
            else:
                joined.add(pc)
        if not ends:
            bad.append(f"{w}: a dict {{a, b, length}}")
            continue
        if s.get("kind", "seam") not in SEAM_KINDS:
            bad.append(f"{w}.kind: one of {', '.join(SEAM_KINDS)}")
        ln = s.get("length")
        if isinstance(ln, dict) and isinstance(ln.get("body"), list) and ln["body"] and all(
                isinstance(m, str) and NAME.fullmatch(m) for m in ln["body"]):
            needs.update(ln["body"])
        elif isinstance(ln, dict) and isinstance(ln.get("style"), dict) and (
                _num(ln["style"].get("ratio")) or _num(ln["style"].get("value_mm"))):
            _src(ln["style"], f"{w}.length.style", bad)
        else:
            bad.append(f"{w}.length: {{body: [measurement names]}} (step 3 measures them) or {{style: {{ratio | value_mm, "
                       "of, source}}}} read off the reference")
    lone = [n for n, x in pieces.items() if isinstance(x, dict) and x.get("build") != "omit" and n not in joined]
    if lone:
        bad.append(f"pieces with no seam: {', '.join(lone)} (every built piece joins another piece, or is folded from one)")
    from . import body_tape as bt, chain_drape as cd
    define = p.get("define") or {}
    kinds = [k for k in bt.KINDS if k != "freesewing"]
    if not isinstance(define, dict) or any(v not in kinds for v in define.values()):
        bad.append(f"define: {{measurement name: kind}} for names body_tape doesn't take by FreeSewing name; kind one of "
                   f"{', '.join(kinds)} (step 3 measures it by that kind)")
        define = {}
    bad += [f"seams length.body: {e}" for e in bt.name_errors(sorted(needs), define)]
    cd.check_parts(pieces, bad)  # (T13: hang fitted | draped, held edges)
    from . import garment_parts_edges as pe  # (every edge named, a seen piece's as spans of its outline: C343)
    edges = pe.check(pieces, bad)
    for i, s in enumerate(seams):
        if isinstance(s, dict):
            pe.refs(f"seams[{i}]", [s.get("a"), s.get("b")], edges, bad)
    for n, x in (details.items() if isinstance(details, dict) else []):
        if isinstance(x, dict) and isinstance(x.get("follows"), list):
            pe.refs(f"details.{n}.follows", x["follows"], edges, bad)
    fr = read.get("fit_read") or {}
    sc = fr.get("scale") or {}
    scale = (sc.get("across_mm_per_px", 0) + sc.get("up_mm_per_px", 0)) / 2 if sc else None
    b = body() if callable(body) else body
    mm = dict(getattr(getattr(b, "tape", None), "R", {}).get("mm") or {}) if b is not None else {}
    p["seam_lengths_checked"] = pe.lengths(seams, edges, fr.get("view", 0), scale, mm, bad)
    bad += pixel_errors(p, read.get("views"))
    if bad:
        raise PlanRefused("step 1 (parts) refused:\n  " + "\n  ".join(bad) + "\n" + form("1"))
    p["measurements"] = sorted(needs)  # (what step 3 must measure, by name)
    return p


# ---------------------------------------------------------------- step 2
def check_style(p: dict, read: dict, parts: dict) -> dict:
    bad, p = [], json.loads(json.dumps(p))
    nv = len(read.get("views") or [])
    pieces, details, closures = (parts.get(k) or {} for k in ("pieces", "details", "closures"))
    state = p.get("state") if isinstance(p.get("state"), dict) else {}
    for c in state:
        if c not in closures:
            bad.append(f"state.{c}: no closure {c!r} in the inventory (have {', '.join(closures) or 'none'})")
    for c in closures:
        x = state.get(c)
        if not isinstance(x, dict) or x.get("state") not in STATES:
            bad.append(f"state.{c}: the ONE worn state of this closure: {{state: {'|'.join(STATES)}, source}}")
        else:
            _src(x, f"state.{c}", bad)
    names = set(pieces) | set(details) | set(closures)
    kinds = {r.get("id"): r.get("what") for r in p.get("rows") or [] if isinstance(r, dict)}
    for i, b in enumerate(p.get("bends") or []):
        w = f"bends[{i}] {b.get('id', '')}".strip()
        if str(b.get("on", "")).split(":")[0] not in names:
            bad.append(f"{w}.on {b.get('on')!r}: not a piece, detail or closure of the inventory")
        _target(b.get("target"), w, bad)
        _src(b, w, bad)
        if b.get("what") is not None or "value" in (b.get("target") or {}):  # (C286: a numeric bend is judged too)
            sr.check_row(b, w, bad, kinds)
    from .garment_appearance import check_plan  # (T14: the appearance block: amounts from the story, step 9a reads it)
    bad += check_plan(p.get("appearance"), list((read.get("cloth") or {})), list((parts.get("details") or {})))
    lay = p.get("layers")  # (T12: how a garment worn over another layers it: chain_press.py)
    if lay is not None and not (isinstance(lay, dict) and lay.get("mode") in ("visible", "full")
                                and (lay["mode"] == "visible" or str(lay.get("why") or "").strip())):
        bad.append("layers: {mode: visible (default: the garment under kept where seen) | full (the whole garment under "
                   "fitted inside and hung with this one), why (needed for full: it comes off at runtime, a close-up)}")
    pose = p.get("pose")
    if not isinstance(pose, dict) or not pose.get("name"):
        bad.append("pose: {name (e.g. 'arms down, relaxed'), source}")
    else:
        _src(pose, "pose", bad)
    rows = p.get("rows")
    if not isinstance(rows, list) or not rows:
        bad.append("rows: [{id, what, target, source}] what the reference photo judges (the structure gate's targets)")
        rows = []
    ids = [r.get("id") for r in rows]
    for i, r in enumerate(rows):
        w = f"rows[{i}] {r.get('id', '')}".strip()
        if not r.get("id") or ids.count(r.get("id")) > 1 or not r.get("what"):
            bad.append(f"{w}: a unique id and what it judges")
        _target(r.get("target"), w, bad)
        _src(r, w, bad)
        sr.check_row(r, w, bad, kinds)  # (C286: what = a structure_rows kind)
        if r.get("at") is not None and not (_uv_list(r["at"]) and isinstance(r.get("view", 0), int)
                                            and 0 <= r.get("view", 0) < nv):
            bad.append(f"{w}.at: [[u, v], ...] on view (a step-0 view index)")
    from . import chain_drape as cd, structure_outline as so
    so.check_plan(p, read, bad)  # (T15: traced edges + the body marks that place the view)
    if p.get("blockin") is not None:  # (F9: the garment as worn, an SDF block-in: garment_blockin's docstring)
        from .garment_blockin import validate as _bv
        bad += _bv(p["blockin"])
    cd.check_style(p, pieces, bad)  # (T13: drape falls; a hang row needs a draped piece falling that way)
    falls = {x["falls"] for x in cd.plan_drape({"parts": parts, "style": p}).values()}
    for i, r in enumerate(rows):
        k = sr.KINDS.get(r.get("what")) or {}
        if k.get("needs_drape") and k["needs_drape"] not in falls:
            bad.append(f"rows[{i}] {r.get('id', '')}: {r['what']} is judged on the hang of a draped piece falling "
                       f"{k['needs_drape']}; step 1 / 2 have none ({sr.stage_kinds()})")
    bad += pixel_errors(p, read.get("views"))
    if bad:
        raise PlanRefused("step 2 (style) refused:\n  " + "\n  ".join(bad))
    return p


# ---------------------------------------------------------------- the record
def write(model: str, garment: str, step: str, plan: dict, look: bool = True) -> dict:
    """Validate a step's plan, write it into the garment record, draw its look over the reference."""
    sid = STEPS.get(str(step))
    if sid is None:
        raise ValueError(f"step {step!r}: read (0), parts (1) or style (2)")
    plan = json.loads(plan) if isinstance(plan, str) else plan
    rec = gr.load(model, garment)
    out = {k: rec["steps"][k].get("output") or {} for k in ("0", "1")}
    if sid != "0" and not out["0"].get("views"):
        raise PlanRefused(f"step {sid} refused: step 0 (read) has no reading yet: garment_plan step='read' first")
    if sid == "2" and not out["1"].get("pieces"):
        raise PlanRefused("step 2 refused: step 1 (parts) has no inventory yet: garment_plan step='parts' first")
    bad = views_by_name(plan, (plan if sid == "0" else out["0"]).get("views") or [])
    if bad:
        raise PlanRefused(f"step {sid} refused:\n  " + "\n  ".join(bad))
    from . import garment_fit as gf
    held = []  # (the model's body, measured once for the fit's ratios and its look)

    def body():
        held[:] = held or [gf.body_for(model)]
        return held[0]
    try:
        p = check_read(plan, body=body) if sid == "0" else check_parts(plan, out["0"], body) if sid == "1" else \
            check_style(plan, out["0"], out["1"])
    except PlanRefused as e:
        if sid == "0" and "fit" in str(e):  # (the model's landmarks, drawn and in words, before the marks: C338)
            raise PlanRefused(f"{e}\n{gf.landmark_help(model, garment, body)}") from None
        raise
    if sid == "1" and "over" in p:  # (worn over another garment of this model: exists, has a record, no loop; T9)
        from . import chain_layers as cl
        try:
            p["over"] = cl.check_over(model, garment, p["over"])
        except cl.LayerRefused as e:
            raise PlanRefused(f"step 1 (parts) refused: {e}") from None
    ref = p["views"][0]["image"] if sid == "0" else None
    st = gr.write(model, garment, sid, "done", output=p, reference=ref, by="garment_plan")
    from . import garment_carry as gc  # (later steps that still validate are re-stamped, not left stale: F2)
    carried = gc.carry(model, garment, sid) if sid in ("0", "1") else []
    paths = []
    if look:
        from . import garment_plan_look as gl
        paths = gl.draw(model, garment, sid, p, out["0"] if sid != "0" else p, out["1"] if sid == "2" else None)
        if sid == "0" and p.get("fit_read"):  # (the marks beside the model with the widths and heights they give)
            from . import garment_fit_look as gfl
            paths.append(gfl.draw(model, garment, p, body()))
            c = gfl.card(model, garment, body())  # (the model's landmarks: what the marks were matched to)
            paths += [c] if c else []
        gr.attach_look(model, garment, sid, paths)
    return {"step": sid, "plan": p, "digest": st["digest"], "look": paths, "carried": carried}


def text(model: str, garment: str, r: dict) -> str:
    sid, p = r["step"], r["plan"]
    L = [f"{model}:{garment} step {sid} ({gr.STEP[sid]['key']}) written: digest {r['digest']}"]
    L.append("  coordinates (at / outline / points): PIXELS of the named view, u right, v down from its top-left")
    L += r.get("carried") or []
    if sid == "0":
        L.append(f"  kind: {p['kind']}; views: " + ", ".join(f"{i} {v['view']}" for i, v in enumerate(p["views"])))
        for n, c in p["cloth"].items():
            L.append(f"  cloth {n}: gsm {c['gsm']}, {c['thickness_mm']} mm, {c['stiffness']}, colour {c['colour']}"
                     f" ({c['source']})")
        from . import garment_fit as gf
        L += gf.text(p["fit"], p.get("heights") or {})
        sc = (p.get("fit_read") or {}).get("scale")
        if sc:  # (one picture, one scale: C340)
            L.append(f"  scale: across {sc['across_mm_per_px']:.2f} mm/px (body widths), up and down "
                     f"{sc['up_mm_per_px']:.2f} (landmarks): {abs(sc['apart']) * 100:.0f} % apart")
        L.append(choices())
    elif sid == "1":
        if p.get("over"):
            L.append(f"  worn over: {', '.join(p['over'])} (built over their approved builds: chain_layers, T9)")
        for n, x in p["pieces"].items():  # (every item of the look's legend: C288, the look is for shape)
            L.append(f"  piece {n}: {x['seen']}, build {x['build']}, {'stiff' if x['stiff'] else 'soft'}, layer {x['layer']}"
                     + (f", from {x['from']}" if x["seen"] != "seen" and x.get("from") else "")
                     + (f", DRAPED (held: {', '.join(x.get('held') or []) or 'by its seam to a held edge'}; its fall "
                        "judged on the hang)" if x.get("hang") == "draped" else "")
                     + ("" if isinstance(x.get("where"), dict) else " (no place on the picture)"))
        for n, x in (p.get("details") or {}).items():
            L.append(f"  detail {n} x{x.get('count', 1)} on {', '.join(x['on'])}: {x['seen']}, build {x['build']}")
        L.append("  closures: " + (", ".join(f"{c} ({', '.join(v.get('pieces') or [])}; {len(v.get('details') or [])} details)"
                                            for c, v in (p.get("closures") or {}).items()) or "none"))
        L += [f"  seam {r_['a']} = {r_['b']}" + (f" ({r_['kind']})" if r_.get("kind") else "") for r_ in p["seams"]]
        L.append(f"  step 3 measures: {', '.join(p['measurements']) or 'nothing by body'}")
    else:
        from .garment_plan_look import _tgt
        L += [f"  closure {c}: {x['state']}" + (f" ({x['detail']})" if x.get("detail") else "") for c, x in p["state"].items()]
        L.append(f"  pose: {p['pose']['name']}")
        L += [f"  bend {b.get('id', '')} on {b['on']}: {_tgt(b['target'])}" for b in p.get("bends") or []]
        L += [f"  drape {n}: falls {x['falls']}" for n, x in (p.get("drape") or {}).items()]
        L += [f"  row {r_['id']}: {_tgt(r_['target'])}" + (f" (marked on view {r_.get('view', 0)})" if r_.get("at")
                                                          else " (not marked)")
              + (" [judged on the HANG, step 8]" if (sr.KINDS.get(r_.get("what")) or {}).get("on") == "hang" else "")
              for r_ in p["rows"]]
        L += [f"  trace {t['id']} ({t['what']}) on view {t.get('view', 0)}: {len(t['points'])} points, corners at "
              f"{t.get('corners') or 'none'}" for t in p.get("traces") or []]
        L += [f"  body marks on view {m.get('view', 0)}: {', '.join(m['at'])}" for m in p.get("body_marks") or []]
    L += [f"  look: {x}" for x in r["look"]]
    nxt = {"0": "judge the look against the picture (are the samples on the right cloth), then garment_plan step='parts'",
           "1": "judge the look's SHAPES against the picture (does each outline follow its piece; occluded / inferred "
                "marked), then garment_plan step='style'",
           "2": "judge the look against the picture (does each yellow mark span what its row names; does each cyan trace "
                "sit ON its edge, corners ringed where it turns sharply)"
                "; step 3 measures the names step 1 calls for"}[sid]
    nxt += "; names and numbers are this text's, never read off the look"
    return "\n".join(L + [f"next: {nxt} (garment_record shows the record)"])
