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
block-in's "sculpt:<zone>" move (Garrett's narrow bridge, made without a designed local).

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at gnm_controls.NAME: C422). gnm_controls_latent: the controls themselves: names and families, a control's
coefficients, the vertices and fields it gives, zone stats, macro effects. gnm_controls_table: the table of what each
control moves (built once), and the query: zones matched from words, `query`, `describe`, `text`. gnm_controls_sculpt:
sculpt: a zone moved the GNM way (`zone_row`, `sculpt`), its key and its parser.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from . import moved

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
    """GNM's arrays incl. what base_identity._gnm_data leaves out (skinning, joints' parents), GNM frame (x = the subject's
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


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("gnm_controls_latent", "gnm_controls_table", "gnm_controls_sculpt")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
