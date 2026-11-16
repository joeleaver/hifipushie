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
    """Read a reference picture of a character or a prop: cut the sheet into its views, give each a camera, and show what it
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
        if "notches" not in rec:  # a view read before notches were found
            import numpy as np
            from PIL import Image as PI
            rec["notches"] = refread.notches(np.asarray(PI.open(rec["image"]).convert("RGBA"))[..., 3] > 127)
            featuremap.save(name, fm)
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
    if rec.get("notches"):
        lines.append(f"{view}: notches (where the outline pinches in; a cut's ends) @px: "
                     + ", ".join(f"n{i} ({x:.0f}, {y:.0f})" for i, (x, y) in enumerate(rec["notches"], 1)))
    return [_out(refread.draw(name, view, rec, focus), save), "\n".join(lines)]


@mcp.tool(structured_output=False)
def mark_features(name: str, features: dict | None = None, remove: list[str] | None = None, notes: str | None = None,
                  view: str | None = None, focus: list[float] | None = None, save: str | None = None):
    """Name what a reference shows, as marks on its pictures: the feature map a model's parts are placed from and measured
    against. features: {name: {"kind": "mass" | "form" | "paint", "on": feature, "join": words, "separate": bool,
    "authority": view, "inferred": words, "marks": {view: {"piece": [x, y] + "cuts" (cut off the figure's own
    outline) | "patches": [ids] | "box" | "ellipse" | "polygon" | "line", "minus", "mirror"} | null}}}. A call
    adds to the map (null clears a view's mark). Returns the map on every view (or one `view`, with rulers) and
    what it still owes. Details: guide(topic="mark_features"); the page: guide(topic="features")."""
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
    row; the features inside it are the rest: a model is not done on its outline. Returns the table and, for
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
    measured = len(by) - count["IN ITS MASS"] - count[CANT]
    if measured and count["right"] >= 0.8 * measured:   # the moment an agent would go round again for the likeness
        lines.append("PLACED, NOT A LIKENESS: \"right\" is where a part is and how big it is, nothing more. More rounds of "
                     "this do not make it look like the reference (four blind builds of one goat gave four different "
                     "heads), and neither does shaping or fitting these parts: they stay parts. docs/state/feature_map.md")
    view = view or next(iter(rep["cams"]), None)
    if view is None:
        return "\n".join(lines)
    return [_out(featuresee.draw(name, rep, view), save), "\n".join(lines)]


@mcp.tool(structured_output=False)
def build_masses(name: str, how: dict, symmetry: bool = True, view: str | None = None, save: str | None = None):
    """Turn masses of the feature map into shapes, their numbers read off the marks: no coordinate typed. how:
    {feature: {"as": "ball" (a rounded lump) | "drum" (a cylinder) | "flap" (a thin sheet) | "trunk" (an upright
    mass through cross-sections) | "tube" (a limb or horn along its own middle line, as bones), "round": 2 = round .. higher
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


@mcp.tool(structured_output=False)
def build_forms(name: str, how: dict, view: str | None = None, save: str | None = None):
    """Lay forms of the feature map on the built masses as strokes, their paths read off the marks: no surface
    address typed. how: {feature: {"as": "raise" (it stands out of the mass) | "sink" (pressed in: a hollow, a
    groove) | "rim" (a raised ring round its mark) | "band" (a ring round a limb), "depth": metres out or in, "width": metres (half across, for
    a line or a rim), "profile": "soft" | "round" | "flat" | "sharp", "view": the flat view to lay it from}}.
    A form laid again replaces what was laid for it. Returns what was laid, what had to be assumed, and the
    feature report for the forms with a picture. Details: guide(topic="build_forms"); the page: guide(topic="features")."""
    from . import featuresee, forms
    res = forms.build(name, how)
    lines = [f"saved {name} v{res['version']}: laid {len(res['made'])} forms: " + ", ".join(sorted(res["made"]))]
    lines += [f"  ASSUMED {n}" for n in res["notes"]]
    rep = featuresee.report(name)
    by, fm = rep["by_feature"], rep["map"]
    for st in ("NOT MADE", "OFF", "HIDDEN", "CAN'T MEASURE", "IN ITS MASS", "right"):
        fs = sorted(f for f, s in by.items() if s == st and fm["features"][f]["kind"] == "form")
        if fs:
            lines.append(f"forms {st}: " + ", ".join(fs))
    for r in rep["rows"]:
        if r["status"] in ("OFF", "HIDDEN", "CAN'T MEASURE") and fm["features"][r["feature"]]["kind"] == "form":
            lines.append(f"  {r['status']} {r['feature']} ({r['view']}): {r['why']}")
    off = sorted(f for f, s in by.items() if s in ("OFF", "NOT MADE") and fm["features"][f]["kind"] == "mass")
    if off:
        lines.append("masses not right (a form laid on one moves with it): " + ", ".join(off))
    lines.append("The numbers place a form; whether it READS is seen in a clay look, close up, beside the picture.")
    view = view or next(iter(rep["cams"]), None)
    if view is None:
        return "\n".join(lines)
    return [_out(featuresee.draw(name, rep, view), save), "\n".join(lines)]


@mcp.tool(structured_output=False)
def look_beside(name: str, views: list[str] | None = None, ignore: list[str] | None = None,
                on_purpose: list[dict] | None = None, resolution: int = 176, save: str | None = None,
                focus: list[str] | None = None):
    """Compare the model with its reference pictures, view by view, and see what to change: the model beside each
    flat reference view (front, side, back; read_reference first) AND from the concept painting's own angle (view
    "painting": fit_concept_camera once, on the painting), one picture a view: the reference with the model's
    outline over it (the painting) | the model, its parts tinted, with the reference's outline and inside lines in
    red | the difference (red = add clay, blue = take away) with its worst places numbered. The text lists those
    places biggest first, with the mass each is on, the PROPORTIONS (how wide and deep the figure is where the
    reference is widest and narrowest: the balance of the masses), and the pieces that touch nothing. Seconds, no render: use it
    after every change. LOOK at the pictures: the painting's view is where a figure reads as itself, and where a
    mass in the wrong place shows (a snout beside the painted snout) that no outline number says. These are
    differences, not faults: where you differ ON PURPOSE (a limb held out for the rig, a choice between pictures
    that disagree) record it with on_purpose=[{"view", "at": [u, v] as listed, "why"}]: it is then shown apart with
    its reason and left out of the list and the overlap. ignore: masses to leave out. focus: masses to see CLOSE
    UP (an ear, a snout): every picture is cut to them and drawn large, beside the same part of each reference view
    and the painting. save: a folder for the pictures, or a .png file name (the first picture; the rest beside it). Details: guide(topic="look_beside")."""
    from pathlib import Path

    from . import beside
    from .tool_common import _png, save_path
    if on_purpose:
        beside.set_on_purpose(name, on_purpose)
    res = beside.compare(name, views, ignore, resolution, focus=focus)
    import os
    out = []
    for i, (title, pic) in enumerate(beside.layout(res, "sheet")):
        if save:
            d = save_path(save)
            if d.suffix.lower() == ".png":  # a file name: the first picture there, the rest beside it (e16, e17 got a
                d.parent.mkdir(parents=True, exist_ok=True)  # folder called "x.png")
                pic.save(d if i == 0 else d.with_name(f"{d.stem}_{title}.png"))
            else:
                d.mkdir(parents=True, exist_ok=True)
                pic.save(d / f"{title}.png")
        out.append(_png(pic))
    return [*out, beside.text(name, res)]



@mcp.tool(structured_output=False)
def study_part(name: str, what: str, at: list[float], size: float = 0.08):
    """Study ONE part of the reference before you model it (an ear, a snout, a horn): the same part cut from every
    reference picture (each flat view and the painting), one large picture each, and the order to read it in.
    what: the part in plain words ("the left ear"); at: [x, y, z], its middle in metres (read off read_reference's or
    look_beside's rulers; it need not exist in the model yet); size: half the box's side, m (the part and a little
    of what it grows from). Why the order: where one part hides another in a view (a folded lobe in front of an
    ear's root, seen from the side), the outline reads as one broad shape, and plain looking got it wrong every time
    in blind trials; reading each view alone, naming what hides what and taking each size only from a view where
    nothing is in front of it got it right. Seconds. Details: guide(topic="study_part")."""
    from . import study
    from .tool_common import _png
    if not (isinstance(at, (list, tuple)) and len(at) == 3):
        raise ValueError("at is the part's middle [x, y, z] in metres (x, z in the front view; y, z in the side view)")
    if not 0.005 <= float(size) <= 1.0:
        raise ValueError("size is half the box's side in metres: the part and a little round it (e.g. 0.06)")
    got = study.crops(name, at, float(size))
    if not got:
        raise ValueError(f"the box {at} +- {size} m falls outside every reference picture: check at against the "
                         "rulers (look_beside shows them), and that read_reference has been run")
    lines = [f"{what}: {len(got)} pictures, one each: " + "; ".join(c for c, _, _ in got) + ".", "", study.order(what),
             "", f"next: once step 5 is written, model {what}; then look_beside with focus on its masses, and "
             f"review_part for a fresh reviewer's eyes."]
    return [*[_png(p) for _, p, _ in got], "\n".join(lines)]


@mcp.tool(structured_output=False)
def review_part(name: str, masses: list[str], region: str, context: str = "a game character: a concept painting "
                "and a clay blockout of it, seen from the same camera"):
    """A fresh pair of eyes on ONE part of the model: the part rendered in clay through the concept painting's own
    camera, cut with the same box from the painting, and judged by an independent reviewer who sees only the two
    pictures (no captions, no numbers, none of your reasoning). Its form first, then the differences, worst first.
    masses: the part's masses (e.g. ["ear.L", "ear_top.L"]); region: what the reviewer is told it is, plain words
    ("the ear"). The one who made a part sees what they meant; a fresh reviewer sees what is there: in blind trials
    the maker passed an ear whose base was plainly wrong, and two fresh reviewers named it unprompted. A minute or
    two (a render and a review). Needs the painting's camera (fit_concept_camera). Details: guide(topic="review_part")."""
    from pathlib import Path

    from . import beside_painting, matched
    from .tools_model import review_view
    label = beside_painting.camera_label(name)
    if label is None:
        raise ValueError("the painting has no camera yet: fit_concept_camera(name, image=<the painting>) first")
    matched.render(name, label)
    r = matched.tiles(name, {region: list(masses)}, label)
    ref, ours, box = r["tiles"][region]
    # (a first run spent half its faults on clay texture and colour: a blockout is judged on its big form)
    out = review_view(region=region, reference=ref, result=ours, context=context,
                      stage="blockout: the big form of this part (its shape, size, thickness, fold and how it meets "
                            "the head) and where it sits", not_stages="surface texture, colour, material, fine creases",
                      out_dir=str(Path(r["dir"]) / "review"))
    text = out[-1] if isinstance(out, (list, tuple)) else str(out)
    return [*out[:-1], f"{region}: the painting | the model, through the painting's camera (box {box}).\n{text}\n"
            "next: fix the worst difference the reviewer names that belongs to this pass, then look again. The "
            "reviewer judges what it sees; where you differ on purpose, say so in your log, not to it."]
