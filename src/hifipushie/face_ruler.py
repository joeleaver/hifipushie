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
ERR: the validated reader error per measure (spikes/faceruler/validate.py; the notes' "## faceruler")."""
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
        from . import base as basemod, gnm_mm
        g = basemod._gnm_data()
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


# ---- outlines ---------------------------------------------------------------------------------------------------------

def _curve(mask, sigma: float = 1.0):
    """The longest closed / open boundary curve of a mask as a sub-pixel polyline (x, y)."""
    from scipy.ndimage import gaussian_filter
    from skimage import measure
    a = gaussian_filter(np.pad(mask.astype(np.float32), 2), sigma)
    cs = measure.find_contours(a, 0.5)
    if not cs:
        return None
    c = max(cs, key=len)
    return c[:, ::-1] - 2.0


def _resample(P, step):
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    s = np.arange(0, d[-1], step)
    return np.stack([np.interp(s, d, P[:, 0]), np.interp(s, d, P[:, 1])], 1)


def foreground(img, bg=None, thr: float = 22.0):
    """A render's (or a studio photo's) foreground: pixels that differ from the background colour (default: the
    median of the picture's border). The largest connected piece, holes filled."""
    from scipy import ndimage as ndi
    a = np.asarray(img.convert("RGB"), float)
    if bg is None:
        b = np.r_[a[:3].reshape(-1, 3), a[-3:].reshape(-1, 3), a[:, :3].reshape(-1, 3), a[:, -3:].reshape(-1, 3)]
        bg = np.median(b, 0)
    m = np.abs(a - np.asarray(bg, float)).sum(-1) > thr
    lab, n = ndi.label(m)
    if n > 1:
        m = lab == (1 + int(np.argmax(ndi.sum(m, lab, range(1, n + 1)))))
    return ndi.binary_fill_holes(m)


def photo_masks(img, cam, head, thr: float = 30.0, origin=(0.0, 0.0), scale: float = 1.0):
    """A photo in front of a PLAIN background: (the figure's mask, where it is SKIN). Skin = as warm ((R - B) / sum) and
    at least 0.6 x as bright as the face's own skin, sampled at the model's nose bridge and cheeks through the fitted
    camera. Only an outline with skin just inside it is read: hair, cloth and loose strands are not the head's shape."""
    from scipy import ndimage as ndi
    a = np.asarray(img.convert("RGB"), float)
    fg = foreground(img, thr=thr)
    _, PL = _cam_points(cam, np.asarray(head["L"], float)[:68])
    PL = (PL - np.asarray(origin, float)) * scale
    pts = np.r_[PL[27:31], 0.5 * (PL[1:4] + PL[31][None]), 0.5 * (PL[13:16] + PL[35][None])]
    H, W = a.shape[:2]
    r = max(int(0.004 * cam["f"] / cam["t"][2]), 2)
    smp = []
    for x, y in pts:
        if r <= x < W - r and r <= y < H - r:
            smp.append(a[int(y) - r:int(y) + r, int(x) - r:int(x) + r].reshape(-1, 3))
    if not smp:
        return fg, np.zeros_like(fg)
    smp = np.concatenate(smp)
    warm = (a[..., 0] - a[..., 2]) / np.maximum(a.sum(-1), 1.0)
    w0 = float(np.median((smp[:, 0] - smp[:, 2]) / np.maximum(smp.sum(1), 1.0)))
    l0 = float(np.median(smp.mean(1)))
    skin = fg & (warm > 0.45 * w0) & (warm < 2.2 * w0) & (a.mean(-1) > 0.6 * l0)
    return fg, ndi.binary_opening(skin, iterations=2)


def _silhouette_vertices(head, cam):
    """Vertices on the model's silhouette through cam (an edge between a face turned to the camera and one turned
    away), boundary vertices left out."""
    Xc, P = _cam_points(cam, head["V"])
    F = head["F"]
    fn = np.cross(Xc[F[:, 1]] - Xc[F[:, 0]], Xc[F[:, 2]] - Xc[F[:, 0]])
    front = (fn * Xc[F].mean(1)).sum(1) < 0
    has_f = np.zeros(len(Xc), bool)
    has_b = np.zeros(len(Xc), bool)
    has_f[F[front].ravel()] = True
    has_b[F[~front].ravel()] = True
    sil = has_f & has_b & ~head["bnd"]
    return np.where(sil)[0], Xc, P


def _outline_obs(head, view, mask_model, mask_pic, trust=None, curve=None):
    """Offsets (mm, + = the picture's outline lies outside the model's) at steps along the model's outline, each with
    the vertex that makes it. trust: bool picture mask of where the picture's outline is the head's own skin / skull
    (None = everywhere)."""
    from scipy.spatial import cKDTree
    cam = view["cam"]
    s = float(view.get("scale", 1.0))
    cm = _curve(mask_model)
    cp = _curve(mask_pic) if mask_pic is not None else np.asarray(curve, float)
    if cm is None or cp is None or len(cp) < 4:
        return []
    sv, Xc, P = _silhouette_vertices(head, cam)
    o = np.asarray(view.get("origin", (0.0, 0.0)), float)
    Pi = (P - o) * s                                    # model vertices in image px
    mmpx = float(np.median(Xc[sv, 2]) / cam["f"] * 1000.0) / s
    S = _resample(cm, STEP_MM / mmpx)
    if len(S) < 8:
        return []
    T = np.gradient(S, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    N = np.stack([T[:, 1], -T[:, 0]], 1)
    H, W = mask_model.shape
    # outward: the side where the model's mask is empty
    q = np.clip(np.round(S + 2.5 * N).astype(int), 0, [W - 1, H - 1])
    flip = mask_model[q[:, 1], q[:, 0]]
    N[flip] *= -1
    tv = cKDTree(Pi[sv])
    dv, iv = tv.query(S)
    cpd = _resample(cp, 0.25)
    Tp = np.gradient(cpd, axis=0)
    Tp /= np.maximum(np.linalg.norm(Tp, axis=1, keepdims=True), 1e-9)
    tp = cKDTree(cpd)
    out = []
    edge = 4
    for k in range(len(S)):
        if dv[k] > 2.5 / mmpx or not (edge < S[k, 0] < W - edge and edge < S[k, 1] < H - edge):
            continue
        # the picture's outline along the normal: nearest picture-outline point within a narrow cone of the normal
        idx = tp.query_ball_point(S[k], REACH_MM / mmpx)
        if not idx:
            continue
        D = cpd[idx] - S[k]
        along = D @ N[k]
        across = np.abs(D @ T[k])
        j = np.argmin(across + 0.05 * np.abs(along))
        if across[j] > 0.6:
            continue
        qp = cpd[idx[j]]
        if abs(Tp[idx[j]] @ T[k]) < 0.6:               # the picture's outline runs another way there: no match
            continue
        if not (edge < qp[0] < W - edge and edge < qp[1] < H - edge):
            continue
        if mask_pic is not None:      # the same SIDE of the figure: inside the picture's mask just inside the outline,
            qa = np.clip(np.round(qp - 3.0 * N[k]).astype(int), 0, [W - 1, H - 1])     # outside it just outside
            qb = np.clip(np.round(qp + 3.0 * N[k]).astype(int), 0, [W - 1, H - 1])
            if not mask_pic[qa[1], qa[0]] or mask_pic[qb[1], qb[0]]:
                continue             # (a jaw's underside matched to the far side of the neck, a nose to a cheek)
        if trust is not None:
            ok = True
            for back in (3.0, 6.0):       # skin just inside the picture's outline, twice
                qi = np.clip(np.round(qp - back * N[k]).astype(int), 0, [W - 1, H - 1])
                ok &= bool(trust[qi[1], qi[0]])
            if not ok:
                continue
        v = int(sv[iv[k]])
        Jp, mm1 = _proj_jac(cam, head, v)
        out.append({"type": "outline", "view": view["kind"], "o": float(along[j]) * mm1 / s, "J": (N[k] @ Jp) * mm1,
                    "sig": SIG["outline"], "v": v, "p": S[k].tolist(), "n": N[k].tolist(), "q": qp.tolist(),
                    "X": head["V"][v].tolist()})
    return out


# ---- colour features (clay; a dressed render / photo has its own readers) ---------------------------------------------

def _circle(pts):
    A = np.c_[2 * pts, np.ones(len(pts))]
    b = (pts ** 2).sum(1)
    x, *_ = np.linalg.lstsq(A, b, rcond=None)
    return x[:2], float(np.sqrt(max(x[2] + x[:2] @ x[:2], 0)))


def iris_centre(a, p0, r_px):
    """Clay: the PUPIL's centroid near p0 (px; r_px = the iris' radius): the near-black disc at the iris' centre, whole
    under a neutral lid (the iris' own edge is cut by the lids and sits in the socket's shade: its circle read 0.4-1.1
    mm off)."""
    from scipy import ndimage as ndi
    H, W = a.shape[:2]
    R = int(2.6 * r_px)
    x0, y0 = int(round(p0[0])), int(round(p0[1]))
    xa, xb, ya, yb = max(x0 - R, 0), min(x0 + R, W), max(y0 - R, 0), min(y0 + R, H)
    if xb - xa < 6 or yb - ya < 6:
        return None
    lum = a[ya:yb, xa:xb].mean(-1)
    dark = lum < 32.0
    lab, n = ndi.label(dark)
    best, bd = None, 1e9
    for i in range(1, n + 1):
        ys, xs = np.where(lab == i)
        if not (0.05 * r_px ** 2 < len(ys) < 3.0 * r_px ** 2):
            continue
        d = np.hypot(xs.mean() - (x0 - xa), ys.mean() - (y0 - ya))
        if d < bd:
            best, bd = i, d
    if best is None:
        return None
    wgt = np.where(lab == best, np.clip(40.0 - lum, 0, None), 0.0)
    yy, xx = np.mgrid[:lum.shape[0], :lum.shape[1]]
    return np.array([(wgt * xx).sum() / wgt.sum() + xa, (wgt * yy).sum() / wgt.sum() + ya])


def lip_mask(a):
    """Clay: the tinted vermilion (redder than the skin around it)."""
    from scipy import ndimage as ndi
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    ratio = g / np.maximum(r, 1.0)
    return ndi.binary_opening((ratio < 0.83) & (r > 60), iterations=1)


def brow_mask(a):
    """Clay: the drawn brows (dark brown strokes)."""
    return (a.mean(-1) < 95) & (a[..., 0] > a[..., 2] + 8)


def _lip_points(m, box):
    """corners (leftmost / rightmost), top and bottom at the middle column of the lip blob inside box (x0, y0, x1, y1)."""
    from scipy import ndimage as ndi
    x0, y0, x1, y1 = [int(v) for v in box]
    sub = m[max(y0, 0):y1, max(x0, 0):x1]
    lab, n = ndi.label(sub)
    if not n:
        return None
    sub = lab == (1 + int(np.argmax(ndi.sum(sub, lab, range(1, n + 1)))))
    ys, xs = np.where(sub)
    if len(xs) < 30:
        return None
    xl, xr = xs.min(), xs.max()
    out = {"corner_l": [xl - 0.5, ys[xs <= xl + 1].mean()], "corner_r": [xr + 0.5, ys[xs >= xr - 1].mean()]}
    xm = 0.5 * (xl + xr)
    col = np.abs(xs - xm) <= 2
    out["top"] = [xm, ys[col].min() - 0.5]
    out["bottom"] = [xm, ys[col].max() + 0.5]
    return {k: [v[0] + max(x0, 0), v[1] + max(y0, 0)] for k, v in out.items()}


def _colour_obs(head, view, im_model, im_pic):
    """Iris centres, lip points, brow tops: the same reader on the picture and on the model's own clay picture
    (differential: the reader's bias cancels), the Jacobian from the model's vertices that carry the feature."""
    cam = view["cam"]
    kind = view["kind"]
    s = float(view.get("scale", 1.0))
    o = np.asarray(view.get("origin", (0.0, 0.0)), float)
    A, B = np.asarray(im_model.convert("RGB"), float), np.asarray(im_pic.convert("RGB"), float)
    gr, L = head["gr"], head["L"]
    _, PL = _cam_points(cam, L)
    PL = (PL - o) * s
    out = []

    def add(typ, name, pa, pb, idx, w=None, axes=(0, 1), sig=None):
        Jp, mm1 = _proj_jac(cam, head, idx, w)
        ii_ = np.atleast_1d(idx)
        X = ((np.full(len(ii_), 1.0 / len(ii_)) if w is None else np.asarray(w, float))[:, None] * head["V"][ii_]).sum(0)
        for ax in axes:
            out.append({"type": typ, "view": kind, "name": f"{name}.{'xy'[ax]}", "o": float(pb[ax] - pa[ax]) * mm1 / s,
                        "J": Jp[ax] * mm1, "sig": sig or SIG[typ], "p": list(map(float, pa)), "q": list(map(float, pb)),
                        "X": X.tolist()})

    if kind in ("front", "3q"):
        for side in ("left", "right"):
            iv = np.where(gr[f"{side}_eye"] & gr["pupils"])[0]
            ii = np.where(gr[f"{side}_eye"] & gr["irises"])[0]
            Xc, Pv = _cam_points(cam, head["V"][ii])
            p0 = (Pv.mean(0) - o) * s
            r_px = 0.5 * float(np.ptp(Pv[:, 0])) * s / max(np.cos(np.radians(abs(cam.get("yaw", 0.0)))), 0.5)
            ca, cb = iris_centre(A, p0, r_px), iris_centre(B, p0, r_px)
            if ca is not None and cb is not None:
                add("iris", f"iris_{side}", ca, cb, iv)
        # lips
        lo, hi = PL[48:68].min(0), PL[48:68].max(0)
        pad = 0.45 * (hi[0] - lo[0]) + 8
        box = (lo[0] - pad, lo[1] - pad, hi[0] + pad, hi[1] + pad)
        la, lb = _lip_points(lip_mask(A), box), _lip_points(lip_mask(B), box)
        if la and lb:
            # image left = the subject's right in a front view (landmark 48), image right = landmark 54
            ends = sorted([(PL[48, 0], 48), (PL[54, 0], 54)])
            wl = np.where(head["WL"][ends[0][1]] > 0)[0]
            wr = np.where(head["WL"][ends[1][1]] > 0)[0]
            add("lips", "corner_l", la["corner_l"], lb["corner_l"], wl, head["WL"][ends[0][1]][wl], axes=(0,))
            if kind == "front":
                add("lips", "corner_r", la["corner_r"], lb["corner_r"], wr, head["WL"][ends[1][1]][wr], axes=(0,))
            for nm, lm in (("top", 51), ("bottom", 57)):
                wi = np.where(head["WL"][lm] > 0)[0]
                add("lips", nm, la[nm], lb[nm], wi, head["WL"][lm][wi], axes=(1,))
    if kind == "front":
        ba, bb = brow_mask(A), brow_mask(B)
        for lm in (19, 24):
            x = int(round(PL[lm, 0]))
            w = max(int(2.0 * s * cam["f"] / (1000.0 * cam["t"][2])), 3)     # +-2 mm of columns
            mmi = s * cam["f"] / (1000.0 * cam["t"][2])                       # image px per mm
            ta, tb = _brow_top(ba, x, w, PL[lm, 1], mmi), _brow_top(bb, x, w, PL[lm, 1], mmi)
            if ta is not None and tb is not None:
                wi = np.where(head["WL"][lm] > 0)[0]
                add("brows", f"brow_{lm}", [x, ta], [x, tb], wi, head["WL"][lm][wi], axes=(1,))
    if kind == "profile":
        # where the lip colour meets the outline: the reds' top and bottom heights on the profile
        for nm, lm in (("top", 51), ("bottom", 57)):
            ra, rb = _profile_lip(lip_mask(A), PL, nm), _profile_lip(lip_mask(B), PL, nm)
            if ra is not None and rb is not None:
                wi = np.where(head["WL"][lm] > 0)[0]
                add("lips", nm, [0.0, ra], [0.0, rb], wi, head["WL"][lm][wi], axes=(1,))
    return out


def _brow_top(m, x, w, y0, mmi):
    """The top of the brow stroke in columns x +- w: the LOWEST dark run within 22 mm above / 8 mm below the model's
    brow (the hair cap is dark too and comes down to within a centimetre of a high brow: the topmost run was the cap,
    s7_00: brows read +10.6 mm for -5.4)."""
    rows = np.where(m[:, max(x - w, 0):x + w + 1].any(1))[0]
    rows = rows[(rows > y0 - 22 * mmi) & (rows < y0 + 8 * mmi)]
    if not len(rows):
        return None
    runs = np.split(rows, np.where(np.diff(rows) > 2)[0] + 1)
    return float(runs[-1][0])


def _profile_lip(m, PL, which):
    lo, hi = PL[48:68].min(0), PL[48:68].max(0)
    pad = 0.6 * (hi[1] - lo[1]) + 8
    y0, y1 = int(lo[1] - pad), int(hi[1] + pad)
    x0, x1 = int(min(lo[0], hi[0]) - pad), int(max(lo[0], hi[0]) + pad)
    sub = m[max(y0, 0):y1, max(x0, 0):x1]
    rows = np.where(sub.sum(1) >= 2)[0]
    if len(rows) < 4:
        return None
    return float((rows.min() - 0.5 if which == "top" else rows.max() + 0.5) + max(y0, 0))


# ---- observe / solve --------------------------------------------------------------------------------------------------

def hair_vertices(head: dict) -> np.ndarray:
    """Vertices a head of hair hides (the clay's hair cap: outside GNM's face mask, above the ears' bottom, not the
    ears): on a dressed render or a photo the outline there is hair, not the skull."""
    if "hair" in head:
        return head["hair"]
    L, gr = head["L"], head["gr"]
    zcut = 0.5 * (L[1, 2] + L[15, 2])
    return (~gr["hockey_mask"]) & (~gr["ears"]) & (head["V"][:, 2] > zcut - 0.005)


def observe(head: dict, views: list, outline: bool = True, colour: bool = True) -> list:
    """Every observation of the pictures against the model: [{"type", "view", "o" mm, "J" (K,) mm per comp, "sig"}].
    A view with "hair": True drops the outline where hair would hide the skull (hair_vertices)."""
    obs = []
    for view in views:
        cam = view["cam"]
        im_m, ps = clay(head, cam, passes=True) if "scale" not in view else _clay_crop(head, view)
        if outline:
            mp, cv = view.get("mask"), view.get("outline")
            if mp is None and cv is None and view.get("style", "clay") != "photo":
                mp = foreground(view["img"])
            if cv is not None:      # image px of the picture's own outline (a photo's skin edge), as (x, y) points
                cv = (np.asarray(cv, float) - np.asarray(view.get("origin", (0.0, 0.0)), float)) * float(view.get("scale", 1.0))
            oo = [] if (mp is None and cv is None) else _outline_obs(
                head, view, ps["part"] >= 0, None if mp is None else np.asarray(mp, bool), view.get("trust"), cv)
            if view.get("hair"):
                hv = hair_vertices(head)
                oo = [ob for ob in oo if not hv[ob["v"]]]
            if view.get("face_only") and "face" in head:      # a photo: the neck and shoulders are a pose, not the head
                oo = [ob for ob in oo if head["face"][ob["v"]]]
            obs += oo
        if colour and view.get("style", "clay") == "clay" and view.get("colour", True):
            obs += _colour_obs(head, view, im_m, view["img"])
        if view["kind"] != "front" and view.get("limbus", True) and ("eye_X" in head or head.get("kind") == "gnm"):
            view["_part"] = ps["part"]
            if "_valid" not in view:
                from scipy import ndimage as ndi
                fg = view["mask"] if view.get("mask") is not None else foreground(view["img"])
                view["_valid"] = ndi.binary_erosion(np.asarray(fg, bool), iterations=3)
            obs += _limbus_obs(head, view)
        obs += list(view.get("extra_obs") or [])
    return obs


def _clay_crop(head, view):
    from . import likeness
    cam, s, o = view["cam"], float(view["scale"]), view.get("origin", (0.0, 0.0))
    w, h = view["img"].size
    box = (o[0], o[1], o[0] + w / s, o[1] + h / s)
    mesh = head["mesh"] if "mesh" in head else _mesh(head)
    out = likeness.render(mesh, cam, box, px=max(w, h), brows="mesh" not in head, passes=True)
    return out[0], out[2]


def cam_moved(cam: dict, dx=0.0, dy=0.0, sc=0.0, roll=0.0, yaw=0.0, pitch=0.0) -> dict:
    """A fitted camera moved by the ruler's camera freedoms: mm of shift (x, y), % of scale, degrees of roll, of YAW
    (the head turned about the vertical through the camera's centre point) and of PITCH (nodded about the picture's
    horizontal)."""
    from . import humanfit
    c = dict(cam)
    c["t"] = [c["t"][0] + dx * 1e-3, c["t"][1] + dy * 1e-3, c["t"][2]]
    c["f"] = c["f"] * (1 + 0.01 * sc)
    r = list(c.get("r", [0.0, 0.0, 0.0]))
    c["r"] = [r[0], r[1], r[2] + float(np.radians(roll))]
    if yaw:
        c["yaw"] = float(c.get("yaw", 0.0)) + float(yaw)
    if pitch:
        from scipy.spatial.transform import Rotation
        c["r"] = (Rotation.from_rotvec([float(np.radians(pitch)), 0.0, 0.0]) * Rotation.from_matrix(humanfit._rotvec(np.asarray(c["r"], float)))).as_rotvec().tolist()
    return c


def cam_sd_of(cam_sd, kind):
    """cam_sd per view kind: a tuple (every view the same) or {"front": .., "3q": .., "profile": ..}."""
    return tuple(cam_sd[kind]) if isinstance(cam_sd, dict) else tuple(cam_sd)


def _cam_columns(obs, views, cam_sd):
    """Nuisance columns for a camera that was FITTED (its shift, scale, roll, and with 6 numbers its yaw and pitch, are
    not known exactly): per view the observation's change per mm of shift (x, y), per 1 % of scale, per degree of roll
    / yaw / pitch. Yaw matters for depth off the midline: in a profile 1 degree moves the eye (30 mm from the midline)
    0.5 mm along the picture while the profile line itself stays."""
    cols, pri = [], []
    for view in views:
        k = view["kind"]
        sc = float(view.get("scale", 1.0))
        c = (np.asarray(view["cam"]["size"], float) / 2 - np.asarray(view.get("origin", (0.0, 0.0)), float)) * sc
        mm = float(view["cam"]["t"][2]) / view["cam"]["f"] * 1000.0 / sc
        sds = cam_sd_of(cam_sd, k)
        iv = [i for i, ob in enumerate(obs) if ob["view"] == k and "X" in ob]
        rot = {}
        if len(sds) > 4 and iv:       # the rotations: finite differences of each observation's own 3D point
            X = np.array([obs[i]["X"] for i in iv], float)
            p0 = _cam_points(view["cam"], X)[1]
            for j, key in ((4, "yaw"), (5, "pitch")):
                d = (_cam_points(cam_moved(view["cam"], **{key: 0.5}), X)[1] - p0) / 0.5 * sc * mm     # mm per degree
                rot[j] = dict(zip(iv, d))
        for j, (nm, sd) in enumerate(zip(("dx", "dy", "scale", "roll", "yaw", "pitch"), sds)):
            col = np.zeros(len(obs))
            for i, ob in enumerate(obs):
                if ob["view"] != k:
                    continue
                if j >= 4:
                    if i not in rot[j]:
                        continue
                    d = rot[j][i]
                    col[i] = d @ np.asarray(ob["n"]) if "n" in ob else (d[0] if ob["name"].endswith(".x") else d[1])
                    continue
                p = (np.asarray(ob["p"], float) - c) * mm                # mm from the picture's centre
                d = {0: np.array([1.0, 0.0]), 1: np.array([0.0, 1.0]), 2: 0.01 * p,
                     3: np.radians(1.0) * np.array([-p[1], p[0]])}[j]
                if "n" in ob:
                    col[i] = d @ np.asarray(ob["n"])
                else:
                    col[i] = d[0] if ob["name"].endswith(".x") else d[1]
            cols.append(col)
            pri.append(sd)
    return np.array(cols).T, np.array(pri)


def solve(obs: list, head: dict, tau: float = TAU, span: bool = False, cam_sd=None, views=None, huber: float = 2.5,
          weights: dict | None = None, done=None, cam_done=None, prior_off=None) -> dict:
    """The gaps of the 23 measures from the observations. Default: the most likely identity change dc (prior N(0,
    tau^2) per comp) and the measures read off it, with posterior sd. span=True: least squares over the 23 `mm:` moves
    alone. cam_sd = (shift mm, shift mm, scale %, roll deg): the camera was fitted, so much of each is unknown."""
    from . import gnm_mm
    names = list(gnm_mm.NAMES)
    Jm = head["Jm"]
    o = np.array([ob["o"] for ob in obs])
    J = np.array([ob["J"] for ob in obs])
    sig = np.array([ob["sig"] * (weights or {}).get(ob["type"], 1.0) for ob in obs])
    K = J.shape[1]
    if span:
        D = np.array([gnm_mm.direction(n) for n in names]).T          # (170, 23)
        Jx, pri = J @ D, np.array([10.0 * s for s in gnm_mm.sd().values()])
    else:
        Jx, pri = J, np.full(K, tau)
    nc = 0
    if cam_sd is not None:
        C, cp = _cam_columns(obs, views, cam_sd)
        Jx, pri, nc = np.c_[Jx, C], np.r_[pri, cp], C.shape[1]
        if cam_done is not None:       # the cameras were already moved this much: the prior is on the whole of it
            cam_m0 = -np.asarray(cam_done, float).ravel()
    m0 = np.zeros(len(pri))
    if nc and cam_done is not None:
        m0[-nc:] = cam_m0
    if done is not None and not span:      # a later round: the prior is on the WHOLE change (done + this step)
        m0[:K] = -np.asarray(done, float)
    if prior_off is not None and not span:  # the model already stands this far from the prior's centre (its start
        m0[:K] -= np.asarray(prior_off, float)   # class's mean): the prior is on the WHOLE identity, across calls
    nn = 0                                 # NUISANCE columns an observation brings itself ({"nu": {name: value}}:
    keys = sorted({k for ob in obs for k in (ob.get("nu") or {})})   # a shading read's albedo / exposure field per view)
    if keys:
        Cn = np.array([[(ob.get("nu") or {}).get(k, 0.0) for k in keys] for ob in obs], float)
        Jx, pri, m0, nn = np.c_[Jx, Cn], np.r_[pri, np.full(len(keys), NU_SD)], np.r_[m0, np.zeros(len(keys))], len(keys)
    w = 1.0 / sig ** 2
    for _ in range(3):
        A = (Jx * w[:, None]).T @ Jx + np.diag(1.0 / pri ** 2)
        Ai = np.linalg.inv(A)
        th = Ai @ (Jx.T @ (w * o) + m0 / pri ** 2)
        r = (o - Jx @ th) / sig
        w = 1.0 / sig ** 2 * np.minimum(1.0, huber / np.maximum(np.abs(r), 1e-9))
    n1 = len(th) - nc - nn
    if span:
        g, cov = th[:n1], Ai[:n1, :n1]
        dc = D @ g
    else:
        dc = th[:n1]
        g, cov = Jm @ dc, Jm @ Ai[:n1, :n1] @ Jm.T
        if done is not None:          # the gap of the WHOLE change (earlier rounds + this one)
            g = Jm @ (np.asarray(done, float) + dc)
    err = np.sqrt(np.maximum(np.diag(cov), 0))
    err = np.hypot(ERR_POST * err, [ERR[n] for n in names])
    sd = gnm_mm.sd()
    rows = []
    for i, n in enumerate(names):
        prior = np.sqrt(2.0) * tau * sd[n] if not span else np.inf
        rows.append({"measure": n, "current": head["measures"][n], "gap": float(g[i]), "sd": float(g[i] / sd[n]),
                     "err": float(err[i]), "read": float(max(0.0, 1 - (err[i] / (tau * sd[n])) ** 2)) if not span else 1.0,
                     "view": gnm_mm.SEE[n][0], "see": gnm_mm.SEE[n][1]})
    rows.sort(key=lambda r: -abs(r["sd"]))
    full = ERR_POST ** 2 * cov + np.diag([ERR[n] ** 2 for n in names])
    return {"dc": dc, "gaps": rows, "n": len(obs), "rms": float(np.sqrt(np.mean(r ** 2))),
            "cam": th[n1:n1 + nc].tolist() if nc else None, "cov": full, "names": names,
            "cam_post": np.sqrt(np.maximum(np.diag(Ai)[n1:n1 + nc], 0)).tolist() if nc else None}


def read(head: dict, views: list, rounds: int = 3, **kw) -> dict:
    """The ruler: the pictures against the model, `rounds` Gauss-Newton rounds (the outline's maker and normal are
    re-taken on the moved head: one round is off by the step's curvature when the gap is large). Gaps are the measures
    of the fitted head minus the model's."""
    from . import gnm_mm
    if kw.get("span"):
        rounds = 1
    make = head.get("rebuild") or (lambda c: gnm_head(c))
    done = np.zeros(head["B"].shape[0])
    cur = head
    views = [dict(v) for v in views]
    free = kw.get("cam_sd") is not None
    ncam = len(cam_sd_of(kw["cam_sd"], views[0]["kind"])) if free else 4
    cam_done = np.zeros((len(views), ncam))
    for k in range(rounds):
        for v in views:              # per-view extra observations follow the moved head and camera
            if v.get("extra"):
                v["extra_obs"] = v["extra"](cur, v)
        obs = observe(cur, views)
        if not obs:
            raise ValueError("face_ruler: nothing could be read (no outline, no feature) in these pictures")
        out = solve(obs, cur, views=views, done=done if k else None, cam_done=cam_done if (free and k) else None, **kw)
        done = done + out["dc"]
        if free:                     # the fitted cameras are refined too: the next round reads through the moved ones
            th = np.asarray(out["cam"], float).reshape(len(views), ncam)
            lim = 2.5 * np.array([cam_sd_of(kw["cam_sd"], v["kind"]) for v in views], float)   # never past 2.5 sd of the fit
            th = np.clip(cam_done + th, -lim, lim) - cam_done
            cam_done += th
            for v, t_ in zip(views, th):
                v["cam"] = cam_moved(v["cam"], *t_)
        if k + 1 < rounds:
            cur = make(head["c"] + done)
    out["cam_done"], out["views"] = cam_done.tolist(), views
    if free and out.get("cam_post") is not None:
        out["cam_post"] = np.asarray(out["cam_post"], float).reshape(len(views), ncam).tolist()
    if rounds > 1 and head.get("kind") == "gnm":
        fin = gnm_head(head["c"] + done)
        sd = gnm_mm.sd()
        for r in out["gaps"]:
            r["gap"] = fin["measures"][r["measure"]] - head["measures"][r["measure"]]
            r["current"], r["sd"] = head["measures"][r["measure"]], r["gap"] / sd[r["measure"]]
        out["gaps"].sort(key=lambda r: -abs(r["sd"]))
    for r in out["gaps"]:
        r["current"] = head["measures"][r["measure"]]
    out["dc"], out["obs"] = done, obs
    out["orbit"] = orbit_rows(out, head)
    return out


def orbit_rows(res: dict, head: dict) -> list:
    """The orbit as a side view shows it (gnm_mm.ORBIT_SEEN: each a combination of the measures): [{"row", "current",
    "gap", "err", "sd" (the row's population sd), "read"}], the error from the solve's covariance (the cameras' yaw
    included when it was left free)."""
    from . import gnm_mm
    names = list(res["names"])
    g = {r["measure"]: r["gap"] for r in res["gaps"]}
    J = gnm_mm.jacobian()
    sp = gnm_mm._space()
    cur = gnm_mm.orbit(sp["T"] + np.tensordot(np.asarray(head["c"], float), sp["IB"], 1))
    out = []
    for row, comb in gnm_mm.ORBIT_SEEN.items():
        a = np.zeros(len(names))
        for k, w in comb.items():
            a[names.index(k)] = w
        gap = float(sum(w * g[k] for k, w in comb.items()))
        err = float(np.sqrt(max(a @ res["cov"] @ a, 0.0)))
        psd = float(np.linalg.norm(a @ J[:len(names)]))
        out.append({"row": row, "current": float(cur[row]), "gap": gap, "err": err, "sd": psd,
                    "read": float(max(0.0, 1 - (err / psd) ** 2))})
    return out


ORBIT_SAY = {"apex_behind_nasion": "the corneal apex behind the nasion (+ = deeper-set)",
             "brow_over_apex": "the brow ridge ahead of the cornea (+ = more overhang)",
             "apex_ahead_of_side_rim": "the cornea ahead of the orbit's side rim (+ = more eye shows from the side)",
             "apex_ahead_of_cheek": "the cornea ahead of the cheek under the eye (- = the cheek leads)",
             "brows_over_eyes": "the brow's height over the pupil",
             "brow_hollow": "the hollow under the brow (+ = sunken)"}


def orbit_text(rows: list) -> str:
    """The orbit's table: what a side view shows, model -> picture, +- the reader's error."""
    out = ["ORBIT (eye depth; a big-mass decision: set it BEFORE any lid work)   model -> picture   gap +-err"]
    for r in rows:
        flag = "" if abs(r["gap"]) > 2 * r["err"] else "  (inside the reader's error)"
        if r["read"] < 0.75:
            flag = "  NOT READ (these pictures do not pin it: the population's guess)"
        out.append(f"  {r['row']:24s} {r['current']:6.1f} -> {r['current'] + r['gap']:6.1f} mm  {r['gap']:+5.1f} +-{r['err']:.1f} "
                   f"(sd {r['sd']:.1f})  {ORBIT_SAY[r['row']]}{flag}")
    return "\n".join(out)


# ---- the limbus in a turned view (orbit, 2026-10-11) ------------------------------------------------------------------

def limbus_model(head: dict, iris_mm: float | None = None) -> list:
    """The model's two limbus circles in 3D: [{"X" centre, "r", "fwd", "lat" (unit, toward that eye's temple), "up",
    "B" (K, 3): the centre's move per identity comp}], the subject's right eye first. iris_mm: the iris' diameter to
    draw (the PICTURE's, read on the front view; default the model's own)."""
    out = []
    if head.get("kind") == "gnm":
        gr, V = head["gr"], head["V"]
        fwd, up = np.array([0.0, -1.0, 0.0]), np.array([0.0, 0.0, 1.0])
        for side in ("right", "left"):
            ids = np.where(gr[f"{side}_eye"] & gr["irises"])[0]
            P = V[ids] - V[ids].mean(0)
            rad = np.linalg.norm(P - np.outer(P @ fwd, fwd), axis=1)
            rim = ids[rad > 0.92 * rad.max()]
            X = V[rim].mean(0)
            out.append({"X": X, "r": float(rad[rad > 0.92 * rad.max()].mean()) if iris_mm is None else iris_mm / 2000.0,
                        "fwd": fwd, "up": up, "lat": np.array([np.sign(X[0] - head["L"][27, 0]), 0.0, 0.0]),
                        "B": head["B"][:, rim].astype(np.float64).mean(1)})
        return out
    from . import humanfit
    st = humanfit.state(head["spec"]["base"])
    ht = st["head"]
    fwd = np.asarray(ht.get("forward", [0, -1, 0]), float)
    r = float(ht["eye_r"])
    ri = 0.51 * 0.985 * r
    drawn = ((head["spec"].get("skin") or {}).get("eyes") or {}).get("iris_size")
    if drawn:
        ri = 0.5 * float(drawn)
    if iris_mm:
        ri = iris_mm / 2000.0
    up = np.array([0.0, 0.0, 1.0]) - fwd * fwd[2]
    up /= np.linalg.norm(up)
    xs = [float(e[0]) for e in head["eye_X"]]
    for j in (int(np.argmin(xs)), int(np.argmax(xs))):
        c = np.asarray(head["eye_X"][j], float)
        lat = np.cross(up, fwd) * (1.0 if j == int(np.argmax(xs)) else -1.0)
        lat = lat * np.sign(lat[0] * (c[0] - np.mean(xs)) + 1e-12) * 1.0
        out.append({"X": c + fwd * np.sqrt(max(0.985 ** 2 * r * r - ri * ri, 0.0)), "r": ri, "fwd": fwd, "up": up, "lat": lat,
                    "B": np.asarray(head["eye_B"][j], float)})
    return out


def _lum(img):
    """The picture as WHITENESS (the least of R, G, B; 0..1): the sclera is the only white thing round an eye (skin's
    blue is ~0.6 of its red), so sclera -> iris is the strongest step and skin -> lash a weaker one."""
    a = np.asarray(img.convert("RGB"), float) / 255.0
    return a.min(-1)


def _bil(A, x, y):
    H, W = A.shape
    x, y = np.clip(x, 0, W - 1.001), np.clip(y, 0, H - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return (A[y0, x0] * (1 - fx) * (1 - fy) + A[y0, x0 + 1] * fx * (1 - fy) + A[y0 + 1, x0] * (1 - fx) * fy + A[y0 + 1, x0 + 1] * fx * fy)


def limbus_read(lum, cam, lb: dict, origin=(0.0, 0.0), scale: float = 1.0, reach_mm: float = 7.0, far: bool = False,
                part=None, valid=None) -> dict | None:
    """One eye's limbus in a picture, near where the model's is: the shift (picture px) of the model's projected limbus
    circle that puts its side arcs on the picture's sclera -> iris edge (bright outside, dark inside; +-40 deg about the
    eye line, the lids cover the rest). Turned away from the camera the circle is a thin ellipse: the edge is then read
    ALONG THE EYE'S AXIS at the side arc nearer the camera (in a profile the iris shows through the cornea in front of
    the limbus' plane, the sclera lies behind it), and the far (nose-side) arc is used only when the disc is still
    open (cos > 0.45). -> {"d": (dx, dy) px, "p": the model's centre px, "q": the picture's, "score", "sharp", "open"}
    or None when the eye faces away. part: the model's own part picture through this camera (likeness.render's pass:
    >= 1 = eyeball): an arc the MODEL hides behind the nose bridge or a lid (under 60 % of it on the eyeball) is not
    read, and no read at all without the arc nearer the camera (a 45 deg view hides most of the far eye)."""
    from . import humanfit
    Rc = humanfit._cam_rot(cam)
    X, r, fwd, up, lat = lb["X"], lb["r"], lb["fwd"], lb["up"], lb["lat"]
    eye_c = np.asarray(cam["centre"], float) - Rc.T @ np.asarray(cam["t"], float)
    to = eye_c - X
    to /= np.linalg.norm(to)
    op = float(to @ fwd)                              # how open the disc is to the camera (1 = face on)
    if op < -0.05 or (far and op < FAR_OPEN):
        return None
    near_side = 1.0 if (to @ lat) >= 0 else -1.0      # which side arc is nearer the camera (+ = temple)
    th = np.radians(np.arange(-40, 41, 10.0))
    pin, pout, arc = [], [], []
    for sg in (1.0, -1.0):
        if sg != near_side and op < 0.45:
            continue
        if part is not None:
            tv = th[np.abs(th) < 0.4]            # (+-20 deg: the lids cover the arc's ends on any eye)
            Pa = X + r * 0.9 * (sg * np.cos(tv)[:, None] * lat + np.sin(tv)[:, None] * up)
            qa = np.round((_cam_points(cam, Pa)[1] - np.asarray(origin, float)) * scale).astype(int)
            ok = (qa[:, 0] >= 0) & (qa[:, 1] >= 0) & (qa[:, 0] < part.shape[1]) & (qa[:, 1] < part.shape[0])
            seen = np.mean([part[y, x] >= 1 for x, y in qa[ok]]) if ok.any() else 0.0
            if seen < 0.5:
                if sg == near_side or far:     # the FAR eye is read only whole (both arcs on the eyeball): with one arc
                    return None                # behind the bridge it latched onto lashes / the outline (3 of 8, 2.6-5.8 mm)
                continue
        for a in th:
            arc.append(sg)
            rad = sg * np.cos(a) * lat + np.sin(a) * up
            P = X + r * rad
            ax = (0.0007 * (1 - op)) * fwd if sg == near_side else 0.0 * fwd
            pin.append(P - 0.0009 * rad * max(op, 0.0) - 0.0002 * rad + ax)
            pout.append(P + 0.0009 * rad * max(op, 0.0) + 0.0002 * rad - ax)
    o = np.asarray(origin, float)
    qi = (_cam_points(cam, np.array(pin))[1] - o) * scale
    qo = (_cam_points(cam, np.array(pout))[1] - o) * scale
    pc = (_cam_points(cam, X[None])[1][0] - o) * scale
    mmpx = float(((X - np.asarray(cam["centre"], float)) @ Rc.T + np.asarray(cam["t"], float))[2] / cam["f"] * 1000.0) / scale
    from scipy.ndimage import gaussian_filter
    Ls = gaussian_filter(lum, max(0.15 / mmpx, 0.6))

    arc = np.array(arc)
    two = len(set(arc.tolist())) == 2

    Vd = None if valid is None else gaussian_filter(np.asarray(valid, np.float32), 1.0)

    def score(dx, dy):
        xo, yo = qo[:, 0][None] + dx[:, None], qo[:, 1][None] + dy[:, None]
        st = _bil(Ls, xo, yo) - _bil(Ls, qi[:, 0][None] + dx[:, None], qi[:, 1][None] + dy[:, None])
        st = np.clip(st, -0.08, 0.3)
        if Vd is not None:      # the "sclera" side must be on the figure: a white backdrop past the far eye's lashes is not
            st = np.where(_bil(Vd, xo, yo) > 0.9, st, -0.08)
        if not two:
            return st.mean(1)
        # BOTH side arcs must sit on an edge: one arc on a strong edge (the far eye's sclera against the nose, a lash
        # line) scored as well as the limbus (3 of 8 far eyes read 2.6-5.8 mm off)
        a, b = st[:, arc > 0].mean(1), st[:, arc < 0].mean(1)
        return 0.5 * (a + b) - 0.5 * np.maximum(LIMBUS_MIN - np.minimum(a, b), 0.0)
    R = reach_mm / mmpx
    best = None
    for step, span, c0 in ((0.3 / mmpx, R, np.zeros(2)), (0.06 / mmpx, 0.45 / mmpx, None)):
        c0 = best[1] if c0 is None else c0
        g = np.arange(-span, span + 1e-9, step)
        DX, DY = np.meshgrid(c0[0] + g, c0[1] + g)
        S = score(DX.ravel(), DY.ravel()) - 0.0015 * ((DX.ravel() ** 2 + DY.ravel() ** 2) * mmpx ** 2) / 10.0
        i = int(np.argmax(S))
        best = (float(S[i]), np.array([DX.ravel()[i], DY.ravel()[i]]), S.reshape(DX.shape), g)
    sc, d, S, g = best
    # how much better than the next best place 1.5+ mm away (a lash line, the other limbus): the read's sharpness
    g0 = np.arange(-R, R + 1e-9, 0.3 / mmpx)
    DX, DY = np.meshgrid(g0, g0)
    S0 = score(DX.ravel(), DY.ravel())
    away = np.hypot(DX.ravel() - d[0], DY.ravel() - d[1]) * mmpx > 1.5
    sharp = float(sc - S0[away].max()) if away.any() else 0.0
    f2 = (_cam_points(cam, (X + 0.001 * fwd)[None])[1][0] - o) * scale - pc      # the picture's direction of "forward"
    f2 = f2 / max(np.linalg.norm(f2), 1e-9)
    if op < 0.5:      # a side view: the reader puts the edge LIMBUS_SIDE_BIAS mm forward of the model's own limbus
        d = d - LIMBUS_SIDE_BIAS / mmpx * f2 * (1.0 if LIMBUS_SIDE_BIAS else 0.0)
    return {"d": d, "p": pc, "q": pc + d, "score": sc, "sharp": sharp, "open": op, "mmpx": mmpx, "fwd": f2}


FAR_OPEN = 0.8           # the far eye is read only in views turned under ~37 deg: at 45 it is half behind the bridge and, on a head
                         # that is not the model's, read 2-4.6 mm off (5 dressed pairs) even with both arcs on the model's eyeball
LIMBUS_MIN = 0.03        # a limbus read under this edge contrast (luminance 0..1), or no better than another place, is dropped
# mm: in a side view (the disc under half open) the reader puts the edge this far FORWARD of the model's own limbus
# (spikes/orbit/oval.py limbus: 16 dressed profile pictures of 8 known heads, +0.40, sd 0.18; a 3/4's near eye: +0.09,
# sd 0.18, left alone). On a PHOTO the cornea's dome lies over that edge: unvalidated there, so the side read's sigma
# is 0.5 mm, not the renders' 0.2.
LIMBUS_SIDE_BIAS = 0.4
SIG_LIMBUS_SIDE = (0.5, 0.9)


def _limbus_obs(head, view, iris_mm=None):
    """The limbus of each eye that shows in a TURNED view (3/4: both; profile: the near one): where the picture has it
    against where the model has it, moving with the model's eye centres. Triangulated by the solve itself: the front
    picture gives each eye's place across the face, a turned one its depth; the camera's yaw moves the two eyes
    opposite ways, so both eyes of a 3/4 view pin depth without it, the one eye of a profile does not."""
    cam = view["cam"]
    lum = view.get("_lum")
    if lum is None:
        lum = view["_lum"] = _lum(view["img"])
    lbs = limbus_model(head, iris_mm or view.get("iris_mm"))
    from . import humanfit
    Rc = humanfit._cam_rot(cam)
    eye_c = np.asarray(cam["centre"], float) - Rc.T @ np.asarray(cam["t"], float)
    dist = [float(np.linalg.norm(lb["X"] - eye_c)) for lb in lbs]
    out = []
    for j, lb in enumerate(lbs):
        rd = limbus_read(lum, cam, lb, view.get("origin", (0.0, 0.0)), float(view.get("scale", 1.0)), far=dist[j] > min(dist) + 1e-6,
                         part=view.get("_part"), valid=view.get("_valid"))
        if rd is None or rd["score"] < LIMBUS_MIN or rd["sharp"] <= 0.0:
            continue
        Jp, mm1 = _proj_jac_pt(cam, lb["X"], lb["B"])
        s = float(view.get("scale", 1.0))
        for ax in (0, 1):
            out.append({"type": "limbus", "view": view["kind"], "name": f"limbus_{'rl'[j]}.{'xy'[ax]}", "o": float(rd["d"][ax]) * mm1 / s,
                        "J": Jp[ax] * mm1, "sig": (SIG_LIMBUS if rd["open"] >= 0.5 else SIG_LIMBUS_SIDE)[ax], "p": list(map(float, rd["p"])), "q": list(map(float, rd["q"])),
                        "X": list(map(float, lb["X"])), "score": rd["score"], "sharp": rd["sharp"], "open": rd["open"]})
    return out


def text(rows: list, top: int = 0, floor: float = 0.0) -> str:
    """The ruler's table: one line per measure, target - current, the reader's error, the move that closes it."""
    out = ["measure            target - current   +-err   move that closes it          what + looks like"]
    for r in rows[: top or None]:
        if abs(r["gap"]) < floor:
            continue
        mv = '"mm:%s": %+.1f' % (r["measure"], r["gap"])
        flag = "" if abs(r["gap"]) > 2 * r["err"] else "  (inside the reader's error)"
        if r.get("read", 1.0) < 0.75:      # the error is over half the population's sd
            flag = "  NOT READ (these pictures do not show it: the number is the population's guess)"
        out.append(f"{r['measure']:18s} {r['gap']:+6.1f} mm ({r['sd']:+.1f} sd) +-{r['err']:.1f}  {mv:28s} "
                   f"[{r['view']}] {r['see']}{flag}")
    return "\n".join(out)


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


def model_head(spec: dict, c=None, kappa=None) -> dict:
    """A block-in model (the one human mesh, GNM's head on it) as the ruler's model: the whole mesh for the picture's
    mask, the head's vertices with their move per GNM identity comp (as humanfit._silhouette: the head's carry and the
    stitch's fade), the measures of its GNM identity (gnm_mm, GNM's own mm). c: another identity (170) on the same model."""
    import copy
    from . import base as basemod, blockin as bi, gnm_mm, headfit, humanfit, likeness, onemesh
    if c is not None:
        spec = copy.deepcopy(spec)
        bi.set_identity(spec, c)
    st = humanfit.state(spec["base"])
    mesh = likeness.model_mesh_from_state(st)
    tpl, carry = st["tpl"], st["head"]["carry"]
    P = np.asarray(tpl["P"], float)
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
    fade = np.asarray(onemesh.asset()["g_fade"], float)
    hv = (gid >= 0) & (fade[np.maximum(gid, 0)] > 0.3)
    if "mh" not in _C:
        g = basemod._gnm_data()
        names = [str(n) for n in g["identity_names"]]
        comps = [i for i, n in enumerate(names) if n.startswith("head")][:170]
        gg = _gnm()
        T, gr, sp = gg["sp"]["T"], gg["gr"], gg["sp"]
        Lt = sp["WL"] @ T
        ycut = 0.5 * (Lt[1, 1] + Lt[15, 1])
        from . import humanmacro as hm
        face = gr["hockey_mask"].copy()
        face[np.asarray(hm.space()["sets"]["under_chin"], int)] = True
        IBh = np.asarray(g["vertex_identity_basis"])[comps].astype(np.float32)
        _C["mh"] = {"face": face, "LB": np.einsum("lv,kvc->klc", sp["WL"], IBh.astype(np.float64)),
                    "IB": IBh,
                    "JB": np.array([g["joint_identity_basis"][i][2:4] for i in comps], float),
                    "hair": (~gr["hockey_mask"]) & (~gr["ears"]) & (T[:, 1] > ycut - 0.005)}
    mh = _C["mh"]
    R, sc = np.asarray(carry["R"], float), float(carry["s"])
    idx = np.where(hv)[0]
    jm = mh["JB"].mean(1, keepdims=True)
    B = np.zeros((170, len(P), 3), np.float32)
    Bh = sc * (mh["IB"][:, gid[idx]].astype(np.float64) - jm) @ R.T * fade[gid[idx]][None, :, None]
    # How much of GNM's own move the model's head really makes (the one mesh blends, stitches and re-seats the head):
    # measured once per model on one fixed identity step, as the slope of the head's real vertex moves on the basis'
    # (0.85-0.89 on the gk_s models; TRIED and wrong: taking each comp's uniform scaling out, "the head's size comes
    # from the body": the outline's residual tripled).
    if kappa is None:
        dlt = 1.2 * np.sin(1.7 * np.arange(170) + 0.3) / np.sqrt(85.0) * np.sqrt(170.0) / 6.0
        sp2 = copy.deepcopy(spec)
        bi.set_identity(sp2, bi.identity(spec) + dlt)
        P2 = np.asarray(humanfit.state(sp2["base"])["tpl"]["P"], float)
        a_, b_ = (P2[idx] - P[idx]).ravel(), np.tensordot(dlt, Bh, 1).ravel()
        kappa = float(a_ @ b_ / max(b_ @ b_, 1e-18))
        kres = float(np.linalg.norm(a_ - kappa * b_) / max(np.linalg.norm(a_), 1e-12))
    else:
        kres = None
    Bh = kappa * Bh
    B[:, idx] = Bh.astype(np.float32)
    F = np.asarray(mesh["F"])
    cid = bi.identity(spec)
    Vg = _gnm()["sp"]["T"] + np.tensordot(cid, _gnm()["sp"]["IB"], 1)
    r = gnm_mm.readers(Vg)
    hair = np.zeros(len(P), bool)
    hair[idx] = mh["hair"][gid[idx]]
    # the two eye centres (st L 68, 69) and their bases: paired with GNM's eye joints by side
    g0 = headfit._gnm()
    eyeB = kappa * sc * (mh["JB"] - jm) @ R.T               # (170, 2, 3)
    off = sc * (np.asarray(g0["J0"], float)[:2] - np.asarray(g0["J0"], float)[:2].mean(0)) @ R.T
    E = np.asarray(st["L"], float)[68:70]
    order = [int(np.argmin(np.linalg.norm(off - (e - E.mean(0)), axis=1))) for e in E]
    face = np.zeros(len(P), bool)
    face[idx] = mh["face"][gid[idx]]
    LB = kappa * sc * (mh["LB"] - jm) @ R.T                  # (170, 68, 3): the 68 landmarks' moves
    return {"face": face, "LB": LB, "c": cid, "V": P, "F": F[hv[F].all(1)], "B": B, "bnd": np.zeros(len(P), bool), "mesh": mesh, "L": st["L"],
            "Jm": gnm_mm.jacobian()[:len(gnm_mm.NAMES)], "measures": {n: float(r[n]) for n in gnm_mm.NAMES},
            "kind": "model", "hair": hair, "spec": spec, "eye_X": E, "eye_B": [eyeB[:, j] for j in order],
            "kappa": kappa, "kappa_res": kres, "rebuild": lambda c2: model_head(spec, c2, kappa), "gid": gid}


def _iris_obs(head, view, eyes_pic):
    """Iris centres: the picture's (eye_ruler.read: a circle through the limbus) against the model's (eye_ruler.model),
    moving with the model's eye centres."""
    from . import eye_ruler as er
    tru = er.model(head["spec"], view["cam"])
    out = []
    xs = [float(e[0]) for e in head["eye_X"]]
    for s_ in (0, 1):           # eye_ruler: the subject's right eye first (world x smaller: the creature's left is +X)
        j = int(np.argmin(xs)) if s_ == 0 else int(np.argmax(xs))
        Jp, mm1 = _proj_jac_pt(view["cam"], head["eye_X"][j], head["eye_B"][j])
        d = np.asarray(eyes_pic[s_]["c"], float) - np.asarray(tru[s_]["c"], float)
        for ax in (0, 1):
            out.append({"type": "iris", "view": view["kind"], "name": f"iris_{'rl'[s_]}.{'xy'[ax]}", "o": float(d[ax]) * mm1,
                        "J": Jp[ax] * mm1, "sig": 0.2, "p": list(map(float, tru[s_]["c"])), "q": list(map(float, eyes_pic[s_]["c"])),
                        "X": list(map(float, head["eye_X"][j]))})
    return out


SIG_LID = (0.2, 0.4, 0.4)   # mm: a lid margin at a column within 7 mm of the iris centre / beyond it / a canthus


def _lid_obs(head, view, rv):
    """THE LIDS IN THE SAME SOLVE (reruns, 2026-10-11): the eye ruler's read of the front picture (rv = eye_ruler.mean:
    upper / lower margin at its columns, the canthi; mm at the model in the eye's own frame, from the iris centre)
    against the model's margin ring read the same way (blockin_eyes.Reader.margins, the subject's left eye). Each
    moves with GNM's ring-0 vertices relative to the eye's centre. In the EYE's frame, so no camera column: its view
    is "eye frame". The eye step solved these alone and later steps undid them (lips 0.2 -> 1.8 mm, brows 1.8 mm)."""
    from . import blockin_eyes as be, lidrings, onemesh
    ht = onemesh.head_template(head["spec"]["base"])
    mg = be.Reader(ht).margins(ht)
    gg = _gnm()["sp"]
    T = gg["T"]
    r0 = np.asarray(lidrings.topo()["loops"][0], int)
    if "lid_mv" not in _C:
        _C["lid_mv"] = {}
    key = len(head["gid"])
    if key not in _C["lid_mv"]:
        gid = np.asarray(head["gid"], int)
        first = {}
        for i, g_ in enumerate(gid):
            if g_ >= 0 and g_ not in first:
                first[int(g_)] = i
        _C["lid_mv"][key] = np.array([first.get(int(g_), -1) for g_ in r0])
    mv = _C["lid_mv"][key]
    ok = mv >= 0
    r0, mv = r0[ok], mv[ok]
    j = int(np.argmax([float(e[0]) for e in head["eye_X"]]))        # the subject's left eye (world +X)
    E, EB = np.asarray(head["eye_X"][j], float), np.asarray(head["eye_B"][j], float)       # (3,), (170, 3)
    ejy = 0.5 * (T[r0, 1].max() + T[r0, 1].min())
    up = T[r0, 1] > ejy
    x = (np.asarray(head["V"], float)[mv, 0] - E[0]) * 1000.0
    Bx = (np.asarray(head["B"][:, mv, 0], float) - EB[:, 0:1]) * 1000.0     # (170, n) mm per unit, across
    Bz = (np.asarray(head["B"][:, mv, 2], float) - EB[:, 2:3]) * 1000.0     # up
    out = []

    def col_J(sel, u):
        xs = x[sel]
        o = np.argsort(np.abs(xs - u))[:2]
        w = 1.0 / np.maximum(np.abs(xs[o] - u), 0.05)
        w /= w.sum()
        return Bz[:, np.flatnonzero(sel)[o]] @ w
    for nm, sel, pic, mod in (("up", up, np.asarray(rv["up"], float), mg["up"]),
                              ("lo", ~up, np.asarray(rv["lo"], float) - be.LO_BIAS, mg["lo"])):
        for k, u in enumerate(be.RULER_COLS):
            if not (np.isfinite(pic[k]) and np.isfinite(mod[k])):
                continue
            out.append({"type": "lid", "view": "eye frame", "name": f"lid_{nm}_{u:+.0f}.y", "o": float(pic[k] - mod[k]),
                        "J": col_J(sel, float(u)), "sig": SIG_LID[0] if abs(u) < 7 else SIG_LID[1]})
    io, ii = int(np.argmax(x)), int(np.argmin(x))
    if np.isfinite(rv["outer"][0]):
        out.append({"type": "lid", "view": "eye frame", "name": "canthus_out.x", "o": float(rv["outer"][0] + be.OUT_RING - mg["ring_out"][0]),
                    "J": Bx[:, io], "sig": SIG_LID[2]})
    if np.isfinite(rv["inner"][0]):
        JL = (np.asarray(head["LB"][:, 42, 0], float) - EB[:, 0]) * 1000.0
        out.append({"type": "lid", "view": "eye frame", "name": "canthus_in.x", "o": float(rv["inner"][0] - mg["inner"][0]),
                    "J": JL, "sig": SIG_LID[2]})
    return out


NU_SD = 2.0                 # prior sd of an observation's own nuisance columns (log units: wide)
SIG_SHADE = 0.05            # log luminance: one shading sample (validated on clay pairs: spikes/reruns/shval.py)
SHADE_N = 350               # shading samples per view
SHADE_REGIONS = ("forehead_region", "left_temple_region", "right_temple_region", "left_zygomatic_region",
                 "right_zygomatic_region", "left_parotid_region", "right_parotid_region", "left_infraorbital_region",
                 "right_infraorbital_region", "left_cheek_region", "right_cheek_region", "chin_region")


def _vnormals(V, F):
    n = np.zeros_like(V)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    for k in range(3):
        np.add.at(n, F[:, k], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def _shade_model(head) -> dict:
    """Per head: the model vertices of the plain-skin regions (SHADE_REGIONS: no brows, lids, nose, lips: albedo
    edges and cast shadows), their world normals and the normals' change per identity comp (finite differences of
    the head's own faces): {"idx", "N" (n, 3), "dN" (170, n, 3)}."""
    if "_shade" in head:
        return head["_shade"]
    gr = _gnm()["gr"]
    sel = np.zeros(len(next(iter(gr.values()))), bool)
    for k in SHADE_REGIONS:
        sel |= gr[k]
    gid = np.asarray(head["gid"], int)
    V, F = np.asarray(head["V"], float), np.asarray(head["F"], int)
    used = np.zeros(len(V), bool)
    used[F.ravel()] = True
    idx = np.flatnonzero((gid >= 0) & sel[np.maximum(gid, 0)] & used)
    N0 = _vnormals(V, F)
    c = V[idx].mean(0)
    if ((V[idx] - c) * N0[idx]).sum() < 0:      # outward
        N0 = -N0
        sgn = -1.0
    else:
        sgn = 1.0
    eps = 0.5
    dN = np.zeros((head["B"].shape[0], len(idx), 3))
    for k in range(head["B"].shape[0]):
        dN[k] = (sgn * _vnormals(V + eps * np.asarray(head["B"][k], float), F)[idx] - N0[idx]) / eps
    head["_shade"] = {"idx": idx, "N": N0[idx], "dN": dN}
    return head["_shade"]


def _shade_obs(head, view):
    """SHADING (reruns, 2026-10-11; Joe on tk_03: "the puffiness of her cheeks is really weird"): what no outline sees,
    the surface INSIDE the silhouette. On the plain-skin regions (cheeks, zygoma, parotid, under the eye, chin,
    forehead, temples) the picture's luminance is albedo x (c0 + w . n): the light (c0, w) is fitted on the model's
    own normals at the sampled vertices (robust), and each sample's log luminance minus the log of the model's
    predicted shading is the observation: it moves with the vertex's NORMAL, d = (w . dn / dc) / (c0 + w . n). The
    albedo, exposure and their slow drift across the face are the observation's own nuisance columns (a quadratic in
    the picture's coordinates per view). Samples: visible (the clay pass's depth), turned at least 25 deg off
    grazing, on the picture's skin (view["trust"]) and not in the darkest shading (cast shadows)."""
    from scipy import ndimage as ndi
    from . import humanfit
    sm = _shade_model(head)
    cam = view["cam"]
    kind = view["kind"]
    sc, org = float(view.get("scale", 1.0)), np.asarray(view.get("origin", (0.0, 0.0)), float)
    if "_Ylog" not in view:
        a = (np.asarray(view["img"].convert("RGB"), float) / 255.0) ** 2.2
        Y = a @ np.array([0.2126, 0.7152, 0.0722])
        mmpx = float(cam["t"][2]) / cam["f"] * 1000.0 / sc
        view["_Ylog"] = ndi.gaussian_filter(Y, 1.5 / mmpx)       # 1.5 mm: pores, freckles, noise
    Y = view["_Ylog"]
    H, W = Y.shape
    Rc = humanfit._cam_rot(cam)
    X = np.asarray(head["V"], float)[sm["idx"]]
    Xc, px = _cam_points(cam, X)
    px = (px - org) * sc
    nc_ = sm["N"] @ Rc.T
    facing = -nc_[:, 2]                                          # the camera looks along +z
    _, ps = clay(head, cam, passes=True)
    zb = ps["zb"]
    kz = zb.shape[0] / float(cam["size"][1])
    qx = np.clip((px / sc + org)[:, 0] * kz, 0, zb.shape[1] - 1).astype(int)
    qy = np.clip((px / sc + org)[:, 1] * kz, 0, zb.shape[0] - 1).astype(int)
    vis = np.abs(zb[qy, qx] - Xc[:, 2]) < 0.004
    ix, iy = np.round(px[:, 0]).astype(int), np.round(px[:, 1]).astype(int)
    ok = vis & (facing > 0.42) & (ix >= 2) & (ix < W - 2) & (iy >= 2) & (iy < H - 2)
    if "hair" in head:
        ok &= ~np.asarray(head["hair"], bool)[sm["idx"]]        # the hairline / a clay picture's hair cap
    if view.get("trust") is None and view.get("style") == "photo":
        view["trust"] = photo_masks(view["img"], cam, head, origin=org, scale=sc)[1]
    if view.get("trust") is not None:
        tr = ndi.binary_erosion(view["trust"], iterations=max(int(2.0 / (float(cam["t"][2]) / cam["f"] * 1000.0 / sc)), 1))
        ok &= tr[np.clip(iy, 0, H - 1), np.clip(ix, 0, W - 1)]
    if ok.sum() < 60:
        return []
    k = np.flatnonzero(ok)
    y = Y[iy[k], ix[k]]
    n = nc_[k]
    A = np.c_[np.ones(len(k)), n]
    use = y > 0.02
    sol = np.zeros(4)
    for _ in range(5):
        if use.sum() < 40:
            return []
        sol = np.linalg.lstsq(A[use], y[use], rcond=None)[0]
        r = y - A @ sol
        use = (np.abs(r) < 2.5 * r[use].std()) & (y > 0.02)
    S = A @ sol
    good = (S > 0.35 * np.median(S[use])) & (y > 0.25 * np.median(y[use]))     # not the shadow side's floor
    k, y, S, n = k[good], y[good], S[good], n[good]
    if len(k) < 40:
        return []
    if len(k) > SHADE_N:
        pick = np.round(np.linspace(0, len(k) - 1, SHADE_N)).astype(int)
        k, y, S, n = k[pick], y[pick], S[pick], n[pick]
    wv = sol[1:]
    dNc = np.einsum("knc,dc->knd", sm["dN"][:, k], Rc)                # (170, n, 3) camera frame
    J = (dNc @ wv) / S[None, :]                                       # (170, n)
    u = (px[k] - px[k].mean(0)) / max(float(np.ptp(px[k][:, 0])), float(np.ptp(px[k][:, 1])), 1.0)
    o = np.log(y) - np.log(S)
    out = []
    for i in range(len(k)):
        nu = {f"sh_{kind}_1": 1.0, f"sh_{kind}_x": u[i, 0], f"sh_{kind}_y": u[i, 1], f"sh_{kind}_xx": u[i, 0] ** 2,
              f"sh_{kind}_xy": u[i, 0] * u[i, 1], f"sh_{kind}_yy": u[i, 1] ** 2}
        out.append({"type": "shade", "view": "shade:" + kind, "name": f"shade_{kind}_{i}", "o": float(o[i]), "J": J[:, i],
                    "sig": SIG_SHADE, "nu": nu, "px": list(map(float, px[k[i]])),
                    "vid": int(sm["idx"][k[i]])})
    view["_shade_light"] = (float(sol[0]), [float(x) for x in sol[1:]], int(len(k)))
    return out


SIG_LIP = 0.3               # mm: a vermilion border vertex against the picture's traced border


def _gnm_to_model(head) -> dict:
    """GNM vertex id -> a model vertex of head["V"] (the first that carries it)."""
    key = ("g2m", len(head["gid"]))
    if key not in _C:
        first = {}
        for i, g_ in enumerate(np.asarray(head["gid"], int)):
            if g_ >= 0 and g_ not in first:
                first[int(g_)] = i
        _C[key] = first
    return _C[key]


def _lip_obs(head, view, ev):
    """THE LIP BORDERS IN THE SAME SOLVE: the front picture's traced vermilion borders (blockin_lips.photo_evidence:
    upper / lower polylines, px) against the model's border loops (GNM's lip-group vertices next to skin) through the
    view's camera: per border vertex its distance to the picture's border (mm, along the line to the nearest point),
    moving with the vertex. Every other border vertex; past the traced part's ends there is no evidence."""
    from . import base as basemod, blockin_lips as bl
    sk = np.flatnonzero(np.asarray(basemod._gnm_data()["skin"]))
    g2m = _gnm_to_model(head)
    cam = view["cam"]
    s_ = float(view.get("scale", 1.0))
    o_ = np.asarray(view.get("origin", (0.0, 0.0)), float)
    out = []
    for nm, rows in zip(("upper", "lower"), bl.border_loops()):
        mv = np.array([g2m.get(int(sk[r]), -1) for r in np.asarray(rows)[::2]])
        mv = mv[mv >= 0]
        if not len(mv):
            continue
        X = np.asarray(head["V"], float)[mv]
        px = _cam_points(cam, X)[1]
        d, q, ins = bl._poly_dist(px, (np.asarray(ev[nm], float) - o_) / 1.0)
        for i in np.flatnonzero(ins):
            Jp, mm1 = _proj_jac_pt(cam, X[i], head["B"][:, mv[i]])
            if d[i] < 1e-6:
                n = np.array([0.0, 1.0 if nm == "lower" else -1.0])
            else:
                n = (q[i] - px[i]) / d[i]
            out.append({"type": "lip", "view": view["kind"], "name": f"lip_{nm}_{i}", "o": float(d[i]) * mm1 / s_, "n": n.tolist(),
                        "J": (n @ Jp) * mm1, "sig": SIG_LIP, "p": list(map(float, px[i])), "q": list(map(float, q[i])),
                        "X": list(map(float, X[i]))})
    return out


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
LM_SIG = 1.5                          # mm: a clicked / detected landmark as an anchor (biased, never the measure)


def _landmark_obs(head, view, points):
    """The reference's own landmark points ("lmNN": picture px, the ones its camera was fitted with) as weak anchors:
    without them a partial outline (one cheek, the profile's front) lets the camera slide and scale freely."""
    out = []
    for key, p in (points or {}).items():
        if not (key.startswith("lm") and key[2:].isdigit()) or int(key[2:]) >= 68:
            continue
        i = int(key[2:])
        Jp, mm1 = _proj_jac_pt(view["cam"], np.asarray(head["L"], float)[i], head["LB"][:, i])
        _, q = _cam_points(view["cam"], np.asarray(head["L"], float)[i][None])
        for ax in (0, 1):
            out.append({"type": "landmark", "view": view["kind"], "name": f"{key}.{'xy'[ax]}", "o": float(p[ax] - q[0, ax]) * mm1,
                        "J": Jp[ax] * mm1, "sig": LM_SIG, "p": list(map(float, q[0])), "q": list(map(float, p)),
                        "X": list(map(float, np.asarray(head["L"], float)[i]))})
    return out


LM_SIG_DIFF = 1.0                     # mm: a DIFFERENTIAL anchor (the same detector on picture and render), + its pixel floor
LM_PX = 0.6                           # picture px: the detector's own scatter on a small face (Garrett's: 1.2 mm / px)


def _detect_model(head, cam, box):
    """The detector's 478 points (picture px) on the MODEL's own clay picture through cam, cropped to box as the
    picture's own detection is (likeness.model_sides does the same for the table); cached by head and camera."""
    from . import likeness
    key = (np.asarray(head["c"], np.float32).tobytes(),
           tuple(np.round(np.r_[cam["r"], cam["t"], cam["f"], cam.get("yaw", 0.0), cam["centre"]], 6)), tuple(np.round(box, 1)))
    D = _C.setdefault("det", {})
    if key not in D:
        if len(D) > 64:
            D.clear()
        im, k = likeness.render(head["mesh"], cam, box)[:2]
        P = likeness.detect([im])[0]
        D[key] = None if P is None else np.asarray(P, float) / k + [box[0], box[1]]
    return D[key]


def _anchor_obs(head, view, points, det):
    """DIFFERENTIAL DETECTOR ANCHORS (refread, 2026-10-11): the detector's point on the PICTURE minus the same
    detector's point on the model's own render through this view's camera (det = {"P": the picture's 478, "box"}),
    as the block-in table compares them, moving with the landmark itself. _landmark_obs compares the detector with
    the model's TRUE mesh landmarks: the detector's definition bias (3-12 mm on some points, more on a painting) then
    goes into the identity (Garrett: 204 anchors forced comps to 3.9 sd). Falls back to _landmark_obs when the
    detector finds no face on the render."""
    from . import likeness
    if det is None or det.get("P") is None:
        return _landmark_obs(head, view, points)
    Pm = _detect_model(head, view["cam"], det["box"])
    if Pm is None:
        return _landmark_obs(head, view, points)
    out = []
    L = np.asarray(head["L"], float)
    for key in (points or {}):
        if not (key.startswith("lm") and key[2:].isdigit()) or int(key[2:]) >= 68:
            continue
        i = int(key[2:])
        m = likeness.MP68[i]
        Jp, mm1 = _proj_jac_pt(view["cam"], L[i], head["LB"][:, i])
        p, q = Pm[m], np.asarray(det["P"], float)[m]
        sig = float(np.hypot(LM_SIG_DIFF, LM_PX * mm1))
        for ax in (0, 1):
            out.append({"type": "landmark", "view": view["kind"], "name": f"{key}.{'xy'[ax]}", "o": float(q[ax] - p[ax]) * mm1,
                        "J": Jp[ax] * mm1, "sig": sig, "p": list(map(float, p)), "q": list(map(float, q)),
                        "X": list(map(float, L[i])), "diff": True})
    return out


def kind_of(yaw: float) -> str:
    a = abs(float(yaw or 0.0))
    return "front" if a < 20 else ("3q" if a < 70 else "profile")


def reference_views(name: str, hair: bool = True, lids: bool = False, lips: bool = False, shade: bool = False,
                    anchors: str = "differential", parse: bool | str = False, normals: bool = False) -> tuple:
    """A block-in model's reference pictures as the ruler's views: per picture its fitted camera, the skin's own
    outline where the picture has one (a profile in front of a plain background: blockin.profile_contour; any view's
    "outline" points), and on the front picture the iris centres (eye_ruler). -> (views, notes)."""
    from PIL import Image
    from . import blockin as bi, eye_ruler as er, humanfit, likeness, store
    rj = bi._refs(name)
    spec = store.load(name)
    head = model_head(spec)
    views, notes = [], []
    iris_mm = None
    for v, cam in zip(rj["views"], rj["cameras"]):
        k = kind_of(v.get("yaw", 0))
        img = Image.open(v["image"]).convert("RGB")
        view = {"img": img, "cam": cam, "kind": k, "style": "photo", "hair": hair, "name": str(v["image"]).split("/")[-1],
                "face_only": True}
        pts = dict(v.get("points") or {})
        det = None
        if anchors == "differential" and any(k_.startswith("lm") and k_[2:].isdigit() for k_ in pts):
            box = likeness._box(pts, img.size)       # the detector on the picture, on the crop the table uses
            Pd = likeness.detect_region(img, box)
            if Pd is None:
                notes.append(f"{view['name']}: the detector finds no face: its stored points are absolute anchors")
            else:
                det = {"P": Pd, "box": box}
        extras = [] if anchors == "none" else [lambda h, vw, pts=pts, det=det: _anchor_obs(h, vw, pts, det)]
        if v.get("outline"):
            view["outline"] = np.asarray(v["outline"], float)
        else:
            view["mask"], view["trust"] = photo_masks(img, cam, head)
        if k == "front":
            try:
                P = bi.detect_view(img, v)
                mm = likeness._mm_per_px(cam, humanfit.state(spec["base"])["L"][27:48])
                eyes = er.read(img, P, mm)
                extras.append(lambda h, vw, eyes=eyes: _iris_obs(h, vw, eyes))
                iris_mm = float(np.mean([e["iris"] for e in eyes]))
                rv = er.mean(eyes)
                if lids and rv["iris"] / mm >= 30.0 and all(np.isfinite(rv[q]).sum() >= 5 for q in ("up", "lo")):
                    extras.append(lambda h, vw, rv=rv: _lid_obs(h, vw, rv))
                elif lids:
                    notes.append(f"{view['name']}: the lids were not read (iris {rv['iris'] / mm:.0f} px; needs 30)")
            except Exception as e:  # noqa: BLE001
                notes.append(f"{view['name']}: the irises were not read ({e})")
            if lips:
                try:
                    from . import blockin_lips as bl
                    lev = bl.photo_evidence(img, v)
                    extras.append(lambda h, vw, lev=lev: _lip_obs(h, vw, lev))
                except Exception as e:  # noqa: BLE001
                    notes.append(f"{view['name']}: the lip borders were not read ({e})")
        if shade:
            extras.append(_shade_obs)
        view["extra"] = lambda h, vw, extras=tuple(extras): [ob for f in extras for ob in f(h, vw)]
        views.append(view)
    if iris_mm and np.isfinite(iris_mm):       # the turned views draw the limbus at the PICTURE's iris size (the limbus'
        for view in views:                     # plane lies 0.4 mm further forward for an iris 1.4 mm smaller)
            view["iris_mm"] = iris_mm
    return head, views, notes


def compare(name: str, rounds: int = 3, cam_sd=PHOTO_CAM_SD6, hair: bool = True, views: list | None = None,
            prior_off=None, lids: bool = False, lips: bool = False, shade: bool = False, anchors: str = "differential",
            parse: bool | str = False, normals: bool = False) -> dict:
    """The face ruler on a block-in model: its reference pictures against the model, the 23 measures' gaps (picture -
    model, GNM's mm), largest first, each with the reader's error and its `mm:` move. {"rows", "text", "notes", "n"}."""
    only = views
    head, views, notes = reference_views(name, hair, lids=lids, lips=lips, shade=shade, anchors=anchors, parse=parse,
                                         normals=normals)
    if only is not None:          # a subset of the pictures (indices): what one view alone says
        views = [v for i, v in enumerate(views) if i in set(int(j) for j in only)]
    res = read(head, views, rounds=rounds, cam_sd=cam_sd, **({} if prior_off is None else {"prior_off": prior_off}))
    from . import gnm_mm
    sd = gnm_mm.sd()
    for r in res["gaps"]:
        r["picture"] = r["current"] + r["gap"]
        r["err"] = float(np.hypot(r["err"], MODEL_ERR[r["measure"]]))
        r["read"] = float(max(0.0, 1 - (r["err"] / sd[r["measure"]]) ** 2))
    n = {t: sum(ob["type"] == t for ob in res["obs"]) for t in ("outline", "iris", "landmark", "limbus", "lid", "lip", "shade")}
    for r in res["orbit"]:        # the orbit rows' error: never under the block-in path's validated floor
        fl = np.sqrt(sum((w * MODEL_ERR[k]) ** 2 for k, w in gnm_mm.ORBIT_SEEN[r["row"]].items()))
        r["err"] = float(np.hypot(r["err"], fl))
        r["read"] = float(max(0.0, 1 - (r["err"] / r["sd"]) ** 2))
    cams = []
    if res.get("cam_post"):
        for v, done, post in zip(res["views"], res["cam_done"], res["cam_post"]):
            if len(done) > 4:
                cams.append(f"{v['kind']}: yaw {done[4]:+.1f} +-{post[4]:.1f} deg, pitch {done[5]:+.1f} +-{post[5]:.1f}")
    lim = sorted({(ob["view"], ob["name"][:8]) for ob in res["obs"] if ob["type"] == "limbus"})
    notes = list(notes) + [f"limbus read in: {', '.join(f'{a} {b}' for a, b in lim) or 'no turned view'}"]
    if cams:
        notes.append("cameras turned by the solve (their fitted yaw / pitch were left free): " + "; ".join(cams))
    per = {v["kind"]: sum(ob["view"] == v["kind"] for ob in res["obs"]) for v in views}
    head_txt = (f"face ruler: {name} against its {len(views)} pictures ({', '.join(f'{k}: {m} reads' for k, m in per.items())}); "
                "gap = picture - model in GNM's mm; cameras were fitted, so a shift / scale / roll of each picture is left free")
    views = res["views"]
    return {"rows": res["gaps"], "orbit": res["orbit"],
            "text": head_txt + "\n" + orbit_text(res["orbit"]) + "\n" + text(res["gaps"]) + ("\n" + "\n".join(notes) if notes else ""),
            "notes": notes, "n": n, "dc": res["dc"], "views": views, "head": head, "obs": res["obs"],
            "cam_done": res.get("cam_done"), "cam_post": res.get("cam_post")}




def overlay(res: dict, height: int = 640):
    """compare()'s pictures side by side: the model's outline (green), the matched outline reads (yellow: from the
    model's outline to the picture's), the iris reads (magenta = picture, cyan = model)."""
    from PIL import Image, ImageDraw
    tiles = []
    for v in res["views"]:
        im = v["img"].copy()
        d = ImageDraw.Draw(im)
        _, ps = clay(res["head"], v["cam"], passes=True)
        cm = _curve(ps["part"] >= 0)
        if cm is not None:
            d.line([tuple(p) for p in cm], fill=(0, 220, 0), width=2)
        for ob in res["obs"]:
            if ob["view"] != v["kind"]:
                continue
            if ob["type"] == "outline":
                d.line([tuple(ob["p"]), tuple(ob["q"])], fill=(255, 235, 0), width=2)
            else:
                for q, col in ((ob["q"], (255, 0, 255)), (ob["p"], (0, 255, 255))):
                    d.ellipse([q[0] - 6, q[1] - 6, q[0] + 6, q[1] + 6], outline=col, width=2)
        k = height / im.size[1]
        tiles.append(im.resize((int(im.size[0] * k), height), Image.LANCZOS))
    W = Image.new("RGB", (sum(t.size[0] for t in tiles), height), "white")
    x = 0
    for t in tiles:
        W.paste(t, (x, 0))
        x += t.size[0]
    return W
