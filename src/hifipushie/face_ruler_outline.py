"""Outlines and colour features read from a picture: the silhouette, the hair's edge, the iris, lips and brows. Part of the face ruler (face_ruler.py has the overview)."""
from __future__ import annotations

import numpy as np

from .face_ruler import REACH_MM, SIG, STEP_MM, _cam_points, _proj_jac

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


HAIR_EDGE = True            # reference_views(hair_edge=None) takes this
SIG_HAIR_EDGE = 0.8         # mm: a skin | hair boundary off the parser (its outline reads: 0.5; + strands lying on the skin)
HAIR_EDGE_MIN = 0.5         # mm: the read is ONE-SIDED: only a boundary this far OUTSIDE the model's outline pulls
OUTLINE_FEW = 20            # a view with fewer two-sided outline reads than this is said to have none worth the name


def _hair_edge_obs(head, view, mask_model):
    """THE FACE'S EDGE UNDER LOOSE HAIR, ONE-SIDED (readmix, after familynative's finding 1: with hair down both sides
    the figure's outline is hair everywhere and a front picture gave ZERO outline reads; every face width was the
    prior's). Where the parser says the picture's SKIN ends against HAIR (not background), the face's true edge lies
    AT or OUTSIDE that boundary (hair hangs in front of the cheek or behind it; skin is never drawn where there is no face). So
    the boundary is read like an outline, but only where it lies OUTSIDE the model's own outline (the model is too
    narrow there: it must reach at least the skin the picture shows); where the model is already outside it nothing is
    said. view["hair_edge"] = {"skin", "hair"} picture masks (faceparse)."""
    he = view.get("hair_edge")
    if not he or "gid" not in head or "ears" not in head:
        return []
    skin, hair = np.asarray(he["skin"], bool), np.asarray(he["hair"], bool)
    H, W = hair.shape
    out = []
    # the head's own skin from the chin up, ears and scalp left out (an ear under hair is not seen; the neck is a pose):
    # in a front view the cheek's and the jaw's silhouette is made by vertices beside GNM's face mask, so "face" alone
    # would leave the jaw line's last centimetres only
    V = np.asarray(head["V"], float)
    keep = (np.asarray(head["gid"], int) >= 0) & ~np.asarray(head["ears"], bool) & ~hair_vertices(head) & (V[:, 2] > float(np.asarray(head["L"], float)[8, 2]) + 0.004)
    for ob in _outline_obs(head, view, mask_model, skin, None):
        if not keep[ob["v"]] or ob["o"] < HAIR_EDGE_MIN:
            continue
        q, n = np.asarray(ob["q"], float), np.asarray(ob["n"], float)
        ok = True
        for b in (3.0, 6.0):                  # HAIR just outside the skin's edge, twice (background there = an ordinary outline)
            qo = np.clip(np.round(q + b * n).astype(int), 0, [W - 1, H - 1])
            ok &= bool(hair[qo[1], qo[0]])
        if not ok:
            continue
        ob["type"], ob["sig"], ob["name"] = "hairedge", SIG_HAIR_EDGE, "hairedge"
        out.append(ob)
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
