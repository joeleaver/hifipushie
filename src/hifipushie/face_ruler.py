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
REACH_MM = 14.0          # an outline further than this from the model's is not matched
TAU = 1.0                # prior sd of each identity component of (target - model)
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
    out = likeness.render(_mesh(head), cam, (0, 0, w, h), px=max(w, h), brows=True, light=light, passes=passes)
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


def _outline_obs(head, view, mask_model, mask_pic, trust=None):
    """Offsets (mm, + = the picture's outline lies outside the model's) at steps along the model's outline, each with
    the vertex that makes it. trust: bool picture mask of where the picture's outline is the head's own skin / skull
    (None = everywhere)."""
    from scipy.spatial import cKDTree
    cam = view["cam"]
    s = float(view.get("scale", 1.0))
    cm, cp = _curve(mask_model), _curve(mask_pic)
    if cm is None or cp is None:
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
        if trust is not None:
            qi = np.clip(np.round(qp - 2.0 * N[k]).astype(int), 0, [W - 1, H - 1])
            if not trust[qi[1], qi[0]]:
                continue
        v = int(sv[iv[k]])
        Jp, mm1 = _proj_jac(cam, head, v)
        out.append({"type": "outline", "view": view["kind"], "o": float(along[j]) * mm1 / s, "J": (N[k] @ Jp) * mm1,
                    "sig": SIG["outline"], "v": v, "p": S[k].tolist(), "n": N[k].tolist(), "q": qp.tolist()})
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
        for ax in axes:
            out.append({"type": typ, "view": kind, "name": f"{name}.{'xy'[ax]}", "o": float(pb[ax] - pa[ax]) * mm1 / s,
                        "J": Jp[ax] * mm1, "sig": sig or SIG[typ], "p": list(map(float, pa)), "q": list(map(float, pb))})

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
            ya = np.where(ba[:, x - w:x + w + 1].any(1))[0]
            yb = np.where(bb[:, x - w:x + w + 1].any(1))[0]
            ya = ya[np.abs(ya - PL[lm, 1]) < 60 * s]
            yb = yb[np.abs(yb - PL[lm, 1]) < 60 * s]
            if len(ya) and len(yb):
                wi = np.where(head["WL"][lm] > 0)[0]
                add("brows", f"brow_{lm}", [x, float(ya.min())], [x, float(yb.min())], wi, head["WL"][lm][wi], axes=(1,))
    if kind == "profile":
        # where the lip colour meets the outline: the reds' top and bottom heights on the profile
        for nm, lm in (("top", 51), ("bottom", 57)):
            ra, rb = _profile_lip(lip_mask(A), PL, nm), _profile_lip(lip_mask(B), PL, nm)
            if ra is not None and rb is not None:
                wi = np.where(head["WL"][lm] > 0)[0]
                add("lips", nm, [0.0, ra], [0.0, rb], wi, head["WL"][lm][wi], axes=(1,))
    return out


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
            mp = view.get("mask")
            if mp is None:
                mp = foreground(view["img"])
            oo = _outline_obs(head, view, ps["part"] >= 0, np.asarray(mp, bool), view.get("trust"))
            if view.get("hair"):
                hv = hair_vertices(head)
                oo = [ob for ob in oo if not hv[ob["v"]]]
            obs += oo
        if colour and view.get("style", "clay") == "clay" and view.get("colour", True):
            obs += _colour_obs(head, view, im_m, view["img"])
        obs += list(view.get("extra_obs") or [])
    return obs


def _clay_crop(head, view):
    from . import likeness
    cam, s, o = view["cam"], float(view["scale"]), view.get("origin", (0.0, 0.0))
    w, h = view["img"].size
    box = (o[0], o[1], o[0] + w / s, o[1] + h / s)
    out = likeness.render(_mesh(head), cam, box, px=max(w, h), brows=True, passes=True)
    return out[0], out[2]


def _cam_columns(obs, views, cam_sd):
    """Nuisance columns for a camera that was FITTED (its shift, scale and roll are not known exactly): per view the
    observation's change per mm of shift (x, y), per 1 % of scale, per degree of roll."""
    cols, pri = [], []
    for view in views:
        k = view["kind"]
        sc = float(view.get("scale", 1.0))
        c = (np.asarray(view["cam"]["size"], float) / 2 - np.asarray(view.get("origin", (0.0, 0.0)), float)) * sc
        mm = float(view["cam"]["t"][2]) / view["cam"]["f"] * 1000.0 / sc
        for j, (nm, sd) in enumerate(zip(("dx", "dy", "scale", "roll"), cam_sd)):
            col = np.zeros(len(obs))
            for i, ob in enumerate(obs):
                if ob["view"] != k:
                    continue
                p = (np.asarray(ob["p"], float) - c) * mm                # mm from the picture's centre
                d = {0: np.array([1.0, 0.0]), 1: np.array([0.0, 1.0]), 2: 0.01 * p,
                     3: np.radians(1.0) * np.array([-p[1], p[0]])}[j]
                if ob["type"] == "outline":
                    col[i] = d @ np.asarray(ob["n"])
                else:
                    col[i] = d[0] if ob["name"].endswith(".x") else d[1]
            cols.append(col)
            pri.append(sd)
    return np.array(cols).T, np.array(pri)


def solve(obs: list, head: dict, tau: float = TAU, span: bool = False, cam_sd=None, views=None, huber: float = 2.5,
          weights: dict | None = None, done=None) -> dict:
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
    m0 = np.zeros(len(pri))
    if done is not None and not span:      # a later round: the prior is on the WHOLE change (done + this step)
        m0[:K] = -np.asarray(done, float)
    w = 1.0 / sig ** 2
    for _ in range(3):
        A = (Jx * w[:, None]).T @ Jx + np.diag(1.0 / pri ** 2)
        Ai = np.linalg.inv(A)
        th = Ai @ (Jx.T @ (w * o) + m0 / pri ** 2)
        r = (o - Jx @ th) / sig
        w = 1.0 / sig ** 2 * np.minimum(1.0, huber / np.maximum(np.abs(r), 1e-9))
    n1 = len(th) - nc
    if span:
        g, cov = th[:n1], Ai[:n1, :n1]
        dc = D @ g
    else:
        dc = th[:n1]
        g, cov = Jm @ dc, Jm @ Ai[:n1, :n1] @ Jm.T
    err = np.sqrt(np.maximum(np.diag(cov), 0))
    sd = gnm_mm.sd()
    rows = []
    for i, n in enumerate(names):
        prior = np.sqrt(2.0) * tau * sd[n] if not span else np.inf
        rows.append({"measure": n, "current": head["measures"][n], "gap": float(g[i]), "sd": float(g[i] / sd[n]),
                     "err": float(err[i]), "read": float(1 - (err[i] / (tau * sd[n])) ** 2) if not span else 1.0,
                     "view": gnm_mm.SEE[n][0], "see": gnm_mm.SEE[n][1]})
    rows.sort(key=lambda r: -abs(r["sd"]))
    return {"dc": dc, "gaps": rows, "n": len(obs), "rms": float(np.sqrt(np.mean(r ** 2))),
            "cam": th[n1:].tolist() if nc else None}


def read(head: dict, views: list, rounds: int = 3, **kw) -> dict:
    """The ruler: the pictures against the model, `rounds` Gauss-Newton rounds (the outline's maker and normal are
    re-taken on the moved head: one round is off by the step's curvature when the gap is large). Gaps are the measures
    of the fitted head minus the model's."""
    from . import gnm_mm
    if head.get("kind") != "gnm" or kw.get("span"):
        rounds = 1
    done = np.zeros(head["B"].shape[0])
    cur = head
    for k in range(rounds):
        obs = observe(cur, views)
        out = solve(obs, cur, views=views, done=done if k else None, **kw)
        done = done + out["dc"]
        if k + 1 < rounds:
            cur = gnm_head(head["c"] + done)
    if rounds > 1:
        fin = gnm_head(head["c"] + done)
        sd = gnm_mm.sd()
        for r in out["gaps"]:
            r["gap"] = fin["measures"][r["measure"]] - head["measures"][r["measure"]]
            r["current"], r["sd"] = head["measures"][r["measure"]], r["gap"] / sd[r["measure"]]
        out["gaps"].sort(key=lambda r: -abs(r["sd"]))
    out["dc"], out["obs"] = done, obs
    return out


def text(rows: list, top: int = 0, floor: float = 0.0) -> str:
    """The ruler's table: one line per measure, target - current, the reader's error, the move that closes it."""
    out = ["measure            target - current   +-err   move that closes it          what + looks like"]
    for r in rows[: top or None]:
        if abs(r["gap"]) < floor:
            continue
        mv = '"mm:%s": %+.1f' % (r["measure"], r["gap"])
        flag = "" if abs(r["gap"]) > 2 * r["err"] else "  (inside the reader's error)"
        out.append(f"{r['measure']:18s} {r['gap']:+6.1f} mm ({r['sd']:+.1f} sd) +-{r['err']:.1f}  {mv:28s} "
                   f"[{r['view']}] {r['see']}{flag}")
    return "\n".join(out)
