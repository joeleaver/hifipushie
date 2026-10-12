"""Folds: the soft-tissue lines and bulges a face's SHAPE model does not make (GNM's identity space has no eye bags,
no deep nasolabial fold, no crisp lid crease): spec["skin"]["folds"]. Each is a named anatomical feature placed from
the head's own landmarks (a path over the skin in interocular units: FOLDS), with the path's measured placement as
parameters (what skin_read reads off the reference pictures), laid as colour AND relief from ONE unique map on the
head (skin_marks' sphere wrap, as the stubble / freckle / base maps are):

  r  the groove: a soft valley along the path (painted height down + a darker, redder crease line)
  g  the roll beside it: a bulge (painted height up): the bag over a tear trough, the cheek's pad over a nasolabial fold
  b  the fold's own shade: a wider, soft darkening (what the valley's occlusion does to the light)

skin["folds"] = {name: amount | {"amount": 0..1.5, "width": mm (the feature's default), "roll": 0..1.5 (x the
  feature's own roll), "L": {"amount": x (times the fold's), "shift": [mm, ...] (the line moved ACROSS its landmark path,
  at stations evenly spaced along it; + = the feature's `plus` side), "extent": [t0, t1] (the part of the path that
  shows, 0..1)}, "R": {...}}}   (a centre-line fold takes "shift" / "extent" directly)

RELIEF IS GEOMETRY (skinfolds, 2026-10-12; skin["fold_relief"] = "geometry", the default): each fold is a modifier
of the skin part's FIELD (`prims`, sdf kind "tissue"): a profile across the path (RELIEF: a groove, a roll rising
from the groove's line on the plus side: the bag over a tear trough, the cheek's pad over a nasolabial fold, the
hooding over a lid's crease, and for the lid a platform under it) swept along the same landmark path with the same
amount / shift / extent per side, so what skin_read measures drives it. It is in the built surface: every render,
the silhouette, raking light, the export's high-poly (its normal / AO maps; the low-poly as far as its triangles
go). The displacement fades out toward the lid margins and the lip line (KEEP) and can never push the skin onto the
eyeball (BALL). Amount 0 = no primitive: nothing is evaluated, the build key is the fold-free model's. The paths are
seated on the part's field WITHOUT the folds (`field_surface`), in the paint map, the reader and the geometry alike.
skin["fold_relief"] = "paint" keeps the old painted height (bump in the look): it shades like a groove 0.2-0.8 mm
deep seen from the front, never changes the silhouette, and a raking light or a profile view shows a flat cheek.
The map then carries the COLOUR only (the crease line's tint, the soft shade): b.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

from .spec import SpecError

VERSION = 9
PX = 0.0001            # m a map pixel at the face
DEPTH = 0.0009         # m: the groove layer's painted depth at map value 1
BULGE = 0.0010         # m: the roll layer's painted height at map value 1
STATION = 0.001        # m between stations along a path (the map's and the reader's)
N_SHIFT = 9            # shift is given at this many stations by default (any number is taken: interpolated)

# name -> path [(anchor joint, offset in interocular units)] on the LEFT side (".L" anchors: mirrored to the right;
# without: one centre-line fold), "plus": the anatomical direction of + shift (a world vector the across direction is
# signed by), width (mm, the valley's full width at half depth), depth (share of DEPTH at amount 1), tint (the crease
# line's darkening at amount 1), shade (the wide soft darkening), roll (bulge: (offset mm toward plus, width mm,
# share of BULGE)) or None, search (mm either side of the path the reader looks), res (mm a picture pixel: coarser
# pictures answer "cannot tell"), about.
FOLDS = {
    "nasolabial": {"path": [("lm_nostril.L", (0.08, 0.02, 0.03)), ("lm_mouth_corner.L", (0.14, 0.05, 0.12)),
                            ("lm_mouth_corner.L", (0.16, 0.07, -0.15))], "plus": (1, 0, 0.3), "width": 3.5, "depth": 0.8,
                   "tint": 0.35, "shade": 0.2, "roll": (4.5, 5.0, 0.35), "search": 6.0, "res": 1.6,
                   "about": "the fold from the nose's wing past the mouth's corner (the cheek's pad over it)"},
    # (from under the corner's own dimple: a young mouth's corner shadow is not a marionette line)
    "marionette": {"path": [("lm_mouth_corner.L", (0.07, 0.02, -0.12)), ("lm_mouth_corner.L", (0.12, 0.05, -0.45))],
                   "plus": (1, 0, 0), "width": 3.0, "depth": 0.7, "tint": 0.3, "shade": 0.2, "roll": (4.0, 4.5, 0.3),
                   "search": 4.5, "res": 1.4, "about": "the line down from the mouth's corner (the jowl's front edge)"},
    "mouth_corner": {"path": [("lm_mouth_corner.L", (0.06, 0.01, 0.0)), ("lm_mouth_corner.L", (0.18, 0.07, -0.03))],
                     "plus": (0, 0, 1), "width": 1.4, "depth": 0.45, "tint": 0.5, "shade": 0.15, "roll": None,
                     "search": 2.5, "res": 0.7, "about": "the crease running out from the mouth's corner"},
    "mentolabial": {"path": [("lm_lip_lower", (-0.3, 0.04, -0.13)), ("lm_lip_lower", (0.0, 0.0, -0.15)),
                             ("lm_lip_lower", (0.3, 0.04, -0.13))], "plus": (0, 0, 1), "width": 4.0, "depth": 0.6,
                    "tint": 0.2, "shade": 0.25, "roll": None, "search": 4.0, "res": 1.6,
                    "about": "the groove between the lower lip and the chin"},
    # (the orbit's lower rim: from under the inner corner down, and UP again toward the outer corner: with three
    # points running on down and out the bag over it was a box with a cut end, not a crescent)
    # (the lid-cheek junction lies ~10 mm under the lid's margin: at 0.215 x the pupils' distance, 13 mm, Garrett's
    # painted troughs sat at the upper end of the reader's window and were read along 15-31 % of the path)
    "tear_trough": {"path": [("lm_eye_inner.L", (0.03, 0.0, -0.08)), ("lm_lid_lower_in.L", (0.0, 0.0, -0.15)),
                             ("lm_lid_lower.L", (0.02, 0.0, -0.175)), ("lm_lid_lower_out.L", (0.05, 0.0, -0.15)),
                             ("lm_eye_outer.L", (0.05, 0.0, -0.09))], "plus": (0, 0, 1), "width": 3.5, "depth": 0.7,
                    "tint": 0.25, "shade": 0.25, "roll": (4.0, 4.0, 0.8), "search": 5.0, "res": 1.6,
                    "about": "the groove under the lower lid; its roll is the eye bag over it"},
    # (along the upper margin's own landmarks, a crease height over each: with three points the ends cut across the
    # opening's corners and were seated inside the socket)
    "lid_fold": {"path": [("lm_eye_inner.L", (0.035, 0.0, 0.045)), ("lm_lid_upper_in.L", (0.0, 0.0, 0.058)),
                          ("lm_lid_upper.L", (0.0, 0.0, 0.062)), ("lm_lid_upper_out.L", (0.0, 0.0, 0.058)),
                          ("lm_eye_outer.L", (0.025, 0.0, 0.04))], "plus": (0, 0, 1), "width": 1.2, "depth": 0.3,
                 "tint": 1.3, "shade": 0.5, "roll": None, "search": 2.0, "flank": 1.0, "res": 0.5,
                 "about": "the upper eyelid's crease line (the fold GNM's lids only hint at)"},
    "glabella": {"path": [("lm_brow_inner.L", (-0.035, -0.01, 0.1)), ("lm_brow_inner.L", (-0.015, -0.01, -0.08))],
                 "plus": (1, 0, 0), "width": 1.4, "depth": 0.6, "tint": 0.5, "shade": 0.15, "roll": None, "search": 3.0,
                 "res": 0.7, "about": "the vertical frown lines between the brows"},
}
# The folds' RELIEF as geometry, mm at amount 1 (x the side's amount along the path; "roll" x the fold's `roll`):
#   depth   the groove's depth (its width is the fold's `width`, full width at half depth)
#   roll    (peak offset toward plus, sigma, height, shoulder): the bulge beside the groove, rising from the groove's
#           own line over `shoulder` (a symmetric bump there half filled the groove: lidfold's finding)
#   plat    (depth, height): the skin on the minus side a little in over `height` (a lid's pretarsal platform)
#   reach   how far along the normal the move is felt (it never reaches through a lid or into a nostril)
RELIEF = {
    "nasolabial": {"depth": 0.6, "roll": (5.0, 3.4, 1.3, 3.0), "reach": 4.0},
    "marionette": {"depth": 0.5, "roll": (4.0, 2.6, 0.6, 2.5), "reach": 4.0},
    "mouth_corner": {"depth": 0.3, "reach": 3.0},
    "mentolabial": {"depth": 0.8, "reach": 4.0},
    "tear_trough": {"depth": 0.6, "roll": (4.6, 2.4, 1.4, 2.6), "reach": 4.0},
    "lid_fold": {"depth": 0.85, "roll": (2.3, 2.6, 0.6, 2.6), "plat": (0.15, 2.5), "reach": 3.0},
    "glabella": {"depth": 0.35, "reach": 3.0},
}
END = 0.004               # m: a fold's relief comes in from nothing over this length at each end of its extent
# With the relief in the surface, what a tight crease still lacks in a rasterised render is its own OCCLUSION (skin
# lying on skin: no light gets in; EEVEE has none at 0.5 mm): the crease line's share of a dark multiply layer
# (folds_crease), 0.6 x the groove's width. Without it a lid's crease at amount 1 was a faint line (foldval's truth
# pictures: read_lid darkness 0.05-0.13, a photograph's fold line reads 0.15-0.4).
OCCLUSION = {"lid_fold": 1.0, "nasolabial": 0.35, "marionette": 0.25, "mouth_corner": 0.4, "glabella": 0.45, "mentolabial": 0.0,
             "tear_trough": 0.0}
KEEP = (0.0012, 0.0032)   # m: no displacement within KEEP[0] of a lid margin or the lips, all of it from KEEP[1]
BALL = 0.0004             # m: the skin a fold pushes in stays this far outside the eyeball
STEP = 0.0005             # m between the geometry's samples along a path
KEYS = {"amount", "width", "roll", "depth", "L", "R", "shift", "extent"}
SIDE_KEYS = {"amount", "shift", "extent"}


def sided(name: str) -> bool:
    return any(a.endswith(".L") for a, _ in FOLDS[name]["path"])


def options(folds: dict | None) -> dict:
    """skin["folds"] validated: {name: {"amount", "width", "roll", "sides": {"L" | "R" | "": {"amount", "shift",
    "extent"}}}} (folds with amount 0 left out)."""
    out = {}
    if not folds:
        return out
    if not isinstance(folds, dict) or set(folds) - set(FOLDS):
        raise SpecError(f"skin folds: {{name: amount | {{...}}}} over {', '.join(FOLDS)}")
    for name, v in folds.items():
        v = {"amount": float(v)} if isinstance(v, (int, float)) else dict(v or {})
        if set(v) - KEYS:
            raise SpecError(f"skin folds.{name}: unknown keys {sorted(set(v) - KEYS)} (have {', '.join(sorted(KEYS))})")
        a = float(v.get("amount", 1.0))
        if not 0 <= a <= 1.5:
            raise SpecError(f"skin folds.{name}: amount is 0..1.5")
        if a <= 0:
            continue
        sides = {}
        for s in ((".L", ".R") if sided(name) else ("",)):
            q = v.get(s[1:]) if s else {k: v[k] for k in ("shift", "extent") if k in v}
            q = dict(q or {})
            if set(q) - SIDE_KEYS:
                raise SpecError(f"skin folds.{name}: a side takes amount, shift, extent")
            ext = [float(x) for x in q.get("extent", (0.0, 1.0))]
            if len(ext) != 2 or not 0 <= ext[0] < ext[1] <= 1:
                raise SpecError(f"skin folds.{name}: extent is [t0, t1] within 0..1")
            sides[s] = {"amount": float(np.clip(q.get("amount", 1.0), 0, 3)), "shift": [float(x) for x in q.get("shift", [])], "extent": ext}
        if not 0 <= float(v.get("roll", 1.0)) <= 3 or not 0 <= float(v.get("depth", 1.0)) <= 3:
            raise SpecError(f"skin folds.{name}: roll and depth are 0..3 (x the feature's own)")
        out[name] = {"amount": a, "width": float(v.get("width", FOLDS[name]["width"])), "roll": float(v.get("roll", 1.0)),
                     "depth": float(v.get("depth", 1.0)), "sides": sides}
    return out


def geometry_key(skin: dict) -> dict | None:
    """What of spec["skin"] shapes the surface (spec.geometry keeps it as spec["tissue"]): the folds that have an
    amount, unless the relief is painted. None: nothing (the fold-free model's build key)."""
    if (skin or {}).get("fold_relief", "geometry") != "geometry":
        return None
    try:
        cfg = options(skin.get("folds"))
    except (SpecError, TypeError, ValueError):
        return None        # (said by skin.params where the skin is validated)
    cfg = {k: v for k, v in cfg.items() if any(q["amount"] > 0 for q in v["sides"].values())}
    return {"folds": cfg, "part": skin.get("part", "body"), "v": VERSION} if cfg else None


class _Surface:
    """The head's skin under the map: a point for any direction from the wrap's centre (smooth: the mesh's radius
    interpolated), and the normal there."""

    def __init__(self, spec: dict, part: str, J: dict):
        from scipy.interpolate import LinearNDInterpolator
        from scipy.spatial import cKDTree
        from . import skin_marks as sm
        self.sp = sm.sphere(J, (-62.0, 72.0), 220.0, PX)
        V, Nn, _ = sm.head_mesh(spec, part, J)
        V, Nn = np.asarray(V, float), np.asarray(Nn, float)
        keep = sm.outward(self.sp, V, Nn, V)
        self.o = np.asarray(self.sp["fr"]["o"], float)
        self._R = LinearNDInterpolator(sm.pix(self.sp, V[keep]), np.linalg.norm(V[keep] - self.o, axis=1))
        self._tree, self._N, self.V, self.Nall, self._Vk = cKDTree(V[keep]), Nn[keep], V, Nn, V[keep]

    def seat(self, P: np.ndarray, snap: bool = False) -> np.ndarray:
        """Points moved along their ray from the wrap's centre onto the skin (left where the wrap does not see).
        snap: first to the nearest point of the skin (a landmark offset floats a few mm off it, and the ray from a centre
        at the mouth's height would carry a point by the eye several mm up the lid)."""
        from . import skin_marks as sm
        P = np.asarray(P, float)
        if snap:
            P = self._Vk[self._tree.query(P)[1]]
        d = P - self.o
        r = np.linalg.norm(d, axis=1)
        R = self._R(sm.pix(self.sp, P))
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


_SURF: dict = {}
_MAPSURF: dict = {}


def without(spec: dict) -> dict:
    """The spec with no folds (what their paths are seated on)."""
    if not (spec.get("skin") or {}).get("folds"):
        return spec
    return {**spec, "skin": {k: v for k, v in spec["skin"].items() if k != "folds"}}


def field_surface(prims: list, J: dict) -> _FieldSurface:
    from . import sdf
    key = hashlib.sha1(json.dumps([[sdf.fingerprint(p) for p in prims], [np.round(a, 6).tolist() for a in head_frame(J)]]).encode()).hexdigest()
    if key not in _SURF:
        if len(_SURF) > 3:
            _SURF.pop(next(iter(_SURF)))
        _SURF[key] = _FieldSurface(prims, J)
    return _SURF[key]


def surface(spec: dict, part: str, J: dict) -> _FieldSurface:
    """The skin part's fold-free field as a surface (`spec`: the model; its own folds are left out)."""
    from . import images
    return field_surface(images.prims_on(without(spec), [part]), J)


def map_surface(spec: dict, part: str, J: dict) -> _Surface:
    """The head's skin under the fold map (the mesh the map's pixels are laid on: with the folds' own relief)."""
    from . import skin_marks as sm
    V, _, _ = sm.head_mesh(spec, part, J)
    key = hashlib.sha1(json.dumps([np.asarray(V[:50]).round(5).tolist(), len(V)]).encode()).hexdigest()
    if key not in _MAPSURF:
        if len(_MAPSURF) > 3:
            _MAPSURF.pop(next(iter(_MAPSURF)))
        _MAPSURF[key] = _Surface(spec, part, J)
    return _MAPSURF[key]


def _resample(P: np.ndarray, step: float) -> np.ndarray:
    """A polyline as a smooth curve (Catmull-Rom) sampled every `step`."""
    P = np.asarray(P, float)
    if len(P) > 2:
        Q = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
        out = []
        for i in range(1, len(Q) - 2):
            for t in np.linspace(0, 1, 12, endpoint=False):
                p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
                out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
        P = np.array(out + [P[-1]])
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    n = max(int(round(s[-1] / step)) + 1, 4)
    t = np.linspace(0, s[-1], n)
    return np.stack([np.interp(t, s, P[:, k]) for k in range(3)], 1)


def paths(spec: dict | None, part: str, J: dict, cfg: dict | None = None, names=None, S=None) -> dict:
    """{(name, side): {"P": (m, 3) stations on the skin every STATION, "across": (m, 3) unit vectors in the skin
    toward the fold's plus side, "t": 0..1 along, "amount": (m,) (the side's amount, 0 outside its extent, eased at the
    ends), "width", "roll"}}. cfg = options(skin["folds"]): the measured shift is applied; None: the landmark paths
    themselves (what the reader measures from), amount 1."""
    from .skin import interocular
    io = interocular(J)
    S = S or surface(spec, part, J)
    out = {}
    for name in (names or (cfg if cfg is not None else FOLDS)):
        fd = FOLDS[name]
        o = (cfg or {}).get(name)
        for sd, sx in (((".L", 1.0), (".R", -1.0)) if sided(name) else (("", 1.0),)):
            try:
                # each control point is WALKED over the skin from its landmark (half-millimetre steps, re-seated): the
                # offset alone floats off the surface, and seating that along the wrap's ray (or onto the nearest
                # vertex) put a lid's fold several mm up the lid on one side and across the eye's corner on the other
                # (in the head's own frame; seated from the FRONT: the visible skin under the offset point. The first
                # version walked each point over a mesh from its landmark; on the exact field's closest point a lid's
                # landmark landed inside the lid and the tear trough ran round the socket)
                jn = lambda a: a[:-2] + sd if a.endswith(".L") else a  # noqa: E731
                # (a head with the 68 landmarks only has no lm_lid_*_in / _out: the path runs through the rest)
                cps = [(a, off) for a, off in fd["path"] if jn(a) in J or not a.split(".")[0].endswith(("_in", "_out"))]
                pl = np.array([np.asarray(J[jn(a)], float)
                               + io * (sx * off[0] * S.right - off[1] * S.front + off[2] * S.up) for a, off in cps])
                pl = S.seat(pl)
            except KeyError as err:
                raise SpecError(f"skin folds.{name}: needs joint {err.args[0]!r} (a GNM head's lm_* landmarks)")
            P = S.seat(_resample(pl, STATION))
            nrm = S.normal(P)
            tan = np.gradient(P, axis=0)
            tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-12)
            ac = np.cross(nrm, tan)
            ac /= np.maximum(np.linalg.norm(ac, axis=1, keepdims=True), 1e-12)
            plus = sx * fd["plus"][0] * S.right - fd["plus"][1] * S.front + fd["plus"][2] * S.up
            if float((ac @ plus).mean()) < 0:
                ac = -ac
            t = np.linspace(0, 1, len(P))
            amount = np.ones(len(P))
            if o is not None:
                q = o["sides"][sd]
                if q["shift"]:
                    sh = np.interp(t, np.linspace(0, 1, len(q["shift"])), q["shift"]) * 0.001
                    P = S.seat(P + sh[:, None] * ac)
                e0, e1 = q["extent"]
                amount = o["amount"] * q["amount"] * ((t >= e0) & (t <= e1))
            ease = np.clip(np.minimum(t - (o["sides"][sd]["extent"][0] if o else 0.0), (o["sides"][sd]["extent"][1] if o else 1.0) - t) / 0.18, 0, 1)
            amount = amount * (0.25 + 0.75 * np.sin(0.5 * np.pi * ease))   # a fold fades toward its ends
            out[(name, sd)] = {"P": P, "across": ac, "t": t, "amount": amount, "width": (o or fd)["width"],
                               "roll": (o["roll"] if o else 1.0), "depth": (o["depth"] if o else 1.0), "normal": S.normal(P)}
    return out


def fold_map(spec: dict, part: str, J: dict, cfg: dict) -> tuple[str, dict, dict]:
    """The fold map's file, the image dict's placement keys, stats. cfg = options(skin["folds"])."""
    from scipy.ndimage import gaussian_filter
    from scipy.spatial import cKDTree
    from . import skin_marks as sm, store
    S = map_surface(spec, part, J)
    sp = S.sp
    geo = geometry_key(spec.get("skin") or {}) is not None
    key = hashlib.sha1(json.dumps([cfg, geo, np.asarray(S.V[:50]).round(5).tolist(), len(S.V), sp["img"], VERSION, sm.VERSION, FOLDS],
                                  sort_keys=True, default=str).encode()).hexdigest()[:16]
    path = store.HOME / "_images" / f"mk_folds_{key}.png"
    stats_f = path.with_suffix(".json")
    if path.exists() and stats_f.exists():
        return str(path), sp["img"], json.loads(stats_f.read_text())
    W, H = sp["W"], sp["H"]
    out = np.zeros((H, W, 3), np.float32)
    ps = paths(spec, part, J, cfg)
    rows = sm._pixel_points(sp, S.V, S.Nall, step=2)
    stats = {"size": [W, H], "folds": {}}
    for (name, sd), q in ps.items():
        fd = FOLDS[name]
        if not (q["amount"] > 0).any():
            continue
        x = sm.pix(sp, q["P"])
        reach = 0.001 * (max(q["width"] * 1.5 * 2.5, (fd["roll"][0] + 1.5 * fd["roll"][1]) if fd["roll"] else 0.0) + 2.0)
        pad = int(reach / PX * 1.6) + 4
        x0, x1 = max(int(np.nanmin(x[:, 0])) - pad, 0), min(int(np.nanmax(x[:, 0])) + pad, W)
        y0, y1 = max(int(np.nanmin(x[:, 1])) - pad, 0), min(int(np.nanmax(x[:, 1])) + pad, H)
        if x1 <= x0 or y1 <= y0:
            continue
        Q, ok, _ = rows(y0, y1)
        Q = Q.reshape(y1 - y0, W, 3)[:, x0:x1].reshape(-1, 3)
        ok = ok.reshape(y1 - y0, W)[:, x0:x1].ravel()
        # (the distance to the LINE: its stations a millimetre apart, measured to the nearest, drew a lid's fold as dashes)
        tt = np.linspace(0, 1, 10 * (len(q["P"]) - 1) + 1)
        fine = lambda arr: np.stack([np.interp(tt, q["t"], arr[:, k_]) for k_ in range(arr.shape[1])], 1)  # noqa: E731
        Pf, Af, amf = fine(q["P"]), fine(q["across"]), np.interp(tt, q["t"], q["amount"])
        d, i = cKDTree(Pf).query(Q)
        s = ((Q - Pf[i]) * Af[i]).sum(1)
        a = amf[i] * ok
        sg = 0.001 * q["width"] / 2.355
        groove = a * fd["depth"] * np.exp(-0.5 * (d / sg) ** 2)
        shade = a * fd["shade"] * np.exp(-0.5 * (d / (2.6 * sg)) ** 2)
        tint = a * fd["tint"] * np.exp(-0.5 * (d / (0.8 * sg)) ** 2)
        roll = np.zeros_like(groove)
        if fd["roll"]:
            r0, rw, rk = fd["roll"]
            along = np.sqrt(np.maximum(d * d - s * s, 0.0))          # past the path's ends
            roll = a * rk * q["roll"] * np.exp(-0.5 * ((s - 0.001 * r0) / (0.001 * rw / 2.355)) ** 2) * np.exp(-0.5 * (along / (0.004)) ** 2)
        blk = out[y0:y1, x0:x1]
        shp = blk.shape[:2]
        # r: the groove's depth (x DEPTH); g: the roll (x BULGE); b: the darkening (crease line + soft shade, 0..1)
        if geo:   # r: the crease's occlusion instead of a painted groove
            groove = a * OCCLUSION[name] * np.exp(-0.5 * (d / (0.6 * sg)) ** 2)
        blk[..., 0] = np.maximum(blk[..., 0], (groove / 1.5).reshape(shp))
        blk[..., 1] = np.maximum(blk[..., 1], (roll / 1.5).reshape(shp))
        blk[..., 2] = np.maximum(blk[..., 2], np.clip(np.maximum(tint, shade), 0, 1).reshape(shp))
        stats["folds"][name + sd] = {"stations": int(len(q["P"])), "amount": round(float(q["amount"].max()), 3)}
    for k in range(3):
        out[..., k] = gaussian_filter(out[..., k], 1.0)
    sm._save(path, out)
    stats_f.write_text(json.dumps(stats))
    return str(path), sp["img"], stats


# ---------------------------------------------------------------- the folds as geometry

def profile(t: np.ndarray, pr: dict, j: np.ndarray) -> np.ndarray:
    """The skin's move along its normal (m, + = out) at signed distance t (m) across a fold's line (+ = its plus
    side), per sample j's parameters: the groove (G deep, sg wide), the roll (O high, peaking r0 out, so wide,
    rising from the line over sh), the platform on the minus side (Pl in, over ph)."""
    G, sg = pr["G"][j], pr["sg"][j]
    # (a fold with a roll is a STEP: steep under the roll, a long gentle wall on the other side; symmetric it read
    # as a channel cut with a gouge)
    out = -G * np.exp(-0.5 * (t / np.where(t < 0, sg * pr["lee"], sg)) ** 2)
    if pr["has_roll"]:
        ur = np.clip(t / pr["sh"], 0, 1)
        out = out + pr["O"][j] * ur * ur * (3 - 2 * ur) * np.exp(-0.5 * ((t - pr["r0"]) / pr["so"]) ** 2)
    if pr["has_plat"]:
        x = np.clip(-t / pr["ph"], 0, 1)
        out = out - pr["Pl"][j] * np.where(t < 0, np.sin(np.pi * x) ** 2, 0.0)
    return out


_KEEP_TREES: dict = {}


def _keep_tree(pr: dict):
    from scipy.spatial import cKDTree
    k = pr["keep_key"]
    if k not in _KEEP_TREES:
        if len(_KEEP_TREES) > 8:
            _KEEP_TREES.pop(next(iter(_KEEP_TREES)))
        _KEEP_TREES[k] = cKDTree(pr["keep"])
    return _KEEP_TREES[k]


def mod_tissue(cur: np.ndarray, p: np.ndarray, pr: dict, chunk: int = 4096) -> np.ndarray:
    """sdf's modifier "tissue": the field moved by `profile` of the distance across the fold's line. Smooth along the
    line (a normalised Gaussian over the nearest samples, as sdf.mod_fold); it fades over the line's ends (`taper`),
    past `reach` along the normal, toward the keep-out lines (lid margins, lips: `keep`), and where it pushes the
    skin IN it stops BALL outside each eyeball (`balls`: centre + radius)."""
    P, Nn, U, T = pr["pts"], pr["nrm"], pr["up"], pr["along"]
    flat = p.reshape(-1, 3)
    c0 = cur.reshape(-1)
    out = c0.copy()
    K, R, sa, H = pr["k"], pr["radius"], pr["sa"], pr["reach"]
    kt = _keep_tree(pr) if len(pr["keep"]) else None
    for s_ in range(0, len(flat), chunk):
        q = flat[s_:s_ + chunk].astype(np.float64)
        dist, idx = pr["tree"].query(q, k=K, distance_upper_bound=R)
        idx = idx.reshape(len(q), K)
        ok = idx < len(P)
        hit = ok.any(1)
        if not hit.any():
            continue
        q, ok, idx = q[hit], ok[hit], idx[hit]
        j = np.where(ok, idx, 0)
        r = q[:, None, :] - P[j]
        h = (r * Nn[j]).sum(-1)
        t = (r * U[j]).sum(-1)
        a = (r * T[j]).sum(-1)
        w = np.where(ok, np.exp(-0.5 * (a / sa) ** 2), 0.0)
        ws = w.sum(1)
        d = (w * profile(t, pr, j)).sum(1) / np.maximum(ws, 1e-12)
        tap = (w * pr["taper"][j]).sum(1) / np.maximum(ws, 1e-12)
        fade = np.clip(ws / (0.3 * pr["wfull"]), 0, 1) * tap
        hn = (w * np.abs(h)).sum(1) / np.maximum(ws, 1e-12)
        x = np.clip((hn - H) / H, 0, 1)
        fade = fade * (1 - x * x * (3 - 2 * x))
        if kt is not None:
            x = np.clip((kt.query(q)[0] - KEEP[0]) / (KEEP[1] - KEEP[0]), 0, 1)
            fade = fade * x * x * (3 - 2 * x)
        c = c0[s_:s_ + chunk][hit]
        new = c - d * fade
        for b in pr["balls"]:           # pushed in: never onto the eyeball
            sd = np.linalg.norm(q - b[:3], axis=1) - b[3] - BALL
            near = (new > c) & (sd < 0.006)
            new = np.where(near, np.minimum(new, np.maximum(c, sd)), new)
        o = out[s_:s_ + chunk]
        o[hit] = new
    return out.reshape(cur.shape)


def keep_lines(J: dict) -> np.ndarray:
    """(n, 3) points along what the folds' displacement keeps off: the lid margins (the opening's landmarks, a closed
    line per eye) and the lips (the vermilion's borders, the seam, and the lips' bodies between them)."""
    def dense(P, closed=False):
        P = np.asarray(P, float)
        if closed:
            P = np.r_[P, P[:1]]
        n = np.maximum(np.ceil(np.linalg.norm(np.diff(P, axis=0), axis=1) / 0.0005).astype(int), 1)
        return np.concatenate([P[i] + np.linspace(0, 1, k, endpoint=False)[:, None] * (P[i + 1] - P[i]) for i, k in enumerate(n)] + [P[-1:]])
    out = []
    for sd in (".L", ".R"):
        ring = [f"lm_eye_inner{sd}", f"lm_lid_upper_in{sd}", f"lm_lid_upper{sd}", f"lm_lid_upper_out{sd}", f"lm_eye_outer{sd}",
                f"lm_lid_lower_out{sd}", f"lm_lid_lower{sd}", f"lm_lid_lower_in{sd}"]
        ring = [J[k] for k in ring if k in J]
        if len(ring) >= 4:
            out.append(dense(ring, closed=True))
    rows = {}
    for tag in ("verm_u", "verm_iu", "verm_il", "verm_l"):
        ks = sorted(k for k in J if k.startswith(tag) and k[len(tag):].isdigit())
        if len(ks) >= 3:
            rows[tag] = np.array([J[k] for k in ks])
    for tag, Q in rows.items():
        out.append(dense(Q))
    for a, b in (("verm_u", "verm_iu"), ("verm_il", "verm_l")):      # the lips' bodies
        if a in rows and b in rows and len(rows[a]) == len(rows[b]):
            for f in (0.33, 0.67):
                out.append(dense((1 - f) * rows[a] + f * rows[b]))
    return np.concatenate(out) if out else np.zeros((0, 3))


def prims(s: dict, stream: list) -> list:
    """The folds' modifiers for an expanded geometry spec (spec._compile; s["tissue"] = geometry_key(skin)): one per
    fold and side with an amount, on the skin's part. `stream`: that part's primitives without them (what the paths
    are seated on: the same field the paint map and the reader seat theirs on)."""
    from scipy.ndimage import gaussian_filter1d
    from scipy.spatial import cKDTree
    from .spec import Prim
    tis = s.get("tissue") or {}
    cfg = tis.get("folds") or {}
    J = {k: np.asarray(v["pos"], float) for k, v in s["joints"].items() if "pos" in v}
    if not cfg or "lm_jaw_1.L" not in J:
        return []
    part = tis.get("part", "body")
    S = field_surface(stream, J)
    keep = keep_lines(J)
    kkey = hashlib.sha1(np.ascontiguousarray(keep).tobytes()).hexdigest()
    balls = np.zeros((0, 4))
    if s.get("base"):
        from . import base as basemod
        head = basemod.head_of(s, s["base"])
        if head is not None and head.get("eyes") is not None:
            balls = np.array([[*np.asarray(c, float), float(head["eye_r"])] for c in head["eyes"]])
    layer = max([p.layer for p in stream if p.op != "intersect"] or [0])
    out = []
    for (name, sd), q in paths(None, part, J, cfg, S=S).items():
        if not (q["amount"] > 0).any():
            continue
        rl = RELIEF[name]
        # the samples: the stations (1 mm) refined to STEP, normals and across smoothed along the line
        n = int(round((len(q["P"]) - 1) * STATION / STEP)) + 1
        tt = np.linspace(0, 1, n)
        fine = lambda arr: np.stack([np.interp(tt, q["t"], arr[:, k_]) for k_ in range(arr.shape[1])], 1)  # noqa: E731
        P = gaussian_filter1d(fine(q["P"]), 1.5, axis=0, mode="nearest")
        Nn = gaussian_filter1d(fine(q["normal"]), 4.0, axis=0, mode="nearest")
        Nn /= np.linalg.norm(Nn, axis=1, keepdims=True)
        T = np.gradient(P, axis=0)
        T -= (T * Nn).sum(1, keepdims=True) * Nn
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
        U = fine(q["across"])
        U -= (U * Nn).sum(1, keepdims=True) * Nn
        U -= (U * T).sum(1, keepdims=True) * T
        U /= np.maximum(np.linalg.norm(U, axis=1, keepdims=True), 1e-12)
        am = np.interp(tt, q["t"], q["amount"])
        on = np.flatnonzero(am > 0)
        e = np.clip(np.minimum(np.arange(n) - on[0], on[-1] - np.arange(n)) * STEP / END, 0, 1)
        am = am * e * e * e * (e * (6 * e - 15) + 10)       # (no visible start: cut ends read as knife marks)
        sp = float(np.median(np.linalg.norm(np.diff(P, axis=0), axis=1)))
        sa = 1.5 * sp
        G = am * rl["depth"] * q["depth"] * 0.001
        sg = np.full(n, 0.001 * q["width"] / 2.355)
        roll, plat = rl.get("roll"), rl.get("plat")
        # (the roll swells toward the fold's middle: a bag is a crescent, a cheek's pad fullest beside the nose's wing)
        er = np.clip(np.minimum(np.arange(n) - on[0], on[-1] - np.arange(n)) / max(0.3 * (on[-1] - on[0]), 1), 0, 1)
        O = am * er * er * (3 - 2 * er) * (roll[2] * q["roll"] * 0.001 if roll else 0.0)
        Pl = am * (plat[0] * 0.001 if plat else 0.0)
        so = 0.001 * roll[1] if roll else 0.001
        reach = 0.001 * rl["reach"]
        Rr = float(max((0.001 * roll[0] + 3 * so) if roll else 0.0, 3.5 * float(sg.max()) * (2.2 if roll else 1.0), (0.001 * plat[1]) if plat else 0.0, 3 * sa) + 0.001)
        params = {"pts": P, "nrm": Nn, "up": U, "along": T, "taper": np.ones(n), "sa": sa,
                  "wfull": float(np.sqrt(2 * np.pi) * sa / sp) * 0.98, "reach": reach, "G": G, "sg": sg, "O": O, "Pl": Pl,
                  "lee": 2.2 if roll else 1.0, "has_roll": bool(roll), "r0": 0.001 * roll[0] if roll else 0.0, "so": so, "sh": 0.001 * roll[3] if roll else 0.001,
                  "has_plat": bool(plat), "ph": 0.001 * plat[1] if plat else 0.001,
                  "keep": keep, "keep_key": kkey, "balls": balls, "radius": float(np.hypot(Rr, 2 * reach)),
                  "k": int(min(n, 2 * (3.5 * sa) / sp + 6)), "tree": cKDTree(P)}
        lo, hi = P.min(0) - Rr - reach, P.max(0) + Rr + reach
        gm, om = float(am.max()) * rl["depth"] * q["depth"] * 0.001, float(am.max()) * (roll[2] * q["roll"] * 0.001 if roll else 0.0)
        lip = 1.0 + 0.61 * gm / float(sg.min()) + 0.61 * om / min(so, params["sh"])
        out.append(Prim(f"fold_{name}{sd}", "tissue", "modify", 0.0, layer, lo, hi, params, lip=lip, part=part))
    return out


def build(spec: dict, p: dict, J: dict, layer, ctx: dict) -> None:
    """The folds' layers (skin_features.build calls this after the wrinkles): groove, roll, shade."""
    cfg = options(p.get("folds"))
    if not cfg or not ctx.get("face") or "lm_jaw_1.L" not in J:
        return
    path, place, _ = fold_map(spec, p["part"], J, cfg)
    im = lambda ch: {"image": {"file": path, **place, "channel": ch}}  # noqa: E731
    base_r = ctx["base_r"]
    # (map values are amount x share / 1.5: the layers' strengths carry the 1.5 back)
    # (no "levels" on the image: a post-processed mask is measured per vertex, and a lid's 1 mm line came out as dots)
    # (a shade, not a stain: near neutral. At [0.66, 0.53, 0.5] with the first tints a tear trough under a flat frontal
    # light, where painted relief hardly shades, read as a brown smudge under Garrett's eye)
    layer("folds_shade", color=[0.74, 0.66, 0.64], mix="multiply", opacity=1.0, mask=[im("b")])
    if geometry_key(spec.get("skin") or {}) is not None:
        # the relief is in the surface itself (prims): the map carries colour only: the shade, and the crease's occlusion
        # (the map holds amount x share / 1.5: full strength at amount 1.5)
        layer("folds_crease", color=[0.42, 0.3, 0.28], mix="multiply", opacity=1.0, mask=[im("r")])
        return
    layer("folds_groove", height=-round(DEPTH * 1.5, 7), roughness=min(base_r + 0.08, 0.95), opacity=0.6, mask=[im("r")])
    layer("folds_roll", height=round(BULGE * 1.5, 7), mask=[im("g")])


def reference() -> str:
    return "\n".join(["FOLDS (skin.folds: {name: amount | {amount, width mm, depth, roll, L / R: {amount, shift [mm..], extent [t0, t1]}}}; "
                      "GEOMETRY (a groove + roll in the surface itself) + their tint; skin_from_reference reads them off the references):"] +
                     [f"  {k:13s} {v['about']} (width {v['width']} mm, {RELIEF[k]['depth']} mm deep" + (f", a roll {RELIEF[k]['roll'][2]} mm high" if RELIEF[k].get("roll") else "") +
                      f"; readable from {v['res']} mm a pixel)" for k, v in FOLDS.items()])
