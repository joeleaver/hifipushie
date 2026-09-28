"""disc_basket: a disc golf target (pole, tray, chain assembly, top band with a number plate), a companion prop for
the gopher disc golfer. Writes examples/disc_basket.json.

Real-world proportions, taken from a reference photo the user supplied: pole 1.33 m, top band 0.55 m across at
1.25-1.30 m, tray 0.66 m across (wider than the band), rim at 0.745 m, bottom at 0.59 m, chains converging on a collar
at 0.66 m below the rim. Slightly stylised: chain links a little chunkier than real, 20 outer + 10 inner chains.

Chains: each chain is a prefab of real interlocking links (flattened ellipsoids with an elliptical hole cut through
each, targeted at that link only, every other link rolled 90 deg), sampled along a slack curve (a cubic Bezier
from the band to the collar on the pole: a deep funnel as tall as the band-to-tray gap, as on real baskets). One prefab per ring, instanced round the pole: the export meshes and bakes
each chain once and places it with a glTF node per instance. The low poly can't keep the holes at a game budget;
the normal/height maps carry them.
Metres, Z up, front -Y."""
import json, math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hifipushie.assemble import _euler_of  # noqa: E402


def box(at, size, part, **kw):
    return {"shape": "box", "at": at, "size": size, "part": part, **kw}


def cyl(at, size, part, **kw):
    return {"shape": "cylinder", "at": at, "size": size, "part": part, **kw}


def cut(at, size, targets, shape="box", **kw):
    return {"shape": shape, "at": at, "size": size, "op": "subtract", "blend": 0, "targets": targets, **kw}


def ring(name, z, r, half_h, wall, part, round_=None, **kw):
    """A hoop: a hollow cylinder with its caps cut away (a band `half_h` tall, `wall` thick)."""
    return {name: cyl([0, 0, z], [r, r, half_h], part, hollow=wall, round=round_ if round_ is not None else wall * 0.45,
                      tags=[name], **kw),
            f"{name}_open": cut([0, 0, z], [r - wall, r - wall, half_h + 0.02], [name], shape="cylinder")}


# ---- heights -----------------------------------------------------------------------------------------------------
# Proportions measured off the user's reference photo (a portable target), scaled to a 0.66 m tray: band 0.84 x the
# tray across, band top to tray rim ~0.85 x tray width, pole thin (~0.06 x tray width), tray ~0.24 x its width deep
POLE_R, POLE_TOP = 0.019, 1.325
BAND_R, BAND_Z, BAND_H, BAND_W = 0.275, 1.275, 0.025, 0.006     # top band: outer radius, centre, half height, wall
HOOP_R = 0.16                                                    # the inner chains' hoop
TRAY_TOP, TRAY_BOT, TRAY_R, TRAY_RB = 0.745, 0.59, 0.33, 0.28
COLLAR_Z = 0.66                                                  # where the chains converge on the pole, below the rim

spec = {"symmetry": False, "blend": 0.003}
spec["story"] = {
    "summary": "a hole on a municipal disc golf course in a city park, installed six years ago, played every day",
    "age": 6,
    "climate": "temperate park: rain, summer sun, winter frost; grass round the pole",
    "use": "thousands of putts a season: discs hit the chains front-on, drop into the tray, are pulled out by hand",
    "directions": {"weather": [-0.4, 1, 0.3], "sun": [0.3, -1, 0.8], "tee": [0, -1, 0]},
    "events": [
        "the top band's paint has faded a little in the sun and is chipped at its lower edge where discs strike",
        "discs have polished the chains bright where they strike; the top links by the band stay duller",
        "hands lifting discs out have scuffed the tray rim bare in places",
        "rain has left faint streaks under the band and a little rust at the tray's welds",
        "grass clippings and mud splash the bottom of the pole",
    ],
}
spec["parts"] = {
    "pole": {"color": "#9ea3a6", "roughness": 0.45, "metallic": 1.0},
    "tray": {"color": "#9ea3a6", "roughness": 0.5, "metallic": 1.0},
    "band": {"color": "#f2b01e", "roughness": 0.45, "metallic": 0.0, "specular": 0.5},
    "plate": {"color": "#f4f1e8", "roughness": 0.5, "specular": 0.5},
    "chains": {"color": "#b8bcbf", "roughness": 0.35, "metallic": 1.0},
}

BL, BO, JO = {}, {}, {}
# pole: one thin tube from the ground to the top cap, straight through band and tray, a sleeve at the ground
JO["pole0"] = {"pos": [0, 0, -0.02], "r": POLE_R}
JO["pole1"] = {"pos": [0, 0, POLE_TOP - 0.01], "r": POLE_R}
BO["pole"] = {"a": "pole0", "b": "pole1", "part": "pole", "ends": "flat"}
BL["cap"] = cyl([0, 0, POLE_TOP - 0.005], [POLE_R + 0.004, POLE_R + 0.004, 0.007], "pole", round=0.005)
BL["sleeve"] = cyl([0, 0, 0.03], [POLE_R + 0.01, POLE_R + 0.01, 0.035], "pole", round=0.005)

# top band: a thin flat ring, a little narrower than the tray, with a lip at its lower edge; spokes from a hub on
# the pole to its top edge; an inner hoop the inner chains hang from; the number plate on its front
BAND_TOP = BAND_Z + BAND_H
BL.update(ring("band", BAND_Z, BAND_R, BAND_H, BAND_W, "band", round_=0.003))
BL["band_lip"] = cyl([0, 0, BAND_Z - BAND_H + 0.004], [BAND_R + 0.003, BAND_R + 0.003, 0.005], "band", round=0.003,
                     hollow=0.01, tags=["band"])
BL["band_lip_open"] = cut([0, 0, BAND_Z - BAND_H + 0.004], [BAND_R - 0.007, BAND_R - 0.007, 0.02], ["band_lip"],
                          shape="cylinder")
BL["hub_top"] = cyl([0, 0, BAND_TOP - 0.012], [0.034, 0.034, 0.018], "pole", round=0.005)
BL["spoke"] = box([BAND_R / 2 + 0.015, 0, BAND_TOP - 0.006], [BAND_R / 2 - 0.02, 0.01, 0.004], "pole", round=0.003,
                  array={"count": 6, "rot": [0, 0, 60], "pivot": [0, 0, 0], "seed": 1})
BL.update(ring("hoop", BAND_Z - 0.012, HOOP_R, 0.005, 0.007, "pole"))
BL["hanger"] = box([HOOP_R, 0, BAND_TOP - 0.022], [0.005, 0.005, 0.018], "pole", round=0.003,
                   array={"count": 6, "rot": [0, 0, 60], "pivot": [0, 0, 0]})
BL["plate"] = box([0, -(BAND_R + 0.004), BAND_Z], [0.06, 0.004, 0.02], "plate", round=0.004, tags=["plate"])
# two low screw heads hold the plate on. They are also what makes the lettering crisp: paint paths are measured per
# vertex of the scene mesh, and a part's voxel follows its thinnest feature, so these 1.8 mm heads take the plate
# from a 3.2 mm voxel to ~0.7 mm
BL["plate_screw"] = cyl([-0.052, -(BAND_R + 0.008), BAND_Z], [0.0035, 0.0035, 0.0009], "plate", rot=[90, 0, 0],
                        round=0.0008, array={"count": 2, "offset": [0.104, 0, 0]})

# chain collar on the pole, where the chains end, a little below the tray rim
BL["collar"] = cyl([0, 0, COLLAR_Z], [0.042, 0.042, 0.01], "pole", round=0.004)

# tray: shallow, open wire. A round top rim ring, two middle rings, a flat bottom ring, 20 bars, a spoked bottom
# (12 spokes, an inner ring) and a hub on the pole
WIRE = 0.006                                            # half thickness of the tray's wire
def tray_ring(name, z, r):
    return ring(name, z, r, WIRE, 2 * WIRE, "tray", round_=WIRE * 0.9)
BL.update(tray_ring("tray_rim", TRAY_TOP, TRAY_R))
for k, f in (("tray_mid1", 1 / 3), ("tray_mid2", 2 / 3)):
    BL.update(tray_ring(k, TRAY_TOP - f * (TRAY_TOP - TRAY_BOT), TRAY_R - f * (TRAY_R - TRAY_RB)))
BL.update(tray_ring("tray_low", TRAY_BOT, TRAY_RB))
BL.update(tray_ring("tray_inner", TRAY_BOT, 0.14))
JO["bar0"] = {"pos": [0, -(TRAY_RB - WIRE), TRAY_BOT], "r": 0.005}
JO["bar1"] = {"pos": [0, -(TRAY_R - WIRE), TRAY_TOP], "r": 0.005}
BO["bar"] = {"a": "bar0", "b": "bar1", "part": "tray", "tags": ["tray_bars"],
             "array": {"count": 20, "rot": [0, 0, 18], "pivot": [0, 0, 0], "seed": 4,
                       "jitter": {"rot": [1.2, 1.2, 0.6]}}}   # bars knocked a degree off by years of discs
JO["tspoke0"] = {"pos": [0, -0.03, TRAY_BOT], "r": 0.005}
JO["tspoke1"] = {"pos": [0, -(TRAY_RB - WIRE), TRAY_BOT], "r": 0.005}
BO["tray_spoke"] = {"a": "tspoke0", "b": "tspoke1", "part": "tray", "tags": ["tray_spokes"],
                    "array": {"count": 12, "rot": [0, 0, 30], "pivot": [0, 0, 0], "seed": 6}}
BL["tray_hub"] = cyl([0, 0, TRAY_BOT + 0.01], [0.034, 0.034, 0.024], "tray", round=0.005)

spec["joints"], spec["bones"], spec["blobs"] = JO, BO, BL


# ---- chains ------------------------------------------------------------------------------------------------------
LINK = [0.0095, 0.0045, 0.021]   # half width, half thickness, half length of a link: long ovals
HOLE = [0.0045, 0.02, 0.0155]    # the hole through it
PITCH = 0.031                     # link to link along the chain


def chain_prefab(p0, p1, p2, p3, seed):
    """Links along a cubic Bezier in the prefab's x-z plane (x = out from the pole), top to bottom."""
    p0, p1, p2, p3 = (np.asarray(p, float) for p in (p0, p1, p2, p3))
    t = np.linspace(0, 1, 4001)[:, None]
    pts = (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    n = int(s[-1] // PITCH) + 1
    blobs = {}
    rng = np.random.default_rng(seed)
    for i in range(n):
        si = i * PITCH
        k = int(np.searchsorted(s, si))
        k = min(max(k, 1), len(pts) - 1)
        c = pts[k]
        tan = pts[min(k + 1, len(pts) - 1)] - pts[k - 1]
        tan /= np.linalg.norm(tan)
        side = np.array([0.0, 1.0, 0.0])                      # across the chain's plane
        inplane = np.cross(tan, side)
        # links alternate: width across the plane, then width in the plane; a few degrees of twist each
        twist = math.radians(rng.uniform(-12, 12))
        w0, w1 = (side, inplane) if i % 2 == 0 else (inplane, -side)
        wx = math.cos(twist) * w0 + math.sin(twist) * w1
        wy = np.cross(tan, wx)
        R = np.stack([wx, wy, tan], axis=1)                   # local x (width), y (thickness), z (length)
        rot = _euler_of(R)
        at = [round(float(v), 5) for v in c]
        blobs[f"link{i:02d}"] = {"at": at, "size": LINK, "rot": rot, "part": "chains", "tags": ["link"]}
        blobs[f"hole{i:02d}"] = {"at": at, "size": HOLE, "rot": rot, "op": "subtract", "blend": 0,
                                 "targets": [f"link{i:02d}"]}
    return {"blobs": blobs}


BAND_IN = BAND_R - BAND_W
spec["prefabs"] = {
    # outer chains: from just inside the band they hang almost straight down, tapering in a little, then curve in
    # together to the collar below the tray rim: a deep funnel as tall as the band-to-tray gap. The control points
    # were fitted to the chain envelope measured off the user's reference photo (r 0.23 at z 1.11, 0.195 at 0.90,
    # 0.165 at 0.78)
    "chain_outer": chain_prefab([BAND_IN - 0.01, 0, BAND_Z - BAND_H], [0.232, 0, 1.06], [0.185, 0, 0.584],
                                [0.05, 0, COLLAR_Z + 0.012], seed=3),
    # inner chains: a smaller bowl from the hoop to the same collar
    "chain_inner": chain_prefab([HOOP_R, 0, BAND_Z - 0.02], [0.14, 0, 1.04], [0.12, 0, 0.62],
                                [0.046, 0, COLLAR_Z + 0.022], seed=5),
}
N_OUT, N_IN = 20, 10
spec["instances"] = {}
for i in range(N_OUT):
    spec["instances"][f"chain_o{i:02d}"] = {"use": "chain_outer", "at": [0, 0, 0], "rot": [0, 0, 360 / N_OUT * i + 9],
                                            "tags": ["chains"]}
for i in range(N_IN):
    spec["instances"][f"chain_i{i:02d}"] = {"use": "chain_inner", "at": [0, 0, 0], "rot": [0, 0, 360 / N_IN * i + 18],
                                            "tags": ["chains"]}

# export budget: the chains are drawn 24 times, so each gets few triangles; the open tray cage, the thin band and the
# pole need more than the joint decimation gives them (at weight 1 the tray's bars were bridged into faceted walls)
for p_, w_ in {"pole": 4, "tray": 2.5, "band": 5, "chains": 0.4}.items():
    spec["parts"][p_]["triangle_weight"] = w_

# ---- paint: galvanised steel, a yellow band, restrained wear from the story -------------------------------------
spec["paint"] = {
 "pole_metal": {
  "material": "metal",
  "part": [
   "pole",
   "tray"
  ],
  "color": "#a3a8aa",
  "roughness": 0.45,
  "wear": 0.2,
  "dirt": 0.2
 },
 "chain_metal": {
  "material": "metal",
  "part": "chains",
  "color": "#bcc1c3",
  "roughness": 0.32,
  "wear": 0.25,
  "dirt": 0.15
 },
 "chain_dull_top": {
  "part": "chains",
  "color": "#8e9496",
  "roughness": 0.55,
  "opacity": 0.35,
  "axis": {
   "dir": [
    0,
    0,
    1
   ],
   "from": 1.17,
   "to": 1.24
  }
 },
 "band_fade": {
  "part": "band",
  "color": "#f6d36a",
  "opacity": 0.2,
  "facing": "sun",
  "range": [
   0.2,
   0.9
  ],
  "mask": [
   {
    "noise": {
     "scale": 0.08,
     "range": [
      0.3,
      0.8
     ]
    }
   }
  ]
 },
 "band_chips": {
  "part": "band",
  "color": "#8f9496",
  "metallic": 1,
  "roughness": 0.4,
  "mask": [
   {
    "cavity": "convex",
    "radius": [
     0.02,
     0.006
    ],
    "breakup": {
     "amount": 0.45,
     "scale": 0.01,
     "sharpness": 0.7
    }
   },
   {
    "axis": {
     "dir": [
      0,
      0,
      1
     ],
     "from": 1.262,
     "to": 1.248
    }
   }
  ]
 },
 "band_streaks": {
  "part": "band",
  "color": "#6e5a33",
  "opacity": 0.15,
  "mask": [
   {
    "noise": {
     "scale": 0.015,
     "stretch": {
      "dir": [
       0,
       0,
       1
      ],
      "factor": 8
     },
     "range": [
      0.6,
      0.78
     ]
    }
   },
   {
    "axis": {
     "dir": [
      0,
      0,
      1
     ],
     "from": 1.29,
     "to": 1.255
    }
   }
  ]
 },
 "tray_rust": {
  "part": "tray",
  "color": "#7a4a2a",
  "roughness": 0.85,
  "metallic": 0.2,
  "opacity": 0.4,
  "mask": [
   {
    "ao": [
     0.75,
     0.45
    ],
    "breakup": {
     "amount": 0.4,
     "scale": 0.01
    }
   }
  ]
 },
 "rim_scuff": {
  "part": "tray",
  "color": "#c9cdce",
  "roughness": 0.25,
  "opacity": 0.6,
  "mask": [
   {
    "axis": {
     "dir": [
      0,
      0,
      1
     ],
     "from": 0.72,
     "to": 0.742
    }
   },
   {
    "cavity": "convex",
    "radius": [
     0.02,
     0.006
    ],
    "breakup": {
     "amount": 0.4,
     "scale": 0.02
    }
   }
  ]
 },
 "pole_mud": {
  "part": "pole",
  "color": "#5a4d36",
  "roughness": 0.9,
  "metallic": 0,
  "opacity": 0.45,
  "mask": [
   {
    "axis": {
     "dir": [
      0,
      0,
      1
     ],
     "from": 0.22,
     "to": 0
    }
   },
   {
    "noise": {
     "scale": 0.02,
     "range": [
      0.35,
      0.65
     ]
    },
    "breakup": 0.3
   }
  ]
 },
 "plate_number": {
  "part": "plate",
  "color": "#1d2a44",
  "path": [
   {
    "at": [
     -0.017,
     -0.283,
     1.289
    ]
   },
   {
    "at": [
     0.016,
     -0.283,
     1.289
    ]
   },
   {
    "at": [
     0.003,
     -0.283,
     1.275
    ]
   },
   {
    "at": [
     -0.006,
     -0.283,
     1.261
    ]
   }
  ],
  "width": 0.005
 },
 "plate_border": {
  "part": "plate",
  "color": "#1d2a44",
  "mask": [
   {
    "cavity": "convex",
    "radius": [
     0.01,
     0.004
    ]
   }
  ]
 }
}

# the plate's lettering: bold "KSM" (a stand-in for the user's logo), one paint path per pen stroke, max-blended;
# addressed on the plate's face (a path point's ray only reaches about the part's size, so "at" sits on the face)
PLATE_Y = -(BAND_R + 0.008)
Z0, Z1, ZM = BAND_Z - 0.013, BAND_Z + 0.013, BAND_Z


def pen(*pts):
    return {"path": [{"at": [x, PLATE_Y, z]} for x, z in pts], "width": 0.0032, "profile": "flat", "blend": "max"}


KSM = [
    pen((-0.041, Z0), (-0.041, Z1)),                                          # K
    pen((-0.024, Z1), (-0.039, ZM)), pen((-0.036, ZM + 0.002), (-0.023, Z0)),
    pen((0.009, Z1 - 0.003), (0.001, Z1), (-0.008, Z1 - 0.005), (-0.006, ZM + 0.002),   # S
        (0.006, ZM - 0.003), (0.009, Z0 + 0.005), (0.0, Z0), (-0.009, Z0 + 0.003)),
    pen((0.023, Z0), (0.023, Z1)), pen((0.024, Z1), (0.032, ZM - 0.002)),     # M
    pen((0.032, ZM - 0.002), (0.040, Z1)), pen((0.041, Z1), (0.041, Z0)),
]
spec["paint"]["plate_number"] = {"part": "plate", "color": "#1d2a44", "mask": KSM}


# ---- plan: the solid envelope, front view (the basket is round: side is the same) ----------------------------------
env = {"pole": {"capsule": [0, 0, 0, POLE_TOP], "r": POLE_R},
       "band": {"poly": [[-BAND_R, BAND_Z - BAND_H], [BAND_R, BAND_Z - BAND_H], [BAND_R, BAND_Z + BAND_H],
                         [-BAND_R, BAND_Z + BAND_H]]},
       "tray": {"poly": [[-TRAY_RB, TRAY_BOT], [TRAY_RB, TRAY_BOT], [TRAY_R, TRAY_TOP], [-TRAY_R, TRAY_TOP]]}}
spec["plan"] = {"views": {"front": {"shapes": env}, "side": {"shapes": env}},
                "landmarks": {}, "sections": {}}

out = Path(__file__).with_name("disc_basket.json")
out.write_text(json.dumps(spec, indent=1))
print(out, len(json.dumps(spec)), "bytes;", {k: len(v["blobs"]) for k, v in spec["prefabs"].items()})
