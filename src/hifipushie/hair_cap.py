"""The hair cap of a SHORT cut: the scalp chart baked from the groom's own strands.

What game hair artists do for crops and short back and sides: a cap mesh close over the head wears a texture BAKED
from the strand groom (colour, alpha, normal, depth / AO, flow, id), opaque wherever the hair is dense, and a sparse
layer of cards over it breaks the surface and the outline (guide topic hair_short).

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

VERSION = 12  # (sh1) the chart also carries lay (signed flow), base, length, R
WIDTH = 0.00055  # m: a strand's drawn width on the chart (a real hair is 0.08 mm: one screen pixel at bust distance
# is ~0.6 mm, and the chart is read 1-2 mips down there; thinner lines average to a haze and sparkle when minified)
LIFT = 0.7  # the cap stands at this share of the hair's height over the scalp
LIFT_MAX = 0.024  # m
EASE, EASE_FRONT = 0.012, 0.006  # m inside the hairline over which the cap rises to its height (sides / forehead)
RELIEF = 0.7  # x the strands' real slopes in the normal map (clamped at SLOPE)
SLOPE = 1.0
BASE_DEPTH = 0.75  # the base's shade (depth): a scalp tint in the hair's own colour; at 0.22 a near-black band at the nape
BASE_DENSE = (0.05, 0.2)  # the opaque base (the hair's dark inside) where the strands' coverage passes this ramp: at
# (0.3, 0.35) a short sparse nape (8 mm) had none and showed as pale speckled skin (game: a scalp tint under hair)
KEEP_SOFT, THIN_SOFT = 1.8, 1.5  # (c7 levers) strands rooted within KEEP_SOFT x soft of the line are drawn fewer, within THIN_SOFT x soft finer
BASE_IN, BASE_RAMP = 1.0, 1.5  # (c7 levers) the opaque base starts BASE_IN x soft inside the hairline and is full BASE_RAMP x soft
# further in (1.0 / 1.5 = full only 2.5 x soft = 37 mm in: Garrett's temple band (roots p50 29 mm in) stayed see-through)


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
    keep = ((np.asarray(D["rand"], float) * 13.7 + 0.11) % 1.0) < (0.12 + 0.88 * _ss(root_in / (KEEP_SOFT * soft_)))
    ok &= keep[sid]
    i0 = np.nonzero(ok & ~last & np.r_[ok[1:], False])[0]
    i1 = i0 + 1
    # metres per (supersampled) texel: along u it shrinks with the elevation's cosine, along v it is the same everywhere
    m_u = 2 * np.pi * R[i0] * np.maximum(np.cos(np.radians(el[i0])), 0.03) / W2
    m_v = float(np.radians(90.0 - e0) * np.median(R)) / H2
    thin = 0.5 + 0.5 * _ss(d_in[i0] / (THIN_SOFT * soft_))  # single fine hairs at the line
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
    # (sh1) the LAY: the strands' signed direction (root -> tip, east / up) smoothed over a few mm: where the hair is
    # combed to (the flow map below has no sign); the combed picture's strands are traced along it
    lu_, lv_ = blur(fu, 0.003), blur(fv, 0.003)
    ll_ = np.maximum(np.hypot(lu_, lv_), 1e-9)
    lay = np.stack([lu_ / ll_, lv_ / ll_], -1).astype(np.float32)
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
    base = _ss((din - BASE_IN * soft) / (BASE_RAMP * soft)) * _ss((dens - BASE_DENSE[0]) / BASE_DENSE[1])  # (the line itself is single strands)
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
    # (sh1) how long the strands are, by where they are rooted (same coarse grid): the combed picture's lay length
    seg_ = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    slen = np.add.reduceat(np.r_[seg_, 0.0] * ~last, first_)
    rk = key[first_]
    Lg = np.zeros(na * ne, np.float32)
    for k_ in np.unique(rk):
        sel_ = slen[rk == k_]
        if len(sel_) >= 6:
            Lg[k_] = np.median(sel_)
    Lg = Lg.reshape(ne, na)
    if (Lg > 0).any():  # (no roots in a cell: the nearest cell's length)
        ix_ = ndimage.distance_transform_edt(Lg <= 0, return_distances=False, return_indices=True)
        Lg = ndimage.gaussian_filter(Lg[ix_[0], ix_[1]], (1.0, 1.0), mode=("nearest", "wrap"))
    return {"alpha": a_out.astype(np.float32), "id": np.clip(idm, 0, 1).astype(np.float32),
            "depth": dep.astype(np.float32), "grey": np.clip(grey, 0, 1).astype(np.float32),
            "cover": alpha.astype(np.float32), "normal": nrm.astype(np.float32), "flow": flow,
            "lift": {"az0": 0.0, "el0": float(e0), "step": step, "h": Hg.astype(np.float32)},
            "length": {"az0": 0.0, "el0": float(e0), "step": step, "h": Lg.astype(np.float32)},
            "lay": lay, "base": base.astype(np.float32), "R": float(np.median(R)), "e0": float(e0)}


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


# ------------------------------------------------------------------------------- short hair as SHELLS (sh1, Garrett)
# How games build short men's cuts (crew, taper, buzz): a scalp cap wearing a picture of COMBED strands lying in the
# groom's own direction, 2-3 alpha-tested shell copies of it standing at the hair's measured heights (depth and a soft
# outline), fins on the silhouette and cards only at the hairline / sideburns / nape (spec hair.export.style "shells").
# The baked chart above draws the groom's strands seen from above at one depth: Garrett's short even groom read as a
# nubbly mat with no lay (c14: "terrycloth"). `combed` traces strands along the chart's LAY instead.
SHELL_HEIGHTS = (0.62, 0.85)  # the shells' heights: shares of the hair's height (lift) over the scalp
SHELL_BASE = 0.4  # the cap's own height, same share (the shells stand between it and the hair's top)
LAY_LEN = 0.75  # a traced strand's length: this share of the groom's strand length rooted there
LAY_MIN, LAY_MAX = 0.006, 0.035  # m
LAY_COVER = 5.0  # strands traced: this many times the hair's area / (width x length) (cover overlap)
LAY_STEP = 0.0008  # m per tracing step
LAY_WOBBLE = 0.12  # rad: a strand's own slow turn off the lay (combed hair is not parallel lines)
GREY_SPREAD = 1.0  # (sh2) the combed strands' regional grey share stretched about its median over the hair (Garrett's
# photo: sides / temples 61-68 % grey, back 12 %; the groom's regional shares are flatter). 1 = as charted
GREY_REGION = 0.0  # (sh3) 0..1: the combed strands' grey share blended toward GREY_MAP (a regional target read from
# Garrett's photo, segmented tone by view and band: top / crown dark, the side band over the ears and the temples silver,
# the nape and the back darker, the sideburns light). At 1 the groom's lock-scale grey (6-texel blur, ~2 mm: what
# GREY_SPREAD stretched: lock noise, not regions; the groom has no side-vs-back trend) is gone: grey hairs interleave
# finely and the share follows the regions.
GREY_MAP = {"top": 0.15, "fa": (0.0, 60.0, 100.0, 140.0, 180.0), "band": (0.55, 0.7, 0.65, 0.4, 0.3),
            "low": (0.5, 0.55, 0.4, 0.15, 0.1), "band_h": (0.15, 0.35, 0.6, 0.8)}  # band_h: low->band, band->top ramps
SHADE_MAP = None  # (sh3) a GREY_MAP-shaped dict of depth (shade) factors by region, e.g. {"top": .55, "band": (1,)*5,
# "low": (1,)*5, ...}: sh3a's top read 47-53 L* (photo 33-38) at a .15 grey share: the top is LIT, not grey; None = off
VALUE_MAP = None  # (sh4) a GREY_MAP-shaped dict of colour (value) factors by region, applied to the final colour of the
# cap and shells (strands, grey hairs and base alike): SHADE_MAP only scales depth, and shade = .45 + .55 dep^.8 floors
# it (sh3d's top stayed ~+10 L* over the photo at SHADE_MAP top .6). None = off
EDGE_SHADE = 0.3  # (sh3) a strand's edges shaded by this share (the dark gap between hairs)
BASE_EDGE = 0.0  # m: (sh2) the cap's opaque base fades out over this distance in from the hair's edge, so the hairline
# and the nape edge are strands over skin (alpha-tested), not the base's dark rim (Garrett's front hairline drew a hard dark
# line). 0 = the base runs to the edge (sh1)
SHELL_WIDTH = 0.0008  # m: the shells' strands are drawn wider (their slots are half the chart's resolution)
LAY_DEP0, LAY_DEP_T, LAY_DEP_S = 0.3, 0.4, 0.25  # a combed strand's depth (shade): base + along x t + standing x s
SHELL_LIT = 0.08  # depth lift per shell outward (outer strands catch more light)


def shell_height(lift: dict, d_in, az, el, share: float) -> np.ndarray:
    """A surface at `share` of the hair's height over the scalp (m), easing to 0 at the hairline (cap_height's ease)."""
    fa = np.abs(((np.asarray(az, float) + 180) % 360) - 180)
    ease = EASE - (EASE - EASE_FRONT) * (1 - _ss((fa - 40.0) / 25.0))
    return np.minimum(share * lift_at(lift, az, el), LIFT_MAX * share / LIFT) * _ss(np.asarray(d_in, float) / ease)


def grey_map(hair: np.ndarray, rows_el: np.ndarray, m: dict | None = None) -> np.ndarray:
    """GREY_MAP on the chart (rows = elevation 90 -> e0, columns = azimuth, 0 = the front): a grey share by the hair's
    own height h (0 = its lowest row, 1 = the top) and fa = degrees from the front, smoothed ~1 cm."""
    from scipy import ndimage
    m = m or GREY_MAP
    H, W = hair.shape
    lo = float(rows_el[np.nonzero(hair.any(1))[0].max()])
    h = np.clip((rows_el - lo) / max(90.0 - lo, 1e-3), 0, 1)[:, None] * np.ones((1, W))
    fa = np.abs((((np.arange(W) + 0.5) / W * 360.0 + 180) % 360) - 180)[None] * np.ones((H, 1))
    band, low = np.interp(fa, m["fa"], m["band"]), np.interp(fa, m["fa"], m["low"])
    a0, a1, b0, b1 = m["band_h"]
    g = low + (band - low) * _ss((h - a0) / max(a1 - a0, 1e-3))
    g = g + (float(m["top"]) - g) * _ss((h - b0) / max(b1 - b0, 1e-3))
    return ndimage.gaussian_filter(g, (H / 60.0, W / 120.0), mode=("nearest", "wrap"))


def combed(chart: dict, heights=SHELL_HEIGHTS, base: float = SHELL_BASE, seed: int = 0, ss: int = 2,
           cover: float | None = None) -> dict:
    """The combed picture: {"cap": chart-like maps (alpha, id, depth, grey, cover, normal, flow) for the cap,
    "shells": [the same per shell height]}. Strands are traced along chart["lay"] from blue-ish random roots over the
    hair, each LAY_LEN x the groom's length there, and drawn into a z-buffer whose height rises root -> tip (each
    strand's tip lies over the next one's root: the shingled lay of combed hair) plus how far the strand stands
    (`s`). A shell at height share h shows only the strands' runs that stand above it: s x rise(t) >= (h - base) /
    (1 - base), so the outer shells are sparse strand bits (alpha-tested), never a copy of the cap."""
    from scipy import ndimage
    H, W = chart["alpha"].shape
    e0, R = float(chart["e0"]), float(chart["R"])
    rng = np.random.default_rng(seed + 977)
    rows_el = 90.0 - (np.arange(H) + 0.5) / H * (90.0 - e0)
    mu = 2 * np.pi * R * np.maximum(np.cos(np.radians(rows_el)), 0.03) / W  # m per texel round the head, by row
    mv = float(np.radians(90.0 - e0) * R) / H
    dens = ndimage.gaussian_filter(np.maximum(chart["cover"], chart["base"]), 3.0)
    hair = dens > 0.08
    area = hair * np.clip(dens / 0.4, 0, 1) * mu[:, None] * mv  # (thinning toward the hairline, as the groom does)
    AA, EE = np.meshgrid((np.arange(W) + 0.5) / W * 360.0, rows_el, indexing="xy")
    Lmap = np.clip(LAY_LEN * lift_at(chart["length"], AA, EE), LAY_MIN, LAY_MAX)
    n = int((cover or LAY_COVER) * float(area.sum()) / (WIDTH * float(np.mean(Lmap[hair])))) if hair.any() else 0
    p = (area / max(float(area.sum()), 1e-12)).ravel()
    cell = rng.choice(len(p), size=n, p=p)
    y = (cell // W) + rng.uniform(0, 1, n)
    x = (cell % W) + rng.uniform(0, 1, n)
    L = Lmap[np.clip(y.astype(int), 0, H - 1), np.clip(x.astype(int), 0, W - 1)]
    K = int(np.ceil(LAY_MAX / LAY_STEP))
    s = rng.uniform(0, 1, n) ** 0.7  # how far each strand stands off the cap (0 = lies on it, 1 = the hair's top)
    sid_r = rng.uniform(0, 1, n).astype(np.float32)
    lay = chart["lay"]
    # grey: each strand grey by the chart's regional share (its top strands' grey over its cover, ~6 mm)
    gsh = ndimage.gaussian_filter(chart["grey"], 6.0) / np.maximum(ndimage.gaussian_filter(np.minimum(chart["cover"] * 4, 1.0), 6.0), 1e-3)
    if GREY_SPREAD != 1.0 and hair.any():
        md_ = float(np.median(gsh[hair]))
        gsh = md_ + GREY_SPREAD * (gsh - md_)
        print(f"combed grey: share p10/50/90 {np.round(np.percentile(np.clip(gsh[hair], 0, 1), [10, 50, 90]), 2)} (spread {GREY_SPREAD})", flush=True)
    if GREY_REGION > 0 and hair.any():
        gsh = (1 - GREY_REGION) * gsh + GREY_REGION * grey_map(hair, rows_el)
        print(f"combed grey: regional share p10/50/90 {np.round(np.percentile(np.clip(gsh[hair], 0, 1), [10, 50, 90]), 2)} (region {GREY_REGION})", flush=True)
    gsh = np.clip(gsh, 0, 1)
    grey_s = rng.uniform(0, 1, n) < gsh[np.clip(y.astype(int), 0, H - 1), np.clip(x.astype(int), 0, W - 1)]
    ang_w = rng.normal(0, LAY_WOBBLE, n)
    turn = rng.normal(0, LAY_WOBBLE / 8, n)  # rad per step
    P = np.zeros((K + 1, n, 2))
    P[0, :, 0], P[0, :, 1] = x, y
    for k in range(K):
        iy = np.clip(P[k, :, 1].astype(int), 0, H - 1)
        ix = P[k, :, 0].astype(int) % W
        e_, u_ = lay[iy, ix, 0].astype(float), lay[iy, ix, 1].astype(float)
        a_ = ang_w + turn * k
        e2, u2 = e_ * np.cos(a_) - u_ * np.sin(a_), e_ * np.sin(a_) + u_ * np.cos(a_)
        P[k + 1, :, 0] = (P[k, :, 0] + e2 * LAY_STEP / mu[iy]) % W
        P[k + 1, :, 1] = P[k, :, 1] - u2 * LAY_STEP / mv
    ks = np.minimum(np.ceil(L / LAY_STEP).astype(int), K)  # each strand's steps
    kk, jj = np.nonzero(np.arange(K)[:, None] < ks[None])  # (step, strand) of every segment
    t0, t1 = kk / ks[jj], (kk + 1) / ks[jj]
    u0, v0 = P[kk, jj, 0] * ss, P[kk, jj, 1] * ss
    u1, v1 = P[kk + 1, jj, 0] * ss, P[kk + 1, jj, 1] * ss
    tm = 0.5 * (t0 + t1)
    rise = _ss(tm / 0.35) * (1 - 0.2 * tm)  # out of the scalp, then lying (tips a little lower)
    W2, H2 = W * ss, H * ss
    mu2 = np.repeat(mu / ss, ss).astype(np.float64)
    mv2 = mv / ss

    def draw(sel, wd, hgt):
        zb = np.full((H2, W2), -1.0, np.float32)
        sb = np.full((H2, W2), -1, np.int32)
        dub = np.zeros((H2, W2), np.float32)
        dvb = np.zeros((H2, W2), np.float32)
        iv_ = np.clip(v0[sel].astype(int), 0, H2 - 1)
        ru = np.clip(0.5 * wd / mu2[iv_], 0.6, 30.0)
        rv = np.clip(np.full(len(iv_), 0.5 * wd / mv2), 0.6, 30.0)
        _raster(u0[sel], v0[sel], hgt[sel].astype(np.float64), u1[sel], v1[sel], hgt[sel].astype(np.float64), ru, rv,
                np.nonzero(sel)[0].astype(np.int64), W2, H2, zb, sb, dub, dvb, mu2, mv2)
        return zb, sb, dub, dvb

    def maps(zb, sb, dub, dvb, under=None, lift_dep=0.0):
        cov = sb >= 0
        sg = np.maximum(sb, 0)

        def down(a):
            return a.reshape(H, ss, W, ss).mean((1, 3)).astype(np.float32)
        a = down(cov.astype(np.float32))
        ws = np.maximum(a, 1e-4)
        idm = down(np.where(cov, sid_r[jj[sg]], 0.0)) / ws
        tt = down(np.where(cov, tm[sg], 0.0)) / ws
        st = down(np.where(cov, s[jj[sg]], 0.0)) / ws
        gr = down(np.where(cov, grey_s[jj[sg]].astype(np.float32), 0.0)) / ws
        fu, fv = down(np.where(cov, dub, 0.0)), down(np.where(cov, dvb, 0.0))
        hm = down(np.where(cov, zb, 0.0)) / ws
        # depth: roots deep, tips and standing strands lit; the edge of every strand shaded (the gap between hairs)
        edge = ndimage.gaussian_filter(a, 0.8)
        dep = np.clip(LAY_DEP0 + LAY_DEP_T * tt + LAY_DEP_S * st + lift_dep, 0.08, 1.0) * (1 - EDGE_SHADE + EDGE_SHADE * np.clip(edge, 0, 1))
        if SHADE_MAP:
            dep = dep * grey_map(hair, rows_el, {**GREY_MAP, **SHADE_MAP})
        vm = grey_map(hair, rows_el, {**GREY_MAP, **VALUE_MAP}).astype(np.float32) if VALUE_MAP else None
        hs = ndimage.gaussian_filter(hm * 0.0012, 0.7)
        su = np.gradient(hs, axis=1) / mu[:, None]
        sv = -np.gradient(hs, axis=0) / mv
        su, sv = np.clip(RELIEF * su, -SLOPE, SLOPE), np.clip(RELIEF * sv, -SLOPE, SLOPE)
        nrm = np.stack([-su, -sv, np.ones_like(su)], -1)
        nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
        fl = np.maximum(np.hypot(fu, fv), 1e-9)
        flow = np.stack([fu / fl, fv / fl, np.clip(a * 2, 0, 1)], -1).astype(np.float32)
        out = {"alpha": a, "id": np.clip(idm, 0, 1), "depth": dep, "grey": np.clip(gr, 0, 1), "cover": a,
               "normal": nrm.astype(np.float32), "flow": flow}
        if vm is not None:
            out["value"] = vm
        if under is not None:  # the cap: the opaque base (the hair's dark inside) between the strands
            u_ = a < under
            out["depth"] = np.where(u_, a * dep + (1 - a) * BASE_DEPTH * 0.8, dep).astype(np.float32)
            out["id"] = np.where(u_, a * out["id"] + (1 - a) * 0.5, out["id"]).astype(np.float32)
            out["grey"] = (out["grey"] * np.where(u_, a, 1.0)).astype(np.float32)
            out["alpha"] = np.maximum(a, under).astype(np.float32)
        return out
    allsel = np.ones(len(kk), bool)
    under = np.asarray(chart["base"], np.float32)
    if BASE_EDGE > 0 and hair.any():  # the base fades in from the hair's edge (distance in metres: rows mv, columns mu)
        mu_h = float(np.median(np.broadcast_to(mu[:, None], hair.shape)[hair]))
        dist = ndimage.distance_transform_edt(hair, sampling=(mv, mu_h))
        under = (under * _ss(np.clip(dist / BASE_EDGE, 0, 1))).astype(np.float32)
    cap = maps(*draw(allsel, WIDTH, tm + 0.5 * s[jj]), under=under)
    shells = []
    for j, hsh in enumerate(heights):
        g = (float(hsh) - base) / max(1 - base, 1e-3)
        sel = s[jj] * rise >= g
        sh = maps(*draw(sel, SHELL_WIDTH, tm + 0.5 * s[jj]), lift_dep=SHELL_LIT * (j + 1))
        sh["height"] = float(hsh)
        shells.append(sh)
    return {"cap": {**cap, "lift": chart["lift"]}, "shells": shells, "strands": int(n), "segments": int(len(kk)),
            "base": float(base)}
