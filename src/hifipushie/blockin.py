"""blockin.py: the ARTIST BLOCK-IN, the default way to model a person's head from reference pictures (faces6's
method, docs/notes/gnm_atlas.md "THE ARTIST BLOCK-IN METHOD"; Joe, 2026-10-10: "this method should be our default for
all modeling humans going forward").

The model is the artist: start from a base head of the right KIND (the person's body, GNM's sampler class mean for
the sex, an age-dependent GNM base share), look at it beside the pictures the way a sculptor does (eye-registered
photo | clay under the photo's own light | overlay | outline difference | squint), name the single biggest difference
in masses and planes, take ONE small whole-face step, keep it only if the whole face reads closer and the target
table didn't lose an item. Every step is a new model (revert = step again from an earlier one); one log per block-in.

  start(name, refs, ...)        the base of the right kind, with the references' fitted cameras
  look(name, out)               the six-column sheet per view (+ the target table: table / table_text)
  step(src, moves, out, ...)    free / held / data-backed gap directions, base keys, lid pose; logged
  lid_read(name) / lid_match    lid margins vs the iris (MRD-style, in iris radii), photo and render; lids by measure

Direction vocabulary (step moves, in population sd unless said):
  <macro>        humanmacro FREE: the population's conditional mean per +1 sd, the head's SIZE kept (masses,
                 proportions; try first)
  <macro>~       the raw population coupling, size included (faces6's free mode: lean cheeks came with a smaller head)
  <macro>!       humanmacro HELD: that macro alone, every other macro kept (one feature; costs more |c| per unit)
  nd:<gap>       filled vocabulary gaps (newdirs: coupled within sex): see gap_names()
  sex            +1 = GNM's sampler female class mean -> male class mean
  eth0..eth2     the sampler's ethnicity contrasts, per +1 population sd along each
  weight / dimorphism / gnm_base / head_scale    base keys, SET (head_scale = base.style.human.head_size: the head's
                 uniform size about the top of the neck, x the body's own head; 1 = the body's)
  lid_upper / lid_lower                          base.head.pose, SET, metres (-0.001 = that lid 1 mm up)

Where the code is (split by responsibility, as C414): this module holds the constants and data, identity, directions.
blockin_models: start, native_step, fork, references, the log, the cameras. blockin_expression: each picture's own
expression. blockin_steps: step, solve_step, expression_step. blockin_table: the target table. blockin_clay: the clay's
hair cap, eyes, brows, lip tint, iris. blockin_look: look and the lit render. blockin_focus: focus, note.
blockin_lid_measure: lids by measure.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from . import moved

DATA = Path(__file__).with_name("blockin_data.npz")
_C: dict = {}

# the five target groups (Joe: "Head and jaw shape, eye placement, nose size and shape, mouth size and placement"):
# likeness checklist items read on the photo and on the model through each picture's fitted camera
GROUPS = {
    "head shape": ["face_height", "face_index", "upper_third", "middle_third", "width_temple", "width_cheekbone",
                   "forehead_slope", "prof_forehead_slope"],
    "jaw and chin": ["width_jaw", "width_chin", "jaw_taper", "jaw_gonial", "jaw_angle_height", "chin_height",
                     "chin_shape", "chin_projection", "prof_chin"],
    "eye placement": ["pupil_distance", "intercanthal", "eye_width"],
    "nose": ["nose_length", "alar_width", "width_nose_base", "nose_projection", "prof_nose_length", "prof_bridge_bow",
             "tip_height", "nasolabial_angle"],
    "mouth": ["mouth_width", "mouth_line", "philtrum", "lower_third", "mouth_over_alar"],
}
# items whose reading is not the anatomy their name says: shown, not counted (brow_eye was dropped: it reads GNM's brow
# landmarks, not the person's hair brows)
FLAGGED = {"jaw_angle_height": "reads MediaPipe 172 / 397 (the detector's guess at the jaw contour), not the gonion",
           # (blockin2, Garrett: a held nose_width -1.0 moved the alae 3.4 mm and this row < 0.45 mm; MediaPipe's alar
           # points sit on the cheek past the alae on picture and clay alike)
           "alar_width": "reads MediaPipe's alar points, which sit on the cheek past the alae (blind to the alae)",
           "mouth_over_alar": "its alar width is MediaPipe's (on the cheek past the alae)"}

BODY_KEYS = ("weight", "neck_double", "neck_depth")
HEAD_KEYS = {"dimorphism": "dimorphism", "gnm_base": "gnm_base", "eye_size": "eyes", "eye_radius": "eye_radius",
             "gnm_base_rest": "gnm_base_rest"}
# head_scale: the one mesh's head is the BODY's head (base.head.scale is overwritten by the body's size); a uniform size
# change is base.style.human.head_size (humanstyle: the head scaled about the top of the neck, eyeballs with it)
POSE_KEYS = ("lid_upper", "lid_lower")
# LOCAL residuals (what GNM's identity can't draw: a confirmed capability gap), as faceslide's local sliders, SET, with
# the population sd ICT's scans give them beyond GNM's identity (faces5 regbasis2_nose's 8 leading modes projected on
# each field, blockin/radix.py): the radix width varies 0.09 units (~0.13 mm) past GNM: a real but near-invisible gap
# designed (hand-authored, not data-backed) soft-tissue / age ops a block-in step may SET: faceslide's age sliders (units:
# +1 = the op's unit amount, faceslide.UNITS: age_nasolabial 2 mm crease, cheek_hollow 4 mm ...) and headage's ops
# without a slider (base.head.shape: m, or a share for lips_thin)
SHAPE_MOVES = ("age_nasolabial", "age_prejowl", "age_cheek_flat", "age_lid_fold", "face_planes", "face_lean",
               "cheek_hollow", "eye_bag", "lip_bow", "lip_roll", "lips_thin")
LOCAL_SD = {"nose_radix_width": 0.09, "nose_tip_width": 0.18, "nose_dorsum_width": 0.12}
STRIP = ("sliders", "warp", "fold", "pose", "shape", "seed", "spread", "features", "expression", "habitual", "posed")
SQUINT_MM = 9.0
LIGHT = "sh"            # the sheets' light: "sh" (2nd-order spherical harmonics fitted on the skin) | "linear" (c0 + w.n, AO, shadow)
FILL = 0.45             # display fill: the clay's shadow side lifted to this share of the lit skin's median
HAIR_RGB = np.array([62.0, 46.0, 36.0])
BROWS_R = ([70, 63, 105, 66, 107], [46, 53, 52, 65, 55])
BROWS_L = ([300, 293, 334, 296, 336], [276, 283, 282, 295, 285])


# ---------------------------------------------------------------- data, identity, directions
def data() -> dict:
    """The precomputed table (blockin_data.npz, from GNM's semantic sampler via the audit's numpy decoder, and faces6
    newdirs.py): class means m_f / m_m / mean, eth_means (gender x ethnicity), eth_dirs / eth_sd, nd_* (gaps)."""
    if "d" not in _C:
        z = np.load(DATA)
        _C["d"] = {k: (z[k] if z[k].dtype.kind in "US" else np.asarray(z[k], float)) for k in z.files}
    return _C["d"]


def gap_names() -> list[str]:
    return [str(x) for x in data()["nd_names"]]


def default_gnm_base(age: float) -> float:
    """The GNM base share by age (coordinator, 2026-10-10): a young face reads right on half GNM's template (0.5: soft,
    young); an older one on MakeHuman's own aged head (0): linear between 25 and 50."""
    return float(np.clip(0.5 * (50.0 - float(age)) / 25.0, 0.0, 0.5))


def identity(spec: dict) -> np.ndarray:
    v = np.zeros(170)
    idn = (spec["base"]["head"].get("identity") or {})
    if isinstance(idn, dict):
        for k, x in idn.items():
            if k.startswith("head_"):
                v[int(k.split("_")[1])] = float(x)
    else:
        v[:len(idn)] = np.asarray(idn, float)[:170]
    return v


def ruler(a, b) -> list[dict]:
    """The millimetre RULER between two GNM identities (gnm_mm.gaps): a = the head being driven, b = the head it should
    become; each a model name, a spec or a (170,) identity. b - a for the 23 measures, largest (in population sd)
    first; each row's gap is the amount of the `mm:<measure>` move that closes it. GNM's own head (the identity comps
    alone: a model's gnm_base share / age ops are not in it)."""
    from . import gnm_mm, store

    def cof(x):
        if isinstance(x, str):
            x = store.load(x)
        return identity(x) if isinstance(x, dict) else np.asarray(x, float)
    sp = gnm_mm._space()
    V = [sp["T"] + np.tensordot(cof(x), sp["IB"], 1) for x in (a, b)]
    return gnm_mm.gaps(V[0], V[1])


def set_identity(spec: dict, c) -> None:
    """The head's 170 components written into the spec; GNM's OTHER identity components (eyes_000..002: limbus and
    cornea; teeth_000..079) are kept as they are (they are the same identity: one vector, GNM's 253)."""
    old = spec["base"]["head"].get("identity")
    keep = {k: v for k, v in old.items() if not k.startswith("head_")} if isinstance(old, dict) else {}
    spec["base"]["head"]["identity"] = {**{f"head_{i:03d}": round(float(x), 5) for i, x in enumerate(c)}, **keep}


def identity_extra(spec: dict) -> dict:
    """GNM's identity components beyond the head's 170 that the spec holds: {"eyes_000": .., "teeth_012": ..}
    (unset = 0 = GNM's mean eye and teeth)."""
    idn = spec["base"]["head"].get("identity")
    return {k: float(v) for k, v in idn.items() if not k.startswith("head_")} if isinstance(idn, dict) else {}


GNM_SET = ("eyes_", "teeth_")          # identity components a step may SET by name: "id:eyes_001": sd
GNM_EXPR_SET = ("pupils_", "tongue_")  # expression components a step may SET by name: "ex:pupils_000": value


def vocabulary() -> str:
    from . import humanmacro as hm
    return ("macros (free, size kept; append ! for held, ~ for the raw coupling incl. size): " + ", ".join(hm.NAMES) + "\ngaps: " + ", ".join("nd:" + n for n in gap_names())
            + "\nsex, eth0, eth1, eth2; base keys (set): weight; on a body-carried head only (REFUSED on a GNM-native "
            "head): dimorphism, gnm_base, head_scale, eye_size; attach (\"native\": a step of its own: the head switched "
            "to GNM-native, cameras carried); neck_mm (the neck's girth at its narrowest, real mm, the face's measures "
            "and size held); lids (set, m): "
            "lid_upper, lid_lower; eye_radius (set, m: OVERRIDES GNM's own eyeball, 0 drops it); GNM's other "
            "components (set): iris_mm (mm: the identity's limbus, eyes_000), id:eyes_001 (cornea), id:teeth_NNN, "
            "ex:pupils_000 (pupil), ex:tongue_NNN; DESIGNED age ops (set, not data): "
            + ", ".join("shape:" + k for k in SHAPE_MOVES) + "; local residuals (set): local:<faceslide slider>, e.g. "
            + ", ".join(f"local:{k} (sd {v})" for k, v in LOCAL_SD.items())
            + "; GNM region principal directions (coupled, size kept): pc:<GNM region><i>, e.g. pc:nose_region0 .. 7"
            + "; SCULPT a zone the GNM way (mm, its mean normal; macros held, locality): sculpt:<zone>, relief:<zone> "
            "(against its surround: - deepens a groove), options |hold=<zone>+..|free=<macro>+..|loc=<w>; zones: "
            "gnm_controls(zones=True); any atlas identity control raw: gnm:<control> (head_042, z:05, label:sex ...)"
            "; a MEASURE moved in mm, every other measure held in mm: mm:<measure> (pupils_apart, eyes_forward, "
            "chin_forward, forehead_forward, tip_forward, philtrum_length ...: gnm_mm.NAMES; the ORBIT: eyes_forward "
            "= the eye unit in its orbit, brow_ridge_forward, side_rim_forward, under_eye_forward, brow_hollow, "
            "brows_over_eyes: set before the eye step); HOODING (a hooded / deep-set eye: the brow and the drape under "
            "it come down over the lid; per unit ~+0.6 mm of fold overhang, brow -2.4 mm, eyes 1.8 mm deeper; not a "
            "local fold and wrong for an open lid with a platform): hooding; what to use for a "
            "difference you see: guide topic gnm_driving / gnm_controls(phrase=...)")


def _size_row() -> np.ndarray:
    """head_size's row of humanmacro's table in sd per component (the interocular distance: the head's absolute size)."""
    from . import humanmacro as hm
    t = hm.table()
    i = hm.NAMES.index("head_size")
    return t["A"][i] / t["sd"][i]


def keep_size(d: np.ndarray) -> np.ndarray:
    """d with the least change that keeps head_size (the interocular distance) where it was. The population couples
    size with everything (lean cheeks come with smaller heads: a free cheek_fullness -0.5 shrank Garrett's face 1-2 %
    in every width and length, and faces6's free rounds ended 8-10 % small); a sculptor sets size separately."""
    from . import humanmacro as hm
    a = _size_row()
    d = np.asarray(d, float).copy()
    d[:hm.K] -= a * (a @ d[:hm.K]) / (a @ a)
    return d


_PCS: dict = {}


def region_pcs(region: str, n: int = 8) -> np.ndarray:
    """GNM's OWN principal directions for one region (a GNM vertex group: nose_region, ...): the right singular vectors
    of the identity basis restricted to the region's vertices, i.e. the coefficient directions (unit |c| = 1 population
    sd, the coefficients being unit variance) that move that region most; the rest of the head moves as GNM couples it.
    Sign: + moves the region forward (out of the face) on average. (n, 170)."""
    if region not in _PCS:
        from . import base_identity
        g = base_identity._gnm_data()
        if region not in g["groups"]:
            raise ValueError(f"pc: no GNM region {region!r} (one of {', '.join(sorted(g['groups']))})")
        msk = np.asarray(g["groups"][region]) > 0.5
        B = np.asarray(g["vertex_identity_basis"], float)[:170, msk, :]    # (170, V_region, 3)
        _, S, Vt = np.linalg.svd(B.reshape(170, -1).T, full_matrices=False)
        fwd = B[:, :, 2].mean(1)                                           # GNM faces +Z
        Vt = Vt[:n] * np.sign(Vt[:n] @ fwd + 1e-30)[:, None]
        _PCS[region] = Vt
    return _PCS[region]


def direction(name: str) -> np.ndarray:
    """A move's change of the 170 head components per unit (see the module doc). Free macros, gaps and ethnicity keep
    the head's size (keep_size); `<macro>~` is the raw population coupling, size included (faces6's free mode)."""
    from . import humanmacro as hm
    d = np.zeros(170)
    if name.endswith("!") and name[:-1] in hm.NAMES:
        d[:hm.K] = hm.direction(name[:-1], held=True)
        return d
    if name.endswith("~") and name[:-1] in hm.NAMES:
        d[:hm.K] = hm.direction(name[:-1])
        return d
    if name in hm.NAMES:
        if name == "head_size":
            d[:hm.K] = hm.direction(name)
            return d
        t = hm.table()
        An = t["A"] / t["sd"][:, None]
        d[:hm.K] = np.linalg.pinv(An[[hm.NAMES.index(name), hm.NAMES.index("head_size")]])[:, 0]
        return d
    D = data()
    gn = gap_names()
    if name.startswith("nd:") and name[3:] in gn or name in gn:
        return keep_size(D["nd_dirs"][:, gn.index(name[3:] if name.startswith("nd:") else name)])
    if name in ("sex", "sex_gnm_dir"):
        d = np.asarray(D["m_m"] - D["m_f"], float)
        return d if name == "sex" else d / np.linalg.norm(d)   # (sex_gnm_dir: faces6's unit vector)
    if name.startswith(("eth_dir", "eth")) and name[-1].isdigit():
        k = int(name[-1])
        if k < D["eth_dirs"].shape[1]:
            return keep_size(np.asarray(D["eth_dirs"][:, k], float) * float(D["eth_sd"][k]))
    if name.startswith("pc:"):
        reg, k = name[3:].rstrip("0123456789"), name[3:][len(name[3:].rstrip("0123456789")):]
        return keep_size(region_pcs(reg)[int(k or 0)])
    if name.startswith(("sculpt:", "relief:")):   # (gnmcontrols) a zone moved the GNM way: per +1 mm, macros held
        from . import gnm_controls_latent, gnm_controls_sculpt
        return gnm_controls_sculpt.sculpt(**gnm_controls_sculpt.parse_sculpt(name))["dc"]
    if name.startswith("mm:"):    # (gnmdrive) a measure you can see moved 1 mm, every other measure held in mm
        from . import gnm_mm
        return gnm_mm.direction(name)
    if name == "hooding":         # (overhang) GNM's one overhang direction: the brow and drape down over a deeper-set eye
        from . import gnm_fold_design
        return gnm_fold_design.hood_direction(5)["dc"]
    if name.startswith("gnm:"):   # (gnmcontrols) any identity-space control of the atlas, raw (its own unit)
        from . import gnm_controls_latent, gnm_controls_sculpt
        d = gnm_controls_latent.identity_direction(name[4:])
        if d is None:
            raise ValueError(f"{name}: an expression / pose control, not an identity move (block_in_expression fits a "
                             "picture's expression)")
        return d
    raise ValueError(f"block-in: no direction {name!r}. Vocabulary:\n{vocabulary()}")


def _macro_read(c) -> dict:
    from . import humanmacro as hm
    return hm.read(np.asarray(c, float)[:hm.K])


CAM_STALE = (0.10, 0.30)     # cameras are STALE when the head's landmarks through them are this far off the pictures' own
# stored points: 10 % in size, or 0.3 of the face's spread in place (a head switched to native is 10-20 % larger)

NATIVE_REFUSE = {
    "head_scale": "a GNM-native head stands at GNM's own size (x base.head.size, by default the stature's allometry); the "
                  "style's head_size is not applied to it",
    "gnm_base": "a GNM-native head IS GNM's true base: there is no MakeHuman head under it to blend",
    "gnm_base_rest": "a GNM-native head IS GNM's true base: there is no MakeHuman head under it to blend",
    "dimorphism": "the dimorphism field is MakeHuman's sex difference laid on the body-carried head; a GNM-native head has none "
                  "(the sex is in the identity: the `sex` move)",
    "eye_size": "a GNM-native head has GNM's own eyeball at its real size (the lids are shaped on it); the iris is the "
                "identity's limbus (iris_mm)",
}

FIT_LENS_SD = 0.05      # block_in_start's camera fit: the lens at its prior (EXIF / lens_mm, else a 70 mm portrait), +- this
FIT_PITCH_SD = 5.0      # ... and the camera level with the head, +- this many degrees

# ---------------------------------------------------------------- per-picture expression
# GNM's identity is the relaxed neutral; a picture shows the person WITH an expression (a front picture with a slight smile:
# fuller lips, lifted corners, a cheek apple). Comparing the neutral clay with it leaks the smile into mouth / cheek
# identity steps. Each view may carry its own fitted expression (human_refs "expressions": one {GNM expression comp:
# value} per view, {} = neutral), applied in look / focus / the table / lid reads / camera refits, never to the model.
# Lower face only by default: with 6 eye-region comps per side a fit dropped the upper lid from 0.75 to 0.36 iris
# radii (the detector's calibrated lid points disagree with the iris-radius lid read that lid_read matches: the comps
# fought the lid pose); EYE_COMPS is the opt-in (a picture that clearly squints)
EXPR_COMPS = {"lower_face_region": 20}
EYE_COMPS = {"left_eye_region": 6, "right_eye_region": 6}
EXPR_SD = {"lower_face_region": 0.8, "left_eye_region": 0.5, "right_eye_region": 0.5}

# block_in_solve's defaults (solvereads, 2026-10-12; each decided by the validation in the notes' "## solvereads")
SOLVE_HOLD = None            # "auto": every measure no read looks at is held at the start head's value
SOLVE_EXPRESSION = False     # "view" | "shared": the pictures' expression as a nuisance (face_ruler_blockin.EXPR_SET)
SOLVE_JAW_LM = None          # detector landmarks added to the differential anchors (the jaw line: 3..13)
CAM_FIRST = 1                # cameras-first rounds of every block_in_solve call (the head held; "refit": 2, wider, and the new start)
SEESAW_COS = -0.2            # a step whose cosine with the last call's step is under this is halved
RELAX_KEEP = 0.85            # the cmax down-weighting comes down at most this share a call (it goes up at once)

BROW_RGB = np.array([70.0, 52.0, 40.0])

LIP_TINT = np.array([0.98, 0.74, 0.74])   # the clay's vermilion, x skin: presentation only (no reader sees it)

_IRIS: dict = {}

# Joe (2026-10-10): "having the reviewer focus more on each feature, then zoom back out after making each change".
# Per feature: the model's 68 landmarks that frame and register it, MediaPipe's matching points on the picture (the
# same anatomical points: feature-local registration, a 2D shift), MediaPipe contours drawn for the local outline
# difference, and the checklist stages whose rows are its table.
FEATURES = {
    "eyes": {"lm": list(range(17, 27)) + list(range(36, 48)), "pairs": [(36, 33), (39, 133), (42, 362), (45, 263)],
             "lines": [[33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7, 33],
                       [263, 466, 388, 387, 386, 385, 384, 398, 362, 382, 381, 380, 374, 373, 390, 249, 263],
                       [70, 63, 105, 66, 107], [300, 293, 334, 296, 336], [46, 53, 52, 65, 55], [276, 283, 282, 295, 285]],
             "stages": ("eyes", "brows"), "items": ("under_eye", "brow_ridge", "prof_brow_ridge"), "squint_mm": 3.0, "pad": 1.12},
    "nose": {"lm": list(range(27, 36)) + [39, 42], "pairs": [(27, 168), (30, 4), (31, 98), (33, 2), (35, 327)],
             "lines": [[168, 6, 197, 195, 5, 4], [64, 98, 97, 2, 326, 327, 294], [48, 115, 220, 45, 4, 275, 440, 344, 278]],
             "stages": ("nose",), "squint_mm": 3.0},
    "mouth": {"lm": list(range(48, 68)) + [33], "pairs": [(48, 61), (54, 291), (51, 0), (57, 17), (62, 13), (66, 14)],
              "lines": [[61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146, 61],
                        [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95, 78]],
              "stages": ("mouth",), "items": ("nasolabial_fold",), "squint_mm": 3.0},
    "chin_jaw": {"lm": list(range(3, 14)) + [57], "pairs": [(8, 152), (57, 17), (6, 176), (10, 400)],
                 "lines": [[132, 58, 172, 136, 150, 149, 176, 148, 152, 377, 400, 378, 379, 365, 397, 288, 361]],
                 "stages": ("chin_jaw",), "items": ("width_jaw", "width_chin", "jaw_taper", "jaw_gonial", "jaw_ramus",
                                                    "jaw_border", "corner_jaw", "jaw_neck_step"), "squint_mm": 5.0},
    "cheeks": {"lm": [1, 2, 3, 13, 14, 15, 31, 35, 36, 45, 48, 54], "pairs": [(36, 33), (45, 263), (31, 98), (35, 327)],
               "lines": [[127, 234, 93, 132, 58], [356, 454, 323, 361, 288]],
               "stages": (), "items": ("width_cheekbone", "corner_cheekbone", "cheek_hollow", "nasolabial_fold",
                                       "under_eye", "width_temple", "corner_temple"), "squint_mm": 6.0},
    "ears": {"lm": [0, 1, 2, 15, 16], "pairs": [], "lines": [], "stages": ("ears",), "squint_mm": 4.0},
}
RAKE = np.array([-0.85, -0.35, -0.25])   # camera frame: a grazing key from the picture's upper left (forms, not tone)

RAKE = RAKE / np.linalg.norm(RAKE)


# The modules this one was split into (C419). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("blockin_models", "blockin_expression", "blockin_steps", "blockin_table", "blockin_clay",
           "blockin_look", "blockin_focus", "blockin_lid_measure")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C427)
