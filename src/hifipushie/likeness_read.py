"""Stage 0 of the likeness checklist: the CHARACTER READ (likeness_guide.md).

A person looking at one front picture knows "a chunky, handsome man with a square jaw, a cleft chin and a cute nose",
and so knows a three-quarter view is wrong before any millimetre is read. The pathway to the same check:

1. `descriptors()` (likeness.json): gestalt words bound to bands on checklist items in every view.
2. The read is made by an LLM looking at the references: `form()` is what it fills; `set_read(name, "reference", ...)`
   stores it (<model>/likeness_read.json). `apply_prior(cmp, read)`: items no picture measures take the read's band
   ("from the read"), measured items that fall outside it are flagged (a view against the macro = suspect camera or
   expression), and the model's own value is checked against the band.
3. The round trip: `render_views(name, out)` draws the model from each reference camera and from views no reference
   shows (profiles, the other three-quarter, low angle); the SAME form is filled blind on each render (a fresh agent
   that never saw the references) and stored with `set_read(name, "<tag>", ..., view=)`; `diff(name, tag)` leads the
   likeness report: "reference: square jaw, strong chin, snub nose; model three-quarter: soft jaw, weak chin".
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

READ = "likeness_read.json"
CONF = {"clear": 1.0, "likely": 0.6, "hint": 0.3}
UNSEEN = [("profile_right", -90.0, 0.0), ("profile_left", 90.0, 0.0), ("three_quarter_other", None, 0.0), ("low_angle", 0.0, 25.0)]


def descriptors() -> list:
    from . import likeness
    return json.loads(likeness.CHECKLIST.read_text()).get("descriptors", [])


def form() -> str:
    """The form an LLM fills while looking at ONE picture (or one set of references)."""
    groups = {}
    for d in descriptors():
        groups.setdefault(d["group"], []).append(d)
    lines = ["CHARACTER READ. Look at the face as a casting director or a portrait artist would, before measuring anything.",
             "For each group pick the descriptors that apply (none, one or several), each with a confidence: clear | likely | hint.",
             "Only what this picture shows; a descriptor the picture can't show (a jaw corner under a collar) is left out.",
             "Answer as JSON: {\"descriptors\": {\"<id>\": {\"confidence\": \"clear\", \"picture\": \"<file or view>\", \"note\": \"...\"}}, "
             "\"summary\": \"one sentence, as you'd describe the person to someone\"}", ""]
    for g, ds in groups.items():
        lines.append(f"{g}:")
        for d in ds:
            lines.append(f"  {d['id']}: {d['name']}: {d['what']}")
    return "\n".join(lines)


def _path(name: str) -> Path:
    from . import store
    return store.HOME / name / READ


def load(name: str) -> dict:
    p = _path(name)
    return json.loads(p.read_text()) if p.exists() else {"format": 1, "reads": {}}


def set_read(name: str, tag: str, read: dict, view: str | None = None, by: str = "") -> dict:
    """Store a filled form. tag "reference" = the read of the reference pictures (the prior); any other tag = a blind
    read of renders of a model (then `view` names the render: front, three_quarter, profile_right...)."""
    ids = {d["id"] for d in descriptors()}
    bad = [k for k in read.get("descriptors", {}) if k not in ids]
    if bad:
        raise ValueError(f"unknown descriptors {bad}; see likeness_read.form()")
    for k, v in read.get("descriptors", {}).items():
        if v.get("confidence", "likely") not in CONF:
            raise ValueError(f"{k}: confidence must be one of {list(CONF)}")
    d = load(name)
    slot = d["reads"].setdefault(tag, {})
    entry = {"descriptors": read.get("descriptors", {}), "summary": read.get("summary", ""), "by": by}
    if view:
        slot.setdefault("views", {})[view] = entry
    else:
        slot.update(entry)
    _path(name).parent.mkdir(parents=True, exist_ok=True)
    _path(name).write_text(json.dumps(d, indent=1))
    return d


def bands(read: dict) -> dict:
    """{item id: (lo, hi, [descriptor names], weight)}: what a read implies for each checklist item (bands of several
    descriptors on one item intersect)."""
    by = {d["id"]: d for d in descriptors()}
    out = {}
    for k, v in (read.get("descriptors") or {}).items():
        w = CONF.get(v.get("confidence", "likely"), 0.6)
        for m in by[k]["implies"]:
            lo, hi = m["band"]
            a = out.get(m["item"])
            out[m["item"]] = (max(lo, a[0]), min(hi, a[1]), a[2] + [by[k]["name"]], max(w, a[3])) if a else (lo, hi, [by[k]["name"]], w)
    return out


def _band_text(lo, hi, unit):
    if lo < -1e8:
        return f"<= {hi:g}{unit}"
    if hi > 1e8:
        return f">= {lo:g}{unit}"
    return f"{lo:g}..{hi:g}{unit}"


def apply_prior(cmp: dict, read: dict) -> list:
    """Lines for the report, and rows marked in place: r["read"] = the band's text; r["read_flag"] = "photo" (a measured
    reference value outside the band its own read implies: suspect that view's camera or expression) / "model" (the
    model outside the band); an unmeasured row gets r["prior"] (the band stands in for the missing picture)."""
    b = bands(read)
    lines = []
    seen = set()
    for r in cmp["rows"]:
        if r["id"] not in b:
            continue
        lo, hi, names, w = b[r["id"]]
        txt = _band_text(lo, hi, r["unit"]) + f" ({', '.join(names)})"
        r["read"] = txt
        slack = r["tol"] or 0.0
        if r["score"] < 0:
            if r["id"] not in seen:
                r["prior"] = txt
                lines.append(f"  from the read (no picture measures it): {r['name']} {txt}")
                seen.add(r["id"])
            continue
        for who, val in (("photo", r.get("photo")), ("model", r.get("model"))):
            if r.get("kind") == "shape" and who == "model":
                continue
            if isinstance(val, float) and (val < lo - slack or val > hi + slack):
                r["read_flag"] = who if "read_flag" not in r else "both"
                lines.append(f"  {'CONTRADICTS the read' if who == 'photo' else 'MODEL outside the read'}: {r['name']} [{r['view']}] "
                             f"{who} {val:.1f}{r['unit']} vs {txt}"
                             + (" -> suspect that picture's camera or expression" if who == "photo" else ""))
    return lines


def _views(name: str) -> list:
    """[(view name, camera, box)]: each reference's camera, then the unseen views made from the front camera."""
    from scipy.spatial.transform import Rotation as R
    from . import likeness as lk
    refs = lk._refs(name)
    photos = lk._photos(refs)
    out, front = [], None
    for ph in photos:
        out.append((ph["kind"], ph["cam"], ph["box"]))
        if ph["kind"] == "front" and front is None:
            front = ph
    if front is None:
        return out
    tq = next((float(ph["cam"].get("yaw", 0.0)) for ph in photos if ph["kind"] == "three_quarter"), -45.0)
    for nm, yaw, pitch in UNSEEN:
        cam = dict(front["cam"])
        cam["yaw"] = float(front["cam"].get("yaw", 0.0)) + (-tq if yaw is None else yaw)
        if pitch:   # the camera lowered: a turn about its own x axis in front of the head
            cam["r"] = (R.from_rotvec([-np.radians(pitch), 0, 0]) * R.from_rotvec(cam["r"])).as_rotvec().tolist()
        b = front["box"]
        w = (b[2] - b[0]) * 0.25
        out.append((nm, cam, (b[0] - w, b[1], b[2] + w, b[3])))
    return out


def render_views(name: str, out: str, base: dict | None = None, px: int = 520, label: bool = True) -> dict:
    """One sheet of the model's head, a panel per view (reference cameras first, then views no reference shows), lit
    from the upper left, brows drawn; panels are labelled with the view's name only (nothing of the reference). For the
    blind read. Returns {"sheet": path, "views": [names]}."""
    from PIL import Image, ImageDraw
    from . import likeness as lk, store
    base = base or store.load(name)["base"]
    mesh = lk.model_mesh(base)
    cells, names = [], []
    for nm, cam, box in _views(name):
        im, k = lk.render(mesh, cam, box, px=px)[:2]
        c = Image.new("RGB", (px, px + 20), (238, 238, 238))
        c.paste(im.convert("RGB"), ((px - im.size[0]) // 2, 20 + (px - im.size[1]) // 2))
        if label:
            ImageDraw.Draw(c).text((6, 4), nm, fill=(20, 20, 20))
        cells.append(c)
        names.append(nm)
    cols = 3
    rows = (len(cells) + cols - 1) // cols
    W = Image.new("RGB", (cols * px + (cols - 1) * 6, rows * (px + 20) + (rows - 1) * 6), (24, 24, 28))
    for i, c in enumerate(cells):
        W.paste(c, ((i % cols) * (px + 6), (i // cols) * (px + 26)))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    W.save(out)
    return {"sheet": out, "views": names}


def diff(name: str, tag: str, ref_from: str | None = None) -> str:
    """The reference's read against a model's blind reads, view by view: what the reference has that a view of the
    model lacks (or contradicts: an `opposite` descriptor read instead), and what the model shows that the reference
    doesn't. This leads the likeness report."""
    by = {d["id"]: d for d in descriptors()}
    ref = load(ref_from or name)["reads"].get("reference")
    mod = load(name)["reads"].get(tag)
    if not ref:
        return "no reference read stored (likeness_read.set_read(name, 'reference', ...))"
    if not mod or not mod.get("views"):
        return f"no blind read '{tag}' stored for {name}"
    want = ref["descriptors"]
    nm = lambda ks: ", ".join(by[k]["name"] for k in ks) or "-"  # noqa: E731
    lines = [f"CHARACTER READ. reference: {nm(want)}" + (f"  (\"{ref.get('summary')}\")" if ref.get("summary") else "")]
    score = []
    for view, rd in mod["views"].items():
        got = rd["descriptors"]
        # (an opposite the reference itself also holds, "long" with a hint of "square", is not a contradiction)
        contra = [(k, o) for k in want for o in by[k].get("opposite", []) if o in got and o not in want and k not in got]
        missing = [k for k in want if k not in got and not any(c[0] == k for c in contra) and by[k]["group"] != "overall"]
        extra = [k for k in got if k not in want and not any(c[1] == k for c in contra) and by[k]["group"] != "overall"]
        kept = [k for k in want if k in got]
        score.append((len(kept), len(want)))
        lines.append(f"  model {view}: keeps {nm(kept)}"
                     + ("; CONTRADICTS: " + ", ".join(f"{by[a]['name']} -> reads {by[b]['name']}" for a, b in contra) if contra else "")
                     + (f"; missing: {nm(missing)}" if missing else "") + (f"; adds: {nm(extra)}" if extra else "")
                     + (f"  (\"{rd.get('summary')}\")" if rd.get("summary") else ""))
    k, n = sum(a for a, _ in score), sum(b for _, b in score)
    lines.insert(1, f"  kept {k} of {n} descriptor-views")
    gaps = sorted({by[k]["control"] for k in want if "GAP" in by[k]["control"]})
    if gaps:
        lines.append("  controls the read needs and we lack: " + "; ".join(gaps))
    return "\n".join(lines)
