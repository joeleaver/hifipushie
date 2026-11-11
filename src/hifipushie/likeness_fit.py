"""Staged fitting: the lever fit, fit_stage, the profile fit, stage_text, fit_likeness. Part of likeness (likeness.py has the overview)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .likeness import LEVERS, checklist, stage_names
from .likeness_compare import compare, profile_read
from .likeness_measure import _item
from .likeness_notes import EXPR_LEVERS, _fmt, expression_bias
from .likeness_panels import focus_sheet
from .likeness_sides import _refs
from .likeness_stages import (
    LEVER_VIEWS, _photos, _signed, _stage, _undone, _views_with, lever_value, stage_wants, with_lever,
)

def _lever_fit(name, base, photos, start, cmp0, k, ids, lever, force, log) -> tuple:
    """1-D secant on the lever for the items' signed miss, from `base` (measured: cmp0); every candidate
    integrity-guarded and checked against the earlier stages' items (re-measured against `start`). (base, compare,
    note)."""
    from . import humanfit
    path, step, (lo, hi), dflt = lever
    kind = _item(ids[0])["measure"]["kind"]
    views = LEVER_VIEWS.get(kind)
    x0 = lever_value(base, path, dflt)
    st0 = humanfit.state(base)
    f0 = _signed(cmp0, ids, views)
    if f0 is None:
        return base, cmp0, f"{path}: not measured"
    tol = _item(ids[0])["tol"]
    if abs(f0) <= tol:
        return base, cmp0, f"{path}: already within tolerance ({f0:+.2f})"
    tried = [(abs(f0), x0, base, cmp0, f0)]
    fresh = path.startswith("shape.jawline") and not isinstance((base.get("head", {}).get("shape") or {}).get("jawline"), dict)

    def ev(x):
        x = float(np.clip(x, lo, hi))
        nb, refused = with_lever(base, path, x, force)
        if refused:
            return None
        it = humanfit.integrity(nb, None, st0)
        if not it["ok"] and not force and humanfit._newly_broken(base, it):
            log.append(f"    {path} = {x:.4g}: BROKEN ({'; '.join(it['broken'])[:120]})")
            return None
        c = compare(name, nb, photos=photos)
        f = _signed(c, ids, views)
        und = _undone(start, c, k)
        log.append(f"    {path} = {x:.4g}: miss {f if f is None else round(f, 2)}" + (f", undoes {[u[1]['id'] for u in und]}" if und else ""))
        if f is None:
            return None
        if not und:
            tried.append((abs(f), x, nb, c, f))
        return f       # (a vetoed try still tells the secant which way the lever moves the item)
    if fresh:   # the control at its default first: that is the lever's real starting point
        fd = ev(x0)
        if fd is None:
            return base, cmp0, f"{path}: its default was refused"
        f0 = fd
    x1 = x0 + step if x0 + step <= hi else x0 - step
    f1 = ev(x1)
    if f1 is not None and abs(f1 - f0) > 0.02 * max(abs(f0), 1e-9):
        xs = float(np.clip(x1 - f1 * (x1 - x0) / (f1 - f0), lo, hi))
        if abs(xs - x1) > 1e-9 and abs(xs - x0) > 1e-9:
            f2 = ev(xs)
            if f2 is not None and abs(f2) > tol and len(tried) < 2:   # still vetoed or off: one try half way
                ev(x0 + 0.5 * (xs - x0))
    elif f1 is not None:
        log.append(f"    {path}: no effect on the item (lever doesn't reach it)")
    best = min(tried, key=lambda t: t[0])
    return best[2], best[3], f"{path}: {x0:.4g} -> {best[1]:.4g}, miss {f0:+.2f} -> {best[4]:+.2f} (tol {tol:g})"


def fit_stage(name: str, stage: str, base: dict | None = None, force: bool = False, save: bool = False,
              panels: str | None = None) -> dict:
    """One stage of the likeness fit: the stage's controls run on the model, the checklist measured before and after.
    Controls: humanfit.solve on the stage's solver measures (front view), fit_outline (widths), fit_hood (eyes), and
    1-D lever fits (LEVERS: shape.hollow / planes / jaw_angle / under_eye, features.brow_ridge, pose.smile, nudges of
    eye corners and nose tip) on the items' own misses. Every result is integrity-guarded (refused if it breaks the
    mesh) and PINNED to the earlier stages' checklist items, re-measured: a step that makes one worse (> 0.5 x tol, past
    tol) is not taken (a solve is retried with half its asks first). save=True stores the result (and the cameras)."""
    from . import humanfit, store
    sp = store.load(name)
    base = base or sp["base"]
    refs = _refs(name)
    st = _stage(stage)
    photos = _photos(refs)
    start = compare(name, base, photos=photos)
    start["_base"] = base
    order = [s["name"] for s in stage_names()]
    k = order.index(stage)
    rep = {"stage": stage, "control": st["control"], "steps": [], "log": []}
    cur, cur_cmp = base, start
    biased = expression_bias(start["pictures"])
    rep["expression"] = {i: v for i, v in biased.items() if _item(i)["stage"] == stage}
    want, pins, gaps = stage_wants(start, stage, skip=biased)
    rep["want"], rep["pins"] = want, pins
    if stage == "widths":
        nb, r = humanfit.fit_outline(cur, refs["views"], [m["cam"] for m in start["models"]], force=force)
        c = compare(name, nb, photos=photos)
        und = _undone(start, c, k)
        rep["steps"].append(("fit_outline", r))
        if und and not force:
            rep["log"].append(f"  fit_outline not taken: undoes {[u[1]['id'] for u in und]}")
        elif not r.get("refused"):
            cur, cur_cmp = nb, c
    if want:
        for frac in (1.0, 0.5):
            ask = {m: f"{float(v) * frac:+.2f}" for m, v in want.items()}
            nb, r = humanfit.solve(cur, {**pins, **ask}, force=force)
            if r.get("refused"):
                rep["steps"].append((f"solve {ask}", r))
                break
            c = compare(name, nb, photos=photos)
            und = _undone(start, c, k)
            rep["steps"].append((f"solve {ask}" + (f" (pinned {sorted(pins)})" if pins else ""), r))
            if not und or force:
                cur, cur_cmp = nb, c
                break
            rep["log"].append(f"  solve x{frac}: undoes {[u[1]['id'] for u in und]}" + ("; retry at half" if frac == 1.0 else "; not taken"))
    if stage == "eyes" and "eye_opening" not in biased:
        nb, r = humanfit.fit_hood(cur, _views_with(refs, list(humanfit.HOOD_LIDS)), [m["cam"] for m in cur_cmp["models"]], force=force)
        c = compare(name, nb, photos=photos)
        if not _undone(start, c, k) and not r.get("refused"):
            cur, cur_cmp = nb, c
        rep["steps"].append(("fit_hood", r))
    part = {"nose": "nose", "chin_jaw": "chin", "structure": "cheek"}.get(stage)
    if part and _profile_score(cur_cmp, part) is not None:
        cur, cur_cmp, plog = fit_profile(name, cur, parts=(part,), force=force, start=start, k=k, photos=photos)
        rep["log"] += plog
        rep["steps"].append((f"profile contour ({part})", {}))
    done = set()
    for it in checklist():
        lv_of = lambda i: EXPR_LEVERS[i] if (i in biased and i in EXPR_LEVERS) else LEVERS.get(i)  # noqa: E731
        if it["stage"] != stage or lv_of(it["id"]) is None or it["id"] in done:
            continue
        lever = lv_of(it["id"])
        ids = [i for i in list(LEVERS) + list(EXPR_LEVERS) if lv_of(i) and lv_of(i)[0] == lever[0] and _item(i)["stage"] == stage]
        ids = list(dict.fromkeys(ids))
        # a contour reading (mm, geometry) drives the lever alone where there is one: mixed with the shading's % the
        # mean miss means nothing
        cids = [i for i in ids if _item(i)["measure"]["kind"] == "contour"
                and any(r["id"] == i and r["score"] >= 0 for r in cur_cmp["rows"])]
        ids = cids or [i for i in ids if _item(i)["measure"]["kind"] != "contour"]
        if not ids:
            continue
        done.update(ids)
        rep["log"].append(f"  lever {lever[0]} for {ids}:")
        cur_cmp["_base"] = cur
        cur, cur_cmp, note = _lever_fit(name, cur, photos, start, cur_cmp, k, ids, lever, force, rep["log"])
        rep["steps"].append((f"lever {note}", {}))
    gaps = []
    for r in cur_cmp["rows"]:
        it = _item(r["id"])
        if it["stage"] == stage and r["score"] > 1.0 and not it.get("solve") and r["id"] not in LEVERS \
                and not any(w in it["control"] for w in ("fit_outline", "fit_hood")):
            gaps.append(f"{it['name']} [{r['view']}] ({r['miss']:+.2f} {it['unit']}): {it['control']}")
    rep["gaps"] = gaps
    if not rep["steps"]:
        rep["gap"] = f"nothing wired for {stage}" + (": judge the panels" if gaps else "")
    after = cur_cmp
    rep["refused"] = [f"{n}: {r['refused']}" for n, r in rep["steps"] if isinstance(r, dict) and r.get("refused")]
    rep["integrity"] = humanfit.verdict(humanfit.integrity(cur, None, humanfit.state(base))) if cur is not base else "unchanged"
    bmap = {(r["id"], r["vi"]): r for r in start["rows"]}
    rep["rows"] = [(bmap[(r["id"], r["vi"])], r) for r in after["rows"]
                   if (r["id"], r["vi"]) in bmap and order.index(r["stage"]) == k]
    rep["undone"] = _undone(start, after, k)
    rep["text"] = stage_text(rep)
    rep["base"], rep["after"] = cur, after
    if panels:
        focus_sheet(after, panels, top=14, rows=[r for _, r in rep["rows"]])
        rep["panels"] = panels
    if save and cur is not base:
        v = store.save(name, {**sp, "base": cur}, f"likeness stage {stage}")
        refs2 = {**refs, "cameras": [m["cam"] for m in after["models"]]}
        (store.HOME / name / "human_refs.json").write_text(json.dumps(refs2, indent=1))
        rep["saved"] = v
        rep["text"] += f"\nsaved {name} v{v}"
    return rep


PROFILE_PARTS = {   # part -> (region group(s), contour, heights it reads (levels, mm either side), landmarks held)
    "nose": ("nose_region", "nose", None, None),
    "chin": (["chin_region", "lower_lip_region"], "outer", ("sto", 6.0, "chin", 9.0),
             [i for i in range(17, 68) if i not in (55, 56, 57, 58, 59, 65, 66, 67)]),
    # the cheek's fullness at the mouth's height (the far cheek's line in a turned view), the front outline held
    "cheek": (["left_cheek_region", "right_cheek_region"], "outer", ("sn", 2.0, "sto", 10.0), list(range(17, 68))),
}
PROFILE_ITEMS = {"cheek": ["prof_cheek_line"], "nose": ["prof_nose_tip", "prof_nose_gap", "prof_nose_length", "prof_bridge_bow"],
                 "chin": ["prof_chin", "prof_chin_height", "prof_mentolabial"]}
PROFILE_ROUNDS = 5
PROFILE_DONE = 1.5    # mm rms of the contour's miss at its vertices: done


PROFILE_FRONT = {"nose": list(range(27, 36)), "chin": [7, 8, 9, 56, 57, 58]}


PROFILE_HOLD_N = 60     # region vertices held in the front picture's plane
PROFILE_HOLD_W = 3      # ... each counted this many times against a contour vertex
PROFILE_GAIN = 0.7      # share of the contour's miss asked a round (to the contour, not past it)
PROFILE_SIGMA = 1.6     # a round that takes the region's components past this is not taken (plausibility)


def _front_holds(cmp, part) -> list:
    """The part's skin held where a FRONT picture has it (fit_region targets at their own projection): a turned view's
    contour says how far things stand along the front camera's line of sight; heights and widths are the front
    picture's. Landmarks alone (round 1) left the subnasale free to slide 3 mm down (philtrum, lower third): now
    PROFILE_HOLD_N vertices spread over the region, so what is left to the solve is depth."""
    from . import humanfit
    from . import likeness_profile as lp
    out = []
    for vi, (ph, md) in enumerate(zip(cmp["photos"], cmp["models"])):
        if ph["kind"] != "front":
            continue
        V, L = md["mesh"]["V"], md["mesh"]["L"]
        if part == "nose":
            ids = lp.nose_ids(V, L)
        elif part == "cheek":   # both cheeks, between the mouth's corner and the jaw's side
            cs = [0.5 * (L[48] + L[4]), 0.5 * (L[54] + L[12])]
            ids = np.nonzero(np.min([np.linalg.norm(V - c, axis=1) for c in cs], axis=0) < 0.03)[0]
        else:
            c = 0.5 * (L[8] + L[57])
            ids = np.nonzero(np.linalg.norm(V - c, axis=1) < 0.032)[0]
        if len(ids) > PROFILE_HOLD_N:
            ids = ids[np.linspace(0, len(ids) - 1, PROFILE_HOLD_N).astype(int)]
        uv = humanfit.project(md["cam"], V[ids])
        out += [{"view": vi, "tpl": [int(a)] * 3, "bary": [1.0, 0.0, 0.0], "uv": [float(u[0]), float(u[1])], "hold": True}
                for a, u in zip(ids, uv)] * PROFILE_HOLD_W
    return out


def _rms(tg) -> float:
    return float(np.sqrt(np.mean([t["raw_mm"] ** 2 for t in tg]))) if tg else 1e9


def _profile_targets(cmp, traces, part) -> list:
    from . import likeness_profile as lp
    group, contour, rng, hold = PROFILE_PARTS[part]
    tg = []
    for vi, (ph, md) in enumerate(zip(cmp["photos"], cmp["models"])):
        rd = profile_read(ph, md, traces)
        if rd is None:
            continue
        vr = None
        if rng:
            lv = rd["model_levels"]
            vr = (lv[rng[0]] + rng[1], lv[rng[2]] + rng[3])
        tg += lp.targets(rd, md["mesh"], md["cam"], vi, contour, v_range=vr, gain=PROFILE_GAIN)
    return tg


def _profile_score(cmp, part):
    v = [r["score"] for r in cmp["rows"] if r["id"] in PROFILE_ITEMS[part] and r["score"] >= 0]
    return float(np.sum(np.square(v))) if v else None


def fit_profile(name: str, base: dict | None = None, parts=("nose", "chin"), force: bool = False, save: bool = False,
                start: dict | None = None, k: int | None = None, photos=None) -> tuple:
    """(base, cmp, log): the nose and the chin fitted to a turned view's contours. Each round: the contour's miss at
    the model vertices that MAKE its contour (likeness_profile.targets, the camera's offset on the bony upper face
    taken out) -> humanfit.fit_region (GNM identity components inside the nose / chin + lower lip region, the other
    landmarks held, integrity-guarded). A round is kept only if the part's contour items score better and (in a staged
    fit: start, k) no earlier stage's pinned item is undone."""
    from . import humanfit, store
    from . import likeness_profile as lp
    from . import likeness_shape as ls
    sp = store.load(name)
    base = base or sp["base"]
    photos = photos or _photos(_refs(name))
    cur = base
    cmp = compare(name, cur, photos=photos)
    cmp_first = cmp
    cams0 = [m["cam"] for m in cmp["models"]]   # ONE camera per picture through the whole fit: refitted per candidate
    # (as compare does for turned views) the camera follows the nose it is meant to judge
    traces = ls.load_points(name)
    log = []
    for part in parts:
        group, contour, rng, hold = PROFILE_PARTS[part]
        for rnd in range(PROFILE_ROUNDS):
            s0 = _profile_score(cmp, part)
            if s0 is None:
                log.append(f"  {part}: no contour on the references (likeness_points 'profile'" + (" / 'nose'" if part == "nose" else "") + ")")
                break
            tg = _profile_targets(cmp, traces, part)
            if len(tg) < 4:
                log.append(f"  {part}: {len(tg)} contour vertices: too few")
                break
            miss = _rms(tg)
            if miss < PROFILE_DONE:
                log.append(f"  {part}: contour within {miss:.1f} mm rms")
                break
            nb, r = humanfit.fit_region(cur, cams0, tg + _front_holds(cmp, part), group, hold=hold, force=force,
                                        name=f"likeness_{part}")
            if r.get("refused"):
                log.append(f"  {part} round {rnd + 1}: REFUSED ({r['refused'][:90]})")
                break
            c = compare(name, nb, photos=photos, cameras=cams0)
            s1 = _profile_score(c, part)
            tg1 = _profile_targets(c, traces, part)
            miss1 = _rms(tg1)
            # pins: every FRONT-view item (any stage) when run alone; the earlier stages' in a staged fit
            und = _undone(start, c, k) if start is not None else _undone(cmp_first, c, 99)
            if float(r.get("largest_sigma") or 0) > PROFILE_SIGMA and not force:
                log.append(f"  {part} round {rnd + 1}: not taken (components at {r.get('largest_sigma')} sigma, limit {PROFILE_SIGMA})")
                break
            note = (f"{len(tg)} contour vertices, contour rms {miss:.1f} -> {miss1:.1f} mm, share {r.get('share')}, largest "
                    f"{r.get('largest_sigma')} sigma; items' score {s0:.1f} -> {s1 if s1 is None else round(s1, 1)}")
            # judged on the contour itself (the items are a few numbers read off it: one of them worse while the line
            # as a whole comes closer stopped the first runs after one round, the bridge left scooped)
            if (miss1 > 0.97 * miss or und) and not force:
                log.append(f"  {part} round {rnd + 1}: not taken ({note}" + (f"; undoes {[u[1]['id'] for u in und]}" if und else "") + ")")
                break
            log.append(f"  {part} round {rnd + 1}: fit_region {group} ({note})")
            cur, cmp = nb, c
    if save and cur is not base:
        v = store.save(name, {**sp, "base": cur}, "likeness profile contour fit")
        log.append(f"saved {name} v{v}")
    return cur, cmp, log


def stage_text(rep: dict) -> str:
    lines = [f"stage {rep['stage']} ({rep['control']}): {rep['integrity']}"]
    for n, r in rep["steps"]:
        extra = ""
        if isinstance(r, dict):
            if r.get("views"):
                extra = "; ".join(f"rms {v.get('rms_mm')} mm" for v in r["views"])
            if "amount" in r or "asked_mm" in r:
                extra = f"hood {r.get('amount_before')} -> {r.get('amount', r.get('asked_mm'))} mm"
            if r.get("refused"):
                extra += "  REFUSED: " + r["refused"]
        lines.append(f"  {n}: {extra}".rstrip(": "))
    for i, v in (rep.get("expression") or {}).items():
        lines.append(f"  EXPRESSION on the reference ({v}): {_item(i)['name']} is fitted through the pose, not the identity")
    lines += rep.get("log") or []
    if rep.get("gap"):
        lines.append("  GAP: " + rep["gap"])
    for g in rep.get("gaps") or []:
        lines.append("  GAP (no control): " + g)
    lines.append(f"  {'item':40} {'view':14} {'photo':>8} {'before':>8} {'after':>8} {'tol':>6}  x tol before -> after")
    for b, a in rep["rows"]:
        if a["score"] < 0:
            lines.append(f"  {a['name'][:40]:40} {a['view']:14}  (not measured: {(a.get('why') or 'judge by eye')[:80]})")
            continue
        sb = f"{b['score']:.1f}" if b["score"] >= 0 else "-"
        bm = b["model"] if b.get("kind") != "shape" else (-(b.get("miss") or 0.0) if b["score"] >= 0 else None)
        am = a["model"] if a.get("kind") != "shape" else -a["miss"]
        lines.append(f"  {a['name'][:40]:40} {a['view'] + ('~' if a.get('inferred') else ''):14} {_fmt(a['photo'], a['unit']):>8} "
                     f"{_fmt(bm, a['unit']):>8} {_fmt(am, a['unit']):>8} {a['tol']:>6.3g}  {sb} -> {a['score']:.1f}"
                     + ("  ok" if a["score"] <= 1 else "")
                     + (f"  3D {b.get('model3d')} -> {a.get('model3d')} mm" if a.get("kind") == "shape" else ""))
    if rep["undone"]:
        lines.append("  EARLIER STAGES MADE WORSE (review before going on):")
        for b, a in rep["undone"]:
            lines.append(f"    {a['name']} [{a['view']}] ({a['stage']}): {b['score']:.1f} -> {a['score']:.1f} x tol")
    return "\n".join(lines)


def fit_likeness(name: str, stages: list | None = None, force: bool = False, save: bool = True, panels_dir: str | None = None) -> list:
    """Run stages in order (all of them by default), each saved before the next. For a person or an LLM approving
    stage by stage, call with one stage at a time and look at its panels."""
    from . import store
    out = []
    names = stages or [s["name"] for s in stage_names()]
    for s in names:
        pn = str(Path(panels_dir or (store.HOME / "human_renders")) / f"lk_{name}_stage_{s}.png")
        out.append(fit_stage(name, s, force=force, save=save, panels=pn))
    return out
