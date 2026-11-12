"""Measure a model against its feature map (featuremap.py), feature by feature, from each reference view's camera:
is the feature MADE, is it where the picture has it, is it the picture's size, does it cover the picture's mark.

Why: an outline score passes a box-headed block-in (Baynard's Scraps: 88 % overlap, no muzzle, sockets, brows or
mouth). The outline is one row of this table; the features inside it are all the others.

A feature's FOOTPRINT in a view is what is SEEN OF THE THING ITSELF: the pixels its elements change, i.e. where
the first surface a pixel's ray meets moves (or appears, or goes) when those elements are taken out of the model.
One rule for every kind of element: an added shape, a cut, a stroke that pushes skin. A mass is taken out together
with the forms on it (they are its surface), but not with the masses on it: where an eye stands in front of a
head, that pixel is the eye's. Pixels where anything else stands in front don't count either (a feature behind
the body has no footprint: HIDDEN). Measured in the feature's own box at a finer voxel than the whole model's.
The picture's side of the comparison is the same thing: the feature's mark, less the marks of the masses on it.
Paint has no shape and is not measured here.

Per feature and view (rows where the map has a mark and the view has a camera):
  NOT MADE  no model element is named for it        HIDDEN   made, but not seen from this view
  right     centre within `off` (mm, or a share of the mark's smaller side), both sizes within `size`, overlap
            (IoU of footprint and mark) at least `iou`; a mark that is only a LINE has no size: right when the
            model has form along most of it
  OFF       otherwise, with the worst number first
  IN ITS MASS  elements ["="]: the sculptor says the mass's own shape makes this form. Not measured: its tile is.
  CAN'T MEASURE  its elements can't be taken out of the model on their own (something else is built on them), or
            they shape nothing; the reason is given
Elements are named as the model has them (get_model): a blob's, bone's, stroke's or kit's own name (a stroke's or
kit's generated pieces come with it; ".R" is the mirrored twin of ".L"), a shell-style pattern ("fr*", "bib?.L"),
or "part:<part>" for every element of a part. They are taken out of the SPEC, so a cut that is folded into the
shape it cuts counts too. Every name is checked before anything is measured.
"""
from __future__ import annotations

import fnmatch

import numpy as np
from PIL import Image
from scipy import ndimage

from . import featuremap, matched, sdf, store
from .spec import compile_prims

CHUNK = 2500
TOL = {"off_mm": 5.0, "off_share": 0.2, "size": (0.75, 1.33), "iou": 0.5, "line_mm": 6.0, "line_along": 0.6}
IN_MASS = "="  # elements ["="]: the form is made by the shape of the mass it is on, with no element of its own


def rays(cam: dict, xy: np.ndarray):
    D, Fw, R, U = matched.axes(cam["az"], cam["el"], cam["roll"])
    C = np.asarray(cam["aim"], float) + cam["dist"] * D
    W, H = cam["size"]
    f = cam["f_px"]
    return C, Fw[None] + ((xy[:, 0] - W / 2) / f)[:, None] * R[None] - ((xy[:, 1] - H / 2) / f)[:, None] * U[None], Fw


def first_hit(grid: sdf.Grid, cam: dict, xy: np.ndarray) -> np.ndarray:
    """Camera depth of the first surface along each pixel's ray through the grid (inf: none), to a fraction of a voxel."""
    C, d, Fw = rays(cam, xy)
    n = np.array(grid.field.shape)
    corners = grid.origin + grid.voxel * (n - 1) * np.array([[i, j, k] for i in (0, 1) for j in (0, 1) for k in (0, 1)])
    z = (corners - C) @ Fw
    zs = np.arange(max(z.min() - grid.voxel, 1e-3), z.max() + grid.voxel, grid.voxel * 0.7)
    out = np.full(len(xy), np.inf)
    for a in range(0, len(xy), CHUNK):
        P = C + zs[None, :, None] * d[a:a + CHUNK, None, :]
        idx = ((P - grid.origin) / grid.voxel).reshape(-1, 3).T
        f = ndimage.map_coordinates(grid.field, idx, order=1, mode="constant", cval=1.0).reshape(P.shape[:2])
        inside = f < 0
        hit = inside.any(1)
        k = inside.argmax(1)
        i = np.where(hit)[0]
        k0 = np.maximum(k[i] - 1, 0)
        f0, f1 = f[i, k0], f[i, k[i]]
        t = np.where(k[i] > 0, f0 / np.maximum(f0 - f1, 1e-9), 1.0)
        out[a + i] = zs[k0] + np.clip(t, 0, 1) * (zs[k[i]] - zs[k0])
    return out


def depth_image(grid: sdf.Grid, cam: dict, box=None) -> np.ndarray:
    W, H = cam["size"]
    x0, y0, x1, y1 = box or (0, 0, W, H)
    ys, xs = np.mgrid[y0:y1, x0:x1]
    return first_hit(grid, cam, np.stack([xs.ravel() + 0.5, ys.ravel() + 0.5], 1)).reshape(ys.shape)


def relief(depth: np.ndarray, m_per_px: float) -> np.ndarray:
    """A grey shaded picture (H, W, uint8) of a depth image, lit from the upper left front; white where empty."""
    d = np.where(np.isfinite(depth), depth, np.nan)
    fill = np.where(np.isnan(d), np.nanmax(d) if np.isfinite(d).any() else 0.0, d)
    fill = ndimage.gaussian_filter(fill, 0.8)
    gy, gx = np.gradient(fill)
    n = np.dstack([gx / m_per_px, -gy / m_per_px, -np.ones_like(fill)])   # camera frame: right, up, toward the eye = -z
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    light = np.array([-0.45, 0.55, -0.70])
    light /= np.linalg.norm(light)
    sh = 0.25 + 0.75 * np.clip(n @ light, 0, 1)
    out = np.where(np.isnan(d), 255, 40 + 190 * sh)
    return out.astype(np.uint8)


def expanded(spec: dict) -> dict:
    """The spec with kits and strokes turned into their pieces and every ".L" mirrored, symmetry off: each element
    is there under its own name, and taking one out takes out only that one."""
    import copy
    from .spec import expand_mirror
    ex = copy.deepcopy(expand_mirror(spec))
    ex["symmetry"] = False
    return ex


def _canon(n: str) -> str:
    """A generated piece's name as its maker's: "fold_r1.L" -> "fold.L", "warts_s7" -> "warts"."""
    import re
    side = n[-2:] if n[-2:] in (".L", ".R") else ""
    return re.sub(r"(_[rs]\d+)+$", "", n[:len(n) - len(side)]) + side


def resolve(ex: dict, patterns, kits=()) -> tuple[set[str], list[str]]:
    """Element patterns -> (names of the expanded spec's blobs and bones they pick, the patterns that pick none)."""
    names = [*ex.get("blobs", {}), *ex.get("bones", {})]
    part = {n: (ex["blobs"].get(n) or ex["bones"].get(n) or {}).get("part", "body") for n in names}
    out, bad = set(), []
    for pat in patterns:
        if pat.startswith("part:"):
            got = {n for n in names if part[n] == pat[5:]}
        else:
            got = {n for n in names if fnmatch.fnmatchcase(n, pat) or fnmatch.fnmatchcase(_canon(n), pat)}
            if not got and pat in kits:  # a kit's pieces carry its name in front
                got = {n for n in names if n.startswith(pat + "_")}
        if not got:
            import difflib
            pool = sorted({_canon(n) for n in names} | {f"part:{p}" for p in set(part.values())} | set(kits))
            near = difflib.get_close_matches(pat, pool, 4, 0.4)
            bad.append(f"{pat!r}" + (f" (near: {', '.join(near)})" if near else ""))
        out |= got
    return out, bad


def without(ex: dict, names: set[str]) -> dict:
    """The expanded spec less the named blobs and bones, and less any cut that shaped only them (a cut's `targets`
    lose the names that went; a cut left with no target goes too)."""
    gone = set(names)
    out = {**ex, "blobs": {k: v for k, v in ex["blobs"].items() if k not in gone},
           "bones": {k: v for k, v in ex["bones"].items() if k not in gone}}
    again = True
    while again:
        again = False
        for kind in ("blobs", "bones"):
            for k, v in list(out[kind].items()):
                t = v.get("targets")
                left = [x for x in t if x not in gone] if t else t
                if t and len(left) != len(t):
                    if left:
                        out[kind][k] = {**v, "targets": left}
                    else:
                        del out[kind][k]
                        gone.add(k)
                        again = True
    return out


def _mass_of(fm: dict, feature: str) -> str | None:
    """The nearest mass a form (or paint) sits on, up its `on` chain."""
    seen, f = set(), fm["features"][feature].get("on")
    while f and f in fm["features"] and f not in seen:
        if fm["features"][f].get("kind") == "mass":
            return f
        seen.add(f)
        f = fm["features"][f].get("on")
    return None


def seen_mark(name: str, fm: dict, feature: str, view: str) -> np.ndarray:
    """The feature's mark in a view, less the marks of the masses on it: what the picture shows of the thing itself."""
    mk = featuremap.mask(name, feature, view).copy()
    for ch in featuremap.children(fm, feature):
        c = fm["features"][ch]
        if c.get("kind") == "mass" and view in c["marks"]:
            mk &= ~featuremap.mask(name, ch, view)
    return mk


def footprints(spec: dict, fm: dict, elements: dict, views: list[str], cams: dict, resolution: int = 144,
               ex: dict | None = None) -> dict:
    """{(feature, view): bool mask at the view's size} for every made feature marked in a view with a camera;
    "notes" {feature: why it could not be measured}."""
    from .spec import SpecError
    ex = ex or expanded(spec)
    kits = tuple(spec.get("kits") or ())
    prims = compile_prims(ex)
    prints = {sdf.fingerprint(p) for p in prims}
    whole = sdf.evaluate(prims, resolution)
    deep = {}
    for v in views:  # the whole model's first surface: at every other pixel, enough to say what stands in front
        W, H = cams[v]["size"]
        ys, xs = np.mgrid[0:H:2, 0:W:2]
        d = first_hit(whole, cams[v], np.stack([xs.ravel() + 1.0, ys.ravel() + 1.0], 1)).reshape(ys.shape)
        deep[v] = np.repeat(np.repeat(d, 2, 0), 2, 1)[:H, :W]
    lo_all = np.min([p.lo for p in prims], 0)
    hi_all = np.max([p.hi for p in prims], 0)
    out, notes = {}, {}
    for f, pats in elements.items():
        marked = [v for v in views if v in fm["features"][f]["marks"]]
        if not marked or not pats:
            continue
        names, _ = resolve(ex, pats, kits)
        for ch in featuremap.children(fm, f):  # its forms are its surface; the masses on it are their own
            if elements.get(ch) and fm["features"][ch].get("kind") == "form" and _mass_of(fm, ch) == f:
                names |= resolve(ex, elements[ch], kits)[0]
        for v in marked:
            out[(f, v)] = np.zeros((cams[v]["size"][1], cams[v]["size"][0]), bool)
        try:
            rest = compile_prims(without(ex, names))
        except SpecError as e:
            notes[f] = f"can't be taken out of the model on its own ({e})"
            continue
        rprints = {sdf.fingerprint(p) for p in rest}
        mine = [p for p in prims if sdf.fingerprint(p) not in rprints] + [p for p in rest if sdf.fingerprint(p) not in prints]
        if not mine:
            notes[f] = "its elements shape nothing"
            continue
        pad = 0.012 + float(np.max([np.max(p.reach) for p in mine]))
        lo = np.maximum(np.min([p.lo for p in mine], 0) - pad, lo_all - 0.012)
        hi = np.minimum(np.max([p.hi for p in mine], 0) + pad, hi_all + 0.012)
        voxel = float(np.clip((hi - lo).max() / 64, 0.001, whole.voxel))
        shape = tuple(int(n) for n in np.ceil((hi - lo) / voxel) + 1)
        at = (lo, voxel, shape)
        g_all = sdf.evaluate(prims, at=at)
        g_rest = sdf.evaluate(rest, at=at) if rest else sdf.Grid(np.ones(shape), lo, voxel)
        corners = lo + (hi - lo) * np.array([[i, j, k] for i in (0, 1) for j in (0, 1) for k in (0, 1)])
        for v in marked:
            cam = cams[v]
            W, H = cam["size"]
            xy, _ = matched.project(corners, cam)
            x0, y0 = np.floor(xy.min(0)).astype(int) - 2
            x1, y1 = np.ceil(xy.max(0)).astype(int) + 2
            box = (max(x0, 0), max(y0, 0), min(x1, W), min(y1, H))
            if box[2] > box[0] and box[3] > box[1]:
                da, dr = depth_image(g_all, cam, box), depth_image(g_rest, cam, box)
                near = np.minimum(da, dr)
                with np.errstate(invalid="ignore"):
                    moved = (np.isfinite(da) != np.isfinite(dr)) | (np.abs(da - dr) > max(0.6 * voxel, 0.0008))
                seen = near <= deep[v][box[1]:box[3], box[0]:box[2]] + 2.5 * whole.voxel
                out[(f, v)][box[1]:box[3], box[0]:box[2]] = ndimage.binary_opening(moved & seen & np.isfinite(near))
    return {"masks": out, "depth": deep, "voxel": whole.voxel, "notes": notes}


def _line_row(f: str, v: str, ref: np.ndarray, mod: np.ndarray, m_per_px: float, tol: dict) -> dict:
    """A mark that is a line has no size of its own: is there model form along it?"""
    reach = max(tol["line_mm"] / 1000 / m_per_px, 3.0)
    near = ndimage.distance_transform_edt(~mod) <= reach
    along = float((ref & near).sum() / max(ref.sum(), 1))
    ok = along >= tol["line_along"]
    return {"feature": f, "view": v, "status": "right" if ok else "OFF", "along": round(along, 2), "iou": round(along, 2),
            "why": "" if ok else f"the model's form runs along {along:.0%} of the line (within {tol['line_mm']:.0f} mm)"}


def _row(f: str, v: str, ref: np.ndarray, mod: np.ndarray, m_per_px: float, tol: dict, line: bool = False) -> dict:
    ry, rx = np.where(ref)
    if not mod.any():
        return {"feature": f, "view": v, "status": "HIDDEN", "why": "made, but nothing of it is seen from this view"}
    if line:
        return _line_row(f, v, ref, mod, m_per_px, tol)
    my, mx = np.where(mod)
    dx = (mx.mean() - rx.mean()) * m_per_px * 1000
    dy = (ry.mean() - my.mean()) * m_per_px * 1000   # up is +
    rw, rh = np.ptp(rx) + 1, np.ptp(ry) + 1
    sw, shh = (np.ptp(mx) + 1) / rw, (np.ptp(my) + 1) / rh
    iou = float((ref & mod).sum() / max((ref | mod).sum(), 1))
    limit = max(tol["off_mm"], tol["off_share"] * min(rw, rh) * m_per_px * 1000)
    faults = []
    if np.hypot(dx, dy) > limit:
        faults.append((np.hypot(dx, dy) / limit, f"centre {abs(dx):.0f} mm {'right' if dx > 0 else 'left'}, "
                                                 f"{abs(dy):.0f} mm {'high' if dy > 0 else 'low'} in the picture"))
    for s, word in ((sw, "wide"), (shh, "tall")):
        if not tol["size"][0] <= s <= tol["size"][1]:
            faults.append((max(s, 1 / s), f"{s:.0%} as {word} as the picture's"))
    if iou < tol["iou"]:
        faults.append((tol["iou"] / max(iou, 0.05), f"covers the mark {iou:.0%}"))
    faults.sort(key=lambda t: -t[0])
    return {"feature": f, "view": v, "status": "OFF" if faults else "right", "dx_mm": round(float(dx), 1),
            "dy_mm": round(float(dy), 1), "wide": round(float(sw), 2), "tall": round(float(shh), 2),
            "iou": round(iou, 2), "why": "; ".join(t for _, t in faults)}


def report(name: str, elements: dict | None = None, views: list[str] | None = None, resolution: int = 144,
           tol: dict | None = None) -> dict:
    """The table (see the module docstring). `elements` {feature: [element patterns]} is remembered in the map."""
    fm = featuremap.load(name)
    if not fm["features"]:
        raise ValueError(f"{name} has no feature map: read_reference, then mark_features")
    for f, pats in (elements or {}).items():
        if f not in fm["features"]:
            raise ValueError(f"no feature {f!r} (have {sorted(fm['features'])})")
        fm["features"][f]["elements"] = list(pats or [])
    tol = {**TOL, **(tol or {})}
    cams, skipped = {}, []
    for v in views or list(fm["views"]):
        if matched.cam_path(name, v).exists():
            cams[v] = matched.load_camera(name, v)
        else:
            skipped.append(v)
    spec = store.load(name)
    made = {f: (c.get("elements") or []) if c["kind"] != "paint" else [] for f, c in fm["features"].items()}
    ex = expanded(spec)
    bad = {f: resolve(ex, pats, tuple(spec.get("kits") or ()))[1] for f, pats in made.items() if pats and pats != [IN_MASS]}
    bad = {f: b for f, b in bad.items() if b}
    if bad:  # every wrong name at once, before anything slow
        raise ValueError("no model element matches, for " + "; ".join(f"{f}: {', '.join(b)}" for f, b in bad.items())
                         + ". Names are the model's own (get_model): blobs, bones, strokes, kits, or part:<part>")
    if elements:  # remembered only once every name is good
        featuremap.save(name, fm)
    fp = footprints(spec, fm, {f: p for f, p in made.items() if p != [IN_MASS]}, list(cams), cams, resolution, ex)
    rows = []
    for f, c in fm["features"].items():
        for v in cams:
            if v not in c["marks"] or c["kind"] == "paint":
                continue
            if not made[f]:
                rows.append({"feature": f, "view": v, "status": "NOT MADE", "why": "no model element is named for it"})
                continue
            cam = cams[v]
            k = cam.get("m_per_px") or float(np.nanmedian(np.where(np.isfinite(fp["depth"][v]), fp["depth"][v], np.nan))) / cam["f_px"]
            ref = seen_mark(name, fm, f, v)
            if not ref.any():  # nothing of it shows past the masses on it: nothing to measure in this view
                continue
            if made[f] == [IN_MASS]:
                rows.append({"feature": f, "view": v, "status": "IN ITS MASS",
                             "why": "made by the shape of the mass it is on: not measured, judge it on its tile"})
                continue
            row = _row(f, v, ref, fp["masks"][(f, v)], k, tol, bool(c["marks"][v].get("line")))
            if f in fp["notes"]:
                row.update(status="CAN'T MEASURE", why=fp["notes"][f])
            rows.append(row)
    worst = {}
    rank = {"NOT MADE": 5, "OFF": 4, "CAN'T MEASURE": 3, "HIDDEN": 2, "IN ITS MASS": 1, "right": 0}
    for r in rows:
        if rank[r["status"]] >= rank.get(worst.get(r["feature"]), -1):
            worst[r["feature"]] = r["status"]
    return {"rows": rows, "by_feature": worst, "skipped_views": skipped, "footprints": fp, "cams": cams, "map": fm}


def draw(name: str, rep: dict, view: str, width: int = 620) -> Image.Image:
    """picture with its marks | the model from the same camera with its footprints (green right, red off)."""
    fm, cam = rep["map"], rep["cams"][view]
    rec = fm["views"][view]
    rgba = np.asarray(Image.open(rec["image"]).convert("RGBA"))
    fg = rgba[..., 3:4] / 255.0
    left = (rgba[..., :3] * fg + 255 * (1 - fg)).astype(np.uint8)
    depth = rep["footprints"]["depth"][view]
    k = cam.get("m_per_px") or float(np.nanmedian(np.where(np.isfinite(depth), depth, np.nan))) / cam["f_px"]
    g = relief(depth, k)
    right = np.dstack([g, g, g])
    status = {r["feature"]: r["status"] for r in rep["rows"] if r["view"] == view}
    for f, st in status.items():
        ref = seen_mark(name, fm, f, view)
        edge = ref & ~ndimage.binary_erosion(ref, iterations=1)
        left[edge] = (0, 0, 0)
        right[edge] = (0, 0, 0) if st != "NOT MADE" else (40, 90, 235)
        mod = rep["footprints"]["masks"].get((f, view))
        if mod is not None and mod.any():
            right[mod & ~ndimage.binary_erosion(mod, iterations=2)] = (30, 160, 60) if st == "right" else (225, 40, 40)
    s = width / left.shape[1]
    size = (width, int(left.shape[0] * s))
    out = Image.new("RGB", (2 * width + 10, size[1]), (255, 255, 255))
    out.paste(Image.fromarray(left).resize(size, Image.LANCZOS), (0, 0))
    out.paste(Image.fromarray(right).resize(size, Image.LANCZOS), (width + 10, 0))
    return out
