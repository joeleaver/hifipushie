"""Measures on a frame: hairness, outline rays, edge softness, the hairline, baby hairs, the strand field,
the parting, waviness, lengths, the colour split. Part of the hair read (hair_read.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import hair_read
from .hair_read import _hex, _hex_lin, _lab_px, pixel_rays

# ------------------------------------------------------------------------------------------------ measures
def hairness(img, hair_p, bg_p, mm: float) -> dict:
    """Pixel-level hairness: where each pixel lies on the line from the backdrop's colour (0) to the dense hair's (1),
    clipped to [-0.5, 1.5]; also the solid hair mask (hair probability > 0.5, refined to the pixels: hairness > 0.5
    within 3 mm of it, holes filled, single hairs opened away)."""
    from scipy import ndimage as ndi
    a = np.asarray(img, float)[..., :3]
    hp = np.asarray(hair_p, float)
    core = ndi.binary_erosion(hp > 0.9, iterations=max(1, int(round(2.0 / mm))))
    if core.sum() < 50:
        core = hp > 0.9
    hc = np.median(a[core], 0) if core.any() else np.array([90.0, 85, 80])
    bgm = np.asarray(bg_p, float) > 0.95
    bg = np.median(a[bgm], 0) if bgm.sum() > 50 else np.median(a[:40, :40].reshape(-1, 3), 0)
    # the backdrop LOCALLY (a room: a warm wall, a dark couch, a lamp): the backdrop pixels' colour averaged over
    # ~12 mm, filled in under the head from further out; one global backdrop colour made a dark couch "hair"
    w = bgm.astype(float)
    s_ = max(12.0 / mm, 2.0)
    loc = np.stack([ndi.gaussian_filter(a[..., k] * w, s_) for k in range(3)], -1)
    ww = ndi.gaussian_filter(w, s_)
    far = np.stack([ndi.gaussian_filter(a[..., k] * w, 4 * s_) for k in range(3)], -1)
    wf = ndi.gaussian_filter(w, 4 * s_)
    bgl = np.where((ww > 0.05)[..., None], loc / np.maximum(ww, 1e-6)[..., None],
                   np.where((wf > 0.01)[..., None], far / np.maximum(wf, 1e-6)[..., None], bg))
    ax = hc - bgl
    t = np.clip(((a - bgl) * ax).sum(-1) / np.maximum((ax * ax).sum(-1), 100.0), -0.5, 1.5)
    # the pixels may refine the parser's edge by a little (1.5 mm), never claim what it calls something else (a
    # black shirt or a dark couch beside dark hair)
    near = ndi.binary_dilation(hp > 0.5, iterations=max(1, int(round(1.5 / mm)))) & (hp > 0.15)
    solid = near & (ndi.gaussian_filter(t, 0.5) > 0.5)
    solid = ndi.binary_fill_holes(solid)
    solid = ndi.binary_opening(solid, iterations=max(1, int(round(0.4 / mm))))
    lab, n = ndi.label(solid)
    if n > 1:  # the hair is one piece (or two, parted round the face); specks are not the mass
        sz = ndi.sum(solid, lab, range(1, n + 1))
        solid = np.isin(lab, 1 + np.nonzero(sz >= 0.05 * sz.max())[0])
    return {"a": t, "solid": solid, "hair_rgb": hc, "bg_rgb": bg, "core": core}


def outline_rays(skull, solid, a, bg_p, c, mm: float, angles=None) -> dict:
    """Along rays from the head centre's pixel c (angle 0 = image up, + = image right): the skull's edge, the solid
    hair's edge (px), whether the hair there meets the backdrop, and the halo (mean hairness 0.5-4 mm past the edge).
    Returns arrays per angle: ang, skull_px, hair_px, standoff_mm (nan where the hair doesn't meet the backdrop),
    halo, wisps mask (detached hair pieces within WISP_REACH mm)."""
    from scipy import ndimage as ndi
    H, W = solid.shape
    ang = np.arange(-120.0, 120.1, 1.0) if angles is None else np.asarray(angles, float)
    rmax = int(260.0 / mm)
    r = np.arange(0, rmax)
    th = np.radians(ang)
    X = c[0] + np.sin(th)[:, None] * r[None, :]
    Y = c[1] - np.cos(th)[:, None] * r[None, :]
    inb = (X >= 0) & (X < W - 1) & (Y >= 0) & (Y < H - 1)
    xi, yi = np.clip(np.round(X).astype(int), 0, W - 1), np.clip(np.round(Y).astype(int), 0, H - 1)
    S, M, B = skull[yi, xi] & inb, solid[yi, xi] & inb, bg_p[yi, xi]
    A = ndi.map_coordinates(np.asarray(a, float), [Y, X], order=1, mode="nearest")
    sk_px = np.where(S.any(1), S.shape[1] - 1 - np.argmax(S[:, ::-1], 1), 0)
    # the hair's edge: the outermost solid pixel along the ray (the solid mask has no detached pieces). It may lie INSIDE
    # the skull's edge: there the head's shape and the picture disagree (the skull pokes through the hair), reported as
    # a negative stand-off, never clipped
    has = M.any(1)
    hr_px = np.where(has, M.shape[1] - 1 - np.argmax(M[:, ::-1], 1), 0)
    far = np.clip(hr_px + int(round(8.0 / mm)), 0, rmax - 1)
    meets = has & (B[np.arange(len(ang)), far] > 0.6) & inb[np.arange(len(ang)), far]
    # ... and only where the hair reaches the skull's edge region (over the forehead / face the outline is skin)
    meets &= hr_px > sk_px - int(round(25.0 / mm))
    st = np.where(meets, (hr_px - sk_px) * mm, np.nan)
    lo, hi = int(round(hair_read.HALO_BAND[0] / mm)), max(int(round(hair_read.HALO_BAND[0] / mm)) + 1, int(round(hair_read.HALO_BAND[1] / mm)))
    halo = np.full(len(ang), np.nan)
    for k in np.nonzero(meets)[0]:
        seg = A[k, hr_px[k] + lo:hr_px[k] + hi]
        if len(seg):
            halo[k] = float(np.clip(seg, 0, 1).mean())
    # roughness: the edge against its own ROUGH_DEG average (runs that meet the backdrop only)
    rough = np.nan
    e = np.where(meets, hr_px * mm, np.nan)
    if np.isfinite(e).sum() > 2 * hair_read.ROUGH_DEG:
        k_ = int(hair_read.ROUGH_DEG)
        ef = np.where(np.isfinite(e), e, 0.0)
        wt = np.isfinite(e).astype(float)
        sm = ndi.uniform_filter1d(ef, k_) / np.maximum(ndi.uniform_filter1d(wt, k_), 1e-6)
        d = (e - sm)[np.isfinite(e) & (ndi.uniform_filter1d(wt, k_) > 0.99)]
        rough = float(np.std(d)) if len(d) > 10 else np.nan
    # wisps: hair-coloured pieces detached from the solid mass, within WISP_REACH mm, over the backdrop
    near = ndi.binary_dilation(solid, iterations=max(1, int(round(hair_read.WISP_REACH / mm)))) & ~ndi.binary_dilation(
        solid, iterations=max(1, int(round(0.8 / mm))))
    pieces = (ndi.gaussian_filter(np.asarray(a, float), 0.6) > 0.35) & near & (np.asarray(bg_p) > 0.3)
    lab, n = ndi.label(pieces)
    wisps = 0
    if n:
        sz = ndi.sum(pieces, lab, range(1, n + 1))
        sl = ndi.find_objects(lab)
        for k, (s_, sl_) in enumerate(zip(sz, sl)):
            ext = max(sl_[0].stop - sl_[0].start, sl_[1].stop - sl_[1].start) * mm
            if s_ >= 3 and ext >= 1.5:   # a hair, not a speck of noise: at least 1.5 mm long
                wisps += 1
    outline_cm = float(np.nansum(np.where(meets, hr_px, 0)) * np.radians(1.0) * mm / 10.0) if angles is None else np.nan
    return {"ang": ang, "skull_px": sk_px, "hair_px": hr_px, "standoff_mm": st, "halo": halo, "meets": meets,
            "rough_mm": rough, "wisps": wisps, "outline_cm": outline_cm}


def edge_softness(prob, a, pts, normals, mm: float, reach: float = 5.0) -> dict:
    """The mean profile of `a` (0 one side, 1 the other) across a line at pts (px) along normals (unit, toward 1),
    -reach..+reach mm: {"width_mm": distance from 20 % to 80 % of the way, "profile": [...]}. Averaging over many
    places first: one strand's edge is sharp; what is soft is how far the hair thins out."""
    from scipy import ndimage as ndi
    if len(pts) < 5:
        return {}
    s = np.arange(-reach, reach + 1e-9, 0.25)
    X = pts[:, 0][:, None] + normals[:, 0][:, None] * s[None, :] / mm
    Y = pts[:, 1][:, None] + normals[:, 1][:, None] * s[None, :] / mm
    prof = ndi.map_coordinates(np.asarray(a, float), [Y, X], order=1, mode="nearest").mean(0)
    lo, hi = float(np.mean(prof[:4])), float(np.mean(prof[-4:]))
    if hi - lo < 0.15:
        return {"width_mm": None, "profile": prof.round(3).tolist(), "contrast": round(hi - lo, 3)}
    q = (prof - lo) / (hi - lo)
    i20 = int(np.argmax(q >= 0.2))
    i80 = int(np.argmax(q >= 0.8))
    return {"width_mm": round(float(s[i80] - s[i20]), 2), "profile": prof.round(3).tolist(), "contrast": round(hi - lo, 3)}


def hairline_pixels(hair_p, skin_p, step: int = 2):
    """The hair / bare-skin boundary (px, every `step`-th) and its normals toward the hair."""
    from scipy import ndimage as ndi
    H = np.asarray(hair_p) > 0.5
    S = np.asarray(skin_p) > 0.5
    B = H & ndi.binary_dilation(S, iterations=2) & ~ndi.binary_erosion(H, iterations=1)
    ys, xs = np.nonzero(B)
    keep = ((ys % step) == 0) & ((xs % step) == 0)
    ys, xs = ys[keep], xs[keep]
    g = ndi.gaussian_filter(np.asarray(hair_p, float) - np.asarray(skin_p, float), 2.0)
    gy, gx = np.gradient(g)
    n = np.stack([gx[ys, xs], gy[ys, xs]], 1)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    return np.stack([xs, ys], 1).astype(float), n


def skin_hairness(img, skin_p, hair_rgb):
    """Hairness against the SKIN: 0 at the bare skin's colour, 1 at the dense hair's (the hairline's own axis)."""
    a = np.asarray(img, float)[..., :3]
    sk = np.asarray(skin_p) > 0.9
    skc = np.median(a[sk], 0) if sk.sum() > 50 else np.array([200.0, 160, 140])
    ax = np.asarray(hair_rgb, float) - skc
    return np.clip(((a - skc) @ ax) / max(float(ax @ ax), 1e-6), -0.5, 1.5), skc


def baby_hairs(a_skin, hair_p, skin_p, mm: float) -> int:
    """Detached hair specks on the skin side of the hairline (0.5-6 mm from the hair): fine baby hairs."""
    from scipy import ndimage as ndi
    H = np.asarray(hair_p) > 0.5
    band = ndi.binary_dilation(H, iterations=max(1, int(round(6.0 / mm)))) & ~ndi.binary_dilation(
        H, iterations=max(1, int(round(0.5 / mm)))) & (np.asarray(skin_p) > 0.5)
    pieces = band & (ndi.gaussian_filter(np.asarray(a_skin, float), 0.5) > 0.6)
    lab, n = ndi.label(pieces)
    if not n:
        return 0
    k = 0
    sz = ndi.sum(pieces, lab, range(1, n + 1))
    for a_, sl in zip(sz, ndi.find_objects(lab)):  # a hair: 1-8 mm long and thin (its area under 0.5 mm x its length:
        ln = float(np.hypot(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start)) * mm  # pores, creases are round / wide)
        if 1.0 <= ln <= 8.0 and a_ * mm * mm <= 0.5 * ln:
            k += 1
    return k


def strand_field(img, mask, mm: float):
    """Per pixel the strand direction (deg, image axes, y down, axial) and coherence, over `mask` (hair)."""
    from .hair_trace import _orientation
    ang, coh = _orientation(img, max(0.8 / mm, 1.0))
    return ang, np.where(mask, coh, 0.0)


def parting(img, solid, a_skin, mm: float, top_px: int, hairline_px: int, c) -> dict:
    """A part in a front-ish view: across the top band (between the hair's top and its hairline, the middle 70 % of
    its width) the strands' tilt (sin 2 theta, coherence-weighted) per 2 mm column; a part is where the tilt flips
    sharply with a thin line of scalp-coloured pixels along it. {"seen": bool, "x_px", "strength" 0..1, "width_mm"
    (the flip's 25 -> 75 % width), "scalp" (the line's scalp-ness), "sweep": the front's mean upward direction
    (+ = image right)}."""
    from scipy import ndimage as ndi
    H, W = solid.shape
    y0 = int(np.clip(top_px, 0, H - 1))
    y1 = int(np.clip(top_px + 0.6 * max(hairline_px - top_px, 1), y0 + 2, H))
    band = np.zeros_like(solid)
    band[y0:y1] = True
    band &= ndi.binary_erosion(solid, iterations=max(1, int(round(3.0 / mm))))
    if band.sum() < 200:
        return {"seen": False, "why": "no top band"}
    ang, coh = strand_field(img, band, mm)
    th = np.radians(ang)
    s2 = np.sin(2 * th) * coh
    xs = np.nonzero(band.any(0))[0]
    xa, xb = xs.min(), xs.max()
    xa, xb = int(xa + 0.15 * (xb - xa)), int(xb - 0.15 * (xb - xa))
    bw = max(2, int(round(2.0 / mm)))
    cols = np.arange(xa, xb - bw, bw)
    prof, sc_ = [], []
    for x in cols:
        m = band[:, x:x + bw]
        prof.append(float(s2[:, x:x + bw][m].sum() / max(coh[:, x:x + bw][m].sum(), 1e-6)) if m.sum() > 10 else np.nan)
        sc_.append(float(np.clip(-a_skin[:, x:x + bw][m] + 1, 0, 1).mean()) if m.sum() > 10 else np.nan)
    prof = np.array(prof)
    sc_ = np.array(sc_)
    ok = np.isfinite(prof)
    if ok.sum() < 8:
        return {"seen": False, "why": "too few columns"}
    prof = np.interp(np.arange(len(prof)), np.nonzero(ok)[0], prof[ok])
    sm = ndi.uniform_filter1d(prof, 3)
    d = max(2, int(round(8.0 / (bw * mm))))
    jump = np.zeros(len(sm))
    jump[d:-d] = np.abs(sm[2 * d:] - sm[:-2 * d]) / 2 if len(sm) > 2 * d else 0
    k = int(np.argmax(jump))
    strength = float(jump[k])
    # the flip's width: 25 -> 75 % of the way between the two sides' levels
    a_, b_ = sm[max(k - d, 0)], sm[min(k + d, len(sm) - 1)]
    lo_, hi_ = min(a_, b_), max(a_, b_)
    seg = sm[max(k - d, 0):min(k + d, len(sm) - 1) + 1]
    q = (seg - lo_) / max(hi_ - lo_, 1e-6)
    q = q if a_ < b_ else 1 - q
    w = float((np.argmax(q >= 0.75) - np.argmax(q >= 0.25)) * bw * mm) if len(q) else np.nan
    scl = sc_[k] - float(np.nanmedian(sc_)) if np.isfinite(sc_[k]) else 0.0
    # the front's sweep: the upward strand direction just above the hairline (+ = image right)
    fy0 = int(max(hairline_px - 25.0 / mm, y0))
    fb = np.zeros_like(solid)
    fb[fy0:int(hairline_px)] = True
    fb &= solid
    sweep = np.nan
    if fb.sum() > 100:
        a2, c2 = strand_field(img, fb, mm)
        t2 = np.radians(a2)
        ux, uy = np.cos(t2), np.sin(t2)
        ux = np.where(uy > 0, -ux, ux)  # directed UP the picture (from the root at the hairline)
        x0 = c[0]
        wt = c2 * (np.abs(np.arange(W)[None, :] - x0) < 0.3 * (xb - xa))
        sweep = float((ux * wt).sum() / max(wt.sum(), 1e-6))
    seen = bool(strength > 0.3 and np.isfinite(w) and scl > 0.05)
    return {"seen": seen, "x_px": float(cols[k] + bw / 2), "strength": round(strength, 3),
            "width_mm": round(w, 1) if np.isfinite(w) else None, "scalp": round(float(scl), 3),
            "sweep": round(sweep, 3) if np.isfinite(sweep) else None, "profile": np.round(sm, 2).tolist()}


def pixel_z(cam: dict, C, uv) -> np.ndarray:
    """World z of pixels on the plane through C facing the camera (hair hanging beside / behind the head)."""
    eye, D = pixel_rays(cam, uv)
    fwd = np.asarray(C, float) - eye
    fwd /= np.linalg.norm(fwd)
    t = ((np.asarray(C, float) - eye) @ fwd) / np.maximum(D @ fwd, 1e-6)
    return (eye + t[:, None] * D)[:, 2]


def waviness(img, mask, mm: float) -> float | None:
    """0 straight .. ~1 curly: 1 - the coherence of the strand direction over 15 mm windows (the structure tensor's
    orientation at ~1.5 mm, as unit vectors of twice the angle, averaged): straight lengths keep one direction over a
    window, waves turn within it."""
    from scipy import ndimage as ndi
    m = np.asarray(mask, bool)
    if m.sum() < 400:
        return None
    ang, coh = strand_field(img, m, mm / 2.0)  # (sigma ~1.6 mm)
    th = np.radians(ang)
    w = coh * m
    s = max(15.0 / mm / 2.0, 2.0)
    cx = ndi.gaussian_filter(np.cos(2 * th) * w, s)
    sx = ndi.gaussian_filter(np.sin(2 * th) * w, s)
    ww = ndi.gaussian_filter(w, s)
    R = np.hypot(cx, sx) / np.maximum(ww, 1e-6)
    inner = ndi.binary_erosion(m, iterations=max(1, int(round(4.0 / mm))))
    return round(float(1.0 - np.median(R[inner])), 3) if inner.sum() > 200 else None


def lengths(f: dict, sc, solid, mm: float) -> dict:
    """{"bottom_m": how far under the head centre the hair reaches in this view (m, + = below), "waviness" of the
    hair more than 4 cm under the centre (the lengths), or {} when the hair stops above the jaw}."""
    from scipy import ndimage as ndi
    lab, n = ndi.label(solid)
    if not n:
        return {}
    k = 1 + int(np.argmax(ndi.sum(solid, lab, range(1, n + 1))))
    m = lab == k
    ys, xs = np.nonzero(m)
    j = np.argsort(ys)[-max(5, len(ys) // 1000):]  # the lowest 0.1 % (not one stray pixel)
    zb = float(np.median(pixel_z(f["cam"], sc.C, np.stack([xs[j], ys[j]], 1).astype(float))))
    out = {"bottom_m": round(float(sc.C[2] - zb), 3)}
    # the lengths: hair pixels whose plane height is 4+ cm under the centre
    H, W = m.shape
    rows = np.arange(H)
    zr = pixel_z(f["cam"], sc.C, np.stack([np.full(H, f["c"][0]), rows], 1).astype(float))
    low = m & (zr[:, None] < sc.C[2] - 0.04)
    if low.sum() > 400:
        out["waviness"] = waviness(f["image"], low, mm)
    return out


def colour_split(img, dense, mm: float, T: float | None = None) -> dict:
    """The dense hair's colour (colour_bands with variation) and a TWO-MODE split: the pigmented hair (darker) and the
    light / grey strands (lighter, low chroma), at the Otsu threshold of L*. seen = the median of the upper half of the
    pigmented mode (its lit side, as look.seen wants); grey = the median of the light strands."""
    from .hair_card_fit import colour_bands
    a = np.asarray(img, float)[..., :3]
    m = np.asarray(dense, bool)
    if m.sum() < 200:
        return {}
    px = a[m]
    lab = _lab_px(px)
    L, C = lab[:, 0], np.hypot(lab[:, 1], lab[:, 2])
    # Otsu on L*
    h, e = np.histogram(L, 64)
    p = h / h.sum()
    w0 = np.cumsum(p)
    mu = np.cumsum(p * (e[:-1] + e[1:]) / 2)
    var = (mu[-1] * w0 - mu) ** 2 / np.maximum(w0 * (1 - w0), 1e-9)
    T = float(e[int(np.argmax(var)) + 1]) if T is None else float(T)  # (given: the picture's, so shares compare)
    dark, light = L <= T, L > T
    upper = dark & (L >= np.median(L[dark])) if dark.any() else dark
    out = {"bands": colour_bands(img, m, mm), "threshold_L": round(T, 1),
           "light_share": round(float(light.mean()), 3),
           "seen": _hex(np.median(px[upper], 0)) if upper.sum() > 20 else None,
           "grey": _hex(np.median(px[light & (C < max(8.0, np.median(C)))], 0)) if (light & (C < max(8.0, np.median(C)))).sum() > 20 else None,
           # a grey STRAND is lighter than the light pixels' median: strands are finer than a pixel, so most light
           # pixels are grey hairs mixed with dark ones (salt and pepper); the lightest quarter is nearer one strand
           "grey_strand": (_hex(np.median(px[light & (C < max(8.0, np.median(C))) & (L >= np.percentile(L[light], 75))], 0))
                           if light.sum() > 80 else None),
           # GREY or LIT: grey hairs are LESS chromatic than the pigmented ones (the man's crop 0.73), the lit side of
           # pigmented hair MORE (1.4-1.55 on three heads of brown / black hair): light mode chroma / dark mode chroma
           "chroma_ratio": (round(float(np.median(C[light]) / max(np.median(C[dark]), 0.5)), 2)
                            if light.sum() > 20 and dark.sum() > 20 else None),
           "lit": _hex(np.median(px[light], 0)) if light.sum() > 20 else None,
           # the mean colour (linear light, back to sRGB): what one colour step matches when the modes differ in share
           "mean_rgb": _hex_lin(np.mean(np.where(px / 255 <= 0.04045, px / 255 / 12.92, ((px / 255 + 0.055) / 1.055) ** 2.4), 0)),
           "dark_L": round(float(np.median(L[dark])), 1) if dark.any() else None,
           "light_L": round(float(np.median(L[light])), 1) if light.any() else None,
           "chroma": round(float(np.median(C)), 1)}
    return out
