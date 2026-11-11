"""The reads: lips, freckles, brows, irises, and `read` with its text. Part of the skin read (skin_read.py has the overview)."""
from __future__ import annotations

import copy

import numpy as np

from .skin_read import CLIP, N, _lin, _srgb, lab
from .skin_read_context import Context, MIN_PX, SCLERA_PX, _eye_classes, _region, _wmedian, context, regions
from .skin_read_fold_fit import fold_text
from .skin_read_folds import fold_read

# ---------------------------------------------------------------- lips: in image space, at the picture's own lips
LIP_YAW = 50.0          # deg: views turned further do not give the detector's lip outline


_MP_LIPS = {"outer_up": [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291], "outer_lo": [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291],
            "inner_up": [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308], "inner_lo": [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308]}


def lip_polygons(P) -> dict:
    """{"lip_upper", "lip_lower": (n, 2) polygons} of a picture's own lips from its detector points: MediaPipe's face
    mesh (468+ points: its own lip contours) or the 68 landmarks (outer contour 48-59, inner 60-67)."""
    P = np.asarray(P, float)[:, :2]
    if len(P) >= 468:
        m = _MP_LIPS
        return {"lip_upper": np.r_[P[m["outer_up"]], P[m["inner_up"][::-1]]], "lip_lower": np.r_[P[m["outer_lo"]], P[m["inner_lo"][::-1]]]}
    return {"lip_upper": np.r_[P[48:55], P[64:59:-1]], "lip_lower": np.r_[P[54:60], P[48:49], P[60:61], P[67:63:-1]]}


def _lip_read(c: Context) -> dict:
    """The lips' colour IN IMAGE SPACE, like with like (skinfolds2): the picture's pixels inside ITS OWN lip outline
    (the detector's, a pixel in from the edge) against our render's pixels inside OUR lips, both under the fitted
    light, the picture levelled to our exposure on the plain skin: {region: {"d": Lab picture - ours, "picture",
    "ours", "px", "by_view"}}. Why not the albedo ratio at our lips' pixels: a mouth's shape is never the picture's
    to the millimetre, and where our (fuller) lip lies over the picture's skin the read mixed her upper lip with the
    skin over it: lighter and yellower than her lip (Tess: "orange-brown" for a brown-mauve lip). The rendered lip is
    in the loop by construction: a second round reads what the first one's parameters render as."""
    from PIL import Image, ImageDraw
    from scipy import ndimage
    from . import blockin
    out = {}
    try:
        rj = blockin._refs(c.name)
    except Exception:  # noqa: BLE001
        return out
    R = regions(c)
    acc = {"lip_upper": [], "lip_lower": []}
    for f, v in zip(c.frames, c.views):
        # (and only the views whose light is as white as the best one's: a lamp-lit painting's lips, levelled on its
        # skin, read 10 Lab from the front view's; their spread made the lips' sigma so wide that nothing moved)
        if abs(f.get("yaw", 0.0)) > LIP_YAW or "R" not in f or v["weight"] < 0.7 * max(v_["weight"] for v_ in c.views):
            continue
        try:
            P = blockin.detect_view(Image.open(f["image"]).convert("RGB"), rj["views"][f["view"]])
        except Exception:  # noqa: BLE001
            P = None
        if P is None:
            continue
        k = N / (f["box"][2] - f["box"][0])
        g = np.asarray(v["gain"], float)
        m = c.view == f["view"]
        for key, poly in lip_polygons(P).items():
            im = Image.new("L", (N, N), 0)
            ImageDraw.Draw(im).polygon([tuple((np.asarray(q_) - np.asarray(f["box"][:2])) * k) for q_ in poly], fill=255)
            pm = ndimage.binary_erosion(np.asarray(im) > 127, iterations=1)
            ps_ = _srgb(f["P"])
            pm &= (ps_.max(-1) < CLIP[1]) & (ps_.min(-1) > CLIP[0])
            ours = np.zeros(N * N)
            ours[c.pix[m]] = R[key][m]
            om = (ours.reshape(N, N) > 0.5) & (f["alpha"] > 0.98)
            if pm.sum() < MIN_PX or om.sum() < MIN_PX:
                continue
            lp, lo = lab(np.median(f["P"][pm], 0) / g), lab(np.median(f["R"][om], 0))
            acc[key].append((v["weight"] * min(pm.sum(), om.sum()), lp, lo, f["view"], int(pm.sum())))
    for key, rows in acc.items():
        if not rows:
            continue
        w = np.array([r_[0] for r_ in rows])
        lp, lo = np.average([r_[1] for r_ in rows], 0, w), np.average([r_[2] for r_ in rows], 0, w)
        out[key] = {"d": [round(float(x), 2) for x in lp - lo], "picture": [round(float(x), 1) for x in lp], "ours": [round(float(x), 1) for x in lo],
                    "px": int(sum(r_[4] for r_ in rows)), "by_view": {r_[3]: [round(float(x), 2) for x in r_[1] - r_[2]] for r_ in rows}}
    return out


# ---------------------------------------------------------------- fine marks: freckles (image space, per view)
SPECK = (0.35, 1.3)     # mm: the band (two Gaussian sigmas) a freckle lives in
SPECK_T = 0.035         # a speck is this much darker (log luminance) than its surround in that band
SPECK_MM = 0.5          # mm a pixel: coarser pictures cannot show freckles (NOT READ)
SPECK_SIZE = (0.4, 12.0)  # mm2: a speck's area


def _specks(lum: np.ndarray, where: np.ndarray, mm: float) -> float:
    """Dark specks per cm2 of `where` in a luminance image (mm a pixel): connected blobs of the band-passed log
    luminance under -SPECK_T with a freckle's area."""
    from scipy import ndimage
    lg = np.log(np.maximum(lum, 1e-3))
    wf = where.astype(float)
    def blur(s):
        return ndimage.gaussian_filter(lg * wf, s) / np.maximum(ndimage.gaussian_filter(wf, s), 1e-3)
    bp = blur(SPECK[0] / mm) - blur(SPECK[1] / mm)
    inner = ndimage.binary_erosion(where, iterations=max(int(round(1.5 / mm)), 1))
    lab_, n = ndimage.label((bp < -SPECK_T) & inner)
    if not n or inner.sum() < 200:
        return 0.0
    area = ndimage.sum(np.ones_like(lab_), lab_, np.arange(1, n + 1)) * mm * mm
    return float(((area >= SPECK_SIZE[0]) & (area <= SPECK_SIZE[1])).sum() / (inner.sum() * mm * mm / 100.0))


def _freckle_read(c: Context) -> dict:
    """Freckles: dark specks per cm2 on cheeks, nose and forehead, the picture against our render (same camera and
    light), and the same count on our albedo with and without the freckle layer (what one unit of amount gives)."""
    Yv = np.array([0.2126, 0.7152, 0.0722])
    zone = np.max([c.alb.zone(z) for z in ("cheek", "cheekbone", "nose_bridge", "nose_tip", "forehead")], 0) > 0.5
    sk = copy.deepcopy(c.st.get("skin") or {})
    fr = (sk.get("features") or {}).get("freckles")
    have = float(fr if isinstance(fr, (int, float)) else (fr or {}).get("amount", 1.0 if fr else 0.0)) if fr else 0.0
    proto = have if have > 0.02 else 0.3
    with_ = copy.deepcopy(sk)
    with_.setdefault("features", {})
    if have <= 0.02:
        with_["features"]["freckles"] = {"amount": proto}
    without = copy.deepcopy(sk)
    (without.get("features") or {}).pop("freckles", None)
    A1, A0 = c.alb(with_), c.alb(without)
    out = {"have": round(have, 3), "views": {}, "read": False}
    num = den = 0.0
    for f, v in zip(c.frames, c.views):
        if f.get("mm_native", f["mm"]) > SPECK_MM:
            out["views"][f["view"]] = f"NOT READ ({f.get('mm_native', f['mm']):.2f} mm a pixel: freckles need {SPECK_MM} or finer)"
            continue
        m = c.view == f["view"]
        w2 = np.zeros(N * N, bool)
        w2[c.pix[m]] = zone[m] & (c.w[m] > 0)
        w2 = w2.reshape(N, N)
        if w2.sum() < 2000:
            continue
        def img(a, m=m):
            q = np.zeros(N * N)
            q[c.pix[m]] = a[m] @ Yv
            return q.reshape(N, N)
        sp, sr_, s1, s0 = _specks(f["P"] @ Yv, w2, f["mm"]), _specks(f["R"] @ Yv, w2, f["mm"]), _specks(img(A1), w2, f["mm"]), _specks(img(A0), w2, f["mm"])
        out["views"][f["view"]] = {"picture": round(sp, 2), "ours": round(sr_, 2), "albedo_with": round(s1, 2), "albedo_without": round(s0, 2)}
        if s1 - s0 > 0.3:
            ours_fr = sr_ if have > 0.02 else sr_ + (s1 - s0)   # the render's count had it the prototype's freckles
            num += v["weight"] * (proto * (sp - (ours_fr - (s1 - s0))) / (s1 - s0))
            den += v["weight"]
    if den > 0:
        out.update(read=True, amount=round(float(np.clip(num / den, 0, 2)), 3), proto=proto)
    return out


# ---------------------------------------------------------------- brows, irises
def _brow_read(c: Context) -> dict:
    """Brow hair from the picture's albedo: its colour (the darkest third of the band) and how much of it there is
    (the band's mean darkness under the skin above it), each against ours."""
    Yv = np.array([0.2126, 0.7152, 0.0722])
    band = c.alb.zone("brow", 1.7)
    wide = c.alb.zone("brow", 3.2)
    W = c.w * (band > 0.5)
    ring = c.w * ((wide > 0.05) & (band < 0.2)) * (c.X[:, 2] > np.median(c.X[band > 0.5][:, 2]) if (band > 0.5).any() else 0)
    if W.sum() < MIN_PX or ring.sum() < MIN_PX:
        return {"read": False, "why": "the brows are not in trusted skin (hair over them, turned away)"}
    out = {"read": True, "px": round(float(W.sum()), 0)}
    res = {}
    for key, col in (("picture", c.T), ("ours", c.A0)):
        lum = col @ Yv
        skin_c = _wmedian(col[ring > 0], ring[ring > 0])
        sel = W > 0
        thr = np.quantile(lum[sel], 0.33)
        dk = sel & (lum <= thr)
        dark_c = _wmedian(col[dk], W[dk])
        dness = float(((np.clip(1 - lum[sel] / max(skin_c @ Yv, 1e-4), 0, 1)) * W[sel]).sum() / W[sel].sum())
        res[key] = {"skin": skin_c, "dark": dark_c, "darkness": dness}
        out[key] = {"dark_Lab": [round(float(x), 1) for x in lab(dark_c)], "darkness": round(dness, 3)}
    out["colour_ratio"] = [round(float(x), 3) for x in np.clip(res["picture"]["dark"] / np.maximum(res["ours"]["dark"], 1e-4), 0.3, 3.0)]
    ko = 1 - (res["ours"]["dark"] @ Yv) / max(res["ours"]["skin"] @ Yv, 1e-4)
    kp = 1 - (res["picture"]["dark"] @ Yv) / max(res["picture"]["skin"] @ Yv, 1e-4)
    out["coverage_ratio"] = round(float(np.clip((res["picture"]["darkness"] / max(res["ours"]["darkness"], 1e-3)) / max(kp / max(ko, 1e-3), 0.2), 0.3, 3.0)), 3)
    return out


def _eye_read(c: Context) -> dict:
    """Iris and sclera colour: the picture against our render through the same camera, each relative to the plain
    skin beside it (so the exposure cancels; a lid's shadow on the picture's eye does not: INFERRED)."""
    out = {}
    for cls, i in (("sclera", 0), ("iris", 1)):
        rs, n = [], 0
        for f, v in zip(c.frames, c.views):
            m = _eye_classes(f, c.mesh, c.spec)[i] & (f["alpha"] > 0.98) & (_srgb(f["P"]).max(-1) < CLIP[1]) & (_srgb(f["R"]).max(-1) < CLIP[1])
            if m.sum() < (SCLERA_PX if cls == "sclera" else SCLERA_PX // 2):
                continue
            rs.append(np.median(f["P"][m], 0) / np.maximum(np.median(f["R"][m], 0), 1e-4) / np.asarray(v["gain"]))
            n += int(m.sum())
        out[cls] = {"read": bool(rs), "px": n, **({"ratio": [round(float(x), 3) for x in np.median(rs, 0)]} if rs else {})}
    return out


def _iris_rel(name: str, c: Context) -> dict:
    """THE IRIS AGAINST THE SCLERA BESIDE IT, picture over ours (readmix, 2026-10-13): what sets skin.eyes.iris.
    PICTURE: at the picture's OWN iris (blockin_eyes.limbus: the limbus circle found on the picture; the ring's colour
    along rays in the two lateral sectors, where no lid covers it) and the sclera just outside the limbus on the same
    rays, its BRIGHT part (a picture's sclera lies half under lid and lash shadow: Tess's front reads luminance 0.08 /
    0.16 / 0.25 at its 20 / 50 / 80 %). OURS: the render's eyeball pixels by the model's own geometry. Both tried and
    wrong on Tess: the model's geometry on the PICTURE (its eye opening is not the picture's: lid skin in the ring, a warm
    cast: the iris came out orange-brown whatever the start), and the sclera's median (in shadow: the iris too light).
    Views turned past 50 deg or with an iris under IRIS_R_PX of radius are left out. -> {"read", "ratio" (linear, per
    channel), "views", "px"}."""
    from PIL import Image
    from . import blockin, blockin_eyes as be, lidfold
    from .likeness_eyes import frame
    rj = blockin._refs(name)
    rel, npx = [], 0
    for f in c.frames:
        vi = int(f["view"])
        v = rj["views"][vi]
        if abs(float(v.get("yaw", 0.0) or 0.0)) > 50.0:
            continue
        scl, iris = _eye_classes(f, c.mesh, c.spec)
        ok = (f["alpha"] > 0.98) & (_srgb(f["R"]).max(-1) < CLIP[1])
        scl, iris = scl & ok, iris & ok
        if iris.sum() < SCLERA_PX // 2 or scl.sum() < SCLERA_PX:
            continue
        ours = np.median(f["R"][iris], 0) / np.maximum(np.median(f["R"][scl], 0), 1e-4)
        try:
            img = Image.open(v["image"]).convert("RGB")
            P = blockin.detect_view(img, v)
            if P is None:
                continue
            lb = be.limbus(img, P)
        except Exception:  # noqa: BLE001
            continue
        A = _lin(np.asarray(img, float) / 255.0)
        H, W = A.shape[:2]
        ex, ey = (np.asarray(x_, float) for x_ in frame(np.asarray(P, float)[:, :2]))
        for e in lb:
            r, cen = float(e["r_px"]), np.asarray(e["centre"], float)
            if r < IRIS_R_PX:
                continue
            ring, white = [], []
            for sg in (-1, 1):
                for a in np.radians(np.arange(-30, 31, 5)):
                    d = sg * (np.cos(a) * ex + np.sin(a) * ey)
                    for q, dst in [(q_, ring) for q_ in np.linspace(0.5, 0.85, 8)] + [(q_, white) for q_ in np.linspace(1.15, 1.7, 10)]:
                        p_ = cen + q * r * d
                        dst.append(A[int(np.clip(round(p_[1]), 0, H - 1)), int(np.clip(round(p_[0]), 0, W - 1))])
            ring, white = np.array(ring), np.array(white)
            lr, lw = ring.mean(1), white.mean(1)
            ring = np.median(ring[(lr <= np.percentile(lr, 80)) & (lr >= np.percentile(lr, 10))], 0)
            white = np.median(white[lw >= np.percentile(lw, 80)], 0)
            if white.mean() < 1.6 * ring.mean():      # no sclera beside this iris (a turned eye's far side, lashes): not a reference
                continue
            rel.append((r * r, (ring / np.maximum(white, 1e-4)) / np.maximum(ours, 1e-4)))
            npx += int(r * r)
    if not rel:
        return {"read": False, "px": 0, "views": 0}
    w = np.array([n_ for n_, _ in rel], float)
    return {"read": True, "px": npx, "views": len(rel),
            "ratio": [round(float(x), 3) for x in np.exp((w[:, None] * np.log(np.maximum(np.array([r_ for _, r_ in rel]), 1e-4))).sum(0) / w.sum())]}


IRIS_R_PX = 10.0          # an iris under this radius (picture px) is not read for colour
IRIS_STEP = (0.2, 5.0)    # the most one read changes the iris' lightness (x); its hue is never clipped per channel
IRIS_Y = (0.012, 0.42)    # linear luminance an iris colour may have (near-black brown .. pale grey-blue)


def iris_colour(c0, ratio) -> str:
    """skin.eyes.iris from the read: the colour now (c0: sRGB 0..1) x the picture's (iris / bright sclera) over ours
    (ratio, linear, per channel). The CHANGE's size is limited as a whole (IRIS_STEP on its luminance) and the result's
    luminance kept in IRIS_Y; the channels keep their proportions. (The old rule clipped each channel to 0.5 .. 2: from
    the default brown a grey-green iris needs x1.5 / x4.5 / x11, which the clip turned into orange-brown.)"""
    lumw = np.array([0.2126, 0.7152, 0.0722])
    l0 = _lin(np.asarray(c0, float)[:3])
    want = l0 * np.asarray(ratio, float)
    y0, y1 = float(l0 @ lumw), float(want @ lumw)
    k = float(np.clip(y1 / max(y0, 1e-6), *IRIS_STEP)) * y0 / max(y1, 1e-6)
    want = want * k
    y = float(want @ lumw)
    want = want * (float(np.clip(y, *IRIS_Y)) / max(y, 1e-6))
    if want.max() > 1.0:
        want = want / want.max()
    return "#" + "".join(f"{int(round(255 * float(x))):02x}" for x in np.clip(_srgb(np.clip(want, 0, 1)), 0, 1))


# ---------------------------------------------------------------- the read
def read(name: str, spec: dict | None = None, frames: list | None = None, anchor: str = "auto", log=print, ctx: Context | None = None,
         white=None) -> dict:
    """The measurements: {"anchor", "views", "regions": {region: {"px", "ours" Lab, "picture" Lab, "d", "by_view"}},
    "freckles", "brows", "eyes", "text", "ctx" (the Context, for `fit`)}."""
    c = ctx or context(name, spec, frames, anchor, log, white=white)
    R = regions(c)
    out = {"anchor": {k: v for k, v in c.anchor.items() if k != "gain"}, "views": c.views,
           "regions": {k: _region(c, wz) for k, wz in R.items()}}
    # the lips: in image space at the picture's own lips (the albedo-ratio read at OUR lips' pixels kept beside it)
    out["lips_image"] = _lip_read(c)
    for key, q in out["lips_image"].items():
        r0 = out["regions"].get(key)
        if r0 and r0.get("read"):
            r0["d_albedo"] = r0["d"]
            r0["d"] = q["d"]
            r0["by_view"] = q["by_view"]
            r0["image"] = {"picture": q["picture"], "ours": q["ours"]}
    out["freckles"] = _freckle_read(c)
    out["brows"] = _brow_read(c)
    atlas = bool(c.frames and c.frames[0].get("atlas"))
    # (from the atlas: no eyeball render and no lit render: the irises are skin_project's read, the folds Stage 2's forms)
    if atlas:
        out["eyes"] = {"sclera": {"read": False, "px": 0}, "iris": {"read": False, "px": 0}}
    else:
        out["eyes"] = _eye_read(c)
        try:
            out["eyes"]["iris_rel"] = _iris_rel(name, c)
        except Exception as e_:  # noqa: BLE001
            out["eyes"]["iris_rel"] = {"read": False, "px": 0, "views": 0, "why": str(e_)[:120]}
    out["folds"] = {} if atlas else fold_read(c)
    out["source"] = "atlas" if atlas else "pictures"
    out["ctx"] = c
    out["text"] = read_text(out)
    return out


def read_text(r: dict) -> str:
    L = [f"SKIN READ (the picture's albedo against ours, CIE Lab; d = picture - ours; anchor: {r['anchor']['kind']})",
         "  " + r["anchor"]["note"]]
    for v in r["views"]:
        L.append(f"  view {v['view']}: {v['mm_per_px']} mm a pixel, {v['trusted_px']} trusted px, weight {v['weight']}"
                 + (f", the picture is exposed {v['ev']:+.2f} EV from our render under its fitted light" if "ev" in v else "")
                 + (f" (the light changes colour across the face: {v['light_spread']})" if v["weight"] < 0.6 else ""))
    L.append(f"  (mm a pixel: the PICTURE's own, at the face) {'region':16s} {'px':>7s}  {'ours L a b':20s} {'picture L a b':20s} d L a b")
    for k, x in r["regions"].items():
        L.append(f"  {k:16s} {x['px']:7.0f}  " + (f"{str(x['ours']):20s} {str(x['picture']):20s} {x['d']}" if x["read"] else "NOT READ")
                 + (f"   <- d in IMAGE SPACE at the picture's own lips: rendered {x['image']['ours']} vs the picture's {x['image']['picture']} "
                    f"(the albedo ratio at our lips' pixels said {x['d_albedo']})" if x.get("image") else ""))
    fr = r["freckles"]
    L.append("  freckles: " + (f"picture asks amount {fr['amount']} (ours {fr['have']})" if fr["read"] else "NOT READ") + f"; specks / cm2 by view: {fr['views']}")
    b = r["brows"]
    L.append("  brows: " + (f"hair colour x {b['colour_ratio']} (picture {b['picture']['dark_Lab']}, ours {b['ours']['dark_Lab']}), coverage x {b['coverage_ratio']}"
                             if b["read"] else f"NOT READ ({b.get('why')})"))
    for k, e in r["eyes"].items():
        L.append(f"  {k}: " + (f"picture / ours {e['ratio']} against the skin ({e['px']} px)" if e["read"] else "NOT READ (too few pixels)"))
    e = r["regions"].get("eyelid") or {}
    if e.get("read") and e["d"][0] < -8:
        L.append(f"  NOTE the upper lids read {-e['d'][0]:.0f} L darker in the pictures than ours under the same light: mostly SHADE our head "
                 "does not cast (a deeper-set eye, brow overhang, lashes) or lid pigment / make-up; the fit gives it to the "
                 "eyelids / periorbital tints only up to their bounds. The rest is geometry (eye depth, hooding), not skin.")
    if r.get("folds"):
        L.append(fold_text(r["folds"]))
    return "\n".join(L)
