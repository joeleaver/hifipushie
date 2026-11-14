"""Ground character for the 3D tiles' maps: what the ground looks like between the rock faces, per point (texel or
vertex), the same in every tile and LOD (pointwise on global grids and noise).

The whole-level round (2026-10-02; the user on pebble from 150 m: "WTF?", a cave "with a cover over it"): the ground
was one flat colour per cover layer (plaster), fairways flat light-green stickers, cliffs grey shells on a green
mound with turf rolling over every lip. Compared with photos of real coast (Pebble Beach's 7th, Cornish cliff tops,
Durdle Door), real ground varies at every scale and by its situation:
- the turf ends back from a cliff's lip along a ragged edge (bare rock and a dark undercut below the turf mat), and
  rock breaks through in patches near the edges and on thin-soiled knolls;
- the wave and splash zone is bare rock or sand: no grass within ~1.5 m of the sea;
- grass is drier and paler on convex ground, sun-facing slopes and the salt-burnt first tens of metres above the sea,
  lusher in hollows; patches at tens of metres, tussocks at a metre;
- cover kinds read differently: "mown" (fairways, greens, lawns: even, bright, striped by the mower, a first-cut ring
  at its edge), "rough" (long grass: olive, straw-tipped, tussocky), "scrub" (low bushes: dark grey-green clumps
  with dry gaps, on slopes and near cliffs). Plain "meadow"/"grass" covers are rough; they turn to scrub on
  steeper slopes.
Colour and layer weight (Materials), the maps' own fine relief (Ground.relief: normals only), and two ground edits
finer than the terrain grid that ARE geometry (Edits, applied in Field.column): the turf's step at its edge back from a
cliff lip, and bunkers cut crisp.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at terrain_ground.NAME: C422). terrain_ground_model: `Edits` (what the design cuts and lays) and `Ground`
(the ground's kinds, looks and relief over the terrain). terrain_ground_grass: the grass detail: the sand and grass
swatches (tiling, like the rock's) and their files. terrain_ground_clutter: ground clutter: placeholder instances and
the strips they stand in.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage
from . import moved

def _ss(e0, e1, x):
    u = np.clip((x - e0) / (e1 - e0), 0, 1)
    return u * u * (3 - 2 * u)


def _hex(c):
    return np.array([int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)]) if isinstance(c, str) else np.asarray(c, float)


# what each cover type is, as ground character (types not listed: none of it)
KIND_OF = {"mown": "mown", "lawn": "mown", "fairway": "mown", "green": "mown", "grass": "rough", "meadow": "rough",
           "rough": "rough", "pasture": "rough", "scrub": "scrub", "heath": "scrub", "orchard": "rough"}

LOOK = {  # sRGB
    "straw": [0.66, 0.60, 0.38],        # dry grass, seed heads
    "lush": [0.25, 0.42, 0.14],         # damp hollows
    "salt": [0.58, 0.53, 0.37],         # salt-burnt turf near the sea
    "scrub": [0.25, 0.30, 0.19],        # coastal scrub clumps (sage grey-green)
    "scrub_gap": [0.36, 0.37, 0.24],    # dry grass and litter between them
    "undercut": 0.55,                   # rock just under the turf's edge: shaded
}
LIP = {"band": 1.4, "patches": 7.0, "steep": 50.0, "turf": 0.7, "riser": 0.35, "maps": 0.12, "max": 3.2}
# turf edge set back ~band m (wandering 0.15-2.6x, at most `max` m: inside the cliff overlay's margin); rock patches
# within `patches` m of a lip; a lip = ground steeper than `steep` deg below a top. Geometry: the ground steps down
# `turf` m at the turf's edge (the mat's thickness) onto the bare lip, over a riser +-`riser` m wide (a real step in
# the field: the heightmap, the cliff overlay and both bakes see it); the maps bake it crisper, +-max(`maps`, 2.5
# texels) (+-0.18 m in the meshed field made black shards at the cliff meshes' 0.5 m voxels and pieces floating off
# the lip, and a riser sharper than a couple of texels differed across tile borders).
# Spec: "ground_character": {"lip": {...}}.
STRIPE = {"width": 7.0, "edge": 5.0, "tilt": 0.25, "tone": 0.16}  # mower stripes: m wide, edge crispness, the
# blades' lean as a slope along the mower's way (light one way, dark the other), and the colour step (+-)
RELIEF = {"tussock": 0.07, "clump": 0.06, "bush": 0.16, "cut": 0.01}  # maps-only ground relief, m (fbm^2 heights)
CUT = {"width": 2.2, "wander": 0.25}  # the first cut round mown pieces: m wide, +- share wandering
SHORE = 1.6  # no grass within this many metres above the sea (wandering +-0.8)
BUNKER = {"riser": 0.55, "lip": 0.12, "res": 0.25}  # a bunker's cut face (m across), its turf lip (x depth), sd grid m


def config(T):
    """The spec's ground character settings ({"lip": {...}}), or None when "ground_character" is false."""
    g = getattr(T, "spec", {}).get("ground_character", True)
    if g is False:
        return None
    g = g if isinstance(g, dict) else {}
    return {"lip": {**LIP, **(g.get("lip") or {})}, "bunker": {**BUNKER, **(g.get("bunker") or {})}}


def _grid_at(a, xy, x0, y0, c):
    """A per-cell grid [iy, ix] at points, as Materials._grid reads it (cubic B-spline, no prefilter)."""
    from . import fieldjit
    if fieldjit.ON:
        return fieldjit.grid_at(np.ascontiguousarray(a, dtype=np.float64), np.ascontiguousarray(xy[:, 0], np.float64),
                                np.ascontiguousarray(xy[:, 1], np.float64), float(x0), float(y0), float(c))
    return ndimage.map_coordinates(np.asarray(a, float), [(xy[:, 1] - y0) / c, (xy[:, 0] - x0) / c], order=3,
                                   prefilter=False, mode="nearest")


def signed_distance(T, mask, res=0.5, pad=6.0, box=None, thr=0.5):
    """A smooth signed distance (m, negative inside) to the edge of a cover mask's `thr` contour (the mask read as
    Materials reads it), on a `res` m lattice over `box` ([[x0, y0], [x1, y1]], default the mask's extent) + pad, as
    a function of plan points with .grid/.frame (a cubic spline: the incremental export crops it per tile). Edges cut
    from it are crisp (a mower's line, a bunker's cut) where the cell mask itself is a 2-cell blur."""
    from . import fieldjit
    from .terrain_incremental import Frame
    c = float(T.cell)
    if box is None:
        box = [[float(T.xs[0]), float(T.ys[0])], [float(T.xs[-1]), float(T.ys[-1])]]
    (x0, y0), (x1, y1) = np.asarray(box, float) + np.array([[-pad, -pad], [pad, pad]])
    xs = np.arange(x0, x1 + res, res)
    ys = np.arange(y0, y1 + res, res)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    m = ndimage.map_coordinates(np.asarray(mask, float), [(Y.ravel() - T.ys[0]) / c, (X.ravel() - T.xs[0]) / c],
                                order=3, prefilter=False, mode="nearest").reshape(X.shape)
    inside = m > thr
    if inside.any() and not inside.all():
        sd = np.where(inside, -(ndimage.distance_transform_edt(inside) - 0.5),
                      ndimage.distance_transform_edt(~inside) - 0.5) * res
    else:
        sd = np.full(X.shape, -pad if inside.all() else pad)
    sd = ndimage.gaussian_filter(sd, 0.8)
    coef = ndimage.spline_filter(sd, order=3)
    xs0, ys0 = float(xs[0]), float(ys[0])

    def f(xy):
        xy = np.atleast_2d(np.asarray(xy, float))
        if fieldjit.ON:
            return fieldjit.grid_at(coef, np.ascontiguousarray(xy[:, 1], np.float64),
                                    np.ascontiguousarray(xy[:, 0], np.float64), ys0, xs0, res)
        return ndimage.map_coordinates(coef, [(xy[:, 0] - xs0) / res, (xy[:, 1] - ys0) / res], order=3,
                                       prefilter=False, mode="nearest")
    f.grid, f.frame = coef, Frame("sd", coef.shape, "xy", xs0, ys0, res)
    return f


# ---------------------------------------------------------------- the grass detail (a tiling swatch, like the rock's)
GRASS = {"size": 2.0, "res": 256, "blades": 26000, "length": (0.03, 0.09), "dry": 0.12}
SWATCHES = {  # the tiling grass detail per ground layer: blades per 4 m2, blade length m, dry share, clumpiness,
    # blade lean (0 = any way, 1 = all one way), tip lift
    "turf": {"layers": ["turf"], "blades": 70000, "length": (0.012, 0.035), "dry": 0.03, "clump": 0.35,
             "seed": 4241, "fade": (30.0, 110.0)},  # mown: short, dense, even (fine: it can show farther)
    "grass": {"layers": ["grass", "scrub"], "blades": 22000, "length": (0.05, 0.16), "dry": 0.2, "clump": 1.0,
              "seed": 4243},  # long grass: clumpy, straw blades among the green
    "sand": {"layers": ["sand"], "gen": "sand", "seed": 4245},  # wind ripples in patches, grit, pebbles and shell
    # a stream's bed (terrain_stream): packed cobbles and pebbles; fine silt and damp earth with pebbles and flecks
    "gravel": {"layers": ["gravel"], "gen": "cobble", "seed": 4251, "fade": (25.0, 80.0)},
    "silt": {"layers": ["silt", "bank"], "gen": "silt", "seed": 4253},
}

GRASS_FADE = (20.0, 70.0)  # m: the grass detail fades out with the view distance (its 2 m repeat shows beyond)


# ---------------------------------------------------------------- ground clutter (placeholder instances)
CLUTTER = {  # kind: grid spacing m (jittered grid samples kept by probability)
    "bush": 1.3,       # coastal scrub / heath clumps, 0.5-1.4 m: in scrub, on its clumps (the maps' dark clumps)
    "tussock": 0.7,    # long-grass tussocks, 0.3-0.6 m: in rough grass, off scrub and the first cut
    "tallgrass": 0.3,  # long grass filling in round the eye (renders only, like an engine's grass near the camera)
    "boulder": 1.6,    # rocks 0.3-1.5 m: in clusters on the shore's splash zone and where rock breaks through
}
TREE_LIP = {"default": 4.0, "cypress": 1.5, "shrub": 2.0}  # trees: m in from the turf's edge back from a lip
CLUTTER_NEAR = {"tallgrass": 28.0}  # kinds placed only this close to the render's eyes (m), thinning out with distance
CLUTTER_MID = (20.0, 70.0, 0.6, 0.9)  # tussocks from / to (m from the eye): x (1 + a) as many, x (1 + b) as big
CLUTTER_LIP = {"keep": 1.8, "hug": 7.0, "squash": 0.45}  # bushes: none within `keep` m of the turf's edge (back from
# a cliff's lip), hugging the ground (height x squash, broader) out to `hug` m: wind-shorn, not perched on the edge


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("terrain_ground_model", "terrain_ground_grass", "terrain_ground_clutter")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
