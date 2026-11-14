"""The picture's evidence: the limbus, the iris' scale and check, photo and ruler evidence, the crease target, the socket. Part of the block-in's eyes (blockin_eyes.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import blockin_eyes
from .blockin_eyes_reader import crease_shape

def limbus(img, P) -> list:
    """The iris by its LIMBUS edge, per eye (subject's right, left): {"r_px", "detector_px", "rgb", "centre"}.
    MediaPipe's iris points are a model's guess of the ring: they under-read the visible limbus by 6 % on Tess's photo
    and by 19 % on our own renders (gnmbrow), so "iris radii" from them are not one unit across pictures. From the
    detector's iris centre, luminance along rays in the two lateral sectors (+-35 deg about the eye line: the lids
    cover the rest); the radius of the steepest dark -> light step within 0.5-1.9 detector radii, median over the rays,
    the centre re-seated once between the two sides. rgb: the iris ring's mean colour (0.5-0.85 r, the brightest 20 %
    (catch lights) and darkest 10 % dropped), sRGB 0..1."""
    from . import lidfold
    from .likeness_eyes import frame
    P = np.asarray(P, float)[:, :2]
    L = lidfold._lum(img)
    A = np.asarray(img.convert("RGB"), float) / 255.0
    ex, ey = (np.asarray(v, float) for v in frame(P))
    H, W = L.shape[:2]
    out = []
    for s in (0, 1):
        c = P[lidfold.IRIS_C[s]].copy()
        r0 = float(np.mean([np.linalg.norm(P[i] - c) for i in lidfold.IRIS_RIM[s]]))
        rr = np.arange(0.5 * r0, 1.9 * r0, 0.1)
        sm = max(1, int(round(0.04 * r0 / 0.1)))
        angs = np.radians(np.arange(-35, 36, 5))
        sides = [r0, r0]
        for _ in range(2):
            sides = []
            for sg in (-1, 1):
                rs = []
                for a in angs:
                    d = sg * (np.cos(a) * ex + np.sin(a) * ey)
                    prof = lidfold._bilinear(L, *(c + rr[:, None] * d).T)
                    prof = np.convolve(prof, np.ones(2 * sm + 1) / (2 * sm + 1), mode="same")
                    g = np.gradient(prof)
                    g[:sm + 1] = g[-sm - 1:] = 0
                    rs.append(rr[int(np.argmax(g))])
                sides.append(float(np.median(rs)))
            c = c + 0.5 * (sides[1] - sides[0]) * ex
        r = 0.5 * (sides[0] + sides[1])
        cols = []
        for sg in (-1, 1):
            for a in angs:
                d = sg * (np.cos(a) * ex + np.sin(a) * ey)
                for q in np.linspace(0.5, 0.85, 8) * r:
                    p = c + q * d
                    cols.append(A[int(np.clip(round(p[1]), 0, H - 1)), int(np.clip(round(p[0]), 0, W - 1))])
        cols = np.array(cols)
        lum = cols.mean(1)
        keep = (lum <= np.percentile(lum, 80)) & (lum >= np.percentile(lum, 10))
        out.append({"r_px": float(r), "detector_px": r0, "rgb": cols[keep].mean(0).tolist(), "centre": c.tolist()})
    return out


def iris_scale(img, P) -> float:
    """detector iris radius / limbus radius (both eyes' mean; 1.0 when the limbus read is out of LIMBUS_OK)."""
    try:
        lb = limbus(img, P)
    except Exception:  # noqa: BLE001  (a tiny or cut-off eye: keep the detector's radius)
        return 1.0
    k = float(np.mean([e["detector_px"] / max(e["r_px"], 1e-6) for e in lb]))
    if min(e["detector_px"] for e in lb) < blockin_eyes.MIN_IRIS_PX:
        return 1.0
    return k if blockin_eyes.LIMBUS_OK[0] <= k <= blockin_eyes.LIMBUS_OK[1] else 1.0


def iris_check(name: str) -> dict:
    """The picture's iris against the model's drawn one, both in mm AT THE MODEL (the front picture's limbus through
    its fitted camera): {"photo_mm", "model_mm", "ratio", "eye_radius" (the block-in key's value that makes them
    equal), "iris_rgb" / "iris_hex" (the picture's iris ring colour), "text"}. The lids are matched in iris radii, so a
    drawn iris k x too big opens the eye k x too tall and crowds the brow (Tess: 12.66 mm drawn, 10.7 mm hers)."""
    from PIL import Image
    from . import humanfit, store
    from . import likeness_render
    from . import blockin_clay, blockin_models
    rj = blockin_models._refs(name)
    vi = blockin_clay._front(rj)
    v, cam = rj["views"][vi], rj["cameras"][vi]
    img = Image.open(v["image"]).convert("RGB")
    P = blockin_clay.detect_view(img, v)
    if P is None:
        raise ValueError("iris_check: the detector found no face on the front picture")
    lb = limbus(img, P)
    spec = store.load(name)
    base = spec["base"]
    st = humanfit.state(base)
    from . import base_implied
    native = base_implied.eye_native(spec) is not None   # GNM's own eyeball: the iris is its limbus (identity eyes_000)
    mm = likeness_render._mm_per_px(cam, st["L"][27:48])
    photo = 2 * float(np.mean([e["r_px"] for e in lb])) * mm
    det_px = float(np.mean([e["detector_px"] for e in lb]))
    kd = det_px / max(float(np.mean([e["r_px"] for e in lb])), 1e-6)
    if det_px < blockin_eyes.MIN_IRIS_PX or not blockin_eyes.LIMBUS_OK[0] <= kd <= blockin_eyes.LIMBUS_OK[1]:
        det = 2 * det_px * mm
        r0 = float(st["head"].get("eye_r", 0.012))
        return {"photo_mm": None, "detector_mm": det,
                "model_mm": 2000 * (base_implied.drawn_iris(spec, r0) if native else 0.51 * 0.985 * r0),
                "ratio": None, "eye_radius": None, "eyes_000": None, "iris_rgb": None, "iris_hex": None,
                "text": (f"IRIS: not readable on the front picture (iris radius {det_px:.1f} px, {mm:.2f} mm / px: the "
                         f"limbus needs {blockin_eyes.MIN_IRIS_PX:.0f} px; the detector's ring gives {det:.1f} mm +- {2 * mm:.1f}). "
                         f"Use a closer picture of the eyes to set the iris' size (block_in_step {{\"iris_mm\": mm}}) / colour")}
    r_ball = float(st["head"].get("eye_r", 0.012))
    model = 2000 * base_implied.drawn_iris(spec, r_ball) if native else 2 * 0.51 * 0.985 * r_ball * 1000
    k_eye = float(base["head"].get("eyes") or 1.0)
    want = None if native else r_ball * photo / model / k_eye
    e000 = None
    if native:
        try:
            e000 = base_implied.limbus_identity(spec, photo)["eyes_000"]
        except ValueError:
            e000 = None
    rgb = np.mean([e["rgb"] for e in lb], 0)
    hx = "#%02x%02x%02x" % tuple(int(round(255 * float(x))) for x in rgb)
    txt = (f"IRIS: the picture's limbus is {photo:.1f} mm at the model (fitted camera), the model draws {model:.1f} mm "
           f"({model / photo:.2f} x)")
    if native and abs(model / photo - 1) > 0.05:
        txt += (f": block_in_step {{\"iris_mm\": {photo:.2f}}} sets GNM's limbus component (identity eyes_000 -> "
                + (f"{e000:+.2f} sd" if e000 is not None else "past 3 sd: check the read")
                + "): the eyeball stays GNM's 14.6 mm sphere x the head's scale (its lids are shaped on it), the iris "
                "and the cornea's base change with the identity. skin.eyes.iris_size still overrides the DRAWN iris alone")
    elif abs(model / photo - 1) > 0.05:
        txt += (f": set skin.eyes.iris_size {photo / 1000:.4f} (the drawn iris). This head OVERRIDES GNM's eyeball "
                f"(base.head.eye_radius {r_ball / k_eye:.4f}: our ball, which GNM's lids stand ~0.5 mm off); do not shrink it "
                f"further for the iris. A rebuild (block_in_start) or block_in_step {{\"eye_radius\": 0}} gives GNM's own "
                f"ball, where the iris is the identity's limbus (block_in_step {{\"iris_mm\": {photo:.2f}}})")
    txt += f". The picture's iris ring colour: {hx} (skin.eyes.iris; check it rendered: the eye picture adds its own contrast)"
    return {"photo_mm": photo, "model_mm": model, "ratio": model / photo, "eye_radius": want, "eyes_000": e000, "iris_rgb": rgb.tolist(),
            "iris_hex": hx, "text": txt}


def photo_evidence(img, view: dict) -> dict:
    """{"up", "lo"} (iris radii, both eyes' mean), {"tps" (mm at the 11.7 mm iris), "dark"} (median over the middle
    columns of both eyes), from MediaPipe + lidfold.read_lid on the front picture. The iris' radius is the LIMBUS's
    (limbus(); "iris_k" = detector radius / limbus radius, 1.0 when it could not be read): up / lo / tps are scaled by
    it, so they are in the picture's true iris radii like the model's own reads."""
    from . import lidfold
    from . import blockin_clay, blockin_lid_measure
    lp = blockin_lid_measure.lid_photo(img, view)
    if not lp:
        raise ValueError("eye step: the detector found no face (irises) on the front picture")
    P = np.asarray(blockin_clay.detect_view(img, view), float)
    kk = iris_scale(img, P)
    cols = lidfold.read_lid(img, P)
    tps = [c["tps"] for e in cols for c in e if np.isfinite(c.get("tps", np.nan)) and c.get("dark", 0) >= blockin_eyes.DARK_LINE]
    dk = [c["dark"] for e in cols for c in e]
    hooded = len(tps) < 2   # no fold line in most columns: the fold hangs over the platform
    # the fold line's path across the lid: per column (inner third, pupil, outer third), both eyes' lines that read
    tcols = []
    for k in range(3):
        v = [e[k]["tps"] for e in cols if np.isfinite(e[k].get("tps", np.nan)) and e[k].get("dark", 0) >= blockin_eyes.DARK_LINE]
        tcols.append(float(np.median(v)) if v else np.nan)
    return {"up": kk * float(np.mean([lp[s]["upper"] for s in lp])), "lo": kk * float(np.mean([lp[s]["lower"] for s in lp])),
            "tps": kk * float(np.median(tps)) if not hooded else blockin_eyes.HOODED_SHOW, "dark": float(np.median(dk)) if dk else 0.0,
            "hooded": hooded, "tps_cols": [kk * t for t in tcols], "columns": cols, "iris_k": kk}


def ruler_evidence(name: str) -> dict:
    """The eye ruler's read of the front picture, both eyes' mean, mm at the model (eye_ruler.read through the fitted
    camera): {"up", "lo" (margins at RULER_COLS), "inner", "outer" (canthi (u, v)), "iris", "crease" (the fold line
    over the margin at RULER_COLS), "crease_dark", "crease_cols" (at u -5 / 0 / +5: the eye step's three sections;
    None when the line is fainter than DARK_LINE), "eyes" (per eye), "mm" (mm per picture px)}."""
    from PIL import Image
    from . import eye_ruler, humanfit, store
    from . import likeness_render
    from . import blockin_clay, blockin_models
    rj = blockin_models._refs(name)
    vi = blockin_clay._front(rj)
    v, cam = rj["views"][vi], rj["cameras"][vi]
    img = Image.open(v["image"]).convert("RGB")
    P = blockin_clay.detect_view(img, v)
    if P is None:
        raise ValueError("eye ruler: the detector found no face on the front picture")
    st = humanfit.state(store.load(name)["base"])
    mm = likeness_render._mm_per_px(cam, st["L"][27:48])
    eyes = eye_ruler.read(img, P, mm)
    m = eye_ruler.mean(eyes)
    cr = np.asarray(m["crease"], float)
    cc = [float(np.interp(x, blockin_eyes.RULER_COLS[np.isfinite(cr)], cr[np.isfinite(cr)])) for x in (-5.0, 0.0, 5.0)] if np.isfinite(cr).sum() >= 3 else None
    m["crease_cols"] = cc if m["crease_dark"] >= 0.5 * blockin_eyes.DARK_LINE else None
    m["eyes"], m["mm"] = eyes, mm
    return m


def crease_target(name: str, heights) -> np.ndarray:
    """A crease template's PROFILE carried to the picture's fold line: per section, the template's crease (its most
    recessed point 1.2-6 mm up) is moved to heights[k] (mm over the margin; NaN: the template's own) by stretching the
    platform under it vertically and lifting the fold above it unchanged, then resampled at SECTION_S. The fold's make
    (crest over the crease, a short platform that doesn't recede, the line parallel to the lashes) comes from the
    template, its height and path from the picture (gnmcrease 2: the templates' own height, ~2.5 mm, was #376's, not the
    person's)."""
    T = crease_shape(name)
    out = np.empty_like(T)
    for k in range(len(T)):
        P = np.r_[[[0.0, 0.0]], T[k]]
        low = (P[:, 1] > 1.2) & (P[:, 1] < 6.0)
        ic = int(np.argmin(np.where(low, P[:, 0], np.inf)))
        hc = P[ic, 1]
        H = float(heights[k]) if heights is not None and np.isfinite(heights[k]) else hc
        Q = P.copy()
        f = max(H, 0.5) / max(hc, 0.3)
        Q[:ic + 1, 1] *= f
        Q[ic + 1:, 1] += (f - 1.0) * hc
        d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
        s = np.clip(blockin_eyes.SECTION_S, 0, d[-1])
        out[k] = np.c_[np.interp(s, d, Q[:, 0]), np.interp(s, d, Q[:, 1])]
    return out


def socket(c, expression: dict) -> dict:
    """The socket readings (SOCKET, humanmacro z-scores) of identity c with the head's expression applied: GNM's mesh
    (humanmacro.head) + the expression basis, so a lid tucked back by the eye-region expression counts."""
    from . import humanmacro as hm
    from . import base_identity
    g = base_identity._gnm_data()
    names = {str(n): i for i, n in enumerate(g["expression_names"])}
    V = hm.head(np.asarray(c, float))
    for k, v in (expression or {}).items():
        if v and k in names:
            if k not in blockin_eyes._EB:
                B = np.asarray(g["expression_basis"][names[k]], float)
                blockin_eyes._EB[k] = np.stack([B[..., 0], -B[..., 2], B[..., 1]], -1)   # (humanmacro's world frame)
            V = V + float(v) * blockin_eyes._EB[k]
    z = hm.read(V=V)
    return {k: float(z[k]) for k in blockin_eyes.SOCKET}
