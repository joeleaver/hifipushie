"""A surface refined on a mesh, carried back into the clay as a NUDGE: every point of a solid's surface moved along
its normal by a small, smoothly varying amount (surfacefuse.py's result: how far each vertex of the solid's mesh
moved). A modifier, like a stroke: the solid under it keeps deciding what is inside and what is outside, so thin
parts and sharp edges stay sound (a field made from the refined mesh's points and normals alone gets the sign wrong
beside every thin edge: tried, and it filled the build with blocks).

The points live with the reliefs' arrays (<HOME>/_reliefs/<sha>.npz) and a blob names them:
    {"shape": "nudge", "nudge": "<sha>", "layer": 60}        ("flip": true = mirrored left-right)
"""
from __future__ import annotations

import hashlib
import io

import numpy as np

from . import relief

K = 4
LAYER = 60
_TREES: dict[tuple, tuple] = {}


def put(verts: np.ndarray, moved: np.ndarray) -> str:
    """Store a nudge: the surface's points and how far each moved outwards (metres); returns its name."""
    arrs = {"verts": np.asarray(verts, np.float32), "moved": np.asarray(moved, np.float32)}
    if arrs["verts"].ndim != 2 or len(arrs["verts"]) != len(arrs["moved"]):
        raise ValueError("a nudge is points (n, 3) and one distance per point")
    buf = io.BytesIO()
    np.savez_compressed(buf, **arrs)
    sha = hashlib.sha1(b"".join(np.ascontiguousarray(arrs[k]).tobytes() for k in sorted(arrs))).hexdigest()[:20]
    p = relief.pool() / f"{sha}.npz"
    if not p.exists():
        p.write_bytes(buf.getvalue())
    return sha


def _tree(sha: str, flip: bool):
    key = (sha, flip)
    if key not in _TREES:
        from scipy.spatial import cKDTree
        m = relief.get(sha)
        V = m["verts"].astype(np.float64) * (np.array([-1.0, 1.0, 1.0]) if flip else np.ones(3))
        tree = cKDTree(V)
        d, _ = tree.query(V[:: max(1, len(V) // 2000)], k=2)
        if len(_TREES) > 8:
            _TREES.pop(next(iter(_TREES)))
        _TREES[key] = (tree, m["moved"].astype(np.float64), float(np.median(d[:, 1])))
    return _TREES[key]


def mod_nudge(cur: np.ndarray, p: np.ndarray, pr: dict) -> np.ndarray:
    """The field with the surface moved: cur - (how far the nearest surface points moved), near the surface only."""
    tree, moved, h = _tree(pr["nudge"], pr["flip"])
    c0 = cur.reshape(-1)
    near = np.flatnonzero(np.abs(c0) < 2 * pr["reach"])
    if not len(near):
        return cur
    q = p.reshape(-1, 3)[near].astype(np.float64)
    dist, idx = tree.query(q, k=K, distance_upper_bound=3 * pr["reach"] + 4 * h)
    ok = np.isfinite(dist)
    w = np.where(ok, np.exp(-(dist ** 2 - dist[:, :1] ** 2) / (1.5 * h) ** 2), 0.0)
    d = (w * moved[np.where(ok, idx, 0)]).sum(1) / np.maximum(w.sum(1), 1e-12)
    a = np.abs(c0[near].astype(np.float64))
    s = np.clip((2 * pr["reach"] - a) / pr["reach"], 0.0, 1.0)      # full within reach of the surface, none at twice
    # only the surface the points were taken from: a neighbour's surface passing close by is left alone (it lies
    # further from the points than they moved, plus a couple of spacings)
    own = np.clip(1.0 - (np.where(ok[:, 0], dist[:, 0], np.inf) - np.abs(d) - 2 * h) / (2 * h), 0.0, 1.0)
    out = c0.copy()
    out[near] = (c0[near] - d * s * s * (3 - 2 * s) * own).astype(out.dtype)
    return out.reshape(cur.shape)


def prim(name: str, bl: dict):
    from .spec import Prim, SpecError
    if not isinstance(bl.get("nudge"), str):
        raise SpecError(f"nudge {name!r}: needs \"nudge\": the name its maker gave it")
    try:
        m = relief.get(bl["nudge"])
    except FileNotFoundError as e:
        raise SpecError(f"nudge {name!r}: {e}") from None
    V = m["verts"] * (np.array([-1.0, 1.0, 1.0]) if bl.get("flip") else np.ones(3))
    most = float(np.abs(m["moved"]).max())
    reach = max(2 * most, 0.003)
    lo, hi = V.min(0) - 2 * reach, V.max(0) + 2 * reach
    return Prim(name, "nudge", "modify", 0.0, int(bl.get("layer", LAYER)), lo, hi,
                {"nudge": bl["nudge"], "flip": bool(bl.get("flip")), "reach": reach}, lip=3.0)
