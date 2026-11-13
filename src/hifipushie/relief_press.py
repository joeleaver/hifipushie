"""Press a part's surface, as a reference picture shows it, into the clay: from the feature map's marks and the
picture's read surface (surfaceread.py) to a relief blob (relief.py).

For one mass and one flat view:
  region    what the picture shows of the mass itself: its mark and the marks of the forms on it, less every mass
            that stands on it (they are pressed on their own)
  read      the picture's surface on a close-up of that region, and the relief its slopes add up to there
  place     the picture gives the slopes; how far the part stands towards the viewer at each height is the
            OUTLINE of the view at right angles (its profile). A piece that view can't place is laid on the clay
            that is there by a plane (depth and tilt the clay's)
  press     clay is added up to the relief and whatever stands in front of it is cut away, as far as the read
            surface faces the viewer: fully where it does, less and less as it turns away (another view sees that
            better, and the two meet in a slope), only on the viewer's side of the part (relief.py)
The pictures of a turnaround never agree exactly, and nothing here averages them: each press takes one picture's
word for one region. Which picture a feature is taken from is the sculptor's choice (`leave`).
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from scipy import ndimage

from . import featuremap, featuresee, refread, relief, sdf, surfaceread
from .spec import compile_prims

FRAMES = {  # view kind: (F towards the viewer, U to the picture's right), on the creature's axes
    "front": ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0)), "back": ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)),
    "side": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)), "side_r": ((-1.0, 0.0, 0.0), (0.0, -1.0, 0.0))}
CROSS = {"front": ("side", -1.0, "min"), "back": ("side", 1.0, "max"), "side": ("front", 1.0, "max"),
         "side_r": ("front", -1.0, "min")}  # view kind: (the view at right angles, sign of its sideways axis, which edge)
SUB = 2            # relief pixels are this many read pixels
FACING = (0.35, 0.6)   # how much the read surface faces the viewer (its nz): nothing below, fully above
BORDER = 0.004     # m: the facing is judged over this much of the surface
INSET = 0.002      # m: the cut stays this far in from the region's border (a neighbour standing there isn't shaved)
GATE = 0.02        # m: the relief reaches this deep under the surface, at most (and never past the part's middle)
SCALE = 0.04       # m: a relief brings what is smaller than this; the larger lie of a part is its marks' (the clay's)
EDGE = 0.01        # m: a detail relief has no hold at the figure's outline, and full hold this far in from it
STEEP = (0.5, 0.75)   # the relief's own lie (cosine to the view): no hold below, full hold above
REACH = 0.01       # m: a form counts as part of its mass's surface this far past the mass's own mark
RIM = 0.004        # m: this close to the figure's outline, the clay's own edge says how deep the surface is
RIM_W = 0.05       # how hard a whole press is held there (against 1 for the profile along the middle line)
GAIN = (0.7, 2.5)  # a read's depth as a whole may be muted or exaggerated by this much, no more
ZOOM = (768, 4.0)  # a close-up's long side in read pixels, and the most a view pixel is blown up


def _smooth(s):
    s = np.clip(s, 0.0, 1.0)
    return s * s * (3 - 2 * s)


def region(name: str, fm: dict, feature: str, view: str, leave=(), across=()) -> np.ndarray:
    """What `view` shows of the mass itself (view pixels): its mark and its forms' marks, less the masses on it
    and less every feature named in `leave` (taken from another view). A mass named in `across` is NOT taken out:
    it lies in this surface (an eye in its socket), and the relief runs across it."""
    feats = fm["features"]
    desc = featuremap.children(fm, feature)
    mk = featuremap.mask(name, feature, view).copy()
    k = fm["views"][view].get("m_per_px")
    near = ndimage.binary_dilation(mk, iterations=max(1, round(REACH / k))) if k else np.ones_like(mk)
    for f in desc:  # its forms, as far as they lie on it: a fringe hanging past the mass has other clay under it
        if feats[f].get("kind") == "form" and view in feats[f]["marks"] and featuresee._mass_of(fm, f) == feature:
            mk |= featuremap.mask(name, f, view) & near
    for f in desc:
        if feats[f].get("kind") == "mass" and view in feats[f]["marks"]:
            if across == "*" or f in across:
                mk |= featuremap.mask(name, f, view) & near
            else:
                mk &= ~featuremap.mask(name, f, view)
    for f in leave:
        if f in feats and view in feats[f]["marks"]:
            mk &= ~featuremap.mask(name, f, view)
    return mk


def _zfit(name: str, fm: dict, feature: str, view: str) -> tuple[float, float]:
    """Heights of this view as the view to believe has them: z' = a * z + b (featuresee.fitted's rule)."""
    c, rec = fm["features"][feature], fm["views"][view]
    auth = c.get("authority")
    if not auth or auth == view or auth not in c["marks"]:
        return 1.0, 0.0
    ra = fm["views"].get(auth) or {}
    if rec.get("kind") not in refread.ORTHO or ra.get("kind") not in refread.ORTHO:
        return 1.0, 0.0
    ya = np.where(featuremap.mask(name, feature, auth).any(1))[0]
    yb = np.where(featuremap.mask(name, feature, view).any(1))[0]
    if not len(ya) or not len(yb) or yb[-1] == yb[0]:
        return 1.0, 0.0
    a_hi, a_lo = ((ra["ground_px"] - y) * ra["m_per_px"] for y in (ya[0], ya[-1] + 1))
    b_hi, b_lo = ((rec["ground_px"] - y) * rec["m_per_px"] for y in (yb[0], yb[-1] + 1))
    a = (a_hi - a_lo) / (b_hi - b_lo)
    return float(a), float(a_lo - a * b_lo)


def profile(name: str, fm: dict, feature: str, view: str, leave=(), across=()):
    """How far the mass stands towards `view`'s viewer at each height, from its outline in the view at right
    angles: (heights ascending, metres towards the viewer, that view's name), only where that edge of the mass is
    the figure's own outline there (not where another part stands in front of it). None if no such view."""
    kind, sign, edge = CROSS[fm["views"][view]["kind"]]
    other = next((v for v, r in fm["views"].items() if r.get("kind") == kind), None)
    if other is None or other not in fm["features"][feature]["marks"]:
        return None
    rec = fm["views"][other]
    reg = ndimage.binary_opening(region(name, fm, feature, other, leave, across), iterations=2)   # no slivers left by a
    fig = np.asarray(Image.open(rec["image"]).convert("RGBA").getchannel("A")) > 127       # mass taken out of it
    za, zb = _zfit(name, fm, feature, other)
    zs, ts = [], []
    for y in np.flatnonzero(reg.any(1)):
        xs = np.flatnonzero(reg[y])
        x = xs[0] if edge == "min" else xs[-1]
        out = x - 1 if edge == "min" else x + 1
        if 0 <= out < reg.shape[1] and fig[y, out]:
            continue                                    # another part of the figure stands beyond: not an outline
        side = ((x if edge == "min" else x + 1) - rec["centre_px"]) * rec["m_per_px"]
        zs.append(za * (rec["ground_px"] - (y + 0.5)) * rec["m_per_px"] + zb)
        ts.append(sign * side)
    if len(zs) < 8:
        return None
    o = np.argsort(zs)
    return np.asarray(zs)[o], np.asarray(ts)[o], other


def _one_run(row: np.ndarray) -> bool:
    xs = np.flatnonzero(row)
    return len(xs) > 0 and xs[-1] - xs[0] + 1 <= 1.1 * len(xs)


def closeup(rec: dict, reg: np.ndarray):
    """The close-up of a region the reader is shown: (picture RGB, box in view pixels, zoom)."""
    ys, xs = np.where(reg)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    long = max(x1 - x0, y1 - y0)
    m = int(max(0.3 * long, (200 - long) / 2, 8))
    H, W = reg.shape
    box = (int(max(0, x0 - m)), int(max(0, y0 - m)), int(min(W, x1 + m)), int(min(H, y1 + m)))
    zoom = min(ZOOM[1], ZOOM[0] / max(box[2] - box[0], box[3] - box[1]))
    im = Image.open(rec["image"]).convert("RGBA").crop(box)
    size = (max(16, round(im.width * zoom)), max(16, round(im.height * zoom)))
    bg = Image.new("RGBA", im.size, (245, 245, 245, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB").resize(size, Image.LANCZOS), box, size[0] / im.width


def _hits(prims, P0: np.ndarray, F: np.ndarray, t_hi: float, t_lo: float, step: float = 0.002):
    """Along each ray P0 + t F, coming from the viewer: where the clay is first entered and where that run of clay
    ends (heights t; NaN where the ray meets none)."""
    ts = np.arange(t_hi, t_lo, -step)
    f = sdf.field_at(prims, (P0[:, None, :] + ts[None, :, None] * F[None, None, :]).reshape(-1, 3)).reshape(len(P0), -1)
    inside = f < 0
    any_in = inside.any(1)
    k = np.argmax(inside, 1)
    r = np.arange(len(P0))
    kk = np.maximum(k, 1)
    a, b = f[r, kk - 1], f[r, kk]
    near = ts[kk - 1] + (ts[kk] - ts[kk - 1]) * a / np.where(a - b == 0, 1, a - b)
    after = (~inside) & (np.arange(len(ts))[None, :] > k[:, None])
    e = np.where(after.any(1), np.argmax(after, 1), len(ts) - 1)
    a, b = f[r, e - 1], f[r, e]
    far = ts[e - 1] + (ts[e] - ts[e - 1]) * a / np.where(a - b == 0, 1, a - b)
    near[~any_in | (k == 0)] = np.nan
    far[np.isnan(near)] = np.nan
    return near, far


def _fill(a: np.ndarray) -> np.ndarray:
    """NaNs take the nearest known value."""
    bad = np.isnan(a)
    if not bad.any() or bad.all():
        return np.nan_to_num(a)
    i = ndimage.distance_transform_edt(bad, return_distances=False, return_indices=True)
    return a[tuple(i)]


def _plane(d: np.ndarray, wgt: np.ndarray, lab: np.ndarray, m: int) -> np.ndarray:
    """Per connected piece, the plane through d (weighted, robust): what of d is depth and tilt."""
    out = np.zeros_like(d)
    yy, xx = np.mgrid[0:d.shape[0], 0:d.shape[1]].astype(np.float64)
    for i in range(1, m + 1):
        piece = lab == i
        sel = piece & (wgt > 0) & np.isfinite(d)
        if sel.sum() < 12:
            out[piece] = np.nanmedian(d[piece]) if np.isfinite(d[piece]).any() else 0.0
            continue
        A = np.stack([np.ones(sel.sum()), xx[sel] - xx[sel].mean(), yy[sel] - yy[sel].mean()], 1)
        y, w = d[sel], wgt[sel].astype(np.float64)
        for _ in range(3):
            c = np.linalg.lstsq(A * w[:, None], y * w, rcond=None)[0]
            res = y - A @ c
            s = 1.4826 * np.median(np.abs(res)) + 1e-6
            w = wgt[sel] * np.minimum(1.0, 2.0 * s / np.maximum(np.abs(res), 1e-9))
        out[piece] = c[0] + c[1] * (xx[piece] - xx[sel].mean()) + c[2] * (yy[piece] - yy[sel].mean())
    return out


def _detail(name, fm, feature, view, leave, across, nm, mk, fig, hit, B, wf, px, za, zrow, scale):
    """A relief that brings what is smaller than `scale`: (top, gain, how it was placed)."""
    H2 = mk.shape[0]
    # place: slopes from the picture; the profile from the view at right angles; else a plane on the clay
    lab, m = ndimage.label(mk)
    r = surfaceread.height(nm, mk, px).astype(np.float64)
    main = lab == (1 + int(np.argmax(ndimage.sum(mk, lab, range(1, m + 1)))))
    prof = profile(name, fm, feature, view, leave, across)
    s_row, gain, placed = None, 1.0, "the clay under it (a plane)"
    if prof is not None:
        e_t = np.interp(zrow, prof[0], prof[1], left=np.nan, right=np.nan)
        wide = main.sum(1)
        # a row carries the profile if it shows the part across (not the slivers left beside a mass taken out)
        full = np.array([wide[v] >= 0.5 * wide.max() and _one_run(main[v]) for v in range(H2)])
        e_r = np.array([np.percentile(r[v][main[v]], 95) if full[v] else np.nan for v in range(H2)])
        ok = np.isfinite(e_t - e_r)
        if ok.sum() >= 12:
            vv = np.arange(H2, dtype=float)
            v0 = vv[ok].mean()
            span = (vv[ok].max() - vv[ok].min()) / max(int(np.ptp(np.flatnonzero(main.any(1)))), 1)
            deg = 2 if span >= 0.6 else 1                # depth and tilt; a bow too when most of the part is seen
            # A read mutes or exaggerates depth as a whole (one gain). Where the region ends at the figure's own
            # outline the clay's edge says how far back the surface has fallen by there: with the profile, that
            # fixes the gain. unknowns: gain, then the row polynomial
            rim = main & hit & (ndimage.distance_transform_edt(fig) * px < RIM)
            ry, rx = np.where(rim)
            if len(ry) > 3000:
                pick = np.random.default_rng(0).choice(len(ry), 3000, replace=False)
                ry, rx = ry[pick], rx[pick]
            rows_p = np.flatnonzero(ok)
            poly = lambda t: np.stack([(t - v0) ** i for i in range(deg + 1)], 1)
            A = np.vstack([np.c_[e_r[rows_p], poly(vv[rows_p])], np.c_[r[ry, rx], poly(ry.astype(float))]])
            y = np.r_[e_t[rows_p], B[ry, rx]]
            w0 = np.r_[np.ones(len(rows_p)), np.full(len(ry), len(rows_p) / max(len(ry), 1))]
            if len(ry) < 20:                              # no outline of its own to speak of: the read as it is
                A, y, w0 = np.c_[e_r[rows_p] * 0, poly(vv[rows_p])], e_t[rows_p] - e_r[rows_p], np.ones(len(rows_p))
            wr = w0.copy()
            for _ in range(5):
                c = np.linalg.lstsq(A * wr[:, None], y * wr, rcond=None)[0]
                res = y - A @ c
                sc = 1.4826 * np.median(np.abs(res)) + 1e-6
                wr = w0 * np.minimum(1.0, 2.0 * sc / np.maximum(np.abs(res), 1e-9))
            gain = float(np.clip(c[0], *GAIN)) if len(ry) >= 20 else 1.0
            if len(ry) >= 20 and gain != c[0]:           # the gain hit its limit: the rows alone set the rest
                c2 = np.linalg.lstsq(poly(vv[rows_p]), e_t[rows_p] - gain * e_r[rows_p], rcond=None)[0]
                c = np.r_[gain, c2]
            s_row = poly(vv) @ c[1:]
            fit = float(np.sqrt(np.mean((e_t[rows_p] - gain * e_r[rows_p] - poly(vv[rows_p]) @ c[1:]) ** 2)))
            placed = (f"the {prof[2]} view's outline ({len(rows_p)} rows, to {1e3 * fit:.1f} mm"
                      f"{', bow too' if deg == 2 else ''}); depth gain {gain:.2f}"
                      f"{' from ' + str(len(ry)) + ' outline points' if len(ry) >= 20 else ' (no outline of its own)'}")
    loose = mk & ~main if s_row is not None else mk
    top = r + _plane(np.where(hit & loose, B - r, np.nan), wf * mk * hit * loose, lab, m)
    if s_row is not None:
        top = np.where(main, gain * r + s_row[:, None], top)
    if scale:   # only what is smaller than `scale` is the picture's; the larger lie of the part stays the clay's
        sc = scale / px
        dd = np.where(mk & hit, top - B, 0.0)
        low = ndimage.gaussian_filter(dd, sc) / np.maximum(ndimage.gaussian_filter((mk & hit).astype(float), sc), 1e-3)
        top = np.where(mk, B + (top - B) - low, top)
    return top, gain, placed


def _whole(name, fm, feature, view, leave, rec, box, zoom, nm, mk, mk_full, fig, hit, mid, px, zrow):
    """The part's whole surface on this side, solved over its full mark (what stands in front of it is carried
    through smoothly), held in two places: at the part's own outline to the clay's mid-depth there, and along the
    middle line to the profile the view at right angles shows. The read's depth gain comes out of those two."""
    pin = np.full(mk_full.shape, np.nan)
    pw = np.zeros(mk_full.shape)
    rim = mk_full & hit & (ndimage.distance_transform_edt(fig) * px < RIM)
    pin[rim], pw[rim] = mid[rim], RIM_W
    prof = profile(name, fm, feature, view, leave, "*")
    n_mid = 0
    if prof is not None and feature[-2:] not in (".L", ".R"):
        step = 1.5 * fm["views"][prof[2]]["m_per_px"]
        seen = np.abs(zrow[:, None] - prof[0][None, :]).min(1) < step     # heights the outline really covers
        e_t = np.interp(zrow, prof[0], prof[1])
        c0 = (rec["centre_px"] - box[0]) * zoom / SUB
        for v in np.flatnonzero(seen):
            for c in {int(np.floor(c0)), int(np.ceil(c0))}:
                if 0 <= c < mk_full.shape[1] and mk_full[v, c]:
                    pin[v, c], pw[v, c] = e_t[v], 1.0
                    n_mid += 1
    r, gain = surfaceread.height(nm, mk_full, px, pin=pin, pin_w=pw, data=mk, gain=GAIN)
    placed = (f"its own outline ({int(rim.sum())} points, at the clay's mid-depth)"
              + (f" and the {prof[2]} view's profile along the middle line ({n_mid} points)" if n_mid else "")
              + f"; depth gain {gain:.2f}")
    return r.astype(np.float64), gain, placed


def maps(name: str, spec: dict, fm: dict, feature: str, view: str, leave=(), scale: float | None = SCALE,
         across=(), whole: bool = False) -> dict:
    """The relief of one mass from one flat view: {"frame", "maps", "lip", "about", "look"} (module docstring)."""
    rec = fm["views"][view]
    if rec.get("kind") not in FRAMES:
        raise ValueError(f"view {view!r} is not a flat view (front, back, side): a relief is pressed from one")
    reg = region(name, fm, feature, view, leave, across)
    if reg.sum() < 40:
        raise ValueError(f"{feature!r} shows too little of itself in {view!r} to press (its mark less the masses on it)")
    full = region(name, fm, feature, view, leave, "*") if whole else reg   # with what stands in front of it
    img, box, zoom = closeup(rec, full)
    n = surfaceread.normals([img])[0]
    h, w = n.shape[:2]
    H2, W2 = h // SUB, w // SUB

    def pooled(a, how):
        a = np.asarray(Image.fromarray(a[box[1]:box[3], box[0]:box[2]].astype(np.uint8) * 255).resize((w, h), Image.NEAREST)) > 127
        return getattr(a[:H2 * SUB, :W2 * SUB].reshape(H2, SUB, W2, SUB), how)((1, 3))

    mk = pooled(reg, "all")
    mk = ndimage.gaussian_filter(mk.astype(float), 1.5) > 0.5   # a mark's pixel steps are not the part's edge
    mk_full = ((ndimage.gaussian_filter(pooled(full, "all").astype(float), 1.5) > 0.5) | mk) if whole else mk
    fig = np.asarray(Image.open(rec["image"]).convert("RGBA").crop(box).getchannel("A").resize((w, h), Image.NEAREST)) > 127
    fig = fig[:H2 * SUB, :W2 * SUB].reshape(H2, SUB, W2, SUB).any((1, 3))
    nm = n[:H2 * SUB, :W2 * SUB].reshape(H2, SUB, W2, SUB, 3).mean((1, 3))
    nm /= np.maximum(np.linalg.norm(nm, axis=-1, keepdims=True), 1e-6)
    k = rec["m_per_px"]
    px = k * SUB / zoom
    za, zb = _zfit(name, fm, feature, view)
    # the frame: map pixel (c, r) -> world
    F, U = (np.array(v) for v in FRAMES[rec["kind"]])
    V = np.array([0.0, 0.0, -1.0])
    z0 = za * (rec["ground_px"] - box[1]) * k + zb     # world height of row 0
    o = U * (box[0] - rec["centre_px"]) * k + np.array([0.0, 0.0, z0])
    # the clay as it stands without reliefs, along the same rays (every 3rd pixel, filled in between)
    bare = {**spec, "blobs": {b: v for b, v in spec.get("blobs", {}).items() if v.get("shape") != "relief"}}
    prims = compile_prims(bare)
    adds = [p for p in prims if p.op == "add"]
    ts = sorted(float(c @ F) for c in (np.min([p.lo for p in adds], 0), np.max([p.hi for p in adds], 0)))
    st = 3
    rr, cc = np.mgrid[0:H2:st, 0:W2:st]
    P0 = o[None] + cc.reshape(-1, 1) * px * U[None] + rr.reshape(-1, 1) * px * za * V[None]
    near, far = _hits(prims, P0, F, ts[1] + 0.02, ts[0] - 0.02)
    zoomf = (H2 / rr.shape[0], W2 / rr.shape[1])

    def up(a):
        return ndimage.zoom(_fill(a.reshape(rr.shape)), zoomf, order=1, mode="nearest")[:H2, :W2]

    hit = ndimage.zoom((~np.isnan(near)).reshape(rr.shape).astype(np.float32), zoomf, order=1, mode="nearest")[:H2, :W2] > 0.5
    B, Fh = up(near), up(far)
    # how much the read surface faces the viewer (the lie of the surface, not its creases): the relief's weight.
    # Its footprint is the region where that is anything at all; the cut stays a little in from the border
    sg = BORDER / px
    nzs = ndimage.gaussian_filter(np.where(mk, nm[..., 2], 0.0), sg) / np.maximum(ndimage.gaussian_filter(mk.astype(float), sg), 1e-3)
    wf = _fill(np.where(mk, _smooth((nzs - FACING[0]) / (FACING[1] - FACING[0])), np.nan))

    def signed(a):
        return (ndimage.distance_transform_edt(~a) - ndimage.distance_transform_edt(a)) * px

    zrow = z0 - np.arange(H2) * px * za
    if whole:
        top, gain, placed = _whole(name, fm, feature, view, leave, rec, box, zoom, nm, mk, mk_full, fig, hit,
                                   0.5 * (B + Fh), px, zrow)
        wf = np.ones_like(wf)
    else:
        top, gain, placed = _detail(name, fm, feature, view, leave, across, nm, mk, fig, hit, B, wf, px, za, zrow, scale)
    top = _fill(np.where(mk_full, top, np.nan))         # past the region's border the relief just carries on:
    mid = 0.5 * (B + Fh)                                 # its edge is the footprint's, not a jump in the map
    top = np.where(hit, np.maximum(top, mid + 0.003), top)   # a relief can't cut past the middle of its part
    lo = np.maximum(mid, np.minimum(top, B) - GATE)      # where no clay stood, its neighbours' floor (B is filled)
    gy, gx = np.gradient(top, px * za, px)
    cos = np.clip(1.0 / np.sqrt(1.0 + gx ** 2 + gy ** 2), 0.25, 1.0)
    # a read is biased towards the viewer: it calls surfaces facing that it sees almost edge-on. Where the relief
    # as placed stands steep, this view does not rule either (judged over the same stretch of surface)
    if not whole:
        sy, sx = np.gradient(ndimage.gaussian_filter(top, sg), px * za, px)
        wf = wf * _smooth((1.0 / np.sqrt(1.0 + sx ** 2 + sy ** 2) - STEEP[0]) / (STEEP[1] - STEEP[0]))
        wf = wf * _smooth(ndimage.distance_transform_edt(fig) * px / EDGE)   # at the figure's outline a view sees
        #                                                                      the surface edge-on, by definition
    facing = mk_full & (wf > 0.02)     # a whole press adds under what stands in front too, but cuts only what it sees
    inner = mk & (wf > 0.02) & (ndimage.distance_transform_edt(mk) * px > INSET)
    moved = (top - B)[mk & (wf > 0.5) & hit]
    about = {"feature": feature, "view": view, "region_px": int(reg.sum()), "zoom": round(float(zoom), 2),
             "map": [int(W2), int(H2)], "px_mm": round(px * 1e3, 2),
             "faces": round(float((mk & (wf > 0.5)).sum() / max(mk.sum(), 1)), 2),
             "no_clay": round(float((mk & ~hit).sum() / max(mk.sum(), 1)), 2), "placed_by": placed, "gain": round(gain, 2),
             "moved_mm": [round(float(np.percentile(moved, q)) * 1e3, 1) for q in (2, 50, 98)] if moved.size else None}
    return {"frame": {"o": o, "U": U, "V": V / za, "F": F, "px": px},
            "maps": {"top": top, "lo": lo, "add": signed(facing), "cut": signed(inner), "k": wf, "cos": cos},
            "lip": 2.0, "about": about,
            "look": {"normals": nm, "mask": mk, "base": B, "hit": hit, "facing": facing}}


def blob_name(feature: str, view_kind: str) -> str:
    """A relief's blob: <feature>_relief_<view>, on the feature's own side; a middle feature's SIDE relief is
    named .L (or .R) so that it is mirrored onto the other side."""
    base, side = (feature[:-2], feature[-2:]) if feature[-2:] in (".L", ".R") else (feature, "")
    if not side and view_kind in ("side", "side_r"):
        side = ".L" if view_kind == "side" else ".R"
    return f"{base}_relief_{view_kind}{side}"


def press(name: str, spec: dict, fm: dict, feature: str, view: str, leave=(), scale: float | None = SCALE,
          across=(), whole: bool = False) -> tuple[dict, dict]:
    """The spec with the relief pressed in (a blob; pressing again replaces it), and what was done."""
    c = fm["features"].get(feature)
    if c is None or c.get("kind") != "mass":
        raise ValueError(f"{feature!r} is not a mass of the map: a relief is pressed into a mass (its forms come with it)")
    if not c.get("built"):
        raise ValueError(f"{feature!r} has no clay yet: build_masses first, a relief is pressed into what stands there")
    got = maps(name, spec, fm, feature, view, leave, scale, across, whole)
    sha = relief.put(got["frame"], got["maps"], got["lip"])
    bname = blob_name(feature, fm["views"][view]["kind"])
    blobs = dict(spec.get("blobs", {}))
    blobs[bname] = {"shape": "relief", "relief": sha, "layer": relief.LAYER}
    got["about"].update(blob=bname, relief=sha)
    return {**spec, "blobs": blobs}, got
