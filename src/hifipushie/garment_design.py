"""Stage 1 of the clothing workflow: the design sheet, and the evidence that the pattern really makes it.

A garment's `design` (spec["cloth"][g]["design"]) states what a pattern maker decides before drafting:
  {"kind": "shirt" | "tee" | "coat" | "skirt" | ... (garment_kb.json kinds),
   "from": a design that can make it ("simon", "carlton", "skirt_block": garment_kb.json "designs"),
   "fit": a fit of the kind ("slim", "regular", ...: ease bands per girth),
   "fabric": a fabric name (garment_kb.json fabrics: physical numbers + the solver preset), a cloth preset, or
             {"preset", overrides},
   "details": {detail: choice | {"type": choice, "options": {raw design options}, ...}} (collar, cuff,
             sleeve_placket, front_closure, placket, waistband, fly, skirt_closure, pockets, hem, yoke, darts, pleats,
             back_vent, belt, lining, shoulder, topstitch),
   "pattern": {design words: ease, length, sleeve_length, options...} (passed to the draft as they are),
   "notes": free text}
Anything the sheet leaves out is filled from the kind's defaults (`resolve` says which came from where). A choice
the chosen design can't make is a hard failure naming what it can make: say so in the sheet (e.g. "lining": "none").

`expand(g)` compiles the sheet into the ordinary garment keys (pattern from/options, drop, fabric, folds, generate,
detail); keys written on the garment itself win. `evidence(...)` proves each choice is in the drafted pieces and seam
table (garment_kb details.*.evidence): a barrel cuff needs a cuff piece closed on itself and interfaced, a turned
collar needs a fold line, a notched lapel a facing and fronts that aren't frozen as made...
"""
from __future__ import annotations

import copy
import functools
import json
import re
from pathlib import Path

import numpy as np

from . import pattern

KB_PATH = Path(__file__).with_name("garment_kb.json")
DETAIL_KINDS = ("collar", "cuff", "sleeve_placket", "front_closure", "placket", "waistband", "fly", "skirt_closure",
                "pockets", "hem", "yoke", "darts", "pleats", "back_vent", "belt", "lining", "shoulder", "topstitch")
SHEET_KEYS = {"kind", "from", "fit", "fabric", "details", "pattern", "notes", "method", "made", "block",
              "block_options", "ops", "over", "support", "layer_gap", "open"}
METHODS = ("simulate", "settle")


class DesignError(ValueError):
    pass


@functools.lru_cache(maxsize=1)
def _kb_cached(mtime: float) -> dict:
    return json.loads(KB_PATH.read_text())


def kb() -> dict:
    return _kb_cached(KB_PATH.stat().st_mtime)


def _choice(v) -> tuple[str, dict]:
    if isinstance(v, str):
        return v, {}
    if isinstance(v, dict) and "type" in v:
        return v["type"], {k: x for k, x in v.items() if k != "type"}
    raise DesignError(f'a detail is a choice name or {{"type": choice, "options": {{...}}}}, got {v!r}')


def validate(sheet: dict, where: str = "design") -> None:
    """Cheap checks: known keys, kind, design, fit, fabric and every detail choice exist in the knowledge base."""
    from .cloth import ClothError
    K = kb()
    if not isinstance(sheet, dict):
        raise ClothError(f"{where}: design is an object {{kind, from, fit, fabric, details, pattern, notes}}")
    bad = set(sheet) - SHEET_KEYS
    if bad:
        raise ClothError(f"{where}: design keys {sorted(bad)} unknown (have {sorted(SHEET_KEYS)})")
    kinds = [k for k in K["kinds"] if not k.startswith("_")]
    kind = sheet.get("kind")
    if kind not in kinds:
        raise ClothError(f"{where}: design kind {kind!r} unknown (have {', '.join(kinds)})")
    designs = [d for d in K["designs"] if not d.startswith("_")]
    fr = sheet.get("from")
    if fr == "draft" or (fr is None and sheet.get("block")):
        from . import pattern_blocks, pattern_draft
        if sheet.get("block") not in ("bodice", "knit", "trouser", "skirt"):
            raise ClothError(f"{where}: a drafted design needs \"block\": bodice | knit | trouser | skirt, then "
                             "\"ops\": [pattern operations]")
        for k_, op in enumerate(sheet.get("ops") or []):
            if not isinstance(op, dict) or op.get("op") not in list(pattern_draft.OPS) + ["unfold"]:
                raise ClothError(f"{where}: ops[{k_}] is {{\"op\": one of {', '.join(pattern_draft.OPS)}, unfold, ...}}")
    elif fr is not None and fr not in designs:
        raise ClothError(f"{where}: design from {fr!r}: no recipe (have {', '.join(designs)}; or leave it out and give "
                         "own pieces + seams on the garment)")
    fits = list(K["kinds"][kind].get("fit", {}))
    if sheet.get("fit") is not None and sheet["fit"] not in fits:
        raise ClothError(f"{where}: fit {sheet['fit']!r} unknown for {kind} (have {', '.join(fits) or 'none'})")
    f = sheet.get("fabric")
    if isinstance(f, str):
        from .cloth import FABRICS
        if f not in K["fabrics"] and f not in FABRICS:
            raise ClothError(f"{where}: fabric {f!r} unknown (have {', '.join(k for k in K['fabrics'] if not k.startswith('_'))} "
                             f"or a preset: {', '.join(FABRICS)})")
    if sheet.get("method") is not None and sheet["method"] not in METHODS:
        raise ClothError(f'{where}: method is "simulate" (sewn and fully simulated) or "settle" (structured parts '
                         "constructed finished, the loose cloth settled lightly from the fitted placement)")
    if sheet.get("over") is not None and not isinstance(sheet["over"], str):
        raise ClothError(f'{where}: over is the name of the garment this one is worn over (a jacket over "shirt")')
    if sheet.get("made") is not None and not (isinstance(sheet["made"], dict) and all(
            v in ("made", "draped") for v in sheet["made"].values())):
        raise ClothError(f'{where}: made is {{piece or role: "made" | "draped"}}')
    for d, v in (sheet.get("details") or {}).items():
        if d not in K["details"]:
            raise ClothError(f"{where}: detail {d!r} unknown (have {', '.join(k for k in K['details'] if not k.startswith('_'))})")
        try:
            c, _ = _choice(v)
        except DesignError as e:
            raise ClothError(f"{where}: {d}: {e}")
        choices = [k for k in K["details"][d] if not k.startswith("_")]
        if c not in choices:
            raise ClothError(f"{where}: {d} {c!r} unknown (have {', '.join(choices)})")


def resolve(sheet: dict) -> dict:
    """The sheet with every detail decided: {"kind", "from", "fit", "fabric" (name, solver spec, physical numbers),
    "details": {d: {"choice", "params", "source": "sheet" | "kind default", "kb": entry, "recipe": what the design
    does for it, or None, "cannot": why the design can't}}, "problems": [hard failures]}."""
    K = kb()
    kind = sheet["kind"]
    kd = K["kinds"][kind]
    fr = sheet.get("from") or ("draft" if sheet.get("block") else None)
    rec = K["designs"].get(fr) if (fr and fr != "draft") else None  # a drafted design is judged by evidence alone
    fit = sheet.get("fit") or (next(iter(kd.get("fit", {})), None))
    problems = []
    if rec and rec.get("kind") != kind and kind not in rec.get("kinds", []):
        problems.append(f"design {fr} makes a {rec.get('kind')}, not a {kind}")
    fab_name = sheet.get("fabric") or kd.get("fabric")
    fab = fabric_spec(fab_name)
    details = {}
    asked = dict(sheet.get("details") or {})
    want = list(dict.fromkeys(list(kd.get("details", {})) + list(asked)))
    for d in want:
        src = "sheet" if d in asked else "kind default"
        c, params = _choice(asked[d] if d in asked else kd["details"][d])
        entry = K["details"][d][c]
        r, cannot = None, None
        if rec is not None:
            can = rec.get("can", {}).get(d)
            if can is None:
                if c != "none" and entry.get("evidence"):
                    cannot = rec.get("cannot", {}).get(f"{d}.{c}") or f"{fr}'s recipe says nothing about {d}"
                else:
                    r = {}
            elif c in can:
                r = can[c]
            else:
                cannot = rec.get("cannot", {}).get(f"{d}.{c}") or f"{fr} can make {d}: {', '.join(can)}"
        if cannot:
            problems.append(f"{d} {c!r} ({src}): {fr} can't make it: {cannot}. Choose one it can make in the sheet.")
        details[d] = {"choice": c, "params": params, "source": src, "kb": entry, "recipe": r, "cannot": cannot}
    for d, info in details.items():  # a choice that needs another detail (a barrel cuff needs a sleeve placket)
        for need in info["kb"].get("needs", []):
            nc = details.get(need, {}).get("choice")
            if nc in (None, "none"):
                problems.append(f"{d} {info['choice']!r} needs a {need} (it is {nc or 'not chosen'}): "
                                f"{K['details'][d][info['choice']]['label']}")
    for r_ in kd.get("required", []):
        if r_ not in details:
            problems.append(f"{kind} needs a {r_} choice")
    return {"kind": kind, "from": fr, "fit": fit, "fit_bands": kd.get("fit", {}).get(fit, {}), "fabric": fab,
            "details": details, "problems": problems, "kind_kb": kd, "recipe": rec}


def fabric_spec(f) -> dict:
    """{"name", "solver" (what cloth.fabric takes), "physical" (gsm, thickness, stretch...)}."""
    K = kb()
    if isinstance(f, dict):
        return {"name": f.get("preset", "custom"), "solver": f, "physical": {}}
    if f in K["fabrics"]:
        e = K["fabrics"][f]
        solver = dict({"preset": e["preset"]}, **e.get("overrides", {})) if e.get("overrides") else e["preset"]
        return {"name": f, "solver": solver, "physical": {k: v for k, v in e.items() if k not in ("preset", "overrides")}}
    return {"name": f, "solver": f, "physical": {}}


def _merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def compile_sheet(sheet: dict) -> dict:
    """The garment keys the sheet stands for (no draft yet): pattern, drop, fabric, folds, generate, detail."""
    r = resolve(sheet)
    rec = r["recipe"] or {}
    out: dict = {}
    if r["from"] == "draft":
        bo = dict(sheet.get("block_options") or {})
        band = r["fit_bands"].get("chest")
        if band and "chest_ease" not in bo and sheet["block"] in ("bodice", "knit"):
            bo["chest_ease"] = round(0.5 * (band[0] + band[1]), 3)  # ease by garment category: the fit's middle
        out["pattern"] = {"from": "draft", "block": sheet["block"], "block_options": bo, "ops": list(sheet.get("ops") or [])}
    elif r["from"]:
        pat = {"from": rec.get("pattern_from", r["from"])}
        fo = (rec.get("fit_options") or {}).get(r["fit"]) or {}
        pat = _merge(pat, fo)
        out["pattern"] = pat
    detail, drop, folds, gen = {}, [], [], []
    for d, info in r["details"].items():
        rc = info["recipe"] or {}
        if "options" in rc and "pattern" in out:
            out["pattern"] = _merge(out["pattern"], {"options": rc["options"]})
        if "pattern" in rc and "pattern" in out:
            out["pattern"] = _merge(out["pattern"], rc["pattern"])
        if info["params"].get("options") and "pattern" in out:
            out["pattern"] = _merge(out["pattern"], {"options": info["params"]["options"]})
        drop += rc.get("drop", [])
        folds += rc.get("folds", [])
        gen += rc.get("generate", [])
        detail.update(info["kb"].get("detail", {}))
    if sheet.get("pattern") and "pattern" in out:
        out["pattern"] = _merge(out["pattern"], sheet["pattern"])
    out["fabric"] = r["fabric"]["solver"]
    if sheet.get("method"):
        out["method"] = sheet["method"]
    for k in ("over", "support", "layer_gap"):  # layering: worn over another garment, with its structure pieces
        if sheet.get(k) is not None:
            out[k] = sheet[k]
    if drop:
        out["drop"] = drop
    if folds:
        out["folds"] = folds
    if gen:
        out["generate"] = gen
    if detail:
        out["detail"] = detail
    return out


def expand(g: dict) -> dict:
    """The garment with its design compiled in (garment keys win; pattern dicts merge, the garment's on top)."""
    sheet = g["design"]
    base = compile_sheet(sheet)
    own = {k: v for k, v in g.items() if k != "design"}
    out = _merge(base, own) if own else base
    for k in ("folds", "generate", "drop"):  # lists add up: the design's and the garment's
        if k in base and k in own:
            out[k] = list(base[k]) + [x for x in own[k] if x not in base[k]]
    out["_design"] = sheet
    return out


# ---------------------------------------------------------------- fold lines


def fold_polyline(pcs: dict, f: dict, step: float = 0.003) -> np.ndarray:
    """A fold entry's line in its piece's pattern coordinates: `pattern.fold_line` (the one resolver; it also runs
    the ends out to the outline)."""
    return pattern.fold_line(pcs, f, step)


# ---------------------------------------------------------------- roles


def role_of(name: str, piece: dict | None = None) -> str:
    if piece is not None and piece.get("role"):
        return piece["role"]
    base = re.sub(r"(\.(L|R|m))+$", "", name)
    base = re.sub(r"\d+$", "", base)
    K = kb()["roles"]
    low = base.lower()
    for role, al in K.items():
        if role.startswith("_"):
            continue
        if low in (a.lower() for a in al):
            return role
    for role, al in K.items():
        if role.startswith("_"):
            continue
        if any(low.startswith(a.lower()) for a in al):
            return role
    return base


def roles(Bp: dict) -> dict:
    out: dict = {}
    for nm, pc in Bp["pieces"].items():
        out.setdefault(role_of(nm, pc), []).append(nm)
    return out


def made_or_draped(Bp: dict, res: dict | None = None, sheet: dict | None = None) -> dict:
    """{piece: ("made" | "draped", why)}: how each piece gets its shape. Made = constructed finished, as a tailor
    makes it on the table before it goes on the body (a collar turned and pressed, a cuff, a waistband, a placket):
    its shape comes from its construction (fold lines, interfacing), never from simulating it into shape. Draped =
    loose cloth whose shape is the body, gravity and its seams (fronts, backs, sleeves, skirt panels). From: the
    sheet's own "made" {piece or role: ...}, else the knowledge base (a detail's made_of rests "as_made" / "flat"),
    else interfacing (wholly interfaced = made)."""
    pcs = Bp["pieces"]
    whole = {e for e in Bp["interfaced"] if isinstance(e, str)}
    by_role = {}
    for d, info in ((res or {}).get("details") or {}).items():
        for part in info["kb"].get("made_of", []):
            if part.get("rests"):
                by_role[part["role"]] = ("made" if part["rests"] == "as_made" else "draped", f"{d} {info['choice']}")
    own = (sheet or {}).get("made") or {}
    out = {}
    for nm, pc in pcs.items():
        role = role_of(nm, pc)
        if nm in own or role in own:
            out[nm] = (own.get(nm, own.get(role)), "the sheet says so")
        elif role in by_role:
            out[nm] = by_role[role]
        elif nm in whole:
            out[nm] = ("made", "wholly interfaced")
        else:
            out[nm] = ("draped", "loose cloth")
    return out


# ---------------------------------------------------------------- measuring the pattern


def _extent_at_x(P: np.ndarray, x: float) -> float:
    ys = []
    for a, b in zip(P, np.roll(P, -1, axis=0)):
        if (a[0] - x) * (b[0] - x) <= 0 and a[0] != b[0]:
            t = (x - a[0]) / (b[0] - a[0])
            ys.append(a[1] + t * (b[1] - a[1]))
    return (max(ys) - min(ys)) if len(ys) >= 2 else 0.0


def _band_height(pc: dict) -> float:
    """A band's height at its middle (bands are drawn along x: collar, stand, cuff, waistband)."""
    P = pc["P"]
    return _extent_at_x(P, 0.5 * (P[:, 0].min() + P[:, 0].max()))


def _closed_girth(Bp: dict, nm: str) -> float:
    pc = Bp["pieces"][nm]
    best = 0.0
    for a, b in Bp["stitches"]:
        pa, ka = a.split(":", 1)
        pb, kb_ = b.split(":", 1)
        if pa == nm and pb == nm:
            qa = pc["marks"].get(ka, pc["P"][pc["names"][ka]] if ka in pc["names"] else None)
            qb = pc["marks"].get(kb_, pc["P"][pc["names"][kb_]] if kb_ in pc["names"] else None)
            if qa is not None and qb is not None:
                best = max(best, float(abs(qa[0] - qb[0])))
    return best


def _roll_rise(Bp: dict, nm: str) -> float:
    for f in Bp.get("folds") or []:
        if f.get("piece") == nm and isinstance(f.get("line"), dict) and "offset" in f["line"]:
            return float(f["line"]["offset"])
    w = Bp["pieces"][nm].get("wrap") or {}
    if w.get("fold"):
        return float(w["fold"][0])
    return 0.003


def dims(Bp: dict, meas_mm: dict) -> dict:
    """Named dimensions of the drafted pattern (mm, or a ratio), where the pieces exist."""
    R = roles(Bp)
    pcs = Bp["pieces"]
    out = {}
    first = lambda r: R.get(r, [None])[0]
    st, fa, cu, wb, nb = first("collar_stand"), first("collar_fall"), first("cuff"), first("waistband"), first("neckband")
    if st:
        out["stand_cb"] = _band_height(pcs[st]) * 1000
    if fa:
        out["collar_cb"] = _band_height(pcs[fa]) * 1000
        if st:
            out["fall_cover"] = (_band_height(pcs[fa]) - _roll_rise(Bp, fa) - _band_height(pcs[st])) * 1000
    if cu:
        out["cuff_height"] = _band_height(pcs[cu]) * 1000
        cg = _closed_girth(Bp, cu)
        if cg and meas_mm.get("wrist"):
            out["cuff_over_wrist"] = cg * 1000 - meas_mm["wrist"]
        P = pcs[cu]["P"]
        if cg:
            out["cuff_overlap"] = (P[:, 0].max() - P[:, 0].min() - cg) * 1000
    if wb:
        out["waistband_height"] = _band_height(pcs[wb]) * 1000
        cg = _closed_girth(Bp, wb)
        if cg and meas_mm.get("waist"):
            out["waistband_over_waist"] = cg * 1000 - meas_mm["waist"]
        P = pcs[wb]["P"]
        if cg:
            out["waistband_overlap"] = (P[:, 0].max() - P[:, 0].min() - cg) * 1000
    if nb:
        from . import cloth_check
        for s in cloth_check.seams(Bp):
            sides = [s["a"], s["b"]]
            names = [[e.split(":")[0] for e in ([x] if isinstance(x, str) else x)] for x in sides]
            if names[0] == [nb] and nb not in names[1]:
                out["neckband_ratio"] = s["len_a_mm"] / max(s["len_b_mm"], 1e-9)
            elif names[1] == [nb] and nb not in names[0]:
                out["neckband_ratio"] = s["len_b_mm"] / max(s["len_a_mm"], 1e-9)
        out["neckband_width"] = _band_height(pcs[nb]) * 1000
    return out


# ---------------------------------------------------------------- evidence


def _sides(s):
    return [e.split(":")[0] for e in ([s] if isinstance(s, str) else s)]


def _check(ev: dict, Bp: dict, R: dict, D: dict, entry: dict, lap: str | None) -> tuple[bool, str]:
    pcs = Bp["pieces"]
    whole = {e for e in Bp["interfaced"] if isinstance(e, str)}
    anyint = {e if isinstance(e, str) else e["piece"] for e in Bp["interfaced"]}
    if "piece" in ev:
        r = ev["piece"]
        fz = [n for n, pc in ((Bp.get("fused") or {}).get("pieces") or {}).items() if role_of(n, pc) == r]
        if r not in R and fz:  # (cut as its own piece, fused to another: one cloth in the sim)
            return True, f"a {r} piece: {', '.join(fz)} (fused to its piece)"
        return (r in R), f"a {r} piece" + (f": {', '.join(R[r])}" if r in R else " (none in the pattern)")
    if "no_piece" in ev:
        r = ev["no_piece"]
        return (r not in R), f"no {r} piece" + (f" (but there is: {', '.join(R[r])})" if r in R else "")
    if "seam" in ev:
        a, b = ev["seam"]
        for s in Bp["seams"]:
            ra = {role_of(n, pcs[n]) for n in _sides(s[0])}
            rb = {role_of(n, pcs[n]) for n in _sides(s[1])}
            if (a in ra and b in rb) or (b in ra and a in rb):
                return True, f"{a} sewn to {b}"
        return False, f"no seam joins {a} to {b}"
    if "fold" in ev:
        r = ev["fold"]
        names = R.get(r, [])
        fl = [f for f in Bp.get("folds") or [] if f.get("piece") in names]
        legacy = [n for n in names if (pcs[n].get("wrap") or {}).get("fold")]
        if fl:
            return True, f"fold line on {r}: " + ", ".join(f"{f['piece']} {f.get('kind', 'press')} {f.get('angle')} deg" for f in fl)
        if legacy:
            return True, f"{r} placed folded (wrap.fold {pcs[legacy[0]]['wrap']['fold']}: the old U; a fold line replaces it)"
        return False, f"no fold line on {r} ({', '.join(names) or 'no such piece'})"
    if "not_made" in ev:
        r = ev["not_made"]
        frozen = [n for n in R.get(r, []) if n in whole]
        return (not frozen), (f"{r} free to roll" if not frozen else
                              f"{', '.join(frozen)} wholly interfaced: rests as made (frozen flat as placed), so it can't "
                              "roll. Interface a band instead")
    if "interfaced" in ev:
        r = ev["interfaced"]
        hit = [n for n in R.get(r, []) if n in anyint]
        return bool(hit), (f"{r} interfaced ({', '.join(hit)})" if hit else f"{r} not interfaced")
    if "closed" in ev:
        r = ev["closed"]
        hit = [n for n in R.get(r, []) if _closed_girth(Bp, n) > 0]
        return bool(hit), (f"{r} closed on itself by a stitch ({', '.join(hit)})" if hit else
                           f"{r} isn't closed on itself (no button/buttonhole stitch on the piece)")
    if "stitches" in ev:
        r = ev["stitches"]
        names = set(R.get(r, []))
        n = sum(1 for a, b in Bp["stitches"] if a.split(":")[0] in names or b.split(":")[0] in names)
        return n >= int(ev.get("min", 1)), f"{n} stitches (buttons) on {r} (need {ev.get('min', 1)})"
    if "lap" in ev:
        r = ev["lap"]
        if not lap:
            return True, "no lap convention for this kind"
        outer_side = "L" if lap.startswith("left") else "R"
        holes = {a.split(":")[0] for a, b in Bp["stitches"] for a in (a, b) if "hole" in a.split(":", 1)[1].lower()}
        names = R.get(r, [])
        outs = {n: float((pcs[n].get("wrap") or {}).get("out", 0)) for n in names}
        if len(outs) < 2:
            return True, "one front"
        outer = max(outs, key=outs.get)
        ok = outer.endswith("." + outer_side)
        conv = lap.replace("_", " ")
        if not ok:
            return False, f"{outer} is the outer front (wrap.out), the convention is {conv}"
        hole_side = holes & set(names)
        if hole_side and outer not in hole_side:
            return False, f"{outer} laps over ({conv}) but the buttonholes are on {', '.join(sorted(hole_side))}"
        return True, f"{outer} laps over ({conv})"
    if "darts" in ev:
        n = 0
        for a, b in Bp["seams"]:
            if isinstance(a, str) and isinstance(b, str) and a.split(":")[0] == b.split(":")[0] \
                    and a.split(">")[-1] == b.split(">")[-1]:
                n += 1
        return n > 0, f"{n} darts sewn"
    if "dim" in ev:
        k = ev["dim"]
        rng = entry.get("dims", {}).get(k)
        if k not in D:
            return False, f"{k}: can't be measured (the piece isn't there)"
        v = D[k]
        if rng is None:
            return True, f"{k} {v:.1f}"
        ok = rng[0] - 0.5 <= v <= rng[1] + 0.5 if k != "neckband_ratio" else rng[0] - 1e-3 <= v <= rng[1] + 1e-3
        unit = "" if "ratio" in k else " mm"
        return ok, f"{k} {v:.2f}{unit} (practice {rng[0]}..{rng[1]}{unit})" if "ratio" in k else \
            f"{k} {v:.1f}{unit} (practice {rng[0]}..{rng[1]}{unit})"
    return False, f"unknown evidence {ev}"


def evidence(res: dict, Bp: dict, meas_mm: dict) -> list:
    """[(ok, detail, choice, text)] for every evidence check of every chosen detail."""
    R = roles(Bp)
    D = dims(Bp, meas_mm)
    lap = res["kind_kb"].get("lap")
    out = []
    for d, info in res["details"].items():
        for ev in info["kb"].get("evidence", []):
            ok, txt = _check(ev, Bp, R, D, info["kb"], lap)
            out.append((ok, d, info["choice"], txt))
    return out


def sheet_text(res: dict) -> list:
    """The resolved sheet as lines: every choice, where it came from, its dimensions to work to."""
    L = [f"kind {res['kind']}" + (f", from {res['from']}" if res["from"] else ", own pieces") + f", fit {res['fit']} "
         f"(ease bands {', '.join(f'{k} {v[0] * 100:+.0f}..{v[1] * 100:+.0f}%' for k, v in res['fit_bands'].items()) or 'none'})"]
    fp = res["fabric"]
    ph = fp["physical"]
    L.append(f"fabric {fp['name']}: solver {fp['solver']}" + (
        f"; {ph.get('gsm')} g/m2, {ph.get('thickness_mm')} mm, {ph.get('stretch')}, bending length "
        f"{ph.get('bending_length_mm')} mm" if ph else ""))
    for d, info in res["details"].items():
        dm = info["kb"].get("dims") or {}
        L.append(f"  {d}: {info['choice']} [{info['source']}] - {info['kb'].get('label', '')}"
                 + (f"; dims {', '.join(f'{k} {v[0]}..{v[1]}' for k, v in dm.items())}" if dm else "")
                 + (f"; NEEDS {', '.join(info['kb']['needs'])}" if info["kb"].get("needs") else "")
                 + (f"  !! {res['from']} can't: {info['cannot']}" if info["cannot"] else ""))
    return L
