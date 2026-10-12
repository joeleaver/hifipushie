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


def plain_backdrop(img, thr: float = 30.0) -> float:
    """How plain a picture's backdrop is: the share of its top and side border pixels (the bottom edge is the figure's)
    within thr of their median colour. A studio photo: ~1; a painted or lit scene: under 0.8."""
    a = np.asarray(img.convert("RGB"), float)
    b = np.r_[a[:4].reshape(-1, 3), a[:, :4].reshape(-1, 3), a[:, -4:].reshape(-1, 3)]
    return float((np.abs(b - np.median(b, 0)).sum(-1) < thr).mean())


PARSE_MODEL = "mediapipe"   # faceparse: the outline's parser (validated: spikes/refread/pval.py)
PARSE_SIG = 0.5             # mm: an outline read off the parser's mask (rms 0.2-0.5 on dressed renders, painted backdrop)
PLAIN_MIN = 0.75            # parse="auto": the plain-background reader is used when the backdrop is this plain ...
PLAIN_READS = 40            # ... and it finds this many outline samples in the view; else the parser


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
                keep = head["face"] | head["ears"] if (view.get("ears") and "ears" in head) else head["face"]
                oo = [ob for ob in oo if keep[ob["v"]]]
            if view.get("outline_sig"):
                for ob in oo:
                    ob["sig"] = float(view["outline_sig"])
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
        if view.get("jaw") and view["kind"] != "profile" and "gid" in head:
            obs += _jaw_obs(head, view, ps)
        if (view.get("chin") or {}).get("ramp", RAMP) and view["kind"] != "profile" and "gid" in head and view.get("style") == "photo":
            obs += _ramp_obs(head, view)
        if (view.get("chin") or {}).get("cloth", CLOTH_EDGE) and view["kind"] != "profile" and "gid" in head and view.get("style") == "photo":
            obs += _cloth_obs(head, view, ps)
        obs += list(view.get("extra_obs") or [])
    return obs


# ---- the jaw's edge against the neck (skin on skin: no silhouette, no parser class) -----------------------------------
JAW_REACH = 7.0             # mm: the picture's step is looked for this far either side of the model's contour
JAW_MIN = 0.035             # luminance (0..1): the least step from the lit jaw to the neck under it
SIG_JAW = 0.8               # mm: one jaw-under read (validated on dressed renders: spikes/solvereads/jval.py)
JAW_STEP = 2.0              # mm between reads along the contour


def _head_edges(head):
    key = ("edges", len(head["F"]), int(head["F"][0, 0]))
    if key not in _C:
        F = np.asarray(head["F"])
        e = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1)
        _C[key] = np.unique(e, axis=0)
    return _C[key]


def _jaw_set(head):
    """Model vertices where the jaw's lower edge can lie: exterior skin from the lower lip's height down to 3 cm under
    the chin, in front of the ears (fixed on GNM's template)."""
    key = ("jawset", len(head["gid"]))
    if key not in _C:
        sp = _gnm()["sp"]
        T, gr = sp["T"] * 1000, sp["gr"]
        L = sp["WL"] @ T
        ok = gr["skin_exterior"] & (T[:, 1] < L[57, 1] - 4.0) & (T[:, 1] > L[8, 1] - 30.0) & (T[:, 2] > 0.5 * (L[0, 2] + L[16, 2]) + 5.0)
        ok &= ~(gr["upper_lip"] | gr["lower_lip"] | gr["ears"])
        gid = np.asarray(head["gid"], int)
        _C[key] = (gid >= 0) & ok[np.maximum(gid, 0)]
    return _C[key]


def jaw_contour(head, cam):
    """The model's OCCLUDING CONTOUR in the jaw's set through cam: points on mesh edges where the smooth normal turns
    perpendicular to the line of sight. -> [(a, b, t)] edge vertex ids and the weight of b, camera-frame points (n, 3),
    pixels (n, 2), the contour's outward normal in the picture (n, 2: the surface normal there, which lies in the
    picture plane)."""
    Xc, P = _cam_points(cam, head["V"])
    F = np.asarray(head["F"])
    fn = np.cross(Xc[F[:, 1]] - Xc[F[:, 0]], Xc[F[:, 2]] - Xc[F[:, 0]])
    vn = np.zeros_like(Xc)
    for c_ in range(3):
        np.add.at(vn, F[:, c_], fn)
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)
    g =(vn * Xc).sum(1) / np.maximum(np.linalg.norm(Xc, axis=1), 1e-9)
    E = _head_edges(head)
    js = _jaw_set(head)
    E = E[js[E[:, 0]] & js[E[:, 1]]]
    ga, gb = g[E[:, 0]], g[E[:, 1]]
    E, ga, gb = E[ga * gb < 0], ga[ga * gb < 0], gb[ga * gb < 0]
    t = ga / (ga - gb)
    X = Xc[E[:, 0]] * (1 - t)[:, None] + Xc[E[:, 1]] * t[:, None]
    n3 = vn[E[:, 0]] * (1 - t)[:, None] + vn[E[:, 1]] * t[:, None]
    w, h = cam["size"]
    p = np.stack([cam["f"] * X[:, 0] / X[:, 2] + w / 2, cam["f"] * X[:, 1] / X[:, 2] + h / 2], 1)
    n2 = n3[:, :2] / np.maximum(np.linalg.norm(n3[:, :2], axis=1, keepdims=True), 1e-9)
    return E, t, X, p, n2


def _jaw_obs(head, view, ps):
    """THE JAW'S EDGE AGAINST THE NECK (solvereads, 2026-10-12): in a front or 3/4 picture the chin and jaw end on the
    neck's skin: no silhouette, and a face parser's skin / neck split is unreliable. The model's own occluding contour
    there is known (jaw_contour; kept where it is visible, lies INSIDE the figure and stands at least 4 mm in front of
    what is behind it); the picture shows it as a luminance step, the lit jaw over the neck in its shadow. Per contour
    point: the step's place along the contour's normal (mm, + = the picture's jaw edge lies further out / lower),
    moving with the mesh edge that makes the contour."""
    from scipy import ndimage as ndi
    cam = view["cam"]
    s = float(view.get("scale", 1.0))
    o_ = np.asarray(view.get("origin", (0.0, 0.0)), float)
    E, t, X, p, n2 = jaw_contour(head, cam)
    if not len(E):
        return []
    lum = view.get("_lumj")
    if lum is None:
        a = np.asarray(view["img"].convert("RGB"), float) / 255.0
        lum = view["_lumj"] = a @ np.array([0.299, 0.587, 0.114])
    H, W = lum.shape
    zb, mask = ps["zb"], ps["part"] >= 0
    pi = (p - o_) * s
    mm1 = X[:, 2] / cam["f"] * 1000.0 / s                      # mm per image px at each point
    inb = lambda q: (q[:, 0] > 2) & (q[:, 0] < W - 3) & (q[:, 1] > 2) & (q[:, 1] < H - 3)  # noqa: E731
    qo = pi + n2 * (2.5 / mm1)[:, None]                        # 2.5 mm outward: still the figure, and well behind
    qi = pi - n2 * (1.0 / mm1)[:, None]
    ok = inb(pi) & inb(qo) & inb(qi)
    idx = np.flatnonzero(ok)
    r = lambda q: (np.clip(np.round(q[:, 1]).astype(int), 0, H - 1), np.clip(np.round(q[:, 0]).astype(int), 0, W - 1))  # noqa: E731
    keep = mask[r(qo[idx])] & (zb[r(qo[idx])] - X[idx, 2] > 0.004) & (zb[r(qi[idx])] - X[idx, 2] > -0.03)
    idx = idx[keep]
    if len(idx) < 4:
        return []
    # thin to ~JAW_STEP mm along the contour (greedy on picture distance)
    order = idx[np.argsort(pi[idx, 0])]
    sel, last = [], []
    for i in order:
        if all(np.hypot(*(pi[i] - pi[j])) * mm1[i] >= JAW_STEP for j in last[-12:]):
            sel.append(i)
            last.append(i)
    out = []
    for i in sel:
        m1 = float(mm1[i])
        sg = max(0.7 / m1, 1.0)                                # smoothing: 0.7 mm, at least a pixel
        ts = np.arange(-JAW_REACH / m1 - 3 * sg, JAW_REACH / m1 + 3 * sg + 1e-9, 0.5)
        tg = np.array([-n2[i, 1], n2[i, 0]])
        prof = np.zeros(len(ts))
        for off in (-1.5, -0.75, 0.0, 0.75, 1.5):               # five parallel lines 0.75 mm apart: skin texture averages out
            q = pi[i][None] + ts[:, None] * n2[i][None] + (off / m1) * tg[None]
            prof += _bil(lum, q[:, 0], q[:, 1])
        prof = ndi.gaussian_filter1d(prof / 5.0, sg / 0.5)
        d = np.gradient(prof, 0.5)                              # per px
        inr = np.abs(ts) <= JAW_REACH / m1
        k = int(np.argmin(np.where(inr, d, np.inf)))
        if not (0 < k < len(ts) - 1) or not inr[k - 1] or not inr[k + 1]:
            continue
        w_ = int(round(1.5 * sg / 0.5))
        step = float(prof[max(k - w_, 0)] - prof[min(k + w_, len(ts) - 1)])
        if step < JAW_MIN:
            continue
        far = np.abs(ts - ts[k]) > 3.0 * sg
        if (d[inr & far] < 0.6 * d[k]).any():                   # another step as strong elsewhere in reach: ambiguous
            continue
        den = d[k - 1] - 2 * d[k] + d[k + 1]
        sub = 0.5 * (d[k - 1] - d[k + 1]) / den if abs(den) > 1e-12 else 0.0
        e = float(ts[k] + 0.5 * np.clip(sub, -1, 1))
        Jp, mmc = _proj_jac(cam, head, E[i], w=[1 - t[i], t[i]])
        Xw = head["V"][E[i, 0]] * (1 - t[i]) + head["V"][E[i, 1]] * t[i]
        out.append({"type": "jaw", "view": view["kind"], "name": f"jaw_{i}", "o": e * m1, "J": (n2[i] @ Jp) * mmc,
                    "sig": SIG_JAW, "n": n2[i].tolist(), "p": pi[i].tolist(), "q": (pi[i] + e * n2[i]).tolist(),
                    "X": list(map(float, Xw)), "step": step})
    return out


# ---- the jaw / chin in front of CLOTH (chinread): skin on cloth, inside the figure's mask ----------------------------------
CLOTH_EDGE = False          # default of view["chin"]["cloth"]
CLOTH_REACH = 9.0           # mm: the picture's skin / cloth edge is looked for this far either side of the model's contour
SIG_CLOTH = 0.6             # mm: one read (validated on dressed renders with a collar laid behind the jaw: spikes/chinread/clval.py)
CLOTH_STEP = 2.0            # mm between reads along the contour
CLOTH_DROP = 0.012          # m: the model's own surface (or nothing) lies at least this far behind the contour, 2.5 and 5 mm outside it


def _parse_maps(view, head):
    """The parser's skin and cloth probability maps in the view's picture pixels (cached on the view; None when the
    parser is not installed)."""
    if "_parse" not in view:
        from . import faceparse
        try:
            _, _, full = faceparse.masks(view["img"], view["cam"], head, origin=view.get("origin", (0.0, 0.0)),
                                         scale=float(view.get("scale", 1.0)), model=PARSE_MODEL)
            view["_parse"] = {"skin": full["skin"], "cloth": full["cloth"], "figure": full["figure"]}
        except (FileNotFoundError, RuntimeError, ValueError):
            view["_parse"] = None
    return view["_parse"]


def _cloth_obs(head, view, ps):
    """THE JAW AND CHIN IN FRONT OF CLOTH (chinread, 2026-10-12): in a front or 3/4 picture the far jaw and the chin's
    corner often stand in front of a collar: bare skin against cloth INSIDE the figure's mask, so the outline reader
    (figure against backdrop) never sees it, and it is the one place a 3/4 shows the chin's and jaw's width as an edge.
    The model's own occluding contour over the jaw and chin (jaw_contour) is known; along its normal the picture's edge
    is where the face parser's bare SKIN ends and CLOTH begins (skin just inside, cloth just outside, one such edge in
    reach). o = that edge's place (mm, + = the picture's jaw lies further out), moving with the mesh edge that makes the
    contour. Valid where the garment lies BEHIND or BELOW the jaw; a scarf or collar worn OVER the jaw reads as a
    narrower jaw (the reply says how many reads came from cloth: look at the picture)."""
    pm = _parse_maps(view, head)
    if pm is None:
        return []
    cam = view["cam"]
    s = float(view.get("scale", 1.0))
    o_ = np.asarray(view.get("origin", (0.0, 0.0)), float)
    E, t, X, p, n2 = jaw_contour(head, cam)
    if not len(E):
        return []
    S, C = pm["skin"], pm["cloth"]
    H, W = S.shape
    zb = ps["zb"]
    pi = (p - o_) * s
    mm1 = X[:, 2] / cam["f"] * 1000.0 / s                      # mm per image px at each point

    def zat(q):                                                # the model's depth at image points (the passes are in image px)
        return zb[np.clip(np.round(q[:, 1]).astype(int), 0, zb.shape[0] - 1), np.clip(np.round(q[:, 0]).astype(int), 0, zb.shape[1] - 1)]
    inb = (pi[:, 0] > 4) & (pi[:, 0] < W - 5) & (pi[:, 1] > 4) & (pi[:, 1] < H - 5)
    qo = pi + n2 * (2.5 / mm1)[:, None]
    qi = pi - n2 * (1.0 / mm1)[:, None]
    dq = zat(qi) - X[:, 2]                                     # (1 mm inside a grazing surface stands ~1 cm nearer)
    qo2 = pi + n2 * (5.0 / mm1)[:, None]                       # a REAL step in depth behind it (a garment lies well behind a
    keep = inb & (zat(qo) - X[:, 2] > CLOTH_DROP) & (zat(qo2) - X[:, 2] > CLOTH_DROP) & (dq > -0.03) & (dq < 0.004)   # jaw that stands in front of it: where the skin merely turns under and runs on into a collar the edge is the collar's)
    idx = np.flatnonzero(keep)
    if len(idx) < 3:
        return []
    order = idx[np.argsort(pi[idx, 0])]
    sel, last = [], []
    for i in order:
        if all(np.hypot(*(pi[i] - pi[j])) * mm1[i] >= CLOTH_STEP for j in last[-12:]):
            sel.append(i)
            last.append(i)
    out = []
    for i in sel:
        m1 = float(mm1[i])
        ts = np.arange(-CLOTH_REACH - 4.0, CLOTH_REACH + 4.0 + 1e-9, 0.25)          # mm along the normal
        q = pi[i][None] + (ts / m1)[:, None] * n2[i][None]
        if q[:, 0].min() < 1 or q[:, 1].min() < 1 or q[:, 0].max() > W - 2 or q[:, 1].max() > H - 2:
            continue
        sk, cl = _bil(S, q[:, 0], q[:, 1]), _bil(C, q[:, 0], q[:, 1])
        dn = np.flatnonzero((sk[:-1] >= 0.5) & (sk[1:] < 0.5) & (np.abs(ts[:-1]) <= CLOTH_REACH))
        good = []
        for k in dn:
            a, b = sk[k], sk[k + 1]
            e = float(ts[k] + 0.25 * (a - 0.5) / max(a - b, 1e-9))
            ins = (ts > e - 3.5) & (ts < e - 1.0)
            ots = (ts > e + 1.0) & (ts < e + 3.5)
            if sk[ins].mean() > 0.75 and cl[ots].mean() > 0.6:
                good.append(e)
        if len(good) != 1:
            continue
        e = good[0]
        Jp, mmc = _proj_jac(cam, head, E[i], w=[1 - t[i], t[i]])
        Xw = head["V"][E[i, 0]] * (1 - t[i]) + head["V"][E[i, 1]] * t[i]
        out.append({"type": "cloth", "view": view["kind"], "name": f"cloth_{i}", "o": e, "J": (n2[i] @ Jp) * mmc,
                    "sig": SIG_CLOTH, "n": n2[i].tolist(), "p": pi[i].tolist(), "q": (pi[i] + e / m1 * n2[i]).tolist(),
                    "X": list(map(float, Xw))})
    return out


# ---- the jaw's lower edge as a SHADING ramp, picture against our own render under the picture's light (chinread) ---------
RAMP = False                # default of view["chin"]["ramp"]
RAMP_LM = (4, 12)           # the jaw line's landmarks the profiles cross: the jaw's body and the chin (the ramus is a silhouette)
RAMP_STEP = 3.0             # mm between profiles along the jaw line
RAMP_HALF = 13.0            # mm: a profile's half length across the jaw line
RAMP_REACH = 7.0            # mm: the largest shift looked for
RAMP_MIN = 0.10             # the least fall of the profile (share of its lit level) in the render AND in the picture
RAMP_NCC = 0.90             # the least correlation of the two profiles at the best shift
SIG_RAMP = 1.0              # mm: one profile's shift (validated: spikes/chinread/rval.py)


def _lit_model(head, view):
    """The model's own render under the PICTURE's fitted light (blockin.lit_render: c0 + w.n, ambient occlusion, a soft
    cast shadow), in the view's picture pixels: (luminance 0..1, passes). The light is fitted once per view."""
    from PIL import Image
    from . import blockin as bi, likeness
    cam, img = view["cam"], view["img"]
    w, h = cam["size"]
    if view.get("_light") is None:
        im, lt, ps = bi.lit_render(head["mesh"], cam, img)
        view["_light"] = lt
    else:
        im, _, ps = likeness.render(head["mesh"], cam, (0.0, 0.0, float(w), float(h)), px=int(max(w, h)), brows=False, passes=True,
                                    ao=True, shadow=8.0, light=view["_light"])
    if im.size != img.size:
        im = im.resize(img.size, Image.LANCZOS)
    a = np.asarray(im.convert("RGB"), float) / 255.0
    return a @ np.array([0.299, 0.587, 0.114]), ps


def _ramp_obs(head, view):
    """THE JAW'S LOWER EDGE AS A SHADING RAMP (chinread, 2026-10-12). In a front or 3/4 picture the chin and jaw end on the
    neck's skin: no silhouette. Under a light from above the surface turning under the jaw falls into shade: a ramp of
    luminance across the jaw line, in the picture and in our own render of the model under the picture's fitted light
    (_lit_model). Per profile across the model's jaw line (GNM lm 4..12 through the camera, every RAMP_STEP mm): the
    shift that lays the picture's profile on the render's (the best normalised correlation, gain and offset free: an
    albedo's level does not matter, its edges do), o mm (+ = the picture's ramp lies further OUT / lower), moving with
    the model's surface where the render's ramp is steepest. Read only where both profiles fall by RAMP_MIN and agree
    in shape (RAMP_NCC, one clear best shift): a flat frontal light gives no ramp and no read."""
    from scipy import ndimage as ndi
    from scipy.spatial import cKDTree
    cam = view["cam"]
    if "scale" in view:
        return []
    if "_lump" not in view:
        a = np.asarray(view["img"].convert("RGB"), float) / 255.0
        view["_lump"] = a @ np.array([0.299, 0.587, 0.114])
    lp = view["_lump"]
    if view.get("ramp_lum") is not None:      # the model's picture from OUTSIDE (a dressed render of it under the picture's light:
        lr = np.asarray(view["ramp_lum"], float)          # spikes/chinread/eev.py), luminance 0..1 in the picture's pixels
        ps = clay(head, cam, passes=True)[1]
    else:
        lr, ps = _lit_model(head, view)
    H, W = lp.shape
    L = np.asarray(head["L"], float)
    Xc, P = _cam_points(cam, L[:68])
    mm = float(np.median(Xc[RAMP_LM[0]:RAMP_LM[1] + 1, 2])) / cam["f"] * 1000.0          # mm per px at the jaw
    S = _resample(P[RAMP_LM[0]:RAMP_LM[1] + 1], RAMP_STEP / mm)
    if len(S) < 4:
        return []
    T = np.gradient(S, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    N = np.stack([-T[:, 1], T[:, 0]], 1)
    N[((S - P[62]) * N).sum(1) < 0] *= -1                      # outward: away from the mouth
    # visible head vertices in the picture (the Jacobian's carriers)
    Vc, Vp = _cam_points(cam, head["V"])
    zb = ps["zb"]
    ix = np.clip(np.round(Vp[:, 0]).astype(int), 0, zb.shape[1] - 1)
    iy = np.clip(np.round(Vp[:, 1]).astype(int), 0, zb.shape[0] - 1)
    used = np.zeros(len(Vc), bool)
    used[np.asarray(head["F"]).ravel()] = True
    vis = np.flatnonzero(used & (np.abs(zb[iy, ix] - Vc[:, 2]) < 0.004))
    if len(vis) < 50:
        return []
    tree = cKDTree(Vp[vis])
    ts = np.arange(-RAMP_HALF, RAMP_HALF + 1e-9, 0.25)
    sg = 1.0 / 0.25                                            # 1 mm
    nsh = int(round(RAMP_REACH / 0.25))
    core = slice(nsh, len(ts) - nsh)
    part = ps["part"]
    pm = _parse_maps(view, head)       # the picture's bare skin: the parser's (stubble and shade are skin to it), else the reader's
    skin = (pm["skin"] > 0.5) if pm is not None else view.get("trust")
    out = []
    for k in range(len(S)):
        q = S[k][None] + (ts / mm)[:, None] * N[k][None]
        if q[:, 0].min() < 3 or q[:, 1].min() < 3 or q[:, 0].max() > W - 4 or q[:, 1].max() > H - 4:
            continue
        on = part[np.round(q[:, 1]).astype(int), np.round(q[:, 0]).astype(int)] == 0
        if not on.all():                                       # the whole profile on the model's skin (no backdrop, no eye)
            continue
        if skin is not None:
            if skin[np.round(q[:, 1]).astype(int), np.round(q[:, 0]).astype(int)].mean() < 0.97:
                continue                                       # ... and on the picture's skin (a collar, the backdrop)
        pp, pr = np.zeros(len(ts)), np.zeros(len(ts))
        for off in (-1.5, -0.75, 0.0, 0.75, 1.5):               # five parallel lines: stubble and pores average out
            qq = q + (off / mm) * T[k][None]
            pp += _bil(lp, qq[:, 0], qq[:, 1])
            pr += _bil(lr, qq[:, 0], qq[:, 1])
        pp = ndi.gaussian_filter1d(pp / 5.0, sg, mode="nearest")
        pr = ndi.gaussian_filter1d(pr / 5.0, sg, mode="nearest")
        fall_r = (pr[core].max() - pr[core].min()) / max(pr[core].max(), 1e-6)
        fall_p = (pp.max() - pp.min()) / max(pp.max(), 1e-6)
        if fall_r < RAMP_MIN or fall_p < RAMP_MIN:
            continue
        a = pr[core] - pr[core].mean()
        na = float(np.linalg.norm(a))
        cc = np.zeros(2 * nsh + 1)
        for j, sh in enumerate(range(-nsh, nsh + 1)):          # the picture's profile shifted by sh samples against the render's
            b = pp[nsh + sh:len(ts) - nsh + sh]
            b = b - b.mean()
            cc[j] = float(a @ b) / max(na * float(np.linalg.norm(b)), 1e-12)
        j = int(np.argmax(cc))
        if cc[j] < RAMP_NCC or j in (0, len(cc) - 1):
            continue
        far = np.abs(np.arange(len(cc)) - j) > int(3.0 / 0.25)
        if far.any() and cc[far].max() > cc[j] - 0.02:          # no clear best shift (a straight ramp: its place is free)
            continue
        den = cc[j - 1] - 2 * cc[j] + cc[j + 1]
        sub = 0.5 * (cc[j - 1] - cc[j + 1]) / den if abs(den) > 1e-12 else 0.0
        e = (j - nsh + float(np.clip(sub, -1, 1))) * 0.25
        g = np.gradient(pr)
        kk = nsh + int(np.argmin(g[core]))                     # the render's steepest fall: the surface that carries the ramp
        d_, iv = tree.query(q[kk])
        if d_ * mm > 3.0:
            continue
        v = int(vis[iv])
        Jp, mm1 = _proj_jac(cam, head, v)
        out.append({"type": "ramp", "view": view["kind"], "name": f"ramp_{k}", "o": e, "J": (N[k] @ Jp) * mm1, "sig": SIG_RAMP,
                    "n": N[k].tolist(), "p": q[kk].tolist(), "q": (q[kk] + e / mm * N[k]).tolist(), "X": head["V"][v].tolist(),
                    "ncc": float(cc[j]), "fall": (float(fall_r), float(fall_p))})
    return out


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


def _all_types(obs, weights) -> dict:
    return {t: (weights or {}).get(t, 1.0) for t in {ob["type"] for ob in obs}}


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
          weights: dict | None = None, done=None, cam_done=None, prior_off=None, adapt: bool = False,
          cmax: float | None = None, relax0: float = 1.0, expr_mode: str = "view", expr_sd: float | None = None) -> dict:
    """The gaps of the 23 measures from the observations. Default: the most likely identity change dc (prior N(0,
    tau^2) per comp) and the measures read off it, with posterior sd. span=True: least squares over the 23 `mm:` moves
    alone. cam_sd = (shift mm, shift mm, scale %, roll deg): the camera was fitted, so much of each is unknown."""
    from . import gnm_mm
    names = list(gnm_mm.NAMES)
    Jm = head["Jm"]
    o = np.array([ob["o"] for ob in obs])
    K = Jm.shape[1]
    kx = max(len(ob["J"]) for ob in obs)
    Jall = np.zeros((len(obs), kx))
    for i, ob in enumerate(obs):                # (a hold row has the identity's columns only)
        Jall[i, :len(ob["J"])] = ob["J"]
    J, Xc_ = Jall[:, :K], Jall[:, K:]          # identity | the EXPRESSION each read's own picture shows (model_head expr)
    sig = np.array([ob["sig"] * (weights or {}).get(ob["type"], 1.0) for ob in obs])
    firm = np.array([ob["type"] == "hold" for ob in obs])
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
    xcols = []                             # EXPRESSION as a nuisance: per picture ("view") or one for the set ("shared"),
    if Xc_.shape[1] and not span:          # a strong prior at neutral; never applied to the head, so each round's estimate
        pics = sorted({ob.get("of", ob["view"]) for ob in obs if ob["type"] in EXPR_TYPES}) if expr_mode == "view" else ["all"]
        xn = (head.get("expr") or {}).get("names") or [f"x{j}" for j in range(Xc_.shape[1])]     # is of the whole expression
        cols = []
        for pc in pics:
            m_ = np.array([(expr_mode != "view" or ob.get("of", ob["view"]) == pc) and ob["type"] in EXPR_TYPES for ob in obs], float)
            for j in range(Xc_.shape[1]):
                cols.append(Xc_[:, j] * m_)
                xcols.append((pc, xn[j]))
        Cx = np.array(cols).T
        Jx, pri, m0 = np.c_[Jx, Cx], np.r_[pri, np.full(len(xcols), EXPR_SD if expr_sd is None else float(expr_sd))], np.r_[m0, np.zeros(len(xcols))]
        nn += len(xcols)
    if cmax and not span:     # NOTHING FORCED: if the most likely head has a component past cmax sd, the pictures are
        c_at = np.asarray(head["c"], float)   # (the head as it stands in this round)        # less consistent than
        # their sigmas say (two paintings of one man are two drawings): every sigma x relax, the SMALLEST factor at
        # which no component passes cmax, found by bisection (solvereads: it moved in x1.3 steps, 1.30 / 1.69 / 2.20, so
        # two calls on the same pictures solved different problems and the head hopped |dc| 2.4 -> 5.1), and never
        # under relax0: the factor the block-in already stands at (solve_step lets it come down 15 % a call)

        def at(rx):
            t_ = solve(obs, head, tau=tau, cam_sd=cam_sd, views=views, huber=huber, weights={k_: v_ * rx for k_, v_ in _all_types(obs, weights).items() if k_ != "hold"},
                       done=done, cam_done=cam_done, prior_off=prior_off, adapt=adapt, expr_mode=expr_mode, expr_sd=expr_sd)
            return t_, float(np.abs(c_at + t_["dc"]).max())
        lo = max(float(relax0), 1.0)
        t_, m_ = at(lo)
        if m_ > cmax:
            hi = lo
            for _ in range(40):
                hi *= 1.3
                t_hi, m_ = at(hi)
                if m_ <= cmax:
                    break
            for _ in range(7):                # the factor to ~1 %
                mid = float(np.sqrt(lo * hi))
                t_m, m_ = at(mid)
                if m_ <= cmax:
                    hi, t_hi = mid, t_m
                else:
                    lo = mid
            t_, lo = t_hi, hi
        t_["relax"] = lo
        return t_
    w = 1.0 / sig ** 2
    sig0, grp, scale = sig.copy(), {}, {}
    if adapt:
        for i, ob in enumerate(obs):
            if ob["type"] != "hold":
                grp.setdefault((ob["type"], ob["view"]), []).append(i)
    for it in range(6 if adapt else 3):
        A = (Jx * w[:, None]).T @ Jx + np.diag(1.0 / pri ** 2)
        Ai = np.linalg.inv(A)
        th = Ai @ (Jx.T @ (w * o) + m0 / pri ** 2)
        if adapt and it in (2, 3, 4):     # a group the model cannot explain to its sigma is NOISIER than assumed (a
            for key, ii in grp.items():   # painting's outline, a detector on brush strokes): its sigma = its own scatter
                if len(ii) >= ADAPT_MIN:
                    s_ = 1.4826 * float(np.median(np.abs((o - Jx @ th)[ii])))
                    scale[key] = max(1.0, s_ / float(np.median(sig0[ii])))
                    sig[ii] = sig0[ii] * scale[key]
        r = (o - Jx @ th) / sig
        w = 1.0 / sig ** 2 * np.where(firm, 1.0, np.minimum(1.0, huber / np.maximum(np.abs(r), 1e-9)))
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
    return {"dc": dc, "gaps": rows, "n": len(obs), "rms": float(np.sqrt(np.mean(r ** 2))), "sig_scale": scale, "relax": 1.0,
            "cam": th[n1:n1 + nc].tolist() if nc else None, "cov": full, "names": names,
            "cam_post": np.sqrt(np.maximum(np.diag(Ai)[n1:n1 + nc], 0)).tolist() if nc else None,
            # the linear-Gaussian system as solved (solve_report: what each measure's posterior owes to which reads)
            "post": {"Jx": Jx, "w": w, "pri": pri, "n1": n1, "tau": tau, "span": span},
            "expr": {pc: {} for pc, _ in xcols} and _expr_out(xcols, th[len(th) - len(xcols):], np.sqrt(np.maximum(np.diag(Ai)[len(th) - len(xcols):], 0)))}


def _expr_out(xcols, val, sd) -> dict:
    out = {}
    for (pc, nm), v, s_ in zip(xcols, val, sd):
        out.setdefault(pc, {})[nm] = (float(v), float(s_))
    return out


def read(head: dict, views: list, rounds: int = 3, **kw) -> dict:
    """The ruler: the pictures against the model, `rounds` Gauss-Newton rounds (the outline's maker and normal are
    re-taken on the moved head: one round is off by the step's curvature when the gap is large). Gaps are the measures
    of the fitted head minus the model's."""
    from . import gnm_mm
    if kw.get("span"):
        rounds = 1
    make = head.get("rebuild") or (lambda c: gnm_head(c))
    done = np.zeros(len(head["c"]) if "c" in head else head["B"].shape[0])
    cur = head
    relax0 = float(kw.pop("relax0", 1.0))      # the down-weighting the block-in already stands at (cmax)
    hold = kw.pop("hold", None)                # None | "auto" (every measure no read looks at) | [measure names]
    held0 = list(kw.pop("held0", None) or [])  # measures held in the block-in's earlier calls: they stay held
    tie = kw.pop("tie", None)                  # None | {"names", "given", "sig"}: solve_report.tie_rows every round
    poff = kw.get("prior_off")
    held = []
    views = [dict(v) for v in views]
    free = kw.get("cam_sd") is not None
    ncam = len(cam_sd_of(kw["cam_sd"], views[0]["kind"])) if free else 4
    cam_done = np.zeros((len(views), ncam))
    cam0 = kw.pop("cam_done0", None)     # the cameras' move in EARLIER calls (per view): the prior is on the whole of it
    cam_first = int(kw.pop("cam_first", 0))
    if not free:
        cam_first = 0
    for _ in range(cam_first):       # CAMERAS FIRST: the head held (tau tiny), each camera CAM_LOOSE x its freedom, never
        for v in views:              # past 2.5 sd of that per round: a camera fitted on another head (a block-in's start
            if v.get("extra"):       # with kept cameras) is first laid on THIS head's outline and anchors
                v["extra_obs"] = v["extra"](cur, v)
        obs = observe(cur, views)
        if not obs:
            break
        loose = {kk: tuple(CAM_LOOSE * x for x in cam_sd_of(kw["cam_sd"], kk)) for kk in ("front", "3q", "profile")}
        o_ = solve(obs, cur, views=views, **{**kw, "tau": 0.02, "cam_sd": loose})
        th = np.asarray(o_["cam"], float).reshape(len(views), ncam)
        lim = 2.5 * np.array([loose[v["kind"]] for v in views], float)
        for v, t_ in zip(views, np.clip(th, -lim, lim)):
            v["cam"] = cam_moved(v["cam"], *t_)
        cam0 = None                  # refitted cameras are the new start
    prior_cam = cam0 is not None and free
    if prior_cam:
        a0 = np.zeros_like(cam_done)
        c0_ = np.atleast_2d(np.asarray(cam0, float))
        a0[:min(len(a0), len(c0_)), :min(ncam, c0_.shape[1])] = c0_[:len(a0), :ncam]
        cam_done = a0
    cam_start = cam_done.copy()
    relax = 1.0
    for k in range(rounds):
        for v in views:              # per-view extra observations follow the moved head and camera
            if v.get("extra"):
                v["extra_obs"] = v["extra"](cur, v)
        obs = observe(cur, views)
        if not obs:
            raise ValueError("face_ruler: nothing could be read (no outline, no feature) in these pictures")
        skw = dict(done=done if k else None, cam_done=cam_done if (free and (k or prior_cam)) else None, relax0=max(relax0, relax), **kw)
        out = solve(obs, cur, views=views, **skw)
        if hold and "gid" in cur and not kw.get("span"):
            # HOLD what no read looks at (solve_report.direct) at the START head's value: the prior's correlations may
            # not carry an unread measure along with the read ones (garrett_a1's eye depth: 7.8 mm from nothing)
            from . import solve_report as sr
            whole = done + (np.asarray(poff, float) if poff is not None else 0.0)
            if hold == "auto":      # STICKY: a measure whose read hovers at the threshold was held in one round and let
                drc = sr.direct(out["post"], obs, views, cur, groups=False)       # go in the next, and drifted
                now = [h["name"][5:] for h in sr.hold_rows(drc["read"], done=whole)]
                held0 = held0 + [n for n in now if n not in held0]
                hrows = sr.hold_rows(None, done=whole, names=held0)
            else:
                hrows = sr.hold_rows(None, done=whole, names=list(hold))
            held = [h["name"][5:] for h in hrows]
            if hrows:
                obs = obs + hrows
                out = solve(obs, cur, views=views, **skw)
        if tie and "gid" in cur and not kw.get("span"):
            # TIE what no picture reads to its expectation given what they do read (solve_report.tie_rows; chinread)
            from . import solve_report as sr
            whole = done + (np.asarray(poff, float) if poff is not None else 0.0)
            tk = {k_: v_ for k_, v_ in tie.items() if k_ != "size"}
            obs = obs + (sr.tie_rows(done=whole, **tk) if tk.get("names") else []) + ([sr.size_row(done=whole)] if tie.get("size") else [])
            out = solve(obs, cur, views=views, **skw)
        relax = float(out.get("relax", 1.0))
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
    out["cam_step"], out["relax"], out["held"] = (cam_done - cam_start).tolist(), relax, held
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
    from . import base as _basemod
    ri = _basemod.drawn_iris(head["spec"], r)   # skin.eyes.iris_size, else GNM's limbus (its eyeball), else 0.51 r
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


EXPR_SET = ("compress_face", "surprise", "squint", "lips_roll_in", "corners_down", "happy", "mouth_left", "mouth_right")
EXPR_SAY = {"compress_face": "frown / brows drawn down and together", "surprise": "brows raised (jaw dropped)", "squint": "squint",
            "lips_roll_in": "lips pressed", "corners_down": "mouth corners down", "happy": "smile (corners pulled)",
            "mouth_left": "mouth pulled to its left", "mouth_right": "mouth pulled to its right"}
# the reads an expression may explain: the INTERIOR ones. TRIED with the outlines in (solvereads): per-view expression then
# ate the profile (compress +0.9, surprise -0.9 on the 72 deg view: chin 10 mm back, the head 3.5 mm rms from the truth
# after three calls against 1.8 without the term): a silhouette cannot tell an expression from a shape.
EXPR_TYPES = ("landmark", "lid", "lip")
EXPR_SD = 0.35              # prior sd of one expression coefficient (1 = GNM's full prototype of that expression class)


def expression_protos(names=EXPR_SET) -> np.ndarray:
    """(n, 383) GNM expression coefficients of the sampler's class prototypes (gnm_sampler.prototype)."""
    key = ("xproto", tuple(names))
    if key not in _C:
        from . import gnm_sampler
        _C[key] = np.array([gnm_sampler.prototype(n) for n in names], float)
    return _C[key]


def expression_coeffs(amounts: dict) -> dict:
    """{expression class: amount} -> base.head.expression's {GNM expression comp: value}."""
    from . import base as basemod
    names = [str(n) for n in basemod._gnm_data()["expression_names"]]
    e = sum(float(a) * expression_protos((k,))[0] for k, a in amounts.items())
    return {n: round(float(x), 5) for n, x in zip(names, np.atleast_1d(e)) if abs(x) >= 1e-4}


def _expr_fields(names) -> np.ndarray:
    """(n, V, 3): each prototype's move of GNM's vertices (raw GNM frame, m)."""
    key = ("xfield", tuple(names))
    if key not in _C:
        from . import gnm_controls
        EB = gnm_controls.gnm()["EB"]
        P = expression_protos(names)
        _C[key] = np.array([np.tensordot(e.astype(np.float32), EB[:len(e)], 1) for e in P], np.float32)
    return _C[key]


def model_head(spec: dict, c=None, kappa=None, expr=None) -> dict:
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
    nx = len(expr["names"]) if expr else 0
    B = np.zeros((170 + nx, len(P), 3), np.float32)
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
    B[:170, idx] = Bh.astype(np.float32)
    XLB = None
    if expr:      # EXPRESSION columns (solvereads): each prototype's move of the model's head vertices and landmarks, carried
        if "XB" not in expr:      # as the identity's are; how much of it the model really makes is measured once (kx)
            Fx = _expr_fields(expr["names"])
            XB = sc * Fx[:, gid[idx]].astype(np.float64) @ R.T * fade[gid[idx]][None, :, None]
            mix = {n: 0.3 * (-1) ** i for i, n in enumerate(expr["names"])}
            sp2 = copy.deepcopy(spec)
            e0 = dict(sp2["base"]["head"].get("expression") or {})
            for k_, v_ in expression_coeffs(mix).items():
                e0[k_] = float(e0.get(k_, 0.0)) + v_
            sp2["base"]["head"]["expression"] = e0
            P2 = np.asarray(humanfit.state(sp2["base"])["tpl"]["P"], float)
            a_, b_ = (P2[idx] - P[idx]).ravel(), np.tensordot(np.array(list(mix.values())), XB, 1).ravel()
            expr["kx"] = float(a_ @ b_ / max(b_ @ b_, 1e-18))
            expr["kx_res"] = float(np.linalg.norm(a_ - expr["kx"] * b_) / max(np.linalg.norm(a_), 1e-12))
            expr["XB"] = (expr["kx"] * XB).astype(np.float32)
            expr["XLB"] = expr["kx"] * sc * np.einsum("lv,kvc->klc", _gnm()["sp"]["WL"], Fx.astype(np.float64)) @ R.T
        B[170:, idx] = expr["XB"]
        XLB = expr["XLB"]
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
    ears = np.zeros(len(P), bool)
    ears[idx] = _gnm()["gr"]["ears"][gid[idx]]
    LB = kappa * sc * (mh["LB"] - jm) @ R.T                  # (170, 68, 3): the 68 landmarks' moves
    eB = [eyeB[:, j] for j in order]
    if expr:
        LB = np.concatenate([LB, XLB])
        eB = [np.concatenate([e_, np.zeros((nx, 3))]) for e_ in eB]      # the eyeballs do not move with an expression
    return {"face": face, "ears": ears, "LB": LB, "c": cid, "V": P, "F": F[hv[F].all(1)], "B": B, "bnd": np.zeros(len(P), bool), "mesh": mesh, "L": st["L"],
            "Jm": gnm_mm.jacobian()[:len(gnm_mm.NAMES)], "measures": {n: float(r[n]) for n in gnm_mm.NAMES},
            "kind": "model", "hair": hair, "spec": spec, "eye_X": E, "eye_B": eB, "expr": expr,
            "kappa": kappa, "kappa_res": kres, "rebuild": lambda c2: model_head(spec, c2, kappa, expr), "gid": gid, "R": R, "sc": sc}


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
                        "J": col_J(sel, float(u)), "sig": SIG_LID[0] if abs(u) < 7 else SIG_LID[1], "of": view.get("kind", "front")})
    io, ii = int(np.argmax(x)), int(np.argmin(x))
    if np.isfinite(rv["outer"][0]):
        out.append({"type": "lid", "view": "eye frame", "name": "canthus_out.x", "o": float(rv["outer"][0] + be.OUT_RING - mg["ring_out"][0]),
                    "J": Bx[:, io], "sig": SIG_LID[2], "of": view.get("kind", "front")})
    if np.isfinite(rv["inner"][0]):
        JL = (np.asarray(head["LB"][:, 42, 0], float) - EB[:, 0]) * 1000.0
        out.append({"type": "lid", "view": "eye frame", "name": "canthus_in.x", "o": float(rv["inner"][0] - mg["inner"][0]),
                    "J": JL, "sig": SIG_LID[2], "of": view.get("kind", "front")})
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


SIG_NORMAL = 0.10           # radians: one learned-normal sample's tangent component (spikes/refread/nrmval.py)
NORMAL_N = 400              # normal samples per view
NORMAL_REGIONS = SHADE_REGIONS + ("nose_region",)


def _normal_model(head, regions=NORMAL_REGIONS) -> dict:
    """as _shade_model for any set of GNM regions (cached on the head)."""
    key = "_nm_" + ",".join(regions)
    if key in head:
        return head[key]
    old = head.pop("_shade", None)
    global SHADE_REGIONS
    keep = SHADE_REGIONS
    try:
        SHADE_REGIONS = tuple(regions)
        head[key] = _shade_model(head)
    finally:
        SHADE_REGIONS = keep
        head.pop("_shade", None)
        if old is not None:
            head["_shade"] = old
    return head[key]


def _normals_of_model(head, view) -> dict:
    """The estimator's normals on the MODEL's own clay picture on the view's pixel grid (the differential reference of
    _normal_obs: the same estimator on picture and render, as the anchors)."""
    from . import facenormals as fnm
    cam = view["cam"]
    sc, org = float(view.get("scale", 1.0)), np.asarray(view.get("origin", (0.0, 0.0)), float)
    im = _clay_crop(head, view)[0] if "scale" in view else clay(head, cam)
    if im.size != view["img"].size:
        im = im.resize(view["img"].size)
    PL = (_cam_points(cam, np.asarray(head["L"], float)[:68])[1] - org) * sc
    return fnm.estimate(im, fnm.head_box(PL, im.size))


def _normal_obs(head, view, differential=None):
    """LEARNED SURFACE NORMALS as the interior observation (refread, 2026-10-11): at sampled visible skin vertices
    (NORMAL_REGIONS) the picture's normal from a monocular estimator (facenormals: camera frame) against the model's
    own: the two tangent components of the difference (radians), each moving with the vertex's normal (dn / dc from
    _shade_model, as the shading read). Nuisance per view: a small global ROTATION of the estimator's normals (3) and
    its RELIEF gain (1: estimators flatten or exaggerate the turn away from the camera). differential = the
    estimator's normals on a picture of the MODEL itself through the same camera ({"n", "box"}, facenormals.estimate):
    then the observation is estimate(picture) - estimate(model's picture), the estimator's own bias taken out."""
    from . import facenormals as fnm, humanfit
    sm = _normal_model(head)
    cam, kind = view["cam"], view["kind"]
    sc, org = float(view.get("scale", 1.0)), np.asarray(view.get("origin", (0.0, 0.0)), float)
    img = view["img"]
    Wd, Hd = img.size
    Rc = humanfit._cam_rot(cam)
    X = np.asarray(head["V"], float)[sm["idx"]]
    Xc, pc = _cam_points(cam, X)
    px = (pc - org) * sc
    nc_ = sm["N"] @ Rc.T
    _, ps = _clay_crop(head, view) if "scale" in view else clay(head, cam, passes=True)
    zb = ps["zb"]
    kz = zb.shape[0] / float(Hd)
    qx = np.clip(px[:, 0] * kz, 0, zb.shape[1] - 1).astype(int)
    qy = np.clip(px[:, 1] * kz, 0, zb.shape[0] - 1).astype(int)
    ok = (np.abs(zb[qy, qx] - Xc[:, 2]) < 0.004) & (-nc_[:, 2] > 0.35)
    ok &= (px[:, 0] >= 2) & (px[:, 0] < Wd - 2) & (px[:, 1] >= 2) & (px[:, 1] < Hd - 2)
    if "hair" in head and view.get("hair", True):
        ok &= ~np.asarray(head["hair"], bool)[sm["idx"]]
    if view.get("trust") is not None:
        from scipy import ndimage as ndi
        mmpx = float(cam["t"][2]) / cam["f"] * 1000.0 / sc
        tr = ndi.binary_erosion(np.asarray(view["trust"], bool), iterations=max(int(2.0 / mmpx), 1))
        ok &= tr[np.clip(px[:, 1].astype(int), 0, Hd - 1), np.clip(px[:, 0].astype(int), 0, Wd - 1)]
    if ok.sum() < 60:
        return []
    if "_nrm" not in view:
        PL = (_cam_points(cam, np.asarray(head["L"], float)[:68])[1] - org) * sc
        view["_nrm"] = fnm.estimate(img, fnm.head_box(PL, img.size))
    k = np.flatnonzero(ok)
    ne = fnm.at(view["_nrm"], px[k])
    ref = nc_[k]
    if differential is not None:
        ref = fnm.at(differential, px[k])
    g = np.isfinite(ne).all(1) & np.isfinite(ref).all(1)
    k, ne, ref = k[g], ne[g], ref[g]
    if len(k) > NORMAL_N:
        pick = np.round(np.linspace(0, len(k) - 1, NORMAL_N)).astype(int)
        k, ne, ref = k[pick], ne[pick], ref[pick]
    n = nc_[k]
    t1 = np.cross(n, [0.0, 1.0, 0.0])
    t1 /= np.maximum(np.linalg.norm(t1, axis=1, keepdims=True), 1e-9)
    t2 = np.cross(n, t1)
    dNc = np.einsum("knc,dc->knd", sm["dN"][:, k], Rc)                # (170, n, 3) camera frame
    zc = np.array([0.0, 0.0, -1.0])
    out = []
    for i in range(len(k)):
        for a, t in (("u", t1[i]), ("v", t2[i])):
            rot = np.cross(n[i], t)
            nu = {f"nr_{kind}_x": rot[0], f"nr_{kind}_y": rot[1], f"nr_{kind}_z": rot[2], f"nr_{kind}_gain": float(zc @ t)}
            out.append({"type": "normal", "view": "normal:" + kind, "name": f"normal_{kind}_{i}.{a}", "o": float((ne[i] - ref[i]) @ t),
                        "J": dNc[:, i] @ t, "sig": SIG_NORMAL, "nu": nu, "px": list(map(float, px[k[i]])),
                        "vid": int(sm["idx"][k[i]])})
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


ADAPT_MIN = 8                         # solve(adapt=True): groups (type, view) of at least this many reads get their own scale
CAM_LOOSE = 2.0                       # read(cam_first=n): the cameras-first rounds' freedom, x the cameras' sd
CHIN_LM = (7, 8, 9)                   # differential anchors always include the chin's three
SIZE_HOLD = False                     # compare(chin={"size": True}): the face's size held at the start head's (solve_report.size_row)
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
    keys = [k_ for k_ in (points or {}) if k_.startswith("lm") and k_[2:].isdigit() and int(k_[2:]) < 68]
    ch = view.get("chin") or {}
    cl = ch.get("chin_lm", CHIN_LM_AXES)
    if cl == "auto":          # reference_views resolves it per set (a side view present or not); a bare view: the old behaviour
        cl = "xy"
    chin_ax = {"xy": (0, 1), "y": (1,), "x": (0,), "fx": (0,) if view["kind"] == "front" else (), "none": ()}[cl]
    if keys and view["kind"] in ("front", "3q") and chin_ax:      # the CHIN: a picture's stored points often leave the jaw contour out
        keys += [f"lm{i}" for i in view.get("jaw_lm", CHIN_LM) if f"lm{i}" not in keys]   # (the detector guesses it); like with like it is the
    stretch = ch.get("lm_stretch", LM_STRETCH)        # table's own chin read, and nothing else sees the chin from the front
    P0 = np.asarray(det["P"], float)[[likeness.MP68[int(k_[2:])] for k_ in keys]].mean(0) if keys else np.zeros(2)
    for key in keys:
        i = int(key[2:])
        m = likeness.MP68[i]
        Jp, mm1 = _proj_jac_pt(view["cam"], L[i], head["LB"][:, i])
        p, q = Pm[m], np.asarray(det["P"], float)[m]
        sig = float(np.hypot(LM_SIG_DIFF, LM_PX * mm1)) * float(ch.get("lm_sig", LM_SIG_SCALE))
        for ax in ((0, 1) if i not in CHIN_LM else chin_ax):
            ob = {"type": "landmark", "view": view["kind"], "name": f"{key}.{'xy'[ax]}", "o": float(q[ax] - p[ax]) * mm1,
                  "J": Jp[ax] * mm1, "sig": sig, "p": list(map(float, p)), "q": list(map(float, q)),
                  "X": list(map(float, L[i])), "diff": True}
            if stretch:       # THE DETECTOR'S OWN STRETCH (chinread): its face on a photo is not its face on our clay render
                ob["nu"] = {f"lm_{view['kind']}_s{'xy'[ax]}": LM_STRETCH_UNIT * float(q[ax] - P0[ax]) * mm1}
            out.append(ob)
    if view["kind"] == "3q" and keys and "eye_X" in head and len(Pm) > max(likeness.MP_EYES):
        # BOTH IRIS CENTRES of a turned view (the detector's, picture - render): two irises pin its yaw (one limbus
        # does not: the profile and 3/4 cameras over-rotated 3.5-4 deg over four calls on Tess)
        xs = [float(e[0]) for e in head["eye_X"]]
        for s_, m in enumerate(likeness.MP_EYES):     # the subject's right eye first (world x smaller)
            j = int(np.argmin(xs)) if s_ == 0 else int(np.argmax(xs))
            Jp, mm1 = _proj_jac_pt(view["cam"], head["eye_X"][j], head["eye_B"][j])
            p, q = Pm[m], np.asarray(det["P"], float)[m]
            sig = float(np.hypot(SIG_IRIS_3Q, LM_PX * mm1))
            for ax in (0, 1):
                out.append({"type": "iris", "view": view["kind"], "name": f"iris_{'rl'[s_]}.{'xy'[ax]}", "o": float(q[ax] - p[ax]) * mm1,
                            "J": Jp[ax] * mm1, "sig": sig, "p": list(map(float, p)), "q": list(map(float, q)),
                            "X": list(map(float, head["eye_X"][j])), "diff": True})
    return out


def kind_of(yaw: float) -> str:
    a = abs(float(yaw or 0.0))
    return "front" if a < 20 else ("3q" if a < 70 else "profile")


VIEW_DOUBT = 15.0                     # degrees between a view's stated yaw and its fitted camera's turn: say so
KIND_SAY = {"front": "a front view", "3q": "a three-quarter view", "profile": "a profile"}


def view_yaw(cam: dict) -> float:
    """How far the head is turned from the camera, from the FITTED camera itself (degrees; 0 = facing it, 90 = a true
    profile): the angle between the camera's line of sight and the head's forward axis, about the vertical."""
    from . import humanfit
    f = humanfit._cam_rot(cam) @ np.array([0.0, -1.0, 0.0])      # the head's forward (-Y) in the camera's frame
    return float(np.degrees(np.arctan2(f[0], -f[2])))


def view_sanity(views: list, cameras: list) -> list:
    """Per reference view: what it was SAID to be against what its fitted camera says ({"stated", "fitted", "kind",
    "stated_kind", "warn"}). A "profile" whose camera sits at 72 degrees has no true side (the far brow shows: depth
    rides on one camera's angle); a "three-quarter" at 23 shows little more than the front."""
    out = []
    for v, cam in zip(views, cameras):
        st = abs(float(v.get("yaw", 0.0) or 0.0))
        if not cam:
            out.append({"stated": st, "fitted": None, "kind": kind_of(st), "stated_kind": kind_of(st), "warn": ""})
            continue
        fy = abs(view_yaw(cam))
        w = ""
        if abs(fy - st) > VIEW_DOUBT:
            nm = str(v.get("image", "")).split("/")[-1]
            w = (f"VIEW: {nm} was given as {KIND_SAY[kind_of(st)]} (yaw {st:.0f}) but its fitted camera is turned {fy:.0f} deg"
                 + (f" = {KIND_SAY[kind_of(fy)]}" if kind_of(fy) != kind_of(st) else "")
                 + (": NO TRUE SIDE VIEW (at this angle the far brow and cheek show in front of the profile line; forehead "
                    "slope, eye depth and chin projection ride on this one camera's angle: INFERRED)" if st >= 70 else
                    ": it shows less of the side than a 3/4 should (the far cheek's outline reads width, little depth)" if fy < st
                    else ""))
        out.append({"stated": st, "fitted": fy, "kind": kind_of(fy), "stated_kind": kind_of(st), "warn": w})
    return out


def reference_views(name: str, hair: bool = True, lids: bool = False, lips: bool = False, shade: bool = False,
                    anchors: str = "differential", parse: bool | str = False, normals: bool = False,
                    kinds: list | None = None, readers: list | None = None, jaw_lm=None, expr: bool = False,
                    jaw: bool = False, chin: dict | None = None) -> tuple:
    """A block-in model's reference pictures as the ruler's views: per picture its fitted camera, the skin's own
    outline where the picture has one (a profile in front of a plain background: blockin.profile_contour; any view's
    "outline" points), and on the front picture the iris centres (eye_ruler). -> (views, notes)."""
    from PIL import Image
    from . import blockin as bi, eye_ruler as er, humanfit, likeness, store
    rj = bi._refs(name)
    spec = store.load(name)
    head = model_head(spec, expr={"names": EXPR_SET} if expr else None)
    views, notes = [], []
    iris_mm = None
    chin = dict(chin or {})
    if chin.get("chin_lm", CHIN_LM_AXES) == "auto":
        side = any(cam and abs(view_yaw(cam)) >= SIDE_MIN for cam in rj["cameras"])
        chin["chin_lm"] = "none" if side else "xy"
        if side and anchors == "differential":
            notes.append("CHIN: the detector's chin points are left out: this set has a side view, whose outline reads the chin's "
                         "height and projection (the block-in table's chin_height / lower_third rows are the detector's: expect "
                         "them out by 2-4 mm where the side view disagrees with it)")
    for vi, (v, cam) in enumerate(zip(rj["views"], rj["cameras"])):
        # the READERS go by the view's STATED kind, fixed for the whole block-in (kinds). TRIED and wrong (solvereads):
        # the kind from the fitted camera. Tess's "profile" camera stands at 67 deg, so it became a second "3q": two
        # views of one kind share their camera columns here (obs are keyed by kind), and its readers changed (every
        # sigma x3.6, the camera turned 26 deg). What the fitted camera says is REPORTED instead (view_sanity, compare).
        k = kinds[vi] if kinds and vi < len(kinds) and kinds[vi] else kind_of(v.get("yaw", 0))
        img = Image.open(v["image"]).convert("RGB")
        view = {"img": img, "cam": cam, "kind": k, "style": "photo", "hair": hair, "name": str(v["image"]).split("/")[-1],
                "face_only": True, "reader": "points", "jaw": bool(jaw), "chin": dict(chin or {})}
        if jaw_lm:
            view["jaw_lm"] = tuple(jaw_lm)
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
            use = bool(parse) and parse != "auto"
            rd0 = readers[vi] if readers and vi < len(readers) else None
            if rd0 in ("plain", "parser"):       # ONE outline reader per view for a whole block-in (solve_step keeps it):
                use = rd0 == "parser"            # re-decided per call it flipped with the head (outline 211 -> 77 -> 160)
            elif parse == "auto":    # the plain-background reader where it works (a finer edge), the parser elsewhere
                n0 = sum(ob["type"] == "outline" for ob in observe(head, [dict(view, limbus=False, jaw=False)], colour=False))
                use = plain_backdrop(img) < PLAIN_MIN or n0 < PLAIN_READS
            view["reader"] = "parser" if use else "plain"
            if use:
                from . import faceparse
                try:
                    view["mask"], view["trust"], _ = faceparse.masks(img, cam, head, model=parse if parse in faceparse.SIZE else PARSE_MODEL)
                    view["outline_sig"] = PARSE_SIG
                    view["ears"] = True      # the parser knows hair from skin: an ear it shows bare is the head's outline
                    notes.append(f"{view['name']}: outline from the face parser ({parse if parse in faceparse.SIZE else PARSE_MODEL})")
                except (FileNotFoundError, RuntimeError, ValueError) as e:
                    notes.append(f"{view['name']}: the face parser is not available ({str(e)[:160]}): plain-background outline")
                    view["reader"] = "plain"
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
        if normals:      # OFF by default: failed its validation (the notes' "## refread", 3): differential against the
            extras.append(lambda h, vw: _normal_obs(h, vw, _normals_of_model(h, vw)))     # model's own clay picture
        view["extra"] = lambda h, vw, extras=tuple(extras): [ob for f in extras for ob in f(h, vw)]
        views.append(view)
    if iris_mm and np.isfinite(iris_mm):       # the turned views draw the limbus at the PICTURE's iris size (the limbus'
        for view in views:                     # plane lies 0.4 mm further forward for an iris 1.4 mm smaller)
            view["iris_mm"] = iris_mm
    return head, views, notes


def compare(name: str, rounds: int = 3, cam_sd=PHOTO_CAM_SD6, hair: bool = True, views: list | None = None,
            prior_off=None, lids: bool = False, lips: bool = False, shade: bool = False, anchors: str = "differential",
            parse: bool | str = False, normals: bool = False, cam_first: int = 0, adapt: bool = False,
            cam_done0=None, cmax: float | None = None, relax0: float = 1.0, hold=None, held0=None, expr: bool | str = False,
            expr_sd: float | None = None, kinds: list | None = None, readers: list | None = None, jaw_lm=None,
            jaw: bool = False, chin: dict | None = None) -> dict:
    """The face ruler on a block-in model: its reference pictures against the model, the 23 measures' gaps (picture -
    model, GNM's mm), largest first, each with the reader's error and its `mm:` move. {"rows", "text", "notes", "n"}."""
    only = views
    head, views, notes = reference_views(name, hair, lids=lids, lips=lips, shade=shade, anchors=anchors, parse=parse,
                                         normals=normals, kinds=kinds, readers=readers, jaw_lm=jaw_lm, expr=bool(expr), jaw=jaw, chin=chin)
    if only is not None:          # a subset of the pictures (indices): what one view alone says
        views = [v for i, v in enumerate(views) if i in set(int(j) for j in only)]
    tie = None
    tc = (chin or {}).get("tie", CHIN_TIE)
    if (chin or {}).get("size", SIZE_HOLD):
        tie = {"names": (), "size": True}
    if tc:
        from . import solve_report as sr
        side = any(abs(view_yaw(v["cam"])) >= 60.0 for v in views)       # a side view's outline reads the profile line
        t35 = [abs(view_yaw(v["cam"])) for v in views]
        names = tuple(sr.TIE) if isinstance(tc, (bool, int, float)) else (tuple(tc.split("+")) if isinstance(tc, str) else tuple(tc))
        if any(TIE_OPEN[0] <= y <= TIE_OPEN[1] for y in t35):            # a TRUE 3/4: the far jaw and chin make its silhouette
            names = tuple(n for n in names if n not in ("jaw_width", "gonial_width", "jaw_square"))
            notes.append("CHIN / JAW: a view turned 35-60 deg shows the far jaw on its silhouette: jaw width and squareness are left to the pictures")
        tie = {**(tie or {}), "names": names, "given": sr.TIE_GIVEN + (sr.TIE_GIVEN_SIDE if side else ()), "sig": float((chin or {}).get("tie_sig", sr.TIE_SIG))}
    res = read(head, views, rounds=rounds, cam_sd=cam_sd, cam_first=cam_first, adapt=adapt, cam_done0=cam_done0, cmax=cmax,
               relax0=relax0, hold=hold, held0=held0, tie=tie, expr_mode="shared" if expr == "shared" else "view", expr_sd=expr_sd,
               **({} if prior_off is None else {"prior_off": prior_off}))
    from . import gnm_mm
    sd = gnm_mm.sd()
    for r in res["gaps"]:
        r["picture"] = r["current"] + r["gap"]
        r["err"] = float(np.hypot(r["err"], MODEL_ERR[r["measure"]]))
        r["read"] = float(max(0.0, 1 - (r["err"] / sd[r["measure"]]) ** 2))
    n = {t: sum(ob["type"] == t for ob in res["obs"]) for t in ("outline", "iris", "landmark", "limbus", "lid", "lip", "jaw", "cloth", "ramp", "shade", "normal")}
    for r in res["orbit"]:        # the orbit rows' error: never under the block-in path's validated floor
        fl = np.sqrt(sum((w * MODEL_ERR[k]) ** 2 for k, w in gnm_mm.ORBIT_SEEN[r["row"]].items()))
        r["err"] = float(np.hypot(r["err"], fl))
        r["read"] = float(max(0.0, 1 - (r["err"] / r["sd"]) ** 2))
    cams = []
    if res.get("cam_post"):
        for v, done, post in zip(res["views"], res["cam_done"], res["cam_post"]):
            if len(done) > 4:
                cams.append(f"{v['kind']}: yaw {done[4]:+.1f} +-{post[4]:.1f} deg, pitch {done[5]:+.1f} +-{post[5]:.1f}")
    try:      # each view's stated kind against the camera the solve ended on
        from . import blockin as bi
        rv_ = bi._refs(name)["views"]
        if only is not None:
            rv_ = [v for i, v in enumerate(rv_) if i in set(int(j) for j in only)]
        notes = list(notes) + [x["warn"] for x in view_sanity(rv_, [v["cam"] for v in res["views"]]) if x["warn"]]
    except Exception:  # noqa: BLE001
        pass
    lim = sorted({(ob["view"], ob["name"][:8]) for ob in res["obs"] if ob["type"] == "limbus"})
    notes = list(notes) + [f"limbus read in: {', '.join(f'{a} {b}' for a, b in lim) or 'no turned view'}"]
    if res.get("relax", 1.0) > 1.0:
        notes.append(f"INCONSISTENT PICTURES: at their own sigmas the most likely head had a component past {cmax:g} sd; every "
                     f"read's sigma was raised x{res['relax']:.2f} until none did (the pictures disagree with each other or "
                     "with any one GNM head by that much: paintings, expressions, a wrong camera)")
    big = {k: v for k, v in (res.get("sig_scale") or {}).items() if v > 1.5}
    if big:
        notes.append("NOISIER than assumed (the head that fits best leaves these reads scattered; their sigma was raised by): "
                     + ", ".join(f"{t} {vw} x{v:.1f}" for (t, vw), v in sorted(big.items())))
    if cams:
        notes.append("cameras turned by the solve (their fitted yaw / pitch were left free): " + "; ".join(cams))
    per = {v["kind"]: sum(ob["view"] == v["kind"] for ob in res["obs"]) for v in views}
    head_txt = (f"face ruler: {name} against its {len(views)} pictures ({', '.join(f'{k}: {m} reads' for k, m in per.items())}); "
                "gap = picture - model in GNM's mm; cameras were fitted, so a shift / scale / roll of each picture is left free")
    views = res["views"]
    return {"rows": res["gaps"], "orbit": res["orbit"],
            "text": head_txt + "\n" + orbit_text(res["orbit"]) + "\n" + text(res["gaps"]) + ("\n" + "\n".join(notes) if notes else ""),
            "notes": notes, "n": n, "dc": res["dc"], "views": views, "head": head, "obs": res["obs"],
            "cam_done": res.get("cam_done"), "cam_post": res.get("cam_post"), "post": res.get("post"),
            "sig_scale": res.get("sig_scale") or {}, "relax": res.get("relax", 1.0), "cam_step": res.get("cam_step"),
            "held": res.get("held") or [], "tie": tie, "expr": res.get("expr") or {}, "kinds": [v["kind"] for v in views],
            "readers": [v.get("reader") for v in views]}




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
