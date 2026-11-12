"""Clay presentation: the hair cap, eyes, brows, lip tint and iris put on the clay, the presented mesh. Part of the block-in (blockin.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import blockin

# ---------------------------------------------------------------- clay presentation
def haircap(mesh: dict, st: dict) -> np.ndarray:
    """Per-vertex colour: skin, and a neutral dark cap over GNM's scalp (outside its hockey_mask face region, not the
    ears, above the ears' bottom): bald clay reads male."""
    from . import onemesh
    from . import likeness
    from . import base_identity
    g = base_identity._gnm_data()
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(st["tpl"]["fid"])]
    ok = gid >= 0
    hm_ = np.zeros(len(gid))
    hm_[ok] = np.asarray(g["groups"]["hockey_mask"], float)[gid[ok]]
    ear = np.zeros(len(gid))
    ear[ok] = np.asarray(g["groups"]["ears"], float)[gid[ok]]
    L = st["L"]
    zcut = 0.5 * (L[1, 2] + L[15, 2])
    w = ok * (1 - hm_) * (1 - ear) * np.clip((mesh["V"][:, 2] - zcut) / 0.01, 0, 1)
    return (1 - w)[:, None] * likeness.SKIN + w[:, None] * blockin.HAIR_RGB


def eye_presentation(mesh: dict, iris=(128, 112, 82)) -> dict:
    """A presentable eye for whole-face reads (dark iris caps dominated every clay read): a light iris with a darker
    limbal ring and pupil, and a lash line (the skin hugging the upper half of each eyeball, darkened)."""
    from . import likeness
    out = []
    fwd = np.asarray(mesh["state"]["head"].get("forward", [0, -1, 0]), float)
    fwd = fwd / np.linalg.norm(fwd)
    for V, F_, _ in mesh["eyes"]:
        c = V.mean(0)
        cs = ((V - c) / np.linalg.norm(V - c, axis=1, keepdims=True)) @ fwd
        col = np.where(cs[:, None] > 0.97, [20, 16, 14], np.where(cs[:, None] > 0.885, list(iris),
                       np.where(cs[:, None] > 0.86, [60, 50, 40], [238, 234, 228]))).astype(float)
        out.append((V, F_, col))
    mesh["eyes"] = out
    C = np.asarray(mesh["C"] if mesh.get("C") is not None else np.tile(likeness.SKIN, (len(mesh["V"]), 1)), float).copy()
    for V, _, _ in out:
        c = V.mean(0)
        r = float(np.median(np.linalg.norm(V - c, axis=1)))
        dist = np.linalg.norm(mesh["V"] - c, axis=1) - r
        near = (dist < 0.0015) & (mesh["V"][:, 2] > c[2] - 0.0005) & ((mesh["V"] - c) @ fwd > 0.3 * r)
        C[near] = C[near] * 0.35
    mesh["C"] = C
    return mesh


def draw_photo_brows(im, P, to):
    """The PERSON's brows on the clay: the photo detector's brow band (upper and lower contour) as a filled shape,
    through `to` (picture pixels -> this image's). A drawn line on GNM's brow landmarks sat low and heavy."""
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    P = np.asarray(P, float)[:, :2]
    for up, lo in (blockin.BROWS_R, blockin.BROWS_L):
        d.polygon([tuple(p) for p in to(np.r_[P[up], P[lo][::-1]])], fill=(70, 52, 40))
    return im


def brow_source(mesh: dict, rj: dict) -> dict | None:
    """The person's brows SEATED ON THE SURFACE (Joe: 2D-pasted brows stuck out past the 3/4 silhouette and hooked over
    the bridge in profile): the front picture's detector brow band as a mask in that picture, plus the model's depth
    seen through the front camera. seat_brows then paints, in ANY view, the skin points that project into the band from
    the front AND are visible from the front: they follow the surface, foreshorten and are occluded like paint. Cached
    on the mesh dict. None when the front picture's detector misses (draw_brows' landmark line is the fallback)."""
    from PIL import Image, ImageDraw, ImageFilter
    from . import humanfit_views
    from . import likeness_render
    if "_brows" in mesh:
        return mesh["_brows"]
    vf = _front(rj)
    v, cam = rj["views"][vf], rj["cameras"][vf]
    img = Image.open(v["image"]).convert("RGB")
    P = detect_view(img, v)
    out = None
    if P is not None:
        P = np.asarray(P, float)[:, :2]
        # the band rasterised SUPERSAMPLED over its own box (a full-figure picture's brows are a few pixels tall:
        # nearest samples of a picture-resolution mask came out as stair steps), sampled bilinearly
        polys = [np.r_[P[up], P[lo][::-1]] for up, lo in (blockin.BROWS_R, blockin.BROWS_L)]
        allp = np.concatenate(polys)
        pad = max(6.0, 0.05 * float(allp[:, 0].max() - allp[:, 0].min()))   # (room for the tails past the band)
        o = allp.min(0) - pad
        ss = 8.0
        size = tuple(int(x) for x in np.ceil((allp.max(0) + pad - o) * ss))
        m = Image.new("L", size, 0)
        d = ImageDraw.Draw(m)
        for poly in polys:
            d.polygon([tuple(q) for q in (poly - o) * ss], fill=255)
        hb = brow_hair_band(img, polys, o, cam, mesh)   # (None for light, fine brows: the detector band, below)
        # the brows' own colour: the picture's pixels under the hair mask (or the band), their darkest quarter (a fair
        # person's light-brown brows painted in the fixed dark brown read as heavy bars)
        Wb, Hb = int(np.ceil(allp.max(0)[0] + pad - o[0])), int(np.ceil(allp.max(0)[1] + pad - o[1]))
        crop = np.asarray(img.crop((int(o[0]), int(o[1]), int(o[0]) + Wb, int(o[1]) + Hb)), float)
        msk = (np.asarray(hb) > 0) if hb is not None else (np.asarray(m.resize((Wb, Hb), Image.BILINEAR)) > 127)
        rgb = blockin.BROW_RGB
        if msk.shape == crop.shape[:2] and msk.sum() > 20:
            px_ = crop[msk]
            lum_ = px_.mean(1)
            rgb = np.median(px_[lum_ <= np.percentile(lum_, 25)], 0)
        if hb is not None:
            m = hb.resize(size, Image.BILINEAR)
        L2 = humanfit_views.project(cam, mesh["state"]["L"])
        c = 0.5 * (L2.min(0) + L2.max(0))
        side = 1.5 * float(np.max(L2.max(0) - L2.min(0)))
        box = (c[0] - side / 2, c[1] - side / 2, c[0] + side / 2, c[1] + side / 2)
        _, k, ps = likeness_render.render(mesh, cam, box, px=1200, brows=False, passes=True)
        mmpx = likeness_render._mm_per_px(cam, mesh["state"]["L"][27:48])
        soft = m.filter(ImageFilter.GaussianBlur(max(0.5 / mmpx, 0.4) * ss))   # (a ~0.5 mm soft edge)
        out = {"cam": cam, "rgb": rgb, "mask": np.asarray(soft, float) / 255.0, "mo": o, "ss": ss, "zb": ps["zb"], "part": ps["part"],
               "box": box, "k": k}
    mesh["_brows"] = out
    return out


def brow_hair_band(img, polys, o, cam, mesh, grow_mm: float = 2.0, dark: float = 0.66, density: bool = True,
                   tail_mm: float = 4.0):
    """The brows as the HAIR the picture shows, not the detector's band: MediaPipe's brow contour is a smooth arch of
    a fixed thickness (straight, dense brows came out thinner and more arched). Inside the detector band grown by
    grow_mm, the pixels darker than `dark` x the surrounding skin; the largest pieces per side kept. A mask over the
    band's own box (origin o, picture pixels) or None when it finds too little. density: the mask is the hair's
    density (its darkness against the skin, 0..1)."""
    from PIL import Image, ImageDraw, ImageFilter
    from scipy import ndimage
    from . import likeness_render
    allp = np.concatenate(polys)
    hi = allp.max(0) + (allp.min(0) - o)   # (the same margin as the caller gave below the band)
    W, H = int(np.ceil(hi[0] - o[0])), int(np.ceil(hi[1] - o[1]))
    if W < 4 or H < 4:
        return None
    mmpx = likeness_render._mm_per_px(cam, mesh["state"]["L"][27:48])
    band = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(band)
    for poly in polys:
        d.polygon([tuple(q) for q in (poly - o)], fill=255)
    g = max(1, int(round(grow_mm / mmpx)))
    crop = np.asarray(img.convert("L").crop((int(o[0]), int(o[1]), int(o[0]) + W, int(o[1]) + H)), float)
    xs = np.arange(W)[None, :]
    keep = np.zeros((H, W), bool)
    skin_lvl = np.full((H, W), float(np.median(crop)))
    inner_all = 0
    for poly in polys:   # per side: its own skin level (one side of a face is often lit brighter)
        q = poly - o
        pm = Image.new("L", (W, H), 0)
        ImageDraw.Draw(pm).polygon([tuple(p_) for p_ in q], fill=255)
        inner = np.asarray(pm) > 0
        grown = np.asarray(pm.filter(ImageFilter.MaxFilter(2 * g + 1))) > 0
        # not past the band's own ends (side hair at the temples is dark too)
        # not past the inner end; past the OUTER end by tail_mm (MediaPipe's brow stops short of the tail: a
        # profile showed a short patch)
        outer_left = q[:, 0].mean() < (allp[:, 0].mean() - o[0])
        lo_, hi_ = (tail_mm, 0.5) if outer_left else (0.5, tail_mm)
        grown &= (xs >= q[:, 0].min() - lo_ / mmpx) & (xs <= q[:, 0].max() + hi_ / mmpx)
        ring = grown & ~inner
        if ring.sum() < 20 or inner.sum() < 20:
            return None
        inner_all += int(inner.sum())
        skin = float(np.percentile(crop[ring], 75))
        skin_lvl[grown] = skin
        hair = ndimage.binary_opening(grown & (crop < dark * skin), iterations=1)
        lab, n = ndimage.label(hair)
        if n == 0:
            continue
        ov = ndimage.sum(inner, lab, index=np.arange(1, n + 1))
        if ov.max() <= 0:
            continue
        for i in np.flatnonzero(ov >= 0.25 * ov.max()):   # the piece(s) overlapping the detector band most
            keep |= lab == i + 1
    if keep.sum() < 0.5 * inner_all:   # too little hair found (light brows, a painting): the detector band
        return None
    keep = ndimage.binary_closing(keep, iterations=2)
    if not density:
        return Image.fromarray((keep * 255).astype(np.uint8))
    # DENSITY, not a flat shape (a binary mask painted at one strength drew the tails as heavy as the dense inner
    # ends): how far each kept pixel is below the skin level, so sparse tails come out light and thin, the dense heads
    # dark
    dens = np.where(keep, np.clip((skin_lvl - crop) / np.maximum(skin_lvl * (1 - 0.35), 1.0), 0, 1), 0.0)
    dens = ndimage.gaussian_filter(dens, 0.6)
    dn = np.clip(dens / max(np.percentile(dens[keep], 98), 1e-3), 0, 1) ** 1.4   # (p90 saturated: one flat band)
    im = Image.fromarray((dn * 255).astype(np.uint8))
    return im


def seat_brows(im, ps, cam, box, k, B: dict, strength: float = 0.9):
    """Paint the seated brows on a render (its passes ps, through cam / box / k): each skin pixel back-projected to
    the surface, seen from the front camera; inside the front band and visible there (depth within 2.5 mm) = brow."""
    from PIL import Image
    from . import likeness_shape as ls
    from . import humanfit_views
    a = np.asarray(im.convert("RGB"), float).copy()
    rr, cc = np.nonzero(ps["part"] == 0)
    if not len(rr):
        return im
    uv = np.c_[cc / k + box[0], rr / k + box[1]]
    X = ls.unproject(cam, uv, ps["zb"][rr, cc])
    from scipy.ndimage import map_coordinates
    q = humanfit_views.project(B["cam"], X)
    qm = (q - B["mo"]) * B["ss"]
    al = map_coordinates(B["mask"], [qm[:, 1], qm[:, 0]], order=1, mode="constant", cval=0.0)
    W, H = B["cam"]["size"]
    ok = (q[:, 0] >= 0) & (q[:, 0] < W) & (q[:, 1] >= 0) & (q[:, 1] < H)
    zi = np.round((q - [B["box"][0], B["box"][1]]) * B["k"]).astype(int)
    zh, zw = B["zb"].shape
    inz = ok & (zi[:, 0] >= 0) & (zi[:, 0] < zw) & (zi[:, 1] >= 0) & (zi[:, 1] < zh)
    Rf = humanfit_views._cam_rot(B["cam"])
    depth = ((X - np.asarray(B["cam"]["centre"], float)) @ Rf.T + np.asarray(B["cam"]["t"], float))[:, 2]
    vis = np.zeros(len(rr), bool)
    vis[inz] = (B["part"][zi[inz, 1], zi[inz, 0]] == 0) & (depth[inz] < B["zb"][zi[inz, 1], zi[inz, 0]] + 0.0025)
    al = al * vis * strength
    a[rr, cc] = a[rr, cc] * (1 - al[:, None]) + np.asarray(B.get("rgb", blockin.BROW_RGB), float) * al[:, None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def brows_on(im, ps, mesh, rj, cam, box, k):
    """The brows on a clay crop: seated from the front picture where it sees them, GNM's landmark line otherwise."""
    B = brow_source(mesh, rj)
    return seat_brows(im, ps, cam, box, k, B) if B is not None else draw_brows(im.convert("RGB"), mesh, cam, box, k)


def draw_brows(im, mesh, cam, box, k, mm: float = 2.0):
    """Brows as a line through the model's brow landmarks (views the detector can't read)."""
    from PIL import ImageDraw
    from . import humanfit_views
    from . import likeness_render
    L = humanfit_views.project(cam, mesh["L"])
    d = ImageDraw.Draw(im)
    wpx = max(1, int(round(mm / likeness_render._mm_per_px(cam, mesh["L"]) * k)))
    for a, b in ((17, 22), (22, 27)):
        d.line([((L[i, 0] - box[0]) * k, (L[i, 1] - box[1]) * k) for i in range(a, b)], fill=(70, 52, 40), width=wpx,
               joint="curve")
    return im


def lip_tint(mesh: dict, st: dict, share: float = 0.8) -> None:
    """The vermilion tinted on the clay (GNM's upper_lip / lower_lip groups): untinted clay lips barely read as lips."""
    from . import onemesh
    from . import base_identity
    g = base_identity._gnm_data()
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(st["tpl"]["fid"])]
    ok = gid >= 0
    w = np.zeros(len(gid))
    for grp in ("upper_lip", "lower_lip"):
        w[ok] = np.maximum(w[ok], np.asarray(g["groups"][grp], float)[gid[ok]])
    C = np.asarray(mesh["C"], float)
    a = (share * np.clip(w, 0, 1))[:, None]
    mesh["C"] = C * (1 - a) + C * blockin.LIP_TINT * a


def photo_iris(rj: dict | None):
    """The person's iris colour from the front picture (MediaPipe's iris ring: the median of the annulus between the
    pupil and the limbus, the brightest tenth (catchlights) left out); None without a front detection."""
    if not rj:
        return None
    from PIL import Image
    vf = _front(rj)
    v = rj["views"][vf]
    key = v["image"]
    if key not in blockin._IRIS:
        img = Image.open(v["image"]).convert("RGB")
        P = detect_view(img, v)
        col = None
        if P is not None and len(P) >= 478:
            P = np.asarray(P, float)[:, :2]
            a = np.asarray(img, float)
            px = []
            for c_, ring in ((468, range(469, 473)), (473, range(474, 478))):
                c = P[c_]
                r = float(np.mean([np.linalg.norm(P[i] - c) for i in ring]))
                yy, xx = np.mgrid[int(c[1] - r):int(c[1] + r) + 1, int(c[0] - r):int(c[0] + r) + 1]
                d = np.hypot(xx - c[0], yy - c[1])
                m = (d > 0.45 * r) & (d < 0.85 * r)
                px.append(a[yy[m], xx[m]])
            q = np.concatenate(px)
            lum = q.mean(1)
            q = q[lum <= np.percentile(lum, 90)]
            col = tuple(float(x) for x in np.median(q, 0))
        blockin._IRIS[key] = col
    return blockin._IRIS[key]


def presented_mesh(base: dict, eyes: bool = True, rj: dict | None = None) -> dict:
    """The clay as presented for whole-face reads: hair cap, tinted lips, a presentable eye (the person's iris colour
    from the front picture when rj is given)."""
    from . import humanfit
    from . import likeness_render
    st = humanfit.state(base)
    mesh = likeness_render.model_mesh_from_state(st)
    mesh["C"] = haircap(mesh, st)
    lip_tint(mesh, st)
    if eyes:
        ir = photo_iris(rj)
        eye_presentation(mesh, iris=ir) if ir else eye_presentation(mesh)
    return mesh


def detect_view(img, view: dict):
    """MediaPipe on a reference picture; where the face is small in a big picture (a full-figure concept), on a crop
    around the clicked points."""
    from . import likeness_detect
    P = likeness_detect.detect([img])[0]
    if P is not None:
        return P
    pts = np.array([p for p in (view.get("points") or {}).values()], float)
    if len(pts) < 3:
        return None
    lo, hi = pts.min(0), pts.max(0)
    c, s = 0.5 * (lo + hi), 1.8 * float(np.max(hi - lo))
    return likeness_detect.detect_region(img, (c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2))


def _front(rj: dict) -> int:
    ys = [abs(float(v.get("yaw", 0))) for v in rj["views"]]
    return int(np.argmin(ys))
