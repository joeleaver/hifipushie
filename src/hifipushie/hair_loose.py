"""Loose hair: hair that grows all over the scalp, is combed some way at its roots and then FALLS (or stands): a
bob, shoulder-length waves, long straight hair, a fringe, short tousled hair, a crop, an afro. One general
capability, `groom.loose`:

  {"length": 0.25 | {"front", "top", "sides", "back", "nape"},   m of hair from the root (a layered cut: per region)
                            ("top_el": [e0, e1] deg: the top's length only above e0..e1, the sides' below: a crop)
   "level": -0.13,          optional: every lock is cut where it crosses this height (m from the head centre, - is
                            below: about -0.10 the jaw, -0.17 the shoulders' top): a one-length cut, a bob
   "spacing": 0.026,        m between lock roots on the scalp (width follows)
   "body": 0.02,            m (or per region): how thick the mass gets where the locks lie over each other (higher
                            roots lie outside)
   "lift": 0.006,           m the hair stands off the scalp at its roots (root volume); or per region {"top": .., ..}
   "lift_ramp": 0.03,       m (or per region): the arc along the lock over which its lift is reached. Short, the root
                            stands up and the rest lies; the default 3 cm on a 5 cm lock is a lock that spends most
                            of its length rising (a bristle)
   "lift_fall": 0.0,        0..1 (or per region): the share of the lift the lock gives back toward its tip (it lifts at
                            the root and lies down along its length onto the locks under it)
   "body_along": 0.0,       0..1 (or per region): the share of `body` x layer a lock reaches gently along its own
                            length (not only where it hangs down): the height of a short top built from lying layers
                            (higher roots lie over the ones under them) instead of standing roots
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
                            A region's flow may instead be {"from": [az, el], "bias": [x, y, z]}: combed away from that
                            scalp point (the crown a crop grows out of), plus a world bias
   "messy": 0.15,           0..1 (or per region): each lock's root direction turned at random (tousled)
   "uneven": 0.3,           0..1: lengths differ lock to lock
   "face": 1.0,             0..1.6: how far the hair is kept from hanging over the face (1 = it frames it: curtains
                            beside the cheeks, out of 58 deg either side of the face's centre; 0 = it falls where it
                            falls; over 1 = held further back, 1.5 = to the ear: hair swept back off the cheek and
                            temple); the fringe is not held back
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
   "fringe": {"length": 0.07, "span": 40, "depth": 0.045, "sweep": 0.0, "level": None, "curtain": 0.0},
                            (sweep "away" + curtain 0..1: CURTAIN BANGS, each side swept down and away from the part,
                            longer toward the outer edges)
   "tuck": "left" | {"side": "left" | "right" | "both", "amount": 1.0},
                            hair over and in front of the (found) ear combed back and passing BEHIND it
   "fade": {"width": 0.02, "length": 0.009, "density": 0.25, "front": {"width": 0.012, "density": 0.3}},
   "whorl": {"at": [az, el], "radius": 0.035, "turn": 1, "spiral": 60}: the CROWN WHORL (every head has one): roots
                            within `radius` m of the scalp point at (az deg, 0 = the face's centre, + toward the head's
                            left; el deg) comb in a spiral round it (`spiral` deg off straight outward; `turn` +1 =
                            clockwise seen from above, -1 = anticlockwise), fading into the comb by the rim;
                            "core": m (> 0): the spiral only within it, a straight RADIAL spread beyond (a large
                            `radius` then governs the whole top: the hair grows out of the whorl)
                            the back's locks shorten and thin out over `width` m toward the nape hairline (a fade)
                            ("front": {width, density, reach}: fewer roots near the FRONT hairline, tips lie over them;
                            reach: m past the line a forward-combed front's tips end; row: m, the reach only
                            within `row` of the line, the front behind it keeps its length)
   (fade "taper": m (2026-10-15, Garrett's nape): a barber's TAPER instead of the cut above: over `taper` m above the
                            nape line the length AND the lift ramp down to `floor` x their own (smoothly, the line
                            jittered by `rough` m per lock: a soft edge), density only to `density` at the very line;
                            `width` / `length` are then unused. The cut's short sparse band read as a bald rectangle.
                            "taper_from": deg (default 100): |az| where the taper starts (over 30 deg); 70-80 takes it
                            round behind the ear, where the sides' full length otherwise hangs long and ragged)
   (whorl "thin": 0..1, "thin_radius": m: fewer roots (lock and even strands) at the whorl's centre, a Gaussian of
                            `thin_radius`: the scalp shows through a broad whorl, as on most heads)
   "bend": {"rise": {"front": 0.012}, "angle": 90, "lay": 0.7, "up": 0.8, "arc": 0.004},
                            (2026-10-16, Garrett's forelock) a lock PROFILE: the lock RISES straight from its root for
                            `rise` m (number or per region; 0 = no bend), leaning `up` 0..1 toward the scalp's normal
                            (1 = straight out, 0 = along the comb), with no gravity and no lay on the way up; then over
                            `arc` m it BENDS by `angle` deg (number or per region) toward its comb direction, and after
                            the bend it lies forward and over, pressed by `lay` (number or per region; replaces the
                            region's lay after the bend) and falling by its region's `stiff`. Height comes from the
                            rise, the lie from the bend: with `lift` / `lay` the height and the lie came together
                            with the length (a longer front stood up AND stood out). Not on fringe or swoop locks.
                            "from": m (default 0): the rise comes in over `from` m behind the hairline (0 at the line;
                            roots under BEND_GATE of the ramp get no bend at all: a short bent rise hooked);
                            "toward": [x, y, z] or {region: [x, y, z]} (default: the comb): the world direction the lock lies toward after the
                            bend (a front combed forward bends DOWN the forehead: hooks; [1, -0.3, 0.3] lies over to his
                            left, Garrett's forelock)
   "trace": {"samples": [[az, el, h], ...], "regions": {"front": 1, "top": 1}, "sigma": 6, "under": 0.75,
             "rise": 0.008},
                            (2026-10-16, Garrett's front) the hair's OUTLINE matched to a reference: `samples` are
                            stand-off heights h (m) over scalp points (az, el deg), traced from the photo's outline
                            through the fitted cameras (spikes/hair_garrett/fronttrace.py). Locks rooted in `regions`
                            (root weight per region) are HELD at the traced height wherever they pass over the traced
                            area (Gaussian over the samples, `sigma` deg; full where samples are dense, none away
                            from them): each point is set onto h x (under + (1 - under) x layer) (the top layer on the
                            outline, the ones under it lower), reached over `rise` m from the root ("from": m, the hold
                            comes in over that distance behind the hairline: the hairline row lies). No slider decides
                            the shape: the trace does (the per-sample h is solved against the screen's own outline)
                            "forward": 0..1 (x the root's front weight): the hold's push leans forward along the
                            scalp, so front locks reach the traced height running over the hairline, not up off it
                            ("forward": [x, y, z]: leans toward that world direction instead, its length the amount:
                            [0.8, -0.4, 0] sweeps the front across to his left; the front view reads it lying across; or per side
                            {"left": f, "right": f}, each a number or a vector, blended over +-"forward_blend" deg
                            about the centre, default 10: diverging sides over a narrow blend fan out from a point)
   "comb_trace": {"samples": [[az, el, x, y, z, run_mm, seeds], ...], "regions": {"top": 1, "sides": 1, "back": 1},
                  "sigma": 6, "amount": 1, "full": 1.5},
                            (2026-10-16, Garrett's sweep) the COMB traced from a reference: each sample is the laid strand
                            direction (world x, y, z) the photo shows over scalp point (az, el), from its orientation field
                            cast through the fitted cameras (spikes/hair_garrett/flowtrace.py). A root's comb turns toward
                            the Gaussian (`sigma` deg) mean of the samples near it, by `amount` x the root's weight in
                            `regions` x (1 - exp(-sum of the samples' weights / `full`)): full where the photo shows the
                            hair, none away from it (the region combs and the whorl stay there). Applied after the whorl,
                            before messy; a bend / trace "forward" still acts later. No slider decides the sweep: the photo does
   "blend": 1.0 (x): the region transitions (top / sides / back / nape) this many times wider for lift, lay, out,
                            stiff, grey and length: a lifted top over close sides makes a ledge, a pale top a seam
   "halo": 0..1, "flyaway": 0..1}
                            loose hair's own halo / fly-aways (the strands' dials for its free locks; a TAIL's halo
                            stays quartered, loose hair's is not)}
                            hair rooted within `depth` m of the front hairline, `span` deg either side of the
                            centre, combed forward over the forehead (sweep -1..1: to his right / left); level
                            (m from the head centre) cuts it straight, e.g. at the brows

The hair is kept off the head, neck, shoulders and clothes by the body's own signed distance (`collider`: a grid
cached per body geometry, the EDT of the field's sign), so it lies on the shoulders and falls down the back; the
same surface (meshed) is what Blender's Shrinkwrap keeps the strands out of. Locks are "space": "xyz" locks with
`free` 1, like a tail's: ordinary locks a person can edit.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at hair_loose.NAME: C422). hair_loose_body: the body loose hair falls on: `Collider` and `collider` (the SDF
body round the head, cached). hair_loose_grow: the locks: `grow`, loose hair grown strand by strand from the scalp,
and their lengths.
"""
from __future__ import annotations

import numpy as np
from . import moved

LOOSE = {"length": 0.25, "level": None, "spacing": 0.026, "body": 0.02, "lift": 0.006, "lift_ramp": 0.03, "lift_fall": 0.0, "body_along": 0.0, "stiff": 0.3, "out": 0.0, "lay": 0.0,
         "back": 0.0, "messy": 0.15, "uneven": 0.3, "ends": 0.0, "fringe": None, "face": 1.0, "width": 1.5, "thickness": 0.006,
         "flow": None, "swoop": None, "below": None, "tuck": None, "fade": None, "halo": None, "flyaway": None,
         "inset": None, "part_soft": None, "whorl": None, "blend": 1.0, "bend": None, "trace": None,
         "comb_trace": None}
TRACE = {"samples": [], "regions": {"front": 1.0}, "sigma": 6.0, "under": 0.75, "rise": 0.008, "from": 0.0, "keys": None, "forward": 0.0, "forward_blend": 10.0}  # (see "trace" above; keys: the tracer's (view, ray) per sample)
COMB_TRACE = {"samples": [], "regions": {"top": 1.0, "sides": 1.0, "back": 1.0}, "sigma": 6.0, "amount": 1.0, "full": 1.5}
# (see "comb_trace" above: samples [az, el, x, y, z, (run mm, seeds)] from spikes/hair_garrett/flowtrace.py)
BEND_GATE = 0.35  # bend.from: roots whose ramp weight is under this get no bend (they lie: the hairline row)
BEND = {"rise": 0.0, "angle": 90.0, "lay": 0.7, "up": 0.8, "arc": 0.004, "from": 0.0, "toward": None}  # (see "bend" in the doc at the top)
WHORL = {"at": [180.0, 62.0], "radius": 0.035, "turn": 1.0, "spiral": 60.0, "core": 0.0, "thin": 0.0, "thin_radius": 0.012}  # (see the doc at the top)
TUCK = {"side": "both", "amount": 1.0, "from": None}  # hair over the ear combed back BEHIND it (one side, or both);
# from: deg of azimuth from which hair is tucked (default 45 deg in front of the ear: the temple; 10-15: the front
# hair from the part too, swept back over the ear on that side)
FADE = {"width": 0.02, "length": 0.009, "density": 0.25, "front": None, "taper": None, "taper_from": 100.0, "floor": 0.3, "rough": 0.004}  # a short cut fading out toward the nape hairline (locks
# under 8 mm are not grown: length stays over that)
FRINGE = {"length": 0.07, "span": 40.0, "depth": 0.045, "sweep": 0.0, "level": None, "stiff": 0.45, "curtain": 0.0}
SWOOP = {"at": 0.0, "span": 30.0, "depth": 0.03, "rise": 0.35, "sweep": 0.0, "stiff": 0.75, "length": 0.01, "body": 1.6,
         "lay": 0.06}
DOWN = np.array([0.0, 0.0, -1.0])
FACE_AZ = 58.0  # deg either side of the face's centre line that hair (not a fringe) is kept out of
FACE_MIN_LEN = 0.06  # m: shorter hair (ending about at the hairline: forehead height) is not steered by the face rule
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
        bad = set(p["length"]) - {"front", "top", "sides", "back", "nape", "top_el"}
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
    for key, dflt in (("tuck", TUCK), ("fade", FADE), ("whorl", WHORL), ("bend", BEND), ("trace", TRACE),
                      ("comb_trace", COMB_TRACE)):
        if p.get(key):
            v = {} if p[key] is True else ({"side": p[key]} if key == "tuck" and isinstance(p[key], str) else p[key])
            bad = set(v) - set(dflt)
            if bad:
                raise ValueError(f"hair loose {key}: unknown keys {sorted(bad)} (have {', '.join(sorted(dflt))})")
            p[key] = {**dflt, **v}
    if p.get("tuck") and p["tuck"]["side"] not in ("left", "right", "both"):
        raise ValueError("hair loose tuck.side: left, right or both (the person's own)")
    if p.get("fringe") and isinstance(p["fringe"].get("sweep"), str) and p["fringe"]["sweep"] != "away":
        raise ValueError('hair loose fringe.sweep: -1..1, or "away" (curtain bangs: each side swept away from the part)')
    return p


_COLL: dict = {}


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("hair_loose_body", "hair_loose_grow")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
