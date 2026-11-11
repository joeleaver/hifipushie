"""The FACE RULER (faceruler, 2026-10-11): gnm_mm's 23 millimetre measures read from PICTURES of a head (front, 3/4,
profile; a photo, a dressed render or a clay render) through each picture's fitted camera, against the model.

Why: the driving test (docs/notes/gnm_atlas.md "## gnmdrive") showed that driving GNM by measures works (one measure =
one `mm:` move = the dose) and that Claude's eye cannot read the measures (sizes 30-50 % off, 7-12 mm differences
missed). The mesh ruler (gnm_mm.gaps) needs the target's MESH; a picture has none. This module reads the gaps off the
picture.

How a picture is read (edges and outlines, not detector landmarks):
  outline   the head's silhouette in each view as a sub-pixel curve. The model's own silhouette through the same
            camera is the reference: at ~1.5 mm steps along it, the picture's outline lies o mm outside (+) or inside
            (-) along the outline's normal. Profile: forehead, nasion, dorsum, tip, nose base, lips, chin, the line
            under the chin, throat, the vault and the back of the skull. Front: skull, cheek / jaw line, neck. 3/4: the
            far brow, cheekbone, cheek and jaw.
  iris      the iris disc's centre (a circle through the limbus' side edges), front and 3/4.
  lips      the vermilion's colour edge: corners, the upper red's top and the lower red's bottom at the midline (front
            and 3/4), their heights on the profile outline.
  brows     the brow's top over each eye (front).
Each observation moves in a KNOWN way with GNM's 170 identity components (a silhouette point moves with the surface
point that makes it, along the outline's normal: the envelope theorem, as fit.py). So the picture's offsets o = J dc +
noise, and the measures' gaps are g = Jm dc. `solve` gives the most likely dc under GNM's own prior (dc ~ N(0, tau^2))
and reads the 23 gaps off it, each with its posterior sd: a measure the pictures do not show comes back near 0 with an
sd near its population sd (NOT READ), never as a confident number. `span=True` fits the 23 `mm:` moves alone instead
(least squares: the outline compared as a curve in the measures' own vocabulary).

  gnm_head(c)                      a raw GNM head (170 identity comps) as the ruler's model
  clay(head, cam)                  its clay picture (hair cap, eyes, drawn brows, lip tint), as the driving test's
  observe(head, views)             the observations: picture vs model, with their Jacobians
  solve(obs, head)                 -> {"dc", "gaps": rows as gnm_mm.gaps + "err", "read"}
  read(head, views)                observe + solve; text(rows) prints the table with the `mm:` move per row
A view = {"img": PIL image, "cam": fitted camera (humanfit.project), "kind": "front" | "3q" | "profile",
"style": "clay" | "dressed" | "photo"}; "scale" / "origin" if the image is a crop of the camera's picture.
ERR: the validated reader error per measure (spikes/faceruler/validate.py; the notes' "## faceruler").

Where the code is (split by responsibility, C417): this module holds the constants and the model side (the GNM head,
the camera, the clay picture, projection). face_ruler_outline: outlines and colour features. face_ruler_jaw: the jaw's
lower edge. face_ruler_solve: observe / solve / read. face_ruler_orbit: the orbit's rows, the limbus in a turned view.
A block-in model against its reference pictures: face_ruler_blockin (the model's head, the expression prior),
face_ruler_features (iris, lids, shading, normals, lips), face_ruler_nose, face_ruler_camera (camera priors, lens,
distance, landmarks, anchors, dense) and face_ruler_compare (reference_views, compare, the overlay)."""
from __future__ import annotations

import numpy as np

STEP_MM = 1.5            # outline sample spacing
SIG = {"outline": 0.3, "iris": 0.12, "lips": 0.25, "brows": 0.2}     # mm: each observation's noise (validated)
SIG_LIMBUS = (0.25, 0.6)  # mm: a limbus read in a turned view, across (the depth's direction) / up
REACH_MM = 14.0          # an outline further than this from the model's is not matched
TAU = 1.0                # prior sd of each identity component of (target - model)
# The reader's own error per measure with the camera KNOWN (mm; sd of reader - mesh truth, 60 clay pairs incl. 20 from
# GNM's template: spikes/faceruler/validate.py "hair" variant) and the factor the posterior sd is short by when the
# camera was fitted (observed / posterior, median over measures). The table's +- is hypot(ERR_POST x posterior, ERR).
ERR = {"pupils_apart": 0.05, "eyes_forward": 0.19, "eyes_height": 0.3, "brows_over_eyes": 0.23, "forehead_forward": 0.6,
       "tip_forward": 0.18, "subnasale_forward": 0.15, "upper_lip_forward": 0.16, "lower_lip_forward": 0.12,
       "chin_forward": 0.49, "philtrum_length": 0.23, "chin_length": 0.57, "nose_length": 0.55, "cheekbone_width": 1.2,
       "jaw_width": 1.7, "chin_width": 1.1, "mouth_width": 0.29, "nose_width": 0.87, "skull_width": 1.76,
       "skull_top": 1.15, "skull_back": 0.87, "neck_width": 1.7, "under_chin": 0.57,
       # the orbit's rims (orbit, 2026-10-11): NOT validated on clay of raw GNM heads; half the block-in path's error
       # with the cameras known (spikes/orbit/osum.py known/all: 1.05 / 1.04 / 1.72 / 0.88)
       "brow_ridge_forward": 0.5, "side_rim_forward": 0.5, "under_eye_forward": 0.9, "brow_hollow": 0.45}
ERR_POST = 1.5
SUPER = 1                # mask supersampling
_C: dict = {}


# ---- the model side ---------------------------------------------------------------------------------------------------
def _gnm() -> dict:
    if "g" not in _C:
        from . import gnm_mm
        from . import base_identity
        g = base_identity._gnm_data()
        sp = gnm_mm._space()
        gr = sp["gr"]
        Q = np.asarray(g["quads"], int)

        def faces(mask):
            q = Q[mask[Q].all(1)]
            return np.r_[q[:, [0, 1, 2]], q[:, [0, 2, 3]]].astype(np.int64)
        F = faces(gr["skin"])
        # boundary vertices of the skin (the neck's cut edge, lid and lip openings): never an outline's maker
        e = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1)
        u, n = np.unique(e, axis=0, return_counts=True)
        bnd = np.zeros(len(sp["T"]), bool)
        bnd[u[n == 1].ravel()] = True
        _C["g"] = {"F": F, "bnd": bnd, "gr": gr, "sp": sp,
                   "eyes": [(faces(gr["scleras"]), np.array([236.0, 232.0, 226.0])),
                            (faces(gr["irises"] & ~gr["pupils"]), np.array([128.0, 112.0, 82.0])),
                            (faces(gr["pupils"]), np.array([22.0, 18.0, 16.0]))]}
    return _C["g"]


def _world(X):
    """GNM frame (x left, y up, z forward) -> world (Z up, facing -Y)."""
    return np.stack([X[..., 0], -X[..., 2], X[..., 1]], -1)


def gnm_head(c) -> dict:
    """A raw GNM head (identity c: 170 head comps, expression 0) as the ruler's model: world vertices V (m), the skin's
    triangles F, B (170, V, 3) = world metres per unit comp, L (68 landmarks), the measures and their Jacobian."""
    from . import gnm_mm
    g = _gnm()
    sp = g["sp"]
    c = np.asarray(c, float)
    Vg = sp["T"] + np.tensordot(c, sp["IB"], 1)
    if "Bw" not in _C:
        _C["Bw"] = _world(sp["IB"]).astype(np.float32)
    r = gnm_mm.readers(Vg)
    return {"c": c, "V": _world(Vg), "F": g["F"], "B": _C["Bw"], "WL": sp["WL"], "L": sp["WL"] @ _world(Vg),
            "bnd": g["bnd"], "gr": g["gr"], "eyes": g["eyes"], "Jm": gnm_mm.jacobian()[:len(gnm_mm.NAMES)],
            "measures": {n: float(r[n]) for n in gnm_mm.NAMES}, "kind": "gnm"}


def camera(kind: str = "front", centre=None, px: int = 880, half: float = 0.15, dist: float = 0.8) -> dict:
    """A test camera (the driving test's): yaw 0 / -35 / -90, the picture `px` square showing 2 x half metres."""
    yaw = {"front": 0.0, "3q": -35.0, "profile": -90.0}[kind] if isinstance(kind, str) else float(kind)
    if centre is None:      # GNM's template: between eyes and mouth, a little down (the whole head in the frame)
        sp = _gnm()["sp"]
        centre = (sp["WL"] @ _world(sp["T"]))[[36, 45, 48, 54]].mean(0) + np.array([0.0, 0.0, 0.01])
        if abs(yaw) > 60:   # a profile: the back of the skull in the frame too
            centre = centre + np.array([0.0, 0.06, 0.0])
    return {"r": [0.0, 0.0, 0.0], "t": [0.0, 0.0, dist], "f": px / 2 * dist / half, "size": [px, px],
            "centre": list(map(float, centre)), "yaw": yaw}


def _cap_colours(head):
    from . import likeness
    W, L, gr = head["V"], head["L"], head["gr"]
    zcut = 0.5 * (L[1, 2] + L[15, 2])
    w = (~gr["hockey_mask"]) * (~gr["ears"]) * np.clip((W[:, 2] - zcut) / 0.01, 0, 1)
    C = (1 - w)[:, None] * likeness.SKIN + w[:, None] * np.array([62.0, 46.0, 36.0])
    lip = gr["upper_lip"] | gr["lower_lip"]
    C[lip] = C[lip] * np.array([0.98, 0.78, 0.76])
    return C


def _mesh(head, cap=True):
    m = {"V": head["V"], "F": head["F"], "eyes": [(head["V"], f, col) for f, col in head["eyes"]], "L": head["L"]}
    if cap:
        m["C"] = _cap_colours(head)
    return m


def clay(head: dict, cam: dict, passes: bool = False, light=None):
    """The head's clay picture through cam (the camera's whole frame): hair cap, GNM's eyes, drawn brows, lip tint."""
    from . import likeness_render
    w, h = cam["size"]
    mesh = head["mesh"] if "mesh" in head else _mesh(head)
    out = likeness_render.render(mesh, cam, (0, 0, w, h), px=max(w, h), brows="mesh" not in head, light=light, passes=passes)
    return (out[0], out[2]) if passes else out[0]


def _cam_points(cam, X):
    """camera-frame coordinates and pixels of world points."""
    from . import humanfit
    Xc = (np.asarray(X, float) - np.asarray(cam["centre"], float)) @ humanfit._cam_rot(cam).T + np.asarray(cam["t"], float)
    w, h = cam["size"]
    return Xc, np.stack([cam["f"] * Xc[:, 0] / Xc[:, 2] + w / 2, cam["f"] * Xc[:, 1] / Xc[:, 2] + h / 2], 1)


def _proj_jac(cam, head, idx, w=None):
    """d(pixel) / d(comp) of the world point sum_j w_j V[idx_j] (or one vertex): (2, K) px per unit comp, + its
    mm / px."""
    from . import humanfit
    Rc = humanfit._cam_rot(cam)
    idx = np.atleast_1d(idx)
    w = np.full(len(idx), 1.0 / len(idx)) if w is None else np.asarray(w, float)
    X = (w[:, None] * head["V"][idx]).sum(0)
    Bx = np.tensordot(w, head["B"][:, idx, :].astype(np.float64), (0, 1))        # (K, 3) world
    Xc = (X - np.asarray(cam["centre"], float)) @ Rc.T + np.asarray(cam["t"], float)
    Bc = Bx @ Rc.T
    f = cam["f"]
    du = f * (Bc[:, 0] * Xc[2] - Xc[0] * Bc[:, 2]) / Xc[2] ** 2
    dv = f * (Bc[:, 1] * Xc[2] - Xc[1] * Bc[:, 2]) / Xc[2] ** 2
    return np.stack([du, dv]), float(Xc[2] / f * 1000.0)


PARSE_MODEL = "mediapipe"   # faceparse: the outline's parser (validated: spikes/refread/pval.py)
PARSE_SIG = 0.5             # mm: an outline read off the parser's mask (rms 0.2-0.5 on dressed renders, painted backdrop)
PLAIN_MIN = 0.75            # parse="auto": the plain-background reader is used when the backdrop is this plain ...
PLAIN_READS = 40            # ... and it finds this many outline samples in the view; else the parser

HAIR_EDGE = True            # reference_views(hair_edge=None) takes this
SIG_HAIR_EDGE = 0.8         # mm: a skin | hair boundary off the parser (its outline reads: 0.5; + strands lying on the skin)
HAIR_EDGE_MIN = 0.5         # mm: the read is ONE-SIDED: only a boundary this far OUTSIDE the model's outline pulls
OUTLINE_FEW = 20            # a view with fewer two-sided outline reads than this is said to have none worth the name

# ---- the jaw's edge against the neck (skin on skin: no silhouette, no parser class) -----------------------------------
JAW_REACH = 7.0             # mm: the picture's step is looked for this far either side of the model's contour
JAW_MIN = 0.035             # luminance (0..1): the least step from the lit jaw to the neck under it
SIG_JAW = 0.8               # mm: one jaw-under read (validated on dressed renders: spikes/solvereads/jval.py)
JAW_STEP = 2.0              # mm between reads along the contour

# ---- the jaw / chin in front of CLOTH (chinread): skin on cloth, inside the figure's mask ----------------------------------
CLOTH_EDGE = False          # default of view["chin"]["cloth"]
CLOTH_REACH = 9.0           # mm: the picture's skin / cloth edge is looked for this far either side of the model's contour
SIG_CLOTH = 0.6             # mm: one read (validated on dressed renders with a collar laid behind the jaw: spikes/chinread/clval.py)
CLOTH_STEP = 2.0            # mm between reads along the contour
CLOTH_DROP = 0.012          # m: the model's own surface (or nothing) lies at least this far behind the contour, 2.5 and 5 mm outside it

# ---- the jaw's lower edge as a SHADING ramp, picture against our own render under the picture's light (chinread) ---------
RAMP = False                # default of view["chin"]["ramp"]
RAMP_LM = (4, 12)           # the jaw line's landmarks the profiles cross: the jaw's body and the chin (the ramus is a silhouette)
RAMP_STEP = 3.0             # mm between profiles along the jaw line
RAMP_HALF = 13.0            # mm: a profile's half length across the jaw line
RAMP_REACH = 7.0            # mm: the largest shift looked for
RAMP_MIN = 0.10             # the least fall of the profile (share of its lit level) in the render AND in the picture
RAMP_NCC = 0.90             # the least correlation of the two profiles at the best shift
SIG_RAMP = 1.0              # mm: one profile's shift (validated: spikes/chinread/rval.py)


def _clay_crop(head, view):
    from . import likeness_render
    cam, s, o = view["cam"], float(view["scale"]), view.get("origin", (0.0, 0.0))
    w, h = view["img"].size
    box = (o[0], o[1], o[0] + w / s, o[1] + h / s)
    mesh = head["mesh"] if "mesh" in head else _mesh(head)
    out = likeness_render.render(mesh, cam, box, px=max(w, h), brows="mesh" not in head, passes=True)
    return out[0], out[2]


ORBIT_SAY = {"apex_behind_nasion": "the corneal apex behind the nasion (+ = deeper-set)",
             "brow_over_apex": "the brow ridge ahead of the cornea (+ = more overhang)",
             "apex_ahead_of_side_rim": "the cornea ahead of the orbit's side rim (+ = more eye shows from the side)",
             "apex_ahead_of_cheek": "the cornea ahead of the cheek under the eye (- = the cheek leads)",
             "brows_over_eyes": "the brow's height over the pupil",
             "brow_hollow": "the hollow under the brow (+ = sunken)"}


def _bil(A, x, y):
    H, W = A.shape
    x, y = np.clip(x, 0, W - 1.001), np.clip(y, 0, H - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return (A[y0, x0] * (1 - fx) * (1 - fy) + A[y0, x0 + 1] * fx * (1 - fy) + A[y0 + 1, x0] * (1 - fx) * fy + A[y0 + 1, x0 + 1] * fx * fy)


FAR_OPEN = 0.8           # the far eye is read only in views turned under ~37 deg: at 45 it is half behind the bridge and, on a head
                         # that is not the model's, read 2-4.6 mm off (5 dressed pairs) even with both arcs on the model's eyeball

LIMBUS_MIN = 0.03        # a limbus read under this edge contrast (luminance 0..1), or no better than another place, is dropped
# mm: in a side view (the disc under half open) the reader puts the edge this far FORWARD of the model's own limbus
# (spikes/orbit/oval.py limbus: 16 dressed profile pictures of 8 known heads, +0.40, sd 0.18; a 3/4's near eye: +0.09,
# sd 0.18, left alone). On a PHOTO the cornea's dome lies over that edge: unvalidated there, so the side read's sigma
# is 0.5 mm, not the renders' 0.2.
LIMBUS_SIDE_BIAS = 0.4
SIG_LIMBUS_SIDE = (0.5, 0.9)


# ---- a block-in model against its reference pictures ------------------------------------------------------------------
def _proj_jac_pt(cam, X, Bx):
    """as _proj_jac for a world point X with basis Bx (K, 3)."""
    from . import humanfit
    Rc = humanfit._cam_rot(cam)
    Xc = (np.asarray(X, float) - np.asarray(cam["centre"], float)) @ Rc.T + np.asarray(cam["t"], float)
    Bc = np.asarray(Bx, float) @ Rc.T
    f = cam["f"]
    du = f * (Bc[:, 0] * Xc[2] - Xc[0] * Bc[:, 2]) / Xc[2] ** 2
    dv = f * (Bc[:, 1] * Xc[2] - Xc[1] * Bc[:, 2]) / Xc[2] ** 2
    return np.stack([du, dv]), float(Xc[2] / f * 1000.0)


EXPR_SET = ("compress_face", "surprise", "squint", "lips_roll_in", "corners_down", "happy", "mouth_left", "mouth_right")
EXPR_SAY = {"compress_face": "frown / brows drawn down and together", "surprise": "brows raised (jaw dropped)", "squint": "squint",
            "lips_roll_in": "lips pressed", "corners_down": "mouth corners down", "happy": "smile (corners pulled)",
            "mouth_left": "mouth pulled to its left", "mouth_right": "mouth pulled to its right"}
# the reads an expression may explain: the INTERIOR ones. TRIED with the outlines in (solvereads): per-view expression then
# ate the profile (compress +0.9, surprise -0.9 on the 72 deg view: chin 10 mm back, the head 3.5 mm rms from the truth
# after three calls against 1.8 without the term): a silhouette cannot tell an expression from a shape.
EXPR_TYPES = ("landmark", "lid", "lip", "dense", "mp")
# (readmix, 2026-10-14) expression="lower": each picture's LOWER-FACE expression free (the mouth: a slight smile, lips pressed /
# rolled, corners down, mouth to one side), the upper face's classes PINNED at neutral (EXPR_PIN): solvereads' and groundtruth's
# per-view runs let squint / surprise / compress take the misfit ("finds 0.18 of 0.30 plus spurious surprise / squint");
# a side view's expression pinned too (its reads are the outline, which the expression never explains). MediaPipe's
# blendshape scores are NOT a gate: a slight smile (GNM's happy x0.3, dressed) scores mouthSmile 0.024, neutral 0.001
# (spikes/readmix/smilecal.py: on clay the score stays under 0.11 up to happy 0.3; one head scored 0 at 0.6)
EXPR_LOWER = ("happy", "lips_roll_in", "corners_down", "mouth_left", "mouth_right")
EXPR_PIN = 0.02

EXPR_SD = 0.35              # prior sd of one expression coefficient (1 = GNM's full prototype of that expression class)

SIG_LID = (0.2, 0.4, 0.4)   # mm: a lid margin at a column within 7 mm of the iris centre / beyond it / a canthus

NU_SD = 2.0                 # prior sd of an observation's own nuisance columns (log units: wide)
SIG_SHADE = 0.05            # log luminance: one shading sample (validated on clay pairs: spikes/reruns/shval.py)
SHADE_N = 350               # shading samples per view
SHADE_REGIONS = ("forehead_region", "left_temple_region", "right_temple_region", "left_zygomatic_region",
                 "right_zygomatic_region", "left_parotid_region", "right_parotid_region", "left_infraorbital_region",
                 "right_infraorbital_region", "left_cheek_region", "right_cheek_region", "chin_region")

SIG_NORMAL = 0.10           # radians: one learned-normal sample's tangent component (spikes/refread/nrmval.py)
NORMAL_N = 400              # normal samples per view
NORMAL_REGIONS = SHADE_REGIONS + ("nose_region",)

SIG_LIP = 0.3               # mm: a vermilion border vertex against the picture's traced border
# (readmix, 2026-10-14) THE LIPS' READS ON A PHOTOGRAPH ARE NOT THE MODEL'S BORDER ROWS: at the TRUE head (seven HSRD training
# subjects, the scan-fitted identity through the rig's cameras) the photograph's colour edge lies 0.5-2.4 mm ABOVE GNM's
# upper border row and 0.4-4.0 mm BELOW its lower one (most at the middle), and MediaPipe's border points and the
# differential anchors (picture minus our render) agree: our render's lips look thinner to every reader than the same
# lips photographed. Uncorrected, the solve makes lips 3-8 mm too tall. Each read's mean vertical offset (per border
# position / point) is taken out of a PHOTO's lip reads (lip_photo_bias.json; spikes/readmix/lipbias.py); per-person
# scatter remains (sd 0.5-2.5 mm). The colour edge itself belongs to the PAINT, placed from the picture.
LIP_PHOTO_BIAS = False      # OFF (2026-10-14, the coordinator's decision): on three held-out HSRD heads it took the lip heights' error
#                             4.4 -> 1.8 mm against the fit's vertices, but the scan's SURFACE did not confirm it (lips 1.06 / 0.69 /
#                             1.60 -> 1.03 / 0.80 / 1.76 mm; one chin 1.29 -> 2.00): an option, docs/notes/readmix.md "## TALL LIPS"

# ---- the NOSE's own read: the nostril openings (readmix, 2026-10-13) -----------------------------------------------------
# On two scanned heads the solved nose stayed 2-5 mm too WIDE with the front camera at its true distance: nothing read it (the
# class mean's nose is that much wider, and neither detector's nose points follow a narrow nose: MediaPipe's alar width +2.4
# / +5.5 mm there). The picture itself shows the nostril openings: dark, high contrast. Each opening's LATERAL and MEDIAL end
# along the line through both openings is read against the model's nostril RIM (GNM's exterior skin where it turns into the
# nostril: fixed vertices) through the view's camera.
NOSTRIL = False             # reference_views(nostrils=None) takes this. OFF: validated on ONE scanned head's front picture only (the
#                             other scanned head's tip hides its nostrils, our own renders have no dark openings): there the
#                             picture's opening ends 1.1 mm OUTSIDE the true rim on each side and 2.1 mm past it toward the midline
#                             (the half-depth contour is larger than GNM's rim loop): a bias known from one head is not a calibration
NOSTRIL_TURN = 30.0         # degrees: read in views turned less than this
SIG_NOSTRIL = (0.8, 1.2)    # mm: an opening's lateral end / its medial end (validated on scanned heads: spikes/readmix/nostril_eval.py)
NOSTRIL_ROI = 7.0           # mm round the model's rims that the picture is searched in
NOSTRIL_AREA = (3.0, 160.0) # mm2: an opening smaller / larger than this is not one (hidden under the tip; a moustache's shadow)
NOSTRIL_BIAS = (0.0, 0.0)   # mm: the picture's dark opening against the rim at the TRUE head (lateral, medial), taken out

# ---- the NOSE's width from its WING's edge (readmix, 2026-10-14) ----------------------------------------------------------
# From the front the ala is drawn IN FRONT of the cheek: its outer edge is an occluding contour of the model (a vertex with a
# face turned to the camera and one turned away, in GNM's nose region) and in a photograph a dark line: the alar-facial
# groove's shadow, or the step from the lit wing to the cheek behind it. Per contour vertex the picture's luminance along
# the camera's horizontal, outward, and the read is where the chosen FEATURE lies against the model's contour, minus its
# BIAS measured at the truth on TRAIN subjects only (spikes/readmix/alar_eval.py); scored on the held-out ones.
ALAR = True                 # reference_views(alar=None) takes this. ON (2026-10-14): on the three HELD-OUT HSRD subjects (4 calls, the
#                             told-lens pooled start) the alar width error +1.7 / +1.1 / +1.7 -> +0.4 / +0.7 / +0.4 mm, nose base
#                             +0.6 / +1.4 / +0.6 -> -0.9 / +0.9 / -0.8, lower face 2.74 / 3.49 / 3.61 -> 2.93 / 3.11 / 3.03 mm
ALAR_TURN = 25.0            # degrees: read in views turned less than this
ALAR_WIN = (-2.5, 4.5)      # mm along the outward horizontal, from the model's contour, searched
ALAR_FEATURE = "edge"       # "valley" = the darkest point (the groove's shadow) | "edge" = the steepest fall going outward
ALAR_BIAS = 0.3             # mm: the feature against the TRUE contour (+ = outside it): the steepest fall lies 0.29 mm
#                             outside it on five TRAIN subjects (16 sides, sd 1.46); on the three HELD-OUT ones +0.15 (6 sides, sd 0.76)
SIG_ALAR = 1.0              # mm: one side's read (its contour vertices count as one)
ALAR_MIN = 0.04             # the least depth of the valley / step (luminance 0..1, against the profile's ends)

# A FITTED camera: mm of shift (x, y), % of scale, degrees of roll left free per view. Measured (spikes/faceruler/
# arms2.py): a camera fitted by laying the MODEL's landmarks on the picture's is off by 1.9 mm / 1.7 mm / 4.8 % / 1.1 deg
# rms when the model is a regional transplant away from the person (the scale up to 9 %: a broader jaw reads as "closer").
CAM_SD = (2.0, 2.0, 5.0, 1.2)
# The reader's error on a BLOCK-IN model (the one mesh) through real fitted cameras, hair masked, camera free: sd of
# reader - truth on dressed EEVEE pictures of 8 sampled GNM heads on the same body (spikes/faceruler/dval.py; size-free
# gaps). compare() never shows less. neck_width (the body's neck), nose_width, lower_lip_forward and mouth_width are
# NOT readable there (error >= half their population sd).
MODEL_ERR = {"pupils_apart": 0.83, "eyes_forward": 2.79, "eyes_height": 1.13, "brows_over_eyes": 1.13,
             "forehead_forward": 1.18, "tip_forward": 0.59, "subnasale_forward": 1.99, "upper_lip_forward": 0.42,
             "lower_lip_forward": 1.27, "chin_forward": 0.64, "philtrum_length": 0.77, "chin_length": 1.73,
             "nose_length": 0.86, "cheekbone_width": 3.06, "jaw_width": 5.0, "chin_width": 2.87, "mouth_width": 3.34,
             "nose_width": 5.2, "skull_width": 2.99, "skull_top": 2.29, "skull_back": 2.45, "neck_width": 13.5,
             "under_chin": 0.91,
             # (orbit: spikes/orbit/oval.py + osum.py: 8 far pairs, dressed, hair masked, each camera put OFF by a random
             # yaw (profile 6, 3/4 4 deg sd) / shift / scale and left free: a fitted camera. eyes_forward itself: 2.7-3.6
             # there (0.6-0.8 with the cameras KNOWN, 2.2 with true cameras left free): the profile camera's yaw, which
             # the outline pins only to ~2.5-3.3 deg, is what limits eye depth on a photo, not the limbus read (0.1 mm).)
             "brow_ridge_forward": 1.5, "side_rim_forward": 3.5, "under_eye_forward": 2.8, "brow_hollow": 1.1}
PHOTO_CAM_SD = (1.5, 1.5, 2.5, 0.8)   # a block-in's cameras were fitted to THIS model and are anchored by its landmarks
# with the cameras' YAW and PITCH left free too (degrees; the last two): a profile's yaw is the least known thing in a
# block-in (few landmarks, all near the midline: Tess's was refitted by 30 degrees once), a 3/4's is held by both eyes
PHOTO_CAM_SD6 = {"front": (1.5, 1.5, 2.5, 0.8, 2.0, 2.0), "3q": (1.5, 1.5, 2.5, 0.8, 4.0, 2.0),
                 "profile": (1.5, 1.5, 2.5, 0.8, 6.0, 2.0)}
# (solvecams, 2026-10-13; docs/notes/solvecams.md) THE CAMERAS' PRIOR, seven numbers a view: shift mm (x, y), scale %,
# roll, YAW, PITCH deg, DISTANCE (log x 100 ~ %): the sd of each camera's WHOLE move since the block-in's start. Measured on
# known heads: block_in_start's fit is off by 2.2 deg yaw, 3.5 deg pitch (the front 4.6, worst 8.7), 3.5 % scale, 1-4 mm
# rms and has no idea of the distance; at the right head the reads hold every rotation to 0.2-0.6 deg (a side view 1-2).
# 5 deg of FRONT pitch = 7 mm of jaw width, half the distance = +6 mm of jaw and +9 of cheekbone, so these are wide: the
# reads decide. block_in_solve(cameras="free") = these; "trust" = a third of them (cameras measured or carried from an
# accepted head); never a clip (read()).
PHOTO_CAM_SD7 = {"front": (3.0, 3.0, 4.0, 1.5, 3.0, 6.0, 15.0), "3q": (3.0, 3.0, 4.0, 1.5, 8.0, 4.0, 12.0),
                 "profile": (3.0, 3.0, 4.0, 1.5, 10.0, 4.0, 8.0)}
# DISTANCE: outlines and anchors read it weakly (at the right head, reads alone: front 20 %, 3/4 13 %, side 63 %) and on a
# head still far from the person its column soaks up shape (a true camera drifted +28 %, a +100 % start went to +129 %):
# held near the start's lens (lens_mm / EXIF / the 70 mm portrait prior) unless a read that sees perspective is in (the
# dense landmarks: 5-9 %; then PHOTO_CAM_DIST_DENSE)
PHOTO_CAM_DIST_DENSE = 40.0
# A KNOWN LENS (readmix, 2026-10-13): a view that carries lens_mm (the brief, the file's EXIF FocalLengthIn35mmFilm) has its
# distance held this tightly (log x 100 ~ %) round the start's, WITH the dense landmarks too: familynative's phone
# pictures went to 0.65 x / 1.6 x / 3 x their EXIF distance under PHOTO_CAM_DIST_DENSE, worth 3-4 mm of jaw width
PHOTO_CAM_DIST_LENS = 7.0
MP_DROPS_ANCHORS = False    # see reference_views
LENS_PINS = False           # True: a view with a known lens has its focal length PINNED and its scale freedom moves the camera's
#                             distance (cam_moved(lens=True)): distance = focal x head size / pixels. BUILT, and OFF: on a scanned head
#                             (h112, the rig's lens told) four chains with it ended at face 2.45-2.67 / lower face 2.9-3.6 mm against
#                             2.02-2.15 / 2.3-2.5 for three without (the lens held by PHOTO_CAM_DIST_LENS's prior instead, the front
#                             camera's distance within 1 %): cause not found (docs/notes/readmix.md "## Distance")
CLOSE_M = 0.6               # a front picture taken nearer than this: strong perspective, the distance must be KNOWN

DIST_RANGE = (0.5, 2.0)     # a distance that is NOT known is taken to lie between these multiples of where the camera stands
DIST_MEASURES = {"cheekbone": ("cheekbone_width", "skull_width"), "jaw": ("jaw_width", "gonial_width")}

CAM_STEP = (3.0, 3.0, 4.0, 2.0, 5.0, 4.0, 15.0)      # the most one Gauss-Newton round moves a camera (same units)
LM_SIG = 1.5                          # mm: a clicked / detected landmark as an anchor (biased, never the measure)

ADAPT_MIN = 8                         # solve(adapt=True): groups (type, view) of at least this many reads get their own scale
CAM_LOOSE = 2.0                       # read(cam_first=n): the cameras-first rounds' freedom, x the cameras' sd
CHIN_LM = (7, 8, 9)                   # differential anchors always include the chin's three
NECK_HOLD = True                      # an anthropometric PRIOR on the neck's girth (ANSUR's mean and sd for the sex and stature) on a GNM-native head (solve_report.neck_row)
SIZE_HOLD = True                      # the face's SIZE is held at the block-in's start head's (solve_report.size_row): no picture reads
# it (every camera's scale and distance are free: a bigger head further away is the same image), so left free it is whatever the prior's
# correlations make of the shape reads (GNM's head_000 is width AND size: Tess's narrow face came out 3 % small, tess_a1 3.4 % large, the
# benchmark's heads 1-8 % large). Joe, 2026-10-12: "I'd trust the model more". compare(chin={"size": False}) / block_in_solve(size="free") releases it
CHIN_TIE = False                      # compare(chin={"tie": ..}): the unread jaw / chin widths tied to their expectation (solve_report.tie_rows)
TIE_OPEN = (35.0, 60.0)               # a view whose fitted camera is turned this much shows the far jaw on its silhouette: no tie on the jaw
CHIN_LM_AXES = "auto"                 # ... "xy" | "y" | "x" | "none" | "auto" = left out when the set has a SIDE view (its outline reads
#   the chin's height and projection to 0.3 mm; the detector's chin on a dressed picture stands 2.6 +-1.1 mm higher and
#   2.4 mm aside of its chin on our clay render of the SAME head (eyes: 0.1) and, against that outline, left known heads'
#   chins 3.9 mm short on average and their lower faces worse than the class mean they started from: the notes' "## chinread"), kept when it has none (nothing else reads the chin)
SIDE_MIN = 60.0                       # degrees: a view whose fitted camera is turned at least this much is a side view
LM_SIG_SCALE = 1.0                    # differential anchors: their sigma x this (their errors are CORRELATED: a bias, not scatter)
LM_STRETCH = False                    # differential anchors: a free stretch (x, y apart) of the detector's face per view
LM_STRETCH_UNIT = 0.05                # its nuisance column's unit: 5 % (prior sd NU_SD = 2 units: wide)
SIG_IRIS_3Q = 0.5                     # mm: a 3/4 view's iris centre, detector on picture - detector on render (gaze differs)
LM_SIG_DIFF = 1.0                    # mm: a DIFFERENTIAL anchor (the same detector on picture and render), + its pixel floor
LM_PX = 0.6                           # picture px: the detector's own scatter on a small face (Garrett's: 1.2 mm / px)
# (readmix, from groundtruth's Part 2) THE DIFFERENTIAL ANCHORS DO NOT CANCEL AT THE NOSE: at the TRUE head the detector on a
# PHOTOGRAPH draws the nose base (landmarks 31-35) +1.7 / +1.6 mm wider than on our render of the same head (two scanned heads;
# -0.1 on a render of a scan): our renders of a nose do not look to it like a photographed one. That much width is taken out
# of the nose-base anchors of a view styled "photo", in proportion to each point's place across the base (0 = left as it was)
LM_NOSE_WIDE = 0.0          # OFF (2026-10-14): scored on the three HELD-OUT HSRD subjects it was not calibrated on, the 1.65 mm
#                             took the nose base from +0.6 / +1.4 / +0.6 mm to -0.9 / -0.8 / -1.5 (mean |error| 0.87 -> 1.07): the
#                             wide nose of the two calibration heads is not a constant of the detector

# DENSE LANDMARKS (denselm, 2026-10-12; docs/notes/fitter_whitepaper.md "## denselm"): our own detector's ~600 points, each a
# GNM skin vertex's picture position with the network's own sigma. ABSOLUTE (no render of the model): the network is
# trained on our renders, so its landmark IS the vertex's projection. OFF by default (a pilot network).
DENSE = False                         # reference_views(dense=None) takes this
DENSE_SIG_SCALE = 1.0                 # x the network's sigma (2.0 until solvecams: the region floors and DENSE_NEFF do that job now)
DENSE_SIG_FLOOR = 0.5                 # mm: never surer than this
DENSE_MAX_MM = 3.0                    # a landmark the network is less sure of than this (mm) is left out (hidden, under hair)
# (solvecams, 2026-10-13) THE NETWORK'S MEASURED ERROR at known heads through true cameras (6 heads, 3 dressings, one with
# hair; spikes/solvecams/dres.py): per-axis mm by view kind and region = the FLOOR of a dense read's sigma there. Its own
# sigma said 1.5-2.5 mm everywhere; at the truth it is 0.7 mm on a front view's lids and 4 on a true profile's, and the
# solve fitted it to 1.6-1.9 mm rms where its error is 2.3-3.0: it fitted the network's biases (every width +4-6 mm).
# EARS and SCALP / NECK are out (4-9 and 5-12 mm; under hair worse).
# (readmix, 2026-10-13) ... AND ON PHOTOGRAPHS OF SCANNED HEADS (two HSRD-100 heads through the rig's cameras against the
# scan-fitted GNM; spikes/readmix/gmix.py, the error left after the network's own 2D similarity per view): 1.4-2.8 mm
# everywhere, lids 2.1 where the renders said 0.5, chin 2.3 against 1.1, lips 1.8 against 0.8: trained on our renders only,
# it is a coarse read on a real face. Each floor = the larger of the two measurements.
DENSE_REGION_SIG = {"front": {"lids": 2.1, "eyes": 2.3, "lips": 1.8, "brows": 2.1, "mouth": 1.4, "chin": 2.3, "nose": 1.5, "cheeks": 2.4, "forehead": 2.8},
                    "3q": {"lids": 2.4, "eyes": 2.2, "lips": 1.7, "brows": 1.9, "mouth": 1.7, "chin": 1.7, "nose": 1.8, "cheeks": 2.6, "forehead": 2.4},
                    "profile": {"lids": 2.9, "eyes": 2.6, "lips": 1.3, "brows": 2.5, "mouth": 1.8, "chin": 2.9, "nose": 2.0, "cheeks": 3.2, "forehead": 2.6}}
DENSE_REGIONS = tuple(DENSE_REGION_SIG["front"])     # None = every skin landmark; or a tuple of denselm regions
DENSE_IDENTITY = "all"                # "all" | "inner" (DENSE_INNER's regions only) | "none": the dense reads that may move identity
DENSE_INNER = ("lids", "eyes", "lips", "brows", "mouth", "nose")
DENSE_NEFF = 80                       # a view's dense reads count as this many independent ones (one crop, one network: neighbours err
#                                       together): every sigma x sqrt(n / DENSE_NEFF)

VIEW_DOUBT = 15.0                     # degrees between a view's stated yaw and its fitted camera's turn: say so
KIND_SAY = {"front": "a front view", "3q": "a three-quarter view", "profile": "a profile"}

DISAGREE = 2.0        # a read group left at more than this many of its own sigmas (rms) after the solve is named


# The modules this one was split into (C417). Its constants stay HERE (C421): tests/test_constants_address.py.
MODULES = ("face_ruler_outline", "face_ruler_jaw", "face_ruler_solve", "face_ruler_orbit", "face_ruler_blockin",
           "face_ruler_features", "face_ruler_nose", "face_ruler_camera", "face_ruler_compare")
