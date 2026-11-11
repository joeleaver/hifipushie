"""The jaw's lower edge: against the neck (skin on skin), in front of cloth, and as a shading ramp under the
picture's light. Part of the face ruler (face_ruler.py has the overview)."""
from __future__ import annotations

import numpy as np

from .face_ruler import _C, _bil, _cam_points, _gnm, _proj_jac, clay
from .face_ruler_outline import PARSE_MODEL, _resample

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
    """The model's own render under the PICTURE's fitted light (blockin_look.lit_render: c0 + w.n, ambient occlusion, a soft
    cast shadow), in the view's picture pixels: (luminance 0..1, passes). The light is fitted once per view."""
    from PIL import Image
    from . import likeness
    from . import blockin_look
    cam, img = view["cam"], view["img"]
    w, h = cam["size"]
    if view.get("_light") is None:
        im, lt, ps = blockin_look.lit_render(head["mesh"], cam, img)
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
