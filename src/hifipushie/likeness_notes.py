"""What a set of pictures can support: expression bias, lens, picture notes, coverage, the table's text. Part of likeness (likeness.py has the overview)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import likeness
from .likeness_detect import head_yaw
from .likeness_measure import Unmeasurable, _item
from .likeness_sides import _near_sign

def expression_bias(pictures: list, view: str | None = "front") -> dict:
    """{item id: "squint 0.70"}: the items an expression read on the references biases (in pictures of that view)."""
    out = {}
    for pn in pictures:
        if view and pn.get("view") != view:
            continue
        for nm, v in (pn.get("expressions") or {}).items():
            for iid in likeness.EXPR_BIAS.get(nm, []):
                out.setdefault(iid, f"{nm} {v:.2f}")
    return out


def lens_mm(cam: dict) -> float:
    """35 mm-equivalent focal length of a fitted camera (full-frame diagonal over the picture's)."""
    w, h = cam["size"]
    return float(cam["f"] * 43.27 / np.hypot(w, h))


def _skinlike(img, box_px, ref_rgb) -> float:
    """Share of a picture region whose colour is close to the face's skin (chroma and brightness)."""
    a = np.asarray(img.crop(tuple(int(round(v)) for v in box_px)).convert("RGB"), float).reshape(-1, 3)
    if len(a) == 0:
        return float("nan")
    ch = a / np.maximum(a.sum(1, keepdims=True), 1)
    cr = np.asarray(ref_rgb, float) / max(sum(ref_rgb), 1)
    lum = a.mean(1) / max(np.mean(ref_rgb), 1)
    return float(((np.linalg.norm(ch - cr, axis=1) < 0.035) & (lum > 0.45) & (lum < 1.7)).mean())


def picture_notes(ph: dict, md: dict | None = None) -> dict:
    """What a reference picture is good and bad for: view (and the detector's head yaw), lens, expression, light,
    ears and hairline showing. Each a short phrase; "problems" lists the ones that cost checklist items."""
    out = {"image": Path(ph["view"]["image"]).name, "view": ph["kind"], "problems": []}
    info = ph.get("info") or {}
    out["head_yaw"] = head_yaw(info.get("M"))
    cam = md["cam"] if md else ph["cam"]
    cy = abs(float(cam.get("yaw", 0.0)))
    if out["head_yaw"] is not None and ph["kind"] != "front" and abs(abs(out["head_yaw"]) - cy) > likeness.YAW_DOUBT:
        out["yaw_doubt"] = abs(abs(out["head_yaw"]) - cy)
        out["problems"].append(f"NOT ONE PROJECTION: the detector reads the head turned {abs(out['head_yaw']):.0f} deg, the fitted camera "
                               f"{cy:.0f} (a painting / generated picture): distances and widths are the FRONT picture's; this one gives "
                               "character (the contour's shape: bridge, tip, chin, jaw corner), its depth items' tolerances are widened")
    f = lens_mm(cam)
    out["lens_mm"] = round(f, 0)
    if f < 60:
        out["problems"].append(f"short lens (~{f:.0f} mm equivalent): perspective swells the nose, shrinks the ears")
    bs = info.get("bs") or {}
    for nm, (keys, lim) in likeness.EXPR.items():
        v = max((bs.get(k, 0.0) for k in keys), default=0.0)
        if v > lim:
            out.setdefault("expressions", {})[nm] = float(v)
            out["problems"].append(f"{nm} ({v:.2f}): an expression, not shape; it biases "
                                   + ", ".join(likeness.EXPR_BIAS[nm]) + " (fit those through the pose)")
    sh = md.get("shade") if md else None
    if sh:
        out["light_hard"] = round(sh["hard"], 2)
        out["light_fit"] = round(sh["fit_share"], 3)
        if sh["hard"] > 0.75:
            out["problems"].append(f"hard light ({sh['hard']:.2f}): shading reads shape and shadow edges together")
        if sh["fit_share"] > 0.15:
            out["problems"].append(f"one light explains the shading badly ({100 * sh['fit_share']:.0f}% rms): painted or "
                                   "mixed light, shape items unreliable")
    s = ph["side"]
    if s.P is not None and ph.get("mmpx"):
        mmpx = ph["mmpx"]
        try:
            ref = np.asarray(ph["img"].crop(tuple(int(v) for v in np.r_[s.pt(50) - 3, s.pt(50) + 3])).convert("RGB"),
                             float).reshape(-1, 3).mean(0)
            ex, ey = s.frame()
            ears = []
            for i, sgn in ((234, -1), (454, 1)):
                c = s.pt(i) + sgn * ex * 14 / mmpx
                r = 7 / mmpx
                ears.append(_skinlike(ph["img"], (c[0] - r, c[1] - r, c[0] + r, c[1] + r), ref))
            near = _near_sign(s)
            seen = [e for e, sg in zip(ears, (-1, 1)) if sg in near]
            out["ears_skin"] = [round(e, 2) for e in ears]
            if seen and min(seen) < 0.25:
                out["problems"].append("ears hidden (hair, collar or out of frame): ear items judge-only")
            top = s.pt([105, 334]) - ey * 12 / mmpx
            hb = (top[0] - 25 / mmpx, top[1] - 22 / mmpx, top[0] + 25 / mmpx, top[1])
            out["forehead_skin"] = round(_skinlike(ph["img"], hb, ref), 2)
            if out["forehead_skin"] < 0.5:
                out["problems"].append("hair over the forehead / hairline: forehead height unreadable")
        except (Unmeasurable, ValueError):
            pass
    elif s.P is None:
        out["problems"].append("no face found by the detector: only the stored landmarks are read")
    return out


def coverage_text(cmp: dict) -> str:
    """One glance: which checklist items these pictures support, which only by eye or inferred, which not, and why."""
    by = {}
    for r in cmp["rows"]:
        by.setdefault(r["id"], []).append(r)
    meas, inf, judge, none = [], [], [], {}
    for iid, rs in by.items():
        ok = [r for r in rs if r["score"] >= 0]
        if ok:
            (inf if all(r.get("inferred") for r in ok) else meas).append(iid)
        elif any(r.get("kind") == "judge" and r["vi"] != "-" for r in rs):
            judge.append(rs[0]["name"])
        else:
            why = (rs[0].get("why") or "").split(":")[0].split(";")[0][:60]
            none.setdefault(why or "?", []).append(rs[0]["name"])
    lines = [f"coverage: {len(meas)} items measured, {len(inf)} inferred from a weaker view, {len(judge)} judge by eye, "
             f"{sum(len(v) for v in none.values())} not supported by these pictures"]
    if inf:
        lines.append("  inferred (three-quarter for profile, tolerance x1.5): " + ", ".join(by[i][0]["name"] for i in inf))
    for why, names in none.items():
        lines.append(f"  not supported ({why}): " + ", ".join(names))
    if judge:
        lines.append("  judge by eye (panels): " + ", ".join(judge))
    kinds = [p["kind"] for p in cmp["photos"]]
    if "profile" not in kinds:
        need = sorted({r["name"] for r in cmp["rows"] if "profile" in _item(r["id"])["views"]})
        lines.append("  a true profile would measure (now inferred or judged): " + ", ".join(need))
    for pn in cmp.get("pictures", []):
        lines.append(f"  picture {pn['image']} ({pn['view']}, head yaw {pn['head_yaw'] if pn['head_yaw'] is None else round(pn['head_yaw'])}, "
                     f"lens ~{pn['lens_mm']:.0f} mm" + (f", light hardness {pn['light_hard']}" if "light_hard" in pn else "") + "): "
                     + ("; ".join(pn["problems"]) or "no problems found"))
    return "\n".join(lines)


def _fmt(v, unit):
    if not isinstance(v, float):
        return "-"
    return f"{v:.3f}" if unit == "" else f"{v:.1f}"


def table_text(cmp: dict, top: int | None = None) -> str:
    rows = cmp["rows"]
    meas = [r for r in rows if r["score"] >= 0]
    over = [r for r in meas if r["score"] > 1.0]
    res = ", ".join(f"{p['kind']} {m['mmpx']:.2f} mm/px ({p['side'].source} / {m['side'].source}"
                    + (", camera refitted" if m.get("cam_res") is not None else "") + ")"
                    for p, m in zip(cmp["photos"], cmp["models"]))
    lines = [coverage_text(cmp), "",
             f"likeness: {len(meas)} item-views measured, {len(over)} beyond tolerance (photo vs model through the same "
             f"camera; miss = model - photo). Pictures: {res}.",
             "  lm miss = the same measure on the landmarks alone; '!' = the readings differ by more than the tolerance (the "
             "miss depends on the definition: look at the panel). '~' = inferred from a weaker view (tolerance x1.5). cam = "
             "the refitted camera's residual at the item's points (mm; includes shape misses; widens the tolerance by half). "
             "Shape rows (%): the photo's shading against the model lit like the photo, region vs reference region; + miss "
             "= the photo is darker there than the model's shape predicts (deeper hollow, sharper turn); 3D = the model's "
             "own number in mm.",
             f"{'#':>2} {'item':40} {'view':14} {'photo':>8} {'model':>8} {'miss':>8} {'tol':>6} {'xtol':>5} {'lm miss':>8} {'cam':>5} {'3D':>6}  stage: control"]
    for i, r in enumerate(meas[:top] if top else meas, 1):
        dp = 3 if r["unit"] == "" else 1
        view = r["view"] + ("~" if r.get("inferred") else "")
        lines.append(f"{i:>2} {r['name'][:40]:40} {view:14} {_fmt(r['photo'], r['unit']):>8} {_fmt(r['model'], r['unit']):>8} "
                     f"{r['miss']:+8.{dp}f} {r['tol']:>6.3g} {r['score']:5.1f} "
                     + (f"{r['miss_lm']:+7.{dp}f}{' ' if r['agree'] else '!'}" if "miss_lm" in r else f"{'-':>8}")
                     + (f" {r['cam_mm']:5.1f}" if r.get("cam_mm") is not None else f" {'-':>5}")
                     + (f" {r['model3d']:6.1f}" if isinstance(r.get("model3d"), float) else f" {'-':>6}")
                     + f"  {r['stage']}: {r['control']}"
                     + ("" if r.get("source") == "detector/detector" else f"  [{r.get('source')}]")
                     + (f"  EXPRESSION ({r['expression']}): fit through the pose, not the identity" if r.get("expression") else "")
                     + (f"  CAUTION {r['reliability']}" if r["reliability"] and r["score"] > 1 else ""))
    rest = [r for r in rows if r["score"] < 0]
    if rest:
        lines.append("not measured (judge in the focus panels, or what is missing):")
        for r in rest:
            lines.append(f"   {r['name']} [{r['view']}{'~' if r.get('inferred') else ''}]: {r.get('why') or 'judge by eye'}"
                         + (f"; {r['reliability']}" if r["reliability"] and r["reliability"] not in (r.get("why") or "") else ""))
    return "\n".join(lines)
