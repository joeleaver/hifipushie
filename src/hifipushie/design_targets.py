"""THE KIND'S CHECKLIST IS THE DESIGN INPUT (trials lesson 3, codified C243; Joe 2026-10-27: "why can't all measuring
and fitting be done in the first pass? why is it trial and error much past two rounds?").

Blind trial agents wrote their pass conditions (lengths, ease, sleeve length, shoulder, neckline, band widths, hem
shape) in their own logs, then hand-translated each into a block option or an op parameter, ran, measured and nudged:
every translation cost a round (tee t4: hip length took 3 rounds in metres, 0 once lengths were body levels, C238;
shirt t7: 7 rounds on a shirttail it could not reach, lengthBonus 0.05 cut 17 cm; hoodie t6: 4 rounds on a dropped
shoulder). Here the brief's items ARE the input:

  design_garment(design={"kind": "tee", "targets": {"body_length": "hips", "sleeve_length": "short", ...}})

Each item has ONE definition (cloth_checklist.json "design_targets": what it is on the body, how the pattern is
measured, units, tolerance, what it sets) used by all four jobs: the design input (`check`, `resolve`), the draft's
target (`plan` maps each item to the block option / op / FreeSewing option that makes it, `solve` drafts and measures
until the numeric ones are met), the gate row (`gate_rows`: target vs drafted, pattern_check) and the review item (the
item's "review" sentence). A kind's items and defaults: garment_kb.json kinds.<kind>.targets (+ the fit's ease per
girth, + every detail as a choice item). An option or op the sheet gives itself OVERRIDES the target's (said in the
reply; the gate still measures the target). An item the draft can't make is refused with the reason.

The solved numbers are stored in the sheet ("solved": {path: value}); `effective(sheet)` lays them, the target's own
choices and the sheet's explicit keys (on top) into an ordinary sheet that garment_design compiles as before.
"""
from __future__ import annotations

import copy
import functools
import json
from pathlib import Path

import numpy as np

CHECKLIST_PATH = Path(__file__).with_name("cloth_checklist.json")
BODY_LEVELS = {"waist": "hpsToWaistBack", "hips": "hpsToHipLineBack", "seat": "hpsToSeatBack",
               "crotch": "hpsToCrotchBack"}
EASE_ITEMS = {"chest": "chest_ease", "waist": "waist_ease", "hips": "hip_ease"}
NOT_CHOICE = ("shoulder",)  # (a detail name that is a measured item here: the shoulder's drop)
MAX_DRAFTS = 7  # the solve's drafts (each ~1-1.5 s); knit targets land on the first, FreeSewing ones in 3-4
SOLVE_SHARE = 0.4  # an item counts as solved within this share of its tolerance (the gate has the rest in hand)


class TargetError(ValueError):
    pass


@functools.lru_cache(maxsize=2)
def _items_cached(mtime: float) -> dict:
    return json.loads(CHECKLIST_PATH.read_text())["design_targets"]["items"]


def items() -> dict:
    """{item id: definition} (cloth_checklist.json design_targets.items)."""
    return _items_cached(CHECKLIST_PATH.stat().st_mtime)


def _kb():
    from . import garment_design
    return garment_design.kb()


def _kind(kind: str) -> dict:
    return (_kb().get("kinds") or {}).get(kind) or {}


def kinds_with_targets() -> list:
    return [k for k, v in _kb()["kinds"].items() if not k.startswith("_") and isinstance(v, dict) and v.get("targets")]


def choice_items(kind: str) -> dict:
    """{detail: [choices]}: every detail a sheet may choose, as a choice item (the detail's evidence is its row)."""
    from . import garment_design
    D = _kb()["details"]
    return {d: [c for c in D[d] if not c.startswith("_")] for d in garment_design.DETAIL_KINDS
            if d in D and d not in NOT_CHOICE}


def kind_items(kind: str) -> list:
    """Every item a kind takes: its checklist (kinds.<kind>.targets), fit + the ease per girth its fits band, the
    choice items. [] = the kind has no checklist yet."""
    kd = _kind(kind)
    if not kd.get("targets"):
        return []
    out = list(kd["targets"])
    girths = {g for f in (kd.get("fit") or {}).values() for g in f}
    out += [EASE_ITEMS[g] for g in ("chest", "waist", "hips") if g in girths and EASE_ITEMS[g] not in out]
    out += [k for k in ("fit", "cap_ease") if k not in out]
    out += [d for d in choice_items(kind) if d not in out]
    return out


def route(sheet: dict) -> tuple:
    """("draft", block) for a design drafted from a block, ("fs", design) for a FreeSewing draft: the sheet's own
    from / block, else the kind's draft, else the kind's first design (a shirt: simon)."""
    from . import design_schema
    kind = sheet.get("kind")
    kd = _kind(kind)
    fr = sheet.get("from")
    if fr == "draft" or (fr is None and (sheet.get("block") or kd.get("draft"))):
        return "draft", sheet.get("block") or (kd.get("draft") or {}).get("block") or "bodice"
    if fr is None:
        ds = [d for d, v in _kb()["designs"].items() if not d.startswith("_") and kind in (v.get("kinds") or [v.get("kind")])]
        if not ds:
            raise TargetError(f"targets: no draft makes a {kind} (give \"from\" or \"block\")")
        fr = ds[0]
    if design_schema.fs_options(fr) is None:
        raise TargetError(f"targets: {fr} is not a FreeSewing design with an option table (refresh_freesewing_options)")
    return "fs", fr


# ---------------------------------------------------------------- values


def _level(v, levels, what: str) -> dict:
    """{"to": level, "below": m} | {"m": metres}."""
    if isinstance(v, bool):
        raise TargetError(f"{what}: a level ({', '.join(levels)}), {{\"to\": level, \"below\": m}} or metres, got {v!r}")
    if isinstance(v, (int, float)):
        if not 0.05 <= float(v) <= 2.0:
            raise TargetError(f"{what}: {v} m is not a length (metres, e.g. 0.62)")
        return {"m": float(v)}
    if isinstance(v, str):
        v = {"to": v}
    if not isinstance(v, dict) or set(v) - {"to", "below"} or v.get("to") not in levels:
        raise TargetError(f"{what}: a level ({', '.join(levels)}), {{\"to\": level, \"below\": m (+ = lower)}} or "
                          f"metres, got {v!r}")
    b = v.get("below", 0.0)
    if isinstance(b, bool) or not isinstance(b, (int, float)) or abs(float(b)) > 0.3:
        raise TargetError(f"{what}: below is metres (+ = lower, - = higher; within 0.3), got {b!r}")
    return {"to": v["to"], "below": float(b)}


def _drop(v) -> float:
    if v == "set_in" or v is None:
        return 0.0
    if v == "dropped":
        from .pattern_styles import DROP_SHOULDER
        return float(DROP_SHOULDER)
    if isinstance(v, dict) and set(v) <= {"dropped"}:
        v = v.get("dropped")
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= float(v) <= 0.15:
        return float(v)
    raise TargetError(f"shoulder: \"set_in\", \"dropped\" (50 mm) or metres past the shoulder point (0..0.15), got {v!r}")


def normalise(item: str, v, kind: str):
    """The item's value in one shape (raises TargetError naming the item's units)."""
    I = items()
    if item in choice_items(kind):
        ch = choice_items(kind)[item]
        if v not in ch:
            raise TargetError(f"{item}: a choice of {', '.join(ch)}, got {v!r}")
        return v
    it = I[item]
    t = it["type"]
    if t == "choice":  # fit
        fits = list((_kind(kind).get("fit") or {}))
        if v not in fits:
            raise TargetError(f"fit: one of the {kind}'s fits ({', '.join(fits)}), got {v!r}")
        return v
    if t == "level":
        return _level(v, it["levels"], item)
    if t == "sleeve_level":
        return _level(v, it["levels"], item)
    if t == "shoulder":
        return _drop(v)
    if t == "fraction":
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not -0.2 <= float(v) <= 1.0:
            raise TargetError(f"{item}: {it['units']} (e.g. 0.12 = 12 %), got {v!r}")
        return float(v)
    if t == "m":
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0.003 <= float(v) <= 0.25:
            raise TargetError(f"{item}: {it['units']} (e.g. 0.02), got {v!r}")
        return float(v)
    if t == "neckline":
        v = {"style": v} if isinstance(v, str) else v
        if not isinstance(v, dict) or set(v) - {"style", "width", "depth"} or v.get("style") not in it["styles"]:
            raise TargetError(f"neckline: {it['units']}; style one of {', '.join(it['styles'])}, got {v!r}")
        for k in ("width", "depth"):
            if v.get(k) is not None and (isinstance(v[k], bool) or not isinstance(v[k], (int, float))
                                         or not 0.0 <= float(v[k]) <= 0.4):
                raise TargetError(f"neckline {k}: metres (0..0.4), got {v[k]!r}")
        return {k: (float(x) if k != "style" else x) for k, x in v.items()}
    if t == "hem":
        v = {"shape": v} if isinstance(v, str) else v
        if not isinstance(v, dict) or set(v) - {"shape", "rise"} or v.get("shape") not in it["shapes"]:
            raise TargetError(f"hem_shape: {it['units']}; shape one of {', '.join(it['shapes'])}, got {v!r}")
        if v.get("rise") is not None and (isinstance(v["rise"], bool) or not isinstance(v["rise"], (int, float))
                                          or not 0.0 <= float(v["rise"]) <= 0.15):
            raise TargetError(f"hem_shape rise: metres the side point stands above the centre-front hem (0..0.15), "
                              f"got {v['rise']!r}")
        return {k: (float(x) if k == "rise" else x) for k, x in v.items()}
    raise TargetError(f"{item}: no value rule for type {t}")


def check(sheet: dict, where: str = "design") -> None:
    """The contract (C241) for design.targets: a dict of the kind's items, each value in its units; an unknown item is
    refused with the kind's list."""
    tg = sheet.get("targets")
    if tg is None:
        return
    kind = sheet.get("kind")
    if not isinstance(tg, dict):
        raise TargetError(f"{where} targets is {{item: value}} (the kind's checklist: garment_reference(kind=...))")
    if not kind_items(kind):
        raise TargetError(f"{where} targets: the {kind} has no target checklist yet (kinds with one: "
                          f"{', '.join(kinds_with_targets())}); give block_options / ops / options instead")
    ok = kind_items(kind)
    bad = [k for k in tg if k not in ok]
    if bad:
        I = items()
        raise TargetError(f"{where} targets: unknown item{'s' if len(bad) > 1 else ''} "
                          + ", ".join(f'"{b}"' for b in bad) + f"; a {kind} takes: "
                          + "; ".join(f"{k} ({I[k]['units']})" if k in I else f"{k} (a choice)" for k in ok))
    for k, v in tg.items():
        try:
            normalise(k, v, kind)
        except TargetError as e:
            raise TargetError(f"{where} targets.{e}")


def resolve(sheet: dict) -> dict:
    """{item: normalised value}: the kind's defaults, the fit's ease (middle of the band) for the girths the route
    can target, then the sheet's targets."""
    kind = sheet["kind"]
    kd = _kind(kind)
    raw = dict(copy.deepcopy(kd.get("targets") or {}), **copy.deepcopy(sheet.get("targets") or {}))
    if sheet.get("fit") and "fit" not in (sheet.get("targets") or {}):
        raw["fit"] = sheet["fit"]  # (the sheet's own fit key is the same item)
    out = {k: normalise(k, v, kind) for k, v in raw.items()}
    band = (kd.get("fit") or {}).get(out.get("fit")) or {}
    rt, _ = route(sheet)
    # (a block's side seam runs straight down from the chest unless the hips need more: its waist and hips follow
    # chest_ease, so only the chest is a default target there; tee probe: hips_ease at its floor -0.15 still read +39 %)
    can = ("chest",) if rt == "draft" else ("chest", "waist", "hips")
    for g in can:
        it = EASE_ITEMS[g]
        if it not in out and g in band:
            out[it] = round(0.5 * (band[g][0] + band[g][1]), 4)
    return out


# ---------------------------------------------------------------- the plan: target -> what makes it


def level_m(v: dict, meas: dict, item: str) -> float:
    """m: a level's length on this body (body_length from the hps down the back, sleeve_length from the shoulder
    point down the arm)."""
    if "m" in v:
        return v["m"]
    mm = lambda k: float(meas[k]) / 1000.0
    if item == "body_length":
        tape = BODY_LEVELS[v["to"]]
        if tape not in meas:
            raise TargetError(f"body_length {v['to']}: the body has no {tape} tape")
        return mm(tape) + v["below"]
    from .pattern_blocks import SHORT_SLEEVE
    se = mm("shoulderToElbow") if "shoulderToElbow" in meas else 0.55 * mm("shoulderToWrist")
    sw = mm("shoulderToWrist")
    return {"short": SHORT_SLEEVE * se, "elbow": se, "three_quarter": 0.5 * (se + sw), "long": sw}[v["to"]] + v["below"]


def _gen_height(detail: str, choice: str) -> float | None:
    """m: the cut height of a detail's generated band (garment_kb details.<d>.<choice>.draft.generate), None if it
    generates none. Bands fold in half: the finished height is half."""
    e = ((_kb()["details"].get(detail) or {}).get(choice) or {}).get("draft") or {}
    gen = e.get("generate") or []
    return float(gen[0].get("height", 0.035)) if gen else None


def _get_path(d: dict, path: str):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _explicit(sheet: dict, path: str):
    """The value the sheet ITSELF gives at a knob path (None: not given): block_options.*, ops.<op>.<param> (the
    sheet's own op of that kind), options.* (pattern.options), details.<d>.generate.*"""
    head, _, rest = path.partition(".")
    if head == "block_options":  # (a block option given at all overrides the whole target: length {"to": "hips"}
        # with the target's "below" turned under it read seat-long and passed, the override silent)
        return (sheet.get("block_options") or {}).get(rest.split(".")[0])
    if head == "ops":
        op, _, prm = rest.partition(".")
        for o in sheet.get("ops") or []:
            if isinstance(o, dict) and o.get("op") == op:
                return o.get(prm, "(the op, default)") if prm else o
        return None
    if head == "options":
        return _get_path((sheet.get("pattern") or {}).get("options") or {}, rest)
    if head == "details":
        d, _, prm = rest.partition(".")
        v = (sheet.get("details") or {}).get(d)
        return _get_path(v, prm) if isinstance(v, dict) else None
    return None


def plan(sheet: dict) -> dict:
    """What each target sets, before any body is known: {"targets", "route", "from", "fit", "details" {d: choice},
    "values" {path: value} (the analytic first guess; numbers that need the body are filled by `solve`), "knobs"
    {item: {"path", "slope", "lo", "hi"}} (the numbers `solve` turns), "ops" [op kinds in order], "overrides" [lines],
    "notes" [lines]}. Raises TargetError for an item the route can't make."""
    from . import design_schema
    tg = resolve(sheet)
    rt, src = route(sheet)
    kind = sheet["kind"]
    fs = design_schema.fs_options(src) if rt == "fs" else None
    values, knobs, details, ops, notes = {}, {}, {}, [], []
    from . import cloth
    tbl_opts = ((cloth.designs().get(src) or {}).get("options") or {}) if rt == "fs" else {}

    def fs_knob(item, opt, slope):
        e = (fs or {}).get(opt)
        if not e:
            raise TargetError(f"targets.{item}: {src} has no option {opt}")
        values[f"options.{opt}"] = tbl_opts.get(opt, e.get("default"))
        knobs[item] = {"path": f"options.{opt}", "slope": slope, "lo": e.get("min"), "hi": e.get("max")}

    asked = sheet.get("targets") or {}
    for d in choice_items(kind):  # choice items: the detail's choice (the sheet's own details win)
        if d in tg:
            details[d] = tg[d]
    for item, v in tg.items():
        if item in details or item == "fit":
            continue
        if item == "body_length":
            if rt == "draft":
                if "m" in v:
                    values["block_options.length"] = v["m"]
                    knobs[item] = {"path": "block_options.length", "slope": 1.0, "lo": 0.2, "hi": 1.5}
                else:
                    values["block_options.length"] = {"to": v["to"], "below": v["below"]}
                    knobs[item] = {"path": "block_options.length.below", "slope": 1.0, "lo": -0.3, "hi": 0.4}
            else:
                fs_knob(item, "lengthBonus", 0.7)
        elif item == "sleeve_length":
            if rt == "draft":
                ops.append("sleeve")
                if "m" in v:
                    values["ops.sleeve.length"] = v["m"]
                    knobs[item] = {"path": "ops.sleeve.length", "slope": 1.0, "lo": 0.05, "hi": 0.9}
                else:
                    values["ops.sleeve.length"] = v["to"]
                    values["ops.sleeve.length_bonus"] = 0.0
                    knobs[item] = {"path": "ops.sleeve.length_bonus", "slope": None, "lo": -0.6, "hi": 0.6}
            else:
                fs_knob(item, "sleeveLengthBonus", 0.55)
        elif item == "shoulder":
            if v > 0:
                if rt != "draft":
                    raise TargetError(f"targets.shoulder: {src} drafts a set-in shoulder; a dropped shoulder needs a "
                                      "design drafted from a block (\"from\": \"draft\", \"block\": \"knit\" | "
                                      "\"bodice\") with op drop_shoulder")
                ops.append("drop_shoulder")
                values["ops.drop_shoulder.drop"] = v
                knobs[item] = {"path": "ops.drop_shoulder.drop", "slope": 1.0, "lo": 0.0, "hi": 0.15}
                details["shoulder"] = "dropped"
        elif item in ("chest_ease", "hip_ease", "waist_ease"):
            if rt == "draft":
                if item == "waist_ease":
                    if item in asked:
                        raise TargetError("targets.waist_ease: a block's side seam runs straight from the chest (its "
                                          "waist follows chest_ease); give chest_ease, or op take_in on the side seams")
                    continue
                key = {"chest_ease": "chest_ease", "hip_ease": "hips_ease"}[item]
                values[f"block_options.{key}"] = v
                knobs[item] = {"path": f"block_options.{key}", "slope": 1.0, "lo": -0.15, "hi": 1.0}
            else:
                fs_knob(item, {"chest_ease": "chestEase", "waist_ease": "waistEase", "hip_ease": "hipsEase"}[item], 1.0)
        elif item == "cap_ease":
            if rt == "draft":
                if "sleeve" not in ops:
                    ops.append("sleeve")
                values["ops.sleeve.cap_ease"] = v
                knobs[item] = {"path": "ops.sleeve.cap_ease", "slope": 1.0, "lo": -0.05, "hi": 0.1}
            else:
                fs_knob(item, "sleevecapEase", 1.0)
        elif item == "neckline":
            st = v["style"]
            if st in ("collar", "hood"):
                want = "hood" if st == "hood" else None
                if want:
                    details.setdefault("collar", "hood")
                if v.get("width") is not None or v.get("depth") is not None:
                    raise TargetError(f"targets.neckline: a {st} neckline is the {st}'s own (give its width / depth on "
                                      "a crew, round or v neckline)")
                continue
            if rt != "draft":
                raise TargetError(f"targets.neckline {st}: {src} drafts a collared neckline (style \"collar\"); a "
                                  f"{st} neckline needs a design drafted from a block")
            if st == "crew":
                values["block_options.neckline"] = "crew"
            elif st == "round":
                values["block_options.neckline"] = "upper_loop"
            if st == "v" or v.get("width") is not None or v.get("depth") is not None:
                ops.append("neckline")
                values["ops.neckline.shape"] = "v" if st == "v" else "round"
                if v.get("width") is not None:
                    values["ops.neckline.widen"] = 0.0
                    knobs["neckline.width"] = {"path": "ops.neckline.widen", "slope": 1.8, "lo": -0.03, "hi": 0.12}
                if v.get("depth") is not None:
                    values["ops.neckline.front"] = 0.0
                    knobs["neckline.depth"] = {"path": "ops.neckline.front", "slope": 1.0, "lo": -0.05, "hi": 0.3}
        elif item in ("neckband_width", "cuff_height", "hem_band_height"):
            det = items()[item]["detail"]
            ch = details.get(det) or _choice_of(sheet, det)
            h = _gen_height(det, ch) if ch else None
            if h is not None:
                values[f"details.{det}.generate.height"] = 2.0 * v
                knobs[item] = {"path": f"details.{det}.generate.height", "slope": 0.5, "lo": 0.01, "hi": 0.4}
                if item == "neckband_width" and rt == "draft":
                    values["block_options.band_width"] = v  # (the crew's seam one band out from the neck base)
            elif rt == "fs" and item == "cuff_height":
                fs_knob(item, "cuffLength", 0.55)
            else:
                raise TargetError(f"targets.{item}: the {det} {ch or 'none'} has no band to size (choose a banded "
                                  f"{det}: {', '.join(c for c in choice_items(kind)[det] if _gen_height(det, c))})")
        elif item == "hem_shape":
            sh = v["shape"]
            if rt == "draft":
                if sh != "straight" or v.get("rise"):
                    from .pattern_tailor import HEM_RISE
                    ops.append("hem_shape")
                    values["ops.hem_shape.shape"] = sh
                    values["ops.hem_shape.rise"] = v.get("rise", HEM_RISE[sh])
                    if v.get("rise") is not None:
                        knobs[item] = {"path": "ops.hem_shape.rise", "slope": 1.0, "lo": 0.0, "hi": 0.15}
            else:
                hs = {"shirttail": "shirttail", "straight": "straight_double"}.get(sh)
                if hs is None:
                    raise TargetError(f"targets.hem_shape {sh}: {src}'s hems are straight and shirttail (Simon's "
                                      "baseball hem); a curved hem needs a drafted design (op hem_shape)")
                details["hem"] = hs
                if v.get("rise") is not None:
                    if sh != "shirttail":
                        raise TargetError("targets.hem_shape: a straight hem has no rise")
                    fs_knob(item, "hemCurve", 0.14)
    fit = tg.get("fit")
    fr = None if rt == "draft" else (sheet.get("from") or src)
    if rt == "fs" and not sheet.get("from"):
        notes.append(f"from {src} (the {kind}'s draft source: garment_reference(kind={kind!r}) draft_sources)")
    overrides = []
    for item, kn in knobs.items():
        ex = _explicit(sheet, kn["path"])
        if ex is not None:
            overrides.append(f"{item}: the sheet's own {kn['path']} = {json.dumps(ex)} overrides the target's (the "
                             "gate still measures the target)")
            kn["overridden"] = ex
    for d, c in details.items():
        own = (sheet.get("details") or {}).get(d)
        own_c = own if isinstance(own, str) else (own or {}).get("type")
        if own_c is not None and own_c != c:
            overrides.append(f"{d}: the sheet's own details.{d} {own_c!r} overrides the target's {c!r}")
    return {"targets": tg, "route": rt, "source": src, "from": fr, "fit": fit, "details": details, "values": values,
            "knobs": knobs, "ops": ops, "overrides": overrides, "notes": notes}


def _choice_of(sheet: dict, d: str):
    own = (sheet.get("details") or {}).get(d)
    if own is not None:
        return own if isinstance(own, str) else own.get("type")
    return ((_kind(sheet["kind"]).get("details") or {}).get(d))


def _set_path(d: dict, path: str, v) -> None:
    ks = path.split(".")
    cur = d
    for k in ks[:-1]:
        if not isinstance(cur.get(k), dict):
            cur[k] = {}
        cur = cur[k]
    cur[ks[-1]] = v


OP_ORDER = ("drop_shoulder", "neckline", "hem_shape", "sleeve")  # (drop before the sleeve's draft; hem before stands)


def effective(sheet: dict) -> dict:
    """The sheet with its targets laid in: the plan's choices and first guesses, the solved numbers over them, the
    sheet's own keys on top. No "targets" / "solved" keys (so it is idempotent); "_targets" keeps the resolved
    targets for the rows."""
    if not sheet.get("targets"):  # (no targets: a left-over "solved" means nothing)
        return {k: v for k, v in sheet.items() if k != "solved"} if "solved" in sheet else sheet
    p = plan(sheet)
    eff = {k: copy.deepcopy(v) for k, v in sheet.items() if k not in ("targets", "solved")}
    vals = dict(p["values"])
    for path, v in (sheet.get("solved") or {}).items():
        if any(kn["path"] == path for kn in p["knobs"].values()) or path in vals:
            vals[path] = v
    lay: dict = {}
    for path, v in vals.items():
        _set_path(lay, path, v)
    if p["from"] and not sheet.get("from"):
        eff["from"] = p["from"]
    if p["fit"] and not sheet.get("fit"):
        eff["fit"] = p["fit"]
    if lay.get("block_options"):
        eff["block_options"] = dict(lay["block_options"], **copy.deepcopy(sheet.get("block_options") or {}))
    if p["ops"]:
        mine = {o.get("op") for o in sheet.get("ops") or [] if isinstance(o, dict)}
        add = [dict({"op": k}, **((lay.get("ops") or {}).get(k) or {})) for k in OP_ORDER if k in p["ops"] and k not in mine]
        eff["ops"] = add + list(copy.deepcopy(sheet.get("ops") or []))
    if lay.get("options"):
        from .garment_design import _merge
        eff["pattern"] = _merge({"options": lay["options"]}, sheet.get("pattern") or {})
    det = dict(copy.deepcopy(sheet.get("details") or {}))
    for d, c in p["details"].items():
        det.setdefault(d, c)
    for d, prm in (lay.get("details") or {}).items():
        cur = det.get(d, _choice_of(sheet, d))
        cur = {"type": cur} if isinstance(cur, str) else dict(cur)
        from .garment_design import _merge
        cur = _merge(prm, cur)  # (the sheet's own params on top)
        det[d] = cur
    if det:
        eff["details"] = det
    eff["_targets"] = p["targets"]
    return eff


# ---------------------------------------------------------------- measuring the drafted pattern


def _pt(pc, nm):
    return np.asarray(pc["P"][pc["names"][nm]], float) if nm in pc["names"] else None


def _pieces_by_role(Bp: dict, role: str) -> list:
    from . import garment_design as gd
    return [(n, pc) for n, pc in Bp["pieces"].items() if gd.role_of(n, pc) == role]


def _first(Bp, role):
    ps = _pieces_by_role(Bp, role)
    return ps[0] if ps else (None, None)


def ease_rows(Bp: dict, body) -> dict:
    """{chest | waist | hips: ease} as look_pattern's "ease at" lines and the flat_pattern gate read it (cloth.sizing:
    each torso piece's width at the draft's girth line or the body's own height, the chest at the underarm, a
    closure's overlap left out, over the body's tape): ONE definition of ease. A girth the garment doesn't go round
    (above its hem, or crossed only by a curved hem's tip) is left out. (A pattern-only chord read 25 mm under the
    underarm gave the shirt +17.0 % chest where look_pattern printed +21.8 %: two definitions, two answers.)"""
    if body is None:
        return {}
    from . import cloth
    from . import garment_design as gd
    rows = cloth.sizing({"pieces": Bp, "body": body})["rows"]
    # (a hem band is a torso piece that ends below the chest by design, like the yoke above it: sizing flags it
    # "partial" and the hoodie's chest read "not measured" in look_pattern too; the band's absence is not a hem tip)
    bands = {n for n, pc in Bp["pieces"].items() if gd.role_of(n, pc) in ("hem_band", "waistband")}
    return {g: float(v["ease"]) for g, v in rows.items()
            if g in EASE_ITEMS and v.get("garment_mm", 0) > 0 and not set(v.get("partial") or ()) - bands}


def shoulder_drop(Bp: dict) -> float:
    """m: the front's shoulder seam past the shoulder point (0 without a drop)."""
    _, pc = _first(Bp, "front")
    if pc is None or "shoulderDrop" not in pc["names"] or "hps" not in pc["names"]:
        return 0.0
    h = _pt(pc, "hps")
    return float(np.linalg.norm(_pt(pc, "shoulderDrop") - h) - np.linalg.norm(_pt(pc, "shoulder") - h))


def measure(Bp: dict, gx: dict | None = None, body=None) -> dict:
    """{item: drafted value (m / fraction / name)} for every measurable item the draft has (the ease needs the body:
    cloth.Body or anything with .at landmarks and .m["mm"] tapes)."""
    from . import garment_design as gd
    m = ((Bp.get("draft") or {}).get("measurements")) or {}
    D = gd.dims(Bp, m)
    out = {}
    band = D.get("band_height", 0.0) / 1000.0
    _, bk = _first(Bp, "back")
    hps_y = None
    for role in ("back", "yoke"):
        for _, pc in _pieces_by_role(Bp, role):
            if "hps" in pc["names"]:
                hps_y = float(_pt(pc, "hps")[1])
                break
        if hps_y is not None:
            break
    if bk is not None and hps_y is not None and "cbHem" in bk["names"]:
        out["body_length"] = hps_y - float(_pt(bk, "cbHem")[1]) + band
    drop = shoulder_drop(Bp)
    out["shoulder"] = drop
    _, sl = _first(Bp, "sleeve")
    if sl is not None:
        P = np.asarray(sl["P"], float)
        out["sleeve_length"] = float(P[:, 1].max() - P[:, 1].min()) + D.get("cuff_height", 0.0) / 1000.0 + drop
    for g, e in ease_rows(Bp, body).items():
        out[EASE_ITEMS[g]] = e
    _, fr = _first(Bp, "front")
    if fr is not None and "hps" in fr["names"] and "cfNeck" in fr["names"]:
        h, c = _pt(fr, "hps"), _pt(fr, "cfNeck")
        out["neckline.width"] = 2.0 * abs(float(h[0] - c[0]))
        out["neckline.depth"] = float(h[1] - c[1])
    if fr is not None and "cfHem" in fr["names"]:
        side = next((s for s in ("bballEnd", "slashStart", "hem") if s in fr["names"]), None)
        if side:
            out["hem_shape"] = float(_pt(fr, side)[1] - _pt(fr, "cfHem")[1])
    for it, dk in (("neckband_width", "neckband_width"), ("cuff_height", "cuff_height"), ("hem_band_height", "band_height")):
        if dk in D:
            out[it] = D[dk] / 1000.0
    from . import cloth_check
    kind_ = (((gx or {}).get("_design") or {}).get("kind")) or ""
    caps = [r["ease"] for r in cloth_check.seams(Bp, kind_) if str(r.get("kind", "")).startswith("cap_")]
    if caps:  # (the set-in sleeve's cap seam, as the gate's seams row reads it)
        out["cap_ease"] = float(np.mean(caps))
    R = gd.roles(Bp)
    out["_roles"] = sorted(R)
    out["_style"] = ("hood" if "hood" in R else "collar" if ("collar_stand" in R or "collar_fall" in R or "collar" in R)
                     else "crew" if ((Bp.get("draft") or {}).get("options") or {}).get("neckline") == "crew" else None)
    return out


def target_value(item: str, v, meas: dict):
    """The target as a number (m / fraction) on this body, or a [lo, hi] range; None = nothing numeric to judge."""
    I = items()
    if item in ("body_length", "sleeve_length"):
        return level_m(v, meas, item)
    if item == "shoulder" or item in ("chest_ease", "waist_ease", "hip_ease", "cap_ease", "neckband_width",
                                      "cuff_height", "hem_band_height"):
        return float(v)
    if item == "hem_shape":
        if v.get("rise") is not None:
            return float(v["rise"])
        return list(I["hem_shape"]["ranges"][v["shape"]])
    return None


# ---------------------------------------------------------------- solving


def solve(g: dict, meas: dict, draft, log=None, body=None) -> dict:
    """Draft, measure, turn each numeric item's knob by secant until it is within SOLVE_SHARE of its tolerance (at
    most MAX_DRAFTS drafts). g: the garment (its design has targets); draft(g) -> the drafted pieces (cloth.pieces of
    the expanded garment); body: the ease's (ease_rows). Returns {"solved" {path: value}, "rows" [the last measure as rows], "drafts" n,
    "unreached" [lines]}."""
    sheet = g["design"]
    p = plan(sheet)
    I = items()
    tg = p["targets"]
    solved = {path: v for path, v in (sheet.get("solved") or {}).items()
              if any(kn["path"] == path for kn in p["knobs"].values())}
    # body-dependent first guesses (the band taken off a body length, a sleeve level's length)
    band = 0.0
    hb = p["values"].get("details.hem.generate.height")
    if hb is None:
        ch = p["details"].get("hem") or _choice_of(sheet, "hem")
        hb = _gen_height("hem", ch) if ch else None
    if hb:
        band = 0.5 * float(hb)
    cuff = 0.0
    cg = p["values"].get("details.cuff.generate.height")
    if cg is None:
        ch = p["details"].get("cuff") or _choice_of(sheet, "cuff")
        cg = _gen_height("cuff", ch) if ch else None
    if cg:
        cuff = 0.5 * float(cg)
    for item, kn in p["knobs"].items():
        if kn.get("overridden") is not None or kn["path"] in solved:
            continue
        if item == "body_length" and p["route"] == "draft":
            T = level_m(tg[item], meas, item)
            solved[kn["path"]] = round((tg[item].get("below", 0.0) if "to" in tg[item] else T) - band, 4)
        elif item == "sleeve_length" and p["route"] == "draft":
            T = level_m(tg[item], meas, item)
            drop = tg.get("shoulder", 0.0) or 0.0
            if kn["path"].endswith("length_bonus"):
                L = level_m({"to": tg[item]["to"], "below": 0.0}, meas, item)
                solved[kn["path"]] = round((T - cuff - drop) / L - 1.0, 4)
                kn["slope"] = L
            else:
                solved[kn["path"]] = round(T - cuff - drop, 4)
    if p["route"] == "draft" and "sleeve_length" in p["knobs"] and p["knobs"]["sleeve_length"]["slope"] is None:
        p["knobs"]["sleeve_length"]["slope"] = level_m({"to": tg["sleeve_length"]["to"], "below": 0.0}, meas,
                                                       "sleeve_length")
    hist: dict = {}
    n = 0
    unreached = []
    M = {}
    gg = copy.deepcopy(g)
    while n < MAX_DRAFTS:
        gg["design"] = dict(sheet, solved=dict(solved))
        Bp = draft(gg)
        n += 1
        M = measure(Bp, gg, body)
        moved = False
        for item, kn in p["knobs"].items():
            if kn.get("overridden") is not None:
                continue
            key = item
            if item.startswith("neckline."):
                T = tg["neckline"][item.split(".")[1]]
            else:
                T = target_value(item, tg[item], meas)
            val = M.get(key)
            if val is None or T is None or isinstance(T, list):
                continue
            tol = float(I["neckline" if item.startswith("neckline.") else item]["tolerance"])
            err = T - val
            if abs(err) <= SOLVE_SHARE * tol:
                continue
            x = _get_path(_lay(solved, p), kn["path"])
            x = float(x) if isinstance(x, (int, float)) else 0.0
            h = hist.setdefault(item, [])
            h.append((x, val))
            slope = kn["slope"] or 1.0
            if len(h) >= 2 and abs(h[-1][0] - h[-2][0]) > 1e-9 and abs(h[-1][1] - h[-2][1]) > 1e-9:
                slope = (h[-1][1] - h[-2][1]) / (h[-1][0] - h[-2][0])
            xn = x + err / slope
            lo, hi = kn.get("lo"), kn.get("hi")
            xc = min(max(xn, lo if lo is not None else -1e9), hi if hi is not None else 1e9)
            if abs(xc - x) < 1e-7:
                unreached.append(f"{item}: {kn['path']} at its limit {x:g} reaches {val:.4f}, target {T:.4f}")
                kn["overridden"] = "limit"
                continue
            solved[kn["path"]] = float(round(float(xc), 5))
            moved = True
        if not moved:
            break
    else:  # (the last turn moved a knob: draft what was solved, so the rows read it)
        gg["design"] = dict(sheet, solved=dict(solved))
        Bp = draft(gg)
        n += 1
        M = measure(Bp, gg, body)
    if log:
        log(f"targets solved in {n} draft(s)")
    return {"solved": solved, "measured": M, "drafts": n, "unreached": unreached, "plan": p, "Bp": Bp}


def _lay(solved: dict, p: dict) -> dict:
    lay: dict = {}
    for path, v in dict(p["values"], **solved).items():
        _set_path(lay, path, v)
    return lay


# ---------------------------------------------------------------- rows (the gate and the reply)


def _fmt(item: str, v) -> str:
    if v is None:
        return "-"
    if isinstance(v, list):
        return f"{v[0] * 1000:.0f}..{v[1] * 1000:.0f} mm"
    if isinstance(v, str):
        return v
    if item.endswith("_ease"):
        return f"{v * 100:+.1f} %"
    return f"{v * 1000:.0f} mm"


def _label(item: str, v) -> str:
    if isinstance(v, dict) and "to" in v:
        return f"{v['to']}" + (f" {v['below'] * 1000:+.0f} mm" if v.get("below") else "")
    if isinstance(v, dict):
        return json.dumps(v)
    return str(v)


def rows(Bp: dict, sheet: dict, kind: str = "", gx: dict | None = None, body=None) -> list:
    """One row per target item: {"id": "target:<item>", "stage", "status" PASS | FAIL | INFO, "ours", "ref", "why",
    "fix"} (the gate's row shape). Targets from the sheet (raw, with "targets") or an effective sheet ("_targets")."""
    tg = sheet.get("_targets")
    if tg is None:
        if not sheet.get("targets"):
            return []
        tg = resolve(sheet)
    try:
        p = plan(sheet) if sheet.get("targets") else None
    except TargetError:
        p = None
    I = items()
    meas = ((Bp.get("draft") or {}).get("measurements")) or {}
    M = measure(Bp, gx, body)
    kd = _kind(kind or sheet.get("kind"))
    band = (kd.get("fit") or {}).get(tg.get("fit")) or {}
    out = []
    fix = ("design_garment solves the targets on the current body: call it again (design={} re-solves); an explicit "
           "option / op in the sheet overrides a target (the reply lists them)")
    choices = choice_items(kind or sheet.get("kind"))
    for item, v in tg.items():
        if item in choices:
            out.append({"id": f"target:{item}", "stage": 3, "status": "INFO", "ref": v,
                        "ours": "the detail's evidence rows (look_pattern)", "measure": "garment_design.evidence",
                        "why": "a choice: judged by the detail's evidence"})
            continue
        if item == "fit":
            out.append({"id": "target:fit", "stage": 2, "status": "INFO", "ref": v, "ours": v,
                        "measure": "design.fit", "why": "the ease rows judge it"})
            continue
        it = I[item]
        if item == "neckline":
            st = M.get("_style")
            want = v["style"]
            ok = (st == want) or (want in ("round", "v") and st not in ("collar", "hood")) or (want == "crew" and st == "crew")
            out.append({"id": "target:neckline.style", "stage": 1, "status": "PASS" if ok else "FAIL", "ref": want,
                        "ours": st or "none", "measure": "design_targets.measure"} | ({} if ok else {"fix": fix}))
            for k in ("width", "depth"):
                T = v.get(k)
                val = M.get(f"neckline.{k}")
                if T is None:
                    out.append({"id": f"target:neckline.{k}", "stage": 1, "status": "INFO", "ours": _fmt(k, val),
                                "ref": "as drafted", "measure": "design_targets.measure",
                                "why": "no target given: the draft's own"})
                    continue
                ok = val is not None and abs(T - val) <= it["tolerance"] + 1e-9
                out.append({"id": f"target:neckline.{k}", "stage": 1, "status": "PASS" if ok else "FAIL",
                            "ours": _fmt(k, val), "ref": f"{_fmt(k, T)} +- {it['tolerance'] * 1000:.0f} mm",
                            "measure": "design_targets.measure"} | ({} if ok else {"fix": fix}))
            continue
        T = target_value(item, v, meas)
        val = M.get(item)
        tol = float(it.get("tolerance", 0.0))
        row = {"id": f"target:{item}", "stage": it.get("stage", 2), "measure": "design_targets.measure",
               "ours": _fmt(item, val), "target": _label(item, v)}
        if val is None:
            # (a FreeSewing waist the draft has no point for, an item with no piece): measured nowhere
            row.update(status="FAIL", ref=_fmt(item, T), why=f"{item}: not measurable on this draft ({it['pattern']})",
                       fix=fix)
        elif isinstance(T, list):
            ok = T[0] - 1e-9 <= val <= T[1] + 1e-9
            row.update(status="PASS" if ok else "FAIL", ref=f"{_label(item, v)}: {_fmt(item, T)}",
                       **({} if ok else {"fix": fix}))
        else:
            ok = abs(T - val) <= tol + 1e-9
            unit = f"{tol * 100:.1f} %" if item.endswith("_ease") else f"{tol * 1000:.0f} mm"
            row.update(status="PASS" if ok else "FAIL", ref=f"{_label(item, v)} = {_fmt(item, T)} +- {unit}",
                       miss=None if ok else round((val - T) * 1000, 1), **({} if ok else {"fix": fix}))
            g_ = {"chest_ease": "chest", "waist_ease": "waist", "hip_ease": "hips"}.get(item)
            if g_ and g_ in band and not band[g_][0] - 1e-6 <= T <= band[g_][1] + 1e-6:
                row["why"] = (f"the target is outside the {tg.get('fit')} band {band[g_][0] * 100:+.0f}..{band[g_][1] * 100:+.0f} %"
                              " (asked so)")
        if p and item in p["knobs"] and p["knobs"][item].get("overridden") not in (None, "limit"):
            row["why"] = (row.get("why", "") + f" explicit {p['knobs'][item]['path']} overrides the target").strip()
        out.append(row)
    # the ease a straight block's waist and hips follow (reported: no default target on a block)
    for it_ in ("waist_ease", "hip_ease"):
        if it_ not in tg and M.get(it_) is not None:
            out.append({"id": f"target:{it_}", "stage": 2, "status": "INFO", "ours": _fmt(it_, M[it_]),
                        "ref": "follows the chest (a block's straight side seam)", "measure": "design_targets.measure"})
    return out


def reply_lines(rows_: list, p: dict | None = None, extra: dict | None = None) -> list:
    """design_garment's lines: target -> drafted per item, failures first, then overrides / notes."""
    order = {"FAIL": 0, "PASS": 1, "INFO": 2}
    L = ["targets (the kind's checklist; pattern_check measures the same items):"]
    for r in sorted(rows_, key=lambda r: order.get(r["status"], 3)):
        L.append(f"  {r['status']:<5} {r['id'][7:]}: target {r.get('ref')} -> drafted {r.get('ours')}"
                 + (f" ({r['why']})" if r.get("why") else ""))
    for k in ("overrides", "notes"):
        for ln in (p or {}).get(k) or []:
            L.append(f"  {'OVERRIDE' if k == 'overrides' else 'note'}: {ln}")
    for ln in (extra or {}).get("unreached") or []:
        L.append(f"  UNREACHED: {ln}")
    if extra and extra.get("drafts"):
        L.append(f"  solved in {extra['drafts']} draft(s): " + (", ".join(f"{k} {v}" for k, v in sorted(extra['solved'].items())) or "nothing to solve"))
    return L


def template(kind: str) -> dict:
    """The kind's checklist as the template an agent fills (garment_reference(kind)): {item: {"default", "units",
    "definition", "levels" / "styles" / "shapes" / "choices", "range" (ease: the fit bands), "review"}}."""
    kd = _kind(kind)
    if not kd.get("targets"):
        return {}
    I = items()
    out = {}
    defaults = dict(kd["targets"])
    fits = kd.get("fit") or {}
    for item in kind_items(kind):
        if item in choice_items(kind):
            dflt = (kd.get("details") or {}).get(item)
            out[item] = {"default": dflt, "choices": choice_items(kind)[item]}
            continue
        it = I[item]
        e = {"default": defaults.get(item), "units": it["units"], "definition": it["definition"],
             "review": it.get("review")}
        for k in ("levels", "styles", "shapes"):
            if k in it:
                e[k] = it[k]
        if item == "fit":
            e["choices"] = list(fits)
        if item in ("chest_ease", "waist_ease", "hip_ease"):
            g = {"chest_ease": "chest", "waist_ease": "waist", "hip_ease": "hips"}[item]
            e["default"] = "the middle of the fit's band"
            e["range"] = {f: b[g] for f, b in fits.items() if g in b}
        if item == "hem_shape":
            e["range"] = it["ranges"]
        out[item] = e
    return out
