"""The HAIR READER (the `hair_from_reference` tool; hair-garrett, 2026-10-14): the model's fitted reference pictures as a
MEASUREMENT of the hair, and a START groom / look set from what was measured. Like skin_from_reference: the picture is
never the texture; what the groom and look have a parameter for is read off the pictures, the parameters are set from
the read, and the reply says measured vs set, INFERRED where a picture can't show it, and which view each colour target
came from.

Per fitted reference view (human_refs.json: picture + humanfit camera):
  hair / skin / backdrop probabilities from the face parsers (faceparse: MediaPipe's multiclass + BiSeNet, averaged for
  hair), a pixel-level HAIRNESS a = where the pixel lies between the backdrop's colour (0) and the dense hair's (1),
  the bare skull's silhouette (the model's scalp projected through the camera) and mm a pixel at the head.
Measures (each a function of arrays, so tests run without the nets):
  outline   per image angle from the head centre: mm from the skull's edge to the solid hair's edge where the hair
            meets the backdrop (STAND-OFF, rule 1), by head region (the ray's grazing point on the scalp); the edge's
            ROUGHNESS (mm, against its own 15 deg average) and the HALO density (mean hairness 0.5-4 mm outside the solid
            edge: 0 a cut-out .. 1 solid; rule 4), WISPS (detached hair pieces within 12 mm, per 10 cm of outline; rule 7)
  hairline  every hair / bare-skin boundary pixel cast onto the scalp: the line's height per azimuth (front, temples,
            sideburns, nape; -> groom.hairline.front_points), its SOFTNESS (mm from 20 % to 80 % hair across the
            line, rule 6) and BABY HAIRS (detached specks on the skin side, per cm of line)
  parting   the strand direction field over the top in the authority view: a part is a sharp change of strand
            direction (and a fine line of scalp); position (m off the centre line, his left / right), softness (mm).
            Not seen -> INFERRED from the way the front is combed (rule 5)
  colour    colour_bands + colour_variation of the dense hair in the AUTHORITY view (the front unless told:
            references can disagree on colour between views; the others are checks), a two-mode split into the
            pigmented hair and the light / grey strands, and the light share BY REGION (top, front, sides, back:
            salt and pepper greys at the temples first) (rules 8-11)
  length    not visible on a short cut (the hair lies over itself): INFERRED from the stand-off by region

  frames(name)            -> per view: picture, masks, camera numbers (cached per process)
  read(name)              -> {"views": [...], "summary": {...}, "text"}
  start(r, spec)          -> {"hair": {style, groom patch, strands, look}, "rows": [(key, set, from)], "text"}
  apply(name, out=None)   -> read + start + groom (to `out`, a copy, or onto `name`)
"""
from __future__ import annotations

import copy
import hashlib
import json

import numpy as np

from . import store

VERSION = 1
NETS = ("mediapipe", "bisenet")
SKIN_CLASSES = (1, 14)        # BiSeNet face skin, neck (not ears 7, 8: hair over an ear is not a hairline)
HALO_BAND = (0.5, 4.0)        # mm outside the solid edge read as halo
WISP_REACH = 12.0             # mm: detached hair pieces this far out count as wisps
ROUGH_DEG = 15.0              # deg: the outline's own smooth trend (roughness is what is left)
REGIONS = ("front", "top", "crown", "sides", "back", "nape")


def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _lab_px(a):
    """CIE Lab of sRGB 0..255 pixels (..., 3)."""
    from .hair import _lab
    return np.stack(_lab(np.asarray(a, float)), -1)


def _hex(rgb) -> str:
    c = np.clip(np.round(np.asarray(rgb, float)), 0, 255).astype(int)
    return "#%02x%02x%02x" % tuple(c)


def region_name(az, el) -> np.ndarray:
    """The groom's regions (volume / length keys) of scalp points: top (el >= 55, toward the front), crown (el >= 55,
    behind, under 75 deg), front (within 45 deg of the face), sides (45-120), back, nape (low at the back)."""
    az = np.asarray(az, float)
    el = np.asarray(el, float)
    fa = np.abs(((az + 180) % 360) - 180)
    r = np.where(fa < 45, "front", np.where(fa < 120, "sides", np.where(el > -15, "back", "nape")))
    return np.where(el >= 55, np.where((fa < 100) | (el >= 75), "top", "crown"), r)


# ------------------------------------------------------------------------------------------------ camera helpers

def cam_eye(cam: dict):
    from . import humanfit
    R = humanfit._cam_rot(cam)
    return np.asarray(cam["centre"], float) - R.T @ np.asarray(cam["t"], float), R


def pixel_rays(cam: dict, uv):
    """World ray directions of pixels (u right, v down) through a humanfit camera."""
    eye, R = cam_eye(cam)
    w, h = cam["size"]
    uv = np.atleast_2d(np.asarray(uv, float))
    dc = np.stack([(uv[:, 0] - w / 2) / cam["f"], (uv[:, 1] - h / 2) / cam["f"], np.ones(len(uv))], 1)
    D = dc @ R
    return eye, D / np.linalg.norm(D, axis=1, keepdims=True)


def onto_scalp(sc, cam: dict, uv, height: float = 0.0, step: float = 0.001, chunk: int = 4000):
    """Pixels -> where their camera rays first come within `height` m of the scalp: (points (n, 3), hit (n,) bool,
    graze (n, 3) = each ray's closest approach to the scalp: the silhouette's point for an outline pixel)."""
    eye, D = pixel_rays(cam, uv)
    dist = float(np.linalg.norm(sc.C - eye))
    ts = np.arange(dist - 0.22, dist + 0.06, step)
    P = np.zeros((len(D), 3))
    G = np.zeros((len(D), 3))
    hit = np.zeros(len(D), bool)
    for s in range(0, len(D), chunk):
        d = D[s:s + chunk]
        Q = eye + ts[None, :, None] * d[:, None, :]
        _, _, hh = sc.coords(Q.reshape(-1, 3))
        hh = hh.reshape(len(d), len(ts)) - height
        neg = hh < 0
        k = np.where(neg.any(1), np.argmax(neg, 1), np.argmin(hh, 1))
        hit[s:s + chunk] = neg.any(1)
        P[s:s + chunk] = Q[np.arange(len(d)), k]
        G[s:s + chunk] = Q[np.arange(len(d)), np.argmin(hh, 1)]
    return P, hit, G


# ------------------------------------------------------------------------------------------------ capture

_FRAMES: dict = {}


def frames(name: str, spec: dict | None = None, views=None, images: dict | None = None) -> list:
    """Per fitted reference view: {"i", "image" (PIL RGB), "cam", "box", "mm" (mm a pixel at the head centre), "c"
    (head centre px), "hair" (hair probability, picture px), "skin" (bare face skin + neck), "bg" (backdrop),
    "skull" (the bare skull's silhouette, bool), "yaw"}. Cached per process by the pictures and cameras."""
    from PIL import Image
    from scipy import ndimage as ndi
    from . import faceparse, hair, humanfit
    spec = store.load(name) if spec is None else spec
    sc = hair.scalp(name, spec)
    refs = hair.human_refs(name)
    out = []
    for i, cam in enumerate(refs.get("cameras") or []):
        if views is not None and i not in views:
            continue
        v = (refs.get("views") or [{}] * (i + 1))[i] or {}
        sub = (images or {}).get(i)
        if images is not None and sub is None:
            continue
        if sub is not None:  # OUR render through this camera instead of the picture (like with like)
            img = render_as_picture(sub, cam["size"])
            ident = hashlib.sha1(np.asarray(img).tobytes()).hexdigest()[:16]
        else:
            img, ident = None, v.get("image")
        key = json.dumps([ident, cam, sc.C.tolist(), VERSION], sort_keys=True, default=str)
        if key in _FRAMES:
            out.append(_FRAMES[key])
            continue
        img = Image.open(v["image"]).convert("RGB") if img is None else img
        A, E = np.meshgrid(np.arange(0, 360, 1.0), np.arange(-60, 90, 1.0))
        P = sc.point(A.ravel(), E.ravel(), 0.0)
        uv = humanfit.project(cam, P)
        x0, y0 = uv.min(0)
        x1, y1 = uv.max(0)
        s = 1.3 * max(x1 - x0, y1 - y0)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        box = (cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2)
        hp, bgp = [], None
        skin = None
        for net in NETS:
            res = faceparse.parse(img, box, net)
            g = faceparse.groups(res)
            hp.append(faceparse.to_picture(g["hair"], box, img.size))
            if net == "bisenet":
                skin = faceparse.to_picture(res["p"][list(SKIN_CLASSES)].sum(0), box, img.size)
                bgp = faceparse.to_picture(res["p"][0], box, img.size)
                # (to_picture pads with 0 outside the crop: outside it is backdrop as far as this reader goes)
                inside = faceparse.to_picture(np.ones_like(res["p"][0]), box, img.size) > 0.5
                bgp = np.where(inside, bgp, 1.0)
        W, H = img.size
        sk = np.zeros((H, W), bool)
        q = np.round(uv).astype(int)
        ok = (q[:, 0] >= 0) & (q[:, 0] < W) & (q[:, 1] >= 0) & (q[:, 1] < H)
        sk[q[ok, 1], q[ok, 0]] = True
        sk = ndi.binary_fill_holes(ndi.binary_closing(sk, iterations=4))
        eye, _ = cam_eye(cam)
        from . import humanfit as hf
        Xc = (sc.C - np.asarray(cam["centre"], float)) @ hf._cam_rot(cam).T + np.asarray(cam["t"], float)
        f = {"i": i, "image": img, "cam": cam, "box": box, "mm": float(Xc[2]) / float(cam["f"]) * 1000.0,
             "c": humanfit.project(cam, sc.C[None])[0], "hair": np.mean(hp, 0), "skin": skin, "bg": bgp, "skull": sk,
             "yaw": float(v.get("yaw", cam.get("yaw", 0.0)) or 0.0), "image_path": v.get("image")}
        _FRAMES[key] = f
        out.append(f)
    return out


def render_as_picture(img, size):
    """A square render of a "ref<i>" / fitted view (the picture centred in it, hair.ref_square's layout) cropped and
    scaled back to the picture's own pixels (w, h = size)."""
    from PIL import Image
    im = (Image.open(img) if not hasattr(img, "size") else img).convert("RGB")
    w, h = size
    side = max(w, h)
    n = im.size[0]
    k = n / side
    x0, y0 = (side - w) / 2 * k, (side - h) / 2 * k
    return im.crop((int(round(x0)), int(round(y0)), int(round(x0 + w * k)), int(round(y0 + h * k)))).resize((w, h), Image.LANCZOS)


def compare(name: str, images: dict, spec: dict | None = None, authority: int | None = None) -> dict:
    """The same read on OUR renders through the fitted cameras (images {view index: square render, as hair.look's
    "ref<i>" views or hgshots' v<i>}) and on the pictures: {"ours", "picture", "text"} (the text: a table ours |
    picture per measure). Like with like: the same nets, masks and cameras on both."""
    spec = store.load(name) if spec is None else spec
    fo = frames(name, spec, images=images)
    fp = [f for f in frames(name, spec) if f["i"] in images]
    au = authority if authority is not None else _authority(fp)
    rp = read(name, spec, authority=au, fs=fp, log=lambda s: None)
    # ours split at the PICTURE's light / dark threshold: the light shares then count the same thing
    th = {v["i"]: v["colour"]["threshold_L"] for v in rp["views"] if v.get("colour")}
    ro = read(name, spec, authority=au, fs=fo, log=lambda s: None, thresholds=th)
    return {"ours": ro, "picture": rp, "text": compare_text(ro, rp)}


def compare_text(ro: dict, rp: dict) -> str:
    so, sp = ro["summary"], rp["summary"]
    L = ["HAIR COMPARE ours | picture (same nets, masks, cameras):"]
    for reg in REGIONS:
        a, b = so["standoff"].get(reg), sp["standoff"].get(reg)
        if a is not None or b is not None:
            L.append(f"  stand-off {reg}: {a} | {b} mm" + (f"  ({a - b:+.1f})" if a is not None and b is not None else ""))
    for k, nm in (("halo_all", "halo"), ("rough_mm", "edge roughness mm"), ("wisps_per_10cm", "wisps / 10 cm"),
                  ("baby_per_cm", "baby hairs / cm")):
        L.append(f"  {nm}: {so.get(k)} | {sp.get(k)}")
    L.append(f"  hairline softness mm: {so.get('hairline_softness_mm')} | {sp.get('hairline_softness_mm')}")
    ho = {round(a): z for a, z, e, n in so.get("hairline") or []}
    hp = {round(a): z for a, z, e, n in sp.get("hairline") or []}
    common = sorted(set(ho) & set(hp))
    if common:
        L.append("  hairline height, ours - picture mm by |az|: " + ", ".join(f"{a}: {1000 * (ho[a] - hp[a]):+.0f}" for a in common))
    for v_o, v_p in zip(ro["views"], rp["views"]):
        co, cp = v_o.get("colour") or {}, v_p.get("colour") or {}
        if co and cp:
            bo, bp = co["bands"], cp["bands"]
            tag = " (AUTHORITY)" if v_p["i"] == rp["authority"] else " (check)"
            L.append(f"  view {v_p['i']}{tag} colour L*/chroma/hue mean {bo['mean']['L']}/{bo['mean']['chroma']}/{bo['mean']['hue']} | "
                     f"{bp['mean']['L']}/{bp['mean']['chroma']}/{bp['mean']['hue']}; shadow L {bo['shadow']['L']} | {bp['shadow']['L']}; "
                     f"highlight L {bo['highlight']['L']} | {bp['highlight']['L']}; light share {co['light_share']} | {cp['light_share']}")
            vo, vp = bo.get("variation") or {}, bp.get("variation") or {}
            if vo and vp:
                L.append(f"    variation L_sd {vo.get('L_sd')} | {vp.get('L_sd')}, strand_sd {vo.get('strand_sd')} | {vp.get('strand_sd')}, "
                         f"ribbon_sd {vo.get('ribbon_sd')} | {vp.get('ribbon_sd')}, edge-core L {_ec(vo)} | {_ec(vp)}")
        lo, lp = v_o.get("light_share_by_region") or {}, v_p.get("light_share_by_region") or {}
        if lo and lp:
            L.append(f"    light share by region: " + ", ".join(f"{k} {lo.get(k)} | {lp.get(k)}" for k in REGIONS if k in lo or k in lp))
    return "\n".join(L)


def _lin_hex(h) -> np.ndarray:
    from .hair import _lin
    return _lin(h)  # ("#rrggbb" or [r, g, b] sRGB floats)


def _srgb_list(c) -> list:
    """Linear rgb -> [r, g, b] sRGB floats, 4 decimals: look.seen without 8-bit quantisation."""
    c = np.clip(np.asarray(c, float), 0, 1)
    return [round(float(x), 4) for x in np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)]


def _hex_lin(c) -> str:
    c = np.clip(np.asarray(c, float), 0, 1)
    return _hex(255 * np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055))


def colour_step(cmp: dict, look: dict, gain: float = 1.0) -> dict:
    """One colour correction from a compare (the AUTHORITY view only): each mode's colour as asked (look seen / grey)
    x (the picture's mode / our render's mode), per LINEAR channel (lightness, hue and chroma at once: what the
    renderer, the light and the mass's own shade do to a colour is taken as a fixed gain per channel). gain < 1 takes
    part of the step. Returns {"seen", "grey", "why"} (keys whose modes are missing are left out)."""
    ro, rp = cmp["ours"], cmp["picture"]
    au = rp["authority"]
    co = next((v["colour"] for v in ro["views"] if v["i"] == au), {}) or {}
    cp = next((v["colour"] for v in rp["views"] if v["i"] == au), {}) or {}
    out, why = {}, []
    # hair without grey: `seen` was set from the LIT mode, so the lit modes are compared (the start's rule)
    grey = cp.get("chroma_ratio") is None or cp["chroma_ratio"] < GREY_CHROMA
    if not grey and look.get("seen") and co.get("mean_rgb") and cp.get("mean_rgb"):
        # NO GREY: the step in Lab, as lightness, chroma and hue SEPARATELY on the mean colour (comparing lit modes
        # failed when ours had 1 % lit pixels and the picture 30 %). Per linear channel it blew up (hair-garrett,
        # family round 2: a brown asked bluer came out PURPLE, a near-black asked greener came out GREEN): `seen`
        # derives lit with its saturation / eevee_sat, so a small hue change in seen is a big one in the strands
        from .skin_read import _unlab, lab
        Lp, Lo, Ls = (lab(_lin_hex(h)) for h in (cp["mean_rgb"], co["mean_rgb"], look["seen"]))
        Cp, Co, Cs = (float(np.hypot(x[1], x[2])) for x in (Lp, Lo, Ls))
        hp_, ho_, hs_ = (float(np.degrees(np.arctan2(x[2], x[1]))) for x in (Lp, Lo, Ls))
        L1 = float(np.clip(Ls[0] + gain * (Lp[0] - Lo[0]), 2.0, 90.0))
        C1 = float(np.clip(Cs * (Cp / max(Co, 0.5)) ** gain, 0.0, 40.0))
        dh = float(np.clip(((hp_ - ho_ + 180) % 360 - 180) * gain, -20.0, 20.0))  # (a small turn at most)
        h1 = np.radians(hs_ + dh)
        # (as sRGB FLOATS: near-grey hair's hue does not survive 8 bits: #5b504f asked +6 deg came back the same hex)
        out["seen"] = _srgb_list(_unlab(np.array([L1, C1 * np.cos(h1), C1 * np.sin(h1)])))
        why.append(f"seen (mean colour, Lab): picture L* {Lp[0]:.1f} C {Cp:.1f} h {hp_:.0f}, ours L* {Lo[0]:.1f} C {Co:.1f} h "
                   f"{ho_:.0f} (view {au}): asked {look['seen']} -> {out['seen']} (L* {Ls[0]:.1f} -> {L1:.1f}, C {Cs:.1f} -> "
                   f"{C1:.1f}, hue {dh:+.0f} deg)")
    for key in ("seen", "grey"):
        mk = key
        if key in out or not grey and key == "seen":
            continue
        if co.get(mk) and cp.get(mk) and look.get(key):
            r = _lin_hex(cp[mk]) / np.maximum(_lin_hex(co[mk]), 1e-4)
            r = np.clip(r, 0.25, 4.0) ** float(gain)
            out[key] = _hex_lin(_lin_hex(look[key]) * r)
            why.append(f"{key} ({mk} mode): asked {look[key]}, rendered {co[mk]}, picture {cp[mk]} (view {au}) -> {out[key]}")
    out["why"] = "; ".join(why)
    return out


def _ec(v):
    return round(v["edge_L"] - v["core_L"], 1) if v.get("edge_L") is not None and v.get("core_L") is not None else None


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
    lo, hi = int(round(HALO_BAND[0] / mm)), max(int(round(HALO_BAND[0] / mm)) + 1, int(round(HALO_BAND[1] / mm)))
    halo = np.full(len(ang), np.nan)
    for k in np.nonzero(meets)[0]:
        seg = A[k, hr_px[k] + lo:hr_px[k] + hi]
        if len(seg):
            halo[k] = float(np.clip(seg, 0, 1).mean())
    # roughness: the edge against its own ROUGH_DEG average (runs that meet the backdrop only)
    rough = np.nan
    e = np.where(meets, hr_px * mm, np.nan)
    if np.isfinite(e).sum() > 2 * ROUGH_DEG:
        k_ = int(ROUGH_DEG)
        ef = np.where(np.isfinite(e), e, 0.0)
        wt = np.isfinite(e).astype(float)
        sm = ndi.uniform_filter1d(ef, k_) / np.maximum(ndi.uniform_filter1d(wt, k_), 1e-6)
        d = (e - sm)[np.isfinite(e) & (ndi.uniform_filter1d(wt, k_) > 0.99)]
        rough = float(np.std(d)) if len(d) > 10 else np.nan
    # wisps: hair-coloured pieces detached from the solid mass, within WISP_REACH mm, over the backdrop
    near = ndi.binary_dilation(solid, iterations=max(1, int(round(WISP_REACH / mm)))) & ~ndi.binary_dilation(
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
    from .hair import _orientation
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
    from .hair import colour_bands
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


# ------------------------------------------------------------------------------------------------ the read

def _authority(fs: list, authority=None) -> int:
    if authority is not None:
        return int(authority)
    return int(min(range(len(fs)), key=lambda k: abs(((fs[k]["yaw"] + 180) % 360) - 180)))


def read(name: str, spec: dict | None = None, authority: int | None = None, log=print, fs: list | None = None,
         thresholds: dict | None = None) -> dict:
    """Measure the hair on every fitted reference view (see the module's text). authority = the view whose colour is
    the target (default: the most frontal)."""
    from scipy import ndimage as ndi
    from . import hair
    spec = store.load(name) if spec is None else spec
    sc = hair.scalp(name, spec)
    fs = frames(name, spec) if fs is None else fs
    if not fs:
        raise ValueError(f"{name}: no fitted reference views (human_refs.json cameras: block_in / face solve make them)")
    au = _authority(fs, authority)
    views = []
    for f in fs:
        mm = f["mm"]
        hn = hairness(f["image"], f["hair"], f["bg"], mm)
        o = outline_rays(f["skull"], hn["solid"], hn["a"], f["bg"], f["c"], mm)
        v = {"i": f["i"], "yaw": f["yaw"], "mm_px": round(mm, 3), "hair_rgb": _hex(hn["hair_rgb"]),
             "backdrop_rgb": _hex(hn["bg_rgb"])}
        # stand-off by region: each ray's skull edge pixel -> its grazing point on the scalp
        ks = np.nonzero(o["meets"])[0]
        if len(ks):
            th = np.radians(o["ang"][ks])
            uv = np.stack([f["c"][0] + np.sin(th) * o["skull_px"][ks], f["c"][1] - np.cos(th) * o["skull_px"][ks]], 1)
            _, _, G = onto_scalp(sc, f["cam"], uv, step=0.0015)
            az, el, _ = sc.coords(G)
            reg = region_name(az, el)
            v["standoff"] = {r: round(float(np.nanmedian(o["standoff_mm"][ks][reg == r])), 1)
                             for r in REGIONS if (reg == r).sum() >= 3}
            v["halo"] = {r: round(float(np.nanmean(o["halo"][ks][reg == r])), 3)
                         for r in REGIONS if (reg == r).sum() >= 3}
            v["outline_samples"] = int(len(ks))
        v["halo_all"] = round(float(np.nanmean(o["halo"])), 3) if np.isfinite(o["halo"]).any() else None
        v["rough_mm"] = round(o["rough_mm"], 2) if np.isfinite(o["rough_mm"]) else None
        v["wisps"] = o["wisps"]
        v["wisps_per_10cm"] = round(o["wisps"] / max(o["outline_cm"] / 10.0, 1e-6), 1) if o["outline_cm"] > 1 else None
        # hairline: boundary pixels onto the scalp, front-facing only
        pts, nrm = hairline_pixels(f["hair"], f["skin"], step=max(1, int(round(1.0 / mm))))
        a_sk, skc = skin_hairness(f["image"], f["skin"], hn["hair_rgb"])
        hl = []
        if len(pts) > 10:
            P, hit, _ = onto_scalp(sc, f["cam"], pts, step=0.001)
            eye, _ = cam_eye(f["cam"])
            az, el, _ = sc.coords(P)
            nn = sc.normal(az, el)
            face = ((eye - P) / np.linalg.norm(eye - P, axis=1, keepdims=True) * nn).sum(1)
            ok = hit & (face > 0.35)
            # long hair hanging over the cheeks / jaw meets skin there too: that is not the hairline. A hairline point
            # in front of the ears sits above the sideburns' bottom (~ -12 deg); round the back the nape may go low
            fa_ = np.abs(((az + 180) % 360) - 180)
            ok &= (fa_ > 110) | (el > -12.0)
            for k in np.nonzero(ok)[0]:
                hl.append((float(((az[k] + 180) % 360) - 180), float(el[k]), float(P[k, 2]), k))
            soft = {}
            fa = np.abs(np.array([h_[0] for h_ in hl])) if hl else np.zeros(0)
            idx = np.array([h_[3] for h_ in hl], int) if hl else np.zeros(0, int)
            for nm, (lo, hi) in (("front", (0, 35)), ("temples", (35, 80)), ("sides", (80, 125)), ("nape", (125, 181))):
                sel = idx[(fa >= lo) & (fa < hi)]
                if len(sel) >= 20:
                    soft[nm] = edge_softness(None, a_sk, pts[sel], nrm[sel], mm)
            v["hairline_softness_mm"] = {k: s_.get("width_mm") for k, s_ in soft.items()}
        v["hairline"] = [h_[:3] for h_ in hl]
        v["baby_hairs"] = baby_hairs(a_sk, f["hair"], f["skin"], mm)
        hl_len = len(hl) * max(1.0, 1.0) * mm / 10.0  # cm of line seen (one sample a mm)
        v["baby_per_cm"] = round(v["baby_hairs"] / max(hl_len, 1e-6), 2) if hl_len > 1 else None
        # colour: the dense hair (solid eroded 2 mm, parser sure)
        dense = ndi.binary_erosion(hn["solid"], iterations=max(1, int(round(2.0 / mm)))) & (f["hair"] > 0.8)
        v["colour"] = colour_split(f["image"], dense, mm, T=(thresholds or {}).get(f["i"]))
        # light share by region: dense pixels cast onto the hair's surface
        ys, xs = np.nonzero(dense)
        if len(xs) > 200 and v["colour"]:
            sub = slice(None, None, max(1, len(xs) // 6000))
            uv = np.stack([xs[sub], ys[sub]], 1).astype(float)
            P, hit, _ = onto_scalp(sc, f["cam"], uv, height=0.008, step=0.0015)
            az, el, _ = sc.coords(P)
            reg = region_name(az, el)
            L = _lab_px(np.asarray(f["image"], float)[ys[sub], xs[sub]])[:, 0]
            T = v["colour"]["threshold_L"]
            v["light_share_by_region"] = {r: round(float((L[hit & (reg == r)] > T).mean()), 3)
                                          for r in REGIONS if (hit & (reg == r)).sum() >= 100}
        # LONG hair: how far down it reaches (the hair mask's lowest point, on the plane through the head centre facing
        # the camera: m under the centre) and how WAVY its lengths are (below the ear)
        v.update(lengths(f, sc, hn["solid"], mm))
        # parting (front-ish views only: within 50 deg of frontal)
        if abs(((f["yaw"] + 180) % 360) - 180) <= 50:
            cols = np.nonzero(hn["solid"].any(0))[0]
            top = int(np.nonzero(hn["solid"].any(1))[0].min()) if hn["solid"].any() else 0
            hlr = [pts[h_[3], 1] for h_ in hl if abs(h_[0]) < 25]
            hline = float(np.median(hlr)) if hlr else top + 60.0 / mm
            v["parting"] = parting(f["image"], hn["solid"], a_sk, mm, top, hline, f["c"])
            if v["parting"].get("x_px") is not None:
                # the part's place on the head: its pixel at the band's middle, cast onto the hair's surface
                yy = top + 0.3 * (hline - top)
                P, hit, _ = onto_scalp(sc, f["cam"], [[v["parting"]["x_px"], yy]], height=0.01)
                v["parting"]["x_m"] = round(float(P[0, 0] - sc.C[0]), 4) if hit[0] else None
        views.append(v)
    r = {"views": views, "authority": au, "authority_image": fs[au].get("image_path"), "version": VERSION}
    r["summary"] = summarise(r)
    r["text"] = read_text(r)
    return r


def summarise(r: dict) -> dict:
    """Across views: stand-off and halo by region (median over the views that see the region's outline), hairline
    points (|az| binned, left and right together), softness, parting, colour targets (the authority view's)."""
    vs = r["views"]
    au = vs[r["authority"]]
    s = {"standoff": {}, "halo": {}}
    for k in ("standoff", "halo"):
        for reg in REGIONS:
            x = [v[k][reg] for v in vs if reg in (v.get(k) or {}) and np.isfinite(v[k][reg])]
            if x:
                s[k][reg] = round(float(np.median(x)), 3 if k == "halo" else 1)
    hal = [v["halo_all"] for v in vs if v.get("halo_all") is not None]
    s["halo_all"] = round(float(np.median(hal)), 3) if hal else None
    rough = [v["rough_mm"] for v in vs if v.get("rough_mm") is not None]
    s["rough_mm"] = round(float(np.median(rough)), 2) if rough else None
    wp = [v["wisps_per_10cm"] for v in vs if v.get("wisps_per_10cm") is not None]
    s["wisps_per_10cm"] = round(float(np.median(wp)), 1) if wp else None
    # hairline: per 5 deg of |az| the median height (z) and elevation over every view that saw it
    allp = np.array([p for v in vs for p in v.get("hairline") or []], float).reshape(-1, 3)
    pts = []
    if len(allp):
        fa = np.abs(allp[:, 0])
        for a0 in np.arange(0, 180, 5.0):
            m = (fa >= a0) & (fa < a0 + 5)
            if m.sum() >= 6:
                pts.append([a0 + 2.5, round(float(np.median(allp[m, 2])), 4), round(float(np.median(allp[m, 1])), 1),
                            int(m.sum())])
        left, right = allp[allp[:, 0] > 5], allp[allp[:, 0] < -5]
        s["hairline_asym_mm"] = (round(1000 * float(np.median(left[np.abs(left[:, 0]) < 40, 2]) - np.median(right[np.abs(right[:, 0]) < 40, 2])), 1)
                                 if (np.abs(left[:, 0]) < 40).sum() > 5 and (np.abs(right[:, 0]) < 40).sum() > 5 else None)
    s["hairline"] = pts
    soft = {}
    for v in vs:
        for k, w in (v.get("hairline_softness_mm") or {}).items():
            if w is not None:
                soft.setdefault(k, []).append(w)
    s["hairline_softness_mm"] = {k: round(float(np.median(w)), 1) for k, w in soft.items()}
    bp = [v["baby_per_cm"] for v in vs if v.get("baby_per_cm") is not None]
    s["baby_per_cm"] = round(float(np.median(bp)), 2) if bp else None
    bm = [v["bottom_m"] for v in vs if v.get("bottom_m") is not None]
    s["bottom_m"] = round(float(max(bm)), 3) if bm else None  # (the view that sees the most of it hanging)
    wv = [v["waviness"] for v in vs if v.get("waviness") is not None]
    s["waviness"] = round(float(np.median(wv)), 3) if wv else None
    s["parting"] = au.get("parting") or next((v.get("parting") for v in vs if v.get("parting")), None)
    s["colour"] = au.get("colour") or {}
    s["colour_view"] = r["authority"]
    s["light_share_by_region"] = dict(au.get("light_share_by_region") or {})
    for v in vs:  # regions the authority view can't see (the back) from the others, marked
        for k, x in (v.get("light_share_by_region") or {}).items():
            if k not in s["light_share_by_region"]:
                s["light_share_by_region"][k] = x
                s.setdefault("light_share_from", {})[k] = v["i"]
    return s


def read_text(r: dict) -> str:
    s = r["summary"]
    L = [f"HAIR READ (v{r['version']}): {len(r['views'])} fitted views; colour authority = view {r['authority']} "
         f"(yaw {r['views'][r['authority']]['yaw']:.0f}); the others are checks"]
    L.append("stand-off over the skull, mm (rule 1), median over views: " +
             ", ".join(f"{k} {v}" for k, v in s["standoff"].items()))
    for v in r["views"]:
        L.append(f"  view {v['i']} (yaw {v['yaw']:.0f}, {v['mm_px']} mm/px): stand-off " +
                 ", ".join(f"{k} {x}" for k, x in (v.get("standoff") or {}).items())
                 + f"; halo {v.get('halo_all')}; edge roughness {v.get('rough_mm')} mm; wisps {v.get('wisps')}"
                 + (f" ({v['wisps_per_10cm']} / 10 cm)" if v.get("wisps_per_10cm") is not None else ""))
    L.append(f"halo density (rule 4; mean hairness {HALO_BAND[0]}-{HALO_BAND[1]} mm past the solid edge, 0 cut-out .. 1 "
             f"solid): {s['halo_all']} (by region {s['halo']}); edge roughness {s['rough_mm']} mm; wisps "
             f"{s['wisps_per_10cm']} per 10 cm of outline")
    if s["hairline"]:
        L.append("hairline (rule 6), |az| deg -> height z m / elevation deg (samples): " +
                 "; ".join(f"{a:.0f}: {z} / {e}" for a, z, e, n in s["hairline"][:8]) + (" ..." if len(s["hairline"]) > 8 else ""))
    L.append(f"hairline softness (20->80 % hair across the line, mm): {s['hairline_softness_mm']}; baby hairs "
             f"{s['baby_per_cm']} per cm; left - right height {s.get('hairline_asym_mm')} mm")
    if s.get("bottom_m") is not None:
        L.append(f"lengths: the hair reaches {s['bottom_m']} m under the head centre (the view that shows most of it; "
                 f"the jaw is ~0.11, the shoulders' top ~0.17); waviness of the lengths {s.get('waviness')} (0 straight .. 1 "
                 f"curly)")
    p = s.get("parting") or {}
    if p:
        L.append("parting (rule 5): " + ("SEEN" if p.get("seen") else "NOT SEEN (a part needs a sharp flip of strand "
                 "direction AND a scalp line)") + f": flip strength {p.get('strength')}, width {p.get('width_mm')} mm, "
                 f"scalp line {p.get('scalp')}, at {p.get('x_m')} m off the centre; the front's sweep "
                 f"{p.get('sweep')} (+ = image right)")
    c = s.get("colour") or {}
    if c:
        b = c["bands"]
        L.append(f"colour (authority view {s['colour_view']}): mean L* {b['mean']['L']} chroma {b['mean']['chroma']} hue "
                 f"{b['mean']['hue']}; shadow {b['shadow']['L']} / mid {b['mid']['L']} / highlight {b['highlight']['L']}")
        va = b.get("variation") or {}
        if va:
            L.append(f"  variation: L_sd {va.get('L_sd')}, strand_sd {va.get('strand_sd')}, ribbon_sd {va.get('ribbon_sd')}, "
                     f"mass_sd {va.get('mass_sd')}, light ribbons {va.get('ribbons')}, edge L {va.get('edge_L')} vs core "
                     f"{va.get('core_L')}")
        L.append(f"  two modes at L* {c['threshold_L']}: pigmented {c.get('dark_L')} (seen {c.get('seen')}), light / grey "
                 f"{c.get('light_L')} (grey {c.get('grey')}), light share {c['light_share']}")
        L.append(f"  light share by region: {s['light_share_by_region']}"
                 + (f" (from views {s['light_share_from']})" if s.get("light_share_from") else ""))
    for v in r["views"]:
        if v["i"] != r["authority"] and v.get("colour"):
            b = v["colour"]["bands"]["mean"]
            L.append(f"  check view {v['i']}: mean L* {b['L']} chroma {b['chroma']} hue {b['hue']}, light share "
                     f"{v['colour']['light_share']}")
    return "\n".join(L)


# ------------------------------------------------------------------------------------------------ the start

# fine, straight, dense short hair: many thin strands, no wave / curl, little clumping (long-hair dials made noodles)
CROP = {"strands": {"count": 600000, "thickness": 0.9, "clump": 0.1, "stray": 0.9, "roots": 0.9, "loose": 0.0,
                    "frizz": 0.02, "wave": 0.0, "curl": 0.0, "tips": 0.6, "tip_spread": 0.3, "under_length": 0.01}}
SHORT_MM = 30.0     # mm: a mean stand-off under this (and no region over 1.5x) is a short cut
LIFT_SPREAD = 0.005  # m a laid short lock's strands stand over its guide (render stand-off ~ lift + this)
LOOSE_THICK = 0.003  # m: a short laid lock's thickness (6 mm sank half the strands into the skin: curls)
LONG_BELOW = 0.12  # m under the head centre: hair reaching lower (past the jaw) is loose LONG hair
GREY_CHROMA = 1.0  # light mode chroma / dark mode chroma under this: the light hairs are GREY (else lit pigmented hair)


def start(r: dict, spec: dict) -> dict:
    """The START from a read: style (strands), groom patch (loose short cut: lengths, volume by region, lay, flow,
    hairline front points, parting, grey by region), strands (crop recipe + halo / fly-aways from the read) and look
    (seen, grey, grey_amount, variation, scalp tint). rows = (key, value set, what it came from)."""
    s = r["summary"]
    rows = []

    def put(key, val, why):
        rows.append((key, val, why))
        return val
    so = {k: v / 1000.0 for k, v in s["standoff"].items() if np.isfinite(v)}
    top = so.get("top", so.get("front", 0.012))
    so_all = {reg: so.get(reg, {"crown": so.get("top", top), "nape": 0.4 * so.get("back", so.get("sides", top)),
                                "back": so.get("sides", top), "front": top, "sides": 0.8 * top, "top": top}[reg])
              for reg in REGIONS}
    inferred = {reg: reg not in so for reg in REGIONS}
    bottom = s.get("bottom_m")
    long_ = bottom is not None and bottom > LONG_BELOW
    if long_ or np.mean(list(so_all.values())) * 1000 > SHORT_MM or max(so_all.values()) * 1000 > 1.5 * SHORT_MM:
        short = False
        if not long_:
            rows.append(("style", None, f"mean stand-off {1000 * np.mean(list(so_all.values())):.0f} mm and no hair below "
                                        "the jaw: not a short cut, not loose long hair; the reader sets hairline, parting "
                                        "and look only (groom the shape by hand: tied hair is tie_hair's)"))
    else:
        short = True
    g = {}
    if long_:
        # LOOSE LONG hair (the guide's loose-hair recipes): a one-length cut at the measured bottom (`level`), long
        # enough to reach it, `body` and `lift` from the stand-off at the sides and top, framed off the face
        lvl = -float(bottom) + 0.01  # (m from the head centre; the lowest 0.1 % of the mask is the longest strand)
        ln = float(np.clip(bottom + 0.16, 0.15, 0.8))
        put("groom.loose.level", round(lvl, 3), f"MEASURED: the hair reaches {bottom} m under the head centre (the view "
                                                "showing most of it; behind the shoulders it may reach further: INFERRED)")
        put("groom.loose.length", round(ln, 3), "the level + the crown's way down (INFERRED; the level cuts it)")
        side_so = so_all.get("sides", 0.015)
        body = round(float(np.clip(side_so - 0.006, 0.006, 0.04)), 4)
        lift = round(float(np.clip(so_all.get("top", 0.012) - 0.008, 0.002, 0.015)), 4)
        put("groom.loose.body", body, f"MEASURED side stand-off {round(1000 * side_so, 1)} mm - 6 mm (the strands' spread)")
        put("groom.loose.lift", lift, f"MEASURED top stand-off {round(1000 * so_all.get('top', 0.012), 1)} mm - 8 mm")
        wv = s.get("waviness")
        g["loose"] = {"length": round(ln, 3), "level": round(lvl, 3), "spacing": 0.02, "body": body, "lift": lift,
                      "stiff": 0.25, "messy": 0.08, "uneven": 0.35, "face": 1.0}
        put("groom.loose (rest)", "spacing 0.02, stiff 0.25, messy 0.08, uneven 0.35, face 1", "the guide's long-hair recipes")
        if s.get("halo_all") is not None:  # loose hair's own halo / fly-away words (rule 4 / 7)
            g["loose"]["halo"] = put("groom.loose.halo", round(float(np.clip(2.5 * s["halo_all"], 0.1, 1.0)), 2),
                                     f"MEASURED halo density {s['halo_all']} (hair-garrett family r4: 1.0 read ~0.3 of it "
                                     f"with the old quartered dial)")
        if s.get("wisps_per_10cm") is not None:
            g["loose"]["flyaway"] = put("groom.loose.flyaway", round(float(np.clip(0.01 * s["wisps_per_10cm"], 0.02, 0.2)), 3),
                                        f"MEASURED {s['wisps_per_10cm']} wisps / 10 cm")
        # The two principles (hair_guide.md, top): EVEN ROOTS (EVERY strand from one even sampling of the scalp; the
        # locks are dense GUIDES 4 mm apart that only steer direction, each bank of the part its own, magenta
        # only on the part line) and ARC UP, THEN FALL (out of the scalp by region, from the measured stand-off)
        g["loose"].update({"spacing": 0.004, "width": 2.4})
        arc = {reg: round(float(np.clip(0.25 * (1000 * so_all.get(reg, 0.008) / 10.0) * w, 0.0, 0.4)), 3)
               for reg, w in (("front", 0.8), ("top", 1.0), ("sides", 0.4), ("back", 0.4), ("nape", 0.0))}
        g["loose"]["out"] = put("groom.loose.out", arc, "ARC UP THEN FALL: 0.25 x stand-off / 10 mm x (front .8, top 1, "
                                                        "sides / back .4, nape 0)")
        st_long = {"count": 260000, "clump": 0.45, "loose": 0.2, "stray": 0.6, "tips": 0.5, "even": 1.0, "halo_soft": 1.0}
        put("strands.even", 1.0, "EVEN ROOTS: every strand from one even sampling of the scalp, shaped by the lock "
                                 "guides (groom.loose.spacing 4 mm: guides, not root owners); count 260k")
        if wv is not None:
            k = float(np.clip((wv - 0.08) / 0.3, 0.0, 1.0))  # 0 straight .. 1 waves
            st_long.update({"wave": round(0.002 + 0.014 * k, 4), "wavelength": round(0.16 - 0.07 * k, 3), "curl": round(0.25 * k, 2)})
            put("strands.wave / wavelength / curl", [st_long["wave"], st_long["wavelength"], st_long["curl"]],
                f"MEASURED waviness {wv} of the lengths (0.08 straight .. 0.38 waves; the guide's straight / waves recipes)")
        put("strands (rest)", "count 120000, clump 0.45, loose 0.2, stray 0.6, tips 0.5", "the guide's long-hair recipes")
    if short:
        # LIFT by region (groom.loose.lift; groom.volume does nothing to loose hair): a laid short lock's strands
        # spread ~LIFT_SPREAD m over its guide, so the guide stands at the stand-off less that
        lift = {reg: round(float(np.clip(so_all[reg] - LIFT_SPREAD, 0.001, 0.02)), 4) for reg in ("front", "top", "sides", "back", "nape")}
        put("groom.loose.lift", lift, f"MEASURED stand-off per region - {1000 * LIFT_SPREAD:.0f} mm (the strands' own spread"
            + (f"; INFERRED for {', '.join(k for k in REGIONS if inferred[k])})" if any(inferred.values()) else ")"))
        # a combed short cut is longer on top and front, clipped at the sides and back, tapering to the nape (a
        # barber's taper); the stand-off sets the scale
        ln = {"front": float(np.clip(4.0 * so_all["front"], 0.03, 0.08)), "top": float(np.clip(4.0 * so_all["top"], 0.03, 0.08)),
              "sides": float(np.clip(1.5 * so_all["sides"], 0.01, 0.025)), "back": float(np.clip(1.5 * so_all["back"], 0.01, 0.025)),
              "nape": float(np.clip(0.6 * so_all["nape"], 0.005, 0.012))}
        ln = {k: round(v, 3) for k, v in ln.items()}
        put("groom.loose.length", ln, "INFERRED: a short cut lies over itself, its length is not in a picture; top / front "
                                     "4x the stand-off, sides / back 1.5x, the nape tapering (a barber's taper)")
        p = s.get("parting") or {}
        sweep = p.get("sweep")
        sx = 0.0 if sweep is None else float(np.clip(sweep, -1, 1))
        # front: up and back, over to the side the front is combed toward (image right = his left = +x, front view)
        flow = {"front": [round(0.6 * sx, 2), 0.75, 0.45], "top": [round(0.4 * sx, 2), 0.9, 0.0], "sides": [0.0, 0.7, -0.7],
                "back": [0.0, 0.15, -1.0], "nape": [0.0, 0.05, -1.0]}
        put("groom.loose.flow", flow, f"one comb direction per region: front up and back, over by the measured sweep {sweep}; "
                                      "sides back and down; back and nape down (prior: a combed short cut)")
        lay = {"front": 0.35, "top": 0.65, "sides": 0.5, "back": 0.6, "nape": 0.6}
        put("groom.loose.lay", lay, "prior (combed flat along the flow); with the locks thin enough (thickness) not to sink")
        loose = {"length": ln, "spacing": 0.005, "width": 2.4, "lift": lift, "body": 0.004, "thickness": LOOSE_THICK,
                 "messy": {"front": 0.25, "top": 0.25, "sides": 0.1, "back": 0.06, "nape": 0.04}, "uneven": 0.5,
                 "flow": flow, "lay": lay, "stiff": {"front": 0.55, "top": 0.5, "sides": 0.6, "back": 0.65, "nape": 0.6},
                 "out": {"front": 0.15, "top": 0.05, "sides": 0.0, "back": 0.0, "nape": 0.0}}
        put("groom.loose.thickness", LOOSE_THICK, "a laid lock thicker than twice its clearance sinks half its strands into "
                                                  "the skin; pushed out, they crumple into curls (hair-garrett r1-r2)")
        put("groom.loose (rest)", "spacing 0.005, width 2.4, body 0.004 (a dense, continuous combed surface: at 8 mm the locks parted into ridges with scalp between, hair-heads r11), messy low, uneven 0.5, stiff per region",
            "a combed short cut")
        loose["fade"] = put("groom.loose.fade", {"width": 0.02}, "a short cut fades out at the nape (prior: a barber's "
                                                                 "fade over 2 cm; the nape ended in a ledge without it)")
        g["loose"] = loose
    # hairline: the measured front points (|az| <= 75: the front and temples), heights in m
    hp = [[a, z] for a, z, e, n in s.get("hairline") or [] if a <= 75]
    if len(hp) >= 3:
        g["hairline"] = {"front_points": [[round(a, 1), round(z, 4)] for a, z in hp]}
        put("groom.hairline.front_points", f"{len(hp)} points, |az| {hp[0][0]:.0f}-{hp[-1][0]:.0f} deg",
            "MEASURED: hair / skin boundary pixels cast onto the scalp, left and right together")
    else:
        put("groom.hairline", "default", "INFERRED: too little hairline seen")
    p = s.get("parting") or {}
    if p.get("seen") and p.get("x_m") is not None:
        side = "left" if p["x_m"] > 0 else "right"
        g["parting"] = {"side": side, "offset": round(abs(float(p["x_m"])), 3)}
        put("groom.parting", g["parting"], f"MEASURED (front view: strand flip {p.get('strength')}, scalp line {p.get('scalp')})")
    elif long_ and p.get("sweep") is not None and abs(float(p["sweep"])) > 0.25:
        # long hair combed over to one side falls AWAY from a part on the other (front view: image right = the
        # person's left, +x): a side part there, its offset a guess
        side = "left" if float(p["sweep"]) < 0 else "right"
        g["parting"] = {"side": side, "offset": 0.025}
        put("groom.parting", g["parting"], f"INFERRED from the front's sweep {p['sweep']} (the hair falls away from a part on "
                                           f"the other side); no part line seen: place it by eye")
    else:
        g["parting"] = {"side": "none"}
        put("groom.parting", g["parting"], "INFERRED: no part seen in the front-ish views (combed through)")
    # grey by region: the light share above the least grey region's (that is look.grey_amount)
    ls = s.get("light_share_by_region") or {}
    c = s.get("colour") or {}
    look = {}
    if c:
        from .hair import grey_age
        cr = c.get("chroma_ratio")
        young = (grey_age(spec) <= 0.2) if spec else False  # (under ~34 the light pixels are LIT hair, not grey hairs)
        lit_not_grey = cr is not None and cr >= GREY_CHROMA
        ga_ok = not young and not lit_not_grey
        ga = 0.0
        if not ga_ok:
            g["grey"] = {"temples": 0.0, "sideburns": 0.0}
            look["grey_amount"] = put("look.grey_amount", 0.0, (
                f"MEASURED: the light pixels are LIT hair, not grey: as chromatic as the dark ones or more (ratio {cr}; "
                f"grey hair < {GREY_CHROMA})" if lit_not_grey else "the model's age: no grey under ~34") + "; groom.grey 0")
        else:
            base = min(ls.values()) if ls else c.get("light_share", 0.0)
            ga = round(float(np.clip(base, 0.0, 0.9)), 3)
            look["grey_amount"] = put("look.grey_amount", ga, f"MEASURED: the light-strand share of the least grey region "
                                                             f"(view {s['colour_view']})")
            gr = {k: round(float(np.clip(v - base, 0, 1)) / max(1 - base, 0.1), 3) for k, v in ls.items()
                  if k in ("front", "top", "sides", "back", "nape")}  # (groom.grey's regions: no crown)
            if gr:
                g["grey"] = {**gr, "temples": round(max(gr.get("sides", 0.0), gr.get("front", 0.0)), 3), "sideburns": round(gr.get("sides", 0.0), 3)}
                put("groom.grey", g["grey"], "MEASURED: light share by region above grey_amount (temples / sideburns = the sides')")
        if not ga_ok and c.get("lit"):  # no grey: the two modes are shadow and lit hair; `seen` is the LIT hair's
            look["seen"] = put("look.seen", c["lit"], f"MEASURED: the lit hair (the lighter mode), view {s['colour_view']}")
        elif c.get("seen"):
            look["seen"] = put("look.seen", c["seen"], f"MEASURED: the lit half of the pigmented hair, view {s['colour_view']}")
        gs = c.get("grey_strand") or c.get("grey")
        if gs and ga_ok:
            look["grey"] = put("look.grey", gs, f"MEASURED: the lightest quarter of the light / grey pixels (a grey strand: "
                                                f"the pixels' median mixes it with dark hair), view {s['colour_view']}")
        va = (c.get("bands") or {}).get("variation") or {}
        if va.get("strand_sd") is not None:
            look["variation"] = put("look.variation", round(float(np.clip(0.4 * va["strand_sd"] / 4.2, 0.2, 0.8)), 2),
                                    f"strand_sd {va['strand_sd']} (Tess calibration: 4.2 at 0.4)")
        look["sun"] = put("look.sun", 0.0 if short else 0.2, "INFERRED: a short cut has no old lengths" if short else "default")
        rib = (va.get("ribbons") or {}).get("share") if va else None
        if long_ and not ga_ok and rib is not None:
            look["highlights"] = put("look.highlights", round(float(np.clip(6.0 * rib, 0.0, 0.8)), 2),
                                     f"MEASURED light ribbons {round(100 * rib)} % of the hair (Tess: 9-10 % at 0.7)")
        else:
            look["highlights"] = put("look.highlights", 0.0, "light ribbons on grey hair are the grey strands (not sun streaks)"
                                     if ga > 0.15 else "default")
        if ga > 0.15 or (c.get("dark_L") or 0) > 40:
            look["scalp_tint"] = put("look.scalp_tint", 0.15, "grey / fair hair: at 0.5 the receded temple corners of a grey crop read as dark patches (hair-heads r9)")
    st = copy.deepcopy(CROP["strands"]) if short else (st_long if long_ else {})
    h_ = s.get("halo_all")
    if h_ is not None:
        st["halo"] = put("strands.halo", round(float(np.clip(1.2 * h_, 0.05, 0.6)), 2), f"MEASURED halo density {h_}")
    w_ = s.get("wisps_per_10cm")
    if w_ is not None:
        st["flyaway"] = put("strands.flyaway", round(float(np.clip(0.01 + 0.01 * w_, 0.0, 0.1)), 3), f"MEASURED {w_} wisps / 10 cm")
    sm = (s.get("hairline_softness_mm") or {}).get("front")
    if sm:
        st["soft"] = put("strands.soft", round(float(np.clip(sm / 1000.0, 0.002, 0.012)), 4),
                         f"MEASURED hairline softness {sm} mm (20->80 %)")
    if s.get("baby_per_cm") is not None:
        st["baby"] = put("strands.baby", round(float(np.clip(0.2 + 0.3 * s["baby_per_cm"], 0.0, 1.0)), 2),
                         f"MEASURED {s['baby_per_cm']} baby hairs / cm")
    hairp = {"style": "strands", "groom": g, "strands": st, "look": look}
    return {"hair": hairp, "rows": rows, "short": short, "text": start_text(rows)}


def start_text(rows) -> str:
    L = ["START (set from the read):"]
    for k, v, why in rows:
        L.append(f"  {k} = {json.dumps(v) if not isinstance(v, str) else v}   <- {why}")
    return "\n".join(L)


def apply(name: str, out: str | None = None, authority: int | None = None, seed: int = 0, log=print) -> dict:
    """read + start + groom: the hair patch is saved (and grown) onto `out` (a copy of `name` without hair, its
    human_refs carried) or onto `name`. Returns {"read", "start", "text"}."""
    import shutil
    from . import hair
    r = read(name, authority=authority, log=log)
    spec = store.load(name)
    s = start(r, spec)
    dst = out or name
    if out:
        d = store.HOME / out
        d.mkdir(parents=True, exist_ok=True)
        sp = copy.deepcopy(spec)
        sp.pop("hair", None)
        (d / "spec.json").write_text(json.dumps(sp, indent=1))
        for f in ("human_refs.json",):
            if (store.HOME / name / f).exists():
                shutil.copy(store.HOME / name / f, d / f)
    sp = store.load(dst)
    h = sp.setdefault("hair", {})
    h["style"] = s["hair"]["style"]
    h["strands"] = hair.merge_patch(h.get("strands") or {}, s["hair"]["strands"])
    h["look"] = hair.merge_patch(h.get("look") or {}, s["hair"]["look"])
    hair.validate(sp)
    store.save(dst, sp, "hair_from_reference: style / strands / look")
    gr = hair.groom(dst, replace=True, note="hair_from_reference", patch={**s["hair"]["groom"], "seed": int(seed)})
    text = r["text"] + "\n" + s["text"] + f"\nsaved {dst} v{gr['version']}: grew " + ", ".join(f"{t} {n}" for t, n in gr["grown"].items())
    return {"read": r, "start": s, "text": text}
