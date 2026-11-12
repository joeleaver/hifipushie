"""Measure a model against its feature map (featuremap.py), feature by feature, from each reference view's camera:
is the feature MADE, is it where the picture has it, is it the picture's size, does it cover the picture's mark.

Why: an outline score passes a box-headed block-in (Baynard's Scraps: 88 % overlap, no muzzle, sockets, brows or
mouth). The outline is one row of this table; the features inside it are all the others.

A feature's FOOTPRINT in a view is what is SEEN OF THE THING ITSELF.
- An ADDED shape (a blob, a bone, a loft, a sheet) owns the skin nearest its own surface (`owners`): every visible
  pixel has one owner among the added shapes of the front part there. Blended shapes share a skin, and an eye
  splits it that way: taking a shin out would also move the foot's rim and the hip, but those are not the leg.
- A SHELL part (clothing laid over another part) is owned whole by its elements.
- A CUT or a STROKE owns nothing; its footprint is the pixels whose first surface moves when it is taken out of
  the spec, inside its own bounds, measured in its own box at a finer voxel than the whole model's.
A mass counts the forms on it (they are its surface), not the masses on it: where an eye stands in front of a
head, that pixel is the eye's. A feature with nothing showing from a view is HIDDEN there.
The picture's side of the comparison is the same thing: the feature's mark, less the marks of the masses on it.
Paint has no shape and is not measured here.

Before measuring, each flat view is laid on the model (align_flat): the sheet's scale, each view's ground row and
a side view's centre line are fitted to the model's outline and what moved is reported, because no picture says
how tall a model was built or where its origin is. The whole outline's overlap with each picture leads the report.

Per feature and view (rows where the map has a mark and the view has a camera):
  NOT MADE  no model element is named for it        HIDDEN   made, but not seen from this view
  right     centre within `off` (mm, or a share of the mark's smaller side), both sizes within `size`, overlap
            (how much of each lies within 2 mm of the other, averaged) at least `iou`; a mark that is only a LINE has no size: right when the
            model has form along most of it; a mark of a few pixels is measured by its place only.
            The footprint's pieces that reach the mark are the ones compared (taking a thigh out also moves the
            hip: not the leg the picture marks), and only changes inside the removed shapes' own bounds count (a
            blend sags a millimetre on its neighbours)
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

from . import featurealign, featuremap, matched, refread, sdf, store
from .featurerays import depth_image, first_hit, rays, relief  # noqa: F401  (the pictures and tests use them from here)
from .spec import compile_prims

TOL = {"off_mm": 5.0, "off_share": 0.2, "size": (0.75, 1.33), "iou": 0.5, "line_mm": 6.0, "line_along": 0.6,
       "small_px": 40, "give_mm": 2.0}
IN_MASS = "="  # elements ["="]: the form is made by the shape of the mass it is on, with no element of its own


def expanded(spec: dict, name: str | None = None) -> dict:
    """The spec with kits and strokes turned into their pieces and every ".L" mirrored, symmetry off: each element
    is there under its own name, and taking one out takes out only that one. With `name` it is kept beside the
    model's map for that exact spec (seating a figure's strokes takes half a minute), provided the kept copy
    compiles to the very same shapes."""
    import copy
    import json as _json
    from .spec import expand_mirror, geometry
    q = None
    if name:
        q = featuremap.path(name).with_name(f"_ex_{_h(geometry(spec))}.json")
        if q.exists():
            try:
                return _json.loads(q.read_text())
            except Exception:  # noqa: BLE001  (a kept copy that can't be read is made again)
                pass
    ex = copy.deepcopy(expand_mirror(spec))
    ex["symmetry"] = False
    if q is not None:
        for old in q.parent.glob("_ex_*.json"):
            old.unlink()
        back = _json.loads(_json.dumps(ex, default=float))
        if [sdf.fingerprint(p) for p in compile_prims(back)] == [sdf.fingerprint(p) for p in compile_prims(ex)]:
            q.write_text(_json.dumps(back))
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
            if not got and pat in kits:  # a kit's pieces carry its name in front, and its side at the end
                side = pat[-2:] if pat[-2:] in (".L", ".R") else ""
                base = pat[:len(pat) - len(side)]
                got = {n for n in names if n.startswith(base + "_") and n.endswith(side)
                       and (side or n[-2:] not in (".L", ".R"))} or {n for n in names if n.startswith(base + "_")}
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
    left = {v.get("part", "body") for kind in ("blobs", "bones") for v in out[kind].values()}
    parts = out.get("parts") or {}
    if any(isinstance(d, dict) and d.get("shell") and k not in left for k, d in parts.items()):
        out["parts"] = {k: d for k, d in parts.items() if not (isinstance(d, dict) and d.get("shell") and k not in left)}
    return out


def _pieces(prims: list, gap: float = 0.03, most: int = 24) -> list[list]:
    """Primitives grouped into pieces whose boxes lie within `gap` of each other (one group if there are too many)."""
    n = len(prims)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(n):
        for j in range(i + 1, n):
            if np.all(prims[i].lo - gap <= prims[j].hi) and np.all(prims[j].lo - gap <= prims[i].hi):
                parent[find(i)] = find(j)
    groups: dict[int, list] = {}
    for i, p in enumerate(prims):
        groups.setdefault(find(i), []).append(p)
    return list(groups.values()) if len(groups) <= most else [prims]


def _tidy(mask: np.ndarray) -> np.ndarray:
    """A footprint without its slivers: a connected bit under a twentieth of the biggest bit is where taking the
    feature out nudged a blend somewhere else (a hip above the belt when a thigh goes), not the feature. Pieces of
    like size (a scatter of bumps, a row of teeth) all stay."""
    if not mask.any():
        return mask
    lab, n = ndimage.label(mask)
    if n <= 1:
        return mask
    size = ndimage.sum(mask, lab, range(1, n + 1))
    return np.isin(lab, np.where(size >= 0.05 * size.max())[0] + 1)


def _span(idx: np.ndarray) -> float:
    """A mask's extent along one axis, from its pixels' 1st to 99th percentile (a stray pixel doesn't set a size)."""
    lo, hi = np.percentile(idx, [1, 99])
    return float(hi - lo + 1)


def _mass_of(fm: dict, feature: str) -> str | None:
    """The nearest mass a form (or paint) sits on, up its `on` chain."""
    seen, f = set(), fm["features"][feature].get("on")
    while f and f in fm["features"] and f not in seen:
        if fm["features"][f].get("kind") == "mass":
            return f
        seen.add(f)
        f = fm["features"][f].get("on")
    return None


def fitted(name: str, fm: dict, feature: str, view: str) -> np.ndarray:
    """The feature's mark in a view. Where the feature names a flat view to believe (`authority`) and this is
    another flat view, the mark's heights are fitted to that view's, as build_masses fits them: two views that
    disagree about a height can't both be matched, and the sculptor has said which one counts."""
    mk = featuremap.mask(name, feature, view)
    c = fm["features"][feature]
    auth, rec = c.get("authority"), fm["views"][view]
    if not auth or auth == view or auth not in c["marks"] or not mk.any():
        return mk.copy()
    ra = fm["views"].get(auth) or {}
    if rec.get("kind") not in refread.ORTHO or ra.get("kind") not in refread.ORTHO:
        return mk.copy()
    ya = np.where(featuremap.mask(name, feature, auth).any(1))[0]
    yb = np.where(mk.any(1))[0]
    if not len(ya) or yb[-1] == yb[0]:
        return mk.copy()
    a_hi, a_lo = ((ra["ground_px"] - y) * ra["m_per_px"] for y in (ya[0], ya[-1] + 1))  # metres, top and bottom
    t0, t1 = (rec["ground_px"] - z / rec["m_per_px"] for z in (a_hi, a_lo))             # this view's rows for them
    out = np.zeros_like(mk)
    rows = np.arange(int(np.floor(t0)), int(np.ceil(t1)))
    rows = rows[(rows >= 0) & (rows < mk.shape[0])]
    src = yb[0] + (rows + 0.5 - t0) * (yb[-1] + 1 - yb[0]) / max(t1 - t0, 1e-9)
    out[rows] = mk[np.clip(src.astype(int), yb[0], yb[-1])]
    return out


def seen_mark(name: str, fm: dict, feature: str, view: str) -> np.ndarray:
    """The feature's mark in a view, less the marks of the masses on it: what the picture shows of the thing itself."""
    mk = fitted(name, fm, feature, view)
    for ch in featuremap.children(fm, feature):
        c = fm["features"][ch]
        if c.get("kind") == "mass" and view in c["marks"]:
            mk &= ~featuremap.mask(name, ch, view)
    return mk


def _h(*parts) -> str:
    import hashlib
    import json as _json
    return hashlib.sha1(_json.dumps(parts, sort_keys=True, default=float).encode()).hexdigest()[:20]


class _Kept:
    """What a report worked out for one state of a model, kept beside its map (<model>/features/_fp): the whole
    model's grids, each view's first surface and owners, each cut's or stroke's footprint. A new state of the
    model empties it; a changed mark or link costs only what it changes."""

    def __init__(self, name: str | None, base: str):
        self.dir = None
        if name:
            self.dir = featuremap.path(name).with_name("_fp")
            self.dir.mkdir(exist_ok=True)
            tag = self.dir / "base"
            if not tag.exists() or tag.read_text() != base:
                for q in self.dir.glob("*.npz"):
                    q.unlink()
                tag.write_text(base)

    def get(self, key: str):
        q = self.dir / f"{key}.npz" if self.dir else None
        if q is None or not q.exists():
            return None
        try:
            with np.load(q, allow_pickle=False) as z:
                return {k: z[k] for k in z.files}
        except Exception:  # noqa: BLE001  (a file cut short is worked out again)
            return None

    def put(self, key: str, **arrays) -> None:
        if self.dir:
            np.savez_compressed(self.dir / f"{key}.npz", **arrays)


def owners(prims: list, shells: set, whole: sdf.Grid, cam: dict, depth: np.ndarray, front: np.ndarray, part_ids: list):
    """Which element OWNS the surface each pixel sees: of the added shapes in the front part there, the one whose
    own surface is nearest the point. Blended shapes share a skin, and this is how an eye splits it: the hand's
    skin is the hand's, though taking the forearm out would move it. A shell part (clothing laid over another
    part) is owned whole, as "part:<name>". Returns (index map, -1 where nothing owns; the names)."""
    names = sorted({p.name for p in prims if p.op == "add" and p.part not in shells}) + [f"part:{q}" for q in sorted(shells)]
    at = {n: i for i, n in enumerate(names)}
    W, H = cam["size"]
    ys, xs = np.mgrid[0:H, 0:W]
    C, d, _ = rays(cam, np.stack([xs.ravel() + 0.5, ys.ravel() + 0.5], 1))
    hit = np.isfinite(depth).ravel()
    P = C + np.where(hit, depth.ravel(), 0.0)[:, None] * d
    own = np.full(H * W, -1)
    best = np.full(H * W, np.inf)
    fr = front.ravel()
    for qi, q in enumerate(part_ids):
        here = hit & (fr == qi)
        if not here.any():
            continue
        if q in shells:
            own[here] = at[f"part:{q}"]
            continue
        idx = np.where(here)[0]
        pts = P[idx]
        for p in prims:
            if p.part != q or p.op != "add":
                continue
            m = 0.01 + float(np.max(p.reach)) + whole.voxel
            near = np.all((pts >= p.lo - m) & (pts <= p.hi + m), 1)
            if not near.any():
                continue
            dist = sdf.field_at([p], pts[near], clip=False)
            k = idx[near]
            better = dist < best[k]
            best[k[better]] = dist[better]
            own[k[better]] = at[p.name]
    return own.reshape(H, W), names


def footprints(spec: dict, fm: dict, elements: dict, views: list[str], cams: dict, resolution: int = 144,
               ex: dict | None = None, name: str | None = None) -> dict:
    """{(feature, view): bool mask at the view's size} for every made feature marked in a view with a camera;
    "notes" {feature: why it could not be measured}."""
    from .spec import SpecError
    ex = ex or expanded(spec)
    kits = tuple(spec.get("kits") or ())
    prims = compile_prims(ex)
    prints = {sdf.fingerprint(p) for p in prims}
    kept = _Kept(name, _h(VERSION, resolution, sorted((p.name, sdf.fingerprint(p)) for p in prims)))
    got = kept.get("whole")
    if got is None:
        frame = sdf.frame(prims, resolution)
        fields = {ps[0].part: sdf.evaluate(ps, at=frame).field for ps in sdf.streams(prims)}
        got = {"fields": np.stack(list(fields.values())).astype(np.float32), "parts": np.array(list(fields)),
               "origin": np.asarray(frame[0], float), "voxel": np.array(float(frame[1]))}
        kept.put("whole", **got)
    part_ids = [str(q) for q in got["parts"]]
    part_fields = got["fields"].astype(float)
    whole = sdf.Grid(part_fields.min(0), got["origin"], float(got["voxel"]))
    # a model built from the map (build_masses) lives where the pictures put it: only a model made some other way
    # is laid under the views first
    moved_views = featurealign.align_flat(name, fm, cams, whole) if name and fm.get("frame") != "map" else []
    shells = {k for k, dfn in (ex.get("parts") or {}).items() if isinstance(dfn, dict) and dfn.get("shell")}
    part_of = {n: e.get("part", "body") for kind in ("blobs", "bones") for n, e in ex[kind].items()}
    adds = {p.name for p in prims if p.op == "add" and p.part not in shells}
    owner_names = sorted({p.name for p in prims if p.op == "add" and p.part not in shells}) + [f"part:{q}" for q in sorted(shells)]
    deep, front, owner = {}, {}, {}
    for v in views:  # the whole model's first surface, which part it belongs to, and which shape owns it
        vkey = "view_" + _h(cams[v])
        seen = kept.get(vkey)
        if seen is None:
            d0 = depth_image(whole, cams[v])
            W, H = cams[v]["size"]
            ys, xs = np.mgrid[0:H, 0:W]
            C, d, _ = rays(cams[v], np.stack([xs.ravel() + 0.5, ys.ravel() + 0.5], 1))
            hit = np.isfinite(d0).ravel()
            P = C + np.where(hit, d0.ravel(), 0.0)[:, None] * d
            idx = ((P - whole.origin) / whole.voxel).T
            val = np.stack([ndimage.map_coordinates(g, idx, order=1, mode="constant", cval=1.0) for g in part_fields])
            f0 = np.where(hit, val.argmin(0), -1).reshape(H, W)
            o0, _ = owners(prims, shells, whole, cams[v], d0, f0, part_ids)
            seen = {"deep": d0, "front": f0, "owner": o0}
            kept.put(vkey, **seen)
        deep[v], front[v], owner[v] = seen["deep"], seen["front"], seen["owner"]
    lo_all = np.min([p.lo for p in prims], 0)
    hi_all = np.max([p.hi for p in prims], 0)
    out, notes = {}, {}
    for f, pats in elements.items():
        marked = [v for v in views if v in fm["features"][f]["marks"]]
        if not marked or not pats:
            continue
        names, _ = resolve(ex, pats, kits)
        own_names = set(names)
        for ch in featuremap.children(fm, f):  # its forms are its surface; the masses on it are their own
            if elements.get(ch) and fm["features"][ch].get("kind") == "form" and _mass_of(fm, ch) == f:
                names |= resolve(ex, elements[ch], kits)[0]
        # an added shape's footprint is the skin it owns; a shell part's is the whole shell. What is left (a cut,
        # a stroke that pushes skin) owns nothing and is found by taking it out and seeing what changes
        mine_idx = [owner_names.index(n) for n in names if n in adds] + \
                   [owner_names.index(f"part:{part_of[n]}") for n in names if part_of.get(n) in shells]
        for v in marked:
            out[(f, v)] = np.isin(owner[v], mine_idx) if mine_idx else np.zeros(owner[v].shape, bool)
        names = {n for n in own_names if n not in adds and part_of.get(n) not in shells}
        if not names:
            for v in marked:
                out[(f, v)] = _tidy(out[(f, v)])
            if not mine_idx:
                notes[f] = "its elements shape nothing"
            continue
        rkeys = {v: "rm_" + _h(sorted(names), cams[v]) for v in marked}
        had = {v: kept.get(rkeys[v]) for v in marked}
        if all(h is not None for h in had.values()):
            for v in marked:
                out[(f, v)] = _tidy(out[(f, v)] | had[v]["mask"])
            continue
        try:
            rest = compile_prims(without(ex, names))
        except SpecError as e:
            notes[f] = f"can't be taken out of the model on its own ({e})"
            continue
        rprints = {sdf.fingerprint(p) for p in rest}
        mine = [p for p in prims if sdf.fingerprint(p) not in rprints] + [p for p in rest if sdf.fingerprint(p) not in prints]
        if not mine:
            if not mine_idx:
                notes[f] = "its elements shape nothing"
            continue
        # only the parts the feature's own elements belong to: a shell over them (clothing) is another part's
        own = {p.part for p in mine}
        pa, pr = [p for p in prims if p.part in own], [p for p in rest if p.part in own]
        own_ids = [part_ids.index(q) for q in own if q in part_ids]
        took = {v: np.zeros(owner[v].shape, bool) for v in marked}
        for piece in _pieces(mine):  # pieces far apart (a scatter of bumps) are each measured in their own box
            pad = 0.012 + float(np.max([np.max(p.reach) for p in piece]))
            lo = np.maximum(np.min([p.lo for p in piece], 0) - pad, lo_all - 0.012)
            hi = np.minimum(np.max([p.hi for p in piece], 0) + pad, hi_all + 0.012)
            # fine enough for the smallest piece (a wart, a crease), within a grid of at most 150 cells a side
            sized = [p for p in piece if p.name in own_names] or piece  # (forms on a mass don't set the mass's grid)
            small = float(np.min([np.min(p.hi - p.lo) for p in sized]))
            voxel = float(np.clip(min((hi - lo).max() / 72, small / 3), max((hi - lo).max() / 150, 0.0008), whole.voxel))
            shape = tuple(int(n) for n in np.ceil((hi - lo) / voxel) + 1)
            at = (lo, voxel, shape)
            g_all = sdf.evaluate(pa, at=at) if pa else sdf.Grid(np.ones(shape), lo, voxel)
            g_rest = sdf.evaluate(pr, at=at) if pr else sdf.Grid(np.ones(shape), lo, voxel)
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
                    # only inside the shapes that went: beside them the blend sags a millimetre or two on their
                    # neighbours (a foot's rim when a shin goes), which is not the feature
                    inside = np.zeros(da.shape, bool)
                    for p in piece:
                        c8 = p.lo + (p.hi - p.lo) * np.array([[i, j, k] for i in (0, 1) for j in (0, 1) for k in (0, 1)])
                        q, _ = matched.project(c8, cam)
                        a0, b0 = np.floor(q.min(0)).astype(int) - 2 - np.array(box[:2])
                        a1, b1 = np.ceil(q.max(0)).astype(int) + 3 - np.array(box[:2])
                        inside[max(b0, 0):max(b1, 0), max(a0, 0):max(a1, 0)] = True
                    moved &= inside
                    sub = (slice(box[1], box[3]), slice(box[0], box[2]))
                    seen = (np.isin(front[v][sub], own_ids) | (front[v][sub] < 0)) \
                        & (near <= deep[v][sub] + max(1.2 * whole.voxel, 0.006))
                    took[v][sub] |= moved & seen & np.isfinite(near)
        for v in marked:
            kept.put(rkeys[v], mask=took[v])
            out[(f, v)] = _tidy(out[(f, v)] | took[v])
    return {"masks": out, "depth": deep, "voxel": whole.voxel, "notes": notes, "moved_views": moved_views}


def _line_row(f: str, v: str, ref: np.ndarray, mod: np.ndarray, m_per_px: float, tol: dict) -> dict:
    """A mark that is a line has no size of its own: is there model form along it?"""
    reach = max(tol["line_mm"] / 1000 / m_per_px, 3.0)
    near = ndimage.distance_transform_edt(~mod) <= reach
    along = float((ref & near).sum() / max(ref.sum(), 1))
    ok = along >= tol["line_along"]
    return {"feature": f, "view": v, "status": "right" if ok else "OFF", "along": round(along, 2), "iou": round(along, 2),
            "how": f"form along {along:.0%} of the line",
            "why": "" if ok else f"the model's form runs along {along:.0%} of the line (within {tol['line_mm']:.0f} mm)"}


def _at_mark(ref: np.ndarray, mod: np.ndarray) -> np.ndarray:
    """The footprint's pieces that reach the mark (within a sixth of its smaller side), or its biggest piece when
    none does. Taking a thigh out also moves the hip above the belt: that is not the leg the picture marks."""
    lab, n = ndimage.label(mod)
    if n <= 1:
        return mod
    ry, rx = np.where(ref)
    reach = max(3, int(round(0.16 * min(np.ptp(rx) + 1, np.ptp(ry) + 1))))
    near = ndimage.binary_dilation(ref, iterations=reach)
    hit = np.unique(lab[near & mod])
    if len(hit):
        return np.isin(lab, hit)
    size = ndimage.sum(mod, lab, range(1, n + 1))
    return lab == int(np.argmax(size)) + 1


def _row(f: str, v: str, ref: np.ndarray, mod: np.ndarray, m_per_px: float, tol: dict, line: bool = False) -> dict:
    ry, rx = np.where(ref)
    if not mod.any():
        return {"feature": f, "view": v, "status": "HIDDEN", "why": "made, but nothing of it is seen from this view"}
    if line:
        return _line_row(f, v, ref, mod, m_per_px, tol)
    mod = _at_mark(ref, mod)
    if ref.sum() < tol["small_px"] or min(np.ptp(rx), np.ptp(ry)) + 1 < 5:  # a few pixels: where it is, not its shape
        my, mx = np.where(mod)
        d = float(np.hypot(mx.mean() - rx.mean(), my.mean() - ry.mean())) * m_per_px * 1000
        ok = d <= max(tol["off_mm"], 1.5 * m_per_px * 1000)
        return {"feature": f, "view": v, "status": "right" if ok else "OFF", "iou": 1.0 if ok else 0.0, "small": True,
                "how": "in place (too small in this picture to measure its size)",
                "why": "" if ok else f"the model's is {d:.0f} mm from the mark (too small in this picture to measure its size)"}
    my, mx = np.where(mod)
    dx = (mx.mean() - rx.mean()) * m_per_px * 1000
    dy = (ry.mean() - my.mean()) * m_per_px * 1000   # up is +
    rw, rh = _span(rx), _span(ry)
    sw, shh = _span(mx) / rw, _span(my) / rh
    give = max(1, int(round(tol["give_mm"] / 1000 / m_per_px)))  # each side may be this far out before it counts
    rd, md = ndimage.binary_dilation(ref, iterations=give), ndimage.binary_dilation(mod, iterations=give)
    iou = 0.5 * float((ref & md).sum() / max(ref.sum(), 1) + (mod & rd).sum() / max(mod.sum(), 1))
    limit = max(tol["off_mm"], tol["off_share"] * min(rw, rh) * m_per_px * 1000)
    faults = []
    if np.hypot(dx, dy) > limit:
        faults.append((np.hypot(dx, dy) / limit, f"the model's middle is {abs(dx):.0f} mm to the picture's "
                                                 f"{'right' if dx > 0 else 'left'} of the mark's and {abs(dy):.0f} mm "
                                                 f"{'above' if dy > 0 else 'below'} it"))
    for s, word in ((sw, "wide"), (shh, "tall")):
        if not tol["size"][0] <= s <= tol["size"][1]:
            faults.append((max(s, 1 / s), f"the model's is {s:.0%} as {word} as the mark"))
    if iou < tol["iou"]:
        faults.append((tol["iou"] / max(iou, 0.05), f"model and mark overlap {iou:.0%}"))
    faults.sort(key=lambda t: -t[0])
    return {"feature": f, "view": v, "status": "OFF" if faults else "right", "dx_mm": round(float(dx), 1),
            "dy_mm": round(float(dy), 1), "wide": round(float(sw), 2), "tall": round(float(shh), 2),
            "iou": round(iou, 2), "why": "; ".join(t for _, t in faults)}


VERSION = 13  # bump when a report's numbers change for the same model and map (kept reports are then redone)


def _key(name: str, views, resolution: int, tol: dict) -> str:
    import hashlib
    import json as _json
    h = hashlib.sha1(repr((VERSION, sorted(views or []), resolution, sorted(tol.items()))).encode())
    h.update(_json.dumps(store.load(name), sort_keys=True, default=float).encode())
    h.update(featuremap.path(name).read_bytes())
    for q in sorted((store._dir(name) / "cameras").glob("*.json")):
        h.update(q.read_bytes())
    return h.hexdigest()


def report(name: str, elements: dict | None = None, views: list[str] | None = None, resolution: int = 144,
           tol: dict | None = None) -> dict:
    """The table (see the module docstring). `elements` {feature: [element patterns]} is remembered in the map.
    The last report is kept beside the map and returned as it is while the model, the map, the cameras and the
    settings are unchanged."""
    import gzip
    import pickle
    rep = _report(name, elements, views, resolution, tol, peek=True)
    if rep is not None:
        return rep
    rep = _report(name, elements, views, resolution, tol)
    rep["key"] = _key(name, views, resolution, {**TOL, **(tol or {})})
    with gzip.open(featuremap.path(name).with_name("report.pkl.gz"), "wb", compresslevel=3) as fh:
        pickle.dump(rep, fh, protocol=4)
    return rep


def _report(name: str, elements, views, resolution: int, tol, peek: bool = False):
    """peek=True: the kept report if it still holds for these arguments (after `elements` are written), else None."""
    fm = featuremap.load(name)
    if not fm["features"]:
        raise ValueError(f"{name} has no feature map: read_reference, then mark_features")
    for f, pats in (elements or {}).items():
        if f not in fm["features"]:
            raise ValueError(f"no feature {f!r} (have {sorted(fm['features'])})")
        fm["features"][f]["elements"] = list(pats or [])
    tol = {**TOL, **(tol or {})}
    if peek:
        import gzip
        import pickle
        kept = featuremap.path(name).with_name("report.pkl.gz")
        same = {f: c.get("elements") or [] for f, c in featuremap.load(name)["features"].items()} == \
               {f: c.get("elements") or [] for f, c in fm["features"].items()}
        if not kept.exists() or not same:
            return None
        try:
            with gzip.open(kept, "rb") as fh:
                rep = pickle.load(fh)
        except Exception:  # noqa: BLE001  (a kept report that can't be read is redone)
            return None
        return rep if rep.get("key") == _key(name, views, resolution, tol) else None
    cams, skipped = {}, []
    for v in views or list(fm["views"]):
        if matched.cam_path(name, v).exists():
            cams[v] = matched.load_camera(name, v)
        else:
            skipped.append(v)
    spec = store.load(name)
    made = {f: (c.get("elements") or []) if c["kind"] != "paint" else [] for f, c in fm["features"].items()}
    ex = expanded(spec, name)
    bad = {f: resolve(ex, pats, tuple(spec.get("kits") or ()))[1] for f, pats in made.items() if pats and pats != [IN_MASS]}
    bad = {f: b for f, b in bad.items() if b}
    if bad:  # every wrong name at once, before anything slow
        raise ValueError("no model element matches, for " + "; ".join(f"{f}: {', '.join(b)}" for f, b in bad.items())
                         + ". Names are the model's own (get_model): blobs, bones, strokes, kits, or part:<part>")
    if elements and not peek:  # remembered only once every name is good
        featuremap.save(name, fm)
    fp = footprints(spec, fm, {f: p for f, p in made.items() if p != [IN_MASS]}, list(cams), cams, resolution, ex, name)
    outline = {}
    for v in cams:  # the whole outline: the one row an outline score ever had
        fig = np.asarray(Image.open(fm["views"][v]["image"]).convert("RGBA"))[..., 3] > 127
        mod = np.isfinite(fp["depth"][v])
        outline[v] = float((fig & mod).sum() / max((fig | mod).sum(), 1))
    rows, _seen = [], {}

    def seen(f_, v_):
        if (f_, v_) not in _seen:
            _seen[(f_, v_)] = seen_mark(name, fm, f_, v_)
        return _seen[(f_, v_)]
    for f, c in fm["features"].items():
        for v in cams:
            if v not in c["marks"] or c["kind"] == "paint":
                continue
            if not made[f]:
                rows.append({"feature": f, "view": v, "status": "NOT MADE", "why": "no model element is named for it"})
                continue
            cam = cams[v]
            k = cam.get("m_per_px") or float(np.nanmedian(np.where(np.isfinite(fp["depth"][v]), fp["depth"][v], np.nan))) / cam["f_px"]
            ref = seen(f, v).copy()
            whole = int(ref.sum())
            if c["kind"] == "mass":  # where the model has another marked mass in front, inside what the picture
                # shows of THAT mass, this one is rightly hidden (a thigh under shorts): a mark may run under a
                # neighbour. (What shows of a mass leaves out the masses on it, so a mass never hides its own child.)
                others = np.zeros_like(ref)
                under, up = set(), c.get("on")
                while up in fm["features"] and up not in under:  # what it sits on, all the way down
                    under.add(up)
                    up = fm["features"][up].get("on")
                for g, cg in fm["features"].items():
                    if g != f and cg["kind"] == "mass" and v in cg["marks"] and (g, v) in fp["masks"] and made.get(g):
                        if g not in under:  # the mass it sits on showing through is "too small", never "hidden"
                            others |= fp["masks"][(g, v)]
                        ref &= ~(fp["masks"][(g, v)] & seen(g, v))
                own = fp["masks"].get((f, v))
                if made[f] != [IN_MASS] and own is not None and own.sum() < 0.3 * whole and \
                        (seen(f, v) & others).sum() >= 0.6 * whole:
                    rows.append({"feature": f, "view": v, "status": "HIDDEN",
                                 "why": "most of its mark here lies behind other masses in the model: judged in its "
                                        "other views"})
                    continue
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
    return {"rows": rows, "by_feature": worst, "skipped_views": skipped, "footprints": fp, "cams": cams, "map": fm,
            "outline": outline, "moved_views": fp["moved_views"]}


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
    from . import refread
    s = width / left.shape[1]
    size = (width, int(left.shape[0] * s))
    box = (0, 0, left.shape[1], left.shape[0])
    tiles = [refread._ruler(Image.fromarray(a).resize(size, Image.LANCZOS), box, s, refread.nice_step(box[2]))
             for a in (left, right)]  # the view's own pixels: a mark can be read straight off either panel
    out = Image.new("RGB", (tiles[0].width + tiles[1].width + 10, tiles[0].height), (255, 255, 255))
    out.paste(tiles[0], (0, 0))
    out.paste(tiles[1], (tiles[0].width + 10, 0))
    return out
