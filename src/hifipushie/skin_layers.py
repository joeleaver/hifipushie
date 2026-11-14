"""The skin as a STACK OF LAYER MAPS decomposed from the de-lit reference atlas (projskin, Stage 1b; Joe: "we'd have to
build up a layer map from the reference texture as best we could"). The photograph's pixels do not ship; its
DECOMPOSITION does: each layer is one physical cause with its own map in the head's atlas (where, how much), smooth
at the scale that cause really has; the fine structure inside it stays our procedural generators'.

THE DECOMPOSITION. In optical density (D = -log albedo, per channel) skin colour is close to a base plus two
chromophores' amounts times their absorption colours: melanin and haemoglobin (Tsumura, Haneishi, Miyake 1999,
"Independent-component analysis of skin color image", JOSA A 16:2169; Tsumura et al. 2003, "Image-based skin color and
texture analysis / synthesis by extracting hemoglobin and melanin information in the skin", SIGGRAPH). They find the
two colour axes by ICA on the picture and keep shading on the (1, 1, 1) axis. WHAT IS IMPLEMENTED HERE: the two axes
are OUR pigment model's own (skin.tone_rgb's derivative in melanin and in blood at the model's tone: the same
colours every skin layer of ours is made of, so a map drives our generators directly and an edit is a pigment edit),
plus a NEUTRAL axis (1, 1, 1) for darkness that has no pigment colour (hair under the skin, shade of forms the head
lacks). Per texel D - D_tone = m v_mel + h v_hem + d v_neu is solved exactly (3 unknowns, 3 channels); `ica_check`
runs the paper's ICA in the shading-free plane and reports how far the data's own axes lie from ours.

THE STACK (in this order; each takes, from what the layers before left, its own axes, inside its own support, at its
own scale; what no layer takes is the RESIDUAL):
  pigment      melanin, everywhere, 4 mm            the base pigment field (tan, paler round the mouth)
  redness      haemoglobin, everywhere, 2.5 mm      cheeks, nose, lids, chin
  periorbital  melanin + haemoglobin + neutral, the orbit / lids / under-eye, 1.2 mm    dark circles, the lids' own colour
  brows        melanin + neutral, the brow regions, 0.7 mm          the brows' darkness as skin under our hair curves
  lips         all three, inside the vermilion (its edge from the picture's own colour edge), 0.8 mm
  beard        neutral + melanin, the beard zones, 2 mm              stubble shadow: density / colour (drives strands or paint)
  freckles     melanin's fine band (0.35-1.5 mm, positive), plain skin, as a DENSITY map (3 mm) for the generator;
               prominent marks are placed one by one (skin_project_model.marks)
  shade        neutral, everywhere, 3 mm            dark with no pigment colour and no layer of its own: mostly the
               shade of forms the head does not have (Stage 2 takes it back as form)
Each map is filled where no picture vouches for it: the mirror image first, then the layer's own neighbourhood inside
its support, then its mean; `provenance` marks every texel measured / mirrored / inferred.

  decompose(name)          -> the maps, the recomposition and its error, the per-layer text
  apply(name, out=None)    -> the maps stored as images, spec["skin"]["stack"] saved; skin layers "skin:stack_*"
  layers(spec, st, out, part)   (skin_features_build.build) the stack as paint layers: an opaque base + one multiply layer a map
  edit(spec, **kw)         -> a copy with layer strengths changed (blush, tan, older, no stubble): one map each

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at skin_layers.NAME: C422). skin_layers_lips: the lips in the stack: the lip mask and lips read from the
picture's indications. skin_layers_shade: shading the stack removes: soft fill, the blink still, occlusion, the
crease's tint and map, shadow weights. skin_layers_decompose: `decompose`: the de-lit atlas split into the stack's
layers, with its error and multiplier. skin_layers_stack: the stack in use: apply, re-baked on the export's head,
check, layers, only, edit, even_out.
"""
from __future__ import annotations

import numpy as np

from . import skin_project as sp
from . import skin_project_atlas
from . import moved

VERSION = 1
P0 = 0.8                 # a layer's default opacity: its stored multiplier is exact at P0 and leaves room to 1.0 (x 1.25)
LAYERS = (  # name, axes (m melanin, h haemoglobin, d neutral), support, scale mm
    ("pigment", "m", "all", 4.0),
    ("redness", "h", "all", 4.5),   # (2.5: cheek blush as round saturated patches; real flush is an even warmth)
    ("periorbital", "mh", "orbit", 1.2),   # (no neutral: the socket's own shading, under-lit by the de-lighting, read as a
                                           # purple-brown ring round the orbit, above the crease and under the eye)
    ("brows", "md", "brow", 0.7),
    ("lips", "mh", "lips", 0.3),     # (pigment only: its neutral darkness was the lower lip's own shading, a grey-brown lip)
    ("beard", "dm", "beard", 2.0),
    ("shade", "d", "all", 3.0),
)
SUPPORT = {"orbit": ("orbit", "under_eye"), "brow": ("brow",), "beard": ("upper_lip_skin", "lower_lip_skin", "chin", "jaw_side", "cheek")}
FRECKLE_BAND = (0.35, 1.5)   # mm: the fine melanin band that is freckles
BLEMISH_BAND = (0.4, 2.0)    # mm: the fine haemoglobin band that is blemishes (red papules / marks)
BLEMISH_REF = 0.05           # its 3 mm mean (blood x) that is a full blemish field (p99s measured 0.034 .. 0.050 on test heads)
BLEMISH_FLOOR = 0.03         # a p99 under this: no blemishes (an even skin's own grain)
FINE_FULL = 0.12         # rms log luminance under 1.2 mm that our fine generator gives at full strength (FINE_TINT, two scales)
FINE_TINT = (0.84, 0.77, 0.74)   # the fine generator's colour (a multiply: darker, a little redder: pores, mottle, fine vessels)
FINE_FLOOR = 0.35        # the fine generator's least strength on plain skin (see decompose)
FINE_SCALES = (0.0012,)   # m: (old) its noise scale
PORE_SCALE, PORE_TINT = 0.00045, (0.8, 0.68, 0.64)   # the pore grain's noise scale (m) and its multiply colour
MOTTLE_SCALE, MOTTLE_TINT = 0.004, (0.95, 0.86, 0.86)
FILL_REACH = (0.8, 2.0, 5.0, 15.0, 40.0)   # mm: unmeasured texels take each layer from measured skin within these, nearest first
CAVITY = (0.85, 0.45, 1.3, 0.5)   # unmeasured texels with ambient occlusion under the first: + neutral (up to the third) and
                                  # haemoglobin (up to the fourth) at occlusion first - second: nostrils, the lip seam, the
                                  # socket's edge read dark and warm, not as the lightest skin

CAVITY_SPREAD = (2.5, 2.0, 0.97, 0.12)   # mm, gain, AO under (eased over the fourth): the cavity's darkness carried (a blur x gain, max with its own) over
                                  # the rest of the SAME unmeasured region where it isn't open skin: the nostril's inner alar
                                  # wall (AO 0.7-0.85, filled from the rim) stayed a pale crescent round the dark core (r17)

LIP_REACH = 1.0          # mm: the lips layer's support reaches this far past GNM's lips (a Gaussian's sigma)
LIP_FADE = 0.12          # ... and is full where that blur is over this (about 3 mm out), fading to nothing beyond
OPACITY = {"brows": 0.4, "periorbital": 0.4}   # (periorbital: a bag's shadow the head has no form for was taken as pigment: a
                          # heavy orange-brown under an older eye and on the closed lid; Stage 2's bags take the rest as form)  # a layer's own default: the brows' map is the SKIN-LEVEL darkness under our brow hairs (at full
                          # strength map + hairs doubled: heavier brows than the photograph's)

FRECKLE_REF = 0.2        # the fine melanin band's 3 mm mean (melanin x) that is a full freckle field
OCC_AO_POW = 1.0          # the baked occlusion: ambient occlusion ^ this ...
OCC_CAV = 0.35            # ... x (1 - this x the cavity term: concave skin under 0.2 mm of the local mean surface)
OCC_CAV_MM = 0.2
BLINK_POSE = 0.0095        # base.head.pose lid_upper of a full blink (cu.py's closed-eye renders)
BLINK_MOVE_MM = 1.5       # skin moving this far in it carries no crease line / occlusion
CREASE_MM = 0.35          # the crease cavity line's softness (a Gaussian's sigma over the slit's vertices)
CREASE_DEPTH = 0.62       # the crease line's darkening at full strength, per channel x the skin's shadow weights
CREASE_STRENGTH = 0.5     # the crease line's default opacity (occfit measures it per head)
OCC_FLOOR = 0.55          # the bake never darker than this (a game AO map's usual floor; under it: cracks)
OCC_STRENGTH = 1.0        # the occlusion layer's default opacity (eyecmp / occfit measure it per head)
OCC_WEIGHTS = (0.5, 0.8, 1.0)   # per channel share of the occlusion's darkening (R, G, B) without an atlas: warm
OCC_WARMTH = 0.6          # how much of the measured shadow hue the occlusion keeps (1 = all of it)
OCC_SOFT_MM = 1.2         # the bake's softness (a Gaussian's sigma, mm)
ORBIT_SHADE_CUT = 0.7      # share of the shade layer kept off the orbit (see decompose)
COVER_SOFT_MM = 6.0        # the coverage fade's softness (mm)
COVER_EDGE_MM = 12.0       # the stack's coverage fades over this inside the head island's atlas border
LIPS_VENOUS = 0.5         # the lips' blood colour: share of the venous axis (the rest arterial)
BASE_MAX = 0.9            # linear: the lightest skin's brightest channel at most this (see decompose)
LOW_PCT = 3.0            # the maps' zero: this percentile of each amount over the measured plain skin (the lightest skin there is)
Y = sp.Y


def axes(tone: dict | None) -> np.ndarray:
    """(3, 3): the optical-density colour of one unit of melanin (x 2 the tone's own), of haemoglobin (x 2 its blood)
    and of neutral darkness (1 unit = e-fold), at this tone: rows v_mel, v_hem, v_neu."""
    from . import skin
    t0 = sp._lin(np.asarray(skin.tone_rgb(tone), float))
    vm = -np.log(sp._lin(np.asarray(skin.tone_rgb(tone, melanin=2.0), float)) / t0)
    vh = -np.log(sp._lin(np.asarray(skin.tone_rgb(tone, blood=2.0), float)) / t0)
    return np.stack([vm, vh, np.ones(3)])


def venous_axis(tone: dict | None) -> np.ndarray:
    """The optical density of one unit of DEOXYGENATED blood (x 2 its blood at oxygenation 0.35): the periorbital
    layer's redness. Thin lid skin over venous blood reads pink-violet; with the arterial axis the lids came out orange."""
    from . import skin
    t0 = sp._lin(np.asarray(skin.tone_rgb(tone, oxygenation=0.35), float))
    return -np.log(sp._lin(np.asarray(skin.tone_rgb(tone, blood=2.0, oxygenation=0.35), float)) / t0)


def ica_check(D: np.ndarray, V: np.ndarray) -> dict:
    """The paper's ICA on optical densities D (n, 3) of plain skin, in the plane across (1, 1, 1) (shading leaves it):
    whiten, then the rotation with the largest |excess kurtosis|. Returns the angles (deg, in that plane) between
    the data's two independent axes and our melanin / haemoglobin axes, and the two model axes' own angle."""
    e = np.ones(3) / np.sqrt(3)
    B = np.linalg.svd(np.eye(3) - np.outer(e, e))[0][:, :2]          # an orthonormal basis of the plane
    X = (D - D.mean(0)) @ B
    C = np.cov(X.T)
    w, U = np.linalg.eigh(C)
    Wh = U @ np.diag(1 / np.sqrt(np.maximum(w, 1e-12))) @ U.T
    Z = X @ Wh
    best, ang = -1.0, 0.0
    for a in np.linspace(0, np.pi / 2, 91):
        c, s = np.cos(a), np.sin(a)
        y1, y2 = Z @ [c, s], Z @ [-s, c]
        k = abs(np.mean(y1 ** 4) - 3) + abs(np.mean(y2 ** 4) - 3)
        if k > best:
            best, ang = k, a
    c, s = np.cos(ang), np.sin(ang)
    A = np.linalg.inv(Wh) @ np.array([[c, -s], [s, c]])               # the mixing matrix's columns: the data's axes in the plane
    A = A / np.linalg.norm(A, axis=0)
    M = (V[:2] @ B)
    M = M / np.linalg.norm(M, axis=1, keepdims=True)
    def angle(u, v):
        return float(np.degrees(np.arccos(np.clip(abs(u @ v), 0, 1))))
    d = [[angle(A[:, i], M[j]) for j in range(2)] for i in range(2)]
    pair = min((d[0][0] + d[1][1], (0, 1)), (d[0][1] + d[1][0], (1, 0)))[1]
    return {"melanin_deg": round(d[pair.index(0)][0], 1), "haemoglobin_deg": round(d[pair.index(1)][1], 1),
            "model_axes_deg": round(angle(M[0], M[1]), 1), "kurtosis": round(float(best), 2)}


def _atlas_of(spec: dict):
    from PIL import Image
    from . import images
    pj = (spec.get("skin") or {}).get("projection") or {}
    if not pj.get("albedo") or not pj.get("confidence") or not pj.get("delight", True):
        raise ValueError("skin_layers: the model has no de-lit skin projection (skin_project first)")
    at = skin_project_atlas.atlas(spec["base"])
    alb = sp._lin(np.asarray(Image.open(images.id_path(pj["albedo"])).convert("RGB"), float) / 255.0)[at["ii"], at["jj"]]
    cf = np.asarray(Image.open(images.id_path(pj["confidence"])).convert("RGB"), float)[..., 0][at["ii"], at["jj"]] / 255.0
    return at, alb, cf, pj


PARTING_MM = 0.6        # mm: the parting line's softness (a Gaussian's sigma)
PARTING_MAX = 1.2        # e-folds: at most this dark (the stomion of a photographed closed mouth reads 0.6-1.0)
EDGE_MM = 0.4            # mm: the indications route's vermilion edge softness

EDITS = {"older": {"periorbital": 1.6, "shade": 1.7, "pigment": 1.15}, "blush": {"redness": 2.2}, "pale": {"redness": 0.4},
         "tan": {"pigment": 1.7}, "no_stubble": {"beard": 0.0}, "rested": {"periorbital": 0.5}, "tired": {"periorbital": 1.8}}


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("skin_layers_lips", "skin_layers_shade", "skin_layers_decompose", "skin_layers_stack")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
