"""The eyes: the iris profile, its zones and the iris read. Part of the skin projection (skin_project.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import skin_project
from .skin_project import _lin, _srgb, lab

def iris_profile(img, view: dict) -> dict | None:
    """The irises of one picture as a radial read at the picture's OWN limbus (blockin_eyes_evidence.limbus: MediaPipe's ring
    under-reads it), over the pixels INSIDE the lid margins' contour (the detector's own lid points, drawn in by a
    pixel: no lid skin, whatever the hooding; a fixed sector took lid skin on a hooded eye), both eyes pooled, the
    brightest 15 % of each ring (catch lights) and the darkest 10 % (lash shadow, the lid's edge) left out:
    {"r": bin centres (share of the limbus radius), "rgb": (bins, 3) linear medians, "n", "radius_px", "pupil": the
    pupil's edge (the steepest dark -> light step inside 0.15-0.6), "open": the share of the iris disc the lids leave};
    None without a detection or under IRIS_PX."""
    from PIL import Image, ImageDraw
    from . import blockin_eyes_evidence
    from . import blockin_clay
    P = blockin_clay.detect_view(img, view)
    if P is None or len(P) < 478:
        return None
    P = np.asarray(P, float)[:, :2]
    try:
        lb = blockin_eyes_evidence.limbus(img, P)
    except Exception:  # noqa: BLE001
        return None
    a = _lin(np.asarray(img.convert("RGB"), float) / 255.0)
    H, W = a.shape[:2]
    px = [[] for _ in range(len(skin_project.IRIS_BINS) - 1)]
    rad, opens = [], []
    for s_, e in enumerate(lb):
        r, c = float(e["r_px"]), np.asarray(e["centre"], float)
        if r < skin_project.IRIS_PX:
            continue
        m = Image.new("L", (W, H), 0)
        ring = P[list(skin_project.EYE_RING[s_])]
        cen = ring.mean(0)
        ring = cen + (ring - cen) * (1 - 1.0 / max(np.linalg.norm(ring - cen, axis=1).mean(), 1.0))     # in by ~1 px
        ImageDraw.Draw(m).polygon([tuple(q) for q in ring], fill=255)
        inside = np.asarray(m) > 0
        y0, y1, x0, x1 = int(c[1] - 1.25 * r), int(c[1] + 1.25 * r) + 1, int(c[0] - 1.25 * r), int(c[0] + 1.25 * r) + 1
        if y0 < 0 or x0 < 0 or y1 >= H or x1 >= W:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d = np.hypot(xx - c[0], yy - c[1]) / r
        ok = inside[yy, xx]
        opens.append(float(ok[d < 1.0].mean()))
        rad.append(r)
        for k in range(len(px)):
            q = ok & (d >= skin_project.IRIS_BINS[k]) & (d < skin_project.IRIS_BINS[k + 1])
            px[k].append(a[yy[q], xx[q]])
    if not rad:
        return None
    rgb, n = [], []
    for q in px:
        q = np.concatenate(q) if q else np.zeros((0, 3))
        if len(q) >= 8:
            lum = q @ skin_project.Y
            q = q[(lum <= np.percentile(lum, 85)) & (lum >= np.percentile(lum, 10))]
        rgb.append(np.median(q, 0) if len(q) else np.full(3, np.nan))
        n.append(len(q))
    rgb = np.asarray(rgb)
    rc = 0.5 * (skin_project.IRIS_BINS[:-1] + skin_project.IRIS_BINS[1:])
    lum = rgb @ skin_project.Y
    g = np.gradient(np.where(np.isfinite(lum), lum, 0.0))
    sel = (rc > 0.15) & (rc < 0.6)
    pupil = float(rc[sel][int(np.argmax(g[sel]))]) if sel.any() else 0.36
    return {"r": rc, "rgb": rgb, "n": n, "radius_px": float(np.mean(rad)), "pupil": pupil, "open": float(np.mean(opens))}


def _zones(prof: dict) -> dict:
    """{zone: linear rgb median} of a radial profile: inner (pupil's edge + 0.08 .. 0.55), outer, limbal."""
    out = {}
    for k, (lo, hi) in skin_project.IRIS_ZONES.items():
        lo = max(lo, prof["pupil"] + 0.08) if k == "inner" else lo
        v = prof["rgb"][(prof["r"] >= lo) & (prof["r"] < hi)]
        v = v[np.isfinite(v).all(1)]
        out[k] = np.median(v, 0) if len(v) else None
    return out


def _swatch_zones(eyes: dict, radius_px: float, pupil: float) -> dict:
    """The same zones read off OUR eye picture (skin_swatch.eye_image with these skin.eyes values), blurred to the
    photograph's resolution: what a parameter value gives through the same read (the calibration)."""
    from PIL import Image
    from scipy import ndimage
    from . import skin_swatch
    hx = lambda h: [int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]  # noqa: E731
    span = 2.1
    path = skin_swatch.eye_image(hx(eyes["iris"]), pupil, 0.0, (0.92, 0.89, 0.85), 0, span, limbal=float(eyes.get("limbal", 0.72)),
                                 contrast=float(eyes.get("iris_contrast", 1.0)), limbal_width=float(eyes.get("limbal_width", 0.2)),
                                 inner=hx(eyes["iris_inner"]) if eyes.get("iris_inner") else None, inner_to=float(eyes.get("iris_inner_to", 0.55)))
    a = _lin(np.asarray(Image.open(path).convert("RGB"), float) / 255.0)
    S = a.shape[0]
    R = S / (2 * span)
    a = np.stack([ndimage.gaussian_filter(a[..., c], 0.6 * R / max(radius_px, 1.0)) for c in range(3)], -1)
    yy, xx = np.mgrid[0:S, 0:S]
    d = np.hypot(xx - (S - 1) / 2, yy - (S - 1) / 2) / R
    rgb = np.array([np.median(a[(d >= skin_project.IRIS_BINS[k]) & (d < skin_project.IRIS_BINS[k + 1])], 0) for k in range(len(skin_project.IRIS_BINS) - 1)])
    return _zones({"r": 0.5 * (skin_project.IRIS_BINS[:-1] + skin_project.IRIS_BINS[1:]), "rgb": rgb, "pupil": pupil})


def iris_read(profiles: list, gains: list, eyes0: dict | None = None) -> dict | None:
    """skin.eyes values from the views' iris profiles: {"iris" (#hex: toward the rim), "iris_inner" (#hex: round the
    pupil), "limbal" (0..1), "pupil" (the pupil's edge, share of the radius: reported), "px", "zones" (the picture's
    albedo per zone, sRGB), "text"}. Each zone's colour is the picture's (lightness x the gain of the skin under the
    eye: INFERRED, the eye taken to be lit as that skin; the picture's own hue), and the PARAMETERS are solved so that
    OUR eye picture, read the same way at the picture's resolution, gives those zones (a few fixed-point steps: the
    fibres, crypts and ring darken a colour by 20-65 %, so a parameter is not the colour it gives)."""
    rows = [(p, float(np.asarray(g, float) @ skin_project.Y)) for p, g in zip(profiles, gains) if p is not None]
    if not rows:
        return None
    want = {}
    for k in skin_project.IRIS_ZONES:
        v = [z * g for p, g in rows for z in [_zones(p)[k]] if z is not None]
        want[k] = np.median(v, 0) if v else None
    if want["outer"] is None:
        return None
    if want["inner"] is None:
        want["inner"] = want["outer"]
    px = float(np.mean([p["radius_px"] for p, _ in rows]))
    pupil = float(np.median([p["pupil"] for p, _ in rows]))
    hexs = lambda c: "#" + "".join(f"{int(round(255 * float(x))):02x}" for x in np.clip(_srgb(np.clip(c, 0, 1)), 0, 1))  # noqa: E731
    e = {**{k: v for k, v in (eyes0 or {}).items() if k in ("iris_contrast", "limbal_width")}, "iris": hexs(want["outer"]), "iris_inner": hexs(want["inner"]),
         "limbal": float((eyes0 or {}).get("limbal", 0.72))}
    par = {"iris": np.asarray(want["outer"], float).copy(), "iris_inner": np.asarray(want["inner"], float).copy()}
    for _ in range(5):
        got = _swatch_zones(e, px, pupil)
        if got["outer"] is None or got["inner"] is None:
            break
        par["iris"] = np.clip(par["iris"] * np.clip(want["outer"] / np.maximum(got["outer"], 1e-4), 0.5, 2.0), 0, 1)
        par["iris_inner"] = np.clip(par["iris_inner"] * np.clip(want["inner"] / np.maximum(got["inner"], 1e-4), 0.5, 2.0), 0, 1)
        if want["limbal"] is not None and got["limbal"] is not None:
            rw = float(want["limbal"] @ skin_project.Y) / max(float(want["outer"] @ skin_project.Y), 1e-5)
            rg = float(got["limbal"] @ skin_project.Y) / max(float(got["outer"] @ skin_project.Y), 1e-5)
            e["limbal"] = float(np.clip(e["limbal"] + 0.8 * (rg - rw), 0.0, 0.95))
        e["iris"], e["iris_inner"] = hexs(par["iris"]), hexs(par["iris_inner"])
    got = _swatch_zones(e, px, pupil)
    de = {k: (round(float(np.linalg.norm(lab(want[k]) - lab(got[k]))), 1) if want[k] is not None and got.get(k) is not None else None) for k in skin_project.IRIS_ZONES}
    out = {"iris": e["iris"], "iris_inner": e["iris_inner"], "limbal": round(e["limbal"], 2), "pupil": round(pupil, 2), "px": round(px, 1),
           "zones": {k: (hexs(v) if v is not None else None) for k, v in want.items()}, "left_dE": de,
           "open": round(float(np.mean([p["open"] for p, _ in rows])), 2)}
    out["text"] = (f"the picture's iris (albedo; lightness through the skin under the eye: INFERRED; the picture's own hue): round the pupil {out['zones']['inner']}, "
                   f"toward the rim {out['zones']['outer']}, the limbal ring {out['zones']['limbal']}; pupil's edge at {out['pupil']} of the radius; limbus {out['px']} px, "
                   f"{int(100 * out['open'])} % of the disc inside the lids. Parameters that give them through our eye picture: iris {out['iris']}, iris_inner {out['iris_inner']}, "
                   f"limbal {out['limbal']} (left over, Lab dE by zone: {de})")
    return out
