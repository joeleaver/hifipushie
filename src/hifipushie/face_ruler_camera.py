"""The camera side of a block-in compare: priors on the camera, the lens and the distance, the view's turn, and
the landmark, anchor and dense observations. Part of the face ruler (face_ruler.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import face_ruler
from .face_ruler import _cam_points, _gnm, _proj_jac, _proj_jac_pt, _world
from .face_ruler_features import lip_bias

def lens_info(v: dict) -> dict:
    """What is known of a reference view's LENS: {"mm": the 35 mm equivalent on the frame's DIAGONAL (f / diagonal x 43.27:
    what humanfit_map.lens_prior counts) | None, "source": "lens_mm" | "exif" | None, "warn": str}. The view's own
    "lens_mm" is taken as given. EXIF: FocalLengthIn35mmFilm x DigitalZoomRatio; a picture CROPPED after capture (its
    pixel aspect is not the EXIF's PixelXDimension : PixelYDimension, either way up) no longer has that field of view:
    not known, and said. A resize keeps it."""
    if v.get("lens_mm"):       # ("frame": [w, h] = the uncropped frame in this picture's pixels: the lens is the frame's)
        return {"mm": float(v["lens_mm"]), "source": "lens_mm", "warn": "", "frame": v.get("frame")}
    try:
        from PIL import Image
        im = Image.open(v["image"])
        ex = im.getexif().get_ifd(0x8769)
        mm = ex.get(41989)
        if not mm:
            return {"mm": None, "source": None, "warn": ""}
        mm = float(mm)
        zoom = ex.get(41988)
        try:
            zoom = float(zoom) if zoom else 1.0
        except (TypeError, ValueError, ZeroDivisionError):
            zoom = 1.0
        if zoom > 1.001:
            mm *= zoom
        ew, eh = ex.get(40962), ex.get(40963)
        if ew and eh:
            a_pic, a_ex = max(im.size) / min(im.size), max(float(ew), float(eh)) / min(float(ew), float(eh))
            if abs(a_pic / a_ex - 1.0) > 0.02:
                return {"mm": None, "source": None, "warn": (
                    f"LENS: {str(v.get('image', '')).split('/')[-1]} was CROPPED after capture ({im.size[0]} x {im.size[1]} against the camera's "
                    f"{int(ew)} x {int(eh)}): its EXIF lens ({mm:.0f} mm eq.) no longer gives its field of view: NOT used. Keep the original "
                    "file, or give the view \"lens_mm\" with \"frame\": [w, h] (the uncropped frame's size in this picture's pixels)")}
        return {"mm": mm, "source": "exif", "warn": ""}
    except Exception:  # noqa: BLE001
        return {"mm": None, "source": None, "warn": ""}


def lens_known(v: dict) -> float | None:
    """A reference view's KNOWN lens (35 mm equivalent on the diagonal), None = not known (lens_info)."""
    return lens_info(v)["mm"]


def distance_cost(dist_m: float, err: float = 0.2) -> dict:
    """What a camera-distance error of `err` (0.2 = believed 20 % too far, the picture's scale at the eyes kept) shows as,
    in mm of apparent width at the face, on GNM's mean head: {"cheekbone", "jaw", "alar", "nose_vs_ears"}. Geometry only
    (spikes/readmix/distsens.py): the face's deep parts (cheekbones 80 mm, jaw angles 60 mm behind the eyes' plane) shrink
    against its front as the camera comes closer; what the solve cannot tell from a narrower jaw."""
    if "dcost" not in face_ruler._C:
        sp = _gnm()["sp"]
        L = sp["WL"] @ _world(sp["T"])
        eye = L[36:48].mean(0)
        face_ruler._C["dcost"] = {k: (a[0], b[0], a[1] - eye[1], b[1] - eye[1]) for k, (a, b) in
                       {"alar": (L[31], L[35]), "cheekbone": (L[1], L[15]), "jaw": (L[4], L[12])}.items()}
        face_ruler._C["dcost"]["nose_ear"] = (float(L[30][1] - eye[1]), float(0.5 * (L[0][1] + L[16][1]) - eye[1]))
    out = {}
    for k in ("alar", "cheekbone", "jaw"):
        xa, xb, za, zb = face_ruler._C["dcost"][k]
        w = lambda d: (xb * d / (d + zb) - xa * d / (d + za)) * 1000.0  # noqa: E731
        out[k] = float(w(dist_m) - w(dist_m * (1 + err)))
    zn, ze = face_ruler._C["dcost"]["nose_ear"]
    out["nose_vs_ears"] = float((dist_m + ze) / (dist_m + zn))
    return out


def distance_inferred(views: list, lens: list | None) -> dict:
    """The measures a front / shallow view's UNKNOWN distance leaves uncertain: {measure: +- mm}: what the apparent
    width across the face's depth changes by if the camera really stood anywhere in DIST_RANGE x its place (the larger
    side; distance_cost). Empty when every front / 3-4 view has a known lens. Measures between features at one depth (eye
    spacing, mouth width, lids, lips, the nose's own width) do not depend on it and are not listed."""
    out = {}
    for i, v in enumerate(views):
        if v["kind"] == "profile" or ((lens[i] if lens and i < len(lens) else None) or {}).get("mm"):
            continue
        d = float(v["cam"]["t"][2])
        lo, hi = distance_cost(d, face_ruler.DIST_RANGE[0] - 1.0), distance_cost(d, face_ruler.DIST_RANGE[1] - 1.0)
        k_ = max(0.0, float(np.cos(np.radians(min(abs(view_yaw(v["cam"])), 89.0)))))      # a turned view shows less of the width
        for key, names in face_ruler.DIST_MEASURES.items():
            pm = k_ * max(abs(lo[key]), abs(hi[key]))
            for n in names:
                out[n] = min(out[n], pm) if n in out else pm          # the view that depends on it least says how well it is known
    return {n: round(float(x), 1) for n, x in out.items() if x >= 0.5}


def distance_lines(views: list, lens: list | None) -> list:
    """Per front / 3-4 view what its DISTANCE rests on, and what not knowing it costs (readmix; Joe: "anything more
    specific we need to do about the distance problem")."""
    out = []
    side = any(abs(view_yaw(v["cam"])) >= face_ruler.SIDE_MIN for v in views)
    for i, v in enumerate(views):
        if v["kind"] == "profile":
            continue
        d = float(v["cam"]["t"][2])
        li = (lens[i] if lens and i < len(lens) else None) or {}
        nm = v.get("name", v["kind"])
        c = distance_cost(d, 0.2)
        if li.get("mm"):
            out.append(f"DISTANCE {nm}: {d:.2f} m, from its lens ({li['mm']:.0f} mm eq., {'stated' if li.get('source') == 'lens_mm' else 'EXIF'}) and the head's size "
                       f"(d = focal x size / pixels; the head's size is held at the start's: +- 5 % person to person, the same in the distance)")
        else:
            out.append(f"DISTANCE {nm}: NOT KNOWN (no lens_mm, no usable EXIF): it stands at {d:.2f} m (as if the picture were the whole frame of a "
                       f"{lens_mm(v['cam']):.0f} mm lens, 35 mm equivalent on the diagonal; a head CROPPED from a larger photo was taken through a longer one, from further). At that distance an error of 20 % shows as {abs(c['cheekbone']):.1f} mm of cheekbone width and "
                       f"{abs(c['jaw']):.1f} mm of jaw width (the nose's own width {abs(c['alar']):.1f}): those widths are uncertain by about that much"
                       + ("; a side view is in the set, so the face's depth is read and the solve may find the distance (its CAMERA line says how far it moved)"
                          if side else "; NO side view pins the face's depth: the set cannot determine it") + ". Give lens_mm or keep the file's EXIF")
        if v["kind"] == "front" and d < face_ruler.CLOSE_M:
            out.append(f"STRONG PERSPECTIVE: {nm} was taken from {d:.2f} m: the nose is drawn x{c['nose_vs_ears']:.2f} against the ears' plane and every width "
                       "depends on the distance" + ("" if li.get("mm") else ": it MUST be known: keep the original file with its EXIF, or retake from 1.5-2 m with 2-3x zoom"))
    inf = distance_inferred(views, lens)
    if inf:
        out.append("INFERRED (the camera's distance is not known: taken anywhere from half to twice where it stands): "
                   + ", ".join(f"{n} +- {x:.1f} mm" for n, x in sorted(inf.items(), key=lambda t: -t[1]))
                   + ". Widths between features at ONE depth (eyes, mouth, lids, lips, the nose's own width) do not depend on it")
    return out


def _landmark_obs(head, view, points):
    """The reference's own landmark points ("lmNN": picture px, the ones its camera was fitted with) as weak anchors:
    without them a partial outline (one cheek, the profile's front) lets the camera slide and scale freely."""
    out = []
    for key, p in (points or {}).items():
        if not (key.startswith("lm") and key[2:].isdigit()) or int(key[2:]) >= 68:
            continue
        i = int(key[2:])
        Jp, mm1 = _proj_jac_pt(view["cam"], np.asarray(head["L"], float)[i], head["LB"][:, i])
        _, q = _cam_points(view["cam"], np.asarray(head["L"], float)[i][None])
        for ax in (0, 1):
            out.append({"type": "landmark", "view": view["kind"], "name": f"{key}.{'xy'[ax]}", "o": float(p[ax] - q[0, ax]) * mm1,
                        "J": Jp[ax] * mm1, "sig": face_ruler.LM_SIG, "p": list(map(float, q[0])), "q": list(map(float, p)),
                        "X": list(map(float, np.asarray(head["L"], float)[i]))})
    return out


def _detect_model(head, cam, box):
    """The detector's 478 points (picture px) on the MODEL's own clay picture through cam, cropped to box as the
    picture's own detection is (likeness_sides.model_sides does the same for the table); cached by head and camera."""
    from . import likeness_detect, likeness_render
    key = (np.asarray(head["c"], np.float32).tobytes(),
           tuple(np.round(np.r_[cam["r"], cam["t"], cam["f"], cam.get("yaw", 0.0), cam["centre"]], 6)), tuple(np.round(box, 1)))
    D = face_ruler._C.setdefault("det", {})
    if key not in D:
        if len(D) > 64:
            D.clear()
        im, k = likeness_render.render(head["mesh"], cam, box)[:2]
        P = likeness_detect.detect([im])[0]
        D[key] = None if P is None else np.asarray(P, float) / k + [box[0], box[1]]
    return D[key]


def _anchor_obs(head, view, points, det, skip=()):
    """DIFFERENTIAL DETECTOR ANCHORS (refread, 2026-10-11): the detector's point on the PICTURE minus the same
    detector's point on the model's own render through this view's camera (det = {"P": the picture's 478, "box"}),
    as the block-in table compares them, moving with the landmark itself. _landmark_obs compares the detector with
    the model's TRUE mesh landmarks: the detector's definition bias (3-12 mm on some points, more on a painting) then
    goes into the identity (Garrett: 204 anchors forced comps to 3.9 sd). Falls back to _landmark_obs when the
    detector finds no face on the render."""
    from . import likeness
    if det is None or det.get("P") is None:
        return _landmark_obs(head, view, points)
    Pm = _detect_model(head, view["cam"], det["box"])
    if Pm is None:
        return _landmark_obs(head, view, points)
    out = []
    L = np.asarray(head["L"], float)
    keys = [k_ for k_ in (points or {}) if k_.startswith("lm") and k_[2:].isdigit() and int(k_[2:]) < 68 and int(k_[2:]) not in skip]
    ch = view.get("chin") or {}
    cl = ch.get("chin_lm", face_ruler.CHIN_LM_AXES)
    if cl == "auto":          # reference_views resolves it per set (a side view present or not); a bare view: the old behaviour
        cl = "xy"
    chin_ax = {"xy": (0, 1), "y": (1,), "x": (0,), "fx": (0,) if view["kind"] == "front" else (), "none": ()}[cl]
    if keys and view["kind"] in ("front", "3q") and chin_ax:      # the CHIN: a picture's stored points often leave the jaw contour out
        keys += [f"lm{i}" for i in view.get("jaw_lm", face_ruler.CHIN_LM) if f"lm{i}" not in keys]   # (the detector guesses it); like with like it is the
    stretch = ch.get("lm_stretch", face_ruler.LM_STRETCH)        # table's own chin read, and nothing else sees the chin from the front
    P0 = np.asarray(det["P"], float)[[likeness.MP68[int(k_[2:])] for k_ in keys]].mean(0) if keys else np.zeros(2)
    for key in keys:
        i = int(key[2:])
        m = likeness.MP68[i]
        Jp, mm1 = _proj_jac_pt(view["cam"], L[i], head["LB"][:, i])
        p, q = Pm[m], np.asarray(det["P"], float)[m]
        sig = float(np.hypot(face_ruler.LM_SIG_DIFF, face_ruler.LM_PX * mm1)) * float(ch.get("lm_sig", face_ruler.LM_SIG_SCALE))
        nb = np.zeros(2)
        if 31 <= i <= 35 and face_ruler.LM_NOSE_WIDE and view.get("style") == "photo" and not view.get("render"):
            # the sim-to-real width: along the base's own line in the render, in proportion to the point's place across it
            a_, b_ = Pm[likeness.MP68[31]], Pm[likeness.MP68[35]]
            wd = float(np.linalg.norm(b_ - a_))
            if wd > 1e-6:
                u_ = (b_ - a_) / wd
                fs = min(1.0, wd * mm1 / max(float(np.linalg.norm(L[35] - L[31])) * 1000.0, 1e-6))     # a turned view shows less of it
                nb = face_ruler.LM_NOSE_WIDE * fs * (float((p - a_) @ u_) / wd - 0.5) * u_
        for ax in ((0, 1) if i not in face_ruler.CHIN_LM else chin_ax):
            lb_ = lip_bias("landmark", key) if (ax == 1 and 48 <= i <= 67 and view.get("style") == "photo" and not view.get("render")) else 0.0
            ob = {"type": "landmark", "view": view["kind"], "name": f"{key}.{'xy'[ax]}", "o": float(q[ax] - p[ax]) * mm1 - float(nb[ax]) - lb_,
                  "J": Jp[ax] * mm1, "sig": sig, "p": list(map(float, p)), "q": list(map(float, q)),
                  "X": list(map(float, L[i])), "diff": True}
            if stretch:       # THE DETECTOR'S OWN STRETCH (chinread): its face on a photo is not its face on our clay render
                ob["nu"] = {f"lm_{view['kind']}_s{'xy'[ax]}": face_ruler.LM_STRETCH_UNIT * float(q[ax] - P0[ax]) * mm1}
            out.append(ob)
    if view["kind"] == "3q" and (keys or skip) and "eye_X" in head and len(Pm) > max(likeness.MP_EYES):
        # BOTH IRIS CENTRES of a turned view (the detector's, picture - render): two irises pin its yaw (one limbus
        # does not: the profile and 3/4 cameras over-rotated 3.5-4 deg over four calls on Tess)
        xs = [float(e[0]) for e in head["eye_X"]]
        for s_, m in enumerate(likeness.MP_EYES):     # the subject's right eye first (world x smaller)
            j = int(np.argmin(xs)) if s_ == 0 else int(np.argmax(xs))
            Jp, mm1 = _proj_jac_pt(view["cam"], head["eye_X"][j], head["eye_B"][j])
            p, q = Pm[m], np.asarray(det["P"], float)[m]
            sig = float(np.hypot(face_ruler.SIG_IRIS_3Q, face_ruler.LM_PX * mm1))
            for ax in (0, 1):
                out.append({"type": "iris", "view": view["kind"], "name": f"iris_{'rl'[s_]}.{'xy'[ax]}", "o": float(q[ax] - p[ax]) * mm1,
                            "J": Jp[ax] * mm1, "sig": sig, "p": list(map(float, p)), "q": list(map(float, q)),
                            "X": list(map(float, head["eye_X"][j])), "diff": True})
    return out


def dense_predict(head, view) -> dict | None:
    """The detector on a view's picture, its crop laid on the model's own 68 landmarks through the view's camera (then
    on the network's own 68: denselm.predict). None when no trained network is set up."""
    from . import denselm
    if not denselm.available():
        return None
    _, q = _cam_points(view["cam"], np.asarray(head["L"], float)[:68])
    return denselm.predict(view["img"], q)


def _dense_obs(head, view, pred):
    """per confident skin landmark: (the detector's pixel - the model vertex's projection) in mm, x and y, the vertex's
    own move per component, sigma = the network's own (x DENSE_SIG_SCALE, floored)."""
    from . import denselm
    if pred is None or "gid" not in head:
        return []
    Lm = denselm.landmarks()
    if "dense_v" not in head:
        gid = np.asarray(head["gid"], int)
        at = np.full(int(gid.max()) + 1, -1)
        at[gid[gid >= 0]] = np.where(gid >= 0)[0]
        head["dense_v"] = at[Lm["gnm"]]
    ch = view.get("chin") or {}
    scale, floor = float(ch.get("dense_sig", face_ruler.DENSE_SIG_SCALE)), float(ch.get("dense_floor", face_ruler.DENSE_SIG_FLOOR))
    regions = ch.get("dense_regions", face_ruler.DENSE_REGIONS)
    out = []
    _, Q = _cam_points(view["cam"], head["V"][head["dense_v"]])
    for j, v in enumerate(head["dense_v"]):
        if v < 0 or (regions and Lm["region"][j] not in regions):
            continue
        Jp, mm1 = _proj_jac(view["cam"], head, int(v))
        sg = float(pred["sigma"][j]) * mm1
        if not np.isfinite(sg) or sg > face_ruler.DENSE_MAX_MM:
            continue
        sig = max(floor, sg * scale, float((face_ruler.DENSE_REGION_SIG.get(view["kind"]) or {}).get(str(Lm["region"][j]), 0.0)) if ch.get("dense_region_sig", True) else 0.0)
        idn = ch.get("dense_identity", face_ruler.DENSE_IDENTITY)       # which dense reads may move the IDENTITY (all of them move the cameras)
        keep_id = idn == "all" or (idn == "inner" and str(Lm["region"][j]) in face_ruler.DENSE_INNER)
        for ax in (0, 1):
            out.append({"type": "dense", "view": view["kind"], "name": f"{Lm['names'][j]}.{'xy'[ax]}",
                        "o": float(pred["xy"][j, ax] - Q[j, ax]) * mm1, "J": Jp[ax] * mm1 if keep_id else np.zeros_like(Jp[ax]), "sig": sig,
                        "p": list(map(float, Q[j])), "q": list(map(float, pred["xy"][j])), "X": list(map(float, head["V"][int(v)])),
                        "region": str(Lm["region"][j])})
    neff = float(ch.get("dense_neff", face_ruler.DENSE_NEFF) or 0)
    if neff and len(out) > 2 * neff:
        k_ = float(np.sqrt(len(out) / (2 * neff)))
        for ob in out:
            ob["sig"] *= k_
    return out


def view_yaw(cam: dict) -> float:
    """How far the head is turned from the camera, from the FITTED camera itself (degrees; 0 = facing it, 90 = a true
    profile): the angle between the camera's line of sight and the head's forward axis, about the vertical."""
    from . import humanfit_views
    f = humanfit_views._cam_rot(cam) @ np.array([0.0, -1.0, 0.0])      # the head's forward (-Y) in the camera's frame
    return float(np.degrees(np.arctan2(f[0], -f[2])))


def view_pitch(cam: dict) -> float:
    """How far the camera looks DOWN on the head (degrees; 0 = level with it, + = from above: the head reads as nodded
    forward), from the fitted camera: the head's up axis against the picture's vertical, in the camera's frame."""
    from . import humanfit_views
    u = humanfit_views._cam_rot(cam) @ np.array([0.0, 0.0, 1.0])      # the head's up (+Z) in the camera's frame (y down, z away)
    return float(np.degrees(np.arctan2(-u[2], -u[1])))


def lens_mm(cam: dict, frame=None) -> float:
    """The camera's focal length as a 35 mm equivalent in EXIF's convention: on the frame's DIAGONAL (f / diagonal x
    43.27), the one a view's lens_mm and FocalLengthIn35mmFilm are in (readmix: this counted on the WIDTH, x1.39 on a 3:4
    portrait against what a caller states). frame: the uncropped frame's size when the picture is a crop of it."""
    w, h = frame or cam["size"]
    return float(cam["f"]) * 43.27 / float(np.hypot(w, h))
