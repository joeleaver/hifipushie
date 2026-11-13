"""A relief: a part's surface as one reference picture shows it, pressed into the clay from that picture's side.

A relief is a height map over a view plane: per pixel, how far towards the viewer the surface stands (`top`).
It does two plain things to the clay that is there, both only on the viewer's side of the part (above `lo`):
  adds   clay up to the height map, inside the footprint `add`
  cuts   away whatever stands in front of the height map, inside the footprint `cut`
Both footprints are signed distances (metres, negative inside), so at a border to another part a relief ends in
a clean edge however far it stands from the clay under it. How far the result is taken is the weight `k` (0..1):
full where the picture's surface faces the viewer, falling to nothing as it turns away, so that where another
view sees the surface better the clay (and that view's relief) is left alone and the two meet in a slope, not a
step. The far side of the part, its neighbours and whatever no picture shows keep their shape.

The arrays live content-addressed in <HOME>/_reliefs/<sha>.npz (a copied model keeps working, a changed relief
is a changed spec), and a blob names them:
    {"shape": "relief", "relief": "<sha>", "layer": 60}        ("flip": true = mirrored left-right)
Frame: a world point p has u = (p - o).U / px (map columns), v = (p - o).V / px (map rows: V points down the
map) and t = (p - o).F (metres towards the viewer). relief_press.py makes them from a picture's read surface.
"""
from __future__ import annotations

import hashlib
import io

import numpy as np

from . import store

LAYER = 60          # after every solid of the part, before the strokes laid on top
MAPS = ("top", "lo", "add", "cut", "k", "cos")
WELD = 0.003        # m: how softly added clay meets the clay beside it, and how much a cut's edge is eased
_CACHE: dict[str, dict] = {}


def pool():
    d = store.HOME / "_reliefs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def put(frame: dict, maps: dict, lip: float = 1.3) -> str:
    """Store a relief; returns its name (a hash of its content)."""
    arrs = {k: np.asarray(maps[k], np.float32) for k in MAPS}
    if len({a.shape for a in arrs.values()}) != 1 or arrs["top"].ndim != 2:
        raise ValueError(f"a relief's maps {MAPS} are 2-D arrays of one shape")
    for k in ("o", "U", "V", "F"):
        arrs[k] = np.asarray(frame[k], np.float64)
    arrs["px"] = np.float64(frame["px"])
    arrs["lip"] = np.float64(lip)
    buf = io.BytesIO()
    np.savez_compressed(buf, **arrs)
    sha = hashlib.sha1(b"".join(np.ascontiguousarray(arrs[k]).tobytes() for k in sorted(arrs))).hexdigest()[:20]
    p = pool() / f"{sha}.npz"
    if not p.exists():
        p.write_bytes(buf.getvalue())
    return sha


def get(sha: str) -> dict:
    if sha not in _CACHE:
        p = pool() / f"{sha}.npz"
        if not p.exists():
            raise FileNotFoundError(f"relief {sha!r} is not in {pool()} (a relief pressed in another workspace?)")
        with np.load(p) as z:
            _CACHE[sha] = {k: z[k] for k in z.files}
        if len(_CACHE) > 64:
            _CACHE.pop(next(iter(_CACHE)))
    return _CACHE[sha]


def mod_relief(cur: np.ndarray, p: np.ndarray, pr: dict) -> np.ndarray:
    """The field with the relief pressed in: clay added up to the height map, then what stands in front cut."""
    from .sdf import smin
    q = p.reshape(-1, 3).astype(np.float64) - pr["o"]
    u, v, t = q @ pr["U"] / pr["px"], q @ pr["V"] / pr["px"], q @ pr["F"]
    H, W = pr["top"].shape
    ok = np.flatnonzero((u > 0) & (u < W - 1) & (v > 0) & (v < H - 1))
    if not len(ok):
        return cur
    uu, vv, t = u[ok], v[ok], t[ok]
    j, i = np.floor(uu).astype(int), np.floor(vv).astype(int)
    fu, fv = uu - j, vv - i

    def at(m):
        return m[i, j] * (1 - fu) * (1 - fv) + m[i, j + 1] * fu * (1 - fv) + m[i + 1, j] * (1 - fu) * fv \
            + m[i + 1, j + 1] * fu * fv

    cos, under = at(pr["cos"]), at(pr["lo"]) - t           # under > 0: below the relief's floor
    g = (t - at(pr["top"])) * cos                           # the height map's own field
    out = cur.reshape(-1).copy()
    c0 = out[ok].astype(np.float64)
    c1 = smin(c0, np.maximum(np.maximum(g, at(pr["add"])), under), WELD)
    cut = np.minimum(np.minimum(g, -at(pr["cut"])), -under)          # > 0 where clay must go
    out[ok] = (c0 + at(pr["k"]) * (-smin(-c1, -cut, WELD) - c0)).astype(out.dtype)
    return out.reshape(cur.shape)


def prim(name: str, bl: dict):
    """The modifier primitive of a relief blob."""
    from .spec import Prim, SpecError
    if not isinstance(bl.get("relief"), str):
        raise SpecError(f"relief {name!r}: needs \"relief\": the name press_relief gave it")
    try:
        m = get(bl["relief"])
    except FileNotFoundError as e:
        raise SpecError(f"relief {name!r}: {e}") from None
    sx = np.array([-1.0, 1.0, 1.0]) if bl.get("flip") else np.ones(3)
    pr = {k: m[k] for k in MAPS}
    pr.update(o=m["o"] * sx, U=m["U"] * sx, V=m["V"] * sx, F=m["F"] * sx, px=float(m["px"]))
    on = np.minimum(m["add"], m["cut"]) < 0
    if not on.any():
        raise SpecError(f"relief {name!r} is empty")
    rows, cols = np.where(on)
    pad = 0.004
    ts = (float(m["lo"][on].min()) - pad, float(m["top"][on].max()) + pad)
    corners = np.array([pr["o"] + pr["U"] * c * pr["px"] + pr["V"] * r * pr["px"] + pr["F"] * t
                        for c in (cols.min() - 1, cols.max() + 1) for r in (rows.min() - 1, rows.max() + 1) for t in ts])
    return Prim(name, "relief", "modify", 0.0, int(bl.get("layer", LAYER)), corners.min(0), corners.max(0), pr,
                lip=float(np.clip(m["lip"], 1.0, 4.0)))
