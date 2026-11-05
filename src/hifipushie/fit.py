"""Auto-fit: nudge joint positions/radii and blob offsets/sizes so the model's silhouettes match references.

Each reference is placed once, in world units, with the same alignment `compare` uses. The objective is a
symmetric chamfer between outlines: points on the model's outline should lie on the reference outline, and
points on the reference outline should lie on the model's.

The silhouette along a depth axis is g(u, v) = min over depth of the field f, so its outline moves along its
normal by -(df/dθ)/|∇f| when a parameter θ changes, with f taken at the depth where the ray through the
outline point comes closest to the surface (envelope theorem). Every Jacobian column therefore costs one
field evaluation at a few hundred points, and Levenberg-Marquardt steps are cheap. A mild spring toward the
starting values keeps parameters the references can't see (e.g. X positions in a side-only fit) in place.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np
from scipy import ndimage
from skimage import measure

from . import compare as cmp
from . import sdf, softforms
from .spec import SpecError, compile_prims

VIEW_AXES = {"front": (0, 2, 1), "side": (1, 2, 0), "top": (0, 1, 2)}  # world axes of (u, v, depth)
MIN_SIZE = 0.004
GROUPS = ("pos", "r", "offset", "size", "shape")  # shape: squareness of "super" / "loft" blobs


@dataclass
class Target:
    """A reference silhouette fixed in world units (a compare.Placement), with its outline and distance field
    taken from the full-resolution image so the fit aims at the true edge, not a pixel staircase."""
    view: str
    pl: cmp.Placement
    sd: np.ndarray       # signed distance to the reference outline on the padded full-res image (+ outside)
    sd_pad: int
    outline: np.ndarray  # (n, 2) world (u, v) points along the reference outline

    @property
    def mask(self) -> np.ndarray:
        return self.pl.R

    def ref_sd(self, uv: np.ndarray) -> np.ndarray:
        """Signed distance (world units) from the reference outline at world points."""
        rc = self.pl.ref_px(uv) + self.sd_pad
        return ndimage.map_coordinates(self.sd, rc, order=1, mode="nearest") * self.pl.px * self.pl.scale

    def model_mask(self, grid: sdf.Grid) -> np.ndarray:
        """The model's silhouette point-sampled at this target's canvas pixel centres."""
        ua, va, da = VIEW_AXES[self.view]
        rows, cols = np.indices(self.mask.shape)
        iu = (self.pl.u0 + cols * self.pl.px - grid.origin[ua]) / grid.voxel
        iv = (self.pl.v1 - rows * self.pl.px - grid.origin[va]) / grid.voxel
        return ndimage.map_coordinates(grid.field.min(axis=da), [iu, iv], order=1, cval=sdf.FAR) < 0


def _resample(contours, spacing: float, min_len: float) -> np.ndarray:
    """Evenly spaced points along each contour (in the contours' own units), dropping specks."""
    pts = []
    for c in contours:
        seg = np.linalg.norm(np.diff(c, axis=0), axis=1)
        length = seg.sum()
        if length < min_len:
            continue
        s = np.concatenate([[0.0], np.cumsum(seg)])
        t = np.linspace(0.0, length, max(int(length / spacing), 4), endpoint=False)
        pts.append(np.stack([np.interp(t, s, c[:, 0]), np.interp(t, s, c[:, 1])], 1))
    return np.concatenate(pts) if pts else np.zeros((0, 2))


def make_target(view: str, grid: sdf.Grid, ref: np.ndarray, align: str, world=None) -> Target:
    pl = cmp.place(sdf.silhouettes(grid)[view], ref, align, world)
    pad = max(pl.ref.shape) // 3
    img = np.pad(pl.ref, pad)
    sd = np.where(img, 0.5 - ndimage.distance_transform_edt(img), ndimage.distance_transform_edt(~img) - 0.5)
    step = 1.0 / pl.scale  # one canvas pixel, in reference pixels
    rc = _resample(measure.find_contours(ndimage.gaussian_filter(pl.ref.astype(float), 0.5 * step), 0.5),
                   step, 8.0 * step)
    canvas_rc = (rc + 0.5) * pl.scale + [pl.row0, pl.col0] - 0.5
    outline = np.stack([pl.u0 + canvas_rc[:, 1] * pl.px, pl.v1 - canvas_rc[:, 0] * pl.px], 1)
    return Target(view, pl, sd, pad, outline)


def loft_from_refs(spec: dict, refs: dict, name: str, align: str = "auto", resolution: int = 160,
                   parts=None, jump: float = 0.25) -> tuple[dict, list[str]]:
    """Set loft `name`'s sections from the reference outlines at its own section heights: half_width from the
    front outline, half_depth and offset_y from the side one (squareness kept). The references are placed as
    `fit` places them (against the model's current silhouette), so block the rest out first. A row the outline
    doesn't cross keeps its values, and so does a value the outline would change by more than `jump` (25 %): an
    arm or a snout in the outline, which it can't tell from the body. Returns the new spec and one line per section."""
    bl = spec["blobs"][name]
    if bl.get("shape") != "loft":
        raise ValueError(f"{name!r} is not a loft")
    if bl.get("rot") and any(bl["rot"]):
        raise ValueError(f"{name!r}: sections from references need an upright loft (no rot)")
    grid = sdf.evaluate(_prims(spec, parts), resolution)
    targets = {v: make_target(v, grid, *(m if isinstance(m, tuple) else (m, None))[:1], align,
                              (m[1] if isinstance(m, tuple) else None)) for v, m in refs.items()}
    if not {"front", "side"} <= set(targets):
        raise ValueError("sections from references need front and side references")
    c = np.asarray(bl.get("at", [0, 0, 0]), float) + np.asarray(bl.get("offset", [0, 0, 0]), float)
    secs, lines = [dict(x) for x in bl["sections"]], []
    for sec in secs:
        z = c[2] + float(sec["z"])
        ext = {}
        for v, ax in (("front", 0), ("side", 1)):
            t = targets[v]
            u = np.linspace(c[ax] - 1.5, c[ax] + 1.5, 6001)
            inside = t.ref_sd(np.stack([u, np.full_like(u, z)], 1)) < 0
            run = _run_through(inside, int(np.argmin(np.abs(u - c[ax]))))
            if run is not None:
                ext[v] = (u[run[0]] - c[ax], u[run[1]] - c[ax])
        said = []
        if "front" in ext:
            w = float(max(-ext["front"][0], ext["front"][1]))
            if abs(w / sec["half_width"] - 1) > jump:
                said.append(f"half_width kept {sec['half_width']:.3f} (outline {w:.3f}: another part?)")
            else:
                sec["half_width"] = round(w, 4)
                said.append(f"half_width {w:.3f}")
        if "side" in ext:
            a, b = ext["side"]
            if abs((b - a) / 2 / sec["half_depth"] - 1) > jump:
                said.append(f"depth kept (outline y {a:+.3f}..{b:+.3f}: another part?)")
            else:
                sec["half_depth"], sec["offset_y"] = round(float(b - a) / 2, 4), round(float(a + b) / 2, 4)
                said.append(f"y {a:+.3f}..{b:+.3f}")
        lines.append(f"z {sec['z']:.3f}: " + (" ".join(said) or "(outline not crossed: kept)"))
    out = copy.deepcopy(spec)
    out["blobs"][name] = {**bl, "sections": secs}
    return out, lines


def _run_through(inside: np.ndarray, i: int):
    """(first, last) index of the inside run containing i, or the nearest run to it."""
    if not inside.any():
        return None
    if not inside[i]:
        idx = np.flatnonzero(inside)
        i = int(idx[np.argmin(np.abs(idx - i))])
    a, b = i, i
    while a > 0 and inside[a - 1]:
        a -= 1
    while b < len(inside) - 1 and inside[b + 1]:
        b += 1
    return a, b


# ---------------------------------------------------------------- parameters

def parameters(spec: dict, groups=GROUPS, only=None, lock=()) -> list[tuple]:
    """(kind, name, field, index) for every free scalar. Centre-line X stays on the centre line; subtractive
    and layer>=1 elements (sockets, eyeballs, nostrils) are details, left alone unless named in `only`."""
    sym = spec.get("symmetry", True)
    out = []

    def wanted(name, el=None):
        if name in lock:
            return False
        if only is not None:
            return name in only
        return el is None or (el.get("op", "add") == "add" and int(el.get("layer", 0)) == 0)

    for n, j in spec["joints"].items():
        if not wanted(n):
            continue
        if "pos" in groups:
            out += [("joints", n, "pos", i) for i in range(3) if i or not sym or n.endswith(".L")]
        if "r" in groups:
            out.append(("joints", n, "r", None))
    for n, b in spec["bones"].items():
        if wanted(n, b) and "r" in groups:
            out += [("bones", n, f, None) for f in ("r_a", "r_b") if b.get(f) is not None]
    for n, bl in spec["blobs"].items():
        if not wanted(n, bl):
            continue
        centre = sym and not n.endswith(".L")
        if "offset" in groups:
            field = "at" if isinstance(bl.get("at"), list) else "offset"
            out += [("blobs", n, field, i) for i in range(3) if i or not centre]
        if bl.get("shape") == "loft":
            out += _loft_parameters(n, bl, groups)
            continue
        if "size" in groups:
            out += [("blobs", n, "size", i) for i in range(3)]
        if "shape" in groups and bl.get("shape") == "super":
            out += ([("blobs", n, "exponents", i) for i in range(3)] if bl.get("exponents") is not None
                    else [("blobs", n, "squareness", None)])
    return out


def _loft_parameters(n: str, bl: dict, groups) -> list[tuple]:
    """A loft's free scalars: each section's half sizes ("size"), front/back centre ("offset") and squareness
    ("shape"), and each cap's z ("size": how far the dome reaches). Section heights stay: they're the
    measuring stations."""
    out = []
    for i in range(len(bl.get("sections") or [])):
        if "size" in groups:
            out += [("blobs", n, "sections", (i, "half_width")), ("blobs", n, "sections", (i, "half_depth"))]
        if "offset" in groups:
            out.append(("blobs", n, "sections", (i, "offset_y")))
        if "shape" in groups:
            out.append(("blobs", n, "sections", (i, "squareness")))
    for end in ("bottom", "top"):
        cap = bl.get(end)
        if "size" in groups and isinstance(cap, (int, float)):
            out.append(("blobs", n, end, None))
        elif "size" in groups and isinstance(cap, dict) and "z" in cap:
            out.append(("blobs", n, end, "z"))
    return out


_DEFAULTS = {"squareness": 2.0, "offset_y": 0.0}


def _get(spec, p) -> float:
    kind, name, field, i = p
    el = spec[kind][name]
    if i is None:
        return float(el.get(field, 3.0 if field == "squareness" else 0.05))
    if isinstance(i, tuple):  # (section index, key): a loft's sections
        return float(el[field][i[0]].get(i[1], _DEFAULTS.get(i[1], 0.0)))
    if isinstance(i, str):  # a key of a dict field: a loft's cap
        return float(el[field][i])
    return float(el.get(field, [0.0, 0.0, 0.0])[i])


def _set(spec, p, value: float):
    kind, name, field, i = p
    el = spec[kind][name]
    if i is None:
        el[field] = value
    elif isinstance(i, tuple):
        secs = [dict(s) for s in el[field]]
        secs[i[0]][i[1]] = value
        el[field] = secs
    elif isinstance(i, str):
        el[field] = {**el[field], i: value}
    else:
        v = list(el.get(field, [0.0, 0.0, 0.0]))
        v[i] = value
        el[field] = v


def _is_size(p) -> bool:
    return p[2] in ("r", "r_a", "r_b", "size") or (isinstance(p[3], tuple) and p[3][1].startswith("half_"))


def _is_shape(p) -> bool:
    return p[2] in ("squareness", "exponents") or (isinstance(p[3], tuple) and p[3][1] == "squareness")


# ---------------------------------------------------------------- evaluation

@dataclass
class State:
    theta: np.ndarray
    spec: dict
    grid: sdf.Grid
    P: np.ndarray       # (N, 3) closest-approach points of every outline sample
    gn: np.ndarray      # (N,) |∇f| at P
    r: np.ndarray       # (N,) residuals, world units, + = model sticks out
    w: np.ndarray       # (N,) per-sample weight (1 / samples in that view)
    energy: float       # data term only
    iou: dict
    parts: frozenset | None = None  # the parts the silhouettes count (None: all)


def _prims(spec: dict, parts):
    prims = compile_prims(spec)
    return prims if parts is None else [p for p in prims if p.part in parts]


def _closest_depth(prims, uv: np.ndarray, axes, grid: sdf.Grid):
    """For each (u, v), the point along the depth ray where the field is lowest, and the field there."""
    ua, va, da = axes
    lo = grid.origin[da]
    n = grid.field.shape[da]
    depths = lo + grid.voxel * np.arange(n)
    # coarse: the lowest point along each ray from the grid just built for this very model (trilinear; exact
    # near the surface, block-constant further out), then refine with the exact field around it
    coords = np.zeros((3, len(uv), n))
    coords[ua] = ((uv[:, 0] - grid.origin[ua]) / grid.voxel)[:, None]
    coords[va] = ((uv[:, 1] - grid.origin[va]) / grid.voxel)[:, None]
    coords[da] = np.arange(n)[None, :]
    f = ndimage.map_coordinates(grid.field, coords.reshape(3, -1), order=1, mode="nearest").reshape(len(uv), n)
    d0 = depths[f.argmin(axis=1)]
    fine = d0[:, None] + grid.voxel * np.linspace(-4.0, 4.0, 17)
    pts = np.zeros((len(uv), 17, 3))
    pts[..., ua], pts[..., va], pts[..., da] = uv[:, :1], uv[:, 1:], fine
    f = sdf.field_at(prims, pts, clip=False)
    k = f.argmin(axis=1)
    idx = np.arange(len(uv))
    return pts[idx, k], f[idx, k]


def _huber(r, delta):
    a = np.abs(r)
    rho = np.where(a <= delta, 0.5 * r * r, delta * (a - 0.5 * delta))
    wt = np.where(a <= delta, 1.0, delta / np.maximum(a, 1e-12))
    return rho, wt


def evaluate(spec: dict, theta: np.ndarray, targets: list[Target], resolution: int, parts=None) -> State:
    prims = _prims(spec, parts)
    grid = sdf.evaluate(prims, resolution)
    Ps, gns, rs, ws, iou = [], [], [], [], {}
    energy = 0.0
    for t in targets:
        axes = VIEW_AXES[t.view]
        ua, va, da = axes
        g2 = grid.field.min(axis=da)  # [iu, iv]
        iou[t.view] = cmp._iou(t.model_mask(grid), t.mask)

        # model outline samples: residual = reference signed distance there
        px = t.pl.px
        mc = _resample(measure.find_contours(g2, 0.0), px / grid.voxel, 8.0 * px / grid.voxel)
        m_uv = np.stack([grid.origin[ua] + mc[:, 0] * grid.voxel, grid.origin[va] + mc[:, 1] * grid.voxel], 1)
        r_m = t.ref_sd(m_uv)

        # reference outline samples: residual = how far the model surface is beyond them
        uv = np.concatenate([m_uv, t.outline])
        P, f = _closest_depth(prims, uv, axes, grid)
        h = grid.voxel * 0.25
        grad = []
        for a in (ua, va):
            e = np.zeros(3)
            e[a] = h
            grad.append((sdf.field_at(prims, P + e, clip=False) - sdf.field_at(prims, P - e, clip=False)) / (2 * h))
        gn = np.clip(np.hypot(*grad), 0.2, 5.0)
        r = np.concatenate([r_m, -f[len(m_uv):] / gn[len(m_uv):]])

        w = np.full(len(r), 1.0 / len(r))
        rho, _ = _huber(r, 2.0 * px)
        energy += float((w * rho).sum())
        Ps.append(P), gns.append(gn), rs.append(r), ws.append(w)
    return State(theta, spec, grid, np.concatenate(Ps), np.concatenate(gns), np.concatenate(rs),
                 np.concatenate(ws), energy, iou, parts)


def _left_out(spec: dict, parts) -> set[str]:
    """Bones and blobs outside `parts`, and the joints that only they hang on."""
    out, used = set(), {}
    for kind in ("bones", "blobs"):
        for n, el in spec.get(kind, {}).items():
            kept = el.get("part", "body") in parts
            if not kept:
                out.add(n)
            refs = [el.get("a"), el.get("b")] if kind == "bones" else [el.get("at")]
            for r in refs:
                if isinstance(r, str):
                    used[r] = used.get(r, False) or kept
    return out | {j for j, kept in used.items() if not kept and j in spec.get("joints", {})}


def freeze(spec: dict) -> dict:
    """The model with kits, surface-seated joints and strokes expanded once into plain elements, so the
    hundreds of perturbed copies a fit compiles don't each re-seat them (a face kit and dozens of strokes
    made one iteration take minutes). Details stay where they are while the blockout moves; the fitted
    values are then applied to the real model, whose details regenerate."""
    from . import anatomy, kits, strokes
    out = strokes.expand(strokes.seat_joints(anatomy.expand(kits.expand(spec))))
    out.pop("kits", None)
    out.pop("strokes", None)
    return out


def jacobian(st: State, params: list[tuple], eps: float = 1e-4) -> np.ndarray:
    """d(residual)/dθ: the outline's outward motion is -(df/dθ)/|∇f|, and residuals are + when sticking out."""
    spec = copy.deepcopy(st.spec)
    base = _prims(spec, st.parts)
    f0 = sdf.field_at(base, st.P, clip=False)
    fp0 = {sdf.fingerprint(q): q for q in base}
    kmax = max([q.blend for q in base] + [0.0])
    J = np.zeros((len(st.P), len(params)))
    for k, p in enumerate(params):
        v = _get(spec, p)
        h = eps
        try:
            _set(spec, p, v + h)
            prims = _prims(spec, st.parts)
        except SpecError:  # on an element's limit (a blade as thick as it may be): difference backwards
            h = -eps
            _set(spec, p, v + h)
            prims = _prims(spec, st.parts)
        _set(spec, p, v)
        fp1 = {sdf.fingerprint(q): q for q in prims}
        changed = [fp1[f] for f in fp1.keys() - fp0.keys()] + [fp0[f] for f in fp0.keys() - fp1.keys()]
        # a perturbation only moves the field where a changed primitive is (nearly) the surface: an add
        # within a few blend radii of the current value, anything else within its box
        hit = np.zeros(len(st.P), bool)
        for q in changed:
            if q.op == "add":
                hit |= sdf.SDF[q.kind](st.P, q.params) < f0 + 3 * kmax + 1e-3
            else:
                m = (0.0 if q.op == "modify" else float(np.max(q.reach))) + kmax
                hit |= np.all((st.P >= q.lo - m) & (st.P <= q.hi + m), axis=1)
        idx = np.flatnonzero(hit)
        if len(idx):
            J[idx, k] = -(sdf.field_at(prims, st.P[idx], clip=False) - f0[idx]) / h / st.gn[idx]
    return J


# ---------------------------------------------------------------- driver

@dataclass
class FitResult:
    spec: dict
    iou_before: dict
    iou_after: dict
    changes: list[str]
    log: list[str]
    targets: list[Target]
    grid: sdf.Grid


def fit(spec: dict, refs: dict[str, np.ndarray], align: str = "auto", groups=GROUPS, only=None, lock=(),
        iterations: int = 20, max_step: float = 0.02, stiffness: float = 0.05,
        resolution: int = 160, pin=(), parts=None) -> FitResult:
    """pin: individual scalars to hold, as (kind, name, field, index), e.g. ("joints", "knee.L", "pos", 2) for a
    joint whose height a plan landmark fixes. parts: the part names the silhouettes count (None: all); elements
    of other parts, and joints only they hang on, stay put."""
    original = copy.deepcopy(spec)
    spec = freeze(original)
    grid0 = sdf.evaluate(_prims(spec, parts), resolution)
    # refs: view -> mask, or (mask, world placement) for references with world coordinates (plans)
    targets = []
    for v, m in refs.items():
        mask, world = m if isinstance(m, tuple) else (m, None)
        targets.append(make_target(v, grid0, mask, align, world))
    pinned = {tuple(p) for p in pin}
    seated = {n for n, j in original.get("joints", {}).items() if "on" in j}
    params = [p for p in parameters(spec, groups, only, set(lock) | seated)
              if p not in pinned and p[1] in original.get(p[0], {})]  # the model's own elements only
    if parts is not None:
        params = [p for p in params if p[1] not in _left_out(spec, parts)]
    if not params:
        raise ValueError("nothing to fit: no free parameters")
    theta0 = np.array([_get(spec, p) for p in params])
    sizes = np.array([_is_size(p) for p in params])
    shapes = np.array([_is_shape(p) for p in params])

    def at(theta):
        s = copy.deepcopy(spec)
        for p, v in zip(params, theta):
            _set(s, p, round(float(v), 5))
        return evaluate(s, theta, targets, resolution, parts)

    st = at(theta0)
    iou_before = st.iou
    log = [f"start: energy {st.energy:.3e}  IoU " + " ".join(f"{k} {v:.3f}" for k, v in st.iou.items())
           + f"  | {len(params)} parameters, {len(st.r)} outline samples"]
    lam, mu = 1e-2, None
    for it in range(iterations):
        J = jacobian(st, params)
        _, irls = _huber(st.r, 2.0 * targets[0].pl.px)
        JtW = J.T * (st.w * irls)
        H = JtW @ J
        if mu is None:
            d = np.diag(H)
            mu = stiffness * float(np.median(d[d > 1e-12])) if (d > 1e-12).any() else 1e-6
        prior = lambda th: 0.5 * mu * float(((th - theta0) ** 2).sum())  # noqa: E731
        grad = JtW @ st.r + mu * (st.theta - theta0)
        A0 = H + mu * np.eye(len(params))
        for _ in range(8):
            step = np.linalg.solve(A0 + lam * np.diag(np.diag(A0)), -grad)
            step *= max_step / max(np.abs(step).max(), max_step)
            new = st.theta + step
            new[sizes] = np.maximum(new[sizes], MIN_SIZE)
            new[shapes] = np.clip(new[shapes], softforms.SQ_MIN, softforms.SQ_MAX)
            try:
                cand = at(new)
            except SpecError:  # the step made an element invalid (a blade thicker than it's wide): a smaller one
                lam *= 4
                continue
            if cand.energy + prior(new) < st.energy + prior(st.theta):
                gain = 1 - (cand.energy + prior(new)) / (st.energy + prior(st.theta))
                st, lam = cand, max(lam / 3, 1e-5)
                break
            lam *= 4
        else:
            log.append(f"iter {it + 1}: no improving step; stopping")
            break
        log.append(f"iter {it + 1}: energy {st.energy:.3e}  IoU "
                   + " ".join(f"{k} {v:.3f}" for k, v in st.iou.items()) + f"  (max move {np.abs(step).max():.4f})")
        if gain < 2e-3:
            break

    result = copy.deepcopy(original)  # the fitted values on the real model: its kits and strokes regenerate
    for p, v in zip(params, st.theta):
        _set(result, p, round(float(v), 5))
    changes = []
    moved = {}
    for p, a, b in zip(params, theta0, st.theta):
        if abs(b - a) >= 5e-4:
            moved.setdefault(p[:3], []).append((p[3], a, b))
    for (kind, name, field), vals in moved.items():
        if not isinstance(vals[0][0], (int, type(None))):  # a loft's section values, a cap's z: one line each
            changes += [f"{kind[:-1]} {name}.{field}{list(i) if isinstance(i, tuple) else '.' + i}: {a:.3f} -> {b:.3f}"
                        f" ({b - a:+.3f})" for i, a, b in vals]
        elif vals[0][0] is None:
            _, a, b = vals[0]
            changes.append(f"{kind[:-1]} {name}.{field}: {a:.3f} -> {b:.3f} ({b - a:+.3f})")
        else:
            d = [0.0, 0.0, 0.0]
            for i, a, b in vals:
                d[i] = b - a
            new = [round(v, 3) for v in result[kind][name][field]]
            changes.append(f"{kind[:-1]} {name}.{field}: moved [{d[0]:+.3f},{d[1]:+.3f},{d[2]:+.3f}] -> {new}")
    return FitResult(result, iou_before, st.iou, changes, log, targets, st.grid)


def diff_images(res: FitResult):
    """Diff images (model vs placed reference) for the fitted model, on the fixed placement."""
    return {t.view: cmp.diff_image(t.model_mask(res.grid), t.mask)[0] for t in res.targets}
