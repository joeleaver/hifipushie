"""Plan, reference and concept tools: the 2D blockout plan, reference silhouettes, compare and fit against them,
clearance and style checks, and views matched to a concept picture's camera."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from . import compare as cmp
from . import fit as fitmod
from . import measure as meas
from . import plan as planmod
from . import store
from .spec import empty_spec
from .mcp_app import mcp
from .tool_common import _out, _parts_note, _png, _sil_parts, _silhouettes, _spec_arg

def _refs(name: str, views: list[str] | None, against: str = "auto") -> dict:
    """Reference silhouettes by view: {view: (mask, world placement or None)}. against="plan" uses the model's
    plan (placed exactly in world units), "refs" the images from set_reference, "auto" the plan if there is one."""
    plan = store.load(name).get("plan")
    if against == "plan" or (against == "auto" and plan and plan.get("views")):
        if not plan:
            raise ValueError("this model has no plan; use set_plan first")
        views = views or [v for v in ("front", "side", "top") if planmod.bounds(plan, v) is not None]
        return {v: planmod.reference(plan, v) for v in views}
    if against not in ("auto", "refs"):
        raise ValueError('against must be "auto", "plan" or "refs"')
    cfg_p = store.refs_dir(name) / "refs.json"
    cfg = json.loads(cfg_p.read_text()) if cfg_p.exists() else {}
    views = views or list(cfg)
    if not views:
        raise ValueError("no references set; use set_reference first")
    for v in views:
        if v not in cfg:
            raise ValueError(f"no reference for view {v!r}")
    return {v: (cmp.reference_mask(cfg[v]["path"], cfg[v]["flip"], cfg[v]["threshold"]), None) for v in views}


@mcp.tool(structured_output=False)
def fit_matched(name: str, targets: list[dict], only: list[str], params: list[str] | None = None,
                lock: list[str] | None = None, press: dict | None = None, iterations: int = 20,
                max_step: float = 0.01, stiffness: float = 0.05, resolution: int = 128):
    """Fit elements' numbers (only: element names; params "pos"|"r"|"offset"|"size"|"shape") to pictures from
    fitted cameras (fit_concept_camera) and save a new version. targets: [{"camera": label, "box": [x0,y0,x1,y1],
    "elements"?: [names] = that part's own outline, seen in front of the rest, "outline"?: [[x,y],...] (or a list
    of them) traced in the image, or "mask"?: white-on-black PNG; neither = the camera's image foreground}].
    press: {"elements": [...], "mm": 3, "join": [x,y,z]}: those may sink into the rest only where they join on.
    Returns red / blue diffs per target and the changes. Details: guide(topic="fit_matched")."""
    from PIL import Image as PI
    from . import fit_view, matched
    tg = []
    for i, t in enumerate(targets):
        cam = matched.load_camera(name, t.get("camera", "concept"))
        if t.get("outline"):
            mask = fit_view.polygon_mask(cam["size"], t["outline"])
        elif t.get("mask"):
            mask = np.asarray(PI.open(t["mask"]).convert("L").resize(tuple(cam["size"]))) > 127
        elif not t.get("elements"):
            mask = matched.mask_of(cam["image"], cam.get("mask"))
        else:
            raise ValueError(f"target {i}: a part's outline needs outline= or mask= (traced in the image)")
        lab = t.get("label") or f"{t.get('camera', 'concept')}{'/' + '+'.join(t['elements']) if t.get('elements') else ''}#{i}"
        tg.append({"label": lab, "camera": cam, "mask": mask, "box": t.get("box"), "elements": t.get("elements")})
    spec = store.load(name)
    res = fit_view.fit(spec, tg, tuple(params or fitmod.GROUPS), only, tuple(lock or ()), press, iterations,
                       max_step, stiffness, resolution)
    ver = store.save(name, res.spec, "fit_matched " + " ".join(
        f"{k} {res.before[k]:.3f}->{res.after[k]:.3f}" for k in res.after))
    out = []
    for t in tg:
        out += [_png(PI.fromarray(res.diff(t["label"])).resize(
            tuple(int(2 * x) for x in res.diff(t["label"]).shape[1::-1]))),
            f"[{t['label']}] IoU {res.before[t['label']]:.3f} -> {res.after[t['label']]:.3f} (red = model only, "
            "blue = picture only)"]
    out.append(f"saved {name} v{ver}\n" + "\n".join(res.log) + "\n\nchanges:\n" + "\n".join(res.changes or ["(none)"]))
    return out


@mcp.tool(structured_output=False)
def fit_concept_camera(name: str, image: str, mask: str | None = None, label: str = "concept",
                       az: float | None = None, el: float | None = None, resolution: int = 96):
    """Fit the perspective camera a concept image was drawn from, by the model's silhouette against the image's
    foreground (IoU; mask: a white-on-black PNG when the background isn't plain). Saved under `label`; then
    look_matched renders from it pixel-aligned, feature_tiles cuts review tiles, look(camera={"fitted": label})
    uses it too. az / el: a starting guess (default: a sweep). Returns the overlay (red = model only, blue = image
    only) and the camera. Details: guide(topic="fit_concept_camera")."""
    from . import matched
    cam = matched.fit_camera(name, image, mask, label, resolution, az, el)
    note = "" if cam["iou"] >= 0.85 else (" | LOW IoU: the model is far from the concept's shape, or the mask is wrong "
                                          "(pass mask=...; az / el = a guess)")
    if cam.get("mirror"):
        note += (f" | MIRROR: az {cam['mirror']['az']:+.0f} fits nearly as well (IoU {cam['mirror']['iou']:.3f}; a "
                 "symmetric silhouette can't tell the sides apart): check which way the face turns in look_matched, "
                 "and if it's the wrong way fit again with az of the other sign")
    return [_out(matched.overlay(name, cam, resolution), None),
            f"{name}: camera {label!r} az {cam['az']:+.1f} el {cam['el']:+.1f} roll {cam['roll']:+.1f} "
            f"f {cam['f_px']:.0f} px, IoU {cam['iou']:.3f}{note} | saved {matched.cam_path(name, label)} | next: "
            f"look_beside(name) now shows the model from this angle too (view \"painting\": the picture with the model's "
            f"outline over it, and what differs), in seconds, after every change; look_matched(name, label={label!r}) is "
            "the slow full render, feature_tiles cuts review tiles"]


@mcp.tool(structured_output=False)
def look_matched(name: str, label: str = "concept", resolution: int = 192, samples: int = 32,
                 only_parts: list[str] | None = None, hide_parts: list[str] | None = None, save: str | None = None):
    """Render the model from a fitted concept camera (fit_concept_camera) at the image's own size, in form-revealing
    clay (soft area light, no hard shadows), pixel-aligned with the concept: returns concept | render. The THE
    standard view for comparing a character sculpt with its concept; review it by feature_tiles + review_view, never
    by eye from a camera you picked. Details: guide(topic="look_matched")."""
    from . import matched
    import time
    t = time.time()
    path = matched.render(name, label, resolution, samples, only_parts=only_parts, hide_parts=hide_parts)
    im = matched.pair(name, label)
    return [_out(im, save), f"{name}: matched render {label!r} in {time.time() - t:.0f}s -> {path} | next: "
            "feature_tiles(name, {region: [parts or elements]}) and review_view on each pair"
            + (f" | saved {save}" if save else "")]


@mcp.tool(structured_output=False)
def feature_tiles(name: str, features: dict, label: str = "concept", out_dir: str | None = None,
                  min_px: int = 448, pad: float = 0.2) -> str:
    """Cut named, same-box feature tiles from the concept and its matched render (look_matched first), one pair per
    region, for the blind review: features {region: [element or part names] | [x0, y0, x1, y1] pixels}, e.g.
    {"left ear": ["ear.L", "earroot.L"], "tail": ["tailb0", "tailb3"]}. Region names are what the reviewer reads:
    plain words, no numbers. Returns the tiles and a review_view call per region. Details: guide(topic="feature_tiles")."""
    from . import matched
    r = matched.tiles(name, features, label, out_dir, min_px, pad)
    rows = [f"{k}: box {v[2]} -> {v[0]} | {v[1]}" for k, v in r["tiles"].items()]
    return "\n".join([f"{len(rows)} tile pairs in {r['dir']}", *rows,
                       "next: the blind review, ONE region per call (fill in the context; fix the worst MAJOR, then "
                       "look_matched and these tiles again):", *r["review"]])


@mcp.tool(structured_output=False)
def join_report(name: str, parts: list[str], side: str = "L", sections: bool = False):
    """How each part joins the body, measured: the seam where its skin meets the rest, over the width of its base
    (about 1 = joined along its base; about 0.5 = a stalk or neck; WARNING under 0.75). parts: element or part
    names, a base name takes `side` ("ear" -> ear.L). sections=True adds two flat cuts through each join (the rest
    grey, the part red, 1 cm grid, up = out of the body). put_model / edit_model(joins=[...]) report the same lines
    on every save. Details: guide(topic="join_report")."""
    from . import joins as joinsmod
    lines, images = [], []
    for p in parts:
        r = joinsmod.measure(name, p, side, sections)
        im = r.pop("image", None)
        lines.append(joinsmod.line(r))
        if im is not None:
            images.append(_png(im))
    return [*images, "\n".join(lines)]


@mcp.tool(structured_output=False)
def clearance(name: str, region: list[list[float]] | None = None, path: list[list[float]] | None = None,
              floor: float | None = None, height: float = 1.8, radius: float = 0.25, step: float = 0.2,
              spacing: float | None = None) -> str:
    """Can a person walk here? From the exact field: region [[x0,y0],[x1,y1]] gives a top-view walkability map; path
    [[x,y],...] gives floor, headroom and clear width along it with a verdict. floor, height, radius, step, spacing.
    Details: guide(topic="clearance")."""
    return meas.clearance(store.load(name), region, path, floor, height, radius, step, spacing)


@mcp.tool(structured_output=False)
def set_reference(name: str, view: str, image_path: str, flip: bool = False, threshold: float = 40.0):
    """Attach a reference image for view "front"|"side"|"top" (silhouette from alpha, else from the corner colour by
    threshold; flip=True if a side reference faces right). Returns the extracted mask. Details:
    guide(topic="set_reference")."""
    if view not in ("front", "side", "top"):
        raise ValueError("view must be front, side or top")
    d = store.refs_dir(name)
    src = Path(image_path).expanduser()
    dst = d / f"{view}{src.suffix.lower()}"
    shutil.copy(src, dst)
    cfg_p = d / "refs.json"
    cfg = json.loads(cfg_p.read_text()) if cfg_p.exists() else {}
    cfg[view] = {"path": str(dst), "flip": flip, "threshold": threshold}
    cfg_p.write_text(json.dumps(cfg, indent=1))
    mask = cmp.reference_mask(str(dst), flip, threshold)
    im = PILImage.fromarray((mask * 255).astype("uint8"))
    im.thumbnail((384, 384))
    return [_png(im), f"reference {view} set ({mask.shape[1]}x{mask.shape[0]}, {mask.mean():.1%} foreground)"]


@mcp.tool(structured_output=False)
def compare(name: str, views: list[str] | None = None, fit: str = "auto", resolution: int = 160,
            against: str = "auto", only_parts: list[str] | None = None, hide_parts: list[str] | None = None):
    """Compare model silhouettes to references (set_reference images or the plan): IoU, diff image and edge-error band
    tables per view. fit "auto"|"height"|"width" (scale search), against "auto"|"refs"|"plan", only_parts /
    hide_parts. Details: guide(topic="compare")."""
    spec = store.load(name)
    parts = _sil_parts(spec, only_parts, hide_parts)
    sils = _silhouettes(name, spec, resolution, parts)
    out = []
    for v, (ref, world) in _refs(name, views, against).items():
        iou, diff, report = cmp.compare(sils[v], ref, fit, world=world)
        out += [_png(diff), f"[{v}] {_parts_note(parts)}{report}"]
    return out


@mcp.tool(structured_output=False)
def fit(name: str, views: list[str] | None = None, only: list[str] | None = None,
        lock: list[str] | None = None, params: list[str] | None = None, iterations: int = 20,
        max_step: float = 0.02, stiffness: float = 0.05, align: str = "auto", resolution: int = 160,
        against: str = "auto", only_parts: list[str] | None = None, hide_parts: list[str] | None = None,
        init_loft: str | None = None):
    """Auto-fit joints, radii and blobs (params "pos"|"r"|"offset"|"size"|"shape") to the reference or plan
    silhouettes and save as a new version. only / lock (element names), max_step, stiffness, iterations, against,
    only_parts / hide_parts; init_loft: a loft blob whose sections are first measured off the front / side
    outlines. Block out by hand first; revert undoes. Details: guide(topic="fit")."""
    refs = _refs(name, views, against)
    spec = store.load(name)
    init_lines = []
    if init_loft:
        spec, init_lines = fitmod.loft_from_refs(spec, refs, init_loft, align, resolution,
                                                 _sil_parts(spec, only_parts, hide_parts))
        init_lines = [f"{init_loft} sections from the outlines:"] + init_lines + [""]
    pin = []
    if any(w is not None for _, w in refs.values()):  # fitting to the plan: its landmarks fix joint heights
        pin = [("joints", lm["joint"], "pos", 2) for lm in (spec["plan"].get("landmarks") or {}).values()
               if lm.get("joint") in spec["joints"]]
    parts = _sil_parts(spec, only_parts, hide_parts)
    res = fitmod.fit(spec, refs, align, tuple(params or fitmod.GROUPS), only, tuple(lock or ()),
                     iterations, max_step, stiffness, resolution, pin, parts)
    ver = store.save(name, res.spec, "fit " + " ".join(
        f"{v} {res.iou_before[v]:.3f}->{res.iou_after[v]:.3f}" for v in refs))
    out = []
    for v, im in fitmod.diff_images(res).items():
        out += [_png(im), f"[{v}] IoU {res.iou_before[v]:.3f} -> {res.iou_after[v]:.3f}"]
    out.append(f"saved {name} v{ver}\n" + _parts_note(parts) + "\n".join(init_lines + res.log) + "\n\nchanges:\n" + "\n".join(res.changes or ["(none)"]))
    return out


@mcp.tool(structured_output=False)
def set_plan(name: str, plan: dict, note: str = "", save: str | None = None):
    """Set or replace a model's plan (the 2D blockout: per-view shapes in world units, landmarks, sections); creates
    the model if needed and returns the plan drawn with rulers. plan = {"views": {view: {"shapes"}}, "landmarks",
    "sections"}; save writes the sheet. Details: guide(topic="set_plan")."""
    plan = _spec_arg(plan)
    planmod.validate(plan)
    try:
        spec = store.load(name)
    except ValueError:
        spec = empty_spec()
    spec = {**spec, "plan": plan}
    v = store.save(name, spec, note or "set_plan")
    views = [x for x in ("front", "side", "top") if planmod.bounds(plan, x) is not None]
    return [_out(planmod.sheet(plan, views), save), f"saved {name} v{v} with a plan ({', '.join(views)})"]


@mcp.tool(structured_output=False)
def style_check(name: str, colours: bool = True, save: str | None = None) -> str:
    """Measure a model against its style sheet's rules (spec.style.sheet): face ratios, eye opening and, with
    colours=True, skin colour lit vs shadow from a render (save keeps it). PASS/FAIL per rule. Details:
    guide(topic="style_check")."""
    from . import stylesheet
    from . import scene_sync
    rows = stylesheet.check(name)
    if colours:
        scene_sync.sync(name)
        rows += stylesheet.colour_check(name, save=save)
    lines = []
    for r in rows:
        if "samples" in r:
            lines.append("samples: " + "; ".join(f"{k} {v['hex']} hsv {v['hsv']}" for k, v in r["samples"].items()))
        else:
            lines.append(f"{'PASS' if r['ok'] else 'FAIL'} {r['rule']} = {r['value']} (target {r['target']}): {r['why']}")
    return "\n".join(lines)
