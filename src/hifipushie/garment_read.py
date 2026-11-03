"""Step 0 of the garment record, the READING (garment_plan step "read"; its form: garment_plan's docstring): kind (a
short name), the views, the cloth as numbers, the fit read as ratios on the picture (garment_fit.py). Split out of
garment_plan.py (C335). Refusals name the item and what to write instead; every refusal lists the fabric names and the
stiffness values (t s0-1: no list anywhere the agent could reach)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .garment_plan import NAME, STIFFNESS, VIEWS, PlanRefused, _kb_fabrics, _mid, _num, _src, _uv_list  # (import garment_plan first)

KIND_WORDS = 5


def check_read(p: dict, body=None) -> dict:
    """The reading, validated and completed (fabric numbers from garment_kb; the fit's ratios applied to body: a
    garment_fit Body or a callable giving one); PlanRefused names every fault."""
    bad, p = [], json.loads(json.dumps(p))
    kind = str(p.get("kind") or "").strip()
    if not kind:
        bad.append("kind: a short name of what the garment is (e.g. 'suit trousers', 'hussar jacket')")
    elif len(kind.split()) > KIND_WORDS or re.search(r"[,;:()]", kind):
        bad.append(f"kind {kind[:60]!r}...: a short name (<= {KIND_WORDS} words, no lists: 'suit trousers'); construction "
                   "(fly, loops, pockets, collar, crease, rise) goes in step 1 (parts) as pieces / details, the worn state "
                   "(break, rolled, open) in step 2 (style)")
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
        if isinstance(col, dict):
            from .garment_fit import view_index
            vi = view_index(views, col.get("view", 0), f"{w}.colour", bad)
            col["view"] = vi if vi is not None else col.get("view")
            if not _uv_list(col.get("at")):
                bad.append(f"{w}.colour.at: [[u, v], ...] pixels on the view where the cloth shows plainly")
        if isinstance(col, dict) and _uv_list(col.get("at")) and isinstance(col.get("view"), int) \
                and Path(str(views[col["view"]].get("image", ""))).exists():
            from .cloth_reference import _sample_colour  # (garment_from_reference's working colour reading)
            c["colour"] = _sample_colour(views[col["view"]]["image"], col["at"])
            c["colour_from"] = {"view": col["view"], "at": col["at"]}
        elif not isinstance(col, dict) and not (isinstance(col, list) and len(col) == 3 and all(_num(x) for x in col)):
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
    if True:  # (the fit: ratios read on the picture, applied to the model's body: garment_fit.py, C335)
        from . import garment_fit as gf
        try:
            p["fit"], p["heights"], p["fit_read"] = gf.check(p.get("fit"), views, body if not bad else False)
        except gf.FitRefused as e:
            bad.append(str(e))
    from .garment_plan import pixel_errors
    bad += pixel_errors(p, p.get("views"))
    if bad:
        raise PlanRefused("step 0 (read) refused:\n  " + "\n  ".join(bad) + "\n" + choices())
    return p


def choices() -> str:
    return (f"  fabrics (garment_kb; fills gsm, thickness, bending, stretch): {', '.join(_kb_fabrics())}\n"
            f"  stiffness: {', '.join(STIFFNESS)}; views by name or index")


def views_by_name(plan, views: list):
    """Every "view" a plan names (outside step 0's own views list) as an index: by name or index (t s0-1: "front" was
    refused with only the form's text)."""
    from .garment_fit import view_index
    bad = []

    def walk(x, w):
        if isinstance(x, list):
            for i, y in enumerate(x):
                walk(y, f"{w}[{i}]")
        elif isinstance(x, dict):
            for k, y in x.items():
                if k == "view" and isinstance(y, str):
                    vi = view_index(views, y, w, bad)
                    if vi is not None:
                        x[k] = vi
                elif k != "views":
                    walk(y, f"{w}.{k}" if w else k)
    walk(plan, "")
    return bad


