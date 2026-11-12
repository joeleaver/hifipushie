"""Measuring and fitting the one human mesh (onemesh.py) without wrecking what wasn't asked about.

Sliders are ambiguous, and an agent that hits one number blind breaks the rest of the face. So the interface is:
state evidence (named measures, landmark moves), a SOLVER finds the parameters, and every change comes back with what
ELSE moved and whether the mesh is still sound.

- `measures(base)`: a named vocabulary read off the mesh: body (cm: stature, heads tall, breadths, girths, limb
  lengths; anthro.measure) and face (mm, from the 68 landmarks and the eye centres: FACE below), plus ratios the
  agent asks for as "a/b".
- `solve(base, {"measure": value | "+2" | "x1.1", "a/b": ratio}, free=("identity",))`: minimal change. Gauss-Newton
  on GNM's identity components (the landmarks are linear in them: headfit's tables) and, with "body" in `free`, on
  MakeHuman's macros (finite differences); every measure NOT asked for is held as a soft constraint, every landmark
  far from the asked ones is held in place, the step is ridged toward the CURRENT state, and components stop at the
  plausible range (CLIP sigma; `force` widens it). What the parameters can't reach is reported as the residual, not
  obeyed.
- `nudge(base, landmark, move)`: move one landmark; the parameters take what they can, the rest becomes a small smooth
  correction (a Gaussian push at that landmark, base.head.shape.push_more: it survives later changes) and is REPORTED:
  that is a slider the model lacks.
- `side_effects(before, after, asked)`: all measures before -> after sorted by how far they moved, UNINTENDED flags,
  where the vertices moved and how many outside the region asked.
- `integrity(base)`: gates cheap enough to run on every change: folded faces, edge stretch per named region (lids,
  lips, nose, ears, neck bridge) against the same body with a neutral head, lids over the eyeballs, lips not crossed,
  symmetry, plausibility (sigma). `verdict` leads with INTEGRITY: ok / BROKEN: ...

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at humanfit.NAME: C422). humanfit_integrity: what a fit did besides what was asked: side effects, integrity,
the guard against newly broken regions, the verdict, the table. humanfit_solve: the solve: landmark, skull and cheek
bases, `solve`, `nudge`. humanfit_views: reference images: cameras and the face fitted together on named 2D points
(project, the silhouette, fit_outline, fit_region, fit_hood, fit_views). humanfit_sheet: pictures: before | after |
where it moved, and the report's text.
"""
from __future__ import annotations

import numpy as np
from . import moved

CLIP = 2.6       # sigma: an identity component past this is outside the plausible range (headfit's)
CLIP_FORCE = 4.0
TOL_MM = 0.5     # a face measure counts as met within this
UNINTENDED_MM = 1.0   # a face measure that wasn't asked for and moved more is flagged
FOLD_LIMIT = 6    # faces an edit may turn over before the mesh counts as broken
COLLATERAL = 2.0  # a solve stops where a measure that wasn't asked for would move this many times its tolerance
UNINTENDED_BODY = 0.01  # ... a body measure: 1%
HOLD = 0.35      # weight of holding the measures that weren't asked for (x 1 / mm)
HOLD_SKULL = 0.25  # weight of holding the skull's own points (crown, back, neck) in image fits and solves (x 1 / mm)
HOLD_LM = 0.12   # weight of holding landmarks far from the asked ones (x 1 / mm)
RIDGE = 0.25     # weight of each component's step (per sigma)
EYE_L, EYE_R = 68, 69  # the eye centres, after the 68 landmarks

# name: (points a, points b, axis): the distance from the mean of a to the mean of b along x (across), z (up),
# y (depth, + = a behind b) or None (straight). mm. Mirrored pairs are averaged ("pairs": [(a, b), ...]).
FACE = {
    "interocular": ([EYE_L], [EYE_R], "x"),
    "face_width": ([16], [0], "x"),
    "jaw_width": ([12], [4], "x"),
    "chin_width": ([10], [6], "x"),
    "face_height": ([27], [8], "z"),
    "eye_width": {"pairs": [([45], [42], None), ([39], [36], None)]},
    "eye_height": {"pairs": [([43, 44], [47, 46], "z"), ([37, 38], [41, 40], "z")]},
    "eye_spacing": ([42], [39], "x"),
    "eye_to_chin": ([EYE_L, EYE_R], [8], "z"),
    "brow_height": ([19, 24], [EYE_L, EYE_R], "z"),
    "nose_length": ([27], [33], "z"),
    "nose_width": ([35], [31], "x"),
    "nose_projection": ([33], [30], "y"),
    "philtrum": ([33], [51], "z"),
    "mouth_width": ([54], [48], "x"),
    "lip_height": ([51], [57], "z"),
    "mouth_to_eye": ([EYE_L, EYE_R], [62, 66], "z"),
    "chin_height": ([57], [8], "z"),
}
BODY = ("stature", "heads", "head_height", "sitting_height", "biacromial", "hip_breadth", "trochanter_height",
        "hand_length", "foot_length", "chest_circ", "waist_circ", "neck_circ")
BODY_FREE = ("weight", "muscle", "height")
# MakeHuman's measure modifiers (makehuman.MEASURES; 0..1, 0.5 = none) and the cup size, free only when a measure
# they shape is asked (each is one more body build per round): a slim woman's hips aren't the weight slider
BODY_SHAPE = {"hips": ("hip_breadth", "hip_circ"), "waist": ("waist_circ", "waist_breadth"),
              "shoulders": ("shoulder_breadth", "biacromial"), "chest": ("chest_circ",), "bust": ("bust_circ",),
              "neck_circ": ("neck_circ",)}
AX = {"x": 0, "y": 1, "z": 2}
LANDMARKS = {"chin": 8, "nose_tip": 30, "nose_base": 33, "nose_bridge": 27, "lip_upper": 51, "lip_lower": 57,
             "mouth_corner.L": 54, "mouth_corner.R": 48, "jaw.L": 12, "jaw.R": 4, "jaw_back.L": 15, "jaw_back.R": 1,
             "brow.L": 24, "brow.R": 19, "brow_inner.L": 22, "brow_inner.R": 21, "eye_outer.L": 45, "eye_outer.R": 36,
             "eye_inner.L": 42, "eye_inner.R": 39, "lid_upper.L": 43, "lid_upper.R": 38, "lid_lower.L": 47,
             "lid_lower.R": 40, "ala.L": 35, "ala.R": 31, "chin.L": 10, "chin.R": 6}


def _one(spec, L):
    a, b, ax = spec
    d = L[a].mean(0) - L[b].mean(0)
    return float(np.linalg.norm(d) if ax is None else d[AX[ax]]) * 1000.0


def _grad(spec, L):
    """d(measure, mm) / d(L, m): (70, 3)."""
    a, b, ax = spec
    G = np.zeros_like(L)
    d = L[a].mean(0) - L[b].mean(0)
    u = d / max(np.linalg.norm(d), 1e-12) if ax is None else np.eye(3)[AX[ax]]
    G[a] += u / len(a)
    G[b] -= u / len(b)
    return G * 1000.0


def face_measures(L) -> dict:
    out = {}
    for k, sp in FACE.items():
        out[k] = float(np.mean([_one(p, L) for p in sp["pairs"]])) if isinstance(sp, dict) else _one(sp, L)
    return out


def face_gradient(name: str, L):
    sp = FACE[name]
    if isinstance(sp, dict):
        return np.mean([_grad(p, L) for p in sp["pairs"]], axis=0)
    return _grad(sp, L)


def _points(name: str) -> list:
    sp = FACE[name]
    pr = sp["pairs"] if isinstance(sp, dict) else [sp]
    return sorted({i for a, b, _ in pr for i in a + b})


def state(base: dict) -> dict:
    """The mesh and what is read off it: {"tpl", "head", "L" (68 landmarks + 2 eye centres, world, template pose),
    "measures"}."""
    from . import anthro, onemesh
    from . import onemesh_head
    if not onemesh.applies(base):
        raise ValueError('humanfit: the model\'s base is not the one human mesh (base.body.source "human"; make one with '
                         'the human tool, source="human")')
    tpl = onemesh_head.template(base)
    ht = onemesh_head.head_rest(base)
    L = np.r_[np.asarray(ht["lm68"], float), np.asarray(ht["eyes"], float)]
    if L[EYE_L, 0] < L[EYE_R, 0]:
        L[[EYE_L, EYE_R]] = L[[EYE_R, EYE_L]]
    m = anthro.measure(np.asarray(tpl["P"], float), tpl["J"], float(tpl["chin_mh"]))
    m["neck_circ"] = _neck_girth(tpl)
    body = {k: float(m[k]) * (1.0 if k == "heads" else 100.0) for k in BODY if k in m}
    return {"tpl": tpl, "head": ht, "L": L, "measures": {**body, **face_measures(L)}, "base": base}


HOLLOW_FROM = 0.4  # the cheek hollow is read from this share of the way from the nose's wing to the jaw contour


def cheek_hollow(st: dict) -> dict:
    """mm per side: the hollow under the cheekbone, read on HORIZONTAL sections of the head (between the nose's base
    and the mouth's corners, three levels): the face's outer contour on that side (from the nose's wing out to the
    jaw contour) against its convex hull, the deepest point inside the hull. A lean face with hollow cheeks reads a
    few mm, a full or jowly one ~0 (its contour is convex). The head faces -y."""
    from scipy.spatial import ConvexHull
    P = np.asarray(st["tpl"]["P"], float)
    T = np.array([(f[0], f[j], f[j + 1]) for f in _faces(st["tpl"]) for j in range(1, len(f) - 1)])
    L = st["L"]
    mid = 0.5 * (L[EYE_L] + L[EYE_R])
    out = {"right": 0.0, "left": 0.0}
    for zc in np.linspace(L[33, 2], 0.5 * (L[48, 2] + L[54, 2]), 3):
        dz = P[T, 2] - zc
        cr = (dz.min(1) < 0) & (dz.max(1) > 0)
        pts = []
        for t, d_ in zip(T[cr], dz[cr]):
            for a_, b_ in ((0, 1), (1, 2), (2, 0)):
                if (d_[a_] < 0) != (d_[b_] < 0):
                    u = d_[a_] / (d_[a_] - d_[b_])
                    pts.append((P[t[a_]] + u * (P[t[b_]] - P[t[a_]]))[:2])
        S = np.array(pts)
        if len(S) < 10:
            continue
        c = np.array([mid[0], 0.5 * (L[2, 1] + L[14, 1])])  # a centre inside the face, level with the jaw contour
        ang = np.arctan2(S[:, 0] - c[0], c[1] - S[:, 1])  # 0 = straight ahead (-y): no wrap on either side
        rad = np.linalg.norm(S - c, axis=1)
        for side, sgn, wing, jaw in (("right", -1, 31, 2), ("left", 1, 35, 14)):
            a0 = np.arctan2(L[wing, 0] - c[0], c[1] - L[wing, 1])
            a1 = np.arctan2(L[jaw, 0] - c[0], c[1] - L[jaw, 1])
            a0 = a0 + HOLLOW_FROM * (a1 - a0)  # the outer cheek only: nearer the nose the deepest point is the
            # nasolabial fold, which every face has (3-4 mm on the plain heads)
            lo, hi = min(a0, a1), max(a0, a1)
            bins = np.linspace(lo, hi, 40)
            cont = []
            for b0, b1 in zip(bins[:-1], bins[1:]):
                k = (ang >= b0) & (ang < b1)
                if k.any():
                    cont.append(S[k][np.argmax(rad[k])])  # the outer contour: the farthest crossing at that angle
            cont = np.array(cont)
            if len(cont) < 8:
                continue
            h = ConvexHull(np.r_[cont, c[None]])
            dmin = np.full(len(cont), np.inf)
            for eq in h.equations:  # distance inside each hull facet's line; the deficit is the least of them
                dmin = np.minimum(dmin, -(cont @ eq[:2] + eq[2]))
            out[side] = max(out[side], round(float(dmin.max()) * 1000, 2))
    return out


NECK_AT = 0.35  # the neck's girth is taken this share of the way from the neck joint up to the body's chin


def _neck_girth(tpl: dict) -> float:
    """The neck's girth at ONE level (NECK_AT of the way from the neck joint to the body's own chin vertex), on the
    body's and the bridge's vertices only. (anthro's minimum over the levels up to the chin took the jaw in whenever
    a fit moved the chin: "neck_circ -9 cm" UNINTENDED in every face fit.)"""
    from scipy.spatial import ConvexHull
    P = np.asarray(tpl["P"], float)[: int(tpl["n_body"])]
    zn = float(np.asarray(tpl["J"]["neck"])[2])
    zl = zn + NECK_AT * (float(tpl["chin_mh"]) - zn)
    sh = abs(float(np.asarray(tpl["J"]["shoulder.L"])[0]))
    s = P[(np.abs(P[:, 2] - zl) < 0.004) & (np.abs(P[:, 0]) < 0.6 * sh)][:, :2]
    if len(s) < 4:
        return float("nan")
    h = ConvexHull(s)
    q = s[h.vertices]
    return float(np.linalg.norm(q - np.roll(q, 1, 0), axis=1).sum())


def measures(base: dict) -> dict:
    return state(base)["measures"]


def value(m: dict, name: str) -> float:
    """A measure, or a ratio "a/b"."""
    if "/" in name:
        a, b = name.split("/")
        return m[a.strip()] / m[b.strip()]
    if name not in m:
        raise ValueError(f"humanfit: no measure {name!r} (have {', '.join(m)}; ratios as \"a/b\")")
    return m[name]


def identity(base: dict) -> np.ndarray:
    """The head's GNM identity components as the solver sees them (headfit's 120, sigma units)."""
    from . import headfit
    from . import onemesh_head
    g = headfit._gnm()
    idn = onemesh_head.head_desc(base).get("identity") or {}
    return np.array([float(idn.get(g["names"][i], 0.0)) for i in g["comps"]])


def plausibility(base: dict) -> dict:
    c = identity(base)
    return {"rms_sigma": float(np.sqrt((c ** 2).mean())), "max_sigma": float(np.abs(c).max()),
            "over": int((np.abs(c) > CLIP + 1e-6).sum())}


HOLD_CHEEK = 0.25  # weight of holding the cheeks' fronts in image fits (x 1 / mm): the landmarks (mouth, nose, lips)
# don't see the cheeks, and the identity components that met them filled the cheeks 5 mm (Garrett's pass 2, "jowly")

_CHEEK = {}

NUDGE_CORR = 0.35  # a nudge's correction layer (push_more) may be at most this share of its radius, unless forced
NUDGE_MAX = 0.012  # m: the largest move of one landmark that is still a nudge, unless forced

SLIVER = 0.0015  # m: an edge (a face's longest edge) shorter than this before AND after is a sliver: its stretch ratio
# and its turning over mean nothing. Plain sigma-1 identities (the study's truth heads) read "lids BROKEN x3.4" on
# 0.25 -> 0.9 mm lid edges and "40 faces folded" on sub-mm lid faces, and a correct fit was refused for it.
SLIVER_SQUEEZE = 0.0011  # m: a squeezed edge counts when it was at least this long (a stretched one when it ends >= SLIVER)
GUARD_MM = 0.0001  # m: an edge's length change under this is not a change (integrity against the input)
GUARD_WORSE = 0.08  # a region broken in the input too counts as broken BY the edit when its stretch got this much worse

_CAM0 = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])  # world -> camera for a camera in front (looking +Y)

OUTLINE_W = 0.6  # weight of an outline point against a landmark

STRUCTURE_SOFT = 0.25  # weight of an outline target on the soft mid-cheek (structure mode)
STRUCTURE_HOLD = 1.0   # weight of holding the cheeks' fronts (structure mode)
EAR_RIDE = 2.0   # weight of the ears riding their side as one piece (structure mode)
EAR_FREE = 0.012  # m: holds this close to an ear let go so it can ride (structure mode)


def _gnm_normals(Vg: np.ndarray) -> np.ndarray:
    """Vertex normals of GNM's mesh at positions Vg (GNM's frame: facing +z, y up)."""
    from . import base_identity
    from . import retopo
    q = np.asarray(base_identity._gnm_data()["quads"])
    T = np.r_[q[:, [0, 1, 2]], q[:, [0, 2, 3]]]
    return retopo._vnormals(Vg, T)


OUTLINE_SIGMA = 0.022   # GNM units: the outline warp's reach (a jaw, a cheekbone: no single feature)
OUTLINE_STEP = 0.004    # m: the most an outline point is moved in one round
OUTLINE_HOLD = 0.6      # weight of the features held where they are (eyes, nose, lips, brows) against the outline

HOOD_MAX = 0.005   # m: the most a hooded fold comes down
HOOD_LIDS = (37, 38, 43, 44)  # the upper lids' landmarks: what the hood moves and is fitted on

REGION_K = 60        # identity components a regional fit may use (GNM's first, broadest ones)
REGION_RIDGE = 0.6   # weight of each component's step (per sigma) in a regional fit
REGION_HOLD = 3.0    # weight of holding the face's other landmarks where they are in a regional fit (x 1 / mm)


# ---- pictures: before | after | where it moved ------------------------------------------------------------------
def _faces(tpl):
    Lf, Sf = np.asarray(tpl["L"]), np.asarray(tpl["S"])
    k, out = 0, []
    for n in Sf:
        out.append(Lf[k:k + n])
        k += n
    return out


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("humanfit_integrity", "humanfit_solve", "humanfit_views", "humanfit_sheet")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C427)
