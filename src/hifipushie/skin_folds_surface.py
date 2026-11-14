"""The surfaces folds are laid on: `_Surface`, the head's frame, the field surface and the map surface, cached. Part of the skin's folds (skin_folds.py has the overview)."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from . import skin_folds

class _Surface:
    """The head's skin under the map: a point for any direction from the wrap's centre (smooth: the mesh's radius
    interpolated), and the normal there."""

    def __init__(self, spec: dict, part: str, J: dict):
        from scipy.interpolate import LinearNDInterpolator
        from scipy.spatial import cKDTree
        from . import skin_marks_map
        self.sp = skin_marks_map.sphere(J, (-62.0, 72.0), 220.0, skin_folds.PX)
        V, Nn, _ = skin_marks_map.head_mesh(spec, part, J)
        V, Nn = np.asarray(V, float), np.asarray(Nn, float)
        keep = skin_marks_map.outward(self.sp, V, Nn, V)
        self.o = np.asarray(self.sp["fr"]["o"], float)
        self._R = LinearNDInterpolator(skin_marks_map.pix(self.sp, V[keep]), np.linalg.norm(V[keep] - self.o, axis=1))
        self._tree, self._N, self.V, self.Nall, self._Vk = cKDTree(V[keep]), Nn[keep], V, Nn, V[keep]

    def seat(self, P: np.ndarray, snap: bool = False) -> np.ndarray:
        """Points moved along their ray from the wrap's centre onto the skin (left where the wrap does not see).
        snap: first to the nearest point of the skin (a landmark offset floats a few mm off it, and the ray from a centre
        at the mouth's height would carry a point by the eye several mm up the lid)."""
        from . import skin_marks_map
        P = np.asarray(P, float)
        if snap:
            P = self._Vk[self._tree.query(P)[1]]
        d = P - self.o
        r = np.linalg.norm(d, axis=1)
        R = self._R(skin_marks_map.pix(self.sp, P))
        R = np.where(np.isfinite(R), R, r)
        return self.o + d / np.maximum(r, 1e-9)[:, None] * R[:, None]

    def normal(self, P: np.ndarray) -> np.ndarray:
        return self._N[self._tree.query(P)[1]]


def head_frame(J: dict) -> tuple:
    """(right, front, up) of the head from its landmarks (the head's own axes: a posed head carries its folds)."""
    right = np.asarray(J["eye.L"], float) - np.asarray(J["eye.R"], float) if "eye.L" in J and "eye.R" in J else np.array([1.0, 0, 0])
    right = right / np.linalg.norm(right)
    up = (np.asarray(J["lm_nose_bridge"], float) - np.asarray(J["lm_chin"], float)) if "lm_nose_bridge" in J and "lm_chin" in J else np.array([0, 0, 1.0])
    up = up - (up @ right) * right
    up = up / np.linalg.norm(up)
    front = np.cross(right, up)
    # (the face's plane leans a few degrees: the folds' offsets were laid out on world axes of an upright head)
    return right, front / np.linalg.norm(front), up


class _FieldSurface:
    """A part's skin as its exact field (the fold-free one): a point is seated where a ray from in FRONT of the face
    (along the head's own forward axis) first meets it: the visible skin (the closest point of the field's surface
    put a lid's landmark on the lid's INSIDE and walked the tear trough round the socket); the normal is the field's
    gradient. The same for the geometry, the paint map and the reader."""

    def __init__(self, prims: list, J: dict):
        self.prims = prims
        self.right, self.front, self.up = head_frame(J)

    def f(self, X):
        from . import sdf
        return sdf.field_at(self.prims, np.asarray(X, float))

    def seat(self, P: np.ndarray, snap: bool = False, reach: float = 0.03, step: float = 0.00075) -> np.ndarray:
        P = np.asarray(P, float).reshape(-1, 3)
        O = P + reach * self.front
        ts = np.arange(0.0, reach + 0.09, step)   # (well past the point: a landmark can float centimetres off a hand-made head)
        Q = O[:, None, :] - ts[None, :, None] * self.front
        f = self.f(Q.reshape(-1, 3)).reshape(len(P), len(ts))
        inside = f < 0
        i = np.argmax(inside, 1)
        hit = inside.any(1) & (i > 0)
        i = np.where(hit, i, 1)
        a, b = f[np.arange(len(P)), i - 1], f[np.arange(len(P)), i]
        t = ts[i - 1] + step * np.clip(a / np.maximum(a - b, 1e-12), 0, 1)
        X = O - t[:, None] * self.front
        for _ in range(3):          # the crossing refined (the field is close to a distance there)
            X = X - (self.f(X) / np.maximum(self.grad(X) @ self.front, 0.2))[:, None] * self.front
        return np.where(hit[:, None], X, P)

    def grad(self, P: np.ndarray, e: float = 0.0002) -> np.ndarray:
        return np.stack([self.f(P + e * ax) - self.f(P - e * ax) for ax in np.eye(3)], 1) / (2 * e)

    def normal(self, P: np.ndarray) -> np.ndarray:
        g = self.grad(P, 0.0004)
        return g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)


def without(spec: dict) -> dict:
    """The spec with no folds (what their paths are seated on)."""
    if not (spec.get("skin") or {}).get("folds"):
        return spec
    return {**spec, "skin": {k: v for k, v in spec["skin"].items() if k != "folds"}}


def field_surface(prims: list, J: dict) -> _FieldSurface:
    from . import sdf
    key = hashlib.sha1(json.dumps([[sdf.fingerprint(p) for p in prims], [np.round(a, 6).tolist() for a in head_frame(J)]]).encode()).hexdigest()
    if key not in skin_folds._SURF:
        if len(skin_folds._SURF) > 3:
            skin_folds._SURF.pop(next(iter(skin_folds._SURF)))
        skin_folds._SURF[key] = _FieldSurface(prims, J)
    return skin_folds._SURF[key]


def surface(spec: dict, part: str, J: dict) -> _FieldSurface:
    """The skin part's fold-free field as a surface (`spec`: the model; its own folds are left out)."""
    from . import images_frame
    return field_surface(images_frame.prims_on(without(spec), [part]), J)


def map_surface(spec: dict, part: str, J: dict) -> _Surface:
    """The head's skin under the fold map (the mesh the map's pixels are laid on: with the folds' own relief)."""
    from . import skin_marks_map
    V, _, _ = skin_marks_map.head_mesh(spec, part, J)
    key = hashlib.sha1(json.dumps([np.asarray(V[:50]).round(5).tolist(), len(V)]).encode()).hexdigest()
    if key not in skin_folds._MAPSURF:
        if len(skin_folds._MAPSURF) > 3:
            skin_folds._MAPSURF.pop(next(iter(skin_folds._MAPSURF)))
        skin_folds._MAPSURF[key] = _Surface(spec, part, J)
    return skin_folds._MAPSURF[key]
