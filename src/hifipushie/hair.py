"""Hair as locks: Bezier curves swept with a lens profile, living in the Blender scene.

spec["hair"] = {
  "groom":  the designer's words and numbers; `groom()` grows the first pass of locks from them (hairline from the
            face landmarks, a parting, volume per region, flow per region, lock tiers). Parameters come first: change
            these and regrow before editing locks by hand.
  "locks":  {name: lock}: what the scene shows. Written by `groom()`, then edited by numbers or in Blender (pull
            brings moved control points, handles, radius, tilt and the modifier numbers back).
  "look":   the material: {"gap", "lit", "sheen", "grey" (sRGB hex), "roughness", "sheen_amount", "vary",
            "grooves" (strand ridges across a lock), "groove_depth", "anisotropic"}.
  "cap":    the dark underlayer on the scalp inside the hairline (m, default 0.002; 0 = none).
  "stage":  "mass" shows the groom's volume as one smooth shell (stage a: silhouette), else the locks.
  "part":   the export part (default "hair").
}
A lock: {"pts": [[az, el, h], ...], "width", "thickness", "cup", "taper", "belly", "root", "twist", "flip", "grey",
"radius"?: [per point], "tilt"?: [per point, radians], "handles"?: [[az, el, h, az, el, h] | null per point],
"tier"?: "big" | "fill" | "edge"}. Every point is an address on the head: azimuth in degrees round the head centre
(0 = the front, 90 = his left ear, 180 = the back), elevation in degrees up from the centre's level, and h metres
above the scalp along that ray (pts[0] is the root: h ~ 0). The centre comes from the face landmarks (between the
jaw tops, at the brows' height), so locks follow the head when it changes. Widths etc. in metres: width across the
lock at its widest (Belly: where along, 0..1), Root = the width at the scalp / the widest, Taper 1 = to a point,
Cup = how far the edges curl toward the head, Twist = degrees turned root to tip, Flip = degrees turned everywhere.

In Blender every lock is a curve object in the "hair" collection with the "hp_lock" Geometry Nodes modifier
(`blender_hair.py`): grab its control points and the mesh follows live.
"""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import time
from pathlib import Path

import numpy as np

from . import store



def under(g: dict, H, az, el, d_in):
    """The underlayer's height (m): the mass sunk by about one lock thickness (the big locks' on top, the fill's
    round the sides), so the locks lying on it make the silhouette (a fraction of the volume buried the big locks)."""
    W = weights(az, el, d_in)
    top = W[..., 0] + W[..., 1]
    tb = float((g["tiers"].get("big") or {}).get("thickness", 0.0))
    tf = max(float((g["tiers"].get("fill") or {}).get("thickness", 0.0)),
             float((g["tiers"].get("strip") or {}).get("thickness", 0.0)))
    # not sunk over the upper sides, where the top locks lie down onto the side mass (sunk there too, the mass left
    # a waist under the top locks: a divot at each temple in the front view)
    side = side_tuck(az, el, W)
    # the fill (sides, back) is relief on the mass, not its volume: sunk a whole fill thickness, the gaps between
    # fill locks showed the sunk mass and the sides pinched in under the top again
    tw = top * (1 - side)  # the top proper: sunk by the big locks; the sides (and the top where it lies down) by theirs
    depth = tw * tb * _ss(d_in / 0.006) + FILL_SINK * (1 - tw) * tf  # the front edge not sunk:
    # between the front row's roots the sunk mass read as black pits along the hairline
    return np.maximum(H - depth, np.minimum(H, 0.0015))



SIDE_TUCK = (0.25, 0.65)  # |lateral| of the head direction where a top lock starts / ends lying down on the side


def side_tuck(az, el, W=None):
    """0 on the crown, 1 over the upper sides: where a top lock lies down onto the side mass. (By elevation alone,
    sides and back, it did worse: the back's crown then stood proud of the tucked back.)"""
    fa = np.abs(((np.asarray(az, float) + 180) % 360) - 180)
    lat = np.abs(dirs(az, el)[..., 0])
    down = np.cos(np.radians(np.asarray(el, float))) * _ss((fa - 90) / 40)  # the back, turning down
    return _ss((np.maximum(lat, down) - SIDE_TUCK[0]) / (SIDE_TUCK[1] - SIDE_TUCK[0]))


TIP_STEP = 0.25  # how far a top lock's tip lifts off the lock under it, x its thickness
SIDE_NARROW = 0.35  # and how much narrower it gets there
FILL_SINK = 1.0  # how much of a fill lock's thickness the side/back mass sinks under it
REGIONS = ("front", "top", "sides", "back", "nape")
GROOM = {
    "hairline": {"front": 0.85, "temples": 0.008, "sideburns": 0.028, "nape": 0.0, "ear": 0.01},
    "parting": {"side": "left", "offset": 0.03, "length": 0.1},
    "volume": {"front": 0.045, "top": 0.036, "crown": 0.02, "sides": 0.012, "back": 0.013, "nape": 0.005},
    "length": {"front": 0.17, "top": 0.15, "sides": 0.055, "back": 0.06, "nape": 0.03},
    "flow": {"front": {"back": 1, "up": 0.3, "away": 0.6}, "top": {"back": 1, "away": 0.55},
             "sides": {"back": 1, "down": 0.45}, "back": {"down": 1}, "nape": {"down": 1}},
    "tiers": {"crown": {"width": 0.042, "thickness": 0.009, "spacing": 0.7, "where": ["top"]},
              "big": {"width": 0.05, "thickness": 0.011, "spacing": 0.6, "where": ["front", "top"],
                      "layout": "part", "front_away": 7, "front_part": 3, "root": 1.0, "part_row": 3, "front_span": 42},
              "fill": {"width": 0.026, "thickness": 0.007, "spacing": 0.8,
                       "where": ["sides", "back", "nape", "top"]},
              "gap": {"width": 0.026, "thickness": 0.004, "spacing": 0.8, "length": 0.05},
              "edge": {"width": 0.011, "thickness": 0.0028, "spacing": 0.9, "length": 0.022}},
    "grey": {"temples": 0.35, "sideburns": 0.5},
    "noise": 0.3,
    "seed": 0,
}
LOOK = {"gap": "#221310", "lit": "#56352d", "sheen": "#86524a", "grey": "#9a948d", "roughness": 0.42,
        "sheen_amount": 0.45, "vary": 0.25, "grooves": 5, "groove_depth": 0.12, "anisotropic": 0.7}
LOCK_KEYS = {"pts", "width", "thickness", "cup", "taper", "belly", "root", "twist", "flip", "grey", "radius", "tilt",
             "handles", "tier"}
MOD = {"width": "Width", "thickness": "Thickness", "cup": "Cup", "taper": "Taper", "belly": "Belly", "root": "Root",
       "twist": "Twist", "flip": "Flip", "grey": "Grey"}
LOCK_DEFAULTS = {"taper": 1.0, "belly": 0.3, "root": 0.6, "twist": 0.0, "flip": 0.0, "grey": 0.0, "cup": 0.002}
WORDS = {"back": (0, 1, 0), "forward": (0, -1, 0), "down": (0, 0, -1), "up": (0, 0, 1), "left": (1, 0, 0),
         "right": (-1, 0, 0), "away": None}


class HairError(ValueError):
    pass


def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def dirs(az, el):
    """Unit directions for azimuth / elevation in degrees (0 = front -Y, 90 = +X his left)."""
    a, e = np.radians(az), np.radians(el)
    return np.stack([np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e)], -1)


def az_el(v):
    u = _unit(np.asarray(v, float))
    return np.degrees(np.arctan2(u[..., 0], -u[..., 1])) % 360, np.degrees(np.arcsin(np.clip(u[..., 2], -1, 1)))


# ------------------------------------------------------------------------------------------------ the head

class Scalp:
    """The head as rays from its centre: r(az, el) = where the body's surface is (a 2 degree grid, cached per body
    geometry), plus the face landmarks."""
    STEP = 2.0
    EL = (-70.0, 90.0)

    def __init__(self, C, R, lm):
        self.C = np.asarray(C, float)
        self.R = R  # (180, n_el)
        self.lm = lm
        self.A = np.arange(0.0, 360.0, self.STEP)
        self.E = np.arange(self.EL[0], self.EL[1] + 1e-6, self.STEP)

    def r(self, az, el):
        az = np.asarray(az, float) % 360
        el = np.clip(np.asarray(el, float), self.EL[0], self.EL[1])
        fa, fe = az / self.STEP, (el - self.EL[0]) / self.STEP
        ia, ie = np.floor(fa).astype(int), np.minimum(np.floor(fe).astype(int), len(self.E) - 2)
        ta, te = fa - ia, fe - ie
        ia0, ia1 = ia % len(self.A), (ia + 1) % len(self.A)
        R = self.R
        return ((1 - ta) * (1 - te) * R[ia0, ie] + ta * (1 - te) * R[ia1, ie] + (1 - ta) * te * R[ia0, ie + 1]
                + ta * te * R[ia1, ie + 1])

    def point(self, az, el, h):
        return self.C + (self.r(az, el) + np.asarray(h, float))[..., None] * dirs(az, el)

    def coords(self, P):
        """(az, el, h) of world points."""
        Q = np.asarray(P, float) - self.C
        az, el = az_el(Q)
        return az, el, np.linalg.norm(Q, axis=-1) - self.r(az, el)

    def normal(self, az, el, d=1.0):
        """The scalp's outward normal (finite differences on the grid)."""
        p = self.point(az, el, 0.0)
        ea = self.point(az + d, el, 0.0) - self.point(az - d, el, 0.0)
        ee = self.point(az, el + d, 0.0) - self.point(az, el - d, 0.0)
        n = _unit(np.cross(ea, ee))
        out = _unit(p - self.C)
        return np.where((n * out).sum(-1, keepdims=True) < 0, -n, n)


def _geometry_key(spec: dict) -> str:
    from .spec import geometry
    g = {k: v for k, v in geometry(spec).items() if k != "hair"}
    return hashlib.sha1(json.dumps(g, sort_keys=True, default=float).encode()).hexdigest()[:16]


_SCALPS: dict = {}


def scalp(name: str, spec: dict | None = None) -> Scalp:
    """The model's Scalp (cached in memory and on disk by the body's geometry: hair edits never recompute it)."""
    spec = store.load(name) if spec is None else spec
    key = _geometry_key(spec)
    if key in _SCALPS:
        return _SCALPS[key]
    f = store._dir(name) / f"hair_scalp_{key}.npz"
    if f.exists():
        z = np.load(f, allow_pickle=False)
        sc = Scalp(z["C"], z["R"], json.loads(str(z["lm"])))
    else:
        sc = _measure(spec)
        for old in store._dir(name).glob("hair_scalp_*.npz"):
            old.unlink()
        np.savez(f, C=sc.C, R=sc.R, lm=json.dumps(sc.lm))
    _SCALPS[key] = sc
    return sc


def _measure(spec: dict) -> Scalp:
    from . import sdf
    from .spec import compile_prims, expand_mirror, geometry
    g = {k: v for k, v in geometry(spec).items() if k != "hair"}
    J = expand_mirror(g)["joints"]
    need = ("lm_brow_mid.L", "lm_nose_base", "lm_jaw_0.L", "lm_brow_outer.L", "lm_nose_bridge")
    if not all(n in J for n in need):
        raise HairError(f"hair needs the face landmarks {need} (a base head gives them)")
    lm = {n: [float(x) for x in J[n]["pos"]] for n in J if n.startswith("lm_")}
    j0 = np.array(lm["lm_jaw_0.L"])
    C = np.array([0.0, j0[1] + 0.01, lm["lm_brow_mid.L"][2] + 0.008])
    streams = {ps[0].part: ps for ps in sdf.streams(compile_prims(g))}
    body = streams["body"]
    sc = Scalp(C, None, lm)
    AA, EE = np.meshgrid(sc.A, sc.E, indexing="ij")
    U = dirs(AA.ravel(), EE.ravel())
    ts = np.arange(0.02, 0.26, 0.003)
    F = sdf.field_at(body, (C + ts[None, :, None] * U[:, None, :]).reshape(-1, 3)).reshape(len(U), len(ts))
    if np.any(F[:, 0] >= 0):
        raise HairError(f"hair: the head centre {np.round(C, 3).tolist()} isn't inside the head")
    out = F >= 0
    i = np.argmax(out, 1)
    miss = ~out.any(1)
    lo, hi = ts[np.maximum(i - 1, 0)], ts[i]
    for _ in range(10):
        mid = (lo + hi) / 2
        fm = sdf.field_at(body, C + mid[:, None] * U)
        lo, hi = np.where(fm < 0, mid, lo), np.where(fm < 0, hi, mid)
    r = np.where(miss, ts[-1], hi)
    sc.R = r.reshape(AA.shape)
    return sc


# ------------------------------------------------------------------------------------------------ the groom

def _merge(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return {**a, **{k: _merge(a.get(k), v) for k, v in b.items()}}
    return copy.deepcopy(b) if b is not None else copy.deepcopy(a)


def groom_params(spec: dict) -> dict:
    g = (spec.get("hair") or {}).get("groom") or {}
    bad = set(g) - set(GROOM)
    if bad:
        raise HairError(f"hair groom: unknown keys {sorted(bad)} (have {', '.join(sorted(GROOM))})")
    return _merge(GROOM, g)


def hairline(sc: Scalp, g: dict) -> np.ndarray:
    """The hairline's elevation (degrees) at each whole degree of azimuth (360,), symmetric left/right: from the
    landmarks (front height in brow-to-nose units, temples receding, sideburns, clear of the ears, the nape)."""
    hl = g["hairline"]
    if hl.get("points"):
        ctrl = [(float(a), float(z)) for a, z in hl["points"]]
    else:
        lm = sc.lm
        bz = lm["lm_brow_mid.L"][2]
        fore = bz - lm["lm_nose_base"][2]
        zf = bz + float(hl.get("front", 0.9)) * fore
        tmp = float(hl.get("temples", 0.012))
        j0 = np.array(lm["lm_jaw_0.L"]) - sc.C
        az_j = float(np.degrees(np.arctan2(j0[0], -j0[1])))
        ear_top = lm["lm_brow_outer.L"][2] + 0.004
        ear_bot = lm["lm_nose_base"][2] - 0.01
        clear = float(hl.get("ear", 0.01))
        sb = ear_top - float(hl.get("sideburns", 0.028))
        nape = ear_bot - 0.015 + float(hl.get("nape", 0.0))
        ctrl = [(0, zf), (18, zf - 0.002), (az_j - 44, zf - 0.004 + tmp * 0.5), (az_j - 36, zf - 0.006 + tmp),
                (az_j - 28, zf - float(hl.get("temple_dip", 0.02)) + tmp), (az_j - 18, ear_top + 0.012), (az_j - 10, sb + 0.006),
                (az_j - 7, sb), (az_j - 3, sb + 0.006), (az_j + 3, ear_top + clear),
                (az_j + 22, ear_top + clear), (az_j + 34, ear_bot + 0.006), (150, nape + 0.006), (180, nape)]
    # z -> elevation on the scalp, per control's azimuth (the column's first height reaching z, from the bottom)
    A, E = [], []
    for a, z in ctrl:
        el = np.arange(-60.0, 89.0, 0.25)
        zz = sc.point(np.full(len(el), a), el, 0.0)[:, 2]
        k = int(np.argmax(zz >= z)) if np.any(zz >= z) else len(el) - 1
        A.append(a)
        E.append(el[k])
    from scipy.interpolate import PchipInterpolator
    a = np.array(A, float)
    e = np.array(E, float)
    AA = np.r_[-a[::-1][:-1], a, 360 - a[::-1][1:]]
    EE = np.r_[e[::-1][:-1], e, e[::-1][1:]]
    AA, idx = np.unique(AA, return_index=True)
    return PchipInterpolator(AA, EE[idx])(np.arange(360.0))


def _line_at(line, az):
    f = np.asarray(az, float) % 360
    i0 = np.floor(f).astype(int) % 360
    return line[i0] + (f - np.floor(f)) * (line[(i0 + 1) % 360] - line[i0])


def inside(sc: Scalp, line, az, el):
    """Signed distance (m) inside the hairline over the scalp (> 0 in the hair): the distance to the hairline curve
    (along the elevation alone, the steep run from temple to sideburn measured long and creased the mass)."""
    from scipy.spatial import cKDTree
    key = (id(sc), float(np.sum(line)))
    tree = _LINES.get(key)
    if tree is None:
        a = np.arange(0.0, 360.0, 0.1)
        e = _line_at(line, a)
        L = sc.point(a, e, 0.0)
        # densify steep stretches: consecutive points closer than 1 mm
        seg = np.linalg.norm(np.diff(L, axis=0, append=L[:1]), axis=1)
        extra = [L]
        for i in np.nonzero(seg > 0.001)[0]:
            n = int(seg[i] / 0.001) + 1
            t = np.linspace(0, 1, n + 1)[1:-1]
            a1 = a[i] + 0.1 * t
            e1 = e[i] + (e[(i + 1) % len(e)] - e[i]) * t
            extra.append(sc.point(a1, e1, 0.0))
        tree = cKDTree(np.concatenate(extra))
        if len(_LINES) > 8:
            _LINES.clear()
        _LINES[key] = tree
    az, el = np.asarray(az, float), np.asarray(el, float)
    d, _ = tree.query(sc.point(az, el, 0.0).reshape(-1, 3))
    d = d.reshape(az.shape)
    return np.where(el >= _line_at(line, az), d, -d)


_LINES: dict = {}


def weights(az, el, d_in):
    """Region weights (n, 5) in REGIONS order from where a point sits: front = the first few cm behind the front
    hairline, top above ~30 deg, sides round the ears, back behind, nape low at the back."""
    fa = np.abs(((np.asarray(az) + 180) % 360) - 180)  # 0 front .. 180 back
    front = (1 - _ss((d_in - 0.02) / 0.03)) * (1 - _ss((fa - 30) / 25))
    top = _ss((np.asarray(el) - 22) / 20)
    back = _ss((fa - 105) / 40)
    nape = _ss((-np.asarray(el) + 0) / 20)
    rest = (1 - front) * (1 - top)
    W = np.stack([front, (1 - front) * top, rest * (1 - back), rest * back * (1 - nape), rest * back * nape], -1)
    return W / np.maximum(W.sum(-1, keepdims=True), 1e-9)


def _region(g: dict, key: str, W):
    v = g[key]
    vals = np.array([float(v[r]) for r in REGIONS])
    return W @ vals


def envelope(sc: Scalp, g: dict, line, az, el):
    """The hair's outer surface height above the scalp (m): `_envelope` made convex round the sides (`_fill`)."""
    H, d_in = _envelope(sc, g, line, az, el)
    return np.maximum(H, _fill(sc, g, line)(az, el) * (d_in > 0)), d_in


_FILLS: dict = {}


def _fill(sc: Scalp, g: dict, line):
    """Per azimuth round the sides, the hair's profile (in the vertical plane through the centre) filled out to its
    convex hull: where the full top meets the close sides the outline pinched in above the temples (a waist in the
    front view). Returns an interpolator (az, el) -> the height the hull asks for (0 where nothing is filled)."""
    from scipy.interpolate import RegularGridInterpolator
    from scipy.spatial import ConvexHull
    key = (id(sc), json.dumps(g, sort_keys=True, default=float), float(np.sum(line)))
    if key in _FILLS:
        return _FILLS[key]
    A = np.arange(0.0, 361.0, 2.0)
    E = np.arange(-60.0, 90.01, 1.0)
    out = np.zeros((len(A), len(E)))
    for i, a in enumerate(A):
        fa = abs(((a + 180) % 360) - 180)
        w = _ss((fa - 25) / 15) * (1 - _ss((fa - 140) / 20))  # the sides the front and 3/4 views outline
        if w <= 0:
            continue
        aa = np.full(len(E), a)
        H, d_in = _envelope(sc, g, line, aa, E)
        hair = d_in > 0
        if hair.sum() < 3:
            continue
        rho = sc.r(aa, E) + H
        e = np.radians(E)
        pts = np.stack([rho * np.cos(e), rho * np.sin(e)], 1)[hair]
        pts = np.vstack([pts, [0.0, 0.0]])
        hull = ConvexHull(pts)
        # the hull's radius along each hair ray: the nearest facet the ray leaves through
        u = np.stack([np.cos(e), np.sin(e)], 1)
        best = np.full(len(E), np.inf)
        for eq in hull.equations:  # n.x + c <= 0 inside
            nd = u @ eq[:2]
            t = np.where(nd > 1e-9, -eq[2] / np.maximum(nd, 1e-12), np.inf)
            best = np.minimum(best, t)
        need = np.where(hair & np.isfinite(best), best - sc.r(aa, E), 0.0)
        out[i] = np.maximum(need - H, 0.0) * w + H * (need > H) * w
    fill = RegularGridInterpolator((A, E), out, bounds_error=False, fill_value=0.0)

    def f(az, el):
        az, el = np.asarray(az, float), np.asarray(el, float)
        return fill(np.stack([az % 360, np.clip(el, -60, 90)], -1).reshape(-1, 2)).reshape(np.shape(az))
    if len(_FILLS) > 8:
        _FILLS.clear()
    _FILLS[key] = f
    return f


def _envelope(sc: Scalp, g: dict, line, az, el):
    """The hair's outer surface height above the scalp (m). On top a dome: highest a few cm behind the front hairline
    (volume "front"), falling smoothly to "crown" at the back of the top; the front edge rounds up off the hairline
    like a bull nose (no square wall); the side of the parting the hair is combed away from (his right, for a left
    part) carries more than the other; sides, back and nape their own volume with a short clean ramp."""
    d_in = inside(sc, line, az, el)
    W = weights(az, el, d_in)
    vol = g["volume"]
    fa = np.abs(((np.asarray(az) + 180) % 360) - 180)
    P = sc.point(az, el, 0.0)
    # the top's dome, by distance back from the front hairline (m)
    vf, vt, vc = float(vol["front"]), float(vol["top"]), float(vol["crown"])
    back = np.clip(d_in, 0, None)
    dome = vc + (vf - vc) * np.exp(-((back - 0.03) / 0.075) ** 2)
    dome = np.where(back < 0.03, vf, dome)
    dome = np.minimum(dome, vt + (vf - vt) * (1 - _ss((back - 0.02) / 0.05))) if vt < vf else dome
    # rounded across as well: the dome's height falls off toward the sides, so the front view is a curve over the top
    # and the sides stay close (a dome as full at its edges as on the crest made square shoulders and a bucket back)
    vs = float(vol["sides"])
    dome = vs + (dome - vs) * (1 - 0.65 * _ss((np.abs(P[..., 0]) - 0.02) / 0.06))
    topw = W[..., 0] + W[..., 1]
    side = W[..., 2] * float(vol["sides"]) + W[..., 3] * float(vol["back"]) + W[..., 4] * float(vol["nape"])
    v = topw * dome + side
    xp = _part_x(g)
    if xp is not None:  # the combed-away side is fuller; the part side lies flatter
        sgn = 1.0 if xp >= 0 else -1.0
        v = v * (1 - 0.22 * topw * _ss(sgn * (P[..., 0] - xp) / 0.03))
        v = v * (1 - 0.12 * _part(sc, g, az, el, 0.02) * (1 - _ss((back - 0.02) / 0.03)))
    ramp = topw * 0.028 + (1 - topw) * (0.8 * v + 0.002)  # continuous: a switch creased the temples
    x = np.clip(d_in / ramp, 0, 1)
    return v * np.sin(0.5 * np.pi * x) ** 0.8, d_in


def _part(sc: Scalp, g: dict, az, el, width):
    """How much a scalp point is in the parting (0..1) within `width` m of its line."""
    pt = g["parting"]
    side = pt.get("side", "left")
    if side == "none":
        return np.zeros(np.shape(az))
    xp = {"left": 1.0, "right": -1.0, "centre": 0.0}[side] * float(pt.get("offset", 0.03))
    P = sc.point(az, el, 0.0)
    yf = sc.C[1] - sc.r(0.0, 30.0) * np.cos(np.radians(30.0))
    along = _ss((P[..., 1] - yf + 0.005) / 0.01) * (1 - _ss((P[..., 1] - yf - float(pt.get("length", 0.1))) / 0.02))
    return along * np.exp(-((P[..., 0] - xp) / width) ** 2) * _ss((np.asarray(el) - 20) / 10)


def _part_x(g):
    pt = g["parting"]
    side = pt.get("side", "left")
    return None if side == "none" else {"left": 1.0, "right": -1.0, "centre": 0.0}[side] * float(pt.get("offset", 0.03))


def flow(sc: Scalp, g: dict, P, W, away):
    """The combing direction at points P (tangent to the scalp), from the regions' direction words."""
    fl = g["flow"]
    out = np.zeros(P.shape)
    for ri, r in enumerate(REGIONS):
        words = fl.get(r) or {}
        if isinstance(words, str):
            words = {words: 1.0}
        v = np.zeros(P.shape)
        for wd, amt in words.items():
            if wd not in WORDS:
                raise HairError(f"hair flow {r}: unknown direction {wd!r} (have {', '.join(WORDS)})")
            vec = away[..., None] * np.array([1.0, 0, 0]) if wd == "away" else np.array(WORDS[wd], float)
            v = v + float(amt) * vec
        out += W[..., ri:ri + 1] * v
    n = _unit(P - sc.C)
    t = out - (out * n).sum(-1, keepdims=True) * n
    return t


def _poisson(sc: Scalp, rng, spacing_at, ok, n_try=6000):
    """Blue-noise roots (az, el) over the scalp where ok(az, el), at least spacing_at(az, el) apart (dart throwing)."""
    U = _unit(rng.normal(size=(n_try, 3)))
    az, el = az_el(U)
    keep = ok(az, el)
    az, el = az[keep], el[keep]
    P = sc.point(az, el, 0.0)
    sp = spacing_at(az, el)
    chosen, pts = [], np.zeros((0, 3))
    for i in rng.permutation(len(az)):
        if len(pts) and np.any(np.linalg.norm(pts - P[i], axis=1) < 0.5 * (sp[i] + sp[chosen])):
            continue
        chosen.append(i)
        pts = np.vstack([pts, P[i]])
    return az[chosen], el[chosen]


def grow(sc: Scalp, g: dict) -> dict:
    """The first pass of locks from the groom: {name: lock}."""
    rng = np.random.default_rng(int(g.get("seed", 0)))
    noise = float(g.get("noise", 0.3))
    line = hairline(sc, g)
    xp = _part_x(g)
    locks = {}
    tiers = g["tiers"]
    names = {"big": "b", "crown": "c", "fill": "f", "edge": "e", "gap": "g"}
    if tiers.get("strip"):
        locks.update(_strips(sc, g, line, tiers["strip"], rng))
    for tier in ("big", "crown", "fill", "edge", "gap", "gap"):  # gaps twice: a second look at what's still bare
        td = tiers.get(tier)
        if not td:
            continue
        kind = {"crown": "big", "gap": "fill"}.get(tier, tier)  # crown: big locks laid by spacing; gap: fill locks
        if tier == "gap":
            names["gap"] = "g" if not any(n.startswith("g") for n in locks) else "h"
        w0, t0 = float(td["width"]), float(td["thickness"])
        sp0 = w0 * float(td.get("spacing", 0.8))
        where = [REGIONS.index(r) for r in td.get("where", REGIONS)]
        if tier == "edge":  # along the hairline, just inside it, where it's seen: temples, sideburns, the nape
            az_all = np.arange(0.0, 360.0, 0.5)
            el_all = _line_at(line, az_all) + np.degrees(0.004 / sc.r(az_all, _line_at(line, az_all)))
            P = sc.point(az_all, el_all, 0.0)
            arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
            at = np.arange(0.5 * sp0, arc[-1], sp0)
            at = at + rng.uniform(-0.2, 0.2, len(at)) * sp0
            az = np.interp(at, arc, az_all)
            el = np.interp(at, arc, el_all)
            fa = np.abs(((az + 180) % 360) - 180)
            keep = (fa > 40) & (fa < 115)  # temples and sideburns: not the crisp front line, not the nape
            az, el = az[keep], el[keep]
        elif tier == "gap":  # the artist's pass over what's still bare: roots where no lock covers the volume
            az, el = _gap_roots(sc, g, line, locks, td, rng)
        elif tier == "big" and td.get("layout", "part") == "part" and xp is not None:
            az, el, away_given = _part_roots(sc, g, line, td, xp, rng)
        else:
            def ok(a, e, where=where):
                d = inside(sc, line, a, e)
                W = weights(a, e, d)
                good = (d > (0.006 if kind == "big" else 0.004)) & (W[:, where].sum(1) > 0.5)
                if xp is not None:
                    good &= _part(sc, g, a, e, 0.006) < 0.5
                return good
            az, el = _poisson(sc, rng, lambda a, e: np.full(len(a), sp0), ok)
        if not len(az):
            continue
        if not (tier == "big" and td.get("layout", "part") == "part" and xp is not None):
            away_given = None
        d_in = inside(sc, line, az, el)
        W = weights(az, el, d_in)
        P0 = sc.point(az, el, 0.0)
        away = np.ones(len(az)) if xp is None else np.where(P0[:, 0] >= xp, 1.0, -1.0)
        if xp is None:
            away = np.sign(P0[:, 0] + 1e-9)
        if away_given is not None:
            away = away_given
        if tier == "crown" and xp is not None:  # the whole top sweeps one way, away from the part (each lock choosing
            away = np.full(len(az), -np.sign(xp) or -1.0)  # its side of the part turned the crown into a jumble)
        L = float(td["length"]) * np.ones(len(az)) if td.get("length") else _region(g, "length", W)
        if away_given is not None:  # the short side of a side part: brushed down toward the ear, not over it
            L = np.where(away_given == np.sign(_part_x(g) or 1.0), L * float(td.get("part_side_length", 0.55)), L)
        L = L * (1 + noise * 0.25 * rng.uniform(-1, 1, len(az)))
        if tier == "fill":  # shorter near the hairline: the edge tapers cleanly
            L *= 0.5 + 0.5 * _ss(d_in / 0.02)
        size = 1 + noise * 0.25 * rng.uniform(-1, 1, len(az))
        W_ = w0 * size
        T_ = t0 * size
        if away_given is not None:  # the part side's locks are the short, flat, narrower ones
            ps = away_given == np.sign(_part_x(g) or 1.0)
            W_ = np.where(ps, W_ * 0.75, W_)
            T_ = np.where(ps, T_ * 0.6, T_)
            nr = int(td.get("part_row", 3))  # the row down the parting (last): narrower, lying on the crown's
            if nr:  # curve (full width, their flat edges overhung the dome in the 3/4 view)
                W_[-nr:] *= float(td.get("part_row_width", 0.7))
        # the front row lies over the ones behind it (their roots under its body)
        # what lies on what: a lock covers the roots of those downstream of it (the front row over the top, higher
        # roots over lower ones on the sides and back), consistently, or overlaps cross in a jumble
        rank = 1 - _ss(d_in / 0.08) if kind == "big" else _ss((el + 40) / 120)
        lift = T_ * (0.25 * rank + 0.08 * rng.uniform(-1, 1, len(az))) if tier == "big" else np.zeros(len(az))  # crown, fill: flush
        flat = (away_given == np.sign(_part_x(g) or 1.0)).astype(float) if away_given is not None else None
        if flat is not None:  # the part side's locks lie flat: no lift, no tip step
            lift = lift * (1 - flat)
        paths, sides = _walk(sc, g, line, az, el, L, T_, lift, away, rng, kind, flat=flat)
        for i in range(len(az)):
            path, sfi = paths[i], sides[i]
            if tier != "edge":  # a lock ends inside the hairline (tips standing out over the skin read as a fringe)
                pa, pe, _ = sc.coords(path)
                din = inside(sc, line, pa, pe)
                out = np.nonzero(din < float(td.get("tip_inset", 0.006)))[0]
                out = out[out > 2]
                if len(out):
                    j = int(out[0])
                    c = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(path[:j + 1], axis=0), axis=1))]
                    if c[-1] < 0.35 * L[i]:
                        continue  # too little room: the underlayer carries it
                    t = np.linspace(0, c[-1], len(path))
                    path = np.stack([np.interp(t, c, path[:j + 1, q]) for q in range(3)], 1)
                    sfi = np.interp(t, c, sfi[:j + 1])
                    Li = c[-1]
                else:
                    Li = L[i]
            else:
                Li = L[i]
            k = 5 if Li > 0.08 else (4 if Li > 0.035 else 3)
            idx = np.round(np.linspace(0, len(path) - 1, k)).astype(int)
            a_, e_, h_ = sc.coords(path[idx])
            if tier != "edge":  # the tip tucks into the layer under it (a shortened lock ended in the air)
                Ht, dt = envelope(sc, g, line, a_[-1:], e_[-1:])
                h_[-1] = min(float(h_[-1]), float(under(g, Ht, a_[-1:], e_[-1:], dt)[0]) + 0.1 * float(T_[i]))
            grey = _grey(g, az[i], el[i], line)
            rad = 1 - SIDE_NARROW * sfi[idx]
            tilt = lie_tilt(sc, g, line, _catmull(path[idx], 4 * k)[::4] if k > 1 else path[idx])
            locks[f"{names[tier]}{i:02d}"] = {
                "tier": tier,
                **({"radius": [round(float(v), 3) for v in rad]} if np.any(rad < 0.999) else {}),
                "tilt": [round(float(v), 3) for v in tilt],
                "pts": [[round(float(a_[j]), 2), round(float(e_[j]), 2), round(float(h_[j]), 4)] for j in range(k)],
                "width": round(float(W_[i]), 4), "thickness": round(float(T_[i]), 4),
                "cup": round(float(td["cup"]) * float(size[i]) if "cup" in td else lie_cup(sc, float(W_[i]), path), 4),
                "taper": float(td.get("taper", 1.0)), "belly": round(float(td.get("belly", 0.16) + 0.06 * rng.uniform(-1, 1)), 3),
                "root": float(td.get("root", 0.8)),
                "twist": round(float(rng.uniform(-15, 15) * noise), 1) if tier in ("fill", "edge") else 0.0,
                **({"grey": round(grey, 3)} if grey > 0.01 else {})}
    return locks


def _nape_frame(sc: Scalp):
    """Short back and sides are combed back and down toward the nape: flow lines are the head's sections through a
    point under the nape (N) and an axis from it toward the forehead. Returns N, axis, e1, e2."""
    N = sc.C + np.array([0.0, 0.06, -0.13])
    axis = _unit(np.array([0.0, -0.9, 0.45]))
    e1 = _unit(np.cross(axis, [1.0, 0, 0]))
    return N, axis, e1, np.cross(axis, e1)


def stream_angle(sc: Scalp, P):
    """Each point's flow line: its angle round the nape axis (radians; constant along a combed-back stream)."""
    N, axis, e1, e2 = _nape_frame(sc)
    Q = np.asarray(P, float) - N
    t = Q - (Q @ axis)[..., None] * axis
    return np.arctan2(t @ e2, t @ e1)


def _strips(sc: Scalp, g: dict, line, td: dict, rng) -> dict:
    """The sides and back as long flat locks laid side by side along the combed streams (tier "strip"): each runs
    from under the top's locks (its root hidden by them) down the stream to just inside the hairline, flush with the
    groom's volume, overlapping its neighbours a little, narrowing as the streams converge on the nape. So the whole
    head is locks with one flow: no mass surface shows, and the outline stays the volume's (the fill tier's short
    locks either broke it or read as scales)."""
    N = _nape_frame(sc)[0]
    w0, t0 = float(td.get("width", 0.03)), float(td.get("thickness", 0.003))
    over = float(td.get("overlap", 1.2))
    top_start = float(td.get("start", 0.55))  # the top-region weight where a strip's root sits (under the top locks)
    inset = float(td.get("tip_inset", 0.004))
    A, E = np.meshgrid(np.arange(0.0, 360.0, 0.5), np.arange(-60.0, 89.0, 0.5), indexing="ij")
    A, E = A.ravel(), E.ravel()
    d_in = inside(sc, line, A, E)
    hair_m = d_in > inset
    A, E, d_in = A[hair_m], E[hair_m], d_in[hair_m]
    W = weights(A, E, d_in)
    topw = W[:, 0] + W[:, 1]
    P = sc.point(A, E, 0.0)
    ang = stream_angle(sc, P)
    dist = np.linalg.norm(P - N, axis=1)
    # the strips' start line: where the top gives way to the sides; spacing along it = the strip width
    band = np.abs(topw - top_start) < 0.08
    d_ref = float(np.median(dist[band])) if band.any() else float(np.median(dist))
    step = w0 / over / d_ref
    lo, hi = np.percentile(ang[topw < 0.9], [0.5, 99.5])
    angs = np.arange(lo + 0.5 * step, hi, step)
    angs = angs + rng.uniform(-0.15, 0.15, len(angs)) * step
    out = {}
    noise = float(g.get("noise", 0.3))
    for k, a0 in enumerate(angs):
        m = np.abs(ang - a0) < 0.35 * step
        if m.sum() < 8:
            continue
        dm, tm, Am, Em = dist[m], topw[m], A[m], E[m]
        # from the start (the farthest point from N still at top weight >= start, else the farthest) to the end
        # (the nearest to N: the hairline)
        cand = tm <= top_start + 0.1
        if not cand.any():
            continue
        d_start = dm[cand].max()
        d_end = dm.min()
        if d_start - d_end < 0.03:
            continue
        # the spine: points binned by distance to N (5 mm), their mean direction from the head centre
        bins = np.arange(d_start, d_end - 1e-6, -0.005)
        U = sc.point(Am, Em, 0.0)
        # the spine: per 5 mm of distance to N, the band's point nearest the last one (a band can hold two stretches,
        # above and behind the ear: their mean ran the strip across the ear)
        spine = []
        cur = U[cand][np.argmax(dm[cand])]
        for b in bins:
            q = np.nonzero(np.abs(dm - b) < 0.004)[0]
            if not len(q):
                continue
            j = q[np.argmin(np.linalg.norm(U[q] - cur, axis=1))]
            if np.linalg.norm(U[j] - cur) > 0.03:
                break  # the stream leaves the hair (the ear, the hairline): the strip ends
            cur = U[j]
            spine.append(_unit(cur - sc.C))
        if len(spine) < 4:
            continue
        spine = np.array(spine)
        sa, se = az_el(spine)
        H, dd = envelope(sc, g, line, sa, se)
        U_all = np.linspace(0, 1, len(spine))
        # shingles: the stream's length in `segments` overlapping pieces, each one's root dived under the tip of the
        # piece before it, each tip lifted a `step` (x thickness) off the piece it lies on, so the rows read as layered
        # clumps with a shadow line at every step, not one skin with grooves drawn on it
        nseg = max(1, int(td.get("segments", 3)))
        ov = float(td.get("overlap_along", 0.3))
        step = float(td.get("step", 0.8))
        lo_u = np.linspace(0, 1, nseg + 1)[:-1]
        hi_u = np.minimum(np.linspace(0, 1, nseg + 1)[1:] + ov / nseg, 1.0)
        size = 1 + noise * 0.15 * rng.uniform(-1, 1)
        for sgi in range(nseg):
            sel = (U_all >= lo_u[sgi] - 1e-9) & (U_all <= hi_u[sgi] + 1e-9)
            if sel.sum() < 4:
                continue
            u = (U_all[sel] - U_all[sel][0]) / max(U_all[sel][-1] - U_all[sel][0], 1e-9)
            Hs = H[sel]
            base = Hs - FILL_SINK * t0 + 0.5 * t0  # back at the volume over the sunk underlayer
            last = sgi == nseg - 1
            h = (base - 0.9 * t0 * (1 - _ss(u / 0.2))  # the root dives under the tip before it
                 + (0.0 if last else step * t0) * _ss((u - 0.55) / 0.45)  # the tip lifts off the next row
                 - (0.8 * t0 * _ss((u - 0.8) / 0.2) if last else 0.0))  # the last tucks in at the hairline
            h = np.maximum(h, 0.2 * t0 * _ss(u / 0.2) - 0.6 * t0 * (1 - _ss(u / 0.2)))
            path = sc.point(sa[sel], se[sel], h)
            c = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
            L = c[-1]
            kpts = 5 if L > 0.06 else 4
            tt = np.linspace(0, L, kpts)
            ctrl = np.stack([np.interp(tt, c, path[:, q]) for q in range(3)], 1)
            a_, e_, h_ = sc.coords(ctrl)
            Pc = sc.point(a_, e_, 0.0)
            rad = np.clip(np.linalg.norm(Pc - N, axis=1) / d_start, 0.45, 1.2)
            tilt = lie_tilt(sc, g, line, _catmull(ctrl, 4 * kpts)[::4])
            grey = _grey(g, float(a_[0]), float(e_[0]), line)
            out[f"s{k:02d}{'abcdefgh'[sgi]}"] = {
                "tier": "strip",
                "pts": [[round(float(a_[q]), 2), round(float(e_[q]), 2), round(float(h_[q]), 4)] for q in range(kpts)],
                "radius": [round(float(v), 3) for v in rad],
                "tilt": [round(float(v), 3) for v in tilt],
                "width": round(w0 * size, 4), "thickness": round(t0, 4),
                "cup": round(float(td["cup"]) if "cup" in td else lie_cup(sc, w0 * size, path), 4),
                "taper": float(td.get("taper", 0.6)), "belly": float(td.get("belly", 0.3)), "root": 0.85,
                "twist": 0.0, **({"grey": round(grey, 3)} if grey > 0.01 else {})}
    return out


def _gap_roots(sc: Scalp, g: dict, line, locks: dict, td: dict, rng):
    """Roots for gap locks: cells of the hair (inside the hairline) that the locks so far leave uncovered (their
    outer faces splatted on a 1 degree grid, grown a little), spaced like the tier, each a lock length upstream of the
    hole so the lock lies over it."""
    if not locks:
        return np.array([]), np.array([])
    ext = lock_extents(sc, resolve({"hair": {"locks": locks}}, sc))
    A, E = np.meshgrid(np.arange(0.0, 360.0, 1.0), np.arange(-60.0, 89.0, 1.0), indexing="ij")
    cov = coverage(sc, A, E, ext, reach=0.001)
    d = inside(sc, line, A, E)
    bare = (cov < 0.75) & (d > 0.004)
    if not bare.any():
        return np.array([]), np.array([])
    a0, e0 = A[bare], E[bare]
    sp = float(td.get("width", 0.025)) * float(td.get("spacing", 0.7))
    P = sc.point(a0, e0, 0.0)
    order = rng.permutation(len(a0))
    chosen, pts = [], np.zeros((0, 3))
    for i in order:
        if len(pts) and np.min(np.linalg.norm(pts - P[i], axis=1)) < sp:
            continue
        chosen.append(i)
        pts = np.vstack([pts, P[i]])
    a0, e0 = a0[chosen], e0[chosen]
    # step upstream (against the flow) by a third of the lock so its body covers the hole
    W = weights(a0, e0, inside(sc, line, a0, e0))
    P0 = sc.point(a0, e0, 0.0)
    xp = _part_x(g)
    away = np.sign(P0[:, 0] + 1e-9) if xp is None else np.where(P0[:, 0] >= xp, 1.0, -1.0)
    f = _unit(flow(sc, g, P0, W, away))
    back = P0 - f * float(td.get("length", 0.05)) * 0.35
    a1, e1 = az_el(back - sc.C)
    ok = inside(sc, line, a1, e1) > 0.004
    return np.where(ok, a1, a0), np.where(ok, e1, e0)


def _part_roots(sc: Scalp, g: dict, line, td: dict, xp: float, rng):
    """The big locks' roots, laid out the way the cut is designed: along the front hairline on each side of the
    parting (most on the side the hair is combed to) and in a row down the parting behind it. Returns az, el, away."""
    sgn = 1.0 if xp >= 0 else -1.0  # the part's side; the hair is combed away from it
    P = sc.point(np.array([0.0]), np.array([60.0]), 0.0)[0]
    az_p = float(az_el(np.array([xp, sc.C[1] - 0.12, P[2]]) - sc.C)[0][()])
    az_p = (az_p + 180) % 360 - 180
    nf_away, nf_part, n_row = int(td.get("front_away", 5)), int(td.get("front_part", 2)), int(td.get("part_row", 3))
    far = float(td.get("front_span", 42.0))  # degrees of azimuth the front row reaches round from the middle
    A, E, AW = [], [], []
    inset = float(td.get("inset", 0.016))  # behind the hairline: the roots grow out of the mass, not the skin
    for n, lo, hi, aw in ((nf_away, az_p - sgn * 3, -sgn * far, -sgn), (nf_part, az_p + sgn * 5, sgn * far, sgn)):
        if n <= 0:
            continue
        a = np.linspace(lo, hi, n + 1)[:-1] + (hi - lo) / (2 * n) * 0.3 + rng.uniform(-1, 1, n) * 1.5
        e = _line_at(line, a % 360) + np.degrees(inset / sc.r(a % 360, _line_at(line, a % 360)))
        A += list(a % 360)
        E += list(e)
        AW += [aw] * n
    if n_row > 0:  # down the parting, behind the front row, combed away from it
        L = float(g["parting"].get("length", 0.1))
        y0 = sc.point(0.0, float(_line_at(line, 0.0)), 0.0)[1]
        for k in range(n_row):
            y = y0 + L * (k + 0.9) / (n_row + 0.4)
            q = np.array([xp - sgn * 0.006, y, sc.C[2] + 0.12]) - sc.C
            a, e = az_el(q)
            A.append(float(a))
            E.append(float(e))
            AW.append(-sgn)
    return np.array(A), np.array(E), np.array(AW)


def mass_normal(sc: Scalp, g: dict, line, az, el, d: float = 1.0):
    """The outward normal of the groom's volume (the envelope surface) at (az, el): what a lock lies flat on."""
    def pt(a, e):
        H, _ = envelope(sc, g, line, a, e)
        return sc.point(a, e, H)
    ea = pt(az + d, el) - pt(az - d, el)
    ee = pt(az, el + d) - pt(az, el - d)
    n = _unit(np.cross(ea, ee))
    out = dirs(az, el)
    return np.where((n * out).sum(-1, keepdims=True) < 0, -n, n)


def lie_cup(sc: Scalp, width: float, path) -> float:
    """The cup that makes a lock's flat back follow the head's curve across it (its edges drop by the sag of the
    head over half its width), so neighbours lie flush: a fixed cup tucked narrow locks' edges deep (grooves that
    dented the outline) and let wide ones stand on their edges."""
    P = np.asarray(path, float)
    R = float(np.median(np.linalg.norm(P - sc.C, axis=1)))
    return (0.5 * width) ** 2 / (2 * R)


def lie_tilt(sc: Scalp, g: dict, line, P):
    """Per control point, the tilt (radians about the spine) that turns the node group's flat side (facing away
    from the head centre) to face the volume's own normal: facing the centre, a lock across the steeply curving
    upper side stood on one edge (the fill poked 2-4 mm out of the outline)."""
    P = np.asarray(P, float)
    tg = _unit(np.gradient(P, axis=0))
    n0 = _unit(P - sc.C)
    n0 = _unit(n0 - (n0 * tg).sum(1, keepdims=True) * tg)
    a, e = az_el(P - sc.C)
    n1 = mass_normal(sc, g, line, a, e)
    n1 = _unit(n1 - (n1 * tg).sum(1, keepdims=True) * tg)
    return np.arctan2((np.cross(n0, n1) * tg).sum(1), (n0 * n1).sum(1))


def _grey(g, az, el, line):
    """Grey at the temples and sideburns: by azimuth band and how low the root sits."""
    gr = g.get("grey") or {}
    fa = abs(((az + 180) % 360) - 180)
    temple = float(gr.get("temples", 0)) * float(_ss((fa - 35) / 15) * (1 - _ss((fa - 95) / 15)))
    low = float(_ss((30 - el) / 25))
    burn = float(gr.get("sideburns", 0)) * float(_ss((fa - 60) / 10) * (1 - _ss((fa - 90) / 10))) * low
    return max(temple * (0.4 + 0.6 * low), burn)


def _walk(sc: Scalp, g: dict, line, az, el, L, T, lift, away, rng, tier, n=24, flat=None):
    """Lock spines (m, n, 3): from the root on the scalp along the flow, held under the envelope (the top layer's
    spine half a thickness under it), rising out of the scalp over the first fifth, the tip tucking down."""
    m = len(az)
    P = np.zeros((m, n, 3))
    SF = np.zeros((m, n))
    a, e = np.asarray(az, float).copy(), np.asarray(el, float).copy()
    P[:, 0] = sc.point(a, e, -0.3 * T)
    ds = L / (n - 1)
    W = weights(a, e, inside(sc, line, a, e))
    flat = np.zeros(m) if flat is None else np.asarray(flat, float)

    def flow_flat(q, W):  # locks marked flat comb back and down only (the part side: brushed toward the ear)
        f = flow(sc, g, q, W, away)
        return f - flat[:, None] * np.maximum(f[:, 2:3], 0) * np.array([0.0, 0.0, 1.0])
    d = _unit(flow_flat(P[:, 0], W))
    turn = np.radians(rng.uniform(-1, 1, m) * 6 * float(g.get("noise", 0.3)))
    nrm = _unit(P[:, 0] - sc.C)
    c, s_ = np.cos(turn)[:, None], np.sin(turn)[:, None]
    d = _unit(d * c + np.cross(nrm, d) * s_)
    for k in range(1, n):
        x = k / (n - 1)
        q = P[:, k - 1] + d * ds[:, None]
        a, e = az_el(q - sc.C)
        H, d_in = envelope(sc, g, line, a, e)
        under_h = under(g, H, a, e, d_in)  # the mass under the locks (the blockout kept as the underlayer)
        if tier == "edge":
            h = np.full(m, 0.6) * T + 0.0005 + under_h
        else:  # the lock lies on the mass, its back just proud of the silhouette; the root dives into the mass
            # the lock's back flush with the groom's volume (the fill: relief pressed into the mass, not scales on it)
            surf = under_h + (0.35 if tier == "big" else FILL_SINK - 0.4) * T + lift
            h = (under_h - 0.4 * T) + (surf - under_h + 0.4 * T) * _ss(x / 0.18)
        # over the upper sides a top lock lies down onto the side mass (and narrows: `radius` per point below):
        # standing as proud there as on the crown it overhung the sides and pinched the outline at the temples
        sf = side_tuck(a, e) if tier == "big" else np.zeros(m)
        SF[:, k] = sf
        h = h - sf * np.maximum(lift, 0)  # no lift where it lies down the side (the mass is sunk there too now)
        if tier == "big":  # the tip lifts a step off the lock it lies on (shingles: the next one's root is under it)
            h = h + TIP_STEP * T * _ss((x - 0.55) / 0.45) * (1 - 0.5 * sf) * (1 - flat)
        else:  # the fill's tips tuck (a row of visible points read as feathers)
            h = h - 1.3 * T * _ss((x - 0.72) / 0.28)
        if tier == "fill":  # relief within the volume: its back never stands out of the groom's silhouette
            h = np.minimum(h, H - 0.8 * T)
        floor = np.where(d_in > 0, 0.15, 0.55) * T  # past the hairline (a fringe) it lies on the skin, not in it
        h = np.maximum(h, floor * _ss(x / 0.25) - 0.6 * T * (1 - _ss(x / 0.25)))  # the root grows out of the scalp
        # (floored above the skin from the start, a lock's squared-off root end stood on the forehead as a black notch)
        q = sc.point(a, e, h)
        P[:, k] = q
        seg = _unit(P[:, k] - P[:, k - 1])
        W = weights(a, e, d_in)
        f = _unit(flow_flat(q, W))
        f = _unit(f * c + np.cross(_unit(q - sc.C), f) * s_)
        d = _unit(0.55 * seg + 0.45 * f)
    SF[:, 0] = SF[:, 1]
    return P, SF


# ------------------------------------------------------------------------------------------------ spec I/O

def hair_of(spec: dict) -> dict:
    return spec.get("hair") or {}


def validate(spec: dict) -> None:
    h = hair_of(spec)
    if not h:
        return
    bad = set(h) - {"groom", "locks", "look", "cap", "stage", "part", "filler"}
    if bad:
        raise HairError(f"hair: unknown keys {sorted(bad)} (have groom, locks, look, cap, stage, part)")
    groom_params(spec)
    for n, lk in (h.get("locks") or {}).items():
        bad = set(lk) - LOCK_KEYS
        if bad:
            raise HairError(f"hair lock {n!r}: unknown keys {sorted(bad)} (have {', '.join(sorted(LOCK_KEYS))})")
        pts = lk.get("pts") or []
        if len(pts) < 2 or any(len(p) != 3 for p in pts):
            raise HairError(f"hair lock {n!r}: pts is a list of at least 2 [az, el, h] points")
        for k in ("width", "thickness"):
            if not isinstance(lk.get(k), (int, float)) or lk[k] <= 0:
                raise HairError(f"hair lock {n!r}: {k} (m) must be > 0")


def groom(name: str, replace: bool = False, note: str = "") -> dict:
    """Grow the first pass of locks from spec["hair"]["groom"] and save them. Locks a person or an edit changed
    (their names not starting with the tier letters b/f/e + digits) are kept unless replace."""
    spec = store.load(name)
    h = spec.setdefault("hair", {})
    sc = scalp(name, spec)
    g = groom_params(spec)
    new = grow(sc, g)
    old = h.get("locks") or {}
    keep = {} if replace else {n: lk for n, lk in old.items()
                               if not (n[:1] in "bcfesgh" and n[1:].rstrip("abcdefgh").isdigit())}
    h["locks"] = {**new, **keep}
    store.save(name, spec, note or f"hair: grew {len(new)} locks from the groom")
    return {"locks": len(h["locks"]), "tiers": {t: sum(1 for lk in new.values() if lk["tier"] == t)
                                                for t in ("big", "fill", "edge")}}


def lock_hash(lk: dict, sc: Scalp) -> str:
    return hashlib.sha1(json.dumps([lk, sc.C.tolist(), float(sc.R.sum())], sort_keys=True,
                                   default=float).encode()).hexdigest()[:12]


def resolve(spec: dict, sc: Scalp) -> list:
    """The locks as Blender wants them: world control points, handles, radius, tilt and modifier inputs."""
    out = []
    for n, lk in sorted((hair_of(spec).get("locks") or {}).items()):
        pts = np.asarray(lk["pts"], float)
        W = sc.point(pts[:, 0], pts[:, 1], pts[:, 2])
        H = None
        if lk.get("handles"):
            H = []
            for hd in lk["handles"]:
                if hd:
                    a = sc.point(hd[0], hd[1], hd[2])
                    b = sc.point(hd[3], hd[4], hd[5])
                    H.append([float(v) for v in list(a) + list(b)])
                else:
                    H.append(None)
        inputs = {MOD[k]: float(lk.get(k, LOCK_DEFAULTS.get(k, 0.0))) for k in MOD}
        inputs["Seed"] = (int(hashlib.md5(n.encode()).hexdigest()[:6], 16) % 1000) / 1000.0
        inputs["Centre"] = [float(v) for v in sc.C]
        out.append({"name": n, "pts": W.tolist(), "handles": H, "radius": lk.get("radius"), "tilt": lk.get("tilt"),
                    "inputs": inputs, "hash": lock_hash(lk, sc)})
    return out


def _catmull(P, n):
    """A Catmull-Rom curve through P (close to Blender's auto handles), n points evenly in parameter."""
    P = np.asarray(P, float)
    Q = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    t = np.linspace(0, len(P) - 1, n)
    k = np.minimum(np.floor(t).astype(int), len(P) - 2)
    u = (t - k)[:, None]
    p0, p1, p2, p3 = Q[k], Q[k + 1], Q[k + 2], Q[k + 3]
    return 0.5 * (2 * p1 + (p2 - p0) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u ** 2 + (3 * p1 - p0 - 3 * p2 + p3) * u ** 3)


def lock_width(inp: dict, u):
    """The lock's width factor along it (0 root .. 1 tip), as blender_hair's node group makes it."""
    root, belly, taper = inp.get("Root", 0.6), max(inp.get("Belly", 0.3), 0.02), inp.get("Taper", 1.0)
    rise = root + (1 - root) * _ss(u / belly)
    fall = _ss((u - belly) / max(1 - belly, 1e-6))
    return rise * (1 - taper * fall ** 0.8)


def lock_extents(sc: Scalp, locks: list, n: int = 40):
    """Points on every lock's outer face (the spine as Blender curves it, the lens across it at 7 places, pushed
    out by half the thickness less the cup, sized along the lock like the node group): what the locks add to the
    silhouette."""
    out = []
    cs = np.linspace(-1, 1, 7)
    for lk in locks:
        S = _catmull(lk["pts"], n)
        u = np.linspace(0, 1, n)
        tg = _unit(np.gradient(S, axis=0))
        nr = _unit(S - sc.C)
        nr = _unit(nr - (nr * tg).sum(1, keepdims=True) * tg)
        if lk.get("tilt"):  # Blender turns the flat side by the (interpolated) tilt about the spine
            ti = np.interp(u, np.linspace(0, 1, len(lk["tilt"])), lk["tilt"])[:, None]
            nr = nr * np.cos(ti) + np.cross(tg, nr) * np.sin(ti)
        b = _unit(np.cross(nr, tg))
        inp = lk["inputs"]
        f = lock_width(inp, u)[:, None]
        for c in cs:
            sy = np.sqrt(max(1 - c * c, 0.0)) ** 0.8
            off = c * 0.5 * inp["Width"] * b + (sy * 0.5 * inp["Thickness"] - inp.get("Cup", 0.0) * c * c) * nr
            out.append(S + f * off)
    return np.concatenate(out) if out else np.zeros((0, 3))


def _hull_lift(sc: Scalp, AA, EE, H, d_in, extra, band=12.0):
    """Raise the underlayer round the sides to the convex hull of itself and the locks' outsides, per azimuth plane
    (a waist under wide top locks read as a divot at the temples). Sides only (the top keeps its lock separations),
    below 60 degrees of elevation."""
    from scipy.spatial import ConvexHull
    if not len(extra):
        return H
    ea, ee = az_el(extra - sc.C)
    rho_x = np.linalg.norm(extra - sc.C, axis=1)
    H = H.copy()
    for i, a in enumerate(AA[:, 0]):
        fa = abs(((a + 180) % 360) - 180)
        wa = _ss((fa - 30) / 15) * (1 - _ss((fa - 140) / 15))
        if wa <= 0:
            continue
        near = np.abs(((ea - a + 180) % 360) - 180) < band / 2
        if near.sum() < 3:
            continue
        e = EE[i]
        hair = d_in[i] > 0
        rho = sc.r(np.full(len(e), a), e) + H[i]
        er = np.radians(e)
        pts = np.stack([rho * np.cos(er), rho * np.sin(er)], 1)[hair]
        ex = np.radians(ee[near])
        pts = np.vstack([pts, np.stack([rho_x[near] * np.cos(ex), rho_x[near] * np.sin(ex)], 1), [[0.0, 0.0]]])
        try:
            hull = ConvexHull(pts)
        except Exception:
            continue
        uu = np.stack([np.cos(er), np.sin(er)], 1)
        best = np.full(len(e), np.inf)
        for eq in hull.equations:
            nd = uu @ eq[:2]
            best = np.minimum(best, np.where(nd > 1e-9, -eq[2] / np.maximum(nd, 1e-12), np.inf))
        need = np.where(hair & np.isfinite(best), best - sc.r(np.full(len(e), a), e) - 0.001, 0.0)
        we = wa * (1 - _ss((e - 62) / 12))
        H[i] = np.maximum(H[i], H[i] + (need - H[i]) * we * (need > H[i]))
    return H


GATE_VIEWS = (("front", 0.0, ("left", "right")), ("three_quarter", 40.0, ("left",)),
              ("three_quarter_r", -40.0, ("right",)))


def _outline(sc: Scalp, P, az: float, sgn: float, edges):
    """The outline (outermost lateral extent, m) of points P per height bin, seen along azimuth az, one side."""
    a = np.radians(az)
    right = np.array([np.cos(a), np.sin(a), 0.0]) * sgn
    x, z = (P - sc.C) @ right, P[:, 2]
    k = np.clip(((z - edges[0]) / (edges[1] - edges[0])).astype(int), -1, len(edges))
    prof = np.full(len(edges), -np.inf)
    ok = (k >= 0) & (k < len(edges))
    np.maximum.at(prof, k[ok], x[ok])
    return prof, right


def _envelope_of(prof, edges):
    """The convex envelope of an outline over its heights (what a hull would give), and the deficit per height."""
    from scipy.spatial import ConvexHull
    good = np.isfinite(prof)
    P = np.stack([prof[good], edges[good]], 1)
    base = P[:, 0].min() - 1.0
    P2 = np.vstack([P, [[base, P[0, 1]], [base, P[-1, 1]]]])
    hv = P2[ConvexHull(P2).vertices]
    hv = hv[hv[:, 0] > base + 0.5]
    hv = hv[np.argsort(hv[:, 1])]
    hx = np.full(len(prof), np.nan)
    hx[good] = np.interp(edges[good], hv[:, 1], hv[:, 0])
    return hx, np.where(good, hx - prof, 0.0)


def _silhouette_fill(sc: Scalp, AA, EE, H, d_in, extra, rounds: int = 14, cap=None):
    """Raise the underlayer where the hair's outline (underlayer + the locks' outsides) dents inside its own convex
    envelope in the front and 3/4 views, below the crown band: under the wide top locks the sides pinched in at
    the temples (a divot either side). The underlayer is pushed out only near the outline, where it can fill it."""
    from scipy.ndimage import gaussian_filter
    hair_m = d_in > 0.002
    H = H.copy()
    for _ in range(rounds):
        V = sc.point(AA, EE, H)
        P = np.vstack([V[hair_m], extra]) if len(extra) else V[hair_m]
        z0 = sc.lm["lm_brow_mid.L"][2] + 0.02
        ztop = P[:, 2].max() - 0.01 - CROWN_BAND
        edges = np.arange(z0, ztop, 0.002)
        raise_ = np.zeros(H.shape)
        worst = 0.0
        for _n, az, sides in GATE_VIEWS:
            for side in sides:
                sgn = 1.0 if side == "left" else -1.0
                prof, right = _outline(sc, P, az, sgn, edges)
                if np.isfinite(prof).sum() < 4:
                    continue
                _hx, deficit = _envelope_of(prof, edges)
                deficit = np.nan_to_num(deficit)
                worst = max(worst, float(deficit.max()))
                x = (V - sc.C) @ right
                kz = ((V[..., 2] - edges[0]) / 0.002).astype(int)
                inb = (kz >= 0) & (kz < len(edges)) & hair_m
                kz = np.clip(kz, 0, len(edges) - 1)
                need = np.where(inb, deficit[kz], 0.0)
                near = _ss((x - (np.where(inb, prof[kz], np.inf) - 0.015)) / 0.012)
                lat = np.maximum((dirs(AA, EE) @ right), 0.25)
                raise_ = np.maximum(raise_, need * near / lat)
        if worst * 1000 <= 0.3 * GATE_MM:  # the python outline (lock_extents) runs ~1 mm short of Blender's
            break
        r = gaussian_filter(raise_, sigma=(4.0, 4.0), mode=("wrap", "nearest"))  # broad: a sharp raise read as a shelf
        H = H + 1.5 * r
        if cap is not None:  # never above the volume itself: raised past it, the filler buried the crown locks
            H = np.minimum(H, cap)
    return H


def coverage(sc: Scalp, AA, EE, P, reach: float = 0.004):
    """0..1 on an (az, el) grid: how far each cell is covered by the locks' outer points P (their footprint splatted,
    grown by `reach` m and softened)."""
    from scipy.ndimage import binary_dilation, gaussian_filter
    step = float(AA[1, 0] - AA[0, 0])
    a, e = az_el(np.asarray(P, float) - sc.C)
    ia = np.round((a - AA[0, 0]) / step).astype(int) % AA.shape[0]
    ie = np.clip(np.round((e - EE[0, 0]) / step).astype(int), 0, AA.shape[1] - 1)
    grid = np.zeros(AA.shape, bool)
    grid[ia, ie] = True
    r = max(1, int(round(np.degrees(reach / 0.1) / step)))
    grid = binary_dilation(grid, iterations=r)
    return np.clip(gaussian_filter(grid.astype(float), sigma=r, mode=("wrap", "nearest")) * 1.6, 0, 1)


def cap_mesh(sc: Scalp, g: dict, height: float, mass: bool = False, step: float = 1.0, sunk: bool = False,
             extra=None):
    """The scalp inside the hairline pushed out: the dark underlayer (height m) or, mass=True, the groom's whole
    volume (stage a). Its edge dives under the skin just outside the hairline, so the line is crisp."""
    line = hairline(sc, g)
    A = np.arange(0.0, 360.0, step)
    E = np.r_[np.arange(-60.0, 90.0, step), 90.0]  # up to the pole (a hole there read as a groove)
    AA, EE = np.meshgrid(A, E, indexing="ij")
    if mass:
        H, d_in = envelope(sc, g, line, AA, EE)
        if sunk:
            H0 = H
            H = under(g, H, AA, EE, d_in)
            if extra is not None:  # the filler under the partings: where locks part at the outline, the sunk
                H = _silhouette_fill(sc, AA, EE, H, d_in, extra, cap=H0)  # underlayer rises to close the dent (only there)
        H = np.maximum(H, 0.0015 * _ss(d_in / 0.004))
    else:
        d_in = inside(sc, line, AA, EE)
        H = height * _ss(d_in / 0.006)
    H = np.where(d_in > 0, H, np.maximum(d_in, -0.004) * 0.8)
    V = sc.point(AA, EE, H).reshape(-1, 3)
    na, ne = AA.shape
    idx = np.arange(na * ne).reshape(na, ne)
    live = d_in > -0.003
    faces = []
    for i in range(na):
        i1 = (i + 1) % na
        a, b, c, d = idx[i, :-1], idx[i1, :-1], idx[i1, 1:], idx[i, 1:]
        ok = live[i, :-1] | live[i1, :-1] | live[i1, 1:] | live[i, 1:]
        faces.append(np.stack([a[ok], b[ok], c[ok], d[ok]], 1))
    F = np.concatenate(faces)
    used = np.unique(F)
    remap = -np.ones(len(V), int)
    remap[used] = np.arange(len(used))
    return V[used].astype(np.float32), remap[F].astype(np.int32)


# ------------------------------------------------------------------------------------------------ Blender

def streams(sc: Scalp, g: dict, V) -> dict:
    """The underlayer's combed clumps, for the material: on short back and sides the hair runs back and down toward
    the nape, so flow lines are rays from a point under the nape; `hp_tangent` = that direction on the surface and
    `hp_across` = a sawtooth (-1..1) of the angle round the nape point, one tooth per clump (`clumps.width` m at the
    ear's distance, jittered): the lock shader then draws a dark parting at each tooth's edge and strand grooves
    across. (Geometric fill locks on the sides either broke the outline or read as scales and blotches.)"""
    cl = g.get("clumps") or {}
    width = float(cl.get("width", 0.024))
    N = sc.C + np.array([0.0, 0.06, -0.13])  # under the nape: where the back and sides converge
    axis = _unit(np.array([0.0, -0.9, 0.45]))  # from it toward the forehead
    Q = V - N
    t = _unit(Q - (Q @ axis)[:, None] * axis)
    e1 = _unit(np.cross(axis, [1.0, 0, 0]))
    e2 = np.cross(axis, e1)
    ang = np.arctan2(t @ e2, t @ e1)
    dist = np.linalg.norm(Q, axis=1)
    rng = np.random.default_rng(int(g.get("seed", 0)) + 7)
    k = np.arange(-400, 400)
    edges = np.cumsum(np.r_[0.0, (1 + 0.35 * rng.uniform(-1, 1, len(k) - 1))]) * (width / 0.13)
    edges = edges - edges[len(k) // 2]
    i = np.clip(np.searchsorted(edges, ang) - 1, 0, len(edges) - 2)
    frac = (ang - edges[i]) / (edges[i + 1] - edges[i])
    across = 2 * frac - 1
    n = _unit(V - sc.C)
    tan = -Q  # combed toward the nape point
    tan = _unit(tan - (tan * n).sum(1, keepdims=True) * n)
    del dist
    return {"across": across.astype(np.float32), "tangent": tan.astype(np.float32),
            "lock": (rng.uniform(0, 1, len(edges))[i]).astype(np.float32)}


def job(name: str, spec: dict | None = None) -> dict:
    """What Blender needs to show the hair: the locks, the cap (or the mass), the material."""
    spec = store.load(name) if spec is None else spec
    h = hair_of(spec)
    if not h:
        return {}
    sc = scalp(name, spec)
    g = groom_params(spec)
    tmp = Path(tempfile.mkdtemp(prefix="hifipushie-hair-"))
    stage = h.get("stage", "locks")
    locks = [] if stage == "mass" else resolve(spec, sc)
    V, F = cap_mesh(sc, g, float(h.get("cap", 0.002)), mass=True, sunk=stage != "mass",
                    extra=lock_extents(sc, locks) if (locks and h.get("filler")) else None)
    extra = {k: v for k, v in streams(sc, g, V).items() if k == "tangent"} if stage != "mass" else {}  # (the
    # sawtooth clumps on the underlayer aliased into jagged stripes: the strips carry the clumps now)
    np.savez(tmp / "cap.npz", verts=V, faces=F, **extra)
    return {"locks": locks, "cap": str(tmp / "cap.npz"),
            "cap_kind": "mass" if stage == "mass" else "under", "look": {**LOOK, **(h.get("look") or {})},
            "centre": sc.C.tolist()}


def stage_path(name: str) -> Path:
    return store._dir(name) / "hair_stage.blend"


def make_stage(name: str, pad: float = 0.1) -> Path:
    """A small .blend for fast hair looks: the scene cropped to a box round the head (painted skin, eyes, collar),
    rebuilt when scene.blend is newer."""
    from .scene import _blender, blend_path
    bp = blend_path(name)
    if not bp.exists():
        raise HairError(f"{name}: no scene.blend yet (sync the model once)")
    sp = stage_path(name)
    if sp.exists() and sp.stat().st_mtime > bp.stat().st_mtime:
        return sp
    sc = scalp(name)
    lo = (sc.C - [0.16, 0.2, 0.22]).tolist()
    hi = (sc.C + [0.16, 0.16, 0.16]).tolist()
    _blender({"mode": "hair_stage", "blend": str(bp), "out": str(sp), "box": [lo, hi]})
    return sp


VIEWS = {"front": (0.0, 5.0), "three_quarter": (40.0, 12.0), "side": (90.0, 5.0), "back": (180.0, 10.0),
         "top": (20.0, 60.0), "three_quarter_r": (-40.0, 12.0), "close": (-30.0, 25.0, 0.45),
         "close_back": (150.0, 20.0, 0.45)}


def cameras(sc: Scalp, views, dist: float = 0.62, fov: float = 30.0) -> list:
    out = []
    target = sc.C + np.array([0.0, 0.0, 0.0])
    for v in views:
        az, el, *dd = VIEWS[v]
        eye = target + dirs(az, el) * (dd[0] if dd else dist)  # close-ups: the material at work
        out.append({"name": v, "eye": eye.tolist(), "target": target.tolist(), "fov": fov})
    return out


def look(name: str, views=("front", "three_quarter", "side", "back", "top"), size: int = 480, save: str | None = None,
         reference: str | None = None, spec: dict | None = None, caption: str = "", clay: bool = True) -> tuple:
    """A fast hair look: the head-cropped stage file + the hair from the spec, EEVEE, a few perspective views, a
    thumbnail (how it reads small) and the reference beside. Returns (sheet image, seconds)."""
    from PIL import Image, ImageDraw
    from . import render
    from .scene import _blender
    t = time.time()
    spec = store.load(name) if spec is None else spec
    sp = make_stage(name)
    sc = scalp(name, spec)
    cams = cameras(sc, views)
    frames = [render.camera_frame(c, i) for i, c in enumerate(cams)]
    thumb = render.camera_frame({"name": "thumb", "eye": (sc.C + dirs(25.0, 8.0) * 1.6).tolist(),
                                 "target": (sc.C - [0, 0, 0.12]).tolist(), "fov": 30.0}, len(frames))
    with tempfile.TemporaryDirectory() as tmp:
        for f in frames + [thumb]:
            f["out"] = str(Path(tmp) / f"{f['name']}.png")
        thumb["size"] = 160
        dump = str(Path(tmp) / "hair_pts.npy")
        cf = [{**f, "out": str(Path(tmp) / f"clay_{f['name']}.png")} for f in frames] if clay else []
        idf = [{**f, "out": str(Path(tmp) / f"id_{f['name']}.png"), "size": 240} for f in frames]
        j = {"mode": "hair_look", "blend": str(sp), "views": frames + [thumb], "size": size, "hair": job(name, spec),
             "samples": 16, "dump": dump, "clay_views": cf, "id_views": idf}
        out = _blender(j)
        clays = [Image.open(f["out"]).convert("RGB") for f in cf]
        look.mass_share = {}
        for f in idf:  # red = the underlayer, green = locks (flat emission, nothing else drawn)
            a = np.asarray(Image.open(f["out"]).convert("RGB"), float)
            red, green = a[..., 0] > a[..., 1] + 60, a[..., 1] > a[..., 0] + 60
            look.mass_share[f["name"]] = round(float(red.sum() / max(red.sum() + green.sum(), 1)), 3)
            Image.open(f["out"]).save(store._dir(name) / f"hair_id_{f['name']}.png")  # the last look's id pass
        pts = np.load(dump)
        np.save(store._dir(name) / "hair_points.npy", pts)  # the last look's hair vertices (for measuring) and
        np.savez(store._dir(name) / "hair_point_owners.npz", ids=np.load(dump + ".ids.npy"),  # which object each is
                 names=np.array(json.load(open(dump + ".names.json"))))
        look.gate = silhouette_gate(sc, pts)
        imgs = [Image.open(f["out"]).convert("RGB") for f in frames]
        th = Image.open(thumb["out"]).convert("RGB")
    t_render = time.time() - t
    W = size
    cols = len(imgs) + 1
    rows = 2 if clays else 1
    sheet = Image.new("RGB", (W * cols, rows * W + 22), (30, 31, 35))
    dr = ImageDraw.Draw(sheet)
    for i, (im, f) in enumerate(zip(imgs, frames)):
        sheet.paste(im.resize((W, W)), (i * W, 22))
        dr.text((i * W + 6, 5), f["name"], fill=(220, 220, 220))
    for i, im in enumerate(clays):
        sheet.paste(im.resize((W, W)), (i * W, 22 + W))
    if clays:
        dr.text((6, 22 + W + 6), "clay", fill=(220, 220, 220))
    x0 = (cols - 1) * W
    ref = Path(reference or "/home/joe/dev/hifipushie/workspace/disc_golfer_renders/ref_user_style.png")
    if ref.exists():
        r = Image.open(ref).convert("RGB")
        r = r.crop((250, 20, 560, 330)) if reference is None else r
        r.thumbnail((W, W - 170))
        sheet.paste(r, (x0, 22))
        dr.text((x0 + 6, 5), "reference", fill=(220, 220, 220))
    sheet.paste(th, (x0 + 6, W + 22 - th.height - 4))
    dr.text((x0 + 170, W + 22 - 20), f"thumbnail {th.width}px", fill=(200, 200, 200))
    if caption:
        dr.text((6, rows * W + 6), caption, fill=(240, 220, 160))
    if save:
        sheet.save(save)
    frames_t = [line for line in out.splitlines() if line.startswith("@@")]
    return sheet, round(t_render, 1), frames_t


GATE_MM = 1.5  # the deepest dent allowed in the hair's outline (front and 3/4), mm, from the brows up to...
GATE_SCALE = 0.012  # m: the outline is gated on shapes at least one lock row tall (smoothed over it): a waist or
# divot is tens of mm; a clump's step where one lock ends over the next is a notch, the relief we want
NOTCH_SCALE = 0.006  # m: notches (clump steps at the outline) are measured on this and reported, target 2-5 mm
CROWN_BAND = 0.02  # ...this far under the top (the top's outline is the lock crowns: reported, not gated)


def silhouette_gate(sc: Scalp, V, views=(("front", 0.0, ("left", "right")), ("three_quarter", 40.0, ("left",)),
                                          ("three_quarter_r", -40.0, ("right",)))) -> dict:
    """How far the hair's outline dips inside its own convex hull, per view and side, over the band from a little
    above the brows to near the top (a waist at the temples reads as a divot). Orthographic along the view's azimuth.
    {view: {"left": mm, "right": mm, "at": z of the worst}, "pass": bool}."""
    from scipy.spatial import ConvexHull
    z0 = sc.lm["lm_brow_mid.L"][2] + 0.02
    out, ok = {}, True
    for name, az, sides in views:  # 3/4: the near side's outline (the far one is the forehead's profile)
        a = np.radians(az)
        right = np.array([np.cos(a), np.sin(a), 0.0])  # the view's lateral axis (his left positive)
        Q = V - sc.C
        x, z = Q @ right, V[:, 2]
        keep = z > z0
        x, z = x[keep], z[keep]
        ztop = z.max() - 0.01
        res, worst = {}, (0.0, None)
        edges = np.arange(z0, ztop, 0.002)
        for side, sgn in (("left", 1.0), ("right", -1.0)):
            if side not in sides:
                continue
            raw = np.array([np.max(sgn * x[(z >= e) & (z < e + 0.002)]) if np.any((z >= e) & (z < e + 0.002))
                            else np.nan for e in edges])

            def smoothed(scale):
                k = max(1, int(round(scale / 0.002)))
                if k > 1 and np.isfinite(raw).all():
                    return np.convolve(np.pad(raw, k // 2, mode="edge"), np.ones(k) / k, mode="valid")[:len(edges)]
                return raw
            prof = smoothed(NOTCH_SCALE)
            good = ~np.isnan(prof)
            if good.sum() >= 4:  # the notches: clump steps (6 mm smoothing), reported
                Pn = np.stack([prof[good], edges[good]], 1)
                Pn = Pn[Pn[:, 1] <= ztop - CROWN_BAND]
                if len(Pn) >= 4:
                    b = Pn[:, 0].min() - 1.0
                    P2 = np.vstack([Pn, [[b, Pn[0, 1]], [b, Pn[-1, 1]]]])
                    hv = P2[ConvexHull(P2).vertices]
                    hv = hv[hv[:, 0] > b + 0.5]
                    hv = hv[np.argsort(hv[:, 1])]
                    res[side + "_notch"] = round(float(((np.interp(Pn[:, 1], hv[:, 1], hv[:, 0]) - Pn[:, 0])
                                                        * 1000).max()), 1)
            prof = smoothed(GATE_SCALE)
            good = ~np.isnan(prof)
            if good.sum() < 4:
                continue
            P = np.stack([prof[good], edges[good]], 1)

            def dents(P):
                base = P[:, 0].min() - 1.0  # close the outline on the inside: the hull's outer chain is the envelope
                P2 = np.vstack([P, [[base, P[0, 1]], [base, P[-1, 1]]]])
                hv = P2[ConvexHull(P2).vertices]
                hv = hv[hv[:, 0] > base + 0.5]
                hv = hv[np.argsort(hv[:, 1])]
                return (np.interp(P[:, 1], hv[:, 1], hv[:, 0]) - P[:, 0]) * 1000
            # the gated band: brows + 2 cm up to CROWN_BAND under the top, its own envelope (the lock crowns on top
            # are the clumps; a chord from them down onto the sides is reported as "full", not gated)
            crown = P[:, 1] > ztop - CROWN_BAND
            full = dents(P)
            res[side + "_crown"] = round(float(full[crown].max()), 1) if crown.any() else 0.0
            res[side + "_full"] = round(float(full.max()), 1)
            gap = np.zeros(len(P))
            if (~crown).sum() >= 4:
                gap[~crown] = dents(P[~crown])
            i = int(np.argmax(gap))
            res[side] = round(float(gap[i]), 1)
            if gap[i] > worst[0]:
                worst = (float(gap[i]), round(float(P[i, 1]), 3))
        res["at"] = worst[1]
        out[name] = res
        ok &= worst[0] <= GATE_MM
    out["pass"] = bool(ok)
    return out


def sync(name: str) -> dict:
    """Push the spec's hair into scene.blend (the person's live Blender when it has the scene open)."""
    from .scene import _blender, _blender_live, blend_path, live_session
    j = {"mode": "hair_sync", "blend": str(blend_path(name)), "hair": job(name)}
    t = time.time()
    out = _blender_live(j) if live_session(name) else _blender(j)
    made = next((json.loads(line[7:]) for line in out.splitlines() if line.startswith("@@made")), [])
    return {"made": len(made), "seconds": round(time.time() - t, 1)}


def pull_locks(spec: dict, name: str, got: dict, log: list) -> dict:
    """Locks a person changed in the scene, written into the spec as (az, el, h) addresses and lock numbers."""
    if not got:
        return {}
    h = hair_of(spec)
    locks = h.get("locks") or {}
    sc = scalp(name, spec)
    changes = {}
    inv = {v: k for k, v in MOD.items()}
    for n, st in got.items():
        if n == "__deleted__":
            continue
        lk = locks.get(n)
        if lk is None:
            continue
        P = np.asarray(st["pts"], float)
        a, e, hh = sc.coords(P)
        new = dict(lk)
        new["pts"] = [[round(float(a[i]), 2), round(float(e[i]), 2), round(float(hh[i]), 4)] for i in range(len(P))]
        if st.get("handles"):
            H = []
            for hd in st["handles"]:
                if hd:
                    a1, e1, h1 = sc.coords(np.asarray(hd[:3]))
                    a2, e2, h2 = sc.coords(np.asarray(hd[3:]))
                    H.append([round(float(v), 4) for v in (a1, e1, h1, a2, e2, h2)])
                else:
                    H.append(None)
            new["handles"] = H
        else:
            new.pop("handles", None)
        for k, key in (("radius", 1.0), ("tilt", 0.0)):
            vals = st.get(k) or []
            if vals and any(abs(v - key) > 1e-4 for v in vals):
                new[k] = vals
            else:
                new.pop(k, None)
        for mk, v in (st.get("inputs") or {}).items():
            if mk in inv:
                if abs(float(v) - float(lk.get(inv[mk], LOCK_DEFAULTS.get(inv[mk], 0.0)))) > 1e-5:
                    new[inv[mk]] = round(float(v), 5)
        if new != lk:
            locks[n] = new
            changes[f"hair.{n}"] = "edited in the scene"
            log.append(f"hair lock {n}: edited in the scene")
    for n in got.get("__deleted__", []):
        if n in locks:
            locks.pop(n)
            changes[f"hair.{n}"] = "deleted in the scene"
            log.append(f"hair lock {n}: deleted in the scene")
    return changes
