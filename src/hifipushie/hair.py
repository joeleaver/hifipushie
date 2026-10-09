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
import os
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
    # the front edge not sunk (between generated front-row roots the sunk mass read as black pits along the hairline),
    # unless volume.edge_sink (0..1): a front lock laid on the hairline (drawn "to_hairline") covers the edge, and an
    # unsunk edge stood out under it as a dark lip (the band under the quiff)
    es = float(g["volume"].get("edge_sink", 0.0))
    depth = tw * tb * (es + (1 - es) * _ss(d_in / 0.006)) + FILL_SINK * (1 - tw) * tf
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
    "drawn": [],
    "drawn_under": True,  # an under clump between neighbours of a row: true, false, a sink (x thickness under the
    # row: 0.35 shows between the wedges, 1 is buried under the underlayer) or per row {stem: sink | false}
    "hairline_edge": None,  # {"inset": m (negative: tucked into the skin), "reach": m}: every drawn clump whose edge
    # comes within reach of the hairline lays that edge on it (the volume's rim showed between clump edges and skin)
    "tie": None,  # tied hair (hair_tied.py): {"at": [az, el], "out", "gather", "tail", "escape", "band"} or a list
    "loose": None,  # loose hair (hair_loose.py): grown all over the scalp, combed at the roots, then falling / standing:
    # {"length", "level", "spacing", "body", "lift", "stiff", "out", "back", "messy", "uneven", "ends", "fringe"}
    "noise": 0.3,
    "seed": 0,
    "centre": "head",  # without face landmarks (a kit-built head): the joint (or [x, y, z]) the scalp is measured from
}
LOOK = {"gap": "#221310", "lit": "#56352d", "sheen": "#86524a", "grey": "#9a948d", "roughness": 0.42,
        "sheen_amount": 0.45, "vary": 0.25, "grooves": 5, "groove_depth": 0.12, "anisotropic": 0.7,
        "edge": 0.55, "root": 0.12, "specular": 0.5, "band_shift": 0.25, "tip": "#7a5038", "tip_amount": 0.0,
        "band": "#23252b", "strand_relief": 0.6, "scalp_tint": 0.85, "grey_amount": 0.0, "grey_locks": 1.0, "eevee_gain": 1.6, "light": None, "card_gain": 1.0, "card_sat": 1.0, "card_grey": 0.5,
        "cycles_fit": None}  # band: a tie's colour; strand_relief: the cards' normal map  # edge: how far across a lock its edges darken; root: how far
# along the root darkens (0..1 of the length)
LOCK_KEYS = {"pts", "width", "thickness", "cup", "taper", "belly", "root", "twist", "flip", "grey", "radius", "tilt",
             "handles", "tier", "edge", "hand", "free", "space", "core", "strands"}
# free: 0..1, the lock hangs clear of the head (its underside is hair too, not the dark gap side); space "xyz": pts
# are metres from the head centre [x, y, z] (hair that leaves the head: a tail), not [az, el, h]; core: a polyline
# (same space) the lock's outward side faces away from (a tail's own axis); strands: this lock's own card numbers
MOD = {"width": "Width", "thickness": "Thickness", "cup": "Cup", "taper": "Taper", "belly": "Belly", "root": "Root",
       "twist": "Twist", "flip": "Flip", "grey": "Grey", "edge": "Edge", "free": "Free"}
LOCK_DEFAULTS = {"taper": 1.0, "belly": 0.3, "root": 0.6, "twist": 0.0, "flip": 0.0, "grey": 0.0, "cup": 0.002, "edge": 0.8,
                 "free": 0.0}
STYLES = ("locks", "cards", "strands")  # hair.style: solid sculpted locks (stylised), or strand cards (hair_cards.py)
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
    lm = {n: [float(x) for x in J[n]["pos"]] for n in J if n.startswith("lm_")}
    if all(n in J for n in need):
        j0 = np.array(lm["lm_jaw_0.L"])
        C = np.array([0.0, j0[1] + 0.01, lm["lm_brow_mid.L"][2] + 0.008])
    else:  # no base head (a kit-built creature): the head joint is the centre, the hairline by elevation angles
        cen = ((spec.get("hair") or {}).get("groom") or {}).get("centre", "head")
        if isinstance(cen, str):
            if cen not in J:
                raise HairError(f"hair needs the face landmarks {need} (a base head gives them) or a centre "
                                f"joint (groom.centre, default 'head')")
            C = np.asarray(J[cen]["pos"], float)
        else:
            C = np.asarray(cen, float)
        lm = {}
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
    if ((spec.get("base") or {}).get("body") or {}).get("source") == "human":  # (one mesh) GNM's ear canals and
        # inner surfaces are pockets inside the head: a ray from the centre came out into one 4 cm in (behind the
        # ear), and the locks rooted there hung down the neck. The first crossing into air that STAYS air for
        # POCKET m (the outermost crossing instead sent rays under the ear on to the shoulders: curtains of hair)
        k = max(1, int(round(POCKET / (ts[1] - ts[0]))))
        pad = np.concatenate([out, np.ones((len(out), k), bool)], 1)
        run = np.ones_like(out)
        for j in range(k + 1):
            run &= pad[:, j:j + out.shape[1]]
        i = np.where(run.any(1), np.argmax(run, 1), i)
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
    if g.get("tie"):
        from . import hair_tied
        try:
            hair_tied.params(g["tie"])
        except ValueError as e:
            raise HairError(str(e)) from None
    if g.get("loose"):
        from . import hair_loose
        try:
            hair_loose.params(g["loose"])
        except ValueError as e:
            raise HairError(str(e)) from None
    return _merge(GROOM, g)


POCKET = 0.012  # m: (one mesh) air this deep along a scalp ray is outside the head, not a pocket in it (an ear canal)
HAIRLINE_JOIN = 25.0  # deg of azimuth over which the default line past traced front_points eases onto their end


def hairline(sc: Scalp, g: dict) -> np.ndarray:
    """The hairline's elevation (degrees) at each whole degree of azimuth (360,), symmetric left/right: from the
    landmarks (front height in brow-to-nose units, temples receding, sideburns, clear of the ears, the nape)."""
    hl = g["hairline"]
    if hl.get("points"):
        ctrl = [(float(a), float(z)) for a, z in hl["points"]]
    elif "lm_brow_mid.L" not in sc.lm:  # no landmarks: elevations (degrees from the centre) per azimuth
        ea = float(hl.get("ear_az", 95))
        el = {k: float(hl.get(k, d)) for k, d in (("front_el", 35), ("temple_el", 40), ("sideburn_el", -5),
                                                   ("ear_el", 18), ("nape_el", -25))}
        pts = [(0, el["front_el"]), (ea - 55, el["temple_el"]), (ea - 30, el["temple_el"] - 12),
               (ea - 18, el["sideburn_el"]), (ea - 10, el["sideburn_el"]), (ea - 6, el["ear_el"]),
               (ea + 20, el["ear_el"]), (ea + 32, el["nape_el"] + 15), (180, el["nape_el"])]
        ctrl = [(a, float(sc.point(a, e, 0.0)[2])) for a, e in pts]
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
    if hl.get("front_points"):  # traced (e.g. from the reference through the matched camera): [[az, z], ...] over the
        fp = sorted((float(x), float(z)) for x, z in hl["front_points"])  # front; the rest of the line kept
        # ...eased onto the traced end (HAIRLINE_JOIN deg): joined as it was, the default temple stood ~4 mm off the
        # traced front's end and the hairline stepped up and down again at the temple corner (a notch in the edge)
        ca = np.array([c[0] for c in ctrl])
        cz = np.array([c[1] for c in ctrl])
        dz = fp[-1][1] - float(np.interp(fp[-1][0], ca, cz))
        ctrl = fp + [(a, z + dz * max(0.0, 1.0 - (a - fp[-1][0]) / HAIRLINE_JOIN)) for a, z in ctrl
                     if a > fp[-1][0] + 4]
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
    # volume.across: how much of the dome's height is gone over the upper sides (0.65: a crest down the middle; less, a
    # broad flat top like a side-swept cut's, where the top outline in the front view is a wide curve, not a peak)
    # volume.crest: where across the head (x, m, his left +) the top's crest runs: a quiff swept off a side part is
    # highest just across the part and falls away toward the swept side (0: down the middle)
    dome = vs + (dome - vs) * (1 - float(vol.get("across", 0.65))
                               * _ss((np.abs(P[..., 0] - sc.C[0] - float(vol.get("crest", 0.0))) - 0.02) / 0.06))
    topw = W[..., 0] + W[..., 1]
    side = W[..., 2] * float(vol["sides"]) + W[..., 3] * float(vol["back"]) + W[..., 4] * float(vol["nape"])
    tp = vol.get("taper")
    if tp:  # volume.taper {"from": el, "to": el, "floor": f}: sides and back full down to elevation `from` (deg),
        # easing to `floor` x their volume at `to`: short tapered sides and back under a full top (a back as full at
        # the nape as at the occiput reads as a bucket)
        e0, e1, fl = float(tp.get("from", 30.0)), float(tp.get("to", -15.0)), float(tp.get("floor", 0.35))
        side = side * (fl + (1 - fl) * _ss((np.asarray(el, float) - e1) / max(e0 - e1, 1e-6)))
    v = topw * dome + side
    xp = _part_x(g)
    if xp is not None:  # the combed-away side is fuller; the part side lies flatter
        sgn = 1.0 if xp >= 0 else -1.0
        # parting.flat: how much flatter the part side lies (top and side); parting.full: how much fuller the side
        # the hair is swept onto (a side-swept cut piles up over the far temple)
        pw = topw + W[..., 2]
        flat, full = float(g["parting"].get("flat", 0.22)), float(g["parting"].get("full", 0.0))
        v = v * (1 - flat * pw * _ss(sgn * (P[..., 0] - xp) / 0.03)) \
            * (1 + full * pw * _ss(-sgn * (P[..., 0] - xp + sgn * 0.02) / 0.05))
        # along the parting the volume goes down to the scalp: the roots on both sides grow out of it there, and
        # the part is a thin line of scalp and shadow between clumps (a dip left the volume as a smooth patch)
        # parting.front (m): the part's dip fades in over this far behind the front hairline, so the front roll stays
        # whole and the hairline one clean sweep (dipping right to the hairline it cut a V notch into the edge)
        pf = float(g["parting"].get("front", 0.015))
        fade = _ss(d_in / pf) if pf > 0 else 1.0
        v = v * (1 - float(g["parting"].get("depth", 0.9)) * fade
                 * _part(sc, g, az, el, float(g["parting"].get("width", 0.012))))
    # volume.ramp: how far back from the front hairline the top reaches its height (m): short, the front stands as a
    # wall and the front locks over it jut like a cap's peak; longer, the front face leans back (a quiff's wave)
    ramp = topw * float(vol.get("ramp", 0.028)) + (1 - topw) * (0.8 * v + 0.002)  # continuous: a switch creased the temples
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
    if pt.get("line"):  # a drawn/traced part: distance to its polyline on the scalp, faded in past its front end
        q = np.asarray(pt["line"], float)
        L = _catmull(sc.point(q[:, 0], q[:, 1], 0.0), 40)
        A, AB = L[:-1], L[1:] - L[:-1]
        sh = np.shape(az)
        X = P.reshape(-1, 3)
        best = np.full(len(X), np.inf)
        tf = np.zeros(len(X))
        cum = np.r_[0.0, np.cumsum(np.linalg.norm(AB, axis=1))]
        for k in range(len(A)):
            t = np.clip(((X - A[k]) @ AB[k]) / max(AB[k] @ AB[k], 1e-12), 0, 1)
            d = np.linalg.norm(X - (A[k] + t[:, None] * AB[k]), axis=1)
            m = d < best
            best[m], tf[m] = d[m], (cum[k] + t[m] * np.linalg.norm(AB[k]))
        # past the front end the distance keeps growing (t clipped): fades there by itself; soft at the back end
        fade = 1 - _ss((tf - cum[-1] + 0.015) / 0.015)
        return (np.exp(-(best / width) ** 2) * np.maximum(fade, 0.0)).reshape(sh) * _ss((np.asarray(el) - 20) / 10)
    yf = sc.C[1] - sc.r(0.0, 30.0) * np.cos(np.radians(30.0))
    along = _ss((P[..., 1] - yf + 0.005) / 0.01) * (1 - _ss((P[..., 1] - yf - float(pt.get("length", 0.1))) / 0.02))
    return along * np.exp(-((P[..., 0] - xp) / width) ** 2) * _ss((np.asarray(el) - 20) / 10)


def part_line(sc: Scalp, g: dict):
    """The parting as [[az, el], ...] from its front end back: groom.parting.line (e.g. carried from a traced
    reference), else a straight line at x = offset from the front of the scalp back `length`."""
    pt = g.get("parting") or {}
    if pt.get("line"):
        return np.asarray(pt["line"], float)
    xp = _part_x(g)
    if xp is None:
        return None
    y0 = -sc.r(0.0, 30.0) * np.cos(np.radians(30.0))
    t = np.linspace(0.0, float(pt.get("length", 0.1)), 6)
    a, e = top_to_azel(sc, np.stack([np.full(6, xp), y0 + t], 1))
    return np.stack([a, e], 1)


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


def grow(sc: Scalp, g: dict, col=None) -> dict:
    """The first pass of locks from the groom: {name: lock}. `col`: the body's collider (hair_loose.collider) for
    hair that falls off the head."""
    rng = np.random.default_rng(int(g.get("seed", 0)))
    noise = float(g.get("noise", 0.3))
    line = hairline(sc, g)
    xp = _part_x(g)
    locks = {}
    tiers = g["tiers"]
    names = {"big": "b", "crown": "c", "fill": "f", "edge": "e", "gap": "g", "clumps": "k"}
    if g.get("drawn"):  # the top drawn by hand (clumps on the top view), the rest grown round it
        locks.update(drawn(sc, g, g["drawn"]))
    if g.get("loose"):  # loose hair is the whole groom too (with drawn clumps and any tie: half up)
        from . import hair_loose
        locks.update(hair_loose.grow(sc, g, line, rng, col))
    if g.get("tie"):  # tied hair makes the whole groom (with any drawn clumps): no generated tiers under it
        from . import hair_tied
        locks.update(hair_tied.grow(sc, g, line, rng))
        return locks
    if g.get("loose"):
        return locks
    if tiers.get("strip"):
        locks.update(_strips(sc, g, line, tiers["strip"], rng))
    designed = bool((tiers.get("clumps") or {}).get("list")) or bool(g.get("drawn"))
    for tier in ("clumps", "big", "crown", "fill", "edge", "gap", "gap"):  # gaps twice: a second look at what's bare
        td = tiers.get(tier)
        if not td or (designed and tier in ("big", "crown")):  # designed clumps replace the laid-out top
            continue
        if tier == "clumps" and not td.get("list"):
            continue
        kind = {"crown": "big", "gap": "fill", "clumps": "big"}.get(tier, tier)
        heading = None  # crown: big locks laid by spacing; gap: fill locks
        if tier == "gap":
            names["gap"] = "g" if not any(n.startswith("g") for n in locks) else "h"
        w0, t0 = float(td.get("width", 0.055)), float(td["thickness"])
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
        elif tier == "clumps":  # the designer's big clumps: [az, el, heading deg, length m, width m] each
            arr = np.asarray(td["list"], float)
            az, el, heading = arr[:, 0], arr[:, 1], arr[:, 2]
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
        if tier == "clumps":
            L, W_, size = arr[:, 3], arr[:, 4], np.ones(len(az))
            T_ = t0 * W_ / 0.055
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
        paths, sides = _walk(sc, g, line, az, el, L, T_, lift, away, rng, kind, flat=flat, heading=heading)
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


def _nape_frame(sc: Scalp, td: dict | None = None):
    """Short back and sides are combed back and down toward the nape: flow lines are the head's sections through a
    point under the nape (N) and an axis from it toward the forehead. Returns N, axis, e1, e2. td["nape"] ([x, y, z]
    from the head centre) moves N: long hair falls, so its streams meet far below the head (at the default nape point
    they gathered into a tail)."""
    N = sc.C + np.asarray((td or {}).get("nape", [0.0, 0.06, -0.13]), float)
    axis = _unit(np.array([0.0, -0.9, 0.45]) if "nape" not in (td or {}) else
                 sc.C + np.array([0.0, -0.115, 0.0567]) - N)  # toward the forehead from N
    e1 = _unit(np.cross(axis, [1.0, 0, 0]))
    return N, axis, e1, np.cross(axis, e1)


def stream_angle(sc: Scalp, P, td: dict | None = None):
    """Each point's flow line: its angle round the nape axis (radians; constant along a combed-back stream)."""
    N, axis, e1, e2 = _nape_frame(sc, td)
    Q = np.asarray(P, float) - N
    t = Q - (Q @ axis)[..., None] * axis
    return np.arctan2(t @ e2, t @ e1)


def _strips(sc: Scalp, g: dict, line, td: dict, rng) -> dict:
    """The sides and back as long flat locks laid side by side along the combed streams (tier "strip"): each runs
    from under the top's locks (its root hidden by them) down the stream to just inside the hairline, flush with the
    groom's volume, overlapping its neighbours a little, narrowing as the streams converge on the nape. So the whole
    head is locks with one flow: no mass surface shows, and the outline stays the volume's (the fill tier's short
    locks either broke it or read as scales)."""
    N = _nape_frame(sc, td)[0]
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
    ang = stream_angle(sc, P, td)
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
                 - (0.8 * t0 * _ss((u - 0.8) / 0.2) if last and not td.get("hang") else 0.0))  # the last tucks in
            h = np.maximum(h, 0.2 * t0 * _ss(u / 0.2) - 0.6 * t0 * (1 - _ss(u / 0.2)))
            path = sc.point(sa[sel], se[sel], h)
            hang = float(td.get("hang", 0.0))
            if last and hang > 0:  # longer hair: past the hairline the stream falls, off the head and down
                path = _hang(sc, path, hang, td, rng, k)
            c = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
            L = c[-1]
            kpts = 5 if L > 0.06 else 4
            if hang > 0 and last:
                kpts = int(np.clip(L / 0.025, 5, 12))  # waves need control points
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
    if td.get("where"):  # only the regions asked (a drawn top is left to its clumps: widen them, don't add small ones)
        Wg = weights(A, E, d)
        bare &= Wg[..., [REGIONS.index(r) for r in td["where"]]].sum(-1) > 0.5
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


def _hang(sc: Scalp, path, hang: float, td: dict, rng, k: int):
    """A strip's end carried on past the hairline: it leaves the head along its last heading, turns down under
    gravity and falls `hang` m, kept off the body (the scalp model's surface + a clearance) and waved side to side
    (`wave`: {"amount", "length"} m, phase per strip)."""
    P = [p for p in np.asarray(path, float)]
    d = _unit(P[-1] - P[-2])
    step = 0.008
    n = int(hang / step)
    wv = td.get("wave") or {}
    amp, lam = float(wv.get("amount", 0.0)), float(wv.get("length", 0.06))
    ph = rng.uniform(0, 2 * np.pi)
    clear = float(td.get("clearance", 0.004))
    base = [P[-1].copy()]
    for i in range(n):
        f = min(1.0, (i + 1) / 6)
        d = _unit((1 - f) * d + f * np.array([0.0, 0.0, -1.0]) + 0.15 * _unit(np.r_[(P[-1] - sc.C)[:2], 0.0]))
        q = base[-1] + d * step
        a, e, hh = sc.coords(q[None])
        if hh[0] < clear:  # never into the head, neck or shoulders
            q = sc.point(a, e, np.array([clear]))[0]
        base.append(q)
    base = np.array(base[1:])
    if amp > 0 and len(base) > 2:
        s_ = np.arange(1, len(base) + 1) * step
        side = _unit(np.cross(np.array([0.0, 0.0, 1.0]), _unit(np.r_[(base[0] - sc.C)[:2], 0.0])))
        base = base + (amp * np.minimum(s_ / lam, 1.0) * np.sin(2 * np.pi * s_ / lam + ph))[:, None] * side
    return np.vstack([np.asarray(path, float), base])


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


def _walk(sc: Scalp, g: dict, line, az, el, L, T, lift, away, rng, tier, n=24, flat=None, heading=None):
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
        if heading is not None:  # a designed clump keeps its heading on the surface: 0 back, 90 his right, 180 fwd
            n = _unit(q - sc.C)
            v = np.array([0.0, 1.0, 0.8])  # back over the crown (from the forehead, that is up: +Y alone vanished there)
            back = _unit(v - (n @ v)[:, None] * n)
            right = _unit(np.cross(n, back))  # n x back: toward his right (-X) on the top
            hr = np.radians(heading)[:, None]
            return np.cos(hr) * back + np.sin(hr) * right
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
            h = h + (TIP_STEP if heading is None else 0.1) * T * _ss((x - 0.55) / 0.45) * (1 - 0.5 * sf) * (1 - flat)  # designed
            # clumps lie calm (a lifted tip on a long clump curled up like a claw)
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
    keys = {"groom", "locks", "look", "cap", "stage", "part", "filler", "removed", "export", "style", "strands"}
    bad = set(h) - keys
    if bad:
        raise HairError(f"hair: unknown keys {sorted(bad)} (have {', '.join(sorted(keys))})")
    if h.get("stage", "locks") not in ("mass", "locks"):
        raise HairError('hair stage is "mass" (the groom\'s volume as one shell) or "locks"')
    bad = set(h.get("look") or {}) - set(LOOK)
    if bad:
        raise HairError(f"hair look: unknown keys {sorted(bad)} (have {', '.join(sorted(LOOK))})")
    groom_params(spec)
    if h.get("style", "locks") not in STYLES:
        raise HairError(f'hair style is one of {", ".join(STYLES)}')
    if h.get("strands") is not None:
        from . import hair_cards
        try:
            hair_cards.strands_of(spec)
        except ValueError as e:
            raise HairError(str(e)) from None
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


def merge_patch(a, b):
    """b merged into a key by key (objects merge, null deletes, anything else replaces). A list of named objects
    (the drawn clumps) patched with an object {name: patch | null} merges by name: one clump's numbers change, null
    drops it, a new name is appended (`"*"` / `"sweep*"` patterns patch every match)."""
    if isinstance(a, list) and isinstance(b, dict) and all(isinstance(x, dict) and x.get("name") for x in a):
        from fnmatch import fnmatch
        out = [copy.deepcopy(x) for x in a]
        for k, v in b.items():
            hit = [i for i, x in enumerate(out) if fnmatch(x["name"], k)]
            if v is None:
                out = [x for i, x in enumerate(out) if i not in hit]
            elif hit:
                for i in hit:
                    out[i] = merge_patch(out[i], v)
            elif not any(ch in k for ch in "*?["):
                out.append({"name": k, **copy.deepcopy(v)})
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            if v is None:
                out.pop(k, None)
            else:
                out[k] = merge_patch(a.get(k), v)
        return out
    return copy.deepcopy(b)


def groom(name: str, replace: bool = False, note: str = "", patch: dict | None = None,
          stage: str | None = None) -> dict:
    """Grow the first pass of locks from spec["hair"]["groom"] and save them. Locks a person or an edit changed
    (their names not starting with the tier letters b/f/e + digits) and hand-shaped locks (`"hand": true`: every lock
    edited or added in Blender comes back with it from scene.pull) are kept unless replace; locks deleted in Blender
    (`hair.removed`) aren't grown again."""
    spec = store.load(name)
    h = spec.setdefault("hair", {})
    if patch:
        h["groom"] = merge_patch(h.get("groom") or {}, patch)
    if stage is not None:
        h["stage"] = stage
    validate(spec)
    sc = scalp(name, spec)
    g = groom_params(spec)
    col = None
    if g.get("loose"):
        from . import hair_loose
        col = hair_loose.collider(name, spec, sc)
    new = grow(sc, g, col)
    old = h.get("locks") or {}
    if replace:
        h.pop("removed", None)
    else:
        new = {n: lk for n, lk in new.items() if n not in set(h.get("removed") or [])}
    keep = {} if replace else {n: lk for n, lk in old.items()
                               if lk.get("hand") or (not (n[:1] in "bcfesghk" and n[1:].rstrip("abcdefgh").isdigit())
                                                     and lk.get("tier") not in ("drawn", "tie", "loose"))}
    h["locks"] = {**new, **keep}
    v = store.save(name, spec, note or f"hair: grew {len(new)} locks from the groom")
    tiers: dict = {}
    for n, lk in new.items():
        if n not in keep:  # (a kept lock of the same name wins)
            tiers[lk["tier"]] = tiers.get(lk["tier"], 0) + 1
    return {"version": v, "locks": len(h["locks"]), "grown": tiers, "kept": sorted(keep),
            "not_regrown": sorted(set(h.get("removed") or []))}


def hierarchy(spec: dict, sc: Scalp) -> dict:
    """The groom's size hierarchy, the artists' 6-3-1 (big shapes ~60% of the area, medium ~30%, small ~10%): each
    lock's area (width x length x 0.65, lens and taper) by its width against the widest locks (90th percentile):
    big >= 0.7, medium 0.4-0.7, small < 0.4. Under-layer locks ("_under") don't count (they're hidden). Also how far
    widths spread (coefficient of variation: ~0 = every lock the same, the "uniform locks" look)."""
    locks = {n: lk for n, lk in (hair_of(spec).get("locks") or {}).items() if not n.endswith("_under")}
    if not locks:
        return {}
    W, A = [], []
    for lk in locks.values():
        P = lock_world(sc, lk, lk["pts"])
        L = float(np.linalg.norm(np.diff(_catmull(P, 24), axis=0), axis=1).sum())
        W.append(float(lk["width"]))
        A.append(float(lk["width"]) * L * 0.65)
    W, A = np.array(W), np.array(A)
    ref = np.percentile(W, 90)
    r = W / max(ref, 1e-9)
    tot = max(A.sum(), 1e-12)
    big, med = A[r >= 0.7].sum() / tot, A[(r >= 0.4) & (r < 0.7)].sum() / tot
    return {"big": round(float(big), 2), "medium": round(float(med), 2), "small": round(max(0.0, float(1 - big - med)), 2),
            "width_cv": round(float(W.std() / max(W.mean(), 1e-9)), 2), "locks": len(W),
            "widest_mm": round(float(ref * 1000), 1)}


def lock_hash(lk: dict, sc: Scalp) -> str:
    return hashlib.sha1(json.dumps([lk, sc.C.tolist(), float(sc.R.sum())], sort_keys=True,
                                   default=float).encode()).hexdigest()[:12]


def lock_world(sc: Scalp, lk: dict, pts):
    """A lock's points (its own space: [az, el, h] on the head, or "space": "xyz" metres from the head centre) in
    world metres."""
    pts = np.asarray(pts, float).reshape(-1, 3)
    if lk.get("space") == "xyz":
        return sc.C + pts
    return sc.point(pts[:, 0], pts[:, 1], pts[:, 2])


def lock_address(sc: Scalp, lk: dict, P) -> list:
    """World points as the lock stores them."""
    P = np.asarray(P, float).reshape(-1, 3)
    if lk.get("space") == "xyz":
        return [[round(float(v), 4) for v in q] for q in P - sc.C]
    a, e, hh = sc.coords(P)
    return [[round(float(a[i]), 2), round(float(e[i]), 2), round(float(hh[i]), 4)] for i in range(len(P))]


def resolve(spec: dict, sc: Scalp) -> list:
    """The locks as Blender wants them: world control points, handles, radius, tilt and modifier inputs."""
    out = []
    for n, lk in sorted((hair_of(spec).get("locks") or {}).items()):
        W = lock_world(sc, lk, lk["pts"])
        H = None
        if lk.get("handles"):
            H = []
            for hd in lk["handles"]:
                if hd:
                    a, b = lock_world(sc, lk, [hd[:3], hd[3:]])
                    H.append([float(v) for v in list(a) + list(b)])
                else:
                    H.append(None)
        inputs = {MOD[k]: float(lk.get(k, LOCK_DEFAULTS.get(k, 0.0))) for k in MOD}
        inputs["Seed"] = (int(hashlib.md5(n.encode()).hexdigest()[:6], 16) % 1000) / 1000.0
        inputs["Centre"] = [float(v) for v in sc.C]
        out.append({"name": n, "pts": W.tolist(), "handles": H, "radius": lk.get("radius"), "tilt": lk.get("tilt"),
                    "inputs": inputs, "hash": lock_hash(lk, sc), "free": float(lk.get("free", 0.0)),
                    "strands": lk.get("strands"), "tier": lk.get("tier"),
                    "core": lock_world(sc, lk, lk["core"]).tolist() if lk.get("core") else None})
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


FOLD_LIMIT = 1.0  # in-plane bend x half width: at 1 the lock's inner edge runs backwards (folds over itself)


def folds(sc: Scalp, locks: list, n: int = 80) -> dict:
    """Locks that fold over themselves: where the spine turns within the lock's flat side tighter than its half width
    (in-plane curvature x half width >= 1), the inner edge runs backwards and the lens crumples into overlapping
    flakes. {lock: [ratio, u]} for the worst point of every lock over FOLD_LIMIT (u = 0 root .. 1 tip)."""
    out = {}
    for lk in locks:
        S = _catmull(lk["pts"], n)
        d = np.gradient(S, axis=0)
        ds = np.maximum(np.linalg.norm(d, axis=1), 1e-9)
        tg = d / ds[:, None]
        nr = _unit(S - sc.C)
        nr = _unit(nr - (nr * tg).sum(1, keepdims=True) * tg)
        u = np.linspace(0, 1, n)
        if lk.get("tilt"):
            ti = np.interp(u, np.linspace(0, 1, len(lk["tilt"])), lk["tilt"])[:, None]
            nr = nr * np.cos(ti) + np.cross(tg, nr) * np.sin(ti)
        b = _unit(np.cross(nr, tg))
        k = (np.gradient(tg, axis=0) / ds[:, None] * b).sum(1)  # in-plane curvature (1/m)
        inp = lk["inputs"]
        half = 0.5 * inp["Width"] * lock_width(inp, u)
        r = np.abs(k) * half
        r[[0, -1]] = 0.0  # the ends' one-sided differences
        i = int(np.argmax(r))
        if r[i] >= FOLD_LIMIT:
            out[lk["name"]] = [round(float(r[i]), 2), round(float(u[i]), 2)]
    return out


ROOT_END_MM = 15.0  # a root end wider than this where it rises out of the layer reads as a blunt end


def root_ends(sc: Scalp, g: dict, locks: list, n: int = 80) -> dict:
    """How blunt each lock's root end is where it comes out of the layer: the lens's width (mm) x the steepness of its
    rise (rise over run, at most 1) at the first point
    along it whose back stands ROOT_RISE above the underlayer there. A wide end standing up shows its cut: a crescent
    fin from the side where rows start at a parting, a row of scales along a hairline. {lock: mm} over ROOT_END_MM,
    widest first (lower `root` and raise `climb` on those clumps: a narrow root grows out of the layer)."""
    line = hairline(sc, g)
    out = {}
    for lk in locks:
        if lk["name"].endswith("_under"):
            continue
        S = _catmull(lk["pts"], n)
        u = np.linspace(0, 1, n)
        a, e, h = sc.coords(S)
        H, d_in = envelope(sc, g, line, a, e)
        U = under(g, H, a, e, d_in)
        inp = lk["inputs"]
        f = lock_width(inp, u)
        top = h + 0.5 * inp["Thickness"] * f
        up = np.nonzero((top - U > ROOT_RISE) & (u < 0.5))[0]
        if not len(up):
            continue
        k = up[0]
        below = np.nonzero(top[:k] - U[:k] <= 0)[0]  # where its back was last under the layer
        j = below[-1] if len(below) else 0
        run = float(np.linalg.norm(np.diff(S[j:k + 1], axis=0), axis=1).sum()) if k > j else 0.0
        steep = min(1.0, (top[k] - U[k]) / max(run, 1e-6))  # 1: a wall; a long low ramp shows no cut
        w = 1000 * inp["Width"] * f[k] * steep
        if w > ROOT_END_MM:
            out[lk["name"]] = round(float(w), 1)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


ROOT_RISE = 0.003  # m
FIN_MM = 3.0  # an edge standing this much more than the lock's own thickness over the layer reads as a fin


def fins(sc: Scalp, g: dict, locks: list, n: int = 60) -> dict:
    """Lock edges standing up off the hair under them: for each lock, the highest of its two lens edges (with the
    tilt and cup) over the underlayer there, less the lock's own thickness (a lock lying on another one stands about
    a thickness up), over u 0.1-0.95. {lock: [mm over, u]} above FIN_MM, worst first. A wide flat lock whose path
    crosses the volume's curve, or stacked on rows that lie high, stands on one edge (the top rows' fins in the side
    view): narrow it, lower its `lie`, or move it onto the curve."""
    line = hairline(sc, g)
    out = {}
    for lk in locks:
        S = _catmull(lk["pts"], n)
        u = np.linspace(0, 1, n)
        tg = _unit(np.gradient(S, axis=0))
        nr = _unit(S - sc.C)
        nr = _unit(nr - (nr * tg).sum(1, keepdims=True) * tg)
        if lk.get("tilt"):
            ti = np.interp(u, np.linspace(0, 1, len(lk["tilt"])), lk["tilt"])[:, None]
            nr = nr * np.cos(ti) + np.cross(tg, nr) * np.sin(ti)
        b = _unit(np.cross(nr, tg))
        inp = lk["inputs"]
        f = lock_width(inp, u)
        best = np.full(n, -np.inf)
        for c in (-1.0, 1.0):
            E = S + (f * c * 0.5 * inp["Width"])[:, None] * b - (f * inp["Cup"])[:, None] * nr
            a, e, h = sc.coords(E)
            H, d = envelope(sc, g, line, a, e)
            best = np.maximum(best, h - under(g, H, a, e, d))
        x = (best - inp["Thickness"]) * 1000
        x[(u < 0.1) | (u > 0.95)] = -np.inf
        k = int(np.argmax(x))
        if x[k] > FIN_MM:
            out[lk["name"]] = [round(float(x[k]), 1), round(float(u[k]), 2)]
    return dict(sorted(out.items(), key=lambda kv: -kv[1][0]))


LIFT_RAMP = 0.03  # m: a lift grows to its full height this far in from the hairline


def lift(spec: dict, sc: Scalp, by: dict, fill: bool = False) -> tuple:
    """(new spec, report): the whole groom made fuller (or closer) by region, as a barber's "more at the sides":
    by = {region: m} (REGIONS: front, top, sides, back, nape). Every lock point on the head ([az, el, h] locks; their
    handles too) rises by the region weights there (`weights`, the volume's own) x those metres, and groom.volume
    takes the same amounts, so the underlayer stays under the locks. Hand locks stay hand locks (their shapes are
    kept, only lifted); locks in "xyz" space are left alone and listed.
    fill=True (strand grooms): each lock also grows THICKER by twice its mean lift, so its lens still reaches down to
    where it lay and its strands fill the new volume from the scalp up (lifted alone, a strand groom's sides stood off
    the head as a shell over the short scalp layer; solid locks lifted alone read as a stiff helmet)."""
    import copy as _copy
    bad = set(by) - set(REGIONS)
    if bad:
        raise HairError(f"hair lift: unknown regions {sorted(bad)} (have {', '.join(REGIONS)})")
    out = _copy.deepcopy(spec)
    hs = out.setdefault("hair", {})
    g = groom_params(out)
    line = hairline(sc, g)
    vals = np.array([float(by.get(r, 0.0)) for r in REGIONS])

    def dh(az, el):
        az, el = np.asarray(az, float), np.asarray(el, float)
        d_in = inside(sc, line, az, el)
        # eased in from the hairline (LIFT_RAMP): lifted at the line itself, the hair's edge stood off the skin as
        # a shelf with a dark gap under it at the temples
        return (weights(az, el, d_in) @ vals) * _ss(d_in / LIFT_RAMP)

    moved, skipped, mx = 0, [], 0.0
    for n, lk in (hs.get("locks") or {}).items():
        if lk.get("space") == "xyz":
            skipped.append(n)
            continue
        P = np.asarray(lk["pts"], float).reshape(-1, 3)
        d_ = dh(P[:, 0], P[:, 1])
        P[:, 2] += d_
        lk["pts"] = [[round(float(a), 2), round(float(e), 2), round(float(h), 4)] for a, e, h in P]
        if fill and float(np.mean(d_)) > 0:
            th0 = float(lk.get("thickness", LOCK_DEFAULTS.get("thickness", 0.004)))
            lk["thickness"] = round(th0 + 2.0 * float(np.mean(d_)), 5)
        mx = max(mx, float(np.abs(d_).max()))
        if lk.get("handles"):
            nh = []
            for hd in lk["handles"]:
                if hd:
                    q = np.asarray(hd, float).reshape(2, 3)
                    q[:, 2] += dh(q[:, 0], q[:, 1])
                    nh.append([round(float(v), 4) for v in q.ravel()])
                else:
                    nh.append(hd)
            lk["handles"] = nh
        moved += 1
    gr = hs.setdefault("groom", {})
    vol = gr.setdefault("volume", {})
    for r, v in zip(REGIONS, vals):
        if v:
            vol[r] = round(float(vol.get(r, GROOM["volume"][r])) + float(v), 5)
    return out, {"locks": moved, "skipped_xyz": skipped, "max_lift_mm": round(mx * 1000, 2),
                 "volume": {r: vol.get(r) for r in REGIONS}}


def trim(spec: dict, sc: Scalp, below: float, where=("sides", "back", "nape")) -> tuple:
    """(new spec, report): a barber's clean-up of the outline: every lock on the head ([az, el, h]) is cut where it
    runs more than `below` m outside the hairline (over the skin of the neck or past the sideburns) in the regions
    `where` (a point counts when its region weight there is over a half). The cut point is interpolated along the
    lock; per-point radius / tilt / handles are cut with it. Locks that would keep under two points are left whole
    and listed. A short back and sides: below 0.01 (strands fall past their lock's end by their own spread)."""
    import copy as _copy
    bad = set(where) - set(REGIONS)
    if bad:
        raise HairError(f"hair trim: unknown regions {sorted(bad)} (have {', '.join(REGIONS)})")
    out = _copy.deepcopy(spec)
    hs = out.setdefault("hair", {})
    line = hairline(sc, groom_params(out))
    wi = [REGIONS.index(r) for r in where]
    cut, kept, short = 0, 0, []
    for n, lk in (hs.get("locks") or {}).items():
        if lk.get("space") == "xyz":
            continue
        P = np.asarray(lk["pts"], float).reshape(-1, 3)
        d_in = inside(sc, line, P[:, 0], P[:, 1])
        w = weights(P[:, 0], P[:, 1], d_in)[:, wi].sum(1)
        over = (d_in < -below) & (w > 0.5)
        over[0] = False
        if not over.any():
            kept += 1
            continue
        k = int(np.argmax(over))  # the first point past the line: cut between k - 1 and k
        if k < 1:
            short.append(n)
            continue
        a, b = d_in[k - 1] + below, d_in[k] + below  # a >= 0 > b
        t = float(np.clip(a / max(a - b, 1e-9), 0.0, 1.0))
        end = P[k - 1] + t * (P[k] - P[k - 1])
        Q = np.r_[P[:k], end[None]]
        if len(Q) < 2 or np.linalg.norm(Q[-1] - Q[0]) < 1e-6:
            short.append(n)
            continue
        lk["pts"] = [[round(float(x), 2), round(float(y), 2), round(float(z), 4)] for x, y, z in Q]
        for key in ("radius", "tilt"):
            if isinstance(lk.get(key), list) and len(lk[key]) == len(P):
                v = lk[key]
                lk[key] = v[:k] + [round(float(v[k - 1] + t * (v[k] - v[k - 1])), 4)]
        if isinstance(lk.get("handles"), list) and len(lk["handles"]) == len(P):
            lk["handles"] = lk["handles"][:k] + [None]
        cut += 1
    return out, {"cut": cut, "untouched": kept, "too_short": short}


def lock_meshes(sc: Scalp, locks: list, n: int = 40, across: int = 7) -> tuple:
    """(V, F): every lock as a closed lens-section tube in numpy (its spine as Blender curves it, the lens across it
    sized and turned like the node group: lock_extents' outer face plus the cupped inner face). For quick renders and
    silhouettes without Blender; the material, flips and twists of the node group are not reproduced."""
    Vs, Fs, k = [], [], 0
    cs = np.linspace(-1, 1, across)
    for lk in locks:
        S = _catmull(lk["pts"], n)
        u = np.linspace(0, 1, n)
        tg = _unit(np.gradient(S, axis=0))
        nr = _unit(S - sc.C)
        nr = _unit(nr - (nr * tg).sum(1, keepdims=True) * tg)
        if lk.get("tilt"):
            ti = np.interp(u, np.linspace(0, 1, len(lk["tilt"])), lk["tilt"])[:, None]
            nr = nr * np.cos(ti) + np.cross(tg, nr) * np.sin(ti)
        b = _unit(np.cross(nr, tg))
        inp = lk["inputs"]
        f = lock_width(inp, u)[:, None]
        ring = []  # round the lens: the outer face from one edge to the other, then the inner face back
        for side in (1.0, -1.0):
            for c in (cs if side > 0 else cs[::-1][1:-1]):
                sy = side * np.sqrt(max(1 - c * c, 0.0)) ** 0.8
                ring.append(S + f * (c * 0.5 * inp["Width"] * b + (sy * 0.5 * inp["Thickness"] - inp.get("Cup", 0.0) * c * c) * nr))
        R = np.stack(ring, 1)  # (n, m, 3)
        m = R.shape[1]
        idx = k + np.arange(n * m).reshape(n, m)
        a, b_, c_, d_ = idx[:-1, :], idx[1:, :], np.roll(idx[1:, :], -1, 1), np.roll(idx[:-1, :], -1, 1)
        Fs.append(np.stack([a, b_, c_, d_], -1).reshape(-1, 4))
        Vs.append(R.reshape(-1, 3))
        k += n * m
    if not Vs:
        return np.zeros((0, 3)), np.zeros((0, 4), int)
    return np.concatenate(Vs), np.concatenate(Fs)


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
        z0 = (sc.lm["lm_brow_mid.L"][2] if "lm_brow_mid.L" in sc.lm else float(sc.C[2])) + 0.02
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
             extra=None, ease: float = 0.0):
    """The scalp inside the hairline pushed out: the dark underlayer (height m) or, mass=True, the groom's whole
    volume (stage a). Its edge dives under the skin just outside the hairline, so the line is crisp."""
    line = hairline(sc, g)
    A = np.arange(0.0, 360.0, step)
    # rows follow the hairline: per column, two rows just outside it (the edge dives under the skin), one ON it, then
    # evenly up to the pole (a hole there read as a groove). On a fixed elevation grid the edge was a staircase of
    # cells crossing the line: fine serrations all along the hairline, read as a torn edge in close-ups
    la = _line_at(line, A)
    n = int(np.ceil((90.0 - la.min()) / step))
    t = np.linspace(0.0, 1.0, n + 1)
    AA = np.repeat(A[:, None], n + 3, 1)
    dive = min(step, 1.0)  # (a coarse cap, for exports, still dives just outside the line)
    EE = np.concatenate([(la - 2.5 * dive)[:, None], (la - 1.2 * dive)[:, None],
                         la[:, None] + t[None, :] * (90.0 - la)[:, None]], 1)
    if mass:
        H, d_in = envelope(sc, g, line, AA, EE)
        if sunk:
            H0 = H
            H = under(g, H, AA, EE, d_in)
            if extra is not None:  # the filler under the partings: where locks part at the outline, the sunk
                H = _silhouette_fill(sc, AA, EE, H, d_in, extra, cap=H0)  # underlayer rises to close the dent (only there)
        if ease > 0:  # the volume comes up from the hairline over `ease` m (a far tier's cap: at full height from
            H = H * (0.3 + 0.7 * _ss(d_in / ease))  # the line it was a thick brim over the forehead)
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


def job(name: str, spec: dict | None = None, only=None, budget: int | None = None, cap_step: float = 1.0,
        count: int | None = None) -> dict:
    """What Blender needs to show the hair: the locks, the cap (or the mass), the material. `only`: lock names or
    fnmatch patterns ("sweep*") to show alone on the underlayer (finding which locks make a patch)."""
    spec = store.load(name) if spec is None else spec
    h = hair_of(spec)
    if not h:
        return {}
    sc = scalp(name, spec)
    g = groom_params(spec)
    tmp = Path(tempfile.mkdtemp(prefix="hifipushie-hair-"))
    stage = h.get("stage", "locks")
    if isinstance(budget, str) and budget in CARD_TIERS:
        cap_step = float(CARD_TIERS[budget]["cap_step"])
    locks = [] if stage == "mass" else resolve(spec, sc)
    if isinstance(budget, str) and "cap_step" in SHORT_TIERS.get(budget, {}) and g.get("loose") and locks:
        # a short cut's cap is a smooth dome under its picture: at the long tiers' step it took 4,400 of a main
        # tier's 8,000 triangles and left its cards 4 triangles each (shards poking out of a swim cap)
        ln_ = [float(np.linalg.norm(np.diff(np.asarray(k_["pts"], float), axis=0), axis=1).sum()) for k_ in locks]
        if float(np.mean(ln_)) < MASS_MIN:
            cap_step = float(SHORT_TIERS[budget]["cap_step"])
    if only:
        from fnmatch import fnmatch
        pats = [only] if isinstance(only, str) else list(only)
        locks = [lk for lk in locks if any(fnmatch(lk["name"], q) for q in pats)]
    far = isinstance(budget, str) and CARD_TIERS.get(budget, {}).get("cap") == "mass"  # (a far tier's cap IS the
    # hair on the head: the groom's full volume, not the layer under its locks)
    V, F = cap_mesh(sc, g, float(h.get("cap", 0.002)), mass=True, sunk=stage != "mass" and not far, step=cap_step, ease=0.035 if far else 0.0,
                    extra=lock_extents(sc, locks) if (locks and h.get("filler")) else None)
    extra = {k: v for k, v in streams(sc, g, V).items() if k == "tangent"} if stage != "mass" else {}  # (the
    # sawtooth clumps on the underlayer aliased into jagged stripes: the strips carry the clumps now)
    if stage != "mass":  # the parting is a line of shadow: the underlayer there takes the gap colour
        va, ve, _ = sc.coords(V)
        pw = _part(sc, g, va, ve, 2 * float(g["parting"].get("width", 0.012)))
        extra["across"] = (0.45 + 0.55 * np.clip(pw * 1.5, 0, 1)).astype(np.float32)
    np.savez(tmp / "cap.npz", verts=V, faces=F, **extra)
    out = {"locks": locks, "cap": str(tmp / "cap.npz"),
           "cap_kind": "mass" if stage == "mass" else "under", "look": {**LOOK, **(h.get("look") or {})},
           "centre": sc.C.tolist()}
    if h.get("style") == "cards" and stage != "mass":
        from . import hair_loose
        body = hair_loose.collider(name, spec, sc)
        colc = body if g.get("loose") else None
        out["cards"] = cards_job(sc, g, spec, locks, tmp, V, F, budget=budget, cap_step=cap_step, col=colc,
                                 clear_col=body)
    if h.get("style") == "strands" and stage != "mass":
        from . import hair_strands
        col = None
        if g.get("loose"):
            from . import hair_loose
            col = hair_loose.collider(name, spec, sc)
        out["strands"] = hair_strands.job(sc, g, spec, locks, tmp, count=count, col=col)
    return out


def card_cap(sc: Scalp, g: dict, S: dict, tiles: list, V, F, e0: float | None = None) -> dict:
    """The underlayer as a card mesh: it wears a dense strand tile whose ragged end lies along the hairline, so the
    hair's edge on the skin breaks up into strands over `strands.soft` m instead of ending on a line."""
    line = hairline(sc, g)
    az, el, _ = sc.coords(V)
    d_in = inside(sc, line, az, el)
    t = next(t for t in tiles if t["kind"] == "hairline")
    x = np.radians(az) * 0.09 / 0.03
    tan = streams(sc, g, V)["tangent"]
    tie = g.get("tie")
    if tie:  # tied hair runs to the tie: the cap's strands converge there (round the nearest tie's own direction)
        from . import hair_tied
        D = _unit(np.asarray(V, float) - sc.C)
        best = np.full(len(V), -2.0)
        for tp in hair_tied.params(tie):
            ax = dirs(*tp["at"])
            e1 = _unit(np.cross(ax, [0.0, 0.0, 1.0]))
            e2 = np.cross(ax, e1)
            c = D @ ax
            xa = np.arctan2(D @ e2, D @ e1) * 0.09 / 0.03
            toward = _unit(ax[None] - c[:, None] * D)
            x = np.where(c > best, xa, x)
            tan = np.where((c > best)[:, None], toward, tan)
            best = np.maximum(best, c)
    tri = np.abs((x % 2.0) - 1.0)
    # the tile's first 45% (single roots, then more, then the opaque base) laid over 3 x soft from the line in
    vt = 0.45 * np.clip(d_in / max(3 * float(S["soft"]), 1e-4), 0, 1)
    uv = np.stack([t["u0"] + (t["u1"] - t["u0"]) * tri, 1 - vt], 1)
    F = np.asarray(F)
    tris = np.concatenate([F[:, [0, 1, 2]], F[:, [0, 2, 3]]])
    chart = next((t_ for t_ in tiles if t_["kind"] == "cap"), None)
    if chart is not None and e0 is not None:  # the cap wears the scalp chart: its own hair, drawn where it lies
        u = (az % 360) / 360.0
        vv = np.clip((el - e0) / (90.0 - e0), 0.0, 1.0)
        V, tan = np.asarray(V, float), np.asarray(tan, float)
        wrap = np.ptp(u[tris], axis=1) > 0.5  # faces across the azimuth seam: their low-u corners get u + 1
        if wrap.any():
            lo = np.unique(tris[wrap][u[tris[wrap]] < 0.5])
            new = len(V) + np.arange(len(lo))
            remap = np.arange(len(V))
            remap[lo] = new
            tw_ = tris[wrap]
            tris[wrap] = np.where(u[tw_] < 0.5, remap[tw_], tw_)
            V, tan = np.vstack([V, V[lo]]), np.vstack([tan, tan[lo]])
            u, vv = np.r_[u, u[lo] + 1.0], np.r_[vv, vv[lo]]
            az, el = np.r_[az, az[lo]], np.r_[el, el[lo]]
        uv = np.stack([chart["u0"] + (chart["u1"] - chart["u0"]) * np.clip(u, 0.0, 1.0), vv], 1)
    n = len(V)
    return {"verts": np.asarray(V, np.float32), "tris": tris.astype(np.int32), "uv": uv.astype(np.float32),
            "normal": sc.normal(az, el).astype(np.float32), "tangent": np.asarray(tan, np.float32),
            "col": np.full((n, 3), 0.9, np.float32), "along": np.full(n, 0.5, np.float32),
            "layer": np.full(n, -1.0, np.float32), "card": np.zeros(n, np.int32)}


def baby_locks(sc: Scalp, g: dict, S: dict, seed: int = 0) -> list:
    """Baby hairs: short fine locks rooted just inside the hairline all the way round, lying on the skin at every
    angle from along the line to straight out over it (resolved locks, for hair_cards)."""
    n_cm = float(S.get("baby", 0.0))
    if n_cm <= 0:
        return []
    line = hairline(sc, g)
    rng = np.random.default_rng(seed + 31)
    a = np.arange(0.0, 360.0, 0.5)
    L = sc.point(a, _line_at(line, a), 0.0)
    seg = np.linalg.norm(np.diff(L, axis=0, append=L[:1]), axis=1)
    cum = np.r_[0.0, np.cumsum(seg)]
    out = []
    for k, d in enumerate(np.arange(0.0, cum[-1], 0.025 / n_cm)):  # (the soft line itself is painted in the cap's
        # chart: cards only add stray hairs over it; one a cm overlapped into smudges)
        az = float(np.interp(d + rng.uniform(-0.3, 0.3) * 0.01 / n_cm, cum, np.r_[a, 360.0])) % 360
        el = float(_line_at(line, az))
        r = float(sc.r(az, el))
        de, da = np.degrees(0.002 / r), np.degrees(0.002 / max(r * np.cos(np.radians(el)), 0.02))
        gn = float(inside(sc, line, az, el + de) - inside(sc, line, az, el - de))  # which way is into the hair
        ge = float(inside(sc, line, az + da, el) - inside(sc, line, az - da, el))
        # most lie back into the hair (they soften the edge), a quarter stray out over the skin
        stray = rng.uniform() < 0.25
        th = np.arctan2(ge, gn) + (np.pi + rng.uniform(-1.0, 1.0) if stray else rng.normal(0, 0.8))
        ln = rng.uniform(0.008, 0.016) if stray else rng.uniform(0.015, 0.035)
        pts = []
        for f in (-0.12, 0.3, 0.65, 1.0):
            e2 = el + np.degrees(np.cos(th) * ln * f / r) + de * 1.5
            a2 = az + np.degrees(np.sin(th) * ln * f / max(r * np.cos(np.radians(el)), 0.02))
            pts.append(sc.point(a2, e2, 0.0012 + 0.002 * max(f, 0.0)))
        out.append({"name": f"baby{k}", "pts": np.asarray(pts).tolist(), "handles": None, "radius": None, "tilt": None,
                    "inputs": {"Width": rng.uniform(0.012, 0.02), "Thickness": 0.001, "Cup": 0.0, "Taper": 0.3,
                               "Belly": 0.3, "Root": 0.8, "Twist": 0.0, "Flip": 0.0},
                    "strands": {"layers": 1, "flyaway": 0.0, "wave": 0.0}, "free": 0.0, "core": None, "kind": "baby"})
    return out


# Card budgets by what the hair is for (triangles for the whole hair: cards, cap, baby hairs, tie). Epic's Hair Card
# Generator tutorial spends ~54k on a hero's LOD 0 in five layers (coverage 4%, mid 14%, top 46%, fly-aways 18%, short
# hairs 18%); a game character whose whole body is ~46k can't. The layers below are ours: 0 = the opaque coverage
# (dense / hairline tiles), 1 = mid, 2+ = top and break-up, fly-aways and baby hairs on top; the cap is the scalp chart.
# group: how big a clump of strands one card stands for (hair_cards.clump_cards): a lower tier has FEWER, WIDER cards
# from bigger clumps, never the same thin cards thinned out; "free" = only hair off the head gets cards, the cap
# (the scalp chart) and the tail's core carry the rest.
_CHARTS: dict = {}  # the last short chart baked (every tier of an export wears the same one)
MASS_MIN = 0.06  # m: loose hair shorter than this (mean lock length) gets no mass shell under its cards
# A SHORT cut (loose hair under MASS_MIN) as game artists build it: the cap, wearing the scalp chart with EVERY strand
# of the groom drawn where it lies (1 texel a strand at a 2048 chart: ~0.3 mm), carries the look; over it only a
# sparse layer of cards for what stands off the head (the lifted front, the silhouette's breakup), each on a tile of
# many fine strands with soft tips and no opaque base, plus single-hair cards along the hairline. Cards cut one per
# clump and worn on the dense tile read as torn paper / leaf litter at bust distance (Garrett's crop).
SHORT_TIERS = {"hero": {"triangles": 16000, "cap_step": 6.0, "group": "pair", "layers": 2, "baby": 0.0, "fly": 2},
               "main": {"triangles": 8000, "cap_step": 7.5, "group": "pair", "layers": 1, "baby": 0.0, "fly": 1},
               "npc": {"triangles": 4000, "cap_step": 10.0, "group": "lock", "layers": 1, "baby": 0.0, "fly": 0},
               "far": {"triangles": 1500, "group": "lock", "layers": 1, "baby": 0.0, "fly": 0}}
SHORT_TOP = 1.3  # x a clump's spread along its normal: a short cut's card stands at the top of its clump
SHORT_TIP = 0.005  # m: how far a short cut's card tips rise off the cap (x 0.2-1.6 per card)
SHORT_GREY = 0.45  # a short cut's card is darker by this x (the greyest locks' grey share - its own lock's)
SHORT_ATLAS = 2048
CARD_TIERS = {
    "hero": {"triangles": 40000, "cap_step": 4.0, "group": "sub", "layers": 3, "card_width": 0.012, "segment": 0.008,
             "fly": 2, "baby": 2.0, "core_sides": 12, "mass": 5000},
    "main": {"triangles": 16000, "cap_step": 5.0, "group": "pair", "layers": 2, "card_width": 0.02, "segment": 0.012,
             "baby": 0.6, "core_sides": 10, "mass": 3500},
    "npc": {"triangles": 6000, "cap_step": 8.0, "group": "lock", "layers": 1, "card_width": 0.028, "segment": 0.025,
            "baby": 0.0, "core_sides": 8, "mass": 1800},
    "far": {"triangles": 1500, "cap_step": 14.0, "cap": "mass", "group": "free", "layers": 1, "card_width": 0.07, "segment": 0.05,
            "baby": 0.0, "core_sides": 6, "mass": 800},
}


def cards_job(sc: Scalp, g: dict, spec: dict, locks: list, tmp: Path, V, F, budget: int | None = None,
              cap_step: float = 1.0, col=None, clear_col=None) -> dict:
    """The hair as cards (hair_cards.py): the card mesh of every lock + baby hairs, the underlayer wearing the strand
    atlas, and the atlas's pictures. `budget`: triangles for the cards (segments lengthen, then layers go)."""
    from . import hair_cards as hc
    h = hair_of(spec)
    S = hc.strands_of(spec)
    lens_ = [float(np.linalg.norm(np.diff(np.asarray(k_["pts"], float), axis=0), axis=1).sum())
             for k_ in locks] if g.get("loose") else []
    short = bool(lens_) and float(np.mean(lens_)) < MASS_MIN
    tier_given = isinstance(budget, str)
    if isinstance(budget, str):  # a tier: its triangles, and how fine the cards are cut to spend them
        if budget not in CARD_TIERS:
            raise HairError(f"hair cards: tier is one of {', '.join(CARD_TIERS)} (or a triangle count)")
        tier = {**CARD_TIERS[budget], **(SHORT_TIERS[budget] if short else {})}
        S = {**S, **{k: v for k, v in tier.items() if k not in ("triangles", "cap_step", "cap")}}
        budget = int(tier["triangles"])
    if short:
        S = {**S, "atlas": max(int(S["atlas"]), SHORT_ATLAS), "fly": int(S.get("fly", 0)) if tier_given else 0,
             "short": True}
    lk = {**LOOK, **(h.get("look") or {})}
    # grey hairs in the cards' pictures: the share the strand look draws (the look's own + the locks' mean grey)
    gl = [float((k_.get("inputs") or {}).get("Grey", k_.get("grey", 0.0)) or 0.0) for k_ in locks]
    lk["grey_share"] = round(float(np.clip(float(lk.get("grey_amount", 0.0))
                                           + float(lk.get("grey_locks", 1.0)) * (np.mean(gl) if gl else 0.0), 0, 1)), 3)
    D, e_chart = None, None
    if S.get("source", "groom") == "groom":  # the pictures are the groom's own strands (hair_strands.py)
        from . import hair_strands as hs
        import re as _re
        sd = hs.job(sc, g, spec, [k_ for k_ in locks if not _re.fullmatch(r"t\d*band", k_["name"])], tmp, col=col)
        D, e_chart = hs.strands_of_model(sd), sd["e0"]
        if short:  # the cap's picture is BAKED from the strands: colour, depth, normal, flow, grey (hair_cap.py)
            from . import hair_cap
            ck = (hs.key(sd), int(S["atlas"]), hair_cap.VERSION, lk.get("grey_locks"), lk.get("grey_amount"), lk.get("card_grey"), float(S["soft"]))
            if ck not in _CHARTS:
                _CHARTS.clear()
                _CHARTS[ck] = hair_cap.chart(sc, g, hairline(sc, g), S, D, [k_ for k_ in locks if not _re.fullmatch(r"t\d*band", k_["name"])],
                                             e_chart, int(S["atlas"]), lk)
            chart = _CHARTS[ck]
        else:
            chart = hs.cap_chart(sc, g, hairline(sc, g), S, D, e_chart, int(S["atlas"]))
        at = hc.atlas(S, lk, lines=hs.tile_lines(S), cap=chart,
                      key=hs.key(sd) + (f"short{hair_cap.VERSION}" if short else ""))
    else:
        at = hc.atlas(S, lk)
    import re
    bands = [k_ for k_ in locks if re.fullmatch(r"t\d*band", k_["name"])]  # the tie is its own mesh, not hair
    line = hairline(sc, g)
    for k_ in locks:  # locks rooted at the hairline wear the thin-rooted tile there
        if not k_.get("free"):
            a0, e0, h0 = sc.coords(np.asarray(k_["pts"][0], float)[None])
            k_["at_hairline"] = bool(h0[0] < 0.01 and inside(sc, line, a0, e0)[0] < 0.008)
    hair_locks = [k_ for k_ in locks if k_ not in bands]
    core = None
    if D is not None:  # cards cut from the groom's own strands, clustered as coarsely as the tier asks
        cards = hc.clump_cards(D, hair_locks, sc.C, S, lk, int(g.get("seed", 0)))
        if short:  # cards wherever the groom has length, lying just over the cap (which stands at the hair's mid
            # height), on the open tiles (a few thick strands, no opaque base). The budget thins them EVENLY: what
            # stands off the cap (the lifted front, the outline) and the hairline's cards stay longest, the rest go
            # at random, so the whole top keeps a broken, layered surface instead of a rim of tufts round a dome
            edge_ = {k_["name"] for k_ in hair_locks if k_.get("at_hairline")}
            grey_ = {k_["name"]: float((k_.get("inputs") or {}).get("Grey", k_.get("grey", 0.0)) or 0.0) for k_ in hair_locks}
            gmax_ = float(np.percentile(list(grey_.values()), 90)) if grey_ else 0.0
            from scipy.spatial import cKDTree as _KD
            va_, ve_, vh_ = sc.coords(np.asarray(V, float))
            capt_ = _KD(dirs(va_, ve_))
            capb_ = np.maximum(vh_, 0.0) + 0.1 * (1 - np.cos(np.radians(cap_step) / 2)) * 1.6 + 0.002
            hr_ = np.random.default_rng(int(g.get("seed", 0)) + 17)
            kept_ = []
            for c_ in cards:
                P_ = np.asarray(c_["P"], float)
                a_, e_, h_ = sc.coords(P_)
                din_ = inside(sc, line, a_, e_)
                # a card ends at the hairline: past it (over the forehead, round the ear) its few thick strands
                # stood off the skin as wires. The cap's own thinned strands are the hairline.
                ok_ = np.cumprod(din_ > 0.002).astype(bool) if din_[0] > 0.002 else np.zeros(len(din_), bool)
                if ok_.sum() < 3:
                    continue
                if not ok_.all():
                    for k__ in ("P", "X", "N", "hw", "u", "s", "bend", "T"):
                        c_[k__] = np.asarray(c_[k__])[ok_]
                    if np.ndim(c_.get("sn", 0.0)):
                        c_["sn"] = np.asarray(c_["sn"])[ok_]
                    P_, a_, e_, h_, din_ = P_[ok_], a_[ok_], e_[ok_], h_[ok_], din_[ok_]
                kept_.append(c_)
                if c_["kind"] != "fly":  # the card stands at the TOP of its clump (its line is the clump's mean: the
                    # hair's outline is the strands above it), along the strands' own direction
                    sn_ = np.broadcast_to(np.asarray(c_.get("sn", 0.0), float), (len(P_),))
                    P_ = P_ + (SHORT_TOP * sn_ * _ss(din_ / 0.015))[:, None] * np.asarray(c_["N"], float)
                    a_, e_, h_ = sc.coords(P_)
                # (+ where the cap's own mesh stands before that lift: the groom's volume, a few mm over the scalp.
                # Without it the cards lay UNDER the cap they were meant to break up: nothing of them showed)
                cz_ = hair_cap.cap_height(chart["lift"], din_, a_, e_) + capb_[capt_.query(dirs(a_, e_))[1]]
                f_ = (c_["s"] - c_["s"][0]) / max(float(c_["s"][-1] - c_["s"][0]), 1e-9)
                need_ = cz_ + 0.0012 + 0.0006 * c_["layer"] - 0.002 * (1 - _ss(f_ / 0.25))  # (the root dives into the cap)
                # the tip leaves the cap (SHORT_TIP, uneven card to card): lying IN the cap's surface every card was a
                # decal on a helmet; a crop's outline is tufts' ends
                need_ = need_ + SHORT_TIP * float(hr_.uniform(0.2, 1.6)) * f_ ** 1.5
                up_ = np.where(h_ > -0.004, np.clip(need_ - h_, 0.0, 0.03), 0.0)  # (not where a ray meets the ear first)
                c_["P"] = P_ + up_[:, None] * _unit(P_ - sc.C)
                c_["hw"] = np.asarray(c_["hw"], float) * (1 - 0.45 * _ss((f_ - 0.55) / 0.45))  # no square end
                if c_["kind"] != "fly":
                    c_["kind"] = "medium" if c_["layer"] == 0 else "sparse"
                # grey by region: the tiles are drawn with ONE grey share (the locks' mean); a card of a less grey
                # lock is darker by its vertex colour (the cap's own picture has the per-lock grey, but the cards
                # now cover it: greying temples under a uniform top)
                c_["value"] = float(c_.get("value", 1.0)) * (1.0 - SHORT_GREY * (gmax_ - grey_.get(c_.get("lock"), gmax_)))
                off_ = float((h_ - cz_).max())
                c_["prio"] = ((0.0 if off_ > 0.005 else 0.45 if c_.get("lock") in edge_ else 1.0)
                              + 0.5 * min(c_["layer"], 1) + float(hr_.uniform(0.0, 0.9)))
            cards = kept_
        tc = hc.tail_cores(D, hair_locks, sides=int(S.get("core_sides", 10)))
        core = hc.core_mesh(tc, at["tiles"]) if tc is not None else None
        # (not for a short cut: hair under MASS_MIN long has no inside; its shell stood OUTSIDE the cards on the
        # sides and back as a pale dome with a dark rim at the temples (Garrett's crop). The cap, wearing the
        # scalp chart, is the surface under short cards.)
        lens = [float(np.linalg.norm(np.diff(np.asarray(k_["pts"], float), axis=0), axis=1).sum()) for k_ in hair_locks]
        if g.get("loose") and lens and float(np.mean(lens)) > MASS_MIN:  # a loose mass: a solid surface inside it
            shell = hc.mass_shell(D, hair_locks, sc.C, at["tiles"], col=col, triangles=int(S.get("mass", 3000)))
            if shell is not None:
                core = hc.join(core, shell)
    else:
        cards = hc.cards_of(hair_locks, sc.C, S, lk)
    # a coarse cap's flat faces cut under the round head between their corners (skin through the hair): it is
    # lifted by that sagitta
    Vc = np.asarray(V, float)
    lift = 0.1 * (1 - np.cos(np.radians(cap_step) / 2)) * 1.6 + 0.002  # (+ the scalp grid vs the skin mesh: ~1 mm)
    Vc = Vc + lift * _unit(Vc - sc.C)
    if short and D is not None:  # the cap is the hair's MASS: it stands at the hair's mid height, easing down to the
        # skin at the hairline (on the scalp itself the head's profile was a bald dome under a fringe of cards)
        ca_, ce_, _ch = sc.coords(Vc)
        Vc = Vc + hair_cap.cap_height(chart["lift"], inside(sc, line, ca_, ce_), ca_, ce_)[:, None] * _unit(Vc - sc.C)
    cap = card_cap(sc, g, S, at["tiles"], Vc, F, e0=e_chart)
    baby = hc.cards_of(baby_locks(sc, g, S, int(g.get("seed", 0))), sc.C, S, lk)
    for c in baby:  # (the first to go under a budget, after single fly-aways)
        c["kind"], c["layer"], c["prio"] = "baby", 1, float(S["layers"]) + 0.6
    info = {}
    seg = None
    if budget:  # baby hairs are cards like any others: they go before coverage does
        cards, baby = cards + baby, []
    mb = hc.mesh(baby, S, lk, at["tiles"])
    band = []
    if bands:
        from . import hair_tied
        band = [hair_tied.band_mesh(b, at["tiles"]) for b in bands]
    if budget:  # the budget is the whole hair's: the cap, the baby hairs and the tie come off it first
        fixed = (len(cap["tris"]) + len(mb["tris"]) + sum(len(b["tris"]) for b in band)
                 + (len(core["tris"]) if core is not None else 0))
        cards, seg, info = hc.fit_budget(cards, S, max(int(budget) - fixed, 200))
        info["asked"], info["fixed"] = int(budget), int(fixed)
    mc = hc.mesh(cards, S, lk, at["tiles"], segment=seg)
    # against the body's own signed distance (hair_loose.collider), not the scalp's rays: a ray from the head's centre
    # meets the EAR first, so cards lying on the head behind and over the ear read 5-6 cm "under the skin" and were
    # moved out to the ear's silhouette (Garrett: 936 hero vertices, the ragged dark patches behind the ear and at
    # the temple)
    clearance = card_clearance(sc, mc, [c.get("lock", "?") for c in cards], fix=CARD_CLEAR,
                               col=col if col is not None else clear_col)
    # hair off the head must come OUT of the hair: a free card whose root lies on bare skin outside the hairline
    # is a detached wisp
    free_names = {k_["name"] for k_ in hair_locks if float(k_.get("free", 0.0)) > 0.5 and k_.get("core") is None}
    det: dict = {}
    for c in cards:
        if c.get("lock") in free_names:
            a_, e_, _h = sc.coords(np.asarray(c["P"][:1], float))
            d_ = float(inside(sc, line, a_, e_)[0])
            if d_ < -0.003:
                det[c["lock"]] = round(min(det.get(c["lock"], 0.0), d_) * 1000, 1)
    clearance["detached"] = det
    m = hc.join(core, mc, mb, *band)
    np.savez(tmp / "cards.npz", **m)
    np.savez(tmp / "cards_cap.npz", **cap)
    files = hc.write_atlas(at, str(tmp / "hair"))
    return {"mesh": str(tmp / "cards.npz"), "cap": str(tmp / "cards_cap.npz"), "color": files["color"],
            "normal": files["normal"], "aux": files["aux"], "flow": files["flow"], "short": bool(short),
            "triangles": int(len(m["tris"])),
            "cap_triangles": int(len(cap["tris"])), "cards": len(cards), "baby": len(baby), "budget": info,
            "coverage": at["coverage"], "clearance": clearance}


CARD_CLEAR = 0.0015  # m: every card vertex stays this far outside the head (None: measure only)


def card_clearance(sc: Scalp, M: dict, locks: list, fix: float | None = None, col=None) -> dict:
    """Card vertices under the skin: how many, the deepest, and by lock (the head as the scalp's rays see it: sc).
    A card's centre line is the MEAN of its clump's strands and its width is laid flat: over a convex forehead or
    temple both cut through the head like a chord, where the strands themselves were kept off it. fix: move every
    vertex nearer than that out to it along its ray (in place). Reported as it was BEFORE the fix."""
    V = M["verts"]
    if not len(V):
        return {"verts": 0, "under": 0, "deepest_mm": 0.0, "locks": {}}
    az, el, h = sc.coords(V.astype(float))
    ok = el > sc.EL[0] + 1.0  # (below the scalp's measured range there is no surface to compare with)
    if col is not None:  # loose hair: the whole body's signed distance (neck, shoulders, back, clothes)
        h = col.at(V.astype(float))
        ok = np.ones(len(V), bool)
    under = ok & (h < 0)
    by: dict = {}
    for ci in np.unique(M["card"][under]):
        nm = locks[int(ci)] if int(ci) < len(locks) else "?"
        by[nm] = min(by.get(nm, 0.0), float(h[under & (M["card"] == ci)].min()))
    out = {"verts": int(len(V)), "under": int(under.sum()), "under_share": round(float(under.mean()), 4),
           "deepest_mm": round(float(-h[under].min() * 1000), 1) if under.any() else 0.0,
           "locks": {k: round(-v * 1000, 1) for k, v in sorted(by.items(), key=lambda kv: kv[1])[:12]}}
    if fix is not None:
        low = ok & (h < fix)
        if low.any() and col is not None:
            V[low] = col.push(V[low].astype(float), fix).astype(V.dtype)
        elif low.any():
            V[low] = sc.point(az[low], el[low], np.full(int(low.sum()), fix)).astype(V.dtype)
        out["moved"] = int(low.sum())
    return out


def _bust(spec: dict | None) -> bool:
    """Hair that leaves the head downward (groom.loose): looks and stages take in the neck and shoulders."""
    return bool(spec and ((hair_of(spec).get("groom") or {}).get("loose")))


def stage_path(name: str, bust: bool = False) -> Path:
    return store._dir(name) / ("hair_stage_bust.blend" if bust else "hair_stage.blend")


def make_stage(name: str, pad: float = 0.1, spec: dict | None = None) -> Path:
    """A small .blend for fast hair looks: the scene cropped to a box round the head (painted skin, eyes, collar),
    rebuilt when scene.blend is newer. With loose hair the box takes in the shoulders and the back."""
    from .scene import _blender, blend_path
    bp = blend_path(name)
    if not bp.exists():
        raise HairError(f"{name}: no scene.blend yet (sync the model once)")
    bust = _bust(spec)
    sp = stage_path(name, bust)
    if sp.exists() and sp.stat().st_mtime > bp.stat().st_mtime:
        return sp
    sc = scalp(name)
    lo = (sc.C - ([0.32, 0.28, 0.7] if bust else [0.16, 0.2, 0.22])).tolist()
    hi = (sc.C + ([0.32, 0.28, 0.16] if bust else [0.16, 0.16, 0.16])).tolist()
    _blender({"mode": "hair_stage", "blend": str(bp), "out": str(sp), "box": [lo, hi]})
    return sp


def reference_image(name: str, reference: str | None = None):
    """(path, crop or None) of the image the hair is judged against: `reference` if given, else the traced
    reference's image (ref_trace.json "image", cropped to the matched camera's crop), else none."""
    if reference:
        p = Path(reference).expanduser()
        return (p, None) if p.exists() else (None, None)
    tr = ref_trace(name) or {}
    cam = ref_camera(name) or {}
    p = tr.get("image") or cam.get("reference")
    if p and Path(p).exists():
        return Path(p), cam.get("crop") or tr.get("crop")
    return None, None
VIEWS = {"front": (0.0, 5.0), "three_quarter": (40.0, 12.0), "side": (90.0, 5.0), "back": (180.0, 10.0),
         "top": (20.0, 60.0), "three_quarter_r": (-40.0, 12.0), "side_r": (-90.0, 5.0),
         "back_quarter": (140.0, 8.0), "wide_r": (-95.0, 4.0, 0.95), "wide_back": (165.0, 6.0, 0.95),
         "wide_front": (-20.0, 4.0, 0.9), "close": (-30.0, 25.0, 0.45),
         "close_back": (150.0, 20.0, 0.45), "close_front": (12.0, 8.0, 0.4), "close_side": (75.0, 15.0, 0.42),
         # (az, el, distance, m the target sits under the head centre): the bust, for hair that falls
         "bust_front": (0.0, 4.0, 1.25, 0.14), "bust_three_quarter": (40.0, 8.0, 1.25, 0.14),
         "bust_side": (90.0, 4.0, 1.25, 0.14), "bust_back": (180.0, 6.0, 1.25, 0.14),
         "bust_back_quarter": (140.0, 8.0, 1.25, 0.14), "long_back": (180.0, 4.0, 1.9, 0.26),
         "long_side": (90.0, 4.0, 1.9, 0.26)}


def cameras(sc: Scalp, views, dist: float = 0.62, fov: float = 30.0) -> list:
    out = []
    target = sc.C + np.array([0.0, 0.0, 0.0])
    for v in views:
        az, el, *dd = VIEWS[v]
        tg = target - np.array([0.0, 0.0, dd[1] if len(dd) > 1 else 0.0])
        eye = tg + dirs(az, el) * (dd[0] if dd else dist)  # close-ups: the material at work
        out.append({"name": v, "eye": eye.tolist(), "target": tg.tolist(), "fov": fov})
    return out


# Lights for strand / card looks (each a sun; "dir" points from the head toward the light). Hair is read by its
# highlight band and by light coming through its edge: a key from the front, a soft fill, and a rim from behind
# (what a portrait photographer calls the hair light). Solid locks keep the stage's single sun.
LIGHTS = {
    "salon": {"lights": [{"dir": [-0.45, -0.75, 0.55], "energy": 3.0, "angle": 8.0},
                         {"dir": [0.8, -0.45, 0.15], "energy": 0.7, "angle": 30.0, "specular": 0.0,
                          "color": [0.86, 0.9, 1.0]},
                         {"dir": [0.35, 0.8, 0.5], "energy": 4.5, "angle": 5.0, "color": [1.0, 0.96, 0.9]}],
              "world": {"color": [0.77, 0.81, 0.86], "strength": 0.5}},
    "flat": {"lights": [{"dir": [-0.4, -0.7, 0.6], "energy": 3.5, "angle": 3.0}]},
}


def look(name: str, views=("front", "three_quarter", "side", "back", "top"), size: int = 480, save: str | None = None,
         reference: str | None = None, spec: dict | None = None, caption: str = "", clay: bool = True,
         only=None, engine: str = "eevee", count: int | None = None, samples: int | None = None,
         budget: int | None = None, light=None, denoise: bool = True, debug: str | None = None) -> tuple:
    """A fast hair look: the head-cropped stage file + the hair from the spec, EEVEE, a few perspective views, a
    thumbnail (how it reads small) and the reference beside. Returns (sheet image, seconds)."""
    from PIL import Image, ImageDraw
    from . import render
    from .scene import _blender
    t = time.time()
    spec = store.load(name) if spec is None else spec
    sp = make_stage(name, spec=spec)
    sc = scalp(name, spec)
    cams = cameras(sc, views)
    frames = [render.camera_frame(c, i) for i, c in enumerate(cams)]
    rvs = ref_views(name)
    mnames = ["matched" if v == "matched" else f"matched_{v}" for v, _, _ in rvs]
    for fname, (v, rc, _) in zip(mnames, rvs):  # the reference's own cameras (fit_camera): compared with the
        # reference pixel for pixel
        frames.append({"name": fname, "eye": rc["eye"], "dir": rc["dir"], "up": rc["up"], "fov": rc["fov"],
                       "shift": rc["shift"], "center": sc.C.tolist(), "near": 0.01, "scale": None, "axes": None})
    thumb = render.camera_frame({"name": "thumb", "eye": (sc.C + dirs(25.0, 8.0) * 1.6).tolist(),
                                 "target": (sc.C - [0, 0, 0.12]).tolist(), "fov": 30.0}, len(frames))
    with tempfile.TemporaryDirectory() as tmp:
        for f in frames + [thumb]:
            f["out"] = str(Path(tmp) / f"{f['name']}.png")
        thumb["size"] = 160
        dump = str(Path(tmp) / "hair_pts.npy")
        cf = [{**f, "out": str(Path(tmp) / f"clay_{f['name']}.png")} for f in frames] if clay else []
        idf = [{**f, "out": str(Path(tmp) / f"id_{f['name']}.png"),
                "size": 480 if f["name"].startswith("matched") else 240} for f in frames]  # (matched ones finer:
        # the hairline's edge is measured on them)
        j = {"mode": "hair_look", "blend": str(sp), "views": frames + [thumb], "size": size,
             "hair": job(name, spec, only=only, count=count, budget=budget),
             "samples": samples or (32 if engine == "cycles" else 16), "dump": dump, "clay_views": cf, "id_views": idf,
             "look_engine": engine}
        style = hair_of(spec).get("style", "locks")
        if debug and j["hair"].get("cards"):
            j["hair"]["cards"]["debug"] = debug
        light = light if light is not None else (hair_of(spec).get("look") or {}).get("light")
        if light is None and style in ("strands", "cards"):
            light = "salon"
        if light:
            j["lighting"] = LIGHTS[light] if isinstance(light, str) else light
        if engine == "cycles" and style == "strands":
            j.update(hair_bounces=10, denoise=bool(denoise), adaptive_threshold=0.01,
                     samples=samples or 96)
        if engine == "cycles":  # path-traced strands: minutes of every core, one such job at a time on the machine
            from . import resources
            with resources.heavy(f"hair look {name} (cycles)", kind="hair_cycles", model=name):
                out = _blender(j, timeout=3600)
        else:
            out = _blender(j)
        clays = [Image.open(f["out"]).convert("RGB") for f in cf]
        look.mass_share, look.lit_mass, masks = {}, {}, {}
        for f, fm in zip(idf, frames):  # red = the underlayer, green = locks (flat emission, nothing else drawn)
            a = np.asarray(Image.open(f["out"]).convert("RGB"), float)
            red, green = a[..., 0] > a[..., 1] + 60, a[..., 1] > a[..., 0] + 60
            if f["name"] in mnames:
                masks[f["name"]] = red | green
            look.mass_share[f["name"]] = round(float(red.sum() / max(red.sum() + green.sum(), 1)), 3)
            # lit bare volume: where the volume shows AND is shaded like the locks around it (not a crevice or a
            # parting in shadow): the smooth patch the eye reads as a helmet
            lum = np.asarray(Image.open(fm["out"]).convert("L").resize(a.shape[1::-1]), float)
            lit_ref = np.percentile(lum[green], 35) if green.any() else 255.0
            lit = red & (lum >= lit_ref)
            look.lit_mass[f["name"]] = round(float(lit.sum() / max(red.sum() + green.sum(), 1)), 3)
            Image.open(f["out"]).save(store._dir(name) / f"hair_id_{f['name']}.png")  # the last look's id pass
        pts = np.load(dump)
        np.save(store._dir(name) / "hair_points.npy", pts)  # the last look's hair vertices (for measuring) and
        np.savez(store._dir(name) / "hair_point_owners.npz", ids=np.load(dump + ".ids.npy"),  # which object each is
                 names=np.array(json.load(open(dump + ".names.json"))))
        owners = (pts, np.load(dump + ".ids.npy"), json.load(open(dump + ".names.json")))
        look.bare_where = {}
        if j["hair"] and j["hair"].get("cap"):  # where the bare volume shows, by head region
            capV = np.load(j["hair"]["cap"])["verts"]
            g_ = groom_params(spec)
            for f, fm in zip(idf, frames):
                a = np.asarray(Image.open(f["out"]).convert("RGB"), float)
                red, green = a[..., 0] > a[..., 1] + 60, a[..., 1] > a[..., 0] + 60
                look.bare_where[f["name"]] = bare_regions(sc, g_, capV, fm, red, red.sum() + green.sum(),
                                                          cam=dict(zip(mnames, [rc for _, rc, _ in rvs])).get(f["name"]))
        look.gate = silhouette_gate(sc, pts)
        look.folds = folds(sc, j["hair"].get("locks") or []) if j["hair"] else {}
        look.root_ends = root_ends(sc, groom_params(spec), j["hair"].get("locks") or []) if j["hair"] else {}
        look.fins = fins(sc, groom_params(spec), j["hair"].get("locks") or []) if j["hair"] else {}
        imgs = [Image.open(f["out"]).convert("RGB") for f in frames]
        th = Image.open(thumb["out"]).convert("RGB")
    t_render = time.time() - t
    W = size
    nm = len(rvs)
    matched, mclay = [], []
    if nm:  # a row each: matched render, clay, reference, 50% blend, the traced lines
        matched = imgs[len(imgs) - nm:]
        imgs = imgs[:len(imgs) - nm]
        if clays:
            mclay = clays[len(clays) - nm:]
            clays = clays[:len(clays) - nm]
        frames = frames[:len(frames) - nm]
    cols = max(len(imgs) + 1, 5 if nm else 0)
    rows = (2 if clays else 1) + nm
    sheet = Image.new("RGB", (W * cols, rows * W + 22), (30, 31, 35))
    dr = ImageDraw.Draw(sheet)
    for i, (im, f) in enumerate(zip(imgs, frames)):
        sheet.paste(im.resize((W, W)), (i * W, 22))
        dr.text((i * W + 6, 5), f["name"], fill=(220, 220, 220))
    for i, im in enumerate(clays):
        sheet.paste(im.resize((W, W)), (i * W, 22 + W))
    if clays:
        dr.text((6, 22 + W + 6), "clay", fill=(220, 220, 220))
    x0 = len(imgs) * W
    ref, rcrop = reference_image(name, reference)
    if ref is not None:
        r = Image.open(ref).convert("RGB")
        r = r.crop(tuple(rcrop)) if rcrop else r
        r.thumbnail((W, W - 170))
        sheet.paste(r, (x0, 22))
        dr.text((x0 + 6, 5), "reference", fill=(220, 220, 220))
    sheet.paste(th, (x0 + 6, W + 22 - th.height - 4))
    dr.text((x0 + 170, W + 22 - 20), f"thumbnail {th.width}px", fill=(200, 200, 200))
    look.fits = {v: fit_metrics(name, sc, rc, spec, masks.get(fn), tr=t, owners=owners)
                 for fn, (v, rc, t) in zip(mnames, rvs)}
    look.fit = look.fits.get("matched")
    if look.fit:
        f = look.fit
        caption = (caption + "   " if caption else "") + "fit: " + ", ".join(
            f"{k} {v}" for k, v in f.items() if k not in ("clumps", "mm_per_px", "regions", "front_edge"))
    for j, (fn, (v, rc, t)) in enumerate(zip(mnames, rvs)):
        y = (rows - nm + j) * W + 22
        rimg = Path(t["image"]) if t.get("image") and Path(t["image"]).exists() else None
        mr = matched[j].resize((W, W))
        panels = [(f"matched camera ({v})", mr)]
        if rimg is not None:
            refc = Image.open(rimg).convert("RGB").crop(tuple(rc["crop"])).resize((W, W))
            fv = look.fits.get(v)
            if fv and masks.get(fn) is not None:
                fl = front_flow(rc, t, Image.open(rimg).convert("RGB").crop(tuple(rc["crop"])), matched[j],
                                masks[fn], fv["mm_per_px"])
                if fl:
                    fv["front_flow"] = fl
            panels += [("reference", refc), ("50% blend", Image.blend(mr, refc, 0.5))]
        if mclay:
            panels.insert(1, ("matched clay", mclay[j].resize((W, W))))
        tro = trace_overlay(name, sc, rc, mr, spec, tr=t, mask=masks.get(fn))
        if tro is not None:
            panels.append(("trace: ref yellow/orange, ours cyan/magenta", tro))
        for i, (lab, im) in enumerate(panels[:cols]):
            sheet.paste(im, (i * W, y))
            dr.text((i * W + 6, y + 4), lab, fill=(255, 255, 120))
    if caption:
        dr.text((6, rows * W + 6), caption, fill=(240, 220, 160))
    if save:
        sheet.save(save)
    frames_t = [line for line in out.splitlines() if line.startswith("@@")]
    return sheet, round(t_render, 1), frames_t


def look_glb(name: str, glb, views=("wide_r", "back_quarter", "close_front", "three_quarter"), size: int = 480,
             alpha: str = "test", light="salon", spec: dict | None = None, dist: float | None = None,
             engine: str = "eevee") -> tuple:
    """An exported hair GLB re-imported onto the model's head stage and rendered as an engine draws it (Blender's
    glTF importer; alpha "test" = cut at the material's alphaCutoff, "dither" = hashed alpha, "off" = solid cards).
    Returns ([image per view], what the importer made, seconds). `dist`: the camera's distance (m) in place of the
    close look's 0.62: a tier is judged where it is meant to be seen."""
    from PIL import Image
    from . import render
    from .scene import _blender
    t = time.time()
    spec = store.load(name) if spec is None else spec
    sp = make_stage(name, spec=spec)
    sc = scalp(name, spec)
    cams = cameras(sc, views) if dist is None else cameras(sc, views, dist=dist)
    frames = [render.camera_frame(c, i) for i, c in enumerate(cams)]
    with tempfile.TemporaryDirectory() as tmp:
        for f in frames:
            f["out"] = str(Path(tmp) / f"{f['name']}.png")
        j = {"mode": "hair_glb_look", "blend": str(sp), "views": frames, "size": size, "glb": str(glb) if glb else None,
             "alpha": alpha, "samples": 16, "look_engine": engine}
        if light:
            j["lighting"] = LIGHTS[light] if isinstance(light, str) else light
        out = _blender(j)
        imgs = [Image.open(f["out"]).convert("RGB") for f in frames]
    info = next((json.loads(ln[6:]) for ln in out.splitlines() if ln.startswith("@@glb")), {})
    return imgs, info, round(time.time() - t, 1)


def check_tiers(name: str, export: dict | str | Path, tiers=None, save: str | None = None, size: int = 400,
                views=("wide_r", "back_quarter", "close_front", "three_quarter"), solid: bool = True,
                spec: dict | None = None) -> dict:
    """An export's card tiers judged as an engine draws them, against the strand groom: each tier's GLB re-imported
    on the head (alpha TEST at its cutoff, and dithered), the strands and the bald head in the same views and light.
    Per tier and view (hair_checks.compare): iou / missing (strand silhouette left bare), value and saturation x the
    strands', detached rectangular blobs (cards showing as stamps), straight outline share (plank ends); per tier
    the card mesh's own numbers (cards, widths, triangles by layer, what the budget dropped) and WARNING lines.
    `save`: a sheet: strands | per tier alpha test, dithered, and (solid=True) the cards as solid quads coloured by
    layer | the atlas. `export`: export_hair's report or its folder. Returns {"tiers": {...}, "warnings": [...],
    "sheet": path}."""
    from PIL import Image, ImageDraw
    from . import hair_checks as hk
    if not isinstance(export, dict):
        export = json.loads((Path(export) / f"{name}_hair.json").read_text())
    spec = store.load(name) if spec is None else spec
    tiers = list(tiers or export["tiers"])
    bald, _, _ = look_glb(name, None, views=views, size=size, spec=spec)
    sp = {**spec, "hair": {**hair_of(spec), "style": "strands"}}
    sheet, _, _ = look(name, views=views, size=size, spec=sp, clay=False)
    strands = [sheet.crop((i * size, 22, (i + 1) * size, 22 + size)) for i in range(len(views))]
    rows = [("strands (the groom)", strands)]
    out = {"tiers": {}, "warnings": []}
    for tier in tiers:
        e = export["tiers"][tier]
        r = {"triangles": e["triangles"], "budget": e.get("budget"), "layers": e.get("layers")}
        for alpha in ("test", "dither"):
            imgs, info, _ = look_glb(name, e["glb"], views=views, size=size, alpha=alpha, spec=spec)
            r[alpha] = {v: hk.compare(s_, im, b) for v, s_, im, b in zip(views, strands, imgs, bald)}
            rows.append((f"{tier}: the GLB re-imported, alpha {alpha}   {e['triangles']} triangles", imgs))
        r["clearance"] = e.get("clearance")
        r["warnings"] = sorted(set(hk.verdict(r["test"], far=tier == "far") + hk.verdict(r["dither"], far=tier == "far")
                                   + hk.mesh_verdict(e.get("clearance"))))
        out["warnings"] += [f"{tier}: {w}" for w in r["warnings"]]
        if solid and tier in CARD_TIERS:
            sc_ = {**spec, "hair": {**hair_of(spec), "style": "cards"}}
            sh, _, _ = look(name, views=views, size=size, spec=sc_, clay=False, budget=tier, debug="layers")
            rows.append((f"{tier}: cards as solid quads by layer (cap + core grey, 0 red, 1 green, 2 blue, 3 yellow, "
                         f"above magenta; back faces dark)",
                         [sh.crop((i * size, 22, (i + 1) * size, 22 + size)) for i in range(len(views))]))
        out["tiers"][tier] = r
    if save:
        W_ = size * len(views)
        maps = export.get("maps") or {}
        atl = Image.open(maps["basecolor"]).convert("RGBA") if maps.get("basecolor") else None
        extra = 2 * (W_ // 2 + 18) if atl is not None else 0
        img = Image.new("RGB", (W_, len(rows) * (size + 18) + extra), (30, 31, 35))
        d = ImageDraw.Draw(img)
        y = 0
        for lab, ims in rows:
            d.text((6, y + 3), lab, fill=(240, 220, 160))
            for i, im in enumerate(ims):
                img.paste(im.resize((size, size)), (i * size, y + 18))
            y += size + 18
        if atl is not None:
            bg = Image.new("RGBA", atl.size, (140, 140, 140, 255))
            for lab, im in (("atlas: base colour over grey (left: clump tiles, right: the scalp chart)",
                             Image.alpha_composite(bg, atl).convert("RGB")), ("atlas: alpha", atl.split()[3].convert("RGB"))):
                d.text((6, y + 3), lab, fill=(240, 220, 160))
                img.paste(im.resize((W_, W_ // 2)), (0, y + 18))
                y += W_ // 2 + 18
        img.save(save)
        out["sheet"] = str(save)
        stem = str(save)[:-4]
        for lab, ims in rows:  # each row alone too (the whole sheet is tall)
            rr = Image.new("RGB", (W_, size))
            for i, im in enumerate(ims):
                rr.paste(im.resize((size, size)), (i * size, 0))
            tag = lab.split(":")[0].split(" ")[0] + ("_solid" if "solid" in lab else "_dither" if "dither" in lab
                                                     else "_test" if "test" in lab else "")
            rr.save(f"{stem}_{tag}.png")
    return out


def tiers_text(chk: dict) -> str:
    """check_tiers' numbers as a table."""
    lines = ["tier     tris   view            iou   bare  value   sat  stamps straight   (alpha test | dithered)"]
    for tier, r in chk["tiers"].items():
        for v in r["test"]:
            a, b = r["test"][v], r["dither"][v]
            lines.append(f"{tier:<6} {r['triangles']:>6}   {v:<14} {a['iou']:.2f}  {a['missing']:.2f}   {a['value']:.2f}  {a['sat']:.2f}"
                         f"   {a['stamps']}    {a['straight']:.2f}   |  {b['iou']:.2f}  {b['missing']:.2f}   {b['value']:.2f}  {b['sat']:.2f}"
                         f"   {b['stamps']}    {b['straight']:.2f}")
    lines += chk["warnings"] or ["no warnings"]
    return "\n".join(lines)


def _project_frame(fm: dict, P, W: int):
    """World points -> pixels (u right, v down) of a square look frame (render.camera_frame: perspective, fov across)
    and their depth along the view."""
    eye = np.asarray(fm["eye"], float)
    fwd = -_unit(np.asarray(fm["dir"], float))
    right = _unit(np.cross(fwd, np.asarray(fm["up"], float)))
    up = np.cross(right, fwd)
    Q = np.asarray(P, float) - eye
    z = Q @ fwd
    k = 1.0 / np.tan(np.radians(float(fm["fov"])) / 2)
    x, y = (Q @ right) / z * k, (Q @ up) / z * k
    return np.stack([(x + 1) / 2 * W, (1 - (y + 1) / 2) * W], -1), z


BARE_BAND = 0.015  # m inside the hairline: bare volume there is reported as "<region> hairline"


def bare_regions(sc: Scalp, g: dict, capV, fm: dict, red, total: int, cam: dict | None = None) -> dict:
    """Where the bare volume shows in a view: each underlayer pixel of the id pass labelled by the head region of the
    underlayer point it shows (the nearest projected vertex), "<region> hairline" within BARE_BAND of the hairline.
    {label: share of the view's visible hair}, largest first (above 0.005)."""
    if total == 0 or not red.any():
        return {}
    W = red.shape[0]
    if cam is not None:  # a matched view: the reference camera (lens shift)
        uv = _to_crop(cam, project_ref(cam, capV), W)
        R_, t_, ctr = np.array(cam["R"]), np.array(cam["t"]), np.array(cam["ctr"])
        z = ((capV - ctr) @ R_.T + t_)[:, 2]
    else:
        uv, z = _project_frame(fm, capV, W)
    iu, iv = np.round(uv[:, 0]).astype(int), np.round(uv[:, 1]).astype(int)
    ok = (z > 0) & (iu >= 0) & (iu < W) & (iv >= 0) & (iv < W)
    zb = np.full((W, W), np.inf)
    owner = -np.ones((W, W), int)
    idx = np.nonzero(ok)[0]
    order = idx[np.argsort(-z[idx])]  # far first: nearer vertices overwrite
    zb[iv[order], iu[order]] = z[order]
    owner[iv[order], iu[order]] = order
    from scipy.ndimage import distance_transform_edt
    has = owner >= 0
    _, (ri, ci) = distance_transform_edt(~has, return_indices=True)  # pixels between projected vertices
    ys, xs = np.nonzero(red)
    v = owner[ri[ys, xs], ci[ys, xs]]
    a, e, _ = sc.coords(capV[v])
    d_in = inside(sc, hairline(sc, g), a, e)
    lab = np.char.add(region_of(a, e).astype(str), np.where(d_in < BARE_BAND, " hairline", ""))
    out = {}
    for L in np.unique(lab):
        s = float((lab == L).sum() / total)
        if s >= 0.005:
            out[str(L)] = round(s, 3)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


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
    z0 = (sc.lm["lm_brow_mid.L"][2] if "lm_brow_mid.L" in sc.lm else float(sc.C[2])) + 0.02
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
    bp, sp = blend_path(name), stage_path(name)
    fresh = sp.exists() and bp.exists() and sp.stat().st_mtime > bp.stat().st_mtime
    out = _blender_live(j) if live_session(name) else _blender(j)
    if fresh:  # the stage holds no hair (looks show the spec's): a hair-only save of scene.blend doesn't stale it
        os.utime(sp)
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
        if n in ("__deleted__", "__new__"):
            continue
        lk = locks.get(n)
        if lk is None:
            continue
        stale = bool(st.get("hash")) and st["hash"] != lock_hash(lk, sc)
        # stale: the scene's lock was built from another version of the spec (regrown or synced from another model
        # since): an edit to it isn't an edit to this lock. The next sync replaces it. (A lock pulled from a saved
        # file reads back as itself until the next sync: not news.)
        P = np.asarray(st["pts"], float)
        new = dict(lk)
        new["pts"] = lock_address(sc, lk, P)
        if st.get("handles"):
            H = []
            for hd in st["handles"]:
                if hd:
                    if lk.get("space") == "xyz":
                        q = lock_address(sc, lk, [hd[:3], hd[3:]])
                        H.append(q[0] + q[1])
                    else:
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
        if stale:
            if {k: v for k, v in new.items() if k != "hand"} != {k: v for k, v in lk.items() if k != "hand"}:
                log.append(f"hair lock {n}: the scene's copy was built from another version of the spec (regrown or "
                           f"edited since the last sync): not pulled; sync replaces it")
            continue
        if new != lk:
            new["hand"] = True  # shaped by hand: a regrow (hair.groom) leaves it alone
            locks[n] = new
            changes[f"hair.{n}"] = "edited in the scene"
            log.append(f"hair lock {n}: edited in the scene")
    for n, st in (got.get("__new__") or {}).items():  # curves added in Blender (Shift+D on a lock, or drawn new)
        if n in locks:
            log.append(f"hair lock {n}: added in the scene, but the spec has a lock of that name: not pulled")
            continue
        P = np.asarray(st["pts"], float)
        a, e, hh = sc.coords(P)
        new = {"tier": "hand", "hand": True,
               "pts": [[round(float(a[i]), 2), round(float(e[i]), 2), round(float(hh[i]), 4)] for i in range(len(P))]}
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
        for k in ("radius", "tilt"):
            vals = st.get(k) or []
            if vals and any(abs(v - (1.0 if k == "radius" else 0.0)) > 1e-4 for v in vals):
                new[k] = vals
        for mk, v in (st.get("inputs") or {}).items():
            if mk in inv:
                new[inv[mk]] = round(float(v), 5)
        new.setdefault("width", 0.03)
        new.setdefault("thickness", 0.006)
        locks[n] = new
        changes[f"hair.{n}"] = "added in the scene"
        log.append(f"hair lock {n}: added in the scene")
    removed = h.setdefault("removed", [])
    for n in got.get("__deleted__", []):
        if n in locks:
            locks.pop(n)
            if n not in removed:  # a regrow mustn't bring it back
                removed.append(n)
            changes[f"hair.{n}"] = "deleted in the scene"
            log.append(f"hair lock {n}: deleted in the scene")
    if not removed:
        h.pop("removed", None)
    return changes


# ------------------------------------------------------------------------------------------------ export

def srgb_to_linear(hexc: str) -> list:
    c = hexc.lstrip("#")
    v = [int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in v]


def _srgb8(px):
    """Linear floats -> sRGB 8-bit."""
    c = np.clip(px, 0, 1)
    s = np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)
    return (s * 255 + 0.5).astype(np.uint8)


def _tangents(V, T, UV):
    """Per-corner normals (smooth, by vertex) and tangents (dP/du, orthogonalised) + bitangent sign, for a triangle
    mesh with per-corner uv (T (n, 3) vertex ids, UV (n*3, 2))."""
    P = V[T]
    e1, e2 = P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]
    fn = np.cross(e1, e2)
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, T[:, k], fn)
    vn = _unit(vn)
    u = UV.reshape(-1, 3, 2)
    d1, d2 = u[:, 1] - u[:, 0], u[:, 2] - u[:, 0]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    r = np.where(np.abs(det) > 1e-12, 1.0 / np.where(np.abs(det) > 1e-12, det, 1.0), 0.0)
    t = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * r[:, None]
    b = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * r[:, None]
    vt, vb = np.zeros_like(V), np.zeros_like(V)
    for k in range(3):
        np.add.at(vt, T[:, k], t)
        np.add.at(vb, T[:, k], b)
    n = vn[T].reshape(-1, 3)
    tt = vt[T].reshape(-1, 3)
    tt = tt - (tt * n).sum(1, keepdims=True) * n
    tt = np.where(np.linalg.norm(tt, axis=1, keepdims=True) > 1e-12, _unit(tt), np.array([1.0, 0, 0]))
    sign = np.sign((np.cross(n, tt) * vb[T].reshape(-1, 3)).sum(1))
    return n, tt, np.where(sign == 0, 1.0, sign)


EXPORT = {"segments": 24, "sides": 10}  # per lock (spec["hair"]["export"] overrides): 12 x 8 read faceted in the
# export (the lens's thin edges shaded as flat planes), 24 x 10 is ~20k triangles for 45 locks


def export_part(name: str, out_dir: Path, spec: dict | None = None, texture: int = 1024, segments: int | None = None,
                sides: int | None = None, log: list | None = None) -> tuple[dict, dict] | None:
    """The hair as an export part: (part dict as asset.lowpoly makes them: verts, corner_vert, uv, normal, tangent,
    sign; atlas set by the caller) and its maps {basecolor, orm, normal, specular: png}. Low poly = the curve locks at
    `segments` x `sides` + the underlayer decimated; maps = Cycles bakes from the full-resolution locks (Blender)."""
    from PIL import Image
    from .scene import _blender
    log = [] if log is None else log
    spec = store.load(name) if spec is None else spec
    if not hair_of(spec).get("locks"):
        return None
    if hair_of(spec).get("style") in ("cards", "strands"):  # (a strand groom ships as cards cut from it)
        return export_cards(name, Path(out_dir), spec, log)
    ex = {**EXPORT, **((spec.get("hair") or {}).get("export") or {})}
    segments = int(segments or ex["segments"])
    sides = int(sides or ex["sides"])
    t = time.time()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    j = {"mode": "hair_export", "blend": "", "out": str(out_dir), "hair": job(name, spec), "texture": texture,
         "segments": segments, "sides": sides}
    _blender(j, timeout=1800)
    z = np.load(out_dir / "hair_low.npz")
    V, T, UV = z["verts"].astype(np.float64), z["tris"], z["uv"].astype(np.float64)
    n, tt, sg = _tangents(V, T, UV)
    part = {"verts": V.astype(np.float32), "corner_vert": T.ravel().astype(np.int64), "uv": UV.astype(np.float32),
            "normal": n.astype(np.float32), "tangent": tt.astype(np.float32), "sign": sg.astype(np.float32)}
    col = np.load(out_dir / "hair_color.npy")[::-1]  # Blender's pixels run bottom-up
    rough = np.load(out_dir / "hair_rough.npy")[::-1]
    files = {"basecolor": out_dir / "hair_basecolor.png", "orm": out_dir / "hair_orm.png",
             "normal": out_dir / "hair_normal.png", "specular": out_dir / "hair_specular_gltf.png"}
    Image.fromarray(_srgb8(col[..., :3])).save(files["basecolor"])
    r8 = (np.clip(rough[..., 0], 0, 1) * 255 + 0.5).astype(np.uint8)
    Image.fromarray(np.stack([np.full_like(r8, 255), r8, np.zeros_like(r8)], -1)).save(files["orm"])
    Image.fromarray(np.full((4, 4, 4), [255, 255, 255, 64], np.uint8), "RGBA").save(files["specular"])
    log.append(f"hair: {len(T)} triangles ({segments} x {sides} per lock + the underlayer), maps {texture}^2 baked by Cycles "
               f"from the locks' own material in {time.time() - t:.1f}s")
    return part, files


EXPORT_CARDS = {"triangles": 12000, "tier": None, "cap_step": 6.0, "alpha_cutoff": 0.33}  # spec["hair"]["export"] overrides
CARD_RECIPE = (
    "Hair cards. Draw two-sided with one normal for both faces (the mesh's normals are already bent toward the hair "
    "volume: do not flip them on back faces). Alpha: the base colour's alpha, alpha-tested at alpha_cutoff with "
    "dithering + temporal AA, or alpha-to-coverage with MSAA; keep the alpha's coverage in the mips (or bias mips "
    "-1). COLOR_0 multiplies the base colour: the root-to-tip ramp, a value per lock and per card, lower layers "
    "darker. Anisotropic highlight along the hair: TANGENT's bitangent (the atlas's v) runs root to tip. The aux "
    "texture holds R = root gradient (1 at the root), G = a value per strand (shift the highlight and the value "
    "with it), B = depth in the clump (0 deep: darker, less specular; usable as pixel depth offset), A = alpha. "
    "LODs: drop the cards of `layer` 2, then 1 (extras.layers gives each layer's triangle range).")


def export_hair(name: str, out_dir, tiers=("main", "npc", "far"), groom: bool = True, spec: dict | None = None,
                check: bool = False, sheet: str | None = None, textures: str = "shared") -> dict:
    """The hair alone, game-ready, from a strand (or card) groom: one GLB a tier (`<name>_hair_<tier>.glb`: LODs that
    share ONE atlas: cards cut from the groom's locks, the cap wearing the scalp chart) and, groom=True, the strands
    themselves for engines and renderers that draw them (`<name>_groom.abc` in centimetres for Unreal's groom
    importer / Unity's hair package, `<name>_groom.usdc` with the groom_* attributes as primvars). Returns the
    report (also `<name>_hair.json`)."""
    from . import asset, hair_cards as hc
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = store.load(name) if spec is None else spec
    h = hair_of(spec)
    lk = {**LOOK, **(h.get("look") or {})}
    rep = {"tiers": {}, "recipe": CARD_RECIPE}
    log: list = []
    for tier in tiers:
        sp = {**spec, "hair": {**h, "export": {**(h.get("export") or {}), "tier": tier}}}
        part, files = export_cards(name, out_dir, sp, log)
        hc_ = part.pop("hair")
        hc_["aux_texture"] = list(files).index("aux")
        # (engines: COLOR_0 multiplies the base colour (the root-to-tip ramp, a value per card). glTF says so, but
        # Godot's importer leaves BaseMaterial3D.vertex_color_use_as_albedo off: set it, or the hair is pale and flat)
        hc_["vertex_color"] = "multiplies base colour; Godot: set vertex_color_use_as_albedo = true"
        part["atlas"] = 0
        glb = out_dir / f"{name}_hair_{tier}.glb"
        sheen = [round(float(c), 3) for c in srgb_to_linear(lk["sheen"])]
        ani = {"anisotropyStrength": float(lk.get("anisotropic", 0.7)), "anisotropyRotation": 1.5708}
        if "flow" in files:  # the hair's direction per texel (the cap's strands turn; a card's run down its picture)
            ani = {"anisotropyStrength": float(lk.get("anisotropic", 0.7)), "anisotropyRotation": 0.0,
                   "anisotropyTexture": {"index": list(files).index("flow")}}
            hc_["flow_texture"] = list(files).index("flow")
        hc_["textures"] = textures
        asset.write_glb(glb, f"{name}_hair", {"hair": part}, [("hair", files)], external=textures == "shared",
                        looks={"hair": {"alpha_cutoff": hc_["alpha_cutoff"], "extras": {"hifipushie_hair": hc_}}},
                        extra_ext={0: {"KHR_materials_specular": {  # (a card is a sheet standing for many round
                            # hairs: at a dielectric's white F0 it mirrors a light as one pale plate; half of it, and
                            # in the hair's own colour, as light off and through hairs is)
                            "specularFactor": 0.5, "specularColorFactor": [round(float(c / max(max(sheen), 1e-6)), 3) for c in sheen]},
                                       "KHR_materials_anisotropy": ani,
                                       "KHR_materials_sheen": {"sheenColorFactor": sheen, "sheenRoughnessFactor": 0.35}}})
        rep["tiers"][tier] = {"glb": str(glb), "triangles": len(part["corner_vert"]) // 3, "layers": hc_["layers"],
                              "budget": hc_["budget"], "bytes": glb.stat().st_size, "clearance": hc_.get("clearance")}
    rep["maps"] = {k: str(v) for k, v in files.items()}
    rep["log"] = log
    if groom and h.get("style") == "strands":
        from . import hair_strands as hs
        import re
        sc = scalp(name, spec)
        g = groom_params(spec)
        tmp = Path(tempfile.mkdtemp(prefix="hifipushie-groom-"))
        locks = [k for k in resolve(spec, sc) if not re.fullmatch(r"t\d*band", k["name"])]
        colg = None
        if g.get("loose"):
            from . import hair_loose
            colg = hair_loose.collider(name, spec, sc)
        sd = hs.job(sc, g, spec, locks, tmp, count=int((h.get("export") or {}).get("strands", 0)) or None, col=colg)
        abc, usd = out_dir / f"{name}_groom.abc", out_dir / f"{name}_groom.usdc"  # (binary: the .usda was 33 MB)
        r = hs.evaluate(sd, abc=str(abc), usd=str(usd))
        got = next((json.loads(ln[8:]) for ln in r.splitlines() if ln.startswith("@@groom")), {})
        rep["groom"] = {**{k: v for k, v in got.items() if k not in ("abc", "usd")}, "alembic": str(abc), "usd": str(usd),
                        "bytes": {"alembic": abc.stat().st_size if abc.exists() else 0,
                                  "usd": usd.stat().st_size if usd.exists() else 0},
                        "note": "Alembic: curves + widths in cm (Unreal groom import; guides, ids and root uv are "
                                "the importer's defaults: Blender's Alembic writer drops per-curve attributes). USD: "
                                "BasisCurves + widths + groom_id / groom_guide / groom_group_id primvars, metres."}
    (out_dir / f"{name}_hair.json").write_text(json.dumps(rep, indent=1, default=float))
    if check or sheet:  # every tier re-imported and judged against the strands (check_tiers): WARNINGs in the report
        chk = check_tiers(name, rep, tiers=tiers, save=sheet, spec=spec)
        rep["checks"] = {t: {k: r[k] for k in ("test", "dither", "warnings")} for t, r in chk["tiers"].items()}
        rep["warnings"] = chk["warnings"]
        rep["checks_text"] = tiers_text(chk)
        if sheet:
            rep["sheet"] = str(sheet)
        (out_dir / f"{name}_hair.json").write_text(json.dumps(rep, indent=1, default=float))
    return rep


def export_cards(name: str, out_dir: Path, spec: dict, log: list) -> tuple[dict, dict]:
    """The hair as cards for an engine: the card mesh + the cap (coarse) in one mesh on the strand atlas, within
    `hair.export.triangles`. Part keys as export_part's, plus "vcolor" (per vertex: COLOR_0) and "hair" (the
    material's facts: alpha cutoff, layers' triangle ranges, the recipe); maps basecolor (RGBA), orm, normal,
    specular, aux."""
    from PIL import Image
    from . import hair_cards as hc
    t = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    h = hair_of(spec)
    ex = {**EXPORT_CARDS, **{k: v for k, v in (h.get("export") or {}).items() if k in EXPORT_CARDS}}
    j = job(name, {**spec, "hair": {**h, "style": "cards"}},
            budget=ex["tier"] or int(ex["triangles"]), cap_step=float(ex["cap_step"]))
    cd = j["cards"]
    cap, cards = dict(np.load(cd["cap"])), dict(np.load(cd["mesh"]))
    o = np.argsort(cards["layer"][cards["tris"][:, 0]], kind="stable")  # triangles by layer: a LOD is a range
    cards["tris"] = cards["tris"][o]
    M = hc.join(cap, cards)
    V, T = M["verts"].astype(np.float64), M["tris"]
    UV = M["uv"][T].reshape(-1, 2).astype(np.float64)
    _, tt, sg = _tangents(V, T, UV)
    n = M["normal"][T].reshape(-1, 3).astype(np.float64)
    tt = tt - (tt * n).sum(1, keepdims=True) * n
    tt = np.where(np.linalg.norm(tt, axis=1, keepdims=True) > 1e-9, _unit(tt), _unit(np.cross(n, [0.0, 0.0, 1.0])))
    lay = M["layer"][T[:, 0]]
    ranges = {("cap" if k < 0 else "tie" if k > 8 else f"layer{int(k)}"): [int(np.nonzero(lay == k)[0][0]), int((lay == k).sum())]
              for k in np.unique(lay)}
    lk = j["look"]
    part = {"verts": V.astype(np.float32), "corner_vert": T.ravel().astype(np.int64), "uv": UV.astype(np.float32),
            "normal": n.astype(np.float32), "tangent": tt.astype(np.float32), "sign": sg.astype(np.float32),
            "vcolor": M["col"].astype(np.float32),
            "hair": {"alpha_cutoff": float(ex["alpha_cutoff"]), "layers": ranges, "recipe": CARD_RECIPE,
                     "strands": hc.strands_of(spec), "budget": cd["budget"], "clearance": cd.get("clearance")}}
    aux = np.asarray(Image.open(cd["aux"]).convert("RGBA"), np.float32) / 255
    files = {"basecolor": out_dir / "hair_basecolor.png", "orm": out_dir / "hair_orm.png",
             "normal": out_dir / "hair_normal.png", "specular": out_dir / "hair_specular_gltf.png",
             "aux": out_dir / "hair_aux.png"}
    Image.open(cd["color"]).save(files["basecolor"])
    Image.open(cd["normal"]).convert("RGB").save(files["normal"])
    Image.open(cd["aux"]).save(files["aux"])
    if cd.get("flow"):
        files["flow"] = out_dir / "hair_flow.png"
        Image.open(cd["flow"]).convert("RGB").save(files["flow"])
    rough = np.clip(max(float(lk.get("roughness", 0.42)), 0.5) * (1.25 - 0.4 * aux[..., 2]), 0.05, 1.0)
    if cd.get("short"):  # a baked cap is a surface of many hairs' highlights already in its picture and normal map:
        rough = np.clip(max(float(lk.get("roughness", 0.42)), 0.85) * (1.12 - 0.15 * aux[..., 2]), 0.05, 1.0)  # glossy, it was tin foil
    occ = 0.55 + 0.45 * aux[..., 2]
    Image.fromarray((np.stack([occ, rough, np.zeros_like(occ)], -1) * 255 + 0.5).astype(np.uint8)).save(files["orm"])
    Image.fromarray(np.full((4, 4, 4), [255, 255, 255, 128], np.uint8), "RGBA").save(files["specular"])
    log.append(f"hair: {len(T)} triangles as cards (asked {ex['triangles']}: {cd['cards']} cards + {cd['baby']} baby "
               f"hairs, the cap {cd['cap_triangles']}; {cd['budget']}), strand atlas {aux.shape[1]}^2 generated, "
               f"{time.time() - t:.1f}s")
    return part, files


# ------------------------------------------------------------------------------------------------ drawn clumps

def top_to_azel(sc: Scalp, xy):
    """Points drawn on a top view of the head ([x, y] m from the head centre: x his left, y back) -> (az, el) of the
    scalp point under each, found along the vertical line (the highest scalp crossing)."""
    xy = np.asarray(xy, float)
    az0, el0 = az_el(np.stack([xy[:, 0], xy[:, 1], np.full(len(xy), 0.08)], 1))
    az, el = az0.copy(), el0.copy()
    for _ in range(12):  # solve for the scalp point whose x, y match (its radius varies with direction)
        P = sc.point(az, el, 0.0) - sc.C
        err = xy - P[:, :2]
        Q = P.copy()
        Q[:, :2] += err
        az, el = az_el(Q)
    return az, el


def _under_clumps(clumps: list, sc: Scalp | None = None, sink=True) -> list:
    """The layer under the drawn clumps, as an artist builds it: between each pair of neighbouring clumps of a row
    (consecutive, same name stem: top1, top2...) one more clump halfway between them, lying beneath both, so where
    their wedge tips part the gap shows hair, not the volume (the volume must never be a visible surface)."""
    import re

    def resample(xy, n=5):
        xy = np.asarray(xy, float)
        c = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
        t = np.linspace(0, c[-1], n)
        return np.stack([np.interp(t, c, xy[:, k]) for k in range(2)], 1)
    out = []
    for c0, c1 in zip(clumps, clumps[1:]):
        n0, n1 = c0.get("name", ""), c1.get("name", "")
        stem = re.sub(r"\d+$", "", n0)
        if not n0 or stem != re.sub(r"\d+$", "", n1):
            continue
        sk = sink.get(stem, True) if isinstance(sink, dict) else sink  # per row: {stem: sink | false}
        if sk is False:
            continue
        sk = 0.35 if sk is True else float(sk)
        key = "azel" if ("azel" in c0 and "azel" in c1) else "top"
        if key not in c0 or key not in c1:
            if sc is None or not all(("azel" in c or "top" in c) for c in (c0, c1)):
                continue
            key = "azel"  # one drawn on the top view, one on the head: both as [az, el]

        def pts(c):
            if key == "azel" and "azel" not in c:
                a_, e_ = top_to_azel(sc, np.asarray(c["top"], float))
                q = np.stack([a_, e_], 1)
            else:
                q = np.asarray(c[key], float).copy()
            if key == "azel":
                q[:, 0] = (q[:, 0] + 180) % 360 - 180  # azimuths either side of the front average sensibly
                q[:, 0] = np.degrees(np.unwrap(np.radians(q[:, 0])))  # a clump crossing the back stays continuous
            return resample(q)
        p0, p1 = pts(c0), pts(c1)
        if key == "azel":  # neighbours either side of the back (175 and -170) average across it, not the front
            p1[:, 0] += 360.0 * np.round((p0[:, 0] - p1[:, 0]).mean() / 360.0)
        mid = 0.5 * (p0 + p1)
        out.append({"name": f"{n0}_{n1}_under", key: mid.round(4).tolist(),
                    "width": max(float(c0.get("width", 0.055)), float(c1.get("width", 0.055))),
                    "sink": sk, "edge": 1.2, "taper": 0.85,
                    **({"root": min(float(c0.get("root", 1.0)), float(c1.get("root", 1.0)))}
                       if ("root" in c0 or "root" in c1) else {})})  # (a narrow-rooted row's unders too; sink 1: under the
        # underlayer itself, so the volume still showed between the wedges)
    return out


def split_tips(sc: Scalp, g: dict, line, name: str, lk: dict, n: int = 2, at: float = 0.6, fan: float = 0.5,
               keep: float = 0.2) -> dict:
    """A clump whose end breaks into n smaller locks, the way an artist splits a big shape's tip in twos and threes
    (negative space between the tips, not one blunt point): the clump itself is cut off `keep` past `at` (0..1 along
    it) so its end tucks under the children; each child starts at `at`, lies on top of it (its tips over the layer
    below), is ~1.3/n of its width, and they fan apart across the lock by `fan` x the clump's width at the tips.
    Lengths differ a little (equal tips read as a comb). Returns the children ({name}_t1...); lk is shortened in place."""
    pts = np.asarray(lk["pts"], float)
    P = _catmull(sc.point(pts[:, 0], pts[:, 1], pts[:, 2]), 48)
    c = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    u = c / max(c[-1], 1e-9)
    w, T = float(lk["width"]), float(lk["thickness"])
    tg = _unit(np.gradient(P, axis=0))
    nrm = _unit(P - sc.C)
    side = _unit(np.cross(nrm, tg))  # across the clump, in the head's tangent plane

    def resample(Q, lo, hi, k):
        t = np.linspace(lo, hi, k)
        return np.stack([np.interp(t, u, Q[:, q]) for q in range(3)], 1), t
    # the parent ends a little past the split, its tip under the children
    end = min(1.0, at + keep)
    k0 = max(3, len(pts) - 1)
    Pp, _ = resample(P, 0.0, end, k0)
    a, e, h = sc.coords(Pp)
    lk["pts"] = [[round(float(a[j]), 2), round(float(e[j]), 2), round(float(h[j]), 4)] for j in range(k0)]
    if lk.get("tilt"):
        lk["tilt"] = [round(float(v), 3) for v in lie_tilt(sc, g, line, _catmull(Pp, 4 * k0)[::4])]
    lk.pop("radius", None)
    lk.pop("handles", None)
    lk["taper"] = 1.0  # its cut end comes to a point under the children (a blunt end read as a block on top)
    out = {}
    rng = np.random.default_rng(int(hashlib.md5(name.encode()).hexdigest()[:6], 16))
    for i in range(n):
        o = (i - (n - 1) / 2) / max(n - 1, 1)  # -0.5 .. 0.5 across
        length = 1.0 - 0.12 * rng.uniform(0, 1) if n > 1 else 1.0
        Q, t = resample(P, at - 0.04, at + (1.0 - at) * length, 5)
        s_ = np.clip((t - at) / max(1.0 - at, 1e-9), 0, 1)
        j = np.clip(np.searchsorted(u, t), 0, len(u) - 1)
        off = (o * w * 0.55 * (1 - s_) + o * w * (0.55 + fan) * s_)[:, None] * side[j]  # start side by side, fan out
        # a child never strays further out of the hairline than the clump's own spine there (a split fringe
        # dropped one tip onto the forehead)
        a0, e0, _ = sc.coords(Q)
        lim = np.minimum(inside(sc, line, a0, e0), 0.004)
        for f in np.linspace(1.0, 0.0, 11):
            a1, e1, _ = sc.coords(Q + f * off)
            ok = inside(sc, line, a1, e1) >= lim - 1e-4
            if ok.all() or f == 0.0:
                break
        Q = Q + f * off + nrm[j] * (0.55 * T * np.sin(np.pi * np.clip(s_ * 1.4, 0, 1)) + 0.15 * T)[:, None]
        a, e, h = sc.coords(Q)
        cw = round(w * 1.3 / n * (1 + 0.15 * rng.uniform(-1, 1)), 4)
        out[f"{name}_t{i + 1}"] = {
            "tier": lk.get("tier", "drawn"), "pts": [[round(float(a[q]), 2), round(float(e[q]), 2),
                                                      round(float(h[q]), 4)] for q in range(len(Q))],
            "tilt": [round(float(v), 3) for v in lie_tilt(sc, g, line, Q)], "width": cw,
            "thickness": round(T * 0.8, 4), "cup": round(lie_cup(sc, cw, Q), 4), "taper": 1.0, "belly": 0.25,
            "root": 0.35, "twist": 0.0, "edge": lk.get("edge", 1.6), **({"grey": lk["grey"]} if "grey" in lk else {})}
    return out


ROOT_TILT = 0.5  # the climbing root's tilt, x the lie's tilt behind it (1: nape rows folded at their roots)
ROOT_CLIMB = 0.012  # m: the shortest run over which a drawn clump's root rises from under the layer to lie on it
TILT_MAX = 1.3  # rad: the most a drawn clump's flat side turns off facing away from the head centre
BEND_EASE = 0.7  # drawn clumps are eased until their spine's in-plane bend x half width is under this


def bend_ratio(sc: Scalp, Q, half):
    """Per point of a dense path on the head: how tightly it turns along the head's surface x the half width there
    (>= 1: a lock that wide folds its inner edge)."""
    d = np.gradient(Q, axis=0)
    ds = np.maximum(np.linalg.norm(d, axis=1), 1e-9)
    tg = d / ds[:, None]
    nr = _unit(Q - sc.C)
    b = _unit(np.cross(nr, tg))
    r = np.abs((np.gradient(tg, axis=0) / ds[:, None] * b).sum(1)) * half
    r[[0, -1]] = 0.0
    return r


def ease_bends(sc: Scalp, Q, half, limit: float = BEND_EASE, rounds: int = 200):
    """A dense path on the head smoothed (ends held, kept on the scalp's rays) where it turns tighter than `limit` x
    half width allows: a wide clump drawn round a sharp corner sweeps a wide curve instead."""
    Q = np.asarray(Q, float).copy()
    for _ in range(rounds):
        r = bend_ratio(sc, Q, half)
        if r.max() < limit:
            break
        wgt = np.clip((r - 0.8 * limit) / (0.2 * limit), 0, 1)
        wgt = np.convolve(wgt, np.ones(5) / 5, mode="same")  # ease the neighbourhood, not one point
        wgt[[0, -1]] = 0.0
        L = np.zeros_like(Q)
        L[1:-1] = 0.5 * (Q[:-2] + Q[2:]) - Q[1:-1]
        Q = Q + 0.5 * wgt[:, None] * L
        a, e = az_el(Q - sc.C)
        Q = sc.point(a, e, 0.0)
    return Q


def _to_hairline(sc: Scalp, line, Q, half, inset: float, rounds: int = 6, reach: float | None = None):
    """A dense path on the head moved across itself so the lock's edge facing the hairline (half width `half` per
    point) runs `inset` m inside the hairline (negative: tucked into the skin): the spine lies `half + inset` from the
    line. The edge of the front lock then IS the hairline, one designed sweep, instead of the volume's rim showing
    between it and the skin. `reach` (m): only where the edge already comes within this of that line (fully within
    half of it), so a lock that runs off the hairline keeps its drawn path there."""
    from scipy.ndimage import gaussian_filter1d
    Q = np.asarray(Q, float).copy()
    target = np.asarray(half, float) + inset
    eps = 0.4
    wgt = np.ones(len(Q))
    if reach is not None:
        a, e = az_el(Q - sc.C)
        gap = inside(sc, line, a, e) - target
        wgt = 1 - _ss((gap - 0.5 * reach) / (0.5 * reach))
        wgt = np.clip(gaussian_filter1d(wgt, 3.0, mode="nearest"), 0, 1)
        if wgt.max() < 0.02:
            return Q
    for _ in range(rounds):
        a, e = az_el(Q - sc.C)
        d = inside(sc, line, a, e)
        Pa = sc.point(a + eps, e, 0.0) - sc.point(a - eps, e, 0.0)
        Pe = sc.point(a, e + eps, 0.0) - sc.point(a, e - eps, 0.0)
        da = inside(sc, line, a + eps, e) - inside(sc, line, a - eps, e)
        de = inside(sc, line, a, e + eps) - inside(sc, line, a, e - eps)
        # the gradient of d on the scalp: v in span(Pa, Pe) with Pa.v = da, Pe.v = de
        M = np.stack([Pa, Pe], 1)  # (n, 2, 3)
        G = M @ np.transpose(M, (0, 2, 1))
        lam = np.linalg.solve(G + 1e-12 * np.eye(2), np.stack([da, de], 1)[..., None])[..., 0]
        v = (lam[:, :, None] * M).sum(1)
        step = -(wgt * (d - target) / np.maximum((v * v).sum(1), 1e-12))[:, None] * v
        Q = Q + step
        a, e = az_el(Q - sc.C)
        Q = sc.point(a, e, 0.0)
        if (wgt * np.abs(d - target)).max() < 0.0005:
            break
    return Q


def _edge_cup(sc: Scalp, g: dict, line, P, tilt, half, T) -> float:
    """The cup that brings a lock's edge facing the hairline down onto the underlayer there (a lock laid along a
    rolled front lies on the roll's tangent at its spine; its front edge stood off the roll and the dark rim of the
    volume showed under it). Near the most any control point needs (80th percentile: the roll at the quiff is where
    the rim showed), never less than the head's own sag."""
    P = np.asarray(P, float)
    tg = _unit(np.gradient(P, axis=0))
    n0 = _unit(P - sc.C)
    n0 = _unit(n0 - (n0 * tg).sum(1, keepdims=True) * tg)
    t = np.asarray(tilt, float)[:, None]
    nr = n0 * np.cos(t) + np.cross(tg, n0) * np.sin(t)
    b = _unit(np.cross(nr, tg))
    drops = []
    for sgn in (1.0, -1.0):
        E = P + sgn * np.asarray(half)[:, None] * b
        a, e, hE = sc.coords(E)
        drops.append((a, e, hE))
    # the side nearer the hairline
    (a1, e1, h1), (a2, e2, h2) = drops
    d1, d2 = inside(sc, line, a1, e1), inside(sc, line, a2, e2)
    pick = d1 < d2
    a, e, hE = np.where(pick, a1, a2), np.where(pick, e1, e2), np.where(pick, h1, h2)
    H, d_in = envelope(sc, g, line, a, e)
    want = under(g, H, a, e, d_in) + 0.35 * T
    need = (hE + 0.5 * T) - want  # the lens's outer face at the edge vs lying on the layer under it
    return float(np.clip(np.percentile(need[1:], 80), lie_cup(sc, 2 * float(np.max(half)), P), 0.03))


def drawn(sc: Scalp, g: dict, clumps: list) -> dict:
    """Clumps drawn on the top view: [{"name"?, "top": [[x, y], ...] (root first), "width", "thickness"?, "lie"?}]
    -> locks. Heights come from the volume: the root dives under whatever it grows from, the body lies with its back
    at the volume (the underlayer is sunk under it), the tip tucks onto the clump below (lifted `lie` x thickness,
    default 0.1); past the hairline (a fringe) it lies on the skin."""
    line = hairline(sc, g)
    out = {}
    clumps = list(clumps) + (_under_clumps(clumps, sc, g["drawn_under"]) if g.get("drawn_under", True) is not False else [])
    for i, c in enumerate(clumps):
        w = float(c.get("width", 0.055))
        # the drawing smoothed and resampled (6 points), with one more just past the root: the root grows from the
        # scalp and the clump is up at the volume a short way on (with the rise spread over the whole first segment
        # most of a short clump lay under the volume, which then showed as a smooth patch)
        if c.get("azel"):  # drawn on the head itself ([az, el] from the root)
            q = np.asarray(c["azel"], float)
            Q = _catmull(sc.point(q[:, 0], q[:, 1], 0.0), 40)
        else:  # drawn on the top view
            xy = _catmull(np.c_[np.asarray(c["top"], float), np.zeros(len(c["top"]))], 40)[:, :2]
            qa, qe = top_to_azel(sc, xy)
            Q = sc.point(qa, qe, 0.0)
        # a clump can't turn within its own width: eased where the drawing bends tighter (it folded into flakes)
        Q = ease_bends(sc, Q, 0.5 * w * lock_width({"Root": float(c.get("root", 1.0)),
                                                       "Belly": float(c.get("belly", 0.06)),
                                                       "Taper": float(c.get("taper", 1.0))}, np.linspace(0, 1, len(Q))))
        # the clump's outer edge laid on the hairline: one clean designed sweep. Per clump "to_hairline": inset m
        # (all along it) or {"inset", "reach"}; groom "hairline_edge": {"inset", "reach"} for every drawn clump whose
        # edge comes within reach of the hairline (the volume's rim showed between the clumps' edges and the skin)
        th = c.get("to_hairline", g.get("hairline_edge") if not c.get("name", "").endswith("_under") else None)
        if th is False:
            th = None
        laid = False
        if th is not None:
            thd = th if isinstance(th, dict) else {"inset": th}
            Q0 = Q
            Q = _to_hairline(sc, line, Q, 0.5 * w * lock_width({"Root": float(c.get("root", 1.0)),
                                                                "Belly": float(c.get("belly", 0.06)),
                                                                "Taper": float(c.get("taper", 1.0))},
                                                               np.linspace(0, 1, len(Q))), float(thd.get("inset", 0.0)),
                             reach=float(thd["reach"]) if thd.get("reach") is not None else None)
            laid = thd.get("reach") is None or float(np.abs(Q - Q0).max()) > 1e-4
            if laid:  # a hairline that turns (a temple corner) bent the path tighter than the lock's width allows
                Q = ease_bends(sc, Q, 0.5 * w * lock_width({"Root": float(c.get("root", 1.0)),
                                                               "Belly": float(c.get("belly", 0.06)),
                                                               "Taper": float(c.get("taper", 1.0))},
                                                              np.linspace(0, 1, len(Q))))
        cq =np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
        # (the root's climb out of the layer takes at least ROOT_CLIMB m: over 8% of a short nape lock it rose ~7 mm
        # in 5 mm, and the tilted lens folded there)
        # "climb" (m): how long the root takes to rise onto the layer; long, a narrow root (root 0.05-0.1) grows out
        # of the layer and the lock's body forms further back, with no blunt root end showing
        t1 = min(max(0.08, float(c.get("climb", ROOT_CLIMB)) / max(cq[-1], 1e-9)), 0.4)
        tt = np.r_[0.0, t1, np.linspace(max(0.25, t1 + 0.12), 1.0, 4)] * cq[-1]
        Q = np.stack([np.interp(tt, cq, Q[:, k]) for k in range(3)], 1)
        a, e = az_el(Q - sc.C)
        T = float(c.get("thickness", 0.0055 * w / 0.055))
        H, d_in = envelope(sc, g, line, a, e)
        U = under(g, H, a, e, d_in)
        u = tt / max(tt[-1], 1e-9)
        h = U + 0.35 * T
        # the root dives just under the underlayer where it grows (at the part the underlayer dips to the scalp):
        # sent down to the scalp under a full volume, a root climbed ~2 cm in its first centimetre and the wide lens
        # folded through itself there (flakes along the part)
        h[0] = max(min(U[0] - 0.5 * T, U[1] - T), 0.2 * T)
        h[-1] = U[-1] + float(c.get("lie", 0.1)) * T
        h = h - float(c.get("sink", 0.0)) * T * _ss(u / 0.2)  # an under clump lies beneath its neighbours
        h = np.where(d_in < 0, np.maximum(h, 0.55 * T), h)  # a fringe lies on the forehead
        if d_in[0] < 0:  # a root drawn on or past the hairline grows out of the skin there: its end is buried in
            # the skin (left lying on the forehead, a row of front roots read as rounded scales along the hairline)
            h[0] = -0.6 * T
        P = sc.point(a, e, h)
        tilt = lie_tilt(sc, g, line, _catmull(P, 4 * len(P))[::4])
        # the root takes the next point's tilt: there the spine climbs out of the scalp and the volume's normal turns
        # sideways at a parting, so its own tilt came out ~100 deg off the next one's: the lens twisted through
        # itself at the root (the flakes along the part); and no point lies more than TILT_MAX off the head's own
        tilt[0] = tilt[1]
        tilt = np.clip(tilt, -TILT_MAX, TILT_MAX)
        # where the root climbs out of the layer the spine bends up: a lens turned on its side there bends within its
        # own plane and folds (the nape rows' flags), so the climb faces out (ROOT_TILT of the lie's tilt)
        tilt[:2] = ROOT_TILT * tilt[2]
        cup = lie_cup(sc, w, P)
        if laid:  # its hairline edge brought down onto the layer under it
            cup = _edge_cup(sc, g, line, P, tilt, 0.5 * w * lock_width(
                {"Root": float(c.get("root", 1.0)), "Belly": float(c.get("belly", 0.06)),
                 "Taper": float(c.get("taper", 1.0))}, u), T)
        cup = float(c.get("cup", cup))
        name = c.get("name") or f"k{i:02d}"
        out[name] = {"tier": "drawn", "pts": [[round(float(a[k]), 2), round(float(e[k]), 2), round(float(h[k]), 4)]
                                              for k in range(len(a))],
                     "tilt": [round(float(v), 3) for v in tilt], "width": round(w, 4), "thickness": round(T, 4),
                     "cup": round(cup, 4), "taper": float(c.get("taper", 1.0)),  # wedges: widest
                     "belly": float(c.get("belly", 0.06)), "root": float(c.get("root", 1.0)), "twist": 0.0,  # at
                     "edge": float(c.get("edge", 1.6))}  # the root, to a thin sharp tip; a flat back with crisp edges
        gr = _grey(g, float(a[0]), float(e[0]), line)
        if gr > 0.01:
            out[name]["grey"] = round(gr, 3)
        if c.get("split"):  # breakup: the tip splits into smaller locks
            sp = c["split"] if isinstance(c["split"], dict) else {"n": int(c["split"])}
            out.update(split_tips(sc, g, line, name, out[name], int(sp.get("n", 2)), float(sp.get("at", 0.6)),
                                  float(sp.get("fan", 0.5)), float(sp.get("keep", 0.2))))
    return out


def layout(name: str, save: str | None = None, size: int = 520, spec: dict | None = None):
    """The groom seen from above as a designer's sketch: the hairline, the parting, every lock's spine (drawn clumps
    thick and labelled, with their width; grown locks thin, by tier), roots dotted, arrows at the tips. x his left
    to the right of the image? No: drawn as seen from above with the face at the bottom, his left on the image's
    right (so it matches the top view render)."""
    from PIL import Image, ImageDraw
    spec = store.load(name) if spec is None else spec
    sc = scalp(name, spec)
    g = groom_params(spec)
    line = hairline(sc, g)
    s = size / 0.24

    def px(P):
        Q = np.asarray(P, float) - sc.C
        return np.stack([size / 2 + Q[..., 0] * s, size / 2 - Q[..., 1] * s], -1)
    im = Image.new("RGB", (size, size), (246, 244, 240))
    dr = ImageDraw.Draw(im)
    a = np.arange(0.0, 360.0, 2.0)
    HL = px(sc.point(a, _line_at(line, a), 0.0))
    dr.line([tuple(p) for p in np.vstack([HL, HL[:1]])], fill=(150, 110, 90), width=2)
    xp = _part_x(g)
    if xp is not None:
        L = float(g["parting"].get("length", 0.1))
        y0 = sc.point(0.0, float(_line_at(line, 0.0)), 0.0)[1]
        dr.line([tuple(px([xp, y0, 0])), tuple(px([xp, y0 + L, 0]))], fill=(200, 60, 60), width=2)
    colours = {"drawn": (40, 40, 40), "strip": (120, 150, 190), "gap": (170, 170, 120), "fill": (170, 170, 120),
               "big": (60, 90, 60), "crown": (90, 120, 60)}
    for n, lk in sorted((hair_of(spec).get("locks") or {}).items(), key=lambda kv: kv[1].get("tier") == "drawn"):
        pts = np.asarray(lk["pts"], float)
        P = _catmull(sc.point(pts[:, 0], pts[:, 1], pts[:, 2]), 24)
        Pp = px(P)
        tier = lk.get("tier", "")
        col = colours.get(tier, (140, 140, 140))
        wpx = max(1, int(lk["width"] * s * 0.2))
        dr.line([tuple(p) for p in Pp], fill=col, width=wpx if tier == "drawn" else 1)
        r0 = Pp[0]
        dr.ellipse([r0[0] - 3, r0[1] - 3, r0[0] + 3, r0[1] + 3], outline=col)
        d = Pp[-1] - Pp[-3]
        d = d / max(np.linalg.norm(d), 1e-9)
        nrm = np.array([-d[1], d[0]])
        tip = Pp[-1]
        dr.polygon([tuple(tip + d * 7), tuple(tip - d * 3 + nrm * 5), tuple(tip - d * 3 - nrm * 5)], fill=col)
        if tier == "drawn":
            dr.text(tuple(r0 + np.array([4, -12])), n, fill=(20, 20, 20))
    dr.text((6, 6), f"{name}: from above, face at the bottom, his left on the right", fill=(60, 60, 60))
    dr.text((6, size - 16), "drawn clumps black (thickness = a fifth of the width); strips blue, gap locks olive; red = part",
            fill=(60, 60, 60))
    if save:
        im.save(save)
    return im


# ------------------------------------------------------------------------------------------------ the reference

def _rotvec(r):
    from scipy.spatial.transform import Rotation
    return Rotation.from_rotvec(r).as_matrix()


def fit_camera(name: str, points: dict, image_size, crop, spec: dict | None = None, view: str = "matched",
               save: bool = True, focal: float | None = None) -> dict:
    """A camera matching the reference image, fitted on face landmarks: points = {lm joint name: [u, v]} in the
    reference's pixels (u right, v down), image_size = [w, h], crop = [x0, y0, x1, y1] (the square the views show).
    Pinhole, principal point at the image centre; solves pose + focal by least squares from a frontal start. Saves
    <model>/ref_camera.json: the look frame (eye, dir, up, fov, shift) for the crop, plus the reprojection error."""
    from scipy.optimize import least_squares
    spec = store.load(name) if spec is None else spec
    from .spec import expand_mirror, geometry
    J = expand_mirror({k: v for k, v in geometry(spec).items() if k != "hair"})["joints"]
    names = [n for n in points if n in J]
    X = np.array([J[n]["pos"] for n in names], float)
    uv = np.array([points[n] for n in names], float)
    W, Hh = image_size
    cx, cy = W / 2, Hh / 2
    ctr = X.mean(0)
    B = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])  # world -> camera for a camera in front (looking +Y)

    def project(p):
        R = _rotvec(p[:3]) @ B
        Xc = (X - ctr) @ R.T + p[3:6]
        return np.stack([p[6] * Xc[:, 0] / Xc[:, 2] + cx, p[6] * Xc[:, 1] / Xc[:, 2] + cy], 1)
    p0 = np.r_[0, 0, 0, 0, 0, 1.0, 2000.0]
    uc = uv.mean(0)
    p0[3], p0[4] = (uc[0] - cx) / p0[6] * p0[5], (uc[1] - cy) / p0[6] * p0[5]
    if focal:  # another figure in the same picture: the same lens (a free focal ran off to infinity, orthographic)
        p0[6] = float(focal)
        p0[3], p0[4] = (uc[0] - cx) / p0[6] * p0[5], (uc[1] - cy) / p0[6] * p0[5]
        r = least_squares(lambda q: (project(np.r_[q, focal]) - uv).ravel(), p0[:6],
                          x_scale=[0.1, 0.1, 0.1, 0.05, 0.05, 0.3])
        p = np.r_[r.x, focal]
    else:
        r = least_squares(lambda p: (project(p) - uv).ravel(), p0, x_scale=[0.1, 0.1, 0.1, 0.05, 0.05, 0.3, 500])
        p = r.x
    err = np.linalg.norm(project(p) - uv, axis=1)
    R = _rotvec(p[:3]) @ B
    eye = ctr - R.T @ p[3:6]  # camera centre in world
    fwd = R.T @ np.array([0.0, 0.0, 1.0])
    up = R.T @ np.array([0.0, -1.0, 0.0])
    x0, y0, x1, y1 = crop
    side = max(x1 - x0, y1 - y0)
    fov = float(np.degrees(2 * np.arctan(side / 2 / p[6])))
    # the crop's centre off the principal point: Blender's lens shift, in units of the frame's larger side
    shift = [float(((x0 + x1) / 2 - cx) / side), float(-((y0 + y1) / 2 - cy) / side)]
    cam = {"name": view, "eye": eye.tolist(), "dir": (-fwd).tolist(), "up": up.tolist(), "fov": fov,
           "shift": shift, "crop": list(crop), "image_size": list(image_size), "focal_px": float(p[6]),
           "R": R.tolist(), "t": p[3:6].tolist(), "ctr": ctr.tolist(),
           "error_px": {n: round(float(e), 1) for n, e in zip(names, err)}}
    if save:
        (store._dir(name) / "ref_camera.json").write_text(json.dumps(cam, indent=1))
    return cam


def ref_camera(name: str) -> dict | None:
    f = store._dir(name) / "ref_camera.json"
    return json.loads(f.read_text()) if f.exists() else None


def ref_views(name: str) -> list:
    """Every matched view as (view, camera, trace): the primary ("matched": ref_camera.json, ref_trace.json) then each
    of the trace's "views" (another figure in the same picture, or another picture: a turnaround's side or back),
    whose cameras live in ref_cameras.json. A view's trace inherits "image" from the main trace."""
    tr, cam = ref_trace(name), ref_camera(name)
    out = [("matched", cam, tr)] if (tr is not None and cam is not None) else []
    f = store._dir(name) / "ref_cameras.json"
    cams = json.loads(f.read_text()) if f.exists() else {}
    for v, t in ((tr or {}).get("views") or {}).items():
        if v in cams:
            out.append((v, cams[v], {"image": tr.get("image"), **t}))
    return out


def project_ref(cam: dict, P):
    """World points -> reference image pixels (u, v) through the matched camera."""
    R, t, ctr = np.array(cam["R"]), np.array(cam["t"]), np.array(cam["ctr"])
    W, Hh = cam["image_size"]
    Xc = (np.asarray(P, float) - ctr) @ R.T + t
    return np.stack([cam["focal_px"] * Xc[..., 0] / Xc[..., 2] + W / 2,
                     cam["focal_px"] * Xc[..., 1] / Xc[..., 2] + Hh / 2], -1)


def ray_onto(sc: Scalp, g: dict, cam: dict, uv, onto: str = "volume"):
    """Reference pixels -> points on the head (the scalp, or the groom's volume): each pixel's camera ray, first
    crossing of the surface (sampled from the camera out)."""
    R, t, ctr = np.array(cam["R"]), np.array(cam["t"]), np.array(cam["ctr"])
    W, Hh = cam["image_size"]
    eye = ctr - R.T @ t
    uv = np.atleast_2d(np.asarray(uv, float))
    dc = np.stack([(uv[:, 0] - W / 2) / cam["focal_px"], (uv[:, 1] - Hh / 2) / cam["focal_px"],
                   np.ones(len(uv))], 1)
    D = _unit(dc @ R)  # world directions
    line = hairline(sc, g)
    dist = np.linalg.norm(sc.C - eye)
    ts = np.linspace(dist - 0.2, dist + 0.05, 500)
    out = []
    for d in D:
        P = eye + ts[:, None] * d
        a, e, hh = sc.coords(P)
        if onto == "volume":
            Hv, _ = envelope(sc, g, line, a, e)
            hh = hh - Hv
        k = int(np.argmax(hh < 0)) if np.any(hh < 0) else int(np.argmin(hh))  # a miss: its closest approach
        out.append(P[k])
    return np.array(out)


def ref_trace(name: str) -> dict | None:
    """The reference traced by hand (<model>/ref_trace.json, reference pixels): "part" (polyline from its start),
    "hairline" (polyline across the forehead), "hair" (closed polygon of the visible hair), "clumps" ([{"name",
    "line": root -> tip, "width": px}])."""
    f = store._dir(name) / "ref_trace.json"
    return json.loads(f.read_text()) if f.exists() else None


def _to_crop(cam: dict, uv, W: int):
    x0, y0, x1, y1 = cam["crop"]
    uv = np.asarray(uv, float)
    return (uv - [x0, y0]) * (W / max(x1 - x0, y1 - y0))


def _poly_dist(P, Q):
    """Mean and max distance from each point of P to the polyline Q (px)."""
    P, Q = np.asarray(P, float), np.asarray(Q, float)
    A, B = Q[:-1], Q[1:]
    AB = B - A
    t = np.clip(((P[:, None] - A) * AB).sum(-1) / np.maximum((AB * AB).sum(-1), 1e-9), 0, 1)
    d = np.linalg.norm(P[:, None] - (A + t[..., None] * AB), axis=-1).min(1)
    return d


def _dense(Q, step=2.0):
    Q = np.asarray(Q, float)
    c = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
    t = np.arange(0, c[-1] + 1e-9, step)
    return np.stack([np.interp(t, c, Q[:, k]) for k in range(2)], 1)


def model_lines(name: str, sc: Scalp, cam: dict, spec: dict) -> dict:
    """The groom's own lines in reference pixels, through the matched camera: the hairline (the part of it facing the
    camera), the parting (drawn clumps' roots on the part side: their start points), each drawn clump's spine."""
    g = groom_params(spec)
    line = hairline(sc, g)
    az = np.arange(-70.0, 71.0, 1.0)
    P = sc.point(az, _line_at(line, az), 0.0)
    out = {"hairline": project_ref(cam, P).tolist()}
    locks = (spec.get("hair") or {}).get("locks") or {}
    cl = {}
    for n, lk in locks.items():
        if lk.get("tier") not in ("drawn", "hand") or n.endswith("_under"):
            continue
        p = np.asarray(lk["pts"], float)
        Q = sc.point(p[:, 0], p[:, 1], p[:, 2])
        if lk.get("tier") == "hand":  # locks added by hand anywhere: only those the camera sees (a back lock's spine
            # projected across the face, and the clump match could pick it)
            if float(np.mean(_unit(Q - sc.C) @ _unit(np.asarray(cam["eye"]) - sc.C))) < 0.2:
                continue
        cl[n] = project_ref(cam, _catmull(Q, 24)).tolist()
    out["clumps"] = cl
    q = part_line(sc, g)
    if q is not None:
        H, _ = envelope(sc, g, line, q[:, 0], q[:, 1])
        out["part"] = project_ref(cam, sc.point(q[:, 0], q[:, 1], H)).tolist()
    return out


def fit_metrics(name: str, sc: Scalp, cam: dict, spec: dict, hair_mask=None, tr: dict | None = None,
                owners=None) -> dict:
    """The groom against the traced reference in the matched view (reference pixels, and mm at the head's depth):
    part start (px) and direction (deg) error, hairline mean/max distance, hair silhouette IoU + mean boundary
    distance (from the matched id pass), the outline per head region (`outline_regions`), the hair's top over the
    brows, each traced clump's direction error against the nearest drawn clump."""
    tr = ref_trace(name) if tr is None else tr
    if tr is None:
        return {}
    ml = model_lines(name, sc, cam, spec)
    mm = 1000 * np.linalg.norm(np.asarray(cam["eye"]) - sc.C) / cam["focal_px"]  # mm per reference pixel
    out = {"mm_per_px": round(float(mm), 2)}

    def ang(v):
        return np.degrees(np.arctan2(v[1], v[0]))
    if tr.get("part") and ml.get("part"):
        a, b = np.asarray(tr["part"], float), np.asarray(ml["part"], float)
        da = (ang(a[min(3, len(a) - 1)] - a[0]) - ang(b[min(3, len(b) - 1)] - b[0]) + 180) % 360 - 180
        out["part_start_px"] = round(float(np.linalg.norm(a[0] - b[0])), 1)
        out["part_dir_deg"] = round(float(abs(da)), 1)
    if tr.get("hairline"):
        d = _poly_dist(_dense(tr["hairline"]), ml["hairline"])
        out["hairline_px"] = [round(float(d.mean()), 1), round(float(d.max()), 1)]
    if tr.get("hair") and hair_mask is not None:
        from PIL import Image, ImageDraw
        from scipy.ndimage import distance_transform_edt, binary_erosion
        x0, y0, x1, y1 = cam["crop"]
        Wm = hair_mask.shape[0]
        im = Image.new("L", (Wm, Wm), 0)
        ImageDraw.Draw(im).polygon([tuple(p) for p in _to_crop(cam, tr["hair"], Wm)], fill=255)
        R = np.asarray(im) > 0
        M = hair_mask.copy()
        if tr.get("clip_y") is not None:  # under it: ear, sideburn, beard (not traced)
            cy = int(round((tr["clip_y"] - y0) * Wm / max(x1 - x0, y1 - y0)))
            R[cy:], M[cy:] = False, False
        out["iou"] = round(float((R & M).sum() / max((R | M).sum(), 1)), 3)
        bR, bM = R & ~binary_erosion(R), M & ~binary_erosion(M)
        s = (max(x1 - x0, y1 - y0)) / Wm  # reference px per mask px
        if bR.any() and bM.any():
            d1 = distance_transform_edt(~bM)[bR]
            d2 = distance_transform_edt(~bR)[bM]
            out["outline_px"] = [round(float(np.r_[d1, d2].mean() * s), 1), round(float(max(d1.max(), d2.max()) * s), 1)]
        fe = front_edge(cam, tr, hair_mask, mm, owners=owners)
        if fe:
            out["front_edge"] = fe
        reg, brow = outline_regions(sc, cam, spec, R, M, tr, s * mm)
        out["regions"] = reg
        if brow:
            out["over_brow_mm"] = brow
    if tr.get("clumps") and ml["clumps"]:
        errs = {}
        for c in tr["clumps"]:
            L = np.asarray(c["line"], float)
            # the model's clump nearest along the traced one (mean distance of its points to each spine)
            best = min(ml["clumps"].items(), key=lambda kv: _poly_dist(_dense(L, 4), kv[1]).mean())
            Q = np.asarray(best[1], float)
            dl = _dense(L, 4)
            # direction where they overlap: the traced one's overall heading vs the model spine's over the same span
            k = [int(np.argmin(np.linalg.norm(Q - p, axis=1))) for p in (dl[0], dl[-1])]
            v2 = Q[max(k)] - Q[min(k)] if max(k) > min(k) else Q[-1] - Q[0]
            if np.dot(v2, L[-1] - L[0]) < 0:
                v2 = -v2
            da = (ang(L[-1] - L[0]) - ang(v2) + 180) % 360 - 180
            errs[c.get("name", str(len(errs)))] = [best[0], round(float(abs(da)), 1),
                                                   round(float(_poly_dist(dl, Q).mean()), 1)]
        out["clumps"] = errs
        out["clump_dir_deg_mean"] = round(float(np.mean([v[1] for v in errs.values()])), 1)
    return out


EDGE_SMOOTH = 0.008  # m: the hairline edge's own sweep is the edge with tips/notches narrower than ~this taken out
EDGE_REACH = 0.03  # m: how far either side of the traced hairline the rendered edge is looked for


def front_edge(cam: dict, tr: dict, mask, mm_px: float, owners=None) -> dict | None:
    """The hair's edge against the skin along the traced hairline, measured on the matched id pass: at each point of
    the traced line (every 1.5 mm) the outermost hair pixel along the line's normal (within EDGE_REACH). Its
    roughness is the edge minus itself smoothed along the line (EDGE_SMOOTH): `rough_mm` (rms) and `tooth_mm` (the
    worst tip or notch) read as a jagged, torn hairline past ~1 / ~3 mm (the reference's line is one clean sweep);
    `turn_deg_cm` = how much the edge turns per cm beyond its smoothed sweep (zigzag). `off_mm` = ours minus the
    trace on average (+: our edge sits further out onto the skin), `holes` = the share of the band 1-6 mm inside our
    edge that shows skin (a torn edge: tips with skin between them)."""
    from scipy.ndimage import gaussian_filter1d, map_coordinates, median_filter
    if not tr.get("hairline") or mask is None:
        return None
    Wm = mask.shape[0]
    x0, y0, x1, y1 = cam["crop"]
    px_mm = (Wm / max(x1 - x0, y1 - y0)) / mm_px  # mask px per mm
    L = _to_crop(cam, _dense(tr["hairline"], 1.0), Wm)
    if len(L) < 8:
        return None
    c = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(L, axis=0), axis=1))]
    t = np.arange(0, c[-1], 1.5 * px_mm)
    L = np.stack([np.interp(t, c, L[:, k]) for k in range(2)], 1)
    tg = np.gradient(gaussian_filter1d(L, 3, axis=0, mode="nearest"), axis=0)
    tg /= np.maximum(np.linalg.norm(tg, axis=1, keepdims=True), 1e-9)
    nrm = np.stack([tg[:, 1], -tg[:, 0]], 1)
    if tr.get("landmarks"):  # outward = onto the skin: toward the face's landmarks (the U's inside)
        face = _to_crop(cam, list(tr["landmarks"].values()), Wm).mean(0)
        if np.mean(((face - L) * nrm).sum(1)) < 0:
            nrm = -nrm
    reach = EDGE_REACH * 1000 * px_mm
    s = np.arange(-reach, reach + 1e-9, 0.5)
    S = L[:, None, :] + s[None, :, None] * nrm[:, None, :]  # (n, k, [x, y])
    hv = map_coordinates(mask.astype(float), [S[..., 1].ravel(), S[..., 0].ravel()], order=1, mode="constant",
                         cval=0.0).reshape(S.shape[:2]) > 0.5
    have = hv.any(1) & hv[:, 0]  # the line's inside must be hair (else the part or a gap crosses it)
    if have.sum() < 8:
        return None
    last = np.where(hv.any(1), len(s) - 1 - np.argmax(hv[:, ::-1], 1), 0)
    e = s[last] / px_mm  # mm out from the traced line
    k = np.nonzero(have)[0]
    e, tt = e[k], t[k] / px_mm
    # the sweep: a running median then a light Gaussian (a median keeps the temple's corners, which are design, and
    # drops tips and notches narrower than EDGE_SMOOTH: a Gaussian alone counted every corner as roughness)
    sm = gaussian_filter1d(median_filter(e, size=2 * int(EDGE_SMOOTH * 1000 / 1.5) + 1, mode="nearest"), 1.0,
                           mode="nearest")
    r = e - sm
    turn = np.abs(np.diff(np.arctan2(np.diff(e), np.diff(tt)) - np.arctan2(np.diff(sm), np.diff(tt))))
    inner = []
    for i in k:  # holes: skin in the band 1..6 mm inside our edge
        sel = (s >= s[last[i]] - 6 * px_mm) & (s <= s[last[i]] - px_mm)
        inner.append(1.0 - hv[i, sel].mean() if sel.any() else 0.0)
    E = L[k] + (e * px_mm)[:, None] * nrm[k]  # the measured edge in mask px
    front_edge.last = E
    out = {"rough_mm": round(float(np.sqrt(np.mean(r ** 2))), 2), "tooth_mm": round(float(np.abs(r).max()), 1),
           "turn_deg_cm": round(float(np.degrees(turn.sum()) / max(tt[-1] - tt[0], 1e-9) * 10), 1),
           "off_mm": round(float(e.mean()), 1), "holes": round(float(np.mean(inner)), 3)}
    if owners is not None:  # which lock makes each tooth: the hair vertex nearest the camera at that edge pixel
        P, ids, names = owners
        R_, t_, ctr = np.array(cam["R"]), np.array(cam["t"]), np.array(cam["ctr"])
        depth = ((np.asarray(P, float) - ctr) @ R_.T + t_)[:, 2]
        uv = _to_crop(cam, project_ref(cam, P), Wm)
        teeth = {}
        for i in np.argsort(-np.abs(r)):
            if abs(r[i]) < 2.0 or len(teeth) >= 6:
                break
            near = np.nonzero(np.linalg.norm(uv - E[i], axis=1) < 1.5 * px_mm)[0]
            if not len(near):
                continue
            who = str(names[ids[near[np.argmin(depth[near])]]])
            if who not in teeth:
                teeth[who] = round(float(r[i]), 1)  # + a tip hanging out, - a notch
        out["teeth"] = teeth
    return out


FLOW_BAND = (0.004, 0.028)  # m inside the traced hairline: the band whose strand direction front_flow compares
FLOW_BINS = 6


def _orientation(img, sigma: float):
    """Per pixel the strand direction (deg, image axes, y down; axial: mod 180) and its coherence 0..1 from the
    structure tensor of the luminance (strands run across the strongest gradient)."""
    from scipy.ndimage import gaussian_filter, sobel
    A = np.asarray(img.convert("L"), float)
    gx, gy = sobel(A, 1), sobel(A, 0)
    Jxx, Jyy, Jxy = (gaussian_filter(v, sigma) for v in (gx * gx, gy * gy, gx * gy))
    ang = 0.5 * np.degrees(np.arctan2(2 * Jxy, Jxx - Jyy)) + 90.0
    coh = np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2) / (Jxx + Jyy + 1e-9)
    return ang, coh


def front_flow(cam: dict, tr: dict, ref_img, our_img, mask, mm_px: float) -> dict | None:
    """Which way the strands run in the band just inside the hairline (FLOW_BAND), the reference against our render
    in the same camera, read off the images themselves (structure tensor: grooves, sheen and lock edges). Per bin
    along the traced hairline (from its first traced point to its last), the strands' angle to the hairline (deg,
    axial: 0 = along the hairline, a headband; +-90 = straight out of it), the reference's and ours.
    {"bins": [[ref, ours], ...], "err_deg": mean |ref - ours|}."""
    if not tr.get("hairline") or mask is None:
        return None
    from scipy.ndimage import gaussian_filter1d
    W = mask.shape[0]
    x0, y0, x1, y1 = cam["crop"]
    px_mm = (W / max(x1 - x0, y1 - y0)) / mm_px
    ref = ref_img.resize((W, W))
    our = our_img.resize((W, W))
    sig = 1.5 * px_mm
    ra, rc = _orientation(ref, sig)
    oa, oc = _orientation(our, sig)
    L = _to_crop(cam, _dense(tr["hairline"], 1.0), W)
    c = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(L, axis=0), axis=1))]
    t = np.arange(0, c[-1], 1.0 * px_mm)
    L = np.stack([np.interp(t, c, L[:, k]) for k in range(2)], 1)
    tg = np.gradient(gaussian_filter1d(L, 4, axis=0, mode="nearest"), axis=0)
    tg /= np.maximum(np.linalg.norm(tg, axis=1, keepdims=True), 1e-9)
    nrm = np.stack([tg[:, 1], -tg[:, 0]], 1)
    if tr.get("landmarks"):  # inward = into the hair: away from the face
        face = _to_crop(cam, list(tr["landmarks"].values()), W).mean(0)
        if np.mean(((face - L) * nrm).sum(1)) > 0:
            nrm = -nrm
    line_ang = np.degrees(np.arctan2(tg[:, 1], tg[:, 0]))
    bins = []
    edges = np.linspace(0, len(L), FLOW_BINS + 1).astype(int)
    for b in range(FLOW_BINS):
        rs, os_ = [], []
        for i in range(edges[b], edges[b + 1]):
            for dmm in np.linspace(FLOW_BAND[0] * 1000, FLOW_BAND[1] * 1000, 7):
                x, y = L[i] + dmm * px_mm * nrm[i]
                xi, yi = int(round(x)), int(round(y))
                if not (0 <= xi < W and 0 <= yi < W) or not mask[yi, xi]:
                    continue
                for A_, C_, acc in ((ra, rc, rs), (oa, oc, os_)):
                    rel = np.radians(2 * (A_[yi, xi] - line_ang[i]))
                    acc.append((C_[yi, xi] * np.cos(rel), C_[yi, xi] * np.sin(rel)))
        if len(rs) < 5:
            bins.append(None)
            continue

        def mean_ang(v):
            s = np.sum(v, 0)
            return float((0.5 * np.degrees(np.arctan2(s[1], s[0])) + 90) % 180 - 90)
        bins.append([round(mean_ang(rs)), round(mean_ang(os_))])
    good = [b for b in bins if b]
    if not good:
        return None
    err = [abs((b[0] - b[1] + 90) % 180 - 90) for b in good]
    return {"bins": bins, "err_deg": round(float(np.mean(err)), 1)}


REGION_NAMES = ("front", "top", "side.L", "side.R", "back.L", "back.R", "back")


def region_of(az, el):
    """The head region a point on the hair is in, by where it sits round the centre: top (el >= 55), else front
    (within 45 deg of the face), side (45-110 deg round: his left .L is az > 0), back.L / back.R (110-160), back."""
    fa = np.abs(((np.asarray(az, float) + 180) % 360) - 180)
    lr = np.where(((np.asarray(az, float) + 180) % 360) - 180 > 0, ".L", ".R")
    reg = np.where(fa < 45, "front", np.where(fa < 110, "side", np.where(fa < 160, "back", "back_")))
    reg = np.where(reg == "back_", "back", np.char.add(reg, np.where(reg == "front", "", lr)))
    return np.where(np.asarray(el) >= 55, "top", reg)


OUTLINE_STEP = 3.0  # deg: the matched view's outline is sampled on rays from the head centre this far apart


def outline_regions(sc: Scalp, cam: dict, spec: dict, R, M, tr: dict, mm_px: float):
    """The hair outline in a matched view per head region, in mm at the head's depth. Rays from the head centre's
    image every OUTLINE_STEP deg (above clip_y); on each: the reference outline (outermost traced hair), ours
    (outermost hair in the id pass) and the bare head's (the scalp without hair, projected). Each ray is labelled by
    the region (`region_of`) of the groom volume's point that makes the outline there. Per region:
    "err" = ours - reference (mean over its rays; + = ours sticks out further), "worst" (signed, largest |err|),
    "ref_hair" / "our_hair" = how far each outline stands outside the bare head (the hair's thickness the view
    shows: negative ref_hair = the bare head is already outside the reference there, which hair can't fix),
    "rays". Also the hair's top over the brows (mm along the image's vertical, between the brows): [reference, ours]."""
    g = groom_params(spec)
    line = hairline(sc, g)
    Wm = R.shape[0]
    c = _to_crop(cam, project_ref(cam, sc.C[None])[0][None], Wm)[0]
    AA, EE = np.meshgrid(np.arange(0.0, 360.0, 2.0), np.arange(-40.0, 90.0, 1.5), indexing="ij")
    Hh, d_in = envelope(sc, g, line, AA, EE)
    hair = d_in > 0

    def polar(P):
        q = _to_crop(cam, project_ref(cam, P), Wm) - c
        return np.degrees(np.arctan2(q[..., 0], -q[..., 1])) % 360, np.hypot(q[..., 0], q[..., 1])
    th_v, r_v = polar(sc.point(AA, EE, Hh)[hair])
    th_s, r_s = polar(sc.point(AA, EE, 0.0).reshape(-1, 3))
    az_v, el_v = AA[hair], EE[hair]
    x0, y0, x1, y1 = cam["crop"]
    cy = (tr["clip_y"] - y0) * Wm / max(x1 - x0, y1 - y0) if tr.get("clip_y") is not None else Wm
    rr = np.arange(0.0, 1.5 * Wm, 0.5)
    rows = {}
    for th in np.arange(0.0, 360.0, OUTLINE_STEP):
        t = np.radians(th)
        u, v = c[0] + rr * np.sin(t), c[1] - rr * np.cos(t)
        ok = (u >= 0) & (u < Wm) & (v >= 0) & (v < min(Wm, cy))
        if ok.sum() < 2:
            continue
        iu, iv = u[ok].astype(int), v[ok].astype(int)
        inR, inM = R[iv, iu], M[iv, iu]
        if not inR.any():
            continue
        r_ref = rr[ok][inR].max()
        if v[ok][inR][np.argmax(rr[ok][inR])] > cy - 4:  # the clip line, not an outline
            continue
        r_mod = rr[ok][inM].max() if inM.any() else 0.0
        near = np.abs(((th_v - th + 180) % 360) - 180) < OUTLINE_STEP
        nears = np.abs(((th_s - th + 180) % 360) - 180) < OUTLINE_STEP
        if not near.any() or not nears.any():
            continue
        k = np.argmax(np.where(near, r_v, -1))
        reg = str(region_of(az_v[k], el_v[k]))
        r_sc = r_s[nears].max()
        rows.setdefault(reg, []).append((r_mod - r_ref, r_ref - r_sc, r_mod - r_sc))
    out = {}
    for reg in REGION_NAMES:
        if reg not in rows:
            continue
        a = np.asarray(rows[reg]) * mm_px
        out[reg] = {"err": round(float(a[:, 0].mean()), 1), "worst": round(float(a[np.argmax(np.abs(a[:, 0])), 0]), 1),
                    "ref_hair": round(float(a[:, 1].mean()), 1), "our_hair": round(float(a[:, 2].mean()), 1),
                    "rays": len(a)}
    brow = None
    lms = tr.get("landmarks") or {}
    if "lm_brow_mid.L" in sc.lm and "lm_brow_mid.R" in sc.lm:
        bm = _to_crop(cam, project_ref(cam, np.array([sc.lm["lm_brow_mid.L"], sc.lm["lm_brow_mid.R"]])), Wm)
        br = _to_crop(cam, [lms[k] for k in ("lm_brow_mid.L", "lm_brow_mid.R")], Wm) \
            if all(k in lms for k in ("lm_brow_mid.L", "lm_brow_mid.R")) else bm
        lo, hi = int(max(0, min(bm[:, 0].min(), br[:, 0].min()))), int(min(Wm, max(bm[:, 0].max(), br[:, 0].max())) + 1)

        def top(mask):
            cols = mask[:, lo:hi]
            rws = np.where(cols.any(1))[0]
            return float(rws.min()) if len(rws) else np.nan
        brow = [round(float((br[:, 1].mean() - top(R)) * mm_px), 1), round(float((bm[:, 1].mean() - top(M)) * mm_px), 1)]
    return out, brow


def trace_overlay(name: str, sc: Scalp, cam: dict, img, spec: dict, tr: dict | None = None, mask=None):
    """The matched render with the traced reference lines (yellow, the hair outline orange) and the groom's own
    (cyan); `mask` (the matched id pass's hair) adds our hair's outline in magenta."""
    from PIL import Image, ImageDraw
    tr = ref_trace(name) if tr is None else tr
    if tr is None:
        return None
    W = img.width
    im = img.copy()
    if mask is not None:
        from scipy.ndimage import binary_erosion
        m = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize((W, W))) > 127
        edge = m & ~binary_erosion(m, iterations=2)
        a = np.asarray(im).copy()
        a[edge] = (255, 60, 230)
        im = Image.fromarray(a)
    dr = ImageDraw.Draw(im)
    ml = model_lines(name, sc, cam, spec)

    def poly(pts, col, w=2, closed=False):
        q = [tuple(p) for p in _to_crop(cam, pts, W)]
        if closed:
            q = q + q[:1]
        if len(q) > 1:
            dr.line(q, fill=col, width=w)
    for key, col in (("hairline", None), ("part", None)):
        if tr.get(key):
            poly(tr[key], (255, 230, 40), 3)
        if ml.get(key):
            poly(ml[key], (40, 230, 255), 2)
    if tr.get("hair"):
        poly(tr["hair"], (255, 160, 40), 2, closed=True)
    for c in tr.get("clumps", []):
        poly(c["line"], (255, 230, 40), 2)
        e = _to_crop(cam, c["line"][-1:], W)[0]
        dr.ellipse([e[0] - 3, e[1] - 3, e[0] + 3, e[1] + 3], fill=(255, 230, 40))
    for q in ml["clumps"].values():
        poly(q, (40, 230, 255), 1)
    return im


def trace_image(name: str, out: str | None = None, scale: float = 2.0):
    """The reference crop with the trace drawn on it (part red, hairline white, hair outline orange, clumps yellow
    with tip dots, landmarks green with the matched camera's reprojection in cyan). Returns the image."""
    from PIL import Image, ImageDraw
    tr, cam = ref_trace(name) or {}, ref_camera(name) or {}
    img, _ = reference_image(name)
    if img is None:
        raise HairError("the trace has no reference image (ref_trace.json \"image\")")
    im = Image.open(img).convert("RGB")
    x0, y0, x1, y1 = cam.get("crop") or tr.get("crop") or [0, 0, im.width, im.height]
    im = im.crop((x0, y0, x1, y1))
    im = im.resize((int(im.width * scale), int(im.height * scale)))
    dr = ImageDraw.Draw(im)

    def q(pts):
        return [((u - x0) * scale, (v - y0) * scale) for u, v in pts]
    if tr.get("hair"):
        dr.line(q(tr["hair"] + tr["hair"][:1]), fill=(255, 160, 40), width=2)
    if tr.get("hairline"):
        dr.line(q(tr["hairline"]), fill=(255, 255, 255), width=3)
    if tr.get("part"):
        dr.line(q(tr["part"]), fill=(255, 40, 40), width=4)
    for c in tr.get("clumps") or []:
        dr.line(q(c["line"]), fill=(255, 230, 40), width=3)
        e = q(c["line"][-1:])[0]
        dr.ellipse([e[0] - 5, e[1] - 5, e[0] + 5, e[1] + 5], fill=(255, 230, 40))
        r = q(c["line"][:1])[0]
        dr.text((r[0] + 4, r[1] - 12), c.get("name", ""), fill=(255, 255, 255))
    lms = tr.get("landmarks") or {}
    if lms and cam.get("R"):
        spec = store.load(name)
        from .spec import expand_mirror, geometry
        J = expand_mirror({k: v for k, v in geometry(spec).items() if k != "hair"})["joints"]
        for n, uv in lms.items():
            a = q([uv])[0]
            dr.ellipse([a[0] - 4, a[1] - 4, a[0] + 4, a[1] + 4], outline=(60, 255, 60), width=2)
            if n in J:
                b = q(project_ref(cam, np.asarray(J[n]["pos"], float)[None]).tolist())[0]
                dr.line([a, b], fill=(40, 230, 255), width=2)
    if tr.get("clip_y") is not None:
        y = (tr["clip_y"] - y0) * scale
        dr.line([(0, y), (im.width, y)], fill=(120, 120, 255), width=1)
    if out:
        im.save(out)
    return im


def _signed(az):
    return (np.asarray(az, float) + 180) % 360 - 180


def from_trace(name: str, spec: dict | None = None, widen: float = 1.8, back_rows: int = 3,
               side_rows: int = 3, part_back: float = 0.1, row_step: float = 0.022,
               fan: float = 0.004) -> dict:
    """A groom patch carried from the traced reference through the matched camera (ref_camera + ref_trace):
    - parting.line: the traced part's rays onto the volume, carried on straight back `part_back` m over the top;
    - hairline.front_points: the traced hairline's rays onto the scalp across the forehead, both sides averaged;
    - drawn clumps: each traced clump's rays onto the volume ([az, el]), rooted on the part line (a root hidden
      behind the outline is moved onto the part at its row), width = traced px x mm/px x `widen` (clumps overlap:
      the band you see is part of each); rows behind the traced ones (invisible from the reference) repeat the last
      top row shifted back along the part; the part side's traced clump repeated along the part.
    Returns {"groom": {...}} for spec["hair"]; nothing is saved."""
    spec = store.load(name) if spec is None else spec
    sc = scalp(name, spec)
    g = groom_params(spec)
    cam, tr = ref_camera(name), ref_trace(name)
    if cam is None or tr is None:
        raise HairError("from_trace needs ref_camera.json (fit_camera) and ref_trace.json in the model folder")
    mm = np.linalg.norm(np.asarray(cam["eye"]) - sc.C) / cam["focal_px"]  # m per reference pixel at the head
    # the part
    Pp = ray_onto(sc, g, cam, tr["part"])
    a0, e0, _ = sc.coords(Pp)
    xy = (sc.point(a0, e0, 0.0) - sc.C)[:, :2]  # on the scalp under the hits (top-view terms)
    d = xy[-1] - xy[-2]
    d = d / np.linalg.norm(d)
    ext = [xy[-1] + d * 0.012]
    while ext[-1][1] < xy[0][1] + part_back:  # on straight back (turning off the traced heading)
        step = np.array([0.0, 1.0]) * 0.02
        ext.append(ext[-1] + step)
    pxy = np.vstack([xy, ext])
    pa, pe = top_to_azel(sc, np.asarray(ext))
    part = np.r_[np.stack([_signed(a0), e0], 1), np.stack([_signed(pa), pe], 1)]
    offset = float(abs(xy[0][0]))
    # the hairline over the forehead
    Ph = ray_onto(sc, g, cam, tr["hairline"], onto="scalp")
    ha, he, _ = sc.coords(Ph)
    ha = _signed(ha)
    front = []
    ok = he > 12  # the temples' vertical edges graze the head: their hits are unreliable
    for a0 in np.arange(0.0, 41.0, 8.0):
        zs = []
        for sgn in (1, -1):
            m = ok & (sgn * ha >= -2)
            if m.sum() < 2:
                continue
            aa, zz = sgn * ha[m], Ph[m, 2]
            o = np.argsort(aa)
            if aa[o][0] <= a0 <= aa[o][-1]:
                zs.append(np.interp(a0, aa[o], zz[o]))
        if zs:
            front.append([float(a0), round(float(np.mean(zs)), 4)])
    # clumps

    def on_part(y):  # the part point at top-view y (m from the centre)
        k = np.clip(np.interp(y, pxy[:, 1], np.arange(len(pxy))), 0, len(pxy) - 1)
        i = int(np.floor(k))
        j = min(i + 1, len(pxy) - 1)
        return pxy[i] + (k - i) * (pxy[j] - pxy[i])
    drawn_ = []
    tops = []
    for c in tr["clumps"]:
        P = ray_onto(sc, g, cam, c["line"])
        a, e, _ = sc.coords(P)
        a = _signed(a)
        keep = [0]
        for k in range(1, len(a)):  # a tip past the outline: the ray jumps round the head
            if np.linalg.norm(P[k] - P[keep[-1]]) < 0.06:
                keep.append(k)
            else:
                break
        a, e, P = a[keep], e[keep], P[keep]
        q = (P - sc.C)[:, :2]
        w = round(float(c.get("width", 24)) * mm * widen, 4)
        side = c["name"].startswith("part_side")
        far = (q[0][0] * xy[0][0]) < 0  # starts across the head from the part: the sweep's fall down the far side
        y_prev = tops[-1][1][0][1] if tops else -np.inf
        if not side and not far and (np.linalg.norm(q[0] - on_part(q[0][1])) > 0.012 or q[0][1] < y_prev + 0.015):
            # its root is hidden (or ahead of the row before): the clump carried on backward along its own heading
            # until it meets the part (a sweep running forward across the top grows from further back), never ahead
            # of the previous row's root
            d0 = q[0] - q[1]
            d0 = d0 / max(np.linalg.norm(d0), 1e-9)
            r = on_part(y_prev + 0.018)
            for s_ in np.arange(0.0, 0.12, 0.002):
                t = q[0] + s_ * d0
                if (t[0] - on_part(t[1])[0]) * np.sign(xy[0][0]) >= 0:
                    r = on_part(max(t[1], y_prev + 0.018))
                    break
            ra, re_ = top_to_azel(sc, r[None])
            a, e = np.r_[_signed(ra), a], np.r_[re_, e]
            q = np.vstack([r, q])
        # names: a row's stem + number (sweep1, sweep2...), so the under layer fills between neighbours
        nm = "pside0" if side else ("fall0" if far else f"sweep{len(tops) + 1}")
        drawn_.append({"name": nm, "azel": np.c_[a, e].round(2).tolist(), "width": w,
                       "taper": 0.85 if not side else 1.0, "traced": c["name"]})
        if not side and not far:
            tops.append((nm, q, w))
    # rows behind: the last top row, shifted back along the part
    if tops:
        _, q0, w0 = tops[-1]
        for k in range(1, back_rows + 1):
            dy = row_step * k
            q = q0 + [0.0, dy]
            q[1:, 1] += fan * k * np.linspace(0, 1, len(q) - 1) ** 1.5  # later rows fan back toward the crown
            q[:, 0] = np.clip(q[:, 0], -0.09, 0.09)
            drawn_.append({"name": f"sweep{len(tops) + k}", "top": q.round(4).tolist(), "width": w0, "taper": 0.85})
    # the part side: down toward his ear from the part, one per row along it
    ps = next((c for c in drawn_ if c["name"] == "pside0"), None)
    if ps:
        q = np.asarray(ps["azel"], float)
        for k in range(1, side_rows + 1):
            r = on_part(xy[0][1] + 0.025 * k)
            ra, re_ = top_to_azel(sc, r[None])
            dq = np.array([float(_signed(ra)[0]), float(re_[0])]) - q[0]
            drawn_.append({"name": f"pside{k}", "azel": (q + dq * np.linspace(1, 0.5, len(q))[:, None]).round(2).tolist(),
                           "width": ps["width"], "taper": 1.0})
    return {"groom": {"parting": {"side": "left" if xy[0][0] >= 0 else "right", "offset": round(offset, 4),
                                  "line": part.round(2).tolist()},
                      "hairline": {"front_points": front},
                      "drawn": drawn_}}
