"""Masses from their outlines: a mass marked on a reference's flat views (featuremap.py) becomes a shape in the
model, its numbers read off the marks. The sculptor says WHAT each mass is; no coordinate is typed.

Why (Braynard Racing, 2026-11-12): a block-in typed as numbers cost six saves for a head and ten for a horn, and
still missed the outline by centimetres, because every number was read off a picture by eye and typed. The marks
already hold those numbers.

A mass is built `as`:
  "ball"   one rounded lump: its middle and three half sizes from the marks' boxes (an eye, a nose, a hoof, a head
           that is nearly a ball). `round`: 2 = an ellipsoid, higher = squarer (a soft block). `socket`: true (or
           metres): it is set INTO the mass it is `on`, which is hollowed round it so that it shows (an eyeball).
           A mark in several separate pieces (a row of hanging locks) is one lump per piece.
  "drum"   a made, straight-sided thing: a cylinder along its long axis (a can, a wheel, a post), its radii and
           length from the marks' boxes. `along` x / y / z if the axis it picks is wrong; `edge`: metres its rims
           are rounded by.
  "trunk"  one upright mass through cross-sections: at each height its width from the front (or back) mark and its
           depth and lean from the side mark (a torso, an upright head, a neck). `round` as above, per section.
           `sections`: how many (default 7).
  "tube"   a limb, horn or tail along its mark's own MIDDLE LINE, whichever way that runs and however it bends
           (masslines.py): a chain of bones through `joints` stations (default 4), each station's half sizes read
           ACROSS the line in both views. An end touching another marked mass runs on under it; a free end is
           capped where the mark stops. The bones are the limb's bones later, for the rig.
  "flap"   a thin thing seen broad from one side (an ear, a fin, a leaf, a flat tail): one thick sheet along the
           long axis of its broadest mark, its width read across that axis, its thickness from its other view
           (or `thick`, metres). A sheet running sideways leans the way its other view shows it. `cup`: metres its
           edges lift (a hollow); `joints`: stations along it (4).
Where the flat views disagree about a mass's height, the feature's `authority` view is believed and the others
are fitted to it. What the two views can't give is said, never silently guessed: a mass marked in one flat view takes its depth from
its width (or `depth`, metres), and its place along the missing axis from `y` / `x` (or the mass it is `on`).

`.L` / `.R`: with symmetry (the default) the `.L` mass is built and mirrored; a `.R` with no `.L` twin is built
from its own marks and mirrored the other way. Each built feature's `elements` are written into the map, so
feature_report measures them at once. Building a feature again replaces what was built for it before.
"""
from __future__ import annotations

import numpy as np

from . import featuremap, masslines, refread, store

KINDS = ("ball", "drum", "flap", "trunk", "tube")


def _flat(fm: dict, name: str, feature: str) -> dict:
    """The feature's marks as world extents: {"xz": (x, z) point cloud from front / back marks, "yz": from side
    marks}, metres, mirrored to the creature's own axes; and "touch_xz" / "touch_yz": the points of those marks
    that lie against ANOTHER mass's mark (where it runs on under a neighbour)."""
    from scipy import ndimage
    out, span, touch, px, lines = {}, {}, {}, 0.0, {}
    c = fm["features"][feature]
    masses = [n for n, o in fm["features"].items() if o["kind"] == "mass" and n != feature]
    for v, g in c["marks"].items():
        rec = fm["views"][v]
        if rec["kind"] not in refread.ORTHO:
            continue
        k, c0, ground = rec["m_per_px"], rec["centre_px"], rec["ground_px"]
        px = max(px, float(k))
        own = featuremap.mask(name, feature, v)
        sign = -1.0 if rec["kind"] in ("back", "side_r") else 1.0
        world = lambda m: np.stack([sign * (np.where(m)[1] + 0.5 - c0) * k, (ground - np.where(m)[0] - 0.5) * k], 1)  # noqa: E731
        pts = world(own)
        span[v] = (float(pts[:, 1].min()), float(pts[:, 1].max()))
        key = "xz" if rec["kind"] in ("front", "back") else "yz"
        out[v] = (key, pts)
        others = np.zeros_like(own)
        for n in masses:
            if v in fm["features"][n]["marks"]:
                others |= featuremap.mask(name, n, v)
        touch[v] = (key, world(own & ndimage.binary_dilation(others & ~own, iterations=3)))
        lines.setdefault(key, []).append(bool(g.get("line")))
    auth = c.get("authority")
    if auth in span:  # the other views' heights are fitted to the view to believe
        a0, a1 = span[auth]
        for v, (key, pts) in out.items():
            if v != auth and span[v][1] > span[v][0]:
                b0, b1 = span[v]
                for q in (pts, touch[v][1]):
                    q[:, 1] = a0 + (q[:, 1] - b0) * (a1 - a0) / (b1 - b0)
    merged = {}
    for src, pre in ((out, ""), (touch, "touch_")):
        for key, pts in src.values():
            key = pre + key
            merged[key] = pts if key not in merged else np.concatenate([merged[key], pts])
    if merged:
        merged["px"] = px
        for key, each in lines.items():
            if all(each):
                merged["line_" + key] = True  # marked by a line only there: where it runs, with no width of its own
    return merged


def _span(pts: np.ndarray, along: int, lo: float, hi: float, half: float):
    """(min, max) of the other coordinate among the points within `half` of each of the slice positions."""
    a, b = pts[:, along], pts[:, 1 - along]
    k = (a >= lo - half) & (a <= hi + half)
    return (float(b[k].min()), float(b[k].max())) if k.any() else None


def _stations(pts: np.ndarray, along: int, n: int, inset: float = 0.08):
    """n slices across a point cloud along one of its axes: [(position, low, high)], ends set in a little (the last
    rows of a rounded end are a point)."""
    lo, hi = float(pts[:, along].min()), float(pts[:, along].max())
    at = np.linspace(lo + inset * (hi - lo), hi - inset * (hi - lo), n)
    half = max((hi - lo) / (2.5 * n), 0.002)
    out = []
    for t in at:
        s = _span(pts, along, t, t, half)
        if s:
            out.append((float(t), s[0], s[1]))
    return out, lo, hi


def _profile(pts: np.ndarray, zs, tall: float) -> list:
    """(low, high) of a mark across each height in zs, read every 2 mm and smoothed over a tenth of its height (a
    hand-drawn outline wobbles; a loft through every wobble comes out ribbed)."""
    fine = np.arange(float(pts[:, 1].min()), float(pts[:, 1].max()) + 1e-9, 0.002)
    lo, hi = np.full(len(fine), np.nan), np.full(len(fine), np.nan)
    order = np.argsort(pts[:, 1])
    zsort, vsort = pts[order, 1], pts[order, 0]
    a = np.searchsorted(zsort, fine - 0.002)
    b = np.searchsorted(zsort, fine + 0.002)
    for i, (i0, i1) in enumerate(zip(a, b)):
        if i1 > i0:
            lo[i], hi[i] = vsort[i0:i1].min(), vsort[i0:i1].max()
    ok = ~np.isnan(lo)
    if ok.sum() < 3:
        return [(None, None)] * len(zs)
    k = max(3, int(round(0.1 * tall / 0.002)) | 1)
    pad = k // 2

    def smooth(v):
        v = np.interp(fine, fine[ok], v[ok])
        vp = np.pad(v, pad, mode="edge")
        med = np.array([np.median(vp[i:i + k]) for i in range(len(v))])
        mp = np.pad(med, pad, mode="edge")
        return np.convolve(mp, np.ones(k) / k, mode="valid")
    slo, shi = smooth(lo), smooth(hi)
    return [(float(np.interp(z, fine, slo)), float(np.interp(z, fine, shi))) for z in zs]


def _need(f: dict, feature: str, key: str):
    if key not in f:
        have = "front or back" if key == "xz" else "side"
        raise ValueError(f"{feature}: no {have} mark, so it can't be built from its outlines yet: mark it there")
    return f[key]


def _split(f: dict) -> list[dict]:
    """A mark in several separate pieces (a row of hanging locks, a pair of knobs) as one set of marks per piece:
    the pieces of the view that shows most of them, each with what the other view shows at its heights."""
    from scipy import ndimage
    px = float(f.get("px") or 0.002)
    best = None
    for key in ("xz", "yz"):
        pts = f.get(key)
        if pts is None or len(pts) < 12:
            continue
        lo = pts.min(0) - 2 * px
        ij = np.floor((pts - lo) / px).astype(int)
        m = np.zeros(tuple(ij.max(0) + 3), bool)
        m[ij[:, 0], ij[:, 1]] = True
        lab, n = ndimage.label(ndimage.binary_closing(m, iterations=1) | m, structure=np.ones((3, 3)))
        size = ndimage.sum(m, lab, range(1, n + 1))
        keep = [i + 1 for i, a in enumerate(size) if a >= max(6, 0.08 * size.max())]
        if len(keep) > 1 and (best is None or len(keep) > len(best[1])):
            best = (key, keep, lab[ij[:, 0], ij[:, 1]])
    if best is None:
        return [f]
    key, keep, of = best
    okey = "yz" if key == "xz" else "xz"
    out = []
    for i in sorted(keep, key=lambda i: float(f[key][of == i][:, 0].mean())):
        mine = f[key][of == i]
        g = {key: mine, "px": px}
        other = f.get(okey)
        if other is not None:
            near = other[(other[:, 1] >= mine[:, 1].min() - px) & (other[:, 1] <= mine[:, 1].max() + px)]
            g[okey] = near if len(near) >= 3 else other
        out.append(g)
    return out


def _ball(feature: str, f: dict, how: dict, notes: list) -> dict:
    pieces = _split(f)
    if len(pieces) > 1:  # one lump per piece: <name>_1 ..., left to right (front to back in a side view)
        side = feature[-2:] if feature[-2:] in (".L", ".R") else ""
        base = feature[:len(feature) - len(side)]
        blobs = {}
        for i, g in enumerate(pieces, 1):
            one = _ball(f"{base}_{i}{side}", g, {k: v for k, v in how.items() if k != "socket"}, notes)
            blobs.update(one["blobs"])
        notes.append(f"{feature}: its mark is {len(pieces)} separate pieces: one lump each ({base}_1{side} ..)")
        return {"blobs": blobs}
    xz = f.get("xz")
    yz = f.get("yz")
    if xz is None and yz is None:
        raise ValueError(f"{feature}: no mark in a flat view")
    zs = np.concatenate([p[:, 1] for p in (xz, yz) if p is not None])
    z0, z1 = float(zs.min()), float(zs.max())
    if xz is not None:
        x0, x1 = float(xz[:, 0].min()), float(xz[:, 0].max())
    else:
        x0 = x1 = None
    if yz is not None:
        y0, y1 = float(yz[:, 0].min()), float(yz[:, 0].max())
    else:
        y0 = y1 = None
    rz = (z1 - z0) / 2
    if x0 is None:
        rx = float(how.get("depth", (y1 - y0))) / 2 if "depth" in how else (y1 - y0) / 2
        cx = float(how.get("x", 0.0))
        notes.append(f"{feature}: no front mark: its width is taken as its depth ({2 * rx * 1000:.0f} mm) at x {cx:+.3f}")
    else:
        rx, cx = (x1 - x0) / 2, (x0 + x1) / 2
    if y0 is None:
        ry = float(how["depth"]) / 2 if "depth" in how else min(rx, rz)
        if "y" not in how:
            raise ValueError(f"{feature}: no side mark, so where it sits front to back is unknown: mark it in the side "
                             f"view, or give y (metres, front is negative)")
        cy = float(how["y"])
        notes.append(f"{feature}: no side mark: depth {2 * ry * 1000:.0f} mm at y {cy:+.3f} is your word, not the picture's")
    else:
        ry, cy = (y1 - y0) / 2, (y0 + y1) / 2
    out = {feature: {"shape": "super", "at": [round(cx, 4), round(cy, 4), round((z0 + z1) / 2, 4)],
                     "size": [round(max(rx, 0.002), 4), round(max(ry, 0.002), 4), round(max(rz, 0.002), 4)],
                     "squareness": float(how.get("round", 2.0))}}
    if how.get("socket") and how.get("_targets"):  # the mass it sits on is cut back round it (a little wider)
        more = 0.15 * min(rx, ry, rz) if how["socket"] is True else float(how["socket"])
        side = feature[-2:] if feature[-2:] in (".L", ".R") else ""
        out[f"{feature[:len(feature) - len(side)]}_socket{side}"] = {
            "shape": "ellipsoid", "at": out[feature]["at"], "size": [round(v + more, 4) for v in out[feature]["size"]],
            "op": "subtract", "targets": list(how["_targets"]), "blend": round(min(0.006, more), 4)}
    return {"blobs": out}


def _drum(feature: str, f: dict, how: dict, notes: list) -> dict:
    b = _ball(feature, f, how, notes)["blobs"][feature]
    hx, hy, hz = b["size"]
    axis = how.get("along") or "xyz"[int(np.argmax([hx, hy, hz]))]
    if axis not in ("x", "y", "z"):
        raise ValueError(f"{feature}: along is x, y or z")
    # a cylinder runs along its local z: turn that onto the axis; its two radii are what is left
    rot, size = {"x": ([0, 90, 0], [hz, hy, hx]), "y": ([90, 0, 0], [hx, hz, hy]), "z": ([0, 0, 0], [hx, hy, hz])}[axis]
    return {"blobs": {feature: {"shape": "cylinder", "at": b["at"], "rot": rot, "size": [round(v, 4) for v in size],
                                "round": float(how.get("edge", 0.12 * min(size[:2])))}}}


def _flap(feature: str, f: dict, how: dict, notes: list) -> dict:
    xz, yz = f.get("xz"), f.get("yz")
    if xz is None and yz is None:
        raise ValueError(f"{feature}: no mark in a flat view")
    area = lambda p: 0.0 if p is None else float(np.ptp(p[:, 0]) * np.ptp(p[:, 1]))  # noqa: E731
    broad, key = (xz, "xz") if area(xz) >= area(yz) else (yz, "yz")
    other = yz if key == "xz" else xz
    side_axis = 0 if key == "xz" else 1          # world index of the broad view's sideways axis (x or y)
    thin_axis = 1 if key == "xz" else 0          # the axis the broad view looks along
    run = 0 if np.ptp(broad[:, 0]) >= np.ptp(broad[:, 1]) else 1  # along the broad mark: sideways (0) or up (1)
    if how.get("along"):
        want = "xyz".index(how["along"])
        if want not in (side_axis, 2):
            raise ValueError(f"{feature}: its broadest mark lies in {'xz'[side_axis] if key == 'xz' else 'y'}-z: along is one of those")
        run = 0 if want == side_axis else 1
    n = int(how.get("joints", 4))
    st, _, _ = _stations(broad, run, n, 0.1)
    if len(st) < 2:
        raise ValueError(f"{feature}: its mark is too small to find a run of stations")
    if other is not None:
        thin_mid = float(other[:, 0].mean())
        thick = float(how["thick"]) if "thick" in how else float(np.ptp(other[:, 0]))
    else:
        if "thick" not in how or ("y" if thin_axis == 1 else "x") not in how:
            raise ValueError(f"{feature}: marked in one view only: give thick (metres) and "
                             f"{'y' if thin_axis == 1 else 'x'} (where it sits along the missing axis)")
        thin_mid, thick = float(how["y" if thin_axis == 1 else "x"]), float(how["thick"])
        notes.append(f"{feature}: one view only: {thick * 1000:.0f} mm thick at {thin_mid:+.3f} is your word, not the picture's")
    spine, stations = [], []
    for i, (t, a, b) in enumerate(st):
        p = [0.0, 0.0, 0.0]
        p[thin_axis] = thin_mid
        if run == 0:   # the sheet runs sideways: its width is up and down
            p[side_axis], p[2] = t, (a + b) / 2
        else:          # it runs up: its width is sideways
            p[2], p[side_axis] = t, (a + b) / 2
        hw = max((b - a) / 2, 0.004)
        spine.append([round(c, 4) for c in p])
        stations.append({"t": round(i / (len(st) - 1), 3), "half_width": round(hw, 4),
                         "half_thickness": round(min(max(thick / 2, 0.002), 0.9 * hw), 4),
                         "cup": float(how.get("cup", 0.0)), "puff": float(how.get("puff", 0.4))})
    wide = [0.0, 0.0, 0.0]
    wide[2 if run == 0 else side_axis] = 1.0
    if other is not None and run == 0 and len(other) > 12 and "thick" not in how:
        # a sheet running sideways shows its TILT in the other view: there it is a slanted streak, long across the
        # sheet's width and as thin as the sheet. Lean the width that way and take the thickness across the streak
        q = other - other.mean(0)
        vals, vecs = np.linalg.eigh(np.cov(q.T))
        major, minor = vecs[:, 1] * (1 if vecs[1, 1] >= 0 else -1), vecs[:, 0]
        if vals[1] > 2.0 * vals[0] and major[1] > 0.35:
            wide = [0.0, 0.0, 0.0]
            wide[thin_axis], wide[2] = float(major[0]), float(major[1])
            thin = float(np.ptp(q @ minor))
            for st_ in stations:
                st_["half_width"] = round(st_["half_width"] / max(float(major[1]), 0.5), 4)
                st_["half_thickness"] = round(min(max(thin / 2, 0.002), 0.9 * st_["half_width"]), 4)
            notes.append(f"{feature}: tilted {np.degrees(np.arctan2(abs(major[0]), major[1])):.0f} degrees out of its "
                         f"broad view, as its other view shows it")
    return {"blobs": {feature: {"shape": "sheet", "spine": spine, "width_axis": wide, "stations": stations}}}


def _solid(pts: np.ndarray, px: float, feature: str, notes: list) -> np.ndarray:
    """The mark without the rows it only fringes: a slanted cut leaves slivers at a mark's two sides below (or
    above) its body, and a section read across them spans the whole width with nothing between (a thin flange)."""
    if not px or len(pts) < 20:
        return pts
    row = np.floor((pts[:, 1] - pts[:, 1].min()) / px + 0.5).astype(int)
    n = np.bincount(row)
    lo = np.full(len(n), np.inf)
    hi = np.full(len(n), -np.inf)
    np.minimum.at(lo, row, pts[:, 0])
    np.maximum.at(hi, row, pts[:, 0])
    full = n * px >= 0.5 * (hi - lo + px)
    keep = np.zeros(len(n), bool)
    good = np.flatnonzero(full)
    if len(good) < 3:
        return pts
    keep[good[0]:good[-1] + 1] = True  # only the ends are trimmed: a hollow row inside it stays
    if keep.all():
        return pts
    notes.append(f"{feature}: {int((~keep).sum() * px * 1000)} mm of rows at its end hold only slivers of its mark (a "
                 f"slanted cut's corners): left out of its sections")
    return pts[keep[row]]


def _trunk(feature: str, f: dict, how: dict, notes: list) -> dict:
    xz = _solid(_need(f, feature, "xz"), f.get("px"), feature, notes)
    yz = f.get("yz")
    n = int(how.get("sections", 7))
    z0, z1 = float(xz[:, 1].min()), float(xz[:, 1].max())
    tall = z1 - z0
    caps = []
    for end in (z0 + 0.15 * tall, z1 - 0.15 * tall):  # each end's dome: 0.4 of its half width there, within reason
        w = _span(xz, 1, end, end, max(tall / 30, 0.002))
        caps.append(float(np.clip(0.4 * (w[1] - w[0]) / 2 if w else 0.1 * tall, 0.05 * tall, 0.3 * tall)))
    half = max(tall / (2.5 * n), 0.002)
    zs = np.linspace(z0 + caps[0], z1 - caps[1], n)
    prof = _profile(xz, zs, tall)
    st = [(float(z), lo_, hi_) for z, (lo_, hi_) in zip(zs, prof) if lo_ is not None]
    if len(st) < 2:
        raise ValueError(f"{feature}: its mark is too small to read sections from")
    cx = float(np.mean([(a + b) / 2 for _, a, b in st]))
    side_prof = dict(zip([round(float(z), 6) for z in zs], _profile(yz, zs, tall))) if yz is not None else {}
    if yz is None:
        notes.append(f"{feature}: no side mark: its depth is taken as {how.get('depth_ratio', 0.85):.2f} of its width, upright")
    sections = []
    for z, a, b in st:
        hw = (b - a) / 2
        side = side_prof.get(round(z, 6))
        side = side if side and side[0] is not None else None
        if side:
            hd, oy = (side[1] - side[0]) / 2, (side[0] + side[1]) / 2
        else:
            hd, oy = hw * float(how.get("depth_ratio", 0.85)), float(how.get("y", 0.0))
        sections.append({"z": round(z, 4), "half_width": round(max(hw, 0.003), 4), "half_depth": round(max(hd, 0.003), 4),
                         "offset_y": round(oy, 4), "squareness": float(how.get("round", 2.3))})
    return {"blobs": {feature: {"shape": "loft", "at": [round(cx, 4), 0.0, 0.0], "sections": sections,
                                "top": {"z": round(z1, 4)}, "bottom": {"z": round(z0, 4)}}}}


def build(name: str, how: dict, symmetry: bool = True) -> dict:
    """Build the masses named in `how` {feature: {"as": kind, ...}} into model `name` (made if it doesn't exist).
    Returns {"spec", "version", "made": {feature: [elements]}, "notes": [...]}."""
    fm = featuremap.load(name)
    if not fm["features"]:
        raise ValueError(f"{name} has no feature map: read_reference, then mark_features")
    have = (store._dir(name) / "spec.json").exists()
    spec = store.load(name) if have else {"symmetry": bool(symmetry), "blend": 0.02, "joints": {}, "bones": {}, "blobs": {}}
    for k in ("joints", "bones", "blobs"):
        spec.setdefault(k, {})
    notes, made = [], {}
    for feature, h in how.items():
        if feature not in fm["features"]:
            raise ValueError(f"no feature {feature!r} in the map (have {sorted(fm['features'])})")
        c = fm["features"][feature]
        if c["kind"] != "mass":
            raise ValueError(f"{feature} is a {c['kind']}: build_masses builds masses (a form is laid on a mass)")
        kind = (h or {}).get("as")
        if kind not in KINDS:
            raise ValueError(f"{feature}: as is one of {KINDS} (a ball: one rounded lump; a drum: a straight-sided "
                             f"cylinder; a flap: a thin thing seen broad from one side; a trunk: an upright mass "
                             f"through cross-sections; a tube: a limb or horn along its own axis)")
        tw = featuremap.twin(feature)
        sym = bool(spec.get("symmetry", True))
        if sym and feature.endswith(".R") and tw in how:
            continue  # its .L twin is built and mirrored
        src = _flat(fm, name, feature)
        if not any(k in src for k in ("xz", "yz")):
            raise ValueError(f"{feature}: not marked in any flat view (front, back, side)")
        flip = sym and feature.endswith(".R")
        if flip:  # build it as the .L it mirrors from
            src = {k: v * np.array([-1.0 if k.endswith("xz") else 1.0, 1.0]) if isinstance(v, np.ndarray) else v
                   for k, v in src.items()}
        target = tw if flip else feature
        h = dict(h)
        if h.get("socket"):
            on = fm["features"].get(c.get("on") or "", {})
            under = [n for n in on.get("elements") or [] if n in spec["blobs"] or n in spec["bones"]]
            if kind != "ball" or not under:
                raise ValueError(f"{feature}: socket is for a ball set into the mass it is on, and that mass "
                                 f"({c.get('on')!r}) must be built first (in an earlier call, or earlier in this one)")
            h["_targets"] = [featuremap.twin(n) or n for n in under] if flip else under
        part = {"ball": _ball, "drum": _drum, "flap": _flap, "trunk": _trunk, "tube": masslines.tube}[kind](target, src, h, notes)
        for old in c.get("built") or []:  # what was built for it before goes
            for k in ("joints", "bones", "blobs"):
                spec[k].pop(old, None)
        new_names = {n for k in ("bones", "blobs") for n in (part.get(k) or {})}
        stay = [n for n in c.get("elements") or [] if n not in (c.get("built") or []) and n not in new_names
                and any(n in spec[k] for k in ("bones", "blobs"))]
        if stay:
            notes.append(f"{feature}: {stay} made it before and was not built here, so it is still in the model beside "
                         f"the new shape: take it out (edit_model) if the new shape replaces it")
        names = []
        for k in ("joints", "bones", "blobs"):
            for n, e in (part.get(k) or {}).items():
                if k != "joints" and e.get("op") != "subtract":
                    if h.get("part"):
                        e["part"] = h["part"]
                    if "blend" in h:
                        e["blend"] = float(h["blend"])
                    names.append(n)
                spec[k][n] = e
        built = [n for k in ("joints", "bones", "blobs") for n in (part.get(k) or {})]
        mirror = lambda n: featuremap.twin(n) or n  # noqa: E731
        own = [mirror(n) for n in names] if flip else names
        c["elements"], c["built"], c["as"] = own, built, kind
        made[feature] = own
        if sym and tw and tw in fm["features"] and fm["features"][tw]["kind"] == "mass":
            fm["features"][tw]["elements"] = [mirror(n) for n in own]
            fm["features"][tw]["as"] = kind
            made[tw] = fm["features"][tw]["elements"]
    fm["frame"] = "map"  # the model is built where the pictures put it: a report must not slide the views onto it
    version = store.save(name, spec, "build_masses: " + ", ".join(sorted(made)))
    featuremap.save(name, fm)
    return {"spec": spec, "version": version, "made": made, "notes": notes}
