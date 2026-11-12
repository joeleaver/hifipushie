"""Crown masses: leaf points, masses and subclumps, the crown's field and mesh; silhouettes (is it still the
same tree?). Part of the plant styles (veg_style.py has the overview)."""
from __future__ import annotations

import math

import numpy as np

from . import veg_style
from . import sdf, veg_leaf
from . import vegetation_kernels, vegetation_measures
from .veg_style_wood import mesh_field

# ---------------------------------------------------------------- crown masses
def in_leaf(tree: dict) -> dict:
    """The same tree in summer: a style is fitted to the plant in leaf whatever season it is shown in (a winter tree
    has no twigs to fit masses to, and its limbs must still be the summer tree's)."""
    if tree["spec"].get("season", "summer") == "summer":
        return tree
    return {**tree, "spec": {**tree["spec"], "season": "summer"}}


def leaf_points(tree: dict) -> tuple[np.ndarray, float]:
    """Where the foliage is: the middle of every living twig, and the twig's length (m)."""
    tree = in_leaf(tree)
    tw = veg_leaf.place_live(tree)
    tl = float({**veg_leaf.TWIG, **(tree["spec"]["leaves"].get("twig") or {})}["length"])
    if not len(tw["pos"]):
        return np.zeros((0, 3)), tl
    return tw["pos"] + tw["frame"][:, :, 1] * (0.5 * tl * tw["scale"])[:, None], tl


def _kmeans(X: np.ndarray, k: int, iters: int = 30) -> np.ndarray:
    """Labels of a k-means from a farthest-point start (no randomness: the same tree gives the same masses)."""
    C = [X[np.argmin(np.linalg.norm(X - X.mean(0), axis=1))]]
    d = np.linalg.norm(X - C[0], axis=1)
    for _ in range(1, k):
        C.append(X[int(np.argmax(d))])
        d = np.minimum(d, np.linalg.norm(X - C[-1], axis=1))
    C = np.array(C)
    lab = np.zeros(len(X), int)
    for _ in range(iters):
        D = ((X[:, None, :] - C[None]) ** 2).sum(-1)
        new = D.argmin(1)
        if (new == lab).all() and _:
            break
        lab = new
        for j in range(k):
            if (lab == j).any():
                C[j] = X[lab == j].mean(0)
    return lab


def masses(X: np.ndarray, k: int, st: dict, twig: float, seed: int = 0) -> list[dict]:
    """k ellipsoids over the foliage points: [{"c", "R" (rows = axes), "r" (semi-axes), "n" points}], lowest first."""
    cr = st["crown"]
    ztop = float(X[:, 2].max()) + 0.5 * twig
    if "tiers" in (cr.get("kind"), cr.get("masses_kind")):  # (`masses_kind`: leaf clouds on tiers)
        # stacked dumplings: one upright egg per height band (round above its widest level, flat below it: `tier_under`
        # x the band), seated low in its band, so each overhangs the narrower top of the one below with an undercut.
        # `trunk_show` m of trunk stay bare under the lowest; bands differ in height by `tier_uneven` (the seed's own
        # numbers); the top one is a cap no slimmer than `tier_cap` x its height.
        show = float(cr.get("trunk_show", 0.0))
        z0, z1 = max(float(np.percentile(X[:, 2], 1)), show), float(X[:, 2].max())
        un = float(cr.get("tier_uneven", 0.0))
        jit = (vegetation_kernels._u(np.arange(3 * k + 3).astype(np.uint64) + np.uint64(1000 * (seed + 1)), 91) - 0.5) * 2 if un else np.zeros(3 * k + 3)
        frac = (np.arange(k + 1) / k) ** float(cr.get("tier_power", 1.0))
        frac[1:-1] += 0.5 * un * jit[1:k] * np.diff(frac).min()
        edges = z0 + (z1 - z0) * frac
        out = []
        for j in range(k):
            hgt = edges[j + 1] - edges[j]
            Q = X[(X[:, 2] >= edges[j] - 1e-9) & (X[:, 2] <= edges[j] + 0.6 * hgt)]  # (its width is its lower part's: the band's top is the next one's business)
            if len(Q) < 4:
                Q = X[(X[:, 2] >= edges[j] - 1e-9) & (X[:, 2] <= edges[j + 1] + 1e-9)]
            if len(Q) < 4:
                continue
            c = np.array([Q[:, 0].mean(), Q[:, 1].mean(), edges[j] + float(cr.get("tier_seat", 0.4)) * hgt])
            wj = 1.0 + 0.35 * un * jit[k + 1 + j]
            rx, ry = [wj * float(cr.get("spread", 1.75)) * float(Q[:, i].std()) + float(cr.get("pad", 0.5)) * twig for i in (0, 1)]
            rz = max(float(cr.get("tier_height", 0.75)) * hgt, float(cr.get("roundness", 0.0)) * max(rx, ry) * 0.5)
            if j == k - 1:
                rz = max(ztop - c[2], 0.3 * hgt)
                rx, ry = [max(v, float(cr.get("tier_cap", 0.0)) * rz) for v in (rx, ry)]
            r = np.maximum(np.array([rx, ry, rz]), 0.75 * float(cr.get("min_feature", 0.6)))
            c[2] -= max(0.0, c[2] + r[2] - ztop)
            e = {"c": c, "R": np.eye(3), "r": r, "n": int(len(Q))}
            if cr.get("tier_under") is not None:
                e["down"] = float(np.clip(float(cr["tier_under"]) * hgt, 0.3 * float(cr.get("min_feature", 0.6)), max(c[2] - show, 0.05) if j == 0 else 1e9))
            if cr.get("tier_shape") == "cone":
                # a saw-tooth tier (cartoon firs): a cone standing on its band's foot, `cone_height` x the band tall (it
                # reaches into the next band: the outline steps in and out), its rim cut into `teeth` points in plan
                # (`zig` x its radius in and out): the zigzag outline
                z0 = max(edges[j] - 0.15 * hgt, show) if j else max(edges[0], show)
                Hc = float(cr.get("cone_height", 1.6)) * hgt if j < k - 1 else max(ztop - z0, hgt)
                e["cone"] = {"z0": float(z0), "h": float(min(Hc, ztop - z0)), "teeth": int(cr.get("teeth", 9)), "zig": float(cr.get("zig", 0.12)),
                             "phase": float(vegetation_kernels._u(np.array([j + 7 * (seed + 1)], np.uint64), 93)[0])}
                e["c"] = np.array([c[0], c[1], z0 + 0.3 * e["cone"]["h"]])
                e["r"] = np.array([rx, ry, 0.5 * e["cone"]["h"]])
                e.pop("down", None)
            out.append(e)
        return _scallops(_subclumps(out, X, cr, twig), cr, seed)
    if len(X) > 6000:  # (a cluster's shape doesn't need every twig)
        X = X[np.argsort(vegetation_kernels._u(np.arange(len(X)).astype(np.uint64), 3))[:6000]]
    es = float(cr.get("edge_share", 0.0))
    if es > 0:
        # two sizes of cloud: k big ones over the crown's inner foliage, `edge_count` x k small ones over the outer
        # `edge_share` of it (by its distance out of the crown's middle, in the crown's own proportions); all clouds
        # of one size read as one layer
        r_ = np.linalg.norm((X - X.mean(0)) / np.maximum(X.std(0), 1e-6), axis=1)
        outer = r_ >= np.quantile(r_, 1 - es)
        ke = max(int(round(float(cr.get("edge_count", 1.5)) * k)), 1)
        lab = np.empty(len(X), int)
        lab[~outer] = _kmeans(X[~outer], k)
        lab[outer] = k + _kmeans(X[outer], ke)
        k = k + ke
    else:
        lab = _kmeans(X, k)
    out = []
    for j in range(k):
        Q = X[lab == j]
        if len(Q) < max(4, (0.003 if es > 0 else 0.01) * len(X)):
            continue
        c = Q.mean(0)
        ev, U = np.linalg.eigh(np.cov((Q - c).T) + np.eye(3) * 1e-6)
        r = float(cr.get("spread", 1.75)) * np.sqrt(np.maximum(ev, 0)) + float(cr.get("pad", 0.5)) * twig
        r = np.maximum(r, 0.75 * float(cr.get("min_feature", 0.6)))
        r = np.maximum(r, float(cr.get("roundness", 0.0)) * r.max())  # (a flat cluster as a disc read as a lily pad, not a lump)
        ez = math.sqrt(float(((U.T[:, 2] * r) ** 2).sum()))  # its vertical half extent
        c[2] -= max(0.0, c[2] + ez - ztop)  # never taller than the tree: a rounded-up top mass sinks to the tree's own height
        out.append({"c": c, "R": U.T.copy(), "r": r, "n": int(len(Q))})
    out.sort(key=lambda e: float(e["c"][2]))
    out = _subclumps(out, X, cr, twig)
    out = _scallops(out, cr, seed)
    if cr.get("core") and len(out) > 1:  # the foliage is a shell: a mass in its hollow makes the crown one body with lobes
        c = X.mean(0)
        ev, U = np.linalg.eigh(np.cov((X - c).T) + np.eye(3) * 1e-6)
        r = float(cr["core"]) * np.sqrt(np.maximum(ev, 0))
        r = np.maximum(r, float(cr.get("roundness", 0.0)) * r.max())
        ez = math.sqrt(float(((U.T[:, 2] * r) ** 2).sum()))
        c[2] -= max(0.0, c[2] + ez - ztop)
        out.append({"c": c, "R": U.T.copy(), "r": r, "n": 0, "core": True})
    return out


def _subclumps(out: list, X: np.ndarray, cr: dict, twig: float) -> list:
    """`sub` secondary clumps per mass (pixar: a big canopy shape broken into mid-size leaf clumps with their own volume
    and shadow): each mass's own twigs clustered again, every sub-cluster an ellipsoid (`sub_spread` x its spread +
    `pad`, no axis under `sub_min` x its mass's mean radius) standing on it, `of` = its mass (tone, id, wind), joined
    `sub_join` x the blend (crisper than the masses: the clumps keep their shape and shadow). Sub-clusters sit where
    the twigs are, so they bulge where the real branch clusters are, not on a regular pattern."""
    n = int(cr.get("sub", 0) or 0)
    base = [e for e in out if not e.get("core")]
    if n <= 0 or not base:
        return out
    C = np.array([e["c"] for e in base])
    dn = np.stack([np.linalg.norm(((X - e["c"]) @ e["R"].T) / e["r"], axis=1) for e in base], 1)
    own = dn.argmin(1)
    sp, pad, mn = float(cr.get("sub_spread", 1.6)), float(cr.get("pad", 0.5)), float(cr.get("sub_min", 0.3))
    for j, e in enumerate(base):
        Q = X[own == j]
        k = int(min(n, len(Q) // 12))
        if k < 2:
            continue
        lab = _kmeans(Q, k)
        rm = float(e["r"].mean())
        for q in range(k):
            P = Q[lab == q]
            if len(P) < 6:
                continue
            c = P.mean(0)
            ev, U = np.linalg.eigh(np.cov((P - c).T) + np.eye(3) * 1e-6)
            r = np.maximum(sp * np.sqrt(np.maximum(ev, 0)) + pad * twig, mn * rm)
            r = np.maximum(r, float(cr.get("roundness", 0.0)) * r.max())
            out.append({"c": c, "R": U.T.copy(), "r": r, "n": int(len(P)), "of": next(i for i, x in enumerate(out) if x is e), "join": float(cr.get("sub_join", 0.5))})
    return out


def _scallops(out: list, cr: dict, seed: int) -> list:
    """`scallop` small round bumps standing on each mass's surface (cartoon clumps: a scalloped edge), each bump an
    ellipsoid of `scallop_size` x its mass's mean radius, `of` = its mass's index (one clump for tone, id and wind).
    Placed on the sides and top (a clump's underside stays plain), sunk `scallop_sink` of their radius."""
    n = int(cr.get("scallop", 0) or 0)
    if n <= 0:
        return out
    base = list(out)
    for j, e in enumerate(base):
        if e.get("core") or e.get("cone"):
            continue
        rm = float(e["r"].mean())
        rb = float(cr.get("scallop_size", 0.4)) * rm
        U = _fibonacci(3 * n)
        U = U[U[:, 2] > -0.25][:n] if (U[:, 2] > -0.25).sum() >= n else U[:n]
        ph = 2 * math.pi * float(vegetation_kernels._u(np.array([j + 1000 * (seed + 1)], np.uint64), 95)[0])
        Rz = np.array([[math.cos(ph), -math.sin(ph), 0], [math.sin(ph), math.cos(ph), 0], [0, 0, 1.0]])
        U = U @ Rz.T
        nn = U / e["r"]
        nn /= np.linalg.norm(nn, axis=1, keepdims=True)
        for u, nv in zip(U, nn):
            p = e["c"] + (e["r"] * u) @ e["R"] - float(cr.get("scallop_sink", 0.45)) * rb * (nv @ e["R"])
            out.append({"c": p, "R": np.eye(3), "r": np.full(3, rb), "n": 0, "of": j, "join": float(cr.get("scallop_join", 0.35))})
    return out


def _fibonacci(n: int) -> np.ndarray:
    i = np.arange(n) + 0.5
    z = 1 - 2 * i / n
    a = i * math.pi * (3 - math.sqrt(5))
    r = np.sqrt(np.maximum(1 - z * z, 0))
    return np.c_[r * np.cos(a), r * np.sin(a), z]


def _cone_d(e: dict, p: np.ndarray) -> np.ndarray:
    """A saw-tooth tier's (approximate) distance: a cone on a flat foot with a zigzag rim in plan."""
    cn = e["cone"]
    q = p - np.array([e["c"][0], e["c"][1], cn["z0"]])
    rho = np.linalg.norm(q[:, :2], axis=1)
    th = np.arctan2(q[:, 1], q[:, 0]) / (2 * math.pi) * cn["teeth"] + cn["phase"]
    tri = 4 * np.abs(th - np.floor(th) - 0.5) - 1  # (-1 .. 1, a point at every whole tooth)
    ang = np.arctan2(q[:, 1], q[:, 0])
    R0 = np.sqrt((e["r"][0] * np.cos(ang)) ** 2 + (e["r"][1] * np.sin(ang)) ** 2) * (1 + cn["zig"] * tri)
    H = max(cn["h"], 1e-3)
    Rh = R0 * (1 - np.clip(q[:, 2], 0, None) / H)
    side = (rho - Rh) / np.sqrt(1 + (R0 / H) ** 2)
    return np.maximum(side, -q[:, 2])


def blend_of(ells: list[dict], st: dict) -> float:
    """The crown union's smoothing radius (m): `blend`, or `blend_share` x the masses' mean radius when that is more
    (a fixed 1 m between 5 m masses left eight balloons)."""
    cr = st["crown"]
    size = float(np.mean([e["r"].mean() for e in ells if not e.get("core") and "of" not in e])) if ells else 0.0
    return max(float(cr.get("blend", 0.5)), float(cr.get("blend_share", 0.0)) * size)


def field(ells: list[dict], p: np.ndarray, blend: float, each: bool = False, floor: float | None = None):
    """The crown's field at points (negative inside): the ellipsoids' (approximate) distances under a smooth union.
    each=True also returns the (n, k) distances. floor: nothing under this height."""
    D = np.empty((len(p), len(ells)))
    for j, e in enumerate(ells):
        if e.get("cone"):
            D[:, j] = _cone_d(e, p)
            continue
        q = (p - e["c"]) @ e["R"].T
        r_ = e["r"]
        if e.get("down") is not None:  # an egg: its own (shorter) semi-axis below the middle
            r_ = np.tile(e["r"], (len(q), 1))
            r_[q[:, 2] < 0, 2] = e["down"]
        k0 = np.linalg.norm(q / r_, axis=1)
        k1 = np.linalg.norm(q / (r_ ** 2), axis=1)
        D[:, j] = np.where(k1 > 1e-9, k0 * (k0 - 1.0) / np.maximum(k1, 1e-9), -float(e["r"].min()))
    d = D[:, 0].copy()
    for j in range(1, len(ells)):
        d = sdf.smin(d, D[:, j], blend * float(ells[j].get("join", 1.0)))  # (a scallop bump joins its clump crisper: `join`)
    if floor is not None:
        d = np.maximum(d, floor - p[:, 2])
    return (d, D) if each else d


def _gradient_old(ells, p, blend, floor, h=0.02):
    g = np.empty_like(p)
    for a in range(3):
        e = np.zeros(3)
        e[a] = h
        g[:, a] = field(ells, p + e, blend, floor=floor) - field(ells, p - e, blend, floor=floor)
    return g / (2 * h)


def crown_mesh(ells: list[dict], st: dict, voxel: float | None = None, floor: float | None = None) -> dict:
    """The masses as one closed surface: marching cubes of the field ({"V", "F"}, outward)."""
    cr = st["crown"]
    blend = blend_of(ells, st)
    lo = np.min([e["c"] - e["r"].max() for e in ells], axis=0) - blend
    hi = np.max([e["c"] + e["r"].max() for e in ells], axis=0) + blend
    voxel = voxel or float(cr.get("voxel") or 0) or float(np.clip((hi - lo).max() / 80, 0.06, 0.3))
    V, F = mesh_field(lambda q: field(ells, q, blend, floor=floor), lo, hi, voxel)
    return {"V": V, "F": F, "voxel": voxel, "blend": blend}


def _decimate(V, F, target: int):
    if len(F) <= target:
        return V, F
    import pyfqmr
    for agg in (5, 7, 9):  # (at 5 a long smooth pole stalled at 2.4x its target)
        s = pyfqmr.Simplify()
        s.setMesh(np.ascontiguousarray(V, np.float64), np.ascontiguousarray(F, np.int32))
        s.simplify_mesh(target_count=int(target), aggressiveness=agg, preserve_border=True, verbose=False)
        V2, F2, _ = s.getMesh()
        V, F = np.asarray(V2, float), np.asarray(F2, np.int64)
        if len(F) <= 1.08 * target:
            break
    return V, F


# ---------------------------------------------------------------- silhouettes: is it still the same tree?
def _fill(mask):
    any_, left, right = vegetation_measures._rows(mask)
    f = np.zeros_like(mask)
    for i in np.flatnonzero(any_):
        f[i, left[i]: right[i] + 1] = True
    return f


def mesh_mask(meshes: list, azimuth: float, x0: float, z1: float, px: float, shape) -> np.ndarray:
    """Triangle meshes [(V, F)] seen from the side, in a given frame (as vegetation_measures.silhouette's)."""
    from PIL import Image, ImageDraw
    im = Image.new("L", (shape[1], shape[0]), 0)
    d = ImageDraw.Draw(im)
    c, s_ = math.cos(math.radians(azimuth)), math.sin(math.radians(azimuth))
    for V, F in meshes:
        X = (V[:, 0] * c + V[:, 1] * s_ - x0) * px
        Y = (z1 - V[:, 2]) * px
        T = np.stack([X[F], Y[F]], -1).reshape(len(F), 6)
        for t in T.tolist():
            d.polygon(t, fill=255)
    return np.asarray(im) > 0


def reference(tree: dict, azimuths=veg_style.AZIMUTHS, px: float = 10.0) -> list:
    """The realistic tree's silhouettes in leaf (mask, frame) per azimuth: what every style is held against."""
    return [vegetation_measures.silhouette(in_leaf(tree), az, px, leaves=True, pad=3.0) for az in azimuths]


def compare(tree: dict, meshes: list, azimuths=veg_style.AZIMUTHS, px: float = 10.0, refs: list | None = None) -> dict:
    """The styled meshes against the realistic tree in leaf, from the side at true scale (same frame, feet together):
    IoU of the row-filled outlines per azimuth, and both heights and crown widths (m)."""
    ious, wr, ws = [], [], []
    refs = refs or reference(tree, azimuths, px)
    for az, (A, fr) in zip(azimuths, refs):
        B = mesh_mask(meshes, az, fr["x0"], fr["z1"], px, A.shape)
        A, B = _fill(A), _fill(B)
        ious.append(float((A & B).sum() / max((A | B).sum(), 1)))
        wr.append(float(A.sum(1).max() / px))
        ws.append(float(B.sum(1).max() / px))
    top = max(float(V[:, 2].max()) for V, _ in meshes)
    return {"iou": round(float(np.mean(ious)), 3), "iou_by_azimuth": [round(v, 3) for v in ious], "azimuths": list(azimuths),
            "height_m": [round(float(tree["height"]), 2), round(top, 2)],
            "width_m": [round(float(np.mean(wr)), 2), round(float(np.mean(ws)), 2)]}
