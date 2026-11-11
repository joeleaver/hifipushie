"""The nose's own reads: the nostril openings and the width from the wing's edge. Part of the face ruler (face_ruler.py has the overview)."""
from __future__ import annotations

import numpy as np

from .face_ruler import _C, _bil, _cam_points, _gnm, _proj_jac
from .face_ruler_camera import LM_PX, view_yaw
from .face_ruler_features import _gnm_to_model
from .face_ruler_outline import _silhouette_vertices

# ---- the NOSE's own read: the nostril openings (readmix, 2026-10-13) -----------------------------------------------------
# On two scanned heads the solved nose stayed 2-5 mm too WIDE with the front camera at its true distance: nothing read it (the
# class mean's nose is that much wider, and neither detector's nose points follow a narrow nose: MediaPipe's alar width +2.4
# / +5.5 mm there). The picture itself shows the nostril openings: dark, high contrast. Each opening's LATERAL and MEDIAL end
# along the line through both openings is read against the model's nostril RIM (GNM's exterior skin where it turns into the
# nostril: fixed vertices) through the view's camera.
NOSTRIL = False             # reference_views(nostrils=None) takes this. OFF: validated on ONE scanned head's front picture only (the


#                             other scanned head's tip hides its nostrils, our own renders have no dark openings): there the
#                             picture's opening ends 1.1 mm OUTSIDE the true rim on each side and 2.1 mm past it toward the midline
#                             (the half-depth contour is larger than GNM's rim loop): a bias known from one head is not a calibration
NOSTRIL_TURN = 30.0         # degrees: read in views turned less than this


SIG_NOSTRIL = (0.8, 1.2)    # mm: an opening's lateral end / its medial end (validated on scanned heads: spikes/readmix/nostril_eval.py)


NOSTRIL_ROI = 7.0           # mm round the model's rims that the picture is searched in


NOSTRIL_AREA = (3.0, 160.0) # mm2: an opening smaller / larger than this is not one (hidden under the tip; a moustache's shadow)


NOSTRIL_BIAS = (0.0, 0.0)   # mm: the picture's dark opening against the rim at the TRUE head (lateral, medial), taken out


def nostril_rims(head) -> list:
    """The model's nostril rims: per side (the subject's right: world -X first) the model vertices of GNM's EXTERIOR
    nose skin that border the nostril's interior."""
    key = ("nrim", len(head["gid"]))
    if key not in _C:
        from . import base as basemod
        g, gg = basemod._gnm_data(), _gnm()
        gr, T = gg["gr"], gg["sp"]["T"]
        Q = np.asarray(g["quads"], int)
        ext, sk, nose = gr["skin_exterior"], gr["skin"], gr["nose_region"]
        inn = sk & ~ext
        q = Q[(inn[Q].any(1)) & (ext[Q].any(1)) & (nose[Q].any(1))]
        rim = np.unique(q[ext[q]])
        Lt = gg["sp"]["WL"] @ T
        rim = rim[(np.abs(T[rim, 0]) < 0.03) & (np.abs(T[rim, 1] - Lt[33, 1]) < 0.02)]
        g2m = _gnm_to_model(head)
        _C[key] = [np.array([g2m[int(v)] for v in rim[(T[rim, 0] < 0) == neg] if int(v) in g2m], int) for neg in (True, False)]
    return _C[key]


def nostril_picture(img, centre, u, mmpx: float, roi_mm: float = NOSTRIL_ROI):
    """The picture's dark opening next to `centre` (px): its ends along u and across it, at half the depth between the
    opening's darkest tenth and the skin round it. -> {"lo", "hi" (px along u, from centre), "top", "bottom" (across),
    "area" mm2, "contrast"} | None."""
    from scipy import ndimage as ndi
    A = np.asarray(img.convert("L"), float) / 255.0
    H, W = A.shape
    r = int(round(roi_mm / mmpx))
    x0, y0 = int(round(centre[0])) - r, int(round(centre[1])) - r
    if x0 < 0 or y0 < 0 or x0 + 2 * r >= W or y0 + 2 * r >= H or r < 6:
        return None
    pat = ndi.gaussian_filter(A[y0:y0 + 2 * r + 1, x0:x0 + 2 * r + 1], max(0.3 / mmpx, 0.7))
    skin, dark = float(np.percentile(pat, 75)), float(np.percentile(pat, 2))
    if dark > 0.55 * skin:           # no dark opening here (the tip hides it; a flat frontal light fills it)
        return None
    lab, n = ndi.label(pat < dark + 0.5 * (skin - dark))
    if not n:
        return None
    yy, xx = np.mgrid[:pat.shape[0], :pat.shape[1]]
    best, bd = None, 1e9
    for i in range(1, n + 1):        # the component whose darkest part lies nearest the model's rim centre
        m = lab == i
        core = m & (pat <= np.percentile(pat[m], 30))
        d = float(np.hypot(xx[core].mean() - r, yy[core].mean() - r))
        if d < bd:
            best, bd = m, d
    area = float(best.sum()) * mmpx ** 2
    if bd * mmpx > 4.5 or not NOSTRIL_AREA[0] <= area <= NOSTRIL_AREA[1] or best[0].any() or best[-1].any() or best[:, 0].any() or best[:, -1].any():
        return None
    P = np.stack([xx[best] - r, yy[best] - r], 1).astype(float)
    a, b = P @ u, P @ np.array([-u[1], u[0]])
    return {"lo": float(a.min()), "hi": float(a.max()), "top": float(b.min()), "bottom": float(b.max()), "area": area, "contrast": 1 - dark / skin}


# ---- the NOSE's width from its WING's edge (readmix, 2026-10-14) ----------------------------------------------------------
# From the front the ala is drawn IN FRONT of the cheek: its outer edge is an occluding contour of the model (a vertex with a
# face turned to the camera and one turned away, in GNM's nose region) and in a photograph a dark line: the alar-facial
# groove's shadow, or the step from the lit wing to the cheek behind it. Per contour vertex the picture's luminance along
# the camera's horizontal, outward, and the read is where the chosen FEATURE lies against the model's contour, minus its
# BIAS measured at the truth on TRAIN subjects only (spikes/readmix/alar_eval.py); scored on the held-out ones.
ALAR = True                 # reference_views(alar=None) takes this. ON (2026-10-14): on the three HELD-OUT HSRD subjects (4 calls, the


#                             told-lens pooled start) the alar width error +1.7 / +1.1 / +1.7 -> +0.4 / +0.7 / +0.4 mm, nose base
#                             +0.6 / +1.4 / +0.6 -> -0.9 / +0.9 / -0.8, lower face 2.74 / 3.49 / 3.61 -> 2.93 / 3.11 / 3.03 mm
ALAR_TURN = 25.0            # degrees: read in views turned less than this


ALAR_WIN = (-2.5, 4.5)      # mm along the outward horizontal, from the model's contour, searched


ALAR_FEATURE = "edge"       # "valley" = the darkest point (the groove's shadow) | "edge" = the steepest fall going outward


ALAR_BIAS = 0.3             # mm: the feature against the TRUE contour (+ = outside it): the steepest fall lies 0.29 mm


#                             outside it on five TRAIN subjects (16 sides, sd 1.46); on the three HELD-OUT ones +0.15 (6 sides, sd 0.76)
SIG_ALAR = 1.0              # mm: one side's read (its contour vertices count as one)


ALAR_MIN = 0.04             # the least depth of the valley / step (luminance 0..1, against the profile's ends)


def alar_profiles(head, cam, img, step_mm: float = 0.2):
    """Per side (the subject's right, left) the model's alar contour vertices (model ids) and the picture's luminance
    along the camera's horizontal from each, outward: {"side", "v", "px", "u", "prof" (n, m), "t" (m,) mm, "mm1"}."""
    from scipy import ndimage as ndi
    gr = _gnm()["gr"]
    gid = np.asarray(head["gid"], int)
    nose = np.zeros(len(gid), bool)
    nose[gid >= 0] = gr["nose_region"][gid[gid >= 0]]
    sv, Xc, P = _silhouette_vertices(head, cam)
    sv = sv[nose[sv]]
    if len(sv) < 6:
        return []
    L = np.asarray(head["L"], float)
    V = np.asarray(head["V"], float)
    # the wing's band: from the nostril sill (lm 31 / 35) up to the tip's height (lm 30), in world height
    z0, z1 = float(L[[31, 35], 2].mean()) - 0.002, float(L[30, 2]) + 0.002
    mid = float(L[27:31, 0].mean())
    lum = np.asarray(img.convert("L"), float) / 255.0
    _, q = _cam_points(cam, L[[31, 35]])
    u = q[1] - q[0]
    u /= max(np.linalg.norm(u), 1e-9)                       # toward the subject's left in the picture
    mm1 = float(np.median(Xc[sv, 2]) / cam["f"] * 1000.0)
    lum = ndi.gaussian_filter(lum, max(0.25 / mm1, 0.5))
    t = np.arange(ALAR_WIN[0], ALAR_WIN[1] + 1e-9, step_mm)
    out = []
    for side, sg in ((0, -1.0), (1, 1.0)):
        m = (V[sv, 2] > z0) & (V[sv, 2] < z1) & (sg * (V[sv, 0] - mid) > 0.006)
        vv = sv[m]
        if len(vv) < 2:
            continue
        # per picture row band only the OUTERMOST contour vertex (the wing's own edge, not a fold inside it)
        p = P[vv]
        a = (p - p.mean(0)) @ u * sg
        rows = np.round((p @ np.array([-u[1], u[0]])) * mm1 / 0.8).astype(int)
        keep = [int(np.flatnonzero(rows == r_)[np.argmax(a[rows == r_])]) for r_ in np.unique(rows)]
        vv, p = vv[keep], p[keep]
        prof = np.array([_bil(lum, p_[0] + sg * u[0] * t / mm1, p_[1] + sg * u[1] * t / mm1) for p_ in p])
        out.append({"side": side, "v": vv, "px": p, "u": (sg * u).tolist(), "prof": prof, "t": t, "mm1": mm1})
    return out


def alar_feature(prof, t, feature: str = None):
    """The feature's place (mm along t) on one profile and its strength; None when too weak."""
    feature = feature or ALAR_FEATURE
    if feature == "valley":
        j = int(np.argmin(prof))
        if j in (0, len(prof) - 1):
            return None
        depth = float(min(prof[:j].max(), prof[j:].max()) - prof[j])
        if depth < ALAR_MIN:
            return None
        if 0 < j < len(prof) - 1:                    # sub-sample: a parabola through the three
            a_, b_, c_ = prof[j - 1], prof[j], prof[j + 1]
            den = a_ - 2 * b_ + c_
            off = 0.5 * (a_ - c_) / den if den > 1e-9 else 0.0
            return float(t[j] + off * (t[1] - t[0])), depth
        return float(t[j]), depth
    g = np.gradient(prof, t)
    j = int(np.argmin(g))                            # the steepest FALL going outward
    if -g[j] * 1.0 < ALAR_MIN:
        return None
    return float(t[j]), float(-g[j])


def _alar_obs(head, view):
    """Per side one read: the median feature place over the side's contour vertices against the model's contour (mm,
    + = the picture's wing reaches further out), moving with those vertices (their mean move along the outward direction)."""
    cam = view["cam"]
    if "gid" not in head or abs(view_yaw(cam)) > ALAR_TURN:
        return []
    out = []
    for pr in alar_profiles(head, cam, view["img"]):
        f = [alar_feature(pp, pr["t"]) for pp in pr["prof"]]
        ok = [i for i, x in enumerate(f) if x is not None]
        if len(ok) < 2:
            continue
        o = float(np.median([f[i][0] for i in ok])) - ALAR_BIAS
        vv = pr["v"][ok]
        Jp, mm1 = _proj_jac(cam, head, vv)
        n = np.asarray(pr["u"], float)
        out.append({"type": "alar", "view": view["kind"], "name": f"alar_{'rl'[pr['side']]}", "o": o, "n": n.tolist(),
                    "J": (n @ Jp) * mm1, "sig": float(np.hypot(SIG_ALAR, LM_PX * mm1)), "p": list(map(float, pr["px"][ok].mean(0))),
                    "q": list(map(float, pr["px"][ok].mean(0) + n * o / mm1)), "X": list(map(float, np.asarray(head["V"], float)[vv].mean(0))),
                    "nv": len(ok)})
    return out


def _nostril_obs(head, view):
    """Per nostril two reads along the line through both openings (u, toward the subject's left): its LATERAL end and its
    MEDIAL end, the picture's dark opening against the model's rim, each moving with the rim vertex that makes it."""
    cam = view["cam"]
    if "gid" not in head or abs(view_yaw(cam)) > NOSTRIL_TURN:
        return []
    rims = nostril_rims(head)
    if min(len(r) for r in rims) < 4:
        return []
    V = np.asarray(head["V"], float)
    Xc, P = _cam_points(cam, V[np.r_[rims[0], rims[1]]])
    Pr, Pl = P[:len(rims[0])], P[len(rims[0]):]
    u = Pl.mean(0) - Pr.mean(0)
    u /= max(np.linalg.norm(u), 1e-9)
    mmpx = float(np.median(Xc[:, 2]) / cam["f"] * 1000.0)
    out = []
    for side, (rv, Pp) in enumerate(((rims[0], Pr), (rims[1], Pl))):
        c = Pp.mean(0)
        pic = (view.get("_nostril") or {}).get(side, "none")
        if pic == "none":            # the picture is read ONCE per call round its start place (the head moves under it)
            pic = nostril_picture(view["img"], c, u, mmpx)
            view.setdefault("_nostril", {})[side] = (pic, c.copy()) if pic else None
        else:
            pic = pic
        ent = view["_nostril"][side]
        if not ent:
            continue
        pic, c0 = ent
        a = (Pp - c0) @ u
        lat, med = (int(np.argmin(a)), int(np.argmax(a))) if side == 0 else (int(np.argmax(a)), int(np.argmin(a)))
        for nm, j, edge, sig, bias in (("lateral", lat, pic["lo"] if side == 0 else pic["hi"], SIG_NOSTRIL[0], NOSTRIL_BIAS[0]),
                                       ("medial", med, pic["hi"] if side == 0 else pic["lo"], SIG_NOSTRIL[1], NOSTRIL_BIAS[1])):
            Jp, mm1 = _proj_jac(cam, head, int(rv[j]))
            sgn = (-1.0 if side == 0 else 1.0) * (1.0 if nm == "lateral" else -1.0)       # + = outward (lateral end) / toward the midline (medial end)
            o = (edge - a[j]) * mm1 - sgn * bias
            out.append({"type": "nostril", "view": view["kind"], "name": f"nostril_{'rl'[side]}_{nm}", "o": float(o), "n": u.tolist(),
                        "J": (u @ Jp) * mm1, "sig": float(np.hypot(sig, LM_PX * mm1)), "p": list(map(float, Pp[j])),
                        "q": list(map(float, c0 + edge * u + ((Pp[j] - c0) @ np.array([-u[1], u[0]])) * np.array([-u[1], u[0]]))),
                        "X": list(map(float, V[int(rv[j])])), "area": pic["area"]})
    return out
