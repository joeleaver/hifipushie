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


# what a view cannot show: left out of that view's count (a face shape in a profile is not "missing")
NOT_JUDGEABLE = {
    "profile": {"groups": {"face shape"}, "ids": {"chin_broad", "chin_pointed", "chin_cleft", "nose_broad", "jaw_narrow", "eyes_hooded", "eyes_wide"}},
    "front": {"groups": set(), "ids": {"chin_strong", "chin_weak", "nose_straight", "nose_aquiline", "nose_snub", "brow_flat"}},
    "low_angle": {"groups": set(), "ids": {"nose_straight", "nose_aquiline", "eyes_deep", "brow_heavy", "brow_flat", "face_long", "chin_strong", "chin_weak"}},
}


def judgeable(d: dict, view: str) -> bool:
    k = "profile" if view.startswith("profile") else view if view in NOT_JUDGEABLE else None
    nj = NOT_JUDGEABLE.get(k) if k else None
    return not nj or (d["group"] not in nj["groups"] and d["id"] not in nj["ids"])


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


def _against(k, others, by) -> list:
    return [o for o in others if o in by[k].get("opposite", []) or k in by[o].get("opposite", [])]


def effective(by_author: dict) -> dict:
    """The reference read used as the prior: the USER's wins. The LLM reader's descriptors stay unless one is the
    opposite of something the user said (lean against the user's chunky, straight nose against snub)."""
    by = {d["id"]: d for d in descriptors()}
    user, llm = by_author.get("user") or {}, by_author.get("llm") or {}
    ud = user.get("descriptors", {})
    ds = {k: {**v, "author": "llm"} for k, v in llm.get("descriptors", {}).items() if not _against(k, ud, by)}
    ds.update({k: {**v, "author": "user"} for k, v in ud.items()})
    return {"descriptors": ds, "summary": user.get("summary") or llm.get("summary", "")}


def questions(name: str) -> list:
    """Where the user's read and the LLM reader's disagree: questions for the user, never settled silently."""
    by = {d["id"]: d for d in descriptors()}
    ba = load(name)["reads"].get("reference_by") or {}
    user, llm = (ba.get("user") or {}).get("descriptors", {}), (ba.get("llm") or {}).get("descriptors", {})
    if not user or not llm:
        return []
    out = []
    for k in user:
        opp = _against(k, llm, by)
        if opp:
            notes = "; ".join(llm[o].get("note", "") for o in opp if llm[o].get("note"))[:200]
            out.append(f"{by[k]['group']}: you read {by[k]['name']}; the reader saw {', '.join(by[o]['name'] for o in opp)}"
                       + (f" ({notes})" if notes else "") + ". Which should the model show? (yours is used until you say otherwise)")
        elif k not in llm:
            out.append(f"{by[k]['group']}: you read {by[k]['name']}; the reader did not see it in the pictures. Which picture shows it, "
                       "or is it from knowing the character? (yours is used)")
    return out


def set_read(name: str, tag: str, read: dict, view: str | None = None, by: str = "", author: str = "llm") -> dict:
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
    elif tag == "reference":   # kept per author ("user" | "llm"); the prior is `effective` of them
        if author not in ("user", "llm"):
            raise ValueError("author must be 'user' or 'llm'")
        ba = d["reads"].setdefault("reference_by", {})
        ba[author] = entry
        d["reads"]["reference"] = effective(ba)
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


PROJECT_TOL = 0.004   # m: a point counts as seen by the reference's camera when it lies this near that camera's own depth
PROJECT_GRAZE = 0.2   # and its normal faces that camera by at least this (grazing skin smears the picture)


def project_reference(name: str, out: str, base: dict | None = None, view: int = 0, px: int = 520) -> dict:
    """The fastest honest judge of a head's GEOMETRY: the reference picture projected onto the model through its
    fitted camera as an unlit texture, then looked at from the other views (reference cameras, both profiles, the other
    three-quarter, low angle). Where the likeness holds when turned, the geometry carries it; where the picture
    smears, doubles or slides (the nose's side, the jaw's edge, the chin in profile) the geometry is wrong there.
    Skin the reference's camera does not see (hidden, or grazing) is drawn as dim clay. No light is added: the
    picture's own shading is on the surface, so a turned view is only fair near the reference's own direction and
    for outlines / proportions. Returns {"sheet", "views", "seen": share of each panel's head pixels that carry the
    picture}."""
    from PIL import Image, ImageDraw
    from . import humanfit, likeness as lk, store
    base = base or store.load(name)["base"]
    refs = lk._refs(name)
    src_v, src_cam = refs["views"][view], refs["cameras"][view]
    photo = np.asarray(Image.open(src_v["image"]).convert("RGB"), float)
    mesh = lk.model_mesh(base)
    w, h = src_cam["size"]
    sbox = (0.0, 0.0, float(w), float(h))
    spx = int(min(max(w, h), 1600))
    _, ks, sp = lk.render(mesh, src_cam, sbox, px=spx, passes=True)
    zs = sp["zb"]
    Rs = humanfit._cam_rot(src_cam)
    cells, names, seen = [], [], {}
    for nm, cam, box in _views(name):
        im, k, ps = lk.render(mesh, cam, box, px=px, passes=True)
        zb, nrm = ps["zb"], ps["nrm"]
        H, W = zb.shape
        on = np.isfinite(zb)
        ii, jj = np.nonzero(on)
        z = zb[ii, jj]
        u, v = box[0] + (jj + 0.5) / k, box[1] + (ii + 0.5) / k
        cw, ch = cam["size"]
        Xc = np.c_[(u - cw / 2) / cam["f"] * z, (v - ch / 2) / cam["f"] * z, z]
        Rc = humanfit._cam_rot(cam)
        X = (Xc - np.asarray(cam["t"], float)) @ Rc + np.asarray(cam["centre"], float)
        Xs = (X - np.asarray(src_cam["centre"], float)) @ Rs.T + np.asarray(src_cam["t"], float)
        us, vs = src_cam["f"] * Xs[:, 0] / Xs[:, 2] + w / 2, src_cam["f"] * Xs[:, 1] / Xs[:, 2] + h / 2
        a, b = np.round(vs * ks - 0.5).astype(int), np.round(us * ks - 0.5).astype(int)
        inside = (a >= 0) & (a < zs.shape[0]) & (b >= 0) & (b < zs.shape[1]) & (us >= 0) & (us < w - 1) & (vs >= 0) & (vs < h - 1)
        vis = np.zeros(len(z), bool)
        vis[inside] = Xs[inside, 2] < zs[a[inside], b[inside]] + PROJECT_TOL
        nw = nrm[ii, jj] @ Rc                      # the surface normal in world axes
        to_src = -(Xs / np.linalg.norm(Xs, axis=1, keepdims=True)) @ Rs
        vis &= (nw * to_src).sum(1) > PROJECT_GRAZE
        img = np.asarray(im.convert("RGB"), float) * 0.45 + 40.0
        img[~on] = 238.0
        x0, y0 = np.floor(us[vis]).astype(int), np.floor(vs[vis]).astype(int)
        fx, fy = (us[vis] - x0)[:, None], (vs[vis] - y0)[:, None]
        col = (photo[y0, x0] * (1 - fx) * (1 - fy) + photo[y0, x0 + 1] * fx * (1 - fy)
               + photo[y0 + 1, x0] * (1 - fx) * fy + photo[y0 + 1, x0 + 1] * fx * fy)
        img[ii[vis], jj[vis]] = col
        seen[nm] = round(float(vis.mean()) if len(vis) else 0.0, 2)
        c = Image.new("RGB", (px, px + 20), (238, 238, 238))
        c.paste(Image.fromarray(img.astype(np.uint8)), ((px - W) // 2, 20 + (px - H) // 2))
        ImageDraw.Draw(c).text((6, 4), f"{nm}  (picture on {int(100 * seen[nm])}% of the head)", fill=(20, 20, 20))
        cells.append(c)
        names.append(nm)
    cols = 3
    rows = (len(cells) + cols - 1) // cols
    S = Image.new("RGB", (cols * px + (cols - 1) * 6, rows * (px + 20) + (rows - 1) * 6), (24, 24, 28))
    for i, c in enumerate(cells):
        S.paste(c, ((i % cols) * (px + 6), (i // cols) * (px + 26)))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    S.save(out)
    return {"sheet": out, "views": names, "seen": seen}


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
        can = [k for k in want if judgeable(by[k], view)]
        contra = [(k, o) for k in can for o in by[k].get("opposite", []) if o in got and o not in want and k not in got]
        missing = [k for k in can if k not in got and not any(c[0] == k for c in contra) and by[k]["group"] != "overall"]
        extra = [k for k in got if k not in want and not any(c[1] == k for c in contra) and by[k]["group"] != "overall"]
        kept = [k for k in can if k in got]
        score.append((len(kept), len(can)))
        lines.append(f"  model {view}: keeps {nm(kept)}"
                     + ("; CONTRADICTS: " + ", ".join(f"{by[a]['name']} -> reads {by[b]['name']}" for a, b in contra) if contra else "")
                     + (f"; missing: {nm(missing)}" if missing else "") + (f"; adds: {nm(extra)}" if extra else "")
                     + (f"  (\"{rd.get('summary')}\")" if rd.get("summary") else ""))
    k, n = sum(a for a, _ in score), sum(b for _, b in score)
    lines.insert(1, f"  kept {k} of {n} descriptor-views (views that can't show a descriptor don't count)")
    qs = questions(ref_from or name)
    if qs:
        lines.insert(2, "  QUESTIONS (the user's read and the reader's differ):\n" + "\n".join("    " + q for q in qs))
    gaps = sorted({by[k]["control"] for k in want if "GAP" in by[k]["control"]})
    if gaps:
        lines.append("  controls the read needs and we lack: " + "; ".join(gaps))
    return "\n".join(lines)


def agreement(name: str, tags: list) -> str:
    """Repeatability of blind reads of ONE head (several tags = several readers of the same sheet): per descriptor, in
    how many views the readers all agree (all pick it or none does), and Fleiss-style: of the reader-views that
    picked it, the share where every reader did."""
    by = {d["id"]: d for d in descriptors()}
    reads = load(name)["reads"]
    views = list(reads[tags[0]]["views"])
    rows = []
    for k, d in by.items():
        agree = n = unan = picked = 0
        for v in views:
            if not judgeable(d, v):
                continue
            c = sum(k in reads[t]["views"].get(v, {}).get("descriptors", {}) for t in tags)
            n += 1
            agree += c in (0, len(tags))
            picked += c > 0
            unan += c == len(tags)
        if picked:
            rows.append((unan / picked, k, unan, picked, agree, n))
    rows.sort()
    lines = [f"agreement of {len(tags)} blind readers over {len(views)} views (descriptor: unanimous / views where anyone picked it; all-agree views):"]
    for share, k, unan, picked, agree, n in rows:
        lines.append(f"  {by[k]['name']:28s} {unan}/{picked}  ({agree}/{n})" + ("   UNRELIABLE" if share < 0.34 and picked >= 2 else ""))
    return "\n".join(lines)
