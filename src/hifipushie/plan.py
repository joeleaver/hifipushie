"""Plans: a 2D blockout drawn before modelling, that the model is then checked against at every stage.

spec["plan"] = {
  "views": {                      # outlines as unions of 2D shapes, in world units
    "front": {"shapes": {...}},   #   u = X, v = Z   (".L" shapes mirror to -X)
    "side":  {"shapes": {...}},   #   u = Y, v = Z   (creature faces -Y, i.e. left; ".L" shapes don't mirror)
    "top":   {"shapes": {...}}},  #   u = X, v = Y   (".L" shapes mirror)
  "landmarks": {name: {"z": height, "joint"?: joint whose Z should sit there, "tol"?: m (default 0.01)}},
  "sections":  {name: {"z": height, "near": [x, y] (which part of the slice: the one containing or nearest
                       this point, e.g. the left thigh), "width": X extent, "depth": Y extent,
                       "center"?: [x, y], "x"?: [lo, hi] only measure within this X range (leave out
                       arms touching the torso), "tol"?: fraction (default 0.08)}},
  "parts": [part names],          # optional: the parts the silhouettes count (the body, not the prop it holds);
                                  #   check/compare/fit take only_parts / hide_parts too
  "dimensions": {name: {"of": element | tag | array | kit name (or a list) | "part": part,
                        "measure": "top" | "bottom" | "height" | "width" | "depth" | "diameter" (max of width,
                                   depth) | "left" | "right" | "front" | "back",
                        "value": m, "tol"?: m (0.01)  |  "min"?: m, "max"?: m}},
                                  # real-world numbers, measured on those elements' own surfaces: props, cages,
                                  #   wirework, chains, where silhouette IoU says little
  "close": m                      # gap closing for part shapes (below; default 0.03)
}
A shape may stand for one part: {"capsule": [...], "part": "chains"}. check then compares that part's silhouette,
gaps closed (a curtain of chains, a wire cage compared with its envelope), with those shapes alone, and the untagged
shapes with the other parts.
Shapes (u, v in the view's axes):
  {"ellipse": [cu, cv, ru, rv], "rot": deg}
  {"capsule": [u0, v0, u1, v1], "r": r | [r0, r1]}      a limb: rounded, tapering from r0 to r1
  {"poly": [[u, v], ...], "smooth": true}               any outline; smooth = closed Catmull-Rom curve
  "op": "subtract" cuts a shape out (a gap between the legs, say).

Draw the plan first (proportions in head heights, landmarks, a few sections), look at it, fix it, then block
out against it: `check` scores the model's silhouettes against the plan's at their exact world positions (no
rescaling), lists landmark and section errors, and `fit(against="plan")` pulls the blockout onto it.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw
from skimage import draw as skdraw

from .spec import SpecError

VIEW_AXES = {"front": (0, 2), "side": (1, 2), "top": (0, 1)}  # world axes of (u, v)
MIRRORS = {"front": True, "side": False, "top": True}


def _shapes(plan: dict, view: str) -> list[tuple[str, dict]]:
    shapes = (plan.get("views", {}).get(view) or {}).get("shapes") or {}
    out = []
    for name, sh in shapes.items():
        out.append((name, sh))
        if MIRRORS[view] and name.endswith(".L"):
            out.append((name[:-2] + ".R", _mirror(sh)))
    return out


def _mirror(sh: dict) -> dict:
    m = dict(sh)
    if "ellipse" in sh:
        cu, cv, ru, rv = sh["ellipse"]
        m["ellipse"], m["rot"] = [-cu, cv, ru, rv], -float(sh.get("rot", 0))
    if "capsule" in sh:
        u0, v0, u1, v1 = sh["capsule"]
        m["capsule"] = [-u0, v0, -u1, v1]
    if "poly" in sh:
        m["poly"] = [[-u, v] for u, v in sh["poly"]]
    return m


def _smooth_closed(P: np.ndarray, per: int = 12) -> np.ndarray:
    n = len(P)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = P[i - 1], P[i], P[(i + 1) % n], P[(i + 2) % n]
        for a in np.linspace(0, 1, per, endpoint=False):
            out.append(0.5 * (2 * p1 + (p2 - p0) * a + (2 * p0 - 5 * p1 + 4 * p2 - p3) * a * a
                              + (3 * p1 - p0 - 3 * p2 + p3) * a ** 3))
    return np.array(out)


def _outline(sh: dict, what: str) -> np.ndarray:
    """A shape as a closed polygon (n, 2) in world (u, v)."""
    t = np.linspace(0, 2 * math.pi, 96, endpoint=False)
    if "ellipse" in sh:
        cu, cv, ru, rv = (float(x) for x in sh["ellipse"])
        a = math.radians(float(sh.get("rot", 0)))
        x, y = ru * np.cos(t), rv * np.sin(t)
        return np.stack([cu + x * math.cos(a) - y * math.sin(a), cv + x * math.sin(a) + y * math.cos(a)], 1)
    if "capsule" in sh:
        u0, v0, u1, v1 = (float(x) for x in sh["capsule"])
        r = sh.get("r", 0.02)
        r0, r1 = (float(r), float(r)) if np.ndim(r) == 0 else (float(r[0]), float(r[1]))
        # a tapered capsule is the convex hull of its two end circles
        from scipy.spatial import ConvexHull
        P = np.concatenate([np.stack([u0 + r0 * np.cos(t), v0 + r0 * np.sin(t)], 1),
                            np.stack([u1 + r1 * np.cos(t), v1 + r1 * np.sin(t)], 1)])
        return P[ConvexHull(P).vertices]
    if "poly" in sh:
        P = np.asarray(sh["poly"], float)
        if P.ndim != 2 or len(P) < 3:
            raise SpecError(f"plan shape {what}: poly needs 3+ [u, v] points")
        return _smooth_closed(P) if sh.get("smooth") else P
    raise SpecError(f"plan shape {what}: needs ellipse, capsule or poly")


def bounds(plan: dict, view: str) -> tuple[np.ndarray, np.ndarray] | None:
    pts = [_outline(sh, n) for n, sh in _shapes(plan, view) if sh.get("op", "add") == "add"]
    if not pts:
        return None
    P = np.concatenate(pts)
    return P.min(0), P.max(0)


def mask(plan: dict, view: str, px: float, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Plan silhouette rasterised with pixel size px over world [lo, hi] (row 0 = top = hi v)."""
    W, H = int(math.ceil((hi[0] - lo[0]) / px)) + 1, int(math.ceil((hi[1] - lo[1]) / px)) + 1
    m = np.zeros((H, W), bool)
    for name, sh in _shapes(plan, view):
        P = _outline(sh, name)
        rr, cc = skdraw.polygon((hi[1] - P[:, 1]) / px, (P[:, 0] - lo[0]) / px, m.shape)
        m[rr, cc] = sh.get("op", "add") == "add"
    return m


def reference(plan: dict, view: str, res: int = 700):
    """(mask, world placement (u0, v1, px)) for use as a reference silhouette: pixel (row, col) edge at world
    u = u0 + col*px, v = v1 - row*px."""
    b = bounds(plan, view)
    if b is None:
        raise ValueError(f"the plan has no {view} view")
    lo, hi = b
    pad = 0.08 * float((hi - lo).max())
    lo, hi = lo - pad, hi + pad
    px = float((hi - lo).max()) / res
    return mask(plan, view, px, lo, hi), (float(lo[0]), float(hi[1]), px)


def validate(plan: dict):
    for name, d in (plan.get("dimensions") or {}).items():
        if not isinstance(d, dict) or not ({"of", "element", "tag", "part"} & set(d)):
            raise SpecError(f'plan dimension {name!r}: needs "of" (element, tag, array or kit names) or "part"')
        if d.get("measure", "height") not in MEASURES:
            raise SpecError(f"plan dimension {name!r}: measure is one of {', '.join(MEASURES)}")
        if not ({"value", "min", "max"} & set(d)):
            raise SpecError(f'plan dimension {name!r}: give "value" (+ "tol") or "min" / "max"')
    ps = plan.get("parts")
    if ps is not None and not (isinstance(ps, list) and ps and all(isinstance(x, str) for x in ps)):
        raise SpecError('plan: "parts" is a list of part names, e.g. ["body"]')
    for view in plan.get("views", {}):
        if view not in VIEW_AXES:
            raise SpecError(f"plan: unknown view {view!r} (front, side, top)")
        for name, sh in _shapes(plan, view):
            _outline(sh, name)
    for name, lm in (plan.get("landmarks") or {}).items():
        if "z" not in lm:
            raise SpecError(f"plan landmark {name!r}: needs z")
    for name, sec in (plan.get("sections") or {}).items():
        if not {"z", "width", "depth"} <= set(sec):
            raise SpecError(f"plan section {name!r}: needs z, width and depth (and near)")


# ---------------------------------------------------------------- drawing

def draw_view(img: Image.Image, frame: dict, plan: dict, model_outline=None) -> Image.Image:
    """Draw the plan for one view (in the same camera framing as a look panel): filled shapes, landmark
    lines, planned section widths. With the model's silhouette (a mask with its world extents) it becomes a
    diff: grey both, blue plan only (model missing), red model only (extra)."""
    from .render import FONT
    view = frame["name"]
    ua, va = VIEW_AXES[view]
    W = img.width
    s, c = frame["scale"], frame["center"]

    def to_px(u, v):
        return (np.asarray(u) - c[ua]) / s * W + W / 2, W / 2 - (np.asarray(v) - c[va]) / s * W

    fill = Image.new("L", img.size, 0)
    fd = ImageDraw.Draw(fill)
    for name, sh in _shapes(plan, view):
        P = _outline(sh, name)
        x, y = to_px(P[:, 0], P[:, 1])
        fd.polygon(list(zip(x, y)), fill=255 if sh.get("op", "add") == "add" else 0)
    base = img.convert("RGB")
    plan_in = np.asarray(fill) > 0
    if model_outline is None:
        tint = Image.new("RGB", img.size, (90, 150, 210))
        out = Image.composite(Image.blend(base, tint, 0.55), base, fill)
    else:  # diff in the plan's framing: grey = both, blue = plan only (missing), red = model only (extra)
        m, (u0, u1), (v0, v1) = model_outline
        yy, xx = np.indices(plan_in.shape)
        wu = c[ua] + (xx - W / 2) / W * s
        wv = c[va] + (W / 2 - yy) / W * s
        col = np.rint((wu - u0) / (u1 - u0) * (m.shape[1] - 1)).astype(int)
        row = np.rint((v1 - wv) / (v1 - v0) * (m.shape[0] - 1)).astype(int)
        ok = (col >= 0) & (col < m.shape[1]) & (row >= 0) & (row < m.shape[0])
        model_in = np.zeros_like(plan_in)
        model_in[ok] = m[row[ok], col[ok]]
        a = np.asarray(base).copy()
        a[plan_in & model_in] = (150, 155, 165)
        a[plan_in & ~model_in] = (60, 120, 230)
        a[~plan_in & model_in] = (225, 75, 60)
        out = Image.fromarray(a)
    d = ImageDraw.Draw(out)
    ey, ex = np.nonzero(plan_in ^ np.roll(plan_in, 1, 0) | plan_in ^ np.roll(plan_in, 1, 1))
    for x, y in zip(ex, ey):
        d.point((int(x), int(y)), fill=(40, 90, 160))
    if va == 2:
        for name, lm in (plan.get("landmarks") or {}).items():
            _, y = to_px(0, float(lm["z"]))
            for x0 in range(0, W, 10):
                d.line([(x0, y), (x0 + 5, y)], fill=(250, 210, 60), width=1)
            d.text((4, y - 14), name, fill=(250, 210, 60), font=FONT, stroke_width=2, stroke_fill=(20, 20, 20))
        for name, sec in (plan.get("sections") or {}).items():
            near = sec.get("center") or sec.get("near") or [0, 0]
            cu = near[0] if view == "front" else near[1]
            half = (sec["width"] if view == "front" else sec["depth"]) / 2
            (xa, xb), y = to_px([cu - half, cu + half], float(sec["z"]))[0], to_px(0, float(sec["z"]))[1]
            d.line([(xa, y), (xb, y)], fill=(120, 240, 140), width=2)
            for xe in (xa, xb):
                d.line([(xe, y - 4), (xe, y + 4)], fill=(120, 240, 140), width=2)
            d.text((xb + 4, y - 7), name, fill=(120, 240, 140), font=FONT, stroke_width=2, stroke_fill=(20, 20, 20))
    return out


def sheet(plan: dict, views: list[str], size: int = 448, outlines: dict | None = None) -> Image.Image:
    """The plan alone (or with model outlines), with rulers, framed like a look contact sheet."""
    from .render import VIEWS, contact_sheet
    bs = [bounds(plan, v) for v in views]
    pts = np.array([[0.0, 0.0, 0.0]])
    for v, b in zip(views, bs):
        if b is None:
            continue
        ua, va = VIEW_AXES[v]
        for corner in (b[0], b[1]):
            q = np.zeros(3)
            q[ua], q[va] = corner
            pts = np.vstack([pts, q])
    lo, hi = pts.min(0), pts.max(0)
    center = (lo + hi) / 2
    scale = float((hi - lo).max() * 1.15)
    frames, imgs = [], []
    for v in views:
        dvec, up, axes = VIEWS[v]
        f = {"name": v, "dir": dvec, "up": up, "center": center.tolist(), "scale": scale, "axes": axes}
        frames.append(f)
        imgs.append(draw_view(Image.new("RGB", (size, size), (56, 58, 64)), f, plan,
                              (outlines or {}).get(v)))
    return contact_sheet(imgs, frames, grid=True)


# ---------------------------------------------------------------- checking

MEASURES = ("top", "bottom", "height", "width", "depth", "diameter", "left", "right", "front", "back")


def extents(prims: list, resolution: int = 128) -> tuple[np.ndarray, np.ndarray] | None:
    """World (lo, hi) of the surface of these primitives alone, to a small fraction of a voxel: extremes from a
    grid, each refined by bisection along its axis on the exact field."""
    from . import sdf
    if not any(p.op == "add" for p in prims):
        return None
    g = sdf.evaluate(prims, resolution)
    inside = g.field < 0
    if not inside.any():
        return None
    idx = np.argwhere(inside)
    lo, hi = np.zeros(3), np.zeros(3)
    for a in range(3):
        for sign, out in ((-1, lo), (1, hi)):
            k = idx[np.argmin(idx[:, a])] if sign < 0 else idx[np.argmax(idx[:, a])]
            p_in = g.origin + k * g.voxel  # inside
            p_out = p_in.copy()
            p_out[a] += sign * 2 * g.voxel  # the next voxel out along the axis is outside
            if sdf.field_at(prims, p_out[None], clip=False)[0] < 0:
                p_out[a] += sign * 4 * g.voxel
            for _ in range(30):
                mid = (p_in + p_out) / 2
                if sdf.field_at(prims, mid[None], clip=False)[0] < 0:
                    p_in = mid
                else:
                    p_out = mid
            out[a] = (p_in[a] + p_out[a]) / 2
    return lo, hi


def check_dimensions(spec: dict, plan: dict) -> list[str]:
    """plan["dimensions"]: real-world numbers measured on the elements, tags or part they name (for props, cages and
    anything whose silhouette IoU says little)."""
    dims = plan.get("dimensions") or {}
    if not dims:
        return []
    from .paintnodes import resolve_near
    from .spec import compile_prims
    prims = compile_prims(spec)
    by_name = {p.name: p for p in prims}
    lines = ["Dimensions (measured on the named elements' own surfaces, vs plan):"]
    cache: dict[str, tuple] = {}
    for name, d in dims.items():
        if "part" in d:
            sel, what = [p for p in prims if p.part == d["part"]], f"part {d['part']}"
        else:
            of = d.get("of", d.get("element", d.get("tag")))
            got, missing = resolve_near(spec, of, by_name)
            if missing or not got:
                lines.append(f"  {name}: nothing named {missing or of!r}")
                continue
            got = set(got)
            sel, what = [p for p in prims if p.name in got and p.op == "add"], (of if isinstance(of, str) else ", ".join(of))
        key = repr(sorted(id(p) for p in sel))
        if key not in cache:
            cache[key] = extents(sel)
        ext = cache[key]
        if ext is None:
            lines.append(f"  {name}: {what} has no surface")
            continue
        lo, hi = ext
        m = d.get("measure", "height")
        val = {"top": hi[2], "bottom": lo[2], "height": hi[2] - lo[2], "width": hi[0] - lo[0],
               "depth": hi[1] - lo[1], "diameter": max(hi[0] - lo[0], hi[1] - lo[1]), "left": hi[0],
               "right": lo[0], "front": lo[1], "back": hi[1]}[m]
        if "value" in d:
            err = val - float(d["value"])
            flag = "  <-- off" if abs(err) > float(d.get("tol", 0.01)) else ""
            lines.append(f"  {name:14s} {m} of {what}: {val:.3f} vs {float(d['value']):.3f} ({err:+.3f}){flag}")
        else:
            lo_ok = "min" not in d or val >= float(d["min"])
            hi_ok = "max" not in d or val <= float(d["max"])
            rng = f"{d.get('min', '')}..{d.get('max', '')}"
            flag = "" if lo_ok and hi_ok else f"  <-- {'below' if not lo_ok else 'above'} {rng}"
            lines.append(f"  {name:14s} {m} of {what}: {val:.3f} (want {rng}){flag}")
    return lines


def subplan(plan: dict, part: str | None) -> dict:
    """The plan with only the shapes standing for `part` (a shape's "part"), or only untagged shapes (None)."""
    out = dict(plan)
    out["views"] = {}
    for v, vd in (plan.get("views") or {}).items():
        sh = {n: s for n, s in ((vd or {}).get("shapes") or {}).items() if s.get("part") == part}
        if sh:
            out["views"][v] = {**vd, "shapes": sh}
    return out


def shape_parts(plan: dict) -> set[str]:
    return {s["part"] for vd in (plan.get("views") or {}).values() for s in ((vd or {}).get("shapes") or {}).values()
            if isinstance(s, dict) and s.get("part")}


def check_numbers(spec: dict, plan: dict) -> list[str]:
    """Landmark and section errors, model vs plan."""
    from . import measure as meas
    from .spec import compile_prims, expand_mirror
    lines = []
    s = expand_mirror(spec)
    lms = plan.get("landmarks") or {}
    if any("joint" in lm for lm in lms.values()):
        lines.append("Landmarks (joint Z vs plan):")
        for name, lm in lms.items():
            j = lm.get("joint")
            if not j:
                continue
            if j not in s["joints"]:
                lines.append(f"  {name}: joint {j!r} doesn't exist")
                continue
            z = s["joints"][j]["pos"][2]
            err = z - float(lm["z"])
            flag = "  <-- off" if abs(err) > float(lm.get("tol", 0.01)) else ""
            lines.append(f"  {name:14s} plan z {lm['z']:.3f}  {j} at {z:.3f}  ({err:+.3f}){flag}")
    secs = plan.get("sections") or {}
    if secs:
        prims = compile_prims(spec)
        from scipy import ndimage
        lines.append("Sections (the slice part containing / nearest `near`):  width X | depth Y | centre, vs plan")
        for name, sec in secs.items():
            z = float(sec["z"])
            near = np.asarray(sec.get("near") or sec.get("center") or [0, 0], float)
            half = 0.6 * max(float(sec["width"]), float(sec["depth"])) + float(np.abs(near).max()) + 0.05
            c = np.array([near[0], near[1], z])
            m, grid = meas._plane(prims, c, np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), half)
            if "x" in sec:  # only this X range (e.g. leave out arms that touch the torso)
                xs = c[0] + grid
                m &= ((xs >= sec["x"][0]) & (xs <= sec["x"][1]))[:, None]
            lab, n = ndimage.label(m)
            if n == 0:
                lines.append(f"  {name:14s} z {z:.3f}: nothing there")
                continue
            k = lab[meas.N // 2, meas.N // 2]
            if k == 0:  # nearest part to `near`
                iu, iv = np.nonzero(lab)
                i = np.argmin(grid[iu] ** 2 + grid[iv] ** 2)
                k = lab[iu[i], iv[i]]
            u0, u1, v0, v1, _ = meas._extent(lab == k, grid)
            w, dpt = u1 - u0, v1 - v0
            cx, cy = c[0] + (u0 + u1) / 2, c[1] + (v0 + v1) / 2
            tol = float(sec.get("tol", 0.08))
            ew, ed = w / float(sec["width"]) - 1, dpt / float(sec["depth"]) - 1
            flag = "  <-- off" if max(abs(ew), abs(ed)) > tol else ""
            ctr = ""
            if "center" in sec:
                ctr = f" | centre ({cx:+.3f}, {cy:+.3f}) vs ({sec['center'][0]:+.3f}, {sec['center'][1]:+.3f})"
            lines.append(f"  {name:14s} z {z:.3f}: width {w:.3f} vs {sec['width']:.3f} ({ew:+.0%}) | "
                         f"depth {dpt:.3f} vs {sec['depth']:.3f} ({ed:+.0%}){ctr}{flag}")
    return lines + check_dimensions(spec, plan)
