"""Steps 0, 1, 2 of the garment record (docs/state/garment_steps.md, tooling run T4): the reading, the parts inventory and
the style plan, for ANY garment. The agent is the intelligence (it looks at the picture and knows construction); this
module is the structure it writes into, the validation that refuses an incomplete or inconsistent write BY NAME, and the
look drawn over the reference (garment_plan_look.py). Nothing here is shirt-specific: a hussar jacket fits the same form.

Coordinates on a picture: pixels, u right, v down. Every target carries its source (a named convention, a reading of a
view, a table). Lengths are never chosen here: a seam names the body measurement(s) its length depends on (by name,
step 3 measures them) or a style proportion read off the reference.

STEP 0 "read": {kind, views, cloth, fit, notes?}
  views  [{image, view: front|back|side|three|detail|other, shows?, scale?: {mm_per_px, from}}]
  cloth  {name: {fabric?: garment_kb fabric | gsm, thickness_mm, bending_length_mm, stretch: woven|knit, source;
          stiffness: drapey|soft|medium|crisp|stiff|rigid; colour: [r,g,b] | {at: [[u,v],..], view}; print?: {kind,
          repeat_mm, colours?, source}; grain: text}}   (a fabric name fills the numbers from garment_kb.json)
  fit    {region: {ease_mm, source}}                  (chest, waist, hip, sleeve, neck... any region names)
STEP 1 "parts": {pieces, details, closures, seams, over?}
  over     [garment names of this model it is worn over] (T9: built on their approved builds; chain_layers)
  pieces   {name: {what, cloth (a step-0 cloth), seen: seen|occluded|inferred, from (convention; needed unless seen),
            build: full|simplified|omit, why (unless full), stiff: bool, layer: int (0 = next to the body / the garment
            under it), where?: {view, outline: [[u,v],..]} (needed when seen)}}
  details  {name: {what, on: [pieces], cloth? (braid, zip tape...), follows?: ["piece:edge"] (a trim along edges), count?, seen, from?, build, why?, where?: {view, at: [[u,v],..] | outline | outlines}}}
  closures {name: {what, pieces: [pieces it joins; one for a band closing on itself], details?: [details]}}
  seams    [{a: "piece:edge", b: "piece:edge", kind?: seam|fold|set_in|topstitch, length: {body: [measurement names]} |
            {style: {ratio | value_mm, of?, source}}}]
STEP 2 "style": {state, bends, pose, rows, layers?}
  layers {mode: visible|full, why}  (worn over another garment: visible (default) keeps the garment under where it is seen;
          full fits all of it inside, for a reason: chain_press.py, T12)
  state  {closure: {state: open|closed|partly, detail?, source}}   (EVERY inventory closure, none other)
  bends  [{id, on (piece | piece:edge | detail | closure), target: {value, unit, of (a ratio's base)} | {is}, source}]
  pose   {name, source}
  rows   [{id, what, target: {value, unit, tol?, of?} | {is}, source, note?, view?, at?: [[u,v],..]}]  (what the photo
          judges: the structure gate's targets). what = a structure_rows.KINDS kind (refused otherwise, with the list); a
          ratio is OF the kind's base (its name or a row id of it); a numeric bend names its kind in "what" too (C286)
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


# ---------------------------------------------------------------- step 0
def check_read(p: dict) -> dict:
    """The reading, validated and completed (fabric numbers from garment_kb); PlanRefused names every fault."""
    bad, p = [], json.loads(json.dumps(p))
    if not str(p.get("kind") or "").strip():
        bad.append("kind: say what the garment is (e.g. 'dress shirt', 'hussar jacket, stand collar, zip front')")
    views = p.get("views")
    if not isinstance(views, list) or not views:
        bad.append("views: at least one reference picture [{image, view}]")
        views = []
    for i, v in enumerate(views):
        if not isinstance(v, dict) or not Path(str(v.get("image", ""))).exists():
            bad.append(f"views[{i}]: image {v.get('image') if isinstance(v, dict) else v!r} not found")
        elif v.get("view") not in VIEWS:
            bad.append(f"views[{i}]: view {v.get('view')!r}: one of {', '.join(VIEWS)}")
        elif v.get("scale") is not None and not (_num((v["scale"] or {}).get("mm_per_px")) and (v["scale"] or {}).get("from")):
            bad.append(f"views[{i}].scale: {{mm_per_px, from (what was measured to get it)}}")
    kb = _kb_fabrics()
    cloths = p.get("cloth")
    if not isinstance(cloths, dict) or not cloths:
        bad.append("cloth: {name: {...}} at least the main cloth (also braid, lining, interlining... when the garment has them)")
        cloths = {}
    for n, c in cloths.items():
        w = f"cloth.{n}"
        if not NAME.fullmatch(n) or not isinstance(c, dict):
            bad.append(f"{w}: a name of letters, digits, _ . - and a dict")
            continue
        f = c.get("fabric")
        if f is not None and f not in kb:
            bad.append(f"{w}.fabric {f!r}: not in garment_kb fabrics ({', '.join(kb)}); or give gsm, thickness_mm, "
                       "bending_length_mm, stretch and a source instead")
        elif f is not None:
            for k in ("gsm", "thickness_mm", "bending_length_mm", "stretch"):
                c.setdefault(k, _mid(kb[f].get(k)))
            c.setdefault("source", f"garment_kb.json fabrics.{f}")
        for k in ("gsm", "thickness_mm"):
            if not _num(c.get(k)):
                bad.append(f"{w}.{k}: a number (or fabric= a garment_kb fabric)")
        if c.get("stretch") not in ("woven", "knit", "none"):
            bad.append(f"{w}.stretch: woven | knit | none")
        if c.get("stiffness") not in STIFFNESS:
            bad.append(f"{w}.stiffness: one of {', '.join(STIFFNESS)} (how it holds a shape in the picture)")
        _src(c, w, bad)
        col = c.get("colour")
        if isinstance(col, dict) and _uv_list(col.get("at")) and isinstance(col.get("view", 0), int) \
                and 0 <= col.get("view", 0) < len(views) and Path(str(views[col.get("view", 0)].get("image", ""))).exists():
            from .cloth_reference import _sample_colour  # (garment_from_reference's working colour reading)
            c["colour"] = _sample_colour(views[col.get("view", 0)]["image"], col["at"])
            c["colour_from"] = {"view": col.get("view", 0), "at": col["at"]}
        elif not (isinstance(col, list) and len(col) == 3 and all(_num(x) for x in col)):
            bad.append(f"{w}.colour: [r, g, b] or {{at: [[u, v], ...], view}} (sampled from the picture)")
        pr = c.get("print")
        if pr is not None and pr != "none":
            if not isinstance(pr, dict) or not pr.get("kind"):
                bad.append(f"{w}.print: {{kind (check, stripe, ...), repeat_mm, source}} or 'none'")
            elif pr.get("kind") != "none":
                if not _num(pr.get("repeat_mm")):
                    bad.append(f"{w}.print.repeat_mm: the repeat in mm (from a scale or a count across a known width)")
                _src(pr, f"{w}.print", bad)
        if not str(c.get("grain") or "").strip():
            bad.append(f"{w}.grain: how the grain runs (e.g. 'lengthwise down CF, check matched at CF')")
    fit = p.get("fit")
    if not isinstance(fit, dict) or not fit:
        bad.append("fit: {region: {ease_mm, source}} for each region the reference shows (chest, waist, sleeve...)")
        fit = {}
    for r, e in fit.items():
        if not isinstance(e, dict) or not _num(e.get("ease_mm")):
            bad.append(f"fit.{r}: ease_mm (a number: garment minus body girth)")
        else:
            _src(e, f"fit.{r}", bad)
    if bad:
        raise PlanRefused("step 0 (read) refused:\n  " + "\n  ".join(bad))
    return p


# ---------------------------------------------------------------- step 1
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


def check_parts(p: dict, read: dict) -> dict:
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
        on = x.get("on") or []
        miss = [q for q in on if q not in pieces]
        if not on or miss:
            bad.append(f"{w}.on: the pieces it sits on; not in the inventory: {', '.join(map(str, miss)) or '(none given)'}")
        if x.get("cloth") is not None and x["cloth"] not in cloths:
            bad.append(f"{w}.cloth {x['cloth']!r}: not a step-0 cloth ({', '.join(sorted(cloths))})")
        fl = x.get("follows") or []
        badf = [e for e in fl if not (isinstance(e, str) and ":" in e and e.split(":")[0] in pieces)]
        if not isinstance(fl, list) or badf:
            bad.append(f"{w}.follows: the 'piece:edge' list a trim runs along; not in the inventory: {', '.join(map(str, badf))}")
        if x.get("count") is not None and not (isinstance(x["count"], int) and x["count"] > 0):
            bad.append(f"{w}.count: a positive int")
        _seen(x, w, nv, bad)
    for n, x in (closures.items() if isinstance(closures, dict) else []):
        w = f"closures.{n}"
        ps = (x or {}).get("pieces") or []
        miss = [q for q in ps if q not in pieces] + [d for d in (x or {}).get("details") or [] if d not in details]
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
    if bad:
        raise PlanRefused("step 1 (parts) refused:\n  " + "\n  ".join(bad))
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
    p = check_read(plan) if sid == "0" else check_parts(plan, out["0"]) if sid == "1" else \
        check_style(plan, out["0"], out["1"])
    if sid == "1" and "over" in p:  # (worn over another garment of this model: exists, has a record, no loop; T9)
        from . import chain_layers as cl
        try:
            p["over"] = cl.check_over(model, garment, p["over"])
        except cl.LayerRefused as e:
            raise PlanRefused(f"step 1 (parts) refused: {e}") from None
    ref = p["views"][0]["image"] if sid == "0" else None
    st = gr.write(model, garment, sid, "done", output=p, reference=ref, by="garment_plan")
    paths = []
    if look:
        from . import garment_plan_look as gl
        paths = gl.draw(model, garment, sid, p, out["0"] if sid != "0" else p, out["1"] if sid == "2" else None)
        gr.attach_look(model, garment, sid, paths)
    return {"step": sid, "plan": p, "digest": st["digest"], "look": paths}


def text(model: str, garment: str, r: dict) -> str:
    sid, p = r["step"], r["plan"]
    L = [f"{model}:{garment} step {sid} ({gr.STEP[sid]['key']}) written: digest {r['digest']}"]
    if sid == "0":
        L.append(f"  kind: {p['kind']}; views: " + ", ".join(f"{i} {v['view']}" for i, v in enumerate(p["views"])))
        for n, c in p["cloth"].items():
            L.append(f"  cloth {n}: gsm {c['gsm']}, {c['thickness_mm']} mm, {c['stiffness']}, colour {c['colour']}"
                     f" ({c['source']})")
        L.append("  fit: " + ", ".join(f"{k} +{v['ease_mm']} mm" for k, v in p["fit"].items()))
    elif sid == "1":
        if p.get("over"):
            L.append(f"  worn over: {', '.join(p['over'])} (built over their approved builds: chain_layers, T9)")
        for n, x in p["pieces"].items():  # (every item of the look's legend: C288, the look is for shape)
            L.append(f"  piece {n}: {x['seen']}, build {x['build']}, {'stiff' if x['stiff'] else 'soft'}, layer {x['layer']}"
                     + (f", from {x['from']}" if x["seen"] != "seen" and x.get("from") else "")
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
        L += [f"  row {r_['id']}: {_tgt(r_['target'])}" + (f" (marked on view {r_.get('view', 0)})" if r_.get("at")
                                                          else " (not marked)") for r_ in p["rows"]]
    L += [f"  look: {x}" for x in r["look"]]
    nxt = {"0": "judge the look against the picture (are the samples on the right cloth), then garment_plan step='parts'",
           "1": "judge the look's SHAPES against the picture (does each outline follow its piece; occluded / inferred "
                "marked), then garment_plan step='style'",
           "2": "judge the look against the picture (does each yellow mark span what its row names)"
                "; step 3 measures the names step 1 calls for"}[sid]
    nxt += "; names and numbers are this text's, never read off the look"
    return "\n".join(L + [f"next: {nxt} (garment_record shows the record)"])
