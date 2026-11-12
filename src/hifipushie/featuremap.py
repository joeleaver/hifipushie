"""The feature map: what a reference shows, as NAMED MARKS on its own pictures. The DESCRIBE gate of a sculpt
from concept art, made of pixels a model can be measured against instead of prose and typed numbers.

A feature is one thing the sculptor sees in the reference and names: `kind`
  "mass"   a solid of its own (a head, a muzzle, an ear, a horn, a limb, a hoof, a prop)
  "form"   a shape ON a mass's surface (a socket rim, a brow, a lip, a cuff's edge, a tuft, a crease)
  "paint"  colour only: no shape (a blaze, a patch, a pupil painted on)
plus the structure in words: `on` (the feature it sits on), `join` (how it meets it: "along its whole base",
"by its narrow end", "hangs free"), `separate` (its own rigid part: an eyeball, a prop), `authority` (the view to
believe where two disagree), `inferred` (what no view shows), `says` (anything else), `elements` (the model's
elements that make it, once it is made: featuresee.py measures those).

Marks, per view, in that view's own pixels (the rulers on read_reference's pictures), always clipped to the figure:
  {"patches": [ids]} | {"box": [x0, y0, x1, y1]} | {"ellipse": [cx, cy, rx, ry]} | {"polygon": [[x, y], ...]} |
  {"line": [[x, y], ...], "width": px}; several keys add up; "minus": {...} takes away; "mirror": true on a front /
  back view also marks the ".L" / ".R" twin by reflection (only when the picture really is symmetric there).
Each mark is stored as a mask (<model>/features/masks/<feature>__<view>.png), so reading a view again at another
detail changes no mark.

`checks` are the lessons this holds: every patch of the figure belongs to a feature; a feature's heights agree
between the orthographic views (generated turnarounds often disagree: name the authority); ".L" is the creature's
left, which is the picture's RIGHT in a front view; a mass seen in one view has no depth yet.
"""
from __future__ import annotations

import json

import numpy as np
from PIL import Image, ImageDraw

from . import refread

KINDS = ("mass", "form", "paint")
UNMARKED = 0.02  # a view owes its unmarked pixels above this share of the figure
FIELDS = ("kind", "on", "join", "separate", "authority", "inferred", "says", "elements")
SHAPES = ("patches", "box", "ellipse", "polygon", "line")
PALETTE = [(230, 25, 75), (60, 180, 75), (0, 130, 200), (245, 130, 48), (145, 30, 180), (0, 160, 160), (240, 50, 230),
           (128, 128, 0), (170, 110, 40), (128, 0, 0), (0, 0, 128), (220, 190, 0), (0, 100, 0), (255, 105, 180)]


def path(name: str):
    return refread.folder(name) / "map.json"


def load(name: str) -> dict:
    p = path(name)
    return json.loads(p.read_text()) if p.exists() else {"views": {}, "features": {}, "notes": ""}


def save(name: str, fm: dict) -> None:
    path(name).write_text(json.dumps(fm, indent=1))


def add_views(name: str, recs: dict) -> dict:
    fm = load(name)
    fm["views"].update(recs)
    save(name, fm)
    return fm


def twin(feature: str) -> str | None:
    return feature[:-2] + (".R" if feature.endswith(".L") else ".L") if feature[-2:] in (".L", ".R") else None


def mask_path(name: str, feature: str, view: str):
    d = refread.folder(name) / "masks"
    d.mkdir(exist_ok=True)
    return d / f"{feature}__{view}.png"


def mask(name: str, feature: str, view: str) -> np.ndarray:
    return np.asarray(Image.open(mask_path(name, feature, view))) > 127


WANT = {"patches": "a list of patch numbers, [12, 13]", "box": "four numbers, [x0, y0, x1, y1], or a list of such boxes",
        "ellipse": "four numbers, [cx, cy, rx, ry], or a list of such ellipses",
        "polygon": "three or more points, [[x, y], [x, y], [x, y]], or a list of such polygons",
        "line": "two or more points, [[x, y], [x, y]], or a list of such lines"}


def _each(k: str, v) -> list:
    """One shape or a list of them (several warts, both ends of a handle) -> a list of shapes."""
    if k in ("box", "ellipse"):
        return list(v) if v and isinstance(v[0], (list, tuple)) else [v]
    return list(v) if v and isinstance(v[0], (list, tuple)) and v[0] and isinstance(v[0][0], (list, tuple)) else [v]


def _checked(m, view: str) -> dict:
    """A mark as written, or a refusal that says how it is written."""
    def num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    def pts(v, least):
        return isinstance(v, (list, tuple)) and len(v) >= least and all(
            isinstance(q, (list, tuple)) and len(q) == 2 and all(num(c) for c in q) for q in v)
    if not isinstance(m, dict):
        raise ValueError(f"the mark in {view!r} is written {{shape: numbers}}, e.g. {{\"patches\": [12, 13]}} "
                         f"(got {m!r}; leave a view out to keep the mark it has)")
    unknown = set(m) - set(SHAPES) - {"minus", "mirror", "width"}
    if unknown or not any(k in m for k in SHAPES):
        raise ValueError(f"a mark in {view!r} needs one of {SHAPES} (+ minus, mirror, width); got {sorted(m)}")
    four = lambda v: isinstance(v, (list, tuple)) and len(v) == 4 and all(num(c) for c in v)  # noqa: E731
    ok = {"box": four, "ellipse": four, "polygon": lambda v: pts(v, 3), "line": lambda v: pts(v, 2)}
    if "patches" in m and not (isinstance(m["patches"], (list, tuple)) and m["patches"] and all(num(i) for i in m["patches"])):
        raise ValueError(f"'patches' in {view!r} is {WANT['patches']} (got {m['patches']!r})")
    for k, test in ok.items():
        if k in m and not (isinstance(m[k], (list, tuple)) and m[k] and all(test(one) for one in _each(k, m[k]))):
            raise ValueError(f"{k!r} in {view!r} is {WANT[k]}, in the view's pixels (got {m[k]!r})")
    if m.get("minus") is not None:
        _checked(m["minus"], view)
    return m


def _shape_mask(name: str, view: str, size, m: dict) -> np.ndarray:
    W, H = size
    out = np.zeros((H, W), bool)
    _checked(m, view)
    if "patches" in m:
        lab = refread.patches(name, view)
        ids = [int(i) for i in m["patches"]]
        gone = [i for i in ids if not (lab == i).any()]
        if gone:
            raise ValueError(f"view {view!r} has no patch {gone} (1..{int(lab.max())}; read_reference shows them)")
        out |= np.isin(lab, ids)
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    for b in _each("box", m["box"]) if "box" in m else ():
        d.rectangle([float(v) for v in b], fill=255)
    for e in _each("ellipse", m["ellipse"]) if "ellipse" in m else ():
        cx, cy, rx, ry = (float(v) for v in e)
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)
    for pg in _each("polygon", m["polygon"]) if "polygon" in m else ():
        d.polygon([tuple(float(c) for c in p) for p in pg], fill=255)
    for ln in _each("line", m["line"]) if "line" in m else ():
        d.line([tuple(float(c) for c in p) for p in ln], fill=255, width=int(m.get("width", 3)))
    return out | (np.asarray(im) > 127)


def mark_mask(name: str, view: str, rec: dict, m: dict) -> np.ndarray:
    fig = np.asarray(Image.open(rec["image"]).convert("RGBA"))[..., 3] > 127
    out = _shape_mask(name, view, rec["size"], m)
    if m.get("minus"):
        out &= ~_shape_mask(name, view, rec["size"], m["minus"])
    return out & fig


def _geometry(rec: dict, mk: np.ndarray) -> dict:
    ys, xs = np.where(mk)
    g = {"area_px": int(len(ys)), "box": [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
         "centre_px": [round(float(xs.mean()), 1), round(float(ys.mean()), 1)]}
    if rec.get("m_per_px"):
        k, c0, b = rec["m_per_px"], rec["centre_px"], rec["ground_px"]
        sign = -1.0 if rec["kind"] in ("back", "side_r") else 1.0
        axis = "x" if rec["kind"] in ("front", "back") else "y"
        g["world"] = {axis: round(sign * (float(xs.mean()) - c0) * k, 4), "z": round((b - float(ys.mean())) * k, 4),
                      "z_lo": round((b - (int(ys.max()) + 1)) * k, 4), "z_hi": round((b - int(ys.min())) * k, 4),
                      "w": round((int(np.ptp(xs)) + 1) * k, 4), "h": round((int(np.ptp(ys)) + 1) * k, 4)}
    return g


def mark(name: str, features: dict, remove: list[str] | None = None, notes: str | None = None) -> dict:
    """Add or change features (a feature's marks are replaced per view named; its other views and fields stay)."""
    fm = load(name)
    if not fm["views"]:
        raise ValueError(f"{name} has no reference views yet: read_reference first")
    for f in remove or []:
        if fm["features"].pop(f, None) is None:
            raise ValueError(f"no feature {f!r} to remove (have {sorted(fm['features'])})")
    for fname, spec in (features or {}).items():
        if "__" in fname or "/" in fname:
            raise ValueError(f"feature name {fname!r}: no '__' or '/'")
        if not isinstance(spec, dict) or not isinstance(spec.get("marks") or {}, dict):
            raise ValueError(f"feature {fname!r} is written {{\"kind\": ..., \"marks\": {{view: {{shape: numbers}}}}}} "
                             f"(got {spec!r})")
        cur = fm["features"].setdefault(fname, {"marks": {}})
        for k in FIELDS:
            if k in spec:
                cur[k] = spec[k]
        if cur.get("kind") not in KINDS:
            raise ValueError(f"feature {fname!r}: kind is one of {KINDS} (a mass is a solid of its own, a form is a "
                             f"shape on a mass's surface, paint is colour only)")
        unknown = set(spec) - set(FIELDS) - {"marks"}
        if unknown:
            raise ValueError(f"feature {fname!r}: unknown key(s) {sorted(unknown)}; fields are {FIELDS} and marks")
        for view, m in (spec.get("marks") or {}).items():
            if view not in fm["views"]:
                raise ValueError(f"feature {fname!r}: no view {view!r} (have {sorted(fm['views'])})")
            if m is None:  # null: this view's mark goes
                if cur["marks"].pop(view, None) is not None:
                    mask_path(name, fname, view).unlink(missing_ok=True)
                continue
            rec = fm["views"][view]
            try:
                mk = mark_mask(name, view, rec, m)
            except ValueError as e:
                raise ValueError(f"feature {fname!r}: {e}") from None
            if not mk.any():
                raise ValueError(f"feature {fname!r} in {view!r}: the mark covers none of the figure (marks are in the "
                                 f"view's own pixels, {rec['size'][0]} x {rec['size'][1]}; see the rulers)")
            todo = [(fname, cur, mk)]
            if m.get("mirror") is True:
                tw = twin(fname)
                if not tw or rec["kind"] not in ("front", "back"):
                    raise ValueError(f"feature {fname!r}: mirror needs a .L / .R name and a front or back view")
                idx = int(round(2 * rec["centre_px"])) - np.arange(mk.shape[1])
                ok = (idx >= 0) & (idx < mk.shape[1])
                fl = np.zeros_like(mk)
                fl[:, ok] = mk[:, idx[ok]]
                fig = np.asarray(Image.open(rec["image"]).convert("RGBA"))[..., 3] > 127
                other = fm["features"].setdefault(tw, {"marks": {}})
                for k in FIELDS:
                    if k in cur and k not in other:
                        other[k] = twin(cur[k]) or cur[k] if k == "on" and isinstance(cur[k], str) else cur[k]
                todo.append((tw, other, fl & fig))
            for n2, c2, m2 in todo:
                Image.fromarray(np.where(m2, 255, 0).astype(np.uint8)).save(mask_path(name, n2, view))
                c2["marks"][view] = {"mark": {k: v for k, v in m.items() if k != "mirror"}, **_geometry(rec, m2)}
                if not set(m) & (set(SHAPES) - {"line"}):
                    c2["marks"][view]["line"] = True  # no width of its own: measured by where it runs, not its size
    if notes is not None:
        fm["notes"] = notes
    save(name, fm)
    return fm


def children(fm: dict, feature: str) -> list[str]:
    """Every feature whose `on` chain leads to `feature`."""
    out, grew = [], True
    while grew:
        grew = False
        for f, c in fm["features"].items():
            if f not in out and f != feature and c.get("on") in [feature, *out]:
                out.append(f)
                grew = True
    return out


def checks(name: str, fm: dict) -> list[str]:
    """What the map still owes, worst first (see the module docstring)."""
    notes = []
    feats = fm["features"]
    for view, rec in fm["views"].items():
        fig = np.asarray(Image.open(rec["image"]).convert("RGBA"))[..., 3] > 127
        cover = np.zeros_like(fig)
        for f, c in feats.items():
            if view in c["marks"]:
                cover |= mask(name, f, view)
        free = fig & ~cover
        share = free.sum() / max(fig.sum(), 1)
        if share > UNMARKED:
            from scipy import ndimage
            lab = refread.patches(name, view)
            ids, n = np.unique(lab[free], return_counts=True)
            tot = {int(i): int((lab == i).sum()) for i in ids}
            big = [(int(i), int(c)) for i, c in zip(ids, n) if i and c > 0.5 * tot[int(i)] and c > 0.003 * fig.sum()]
            big.sort(key=lambda t: -t[1])
            cc, k = ndimage.label(free)
            sizes = ndimage.sum(free, cc, range(1, k + 1))
            found = ndimage.find_objects(cc)
            boxes = [found[i] for i in np.argsort(sizes)[::-1][:3]]
            where = "; ".join(f"x {b[1].start}-{b[1].stop} y {b[0].start}-{b[0].stop}" for b in boxes)
            notes.append(f"UNMARKED {view}: {share:.0%} of the figure belongs to no feature (owed above {UNMARKED:.0%}; "
                         f"hatched pink in the picture). Biggest pieces, view px: {where}"
                         + (f"; whole patches {[i for i, _ in big[:14]]}" if big else "")
                         + ". Mark them, or draw the mass they belong to wider: a mark may overrun the outline")
    for f, c in feats.items():
        ortho = {v: g["world"] for v, g in c["marks"].items() if "world" in g}
        if len(ortho) >= 2 and not c.get("authority"):
            los, his = [w["z_lo"] for w in ortho.values()], [w["z_hi"] for w in ortho.values()]
            tol = max(0.015, 0.2 * max(h - lo for h, lo in zip(his, los)))
            if max(los) - min(los) > tol or max(his) - min(his) > tol:
                span = ", ".join(f"{v} z {w['z_lo']:.3f}-{w['z_hi']:.3f}" for v, w in ortho.items())
                notes.append(f"DISAGREE {f}: {span}: the views don't put it at the same height; check the marks, or "
                             f"say which view is the authority")
        for v, g in c["marks"].items():
            rec = fm["views"][v]
            if f[-2:] in (".L", ".R") and rec["kind"] in ("front", "back") and g["area_px"]:
                right_of = g["centre_px"][0] > rec["centre_px"]
                left_side = (rec["kind"] == "front") == right_of  # front: its left is at the picture's right
                if left_side != f.endswith(".L") and abs(g["centre_px"][0] - rec["centre_px"]) > 3:
                    notes.append(f"SIDE {f} in {v}: it is marked on the creature's {'left' if left_side else 'right'} "
                                 f"(in a front view its left is at the picture's RIGHT; in a back view at the left)")
            if f.endswith(".R") and rec["kind"] == "side" or f.endswith(".L") and rec["kind"] == "side_r":
                notes.append(f"SIDE {f} in {v}: this view shows the creature's other side")
        if c.get("on") and c["on"] not in feats:
            notes.append(f"ON {f}: it sits on {c['on']!r}, which is not a feature (have {sorted(feats)[:8]}...)")
        if c["kind"] != "mass" and not c.get("on"):
            notes.append(f"ON {f}: a {c['kind']} sits on a mass: say which (on=)")
        if c["kind"] == "mass" and len(c["marks"]) == 1 and not c.get("inferred"):
            notes.append(f"DEPTH {f}: a mass marked in one view only ({next(iter(c['marks']))}): its depth is a guess; "
                         f"mark it in a second view (any other picture that shows it), or say so in inferred=")
    return notes


def table(fm: dict) -> str:
    rows = []
    for f, c in sorted(fm["features"].items(), key=lambda t: (t[1].get("on") or "", t[0])):
        where = []
        for v, g in c["marks"].items():
            w = g.get("world")
            where.append(f"{v} " + (f"z {w['z_lo']:.2f}-{w['z_hi']:.2f} {w['w'] * 100:.0f}x{w['h'] * 100:.0f}cm" if w
                                    else f"{g['box'][2] - g['box'][0]}x{g['box'][3] - g['box'][1]}px"))
        tags = [c["kind"]] + ([f"on {c['on']}"] if c.get("on") else []) + (["separate"] if c.get("separate") else [])
        tags += ([f"join: {c['join']}"] if c.get("join") else []) + ([f"made by {c['elements']}"] if c.get("elements") else [])
        rows.append(f"  {f}: {', '.join(tags)} | {'; '.join(where)}")
    return "\n".join(rows)


def draw(name: str, view: str, fm: dict, focus=None, width: int = 900) -> Image.Image:
    """The view with every feature marked in it outlined and named (masses thick, forms thin, paint dashed grey);
    what belongs to no feature is hatched pink."""
    from scipy import ndimage
    rec = fm["views"][view]
    rgba = np.asarray(Image.open(rec["image"]).convert("RGBA"))
    fig = rgba[..., 3] > 127
    fg = rgba[..., 3:4] / 255.0
    pic = (rgba[..., :3] * fg + 255 * (1 - fg)) * 0.55 + 255 * 0.45
    H, W = pic.shape[:2]
    x0, y0, x1, y1 = (max(int(v), 0) for v in (focus or (0, 0, W, H)))
    x1, y1 = min(x1, W), min(y1, H)
    s = width / max(x1 - x0, 1)
    up = max(1, int(round(s)))  # outlines are drawn on a whole-number enlargement, then fitted to `width`
    big = np.repeat(np.repeat(pic[y0:y1, x0:x1], up, 0), up, 1).astype(np.uint8)
    names = [f for f, c in fm["features"].items() if view in c["marks"]]
    order = sorted(names, key=lambda f: -fm["features"][f]["marks"][view]["area_px"])
    cover = np.zeros((H, W), bool)
    labels = []
    for n, f in enumerate(order):
        c = fm["features"][f]
        col = (110, 110, 110) if c["kind"] == "paint" else PALETTE[n % len(PALETTE)]
        full = mask(name, f, view)
        cover |= full
        mk = np.repeat(np.repeat(full[y0:y1, x0:x1], up, 0), up, 1)
        if not mk.any():
            continue
        edge = mk & ~ndimage.binary_erosion(mk, iterations=max(1, (3 if c["kind"] == "mass" else 1) * up // 3))
        if c["kind"] == "paint":
            yy, xx = np.indices(mk.shape)
            edge &= ((xx + yy) // 4) % 2 == 0
        big[edge] = col
        sub = full[y0:y1, x0:x1]
        dist = ndimage.distance_transform_edt(sub)
        cy, cx = np.unravel_index(dist.argmax(), dist.shape)
        labels.append(((cx + 0.5) * s, (cy + 0.5) * s, f, col))
    free = np.repeat(np.repeat((fig & ~cover)[y0:y1, x0:x1], up, 0), up, 1)
    yy, xx = np.indices(free.shape)
    big[free & (((xx - yy) // 3) % 2 == 0)] = (255, 60, 200)
    im = Image.fromarray(big).resize((width, int(round((y1 - y0) * s))), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    for cx, cy, f, col in labels:
        d.text((cx, cy), f, fill=col, font=refread._font(13), anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255))
    return refread._ruler(im, (x0, y0, x1, y1), s, refread.nice_step(x1 - x0))


def draw_all(name: str, fm: dict, height: int = 760) -> Image.Image:
    """Every view's map side by side (for one look at the whole map; `draw` one view for the rulers' detail)."""
    tiles = []
    for v, rec in fm["views"].items():
        w = max(160, int(height * rec["size"][0] / rec["size"][1]))
        tiles.append((v, draw(name, v, fm, width=w)))
    out = Image.new("RGB", (sum(t.width for _, t in tiles) + 10 * len(tiles), max(t.height for _, t in tiles) + 22), (255, 255, 255))
    d, x = ImageDraw.Draw(out), 0
    for v, t in tiles:
        d.text((x + 36, 3), v, fill=(0, 0, 0), font=refread._font(14))
        out.paste(t, (x, 22))
        x += t.width + 10
    return out
