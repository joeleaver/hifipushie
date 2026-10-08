"""Garments read from reference art, and simulated garments checked against that reading (guide(topic=
"cloth_reference"); the list is cloth_checklist.json).

Two uses of one checklist, as with the face's likeness list:
- `read(model, garments, views, answers)`: the FORM an LLM fills from the pictures (one row per checklist item of the
  garments' kinds, big to small, with the crop that shows it), then, from the answers, the design-sheet patch per
  garment and the TARGET TABLE (each item's reading with its tolerance and confidence; "not visible" allowed).
  Numbers come from marked image points: an orthographic camera is fitted to the model's own body landmarks
  (`fit_camera`), lengths are read ANCHORED (the fraction t along two body landmarks: the jacket's hem at t of the
  way waist -> knee) and carried onto our body, widths in metres through the camera's scale.
- `check(model, garments, refs, results)`: our cached sims (never simulated here) measured item by item (`MEASURES`),
  each miss in tolerances, ranked (stage weight x miss), with focus panels: the reference crop | our garments drawn
  through the SAME camera (`render_front`), the item's points marked.

A result may be a full cloth.build result or a light one {"V", "F", "piece", "names"} (an npz a scratch run saved):
measures that need more (folds, button marks) say "not measured in this result".
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

CHECKLIST_PATH = Path(__file__).with_name("cloth_checklist.json")
STAGE_WEIGHT = {1: 1.6, 2: 1.4, 3: 1.2, 4: 1.1, 5: 1.0}
CHOICE_MISS = 3.0  # severity of a wrong choice / count / bool (in tolerances)
SLEEVE_ROLES = ("sleeve", "cuff", "sleeve_placket")
NOT_TORSO = SLEEVE_ROLES + ("collar_stand", "collar_fall", "neckband", "hood", "waistband", "belt", "pocket", "facing")
CONF_W = {"high": 1.0, "medium": 0.75, "low": 0.4}


def checklist() -> dict:
    return json.loads(CHECKLIST_PATH.read_text())


def items_for(kind: str | None) -> list:
    """The checklist's items for one garment kind, big to small (stage, then the list's order)."""
    its = [it for it in checklist()["items"] if "*" in it["kinds"] or (kind and kind in it["kinds"])]
    return sorted(its, key=lambda it: it["stage"])


# ---------------------------------------------------------------- body landmarks


def _mirror(p):
    return np.array([-p[0], p[1], p[2]], float)


def landmarks(body) -> dict:
    """Named 3D body landmarks (cloth.Body): what checklist anchors and regions address. Generic names ("knee")
    resolve to the left side (+X)."""
    J, at, V = body.J, body.at, body.V
    L = {}
    top = V[np.argmax(V[:, 2])]
    L["head_top"] = np.array([0.0, top[1], top[2]])
    L["floor"] = np.array([0.0, float(np.median(V[V[:, 2] < V[:, 2].min() + 0.01, 1])), float(V[:, 2].min())])
    if "lm_chin" in J:
        L["chin"] = np.asarray(J["lm_chin"], float)
    if "cf_neck" in at:
        L["neck_base"] = np.asarray(at["cf_neck"], float)
    elif "neck" in J:
        L["neck_base"] = np.asarray(J["neck"], float)
    for s, sg in (("L", 1), ("R", -1)):
        for nm in ("shoulder", "elbow", "wrist"):
            p = at.get(f"{nm}.L") if nm == "shoulder" else None
            p = np.asarray(p, float) if p is not None else (np.asarray(J[f"{nm}.L"], float) if f"{nm}.L" in J else None)
            if p is not None:
                L[f"{nm}.{s}"] = p if sg > 0 else _mirror(p)
        for nm in ("knee", "ankle", "hip"):
            if f"{nm}.{s}" in J:
                L[f"{nm}.{s}"] = np.asarray(J[f"{nm}.{s}"], float)
    yc = float(np.median(V[:, 1]))
    for nm, key in (("armpit", "armpit_z"), ("chest", "chest_z"), ("waist", "waist_z"), ("hip", "hips_z"),
                    ("seat", "seat_z"), ("crotch", "crotch_z")):
        if key in at:
            L[nm] = np.array([0.0, yc, float(at[key])])
    for nm in ("knee", "ankle", "elbow", "wrist", "shoulder"):
        if f"{nm}.L" in L:
            L[nm] = L[f"{nm}.L"]
    return L


# ---------------------------------------------------------------- the camera (orthographic, front)


def fit_camera(points: dict, L: dict, size) -> dict:
    """An orthographic front camera from marked body landmarks {name: [u, v]} (u right, v down) onto the model's
    landmarks: u = u0 + s (c x' - r z'), v = v0 - s (r x' + c z') with x' = x - x0, z' = z - z0 (scale, roll, shift; least
    squares). A concept sheet in A-pose is near orthographic; a painting in perspective is not (use it for choices).
    The report gives each point's residual in px and mm: a big one is a body that differs from ours there."""
    names = [k for k in points if k in L]
    if len(names) < 2:
        raise ValueError(f"fit_camera: need 2+ body landmarks we have (got {list(points)}; have {sorted(L)})")
    P = np.array([L[k] for k in names], float)
    uv = np.array([points[k] for k in names], float)
    x0, z0 = P[:, 0].mean(), P[:, 2].mean()
    X = np.c_[P[:, 0] - x0, P[:, 2] - z0]
    Y = np.c_[uv[:, 0], -uv[:, 1]]
    Xm, Ym = X.mean(0), Y.mean(0)
    A, B = X - Xm, Y - Ym
    # similarity (Umeyama, no reflection): Y = s R X + t
    Hm = A.T @ B
    U, S, Vt = np.linalg.svd(Hm)
    D = np.diag([1, np.sign(np.linalg.det(Vt.T @ U.T))])
    Rm = Vt.T @ D @ U.T
    s = float(np.trace(np.diag(S) @ D) / max((A ** 2).sum(), 1e-12))
    t = Ym - s * Rm @ Xm
    cam = {"kind": "ortho_front", "s": s, "R": Rm.tolist(), "t": t.tolist(), "x0": float(x0), "z0": float(z0),
           "size": [int(size[0]), int(size[1])]}
    res = np.linalg.norm(project(cam, P) - uv, axis=1)
    cam["residual_px"] = {k: round(float(r), 1) for k, r in zip(names, res)}
    cam["residual_mm"] = {k: round(float(r / s * 1000), 1) for k, r in zip(names, res)}
    cam["px_per_m"] = round(s, 2)
    return cam


def project(cam: dict, P) -> np.ndarray:
    P = np.atleast_2d(np.asarray(P, float))
    X = np.c_[P[:, 0] - cam["x0"], P[:, 2] - cam["z0"]]
    Y = cam["s"] * X @ np.asarray(cam["R"]).T + np.asarray(cam["t"])
    return np.c_[Y[:, 0], -Y[:, 1]]


def unproject(cam: dict, uv) -> np.ndarray:
    """Pixels -> world [x, z] in the front plane."""
    uv = np.atleast_2d(np.asarray(uv, float))
    Y = np.c_[uv[:, 0], -uv[:, 1]] - np.asarray(cam["t"])
    X = Y @ np.asarray(cam["R"]) / cam["s"]
    return np.c_[X[:, 0] + cam["x0"], X[:, 1] + cam["z0"]]


def _img_landmark(view: dict, name: str):
    """A landmark's pixel position in a view: marked, else projected through the view's camera."""
    pts = view.get("points") or {}
    if name in pts:
        return np.asarray(pts[name], float)
    if name.split(".")[0] in pts and "." not in name:
        return np.asarray(pts[name], float)
    cam, L = view.get("camera"), view.get("_L")
    if cam is None or L is None or name not in L:
        return None
    return project(cam, L[name])[0]


def anchored_t(p, a, b) -> float:
    """The fraction along a -> b of the point's projection (2D or 3D)."""
    p, a, b = (np.asarray(v, float) for v in (p, a, b))
    d = b - a
    return float((p - a) @ d / max(d @ d, 1e-12))


VERTICAL = ("head_top", "chin", "neck_base", "armpit", "chest", "waist", "hip", "seat", "crotch", "floor")


def _vertical(a_n: str, b_n: str) -> bool:
    """An anchor through a body LEVEL (waist, crotch, floor...) is read in height only: a level has no x of its own."""
    return a_n.split(".")[0] in VERTICAL or b_n.split(".")[0] in VERTICAL


def _t(p, a, b, a_n: str, b_n: str, image: bool = False) -> float:
    """The anchored fraction: by height alone for level anchors (image v / world z), else along a -> b."""
    if _vertical(a_n, b_n):
        k = 1 if image else 2
        p, a, b = (np.asarray(x, float) for x in (p, a, b))
        return float((p[k] - a[k]) / (b[k] - a[k]))
    return anchored_t(p, a, b)


def _anchor_names(it: dict, side: str = "L") -> tuple:
    a, b = it["anchor"]
    fix = lambda n: f"{n}.{side}" if n in ("knee", "ankle", "elbow", "wrist", "shoulder", "hip") else n
    return fix(a), fix(b)


def crop_box(view: dict, it: dict, L: dict) -> list | None:
    """The item's focus crop in a view's pixels: round its region's landmarks (+ pad), at least 160 px."""
    reg = it.get("region") or {}
    if view.get("crops", {}).get(it["id"]):
        return list(view["crops"][it["id"]])
    cam = view.get("camera")
    if cam is None:
        return None
    pts = []
    for nm in reg.get("around", []):
        p = _img_landmark(view, nm if nm in L or nm in (view.get("points") or {}) else nm)
        if p is not None:
            pts.append(p)
    if not pts:
        return None
    pts = np.array(pts)
    pad = float(reg.get("pad", 0.08)) * cam["s"]
    lo, hi = pts.min(0) - pad, pts.max(0) + pad
    # a region of body levels (waist, crotch) has no width of its own: at least the torso's breadth and 8 cm tall
    c, half = (lo + hi) / 2, np.maximum((hi - lo) / 2, [0.2 * cam["s"], 0.08 * cam["s"]])
    w, h = cam["size"]
    lo, hi = np.maximum(c - half, 0), np.minimum(c + half, [w, h])
    return [int(lo[0]), int(lo[1]), int(hi[0]), int(hi[1])]


# ---------------------------------------------------------------- reading a reference


def _kb():
    from . import garment_design
    return garment_design.kb()


def choices_of(it: dict) -> list:
    if it.get("detail"):
        return [k for k in _kb()["details"][it["detail"]] if not k.startswith("_")]
    ch = it.get("choices")
    if ch == "garment_kb fabrics":
        return [k for k in _kb()["fabrics"] if not k.startswith("_")]
    if isinstance(ch, list):
        return ch
    if it.get("scale"):
        return list(it["scale"])
    return []


def form(garments: dict, views: list | None = None) -> list:
    """The form to fill: one row per checklist item of each garment's kind ({garment: kind}), big to small: what to
    look for, which view shows it, the answer's type (choice: the options; length / width: the points to mark), and the
    crop of each view that shows it (when the view has a camera)."""
    rows = []
    for g, kind in garments.items():
        for it in items_for(kind):
            r = {"garment": g, "id": it["id"], "stage": it["stage"], "what": it["what"], "view": it["view"],
                 "type": it["type"]}
            ch = choices_of(it)
            if ch:
                r["choices"] = ch
            if it.get("points"):
                r["points"] = it["points"]
            if views:
                r["crops"] = [crop_box(v, it, v.get("_L") or {}) for v in views]
            rows.append(r)
    return rows


def form_text(rows: list) -> str:
    L = ["Fill each row: {garment: {id: {\"value\": ..., \"points\": {name: [u, v]}, \"view\": i, \"confidence\": "
         "\"high|medium|low\"}}} or \"not visible\". Big to small; don't guess what a picture doesn't show."]
    st = None
    for r in rows:
        if r["stage"] != st:
            st = r["stage"]
            L.append(f"-- stage {st}: {checklist()['stages'][str(st)]}")
        extra = (f" choices: {', '.join(r['choices'])}" if r.get("choices") else "") + \
                (f" mark: {', '.join(r['points'])}" if r.get("points") else "")
        L.append(f"[{r['garment']}.{r['id']}] ({r['type']}, view {r['view']}) {r['what']}{extra}")
    return "\n".join(L)


def _prep_views(views: list, L: dict) -> list:
    out = []
    for v in views:
        v = dict(v)
        if v.get("image") and not v.get("size"):
            from PIL import Image
            v["size"] = list(Image.open(v["image"]).size)
        body_pts = {k: p for k, p in (v.get("points") or {}).items() if k in L}
        if v.get("camera") is None and len(body_pts) >= 3 and v.get("kind", "front") == "front":
            v["camera"] = fit_camera(body_pts, L, v["size"])
        v["_L"] = L
        out.append(v)
    return out


def _side_of(view: dict, pts: dict, p, name: str) -> str:
    """Which side a marked point belongs to: by its name's suffix, else (an arm or leg point marked on the other side
    because that side shows better) the nearer of the two wrists / ankles in the picture."""
    p = np.asarray(p, float)
    best = None
    for s_ in ("L", "R"):
        for j in ("wrist", "ankle", "knee", "elbow"):
            q = _img_landmark({**view, "points": pts}, f"{j}.{s_}")
            if q is not None:
                d = float(np.linalg.norm(q - p))
                if best is None or d < best[0]:
                    best = (d, s_)
    if best is not None:
        return best[1]
    return "R" if name.endswith(".R") else "L"


def _sample_colour(image: str, pts: list, r: int = 7) -> list:
    from PIL import Image
    a = np.asarray(Image.open(image).convert("RGB"), float)
    px = []
    for u, v in pts:
        u, v = int(round(u)), int(round(v))
        px.append(a[max(v - r, 0):v + r + 1, max(u - r, 0):u + r + 1].reshape(-1, 3))
    return [int(round(c)) for c in np.median(np.concatenate(px), 0)]


def reading(it: dict, ans, views: list) -> dict:
    """One answer turned into a target: {"value" (choice / count / bool / level / colour) or "t" (anchored) or
    "width_m" or "mm", "confidence", "view"}; {"visible": False} for "not visible"."""
    if ans is None:
        return {"visible": False, "why": "not answered"}
    if isinstance(ans, str) and ans.strip().lower() in ("not visible", "n/a", "unknown"):
        return {"visible": False, "why": "not visible"}
    if not isinstance(ans, dict):
        ans = {"value": ans}
    vi = int(ans.get("view", 0))
    v = views[vi] if views else {}
    out = {"view": vi, "confidence": ans.get("confidence", "medium")}
    pts = {**(v.get("points") or {}), **(ans.get("points") or {})}
    typ = it["type"]
    if typ == "length" and it.get("anchor") and it.get("points") and it["points"][0] in pts:
        side = _side_of(v, pts, pts[it["points"][0]], it["points"][0])
        a_n, b_n = _anchor_names(it, side)
        a, b = _img_landmark({**v, "points": pts}, a_n), _img_landmark({**v, "points": pts}, b_n)
        if a is None or b is None:
            return {"visible": False, "why": f"anchor {a_n} / {b_n} neither marked nor projectable"}
        out["t"] = round(_t(pts[it["points"][0]], a, b, a_n, b_n, image=True), 4)
        out["anchor"] = [a_n, b_n]
        out["at_px"] = list(map(float, pts[it["points"][0]]))
    elif typ == "length" and it.get("points") and all(p in pts for p in it["points"]) and v.get("camera"):
        p0, p1 = (np.asarray(pts[p], float) for p in it["points"][:2])
        s = v["camera"]["s"]
        d = (p1 - p0)
        if it["id"] == "cuff_show":  # signed along the forearm (elbow -> wrist): + = the cuff past the sleeve
            sd = _side_of(v, pts, p0, it["points"][0])
            e, w = _img_landmark({**v, "points": pts}, f"elbow.{sd}"), _img_landmark({**v, "points": pts}, f"wrist.{sd}")
            ax = (w - e) / np.linalg.norm(w - e)
            out["mm"] = round(float(d @ ax / s * 1000), 1)
        else:
            out["mm"] = round(float(np.linalg.norm(d) / s * 1000), 1)
        out["at_px"] = [list(map(float, p0)), list(map(float, p1))]
    elif typ == "width" and it.get("points") and all(p in pts for p in it["points"]) and v.get("camera"):
        p0, p1 = (np.asarray(pts[p], float) for p in it["points"][:2])
        out["width_m"] = round(float(abs(p1[0] - p0[0]) if it["id"] != "sleeve_width" else np.linalg.norm(p1 - p0))
                               / v["camera"]["s"], 4)
        out["at_px"] = [list(map(float, p0)), list(map(float, p1))]
    elif typ == "colour" and (ans.get("points") or ans.get("value")):
        if ans.get("value") is not None:
            out["value"] = ans["value"]
        else:
            out["value"] = _sample_colour(v["image"], list((ans.get("points") or {}).values()))
            out["at_px"] = [list(map(float, p)) for p in ans["points"].values()]
    elif "value" in ans:
        out["value"] = ans["value"]
        ch = choices_of(it)
        if typ in ("choice", "level") and ch and ans["value"] not in ch and it.get("choices") != ["none", "<garment name>"]:
            raise ValueError(f"{it['id']}: {ans['value']!r} is not one of {ch}")
    else:
        return {"visible": False, "why": "no value or points"}
    if ans.get("note"):
        out["note"] = ans["note"]
    out["visible"] = True
    return out


def _sheet_patch(g: str, kind: str, targets: dict) -> dict:
    """What the readings say the design sheet should hold (choices and states; numbers are targets, see `sets`)."""
    p, design, details = {}, {}, {}
    for iid, t in targets.items():
        if not t.get("visible") or "value" not in t:
            continue
        it = t["_item"]
        v = t["value"]
        if it.get("detail") and v in choices_of(it):
            details[it["detail"]] = v
        elif iid == "fabric":
            design["fabric"] = v
        elif iid == "colour":
            p["color"] = "#%02x%02x%02x" % tuple(v) if isinstance(v, list) else v
        elif iid == "front_state" and v == "open":  # "closed" leaves the kind's own wear (a shirt's top button)
            p.setdefault("closures", []).append({"name": "front", "state": v})
        elif iid == "buttons_done" and isinstance(v, int):
            n = (targets.get("button_count") or {}).get("value")
            st = "open" if v == 0 else "closed" if (n is not None and v >= n) else {"open_top": max(int(n or v) - v, 0)}
            if not any(c["name"] == "front" for c in p.get("closures", [])) or v > 0:
                p["closures"] = [c for c in p.get("closures", []) if c["name"] != "front"] + [{"name": "front", "state": st}]
        elif iid == "collar_state":
            p["tie"] = v == "closed"
        elif iid == "belt" and isinstance(v, bool):
            details["belt"] = "leather" if v else "none"
            details["belt_loops"] = "loops" if v else "none"
        elif iid == "crease" and isinstance(v, bool):
            details["crease"] = "pressed" if v else "none"
        elif iid == "placket":
            p.setdefault("closures", []).append({"name": "front", "finish": {"over": v}})
        elif iid == "layering" and v not in ("none", None):
            p["over"] = v
    if p.get("closures"):  # one entry per closure name, keys merged
        merged = {}
        for e in p["closures"]:
            merged.setdefault(e["name"], {}).update(e)
        p["closures"] = list(merged.values())
    if details:
        design["details"] = details
    if design:
        design["kind"] = kind
        p["design"] = design
    return p


def read(model: str, garments: dict, views: list, answers: dict | None = None, spec: dict | None = None,
         save: str | Path | None = None) -> dict:
    """Read reference art into design sheets + a target table. garments: {name: kind}. views: [{"image", "kind":
    "front" | "side" | "back" | "three" | "other", "points": {landmark: [u, v]}, "crops": {item id: [u0, v0, u1, v1]}}]
    (body landmarks: cloth_reference.LANDMARK_NAMES; 3+ of them on a front view fit its camera). answers: {garment:
    {item id: answer}} (see form_text); without them only the form comes back."""
    from . import cloth, store
    spec = spec or store.load(model)
    body = cloth.Body(cloth.body_mesh(spec=spec))
    L = landmarks(body)
    vs = _prep_views(views, L)
    out = {"cameras": [v.get("camera") for v in vs], "form": form(garments, vs)}
    if answers is None:
        out["text"] = form_text(out["form"])
        return out
    targets, sheets = {}, {}
    for g, kind in garments.items():
        tg = {}
        for it in items_for(kind):
            r = reading(it, (answers.get(g) or {}).get(it["id"]), vs)
            r["_item"] = it
            tg[it["id"]] = r
        sheets[g] = _sheet_patch(g, kind, tg)
        targets[g] = {k: {kk: vv for kk, vv in r.items() if kk != "_item"} for k, r in tg.items()}
    out.update(targets=targets, sheets=sheets, garments=garments)
    refs = {"views": [{k: v_ for k, v_ in v.items() if k != "_L"} for v in vs], "garments": garments,
            "targets": targets, "sheets": sheets, "answers": answers}
    out["refs"] = refs
    if save:
        Path(save).write_text(json.dumps(refs, indent=1, default=_json_default))
    out["text"] = read_text(out)
    return out


def _json_default(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    raise TypeError(type(o).__name__)


def read_text(out: dict) -> str:
    L = []
    for i, c in enumerate(out["cameras"]):
        if c:
            worst = sorted(c["residual_mm"].items(), key=lambda kv: -kv[1])[:3]
            L.append(f"view {i}: camera {c['px_per_m']} px/m; landmark residuals worst {worst} mm")
        else:
            L.append(f"view {i}: no camera (choices and colours only)")
    for g, tg in out["targets"].items():
        L.append(f"== {g}: design-sheet patch {json.dumps(out['sheets'][g])}")
        for iid, t in tg.items():
            if not t.get("visible"):
                L.append(f"  {iid}: - ({t.get('why')})")
                continue
            val = t.get("value", t.get("t", t.get("width_m", t.get("mm"))))
            key = "value" if "value" in t else "t" if "t" in t else "width_m" if "width_m" in t else "mm"
            L.append(f"  {iid}: {key} {val} ({t.get('confidence')})" + (f" [{t['note']}]" if t.get("note") else ""))
    return "\n".join(L)


# ---------------------------------------------------------------- our side: measures on a simulated garment


class Ctx:
    """What the measures read: the model, its body and landmarks, and each garment's result (full or light)."""

    def __init__(self, model: str, spec: dict, results: dict, body=None):
        from . import cloth
        self.model, self.spec = model, spec
        self.body = body or cloth.Body(cloth.body_mesh(spec=spec))
        self.L = landmarks(self.body)
        self.results = {g: _light(r) for g, r in results.items() if r is not None}
        self.full = {g: r for g, r in results.items() if isinstance(r, dict) and "mesh" in r}

    def g(self, gname: str) -> dict:
        return (self.spec.get("cloth") or {}).get(gname) or {}

    def gx(self, gname: str) -> dict:
        from . import cloth
        return cloth.expanded(self.g(gname))

    def kind(self, gname: str) -> str | None:
        from . import cloth
        g = self.g(gname)
        d = (g.get("design") or {}).get("kind")
        if d:
            return d
        try:
            return cloth.garment_kind(g)
        except Exception:
            return None


def _light(r) -> dict:
    """{"V", "F", "piece" (index), "names", "roles"} from a full result, an npz path or a dict."""
    from . import garment_design
    if isinstance(r, (str, Path)):
        path = Path(r)
        z = np.load(path, allow_pickle=True)
        r = {k: z[k] for k in z.files}
        side = path.with_suffix(".json")  # a light copy's closures rows, saved beside it
        if side.exists():
            meta = json.loads(side.read_text())
            if meta.get("closures") is not None:
                r["closures"] = meta["closures"]
    if "mesh" in r:
        M = r["mesh"]
        d = {"V": np.asarray(r["V"], float), "F": np.asarray(M["F"]), "piece": np.asarray(M["piece"]),
             "names": [str(n) for n in M["names"]], "uv": np.asarray(M["uv"])}
    else:
        d = {"V": np.asarray(r["V"], float), "F": np.asarray(r["F"]), "piece": np.asarray(r["piece"]),
             "names": [str(n) for n in r["names"]]}
    d["roles"] = [garment_design.role_of(n) for n in d["names"]]
    if r.get("closures") is not None:  # closures.measure rows (a full result's, or carried beside a light one)
        d["closures"] = list(r["closures"])
    return d


def _verts(R: dict, roles=None, not_roles=(), side: str | None = None) -> np.ndarray:
    ks = [k for k, ro in enumerate(R["roles"]) if (roles is None or ro in roles) and ro not in not_roles]
    sel = np.isin(R["piece"], ks)
    if side == "L":
        sel &= R["V"][:, 0] > 0.0
    elif side == "R":
        sel &= R["V"][:, 0] < 0.0
    return np.where(sel)[0]


def _extent_x(V: np.ndarray, z: float, band: float = 0.012):
    s = np.abs(V[:, 2] - z) < band
    if s.sum() < 3:
        return None
    return float(V[s, 0].max() - V[s, 0].min())


class NotMeasured(Exception):
    pass


def _need(R: dict | None, what: str):
    if R is None:
        raise NotMeasured(f"no result for {what}")
    return R


def m_hem_cf(c: Ctx, g: str):
    R = _need(c.results.get(g), g)
    v = _verts(R, roles=("front",), side="L")
    if not len(v):
        v = _verts(R, not_roles=NOT_TORSO, side="L")
    i = v[np.argmin(R["V"][v, 2])]
    return {"point": R["V"][i]}


def m_hem_cb(c: Ctx, g: str):
    R = _need(c.results.get(g), g)
    v = _verts(R, roles=("back", "skirt_back"))
    v = v[np.abs(R["V"][v, 0]) < 0.06]
    if not len(v):
        raise NotMeasured("no back piece near centre back")
    return {"point": R["V"][v[np.argmin(R["V"][v, 2])]]}


def m_sleeve_end(c: Ctx, g: str):
    R = _need(c.results.get(g), g)
    v = _verts(R, roles=SLEEVE_ROLES, side="L")
    if not len(v):
        raise NotMeasured("no sleeve pieces")
    e, w = c.L["elbow.L"], c.L["wrist.L"]
    t = (R["V"][v] - e) @ (w - e) / ((w - e) @ (w - e))
    k = v[np.argsort(t)[int(0.99 * (len(t) - 1))]]
    return {"point": R["V"][k]}


def m_trouser_hem(c: Ctx, g: str):
    R = _need(c.results.get(g), g)
    v = _verts(R, not_roles=("waistband", "belt", "pocket", "fly"), side="L")
    v = v[R["V"][v, 1] < c.L["ankle.L"][1] - 0.01]
    if not len(v):
        raise NotMeasured("no leg cloth in front of the ankle")
    return {"point": R["V"][v[np.argmin(R["V"][v, 2])]]}


def _width(c: Ctx, g: str, z: float, roles=None, not_roles=(), side=None, band=0.012):
    R = _need(c.results.get(g), g)
    v = _verts(R, roles=roles, not_roles=not_roles, side=side)
    w = _extent_x(R["V"][v], z, band)
    if w is None:
        raise NotMeasured(f"no cloth at z {z:.3f}")
    return {"width_m": w, "z": z}


def m_shoulder_width(c, g):
    return _width(c, g, float(c.body.at["shoulder.L"][2]) - 0.02, band=0.02)


def m_chest_width(c, g):
    return _width(c, g, float(c.body.at["armpit_z"]) - 0.025, not_roles=SLEEVE_ROLES)


def m_waist_width(c, g):
    return _width(c, g, float(c.body.at["waist_z"]), not_roles=SLEEVE_ROLES)


def m_hem_sweep(c, g):
    R = _need(c.results.get(g), g)
    v = _verts(R, not_roles=NOT_TORSO)
    return _width(c, g, float(R["V"][v, 2].min()) + 0.03, not_roles=NOT_TORSO)


def m_seat_width(c, g):
    return _width(c, g, float(c.body.at["seat_z"]), not_roles=("belt", "pocket"))


def m_knee_width(c, g):
    return _width(c, g, float(c.L["knee.L"][2]), side="L", not_roles=("pocket",))


def m_leg_opening(c, g):
    R = _need(c.results.get(g), g)
    v = _verts(R, side="L", not_roles=("pocket", "waistband", "belt"))
    zt = float(c.L["ankle.L"][2]) + 0.06
    return _width(c, g, zt, side="L", not_roles=("pocket", "waistband", "belt"))


def m_sleeve_opening(c, g):
    R = _need(c.results.get(g), g)
    v = _verts(R, roles=SLEEVE_ROLES, side="L")
    if not len(v):
        raise NotMeasured("no sleeve pieces")
    e, w = c.L["elbow.L"], c.L["wrist.L"]
    ax = (w - e) / np.linalg.norm(w - e)
    t = (R["V"][v] - e) @ ax
    near = v[t > t.max() - 0.04]
    a2 = np.array([ax[0], ax[2]]) / np.linalg.norm([ax[0], ax[2]])
    perp = np.array([-a2[1], a2[0]])
    q = R["V"][near][:, [0, 2]] @ perp
    return {"width_m": float(q.max() - q.min())}


def m_front_hang(c, g):
    R = _need(c.results.get(g), g)
    v = _verts(R, roles=("front",))
    if not len(v):
        raise NotMeasured("no front pieces")
    V = R["V"]
    zh = V[v, 2].min()
    hem = v[V[v, 2] < zh + 0.04]
    B = c.body.V
    B = B[np.abs(B[:, 0]) < 0.2]
    dz = np.abs(B[:, 2] - c.body.at["chest_z"])
    ch = B[dz <= max(0.02, float(np.sort(dz)[min(20, len(dz) - 1)]))]
    return {"mm": float(ch[:, 1].min() - V[hem, 1].min()) * 1000}


def m_waistband(c, g):
    R = _need(c.results.get(g), g)
    v = _verts(R, roles=("waistband",))
    if not len(v):
        raise NotMeasured("no waistband piece")
    V = R["V"]
    f = v[(V[v, 1] < np.median(V[v, 1])) & (np.abs(V[v, 0]) < 0.08)]
    f = f if len(f) else v
    return {"point": V[f[np.argmax(V[f, 2])]]}


def _closure_rows(c: Ctx, g: str):
    R = c.results.get(g)
    return None if R is None else R.get("closures")


def _closure_entry(c: Ctx, g: str, name: str = "front") -> dict:
    from . import garment_design
    gx = c.gx(g)
    ent = {}
    for e in garment_design.wear(gx):
        if e.get("name") == name:
            ent.update(e)
    for e in gx.get("closures") or []:
        if e.get("name") == name:
            ent.update(e)
    return ent


def m_button_count(c, g):
    gx = c.gx(g)
    for op in ((gx.get("_design") or gx.get("design") or {}).get("ops") or []):
        if op.get("op") == "buttons":
            return {"value": int(op.get("n", 1))}
    rows = _closure_rows(c, g)
    if rows:
        for r in rows:
            if r["name"] == "front":
                return {"value": int(r["fastenings"])}
    raise NotMeasured("no buttons op and no closures in this result")


def m_buttons_done(c, g):
    rows = _closure_rows(c, g)
    if rows:
        for r in rows:
            if r["name"] == "front":
                return {"value": int(r["closed"]), "source": "sim"}
    st = _closure_entry(c, g).get("state", "closed")
    n = m_button_count(c, g)["value"]
    if st == "open":
        return {"value": 0, "source": "spec"}
    if isinstance(st, dict) and "open_top" in st:
        return {"value": max(n - int(st["open_top"]), 0), "source": "spec"}
    return {"value": n, "source": "spec"}


def m_front_state(c, g):
    st = _closure_entry(c, g).get("state", "closed")
    return {"value": "open" if st == "open" else "closed"}


def m_collar_state(c, g):
    st = _closure_entry(c, g, "collar").get("state", "closed")
    return {"value": "open" if st == "open" or (isinstance(st, dict)) else "closed"}


def m_placket_finish(c, g):
    fin = (_closure_entry(c, g).get("finish") or {}).get("over", "box")
    return {"value": fin}


def _design_details(c: Ctx, g: str) -> dict:
    from . import garment_design
    gx = c.gx(g)
    sheet = dict(gx.get("_design") or gx.get("design") or {})
    sheet.setdefault("kind", c.kind(g))
    if not sheet.get("kind"):
        return {}
    try:
        return {d: info["choice"] for d, info in (garment_design.resolve(sheet).get("details") or {}).items()}
    except Exception:  # a sheet the resolver refuses: the kind's defaults with the sheet's own choices on top
        dd = dict(_kb()["kinds"].get(sheet["kind"], {}).get("details") or {})
        dd.update(sheet.get("details") or {})
        return {k: (v if isinstance(v, str) else v.get("choice")) for k, v in dd.items()}


def m_detail_choice(c, g, it):
    d = _design_details(c, g)
    v = d.get(it["detail"])
    if v is None:
        if d:  # the kind has no such detail by default: none made
            return {"value": "none", "note": f"no {it['detail']} in the resolved sheet"}
        raise NotMeasured(f"no {it['detail']} in the resolved sheet")
    return {"value": v if isinstance(v, str) else (v.get("choice") if isinstance(v, dict) else str(v))}


def m_has_belt(c, g):
    """A belt you can SEE: chosen in the sheet (details belt, the trims that draw it) and not covered at the front by
    an untucked garment hanging past the waistband (Garrett's shirt hung over the trousers' waist: "no belt")."""
    d = _design_details(c, g)
    chosen = d.get("belt") not in (None, "none")
    out = {"value": bool(chosen)}
    if not chosen:
        return out
    try:
        zb = float(m_waistband(c, g)["point"][2])
    except NotMeasured:
        return out
    under = c.g(g).get("over")
    for o, R in c.results.items():
        if o == g or o == under or c.g(o).get("over") == g:
            continue
        v = _verts(R, not_roles=NOT_TORSO)
        f = v[(np.abs(R["V"][v, 0]) < 0.08) & (R["V"][v, 1] < np.median(R["V"][v, 1]))]
        # an open jacket's fronts hang to the sides of the centre front: only cloth across the middle hides the belt
        mid = f[np.abs(R["V"][f, 0]) < 0.03]
        if len(mid) and R["V"][mid, 2].min() < zb - 0.02:
            out.update(value=False, note=f"a belt is chosen but {o} hangs over the waistband at the centre front (untucked)")
            return out
    return out


def m_has_crease(c, g):
    return {"value": _design_details(c, g).get("crease") not in (None, "none")}


def m_tucked(c, g):
    return {"value": any((c.g(o).get("over") == g) and (c.kind(o) or "") in ("trousers", "suit_trousers", "skirt", "shorts")
                         for o in (c.spec.get("cloth") or {}))}


def m_over(c, g):
    return {"value": c.g(g).get("over") or "none"}


def m_fabric(c, g):
    gx = c.gx(g)
    f = (gx.get("_design") or {}).get("fabric")
    if not f and gx.get("_design"):
        f = (_kb()["kinds"].get(c.kind(g) or "", {}) or {}).get("fabric")
    f = f or gx.get("fabric")
    if isinstance(f, dict):
        f = f.get("name") or f.get("preset")
    if isinstance(f, str) and f not in _kb()["fabrics"]:  # a solver preset name: the KB fabric made with it
        for k, v in _kb()["fabrics"].items():
            if isinstance(v, dict) and v.get("preset") == f:
                return {"value": k, "note": f"preset {f!r} read as {k}"}
    return {"value": f}


def m_colour(c, g):
    col = c.gx(g).get("color")
    if not col:
        raise NotMeasured("no colour set")
    col = col.lstrip("#")
    return {"value": [int(col[i:i + 2], 16) for i in (0, 2, 4)]}


def _fabric_entry(name):
    fb = _kb()["fabrics"]
    if isinstance(name, dict):  # {preset, overrides}
        name = name.get("preset")
    if name in fb:
        return fb[name]
    for k, v in fb.items():
        if isinstance(v, dict) and v.get("preset") == name:
            return v
    return None


def m_drape_level(c, g):
    f = _fabric_entry(m_fabric(c, g)["value"])
    if not f or "bending_length_mm" not in f:
        raise NotMeasured("fabric without a bending length")
    b = float(np.mean(f["bending_length_mm"]))
    return {"value": "soft" if b < 12 else "medium" if b <= 18 else "crisp", "bending_length_mm": b}


def crinkle_deg(V: np.ndarray, F: np.ndarray) -> float:
    """Median angle between neighbouring triangles' normals (deg): how rumpled a cloth surface is."""
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    fi = np.tile(np.arange(len(F)), 3)
    key = np.sort(E, 1)
    order = np.lexsort((key[:, 1], key[:, 0]))
    k, f = key[order], fi[order]
    same = (k[1:] == k[:-1]).all(1)
    a, b = f[:-1][same], f[1:][same]
    ang = np.degrees(np.arccos(np.clip((n[a] * n[b]).sum(1), -1, 1)))
    return float(np.median(ang)) if len(ang) else 0.0


def m_fold_level(c, g):
    R = _need(c.results.get(g), g)
    cr = crinkle_deg(R["V"], R["F"])
    h = float(np.median(np.linalg.norm(R["V"][R["F"][:, 0]] - R["V"][R["F"][:, 1]], axis=1)))
    # a coarse mesh reads more angle for the same folds: normalise to 1 cm edges
    crn = cr * 0.01 / max(h, 1e-4)
    return {"value": "clean" if crn < 4 else "some folds" if crn < 8 else "rumpled", "crinkle_deg": round(cr, 1),
            "edge_mm": round(h * 1000, 1)}


def m_silhouette(c, g):
    if (c.kind(g) or "") in ("trousers", "suit_trousers", "shorts"):
        kn, op = m_knee_width(c, g)["width_m"], m_leg_opening(c, g)["width_m"]
        lv = "fitted" if op < 0.8 * kn else "flared" if op > 1.05 * kn else "straight"
        return {"value": lv, "knee_m": round(kn, 3), "opening_m": round(op, 3)}
    try:
        ch, wa = m_chest_width(c, g)["width_m"], m_waist_width(c, g)["width_m"]
        he = m_hem_sweep(c, g)["width_m"]
    except NotMeasured:
        raise
    lv = "flared" if he > 1.25 * wa else "fitted" if wa < 0.97 * ch else "boxy" if he < 1.02 * ch and wa >= ch else "straight"
    return {"value": lv, "chest_m": round(ch, 3), "waist_m": round(wa, 3), "hem_m": round(he, 3)}


def _arm_t(c: Ctx, p) -> float:
    e, w = c.L["elbow.L"], c.L["wrist.L"]
    return float((p - e) @ (w - e))


def m_tell(c: Ctx, g: str, which: str):
    """The layered tells (cloth_layers.tells' definitions), on full or light results: the under garment is the one
    this garment is `over`."""
    ug = c.g(g).get("over")
    if not ug:
        raise NotMeasured("not layered (no `over`)")
    O, U = c.results.get(g), c.results.get(ug)
    if O is None or U is None:
        raise NotMeasured(f"needs both results ({g}, {ug})")
    if which == "collar_show_mm":
        yc = float(c.body.J["neck"][1]) if "neck" in c.body.J else 0.0
        co = _verts(O, roles=("collar_stand", "collar_fall"))
        cu = _verts(U, roles=("collar_stand", "collar_fall"))
        bo = co[(np.abs(O["V"][co, 0]) < 0.025) & (O["V"][co, 1] > yc)]
        bu = cu[(np.abs(U["V"][cu, 0]) < 0.025) & (U["V"][cu, 1] > yc)]
        if not (len(bo) and len(bu)):
            raise NotMeasured("no collar at centre back")
        return {"mm": float(U["V"][bu, 2].max() - O["V"][bo, 2].max()) * 1000}
    if which == "cuff_show_mm":
        e, w = c.L["elbow.L"], c.L["wrist.L"]
        ax = (w - e) / np.linalg.norm(w - e)
        so, su = _verts(O, roles=SLEEVE_ROLES, side="L"), _verts(U, roles=SLEEVE_ROLES, side="L")
        if not (len(so) and len(su)):
            raise NotMeasured("no sleeves")
        return {"mm": float(np.percentile((U["V"][su] - e) @ ax, 99) - np.percentile((O["V"][so] - e) @ ax, 99)) * 1000}
    if which == "collar_hug_mm":
        from scipy.spatial import cKDTree
        co = _verts(O, roles=("collar_stand", "collar_fall"))
        cu = _verts(U, roles=("collar_stand", "collar_fall"))
        if not (len(co) and len(cu)):
            raise NotMeasured("no collars")
        d, _ = cKDTree(U["V"][cu]).query(O["V"][co])
        return {"mm": float(np.median(d)) * 1000}
    if which == "lapel_gap_mm":
        full = c.full.get(g)
        t = (full or {}).get("tells") or {}
        if t.get("lapel_gap_mm"):
            v = t["lapel_gap_mm"]["value"]
            return {"mm": float(np.median(v if isinstance(v, list) else [v]))}
        raise NotMeasured("lapel gap needs the full result (fold rows)")
    raise NotMeasured(which)


def m_lapel_width(c, g):
    """The lapel's width as drafted (op lapel `width`, m): the sim's flap isn't measured on a light result. A front
    view sees it a little narrower (the chest curves away): the reading is compared as it is."""
    for op in ((c.gx(g).get("_design") or {}).get("ops") or []):
        if op.get("op") == "lapel" and op.get("width"):
            return {"width_m": float(op["width"]), "source": "pattern", "note": "drafted width, not measured on the sim"}
    raise NotMeasured("no lapel op with a width")


def m_top_button(c, g):
    full = c.full.get(g)
    if full is None or not full.get("buttons"):
        raise NotMeasured("button positions need the full result (res['buttons']); a light result has none")
    P = np.asarray(full["buttons"].get("centres", full["buttons"].get("P", [])), float).reshape(-1, 3)
    if not len(P):
        raise NotMeasured("no button centres in the result")
    return {"point": P[np.argmax(P[:, 2])]}


def _measure_fn(name: str):
    simple = {"hem_cf_z": m_hem_cf, "hem_cb_z": m_hem_cb, "sleeve_end_t": m_sleeve_end, "trouser_hem_z": m_trouser_hem,
              "shoulder_width": m_shoulder_width, "chest_width": m_chest_width, "waist_width": m_waist_width,
              "hem_sweep": m_hem_sweep, "seat_width": m_seat_width, "knee_width": m_knee_width,
              "leg_opening": m_leg_opening, "sleeve_opening": m_sleeve_opening, "front_hang": m_front_hang,
              "waistband_z": m_waistband, "button_count": m_button_count, "buttons_done": m_buttons_done,
              "front_state": m_front_state, "collar_state": m_collar_state, "placket_finish": m_placket_finish,
              "has_belt": m_has_belt, "has_crease": m_has_crease, "tucked": m_tucked, "over": m_over,
              "fabric": m_fabric, "colour": m_colour, "drape_level": m_drape_level, "fold_level": m_fold_level,
              "silhouette_shape": m_silhouette, "lapel_width": m_lapel_width, "top_button_z": m_top_button}
    return simple.get(name)


MEASURES = sorted(["hem_cf_z", "hem_cb_z", "sleeve_end_t", "trouser_hem_z", "shoulder_width", "chest_width",
                   "waist_width", "hem_sweep", "seat_width", "knee_width", "leg_opening", "sleeve_opening",
                   "front_hang", "waistband_z", "button_count", "buttons_done", "front_state", "collar_state",
                   "placket_finish", "has_belt", "has_crease", "tucked", "over", "fabric", "colour", "drape_level",
                   "fold_level", "silhouette_shape", "lapel_width", "top_button_z", "detail_choice", "tell:collar_show_mm", "tell:cuff_show_mm",
                   "tell:collar_hug_mm", "tell:lapel_gap_mm"])


def measure(c: Ctx, g: str, it: dict) -> dict:
    """Our garment's reading for one item: {"point"} / {"width_m"} / {"mm"} / {"value"} (+ notes), or raises
    NotMeasured (a missing measure says why)."""
    m = it["measure"]
    if m.startswith("missing"):
        raise NotMeasured(m)
    if m.startswith("tell:"):
        return m_tell(c, g, m[5:])
    if m == "detail_choice":
        return m_detail_choice(c, g, it)
    fn = _measure_fn(m)
    if fn is None:
        raise NotMeasured(f"measure {m!r} unknown")
    return fn(c, g)


# ---------------------------------------------------------------- checking


def _lab(rgb):
    c = np.asarray(rgb, float) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = M @ c / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def compare(it: dict, ref: dict, ours: dict, c: Ctx) -> dict:
    """One row: the miss in the item's units and in tolerances (severity)."""
    typ, tol = it["type"], float(it.get("tolerance", 0) or 0)
    row = {"id": it["id"], "stage": it["stage"]}
    if "t" in ref and "point" in ours:
        # our measures read the left side (+X): a reading taken on the right (it showed better) is the same fraction
        a_n, b_n = (n.replace(".R", ".L") for n in (ref.get("anchor") or _anchor_names(it, "L")))
        A, B = c.L[a_n], c.L[b_n]
        t_o = _t(ours["point"], A, B, a_n, b_n)
        L_ab = float(abs(B[2] - A[2])) if _vertical(a_n, b_n) else float(np.linalg.norm(B - A))
        miss = (t_o - ref["t"]) * L_ab * 1000
        row.update(ref=f"t {ref['t']:.3f}", ours=f"t {t_o:.3f}", miss=round(miss, 1), units="mm",
                   detail=f"along {a_n} -> {b_n} ({L_ab * 1000:.0f} mm on our body); + = ours further toward {b_n}")
        row["severity"] = abs(miss) / max(tol, 1e-6)
        row["_pt_ours"] = ours["point"]
    elif "width_m" in ref and "width_m" in ours:
        sh = ours["width_m"] / ref["width_m"] - 1
        row.update(ref=f"{ref['width_m'] * 1000:.0f} mm", ours=f"{ours['width_m'] * 1000:.0f} mm", miss=round(sh, 3),
                   units="share", detail="front-view width; + = ours wider")
        row["severity"] = abs(sh) / max(tol, 1e-6)
    elif "mm" in ours and ("mm" in ref or it.get("target_mm")):
        if "mm" in ref:
            miss = ours["mm"] - ref["mm"]
            row.update(ref=f"{ref['mm']:.1f} mm", ours=f"{ours['mm']:.1f} mm", miss=round(miss, 1), units="mm")
            row["severity"] = abs(miss) / max(tol, 1e-6)
        else:
            lo, hi = it["target_mm"]
            v = ours["mm"]
            miss = 0.0 if lo <= v <= hi else (v - hi if v > hi else v - lo)
            row.update(ref=f"rule {lo}..{hi} mm", ours=f"{v:.1f} mm", miss=round(miss, 1), units="mm",
                       detail="no reading: judged against the tailoring rule")
            row["severity"] = abs(miss) / max(tol, 1e-6)
            row["source"] = "rule"
    elif typ == "colour" and "value" in ref and "value" in ours:
        de = float(np.linalg.norm(_lab(ref["value"]) - _lab(ours["value"])))
        row.update(ref="#%02x%02x%02x" % tuple(ref["value"]), ours="#%02x%02x%02x" % tuple(ours["value"]),
                   miss=round(de, 1), units="deltaE", detail="the reference is LIT colour, ours the albedo: read with care")
        row["severity"] = de / max(tol, 1e-6)
    elif "value" in ref and "value" in ours:
        rv, ov = ref["value"], ours["value"]
        if typ == "level" and it.get("scale") and rv in it["scale"] and ov in it["scale"]:
            d = it["scale"].index(ov) - it["scale"].index(rv)
            row.update(ref=rv, ours=ov, miss=d, units="steps")
            row["severity"] = abs(d) / max(tol, 1) * (1.0 if abs(d) <= tol else 1.5)
        else:
            same = (str(rv).lower() == str(ov).lower())
            row.update(ref=rv, ours=ov, miss=0 if same else 1, units="match")
            row["severity"] = 0.0 if same else CHOICE_MISS
    elif "mm" in ours and it["type"] == "level" and it.get("target_mm"):
        lo, hi = it["target_mm"]
        v = ours["mm"]
        miss = 0.0 if lo <= v <= hi else (v - hi if v > hi else v - lo)
        row.update(ref=f"rule {lo}..{hi} mm", ours=f"{v:.1f} mm", miss=round(miss, 1), units="mm", source="rule")
        row["severity"] = abs(miss) / max(hi - lo, 1.0)
    else:
        row.update(ref=str({k: v for k, v in ref.items() if k not in ('at_px',)})[:60], ours=str(ours)[:60],
                   miss=None, severity=0.0, note="readings not comparable")
    for k in ("note", "source", "bending_length_mm", "crinkle_deg", "edge_mm"):
        if k in ours and k not in row:
            row[k] = ours[k]
    w = CONF_W.get(ref.get("confidence", "medium"), 0.75)
    row["confidence"] = ref.get("confidence", "medium")
    row["score"] = round(row["severity"] * STAGE_WEIGHT.get(it["stage"], 1.0) * w, 2)
    row["sets"] = it.get("sets", "")
    return row


def check(model: str, garments: list | None, refs, results: dict | None = None, spec: dict | None = None,
          panels: str | Path | None = None, top: int = 9) -> dict:
    """Our garments against a reading (`refs`: read()'s refs, or the path of a saved one). results: {garment: full
    result | light dict | npz path}; missing garments are taken from the cache (cloth.cached: never simulates).
    Returns {"rows": {garment: [row]}, "ranked": misses (severity > 1) by score, "unjudged": [...], "text"} and, with
    `panels`, writes the focus sheet there."""
    from . import cloth, store
    spec = spec or store.load(model)
    if isinstance(refs, (str, Path)):
        refs = json.loads(Path(refs).read_text())
    gk = refs["garments"]
    garments = list(garments or gk)
    results = dict(results or {})
    need = set(garments) | {spec["cloth"][g].get("over") for g in garments if spec["cloth"][g].get("over")}
    for g in need:
        if g and g not in results:
            results[g] = cloth.cached(model, spec, g)
    c = Ctx(model, spec, results)
    rows, unjudged, ranked = {}, [], []
    items = {it["id"]: it for it in checklist()["items"]}
    for g in garments:
        rows[g] = []
        for iid, ref in refs["targets"][g].items():
            it = items.get(iid)
            if it is None:
                continue
            try:
                ours = measure(c, g, it)
            except NotMeasured as e:
                if ref.get("visible") or it.get("target_mm"):
                    unjudged.append({"garment": g, "id": iid, "stage": it["stage"], "why": str(e), "sets": it.get("sets")})
                continue
            if not ref.get("visible"):
                if it.get("target_mm") and "mm" in ours:
                    ref = {"visible": False, "confidence": "medium"}
                else:
                    unjudged.append({"garment": g, "id": iid, "stage": it["stage"], "why": f"reference: {ref.get('why')}",
                                     "ours": {k: v for k, v in ours.items() if k != "point"}})
                    continue
            row = compare(it, ref, ours, c)
            row["garment"] = g
            row["_ref"] = ref
            rows[g].append(row)
            if row["severity"] > 1.0:
                ranked.append(row)
    ranked.sort(key=lambda r: -r["score"])
    out = {"rows": rows, "ranked": ranked, "unjudged": unjudged}
    out["text"] = check_text(out)
    if panels:
        out["panels"] = str(focus_sheet(c, refs, ranked[:top], panels))
    return out


def check_text(out: dict) -> str:
    L = [f"RANKED MISSES ({len(out['ranked'])}; score = misses in tolerances x stage weight x confidence):"]
    for k, r in enumerate(out["ranked"], 1):
        L.append(f"{k:2d}. {r['garment']}.{r['id']} (stage {r['stage']}, score {r['score']}): ref {r['ref']} | ours "
                 f"{r['ours']} | miss {r['miss']} {r['units']}" + (f" ({r['detail']})" if r.get("detail") else "")
                 + (f" [{r['source']}]" if r.get("source") else "") + f"  -> {r['sets']}")
    L.append("WITHIN TOLERANCE:")
    for g, rs in out["rows"].items():
        ok = [f"{r['id']} ({r['ours']})" for r in rs if r["severity"] <= 1.0]
        L.append(f"  {g}: " + (", ".join(ok) if ok else "-"))
    if out["unjudged"]:
        L.append("NOT JUDGED:")
        for u in out["unjudged"]:
            L.append(f"  {u['garment']}.{u['id']}: {u['why']}")
    return "\n".join(L)


# ---------------------------------------------------------------- pictures


def _faces_colour(hexcol: str | None, default=(150, 150, 150)):
    if not hexcol:
        return default
    h = hexcol.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _layer_rank(c: Ctx) -> dict:
    """Garments from the skin out: one worn `over` another comes after it (a jacket over a shirt, trousers over a
    tucked shirt)."""
    rank = {}

    def r(g, seen=()):
        if g in rank:
            return rank[g]
        u = c.g(g).get("over")
        rank[g] = 1 + (r(u, seen + (g,)) if u and u not in seen and u in c.results else 0)
        return rank[g]
    for g in c.results:
        r(g)
    return rank


def _zbuffer(P: np.ndarray, F: np.ndarray, shade: np.ndarray, cols: np.ndarray, W: int, H: int) -> np.ndarray:
    """Triangles (pixel x, pixel y, depth: smaller = nearer) rasterised with a depth buffer; per-vertex shade
    interpolated (Gouraud), per-face colour."""
    global _ZB
    if _ZB is not None:
        return _ZB(P, F, shade, cols, W, H)
    from numba import njit

    @njit
    def run(P, F, shade, cols, W, H):
        img = np.empty((H, W, 3), np.float64)
        img[:, :, 0] = 226.0
        img[:, :, 1] = 226.0
        img[:, :, 2] = 228.0
        zb = np.full((H, W), 1e18)
        for f in range(F.shape[0]):
            a, b, c = F[f, 0], F[f, 1], F[f, 2]
            x0, y0, z0 = P[a, 0], P[a, 1], P[a, 2]
            x1, y1, z1 = P[b, 0], P[b, 1], P[b, 2]
            x2, y2, z2 = P[c, 0], P[c, 1], P[c, 2]
            den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(den) < 1e-12:
                continue
            u0 = max(int(np.floor(min(x0, x1, x2))), 0)
            u1 = min(int(np.ceil(max(x0, x1, x2))), W - 1)
            v0 = max(int(np.floor(min(y0, y1, y2))), 0)
            v1 = min(int(np.ceil(max(y0, y1, y2))), H - 1)
            for v in range(v0, v1 + 1):
                for u in range(u0, u1 + 1):
                    px, py = u + 0.5, v + 0.5
                    l0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / den
                    l1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / den
                    l2 = 1.0 - l0 - l1
                    if l0 < 0 or l1 < 0 or l2 < 0:
                        continue
                    z = l0 * z0 + l1 * z1 + l2 * z2
                    if z < zb[v, u]:
                        zb[v, u] = z
                        sh = l0 * shade[a] + l1 * shade[b] + l2 * shade[c]
                        for k in range(3):
                            img[v, u, k] = min(cols[f, k] * sh + 14.0, 255.0)
        return img
    _ZB = run
    return run(P, F, shade, cols, W, H)


_ZB = None


def render_front(c: Ctx, cam: dict, scale: float = 1.0, offset: float = 0.012):
    """The body and the garments drawn through a reference's camera (front, orthographic, depth-buffered, soft
    shading), at the reference image's size x scale: our garment where the reference's is. Each garment is drawn
    `offset` m nearer per layer (skin out, by `over`) so an outer garment wins where a solver left them touching."""
    from PIL import Image
    w, h = cam["size"]
    W, H = int(w * scale), int(h * scale)
    rank = _layer_rank(c)
    layers = [(c.body.V, c.body.T, (198, 170, 150), 0)]
    for g, R in c.results.items():
        layers.append((R["V"], R["F"], _faces_colour(c.g(g).get("color")), rank.get(g, 1)))
    Ps, Fs, Ss, Cs = [], [], [], []
    n0 = 0
    Ld = np.array([0.35, -0.8, 0.5]) / np.linalg.norm([0.35, -0.8, 0.5])
    for V, F, col, k in layers:
        V, F = np.asarray(V, float), np.asarray(F, np.int64)
        uv = project(cam, V) * scale
        fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        vn = np.zeros_like(V)
        for j in range(3):
            np.add.at(vn, F[:, j], fn)
        vn /= np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12
        Ps.append(np.c_[uv, V[:, 1] - offset * k])
        Fs.append(F + n0)
        Ss.append(0.42 + 0.58 * np.abs(vn @ Ld))
        Cs.append(np.repeat(np.array(col, float)[None], len(F), 0))
        n0 += len(V)
    img = _zbuffer(np.concatenate(Ps), np.concatenate(Fs), np.concatenate(Ss), np.concatenate(Cs), W, H)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def focus_sheet(c: Ctx, refs: dict, rows: list, out: str | Path, cell: int = 300):
    """Per ranked miss: the reference crop | ours through the same camera (same box), the reading's points (red) and
    our measured point (blue) marked, a caption."""
    from PIL import Image, ImageDraw
    views = refs["views"]
    items = {it["id"]: it for it in checklist()["items"]}
    renders = {}
    tiles = []
    for r in rows:
        it = items[r["id"]]
        vi = int(r["_ref"].get("view", 0)) if r["_ref"].get("visible") else 0
        v = dict(views[vi])
        v["_L"] = c.L
        cam = v.get("camera")
        ref_im = Image.open(v["image"]).convert("RGB") if v.get("image") else None
        box = crop_box(v, it, c.L) if cam else None
        if box is None and ref_im is not None:
            box = [0, 0, ref_im.width, ref_im.height]
        left = ref_im.crop(box) if ref_im is not None else Image.new("RGB", (cell, cell), (90, 90, 90))
        sx, sy = cell / max(left.width, 1), cell / max(left.height, 1)
        sc = min(sx, sy)
        left = left.resize((max(int(left.width * sc), 1), max(int(left.height * sc), 1)))
        dl = ImageDraw.Draw(left)
        for p in _pts(r["_ref"].get("at_px")):
            q = ((p[0] - box[0]) * sc, (p[1] - box[1]) * sc)
            dl.ellipse([q[0] - 4, q[1] - 4, q[0] + 4, q[1] + 4], outline=(230, 30, 30), width=2)
        if cam is not None:
            if vi not in renders:
                renders[vi] = render_front(c, cam)
            right = renders[vi].crop(box).resize(left.size)
            dr = ImageDraw.Draw(right)
            for p in _pts(r["_ref"].get("at_px")):
                q = ((p[0] - box[0]) * sc, (p[1] - box[1]) * sc)
                dr.ellipse([q[0] - 4, q[1] - 4, q[0] + 4, q[1] + 4], outline=(230, 30, 30), width=2)
            if r.get("_pt_ours") is not None:
                p = project(cam, r["_pt_ours"])[0]
                q = ((p[0] - box[0]) * sc, (p[1] - box[1]) * sc)
                dr.ellipse([q[0] - 5, q[1] - 5, q[0] + 5, q[1] + 5], outline=(30, 60, 230), width=3)
        else:
            right = Image.new("RGB", left.size, (90, 90, 90))
        tile = Image.new("RGB", (2 * cell + 10, cell + 46), (245, 245, 245))
        tile.paste(left, (0, 0))
        tile.paste(right, (cell + 10, 0))
        dt = ImageDraw.Draw(tile)
        dt.text((4, cell + 4), f"{r['garment']}.{r['id']} (stage {r['stage']}, score {r['score']})", fill=(0, 0, 0))
        dt.text((4, cell + 18), f"ref {r['ref']} | ours {r['ours']} | miss {r['miss']} {r['units']}"[:90], fill=(160, 0, 0))
        dt.text((4, cell + 31), f"-> {r['sets']}"[:90], fill=(60, 60, 60))
        tiles.append(tile)
    if not tiles:
        tiles = [Image.new("RGB", (2 * cell + 10, cell + 46), (245, 245, 245))]
    cols = 3
    tw, th = tiles[0].size
    rows_n = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + 8), rows_n * (th + 8)), (200, 200, 200))
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % cols) * (tw + 8), (k // cols) * (th + 8)))
    sheet.save(out)
    return out


def _pts(at):
    if at is None:
        return []
    at = np.asarray(at, float)
    return at.reshape(-1, 2).tolist()


# ---------------------------------------------------------------- the reference brief (what pictures to ask for)

# The shots a garment artist asks for, as one figure in one outfit: a turnaround, detail close-ups, a raking pass.
SHOTS = [
    {"id": "front", "view": {"yaw": 0, "pitch": 0, "framing": "full"}, "light": "even",
     "must_show": ["the whole figure head to shoes, centred, square to the camera",
                   "every front button and whether it is done up; the shirt tucked or not; the belt"],
     "words": "seen straight from the front"},
    {"id": "side", "view": {"yaw": 90, "pitch": 0, "framing": "full"}, "light": "even",
     "must_show": ["the jacket's fronts hanging (straight, or standing forward at the hem)", "the trouser break on the shoe"],
     "words": "seen exactly from the figure's left side, in profile"},
    {"id": "back", "view": {"yaw": 180, "pitch": 0, "framing": "full"}, "light": "even",
     "must_show": ["the collars at the back of the neck (how much shirt collar shows above the jacket's)",
                   "the vent and the back hem"],
     "words": "seen straight from behind"},
    {"id": "three", "view": {"yaw": 45, "pitch": 0, "framing": "full"}, "light": "even",
     "must_show": ["the lapels lying on the chest", "the depth of the garments"],
     "words": "seen from three-quarters front, 45 degrees to the figure's left"},
    {"id": "collar", "view": {"yaw": 20, "pitch": 0, "framing": "close:neck_base"}, "light": "even",
     "must_show": ["the collar type, the lapel's width and notch, the gorge's height", "the shirt collar open or closed, its points"],
     "words": "close-up of the collar and lapels, from the chin to mid-chest"},
    {"id": "closure", "view": {"yaw": 0, "pitch": 0, "framing": "close:chest"}, "light": "even",
     "must_show": ["the placket and its buttons", "which buttons are done up", "the waistband, belt and buckle, the fly"],
     "words": "close-up of the front closure from the chest to below the belt"},
    {"id": "cuff", "view": {"yaw": 0, "pitch": 0, "framing": "close:wrist"}, "light": "even",
     "must_show": ["the jacket sleeve's end and how much shirt cuff shows past it", "the cuff type"],
     "words": "close-up of one sleeve's end and the shirt cuff at the wrist, the arm hanging"},
    {"id": "pockets", "view": {"yaw": 0, "pitch": 0, "framing": "close:hip"}, "light": "even",
     "must_show": ["the pocket types (flap, welt, patch) and the breast pocket"],
     "words": "close-up of the jacket's front from the chest to the hem"},
    {"id": "hem", "view": {"yaw": 60, "pitch": -5, "framing": "close:floor"}, "light": "even",
     "must_show": ["the trouser hem on the shoe: no, half or full break", "the leg opening against the shoe"],
     "words": "close-up from the knees to the floor, three-quarter side view"},
    {"id": "vent", "view": {"yaw": 180, "pitch": 0, "framing": "close:crotch"}, "light": "even",
     "must_show": ["the back vent (centre, sides or none)", "the back hem's level"],
     "words": "close-up of the back from the waist to below the jacket's hem"},
    {"id": "raking", "view": {"yaw": 20, "pitch": 0, "framing": "full"}, "light": "raking",
     "must_show": ["the cloth's weave and weight, where the folds are and how many, the pressed creases"],
     "words": "the same pose lit by one low hard light from the side raking across the cloth"},
]
_CLOSE_SHOT = {"neck_base": "collar", "wrist": "cuff", "elbow": "cuff", "floor": "hem", "ankle": "hem", "knee": "hem",
               "chest": "closure", "waist": "closure", "crotch": "closure", "hip": "pockets"}
_YAW = {"front": 0, "side": 90, "back": 180, "three": 45}
RAKING_ITEMS = ("fold_character", "drape", "wear_age", "fabric")


def shots_for(it: dict) -> list:
    """The brief's shots that show an item: its view's turnaround shot, its close-up, the raking pass for fabric."""
    out = []
    if it["view"] in _YAW:
        out.append(it["view"])
    if it["view"] == "close" or it["type"] == "choice":
        reg = ((it.get("region") or {}).get("around") or ["chest"])[0].split(".")[0]
        sh = {"vent": "vent", "pockets": "pockets"}.get(it["id"], _CLOSE_SHOT.get(reg, "closure"))
        out.append(sh)
    if it["id"] in RAKING_ITEMS:
        out.append("raking")
    return list(dict.fromkeys(out)) or ["front"]


class _NoBody:
    """For the wear sentences no body landmarks are needed."""
    J, at = {}, {}
    V = np.zeros((1, 3))
    T = np.zeros((0, 3), int)


def wear_words(c: Ctx, garments: dict) -> list:
    """The wear state in plain sentences, from the model's own garments (spec only: nothing simulated)."""
    W = []
    for g, kind in garments.items():
        try:
            st = m_front_state(c, g)["value"]
            n = m_button_count(c, g)["value"]
            d = m_buttons_done(c, g)["value"]
            W.append(f"the {g} is worn {st}, " + (f"{d} of its {n} front buttons done up" if d else f"all {n} front buttons undone"))
        except (NotMeasured, KeyError):
            pass
        if kind in ("shirt", "blouse"):
            try:
                cs = m_collar_state(c, g)["value"]
                W.append("the shirt collar is open at the throat with no tie, the collar button undone" if cs == "open"
                         else "the shirt is buttoned to the collar")
                W.append("the shirt is tucked into the trousers" if m_tucked(c, g)["value"] else "the shirt is worn untucked")
            except (NotMeasured, KeyError):
                pass
        if kind in ("trousers", "suit_trousers", "shorts", "skirt"):
            dd = _design_details(c, g)
            if dd.get("belt") not in (None, "none"):
                W.append("a belt with a buckle is worn and plainly visible at the front")
            if dd.get("crease") not in (None, "none"):
                W.append("the trousers have a sharp pressed crease down each leg")
    return W


def wear_from_refs(refs: dict) -> list:
    """The wear state in plain sentences from a reading's targets (what the reference showed: the outfit as it should
    be worn, never our model's current state)."""
    W = []
    for g, tg in refs["targets"].items():
        val = lambda k: (tg.get(k) or {}).get("value") if (tg.get(k) or {}).get("visible") else None
        st, n, d = val("front_state"), val("button_count"), val("buttons_done")
        if st == "closed" and not n:
            W.append(f"the {g} is buttoned down the front")
        elif st:
            W.append(f"the {g} is worn {st}" + (f", {d} of its {n} front buttons done up" if d and n else
                                                 f", all {n} front buttons undone" if d == 0 and n else ""))
        if val("collar_state") == "open":
            W.append(f"the {g} collar is open at the throat with no tie, the collar button undone")
        elif val("collar_state") == "closed":
            W.append(f"the {g} is buttoned to the collar")
        if val("tucked") is True:
            W.append(f"the {g} is tucked into the trousers")
        elif val("tucked") is False:
            W.append(f"the {g} is worn untucked")
        if val("belt") is True:
            W.append("a belt with a buckle is worn and plainly visible at the front")
        if val("crease") is True:
            W.append(f"the {g} have a sharp pressed crease down each leg")
    return W


def reference_brief(garments: dict, subject: str = "a man", outfit: str = "", wear: list | None = None,
                    model: str | None = None, spec: dict | None = None, refs: dict | str | None = None) -> dict:
    """A shot list for reference images of a garment or outfit, from the checklist (the same format as the face's
    likeness brief): {"subject", "common": {"prompt", "negative"}, "shots": [{"id", "view": {yaw, pitch, framing},
    "light", "purpose": [item ids], "must_show", "prompt"}], "text"}. garments: {name: kind}. With `model`, the wear
    state is written from that model's garments (which buttons are done up, tucked, belt, collar); with `refs` (a
    reading) from what the reference showed, which wins: a brief must ask for the outfit as it should be, not for
    what a wrong model does now."""
    if wear is None and refs is not None:
        wear = wear_from_refs(json.loads(Path(refs).read_text()) if isinstance(refs, (str, Path)) else refs)
    if wear is None and model:
        from . import store
        spec = spec or store.load(model)
        wear = wear_words(Ctx(model, spec, {}, body=_NoBody()), garments)
    wear = list(wear or [])
    purposes = {s["id"]: [] for s in SHOTS}
    for g, kind in garments.items():
        for it in items_for(kind):
            for sh in shots_for(it):
                if it["id"] not in purposes[sh]:
                    purposes[sh].append(it["id"])
    wear_s = " ".join(w[0].upper() + w[1:] + "." for w in wear)
    common = (f"Photorealistic garment reference photograph of {subject}{', ' + outfit if outfit else ''}. The SAME "
              "person in the SAME clothes in every image. He stands in a relaxed A-pose: arms straight and held about "
              "20 degrees away from the body so the sleeves and the sides of the jacket are clear, palms facing "
              "forward, feet hip-width apart, weight even, head level. " + (wear_s + " " if wear_s else "")
              + "Plain light grey seamless studio background, no props. Long lens (about 100 mm), camera at chest "
              "height, so proportions are not distorted. Sharp focus, true colours, no stylisation.")
    negative = ("hands in pockets, crossed arms, a jacket held or flapping, wind, dramatic or coloured lighting (except "
                "the raking shot), the head or shoes cropped in full-length shots, wide-angle distortion, accessories "
                "covering the garments, different clothes or a different person between shots")
    shots = []
    for s in SHOTS:
        if not purposes[s["id"]]:
            continue
        light = ("Lit by one low hard light from the left raking across the cloth, a weak fill, so the weave and every "
                 "fold cast a shadow" if s["light"] == "raking" else "Even soft light from the front and both sides, no hard shadows")
        full = s["view"]["framing"] == "full"
        prompt = (f"{common} {'Full-length' if full else 'Detail'} shot, {s['words']}. {light}. Must show: "
                  + "; ".join(s["must_show"]) + ".")
        shots.append({"id": s["id"], "view": dict(s["view"]), "light": s["light"], "purpose": purposes[s["id"]],
                      "must_show": list(s["must_show"]), "prompt": prompt})
    out = {"subject": subject, "common": {"prompt": common, "negative": negative}, "shots": shots}
    out["text"] = brief_text(out)
    return out


def brief_text(b: dict) -> str:
    L = [f"REFERENCE BRIEF: {b['subject']} ({len(b['shots'])} shots). Common to every prompt:", "  " + b["common"]["prompt"],
         "  Negative: " + b["common"]["negative"]]
    for s in b["shots"]:
        v = s["view"]
        L.append(f"[{s['id']}] yaw {v['yaw']}, {v['framing']}, {s['light']} light; serves: {', '.join(s['purpose'])}")
        L.append("  must show: " + "; ".join(s["must_show"]))
    L.append("Each shot's full prompt: shots[i].prompt.")
    return "\n".join(L)


def _yaw_kind(yaw: float) -> str:
    y = abs(((float(yaw) + 180) % 360) - 180)
    return "front" if y <= 15 else "three" if y <= 65 else "side" if y <= 115 else "three_back" if y <= 160 else "back"


def check_references(views: list, garments: dict) -> dict:
    """Which checklist items a given set of pictures can support, and why not. views: [{"image"?, "yaw" (deg: 0
    front, 90 its left side, 180 back), "framing": "full" | "bust" | "close:<region>", "light": "even" | "raking" |
    "dramatic" | "warm", "perspective": "ortho-ish" | "perspective", "posed": "a-pose" | "other", "size": [w, h]?}].
    Returns {"supported": [{"garment", "id", "by": [view index], "why"}], "unsupported": [{"garment", "id", "why",
    "shot": brief shots that would supply it}], "text"}. Rules: numbers (lengths, widths) need a full, near-orthographic
    view in the item's direction with the figure posed so its landmarks show (a seated or perspective painting gives
    choices only); close items need a close-up of their region, or a full view of 1600+ px; folds, drape and wear
    need raking light; colour needs even light."""
    sup, uns = [], []
    for g, kind in garments.items():
        for it in items_for(kind):
            by, whyno = [], []
            for i, v in enumerate(views):
                vk = _yaw_kind(v.get("yaw", 0))
                fr = v.get("framing", "full")
                full = fr == "full"
                light = v.get("light", "even")
                h = (v.get("size") or [0, 0])[1]
                want = it["view"]
                if want in _YAW and want != vk and not (want == "three" and vk in ("front", "side")):
                    whyno.append(f"view {i} is {vk}, the item needs {want}")
                    continue
                if want == "close":
                    reg = ((it.get("region") or {}).get("around") or [""])[0].split(".")[0]
                    if fr.startswith("close") and _CLOSE_SHOT.get(fr.split(":")[-1], fr) != _CLOSE_SHOT.get(reg, reg):
                        whyno.append(f"view {i} is a close-up of {fr.split(':')[-1]}, the item is at {reg}")
                        continue
                    if full and h and h < 1600:
                        whyno.append(f"view {i} is full-length at {h} px: too small for a close item")
                        continue
                    if vk == "back":
                        whyno.append(f"view {i} shows the back")
                        continue
                if it["type"] in ("length", "width") and "target_mm" not in it:
                    if v.get("perspective", "ortho-ish") != "ortho-ish" or v.get("posed", "a-pose") != "a-pose":
                        whyno.append(f"view {i} is {v.get('perspective', 'ortho-ish')} / {v.get('posed', 'a-pose')}: no "
                                     "camera can be fitted to the body for numbers")
                        continue
                    if not full:
                        whyno.append(f"view {i} is a close-up: the body landmarks for anchoring aren't in it")
                        continue
                if it["id"] in ("fold_character", "drape", "wear_age") and light != "raking":
                    whyno.append(f"view {i} is lit {light}: folds and weave read only in raking light")
                    continue
                if it["type"] == "colour" and light != "even":
                    whyno.append(f"view {i} is lit {light}: the colour is biased by the light")
                    continue
                by.append(i)
            if by:
                sup.append({"garment": g, "id": it["id"], "by": by, "why": f"{it['view']} {it['type']}"})
            else:
                uns.append({"garment": g, "id": it["id"], "why": "; ".join(dict.fromkeys(whyno)) or "no view",
                            "shot": shots_for(it)})
    out = {"supported": sup, "unsupported": uns}
    L = [f"{len(sup)} items supported, {len(uns)} not:"]
    for u in uns:
        L.append(f"  {u['garment']}.{u['id']}: {u['why']} -> brief shot {', '.join(u['shot'])}")
    out["text"] = "\n".join(L)
    return out
