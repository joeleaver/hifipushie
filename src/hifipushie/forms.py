"""Forms from their marks: a form marked on a reference's flat view (featuremap.py) is laid on the mass it is `on`
as a stroke (strokes.py), every point of its path a ray from that view through the mark. The sculptor says WHAT
the form is and how far it stands out or sinks; no coordinate is typed.

Why (Baynard Racing, 2026-11-12): two racers stopped at block-in, 18 shapes and no stroke between them, because
every stroke's path had to be typed as surface addresses. A blind block-in built from marks had the best profile
of three sculpts and still a slab for a face: sockets, brows, a muzzle and a fringe are forms, and a character
reads by them. The marks already say where each one is.

A form is built `as`:
  "raise"  the mark stands out of the mass: a strip of clay along the mark's own middle line, as wide at each
           place as the mark is there (masslines.middle), or one dab for a round mark. A `line` mark is a ridge
           along the line (`width`, metres, half across).
  "sink"   the same, pressed in: a hollow for an area, a groove or crease for a line.
  "rim"    a raised ring: round a mark with a hole in it (the ring itself was marked) along the ring's middle;
           round a filled mark just inside its edge (`width`: half the rim's breadth).
`depth` (metres): how far out or in. Left out, it is 0.4 of the form's half breadth (0.8 for a rim, half for a
line): a guess the pictures don't hold from one view, so look at it from the side and set it.
`profile`: "soft" (melts in), "round" (a dome with an edge), "flat" (a plateau), "sharp" (a cusp: creases).
`view`: the flat view to lay it from (default: the one where its mark is largest); a list, or "all", lays it
from each (a band round a limb shows a face to every view). The report measures a form in the views it was laid
from: from any other it is seen in profile. The stroke lands on the part
of the mass the form is `on`, so a mass of another part in front of it (an eyeball, a thing held) is not in the
way. `.L` / `.R`: with symmetry the `.L` form is built and mirrored.
"""
from __future__ import annotations

import numpy as np

from . import featuremap, masslines, refread, store
from . import strokes as strokes_mod
from .spec import SpecError, compile_prims

KINDS = ("raise", "sink", "rim")
# A stroke fades to nothing AT its width, and a path's section is narrower still than a dab's (each place sums the
# dabs along it): what can be SEEN of it (an eighth of its depth or more) ends inside its width. A mark's edge is
# where the form is seen to end, so an area's stroke is this much wider than the mark (measured: sdf.PROFILES)
WIDEN = {"round": 1.15, "soft": 1.3, "flat": 1.08, "sharp": 1.5}
FACING = {"front": [0.0, -1.0, 0.0], "back": [0.0, 1.0, 0.0], "side": [1.0, 0.0, 0.0], "side_r": [-1.0, 0.0, 0.0]}


def _world(rec: dict, xs, ys) -> np.ndarray:
    """View pixels -> (sideways, up) metres on the creature's own axes."""
    sign = -1.0 if rec["kind"] in ("back", "side_r") else 1.0
    return np.stack([sign * (np.asarray(xs, float) - rec["centre_px"]) * rec["m_per_px"],
                     (rec["ground_px"] - np.asarray(ys, float)) * rec["m_per_px"]], 1)


def _at(kind: str, p) -> dict:
    u, z = float(p[0]), float(p[1])
    return {"at": [round(u, 4), 0.0, round(z, 4)] if kind in ("front", "back") else [0.0, round(u, 4), round(z, 4)]}


def _strip(pts: np.ndarray, px: float):
    """A mark's area as a path with a half breadth at each point: its middle line, the ends set in by their own
    breadth (a stroke's end is round); a mark about as long as it is wide is one dab."""
    area = len(pts) * px * px
    try:
        line = masslines.middle(pts, px)
    except ValueError:
        line = None
    r_eq = float(np.sqrt(area / np.pi))
    if line is None or line["length"] < 2.6 * float(np.median(line["half"])) + 2 * px:
        return np.array([pts.mean(0)]), np.array([r_eq])
    L, half = line["length"], np.maximum(line["half"], px)
    # a stroke eases out over its last third of a breadth: its end points sit half a breadth in from the mark's
    s0 = min(0.5 * float(np.interp(min(half[1], 0.3 * L), line["s"], half)), 0.3 * L)
    s1 = L - min(0.5 * float(np.interp(L - min(half[-2], 0.3 * L), line["s"], half)), 0.3 * L)
    n = int(np.clip(round((s1 - s0) / (1.5 * float(np.median(half)))) + 1, 2, 9))
    at = np.linspace(s0, s1, n)
    path = np.stack([np.interp(at, line["s"], line["c"][:, i]) for i in (0, 1)], 1)
    return path, np.interp(at, line["s"], half)


def _ring(mask: np.ndarray, rec: dict, width: float | None):
    """A loop round a mark, as view pixels -> world, and the rim's half breadth."""
    from scipy import ndimage
    from skimage import measure
    k = rec["m_per_px"]
    full = ndimage.binary_fill_holes(mask)
    hole = full & ~mask
    if hole.sum() > 0.05 * full.sum():  # the ring itself was marked: run along its middle
        d_in, d_out = ndimage.distance_transform_edt(~hole), ndimage.distance_transform_edt(full)
        field = np.where(full, d_in - d_out, 1e3)   # 0 where a place is as far from the hole as from the outside
        half = float(np.median(d_in[mask] + d_out[mask])) / 2 * k
        loops = measure.find_contours(field, 0.0)
    else:
        ys, xs = np.where(mask)
        try:
            line = masslines.middle(_world(rec, xs + 0.5, ys + 0.5), k)
        except ValueError:
            line = None
        if line is not None and line["length"] >= 5.0 * 2 * float(np.median(line["half"])):
            # a band that does not close (a C, or a ring the figure's edge clipped): an open rim along its middle
            n = int(np.clip(round(line["length"] / (3.0 * float(np.median(line["half"])))), 4, 14))
            at = np.linspace(0.0, line["length"], n)
            path = np.stack([np.interp(at, line["s"], line["c"][:, i]) for i in (0, 1)], 1)
            return path, (float(width) if width else float(np.median(line["half"])))
        # a filled mark: just inside its edge
        r_eq = float(np.sqrt(full.sum() / np.pi)) * k
        half = float(width) if width else max(0.15 * r_eq, 1.5 * k)
        loops = measure.find_contours(ndimage.distance_transform_edt(full), max(half / k, 1.0))
    if not loops:
        raise ValueError("no ring could be read from its mark: mark the ring itself (an ellipse minus a smaller one, "
                         "or a line round it), clear of the figure's edge")
    loop = max(loops, key=len)                         # (row, col)
    n = int(np.clip(len(loop) // 6, 8, 16))
    pick = loop[np.linspace(0, len(loop) - 1, n, endpoint=False).astype(int)]
    path = _world(rec, pick[:, 1] + 0.5, pick[:, 0] + 0.5)
    return np.vstack([path, path[:1]]), (float(width) if width else half)


def _lines(mark: dict) -> list:
    ln = mark.get("line")
    if not ln:
        return []
    return [ln] if isinstance(ln[0][0], (int, float)) else list(ln)


def build(name: str, how: dict) -> dict:
    """Lay the forms named in `how` {feature: {"as": kind, ...}} on the model. Returns {"spec", "version", "made":
    {feature: [strokes]}, "notes": [...]}."""
    fm = featuremap.load(name)
    if not (store._dir(name) / "spec.json").exists():
        raise ValueError(f"{name} has no model yet: build its masses first (build_masses)")
    spec = store.load(name)
    spec.setdefault("strokes", {})
    sym = bool(spec.get("symmetry", True))
    notes, made, surfs = [], {}, {}
    for feature, h in how.items():
        if feature not in fm["features"]:
            raise ValueError(f"no feature {feature!r} in the map (have {sorted(fm['features'])})")
        c = fm["features"][feature]
        if c["kind"] != "form":
            raise ValueError(f"{feature} is a {c['kind']}: build_forms lays forms (a mass is built by build_masses; "
                             f"paint is colour)")
        kind = (h or {}).get("as")
        if kind not in KINDS:
            raise ValueError(f"{feature}: as is one of {KINDS} (raise: it stands out of the mass; sink: it is pressed "
                             f"in; rim: a raised ring round its mark)")
        tw = featuremap.twin(feature)
        if sym and feature.endswith(".R") and tw in how:
            continue  # its .L twin is laid and mirrored
        host, walked = c.get("on"), set()
        while host in fm["features"] and fm["features"][host]["kind"] != "mass" and host not in walked:
            walked.add(host)  # a form on a form (a nose on a muzzle) lies on that form's mass
            host = fm["features"][host].get("on")
        on = fm["features"].get(host or "")
        if not on or on["kind"] != "mass" or not on.get("elements"):
            raise ValueError(f"{feature}: the mass it is on ({host or c.get('on')!r}) is not built yet")
        flat = {v: g for v, g in c["marks"].items() if fm["views"][v]["kind"] in refread.ORTHO}
        if not flat:
            raise ValueError(f"{feature}: not marked in a flat view (front, back, side): a form is laid from one")
        want = h.get("view") or max(flat, key=lambda v: flat[v].get("area_px", 0))
        views = sorted(flat) if want == "all" else [want] if isinstance(want, str) else list(want)
        for v in views:
            if v not in flat:
                raise ValueError(f"{feature}: view {v!r} is not a flat view it is marked in (has {sorted(flat)}; "
                                 f"\"all\" lays it from each of them)")
        flip = sym and feature.endswith(".R")  # lay it as the .L it mirrors from
        el = [n for n in on["elements"] if n in spec["blobs"] or n in spec["bones"]]
        part = next((spec[kk][n].get("part") for kk in ("blobs", "bones") for n in el if n in spec[kk] and spec[kk][n].get("part")), None)
        side = feature[-2:] if feature[-2:] in (".L", ".R") else ""
        base = (tw if flip else feature)[:len(feature) - len(side)] if side else feature
        sfx = ".L" if flip else side
        op = "crease" if kind == "sink" else "clay"
        strokes = {}
        for view in views:
            rec = fm["views"][view]
            k, vk = rec["m_per_px"], rec["kind"]
            mask = featuremap.mask(name, feature, view)
            vtag = "" if len(views) == 1 else "_" + view
            facing = list(FACING[vk])
            if flip and vk in ("side", "side_r"):
                facing[0] = -facing[0]
            lines = _lines(flat[view].get("mark") or {}) if flat[view].get("line") else []

            def put(tag, path, widths, depth, profile):
                path = np.asarray(path, float)
                if flip:
                    path = path * np.array([-1.0 if vk in ("front", "back") else 1.0, 1.0])
                # a mark can overrun the mass it is on (the picture's is fuller there than the model's): a point whose
                # ray misses the mass is left out, and said
                key = (part or "body", host)
                if key not in surfs:
                    bare = {**spec, "strokes": {}}
                    names = set(on["elements"]) | {featuremap.twin(n) or n for n in on["elements"]}
                    own = [q for q in compile_prims(bare) if q.name in names and q.part == key[0] and q.op == "add"]
                    surfs[key] = strokes_mod.Surface(bare, key[0], prims=own or None)
                hit = []
                for q in path:
                    try:
                        surfs[key].entry(np.array(_at(vk, q)["at"], float), np.array(facing, float), feature)
                        hit.append(True)
                    except SpecError:
                        hit.append(False)
                if not any(hit):
                    raise ValueError(f"{feature}: seen from {view!r} its mark lies off the mass it is on ({c.get('on')!r}): "
                                     f"build or fix that mass first, or lay it from another view (\"view\")")
                if not all(hit):
                    notes.append(f"{feature}: {hit.count(False)} of {len(hit)} places along its mark miss the mass it is on "
                                 f"from {view!r} (the mass is smaller than the picture there): left out")
                    if np.ndim(widths):
                        widths = np.asarray(widths)[hit]
                    path = path[hit]
                pts = [{**_at(vk, p), **({"dir": facing} if i == 0 else {})} for i, p in enumerate(path)]
                st = {"op": op, "path": pts, "width": [round(float(w), 4) for w in np.atleast_1d(widths)] if np.ndim(widths)
                      else round(float(widths), 4), "depth": round(float(depth), 4), "profile": profile}
                if isinstance(st["width"], list) and len(st["width"]) == 1:
                    st["width"] = st["width"][0]
                if part:
                    st["part"] = part
                sname = f"{base}{vtag}{tag}{sfx}"
                try:  # a path that crosses a gap in the mass (a socket, an edge) can't be seated: left out, said
                    compile_prims({**spec, "strokes": {sname: st}})
                except SpecError as e:
                    notes.append(f"{feature}: could not be laid from {view!r} and was LEFT OUT ({e}): its mark crosses a "
                                 f"gap or runs off the mass there. Redraw it clear of the gap, or lay it from another view")
                    return
                strokes[sname] = st

            if kind == "rim":
                try:
                    path, half = _ring(mask, rec, h.get("width"))
                except ValueError as e:
                    raise ValueError(f"{feature}: {e}") from None
                if not np.allclose(path[0], path[-1]):
                    notes.append(f"{feature}: its ring does not close in {view!r}: laid as an open rim along its middle")
                put("", path, half, h.get("depth", 0.8 * half), h.get("profile", "round"))
            elif lines:
                half = float(h.get("width", max(1.5 * k, 0.003)))
                for i, ln in enumerate(lines):
                    path = _world(rec, [p[0] for p in ln], [p[1] for p in ln])
                    put("" if len(lines) == 1 else f"_{i + 1}", path, half, h.get("depth", 0.5 * half),
                        h.get("profile", "sharp" if kind == "sink" else "soft"))
            else:  # each separate piece of the mark is a strip (or a dab) of its own: a row of rings, a pair of bumps
                from scipy import ndimage
                lab, n_lab = ndimage.label(mask, structure=np.ones((3, 3)))
                sizes = ndimage.sum(mask, lab, range(1, n_lab + 1))
                keep = [i + 1 for i, a in enumerate(sizes) if a >= max(6, 0.08 * sizes.max())]
                for j, i in enumerate(keep):
                    ys, xs = np.where(lab == i)
                    path, widths = _strip(_world(rec, xs + 0.5, ys + 0.5), k)
                    prof = h.get("profile", "soft" if kind == "sink" else "round")
                    depth = h.get("depth", 0.4 * float(np.median(widths)))
                    widths = np.full(len(path), float(h["width"])) if "width" in h else widths * WIDEN.get(prof, 1.0)
                    put("" if len(keep) == 1 else f"_{j + 1}", path, widths, depth, prof)
                if len(keep) > 1:
                    notes.append(f"{feature}: its mark is {len(keep)} separate pieces: one stroke each")
        if not strokes:
            notes.append(f"{feature}: NOTHING of it was laid; what was laid for it before stays")
            continue
        if "depth" not in h:
            d = next(iter(strokes.values()))["depth"]
            notes.append(f"{feature}: no depth given: {d * 1000:.1f} mm {'in' if kind == 'sink' else 'out'}, from its "
                         f"breadth (one view can't show it: look from the side and set \"depth\")")
        for old in c.get("built") or []:  # what was laid for it before goes
            spec["strokes"].pop(old, None)
        spec["strokes"].update(strokes)
        mirror = lambda n: featuremap.twin(n) or n  # noqa: E731
        own = [mirror(n) for n in strokes] if flip else list(strokes)
        c["elements"], c["built"], c["as"], c["laid"] = own, list(strokes), kind, views
        made[feature] = own
        if sym and tw and tw in fm["features"] and fm["features"][tw]["kind"] == "form":
            fm["features"][tw]["elements"] = [mirror(n) for n in own]
            fm["features"][tw]["as"], fm["features"][tw]["laid"] = kind, views
            made[tw] = fm["features"][tw]["elements"]
    version = store.save(name, spec, "build_forms: " + ", ".join(sorted(made)))
    featuremap.save(name, fm)
    return {"spec": spec, "version": version, "made": made, "notes": notes}
