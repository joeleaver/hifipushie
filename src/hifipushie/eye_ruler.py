"""The EYE RULER (eyeruler, 2026-10-11; Joe on a matched photo / render sheet: "I notice some measurement errors": our
eye was narrower corner to corner than hers and nobody had measured it). One set of eye measures, in mm AT THE MODEL,
read two ways:

  read(img, P, mmpx, ...)   on a PICTURE (the photo, or a dressed render through the same fitted camera): edges, not
                            detector points. MediaPipe's eye points only say where to look (a +-2.5 mm band).
  model(base, cam, ...)     on the MODEL's mesh through the fitted camera (exact: the truth the image reader was
                            validated against on dressed renders of known GNM heads; ERR below).

Everything is in the EYE FRAME of each eye: origin = the iris (limbus) centre, u = mm toward the outer corner along
the line through the two iris centres, v = mm up. Measures (per eye; `mean()` averages the two):
  inner / outer        the canthi (u, v); fissure = their distance; tilt = the outer canthus over the inner (degrees)
  sclera_in / _out     where the visible eyeball ends; caruncle = sclera_in - inner (the pink corner that shows)
  up[k] / lo[k]        the lid margins (v) at COLS (u = -9 .. 9 mm); open = up - lo; peak_u = where the upper lid peaks
  mrd1 / mrd2          the margins over / under the iris centre; cover_up / cover_lo = iris radius - mrd (mm hidden)
  iris                 the limbus diameter
  crease[k]            the fold line over the upper margin at COLS (= the visible lid platform's height); crease_dark
  brow[k]              the brow hair's lower edge over the upper margin at COLS
How the picture is read: the lash line, liner, waterline and caruncle are all DARK AND WARM against both the skin and
the eyeball, so the opening is ringed by a ridge of f = (R - B) / (R + G + B). The upper and lower ridges are tracked
by dynamic programming inside the detector's band; a margin is the ridge's flank toward the eyeball (half level); the
eyeball ends where the valley between the ridges closes; the inner canthus is the medial tip of the warm ridge past it.
"""
from __future__ import annotations

import numpy as np

STEP = 0.05                                # mm per patch pixel
U = np.arange(-19.0, 19.0001, STEP)        # across: + = toward the outer corner
V = np.arange(-11.0, 24.0001, STEP)        # up
COLS = np.array([-9.0, -6.0, -3.0, 0.0, 3.0, 6.0, 9.0])
BAND = 2.5                                 # mm either side of the detector's lid contours searched for a ridge
PAST = 4.5                                 # mm past the detector's corners searched
IRIS_SECTOR = 28.0                         # degrees either side of the eye line: the iris' own radial picture is read there
IRIS_OUT = 1.1                             # x the limbus radius: inside it the eyeball's edge is not read from f
RIM = 2.2                                  # mm: the most a lid rim (lash line, liner, waterline) is thick
SKIN_LUM = 0.7                             # x the local luminance: darker than this is not skin
# MediaPipe eye contours, outer corner -> inner corner (subject's right eye, left eye)
UPPER = ((33, 246, 161, 160, 159, 158, 157, 173, 133), (263, 466, 388, 387, 386, 385, 384, 398, 362))
LOWER = ((33, 7, 163, 144, 145, 153, 154, 155, 133), (263, 249, 390, 373, 374, 380, 381, 382, 362))
BROW_LOW = ((46, 53, 52, 65, 55), (276, 283, 282, 295, 285))
# The image reader's error on dressed fitted-camera renders of known heads, against model() (mm; rms over heads, both
# eyes; spikes/eyeruler/validate.py -> docs/notes/gnm_atlas.md "## eyeruler"). A difference under ~2 x this is not one.
ERR: dict = {}
FLAGGED: tuple = ()


# ---- patches ---------------------------------------------------------------------------------------------------------

def _bilinear(A, x, y):
    h, w = A.shape[:2]
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    return (A[y0, x0] * (1 - fx) * (1 - fy) + A[y0, x0 + 1] * fx * (1 - fy) + A[y0 + 1, x0] * (1 - fx) * fy
            + A[y0 + 1, x0 + 1] * fx * fy)


def frames(c_r, c_l) -> list:
    """The two eye frames from the iris centres (image px; subject's right eye first = the picture's left):
    [{"c", "ex" (toward the OUTER corner), "ey" (image down)}]."""
    c_r, c_l = np.asarray(c_r, float), np.asarray(c_l, float)
    e = (c_l - c_r) / np.linalg.norm(c_l - c_r)
    down = np.array([-e[1], e[0]])
    if down[1] < 0:
        down = -down
    return [{"c": c_r, "ex": -e, "ey": down}, {"c": c_l, "ex": e, "ey": down}]


def patch(A, fr: dict, k: float) -> np.ndarray:
    """The eye-frame patch (len(V), len(U), channels) of image array A; k = image px per mm. Row 0 = V[0] (lowest)."""
    X = fr["c"][None, None] + (U[None, :, None] * k) * fr["ex"] - (V[:, None, None] * k) * fr["ey"]
    return _bilinear(A, X[..., 0], X[..., 1])


def _iu(u):
    return int(round((u - U[0]) / STEP))


def _iv(v):
    return int(round((v - V[0]) / STEP))


def _smooth(a, mm):
    from scipy.ndimage import gaussian_filter
    return gaussian_filter(a, mm / STEP)


# ---- ridges ----------------------------------------------------------------------------------------------------------

def _ridge(S, cols, lo, hi, lam=4.0, jump=3):
    """The best path through score S (rows v, columns u) over column indices cols, rows within [lo[j], hi[j]]: max of
    sum S - lam * (row step / jump)^2. Returns the row per column."""
    n = len(cols)
    R = S.shape[0]
    rows = np.arange(R)
    NEG = -1e9
    cost = np.full((n, R), NEG)
    back = np.zeros((n, R), int)
    ok = (rows >= lo[0]) & (rows <= hi[0])
    cost[0, ok] = S[ok, cols[0]]
    offs = np.arange(-jump, jump + 1)
    pen = lam * (offs / jump) ** 2
    for j in range(1, n):
        prev = cost[j - 1]
        cand = np.full((len(offs), R), NEG)
        for i, o in enumerate(offs):
            if o >= 0:
                cand[i, o:] = prev[:R - o] - pen[i]
            else:
                cand[i, :R + o] = prev[-o:] - pen[i]
        b = np.argmax(cand, 0)
        best = cand[b, rows]
        ok = (rows >= lo[j]) & (rows <= hi[j])
        cost[j, ok] = best[ok] + S[ok, cols[j]]
        back[j] = rows - offs[b]
    out = np.zeros(n, int)
    out[-1] = int(np.argmax(cost[-1]))
    for j in range(n - 1, 0, -1):
        out[j - 1] = back[j, out[j]]
    return out


def _contour(P, idx, fr, k):
    """Detector contour points in the eye frame (u, v), sorted by u."""
    d = (np.asarray(P, float)[list(idx), :2] - fr["c"]) / k
    uv = np.c_[d @ fr["ex"], -(d @ fr["ey"])]
    return uv[np.argsort(uv[:, 0])]


# ---- the picture -----------------------------------------------------------------------------------------------------

def read(img, P, mmpx: float, scale: float = 1.0, origin=(0.0, 0.0), debug: bool = False) -> list:
    """The measures on a picture, per eye (subject's right, left). P: the detector's 478 points in PICTURE pixels; the
    image may be a crop / enlargement of the picture (image px = (picture px - origin) * scale); mmpx: mm per PICTURE
    pixel at the eyes. Each eye: the module docstring's measures + "c" (the iris centre, picture px), "frame"."""
    from . import blockin_eyes as be
    Pi = (np.asarray(P, float)[:, :2] - np.asarray(origin, float)) * scale
    k = scale / mmpx                                  # image px per mm
    A = np.asarray(img.convert("RGB"), float) / 255.0
    lb = be.limbus(img, Pi)
    fr2 = frames(lb[0]["centre"], lb[1]["centre"])
    lum = 0.2126 * A[..., 0] + 0.7152 * A[..., 1] + 0.0722 * A[..., 2]
    for s in (0, 1):   # the detector's iris centre sits low / high by up to a mm (it follows the visible part): a circle
        c, r, n = limbus_circle(lum, lb[s]["centre"], lb[s]["r_px"], fr2[s]["ex"], fr2[s]["ey"])   # through the limbus
        lb[s] = {**lb[s], "centre": c.tolist(), "r_px": r, "circle_n": n}
    fr2 = frames(lb[0]["centre"], lb[1]["centre"])
    out = []
    for s in (0, 1):
        fr = fr2[s]
        pat = patch(A, fr, k)
        m = _read_patch(pat, lb[s]["r_px"] / k, _contour(Pi, UPPER[s], fr, k), _contour(Pi, LOWER[s], fr, k),
                        _contour(Pi, BROW_LOW[s], fr, k), debug=debug)
        m["c"] = (np.asarray(lb[s]["centre"]) / scale + np.asarray(origin, float)).tolist()
        m["frame"] = {"c": fr["c"].tolist(), "ex": fr["ex"].tolist(), "ey": fr["ey"].tolist(), "k": k}
        m["iris_rgb"] = lb[s]["rgb"]
        out.append(m)
    return out


def limbus_circle(lum, c0, r0, ex, ey, reach: float = 55.0):
    """The limbus as a CIRCLE: its edge (the steepest dark -> light step along rays from c0, 0.6-1.5 r0) in the two
    side sectors (+-reach degrees about the eye line), a least-squares circle through the points, rays the lids cover
    dropped as outliers (3 rounds). Returns (centre px, radius px, rays used). Falls back to (c0, r0) on < 8 rays."""
    c0, ex, ey = np.asarray(c0, float), np.asarray(ex, float), np.asarray(ey, float)
    rr = np.arange(0.6 * r0, 1.5 * r0, 0.1)
    sm = max(1, int(round(0.05 * r0 / 0.1)))
    ker = np.ones(2 * sm + 1) / (2 * sm + 1)
    pts = []
    for sg in (-1, 1):
        for a in np.radians(np.arange(-reach, reach + 0.1, 2.5)):
            d = sg * np.cos(a) * ex + np.sin(a) * ey
            X = c0 + rr[:, None] * d
            prof = np.convolve(_bilinear(lum[..., None], X[:, 0], X[:, 1])[:, 0], ker, mode="same")
            g = np.gradient(prof)
            g[:sm + 1] = g[-sm - 1:] = 0
            i = int(np.argmax(g))
            if g[i] > 0.004:
                pts.append(c0 + rr[i] * d)
    pts = np.array(pts)
    if len(pts) < 8:
        return c0, float(r0), 0
    keep = np.ones(len(pts), bool)
    c, r = c0, float(r0)
    for _ in range(4):
        Q = pts[keep]
        A_ = np.c_[2 * Q, np.ones(len(Q))]
        sol = np.linalg.lstsq(A_, (Q ** 2).sum(1), rcond=None)[0]
        c = sol[:2]
        r = float(np.sqrt(max(sol[2] + c @ c, 1e-9)))
        res = np.abs(np.linalg.norm(pts - c, axis=1) - r)
        tol = max(0.04 * r, 2.5 * float(np.median(res[keep])))
        new = res < tol
        if new.sum() < 8 or (new == keep).all():
            break
        keep = new
    if not (0.8 * r0 < r < 1.3 * r0) or np.linalg.norm(c - c0) > 0.5 * r0:
        return c0, float(r0), 0
    return c, r, int(keep.sum())


def _half_in(col, i0, step, level, n):
    """From row i0 walk by step while col >= level; the sub-row crossing."""
    i = i0
    while 0 <= i + step < n and col[i + step] >= level:
        i += step
    j = i + step
    if not 0 <= j < n:
        return float(i)
    a, b = col[i], col[j]
    t = (a - level) / max(a - b, 1e-9)
    return i + step * float(np.clip(t, 0, 1))


def _read_patch(pat, r_iris, cu, cl, cb, debug=False) -> dict:
    rgb = pat[..., :3]
    lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    f = (rgb[..., 0] - rgb[..., 2]) / (rgb.sum(-1) + 0.02)
    f = _smooth(f, 0.12)
    nV, nU = f.shape
    # the detector's lid contours as band centres, held flat past its corners
    u0, u1 = max(cu[0, 0], cl[0, 0]) - PAST, min(cu[-1, 0], cl[-1, 0]) + PAST
    u0, u1 = max(u0, U[0] + 0.5), min(u1, U[-1] - 0.5)
    cols = np.arange(_iu(u0), _iu(u1) + 1, 2)
    uu = U[cols]
    vu = np.interp(uu, cu[:, 0], cu[:, 1])
    vl = np.interp(uu, cl[:, 0], cl[:, 1])
    mid = 0.5 * (vu + vl)
    skin = float(np.median(f))
    S = f - skin
    sc = float(np.percentile(S[_iv(-5):_iv(8), _iu(-14):_iu(14)], 99)) or 1.0
    S = S / max(sc, 1e-6)
    rho = np.hypot(U[None, :], V[:, None]) / max(r_iris, 1e-6)
    # SKIN-likeness K: the skin's chroma and at least ~0.7 of the local luminance. The eyeball, the lash line, liner,
    # waterline and caruncle are all not skin: K's edges are the OUTER sides of the two lid rims.
    mad = float(np.median(np.abs(f - skin))) or 0.01
    lbig = _smooth(lum, 6.0)
    ls = _smooth(lum, 0.15)
    K = np.exp(-0.5 * ((f - skin) / (4.0 * mad)) ** 2) / (1.0 + np.exp(-(ls / np.maximum(lbig, 0.02) - SKIN_LUM) / 0.05))
    K = _smooth(K, 0.15)
    d = max(1, int(round(0.15 / STEP)))

    def dv(A):
        G = np.zeros_like(A)
        G[d:-d] = A[2 * d:] - A[:-2 * d]
        return G
    GK = dv(K)
    GK = GK / (float(np.percentile(np.abs(GK[_iv(-6):_iv(6), _iu(-12):_iu(12)]), 99)) or 1.0)
    rt = _ridge(GK, cols, np.array([_iv(b + 0.5) for b in mid]), np.array([_iv(a) for a in vu + BAND + 1.0]), lam=1.5)
    rb = _ridge(-GK, cols, np.array([_iv(a) for a in vl - BAND - 1.0]), np.array([_iv(b - 0.5) for b in mid]), lam=1.5)
    # the INNER sides (the margins proper: where the eyeball ends) are edges of f, read outside the iris' disc (inside
    # it the iris' own picture, the limbus ring and the catch lights are edges too) and within RIM mm of the outer side
    GS = dv(S)
    GS[rho < IRIS_OUT] = 0.0
    GS = GS / (float(np.percentile(np.abs(GS[_iv(-6):_iv(6), _iu(-12):_iu(12)]), 99)) or 1.0)
    n_rim = int(round(RIM / STEP))
    ru = _ridge(GS, cols, np.maximum(rt - n_rim, np.array([_iv(b + 0.2) for b in mid])), rt, lam=1.5)
    rl = _ridge(-GS, cols, rb, np.minimum(rb + n_rim, np.array([_iv(b - 0.2) for b in mid])), lam=1.5)
    up, lo = V[ru].astype(float), V[rl].astype(float)
    T, B = V[rt].astype(float), V[rb].astype(float)
    # inside the disc: the rim's thickness (outer side - inner side) carried across from the columns either side
    half = IRIS_OUT * r_iris * 1.02

    def bridge(outer_side, inner_side):
        th = outer_side - inner_side
        ins = np.abs(uu) < half
        left = (uu < -half) & (uu > -half - 1.5)
        right = (uu > half) & (uu < half + 1.5)
        if not left.any() or not right.any():
            return inner_side
        tl_, tr_ = float(np.median(th[left])), float(np.median(th[right]))
        t = np.clip((uu + half) / (2 * half), 0, 1)
        return np.where(ins, outer_side - (tl_ + t * (tr_ - tl_)), inner_side)
    up, lo = bridge(T, up), bridge(B, lo)
    up, lo = _smooth1(up, 0.3), _smooth1(lo, 0.3)
    # the visible eyeball: the run of columns around the iris where the lids are apart and something between them is
    # NOT warm (sclera, iris: f under the rims' crest by a share of the centre's contrast)
    con = np.zeros(len(cols))
    ru_c, rl_c = rt.copy(), rb.copy()
    for j, cj in enumerate(cols):
        col = S[:, cj]
        i0, i1 = _iv(lo[j]), _iv(up[j])
        if i1 - i0 < 4:
            continue
        ru_c[j] = i1 + int(np.argmax(col[i1:max(rt[j], i1) + 1]))
        rl_c[j] = min(rb[j], i0) + int(np.argmax(col[min(rb[j], i0):i0 + 1]))
        con[j] = min(float(col[ru_c[j]]), float(col[rl_c[j]])) - float(np.percentile(col[i0:i1 + 1], 20))
    out_disc = (np.abs(uu) > half) & (np.abs(uu) < half + 2.5)
    ref = float(np.median(con[out_disc])) if out_disc.any() else float(np.max(con))
    opn = ((con > 0.3 * ref) & ((up - lo) > 0.4)) | (np.abs(uu) < half)
    j0 = int(np.argmin(np.abs(uu)))
    a = b = j0
    gap = int(round(0.5 / (2 * STEP)))                 # a 0.5 mm break (a lash, a vein) does not end it
    while True:
        nxt = [j for j in range(max(a - gap, 0), a) if opn[j]]
        if not nxt:
            break
        a = nxt[0]
    while True:
        nxt = [j for j in range(b + 1, min(b + gap + 1, len(cols))) if opn[j]]
        if not nxt:
            break
        b = nxt[-1]
    sclera_in, sclera_out = float(uu[a]), float(uu[b])
    # canthi: the outer one where the opening closes; the inner one = the medial end of the not-skin wedge past the
    # eyeball (the caruncle and the corner's wet pink)
    kmin = np.array([K[min(rb[j], rt[j]):max(rb[j], rt[j]) + 1, cj].min() for j, cj in enumerate(cols)])
    ji = a
    while ji > 0 and kmin[ji - 1] < 0.5 and uu[a] - uu[ji - 1] < 6.0:
        ji -= 1
    wedge = K[rb[ji]:rt[ji] + 1, cols[ji]]
    inner = np.array([uu[ji], V[rb[ji] + int(np.argmin(wedge))] if len(wedge) else 0.5 * (T[ji] + B[ji])])
    outer = np.array([uu[b], 0.5 * (up[b] + lo[b])])
    okc = np.zeros(len(cols), bool)
    okc[a:b + 1] = True
    upc, loc = np.where(okc, up, np.nan), np.where(okc, lo, np.nan)
    upc, loc = _fill(uu, upc), _fill(uu, loc)

    def at(arr, x):
        if x < uu[a] or x > uu[b]:
            return float("nan")
        return float(np.interp(x, uu[a:b + 1], arr[a:b + 1]))
    out = {"inner": inner.tolist(), "outer": outer.tolist(), "sclera_in": sclera_in, "sclera_out": sclera_out,
           "fissure": float(np.linalg.norm(outer - inner)), "tilt": float(np.degrees(np.arctan2(outer[1] - inner[1], outer[0] - inner[0]))),
           "caruncle": float(sclera_in - inner[0]),
           "up": [at(upc, x) for x in COLS], "lo": [at(loc, x) for x in COLS], "iris": 2 * float(r_iris)}
    out["open"] = [a_ - b_ for a_, b_ in zip(out["up"], out["lo"])]
    sm = _smooth1(upc[a:b + 1], 0.6)
    out["peak_u"] = float(uu[a:b + 1][int(np.nanargmax(sm))])
    out["peak_v"] = float(np.nanmax(sm))
    out["mrd1"], out["mrd2"] = out["up"][3], -out["lo"][3]
    out["cover_up"], out["cover_lo"] = float(r_iris) - out["mrd1"], float(r_iris) - out["mrd2"]
    # the fold line: a narrow dark line 1.5 mm over the margin and up, short of the brow
    out.update(_crease(lum, uu, upc, a, b, cb))
    out.update(_brow(lum, uu, upc, a, b, cb))
    if debug:
        out["_dbg"] = {"uu": uu, "ru": V[ru_c], "rl": V[rl_c], "up": up, "lo": lo, "con": con, "a": a, "b": b, "ji": ji, "T": T, "B": B, "K": K,
                       "S": S, "cr": out.get("_cr"), "br": out.get("_br")}
    out.pop("_cr", None)
    out.pop("_br", None)
    return out


def _fill(x, y):
    ok = np.isfinite(y)
    if ok.sum() < 2:
        return y
    return np.where(ok, y, np.interp(x, x[ok], y[ok], left=np.nan, right=np.nan))


def _smooth1(y, mm):
    n = max(1, int(round(mm / (2 * STEP))))
    g = np.exp(-0.5 * (np.arange(-3 * n, 3 * n + 1) / n) ** 2)
    yy = np.where(np.isfinite(y), y, np.nanmedian(y) if np.isfinite(y).any() else 0.0)
    return np.convolve(np.pad(yy, 3 * n, mode="edge"), g / g.sum(), mode="valid")


CREASE_LO, CREASE_HI = 1.5, 10.0     # mm over the upper margin searched for the fold line
CREASE_MIN_DARK = 0.035             # a line fainter than this against the skin either side is "not read"


def _crease(lum, uu, upc, a, b, cb) -> dict:
    """The fold line over the upper lid: a ridge of narrow darkness (the luminance against its 1.2 mm surround),
    tracked across the lid between CREASE_LO and CREASE_HI over the margin (and short of the detector's brow)."""
    D = (_smooth(lum, 1.2) - _smooth(lum, 0.2)) / np.maximum(_smooth(lum, 1.2), 0.05)
    sel = np.arange(a, b + 1)
    sel = sel[np.isfinite(upc[sel])]
    if len(sel) < 10:
        return {"crease": [float("nan")] * len(COLS), "crease_dark": 0.0}
    cols = np.array([_iu(x) for x in uu[sel]])
    brow = np.interp(uu[sel], cb[:, 0], cb[:, 1])
    lo = np.array([_iv(v + CREASE_LO) for v in upc[sel]])
    hi = np.array([_iv(min(v + CREASE_HI, bw - 2.0)) for v, bw in zip(upc[sel], brow)])
    hi = np.maximum(hi, lo + 2)
    hi = np.minimum(hi, D.shape[0] - 1)
    r = _ridge(D / 0.05, cols, lo, hi, lam=2.0, jump=2)
    h = V[r] - upc[sel]
    dk = D[r, cols]
    out = {"crease": [float(np.interp(x, uu[sel], h)) if uu[sel][0] <= x <= uu[sel][-1] else float("nan") for x in COLS],
           "crease_dark": float(np.median(dk[np.abs(uu[sel]) < 7])), "_cr": (uu[sel], V[r])}
    return out


def _brow(lum, uu, upc, a, b, cb) -> dict:
    """The brow hair's lower edge over the upper margin at COLS: the darkest broad band within 4.5 mm of the
    detector's brow line, its edge toward the eye at half contrast against the skin under it."""
    Ls = _smooth(lum, 0.5)
    out, pts = [], []
    for x in COLS:
        if not (uu[a] <= x <= uu[b]) or not (cb[0, 0] - 2 <= x <= cb[-1, 0] + 2):
            out.append(float("nan"))
            continue
        m = float(np.interp(x, uu[a:b + 1], upc[a:b + 1]))
        vb = float(np.interp(x, cb[:, 0], cb[:, 1]))
        j = _iu(x)
        col = Ls[:, max(j - 15, 0):j + 16].mean(1)
        i0, i1 = _iv(max(vb - 4.5, m + 3.0)), min(_iv(vb + 6.0), len(col) - 1)
        if i1 <= i0 + 5:
            out.append(float("nan"))
            continue
        ic = i0 + int(np.argmin(col[i0:i1]))
        under = col[_iv(m + 2.0):ic]
        if len(under) < 5:
            out.append(float("nan"))
            continue
        sk = float(np.percentile(under, 85))
        if (sk - col[ic]) / max(sk, 1e-6) < 0.08:
            out.append(float("nan"))
            continue
        e = _half_in(-col, ic, -1, -0.5 * (sk + col[ic]), len(col))
        out.append(float(V[0] + e * STEP - m))
        pts.append((x, V[0] + e * STEP))
    return {"brow": out, "_br": pts}


# ---- the model -------------------------------------------------------------------------------------------------------

def _ring(ht, c):
    """The lid margin ring's vertex rows around the eye centred at c (skin rows next to the socket lining)."""
    from . import base as basemod, blockin_eyes as be
    g = basemod._gnm_data()
    Vh = np.asarray(ht["verts"], float)
    F = be._tris(ht["faces"])
    sk = np.flatnonzero(np.asarray(g["skin"]))
    sock = np.zeros(len(Vh), bool)
    sock[:len(sk)] = np.asarray(g["groups"]["eye_sockets"])[sk] > 0.5
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    m = sock[e[:, 0]] != sock[e[:, 1]]
    ring = np.unique(np.where(sock[e[m, 0]], e[m, 1], e[m, 0]))
    ring = ring[np.linalg.norm(Vh[ring] - c, axis=1) < 2.0 * float(ht["eye_r"])]
    Fs = F[np.all(~sock[F], axis=1)]
    return ring, Fs[np.all(np.linalg.norm(Vh[Fs] - c, axis=2) < 0.04, axis=1)]


def model(spec: dict, cam: dict, brows: bool = True, px_mm: float = STEP) -> list:
    """The measures on the model (its spec) through a fitted camera, per eye (subject's right, left), same keys as
    read() + "c" (the iris centre in picture px), "gap" (mm of socket lining showing between the lid margin ring and
    the eyeball, per COLS, upper / lower), "ring" (the margin ring in the eye frame), "platform" (the lid skin under
    the fold that a front view shows), "crease_depth". brows=False skips the brow decal's read."""
    from . import humanfit, likeness
    base = spec["base"]
    st = humanfit.state(base)
    ht = st["head"]
    mesh = likeness.model_mesh_from_state(st)
    mm = likeness._mm_per_px(cam, st["L"][27:48])
    fwd = np.asarray(ht.get("forward", [0, -1, 0]), float)
    r = float(ht["eye_r"])
    eyes = sorted([np.asarray(c, float) for c in ht["eyes"]], key=lambda c: c[0])      # subject's right (-x) first
    poles = humanfit.project(cam, np.array([c + 0.985 * r * fwd for c in eyes]))
    fr2 = frames(poles[0], poles[1])
    pad = 26.0 / mm
    lo_, hi_ = poles.min(0) - pad, poles.max(0) + pad
    box = (lo_[0], lo_[1] - 6.0 / mm, hi_[0], hi_[1])
    kk = mm / px_mm                                  # raster px per picture px
    _, k, ps = likeness.render(mesh, cam, box, px=int(round((box[2] - box[0]) * kk)), brows=False, passes=True)
    part = ps["part"]
    r_iris = 0.51 * 0.985 * r * 1000
    drawn = ((spec.get("skin") or {}).get("eyes") or {}).get("iris_size")     # the dressing's own iris diameter (m)
    if drawn:
        r_iris = 500.0 * float(drawn)
    Vh = np.asarray(ht["verts"], float)
    out = []
    for s in (0, 1):
        fr = {"c": (fr2[s]["c"] - np.array(box[:2])) * k, "ex": fr2[s]["ex"], "ey": fr2[s]["ey"]}
        M = patch((part == 1).astype(float)[..., None], fr, k / mm)[..., 0] > 0.5
        ring, tri = _ring(ht, eyes[s])
        d = (humanfit.project(cam, Vh[ring]) - fr2[s]["c"]) * mm
        ruv = np.c_[d @ fr2[s]["ex"], -(d @ fr2[s]["ey"])]
        anyc = M.any(0)
        ucols = U[anyc]
        top = np.array([V[np.flatnonzero(M[:, j])[-1]] + STEP / 2 for j in np.flatnonzero(anyc)])
        bot = np.array([V[np.flatnonzero(M[:, j])[0]] - STEP / 2 for j in np.flatnonzero(anyc)])
        # the inner canthus: the ring's medial end (the caruncle's corner). The outer one: where the visible eyeball
        # ends (the ring's own lateral end is tucked ~1 mm behind the lids' meeting: nothing a picture shows)
        ii = int(np.argmin(ruv[:, 0]))
        inner, outer = ruv[ii], np.array([ucols[-1], 0.5 * (top[-1] + bot[-1])])

        def at(arr, x):
            return float(np.interp(x, ucols, arr, left=np.nan, right=np.nan))
        m = {"inner": inner.tolist(), "outer": outer.tolist(), "sclera_in": float(ucols[0]), "sclera_out": float(ucols[-1]),
             "fissure": float(np.linalg.norm(outer - inner)),
             "tilt": float(np.degrees(np.arctan2(outer[1] - inner[1], outer[0] - inner[0]))),
             "caruncle": float(ucols[0] - inner[0]), "up": [at(top, x) for x in COLS], "lo": [at(bot, x) for x in COLS],
             "iris": 2 * r_iris, "c": fr2[s]["c"].tolist(), "ring": ruv.tolist()}
        m["open"] = [a - b for a, b in zip(m["up"], m["lo"])]
        sm = _smooth1(top, 0.6)
        m["peak_u"], m["peak_v"] = float(ucols[int(np.argmax(sm))]), float(sm.max())
        m["mrd1"], m["mrd2"] = m["up"][3], -m["lo"][3]
        m["cover_up"], m["cover_lo"] = r_iris - m["mrd1"], r_iris - m["mrd2"]
        # the ring against the eyeball: lining that shows between the margin and the ball
        ang = np.arctan2(ruv[:, 1] - ruv[:, 1].mean(), ruv[:, 0] - ruv[:, 0].mean())
        o = np.argsort(ang)
        poly = ruv[o]
        gu, gl = [], []
        for x in COLS:
            ys = _poly_cross(poly, x)
            if len(ys) < 2 or not np.isfinite(at(top, x)):
                gu.append(float("nan"))
                gl.append(float("nan"))
                continue
            gu.append(max(ys) - at(top, x))
            gl.append(at(bot, x) - min(ys))
        m["gap"] = {"up": gu, "lo": gl}
        m.update(_model_crease(ht, tri, eyes[s], r, fwd, s))
        out.append(m)
    if brows:
        _model_brow(out, st, cam, spec, fr2, mm)
    else:
        for m in out:
            m["brow"] = [float("nan")] * len(COLS)
    return out


def _poly_cross(poly, x):
    ys = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if (a[0] - x) * (b[0] - x) < 0:
            t = (x - a[0]) / (b[0] - a[0])
            ys.append(a[1] + t * (b[1] - a[1]))
    return ys


def _model_crease(ht, tri, c, r, fwd, s) -> dict:
    """The fold's height over the margin (blockin_eyes' sagittal profile reader: the deepest narrow valley 2-12 mm up)
    and the platform visible from the front, at COLS (world x = the eye centre's + u toward the outer corner)."""
    from . import blockin_eyes as be
    Vh = np.asarray(ht["verts"], float)
    up = np.array([0, 0, 1.0]) - fwd * fwd[2]
    up /= np.linalg.norm(up)
    sg = -1.0 if s == 0 else 1.0
    cr, show, dep = [], [], []
    for x in COLS:
        best = None
        for L in be._chain(be._slice(Vh, tri, float(c[0] + sg * x * 0.001))):
            d = np.linalg.norm(L - c, axis=1)
            ok = (d > r + 0.0003) & ((L - c) @ up > -0.001) & ((L - c) @ fwd > 0) & ((L - c) @ up < 0.03)
            runs, cur = [], []
            for i, o in enumerate(ok):
                if o:
                    cur.append(i)
                elif cur:
                    runs.append(cur)
                    cur = []
            if cur:
                runs.append(cur)
            for rr in runs:
                if best is None or len(rr) > len(best[1]):
                    best = (L, rr)
        if best is None or len(best[1]) < 4:
            cr.append(float("nan"))
            show.append(float("nan"))
            dep.append(float("nan"))
            continue
        L, rr = best
        P = np.c_[(L[rr] - c) @ fwd, (L[rr] - c) @ up]
        if P[0, 1] > P[-1, 1]:
            P = P[::-1]
        q = be._profile(P)
        cr.append(float(q["height"]))
        show.append(float(q["show"]))
        dep.append(float(q["local"]))
    return {"crease": cr, "platform": show, "crease_depth": dep,
            "crease_dark": float(np.nanmedian(dep)) if np.isfinite(dep).any() else 0.0}


def _model_brow(out, st, cam, spec, fr2, mm) -> None:
    """The brow decal's lower edge (blockin_brows.model_band: calibrated on a dressed render) over the model's upper
    margin at COLS."""
    from . import blockin_brows as bb, skin_look
    hb = ((spec.get("skin") or {}).get("hair") or {}).get("brows")
    o = dict(hb) if isinstance(hb, dict) else {}
    ex, ey = -fr2[0]["ex"], fr2[0]["ey"]
    xs = [np.array([(fr["c"] + x / mm * fr["ex"]) @ ex for x in COLS]) for fr in fr2]
    mb = bb.model_band(skin_look._J(spec), np.asarray(st["tpl"]["P"], float), cam, o,
                       float(o.get("thickness", bb.default_thickness(spec))), xs, ex, ey)
    for s in (0, 1):
        v = (fr2[s]["c"] @ ey - np.asarray(mb[s]["low"], float)) * mm
        out[s]["brow"] = (v - np.asarray(out[s]["up"], float)).tolist()


# ---- comparing -------------------------------------------------------------------------------------------------------

SCALARS = ("fissure", "tilt", "caruncle", "iris", "mrd1", "mrd2", "cover_up", "cover_lo", "peak_u", "sclera_in", "sclera_out")
VECTORS = ("up", "lo", "open", "crease", "brow")


def mean(eyes: list) -> dict:
    """Both eyes' mean of every measure (NaN-aware); "inner" / "outer" as (u, v)."""
    import warnings
    out = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for k in SCALARS + ("crease_dark",):
            out[k] = float(np.nanmean([e.get(k, np.nan) for e in eyes]))
        for k in VECTORS + ("inner", "outer"):
            if all(k in e for e in eyes):
                out[k] = np.nanmean([np.asarray(e[k], float) for e in eyes], 0).tolist()
    return out
