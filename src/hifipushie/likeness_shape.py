"""Likeness, part 2: the SHAPE items (planes, hollows, folds, the jaw's L) that distances between landmarks miss, the
reference's camera refit, hand-placed points, and the picture set's coverage.

Shape is read two ways:
- on the MODEL in 3D (`measures3d`): mm on horizontal / vertical sections of the head (cheek hollow, nasolabial fold,
  under-eye hollow below the hull, the planes' corner radius at temple / cheekbone / jaw, the brow ridge in front of the
  cornea). These numbers compare models with each other (staged fit vs hand passes) and are what a control moves.
- against the PHOTO through its shading (`shading`): a light is fitted to the photo on the MODEL's normals (luminance
  = c0 + w . n over the face's skin, robust), so the model, lit that way, is what the photo would look like if the
  photo's face had the model's shape. Where the photo is darker than that prediction (a region against a nearby
  reference region, both on the face's skin), the photo's surface turns away from the light more there: a deeper
  hollow, a sharper corner, a more projecting brow over a shadowed socket. Confounded by albedo (stubble, paint,
  make-up) and by a painter's light, so it is read with low confidence and the focus panels show the model LIT LIKE
  THE PHOTO beside it.

The jaw's L (Joe, on the desk painting: a near-vertical ramus, a sharp gonial angle, a crisp lower border forward to
the chin, the neck stepping in under it) is measured from a TRACE on the reference (`likeness_points.json`: points and
polylines placed by a person or an LLM, the detector has no gonion) against the model's own jaw contour found along that
trace in its render (the depth edge where the jaw occludes the neck, or its silhouette).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

POINTS = "likeness_points.json"
SHADE_TOL = 8.0          # % of the face's median luminance: models differ by 20-80% on these contrasts; albedo biases the zero
PAIRS = {}               # (filled below) MediaPipe right -> left index for the regions used here


# ---- hand-placed points (likeness_points.json; the format shared with onemesh2's traces) ---------------------------

def load_points(name: str) -> dict:
    """{image path: {"points": {name: [u, v]}, "lines": {name: [[u, v], ...]}}} from <model>/likeness_points.json."""
    from . import store
    p = store.HOME / name / POINTS
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    return {v["image"]: {"points": v.get("points", {}), "lines": v.get("lines", {}), "by": v.get("by", "")}
            for v in d.get("views", [])}


def set_points(name: str, image: str, points: dict | None = None, lines: dict | None = None, by: str = "",
               note: str = "", replace: bool = False) -> dict:
    """Store hand-placed points / polylines for one reference picture (pixels of the full picture, u right, v down;
    .R / .L = the subject's right / left). Merged name by name unless replace (None deletes a name)."""
    from . import store
    p = store.HOME / name / POINTS
    d = json.loads(p.read_text()) if p.exists() else {"format": 1, "views": []}
    v = next((x for x in d["views"] if x["image"] == image), None)
    if v is None or replace:
        if v is not None:
            d["views"].remove(v)
        v = {"image": image, "points": {}, "lines": {}}
        d["views"].append(v)
    for key, new in (("points", points), ("lines", lines)):
        for k, val in (new or {}).items():
            if val is None:
                v[key].pop(k, None)
            else:
                v[key][k] = val
    if by:
        v["by"] = by
    if note:
        v["note"] = note
    p.write_text(json.dumps(d, indent=1))
    return d


# ---- 3D shape on the model ------------------------------------------------------------------------------------------

def _tris(st):
    from . import humanfit
    return np.array([(f[0], f[j], f[j + 1]) for f in humanfit._faces(st["tpl"]) for j in range(1, len(f) - 1)])


def _section(P, T, axis: int, c: float, keep=(0, 1)):
    """Crossings of the mesh with the plane P[:, axis] = c: (n, 2) points on the kept axes."""
    d = P[T, axis] - c
    cr = (d.min(1) < 0) & (d.max(1) > 0)
    out = []
    for t, d_ in zip(T[cr], d[cr]):
        for a, b in ((0, 1), (1, 2), (2, 0)):
            if (d_[a] < 0) != (d_[b] < 0):
                u = d_[a] / (d_[a] - d_[b])
                q = P[t[a]] + u * (P[t[b]] - P[t[a]])
                out.append(q[list(keep)])
    return np.array(out)


def _hull_deficit(cont, extra=None) -> float:
    """The deepest point of a contour inside its convex hull (m)."""
    from scipy.spatial import ConvexHull
    pts = cont if extra is None else np.r_[cont, extra]
    if len(cont) < 5:
        return 0.0
    h = ConvexHull(pts)
    dmin = np.full(len(cont), np.inf)
    for eq in h.equations:
        dmin = np.minimum(dmin, -(cont @ eq[:2] + eq[2]))
    return float(max(dmin.max(), 0.0))


def _polar_contour(S, c, a0, a1, n=40):
    ang = np.arctan2(S[:, 0] - c[0], c[1] - S[:, 1])
    rad = np.linalg.norm(S - c, axis=1)
    lo, hi = min(a0, a1), max(a0, a1)
    cont = []
    for b0, b1 in zip(np.linspace(lo, hi, n)[:-1], np.linspace(lo, hi, n)[1:]):
        k = (ang >= b0) & (ang < b1)
        if k.any():
            cont.append(S[k][np.argmax(rad[k])])
    return np.array(cont)


def _cheek_band(st, P, T, f0, f1, levels) -> float:
    """Deepest hull deficit (mm, mean of the two sides) of the face's horizontal contour between angle fractions f0..f1
    of the way from the nose's wing (0) to the jaw contour (1), round a centre inside the face (as humanfit's cheek
    hollow); negative fractions run from the wing toward the midline."""
    L = st["L"]
    mid = 0.5 * (L[68] + L[69])
    out = []
    for side, wing, jaw in ((-1, 31, 2), (1, 35, 14)):
        best = 0.0
        for zc in levels:
            S = _section(P, T, 2, zc)
            if len(S) < 10:
                continue
            c = np.array([mid[0], 0.5 * (L[2, 1] + L[14, 1])])
            aw = np.arctan2(L[wing, 0] - c[0], c[1] - L[wing, 1])
            aj = np.arctan2(L[jaw, 0] - c[0], c[1] - L[jaw, 1])
            cont = _polar_contour(S, c, aw + f0 * (aj - aw), aw + f1 * (aj - aw))
            if len(cont) >= 8:
                best = max(best, _hull_deficit(cont, c[None]))
        out.append(best)
    return float(np.mean(out)) * 1000


def _corner_radius(V, z0, xc, yc) -> float:
    """The tightest turn (mm) of the head's horizontal section 30-80 deg round from the front (base.plane_measures)."""
    from scipy.ndimage import gaussian_filter1d
    P = V[np.abs(V[:, 2] - z0) < 0.0015][:, :2] - [xc, yc]
    if len(P) < 20:
        return float("nan")
    th = np.degrees(np.arctan2(np.abs(P[:, 0]), -P[:, 1]))
    r = np.linalg.norm(P, axis=1)
    out = []
    for side in (1, -1):
        s = np.sign(P[:, 0]) == side
        bins = np.arange(0, 100, 2.0)
        R = np.array([r[s & (th >= b) & (th < b + 2)].max() if (s & (th >= b) & (th < b + 2)).any() else np.nan for b in bins])
        ok = ~np.isnan(R)
        if ok.sum() < 10:
            continue
        R = gaussian_filter1d(np.interp(bins, bins[ok], R[ok]), 1.5)
        t = np.radians(bins + 1)
        dr = np.gradient(R, t)
        ddr = np.gradient(dr, t)
        k = np.abs(R ** 2 + 2 * dr ** 2 - R * ddr) / (R ** 2 + dr ** 2) ** 1.5
        out.append(1000 / k[(bins >= 30) & (bins <= 80)].max())
    return float(np.mean(out)) if out else float("nan")


def _front_profile(P, T, x, z0, z1):
    """The frontmost surface (min y) of the vertical section x = const for z in [z0, z1]: (z, y) arrays."""
    S = _section(P, T, 0, x, keep=(1, 2))
    if len(S) == 0:
        return np.zeros(0), np.zeros(0)
    zs = np.linspace(min(z0, z1), max(z0, z1), 40)
    ys = []
    for a, b in zip(zs[:-1], zs[1:]):
        k = (S[:, 1] >= a) & (S[:, 1] < b)
        ys.append(S[k, 0].min() if k.any() else np.nan)
    zc = 0.5 * (zs[:-1] + zs[1:])
    ok = ~np.isnan(ys)
    return zc[ok], np.asarray(ys)[ok]


def measures3d(st: dict) -> dict:
    """The model's shape numbers (mm): cheek_hollow, nasolabial_fold, under_eye, corner_temple / _cheekbone / _jaw
    (radius of the front-to-side turn: smaller = a crisper plane change), brow_ridge (how far the brow stands in front of
    the cornea above the pupil)."""
    P = np.asarray(st["tpl"]["P"], float)
    T = _tris(st)
    L = st["L"]
    eyes = st["head"]["eyes"]
    r_eye = float(st["head"].get("eye_r", 0.012))
    io = abs(L[68, 0] - L[69, 0])
    lv = np.linspace(L[33, 2], 0.5 * (L[48, 2] + L[54, 2]), 3)
    out = {"cheek_hollow": _cheek_band(st, P, T, 0.4, 1.0, lv),
           "nasolabial_fold": _cheek_band(st, P, T, -0.6, 0.4, lv)}
    xc, yc = 0.5 * (L[0, 0] + L[16, 0]), 0.5 * (L[0, 1] + L[16, 1]) + 0.01
    out["corner_temple"] = _corner_radius(P, L[24, 2] + 0.01, xc, yc)
    out["corner_cheekbone"] = _corner_radius(P, L[68, 2] - 0.35 * io, xc, yc)
    out["corner_jaw"] = _corner_radius(P, 0.5 * (L[4, 2] + L[12, 2]), xc, yc)
    ue, br = [], []
    for e, lid, brow in ((eyes[0], 47, 24), (eyes[1], 40, 19)):
        e = np.asarray(e, float)
        z, y = _front_profile(P, T, e[0], L[lid, 2] - 0.002, L[lid, 2] - 0.30 * io)
        if len(z) >= 6:
            ue.append(_hull_deficit(np.c_[z, -y]) * 1000)
        z, y = _front_profile(P, T, e[0], L[brow, 2] - 0.006, L[brow, 2] + 0.006)
        if len(z):
            br.append((e[1] - r_eye - y.min()) * 1000)
    out["under_eye"] = float(np.mean(ue)) if ue else float("nan")
    out["brow_ridge"] = float(np.mean(br)) if br else float("nan")
    return {k: round(float(v), 2) for k, v in out.items()}


# ---- shading: a light fitted to the photo on the model's normals ---------------------------------------------------

def _lin(img) -> np.ndarray:
    a = np.asarray(img.convert("RGB"), float) / 255.0
    a = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    return a @ [0.2126, 0.7152, 0.0722]


def _disk(H, W, c, r):
    yy, xx = np.mgrid[0:H, 0:W]
    return (xx + 0.5 - c[0]) ** 2 + (yy + 0.5 - c[1]) ** 2 <= r * r


def skin_mask(side, shape, to_px, px_per_mm) -> np.ndarray:
    """Pixels of the face's skin in a render-sized grid from the photo's detector points: inside the face oval, below the
    forehead's top, outside eyes, brows, mouth and nostrils."""
    from PIL import Image, ImageDraw
    from . import likeness as lk
    H, W = shape
    P = to_px(side.P)
    im = Image.new("L", (W, H), 0)
    ImageDraw.Draw(im).polygon([tuple(p) for p in P[lk.OVAL]], fill=1)
    m = np.asarray(im, bool).copy()
    d = ImageDraw.Draw(im)
    for line in ([70, 63, 105, 66, 107, 55, 65, 52, 53, 46], [300, 293, 334, 296, 336, 285, 295, 282, 283, 276]):
        d.polygon([tuple(p) for p in P[line]], fill=0)
    m &= np.asarray(im, bool)
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    for a, b, up, lo in ((33, 133, 159, 145), (263, 362, 386, 374)):  # the eye opening, a little grown (lashes, lid rim)
        c = 0.5 * (P[a] + P[b])
        u = (P[a] - P[b]) / max(np.linalg.norm(P[a] - P[b]), 1e-9)
        hw = 0.62 * np.linalg.norm(P[a] - P[b])
        hh = 0.5 * np.linalg.norm(P[up] - P[lo]) + 2.0 * px_per_mm
        dx, dy = xx - c[0], yy - c[1]
        s, t = dx * u[0] + dy * u[1], -dx * u[1] + dy * u[0]
        m &= (s / hw) ** 2 + (t / hh) ** 2 > 1
    mw = np.linalg.norm(P[61] - P[291])
    c = 0.5 * (P[13] + P[14])   # the lips: an ellipse over their red (not a disk the mouth's width: the folds beside it)
    u = (P[291] - P[61]) / max(mw, 1e-9)
    dx, dy = xx - c[0], yy - c[1]
    s, t = dx * u[0] + dy * u[1], -dx * u[1] + dy * u[0]
    lh = max(np.linalg.norm(P[0] - P[17]), 1.0)
    m &= (s / (0.6 * mw)) ** 2 + (t / (0.75 * lh)) ** 2 > 1
    for i in (98, 327, 2):
        m &= ~_disk(H, W, P[i], 4 * px_per_mm)
    yy = np.mgrid[0:H, 0:W][0]
    brow_top = min(P[105, 1], P[334, 1]) - 25 * px_per_mm
    return m & (yy > brow_top)


def fit_light(Y, N, mask, iters: int = 4):
    """Luminance ~ c0 + w . n on the masked pixels, robust (outliers past 2.5 sigma dropped): (c0, w, rms)."""
    k = mask & (np.linalg.norm(N, axis=-1) > 0.5) & np.isfinite(Y)
    y, n = Y[k], N[k]
    A = np.c_[np.ones(len(y)), n]
    use = np.ones(len(y), bool)
    sol = np.zeros(4)
    for _ in range(iters):
        if use.sum() < 50:
            break
        sol = np.linalg.lstsq(A[use], y[use], rcond=None)[0]
        r = y - A @ sol
        s = r[use].std()
        use = np.abs(r) < 2.5 * s
    rms = float(np.sqrt(((y - A @ sol)[use] ** 2).mean())) if use.any() else float("nan")
    return float(sol[0]), sol[1:], rms


def residual(Y, N, c0, w, mask, sigma_px):
    """(photo - model lit like it) / the face's median luminance, smoothed over the mask (normalised convolution),
    NaN off it. A difference, not a ratio: where the fitted light predicts ~0 a ratio blows up."""
    from scipy.ndimage import gaussian_filter
    pred = c0 + N @ w
    med = float(np.median(Y[mask])) if mask.any() else 1.0
    R = np.where(mask, (Y - pred) / max(med, 1e-6), 0.0)
    num = gaussian_filter(R, sigma_px)
    den = gaussian_filter(mask.astype(float), sigma_px)
    return np.where(mask & (den > 0.2), num / np.maximum(den, 1e-6), np.nan)


def region_centre(side, spec, sgn, ex, ey, px_per_mm, to_px, pair_index):
    """A region's centre (render pixels): a detector point (or a point t of the way between two), moved dx_mm outward
    (away from the midline: sgn = -1 on the subject's right) and dy_mm down the face."""
    def pt(i):
        return to_px(side.P[pair_index(i)][None])[0]
    c = pt(spec["at"]) if "at" in spec else pt(spec["from"]) + spec.get("t", 0.5) * (pt(spec["to"]) - pt(spec["from"]))
    return c + (sgn * spec.get("dx_mm", 0.0) * ex + spec.get("dy_mm", 0.0) * ey) * px_per_mm


# ---- the jaw's L: a traced line on the reference, the model's contour found along it -------------------------------

def _split_corner(Q):
    """Index splitting a polyline into two straight-ish parts (least total line-fit residual): the corner."""
    best, bi = np.inf, None
    for i in range(2, len(Q) - 2):
        e = 0.0
        for part in (Q[:i + 1], Q[i:]):
            c = part.mean(0)
            s = np.linalg.svd(part - c, compute_uv=False)
            e += s[-1] ** 2
        if e < best:
            best, bi = e, i
    return bi


def _dirfit(part):
    c = part.mean(0)
    v = np.linalg.svd(part - c)[2][0]
    if v @ (part[-1] - part[0]) < 0:
        v = -v
    return v


def jaw_measures(Q, ex, ey, mmpx, lobe=None, mouth=None, neck=None) -> dict:
    """The jaw's L from a polyline running down the ramus, round the angle and forward along the lower border (picture
    pixels), on the face's axes (ex across, ey down): ramus_angle (deg from the face's vertical), gonial_angle (deg at
    the corner), border_straightness (largest deviation of the border from its chord, % of its length), gonion_below_lobe
    / gonion_below_mouth (mm, down the face), neck_step (mm from the border's middle to the neck's line)."""
    Q = np.asarray(Q, float)
    if len(Q) < 6:
        return {}
    i = _split_corner(Q)
    ra, bo = Q[:i + 1], Q[i:]
    vr, vb = _dirfit(ra), _dirfit(bo)
    out = {"ramus_angle": float(np.degrees(np.arctan2(abs(vr @ ex), abs(vr @ ey)))),
           "gonial_angle": float(np.degrees(np.arccos(np.clip(-vr @ vb, -1, 1))))}
    ch = bo[-1] - bo[0]
    lc = np.linalg.norm(ch)
    if lc > 1e-6:
        nrm = np.array([-ch[1], ch[0]]) / lc
        out["border_straightness"] = float(np.abs((bo - bo[0]) @ nrm).max() / lc * 100)
    g = Q[i]
    if lobe is not None:
        out["gonion_below_lobe"] = float((g - np.asarray(lobe)) @ ey * mmpx)
    if mouth is not None:
        out["gonion_below_mouth"] = float((g - np.asarray(mouth)) @ ey * mmpx)
    if neck is not None and len(neck) >= 2:
        N = np.asarray(neck, float)
        m = bo[(2 * len(bo)) // 3]   # two thirds of the way from the angle to the chin: where the neck steps in
        d = np.min(np.linalg.norm(_densify(N) - m, axis=1))
        out["neck_step"] = float(d * mmpx)
    out["_gonion"] = g.tolist()
    return out


def _densify(N, n=200):
    seg = np.linalg.norm(np.diff(N, axis=0), axis=1)
    s = np.r_[0, np.cumsum(seg)]
    t = np.linspace(0, s[-1], n)
    return np.c_[np.interp(t, s, N[:, 0]), np.interp(t, s, N[:, 1])]


def depth_edges(zb, jump: float = 0.012) -> np.ndarray:
    """Render pixels on the model's occluding contour: its silhouette against nothing, or a front surface over one
    more than `jump` m behind it (the jaw over the neck)."""
    f = np.isfinite(zb)
    z = np.where(f, zb, 1e9)
    e = np.zeros_like(f)
    for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        nb = np.roll(np.roll(z, dy, 0), dx, 1)
        e |= f & (nb - z > jump)
    return e


def model_jaw(Q_photo, zb, k, box, along_mm, mmpx, nrm=None):
    """The model's jaw line matched to a photo trace: across each traced point (within `along_mm`), the model's
    occluding contour (a depth jump: the jaw over the neck) if there is one, else where its surface turns fastest (the
    largest change of normal between neighbouring samples: the border's edge, however soft). Picture pixels, or None.
    A search line where the model turns less than 6 deg over two samples (~1 mm) gives no point: the model has no
    edge there."""
    if Q_photo is None or len(Q_photo) < 2:
        return None
    E = depth_edges(zb)
    H, W = zb.shape
    Qd = _densify(np.asarray(Q_photo, float), 40)
    lim = along_mm / mmpx
    out = []
    s_prev = 0.0
    for i, q in enumerate(Qd):
        t = Qd[min(i + 1, len(Qd) - 1)] - Qd[max(i - 1, 0)]
        t /= max(np.linalg.norm(t), 1e-9)
        nv = np.array([-t[1], t[0]])
        s = np.linspace(-lim, lim, 81)
        P = (q + s[:, None] * nv - [box[0], box[1]]) * k
        ij = np.round(P - 0.5).astype(int)
        ok = (ij[:, 0] >= 0) & (ij[:, 0] < W) & (ij[:, 1] >= 0) & (ij[:, 1] < H)
        if ok.sum() < 10:
            out.append([np.nan, np.nan])
            continue
        e = np.zeros(len(s), bool)
        e[ok] = E[ij[ok, 1], ij[ok, 0]]
        if e.any():
            j = np.where(e)[0][np.argmin(np.abs(s[e]))]
            out.append(q + s[j] * nv)
            continue
        if nrm is None:
            out.append([np.nan, np.nan])
            continue
        n = np.zeros((len(s), 3))
        n[ok] = nrm[ij[ok, 1], ij[ok, 0]]
        good = ok & (np.linalg.norm(n, axis=1) > 0.5)
        turn = np.zeros(len(s))
        a, b = n[:-2], n[2:]
        cosang = np.clip((a * b).sum(1), -1, 1)
        turn[1:-1] = np.where(good[:-2] & good[2:], np.degrees(np.arccos(cosang)), 0.0)
        turn = np.convolve(turn, np.ones(5) / 5, mode="same")
        # the strongest turn, kept near the previous line's (a contour runs on; noise jumps)
        score = turn - 10.0 * np.abs(s - s_prev) / max(lim, 1e-9) * (i > 0)
        j = int(np.argmax(score))
        if turn[j] > 4.0:   # (deg between samples ~0.5 mm apart, smoothed)
            out.append(q + s[j] * nv)
            s_prev = s[j]
        else:
            out.append([np.nan, np.nan])
    out = np.array(out, float)
    # a running median of each point's offset across the trace: one stray line can't make a corner
    off = np.array([(o - q) @ np.array([-(Qd[min(i + 1, len(Qd) - 1)] - Qd[max(i - 1, 0)])[1],
                                          (Qd[min(i + 1, len(Qd) - 1)] - Qd[max(i - 1, 0)])[0]])
                    / max(np.linalg.norm(Qd[min(i + 1, len(Qd) - 1)] - Qd[max(i - 1, 0)]), 1e-9)
                    for i, (o, q) in enumerate(zip(out, Qd))])
    sm = np.full(len(off), np.nan)
    for i in range(len(off)):
        w = off[max(0, i - 3):i + 4]
        w = w[np.isfinite(w)]
        if len(w) >= 3 and np.isfinite(off[i]):
            sm[i] = np.median(w)
    for i, q in enumerate(Qd):
        if np.isfinite(sm[i]):
            t = Qd[min(i + 1, len(Qd) - 1)] - Qd[max(i - 1, 0)]
            t /= max(np.linalg.norm(t), 1e-9)
            out[i] = q + sm[i] * np.array([-t[1], t[0]])
        else:
            out[i] = np.nan
    good = np.isfinite(out).all(1)
    return out[good] if good.sum() >= 8 else None


# ---- the camera: refit on the detector's points (photo) against the model's surface under them (render) -----------

def unproject(cam, uv, z):
    """Picture pixels + camera depth -> world points (the inverse of humanfit.project)."""
    from . import humanfit
    w, h = cam["size"]
    Xc = np.c_[(uv[:, 0] - w / 2) * z / cam["f"], (uv[:, 1] - h / 2) * z / cam["f"], z]
    return (Xc - np.asarray(cam["t"])) @ humanfit._cam_rot(cam) + np.asarray(cam["centre"])


def refit_camera(cam, uv_photo, X, prior: float = 0.02):
    """(camera, per-point residual px): pose and focal by least squares (soft_l1) of the model's points X onto the
    photo's points, held near the given camera."""
    from scipy.optimize import least_squares
    from . import humanfit
    sz = max(cam["size"])
    x0 = np.r_[cam["r"], cam["t"], cam["f"]]

    def un(x):
        return {**cam, "r": x[:3].tolist(), "t": x[3:6].tolist(), "f": float(x[6])}

    def res(x):
        r = (humanfit.project(un(x), X) - uv_photo).ravel() / sz * 400
        return np.r_[r, prior * 400 * (x[:3] - x0[:3]), prior * 40 * (x[6] / x0[6] - 1)]
    s = least_squares(res, x0, loss="soft_l1", f_scale=2.0,
                      x_scale=np.r_[0.05, 0.05, 0.05, 0.02, 0.02, 0.1 * max(abs(x0[5]), 1e-3), 0.05 * x0[6]])
    c = un(s.x)
    return c, np.linalg.norm(humanfit.project(c, X) - uv_photo, axis=1)
