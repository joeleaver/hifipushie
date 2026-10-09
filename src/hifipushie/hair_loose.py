"""Loose hair: hair that grows all over the scalp, is combed some way at its roots and then FALLS (or stands): a
bob, shoulder-length waves, long straight hair, a fringe, short tousled hair, a crop, an afro. One general
capability, `groom.loose`:

  {"length": 0.25 | {"front", "top", "sides", "back", "nape"},   m of hair from the root (a layered cut: per region)
   "level": -0.13,          optional: every lock is cut where it crosses this height (m from the head centre, - is
                            below: about -0.10 the jaw, -0.17 the shoulders' top): a one-length cut, a bob
   "spacing": 0.026,        m between lock roots on the scalp (width follows)
   "body": 0.02,            m: how thick the mass gets where the locks lie over each other (higher roots lie outside)
   "lift": 0.006,           m the hair stands off the scalp at its roots (root volume)
   "stiff": 0.3,            0 = hangs at once .. 1 = keeps the direction it left the scalp in (short hair, an afro)
   "out": 0.0,              0 = combed along the scalp .. 1 = straight out of the scalp
   "lay": 0.0,              0..1 (or per region): the hair is pressed onto the head along its flow, as a comb or a
                            hand lays it: each step loses that share of its outward direction. Lowers a crop's top
                            without `stiff` (which, low, lets gravity curl short locks into hooks)
   "back": 0.0,             0..1: the top and front combed back over the crown (with parting "none": slicked back)
   "flow": {"front": [0.4, -0.5, 0.7], "top": [0.6, -0.2, 0.2], "sides": [0, 0.7, -0.7]},
                            optional, per region: the way the hair is combed there as a world direction (x his left,
                            y back, z up; laid in the scalp, `out` lifts it off): a front brushed up and forward to
                            his left, sides back and down. Regions left out keep the default (gravity, away from the
                            parting, `back`). `out` and `stiff` may also be given per region ({"front": 0.5, ...}).
   "messy": 0.15,           0..1: each lock's root direction turned at random (tousled)
   "uneven": 0.3,           0..1: lengths differ lock to lock
   "face": 1.0,             0..1: how far the hair is kept from hanging over the face (1 = it frames it: curtains
                            beside the cheeks; 0 = it falls where it falls); the fringe is not held back
   "ends": 0.0,             -1..1: the ends turn under toward the neck (a bob's bevel, +) or flick out (-)
   "swoop": {"at": 0, "span": 30, "depth": 0.03, "rise": 0.35, "sweep": 0.0, "stiff": 0.75, "length": 0.01, "body": 1.6,
             "lay": 0.06},
                            a front lock lifting off the forehead and curving up and back: hair rooted within `depth`
                            m of the hairline and `span` deg of azimuth `at` (0 = the face's centre, + toward his
                            left) is combed up-and-back (sweep -1..1: over to his right / left), lifts UP and back by
                            `rise` (not along the forehead's normal: that pokes forward past the brow), is stiffer,
                            `length` m longer, laid by `lay` so the wave rolls back behind the hairline, not tousled
                            by messy, and its locks are `body` x wider and thicker with their strands kept together
                            (one coherent lock); weights fade smoothly
   "fringe": {"length": 0.07, "span": 40, "depth": 0.045, "sweep": 0.0, "level": None}}
                            hair rooted within `depth` m of the front hairline, `span` deg either side of the
                            centre, combed forward over the forehead (sweep -1..1: to his right / left); level
                            (m from the head centre) cuts it straight, e.g. at the brows

The hair is kept off the head, neck, shoulders and clothes by the body's own signed distance (`collider`: a grid
cached per body geometry, the EDT of the field's sign), so it lies on the shoulders and falls down the back; the
same surface (meshed) is what Blender's Shrinkwrap keeps the strands out of. Locks are "space": "xyz" locks with
`free` 1, like a tail's: ordinary locks a person can edit.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np

LOOSE = {"length": 0.25, "level": None, "spacing": 0.026, "body": 0.02, "lift": 0.006, "stiff": 0.3, "out": 0.0, "lay": 0.0,
         "back": 0.0, "messy": 0.15, "uneven": 0.3, "ends": 0.0, "fringe": None, "face": 1.0, "width": 1.5, "thickness": 0.006,
         "flow": None, "swoop": None}
FRINGE = {"length": 0.07, "span": 40.0, "depth": 0.045, "sweep": 0.0, "level": None, "stiff": 0.45}
SWOOP = {"at": 0.0, "span": 30.0, "depth": 0.03, "rise": 0.35, "sweep": 0.0, "stiff": 0.75, "length": 0.01, "body": 1.6,
         "lay": 0.06}
DOWN = np.array([0.0, 0.0, -1.0])
FACE_AZ = 58.0  # deg either side of the face's centre line that hair (not a fringe) is kept out of
LAY_EL = (48.0, 66.0)  # deg of scalp elevation over which the "top" region's lay comes in (below: the sides' lay)
STEP = 0.005  # m: the collider grid's cell
BOX = ((-0.34, -0.3, -0.72), (0.34, 0.32, 0.2))  # round the head centre: down to the small of the back


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def params(lo) -> dict:
    if lo is True:
        lo = {}
    bad = set(lo) - set(LOOSE)
    if bad:
        raise ValueError(f"hair loose: unknown keys {sorted(bad)} (have {', '.join(sorted(LOOSE))})")
    p = {**LOOSE, **lo}
    if isinstance(p["length"], dict):
        bad = set(p["length"]) - {"front", "top", "sides", "back", "nape"}
        if bad:
            raise ValueError(f"hair loose length: unknown regions {sorted(bad)} (front, top, sides, back, nape)")
    if p.get("fringe"):
        fr = {} if p["fringe"] is True else p["fringe"]
        bad = set(fr) - set(FRINGE)
        if bad:
            raise ValueError(f"hair loose fringe: unknown keys {sorted(bad)} (have {', '.join(sorted(FRINGE))})")
        p["fringe"] = {**FRINGE, **fr}
    if p.get("swoop"):
        sw = {} if p["swoop"] is True else p["swoop"]
        bad = set(sw) - set(SWOOP)
        if bad:
            raise ValueError(f"hair loose swoop: unknown keys {sorted(bad)} (have {', '.join(sorted(SWOOP))})")
        p["swoop"] = {**SWOOP, **sw}
    return p


# ------------------------------------------------------------------------------------------------ the body

class Collider:
    """The body's signed distance on a grid (m, + outside), read trilinearly."""

    def __init__(self, lo, step, phi):
        self.lo, self.step, self.phi = np.asarray(lo, float), float(step), np.asarray(phi, np.float32)
        self.g = None

    def _ix(self, P):
        return ((np.asarray(P, float) - self.lo) / self.step).T

    def at(self, P):
        from scipy.ndimage import map_coordinates
        return map_coordinates(self.phi, self._ix(P), order=1, mode="nearest")

    def grad(self, P):
        from scipy.ndimage import map_coordinates
        if self.g is None:
            self.g = [np.asarray(a, np.float32) for a in np.gradient(self.phi, self.step)]
        ix = self._ix(P)
        return _unit(np.stack([map_coordinates(a, ix, order=1, mode="nearest") for a in self.g], -1))

    def push(self, P, clear, rounds: int = 3):
        """Points moved out until they are `clear` m off the body."""
        P = np.array(P, float)
        for _ in range(rounds):
            need = np.asarray(clear, float) - self.at(P)
            m = need > 0
            if not m.any():
                break
            P[m] = P[m] + need[m, None] * self.grad(P[m])
        return P

    def mesh(self, every: int = 2) -> dict:
        """The body's surface as triangles (marching cubes on every `every`-th cell): Blender's collision proxy."""
        from skimage import measure
        ph = self.phi[::every, ::every, ::every]
        V, F, _, _ = measure.marching_cubes(ph, 0.0, spacing=(self.step * every,) * 3)
        return {"verts": (V + self.lo).astype(np.float32), "faces": F.astype(np.int32)}


_COLL: dict = {}


def collider(name: str, spec: dict, sc) -> Collider:
    """The model's Collider (cached in memory and on disk by the body's geometry, like the scalp)."""
    from . import sdf, store
    from .hair import _geometry_key
    from .spec import compile_prims, geometry
    key = _geometry_key(spec)
    if key in _COLL:
        return _COLL[key]
    f = store._dir(name) / f"hair_body_{key}.npz"
    if f.exists():
        z = np.load(f)
        c = Collider(z["lo"], float(z["step"]), z["phi"])
    else:
        from scipy import ndimage
        g = {k: v for k, v in geometry(spec).items() if k != "hair"}
        lo = sc.C + np.asarray(BOX[0])
        n = np.ceil((np.asarray(BOX[1]) - np.asarray(BOX[0])) / STEP).astype(int) + 1
        ax = [lo[i] + STEP * np.arange(n[i]) for i in range(3)]
        X = np.stack(np.meshgrid(*ax, indexing="ij"), -1).reshape(-1, 3)
        inside = np.zeros(len(X), bool)
        for ps in sdf.streams(compile_prims(g)):
            for i in range(0, len(X), 400000):
                inside[i:i + 400000] |= sdf.field_at(ps, X[i:i + 400000]) < 0
        ins = inside.reshape(n)
        phi = (ndimage.distance_transform_edt(~ins) - ndimage.distance_transform_edt(ins)) * STEP
        phi = phi - np.sign(phi) * 0.5 * STEP  # (the surface lies between an inside and an outside cell)
        phi = ndimage.gaussian_filter(phi, 0.8)
        c = Collider(lo, STEP, phi)
        for old in store._dir(name).glob("hair_body_*.npz"):
            old.unlink()
        np.savez_compressed(f, lo=c.lo, step=c.step, phi=c.phi)
    _COLL[key] = c
    return c


# ------------------------------------------------------------------------------------------------ the locks

def _lengths(length, W):
    from .hair import REGIONS
    if isinstance(length, dict):
        d = {"front": 0.2, "top": 0.2, "sides": 0.2, "back": 0.2, "nape": 0.2}
        v = [float(x) for x in length.values()]
        base = float(np.mean(v)) if v else 0.2
        return sum(W[:, i] * float(length.get(r, d[r] if not v else base)) for i, r in enumerate(REGIONS))
    return np.full(len(W), float(length))


def grow(sc, g: dict, line, rng, col: Collider | None = None) -> dict:
    """{name: lock} for groom.loose."""
    from .hair import _line_at, _part_x, _poisson, az_el, inside, weights
    p = params(g["loose"])
    sp = float(p["spacing"])
    ok = lambda a, e: (inside(sc, line, a, e) > 0.004) & (e > sc.EL[0] + 4)  # noqa: E731
    r0 = float(np.median(sc.R))
    az, el = _poisson(sc, rng, lambda a, e: np.full(len(a), sp), ok, n_try=int(np.clip(400 * r0 * r0 / sp ** 2, 4000, 40000)))
    m = len(az)
    if not m:
        return {}
    d_in = inside(sc, line, az, el)
    W = weights(az, el, d_in)
    L = _lengths(p["length"], W) * (1 - float(p["uneven"]) * rng.uniform(0, 0.3, m))
    P0 = sc.point(az, el, 0.0005)
    nrm = sc.normal(az, el)
    xp = _part_x(g)
    fa = np.abs(((az + 180) % 360) - 180)
    # the combing direction at the roots: gravity laid in the scalp, plus, on the top and front (where gravity has
    # no direction or points over the face), away from the parting and back over the crown
    upw = _ss((nrm[:, 2] - 0.25) / 0.5)
    frontw = (1 - _ss((fa - 60) / 40)) * (1 - _ss((d_in - 0.03) / 0.05))
    tw = np.maximum(upw, frontw)
    x = P0[:, 0] - sc.C[0]
    away = np.sign(x - xp) if xp is not None else np.sign(x) * 0.0
    away = np.where(away == 0, 1.0, away) if xp is not None else away
    back = float(p["back"])
    if xp is None and back <= 0:
        back = 1.0  # (no parting: the top has to go somewhere)
    comb = DOWN[None] * (1 - 0.8 * frontw[:, None]) + tw[:, None] * (
        (1 - 0.6 * back) * away[:, None] * np.array([1.0, 0, 0]) + back * np.array([0, 1.0, -0.15]))
    from .hair import REGIONS
    if p.get("flow"):  # a combing direction per region, by the region weights (what a traced flow gives)
        bad = set(p["flow"]) - set(REGIONS)
        if bad:
            raise ValueError(f"hair loose flow: unknown regions {sorted(bad)} (have {', '.join(REGIONS)})")
        for i_, r_ in enumerate(REGIONS):
            if r_ in p["flow"]:
                w_ = W[:, i_:i_ + 1]
                comb = comb * (1 - w_) + w_ * _unit(np.asarray(p["flow"][r_], float))[None]

    def by_region(v, default):  # a number, or {region: number} (others: the mean of those given)
        if isinstance(v, dict):
            base = float(np.mean([float(x) for x in v.values()])) if v else default
            return sum(W[:, i_] * float(v.get(r_, base)) for i_, r_ in enumerate(REGIONS)) / np.maximum(W.sum(1), 1e-9)
        return np.full(m, float(v))
    fr = p["fringe"]
    is_fr = np.zeros(m, bool)
    if fr:
        is_fr = (fa < float(fr["span"])) & (d_in < float(fr["depth"]))
        swp = float(fr["sweep"])
        comb[is_fr] = np.array([swp * 1.2, -1.0, -0.8])
        L[is_fr] = float(fr["length"]) * (1 - 0.5 * float(p["uneven"]) * rng.uniform(0, 0.3, int(is_fr.sum())))
        L[is_fr] += d_in[is_fr] * 0.9  # (rooted further back, it has further to go to the same edge)
    sw = p.get("swoop")
    wsw = np.zeros(m)
    if sw:  # a front lock lifting off the forehead and curving up and back (over to one side): a weight that is 1
        # at the hairline at `at` deg and fades over `span` deg and `depth` m into the scalp
        fs = np.abs(((az - float(sw["at"]) + 180) % 360) - 180)
        wsw = (1 - _ss(fs / float(sw["span"]))) * (1 - _ss(d_in / float(sw["depth"]))) * ~is_fr
        comb = comb * (1 - wsw[:, None]) + wsw[:, None] * _unit(np.array([0.9 * float(sw["sweep"]), 0.55, 0.85]))[None]
        L = L + float(sw["length"]) * wsw
    tang = comb - (comb * nrm).sum(1, keepdims=True) * nrm
    bad = np.linalg.norm(tang, axis=1) < 1e-3
    tang[bad] = np.cross(nrm[bad], [1.0, 0, 0])
    tang = _unit(tang)
    turn = rng.uniform(-1, 1, m) * float(p["messy"]) * np.pi / 2 * (1 - wsw)  # (a swoop is combed: its locks in step)
    tang = _unit(tang * np.cos(turn)[:, None] + np.cross(nrm, tang) * np.sin(turn)[:, None])
    out_r = np.clip(by_region(p["out"], 0.0), 0, 1)
    out = float(out_r.mean())
    outi = np.clip(out_r + float(p["messy"]) * rng.uniform(-0.3, 0.3, m), 0, 1)
    outi[is_fr] = np.minimum(outi[is_fr], 0.25)
    lay_v = p.get("lay", 0.0)
    if isinstance(lay_v, dict) and "top" in lay_v:
        # "top"'s region weight is full from 42 deg of elevation, i.e. on the upper SIDES of the head too: laid there,
        # the sides lost 6.7 mm of width (Garrett). The top's lay counts only where the scalp is the head's top
        # (LAY_EL); below it that share of the weight takes the sides' lay.
        base_ = float(np.mean([float(x) for x in lay_v.values()]))
        up_ = _ss((el - LAY_EL[0]) / (LAY_EL[1] - LAY_EL[0]))
        vals_ = [float(lay_v.get(r_, base_)) for r_ in REGIONS]
        it_, is_ = REGIONS.index("top"), REGIONS.index("sides")
        lay = sum(W[:, i_] * vals_[i_] for i_ in range(len(REGIONS)) if i_ != it_)
        lay = (lay + W[:, it_] * (up_ * vals_[it_] + (1 - up_) * vals_[is_])) / np.maximum(W.sum(1), 1e-9)
        lay = np.clip(lay, 0, 1)
    else:
        lay = np.clip(by_region(lay_v, 0.0), 0, 1)
    lay[is_fr] = 0.0
    if sw:
        # the lift is UP and back, not along the scalp's normal (on the forehead that points forward: a cowlick
        # poking out past the brow in profile); the lock keeps a little lay so its wave rolls back over the head
        outi = outi * (1 - wsw)
        lay = lay * (1 - wsw) + float(sw["lay"]) * wsw
    d = _unit(tang * (1 - outi)[:, None] + nrm * (outi + 0.12 * (1 - lay))[:, None])
    if sw:
        d = _unit(d + (float(sw["rise"]) * 2.0 * wsw)[:, None] * _unit(np.array([0.0, 0.45, 1.0]))[None])
    stiff = np.clip(by_region(p["stiff"], 0.3), 0, 1)
    if fr:
        stiff[is_fr] = float(fr["stiff"])
    if sw:
        stiff = stiff * (1 - wsw) + float(sw["stiff"]) * wsw
    kg = (1 - stiff) ** 3 * 400.0  # how fast the direction falls, per metre
    # layers: locks rooted higher (and further from the hairline) lie over the ones under them
    rank = np.clip((el - line.min()) / max(90.0 - line.min(), 1.0), 0, 1)
    layer = 0.7 * rank + 0.3 * rng.uniform(0, 1, m)
    target = float(p["lift"]) + float(p["body"]) * layer
    target[is_fr] = 0.004 + 0.006 * layer[is_fr]
    n = 44
    ds = L / (n - 1)
    P = np.zeros((m, n, 3))
    P[:, 0] = P0
    ends = float(p["ends"])
    rest = np.zeros(m, bool)
    face = float(np.clip(p["face"], 0, 1))
    side0 = np.where(away != 0, away, np.where(rng.uniform(size=m) < 0.5, -1.0, 1.0))
    axis_xy = sc.C[:2] + np.array([0.0, 0.02])
    for k in range(1, n):
        s = ds * k
        t = k / (n - 1)
        d = _unit(d + (kg * ds)[:, None] * DOWN)
        if lay.any():  # laid: the direction's outward part (off the head, about its centre) is combed away
            rn_ = _unit(P[:, k - 1] - sc.C)
            d = _unit(d - (lay * np.maximum((d * rn_).sum(1), 0.0))[:, None] * rn_)
        if rest.any():  # lying on a shoulder: hair slides off it to the front or the back, never out along the arm
            # (long hair fanned out over both arms to the elbows)
            sx = np.sign(P[:, k - 1, 0] - sc.C[0])
            outw = rest & (d[:, 0] * sx > 0)
            d[outw, 0] *= 0.1
            sy = np.where(P[:, k - 1, 1] - sc.C[1] > 0.0, 1.0, -1.0)
            d[rest, 1] += 0.7 * sy[rest]
            d = _unit(d)
        if ends and t > 0.7:
            rad = np.zeros((m, 3))
            rad[:, :2] = P[:, k - 1, :2] - axis_xy
            d = _unit(d - ends * 0.35 * _ss((t - 0.7) / 0.3) * _unit(rad) * ~is_fr[:, None])
        q = P[:, k - 1] + d * ds[:, None]
        # the mass builds up as locks come down over the ones rooted under them (not at their own roots: lifted
        # there, the top stood up in tufts along the parting)
        clear = 0.0015 + float(p["lift"]) * _ss(s / 0.03) + (target - float(p["lift"])) * _ss((P0[:, 2] - q[:, 2]) / 0.07)
        if face > 0:  # off the face: a point hanging in front of it, under the hairline, is turned out to its side
            a_, e_ = az_el(q - sc.C)
            sg = np.where(np.abs(q[:, 0] - sc.C[0]) > 0.004, np.sign(q[:, 0] - sc.C[0]), side0)
            f_ = np.abs(((a_ + 180) % 360) - 180)
            lim = face * FACE_AZ * _ss((_line_at(line, a_) - e_) / 12.0) * _ss((e_ + 75) / 15)
            mv = (f_ < lim) & ~is_fr
            if mv.any():
                rot = np.radians((lim - f_) * sg)[mv]  # (az grows toward +x: the head's left)
                v = q[mv] - sc.C
                c_, s_ = np.cos(rot), np.sin(rot)
                q[mv] = sc.C + np.stack([v[:, 0] * c_ - v[:, 1] * s_, v[:, 0] * s_ + v[:, 1] * c_, v[:, 2]], 1)
        if col is not None:
            low = q[:, 2] < sc.C[2] - 0.12
            rest = low & (col.at(q) < clear + 0.002) & (col.grad(q)[:, 2] > 0.45) & ~is_fr
            q = col.push(q, clear)
        else:
            a_, e_, h_ = sc.coords(q)
            from .hair import dirs
            q = q + (np.maximum(clear - h_, 0) * (e_ > sc.EL[0] + 3))[:, None] * dirs(a_, e_)
        d = _unit(q - P[:, k - 1])
        P[:, k] = P[:, k - 1] + d * ds[:, None]
    locks = {}
    from .hair import _grey
    gq = g.get("grey") or {}
    GR = sum(W[:, i_] * float(gq.get(r_, 0.0)) for i_, r_ in enumerate(REGIONS)) / np.maximum(W.sum(1), 1e-9)
    w0 = float(p["width"]) * sp
    order = np.argsort(-el)
    for j, i in enumerate(order):
        Q = P[i]
        lvl = (fr or {}).get("level") if is_fr[i] else p.get("level")
        if lvl is not None:  # a straight cut: the lock ends where it crosses the level (a little uneven)
            z = Q[:, 2] - sc.C[2] - float(lvl) - float(p["uneven"]) * rng.uniform(-0.006, 0.006)
            below = np.nonzero(z < 0)[0]
            below = below[below > 3]
            if len(below):
                b = int(below[0])
                f = z[b - 1] / max(z[b - 1] - z[b], 1e-9)
                Q = np.vstack([Q[:b], Q[b - 1] + f * (Q[b] - Q[b - 1])])
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
        if s[-1] < 0.008:
            continue
        npt = int(np.clip(round(s[-1] / 0.02) + 3, 5, 16))
        si = np.linspace(0, s[-1], npt)
        Q = np.stack([np.interp(si, s, Q[:, c]) for c in range(3)], 1)
        # a lock standing out of the head fans as it goes (an afro's surface is further apart than its roots)
        rr = np.linalg.norm(Q - sc.C, axis=1)
        fan = np.clip(rr / max(rr[0], 1e-6), 1.0, 2.5) if out > 0.5 else None
        short = s[-1] < 0.05
        lk = {"tier": "loose", "space": "xyz", "pts": [[round(float(v), 4) for v in q] for q in Q - sc.C],
              "free": 1.0, "width": round(float(w0 * (1 + 0.3 * float(p["uneven"]) * rng.uniform(-1, 1))), 4),
              "thickness": float(p["thickness"]) * (0.6 if is_fr[i] else 1.0), "taper": 0.2 if lvl is not None else 0.35,
              "belly": 0.4, "root": 0.7, "cup": 0.0}
        if fan is not None:
            lk["radius"] = [round(float(v), 3) for v in fan]
        if short:
            lk["strands"] = {"tip_spread": 0.6}
        if sw and wsw[i] > 0.3:  # one lock with body: broader, thicker, strands kept together to the tip, no wave
            k_ = 1 + (float(sw["body"]) - 1) * float(wsw[i])
            lk["width"] = round(lk["width"] * k_, 4)
            lk["thickness"] = round(lk["thickness"] * k_, 4)
            lk["strands"] = {"tip_spread": 0.15, "wave": 0.0, "random": 0.1}
        gy = max(_grey(g, float(az[i]), float(el[i]), line), float(GR[i]))  # greying temples / sideburns / regions
        if gy > 0.01:
            lk["grey"] = round(gy, 3)
        locks[("lf" if is_fr[i] else "l") + str(j)] = lk
    return locks
