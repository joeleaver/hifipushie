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

Where the code is (split by responsibility, C416): this module holds the constants and the model side (the GNM head,
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
    from . import likeness
    w, h = cam["size"]
    mesh = head["mesh"] if "mesh" in head else _mesh(head)
    out = likeness.render(mesh, cam, (0, 0, w, h), px=max(w, h), brows="mesh" not in head, light=light, passes=passes)
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


def _clay_crop(head, view):
    from . import likeness
    cam, s, o = view["cam"], float(view["scale"]), view.get("origin", (0.0, 0.0))
    w, h = view["img"].size
    box = (o[0], o[1], o[0] + w / s, o[1] + h / s)
    mesh = head["mesh"] if "mesh" in head else _mesh(head)
    out = likeness.render(mesh, cam, box, px=max(w, h), brows="mesh" not in head, passes=True)
    return out[0], out[2]


def _bil(A, x, y):
    H, W = A.shape
    x, y = np.clip(x, 0, W - 1.001), np.clip(y, 0, H - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return (A[y0, x0] * (1 - fx) * (1 - fy) + A[y0, x0 + 1] * fx * (1 - fy) + A[y0 + 1, x0] * (1 - fx) * fy + A[y0 + 1, x0 + 1] * fx * fy)


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
