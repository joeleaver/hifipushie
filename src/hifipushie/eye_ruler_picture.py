"""The picture's side: `read`, the limbus circle, one patch's read, the crease and the brow. Part of the eye ruler (eye_ruler.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import eye_ruler
from .eye_ruler import _bilinear, _contour, _iu, _iv, _ridge, _smooth, frames, patch

# ---- the picture -----------------------------------------------------------------------------------------------------
def read(img, P, mmpx: float, scale: float = 1.0, origin=(0.0, 0.0), debug: bool = False) -> list:
    """The measures on a picture, per eye (subject's right, left). P: the detector's 478 points in PICTURE pixels; the
    image may be a crop / enlargement of the picture (image px = (picture px - origin) * scale); mmpx: mm per PICTURE
    pixel at the eyes. Each eye: the module docstring's measures + "c" (the iris centre, picture px), "frame"."""
    from . import blockin_eyes_evidence
    Pi = (np.asarray(P, float)[:, :2] - np.asarray(origin, float)) * scale
    k = scale / mmpx                                  # image px per mm
    A = np.asarray(img.convert("RGB"), float) / 255.0
    lb = blockin_eyes_evidence.limbus(img, Pi)
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
        m = _read_patch(pat, lb[s]["r_px"] / k, _contour(Pi, eye_ruler.UPPER[s], fr, k), _contour(Pi, eye_ruler.LOWER[s], fr, k),
                        _contour(Pi, eye_ruler.BROW_LOW[s], fr, k), debug=debug)
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
    u0, u1 = max(cu[0, 0], cl[0, 0]) - eye_ruler.PAST, min(cu[-1, 0], cl[-1, 0]) + eye_ruler.PAST
    u0, u1 = max(u0, eye_ruler.U[0] + 0.5), min(u1, eye_ruler.U[-1] - 0.5)
    cols = np.arange(_iu(u0), _iu(u1) + 1, 2)
    uu = eye_ruler.U[cols]
    vu = np.interp(uu, cu[:, 0], cu[:, 1])
    vl = np.interp(uu, cl[:, 0], cl[:, 1])
    mid = 0.5 * (vu + vl)
    skin = float(np.median(f))
    S = f - skin
    sc = float(np.percentile(S[_iv(-5):_iv(8), _iu(-14):_iu(14)], 99)) or 1.0
    S = S / max(sc, 1e-6)
    rho = np.hypot(eye_ruler.U[None, :], eye_ruler.V[:, None]) / max(r_iris, 1e-6)
    # SKIN-likeness K: the skin's chroma and at least ~0.7 of the local luminance. The eyeball, the lash line, liner,
    # waterline and caruncle are all not skin: K's edges are the OUTER sides of the two lid rims.
    mad = float(np.median(np.abs(f - skin))) or 0.01
    lbig = _smooth(lum, 6.0)
    ls = _smooth(lum, 0.15)
    K = np.exp(-0.5 * ((f - skin) / (4.0 * mad)) ** 2) / (1.0 + np.exp(-(ls / np.maximum(lbig, 0.02) - eye_ruler.SKIN_LUM) / 0.05))
    K = _smooth(K, 0.15)
    d = max(1, int(round(0.15 / eye_ruler.STEP)))

    def dv(A):
        G = np.zeros_like(A)
        G[d:-d] = A[2 * d:] - A[:-2 * d]
        return G
    GK = dv(K)
    GK = GK / (float(np.percentile(np.abs(GK[_iv(-6):_iv(6), _iu(-12):_iu(12)]), 99)) or 1.0)
    rt = _ridge(GK, cols, np.array([_iv(b + 0.5) for b in mid]), np.array([_iv(a) for a in vu + eye_ruler.BAND + 1.0]), lam=1.5)
    rb = _ridge(-GK, cols, np.array([_iv(a) for a in vl - eye_ruler.BAND - 1.0]), np.array([_iv(b - 0.5) for b in mid]), lam=1.5)
    # the INNER sides (the margins proper: where the eyeball ends) are edges of f, read outside the iris' disc (inside
    # it the iris' own picture, the limbus ring and the catch lights are edges too) and within RIM mm of the outer side
    GS = dv(S)
    GS[rho < eye_ruler.IRIS_OUT] = 0.0
    GS = GS / (float(np.percentile(np.abs(GS[_iv(-6):_iv(6), _iu(-12):_iu(12)]), 99)) or 1.0)
    n_rim = int(round(eye_ruler.RIM / eye_ruler.STEP))
    ru = _ridge(GS, cols, np.maximum(rt - n_rim, np.array([_iv(b + 0.2) for b in mid])), rt, lam=1.5)
    rl = _ridge(-GS, cols, rb, np.minimum(rb + n_rim, np.array([_iv(b - 0.2) for b in mid])), lam=1.5)
    up, lo = eye_ruler.V[ru].astype(float), eye_ruler.V[rl].astype(float)
    T, B = eye_ruler.V[rt].astype(float), eye_ruler.V[rb].astype(float)
    # inside the disc: the rim's thickness (outer side - inner side) carried across from the columns either side
    half = eye_ruler.IRIS_OUT * r_iris * 1.02

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
    gap = int(round(0.5 / (2 * eye_ruler.STEP)))                 # a 0.5 mm break (a lash, a vein) does not end it
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
    inner = np.array([uu[ji], eye_ruler.V[rb[ji] + int(np.argmin(wedge))] if len(wedge) else 0.5 * (T[ji] + B[ji])])
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
           "up": [at(upc, x) for x in eye_ruler.COLS], "lo": [at(loc, x) for x in eye_ruler.COLS], "iris": 2 * float(r_iris)}
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
        out["_dbg"] = {"uu": uu, "ru": eye_ruler.V[ru_c], "rl": eye_ruler.V[rl_c], "up": up, "lo": lo, "con": con, "a": a, "b": b, "ji": ji, "T": T, "B": B, "K": K,
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
    n = max(1, int(round(mm / (2 * eye_ruler.STEP))))
    g = np.exp(-0.5 * (np.arange(-3 * n, 3 * n + 1) / n) ** 2)
    yy = np.where(np.isfinite(y), y, np.nanmedian(y) if np.isfinite(y).any() else 0.0)
    return np.convolve(np.pad(yy, 3 * n, mode="edge"), g / g.sum(), mode="valid")


def _crease(lum, uu, upc, a, b, cb) -> dict:
    """The fold line over the upper lid: a ridge of narrow darkness (the luminance against its 1.2 mm surround),
    tracked across the lid between CREASE_LO and CREASE_HI over the margin (and short of the detector's brow)."""
    D = (_smooth(lum, 1.2) - _smooth(lum, 0.2)) / np.maximum(_smooth(lum, 1.2), 0.05)
    sel = np.arange(a, b + 1)
    sel = sel[np.isfinite(upc[sel])]
    if len(sel) < 10:
        return {"crease": [float("nan")] * len(eye_ruler.COLS), "crease_dark": 0.0}
    cols = np.array([_iu(x) for x in uu[sel]])
    brow = np.interp(uu[sel], cb[:, 0], cb[:, 1])
    lo = np.array([_iv(v + eye_ruler.CREASE_LO) for v in upc[sel]])
    hi = np.array([_iv(min(v + eye_ruler.CREASE_HI, bw - 2.0)) for v, bw in zip(upc[sel], brow)])
    hi = np.maximum(hi, lo + 2)
    hi = np.minimum(hi, D.shape[0] - 1)
    r = _ridge(D / 0.05, cols, lo, hi, lam=2.0, jump=2)
    h = eye_ruler.V[r] - upc[sel]
    dk = D[r, cols]
    out = {"crease": [float(np.interp(x, uu[sel], h)) if uu[sel][0] <= x <= uu[sel][-1] else float("nan") for x in eye_ruler.COLS],
           "crease_dark": float(np.median(dk[np.abs(uu[sel]) < 7])), "_cr": (uu[sel], eye_ruler.V[r])}
    return out


def _brow(lum, uu, upc, a, b, cb) -> dict:
    """The brow hair's lower edge over the upper margin at COLS: the darkest broad band within 4.5 mm of the
    detector's brow line, its edge toward the eye at half contrast against the skin under it."""
    Ls = _smooth(lum, 0.5)
    out, pts = [], []
    for x in eye_ruler.COLS:
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
        out.append(float(eye_ruler.V[0] + e * eye_ruler.STEP - m))
        pts.append((x, eye_ruler.V[0] + e * eye_ruler.STEP))
    return {"brow": out, "_br": pts}
