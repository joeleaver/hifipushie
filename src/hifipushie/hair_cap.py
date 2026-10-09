"""The hair cap of a SHORT cut: the scalp chart baked from the groom's own strands.

What game hair artists do for crops and short back and sides: a cap mesh close over the head wears a texture BAKED
from the strand groom (colour, alpha, normal, depth / AO, flow, id), opaque wherever the hair is dense, and a sparse
layer of cards over it breaks the surface and the outline (hair_guide.md, "Short cuts as a cap + cards").

`chart` rasterises every strand onto the scalp chart (u = azimuth / 360, v = elevation e0..90, row 0 = the top) with a
z-buffer by height over the scalp, each strand a constant width in METRES (the chart's texels are not square: ~0.3 mm
round the head, ~0.1 mm up it, and they shrink toward the pole), and returns per texel: alpha, the top strand's id,
depth (how far it stands over its neighbourhood: the shade between hairs), a tangent-space normal from the strands'
heights, the strand's direction (the flow map for anisotropic shading), whether it is a grey hair, plus a coarse map
of how high the hair stands (`lift`: the cap sits at the hair's mid height, not on the skin).
"""
from __future__ import annotations

import numpy as np
from numba import njit

VERSION = 10
WIDTH = 0.00055  # m: a strand's drawn width on the chart (a real hair is 0.08 mm: one screen pixel at bust distance
# is ~0.6 mm, and the chart is read 1-2 mips down there; thinner lines average to a haze and sparkle when minified)
LIFT = 0.7  # the cap stands at this share of the hair's height over the scalp
LIFT_MAX = 0.024  # m
EASE, EASE_FRONT = 0.012, 0.006  # m inside the hairline over which the cap rises to its height (sides / forehead)
RELIEF = 0.7  # x the strands' real slopes in the normal map (clamped at SLOPE)
SLOPE = 1.0
BASE_DEPTH = 0.5  # the base's shade (depth): a scalp tint in the hair's own colour; at 0.22 a near-black band at the nape
BASE_DENSE = (0.05, 0.2)  # the opaque base (the hair's dark inside) where the strands' coverage passes this ramp: at
# (0.3, 0.35) a short sparse nape (8 mm) had none and showed as pale speckled skin (game: a scalp tint under hair)


def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


@njit(cache=True)
def _raster(u0, v0, h0, u1, v1, h1, ru, rv, sid, W, H, zbuf, sbuf, dub, dvb, mu, mv):
    """Segments (pixel coordinates, u wraps) stamped as ellipses (ru, rv px) into a z-buffer by height: the top
    strand's id and its direction in metres (du x mu[row], -dv x mv: east, up)."""
    for k in range(len(u0)):
        du = u1[k] - u0[k]
        if du > W / 2:
            du -= W
        elif du < -W / 2:
            du += W
        dv = v1[k] - v0[k]
        rr = min(ru[k], rv[k])
        n = int(max(abs(du), abs(dv)) / max(0.8 * rr, 0.7)) + 1
        iu, iv = int(ru[k]) + 1, int(rv[k]) + 1
        a2, b2 = 1.0 / (ru[k] * ru[k]), 1.0 / (rv[k] * rv[k])
        for s in range(n + 1):
            t = s / n
            cu, cv = u0[k] + du * t, v0[k] + dv * t
            hh = h0[k] + (h1[k] - h0[k]) * t
            y0, x0 = int(np.floor(cv)), int(np.floor(cu))
            for y in range(y0 - iv, y0 + iv + 1):
                if y < 0 or y >= H:
                    continue
                fy = (y + 0.5 - cv)
                for x in range(x0 - iu, x0 + iu + 1):
                    fx = (x + 0.5 - cu)
                    if fx * fx * a2 + fy * fy * b2 > 1.0:
                        continue
                    xx = x % W
                    if hh > zbuf[y, xx]:
                        zbuf[y, xx] = hh
                        sbuf[y, xx] = sid[k]
                        dub[y, xx] = du * mu[y]
                        dvb[y, xx] = -dv * mv


def strand_grey(D: dict, locks: list, look: dict, sc) -> np.ndarray:
    """Per strand: is it a grey hair (the strand look's own rule: each lock's grey share x look.grey_locks +
    look.grey_amount; strands of the scalp layer take the share of the locks around their root)."""
    gl = np.array([float((k.get("inputs") or {}).get("Grey", k.get("grey", 0.0)) or 0.0) for k in locks] or [0.0])
    n = len(D["counts"])
    first = np.r_[0, np.cumsum(D["counts"])[:-1]]
    names = [str(x) for x in D["names"]]
    head = np.array([nm.startswith("hair_guides") for nm in names])[D["obj"]] if len(names) else np.zeros(n, bool)
    li = np.clip(D["lock"].astype(int), 0, len(gl) - 1)
    share = np.where(head, gl[li], np.nan)
    roots = np.asarray(D["pts"][first], float)
    if head.any() and (~head).any():
        from scipy.spatial import cKDTree
        tr = cKDTree(roots[head])
        _d, ii = tr.query(roots[~head], k=min(8, int(head.sum())))
        share[~head] = share[head][ii].reshape(len(ii), -1).mean(1)
    share = np.nan_to_num(share, nan=float(gl.mean()))
    share = np.clip(float(look.get("grey_amount", 0.0)) + float(look.get("grey_locks", 1.0)) * share, 0, 1)
    # (the chart draws only the TOP strand of each texel, half a millimetre wide and fully lit: the same share of
    # grey hairs that a path tracer buries among shadowed true-width hairs reads twice as silver here)
    share = share * float(look.get("card_grey", 0.5))
    r = (np.asarray(D["rand"], float) * 7.13 + 0.37) % 1.0
    return r < share


def chart(sc, g: dict, line, S: dict, D: dict, locks: list, e0: float, size: int = 2048, look: dict | None = None,
          ss: int = 2, width: float | None = None) -> dict:
    """The short cut's scalp chart from its strands (see the module's note). (size, size) float32 maps: alpha, id,
    depth, grey, cover; normal (.., 3, tangent space, green up); flow (.., 3: direction east / up in -1..1, strength);
    "lift": {"az", "el", "h"} = the hair's height over the scalp on a coarse grid (m)."""
    from scipy import ndimage
    from .hair import _part, inside
    look = look or {}
    W = H = int(size)
    W2, H2 = W * ss, H * ss
    wd = float(width or WIDTH)
    pts = np.asarray(D["pts"], float)
    cnt = np.asarray(D["counts"], int)
    az, el, hh = sc.coords(pts)
    sid = np.repeat(np.arange(len(cnt)), cnt)
    u = (az % 360.0) / 360.0 * W2
    v = (1 - (el - e0) / (90.0 - e0)) * H2
    R = np.linalg.norm(pts - sc.C, axis=1)
    d_in = inside(sc, line, az, el)
    ok = (hh < 0.04) & (hh > -0.006) & (el < 89.3) & (el > e0) & (d_in > -0.004)
    last = np.zeros(len(pts), bool)
    last[np.cumsum(cnt) - 1] = True
    # the hairline is a thinning of HAIRS, not an edge: strands rooted near the line are drawn fewer (a share by how
    # far inside their root is) and finer, so skin shows between them over ~1.5 x soft (drawn in full, 80k scalp
    # hairs half a millimetre wide closed the cap right up to the line: a swim cap's edge)
    soft_ = max(float(S.get("soft", 0.008)), 1e-4)
    first_ = np.r_[0, np.cumsum(cnt)[:-1]]
    root_in = d_in[first_]
    keep = ((np.asarray(D["rand"], float) * 13.7 + 0.11) % 1.0) < (0.12 + 0.88 * _ss(root_in / (1.8 * soft_)))
    ok &= keep[sid]
    i0 = np.nonzero(ok & ~last & np.r_[ok[1:], False])[0]
    i1 = i0 + 1
    # metres per (supersampled) texel: along u it shrinks with the elevation's cosine, along v it is the same everywhere
    m_u = 2 * np.pi * R[i0] * np.maximum(np.cos(np.radians(el[i0])), 0.03) / W2
    m_v = float(np.radians(90.0 - e0) * np.median(R)) / H2
    thin = 0.5 + 0.5 * _ss(d_in[i0] / (1.5 * soft_))  # single fine hairs at the line
    ru = np.clip(0.5 * wd * thin / m_u, 0.6, 30.0)
    rv = np.clip(0.5 * wd * thin / m_v, 0.6, 30.0)
    zbuf = np.full((H2, W2), -1.0, np.float32)
    sbuf = np.full((H2, W2), -1, np.int32)
    dub = np.zeros((H2, W2), np.float32)
    dvb = np.zeros((H2, W2), np.float32)
    rows_el = 90.0 - (np.arange(H2) + 0.5) / H2 * (90.0 - e0)
    mu_row = (2 * np.pi * float(np.median(R)) * np.maximum(np.cos(np.radians(rows_el)), 0.03) / W2).astype(np.float64)
    _raster(u[i0], v[i0], hh[i0].astype(np.float64), u[i1], v[i1], hh[i1].astype(np.float64), ru, rv,
            sid[i0].astype(np.int64), W2, H2, zbuf, sbuf, dub, dvb, mu_row, m_v)
    cov2 = sbuf >= 0
    grey_s = strand_grey(D, locks, look, sc)
    rand = np.asarray(D["rand"], np.float32)
    sb = np.maximum(sbuf, 0)

    def down(a):  # box filter to the chart's size
        return a.reshape(H, ss, W, ss).mean((1, 3)).astype(np.float32)
    alpha = down(cov2.astype(np.float32))
    wsum = np.maximum(alpha, 1e-4)
    idm = down(np.where(cov2, rand[sb], 0.0)) / wsum
    grey = down(np.where(cov2, grey_s[sb].astype(np.float32), 0.0)) / wsum
    hgt = down(np.where(cov2, zbuf, 0.0)) / wsum
    fu, fv = down(np.where(cov2, dub, 0.0)), down(np.where(cov2, dvb, 0.0))
    del zbuf, sbuf, dub, dvb, sb
    covered = alpha > 0.04
    if covered.any():  # values carried into the bare texels (no fringe under filtering; a smooth height to shade)
        ix = ndimage.distance_transform_edt(~covered, return_distances=False, return_indices=True)
        hgt, fu, fv = hgt[ix[0], ix[1]], fu[ix[0], ix[1]], fv[ix[0], ix[1]]
        idm_f, grey_f = idm[ix[0], ix[1]], grey[ix[0], ix[1]]
    else:
        idm_f, grey_f = idm, grey
    # the chart's texel in metres (u at each row; v constant)
    el_r = 90.0 - (np.arange(H) + 0.5) / H * (90.0 - e0)
    mur = (2 * np.pi * float(np.median(R)) * np.maximum(np.cos(np.radians(el_r)), 0.05) / W)[:, None]
    mvr = float(np.radians(90.0 - e0) * np.median(R)) / H
    mu_mid = float(np.median(mur[(el_r > 10) & (el_r < 60)])) if ((el_r > 10) & (el_r < 60)).any() else float(np.median(mur))

    def blur(a, metres):
        return ndimage.gaussian_filter(a, (metres / mvr, metres / mu_mid), mode=("nearest", "wrap"))
    hs = blur(hgt, 0.00035)
    # depth: how far the top strand stands over the hair around it (the shade between hairs and clumps)
    rel = hs - blur(hgt, 0.0022)
    occ = hs - blur(hgt, 0.006)
    occ2 = blur(hgt, 0.004) - blur(hgt, 0.014)  # hollows between tufts, a centimetre across
    dep = np.clip(0.66 + rel / 0.002 + 0.5 * np.minimum(occ, 0.0) / 0.004 + 0.6 * np.clip(occ2, -0.004, 0.002) / 0.004, 0.08, 1.0)
    su = np.gradient(hs, axis=1) / mur
    sv = -np.gradient(hs, axis=0) / mvr  # (up the image = up the head)
    su, sv = np.clip(RELIEF * su, -SLOPE, SLOPE), np.clip(RELIEF * sv, -SLOPE, SLOPE)
    nrm = np.stack([-su, -sv, np.ones_like(su)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    fl = np.hypot(fu, fv)
    fu, fv = fu / np.maximum(fl, 1e-9), fv / np.maximum(fl, 1e-9)
    # (a direction has no sign: smoothed as its double angle)
    c2, s2 = blur(fu * fu - fv * fv, 0.0006), blur(2 * fu * fv, 0.0006)
    ang = 0.5 * np.arctan2(s2, c2)
    strength = np.clip(np.hypot(c2, s2), 0, 1)
    flow = np.stack([np.cos(ang), np.sin(ang), strength], -1).astype(np.float32)
    # the opaque base under the strands: wherever the groom is dense, from `soft` inside the hairline; skin shows only
    # where real strands are sparse (the hairline's band, a part)
    AA, EE = np.meshgrid((np.arange(W) + 0.5) / W * 360.0, el_r, indexing="xy")
    din = inside(sc, line, AA, EE)
    soft = max(float(S.get("soft", 0.008)), 0.001)
    dens = blur(alpha, 0.003)
    base = _ss((din - 1.0 * soft) / (1.5 * soft)) * _ss((dens - BASE_DENSE[0]) / BASE_DENSE[1])  # (the line itself is single strands)
    pw = float(g["parting"].get("width", 0.012))
    if str(g["parting"].get("side", "left")) != "none":
        base = base * (1 - 0.8 * np.clip(_part(sc, g, AA, EE, 0.25 * pw), 0, 1))
    under = alpha < base  # the base shows between the strands: the dark of the hair's inside
    dep = np.where(under, alpha * dep + (1 - alpha) * BASE_DEPTH, dep)
    idm = np.where(covered, idm, idm_f)
    idm = np.where(under, alpha * idm + (1 - alpha) * 0.5, idm)
    grey = np.where(covered, grey, grey_f) * np.where(under, alpha, 1.0)
    a_out = np.maximum(np.where(din > -0.004, alpha, 0.0), base)
    # how high the hair stands (m): the strands' points on a coarse grid, a high-middle percentile, smoothed
    step = 4.0
    na, ne = int(360 / step), int(np.ceil((90.0 - e0) / step))
    ia = np.clip(((az % 360.0) / step).astype(int), 0, na - 1)
    ie = np.clip(((el - e0) / step).astype(int), 0, ne - 1)
    key = ie * na + ia
    use = (hh > 0) & (hh < 0.04) & (d_in > 0)
    o = np.argsort(key[use], kind="stable")
    ks, hv = key[use][o], hh[use][o]
    Hg = np.zeros(na * ne, np.float32)
    if len(ks):
        b = np.r_[0, np.nonzero(np.diff(ks))[0] + 1, len(ks)]
        for j in range(len(b) - 1):
            seg = hv[b[j]:b[j + 1]]
            if len(seg) >= 12:
                Hg[ks[b[j]]] = np.percentile(seg, 85)
    Hg = ndimage.gaussian_filter(Hg.reshape(ne, na), (1.0, 1.0), mode=("nearest", "wrap"))
    return {"alpha": a_out.astype(np.float32), "id": np.clip(idm, 0, 1).astype(np.float32),
            "depth": dep.astype(np.float32), "grey": np.clip(grey, 0, 1).astype(np.float32),
            "cover": alpha.astype(np.float32), "normal": nrm.astype(np.float32), "flow": flow,
            "lift": {"az0": 0.0, "el0": float(e0), "step": step, "h": Hg.astype(np.float32)}}


def lift_at(lift: dict, az, el) -> np.ndarray:
    """The hair's height (m) at chart directions, bilinear on the coarse grid."""
    from scipy import ndimage
    Hg = np.asarray(lift["h"], float)
    step = float(lift["step"])
    x = (np.asarray(az, float) % 360.0) / step - 0.5
    y = (np.asarray(el, float) - float(lift["el0"])) / step - 0.5
    pad = np.concatenate([Hg[:, -1:], Hg, Hg[:, :1]], 1)
    return ndimage.map_coordinates(pad, [np.clip(y, 0, Hg.shape[0] - 1), x + 1.0], order=1, mode="nearest")


def cap_height(lift: dict, d_in, az, el) -> np.ndarray:
    """How far the cap stands over the scalp (m): LIFT x the hair's height there, easing to 0 at the hairline."""
    # (over the forehead the hair stands at the line itself: the ease is EASE_FRONT there, else a lifted front's cap
    # was a ramp leaning back from the hairline while the strands rose straight off it)
    fa = np.abs(((np.asarray(az, float) + 180) % 360) - 180)
    ease = EASE - (EASE - EASE_FRONT) * (1 - _ss((fa - 40.0) / 25.0))
    return np.minimum(LIFT * lift_at(lift, az, el), LIFT_MAX) * _ss(np.asarray(d_in, float) / ease)
