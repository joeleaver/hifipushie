"""disc_basket_stylized: the disc basket (examples/disc_basket_src.py) adapted to the disc golfer's stylised-realistic
animated-feature look, and a little more used. Writes examples/disc_basket_stylized.json.

Same readable design and real proportions as disc_basket (fitted to the user's reference photo), simplified and
pushed a little:
- chunkier, softer members with rounded bevels: pole r 28 mm (19), tray wire 20 mm (12), bars 18 mm (10), fewer of
  them (14 bars, 8 bottom spokes, one middle ring), a bolder band (80 mm tall, 12 mm wall; was 50 / 6);
- fewer, bigger links (60 x 30 mm, was 42 x 19): 20 outer + 10 inner chains, still a dense curtain, reading as shapes;
- gesture: the band sits 0.8 deg askew (knocked by years of discs), one chain has come off its collar hook and hangs
  loose into the tray, two chains are tangled across their neighbours, the front tray bar is bent in;
- paint as clean, saturated colour blocks with soft gradients (no material noise), wear motivated by use: sun-bleached
  band top, disc scuffs and plastic smears on the band's lower front, chipped lower edge, bright steel where discs
  strike the chains and where hands grab the tray rim, rust blooms where water sits (tray bottom ring, spokes, hub),
  mud and grass at the pole foot, an old sticker torn off the pole.
Chains are prefabs of real interlocking links (see disc_basket_src.py), instanced round the pole.
Metres, Z up, front -Y."""
import json, math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hifipushie.assemble import _euler_of  # noqa: E402
from hifipushie.spec import euler_matrix  # noqa: E402


def box(at, size, part, **kw):
    return {"shape": "box", "at": at, "size": size, "part": part, **kw}


def cyl(at, size, part, **kw):
    return {"shape": "cylinder", "at": at, "size": size, "part": part, **kw}


def cut(at, size, targets, shape="box", **kw):
    return {"shape": shape, "at": at, "size": size, "op": "subtract", "blend": 0, "targets": targets, **kw}


def ring(name, z, r, half_h, wall, part, round_=None, rot=None, **kw):
    """A hoop: a hollow cylinder with its caps cut away (a band `half_h` tall, `wall` thick)."""
    extra = {"rot": rot} if rot else {}
    return {name: cyl([0, 0, z], [r, r, half_h], part, hollow=wall, round=round_ if round_ is not None else wall * 0.45,
                      tags=[name], **extra, **kw),
            f"{name}_open": cut([0, 0, z], [r - wall, r - wall, half_h + 0.03], [name], shape="cylinder", **extra)}


# ---- sizes -------------------------------------------------------------------------------------------------------
POLE_R, POLE_TOP = 0.028, 1.34
BAND_R, BAND_Z, BAND_H, BAND_W = 0.28, 1.27, 0.04, 0.012
BAND_TILT = [0.8, 0.5, 0]                                        # deg: knocked askew
HOOP_R = 0.16
TRAY_TOP, TRAY_BOT, TRAY_R, TRAY_RB = 0.745, 0.585, 0.335, 0.28
COLLAR_Z = 0.66
WIRE = 0.010                                                     # tray wire half thickness
BAR_R = 0.009
N_BARS = 14

spec = {"symmetry": False, "blend": 0.006}
spec["story"] = {
    "summary": "a hole on a busy municipal disc golf course, ten years in the ground, played hard every day",
    "age": 10,
    "climate": "temperate park: rain, strong summer sun, winter frost; grass and mud round the pole",
    "use": "thousands of putts a season hit the chains front-on and drop into the tray; players grab the rim to pull "
           "discs out; the course crew mows round it",
    "directions": {"weather": [-0.4, 1, 0.3], "sun": [0.3, -1, 0.8], "tee": [0, -1, 0]},
    "events": [
        "sun has bleached the top of the band pale",
        "discs strike the band's lower front: scuffs, coloured plastic smears and chipped paint along its lower edge",
        "a big drive knocked the band a little askew",
        "discs polish the chains bright where they strike; the links near the band stay dull",
        "one chain came off its hook at the collar and hangs loose; two others got tangled across their neighbours",
        "a drive bent the front tray bar in",
        "hands grabbing the tray rim to pull discs out have worn it bright",
        "rain sits in the tray bottom: rust blooms on the bottom ring, spokes and hub",
        "the mower throws mud and grass at the pole foot",
        "someone's sticker on the pole was torn off years ago; a pale scrap is left",
    ],
}
spec["parts"] = {
    "pole": {"color": "#7d8ea3", "roughness": 0.35, "metallic": 0.85},
    "tray": {"color": "#7d8ea3", "roughness": 0.38, "metallic": 0.85},
    "band": {"color": "#ff9a0a", "roughness": 0.4, "metallic": 0.0, "specular": 0.5},
    "plate": {"color": "#fbf7ec", "roughness": 0.45, "specular": 0.5},
    "chains": {"color": "#d2cdc2", "roughness": 0.5, "metallic": 0.9},
}

R_BAND = euler_matrix(BAND_TILT)


def on_band(p):
    """A point given for the level band, moved with the band's tilt about its centre."""
    c = np.array([0, 0, BAND_Z])
    return [round(float(v), 6) for v in c + R_BAND @ (np.asarray(p, float) - c)]


BL, BO, JO = {}, {}, {}
# pole, cap, ground sleeve
JO["pole0"] = {"pos": [0, 0, -0.02], "r": POLE_R}
JO["pole1"] = {"pos": [0, 0, POLE_TOP - 0.012], "r": POLE_R}
BO["pole"] = {"a": "pole0", "b": "pole1", "part": "pole", "ends": {"flat": 0.006}}
BL["cap"] = {"at": [0, 0, POLE_TOP - 0.008], "size": [POLE_R + 0.008, POLE_R + 0.008, 0.02], "part": "pole"}
BL["sleeve"] = cyl([0, 0, 0.035], [POLE_R + 0.014, POLE_R + 0.014, 0.04], "pole", round=0.01)

# the band (tilted), its lip, spokes to a hub, the inner hoop and its hangers, the plate
BAND_TOP = BAND_Z + BAND_H
BL["band"] = cyl([0, 0, BAND_Z], [BAND_R, BAND_R, BAND_H], "band", hollow=BAND_W, round=0.006, rot=BAND_TILT,
                 tags=["band"])
BL["band_open"] = cut([0, 0, BAND_Z], [BAND_R - BAND_W, BAND_R - BAND_W, BAND_H + 0.03], ["band"], shape="cylinder",
                      rot=BAND_TILT)
BL["band_lip"] = cyl(on_band([0, 0, BAND_Z - BAND_H + 0.006]), [BAND_R + 0.005, BAND_R + 0.005, 0.008], "band",
                     round=0.005, hollow=0.016, rot=BAND_TILT, tags=["band"])
BL["band_lip_open"] = cut(on_band([0, 0, BAND_Z - BAND_H + 0.006]), [BAND_R - 0.011, BAND_R - 0.011, 0.03],
                          ["band_lip"], shape="cylinder", rot=BAND_TILT)
BL["hub_top"] = cyl([0, 0, BAND_TOP - 0.018], [0.045, 0.045, 0.025], "pole", round=0.012)
BL["spoke"] = box([BAND_R / 2 + 0.02, 0, BAND_TOP - 0.01], [BAND_R / 2 - 0.025, 0.014, 0.007], "pole", round=0.006,
                  array={"count": 6, "rot": [0, 0, 60], "pivot": [0, 0, 0], "seed": 1,
                         "jitter": {"rot": [0, 0.6, 1.0]}})
BL.update(ring("hoop", BAND_Z - 0.015, HOOP_R, 0.007, 0.011, "pole", round_=0.006))
BL["hanger"] = box([HOOP_R, 0, BAND_TOP - 0.03], [0.007, 0.007, 0.022], "pole", round=0.005,
                   array={"count": 6, "rot": [0, 0, 60], "pivot": [0, 0, 0]})
PLATE_C = on_band([0, -(BAND_R + 0.006), BAND_Z])
BL["plate"] = box(PLATE_C, [0.07, 0.006, 0.027], "plate", round=0.006, rot=BAND_TILT, tags=["plate"])
# screw heads: real, and they set the plate's scene voxel fine enough for crisp lettering (see disc_basket_src.py)
for i, sx in enumerate((-0.06, 0.06)):
    BL[f"plate_screw{i}"] = cyl(on_band([sx, -(BAND_R + 0.0125), BAND_Z]), [0.0045, 0.0045, 0.0011], "plate",
                                rot=[90 + BAND_TILT[0], BAND_TILT[1], 0], round=0.001)

BL["collar"] = cyl([0, 0, COLLAR_Z], [0.05, 0.05, 0.014], "pole", round=0.008)


# tray: round rim ring, one middle ring, bottom ring, inner bottom ring, 13 bars + one bent in at the front, 8 spokes, hub
def tray_ring(name, z, r):
    return ring(name, z, r, WIRE, 2 * WIRE, "tray", round_=WIRE * 0.95)


BL.update(tray_ring("tray_rim", TRAY_TOP, TRAY_R))
BL.update(tray_ring("tray_mid", (TRAY_TOP + TRAY_BOT) / 2, (TRAY_R + TRAY_RB) / 2))
BL.update(tray_ring("tray_low", TRAY_BOT, TRAY_RB))
BL.update(tray_ring("tray_inner", TRAY_BOT, 0.14))
step = 360 / N_BARS
a1 = math.radians(step)
JO["bar0"] = {"pos": [math.sin(a1) * (TRAY_RB - WIRE), -math.cos(a1) * (TRAY_RB - WIRE), TRAY_BOT], "r": BAR_R}
JO["bar1"] = {"pos": [math.sin(a1) * (TRAY_R - WIRE), -math.cos(a1) * (TRAY_R - WIRE), TRAY_TOP], "r": BAR_R}
BO["bar"] = {"a": "bar0", "b": "bar1", "part": "tray", "tags": ["tray_bars"],
             "array": {"count": N_BARS - 1, "rot": [0, 0, step], "pivot": [0, 0, 0], "seed": 4,
                       "jitter": {"rot": [1.5, 1.5, 0.8]}}}
JO["bent0"] = {"pos": [0, -(TRAY_RB - WIRE), TRAY_BOT], "r": BAR_R}
JO["bent1"] = {"pos": [0, -(TRAY_R - WIRE), TRAY_TOP], "r": BAR_R}
BO["bar_bent"] = {"a": "bent0", "b": "bent1", "part": "tray", "tags": ["tray_bars"], "bow": [0.035, -0.015]}
JO["tspoke0"] = {"pos": [0, -0.04, TRAY_BOT], "r": BAR_R}
JO["tspoke1"] = {"pos": [0, -(TRAY_RB - WIRE), TRAY_BOT], "r": BAR_R}
BO["tray_spoke"] = {"a": "tspoke0", "b": "tspoke1", "part": "tray", "tags": ["tray_spokes"],
                    "array": {"count": 8, "rot": [0, 0, 45], "pivot": [0, 0, 0], "seed": 6}}
BL["tray_hub"] = cyl([0, 0, TRAY_BOT + 0.012], [0.045, 0.045, 0.03], "tray", round=0.012)

spec["joints"], spec["bones"], spec["blobs"] = JO, BO, BL


# ---- chains ------------------------------------------------------------------------------------------------------
LINK = [0.015, 0.0065, 0.030]    # half width, half thickness, half length: fewer, bigger links
HOLE = [0.0072, 0.03, 0.021]
PITCH = 0.043


def chain_prefab(p0, p1, p2, p3, seed):
    """Links along a cubic Bezier from p0 (top) to p3 (x = out from the pole, y = sideways, z up)."""
    p0, p1, p2, p3 = (np.asarray(p, float) for p in (p0, p1, p2, p3))
    t = np.linspace(0, 1, 4001)[:, None]
    pts = (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    n = int(s[-1] // PITCH) + 1
    blobs = {}
    rng = np.random.default_rng(seed)
    for i in range(n):
        k = min(max(int(np.searchsorted(s, i * PITCH)), 1), len(pts) - 1)
        c = pts[k]
        tan = pts[min(k + 1, len(pts) - 1)] - pts[k - 1]
        tan /= np.linalg.norm(tan)
        side = np.cross([0.0, 0.0, 1.0], [c[0], c[1], 0.0])  # across the radial plane
        side = side / np.linalg.norm(side) if np.linalg.norm(side) > 1e-9 else np.array([0.0, 1.0, 0.0])
        side = side - tan * (side @ tan)
        side /= np.linalg.norm(side)
        inplane = np.cross(tan, side)
        twist = math.radians(rng.uniform(-15, 15))
        w0, w1 = (side, inplane) if i % 2 == 0 else (inplane, -side)
        wx = math.cos(twist) * w0 + math.sin(twist) * w1
        wy = np.cross(tan, wx)
        rot = _euler_of(np.stack([wx, wy, tan], axis=1))
        at = [round(float(v), 5) for v in c]
        blobs[f"link{i:02d}"] = {"at": at, "size": LINK, "rot": rot, "part": "chains", "tags": ["link"]}
        blobs[f"hole{i:02d}"] = {"at": at, "size": HOLE, "rot": rot, "op": "subtract", "blend": 0,
                                 "targets": [f"link{i:02d}"]}
    return {"blobs": blobs}


BAND_IN = BAND_R - BAND_W
TOP_O = [BAND_IN - 0.016, 0, BAND_Z - BAND_H + 0.004]
spec["prefabs"] = {
    # the funnel fitted to the reference photo (disc_basket), scaled to the chunkier band
    "chain_outer": chain_prefab(TOP_O, [0.228, 0, 1.06], [0.185, 0, 0.584], [0.052, 0, COLLAR_Z + 0.016], seed=3),
    "chain_inner": chain_prefab([HOOP_R, 0, BAND_Z - 0.024], [0.14, 0, 1.04], [0.12, 0, 0.62],
                                [0.048, 0, COLLAR_Z + 0.03], seed=5),
    # off its hook at the collar: hangs straight down from the band, its free end lying in the tray
    "chain_loose": chain_prefab(TOP_O, [0.262, 0.0, 1.0], [0.258, 0.01, 0.8], [0.25, 0.03, 0.64], seed=7),
    # tangled: crosses over the next chain round and comes back to the collar
    "chain_tangled": chain_prefab(TOP_O, [0.23, 0.13, 1.05], [0.17, 0.15, 0.62], [0.052, 0.0, COLLAR_Z + 0.016], seed=9),
}
N_OUT, N_IN = 20, 10
LOOSE, TANGLED = {15}, {16, 18}      # in front of the main camera (front is -Y: 270 deg)
spec["instances"] = {}
for i in range(N_OUT):
    use = "chain_loose" if i in LOOSE else "chain_tangled" if i in TANGLED else "chain_outer"
    spec["instances"][f"chain_o{i:02d}"] = {"use": use, "at": [0, 0, 0], "rot": [0, 0, 360 / N_OUT * i + 9],
                                            "tags": ["chains"]}
for i in range(N_IN):
    spec["instances"][f"chain_i{i:02d}"] = {"use": "chain_inner", "at": [0, 0, 0], "rot": [0, 0, 360 / N_IN * i + 18],
                                            "tags": ["chains"]}

for p_, w_ in {"pole": 3, "tray": 2.5, "band": 5, "chains": 0.4}.items():
    spec["parts"][p_]["triangle_weight"] = w_

# ---- paint: colour blocks with soft gradients, wear from the story ---------------------------------------------
P = {}
# soft form gradients (top lit, darker toward the ground), like a feature-animation shader, no texture noise
P["steel_top_light"] = {"part": ["pole", "tray"], "color": "#aebccc", "opacity": 0.45, "facing": [0, 0, 1],
                        "range": [0.0, 0.9]}
P["pole_ground_dark"] = {"part": "pole", "color": "#56637a", "opacity": 0.35,
                         "axis": {"dir": [0, 0, 1], "from": 0.55, "to": 0.05}}
# chains: warm light zinc, satin; brightness varies only with wear (dull by the band, bright where discs strike)
P["chain_dull_top"] = {"part": "chains", "color": "#9d998f", "roughness": 0.6, "opacity": 0.55,
                       "axis": {"dir": [0, 0, 1], "from": 1.13, "to": 1.23}}
P["chain_strike_bright"] = {"part": "chains", "color": "#efece4", "roughness": 0.32, "opacity": 0.5,
                            "mask": [{"axis": {"dir": [0, 0, 1], "from": 0.78, "to": 0.9}},
                                     {"axis": {"dir": [0, 0, 1], "from": 1.12, "to": 1.0}}]}
P["band_top_light"] = {"part": "band", "color": "#ffb52e", "opacity": 0.4, "axis": {"dir": [0, 0, 1], "from": 1.235,
                                                                                    "to": 1.3}}
P["band_sun_bleach"] = {"part": "band", "color": "#ffe3a3", "opacity": 0.45,
                        "mask": [{"axis": {"dir": [0, 0, 1], "from": 1.285, "to": 1.31}},
                                 {"facing": "sun", "range": [-0.3, 0.6]},
                                 {"noise": {"scale": 0.06, "range": [0.25, 0.65]}}]}


# disc strikes on the band's lower front: a few arcs, each the curve of a disc's rim, as painted paths
def strike(xc, zc, r, a0, a1, width):
    pts = [on_band([xc + r * math.cos(math.radians(a)), -math.sqrt(max(BAND_R ** 2 - (xc + r * math.cos(math.radians(a))) ** 2, 0)) - 0.001,
                    zc + r * math.sin(math.radians(a))]) for a in np.linspace(a0, a1, 5)]
    return {"path": [{"at": p} for p in pts], "width": width, "profile": "soft"}


P["band_strike_dark"] = {"part": "band", "color": "#5d5249", "opacity": 0.5, "mask": [
    {**strike(-0.12, 1.31, 0.065, 215, 300, 0.007), "blend": "max"},
    {**strike(0.21, 1.305, 0.05, 240, 320, 0.006), "blend": "max"}]}
P["band_strike_pink"] = {"part": "band", "color": "#e0357f", "opacity": 0.65, "mask": [strike(0.13, 1.312, 0.07, 225, 305, 0.008)]}
P["band_strike_teal"] = {"part": "band", "color": "#1fb5a8", "opacity": 0.6, "mask": [strike(-0.2, 1.305, 0.06, 235, 300, 0.007)]}
P["band_chips"] = {"part": "band", "color": "#8795a8", "metallic": 0.9, "roughness": 0.35,
                   "mask": [{"cavity": "convex", "radius": [0.02, 0.006],
                             "breakup": {"amount": 0.35, "scale": 0.012, "sharpness": 0.8}},
                            {"axis": {"dir": [0, 0, 1], "from": 1.25, "to": 1.232}},
                            {"facing": [0, -1, 0], "range": [-0.6, 0.4]}]}
P["tray_rim_worn"] = {"part": "tray", "color": "#e3eaf1", "roughness": 0.15, "opacity": 0.8,
                      "near": ["tray_rim"], "within": 0.004,
                      "mask": [{"facing": [0, 0, 1], "range": [0.2, 0.8]},
                               {"noise": {"scale": 0.06, "range": [0.45, 0.6]}}]}
# rust where water sits: most joints clean; a few spokes rusted at their ends (one value per spoke), a bloom where
# the bottom pools (the low front-left, under the bent bar's side), a streak down two bars from the middle ring
P["rust_spokes"] = {"part": "tray", "color": "#b8561d", "roughness": 0.8, "metallic": 0.1, "opacity": 0.75,
                    "near": ["tray_spoke"], "within": 0.004,
                    "mask": [{"random": {"range": [0.66, 0.68], "seed": 3}},
                             {"ao": [0.97, 0.8], "breakup": {"amount": 0.25, "scale": 0.02}}]}
P["rust_pool"] = {"part": "tray", "color": "#a94c1a", "roughness": 0.85, "metallic": 0.1, "opacity": 0.6,
                  "mask": [{"axis": {"dir": [-0.6, -0.8, 0], "from": 0.12, "to": 0.27}},
                           {"axis": {"dir": [0, 0, 1], "from": 0.63, "to": 0.595}},
                           {"noise": {"scale": 0.03, "range": [0.45, 0.6], "seed": 4}}]}
P["rust_streak"] = {"part": "tray", "color": "#a94c1a", "opacity": 0.6,
                    "near": ["bar"], "within": 0.003,
                    "mask": [{"random": {"range": [0.8, 0.82], "seed": 9}},
                             {"axis": {"dir": [0, 0, 1], "from": 0.59, "to": 0.66}},
                             {"axis": {"dir": [0, 0, 1], "from": 0.685, "to": 0.672}},
                             {"noise": {"scale": 0.008, "stretch": {"dir": [0, 0, 1], "factor": 8},
                                        "range": [0.5, 0.62]}}]}
P["pole_rust_drip"] = {"part": "pole", "color": "#a35423", "opacity": 0.4,
                       "mask": [{"axis": {"dir": [0, 0, 1], "from": 0.45, "to": 0.56}},
                                {"axis": {"dir": [0, 0, 1], "from": 0.585, "to": 0.56}},
                                {"noise": {"scale": 0.01, "stretch": {"dir": [0, 0, 1], "factor": 8},
                                           "range": [0.6, 0.72]}}]}
# the pole foot: one soft band of dark earth fading upward, splashed higher in places, a faint grass tint inside it
P["pole_mud"] = {"part": "pole", "color": "#4e3b27", "roughness": 0.9, "metallic": 0, "opacity": 0.7,
                 "mask": [{"axis": {"dir": [0, 0, 1], "from": 0.2, "to": 0.02}},
                          {"mask": [{"axis": {"dir": [0, 0, 1], "from": 0.32, "to": 0.12}},
                                    {"noise": {"scale": 0.035, "stretch": {"dir": [0, 0, 1], "factor": 3},
                                               "range": [0.5, 0.7]}}], "blend": "max"},
                          {"blur": 0.01}]}
P["pole_grass"] = {"part": "pole", "color": "#5f6a33", "roughness": 0.85, "metallic": 0, "opacity": 0.25,
                   "mask": [{"axis": {"dir": [0, 0, 1], "from": 0.1, "to": 0.02}},
                            {"noise": {"scale": 0.04, "range": [0.3, 0.7], "seed": 5}}]}
P["pole_sticker"] = {"part": "pole", "color": "#efe9d6", "roughness": 0.7, "metallic": 0,
                     "mask": [{"path": [{"bone": "pole", "t": 0.33, "side": [0.4, -1, 0]}, {"t": 0.37}],
                               "width": 0.016},
                              {"noise": {"scale": 0.008, "range": [0.3, 0.55], "seed": 8}}]}
P["pole_sticker_glue"] = {"part": "pole", "color": "#9c9580", "opacity": 0.5,
                          "mask": [{"path": [{"bone": "pole", "t": 0.325, "side": [0.4, -1, 0]}, {"t": 0.375}],
                                    "width": 0.02},
                                   {"noise": {"scale": 0.008, "range": [0.3, 0.55], "seed": 8}, "invert": True}]}

# the plate: KSM (a stand-in for the user's logo), bolder strokes to match the chunkier plate
c = np.asarray(PLATE_C)
PLATE_Y = -(BAND_R + 0.0125)
Z0, Z1, ZM = BAND_Z - 0.016, BAND_Z + 0.016, BAND_Z


def pen(*pts):
    return {"path": [{"at": on_band([x * 1.12, PLATE_Y, z])} for x, z in pts], "width": 0.0045, "profile": "flat",
            "blend": "max"}


P["plate_fade"] = {"part": "plate", "color": "#fff6d8", "opacity": 0.25, "facing": "sun", "range": [0, 0.8]}
P["plate_border"] = {"part": "plate", "color": "#1d2a44", "mask": [{"cavity": "convex", "radius": [0.012, 0.005]}]}
P["plate_number"] = {"part": "plate", "color": "#1d2a44", "mask": [
    pen((-0.041, Z0), (-0.041, Z1)),
    pen((-0.024, Z1), (-0.039, ZM)), pen((-0.036, ZM + 0.002), (-0.023, Z0)),
    pen((0.009, Z1 - 0.004), (0.001, Z1), (-0.008, Z1 - 0.006), (-0.006, ZM + 0.003),
        (0.006, ZM - 0.004), (0.009, Z0 + 0.006), (0.0, Z0), (-0.009, Z0 + 0.004)),
    pen((0.023, Z0), (0.023, Z1)), pen((0.024, Z1), (0.032, ZM - 0.003)),
    pen((0.032, ZM - 0.003), (0.040, Z1)), pen((0.041, Z1), (0.041, Z0))]}
spec["paint"] = P

out = Path(__file__).with_name("disc_basket_stylized.json")
out.write_text(json.dumps(spec, indent=1))
print(out, len(json.dumps(spec)), "bytes;", {k: len(v["blobs"]) for k, v in spec["prefabs"].items()})
