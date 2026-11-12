"""Staged fitting: the stage plan, what a stage wants, its photos, the lever helpers. Part of likeness (likeness.py has the overview)."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from . import likeness
from .likeness import checklist, stage_names
from .likeness_sides import photo_sides

def _stage(name: str) -> dict:
    for s in stage_names():
        if s["name"] == name:
            return s
    raise ValueError(f"likeness: no stage {name!r} (have {', '.join(s['name'] for s in stage_names())})")


def stage_points(stage: str) -> list:
    """The 68-point indices a stage fits: its own and every earlier stage's (so a later stage can't undo them)."""
    pts = []
    for s in stage_names():
        pts += s["points"]
        if s["name"] == stage:
            break
    return sorted(set(pts) - likeness.JAW_CONTOUR)


def stage_plan(name: str | None = None) -> str:
    """The stages in order with their items, controls and gaps (items with no control wired, or not measurable)."""
    sheet = None
    if name:
        from . import store
        p = store.HOME / name / likeness.TARGETS
        sheet = json.loads(p.read_text()) if p.exists() else None
    lines = []
    for i, s in enumerate(stage_names(), 1):
        lines.append(f"{i}. {s['name']}: {s['what']} -> {s['control']}")
        for it in checklist():
            if it["stage"] != s["name"]:
                continue
            c = it["control"]
            if it["measure"]["kind"] == "judge":
                gap = "  -> judge by eye; " + c
            elif c.startswith("GAP"):
                gap = "  -> " + c
            else:
                gap = "  -> " + c
            conf = ""
            if sheet and it["id"] in sheet["items"]:
                conf = " [" + ", ".join(f"{r.get('view', '-')}: {r['confidence']}" for r in sheet["items"][it["id"]]["views"].values()) + "]"
            lines.append(f"     {it['name']}{conf}{gap}")
    return "\n".join(lines)


def _views_with(refs: dict, pts: list) -> list:
    out = []
    for v in refs["views"]:
        p = {f"lm{i}": v["points"][f"lm{i}"] for i in pts if f"lm{i}" in v["points"]}
        out.append({**{k: v[k] for k in v if k != "points"}, "points": p})
    return out


def _photos(refs: dict) -> list:
    k = hashlib.sha1(json.dumps(refs["views"], sort_keys=True).encode()).hexdigest()
    if k not in likeness._PHOTOS:
        likeness._PHOTOS.clear()
        likeness._PHOTOS[k] = photo_sides(refs)
    return likeness._PHOTOS[k]


def stage_wants(cmp: dict, stage: str, skip=()) -> tuple:
    """(want, pins, gaps) for humanfit_solve.solve from a comparison: each of the stage's items with a `solve` measure and a
    miss beyond its tolerance in the FRONT view asks that measure to move by the miss (front views are near
    orthographic: a 2D miss in mm is the 3D measure's, x across and z up); items sharing a measure add up. Earlier
    stages' measures are pinned where they are. gaps = the stage's items that miss with no solver measure."""
    from . import humanfit
    order = [s["name"] for s in stage_names()]
    k = order.index(stage)
    items = {it["id"]: it for it in checklist()}
    want, pins, gaps = {}, {}, []
    for r in cmp["rows"]:
        it = items[r["id"]]
        s = order.index(it["stage"])
        if r["view"] != "front" or s > k:
            continue
        if s < k:
            if it.get("solve"):
                pins[it["solve"]] = None
            continue
        if r["score"] <= 1.0 or r["id"] in skip:
            continue
        if it.get("solve"):
            want[it["solve"]] = want.get(it["solve"], 0.0) - r["miss"]
        elif r["score"] > 0:
            gaps.append(f"{it['name']} ({r['miss']:+.2f} {it['unit']}): {it['control']}")
    want = {m: f"{d:+.2f}" for m, d in want.items() if abs(d) > humanfit.TOL_MM}
    pins = {m: "+0" for m in pins if m not in want}
    return want, pins, gaps


def lever_value(base: dict, path: str, default: float) -> float:
    if path.startswith("nudge:"):
        return 0.0
    d = base.get("head", {})
    keys = path.split(".")
    for k in keys[:-1]:
        d = d.get(k) or {}
        if isinstance(d, (int, float)) and k in likeness.BARE:   # shape.nose_tip = 12 means {"up": 12}
            d = {likeness.BARE[k]: d}
        if not isinstance(d, dict):   # (a control given as a bare number: shape.hollow = 0.005)
            return default
    v = d.get(keys[-1], default) if isinstance(d, dict) else default
    return float(v) if isinstance(v, (int, float)) else default


def with_lever(base: dict, path: str, x: float, force: bool = False) -> tuple:
    """(base, refused?) with the lever set to x (a nudge: the landmark moved x m along its axis from `base`)."""
    import copy as _copy
    from . import humanfit_solve
    if path.startswith("nudge:"):
        _, lm, ax = path.split(":")
        mv = [0.0, 0.0, 0.0]
        mv["xyz".index(ax)] = float(x)
        if abs(x) < 1e-6:
            return base, False
        nb, rep = humanfit_solve.nudge(base, lm, move=mv, force=force)
        return nb, bool(rep.get("refused"))
    out = _copy.deepcopy(base)
    d = out.setdefault("head", {})
    keys = path.split(".")
    for k in keys[:-1]:
        if not isinstance(d.get(k), dict):
            d[k] = {likeness.BARE[k]: d[k]} if isinstance(d.get(k), (int, float)) and k in likeness.BARE else {}
        d = d[k]
    d[keys[-1]] = round(float(x), 5)
    return out, False


def _signed(cmp: dict, ids, views=None) -> float | None:
    v = [r["miss"] for r in cmp["rows"] if r["id"] in ids and r["score"] >= 0 and (views is None or r["view"] in views)]
    return float(np.mean(v)) if v else None


def _undone(start: dict, cur: dict, k: int) -> list:
    """Earlier stages' checklist items (re-measured) that got worse: > 0.5 x tol and past the tolerance."""
    order = [s["name"] for s in stage_names()]
    bmap = {(r["id"], r["vi"]): r for r in start["rows"]}
    out = []
    for r in cur["rows"]:
        b = bmap.get((r["id"], r["vi"]))
        if b is None or order.index(r["stage"]) >= k:
            continue
        # pins are the items read steadily: detector distances / angles in a front view. The shading and traced-jaw
        # readers move by more than a tolerance when anything nearby changes, and a turned view's camera is refitted
        # per model: holding those vetoed every later stage (first run: eyes, mouth and chin all refused).
        if r.get("kind") in likeness.SPECIAL or r["view"] != "front":
            continue
        if r["score"] >= 0 and b["score"] >= 0 and r["score"] > max(b["score"], 1.0) + 0.5:
            out.append((b, r))
    return out
