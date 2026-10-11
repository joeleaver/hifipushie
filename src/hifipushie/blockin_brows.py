"""The dressed BROWS from the picture (gnmbrow, 2026-10-11; Joe on a dressed eye sheet: "the eyebrows in the render now
sit on top the crease, instead of their correct position").

The skin draws each brow as a picture of hairs (skin_swatch.brow_image) laid as a decal from GNM's three brow
landmarks, moved by skin.hair.brows' drop / lift / tilt / apart and shaped by fall / thickness / taper. Those were set
by eye, once, on one head, and then travelled with the dressing onto later heads (Tess: drop 4 mm from an older head
left the hair 4-7 mm under her brow, on the lid's fold). GNM's landmarks are the brow RIDGE's, not the person's hair:
where the hair grows on it is the person's, so it is read off the picture.

  band(img, P, mmpx)        the picture's brow hair per side, per column across the brow: lower edge / core / upper edge
                            (half contrast between the hair band's core and the skin under / over it), picture pixels
  model_band(...)           the decal's band (spine -+ half thickness) carried onto the head's surface and through the
                            fitted front camera, at the same columns
  fit(name)                 skin.hair.brows' placement (drop, tilt, apart, fall, thickness, taper) by least squares on
                            the band's middle line and thickness; returns the new dict, the errors before / after, text
  apply(name, out=None)     writes it (skin.hair.brows; "lift" folded into drop + tilt)
Everything is measured in mm AT THE MODEL (picture pixels x the fitted camera's mm/px at the face)."""
from __future__ import annotations

import copy
import json

import numpy as np

COLS = np.linspace(0.08, 1.0, 9)      # across the detector's brow span, inner end -> outer end
REACH = 9.0                            # mm either side of the detector's band searched for the hair
MIN_CONTRAST = 0.10                    # a column whose band is fainter than this against the skin is not used
EDGE = 0.75                            # the rendered band's half-contrast edge as a share of the decal's nominal half
                                       # thickness (hairs thin out toward the band's edge; calibrated on a dressed render)
GROW = 0.125                           # x the hairs' length: the band reads this far ABOVE the decal's spine in its inner
                                       # half (the hairs grow up from their roots there), fading to 0 at the tail
                                       # (render - geometry on a dressed Tess: 0.6-0.9 mm inner, 0 at the tail, 6 mm hairs)
MOVED = ("drop", "lift", "tilt", "apart")
BROWS = (([70, 63, 105, 66, 107], [46, 53, 52, 65, 55]), ([300, 293, 334, 296, 336], [276, 283, 282, 295, 285]))
BOUNDS = {"drop": (-0.014, 0.014), "tilt": (-25.0, 25.0), "apart": (-0.006, 0.008), "fall": (0.0, 1.6),
          "thickness": (0.35, 2.0), "taper": (0.2, 0.97)}


def _frame(P):
    from .likeness_eyes import frame
    ex, ey = frame(P)
    return np.asarray(ex, float), np.asarray(ey, float)


def columns(P) -> list:
    """Per side (subject's right, left): {"o" (the inner end, px), "sx" (+-1: the way the brow runs along ex), "xs"
    (COLS along the span, px), "yc" (the detector band's middle at each column, px along ey)} in the face's frame."""
    P = np.asarray(P, float)[:, :2]
    ex, ey = _frame(P)
    out = []
    for up, lo in BROWS:
        pts = np.r_[P[up], P[lo]]
        x, y = pts @ ex, pts @ ey
        mid = float(0.5 * (P[468] + P[473]) @ ex)
        inner, outer = (x.max(), x.min()) if x.mean() < mid else (x.min(), x.max())
        xs = inner + COLS * (outer - inner)
        xu, yu = P[up] @ ex, P[up] @ ey
        xl, yl = P[lo] @ ex, P[lo] @ ey
        ou, ol = np.argsort(xu), np.argsort(xl)
        yc = 0.5 * (np.interp(xs, xu[ou], yu[ou]) + np.interp(xs, xl[ol], yl[ol]))
        out.append({"xs": xs, "yc": yc, "inner": float(inner), "outer": float(outer)})
    return out


def band(img, P, mmpx: float, scale: float = 1.0, origin=(0.0, 0.0)) -> list:
    """The brow hair on a picture, per side and column (columns(P)): arrays "low", "core", "top" (px along the face's
    down axis ey; low = the edge toward the eye), "contrast" (band core against the skin under it, 0..1), "xs".
    P: the detector's points in the PICTURE's pixels; the image may be a crop / enlargement of that picture
    (image px = (picture px - origin) * scale), so a render through the same camera is read at the photo's own columns."""
    from . import lidfold
    P = np.asarray(P, float)[:, :2]
    ex, ey = _frame(P)
    L = lidfold._lum(img)
    o = np.asarray(origin, float)
    step = 0.05                                        # mm
    hh = np.arange(-REACH, REACH + 1e-9, step) / mmpx  # px along ey from the detector band's middle
    strip = np.linspace(-0.75, 0.75, 7) / mmpx
    g = np.exp(-0.5 * (np.arange(-30, 31) * step / 0.4) ** 2)
    g /= g.sum()
    out = []
    for c in columns(P):
        low, core, top, con = [], [], [], []
        for x, yc in zip(c["xs"], c["yc"]):
            prof = np.mean([lidfold._bilinear(L, *(((x + w) * ex + (yc + hh)[:, None] * ey - o) * scale).T) for w in strip], 0)
            sm = np.convolve(np.pad(prof, 30, mode="edge"), g, mode="valid")
            n = len(sm)
            a, b = int(0.2 * n), int(0.8 * n)
            ic = a + int(np.argmin(sm[a:b]))
            skin_up = float(np.percentile(sm[:ic], 85)) if ic > 3 else sm[0]       # over the brow (smaller ey)
            skin_dn = float(np.percentile(sm[ic:], 85))                           # under it, toward the eye
            i = ic
            while i > 0 and sm[i] < 0.5 * (skin_up + sm[ic]):
                i -= 1
            j = ic
            while j < n - 1 and sm[j] < 0.5 * (skin_dn + sm[ic]):
                j += 1
            top.append(yc + hh[i])
            low.append(yc + hh[j])
            core.append(yc + hh[ic])
            con.append((skin_dn - sm[ic]) / max(skin_dn, 1e-6))
        out.append({"xs": np.asarray(c["xs"]), "low": np.array(low), "core": np.array(core), "top": np.array(top),
                    "contrast": np.array(con)})
    return out


# ---- the decal on the model ------------------------------------------------------------------------------------------

def _spine(t, fall):
    return 0.56 - 0.2 * np.sin(np.clip(t / 0.62, 0, 1) * np.pi / 2) + 0.3 * fall * np.clip((t - 0.62) / 0.38, 0, 1) ** 1.6


def _half(t, thickness, taper):
    return thickness * (0.03 + 0.14 * np.clip((t + 0.02) / 0.12, 0, 1) * (1 - taper * np.clip((t - 0.25) / 0.75, 0, 1) ** 0.9))


def default_thickness(spec: dict) -> float:
    """The band thickness the skin uses when hair.brows has none (skin_features: thinner for a woman)."""
    sx = (spec.get("skin") or {}).get("sex")
    if sx is None:
        return 1.0
    return 1.0 - 0.32 * float(np.clip(1 - 2 * float(sx), 0, 1)) + 0.12 * float(np.clip(2 * float(sx) - 1, 0, 1))


def decal(J: dict, o: dict, side: int = 1):
    """The brow decal's frame as skin_features lays it (side +1 the subject's left, -1 the mirrored right): centre,
    right (toward the outer end), up, width, height (m)."""
    from .skin import interocular
    a_, m_, b_ = (np.asarray(J[f"lm_brow_{k}.L"], float).copy() for k in ("inner", "mid", "outer"))
    io = interocular(J)
    width = 1.22 * float(np.linalg.norm(b_ - a_))
    c = 0.5 * (a_ + b_)
    c[2] = (a_[2] + 2 * m_[2] + b_[2]) / 4 - 0.02 * io
    c[1] = m_[1]
    c[2] -= float(o.get("drop", 0.0))
    li, lo_ = (float(x) for x in (o.get("lift") or (0.0, 0.0)))
    c[2] += 0.5 * (li + lo_)
    c[0] += float(o.get("apart", 0.0))
    d = np.array([0.42, -1.0, 0.12])
    d /= np.linalg.norm(d)
    slope = float(np.degrees(np.arctan2(b_[2] - a_[2], np.linalg.norm((b_ - a_)[:2])))) * float(o.get("arch", 1.0))
    slope += float(o.get("tilt", 0.0)) + float(np.degrees(np.arctan2(lo_ - li, width)))
    up = np.array([0, 0, 1.0])
    up = up - (up @ d) * d
    up /= np.linalg.norm(up)
    right = np.cross(up, d)
    rot = np.radians(slope)
    right, up = np.cos(rot) * right + np.sin(rot) * up, -np.sin(rot) * right + np.cos(rot) * up
    if side < 0:
        M = np.array([-1.0, 1, 1])
        c, right, up = c * M, right * M, up * M
    return c, right, up, width, 0.42 * width


def model_band(J: dict, V: np.ndarray, cam: dict, o: dict, thickness: float, xs_by_side: list, ex, ey, n: int = 40) -> list:
    """The decal's band on the head (vertices V) through the camera, per side (right, left) at picture columns
    xs_by_side (px along ex): {"low", "mid", "top"} px along ey (NaN where the brow does not reach), and "inner" /
    "outer" (the band's ends along ex)."""
    from . import humanfit
    fall, taper = float(o.get("fall", 1.0)), float(o.get("taper", 0.82))
    out = []
    for s, sd in enumerate((-1, 1)):
        c, right, up, w, h = decal(J, o, sd)
        near = np.flatnonzero((np.linalg.norm(V - c, axis=1) < 0.06) & (V[:, 1] < c[1] + 0.02))
        Q = V[near]
        uv = np.c_[(Q - c) @ right, (Q - c) @ up]
        P2 = humanfit.project(cam, Q)
        t = np.linspace(0.03, 0.99, n)
        u = ((0.04 + 0.92 * t) - 0.5) * w
        sp_ = (0.5 - _spine(t, fall)) * h + GROW * float(o.get("length", 0.006)) * (1 - np.clip((t - 0.55) / 0.4, 0, 1))
        hf = EDGE * _half(t, thickness, taper) * h
        lines = {}
        for key, v in (("mid", sp_), ("low", sp_ - hf), ("top", sp_ + hf)):
            pts = []
            for ui, vi in zip(u, v):
                d2 = (uv[:, 0] - ui) ** 2 + (uv[:, 1] - vi) ** 2
                k = np.argsort(d2)[:10]
                A = np.c_[uv[k], np.ones(len(k))]
                co = np.linalg.lstsq(A, P2[k], rcond=None)[0]      # a local affine map decal (u, v) -> picture
                pts.append(np.array([ui, vi, 1.0]) @ co)
            lines[key] = np.array(pts)
        r = {}
        xm = lines["mid"] @ ex
        r["inner"], r["outer"] = float(xm[0]), float(xm[-1])
        for key, pts in lines.items():
            x, y = pts @ ex, pts @ ey
            oo = np.argsort(x)
            r[key] = np.interp(xs_by_side[s], x[oo], y[oo], left=np.nan, right=np.nan)
        out.append(r)
    return out


def _inputs(name: str, spec: dict | None = None):
    from PIL import Image
    from . import blockin as bi, humanfit, likeness, skin_look, store
    spec = store.load(name) if spec is None else spec
    rj = bi._refs(name)
    vi = bi._front(rj)
    v, cam = rj["views"][vi], rj["cameras"][vi]
    img = Image.open(v["image"]).convert("RGB")
    P = bi.detect_view(img, v)
    if P is None:
        raise ValueError("brows: the detector found no face on the front picture")
    P = np.asarray(P, float)[:, :2]
    st = humanfit.state(spec["base"])
    return {"spec": spec, "cam": cam, "img": img, "P": P, "V": np.asarray(st["tpl"]["P"], float),
            "J": skin_look._J(spec), "mm": likeness._mm_per_px(cam, st["L"][27:48])}


def errors(pb: list, mb: list, mm: float) -> dict:
    """Model band - picture band at the used columns, mm at the model, + = the model's brow is LOWER (toward the eye):
    per column (both sides' mean) for the lower edge and the middle line, their rms, the thickness difference."""
    lo, mid, th = [], [], []
    for p, m in zip(pb, mb):
        ok = (p["contrast"] >= MIN_CONTRAST) & np.isfinite(m["mid"])
        pm = 0.5 * (p["low"] + p["top"])
        lo.append(np.where(ok, (m["low"] - p["low"]) * mm, np.nan))
        mid.append(np.where(ok, (m["mid"] - pm) * mm, np.nan))
        th.append(np.where(ok, ((m["low"] - m["top"]) - (p["low"] - p["top"])) * mm, np.nan))
    lo, mid, th = (np.array(a) for a in (lo, mid, th))
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # (a column neither side reads: NaN, not a warning)
        return {"low": np.nanmean(lo, 0), "mid": np.nanmean(mid, 0), "thick": np.nanmean(th, 0),
                "low_rms": float(np.sqrt(np.nanmean(lo ** 2))), "mid_rms": float(np.sqrt(np.nanmean(mid ** 2))),
                "thick_mean": float(np.nanmean(th)), "n": int(np.isfinite(mid).sum())}


def fit(name: str, spec: dict | None = None, log=None) -> dict:
    """skin.hair.brows' placement and band shape from the front picture: least squares over drop, tilt, apart, fall,
    thickness, taper on the band's middle line, its thickness and its inner end, at COLS across each brow. Returns
    {"brows" (the new hair.brows dict: the old one's colour / density / length / soft kept, lift folded in), "before",
    "after" (errors()), "picture" (the band over the eye... per column), "text"}."""
    from scipy.optimize import least_squares
    q = _inputs(name, spec)
    spec, cam, P, mm, J, V = q["spec"], q["cam"], q["P"], q["mm"], q["J"], q["V"]
    ex, ey = _frame(P)
    pb = band(q["img"], P, mm)
    if sum(int((p["contrast"] >= MIN_CONTRAST).sum()) for p in pb) < 6:
        raise ValueError("brows: the picture's brow hair is too faint to read (fair, sparse or covered brows): set "
                         "skin.hair.brows by eye against a dressed look")
    xs = [p["xs"] for p in pb]
    hb = ((spec.get("skin") or {}).get("hair") or {}).get("brows")
    old = dict(hb) if isinstance(hb, dict) else {}
    th0 = float(old.get("thickness", default_thickness(spec)))
    keys = ("drop", "tilt", "apart", "fall", "thickness", "taper")
    unit = np.array([0.001, 1.0, 0.001, 0.1, 0.1, 0.1])
    cols_in = columns(P)

    def unpack(x):
        o = {k: v for k, v in old.items() if k not in MOVED}
        o.update({k: float(v) for k, v in zip(keys, x * unit)})
        return o

    def resid(x):
        o = unpack(x)
        mb = model_band(J, V, cam, o, o["thickness"], xs, ex, ey)
        r = []
        for s, (p, m) in enumerate(zip(pb, mb)):
            ok = p["contrast"] >= MIN_CONTRAST
            pm = 0.5 * (p["low"] + p["top"])
            dm = np.where(np.isfinite(m["mid"]), (m["mid"] - pm) * mm, 0.0)   # (past the decal's end: not a target)
            dt = np.where(np.isfinite(m["mid"]), ((m["low"] - m["top"]) - (p["low"] - p["top"])) * mm, 0.0)
            r += list(np.where(ok, dm, 0.0)) + list(0.5 * np.where(ok, dt, 0.0))
            r.append(0.3 * (m["inner"] - cols_in[s]["inner"]) * mm)   # (the detector's inner end: a weak anchor for apart)
        return np.nan_to_num(np.array(r, float))

    li, lo_ = (float(v) for v in (old.get("lift") or (0.0, 0.0)))
    x0 = np.array([float(old.get("drop", 0.0)) - 0.5 * (li + lo_), float(old.get("tilt", 0.0)), float(old.get("apart", 0.0)),
                   float(old.get("fall", 1.0)), th0, float(old.get("taper", 0.82))]) / unit
    lo_b = np.array([BOUNDS[k][0] for k in keys]) / unit
    hi_b = np.array([BOUNDS[k][1] for k in keys]) / unit
    before = errors(pb, model_band(J, V, cam, old, th0, xs, ex, ey), mm)
    sol = least_squares(resid, np.clip(x0, lo_b + 1e-6, hi_b - 1e-6), bounds=(lo_b, hi_b), diff_step=0.02, x_scale=1.0)
    new = unpack(sol.x)
    new = {k: (round(v, 5) if k in ("drop", "apart") else round(v, 3) if isinstance(v, float) else v) for k, v in new.items()}
    after = errors(pb, model_band(J, V, cam, new, new["thickness"], xs, ex, ey), mm)
    if log:
        log(f"brows fit: mid rms {before['mid_rms']:.2f} -> {after['mid_rms']:.2f} mm, lower edge rms "
            f"{before['low_rms']:.2f} -> {after['low_rms']:.2f} mm")
    txt = (f"BROWS from the picture (hair band at {after['n']} columns, mm at the model; + = ours lower): middle line rms "
           f"{before['mid_rms']:.1f} -> {after['mid_rms']:.1f} mm, lower edge rms {before['low_rms']:.1f} -> "
           f"{after['low_rms']:.1f} mm, band thickness {before['thick_mean']:+.1f} -> {after['thick_mean']:+.1f} mm; "
           f"skin.hair.brows: " + ", ".join(f"{k} {new[k]:g}" for k in keys))
    return {"brows": new, "before": before, "after": after, "picture": pb, "text": txt, "mm": mm}


def apply(name: str, out: str | None = None, log=None) -> dict:
    """fit(name) written to <out> (default: name itself) as skin.hair.brows. Paint only: no geometry changes."""
    import shutil
    from . import store
    r = fit(name, log=log)
    sp = copy.deepcopy(store.load(name))
    sp.setdefault("skin", {}).setdefault("hair", {})["brows"] = r["brows"]
    dst = out or name
    store.save(dst, sp, "brows placed from the front picture (blockin_brows.fit)", checked=False)
    if dst != name:
        shutil.copy(store.HOME / name / "human_refs.json", store.HOME / dst / "human_refs.json")
    r["model"] = dst
    return r


def check(name: str) -> dict:
    """The model's brow hair against the picture's, as placed now: errors() + a line of text (WARNING past 1.5 mm)."""
    q = _inputs(name)
    ex, ey = _frame(q["P"])
    pb = band(q["img"], q["P"], q["mm"])
    hb = ((q["spec"].get("skin") or {}).get("hair") or {}).get("brows")
    o = dict(hb) if isinstance(hb, dict) else {}
    e = errors(pb, model_band(q["J"], q["V"], q["cam"], o, float(o.get("thickness", default_thickness(q["spec"]))),
                              [p["xs"] for p in pb], ex, ey), q["mm"])
    bad = e["n"] >= 6 and e["low_rms"] > 1.5
    e["text"] = ((("WARNING: " if bad else "") + f"brow hair vs the picture: lower edge {e['low_rms']:.1f} mm rms off (mean "
                  f"{float(np.nanmean(e['low'])):+.1f} mm, + = ours lower, toward the eye), middle line {e['mid_rms']:.1f} mm"
                  + ("; place it from the picture: brow_read(name, match=True)" if bad else ""))
                 if e["n"] >= 6 else "brow hair vs the picture: the picture's brows are too faint to read")
    return e


def _json(e: dict) -> str:
    return json.dumps({k: (np.round(v, 2).tolist() if isinstance(v, np.ndarray) else v) for k, v in e.items()})
