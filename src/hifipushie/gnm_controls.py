"""GNM's controls, catalogued: every way to move Google's GNM head, what each does WHERE (named feature zones), how
much a viewer sees it (face-ID), what it drags along (our macros), and which block-in move it is closest to.
("gnmcontrols", 2026-10-10; Joe: "until we learn how to use ALL the GNM controls intentfully, more references feel like
they'll be of limited value". Notes: docs/notes/gnm_atlas.md "## gnmcontrols".)

Families (control names as `field` / `query` take them):
  identity        head_000 .. head_169 (unit: 1 population sd), eyes_000 .. 002 (limbus / cornea), teeth_000 .. 079
  region_pc       pc:<GNM region><0..7>: GNM's own principal directions per region (= the block-in's pc: moves, size kept)
  expr_eyes       both_eye_region_000 .. 099 (GNM's left / right eye comps are mirrored copies: one side = half this)
  expr_lower      lower_face_region_000 .. 149 (jaw opening, lips, cheeks, nose wrinkle)
  expr_tongue     tongue_mean, tongue_000 .. 030;  pupil (dilation)
  joints          joint:neck_x|y|z, joint:head_x|y|z, joint:eyes_x|y (unit 10 deg; pose, not shape: never ranked)
  sampler_latent  z:00 .. 63 (the identity CVAE's latent dims at its female / white class), zpc:00 .. 15 (its principal
                  latent directions there), linearised (unit: 1 latent sd)
  sampler_label   label:sex (female -> male, half per unit), label:<middle_eastern | asian | white | black>
  sampler_expr    xclass:<20 classes>: the expression CVAE's class prototypes (decoded at z = 0; unit = the prototype)
  blockin         our block-in moves: humanmacro's macros (free, size kept), nd:<gap>, sex (half the class-mean
                  difference), eth0 .. 2
Per control, in gnm_controls.npz (built by build(), from the scratch study's perception runs):
  zone stats per unit: tot (rms |d|), nrm (rms of d . n), sgn (mean d . n, + = out of the face), trans (|mean d|: the
  zone carried rigidly), deform (rms |d - mean d|: the zone's own shape change); face rms / max; the macros it moves
  (sd per unit); the perceptual effect (1 - cos of the face-ID embeddings between -1 and +1: faces4 perc.py's scale,
  SFace / ArcFace); the nearest block-in moves (cosine in the 170-d identity space); its atlas sheet.
query("alar crease") ranks the controls that move a zone: by local shape change (max of nrm, deform) per unit of prior
cost x its specificity (local / face rms, capped at 4), shape families only (no joints).
sculpt(zone) is the least-cost identity change moving a zone 1 mm with every macro held and a locality penalty: the
block-in's "sculpt:<zone>" move (Garrett's narrow bridge, made without a designed local)."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

DATA = Path(__file__).with_name("gnm_controls.npz")
MM = 1000.0
_C: dict = {}

FAMILIES = ("identity", "region_pc", "expr_eyes", "expr_lower", "expr_tongue", "joints", "sampler_latent",
            "sampler_label", "sampler_expr", "blockin")
SHAPE_FAMILIES = tuple(f for f in FAMILIES if f != "joints")
STATS = ("tot", "nrm", "sgn", "trans", "deform", "relief")

# zone: (what it is, words a query may use)
ZONES = {
    "forehead": ("the forehead (GNM forehead_region)", "forehead brow-bone frontal"),
    "glabella": ("between the brows (middle_brow_region)", "glabella between-brows frown"),
    "brows": ("the brow ridges under the brows (brow regions)", "brow brows eyebrow eyebrows brow-ridge supraorbital"),
    "temples": ("the temples", "temple temples"),
    "upper_lid": ("the upper lid skin, lash line to crease (3.5-9.5 mm above the eye centre)", "upper-lid eyelid lid lids upper-eyelid"),
    "lid_fold": ("the upper lid's fold / crease zone (8-13.5 mm above the eye centre)", "crease fold lid-crease eye-crease upper-lid-crease hood hooded supratarsal double-eyelid"),
    "lower_lid": ("the lower lid", "lower-lid under-eye lower-eyelid"),
    "upper_orbital_rim": ("the orbital rim under the brow", "orbital-rim orbit socket brow-bone"),
    "lower_orbital_rim": ("the lower orbital rim", "lower-orbit lower-orbital-rim infraorbital-rim"),
    "tear_trough": ("the tear trough (lower medial orbit)", "tear-trough under-eye-hollow nasojugal"),
    "inner_canthi": ("the inner eye corners", "inner-canthus canthus canthi eye-corner inner-corner epicanthal"),
    "outer_canthi": ("the outer eye corners", "outer-canthus outer-corner canthal-tilt crow"),
    "radix": ("the radix (bridge between the eyes, at the nasion)", "radix nasion bridge-root sellion"),
    "dorsum": ("the nose's dorsum (ridge line, radix to tip)", "dorsum bridge ridge nose-bridge hump"),
    "bridge_walls": ("the nose's side walls (3.5-11 mm off the midline, upper nose)", "bridge-walls side-walls sidewalls nasal-walls walls narrow-bridge bridge-width"),
    "nose_tip": ("the nose tip (pronasale)", "tip nose-tip pronasale lobule"),
    "columella": ("the columella", "columella"),
    "nostrils": ("the nostrils and sills (down-facing base)", "nostril nostrils nares sill"),
    "alae": ("the alae (nose wings)", "ala alae alar wing wings nose-width"),
    "alar_crease": ("the alar crease (the ala's groove into the cheek)", "alar-crease alar-groove alar-facial alar-base"),
    "philtrum": ("the philtrum", "philtrum philtral"),
    "upper_lip_skin": ("the upper lip's skin (nose to vermilion)", "upper-lip-skin cutaneous-lip"),
    "vermilion_border_upper": ("the upper lip's vermilion border (the white roll line)", "lip-border vermilion-border border upper-border lip-line white-roll"),
    "cupids_bow": ("the cupid's bow (upper border, middle)", "cupid cupids-bow bow"),
    "vermilion_border_lower": ("the lower lip's vermilion border", "lip-border vermilion-border border lower-border lip-line"),
    "upper_vermilion": ("the upper lip's red", "upper-lip upper-vermilion lips lip"),
    "lower_vermilion": ("the lower lip's red", "lower-lip lower-vermilion lips lip pout"),
    "mouth_corners": ("the mouth corners (commissures)", "corner corners commissure commissures mouth-corner"),
    "mentolabial_sulcus": ("the groove under the lower lip", "mentolabial sulcus labiomental under-lip"),
    "chin": ("the chin (chin_region)", "chin mental"),
    "pogonion": ("the chin's most forward point", "pogonion chin-point chin-projection"),
    "under_chin": ("under the chin (submental)", "under-chin submental double-chin"),
    "jawline": ("the jaw line (landmarks 2-6, 10-14)", "jawline jaw-line jaw mandible"),
    "jaw_angle": ("the jaw's angle (gonion)", "gonion jaw-angle angle ramus"),
    "jowls": ("the jowls (over the jaw beside the chin)", "jowl jowls prejowl"),
    "marionette": ("the marionette lines (down and out from the mouth corners)", "marionette"),
    "nasolabial": ("the nasolabial fold line (ala to beside the mouth corner)", "nasolabial smile-line laugh-line nasolabial-fold"),
    "malar": ("the cheekbones (zygomatic regions)", "cheekbone cheekbones malar zygomatic zygoma"),
    "cheeks": ("the cheeks (cheek regions)", "cheek cheeks buccal hollow cheek-hollow"),
    "infraorbital": ("below the eyes (infraorbital regions)", "infraorbital midface"),
    "parotid": ("the face's sides in front of the ears (parotid regions)", "parotid side-face masseter"),
    "ears": ("the ears", "ear ears"),
    "cranium": ("the skull outside the face", "cranium skull scalp head-shape"),
    "neck": ("the neck", "neck"),
    "face": ("the face (GNM hockey_mask): the normaliser", "face"),
    "iris": ("the irises", "iris irises limbus"),
    "pupil": ("the pupils", "pupil pupils"),
    "sclera": ("the eyeballs' whites", "sclera eyeball eyeballs cornea"),
    "teeth_upper": ("the upper teeth and gums", "teeth tooth upper-teeth incisor incisors gums"),
    "teeth_lower": ("the lower teeth and gums", "teeth tooth lower-teeth gums"),
    "tongue": ("the tongue", "tongue"),
}


# ---------------------------------------------------------------- geometry

def gnm() -> dict:
    """GNM's arrays incl. what base._gnm_data leaves out (skinning, joints' parents), GNM frame (x = the subject's
    left, y up, z forward), metres."""
    if "g" in _C:
        return _C["g"]
    from . import assets, base
    z = np.load(assets.path("gnm", base.GNM))
    names = [str(n) for n in z["vertex_group_names"]]
    g = {"T": z["template_vertex_positions"].astype(float), "IB": z["vertex_identity_basis"].astype(np.float32),
         "EB": z["expression_basis"].astype(np.float32), "J": z["template_joint_positions"].astype(float),
         "JB": z["joint_identity_basis"].astype(float), "W": z["skinning_weights"].astype(float),
         "parents": [int(p) for p in z["joint_parent_indices"]], "quads": z["quads"].astype(np.int64),
         "id_names": [str(n) for n in z["identity_names"]], "ex_names": [str(n) for n in z["expression_names"]],
         "groups": {n: z["vertex_groups"][i] > 0.5 for i, n in enumerate(names)}}
    q = g["quads"]
    g["tris"] = np.r_[q[:, [0, 1, 2]], q[:, [0, 2, 3]]]
    rows = (Path(assets.path("gnm", base.GNM)).parent.parent.parent / "landmarks" / "head_sparse_68.txt").read_text().split("\n")
    WL = np.zeros((68, len(g["T"])))
    for i, r in enumerate([[float(x) for x in r.split()] for r in rows if r.strip()]):
        for v, w in zip(r[0::2], r[1::2]):
            WL[i, int(v)] += w
    g["WL"] = WL
    _C["g"] = g
    return g


def normals(V: np.ndarray, tris: np.ndarray | None = None) -> np.ndarray:
    tris = gnm()["tris"] if tris is None else tris
    fn = np.cross(V[tris[:, 1]] - V[tris[:, 0]], V[tris[:, 2]] - V[tris[:, 0]])
    n = np.zeros_like(V)
    for k in range(3):
        np.add.at(n, tris[:, k], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-15)


def _neighbours(mask_a, mask_b):
    """Vertices of mask_a with a quad neighbour in mask_b."""
    q = gnm()["quads"]
    out = np.zeros(len(mask_a), bool)
    for i in range(4):
        for j in range(4):
            if i != j:
                a, b = q[:, i], q[:, j]
                hit = mask_a[a] & mask_b[b]
                out[a[hit]] = True
    return out


def zones() -> dict:
    """{zone: vertex indices} on GNM's template (see ZONES)."""
    if "zones" in _C:
        return _C["zones"]
    g = gnm()
    T, G = g["T"], g["groups"]
    n = normals(T)
    L = g["WL"] @ T
    mm = 1e-3
    ext = G["skin_exterior"] & ~G["mouth_sock"]
    eL, eR = T[G["left_eye"]].mean(0), T[G["right_eye"]].mean(0)
    if eL[0] < eR[0]:
        eL, eR = eR, eL
    X, Y, Zc = T[:, 0], T[:, 1], T[:, 2]
    ax = np.abs(X)

    def near(P, r):
        return np.linalg.norm(T - np.asarray(P), axis=1) < r

    def seg(A, B, r):
        A, B = np.asarray(A), np.asarray(B)
        t = np.clip((T - A) @ (B - A) / max((B - A) @ (B - A), 1e-12), 0, 1)
        return np.linalg.norm(T - (A + t[:, None] * (B - A)), axis=1) < r

    def both(fn):
        """fn(side) for side in (+1 subject's left, -1 right), OR-ed."""
        return fn(1.0) | fn(-1.0)

    def eye(side):
        return eL if side > 0 else eR

    def ring(lo, hi, cond):
        def f(side):
            e = eye(side)
            dx, dy = X - e[0], Y - e[1]
            r = np.hypot(dx, dy)
            return (r > lo * mm) & (r < hi * mm) & cond(dx * side, dy) & (Zc > e[2] - 2 * mm)
        return both(f) & ext & (G["left_orbital_region"] | G["right_orbital_region"] | G["left_brow_region"]
                                | G["right_brow_region"] | G["left_infraorbital_region"] | G["right_infraorbital_region"]
                                | G["middle_brow_region"] | G["nose_region"])

    nose = G["nose_region"] & ext
    lips = G["upper_lip"] | G["lower_lip"]
    up_skin = G["upper_lip_region"] & ~G["upper_lip"] & ext
    lo_skin = (G["lower_lip_region"] | G["chin_region"]) & ~G["lower_lip"] & ext
    z = {}
    z["forehead"] = G["forehead_region"] & ext
    z["glabella"] = G["middle_brow_region"] & ext
    z["brows"] = (G["left_brow_region"] | G["right_brow_region"]) & ext
    z["temples"] = (G["left_temple_region"] | G["right_temple_region"]) & ext
    z["upper_lid"] = ring(3.5, 9.5, lambda dx, dy: (dy > 1.5 * mm) & (np.abs(dx) < 12 * mm))
    z["lid_fold"] = ring(8.0, 13.5, lambda dx, dy: (dy > 3.0 * mm) & (np.abs(dx) < 11 * mm))
    z["lower_lid"] = ring(3.5, 9.0, lambda dx, dy: (dy < -1.5 * mm) & (np.abs(dx) < 12 * mm))
    z["upper_orbital_rim"] = ring(14.0, 21.0, lambda dx, dy: (dy > 5 * mm) & (np.abs(dx) < 14 * mm))
    z["lower_orbital_rim"] = ring(12.0, 19.0, lambda dx, dy: (dy < -5 * mm) & (np.abs(dx) < 13 * mm))
    z["tear_trough"] = ring(9.0, 17.0, lambda dx, dy: (dy < -3 * mm) & (dx < 3 * mm))
    z["inner_canthi"] = (near(L[39], 4.5 * mm) | near(L[42], 4.5 * mm)) & ext
    z["outer_canthi"] = (near(L[36], 5 * mm) | near(L[45], 5 * mm)) & ext
    z["radix"] = near(L[27], 7 * mm) & ext & (nose | G["middle_brow_region"])
    zr = (Y > L[30, 1] + 5 * mm) & (Y < L[27, 1] - 3 * mm)
    z["dorsum"] = nose & (ax < 3.5 * mm) & zr & (n[:, 2] > 0.5)
    ala_c = lambda s: np.array([s * (abs(L[35, 0]) + 2 * mm), L[35, 1] + 4 * mm, L[35, 2] - 2 * mm])  # noqa: E731
    z["alae"] = nose & (near(ala_c(1), 6.5 * mm) | near(ala_c(-1), 6.5 * mm))
    z["bridge_walls"] = nose & (ax > 3.5 * mm) & (ax < 11 * mm) & (Y > L[30, 1] + 5 * mm) & (Y < L[27, 1] - 2 * mm) \
        & (np.abs(n[:, 0]) > 0.3) & ~z["alae"]
    z["nose_tip"] = near(L[30], 8 * mm) & ext
    z["columella"] = nose & (ax < 3.5 * mm) & (Y > L[33, 1] + 1 * mm) & (Y < L[30, 1] - 3 * mm) & (Zc > L[33, 2] + 1.5 * mm)
    z["nostrils"] = nose & (n[:, 1] < -0.45) & (ax > 2.5 * mm) & (ax < 16 * mm) & (Y < L[30, 1] - 1 * mm)
    rim = _neighbours(nose, ext & ~nose)
    ab = (ax > 7 * mm) & (Y > L[33, 1] - 3 * mm) & (Y < L[35, 1] + 12 * mm)
    z["alar_crease"] = ((rim & ab) | _neighbours(ext & ~nose & ab, rim & ab)) & ext
    z["philtrum"] = up_skin & (ax < 6 * mm)
    z["upper_lip_skin"] = up_skin & ~z["nostrils"]
    bu = _neighbours(G["upper_lip"] & ext, up_skin)
    z["vermilion_border_upper"] = bu | _neighbours(up_skin, bu)
    z["cupids_bow"] = z["vermilion_border_upper"] & (ax < 9 * mm)
    bl = _neighbours(G["lower_lip"] & ext, lo_skin)
    z["vermilion_border_lower"] = bl | _neighbours(lo_skin, bl)
    z["upper_vermilion"] = G["upper_lip"] & ext
    z["lower_vermilion"] = G["lower_lip"] & ext
    z["mouth_corners"] = (near(L[48], 5 * mm) | near(L[54], 5 * mm)) & ext
    z["mentolabial_sulcus"] = lo_skin & (ax < 13 * mm) & (Y > L[8, 1] + 0.35 * (L[57, 1] - L[8, 1])) & (Y < L[57, 1] - 2 * mm)
    z["chin"] = G["chin_region"] & ext
    ch = np.flatnonzero(G["chin_region"] & ext & (ax < 8 * mm))
    z["pogonion"] = near(T[ch[np.argmax(Zc[ch])]], 8 * mm) & ext
    z["under_chin"] = ext & (ax < 30 * mm) & (Y > L[8, 1] - 35 * mm) & (Y < L[8, 1] + 3 * mm) & (Zc < L[8, 2] - 4 * mm) & (n[:, 1] < -0.3)
    jl = np.zeros(len(T), bool)
    for a, b in ((2, 3), (3, 4), (4, 5), (5, 6), (10, 11), (11, 12), (12, 13), (13, 14)):
        jl |= seg(L[a], L[b], 5 * mm)
    z["jawline"] = jl & ext
    z["jaw_angle"] = (near(L[3], 12 * mm) | near(L[13], 12 * mm)) & ext
    z["jowls"] = (near(L[5] + 0.3 * (L[48] - L[5]), 12 * mm) | near(L[11] + 0.3 * (L[54] - L[11]), 12 * mm)) & ext & ~lips
    mar = np.zeros(len(T), bool)
    nl = np.zeros(len(T), bool)
    for c_, a_, s in ((48, 31, -1.0), (54, 35, 1.0)):
        o = np.array([s, 0, 0])
        C0 = L[c_]
        mar |= seg(C0 + mm * (3 * o + [0, -3, -2]), C0 + mm * (7 * o + [0, -18, -4]), 5 * mm)
        nl |= seg(L[a_] + mm * (5 * o + [0, 3, -3]), C0 + mm * (9 * o + [0, 1, -5]), 4.5 * mm)
    z["marionette"] = mar & ext & ~lips
    z["nasolabial"] = nl & ext & ~nose & ~lips
    z["malar"] = (G["left_zygomatic_region"] | G["right_zygomatic_region"]) & ext
    z["cheeks"] = (G["left_cheek_region"] | G["right_cheek_region"]) & ext
    z["infraorbital"] = (G["left_infraorbital_region"] | G["right_infraorbital_region"]) & ext
    z["parotid"] = (G["left_parotid_region"] | G["right_parotid_region"]) & ext
    z["ears"] = G["ears"] & ext
    z["cranium"] = ext & ~G["hockey_mask"] & ~G["ears"] & (Y > 0.5 * (L[0, 1] + L[16, 1]))
    z["neck"] = ext & (Y < L[8, 1] - 25 * mm) & ~z["under_chin"]
    z["face"] = G["hockey_mask"] & ext
    z["iris"] = G["irises"]
    z["pupil"] = G["pupils"]
    z["sclera"] = G["scleras"]
    z["teeth_upper"] = G["upper_teeth_and_gums"]
    z["teeth_lower"] = G["lower_teeth_and_gums"]
    z["tongue"] = G["tongue"]
    out = {k: np.flatnonzero(z[k]) for k in ZONES}
    # each zone's surround (skin within 5 mm of it, outside it): what "relief" (a groove deepening) is measured against
    from scipy.spatial import cKDTree
    skin = np.flatnonzero(ext)
    tree = cKDTree(T[skin])
    sur = {}
    for k, idx in out.items():
        if not len(idx) or k in ("face", "cranium", "neck", "ears") or not ext[idx].all():
            sur[k] = np.zeros(0, int)
            continue
        hit = np.unique(np.concatenate(tree.query_ball_point(T[idx], 5 * mm)))
        sur[k] = np.setdiff1d(skin[hit], idx)
    _C["zones"] = out
    _C["surround"] = sur
    _C["normals"] = n
    return out


# ---------------------------------------------------------------- the controls

def _sampler():
    from . import gnm_sampler
    return gnm_sampler


def names(family: str | None = None) -> list[str]:
    """Every control name (of one family)."""
    g = gnm()
    out = {"identity": [n for n in g["id_names"]],
           "region_pc": [f"pc:{r}{k}" for r in sorted(k for k in g["groups"] if k.endswith("_region")) for k in range(8)],
           "expr_eyes": [f"both_eye_region_{k:03d}" for k in range(100)],
           "expr_lower": [f"lower_face_region_{k:03d}" for k in range(150)],
           "expr_tongue": [n for n in g["ex_names"] if n.startswith("tongue")] + ["pupil"],
           "joints": [f"joint:{j}_{a}" for j in ("neck", "head") for a in "xyz"] + ["joint:eyes_x", "joint:eyes_y"],
           "sampler_latent": [f"z:{k:02d}" for k in range(64)] + [f"zpc:{k:02d}" for k in range(16)],
           "sampler_label": ["label:sex"] + [f"label:{e}" for e in ("middle_eastern", "asian", "white", "black")],
           "sampler_expr": [f"xclass:{n}" for n in ("surprise", "disgust", "suck", "compress_face", "stretch_face", "happy",
                                                     "squint", "platysma", "blow", "funneler", "smile_wide", "corners_down",
                                                     "pucker", "wink_left", "wink_right", "mouth_left", "mouth_right",
                                                     "lips_roll_in", "snarl", "tongue_center")],
           "blockin": _blockin_names()}
    if family:
        return out[family]
    return [n for f in FAMILIES for n in out[f]]


def _blockin_names() -> list[str]:
    from . import blockin as bi, humanmacro as hm
    return list(hm.NAMES) + [f"nd:{n}" for n in bi.gap_names()] + ["sex", "eth0", "eth1", "eth2"]


def family(name: str) -> str:
    if name.startswith("pc:"):
        return "region_pc"
    if name.startswith("both_eye_region") or name.startswith(("left_eye_region", "right_eye_region")):
        return "expr_eyes"
    if name.startswith("lower_face_region"):
        return "expr_lower"
    if name.startswith("tongue") or name == "pupil" or name.startswith("pupil"):
        return "expr_tongue"
    if name.startswith("joint:"):
        return "joints"
    if name.startswith(("z:", "zpc:")):
        return "sampler_latent"
    if name.startswith("label:"):
        return "sampler_label"
    if name.startswith("xclass:"):
        return "sampler_expr"
    if re.fullmatch(r"(head|eyes|teeth)_\d{3}", name):
        return "identity"
    return "blockin"


def _latent_at():
    """The sampler's latent study point: z = 0 at the female / white class; its Jacobian (253 x 64) and SVD."""
    if "lat" not in _C:
        S = _sampler()
        lab = S.id_label("female", "white")
        J = S.identity().jac(np.zeros(64), lab)[:, :64]
        U, s, Vt = np.linalg.svd(J[:170], full_matrices=False)
        _C["lat"] = {"lab": lab, "J": J, "Vt": Vt, "s": s, "c0": S.identity()(np.zeros(64), lab)[0]}
    return _C["lat"]


def coefficients(name: str, amount: float = 1.0, base_id=None) -> tuple:
    """(identity (253,), expression (383,), rotations (4, 3) or None) for `amount` units of a control, on base_id
    (identity 253; default 0, the template). Linear families add amount x the unit; sampler latents and labels are
    DECODED (non-linear: the sampler's own head at that latent / label, not base_id + a direction)."""
    g = gnm()
    c = np.zeros(len(g["id_names"])) if base_id is None else np.array(base_id, float)
    e = np.zeros(len(g["ex_names"]))
    rot = None
    f = family(name)
    if f == "identity":
        c[g["id_names"].index(name)] += amount
    elif f in ("region_pc", "blockin"):
        from . import blockin as bi
        d = bi.direction(name)
        if name == "sex":
            d = d / 2
        c[:170] += amount * d
    elif f == "expr_eyes":
        k = int(name[-3:])
        for side in ("left", "right"):
            nm = f"{side}_eye_region_{k:03d}"
            if name.startswith(("both", side)):
                e[g["ex_names"].index(nm)] += amount
    elif f in ("expr_lower", "expr_tongue"):
        if name == "pupil":
            e[[i for i, n in enumerate(g["ex_names"]) if "pupil" in n]] += amount
        else:
            e[g["ex_names"].index(name)] += amount
    elif f == "joints":
        rot = np.zeros((4, 3))
        j, a = name[6:].rsplit("_", 1)
        ax = "xyz".index(a)
        rad = np.radians(10.0 * amount)
        if j == "eyes":
            rot[2, ax] = rot[3, ax] = rad
        else:
            rot[["neck", "head"].index(j), ax] = rad
    elif f == "sampler_latent":
        S, la = _sampler(), _latent_at()
        k = int(name.split(":")[1])
        zz = np.zeros(64)
        if name.startswith("z:"):
            zz[k] = amount
        else:
            zz = amount * la["Vt"][k]
        c = S.identity()(zz, la["lab"])[0]
    elif f == "sampler_label":
        S = _sampler()
        t = 0.5 + 0.5 * amount
        if name == "label:sex":
            lab = S.id_label(t, None)
        else:
            u = S.id_label(0.5, None)
            lab = u.copy()
            lab[2:] = (1 - t) * 0.25 + t * (np.arange(4) == S.ETH.index(name[6:]))
            if amount < 0:   # away from the class: the other three
                lab[2:] = (1 + amount) * 0.25 + (-amount) * (np.arange(4) != S.ETH.index(name[6:])) / 3.0
        c = S.identity()(np.zeros(64), lab)[0]
    elif f == "sampler_expr":
        S = _sampler()
        e = amount * S.expression()(np.zeros(64), S.ex_label(name[7:]))[0]
    return c, e, rot


def vertices(c=None, e=None, rot=None) -> np.ndarray:
    """GNM's head (GNM frame, metres) for identity c (253), expression e (383), joint rotations rot (4, 3 axis-angle)."""
    g = gnm()
    V = g["T"].copy()
    if c is not None and np.any(c):
        V += np.tensordot(np.asarray(c, np.float32), g["IB"][:len(c)], 1)
    if e is not None and np.any(e):
        V += np.tensordot(np.asarray(e, np.float32), g["EB"][:len(e)], 1)
    if rot is None or not np.any(rot):
        return V
    J = g["J"] + (np.tensordot(np.asarray(c, float), g["JB"][:len(c)], 1) if c is not None else 0)
    Wt = []
    for k, p in enumerate(g["parents"]):
        R = _rodrigues(rot[k])
        loc = J[k] if p < 0 else J[k] - J[p]
        M = np.eye(4)
        M[:3, :3], M[:3, 3] = R, loc
        Wt.append(M if p < 0 else Wt[p] @ M)
    out = np.zeros_like(V)
    for k in range(len(J)):
        A = Wt[k].copy()
        A[:3, 3] -= A[:3, :3] @ J[k]
        out += g["W"][k][:, None] * (V @ A[:3, :3].T + A[:3, 3])
    return out


def _rodrigues(r):
    r = np.asarray(r, float)
    a = np.linalg.norm(r)
    if a < 1e-12:
        return np.eye(3)
    k = r / a
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K


def field(name: str, base_id=None, h: float = 1.0) -> np.ndarray:
    """The control's move per unit (V, 3, metres, GNM frame): central difference over +-h (exact for the linear
    families)."""
    vp = vertices(*coefficients(name, h, base_id))
    vm = vertices(*coefficients(name, -h, base_id))
    return (vp - vm) / (2 * h)


def zone_stats(D: np.ndarray) -> np.ndarray:
    """(n zones, 6): tot, nrm, sgn, trans, deform, relief (mm per unit) of a move D (V, 3, metres). relief = the zone's
    mean normal move minus its 5 mm surround's: + the zone rises out of its surroundings (a groove gets shallower, a
    ridge stronger), - it sinks (a crease deepens)."""
    Z = zones()
    n = _C["normals"]
    sur = _C["surround"]
    out = np.zeros((len(ZONES), len(STATS)))
    for i, k in enumerate(ZONES):
        idx = Z[k]
        if not len(idx):
            continue
        d = D[idx] * MM
        dn = (d * n[idx]).sum(1)
        m = d.mean(0)
        rel = 0.0
        if len(sur[k]):
            rel = dn.mean() - ((D[sur[k]] * MM) * n[sur[k]]).sum(1).mean()
        out[i] = [np.sqrt((d ** 2).sum(1).mean()), np.sqrt((dn ** 2).mean()), dn.mean(), np.linalg.norm(m),
                  np.sqrt(((d - m) ** 2).sum(1).mean()), rel]
    return out


def macro_effect(name: str, base_id=None) -> np.ndarray:
    """The macros (humanmacro, in their population sd) a control moves per unit (central difference)."""
    from . import humanmacro as hm
    sd = hm.table()["sd"]
    w = lambda V: np.c_[V[:, 0], -V[:, 2], V[:, 1]]  # noqa: E731
    mp = hm.measures(w(vertices(*coefficients(name, 1.0, base_id))))
    mn = hm.measures(w(vertices(*coefficients(name, -1.0, base_id))))
    return np.array([(mp[k] - mn[k]) / 2 / sd[i] for i, k in enumerate(hm.NAMES)])


def identity_direction(name: str) -> np.ndarray | None:
    """The control's move in the 170 head components per unit (None for expression / pose controls)."""
    f = family(name)
    if f in ("expr_eyes", "expr_lower", "expr_tongue", "joints", "sampler_expr"):
        return None
    cp, _, _ = coefficients(name, 1.0)
    cm, _, _ = coefficients(name, -1.0)
    return (cp - cm)[:170] / 2


# ---------------------------------------------------------------- the table

def table() -> dict:
    if "t" not in _C:
        if not DATA.exists():
            raise FileNotFoundError(f"{DATA.name} is missing: build it with gnm_controls.build() (the gnmcontrols study)")
        z = np.load(DATA)
        _C["t"] = {k: (z[k] if z[k].dtype.kind in "US" else np.asarray(z[k], float)) for k in z.files}
        _C["t"]["index"] = {str(n): i for i, n in enumerate(_C["t"]["names"])}
    return _C["t"]


def build(perc: dict | None = None, sheets: dict | None = None, out: Path | None = None, verbose: bool = False) -> dict:
    """Measure every control (zones, face rms / max, macros, nearest block-in moves) into gnm_controls.npz.
    perc: {name: (sface, arcface)} from the perception runs; sheets: {name: "page.png#row"}."""
    from . import humanmacro as hm
    allnames = names()
    fams = [family(n) for n in allnames]
    nz = len(ZONES)
    Zs = np.zeros((len(allnames), nz, len(STATS)), np.float32)
    face = np.zeros((len(allnames), 3), np.float32)
    mac = np.zeros((len(allnames), len(hm.NAMES)), np.float32)
    zi = list(ZONES)
    ext = np.flatnonzero(gnm()["groups"]["skin_exterior"])
    # the block-in moves' identity directions, for "nearest"
    bnames = [n for n in allnames if family(n) in ("blockin", "region_pc")]
    B = np.array([identity_direction(n) for n in bnames])
    Bn = B / np.maximum(np.linalg.norm(B, axis=1, keepdims=True), 1e-12)
    near_n = np.full((len(allnames), 3), "", dtype=object)
    near_c = np.zeros((len(allnames), 3), np.float32)
    lin = np.full(len(allnames), np.nan, np.float32)
    cost = np.full(len(allnames), np.nan, np.float32)
    for i, nm in enumerate(allnames):
        D = field(nm)
        if fams[i] != "joints":
            cp, ep, _ = coefficients(nm, 1.0)
            cm, em, _ = coefficients(nm, -1.0)
            cost[i] = np.linalg.norm(np.r_[cp - cm, ep - em]) / 2
        Zs[i] = zone_stats(D)
        fz = Zs[i, zi.index("face"), 0]
        m = np.linalg.norm(D[ext], axis=1) * MM
        face[i] = [fz, m.max(), np.sqrt((m ** 2).mean())]
        mac[i] = macro_effect(nm)
        d = identity_direction(nm)
        if d is not None and np.linalg.norm(d) > 1e-9:
            cs = Bn @ (d / np.linalg.norm(d))
            top = [j for j in np.argsort(-np.abs(cs)) if bnames[j] != nm][:3]
            near_n[i] = [bnames[j] for j in top]
            near_c[i] = cs[top]
        if fams[i] in ("sampler_latent", "sampler_label"):
            vp, vm = vertices(*coefficients(nm, 2.0)), vertices(*coefficients(nm, -2.0))
            v0 = vertices(*coefficients(nm, 0.0))
            lin[i] = np.linalg.norm((vp + vm - 2 * v0)[ext]) / max(np.linalg.norm((vp - vm)[ext]), 1e-12)
        if verbose and i % 50 == 0:
            print("build", i, "/", len(allnames), nm, flush=True)
    P = np.full((len(allnames), 2), np.nan, np.float32)
    for i, nm in enumerate(allnames):
        if perc and nm in perc:
            P[i] = [np.nan if v is None else v for v in perc[nm]]
    sh = np.array([(sheets or {}).get(nm, "") for nm in allnames])
    res = {"names": np.array(allnames), "family": np.array(fams), "zone_names": np.array(zi), "stats": np.array(STATS),
           "Z": Zs.astype(np.float16), "face": face, "macros": mac.astype(np.float16), "macro_names": np.array(hm.NAMES),
           "perc": P, "near": near_n.astype(str), "near_cos": near_c, "nonlin": lin, "sheet": sh, "cost": cost}
    np.savez_compressed(out or DATA, **res)
    _C.pop("t", None)
    return res


# ---------------------------------------------------------------- the query

def _words(s: str) -> list[str]:
    return [w for w in re.split(r"[\s,;/]+", s.lower().replace("_", "-")) if w]


def match_zones(text: str) -> list[str]:
    """The zones a phrase names ("alar crease" -> alar_crease; "lip border" -> both vermilion borders)."""
    t = text.lower().strip()
    if t.replace(" ", "_") in ZONES:
        return [t.replace(" ", "_")]
    phrase = t.replace("_", "-").replace(" ", "-")
    hits = [k for k, (_, syn) in ZONES.items() if phrase in syn.split()]
    if hits:
        return hits
    ws = _words(t)
    score = {}
    for k, (desc, syn) in ZONES.items():
        toks = set(syn.replace("-", " ").split()) | set(k.split("_"))
        s = sum(1 for w in ws if w in toks or w.rstrip("s") in toks)
        if s:
            score[k] = s
    if not score:
        return []
    best = max(score.values())
    return [k for k, s in score.items() if s == best]


def query(text: str = "", zones_: list | None = None, families: list | None = None, top: int = 12,
          sort: str = "score", sign: int = 0, per_family: int = 0) -> dict:
    """The controls that move a zone. text: a feature in words ("alar crease", "jowl", "lip border") or zone names;
    families: restrict (default every shape family); sort: score (efficiency x specificity (capped at 4): the cheapest, most
    local movers) | efficiency (local mm per unit of PRIOR COST: |coefficient change| in population sd, so a whole
    expression prototype and a single comp compare fairly) | local (mm per control unit) | specific (local / face rms)
    | perc (face-ID effect) | relief (|the zone's move against its 5 mm surround| per unit cost: deepening or
    softening a groove / line); sign: +1 / -1 keeps controls whose + moves the zone out / in (the signed mean normal;
    with sort=relief: rises / sinks against its surround);
    per_family: the top k of every family instead of one ranking. Returns {"zones", "rows": [{name, family, local,
    efficiency, specific, sgn, face_rms, cost, perc, macros (top 3), near, sheet}]}."""
    t = table()
    zn = list(t["zone_names"])
    zs = list(zones_ or []) or match_zones(text)
    if not zs:
        raise ValueError(f"no zone matches {text!r}; zones: {', '.join(zn)}")
    fams = set(families or SHAPE_FAMILIES)
    keep = np.array([f in fams for f in t["family"]])
    idx = [zn.index(z) for z in zs]
    Zsub = t["Z"][:, idx, :].astype(float)
    local = np.max(Zsub[:, :, [1, 4]], axis=2).mean(1)
    sgn = Zsub[:, :, 2].mean(1)
    fr = t["face"][:, 0]
    spec = local / np.maximum(fr, 1e-6)
    cost = t["cost"] if "cost" in t else np.ones(len(local))
    eff = local / np.maximum(cost, 1e-6)
    score = eff * np.minimum(spec, 4.0)
    rel = Zsub[:, :, 5].mean(1) if Zsub.shape[2] > 5 else np.zeros(len(local))
    key = {"score": score, "efficiency": eff, "local": local, "specific": np.where(local > 0.02, spec, 0),
           "perc": np.nan_to_num(t["perc"][:, 0]), "relief": np.abs(rel) / np.maximum(cost, 1e-6)}[sort]
    m = keep & np.isfinite(key)
    if sign:
        m &= np.sign(rel if sort == "relief" else sgn) == np.sign(sign)
    ranked = [i for i in np.argsort(-np.where(m, key, -np.inf)) if m[i]]
    if per_family:
        order = []
        for f in FAMILIES:
            order += [i for i in ranked if t["family"][i] == f][:per_family]
    else:
        order = ranked[:top]
    mn = list(t["macro_names"])
    rows = []
    for i in order:
        mv = t["macros"][i].astype(float)
        tm = np.argsort(-np.abs(mv))[:3]
        rows.append({"name": str(t["names"][i]), "family": str(t["family"][i]), "local": round(float(local[i]), 3),
                     "efficiency": round(float(eff[i]), 3), "cost": round(float(cost[i]), 2),
                     "specific": round(float(spec[i]), 2), "relief": round(float(rel[i]), 3), "sgn": round(float(sgn[i]), 3),
                     "face_rms": round(float(fr[i]), 3), "perc": None if not np.isfinite(t["perc"][i, 0]) else round(float(t["perc"][i, 0]), 4),
                     "macros": {mn[j]: round(float(mv[j]), 2) for j in tm},
                     "near": [f"{n} {c:+.2f}" for n, c in zip(t["near"][i], t["near_cos"][i]) if n],
                     "sheet": str(t["sheet"][i])})
    return {"zones": zs, "rows": rows}


def describe(name: str) -> dict:
    """One control: where it acts (its top zones by local shape change), the macros it moves, perception, near."""
    t = table()
    i = t["index"][name]
    zn = list(t["zone_names"])
    Z = t["Z"][i].astype(float)
    loc = np.max(Z[:, [1, 4]], axis=1)
    fr = float(t["face"][i, 0])
    skip = ("face", "neck", "cranium", "iris", "pupil", "sclera", "teeth_upper", "teeth_lower", "tongue")
    order = [j for j in np.argsort(-loc) if zn[j] not in skip][:6]
    if not order or loc[order[0]] < 1e-3:   # (eyeballs, teeth, tongue, pose: what moves is not the face's skin)
        order = [j for j in np.argsort(-loc) if zn[j] != "face"][:6]
    mv = t["macros"][i].astype(float)
    mn = list(t["macro_names"])
    tm = np.argsort(-np.abs(mv))[:5]
    hint = ", ".join(f"{zn[j]} {'out' if Z[j, 2] > 0 else 'in'}" for j in order[:2])
    if len(tm):
        hint += f"; {mn[tm[0]]} {mv[tm[0]]:+.2f} sd"
    return {"name": name, "family": str(t["family"][i]), "hint": hint, "face_rms": round(fr, 3), "face_max": round(float(t["face"][i, 1]), 3),
            "zones": {zn[j]: {"local": round(float(loc[j]), 3), "sgn": round(float(Z[j, 2]), 3), "specific": round(float(loc[j] / max(fr, 1e-6)), 2)} for j in order},
            "macros": {mn[j]: round(float(mv[j]), 2) for j in tm},
            "perc": None if not np.isfinite(t["perc"][i, 0]) else {"sface": round(float(t["perc"][i, 0]), 4), "arcface": round(float(t["perc"][i, 1]), 4)},
            "near": [f"{n} {c:+.2f}" for n, c in zip(t["near"][i], t["near_cos"][i]) if n],
            "nonlinearity": None if not np.isfinite(t["nonlin"][i]) else round(float(t["nonlin"][i]), 2),
            "sheet": str(t["sheet"][i])}


def text(res: dict) -> str:
    """A query's or describe's reply as text."""
    if "rows" in res:
        z = ", ".join(f"{k} ({ZONES[k][0]})" for k in res["zones"])
        out = [f"zones: {z}", "control | family | local mm/unit | mm per unit prior cost (|coef| per unit) | specificity "
               "(local / face rms) | relief vs its surround (+ rises) | + moves out/in | face rms | face-ID effect (sface, -1 vs +1) | macros moved (sd/unit) | "
               "nearest block-in moves | sheet"]
        for r in res["rows"]:
            out.append(f"{r['name']} | {r['family']} | {r['local']:.3f} | {r['efficiency']:.3f} ({r['cost']:.2f}) | {r['specific']:.2f} | "
                       f"relief {r['relief']:+.3f} | {'out' if r['sgn'] > 0 else 'in'} "
                       f"{r['sgn']:+.3f} | {r['face_rms']:.3f} | {r['perc'] if r['perc'] is not None else '-'} | "
                       + ", ".join(f"{k} {v:+.2f}" for k, v in r["macros"].items()) + " | " + "; ".join(r["near"]) + f" | {r['sheet']}")
        return "\n".join(out)
    r = res
    return (f"{r['name']} ({r['family']}): face rms {r['face_rms']} mm/unit, max {r['face_max']}; zones "
            + ", ".join(f"{k} {v['local']:.2f} mm ({'out' if v['sgn'] > 0 else 'in'}, x{v['specific']:.1f})" for k, v in r["zones"].items())
            + "; macros " + ", ".join(f"{k} {v:+.2f}" for k, v in r["macros"].items())
            + f"; face-ID {r['perc']}; nearest block-in " + "; ".join(r["near"])
            + ("" if r["nonlinearity"] is None else f"; non-linearity {r['nonlinearity']}") + f"; sheet {r['sheet']}")


# ---------------------------------------------------------------- sculpt: a zone moved the GNM way

def _macro_jac() -> np.ndarray:
    """d macros (in their population sd) / d head comp, (40, 170), central differences at the template (the macros are
    linear in the identity: humanmacro's R2 0.97-1.00)."""
    if "MJ" not in _C:
        from . import humanmacro as hm
        sd = hm.table()["sd"]
        g = gnm()
        w = lambda V: np.c_[V[:, 0], -V[:, 2], V[:, 1]]  # noqa: E731
        J = np.zeros((len(hm.NAMES), 170))
        for k in range(170):
            d = g["IB"][k].astype(float)
            mp, mn = hm.measures(w(g["T"] + d)), hm.measures(w(g["T"] - d))
            J[:, k] = [(mp[n] - mn[n]) / 2 / sd[i] for i, n in enumerate(hm.NAMES)]
        _C["MJ"] = J
    return _C["MJ"]


def zone_row(zone: str, kind: str = "zone") -> np.ndarray:
    """(170,): a zone's mean NORMAL move (mm, + out of the face) per head comp; kind "relief": against its 5 mm
    surround (+ rises, - sinks: a groove deepens). Exact: GNM is linear."""
    Z = zones()
    n = _C["normals"]
    IB = gnm()["IB"][:170]
    idx = Z[zone]
    row = np.einsum("kvd,vd->k", IB[:, idx, :].astype(float), n[idx]) / len(idx) * MM
    if kind == "relief":
        sur = _C["surround"][zone]
        if not len(sur):
            raise ValueError(f"relief: zone {zone} has no surround (pick a face zone)")
        row = row - np.einsum("kvd,vd->k", IB[:, sur, :].astype(float), n[sur]) / len(sur) * MM
    return row


def sculpt(zone: str, kind: str = "zone", hold: str | list = "all", hold_zones: tuple = (), locality: float = 3.0,
           release: float = 0.7) -> dict:
    """The least-cost identity change (170 head comps, |dc| in population sd) that moves `zone` 1 mm (its mean normal;
    kind "relief": against its 5 mm surround), with the MACROS held (hold "all" = every humanmacro measure, or a list;
    a held macro too much like the target itself (|cos| > release in the comps' space) is let go and reported), other
    zones held at 0 (hold_zones), and a LOCALITY penalty: locality^2 x the mean squared move (mm) of the face's skin more
    than 6 mm from the zone. Linear, so amount x the returned "dc" is the move for any amount. This is how Garrett's
    narrow bridge was made without a designed local (gnmcontrols: walls 0.746 -> 0.584, designed local 0.670)."""
    from . import humanmacro as hm
    from scipy.spatial import cKDTree
    key = ("sculpt", zone, kind, json_key(hold), tuple(hold_zones), float(locality), float(release))
    if key in _C:
        return _C[key]
    g = gnm()
    Z = zones()
    t = zone_row(zone, kind)
    rows, rhs, names_ = [t], [1.0], [f"{kind}:{zone}"]
    for z in hold_zones:
        rows.append(zone_row(z, "zone"))
        rhs.append(0.0)
        names_.append(f"held zone {z}")
    MJ = _macro_jac()
    want = list(hm.NAMES) if hold == "all" else list(hold)
    released = []
    for m in want:
        r = MJ[hm.NAMES.index(m)]
        cos = abs(r @ t) / max(np.linalg.norm(r) * np.linalg.norm(t), 1e-12)
        if cos > release:
            released.append(f"{m} (cos {cos:.2f})")
            continue
        rows.append(r)
        rhs.append(0.0)
        names_.append(m)
    T = g["T"]
    face = Z["face"]
    near = cKDTree(T[Z[zone]]).query(T[face])[0] < 0.006
    out = face[~near]
    IBo = g["IB"][:170, out, :].reshape(170, -1).astype(float) * MM
    H = np.eye(170) + (locality ** 2) * (IBo @ IBo.T) / len(out)
    C = np.array(rows)
    d = np.array(rhs)
    n, k = 170, len(d)
    K = np.zeros((n + k, n + k))
    K[:n, :n], K[:n, n:], K[n:, :n] = H, C.T, C
    sol = np.linalg.lstsq(K, np.r_[np.zeros(n), d], rcond=None)[0]
    dc = sol[:n]
    mv = MJ @ dc
    top = np.argsort(-np.abs(mv))[:5]
    res = {"dc": dc, "cost": float(np.linalg.norm(dc)), "achieved": float(t @ dc), "released": released,
           "held": names_[1:], "outside_mm": float(np.sqrt(((IBo.T @ dc) ** 2).reshape(-1, 3).sum(1).mean())),
           "macros": {hm.NAMES[j]: round(float(mv[j]), 3) for j in top}}
    _C[key] = res
    return res


def json_key(x):
    return x if isinstance(x, str) else tuple(x)


def parse_sculpt(name: str) -> dict:
    """"sculpt:<zone>[|hold=<zone>+<zone>][|free=<macro>+..][|loc=<w>]" or "relief:<zone>[...]" -> sculpt's kwargs."""
    kind, rest = name.split(":", 1)
    parts = rest.split("|")
    kw = {"zone": parts[0], "kind": "relief" if kind == "relief" else "zone"}
    if kw["zone"] not in ZONES:
        raise ValueError(f"{kind}: no zone {kw['zone']!r}; zones: {', '.join(ZONES)}")
    for p_ in parts[1:]:
        k, _, v = p_.partition("=")
        if k == "hold":
            kw["hold_zones"] = tuple(v.split("+"))
        elif k == "free":
            from . import humanmacro as hm
            kw["hold"] = [m for m in hm.NAMES if m not in v.split("+")]
        elif k == "loc":
            kw["locality"] = float(v)
        else:
            raise ValueError(f"{name}: unknown option {k!r} (hold=, free=, loc=)")
    return kw
