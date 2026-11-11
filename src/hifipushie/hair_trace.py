"""Hair from a traced reference: the front edge and flow, outline regions, the trace overlay and image,
from_trace. Part of hair (hair.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import store
from . import hair_head, hair_reference
from .hair import HairError
from .hair_card_fit import reference_image
from .hair_drawn import top_to_azel
from .hair_groom import envelope, groom_params, hairline
from .hair_head import Scalp
from .hair_reference import _dense, _to_crop, model_lines, project_ref, ray_onto, ref_camera, ref_trace

def front_edge(cam: dict, tr: dict, mask, mm_px: float, owners=None) -> dict | None:
    """The hair's edge against the skin along the traced hairline, measured on the matched id pass: at each point of
    the traced line (every 1.5 mm) the outermost hair pixel along the line's normal (within EDGE_REACH). Its
    roughness is the edge minus itself smoothed along the line (EDGE_SMOOTH): `rough_mm` (rms) and `tooth_mm` (the
    worst tip or notch) read as a jagged, torn hairline past ~1 / ~3 mm (the reference's line is one clean sweep);
    `turn_deg_cm` = how much the edge turns per cm beyond its smoothed sweep (zigzag). `off_mm` = ours minus the
    trace on average (+: our edge sits further out onto the skin), `holes` = the share of the band 1-6 mm inside our
    edge that shows skin (a torn edge: tips with skin between them)."""
    from scipy.ndimage import gaussian_filter1d, map_coordinates, median_filter
    if not tr.get("hairline") or mask is None:
        return None
    Wm = mask.shape[0]
    x0, y0, x1, y1 = cam["crop"]
    px_mm = (Wm / max(x1 - x0, y1 - y0)) / mm_px  # mask px per mm
    L = _to_crop(cam, _dense(tr["hairline"], 1.0), Wm)
    if len(L) < 8:
        return None
    c = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(L, axis=0), axis=1))]
    t = np.arange(0, c[-1], 1.5 * px_mm)
    L = np.stack([np.interp(t, c, L[:, k]) for k in range(2)], 1)
    tg = np.gradient(gaussian_filter1d(L, 3, axis=0, mode="nearest"), axis=0)
    tg /= np.maximum(np.linalg.norm(tg, axis=1, keepdims=True), 1e-9)
    nrm = np.stack([tg[:, 1], -tg[:, 0]], 1)
    if tr.get("landmarks"):  # outward = onto the skin: toward the face's landmarks (the U's inside)
        face = _to_crop(cam, list(tr["landmarks"].values()), Wm).mean(0)
        if np.mean(((face - L) * nrm).sum(1)) < 0:
            nrm = -nrm
    reach = hair_reference.EDGE_REACH * 1000 * px_mm
    s = np.arange(-reach, reach + 1e-9, 0.5)
    S = L[:, None, :] + s[None, :, None] * nrm[:, None, :]  # (n, k, [x, y])
    hv = map_coordinates(mask.astype(float), [S[..., 1].ravel(), S[..., 0].ravel()], order=1, mode="constant",
                         cval=0.0).reshape(S.shape[:2]) > 0.5
    have = hv.any(1) & hv[:, 0]  # the line's inside must be hair (else the part or a gap crosses it)
    if have.sum() < 8:
        return None
    last = np.where(hv.any(1), len(s) - 1 - np.argmax(hv[:, ::-1], 1), 0)
    e = s[last] / px_mm  # mm out from the traced line
    k = np.nonzero(have)[0]
    e, tt = e[k], t[k] / px_mm
    # the sweep: a running median then a light Gaussian (a median keeps the temple's corners, which are design, and
    # drops tips and notches narrower than EDGE_SMOOTH: a Gaussian alone counted every corner as roughness)
    sm = gaussian_filter1d(median_filter(e, size=2 * int(hair_reference.EDGE_SMOOTH * 1000 / 1.5) + 1, mode="nearest"), 1.0,
                           mode="nearest")
    r = e - sm
    turn = np.abs(np.diff(np.arctan2(np.diff(e), np.diff(tt)) - np.arctan2(np.diff(sm), np.diff(tt))))
    inner = []
    for i in k:  # holes: skin in the band 1..6 mm inside our edge
        sel = (s >= s[last[i]] - 6 * px_mm) & (s <= s[last[i]] - px_mm)
        inner.append(1.0 - hv[i, sel].mean() if sel.any() else 0.0)
    E = L[k] + (e * px_mm)[:, None] * nrm[k]  # the measured edge in mask px
    front_edge.last = E
    out = {"rough_mm": round(float(np.sqrt(np.mean(r ** 2))), 2), "tooth_mm": round(float(np.abs(r).max()), 1),
           "turn_deg_cm": round(float(np.degrees(turn.sum()) / max(tt[-1] - tt[0], 1e-9) * 10), 1),
           "off_mm": round(float(e.mean()), 1), "holes": round(float(np.mean(inner)), 3)}
    if owners is not None:  # which lock makes each tooth: the hair vertex nearest the camera at that edge pixel
        P, ids, names = owners
        R_, t_, ctr = np.array(cam["R"]), np.array(cam["t"]), np.array(cam["ctr"])
        depth = ((np.asarray(P, float) - ctr) @ R_.T + t_)[:, 2]
        uv = _to_crop(cam, project_ref(cam, P), Wm)
        teeth = {}
        for i in np.argsort(-np.abs(r)):
            if abs(r[i]) < 2.0 or len(teeth) >= 6:
                break
            near = np.nonzero(np.linalg.norm(uv - E[i], axis=1) < 1.5 * px_mm)[0]
            if not len(near):
                continue
            who = str(names[ids[near[np.argmin(depth[near])]]])
            if who not in teeth:
                teeth[who] = round(float(r[i]), 1)  # + a tip hanging out, - a notch
        out["teeth"] = teeth
    return out


FLOW_BAND = (0.004, 0.028)  # m inside the traced hairline: the band whose strand direction front_flow compares


FLOW_BINS = 6


def _orientation(img, sigma: float):
    """Per pixel the strand direction (deg, image axes, y down; axial: mod 180) and its coherence 0..1 from the
    structure tensor of the luminance (strands run across the strongest gradient)."""
    from scipy.ndimage import gaussian_filter, sobel
    A = np.asarray(img.convert("L"), float)
    gx, gy = sobel(A, 1), sobel(A, 0)
    Jxx, Jyy, Jxy = (gaussian_filter(v, sigma) for v in (gx * gx, gy * gy, gx * gy))
    ang = 0.5 * np.degrees(np.arctan2(2 * Jxy, Jxx - Jyy)) + 90.0
    coh = np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2) / (Jxx + Jyy + 1e-9)
    return ang, coh


def front_flow(cam: dict, tr: dict, ref_img, our_img, mask, mm_px: float) -> dict | None:
    """Which way the strands run in the band just inside the hairline (FLOW_BAND), the reference against our render
    in the same camera, read off the images themselves (structure tensor: grooves, sheen and lock edges). Per bin
    along the traced hairline (from its first traced point to its last), the strands' angle to the hairline (deg,
    axial: 0 = along the hairline, a headband; +-90 = straight out of it), the reference's and ours.
    {"bins": [[ref, ours], ...], "err_deg": mean |ref - ours|}."""
    if not tr.get("hairline") or mask is None:
        return None
    from scipy.ndimage import gaussian_filter1d
    W = mask.shape[0]
    x0, y0, x1, y1 = cam["crop"]
    px_mm = (W / max(x1 - x0, y1 - y0)) / mm_px
    ref = ref_img.resize((W, W))
    our = our_img.resize((W, W))
    sig = 1.5 * px_mm
    ra, rc = _orientation(ref, sig)
    oa, oc = _orientation(our, sig)
    L = _to_crop(cam, _dense(tr["hairline"], 1.0), W)
    c = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(L, axis=0), axis=1))]
    t = np.arange(0, c[-1], 1.0 * px_mm)
    L = np.stack([np.interp(t, c, L[:, k]) for k in range(2)], 1)
    tg = np.gradient(gaussian_filter1d(L, 4, axis=0, mode="nearest"), axis=0)
    tg /= np.maximum(np.linalg.norm(tg, axis=1, keepdims=True), 1e-9)
    nrm = np.stack([tg[:, 1], -tg[:, 0]], 1)
    if tr.get("landmarks"):  # inward = into the hair: away from the face
        face = _to_crop(cam, list(tr["landmarks"].values()), W).mean(0)
        if np.mean(((face - L) * nrm).sum(1)) > 0:
            nrm = -nrm
    line_ang = np.degrees(np.arctan2(tg[:, 1], tg[:, 0]))
    bins = []
    edges = np.linspace(0, len(L), FLOW_BINS + 1).astype(int)
    for b in range(FLOW_BINS):
        rs, os_ = [], []
        for i in range(edges[b], edges[b + 1]):
            for dmm in np.linspace(FLOW_BAND[0] * 1000, FLOW_BAND[1] * 1000, 7):
                x, y = L[i] + dmm * px_mm * nrm[i]
                xi, yi = int(round(x)), int(round(y))
                if not (0 <= xi < W and 0 <= yi < W) or not mask[yi, xi]:
                    continue
                for A_, C_, acc in ((ra, rc, rs), (oa, oc, os_)):
                    rel = np.radians(2 * (A_[yi, xi] - line_ang[i]))
                    acc.append((C_[yi, xi] * np.cos(rel), C_[yi, xi] * np.sin(rel)))
        if len(rs) < 5:
            bins.append(None)
            continue

        def mean_ang(v):
            s = np.sum(v, 0)
            return float((0.5 * np.degrees(np.arctan2(s[1], s[0])) + 90) % 180 - 90)
        bins.append([round(mean_ang(rs)), round(mean_ang(os_))])
    good = [b for b in bins if b]
    if not good:
        return None
    err = [abs((b[0] - b[1] + 90) % 180 - 90) for b in good]
    return {"bins": bins, "err_deg": round(float(np.mean(err)), 1)}


REGION_NAMES = ("front", "top", "side.L", "side.R", "back.L", "back.R", "back")


def region_of(az, el):
    """The head region a point on the hair is in, by where it sits round the centre: top (el >= 55), else front
    (within 45 deg of the face), side (45-110 deg round: his left .L is az > 0), back.L / back.R (110-160), back."""
    fa = np.abs(((np.asarray(az, float) + 180) % 360) - 180)
    lr = np.where(((np.asarray(az, float) + 180) % 360) - 180 > 0, ".L", ".R")
    reg = np.where(fa < 45, "front", np.where(fa < 110, "side", np.where(fa < 160, "back", "back_")))
    reg = np.where(reg == "back_", "back", np.char.add(reg, np.where(reg == "front", "", lr)))
    return np.where(np.asarray(el) >= 55, "top", reg)


OUTLINE_STEP = 3.0  # deg: the matched view's outline is sampled on rays from the head centre this far apart


def outline_regions(sc: Scalp, cam: dict, spec: dict, R, M, tr: dict, mm_px: float):
    """The hair outline in a matched view per head region, in mm at the head's depth. Rays from the head centre's
    image every OUTLINE_STEP deg (above clip_y); on each: the reference outline (outermost traced hair), ours
    (outermost hair in the id pass) and the bare head's (the scalp without hair, projected). Each ray is labelled by
    the region (`region_of`) of the groom volume's point that makes the outline there. Per region:
    "err" = ours - reference (mean over its rays; + = ours sticks out further), "worst" (signed, largest |err|),
    "ref_hair" / "our_hair" = how far each outline stands outside the bare head (the hair's thickness the view
    shows: negative ref_hair = the bare head is already outside the reference there, which hair can't fix),
    "rays". Also the hair's top over the brows (mm along the image's vertical, between the brows): [reference, ours]."""
    g = groom_params(spec)
    line = hairline(sc, g)
    Wm = R.shape[0]
    c = _to_crop(cam, project_ref(cam, sc.C[None])[0][None], Wm)[0]
    AA, EE = np.meshgrid(np.arange(0.0, 360.0, 2.0), np.arange(-40.0, 90.0, 1.5), indexing="ij")
    Hh, d_in = envelope(sc, g, line, AA, EE)
    hair = d_in > 0

    def polar(P):
        q = _to_crop(cam, project_ref(cam, P), Wm) - c
        return np.degrees(np.arctan2(q[..., 0], -q[..., 1])) % 360, np.hypot(q[..., 0], q[..., 1])
    th_v, r_v = polar(sc.point(AA, EE, Hh)[hair])
    th_s, r_s = polar(sc.point(AA, EE, 0.0).reshape(-1, 3))
    az_v, el_v = AA[hair], EE[hair]
    x0, y0, x1, y1 = cam["crop"]
    cy = (tr["clip_y"] - y0) * Wm / max(x1 - x0, y1 - y0) if tr.get("clip_y") is not None else Wm
    rr = np.arange(0.0, 1.5 * Wm, 0.5)
    rows = {}
    for th in np.arange(0.0, 360.0, OUTLINE_STEP):
        t = np.radians(th)
        u, v = c[0] + rr * np.sin(t), c[1] - rr * np.cos(t)
        ok = (u >= 0) & (u < Wm) & (v >= 0) & (v < min(Wm, cy))
        if ok.sum() < 2:
            continue
        iu, iv = u[ok].astype(int), v[ok].astype(int)
        inR, inM = R[iv, iu], M[iv, iu]
        if not inR.any():
            continue
        r_ref = rr[ok][inR].max()
        if v[ok][inR][np.argmax(rr[ok][inR])] > cy - 4:  # the clip line, not an outline
            continue
        r_mod = rr[ok][inM].max() if inM.any() else 0.0
        near = np.abs(((th_v - th + 180) % 360) - 180) < OUTLINE_STEP
        nears = np.abs(((th_s - th + 180) % 360) - 180) < OUTLINE_STEP
        if not near.any() or not nears.any():
            continue
        k = np.argmax(np.where(near, r_v, -1))
        reg = str(region_of(az_v[k], el_v[k]))
        r_sc = r_s[nears].max()
        rows.setdefault(reg, []).append((r_mod - r_ref, r_ref - r_sc, r_mod - r_sc))
    out = {}
    for reg in REGION_NAMES:
        if reg not in rows:
            continue
        a = np.asarray(rows[reg]) * mm_px
        out[reg] = {"err": round(float(a[:, 0].mean()), 1), "worst": round(float(a[np.argmax(np.abs(a[:, 0])), 0]), 1),
                    "ref_hair": round(float(a[:, 1].mean()), 1), "our_hair": round(float(a[:, 2].mean()), 1),
                    "rays": len(a)}
    brow = None
    lms = tr.get("landmarks") or {}
    if "lm_brow_mid.L" in sc.lm and "lm_brow_mid.R" in sc.lm:
        bm = _to_crop(cam, project_ref(cam, np.array([sc.lm["lm_brow_mid.L"], sc.lm["lm_brow_mid.R"]])), Wm)
        br = _to_crop(cam, [lms[k] for k in ("lm_brow_mid.L", "lm_brow_mid.R")], Wm) \
            if all(k in lms for k in ("lm_brow_mid.L", "lm_brow_mid.R")) else bm
        lo, hi = int(max(0, min(bm[:, 0].min(), br[:, 0].min()))), int(min(Wm, max(bm[:, 0].max(), br[:, 0].max())) + 1)

        def top(mask):
            cols = mask[:, lo:hi]
            rws = np.where(cols.any(1))[0]
            return float(rws.min()) if len(rws) else np.nan
        brow = [round(float((br[:, 1].mean() - top(R)) * mm_px), 1), round(float((bm[:, 1].mean() - top(M)) * mm_px), 1)]
    return out, brow


def trace_overlay(name: str, sc: Scalp, cam: dict, img, spec: dict, tr: dict | None = None, mask=None):
    """The matched render with the traced reference lines (yellow, the hair outline orange) and the groom's own
    (cyan); `mask` (the matched id pass's hair) adds our hair's outline in magenta."""
    from PIL import Image, ImageDraw
    tr = ref_trace(name) if tr is None else tr
    if tr is None:
        return None
    W = img.width
    im = img.copy()
    if mask is not None:
        from scipy.ndimage import binary_erosion
        m = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize((W, W))) > 127
        edge = m & ~binary_erosion(m, iterations=2)
        a = np.asarray(im).copy()
        a[edge] = (255, 60, 230)
        im = Image.fromarray(a)
    dr = ImageDraw.Draw(im)
    ml = model_lines(name, sc, cam, spec)

    def poly(pts, col, w=2, closed=False):
        q = [tuple(p) for p in _to_crop(cam, pts, W)]
        if closed:
            q = q + q[:1]
        if len(q) > 1:
            dr.line(q, fill=col, width=w)
    for key, col in (("hairline", None), ("part", None)):
        if tr.get(key):
            poly(tr[key], (255, 230, 40), 3)
        if ml.get(key):
            poly(ml[key], (40, 230, 255), 2)
    if tr.get("hair"):
        poly(tr["hair"], (255, 160, 40), 2, closed=True)
    for c in tr.get("clumps", []):
        poly(c["line"], (255, 230, 40), 2)
        e = _to_crop(cam, c["line"][-1:], W)[0]
        dr.ellipse([e[0] - 3, e[1] - 3, e[0] + 3, e[1] + 3], fill=(255, 230, 40))
    for q in ml["clumps"].values():
        poly(q, (40, 230, 255), 1)
    return im


def trace_image(name: str, out: str | None = None, scale: float = 2.0):
    """The reference crop with the trace drawn on it (part red, hairline white, hair outline orange, clumps yellow
    with tip dots, landmarks green with the matched camera's reprojection in cyan). Returns the image."""
    from PIL import Image, ImageDraw
    tr, cam = ref_trace(name) or {}, ref_camera(name) or {}
    img, _ = reference_image(name)
    if img is None:
        raise HairError("the trace has no reference image (ref_trace.json \"image\")")
    im = Image.open(img).convert("RGB")
    x0, y0, x1, y1 = cam.get("crop") or tr.get("crop") or [0, 0, im.width, im.height]
    im = im.crop((x0, y0, x1, y1))
    im = im.resize((int(im.width * scale), int(im.height * scale)))
    dr = ImageDraw.Draw(im)

    def q(pts):
        return [((u - x0) * scale, (v - y0) * scale) for u, v in pts]
    if tr.get("hair"):
        dr.line(q(tr["hair"] + tr["hair"][:1]), fill=(255, 160, 40), width=2)
    if tr.get("hairline"):
        dr.line(q(tr["hairline"]), fill=(255, 255, 255), width=3)
    if tr.get("part"):
        dr.line(q(tr["part"]), fill=(255, 40, 40), width=4)
    for c in tr.get("clumps") or []:
        dr.line(q(c["line"]), fill=(255, 230, 40), width=3)
        e = q(c["line"][-1:])[0]
        dr.ellipse([e[0] - 5, e[1] - 5, e[0] + 5, e[1] + 5], fill=(255, 230, 40))
        r = q(c["line"][:1])[0]
        dr.text((r[0] + 4, r[1] - 12), c.get("name", ""), fill=(255, 255, 255))
    lms = tr.get("landmarks") or {}
    if lms and cam.get("R"):
        spec = store.load(name)
        from .spec import expand_mirror, geometry
        J = expand_mirror({k: v for k, v in geometry(spec).items() if k != "hair"})["joints"]
        for n, uv in lms.items():
            a = q([uv])[0]
            dr.ellipse([a[0] - 4, a[1] - 4, a[0] + 4, a[1] + 4], outline=(60, 255, 60), width=2)
            if n in J:
                b = q(project_ref(cam, np.asarray(J[n]["pos"], float)[None]).tolist())[0]
                dr.line([a, b], fill=(40, 230, 255), width=2)
    if tr.get("clip_y") is not None:
        y = (tr["clip_y"] - y0) * scale
        dr.line([(0, y), (im.width, y)], fill=(120, 120, 255), width=1)
    if out:
        im.save(out)
    return im


def _signed(az):
    return (np.asarray(az, float) + 180) % 360 - 180


def from_trace(name: str, spec: dict | None = None, widen: float = 1.8, back_rows: int = 3,
               side_rows: int = 3, part_back: float = 0.1, row_step: float = 0.022,
               fan: float = 0.004) -> dict:
    """A groom patch carried from the traced reference through the matched camera (ref_camera + ref_trace):
    - parting.line: the traced part's rays onto the volume, carried on straight back `part_back` m over the top;
    - hairline.front_points: the traced hairline's rays onto the scalp across the forehead, both sides averaged;
    - drawn clumps: each traced clump's rays onto the volume ([az, el]), rooted on the part line (a root hidden
      behind the outline is moved onto the part at its row), width = traced px x mm/px x `widen` (clumps overlap:
      the band you see is part of each); rows behind the traced ones (invisible from the reference) repeat the last
      top row shifted back along the part; the part side's traced clump repeated along the part.
    Returns {"groom": {...}} for spec["hair"]; nothing is saved."""
    spec = store.load(name) if spec is None else spec
    sc = hair_head.scalp(name, spec)
    g = groom_params(spec)
    cam, tr = ref_camera(name), ref_trace(name)
    if cam is None or tr is None:
        raise HairError("from_trace needs ref_camera.json (fit_camera) and ref_trace.json in the model folder")
    mm = np.linalg.norm(np.asarray(cam["eye"]) - sc.C) / cam["focal_px"]  # m per reference pixel at the head
    # the part
    Pp = ray_onto(sc, g, cam, tr["part"])
    a0, e0, _ = sc.coords(Pp)
    xy = (sc.point(a0, e0, 0.0) - sc.C)[:, :2]  # on the scalp under the hits (top-view terms)
    d = xy[-1] - xy[-2]
    d = d / np.linalg.norm(d)
    ext = [xy[-1] + d * 0.012]
    while ext[-1][1] < xy[0][1] + part_back:  # on straight back (turning off the traced heading)
        step = np.array([0.0, 1.0]) * 0.02
        ext.append(ext[-1] + step)
    pxy = np.vstack([xy, ext])
    pa, pe = top_to_azel(sc, np.asarray(ext))
    part = np.r_[np.stack([_signed(a0), e0], 1), np.stack([_signed(pa), pe], 1)]
    offset = float(abs(xy[0][0]))
    # the hairline over the forehead
    Ph = ray_onto(sc, g, cam, tr["hairline"], onto="scalp")
    ha, he, _ = sc.coords(Ph)
    ha = _signed(ha)
    front = []
    ok = he > 12  # the temples' vertical edges graze the head: their hits are unreliable
    for a0 in np.arange(0.0, 41.0, 8.0):
        zs = []
        for sgn in (1, -1):
            m = ok & (sgn * ha >= -2)
            if m.sum() < 2:
                continue
            aa, zz = sgn * ha[m], Ph[m, 2]
            o = np.argsort(aa)
            if aa[o][0] <= a0 <= aa[o][-1]:
                zs.append(np.interp(a0, aa[o], zz[o]))
        if zs:
            front.append([float(a0), round(float(np.mean(zs)), 4)])
    # clumps

    def on_part(y):  # the part point at top-view y (m from the centre)
        k = np.clip(np.interp(y, pxy[:, 1], np.arange(len(pxy))), 0, len(pxy) - 1)
        i = int(np.floor(k))
        j = min(i + 1, len(pxy) - 1)
        return pxy[i] + (k - i) * (pxy[j] - pxy[i])
    drawn_ = []
    tops = []
    for c in tr["clumps"]:
        P = ray_onto(sc, g, cam, c["line"])
        a, e, _ = sc.coords(P)
        a = _signed(a)
        keep = [0]
        for k in range(1, len(a)):  # a tip past the outline: the ray jumps round the head
            if np.linalg.norm(P[k] - P[keep[-1]]) < 0.06:
                keep.append(k)
            else:
                break
        a, e, P = a[keep], e[keep], P[keep]
        q = (P - sc.C)[:, :2]
        w = round(float(c.get("width", 24)) * mm * widen, 4)
        side = c["name"].startswith("part_side")
        far = (q[0][0] * xy[0][0]) < 0  # starts across the head from the part: the sweep's fall down the far side
        y_prev = tops[-1][1][0][1] if tops else -np.inf
        if not side and not far and (np.linalg.norm(q[0] - on_part(q[0][1])) > 0.012 or q[0][1] < y_prev + 0.015):
            # its root is hidden (or ahead of the row before): the clump carried on backward along its own heading
            # until it meets the part (a sweep running forward across the top grows from further back), never ahead
            # of the previous row's root
            d0 = q[0] - q[1]
            d0 = d0 / max(np.linalg.norm(d0), 1e-9)
            r = on_part(y_prev + 0.018)
            for s_ in np.arange(0.0, 0.12, 0.002):
                t = q[0] + s_ * d0
                if (t[0] - on_part(t[1])[0]) * np.sign(xy[0][0]) >= 0:
                    r = on_part(max(t[1], y_prev + 0.018))
                    break
            ra, re_ = top_to_azel(sc, r[None])
            a, e = np.r_[_signed(ra), a], np.r_[re_, e]
            q = np.vstack([r, q])
        # names: a row's stem + number (sweep1, sweep2...), so the under layer fills between neighbours
        nm = "pside0" if side else ("fall0" if far else f"sweep{len(tops) + 1}")
        drawn_.append({"name": nm, "azel": np.c_[a, e].round(2).tolist(), "width": w,
                       "taper": 0.85 if not side else 1.0, "traced": c["name"]})
        if not side and not far:
            tops.append((nm, q, w))
    # rows behind: the last top row, shifted back along the part
    if tops:
        _, q0, w0 = tops[-1]
        for k in range(1, back_rows + 1):
            dy = row_step * k
            q = q0 + [0.0, dy]
            q[1:, 1] += fan * k * np.linspace(0, 1, len(q) - 1) ** 1.5  # later rows fan back toward the crown
            q[:, 0] = np.clip(q[:, 0], -0.09, 0.09)
            drawn_.append({"name": f"sweep{len(tops) + k}", "top": q.round(4).tolist(), "width": w0, "taper": 0.85})
    # the part side: down toward his ear from the part, one per row along it
    ps = next((c for c in drawn_ if c["name"] == "pside0"), None)
    if ps:
        q = np.asarray(ps["azel"], float)
        for k in range(1, side_rows + 1):
            r = on_part(xy[0][1] + 0.025 * k)
            ra, re_ = top_to_azel(sc, r[None])
            dq = np.array([float(_signed(ra)[0]), float(re_[0])]) - q[0]
            drawn_.append({"name": f"pside{k}", "azel": (q + dq * np.linspace(1, 0.5, len(q))[:, None]).round(2).tolist(),
                           "width": ps["width"], "taper": 1.0})
    return {"groom": {"parting": {"side": "left" if xy[0][0] >= 0 else "right", "offset": round(offset, 4),
                                  "line": part.round(2).tolist()},
                      "hairline": {"front_points": front},
                      "drawn": drawn_}}
