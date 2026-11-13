"""A solid made of two skins: its front surface and its back surface, as two height maps over one view plane,
joined at its outline. The shape a creature's head (or its trunk) has when it is built straight from what the
reference pictures show: the front picture's surface, the back picture's, and the outline where they meet.

Over the plane (u to the right, v down, t towards the front viewer) the solid is, inside the footprint `foot`
(a signed distance, metres, negative inside): everything between the front skin t = front(u, v) and the back skin
t = -back(u, v) (`back` is measured towards the back viewer). Whatever lies between the two along a ray is filled:
a horn curling back over the skull joins it where the two overlap in the picture.

The arrays live with the reliefs' (<HOME>/_reliefs/<sha>.npz) and a blob names them:
    {"shape": "twoskin", "skins": "<sha>"}        ("flip": true = mirrored left-right)
twoskin_build.py makes them from the pictures' read surfaces; relief_press.py adds the side picture's detail on top.
"""
from __future__ import annotations

import hashlib
import io

import numpy as np

from . import relief

MAPS = ("front", "back", "foot", "cf", "cb")
ROUND = 0.006       # m: the radius of the edge where the two skins meet


def put(frame: dict, maps: dict) -> str:
    """Store a skin pair; returns its name (a hash of its content)."""
    arrs = {k: np.asarray(maps[k], np.float32) for k in MAPS}
    if len({a.shape for a in arrs.values()}) != 1 or arrs["front"].ndim != 2:
        raise ValueError(f"a skin's maps {MAPS} are 2-D arrays of one shape")
    for k in ("o", "U", "V", "F"):
        arrs[k] = np.asarray(frame[k], np.float64)
    arrs["px"] = np.float64(frame["px"])
    buf = io.BytesIO()
    np.savez_compressed(buf, **arrs)
    sha = hashlib.sha1(b"".join(np.ascontiguousarray(arrs[k]).tobytes() for k in sorted(arrs))).hexdigest()[:20]
    p = relief.pool() / f"{sha}.npz"
    if not p.exists():
        p.write_bytes(buf.getvalue())
    return sha


def sd_twoskin(p: np.ndarray, pr: dict) -> np.ndarray:
    """Distance-like field of the skin pair (a lower bound outside, as an intersection's is)."""
    shp = p.shape[:-1]
    q = p.reshape(-1, 3).astype(np.float64) - pr["o"]
    u, v, t = q @ pr["U"] / pr["px"], q @ pr["V"] / pr["px"], q @ pr["F"]
    H, W = pr["front"].shape
    uc, vc = np.clip(u, 0.0, W - 1.001), np.clip(v, 0.0, H - 1.001)
    off = np.hypot(u - uc, v - vc) * pr["px"]                     # how far outside the maps (0 inside)
    j, i = np.floor(uc).astype(int), np.floor(vc).astype(int)
    fu, fv = uc - j, vc - i

    def at(m):
        return m[i, j] * (1 - fu) * (1 - fv) + m[i, j + 1] * fu * (1 - fv) + m[i + 1, j] * (1 - fu) * fv \
            + m[i + 1, j + 1] * fu * fv

    from .sdf import smin
    a, b = (t - at(pr["front"])) * at(pr["cf"]), (-at(pr["back"]) - t) * at(pr["cb"])
    d = -smin(-a, -b, ROUND)                 # where the two skins meet, a rounded edge, not a knife's
    return np.maximum(d, at(pr["foot"]) + off).reshape(shp)


def prim(name: str, bl: dict, k: float):
    """The additive primitive of a twoskin blob."""
    from .spec import Prim, SpecError
    if not isinstance(bl.get("skins"), str):
        raise SpecError(f"twoskin {name!r}: needs \"skins\": the name build_skins gave it")
    try:
        m = relief.get(bl["skins"])
    except FileNotFoundError as e:
        raise SpecError(f"twoskin {name!r}: {e}") from None
    sx = np.array([-1.0, 1.0, 1.0]) if bl.get("flip") else np.ones(3)
    pr = {key: m[key] for key in MAPS}
    pr.update(o=m["o"] * sx, U=m["U"] * sx, V=m["V"] * sx, F=m["F"] * sx, px=float(m["px"]))
    on = m["foot"] < 0
    if not on.any():
        raise SpecError(f"twoskin {name!r} is empty")
    rows, cols = np.where(on)
    ts = (float(-m["back"][on].max()), float(m["front"][on].max()))
    corners = np.array([pr["o"] + pr["U"] * c * pr["px"] + pr["V"] * r * pr["px"] + pr["F"] * t
                        for c in (cols.min(), cols.max()) for r in (rows.min(), rows.max()) for t in ts])
    return Prim(name, "twoskin", bl.get("op", "add"), k, int(bl.get("layer", 0)), corners.min(0), corners.max(0), pr,
                reach=4.0)   # the field is a lower bound (slopes scaled down to 1/4 at most): a blend reaches further
