"""Stream beds for the 3D tiles: what lies under and beside a river's water, per point (texel or vertex), the same in
every tile and LOD (grids on the terrain's cells read as cubic B-splines, and noise).

The consumer's note (pushieworld 110; Joe: "streambeds aren't textured right, and they aren't typically empty, they
have clutter and debris, rocks"): with real water in the river the bed showed, and it was the meadow's grass and
earth, banks included, with nothing in the channel. What real streams have (guide topic terrain_streams, with
sources; photos in workspace/level_refs/streams):
- the bed's material follows the stream's ENERGY (its grade): bedrock and boulders on steep reaches (cascade,
  step-pool), cobbles and gravel on middling ones (plane-bed, riffles), sand and silt where the water slows (pools,
  slack margins). Along a reach riffles (shallow, coarse) and pools (deep, fine) alternate every 5-7 channel widths;
  in a bend the pool lies against the OUTER bank and a bar of gravel builds on the inside;
- the banks' foot is wet: a damp, darker band a hand or two above the water, moss and algae on stones at the water
  line;
- it is never empty: boulders (some standing proud of the water), cobble patches on bars and riffles, slabs at the
  margin of steep reaches, driftwood caught on rocks and stranded on outer bends and bar heads, reeds and sedges
  along slow margins, leaf litter in the slack.

Three things are made from the built terrain's own river data (T.river_water_lines: path, water level, width):
- `Streams`: grids round every river (distance to the water's edge, water level, energy, bend, pool phase, flow
  direction), and the per-point rules: `shares` (the bed's layers: gravel, silt, bedrock, the damp bank), `colour`,
  `relief` (the maps' cobble lumps), `dz` (the bed's SHAPE in Field.column via terrain_ground_model.Edits: pools deeper on
  the outside of bends, riffles shallower, bars inside bends, an uneven bed; only ever under the water, never the
  banks, and the bed stays under the water's level except a bar's top);
- `clutter`: instances for an engine (clutter.csv): river_rock, cobbles, slab, driftwood, reeds, litter, each with a
  `place` (water / margin / bank / bar);
- the tiling swatches for the new layers (`cobble_swatch`, `silt_swatch`).

Spec: `"streams": false` turns all of it off (the river as before); `"streams": {...}` overrides `CFG`'s numbers;
`rivers.<name>.bed = {"energy": 0..1 | [source .. mouth values]}` sets a river's character by hand (0 a slow silty
lowland stream, 1 a boulder torrent) instead of reading it off its grade.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at terrain_stream.NAME: C422). terrain_stream_streams: class Streams: the streams of a terrain.
terrain_stream_water: the water as built (wet runs, the wet design, the flow report), and the cobble and silt
swatches. terrain_stream_clutter: stream clutter: where it lies, all of it, counts, summary, the manifest.
"""
from __future__ import annotations

import numpy as np
from . import moved

CFG = {
    "reach": 14.0,           # m beyond the water's nominal edge the stream's zone runs (banks, bank stones)
    "grade": [0.04, 0.30],   # bed grade where the energy is 0 .. 1 (real reach types change at 1.5 / 3 / 6.5%: a game
    # level's rivers are compressed in length, so steeper than their character; see the guide)
    "spacing": [2.5, 1.5],   # pool-to-pool spacing in channel widths, at energy 0 (riffle-pool) .. 1 (step-pool).
    # Real rivers: 5-7 and 1-4. A level compresses a river's length, not its width: at 6 widths an 18 m river had
    # one pool in 110 m and nothing alternated in any view
    "bend": 0.2,             # half-width / radius of curvature that counts as a full bend
    "pool": 0.8,             # m: a pool's extra depth (x the channel's size)
    "riffle": 0.85,          # share of the depth (past 0.18 m) a riffle's crest takes back: shallow, stones awash
    "alternate": 0.75,       # how strongly pools and bars alternate from bank to bank along a straight reach (the
    # thalweg's wander: alternate bars), as a share of a full bend; 0 = only real bends sort the bed
    "cut": [0.35, 0.85],     # m: the cut outer bank's height over the water (wandering between; x the channel's size);
    # [0, 0] = banks as the terrain graded them
    "cut_riser": 0.9,        # m: the cut face's half-width in plan in the meshed ground (the heightmap tiles sample the
    # ground every metre: at 0.35 the step was a sawtooth of triangles along the bank; the maps bake it crisper)
    "bar": 0.10,             # m: a point bar's top over the water (0: bars stay awash)
    "lump": 0.07,            # m: the bed's unevenness (metre-scale)
    "min_depth": 0.08,       # m of water the shaped bed keeps (bars aside)
    "damp": 0.9,             # m above the water the bank is damp (wandering; the bank starts ~0.3 m over the water)
    "shape": True,           # the bed's shape (False: material and clutter only)
    "clutter": 1.0,          # density of the stream, lake and beach clutter (0: none)
    "lakes": True,           # lakes get a shore too (bed, damp foot, margin clutter); False: rivers only
}
LAYERS = ("gravel", "silt", "bank")  # the layers a terrain with running rivers gains (plus rock / wet_rock: bedrock)
LOOK = {  # sRGB
    "gravel": [0.44, 0.41, 0.36], "silt": [0.33, 0.29, 0.22], "bank": [0.25, 0.21, 0.15],
    "moss": [0.20, 0.28, 0.11], "algae": [0.24, 0.27, 0.14], "deep": [0.20, 0.23, 0.17],
}
KINDS = {  # clutter kinds: size = the largest plan dimension (m) at scale 1 x scale; squash relative (1 = the asset's
    # own proportions); z = the bed / ground under the pivot (the asset's pivot sinks it)
    "river_rock": {"scale": [0.35, 1.8], "squash": [0.75, 1.3], "what": "a rounded water-worn boulder"},
    "cobbles": {"scale": [0.6, 1.6], "squash": [0.8, 1.3], "what": "a patch of 5-15 rounded cobbles (6-25 cm each)"},
    "slab": {"scale": [0.5, 2.0], "squash": [0.7, 1.3], "what": "a flat bank stone / ledge piece"},
    "driftwood": {"scale": [0.8, 4.5], "squash": [0.7, 1.5], "what": "a bare log, branch or small jam; yaw = its long "
                  "axis (0 = along world +x)"},
    "reeds": {"scale": [0.5, 1.4], "squash": [0.6, 0.95], "what": "a reed / sedge clump rooted at the water line"},
    "litter": {"scale": [0.8, 2.5], "squash": [1.0, 1.0], "what": "a leaf and twig debris patch (a decal)"},
    "sedge": {"scale": [0.4, 0.9], "squash": [0.8, 1.3], "what": "a sedge / tall bank grass tussock along the wet "
              "margin and the bank's foot"},
    "bush": {"scale": [0.6, 1.9], "squash": [0.45, 1.1], "what": "a bank bush (willow / alder scrub) on the bank top"},
}
PLACES = ("", "water", "margin", "bank", "bar", "shore")
COLS = 18  # (a clutter row: x, y, z, kind, scale, yaw, squash, place, river, water, sink, then a capsule's x0, y0,
# z0, x1, y1, z1, diameter: NaN but for snags and limbs)
from . import terrain_shore as _shore  # noqa: E402  (lake margins and sea beaches: the same rows)
KINDS.update(_shore.KINDS)
from . import terrain_snags as _snags  # noqa: E402  (snags and limbs: capsules resting on the bed, banks, boulders)
KINDS.update({k: {kk: v[kk] for kk in ("scale", "squash", "what")} for k, v in _snags.KINDS.items()})
SPACING = {"river_rock": 1.1, "cobbles": 0.8, "slab": 1.5, "driftwood": 2.2, "reeds": 0.9, "litter": 2.0, "sedge": 0.7,
           "bush": 2.4}


CSV_COLUMNS = "x,y,z,kind,scale,yaw,squash,place,water,sink,x0,y0,z0,x1,y1,z1,diameter"
CSV_VERSION = 3  # (1: ..., place; 2: + water, sink; 3: + a capsule's ends and diameter, snags and limbs only)


def pad(R):
    """Rows of 11 columns (or more) padded to COLS with NaN (no capsule)."""
    R = np.asarray(R, float)
    if R.ndim != 2 or R.shape[1] >= COLS:
        return R
    return np.c_[R, np.full((len(R), COLS - R.shape[1]), np.nan)]
FOOTPRINT = {  # what stands in the water's way, per kind: plan axes and height as shares of scale (x squash);
    # the clutter kit's realistic assets' means (height above the pivot: its seasons json has each variant's)
    "river_rock": {"shape": "ellipsoid", "plan": [1.0, 0.85], "height": 0.44},
    "slab": {"shape": "ellipsoid", "plan": [1.0, 0.95], "height": 0.27},
    "driftwood": {"shape": "ellipsoid", "plan": [1.0, 0.14], "height": 0.14},
    "cobbles": {"shape": "ellipsoid", "plan": [1.0, 0.9], "height": 0.12},
}


def _ss(e0, e1, x):
    u = np.clip((x - e0) / (e1 - e0), 0, 1)
    return u * u * (3 - 2 * u)


def config(T):
    """The spec's stream settings (CFG with "streams": {...} over it), or None when "streams" is false."""
    s = getattr(T, "spec", {}).get("streams", True)
    if s is False:
        return None
    s = s if isinstance(s, dict) else {}
    unknown = set(s) - set(CFG)
    if unknown:
        raise ValueError(f"streams: unknown keys {sorted(unknown)} (have {', '.join(CFG)})")
    return {**CFG, **s}


def _energy(T, name, grade, s, cfg):
    bed = ((getattr(T, "spec", {}).get("rivers") or {}).get(name) or {}).get("bed") or {}
    e = bed.get("energy", "auto") if isinstance(bed, dict) else "auto"
    if e is None or e == "auto":
        return _ss(cfg["grade"][0], cfg["grade"][1], grade)
    e = np.atleast_1d(np.asarray(e, float))
    if len(e) == 1:
        return np.full(len(s), float(np.clip(e[0], 0, 1)))
    u = s / max(float(s[-1]), 1e-9)
    return np.clip(np.interp(u, np.linspace(0, 1, len(e)), e), 0, 1)


# ---------------------------------------------------------------------------------------------- the water as built
WET_REACH = 30.0  # m out from a river's water line (or a pool's centre) the water the ground holds is followed
WET_STEP = 0.25  # m between samples along a cross-section
WET_DEEP = 0.05  # m: ground this far under the level is water
WET_GAP = 1.0  # m: a dry run shorter than this (a stone, a bar's crest) doesn't end the water
MIN_GRADE = 0.002  # the least grade a reach's flow is figured at (a level reach still drains)
FALL_HOLD = 6.0  # m upstream of a fall's lip whose cross-sections are left at the design (the lip band, the faces' hold)


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("terrain_stream_streams", "terrain_stream_water", "terrain_stream_clutter")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
