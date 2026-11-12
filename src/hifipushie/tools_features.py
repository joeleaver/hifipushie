"""The feature-map tools: read a reference picture, mark its features, measure a model feature by feature.
refread.py, featuremap.py and featuresee.py hold the work (their docstrings are the spec); guide(topic="features")
is the sculptor's page."""
from __future__ import annotations

from .mcp_app import mcp
from .tool_common import _out


@mcp.tool(structured_output=False)
def read_reference(name: str, image: str | None = None, views: list[str] | None = None, height: float | None = None,
                   mask: str | None = None, boxes: dict | None = None, detail: str = "medium",
                   view: str | None = None, focus: list[float] | None = None, save: str | None = None):
    """Read a reference picture for a sculpt: cut the sheet into its views, give each a camera, and show what it
    holds inside its outline: numbered colour patches to point at, and its form lines. First call: image, views
    (one name per figure, left to right: "front", "side" (faces picture-left), "side_r", "back"; any other name is
    a perspective picture), height (m, feet to top of the first such view). Later calls: view (+ focus [x0, y0,
    x1, y1] in its pixels) to look closer; detail coarse / medium / fine re-cuts the patches. Then mark_features.
    Details: guide(topic="read_reference"); the page: guide(topic="features")."""
    from . import featuremap, refread
    if image:
        if not views:
            raise ValueError('views: one name per figure in the picture, left to right, e.g. ["front", "side", "back"]')
        recs = refread.read(name, image, views, height, mask, boxes, detail)
        fm = featuremap.add_views(name, recs)
        lines = [f"{name}: read {len(recs)} view(s) from {image}"]
        for v, r in recs.items():
            cam = (f"camera saved ({r['m_per_px'] * 1000:.2f} mm per px, top at {r['top_m']:.3f} m, centre line at "
                   f"px {r['centre_px']:.0f}, ground at px {r['ground_px']})" if r.get("m_per_px")
                   else f"in perspective: no camera until fit_concept_camera(name, {r['image']!r}, label={v!r})")
            lines.append(f"  {v}: {r['size'][0]} x {r['size'][1]} px, {r['patches']} patches, {cam}")
        lines.append('In a "front" view the creature\'s LEFT (.L) is at the picture\'s RIGHT; "side" shows its LEFT side, '
                     '"side_r" its right. Marks are written in each view\'s own pixels (the rulers). CHECK each cut-out '
                     "below is the whole figure (a part the colour of the background can be lost: pass mask=). "
                     "Next: read_reference(name, view=...) per view, then mark_features.")
        view = view or views[0]
    else:
        fm = featuremap.load(name)
        if not fm["views"]:
            raise ValueError(f"{name} has no reference views yet: pass image= and views=")
        view = view or next(iter(fm["views"]))
        if view not in fm["views"]:
            raise ValueError(f"no view {view!r} (have {sorted(fm['views'])})")
        rec = fm["views"][view]
        if detail != rec.get("detail", "medium"):
            import numpy as np
            from PIL import Image as PI
            a = np.asarray(PI.open(rec["image"]).convert("RGBA"))
            lab = refread.segment(a[..., :3], a[..., 3] > 127, detail)
            np.save(refread.folder(name) / f"{view}_patches.npy", lab.astype(np.uint16))
            rec["detail"], rec["patches"] = detail, int(lab.max())
            featuremap.save(name, fm)
        lines = [f"{name} {view}: {rec['size'][0]} x {rec['size'][1]} px, {rec['patches']} patches at detail "
                 f"{rec['detail']} (marks already made keep their own masks)"]
    rec = fm["views"][view]
    rows = refread.patch_table(name, view, rec, focus)
    rows.sort(key=lambda r: -r["area_px"])
    lines.append(f"{view}: patches" + (f" in focus {focus}" if focus else "") + " (id colour @px (x, y) size px"
                 + (" | middle in metres (across, up)" if rec.get("m_per_px") else "") + "), biggest first:")
    for r in rows[:60]:
        lines.append(f"  {r['id']} {r['colour']} @({r['px'][0]}, {r['px'][1]}) {r['w_px']}x{r['h_px']}"
                     + (f" | ({r['at_m'][0]:+.3f}, {r['at_m'][1]:.3f})" if "at_m" in r else ""))
    if len(rows) > 60:
        lines.append(f"  ... and {len(rows) - 60} smaller: pass focus= to list a region's")
    return [_out(refread.draw(name, view, rec, focus), save), "\n".join(lines)]


@mcp.tool(structured_output=False)
def mark_features(name: str, features: dict | None = None, remove: list[str] | None = None, notes: str | None = None,
                  view: str | None = None, focus: list[float] | None = None, save: str | None = None):
    """Name what a reference shows, as marks on its pictures: the feature map a sculpt is built from and measured
    against. features: {name: {"kind": "mass" | "form" | "paint", "on": feature, "join": words, "separate": bool,
    "authority": view, "inferred": words, "marks": {view: {"patches": [ids] | "box" | "ellipse" | "polygon" |
    "line" (view px), "minus": {...}, "mirror": bool} | null}}}. A call adds to the map (marks are replaced per
    view named; null clears one). Returns the map on every view (or one `view`, with rulers and focus), each
    feature's place and size, and what the map still owes. Details: guide(topic="mark_features"); the page: guide(topic="features")."""
    from . import featuremap
    fm = featuremap.mark(name, features or {}, remove, notes) if (features or remove or notes is not None) \
        else featuremap.load(name)
    if not fm["views"]:
        raise ValueError(f"{name} has no reference views yet: read_reference first")
    owes = featuremap.checks(name, fm)
    kinds = [c["kind"] for c in fm["features"].values()]
    text = [f"{name}: {len(kinds)} features ({kinds.count('mass')} masses, {kinds.count('form')} forms, "
            f"{kinds.count('paint')} paint) over views {sorted(fm['views'])}", featuremap.table(fm),
            (f"STILL OWED ({len(owes)}):\n  " + "\n  ".join(owes)) if owes else
            "Nothing owed: every patch belongs to a feature and the views agree."]
    if view and view not in fm["views"]:
        raise ValueError(f"no view {view!r} (have {sorted(fm['views'])})")
    return [_out(featuremap.draw(name, view, fm, focus) if view else featuremap.draw_all(name, fm), save), "\n".join(text)]


@mcp.tool(structured_output=False)
def feature_report(name: str, elements: dict | None = None, views: list[str] | None = None, view: str | None = None,
                   resolution: int = 144, save: str | None = None):
    """Measure a model against its feature map, feature by feature, from each reference view's camera: NOT MADE,
    HIDDEN, OFF (how far, how big, how much of the mark it covers) or right. elements: {feature: [the model's
    element names / patterns / "part:<part>"]} says what makes each feature (remembered). The whole outline is one
    row; the features inside it are the rest: a sculpt is not done on its outline. Returns the table and, for
    `view`, the picture with its marks beside the model with its footprints. Details: guide(topic="feature_report"); the page: guide(topic="features")."""
    from . import featuresee
    rep = featuresee.report(name, elements, views, resolution)
    by = rep["by_feature"]
    CANT = "CAN'T MEASURE"
    count = {s: sum(1 for v in by.values() if v == s)
             for s in ("right", "OFF", "HIDDEN", "NOT MADE", "IN ITS MASS", "CAN'T MEASURE")}
    lines = [f"{name}: {len(by)} features: {count['right']} right, {count['OFF']} off, {count['HIDDEN']} hidden, "
             f"{count['NOT MADE']} NOT MADE" + (f", {count['IN ITS MASS']} said to be in their mass (not measured)"
                                                if count["IN ITS MASS"] else "")
             + (f", {count[CANT]} could not be measured" if count[CANT] else "")]
    lines.append("whole outline against each picture (one row among many): "
                 + ", ".join(f"{v} {i:.0%}" for v, i in rep["outline"].items()))
    lines += [f"  MOVED {m}" for m in rep["moved_views"]]
    if rep["skipped_views"]:
        lines.append(f"  views with no camera yet (fit_concept_camera): {rep['skipped_views']}")
    not_made = sorted(f for f, s in by.items() if s == "NOT MADE")
    if not_made:
        lines.append("NOT MADE: " + ", ".join(not_made))
    for r in rep["rows"]:
        if r["status"] in ("OFF", "HIDDEN", "CAN'T MEASURE"):
            lines.append(f"  {r['status']} {r['feature']} ({r['view']}): {r['why']}")
    ok = [f"{r['feature']} ({r['view']}, {r.get("how") or "overlap %d%%" % round(100 * r["iou"])})"
          for r in rep["rows"] if r["status"] == "right"]
    if ok:
        lines.append("right: " + ", ".join(ok))
    view = view or next(iter(rep["cams"]), None)
    if view is None:
        return "\n".join(lines)
    return [_out(featuresee.draw(name, rep, view), save), "\n".join(lines)]


@mcp.tool(structured_output=False)
def build_masses(name: str, how: dict, symmetry: bool = True, view: str | None = None, save: str | None = None):
    """Turn masses of the feature map into shapes, their numbers read off the marks: no coordinate typed. how:
    {feature: {"as": "ball" (a rounded lump) | "drum" (a cylinder) | "flap" (a thin sheet) | "trunk" (an upright
    mass through cross-sections) | "tube" (a limb or horn along its axis, as bones), "round": 2 = round .. higher
    = squarer, "sections" / "joints", "along": "x" | "y" | "z", "part", "blend": m, "thick", "cup", "y" / "x"}}.
    Makes the model if there is none; a feature built again replaces what was built for it. Returns what was
    made, what had to be assumed, and the feature report with a picture. Details: guide(topic="build_masses"); the page: guide(topic="features")."""
    from . import featuremap, featuresee, masses
    res = masses.build(name, how, symmetry)
    lines = [f"saved {name} v{res['version']}: built {len(res['made'])} masses: "
             + ", ".join(f"{f} ({featuremap.load(name)['features'][f].get('as')})" for f in sorted(res["made"]))]
    lines += [f"  ASSUMED {n}" for n in res["notes"]]
    rep = featuresee.report(name)
    by = rep["by_feature"]
    lines.append("whole outline against each picture: " + ", ".join(f"{v} {i:.0%}" for v, i in rep["outline"].items()))
    lines += [f"  MOVED {m}" for m in rep["moved_views"]]
    fm = rep["map"]
    for st in ("NOT MADE", "OFF", "HIDDEN", "CAN'T MEASURE", "right"):
        fs = sorted(f for f, s in by.items() if s == st and fm["features"][f]["kind"] == "mass")
        if fs:
            lines.append(f"masses {st}: " + ", ".join(fs))
    for r in rep["rows"]:
        if r["status"] in ("OFF", "HIDDEN", "CAN'T MEASURE") and fm["features"][r["feature"]]["kind"] == "mass":
            lines.append(f"  {r['status']} {r['feature']} ({r['view']}): {r['why']}")
    forms = sum(1 for f, s in by.items() if fm["features"][f]["kind"] == "form" and s == "NOT MADE")
    lines.append(f"forms not made yet: {forms} (they are laid on the masses once the masses are right)")
    view = view or next(iter(rep["cams"]), None)
    if view is None:
        return "\n".join(lines)
    return [_out(featuresee.draw(name, rep, view), save), "\n".join(lines)]
