"""Fit a model's numbers to pictures seen from fitted cameras (matched.fit_camera), not only to orthographic
turnarounds: a concept's three-quarter view, a photo. The same Levenberg-Marquardt as fit.py (fit.solve), with
three kinds of rows:

- OUTLINE: a view's whole silhouette against a mask, as fit.py does for front / side / top, along each pixel's
  perspective ray. Model outline samples take the reference's signed distance there; reference outline samples
  take how far the model surface is beyond them (-f / |grad f across the ray|) at the ray's lowest field.
- FEATURE: the outline of one part of the model (named elements, e.g. an ear) traced in the picture, against
  the pixels where that part is SEEN: in front of the rest of the model. A whole silhouette can't see a part
  spreading over the body behind it, or shrinking inside it; this can. Rays search the feature's field only in
  front of the first surface they hit.
- PRESS: a part may sink into the rest of the model where it joins on, and elsewhere rest on it at most `mm`
  in. A buried tip changes no outline, so an outline fit will bury tips (Braynard Racing, Puddles' ears, folded
  back 20-41 mm into the head) unless this is a row. The feature's surface buried deeper than `mm` is split into
  connected pieces; the piece within 1 cm of `join` (plus its depth inside the part) (default: the largest piece) is the join, every other one is penalised
  by its depth.

A target: {"camera": cam dict, "mask": bool (H, W) at the camera's size, "elements": [names] or None (whole
model), "box": (x0, y0, x1, y1) or None, "label": str}. Free parameters are chosen as in fit.parameters
(groups / only / lock). Residuals are metres at the point's depth (pixels x depth / focal)."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage, sparse
from scipy.sparse.csgraph import connected_components
from skimage import measure

from . import fit as F
from . import matched, sdf
from .spec import compile_prims

CHUNK = 3000  # rays per field lookup
JOIN_REACH = 0.01  # a buried piece is the join only this close to the given join point (m)


@dataclass
class View:
    label: str
    cam: dict
    mask: np.ndarray
    box: tuple
    elements: tuple | None
    C: np.ndarray = None
    Fw: np.ndarray = None
    R: np.ndarray = None
    U: np.ndarray = None
    sd: np.ndarray = None       # signed distance (px, + outside) to the mask's outline, over the box
    outline: np.ndarray = None  # (n, 2) reference outline points, image px (x, y)

    def __post_init__(self):
        D, self.Fw, self.R, self.U = matched.axes(self.cam["az"], self.cam["el"], self.cam["roll"])
        self.C = np.asarray(self.cam["aim"], float) + self.cam["dist"] * D
        W, H = self.cam["size"]
        x0, y0, x1, y1 = self.box = tuple(int(v) for v in (self.box or (0, 0, W, H)))
        m = self.mask[y0:y1, x0:x1]
        self.sd = np.where(m, 0.5 - ndimage.distance_transform_edt(m), ndimage.distance_transform_edt(~m) - 0.5)
        rc = F._resample(measure.find_contours(np.pad(m.astype(float), 1), 0.5), 1.0, 6.0) - 1
        self.outline = np.stack([rc[:, 1] + x0, rc[:, 0] + y0], 1) if len(rc) else np.zeros((0, 2))

    def dirs(self, xy):
        """Ray directions (forward component 1, so a point's parameter is its camera depth) for image px."""
        W, H = self.cam["size"]
        f = self.cam["f_px"]
        return (self.Fw[None] + ((xy[:, 0] - W / 2) / f)[:, None] * self.R[None]
                - ((xy[:, 1] - H / 2) / f)[:, None] * self.U[None])

    def ref_sd(self, xy):
        x0, y0 = self.box[:2]
        return ndimage.map_coordinates(self.sd, [xy[:, 1] - y0, xy[:, 0] - x0], order=1, mode="nearest")


def _depths(grid: sdf.Grid, v: View):
    n = np.array(grid.field.shape)
    corners = grid.origin + grid.voxel * (n - 1) * np.array([[i, j, k] for i in (0, 1) for j in (0, 1) for k in (0, 1)])
    z = (corners - v.C) @ v.Fw
    return np.arange(max(z.min(), 1e-3), z.max() + grid.voxel, grid.voxel * 0.75)


def _look(grid: sdf.Grid, P):
    idx = ((P - grid.origin) / grid.voxel).reshape(-1, 3).T
    return ndimage.map_coordinates(grid.field, idx, order=1, mode="constant", cval=1.0).reshape(P.shape[:-1])


def _march(v: View, xy, g_all, zs, g_feat=None):
    """Along each pixel's ray: (lowest field of the whole model, its depth) and, with g_feat, the feature's
    lowest field in front of the first surface the ray hits (and its depth)."""
    out = [np.empty(len(xy)) for _ in range(4)]
    for a in range(0, len(xy), CHUNK):
        d = v.dirs(xy[a:a + CHUNK])
        P = v.C + zs[None, :, None] * d[:, None, :]
        fa = _look(g_all, P)
        k = fa.argmin(1)
        out[0][a:a + CHUNK], out[1][a:a + CHUNK] = fa[np.arange(len(k)), k], zs[k]
        if g_feat is not None:
            hit = np.where((fa < 0).any(1), (fa < 0).argmax(1), len(zs) - 1)
            ff = np.where(np.arange(len(zs))[None] <= hit[:, None] + 2, _look(g_feat, P), 1.0)
            k = ff.argmin(1)
            out[2][a:a + CHUNK], out[3][a:a + CHUNK] = ff[np.arange(len(k)), k], zs[k]
    return out


def _refine(prims, v: View, xy, z0, voxel, zmax=None):
    """Exact lowest field near depth z0 on each ray (17 samples over +-4 voxels), the point, and |grad f|
    across the ray."""
    d = v.dirs(xy)
    zz = z0[:, None] + voxel * np.linspace(-4, 4, 17)[None]
    if zmax is not None:
        zz = np.minimum(zz, zmax[:, None])
    P = v.C + zz[..., None] * d[:, None, :]
    f = sdf.field_at(prims, P, clip=False)
    k = f.argmin(1)
    i = np.arange(len(xy))
    P, f = P[i, k], f[i, k]
    g = _grad(prims, P, voxel * 0.25)
    dn = d / np.linalg.norm(d, axis=1, keepdims=True)
    g -= (g * dn).sum(1, keepdims=True) * dn
    return P, f, np.clip(np.linalg.norm(g, axis=1), 0.2, 5.0)


def _grad(prims, P, h):
    g = np.zeros_like(P)
    for a in range(3):
        e = np.zeros(3)
        e[a] = h
        g[:, a] = (sdf.field_at(prims, P + e, clip=False) - sdf.field_at(prims, P - e, clip=False)) / (2 * h)
    return g


@dataclass
class State:
    theta: np.ndarray
    spec: dict
    rows: list            # (selector elements or None, P, gn, mult) per row group
    r: np.ndarray
    w: np.ndarray
    energy: float
    iou: dict
    buried_mm: float = 0.0
    parts: frozenset | None = None
    extra: dict = field(default_factory=dict)


def _sel(elements):
    if elements is None:
        return compile_prims
    names = set(elements)
    return lambda spec: [p for p in compile_prims(spec) if p.name in names]


def _rest(elements):
    names = set(elements)
    return lambda spec: [p for p in compile_prims(spec) if p.name not in names]


def _press_rows(spec, press, resolution):
    """Rows for a feature buried deeper than press['mm'] anywhere but where it joins on."""
    feat, rest = _sel(press["elements"])(spec), _rest(press["elements"])(spec)
    if not feat or not rest:
        return None
    lo = np.min([p.lo for p in feat], 0) - 0.01
    hi = np.max([p.hi for p in feat], 0) + 0.01
    g = sdf.evaluate(feat, resolution, box=(lo, hi))
    if g.field.min() >= 0 or g.field.max() <= 0:
        return None
    V, Fc, _, _ = measure.marching_cubes(g.field, 0.0)
    V = g.origin + V * g.voxel
    fo = sdf.field_at(rest, V, clip=False)
    mm = press.get("mm", 3.0) / 1000
    deep = fo < -mm
    if not deep.any():
        return 0.0, None
    e = Fc[deep[Fc].all(1)]
    A = sparse.coo_matrix((np.ones(len(e) * 3), (np.r_[e[:, 0], e[:, 1], e[:, 2]], np.r_[e[:, 1], e[:, 2], e[:, 0]])),
                          shape=(len(V), len(V)))
    _, lab = connected_components(A, directed=False)
    pieces = np.unique(lab[deep])
    if "join" in press:
        dj = [np.linalg.norm(V[deep & (lab == c)] - press["join"], axis=1).min() for c in pieces]
        j = np.asarray([press["join"]], float)
        inside = float(np.linalg.norm(V - j, axis=1).min()) if sdf.field_at(feat, j, clip=False)[0] <= 0 else 0.0
        keep = pieces[int(np.argmin(dj))] if min(dj) < JOIN_REACH + inside else -1  # one away from it isn't the join
    else:
        keep = pieces[int(np.argmax([(deep & (lab == c)).sum() for c in pieces]))]
    bad = np.flatnonzero(deep & (lab != keep))
    depth = float((-fo[bad] - mm).max() * 1000) if len(bad) else 0.0
    if not len(bad):
        return 0.0, None
    bad = bad[np.linspace(0, len(bad) - 1, min(len(bad), 300)).astype(int)]
    P = V[bad]
    gf, go = _grad(feat, P, g.voxel * 0.25), _grad(rest, P, g.voxel * 0.25)
    gn = np.clip(np.linalg.norm(gf, axis=1), 0.2, 5.0)
    n = gf / gn[:, None]
    mult = -(go * n).sum(1)
    r = -fo[bad] - mm
    return depth, (tuple(press["elements"]), P, gn, mult, r)


def evaluate(spec: dict, theta, views: list[View], resolution: int, press=None) -> State:
    prims = compile_prims(spec)
    grid = sdf.evaluate(prims, resolution)
    feats, seen = {}, {}
    rows, rs, ws, iou = [], [], [], {}
    energy = 0.0
    for v in views:
        gf = None
        if v.elements:
            if v.elements not in feats:
                fp = _sel(v.elements)(spec)
                lo = np.min([p.lo for p in fp], 0) - 0.01
                hi = np.max([p.hi for p in fp], 0) + 0.01
                feats[v.elements] = (fp, sdf.evaluate(fp, resolution, box=(lo, hi)))
            fp, gf = feats[v.elements]
        x0, y0, x1, y1 = v.box
        ys, xs = np.mgrid[y0:y1, x0:x1]
        pix = np.stack([xs.ravel(), ys.ravel()], 1).astype(float)
        zs = _depths(grid, v)
        fa, za, ff, zf = _march(v, pix, grid, zs, gf)
        img = (ff if v.elements else fa).reshape(ys.shape)
        model = img < 0
        ref = v.mask[y0:y1, x0:x1]
        iou[v.label] = float((model & ref).sum() / max((model | ref).sum(), 1))
        seen[v.label] = model
        mc = F._resample(measure.find_contours(np.pad(img, 1, constant_values=1.0), 0.0), 1.0, 6.0) - 1
        m_xy = np.stack([mc[:, 1] + x0, mc[:, 0] + y0], 1) if len(mc) else np.zeros((0, 2))
        xy = np.concatenate([m_xy, v.outline])
        sel = fp if v.elements else prims
        # coarse depth of each sample ray from the grids, then exact
        fa2, za2, ff2, zf2 = _march(v, xy, grid, zs, gf)
        if v.elements:
            hitz = np.where(fa2 < 0, za2, zs[-1])  # nothing in front of the first hit counts
            P, f, gn = _refine(sel, v, xy, zf2, gf.voxel, zmax=np.maximum(hitz, zf2) + 2 * grid.voxel)
        else:
            P, f, gn = _refine(sel, v, xy, za2, grid.voxel)
        scale = ((P - v.C) @ v.Fw) / v.cam["f_px"]  # metres per pixel at each point's depth
        r = np.concatenate([v.ref_sd(m_xy) * scale[:len(m_xy)], -f[len(m_xy):] / gn[len(m_xy):]])
        w = np.full(len(r), 1.0 / max(len(r), 1))
        rho, _ = F._huber(r, 2.0 * float(np.median(scale)))
        energy += float((w * rho).sum())
        rows.append((v.elements, P, gn, np.ones(len(r))))
        rs.append(r), ws.append(w)
    buried = 0.0
    if press:
        pr = _press_rows(spec, press, resolution)
        if pr is not None:
            buried, row = pr
            if row is not None:
                el, P, gn, mult, r = row
                w = np.full(len(r), float(press.get("weight", 1.0)) / len(r))
                rho, _ = F._huber(r, 0.003)
                energy += float((w * rho).sum())
                rows.append((el, P, gn, mult))
                rs.append(r), ws.append(w)
        iou["buried_mm"] = round(buried, 1)
    cat = lambda xs: np.concatenate(xs) if xs else np.zeros(0)  # noqa: E731
    return State(theta, spec, rows, cat(rs), cat(ws), energy, iou, buried, extra={"seen": seen})


def jacobian(st: State, params) -> np.ndarray:
    blocks = []
    for el, P, gn, mult in st.rows:
        sub = F.State(st.theta, st.spec, None, P, gn, None, None, 0.0, {}, None)
        blocks.append(F.jacobian(sub, params, prims_of=_sel(el)) * mult[:, None])
    return np.concatenate(blocks)


@dataclass
class Result:
    spec: dict
    before: dict
    after: dict
    changes: list
    log: list
    views: list = None
    seen: dict = None   # label -> the model's (fitted) mask over that view's box

    def diff(self, label: str):
        """RGB over the view's box: grey = both, red = model only, blue = picture only."""
        v = next(x for x in self.views if x.label == label)
        x0, y0, x1, y1 = v.box
        m, r = self.seen[label], v.mask[y0:y1, x0:x1]
        im = np.full(m.shape + (3,), 255, np.uint8)
        im[m & r] = (150, 150, 150)
        im[m & ~r] = (220, 40, 40)
        im[r & ~m] = (40, 80, 230)
        return im


def fit(spec: dict, targets: list[dict], groups=F.GROUPS, only=None, lock=(), press=None, iterations: int = 20,
        max_step: float = 0.01, stiffness: float = 0.05, resolution: int = 128) -> Result:
    """Fit the free parameters to the targets' pictures (module docstring). press: {"elements": [...], "mm": 3,
    "join": [x, y, z]?, "weight": 1}."""
    original = copy.deepcopy(spec)
    spec = F.freeze(original)
    views = [View(t.get("label") or f"view{i}", t["camera"], np.asarray(t["mask"], bool), t.get("box"),
                  tuple(t["elements"]) if t.get("elements") else None) for i, t in enumerate(targets)]
    params = [p for p in F.parameters(spec, groups, only, set(lock)) if p[1] in original.get(p[0], {})]
    if not params:
        raise ValueError("nothing to fit: no free parameters")
    theta0 = np.array([F._get(spec, p) for p in params])
    sizes = np.array([F._is_size(p) for p in params])
    shapes = np.array([F._is_shape(p) for p in params])

    def at(theta):
        s = copy.deepcopy(spec)
        for p, val in zip(params, theta):
            F._set(s, p, round(float(val), 5))
        return evaluate(s, theta, views, resolution, press)

    st = at(theta0)
    before = dict(st.iou)
    log = [f"start: energy {st.energy:.3e}  " + " ".join(f"{k} {v}" if isinstance(v, float) and k == "buried_mm"
                                                       else f"{k} {v:.3f}" for k, v in st.iou.items())
           + f"  | {len(params)} parameters, {len(st.r)} rows"]
    st = F.solve(st, at, lambda s: jacobian(s, params), theta0, sizes, shapes, 0.003, iterations, max_step,
                 stiffness, log)
    result = copy.deepcopy(original)
    changes = []
    for p, a, b in zip(params, theta0, st.theta):
        F._set(result, p, round(float(b), 5))
        if abs(b - a) >= 5e-4:
            changes.append(f"{p[0][:-1]} {p[1]}.{p[2]}{'' if p[3] is None else [p[3]]}: {a:.3f} -> {b:.3f}")
    return Result(result, before, dict(st.iou), changes, log, views, st.extra["seen"])


def polygon_mask(size, polygons) -> np.ndarray:
    """A mask (H, W) from outline polygons in image pixels: one [[x, y], ...] or a list of them."""
    from PIL import Image, ImageDraw
    if polygons and np.ndim(polygons[0][0]) == 0:
        polygons = [polygons]
    im = Image.new("L", tuple(size), 0)
    d = ImageDraw.Draw(im)
    for poly in polygons:
        d.polygon([tuple(map(float, q)) for q in poly], fill=255)
    return np.asarray(im) > 0
