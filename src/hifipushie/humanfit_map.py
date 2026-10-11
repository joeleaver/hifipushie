"""Fitting the one human mesh's face to pictures as a MAP estimate (the reference-modelling study's result;
CLAUDE.md "Reference modelling study"). What humanfit.fit_views got wrong, measured on heads whose 3D shape is known:

- POINT DEFINITIONS. MediaPipe's points read as GNM's 68 landmarks (the MP68 table) are other places on a face: 9-12
  mm off on the jaw contour, 8 mm on the brows, 3 mm at nose and mouth. Here each of the detector's 478 points is used
  at the place on GNM's surface where the detector really puts it (`mp478_gnm.npz`, calibrated on rendered heads of
  known shape, per kind of view), with its own scatter as its sigma. A profile gets no detector points (it finds 1
  profile in 36): click points there.
- THE PRIOR. GNM's identity components are in standard deviations, so the least-squares weights are not knobs: a
  point counts 1 / its sigma (mm), a component 1 per sigma toward the mean. That is the conditional mean of the
  population's heads given the evidence: what the pictures don't show (jaw depth, profile, skull) comes out as what
  usually goes with what they do show, instead of whatever a 3-sigma identity needed to hit noisy points.
- A CHARACTER READ is evidence: `read` = {"jaw_square": 1.5, "chin_projection": 1, "cheek_fullness": 1} (humanmacro's
  macros, in population sigmas; +-`read_sd`) enters the same solve. On the truth set a noisy 27-word read was worth
  more than a second detector view, and "front picture + read" as much as two views + read.
- CLICKED POINTS with the right definition (view["points"]: humanfit.LANDMARKS names, eye.L / eye.R; +-1.5 mm) beat
  the detector point for point: 21 of them in two views alone do better than the calibrated 478.
Not used, on purpose: the head's outline (it hurts unless the lens is known), a per-picture expression solve (no
gain; ask for neutral pictures), the detector's own depth (worse than the mean head's).

`fit(base, views, read=...)` -> (new base, report) as humanfit's fits (guarded by integrity). Points named lm0..lm67
in a view are taken as a detector's 68 through the old table and IGNORED when the view has its image (the detector
is run again and read through the calibrated table); without an image they are used at sigma `LM68_SIGMA`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

TABLE = Path(__file__).with_name("mp478_gnm.npz")
CLASSES = ("front", "left", "profile", "right")   # the table's view classes: yaw ~0, +40 (the subject's left side shows), 88, -38
CUT = 2.5          # mm: detector points scattering more than this over the calibration heads are left out
FLOOR = 0.7        # mm added in quadrature to every detector point's sigma
INFLATE = 2.0      # the detector's errors are not independent point to point: sigma x this
CLICK_SIGMA = 1.5  # mm: a clicked point
# how well an LLM places a named point on a gridded crop, measured on pictures of heads of known shape (rms mm against
# GNM's landmark of that name, bias included; placers agree with each other to 0.35 mm: the error is DEFINITION):
# front pictures add ~0.1 mm to the detector's fit whatever is clicked; a PROFILE's nose tip / base / nasion / eye and
# mouth corner are good to ~1-1.7 mm and are the only evidence there. The chin's lowest point can't be placed in
# either view (6-11 mm): trace the chin and jaw as a line instead. A point not listed counts CLICK_SIGMA.
CLICK_SIGMAS = {
    "front": {"chin": 10.0, "ala.L": 7.0, "ala.R": 7.0, "nose_bridge": 4.4, "nose_tip": 3.9, "lip_upper": 2.7, "nose_base": 2.0,
              "eye_outer.L": 2.5, "eye_outer.R": 2.5, "eye_inner.L": 1.7, "eye_inner.R": 1.7, "mouth_corner.L": 1.2,
              "mouth_corner.R": 1.2, "lip_lower": 1.6, "eye.L": 1.8, "eye.R": 1.8, "brow.L": 2.5, "brow.R": 2.5,
              "brow_inner.L": 2.5, "brow_inner.R": 2.5},
    "profile": {"chin": 6.4, "lip_upper": 4.4, "lip_lower": 2.1, "nose_bridge": 1.7, "nose_base": 1.4, "nose_tip": 1.2,
                "eye_outer.L": 1.0, "eye_outer.R": 1.0, "mouth_corner.L": 1.0, "mouth_corner.R": 1.0}}
LM68_SIGMA = 4.0   # mm: a detector's 68 given without their image (definitions 3-12 mm off)
LENS = (70.0, 0.4)  # the lens prior: 35 mm-equivalent focal, relative sigma (a portrait; points alone hardly see the lens)
ROUNDS = 3         # rebuilds of the head (the one mesh is not exactly linear in the identity)
INNER = 6


def table() -> dict:
    z = np.load(TABLE)
    return {"vid": z["vid"], "w": z["w"], "sd": z["sd"]}


def view_class(yaw: float) -> int:
    return 0 if abs(yaw) < 20 else 2 if abs(yaw) > 70 else 1 if yaw > 0 else 3


def detector_points(view: dict):
    """(478, 2) picture pixels from MediaPipe for a view with an "image" (cropped round the face when the view's
    points say where it is), or its own "mp478"; None without either or without the detector."""
    if view.get("mp478") is not None:
        return np.asarray(view["mp478"], float)[:, :2]
    if not view.get("image"):
        return None
    from PIL import Image
    from . import likeness
    if not likeness.detector_available():
        return None
    img = Image.open(view["image"]).convert("RGB")
    pts = view.get("points") or {}
    if len(pts) >= 4:
        return likeness.detect_region(img, likeness._box(pts, img.size))
    d = likeness.detect([img])[0]
    return d


def lens_prior(v: dict) -> tuple:
    """(focal in px, relative sigma) for a view: its "lens_mm" (35 mm-film equivalent, the EXIF FocalLengthIn35mmFilm:
    measured on the frame's DIAGONAL, so the picture must not be cropped; resizing is fine), else the image file's own
    EXIF, else the portrait prior LENS. A phone's 24 mm at 27 cm is not a 70 mm portrait: with the portrait prior a
    close phone photo's perspective (centre features big, the face's edges small) was fitted as shape."""
    w, h = v["size"]
    diag = float(np.hypot(w, h))
    mm = v.get("lens_mm")
    sd = 0.05
    if mm is None and v.get("image"):
        try:
            from PIL import Image
            ex = Image.open(v["image"]).getexif().get_ifd(0x8769)
            mm = ex.get(41989)   # FocalLengthIn35mmFilm
            sd = 0.08
        except Exception:  # noqa: BLE001  (no file / no EXIF: the portrait prior)
            mm = None
    if mm:
        return float(mm) / 43.27 * diag, sd
    return LENS[0] / 36.0 * w, LENS[1]


def _fit_cam(cam, X, uv, wt):
    from scipy.optimize import least_squares
    from . import humanfit
    f0, fsd = cam.get("f_prior") or (LENS[0] / 36.0 * cam["size"][0], LENS[1])

    def res(p):
        c = {**cam, "r": p[:3], "t": p[3:6], "f": float(p[6])}
        return np.r_[((humanfit.project(c, X) - uv) * wt[:, None]).ravel(), np.log(max(p[6], 1.0) / f0) / fsd]
    sol = least_squares(res, np.r_[cam["r"], cam["t"], cam["f"]], x_scale=[0.1, 0.1, 0.1, 0.05, 0.05, 0.3, 500.0], loss="soft_l1", f_scale=3.0)
    return {**cam, "r": [float(v) for v in sol.x[:3]], "t": [float(v) for v in sol.x[3:6]], "f": float(sol.x[6])}


def _evidence(st, views) -> list:
    """Per view: world points X (n, 3) of the current head, their identity basis XB (K, n, 3), pixels, sigma (mm)."""
    from . import base as basemod
    from . import headfit, humanfit, onemesh
    g = headfit._gnm()
    gd = basemod._gnm_data()
    tpl, c = st["tpl"], st["head"]["carry"]
    R, s = np.asarray(c["R"], float), float(c["s"])
    P = np.asarray(tpl["P"], float)
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
    of = np.full(len(gd["template_vertex_positions"]), -1)
    of[gid[gid >= 0]] = np.flatnonzero(gid >= 0)
    IB = np.asarray(gd["vertex_identity_basis"])
    jm = g["JB"].mean(1)
    LB = humanfit._lm_basis(st)
    tab = table()
    out = []
    for v in views:
        X, XB, uv, sig, src, used = [], [], [], [], [], np.zeros(0, int)
        named = {k: p for k, p in (v.get("points") or {}).items()}
        lm68 = {k: p for k, p in named.items() if str(k).startswith("lm") and str(k)[2:].isdigit()}
        clicks = {k: p for k, p in named.items() if k not in lm68}
        det = detector_points(v) if v.get("detector", True) else None
        k = int(v["_class"]) if "_class" in v else view_class(float(v.get("yaw", 0.0)))
        if det is not None and np.isfinite(tab["sd"][k]).any():
            ok = (tab["sd"][k] < CUT) & (of[tab["vid"][k]] >= 0).all(1)
            vid, w = tab["vid"][k][ok], tab["w"][k][ok]
            X.append((P[of[vid]] * w[..., None]).sum(1))
            B = (IB[g["comps"]][:, vid].astype(float) * w[None, ..., None]).sum(2)
            XB.append(s * (B - jm[:, None, :]) @ R.T)
            uv.append(det[ok])
            sig.append(np.sqrt(tab["sd"][k][ok] ** 2 + FLOOR ** 2) * INFLATE)
            src.append(f"{int(ok.sum())} detector points (calibrated)")
            used = np.flatnonzero(ok)
        elif lm68:
            clicks = {**lm68, **clicks}   # no image to detect on: the given 68, at their honest sigma
        if clicks:
            ids = np.array([humanfit.point_index(n) for n in clicks])
            X.append(st["L"][ids])
            XB.append(LB[:, ids])
            uv.append(np.array([clicks[n] for n in clicks], float))
            cs = CLICK_SIGMAS["profile" if k == 2 else "front"]
            sig.append(np.array([LM68_SIGMA if n in lm68 else float(v.get("click_sigma") or cs.get(n, CLICK_SIGMA)) for n in clicks]))
            src.append(f"{len(clicks)} given points")
        if not X:
            raise ValueError(f"humanfit_map: view {v.get('image') or v.get('yaw')} has no evidence (no detection, no points). "
                             "A profile needs clicked points: the detector does not find profiles.")
        out.append({"X": np.concatenate(X), "XB": np.concatenate(XB, 1), "uv": np.concatenate(uv), "sig": np.concatenate(sig),
                    "src": ", ".join(src), "mp_idx": used, "ignored_lm68": bool(det is not None and lm68)})
    return out


VIEW_BAD = 5.0     # mm rms of a view's points after the fit: past this the picture disagrees with the others (a painting
# that is not one projection, another person, a wrong yaw hint): it is left out of the identity and said so


def measured_read(views: list) -> dict | None:
    """humanmeasure's macros of the first front view that has its image and detector points: {"macros": {name: (z,
    sigma)}, "used", "note", "view": index} (None without one)."""
    from . import humanmeasure
    for i, v in enumerate(views):
        if abs(float(v.get("yaw", 0.0))) > 15 or not v.get("image"):
            continue
        P = detector_points(v)
        if P is None:
            continue
        from PIL import Image
        return {**humanmeasure.measure(np.asarray(Image.open(v["image"]).convert("RGB")), P, backdrop=False), "view": i}
    return None


def fit(base: dict, views: list, read: dict | None = None, read_sd: float = 0.8, lam: float = 1.0, force: bool = False,
        free=("identity",), drop_bad: bool = True, measure: bool = False, prior_mean=None) -> tuple:
    """(new base, report); see _fit. A view whose points still miss by more than VIEW_BAD mm rms after the fit is
    dropped from the identity's evidence (its camera is still fitted and returned) and the fit run again.
    measure=True: macros MEASURED on the front picture (humanmeasure: a regression calibrated on renders only, not
    validated on photographs) join the read as evidence with their own sigmas; a said read wins where both speak.
    rep["measured"] lists them. prior_mean: the identity prior's centre (default 0, GNM's template; e.g. the semantic
    sampler's class mean for the sex: blockin.data()["m_f"])."""
    meas = measured_read(views) if measure and "identity" in free else None
    if meas:
        read = {**{k: tuple(v) for k, v in meas["macros"].items()}, **(read or {})}
    nb, rep = _fit(base, views, read, read_sd, lam, force, free, None, prior_mean)
    bad =[i for i, v in enumerate(rep["views"]) if v["rms_mm"] > VIEW_BAD]
    if drop_bad and bad and len(bad) < len(views) and "identity" in free:
        nb, rep = _fit(base, views, read, read_sd, lam, force, free, set(bad), prior_mean)
        for i in bad:
            rep["views"][i]["dropped"] = True
        rep["dropped"] = bad
    if meas:
        rep["measured"] = meas
    return nb, rep


def _resolve(st, views: list) -> list:
    """Turned views: which side shows is taken from the picture, not from the hint's sign (hints in stored references
    carry either sign): the table's class and starting yaw whose camera-only fit on the current head is the better."""
    from . import humanfit
    out = []
    for v in views:
        yaw = float(v.get("yaw", 0.0))
        if "_class" in v or not (20 <= abs(yaw) <= 70) or detector_points(v) is None:
            out.append(v)
            continue
        best = None
        det = detector_points(v)
        for cls, sgn in ((1, 1.0), (3, -1.0)):
            cand = {**v, "yaw": sgn * abs(yaw), "_class": cls, "mp478": det}
            e = _evidence(st, [cand])[0]
            w_, h_ = cand["size"]
            f0, fsd = lens_prior(cand)
            z0 = f0 * np.ptp(e["X"], axis=0).max() / max(np.ptp(e["uv"], axis=0).max(), 1.0)
            uc = e["uv"].mean(0)
            cam = {"r": [0.0, 0.0, 0.0], "t": [(uc[0] - w_ / 2) / f0 * z0, (uc[1] - h_ / 2) / f0 * z0, z0], "f": f0, "size": [w_, h_],
                   "centre": st["L"][:68].mean(0).tolist(), "yaw": cand["yaw"], "f_prior": [f0, fsd]}
            cam = _fit_cam(cam, e["X"], e["uv"], (z0 / f0 * 1000) / e["sig"])
            r = float(np.sqrt((((humanfit.project(cam, e["X"]) - e["uv"]) * (cam["t"][2] / cam["f"] * 1000 / e["sig"])[:, None]) ** 2).mean()))
            if best is None or r < best[0]:
                best = (r, cand)
        out.append(best[1])
    return out


def _fit(base: dict, views: list, read, read_sd, lam, force, free, skip, prior_mean=None) -> tuple:
    """(new base, report). views as humanfit.fit_views' ({"image", "size", "yaw", "points": clicks}); read = a
    character read in humanmacro's macros (sigmas). free without "identity": cameras only."""
    from . import humanfit, humanmacro
    st0 = humanfit.state(base)
    views = _resolve(st0, views)
    c0 = humanfit.identity(base)
    K = len(c0)
    c = c0.copy()
    cur = base
    ctr = st0["L"][:68].mean(0)
    cams = [None] * len(views)
    use_id = "identity" in free
    srcs = []
    for it in range(ROUNDS if use_id else 1):
        st = humanfit.state(cur) if it else st0
        evs = _evidence(st, views)
        srcs = evs
        c_lin = c.copy()
        for _ in range(INNER):
            H = np.eye(K) * lam
            b = np.zeros(K) if prior_mean is None else lam * np.asarray(prior_mean, float)[:K]
            for vi, (v, e) in enumerate(zip(views, evs)):
                X = e["X"] + np.tensordot(c - c_lin, e["XB"], 1)
                if cams[vi] is None:
                    w_, h_ = v["size"]
                    f0, fsd = lens_prior(v)
                    z0 = f0 * np.ptp(X, axis=0).max() / max(np.ptp(e["uv"], axis=0).max(), 1.0)
                    uc = e["uv"].mean(0)
                    cams[vi] = {"r": [0.0, 0.0, 0.0], "t": [(uc[0] - w_ / 2) / f0 * z0, (uc[1] - h_ / 2) / f0 * z0, z0], "f": f0,
                                "size": [w_, h_], "centre": ctr.tolist(), "yaw": float(v.get("yaw", 0.0)), "f_prior": [f0, fsd]}
                cam = cams[vi]
                mm0 = cam["t"][2] / cam["f"] * 1000
                cam = cams[vi] = _fit_cam(cam, X, e["uv"], mm0 / e["sig"])
                Rc = humanfit._cam_rot(cam)
                Xc = (X - np.asarray(cam["centre"])) @ Rc.T + np.asarray(cam["t"])
                z = Xc[:, 2]
                J = np.zeros((len(X), 2, 3))
                J[:, 0, 0] = J[:, 1, 1] = cam["f"] / z
                J[:, 0, 2] = -cam["f"] * Xc[:, 0] / z ** 2
                J[:, 1, 2] = -cam["f"] * Xc[:, 1] / z ** 2
                J = J @ Rc
                wt = (z / cam["f"] * 1000) / e["sig"]
                r = (e["uv"] - humanfit.project(cam, X)) * wt[:, None]
                a = np.linalg.norm(r, axis=1)
                hw = np.where(a > 2.5, np.sqrt(2.5 / np.maximum(a, 1e-9)), 1.0)   # Huber at 2.5 sigma
                if skip and vi in skip:   # a camera only: this picture says nothing about the identity
                    continue
                A = (np.einsum("nij,knj->nik", J, e["XB"]) * (wt * hw)[:, None, None]).reshape(-1, K)
                y = A @ c + (r * hw[:, None]).ravel()
                H += A.T @ A
                b += A.T @ y
            if not use_id:
                break
            if read:
                Ar, yr = humanmacro.prior_rows(read, c_ref=c, sd=read_sd)
                H += Ar.T @ Ar
                b += Ar.T @ yr
            c = np.linalg.solve(H, b)
        if use_id:
            cur = humanfit._with_identity(base, c)
    st1 = humanfit.state(cur) if use_id else st0
    per = []
    for cam, e, v in zip(cams, _evidence(st1, views), views):
        d = np.linalg.norm(humanfit.project(cam, e["X"]) - e["uv"], axis=1)
        mm = d * ((e["X"] - ctr) @ humanfit._cam_rot(cam).T + cam["t"])[:, 2] / cam["f"] * 1000
        per.append({"points": len(d), "rms_px": round(float(np.sqrt((d ** 2).mean())), 2), "rms_mm": round(float(np.sqrt((mm ** 2).mean())), 2),
                    "worst": [], "focal": round(cam["f"], 1), "lens_mm": round(cam["f"] / cam["size"][0] * 36.0, 0), "evidence": e["src"],
                    "ignored_lm68": e["ignored_lm68"]})
    rep = {"views": per, "cameras": cams, "plausibility": humanfit.plausibility(cur), "method": "map",
           "side_effects": humanfit.side_effects(st0, st1, set(humanfit.FACE)), "integrity": humanfit.integrity(cur, st1, st0)}
    if read:
        z = humanmacro.read(c)
        rep["read"] = {k: {"asked": (v if not isinstance(v, (list, tuple)) else v[0]), "got": round(z[k], 2)} for k, v in read.items()}
    rep["macros"] = humanmacro.text(humanmacro.read(c), top=10) if use_id else ""
    return humanfit._guarded(base, cur, rep, force)
