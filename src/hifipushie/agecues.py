"""Age cues read on a face picture (a photo or a clay render) from its 478 MediaPipe points: the soft-tissue signs an
artist looks at for age, in landmark (mm) and shading (relative contrast) terms. The same readers run on the
Wikimedia age set (2D statistics, `agestats.npz`) and on the model's renders (the age step, blockin_age.py).

`canonical(img, P, ipd_mm)`: the face rotated level (pupils horizontal) and scaled to CANON_IPD px between the pupils
(a crop CANON_W x CANON_H); `cues(img, P, ipd_mm)`: {name: value} on that frame. mm come from the pupils' distance
(ipd_mm: 63 a default adult; the population sd is ~3 mm, so a single photo's mm are +-5 %); shading cues are contrasts
of luminance relative to its own 8 mm blur (light and skin tone mostly cancel; a flash flattens folds, so they are
statistics, not one picture's truth).

Geometry (mm, mean of both sides): eye open / cover (upper lid over the iris' top) / white_below / aspect / brow_gap
(brow's lower edge over the pupil -> lid margin) / brow_height (pupil -> brow's upper edge) / canthal_tilt (deg),
lip_upper / lip_lower (vermilion heights at the midline), mouth_w, corner_drop (mouth corners below the lips' seam),
philtrum, nose_w, lower_face (subnasale -> menton), jaw_ratio / lower_ratio (the contour's width at the jaw / at the
chin's sides over the cheekbones'; MediaPipe's contour is a guess on the lower face).
Shading: nl_depth (the nasolabial valley: median depth along the alar -> past-corner line, searched +-4 mm across),
nl_len (share of the line's lower part, below the mouth's corner level, where the valley is there), marionette (the
valley under the corners), trough (the deepest valley 3-16 mm under the lower lid: tear trough / bag shadow),
lid_tps (fold line height over the lashes, mm; nan = none), lid_line (share of the lid's columns with a fold line),
lid_dark, wr_forehead / wr_crow / wr_under (fine-line energy, 0.4-1.6 mm band, over the cheek's: wrinkles), and
glasses (horizontal-edge energy at the bridge: a quality flag, not a cue)."""
from __future__ import annotations

import numpy as np

CANON_IPD = 160.0
CANON_W, CANON_H = 480, 600
EYE_Y = 230.0
IRIS_C = (468, 473)
OVAL_L, OVAL_R = 234, 454


def _lum(a):
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def canonical(img, P, ipd_px: float = CANON_IPD):
    """(PIL image W x H, points in it): the face level, pupils at (W/2 -+ ipd/2, EYE_Y)."""
    from PIL import Image
    P = np.asarray(P, float)[:, :2]
    a, b = P[IRIS_C[0]], P[IRIS_C[1]]
    if a[0] > b[0]:
        a, b = b, a
    d = b - a
    s = float(np.linalg.norm(d)) / ipd_px          # source px per canonical px
    ang = np.arctan2(d[1], d[0])
    c, si = np.cos(ang) * s, np.sin(ang) * s
    mid = 0.5 * (a + b)
    # source = R * s * (q - q0) + mid, q0 = canonical pupils' midpoint
    q0 = np.array([CANON_W / 2, EYE_Y])
    A = np.array([[c, -si], [si, c]])
    off = mid - A @ q0
    im = img.convert("RGB").transform((CANON_W, CANON_H), Image.AFFINE, (A[0, 0], A[0, 1], off[0], A[1, 0], A[1, 1], off[1]),
                                      resample=Image.BICUBIC)
    Q = (np.linalg.inv(A) @ (P - off).T).T
    return im, Q


def _bil(L, x, y):
    h, w = L.shape
    x = np.clip(np.asarray(x, float), 0, w - 1.001)
    y = np.clip(np.asarray(y, float), 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return (L[y0, x0] * (1 - fx) * (1 - fy) + L[y0, x0 + 1] * fx * (1 - fy) + L[y0 + 1, x0] * (1 - fx) * fy
            + L[y0 + 1, x0 + 1] * fx * fy)


def _valley(prof, xs, w_mm, side_mm):
    """Depth of the darkest valley within |x| <= w_mm against the brighter of... the dimmer of the two sides' maxima
    (within side_mm beyond it): (ref - min) / ref; 0 when the profile has no valley there. Returns (depth, x)."""
    inner = np.abs(xs) <= w_mm
    if not inner.any():
        return 0.0, np.nan
    i = np.flatnonzero(inner)[np.argmin(prof[inner])]
    left = prof[(xs < xs[i]) & (xs >= xs[i] - side_mm)]
    right = prof[(xs > xs[i]) & (xs <= xs[i] + side_mm)]
    if len(left) == 0 or len(right) == 0:
        return 0.0, np.nan
    ref = min(left.max(), right.max())
    return max(0.0, float((ref - prof[i]) / max(ref, 1e-6))), float(xs[i])


def cues(img, P, ipd_mm: float = 63.0, canon: bool = True) -> dict:
    from scipy.ndimage import gaussian_filter
    from . import likeness_eyes, lidfold
    if canon:
        img, P = canonical(img, P)
    P = np.asarray(P, float)
    mm = ipd_mm / float(np.linalg.norm(P[IRIS_C[1]] - P[IRIS_C[0]]))    # mm per px
    px = 1.0 / mm
    ex, ey = likeness_eyes.frame(P)
    ex, ey = np.asarray(ex, float), np.asarray(ey, float)
    out = {}
    # ---- geometry ----
    em = likeness_eyes.measures(P, mm)
    for k in ("open", "cover", "white_below", "aspect", "brow_gap", "brow_height", "canthal_tilt"):
        out[k] = float(np.mean(em[k]))
    g = lambda i: P[i]  # noqa: E731
    out["lip_upper"] = float((g(13) - g(0)) @ ey) * mm
    out["lip_lower"] = float((g(17) - g(14)) @ ey) * mm
    out["mouth_w"] = float(np.linalg.norm(g(291) - g(61))) * mm
    seam = 0.5 * (g(13) + g(14))
    out["corner_drop"] = float((0.5 * (g(61) + g(291)) - seam) @ ey) * mm
    out["philtrum"] = float((g(0) - g(2)) @ ey) * mm
    out["nose_w"] = float(np.linalg.norm(g(294) - g(64))) * mm
    out["lower_face"] = float((g(152) - g(2)) @ ey) * mm
    cheek = float(np.linalg.norm(g(OVAL_R) - g(OVAL_L)))
    out["jaw_ratio"] = float(np.linalg.norm(g(397) - g(172))) / cheek
    out["lower_ratio"] = float(np.linalg.norm(g(365) - g(136))) / cheek
    # ---- shading ----
    A = np.asarray(img.convert("RGB"), float) / 255.0
    L = _lum(A) + 1e-3
    Lr = L / gaussian_filter(L, 8 * px)
    Ls = gaussian_filter(Lr, 0.35 * px)
    xs = np.arange(-8.0, 8.01, 0.25)

    def prof_at(p, nrm):
        q = p[None, :] + (xs * px)[:, None] * nrm[None, :]
        return _bil(Ls, q[:, 0], q[:, 1])

    # nasolabial: alar crease side (129 / 358) -> the corner (61 / 291) moved 3 mm out, continued past it
    nl, nl_low = [], []
    for al, cor, sgn in ((129, 61, -1), (358, 291, 1)):
        a = g(al)
        b = g(cor) + sgn * 3 * px * ex
        d = b - a
        nrm = np.array([d[1], -d[0]]) / max(np.linalg.norm(d), 1e-9)
        for t in np.linspace(0.15, 1.45, 14):
            dep, _ = _valley(prof_at(a + t * d, nrm), xs, 4.0, 4.0)
            (nl if t <= 1.0 else nl_low).append(dep)
    out["nl_depth"] = float(np.median(nl))
    out["nl_len"] = float(np.mean(np.array(nl_low) > 0.03))
    # marionette: down from the corner, 1.5 mm out, profiles across
    mar = []
    for cor, sgn in ((61, -1), (291, 1)):
        for dz in (4.0, 8.0, 12.0):
            p = g(cor) + sgn * 1.5 * px * ex + dz * px * ey
            mar.append(_valley(prof_at(p, ex), xs, 4.0, 4.0)[0])
    out["marionette"] = float(np.median(mar))
    # under the eye: columns at 30 / 50 / 70 % of the eye, profile down from the lower lid
    ys = np.arange(1.0, 22.0, 0.25)
    tr = []
    for inner, outer, low in ((133, 33, 145), (362, 263, 374)):
        for f in (0.3, 0.5, 0.7):
            x0 = g(inner) + f * (g(outer) - g(inner))
            p0 = x0 + float((g(low) - x0) @ ey) * ey
            q = p0[None, :] + (ys * px)[:, None] * ey[None, :]
            pr = _bil(Ls, q[:, 0], q[:, 1])
            sel = (ys >= 3) & (ys <= 16)
            i = np.flatnonzero(sel)[np.argmin(pr[sel])]
            up, dn = pr[:i], pr[i + 1:]
            if len(up) and len(dn):
                ref = min(up.max(), dn[: int(6 / 0.25)].max() if len(dn) else up.max())
                tr.append(max(0.0, float((ref - pr[i]) / max(ref, 1e-6))))
    out["trough"] = float(np.median(tr)) if tr else np.nan
    # lids: lidfold's fold line reader on this frame
    try:
        cols = [c for side in lidfold.read_lid(img, P, mmpx=mm) for c in side]
        tps = [c["tps"] for c in cols if c["dark"] >= 0.03 and np.isfinite(c["tps"])]
        out["lid_line"] = float(len(tps) / max(len(cols), 1))
        out["lid_tps"] = float(np.median(tps)) if tps else np.nan
        out["lid_dark"] = float(np.mean([c["dark"] for c in cols]))
    except Exception:  # noqa: BLE001
        out["lid_line"], out["lid_tps"], out["lid_dark"] = np.nan, np.nan, np.nan
    # fine lines: band-pass of log luminance, rms in boxes / the cheek's
    lg = np.log(L)
    band = gaussian_filter(lg, 0.4 * px) - gaussian_filter(lg, 1.6 * px)

    def rms(cx, cy, hw, hh):
        c = np.array([cx, cy])
        u = np.arange(-hw, hw + 1e-9, 0.5) * px
        v = np.arange(-hh, hh + 1e-9, 0.5) * px
        U, V = np.meshgrid(u, v)
        q = c[None, :] + U.reshape(-1, 1) * ex[None, :] + V.reshape(-1, 1) * ey[None, :]
        return float(np.sqrt(np.mean(_bil(band, q[:, 0], q[:, 1]) ** 2)))

    pl, pr_ = g(IRIS_C[0]), g(IRIS_C[1])
    mid = 0.5 * (pl + pr_)
    brow_top = 0.5 * (g(105) + g(334))
    fh = brow_top - 14 * px * ey
    ch = []
    for al, sgn in ((129, -1), (358, 1)):
        ch.append(rms(*(g(al) + sgn * 14 * px * ex - 4 * px * ey), 5, 5))
    cheek_rms = max(float(np.mean(ch)), 1e-6)
    out["cheek_rms"] = cheek_rms
    out["wr_forehead"] = rms(fh[0], fh[1], 16, 8) / cheek_rms
    crow = [rms(*(g(o) + sgn * 10 * px * ex), 6, 7) for o, sgn in ((33, -1), (263, 1))]
    out["wr_crow"] = float(np.mean(crow)) / cheek_rms
    und = [rms(*(g(lo) + 6 * px * ey), 8, 3) for lo in (145, 374)]
    out["wr_under"] = float(np.mean(und)) / cheek_rms
    # glasses: horizontal edges over the bridge between the inner corners (a rim / bridge of a frame)
    gy = np.abs(np.diff(Ls, axis=0))
    nas = g(168)
    u = np.arange(-4, 4.01, 0.5) * px
    v = np.arange(-6, 6.01, 0.5) * px
    U, V = np.meshgrid(u, v)
    q = nas[None, :] + U.reshape(-1, 1) * ex[None, :] + V.reshape(-1, 1) * ey[None, :]
    out["glasses"] = float(np.percentile(_bil(gy, q[:, 0], q[:, 1]), 95))
    out["_mm_per_px"] = mm
    return {k: (round(float(v), 4) if np.isfinite(v) else float("nan")) for k, v in out.items()}


def pose(M) -> dict:
    """yaw / pitch / roll (deg) from MediaPipe's facial transformation matrix."""
    if M is None:
        return {"yaw": np.nan, "pitch": np.nan, "roll": np.nan}
    R = np.asarray(M, float)[:3, :3]
    yaw = float(np.degrees(np.arctan2(R[0, 2], R[2, 2])))
    pitch = float(np.degrees(np.arcsin(-np.clip(R[1, 2], -1, 1))))
    roll = float(np.degrees(np.arctan2(R[1, 0], R[1, 1])))
    return {"yaw": yaw, "pitch": pitch, "roll": roll}
