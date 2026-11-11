"""The rows of a comparison (shape, jaw, contour), measure_reference, compare. Part of likeness (likeness.py has the overview)."""
from __future__ import annotations

import json

import numpy as np

from .likeness import TARGETS, checklist, stage_names
from .likeness_measure import Side, Unmeasurable, _confidence, _item, points_of
from .likeness_notes import EXPR_BIAS, YAW_ITEMS, YAW_MM, picture_notes
from .likeness_sides import INFER_TOL, SPECIAL, _allowed, _near_sign, _refs, measure_sides, model_sides, photo_sides

MIRROR = {61: 291, 234: 454, 33: 263, 133: 362, 145: 374, 159: 386, 129: 358, 98: 327, 172: 397, 105: 334, 70: 300,
          107: 336, 52: 282, 58: 288, 136: 365, 116: 345, 123: 352, 50: 280, 205: 425, 147: 376, 187: 411, 93: 323}


def _shape_rows(it, photos, models, kinds) -> list:
    from . import likeness_shape as ls
    rows = []
    m = it["measure"]
    for vi, (ph, md) in enumerate(zip(photos, models)):
        ok, inferred = _allowed(it, kinds[vi], kinds)
        if not ok:
            continue
        sh = md.get("shade")
        r = {"vi": vi, "inferred": inferred, "model3d": md.get("shape3d", {}).get(m.get("model3d"))}
        if sh is None:
            r["why"] = "no shading (no detector on the photo)"
            rows.append(r)
            continue
        vals = []
        for sgn in _near_sign(ph["side"]):
            pidx = (lambda i, s=sgn: MIRROR.get(i, i) if s > 0 else i)
            exs = sh["ex"]
            reg = ls.region_centre(ph["side"], m["region"], sgn, exs, sh["ey"], sh["ppm"], sh["to_px"], pidx)
            ref = ls.region_centre(ph["side"], m["ref"], sgn, exs, sh["ey"], sh["ppm"], sh["to_px"], pidx)
            H, W = sh["R"].shape
            a = sh["R"][ls._disk(H, W, reg, m["region"].get("r_mm", 4) * sh["ppm"])]
            b = sh["R"][ls._disk(H, W, ref, m["ref"].get("r_mm", 5) * sh["ppm"])]
            a, b = a[np.isfinite(a)], b[np.isfinite(b)]
            if len(a) < 10 or len(b) < 10:
                continue
            vals.append(100 * (a.mean() - b.mean()))
            r.setdefault("regions", []).append((reg, ref, m["region"].get("r_mm", 4) * sh["ppm"], m["ref"].get("r_mm", 5) * sh["ppm"]))
        if vals:
            r["photo"] = float(np.mean(vals))
        else:
            r["why"] = "region off the face's skin in this picture"
        rows.append(r)
    return rows


def _jaw_rows(it, photos, models, kinds, traces) -> list:
    from . import likeness_shape as ls
    rows = []
    key = it["measure"]["key"]
    for vi, (ph, md) in enumerate(zip(photos, models)):
        ok, inferred = _allowed(it, kinds[vi], kinds)
        if not ok:
            continue
        tr = traces.get(ph["view"]["image"], {})
        r = {"vi": vi, "inferred": inferred}
        got = False
        for sd in ("R", "L"):
            Q = tr.get("lines", {}).get(f"jaw.{sd}")
            if not Q or len(Q) < 6:
                continue
            pv, mv = _jaw_pair(ph, md, tr, sd)
            if key in pv and key in mv:
                r.setdefault("pairs", []).append((pv[key], mv[key]))
                r.setdefault("traces", []).append((np.asarray(Q, float), mv.get("_line"), pv.get("_gonion"), mv.get("_gonion")))
                got = True
        if got:
            r["photo"] = float(np.mean([a for a, b in r["pairs"]]))
            r["model"] = float(np.mean([b for a, b in r["pairs"]]))
        else:
            r["why"] = ("needs a trace on this picture: likeness_points 'jaw.R' / 'jaw.L' (down the ramus, round the angle, "
                        "forward along the lower border)" + ("; 'ear_lobe.R' for the lobe" if "lobe" in key else "")
                        + ("; 'neck.R' for the neck" if "neck" in key else ""))
        rows.append(r)
    return rows


def profile_read(ph, md, traces):
    """likeness_profile.read for one picture, kept on the model's entry (None: no "profile" line on that picture)."""
    from . import likeness_profile as lp
    if "profile" not in md:
        lines = traces.get(ph["view"]["image"], {}).get("lines", {})
        try:
            md["profile"] = (lp.read(ph["img"], lines, md, ph["box"], ph["side"].P,
                                     traces.get(ph["view"]["image"], {}).get("points", {})) if lines.get("profile") else None)
        except Exception as e:  # noqa: BLE001
            md["profile"] = None
            md["profile_error"] = str(e)
    return md["profile"]


CONTOUR_WHY = {"upper_lip": "the lips don't break this contour (no notch between them at this angle)",
               "lower_lip": "the lips don't break this contour (no notch between them at this angle)",
               "forehead_slope": "the trace doesn't run 4 cm up the forehead"}


def _contour_rows(it, photos, models, kinds, traces) -> list:
    rows = []
    key = it["measure"]["key"]
    nose = key.startswith(("nose", "bridge", "tip_", "columella"))
    for vi, (ph, md) in enumerate(zip(photos, models)):
        ok, inferred = _allowed(it, kinds[vi], kinds)
        if not ok or kinds[vi] == "front":
            continue
        rd = profile_read(ph, md, traces)
        r = {"vi": vi, "inferred": False}
        if rd is None:
            r["why"] = ("needs a trace on this picture: likeness_points line 'profile' (the far side of the face against "
                        "the background, forehead to under the chin)" + ("; 'nose' (the nose's own edge)" if nose else ""))
        elif key in rd["photo"]["m"] and key in rd["model"]["m"]:
            r["photo"], r["model"] = float(rd["photo"]["m"][key]), float(rd["model"]["m"][key])
            r["traces"] = [(rd["photo"]["line"], rd["model"]["line"], None, None)]
            if "nose" in rd["photo"]:
                r["traces"].append((rd["photo"]["nose"]["line"], rd["model"]["nose"]["line"], None, None))
            o, ex, ey = rd["frame"]
            names = {"chin_projection": ("chin", "brow"), "cheek_line": ("mouth", "brow"), "chin_height": ("chin", "mouth"),
                     "brow_ridge": ("brow", "orbit"), "mentolabial": ("sulcus",), "forehead_slope": ("fh1", "fh2"),
                     "upper_lip": ("ul", "sto"), "lower_lip": ("ll_notch", "sto")}.get(key, ())
            marks = []
            for sd_ in ("photo", "model"):
                kk = {**rd[sd_]["kp"], **rd[sd_]["kn"]} if nose else rd[sd_]["kp"]
                nm = ("tip", "under", "base", "nasion", "alar") if nose else names
                marks.append([o + ex * kk[n][1] / rd["mmpx"] + ey * kk[n][0] / rd["mmpx"] for n in nm if n in kk])
            r["marks"] = marks
        else:
            r["why"] = CONTOUR_WHY.get(key, "the line 'nose' is not traced on this picture" if nose and "nose" not in rd["photo"]
                                       else "needs the hand-placed point 'alar_base.R' / '.L' (the near wing's base) on this picture"
                                       if nose and "alar" not in rd["photo"]["kn"] and key in ("nose_base_incl", "tip_height", "columella_show")
                                       else "not found on this contour")
        rows.append(r)
    return rows


def _jaw_pair(ph, md, tr, sd):
    """The jaw measures on the photo's trace and on the model's contour found along it (picture pixels)."""
    from . import likeness_shape as ls
    from . import humanfit
    ex, ey = ph["side"].frame()
    mmpx = md["mmpx"]
    Q = np.asarray(tr["lines"][f"jaw.{sd}"], float)
    pts = tr.get("points", {})
    try:
        mouth_p = ph["side"].pt([13, 14])
        mouth_m = md["side"].pt([13, 14])
    except Unmeasurable:
        mouth_p = mouth_m = None
    neck_p = tr.get("lines", {}).get(f"neck.{sd}")
    pv = ls.jaw_measures(Q, ex, ey, mmpx, pts.get(f"ear_lobe.{sd}"), mouth_p, neck_p)
    # the model's jaw line by GEOMETRY, not an image search (the contour found in the render read a neck step of
    # 7-27 mm on one head between runs): its own jaw-contour landmarks on that side (lm 2..8: the line onemesh2's
    # shape.jawline moves, the skin following), densified in 3D and projected; the neck under it = the outermost skin
    # 12-30 mm below the border two thirds of the way to the chin.
    L3, V3 = md["mesh"]["L"], md["mesh"]["V"]
    mx = 0.5 * (L3[68, 0] + L3[69, 0])
    sx = -1.0 if sd == "R" else 1.0
    ids = [2, 3, 4, 5, 6, 7, 8] if np.sign(L3[3, 0] - mx) == sx else [14, 13, 12, 11, 10, 9, 8]
    O = L3[ids]
    seg = np.linalg.norm(np.diff(O, axis=0), axis=1)
    u = np.r_[0, np.cumsum(seg)] / seg.sum()
    J3 = np.c_[[np.interp(np.linspace(0, 1, 40), u, O[:, c]) for c in range(3)]].T
    Qm = humanfit.project(md["cam"], J3)
    i3 = ls._split_corner(Qm)
    B = J3[i3 + (2 * (len(J3) - i3)) // 3] if i3 is not None else J3[26]
    neck_m = None
    ears_i = md["mesh"].get("ears")
    skin = np.ones(len(V3), bool)
    if ears_i is not None:
        skin[ears_i] = False
    side_v = skin & (np.sign(V3[:, 0] - mx) == sx) & (np.abs(V3[:, 1] - B[1]) < 0.012)
    npts = []
    for z0, z1 in ((0.012, 0.02), (0.02, 0.03)):
        kk = side_v & (V3[:, 2] < B[2] - z0) & (V3[:, 2] > B[2] - z1)
        if kk.any():
            npts.append(V3[kk][np.argmax(np.abs(V3[kk][:, 0] - mx))])
    if len(npts) == 2 and neck_p and len(neck_p) >= 2:
        neck_m = humanfit.project(md["cam"], np.array(npts))
    lobe_m = None
    ears = md["mesh"].get("ears")
    if ears is not None and len(ears):
        V = md["mesh"]["V"][ears]
        s = V[V[:, 0] < 0] if sd == "R" else V[V[:, 0] > 0]
        if len(s):
            lobe_m = humanfit.project(md["cam"], s[np.argmin(s[:, 2])][None])[0]
    mex, mey = md["side"].frame() if md["side"].P is not None else (ex, ey)
    mv = ls.jaw_measures(Qm, mex, mey, mmpx, lobe_m, mouth_m, neck_m)
    mv["_line"] = Qm
    return pv, mv


def measure_reference(name: str, save: bool = True, photos=None) -> dict:
    """The target sheet: every checklist item measured on the model's reference pictures (human_refs.json), with its
    view, tolerance, confidence and source, or why it can't be measured. Saved as <model>/likeness_targets.json.
    Values are mm at the face's depth through each picture's fitted camera (its own scale), degrees or ratios."""
    from . import store
    refs = _refs(name)
    photos = photos or photo_sides(refs)
    vals = measure_sides([p["side"] for p in photos], [p["kind"] for p in photos], [p["mmpx"] for p in photos])
    items = {}
    from . import likeness_shape as ls
    traces = ls.load_points(name)
    kinds = [p["kind"] for p in photos]
    for it in checklist():
        rows = {}
        if it["measure"]["kind"] == "shape":
            vals[it["id"]] = {"-": "unmeasurable: shading is read against a model lit like the photo (compare / likeness)"}
        if it["measure"]["kind"] == "contour":
            vals[it["id"]] = {"-": "unmeasurable: a contour is read in the model's frame through its camera (compare / likeness); "
                                   "trace likeness_points 'profile' / 'nose' on a turned view"}
        if it["measure"]["kind"] == "jaw":
            vals[it["id"]] = {}
            for vi, ph in enumerate(photos):
                if not _allowed(it, ph["kind"], kinds)[0]:
                    continue
                tr = traces.get(ph["view"]["image"], {})
                got = []
                for sd in ("R", "L"):
                    Q = tr.get("lines", {}).get(f"jaw.{sd}")
                    if Q and len(Q) >= 6:
                        ex, ey = ph["side"].frame()
                        try:
                            mouth = ph["side"].pt([13, 14])
                        except Unmeasurable:
                            mouth = None
                        v = ls.jaw_measures(Q, ex, ey, ph["mmpx"], tr.get("points", {}).get(f"ear_lobe.{sd}"), mouth,
                                            tr.get("lines", {}).get(f"neck.{sd}")).get(it["measure"]["key"])
                        if v is not None:
                            got.append(v)
                vals[it["id"]][vi] = float(np.mean(got)) if got else "unmeasurable: needs a trace (likeness_points jaw.R / jaw.L)"
        for vi, v in vals[it["id"]].items():
            if vi == "-":
                rows["-"] = {"value": None, "confidence": "unmeasurable", "why": v.split(": ", 1)[1]}
                continue
            ph = photos[vi]
            if isinstance(v, str):
                rows[str(vi)] = {"view": ph["kind"], "value": None,
                                 "confidence": "judge" if "judge" in v else "unmeasurable", "why": v.split(": ", 1)[1]}
            else:
                rows[str(vi)] = {"view": ph["kind"], "value": round(float(v), 3),
                                 "confidence": _confidence(it, ph["kind"], ph["mmpx"], ph["side"].source),
                                 "source": ph["side"].source, "mm_per_px": round(ph["mmpx"], 3)}
        items[it["id"]] = {"name": it["name"], "stage": it["stage"], "unit": it["unit"], "tol": it["tol"],
                           "control": it["control"], "reliability": it.get("reliability", ""), "views": rows}
    sheet = {"model": name, "references": [{"image": p["view"]["image"], "view": p["kind"], "mm_per_px": round(p["mmpx"], 3),
                                            "detector": p["side"].source == "detector"} for p in photos],
             "stages": [s["name"] for s in stage_names()], "items": items}
    if save:
        (store.HOME / name / TARGETS).write_text(json.dumps(sheet, indent=1))
    return sheet


def sheet_text(sheet: dict) -> str:
    lines = ["target sheet (" + ", ".join(f"{r['view']} {r['mm_per_px']} mm/px{'' if r['detector'] else ' NO DETECTOR'}"
                                          for r in sheet["references"]) + ")"]
    for st in sheet["stages"]:
        lines.append(f"[{st}]")
        for iid, it in sheet["items"].items():
            if it["stage"] != st:
                continue
            for vi, r in it["views"].items():
                v = "-" if r["value"] is None else (f"{r['value']:.3f}" if it["unit"] == "" else f"{r['value']:.1f} {it['unit']}")
                lines.append(f"  {it['name'][:44]:44} {r.get('view', '-'):13} {v:>10}  {r['confidence']}"
                             + (f" ({r['why']})" if r.get("why") else ""))
    return "\n".join(lines)


def compare(name: str, base: dict | None = None, photos=None, cameras=None, mesh=None, points_from: str | None = None) -> dict:
    """Photo vs model for every item and view: rows sorted by miss / tolerance (beyond tolerance first, then big items
    before small), plus the pictures the focus panels need."""
    from . import store
    base = base or store.load(name)["base"]
    photos = photos or photo_sides(_refs(name))
    models = model_sides(base, photos, mesh=mesh, cameras=cameras)
    kinds = [p["kind"] for p in photos]
    mm = [m["mmpx"] for m in models]
    pv = measure_sides([p["side"] for p in photos], kinds, mm)
    mv = measure_sides([m["side"] for m in models], kinds, mm)
    # the same measures on the landmarks alone (the photo's stored 68 + eye centres, the model's own GNM landmarks):
    # where the two readings disagree, the miss depends on the definition, not only on the face
    pl = measure_sides([Side(None, p["side"].lm, "landmarks") for p in photos], kinds, mm)
    ml = measure_sides([Side(None, m["side"].lm, "landmarks") for m in models], kinds, mm)
    from . import likeness_shape as ls
    for md in models:
        md["shape3d"] = md["mesh"].get("shape3d") or {}
    traces = ls.load_points(points_from or name)
    rows = []
    order = [s["name"] for s in stage_names()]
    for it in checklist():
        kind = it["measure"]["kind"]
        if kind in SPECIAL:
            got = (_shape_rows(it, photos, models, kinds) if kind == "shape" else _jaw_rows(it, photos, models, kinds, traces)
                   if kind == "jaw" else _contour_rows(it, photos, models, kinds, traces))
            if not got:
                got = [{"vi": "-", "why": " or ".join(it["views"]) + " view needed"}]
            for g in got:
                vi = g["vi"]
                tol = it["tol"] * (INFER_TOL if g.get("inferred") else 1.0)
                a = g.get("photo")
                b = 0.0 if kind == "shape" and a is not None else g.get("model")
                r = {"id": it["id"], "name": it["name"], "stage": it["stage"], "tier": order.index(it["stage"]) + 1,
                     "view": kinds[vi] if vi != "-" else "-", "vi": vi, "unit": it["unit"], "tol": tol,
                     "control": it["control"], "reliability": it.get("reliability", ""), "photo": a, "model": b,
                     "points": points_of(it["measure"]), "inferred": g.get("inferred", False), "kind": kind,
                     "model3d": g.get("model3d"), "regions": g.get("regions"), "traces": g.get("traces"),
                     "marks": g.get("marks"), "rank": float(it.get("rank", 1.0))}
                if kind == "shape" and r["view"] != "front" and isinstance(a, float):
                    r["score"] = -1.0
                    r["why"] = (f"shading contrast {a:+.1f}% shown in the panel, not scored: a turned / painted view's light "
                                "is not one light")
                elif isinstance(a, float) and isinstance(b, float) and np.isfinite(a) and np.isfinite(b):
                    r["miss"] = b - a
                    r["score"] = abs(b - a) / tol
                    r["source"] = "shading" if kind == "shape" else "trace/render contour"
                    if kind == "contour":
                        r["source"] = "contour"
                else:
                    r["score"] = -1.0
                    r["why"] = g.get("why", "")
                rows.append(r)
            continue
        for vi in pv[it["id"]]:
            a, b = pv[it["id"]][vi], mv[it["id"]].get(vi)
            inferred = vi != "-" and _allowed(it, kinds[vi], kinds)[1]
            tol = (it["tol"] or 0) * (INFER_TOL if inferred else 1.0) or it["tol"]
            r = {"id": it["id"], "name": it["name"], "stage": it["stage"], "tier": order.index(it["stage"]) + 1,
                 "view": kinds[vi] if vi != "-" else "-", "vi": vi, "unit": it["unit"], "tol": tol,
                 "control": it["control"], "reliability": it.get("reliability", ""), "photo": a, "model": b,
                 "points": points_of(it["measure"]), "inferred": inferred, "kind": it["measure"]["kind"]}
            cres = models[vi]["cam_res"] if vi != "-" else None
            if cres is not None:
                pr = [cres[i] for i in r["points"] if i < len(cres) and np.isfinite(cres[i])]
                if pr:
                    r["cam_mm"] = float(np.sqrt(np.mean(np.square(pr)))) * models[vi]["mmpx"]
            if isinstance(a, float) and isinstance(b, float) and it["tol"] and np.isfinite(a) and np.isfinite(b):
                r["miss"] = b - a
                r["score"] = abs(b - a) / tol
                if r.get("cam_mm") is not None and it["unit"] == "mm":  # a loose camera: its residual widens the tolerance
                    r["score"] = abs(b - a) / float(np.hypot(tol, 0.5 * r["cam_mm"]))
                r["source"] = f"{photos[vi]['side'].source}/{models[vi]['side'].source}"
                c, d = pl[it["id"]].get(vi), ml[it["id"]].get(vi)
                if isinstance(c, float) and isinstance(d, float) and np.isfinite(c) and np.isfinite(d):
                    r["miss_lm"] = d - c
                    r["agree"] = abs((d - c) - (b - a)) <= it["tol"]
            else:
                r["score"] = -1.0
                r["why"] = (a if isinstance(a, str) else b if isinstance(b, str) else "").split(": ", 1)[-1]
            rows.append(r)
    # a contour reading replaces the "inferred" detector reading of the same thing on that picture
    gone = {(i, r["vi"]) for r in rows if r.get("kind") == "contour" and r["score"] >= 0
            for i in _item(r["id"]).get("replaces", [])}
    rows = [r for r in rows if not ((r["id"], r["vi"]) in gone and r.get("kind") != "contour")]
    # "rank": identity features people read at once (the nose's base line) sort above their bare miss / tolerance
    rows.sort(key=lambda r: (-(r["score"] > 1.0), -r["score"] * r.get("rank", 1.0) if r["score"] > 1.0 else r["tier"], -r["score"]))
    cmp = {"rows": rows, "photos": photos, "models": models, "name": name, "points_from": points_from}
    cmp["pictures"] = [picture_notes(p, m) for p, m in zip(photos, models)]
    for r in rows:   # a turned picture whose yaw is in doubt: its depth items are judged wider
        if r.get("kind") == "contour" and r["score"] >= 0 and _item(r["id"])["measure"]["key"] in YAW_ITEMS:
            d = cmp["pictures"][r["vi"]].get("yaw_doubt")
            if d:
                r["tol"] = r["tol"] + YAW_MM * d
                r["score"] = abs(r["miss"]) / r["tol"]
                r["reliability"] = f"yaw in doubt by {d:.0f} deg (tolerance widened); " + r.get("reliability", "")
    rows.sort(key=lambda r: (-(r["score"] > 1.0), -r["score"] * r.get("rank", 1.0) if r["score"] > 1.0 else r["tier"], -r["score"]))
    for r in rows:   # items an expression on that picture biases
        if r["vi"] != "-":
            for nm, v in (cmp["pictures"][r["vi"]].get("expressions") or {}).items():
                if r["id"] in EXPR_BIAS.get(nm, []):
                    r["expression"] = f"{nm} {v:.2f}"
    return cmp
