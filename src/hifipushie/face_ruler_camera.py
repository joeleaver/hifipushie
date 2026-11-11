"""The camera side of a block-in compare: priors on the camera, the lens and the distance, the view's turn, and
the landmark, anchor and dense observations. Part of the face ruler (face_ruler.py has the overview)."""
from __future__ import annotations

import numpy as np

from .face_ruler import _C, _cam_points, _gnm, _proj_jac, _proj_jac_pt, _world
from .face_ruler_features import lip_bias

# A FITTED camera: mm of shift (x, y), % of scale, degrees of roll left free per view. Measured (spikes/faceruler/
# arms2.py): a camera fitted by laying the MODEL's landmarks on the picture's is off by 1.9 mm / 1.7 mm / 4.8 % / 1.1 deg
# rms when the model is a regional transplant away from the person (the scale up to 9 %: a broader jaw reads as "closer").
CAM_SD = (2.0, 2.0, 5.0, 1.2)
# The reader's error on a BLOCK-IN model (the one mesh) through real fitted cameras, hair masked, camera free: sd of
# reader - truth on dressed EEVEE pictures of 8 sampled GNM heads on the same body (spikes/faceruler/dval.py; size-free
# gaps). compare() never shows less. neck_width (the body's neck), nose_width, lower_lip_forward and mouth_width are
# NOT readable there (error >= half their population sd).
MODEL_ERR = {"pupils_apart": 0.83, "eyes_forward": 2.79, "eyes_height": 1.13, "brows_over_eyes": 1.13,
             "forehead_forward": 1.18, "tip_forward": 0.59, "subnasale_forward": 1.99, "upper_lip_forward": 0.42,
             "lower_lip_forward": 1.27, "chin_forward": 0.64, "philtrum_length": 0.77, "chin_length": 1.73,
             "nose_length": 0.86, "cheekbone_width": 3.06, "jaw_width": 5.0, "chin_width": 2.87, "mouth_width": 3.34,
             "nose_width": 5.2, "skull_width": 2.99, "skull_top": 2.29, "skull_back": 2.45, "neck_width": 13.5,
             "under_chin": 0.91,
             # (orbit: spikes/orbit/oval.py + osum.py: 8 far pairs, dressed, hair masked, each camera put OFF by a random
             # yaw (profile 6, 3/4 4 deg sd) / shift / scale and left free: a fitted camera. eyes_forward itself: 2.7-3.6
             # there (0.6-0.8 with the cameras KNOWN, 2.2 with true cameras left free): the profile camera's yaw, which
             # the outline pins only to ~2.5-3.3 deg, is what limits eye depth on a photo, not the limbus read (0.1 mm).)
             "brow_ridge_forward": 1.5, "side_rim_forward": 3.5, "under_eye_forward": 2.8, "brow_hollow": 1.1}
PHOTO_CAM_SD = (1.5, 1.5, 2.5, 0.8)   # a block-in's cameras were fitted to THIS model and are anchored by its landmarks
# with the cameras' YAW and PITCH left free too (degrees; the last two): a profile's yaw is the least known thing in a
# block-in (few landmarks, all near the midline: Tess's was refitted by 30 degrees once), a 3/4's is held by both eyes
PHOTO_CAM_SD6 = {"front": (1.5, 1.5, 2.5, 0.8, 2.0, 2.0), "3q": (1.5, 1.5, 2.5, 0.8, 4.0, 2.0),
                 "profile": (1.5, 1.5, 2.5, 0.8, 6.0, 2.0)}
# (solvecams, 2026-10-13; docs/notes/solvecams.md) THE CAMERAS' PRIOR, seven numbers a view: shift mm (x, y), scale %,
# roll, YAW, PITCH deg, DISTANCE (log x 100 ~ %): the sd of each camera's WHOLE move since the block-in's start. Measured on
# known heads: block_in_start's fit is off by 2.2 deg yaw, 3.5 deg pitch (the front 4.6, worst 8.7), 3.5 % scale, 1-4 mm
# rms and has no idea of the distance; at the right head the reads hold every rotation to 0.2-0.6 deg (a side view 1-2).
# 5 deg of FRONT pitch = 7 mm of jaw width, half the distance = +6 mm of jaw and +9 of cheekbone, so these are wide: the
# reads decide. block_in_solve(cameras="free") = these; "trust" = a third of them (cameras measured or carried from an
# accepted head); never a clip (read()).
PHOTO_CAM_SD7 = {"front": (3.0, 3.0, 4.0, 1.5, 3.0, 6.0, 15.0), "3q": (3.0, 3.0, 4.0, 1.5, 8.0, 4.0, 12.0),
                 "profile": (3.0, 3.0, 4.0, 1.5, 10.0, 4.0, 8.0)}
# DISTANCE: outlines and anchors read it weakly (at the right head, reads alone: front 20 %, 3/4 13 %, side 63 %) and on a
# head still far from the person its column soaks up shape (a true camera drifted +28 %, a +100 % start went to +129 %):
# held near the start's lens (lens_mm / EXIF / the 70 mm portrait prior) unless a read that sees perspective is in (the
# dense landmarks: 5-9 %; then PHOTO_CAM_DIST_DENSE)
PHOTO_CAM_DIST_DENSE = 40.0
# A KNOWN LENS (readmix, 2026-10-13): a view that carries lens_mm (the brief, the file's EXIF FocalLengthIn35mmFilm) has its
# distance held this tightly (log x 100 ~ %) round the start's, WITH the dense landmarks too: familynative's phone
# pictures went to 0.65 x / 1.6 x / 3 x their EXIF distance under PHOTO_CAM_DIST_DENSE, worth 3-4 mm of jaw width
PHOTO_CAM_DIST_LENS = 7.0
MP_DROPS_ANCHORS = False    # see reference_views
LENS_PINS = False           # True: a view with a known lens has its focal length PINNED and its scale freedom moves the camera's
#                             distance (cam_moved(lens=True)): distance = focal x head size / pixels. BUILT, and OFF: on a scanned head
#                             (h112, the rig's lens told) four chains with it ended at face 2.45-2.67 / lower face 2.9-3.6 mm against
#                             2.02-2.15 / 2.3-2.5 for three without (the lens held by PHOTO_CAM_DIST_LENS's prior instead, the front
#                             camera's distance within 1 %): cause not found (docs/notes/readmix.md "## Distance")
CLOSE_M = 0.6               # a front picture taken nearer than this: strong perspective, the distance must be KNOWN


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
    if "dcost" not in _C:
        sp = _gnm()["sp"]
        L = sp["WL"] @ _world(sp["T"])
        eye = L[36:48].mean(0)
        _C["dcost"] = {k: (a[0], b[0], a[1] - eye[1], b[1] - eye[1]) for k, (a, b) in
                       {"alar": (L[31], L[35]), "cheekbone": (L[1], L[15]), "jaw": (L[4], L[12])}.items()}
        _C["dcost"]["nose_ear"] = (float(L[30][1] - eye[1]), float(0.5 * (L[0][1] + L[16][1]) - eye[1]))
    out = {}
    for k in ("alar", "cheekbone", "jaw"):
        xa, xb, za, zb = _C["dcost"][k]
        w = lambda d: (xb * d / (d + zb) - xa * d / (d + za)) * 1000.0  # noqa: E731
        out[k] = float(w(dist_m) - w(dist_m * (1 + err)))
    zn, ze = _C["dcost"]["nose_ear"]
    out["nose_vs_ears"] = float((dist_m + ze) / (dist_m + zn))
    return out


DIST_RANGE = (0.5, 2.0)     # a distance that is NOT known is taken to lie between these multiples of where the camera stands
DIST_MEASURES = {"cheekbone": ("cheekbone_width", "skull_width"), "jaw": ("jaw_width", "gonial_width")}


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
        lo, hi = distance_cost(d, DIST_RANGE[0] - 1.0), distance_cost(d, DIST_RANGE[1] - 1.0)
        k_ = max(0.0, float(np.cos(np.radians(min(abs(view_yaw(v["cam"])), 89.0)))))      # a turned view shows less of the width
        for key, names in DIST_MEASURES.items():
            pm = k_ * max(abs(lo[key]), abs(hi[key]))
            for n in names:
                out[n] = min(out[n], pm) if n in out else pm          # the view that depends on it least says how well it is known
    return {n: round(float(x), 1) for n, x in out.items() if x >= 0.5}


def distance_lines(views: list, lens: list | None) -> list:
    """Per front / 3-4 view what its DISTANCE rests on, and what not knowing it costs (readmix; Joe: "anything more
    specific we need to do about the distance problem")."""
    out = []
    side = any(abs(view_yaw(v["cam"])) >= SIDE_MIN for v in views)
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
        if v["kind"] == "front" and d < CLOSE_M:
            out.append(f"STRONG PERSPECTIVE: {nm} was taken from {d:.2f} m: the nose is drawn x{c['nose_vs_ears']:.2f} against the ears' plane and every width "
                       "depends on the distance" + ("" if li.get("mm") else ": it MUST be known: keep the original file with its EXIF, or retake from 1.5-2 m with 2-3x zoom"))
    inf = distance_inferred(views, lens)
    if inf:
        out.append("INFERRED (the camera's distance is not known: taken anywhere from half to twice where it stands): "
                   + ", ".join(f"{n} +- {x:.1f} mm" for n, x in sorted(inf.items(), key=lambda t: -t[1]))
                   + ". Widths between features at ONE depth (eyes, mouth, lids, lips, the nose's own width) do not depend on it")
    return out


CAM_STEP = (3.0, 3.0, 4.0, 2.0, 5.0, 4.0, 15.0)      # the most one Gauss-Newton round moves a camera (same units)
LM_SIG = 1.5                          # mm: a clicked / detected landmark as an anchor (biased, never the measure)


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
                        "J": Jp[ax] * mm1, "sig": LM_SIG, "p": list(map(float, q[0])), "q": list(map(float, p)),
                        "X": list(map(float, np.asarray(head["L"], float)[i]))})
    return out


ADAPT_MIN = 8                         # solve(adapt=True): groups (type, view) of at least this many reads get their own scale
CAM_LOOSE = 2.0                       # read(cam_first=n): the cameras-first rounds' freedom, x the cameras' sd
CHIN_LM = (7, 8, 9)                   # differential anchors always include the chin's three
NECK_HOLD = True                      # an anthropometric PRIOR on the neck's girth (ANSUR's mean and sd for the sex and stature) on a GNM-native head (solve_report.neck_row)
SIZE_HOLD = True                      # the face's SIZE is held at the block-in's start head's (solve_report.size_row): no picture reads
# it (every camera's scale and distance are free: a bigger head further away is the same image), so left free it is whatever the prior's
# correlations make of the shape reads (GNM's head_000 is width AND size: Tess's narrow face came out 3 % small, tess_a1 3.4 % large, the
# benchmark's heads 1-8 % large). Joe, 2026-10-12: "I'd trust the model more". compare(chin={"size": False}) / block_in_solve(size="free") releases it
CHIN_TIE = False                      # compare(chin={"tie": ..}): the unread jaw / chin widths tied to their expectation (solve_report.tie_rows)
TIE_OPEN = (35.0, 60.0)               # a view whose fitted camera is turned this much shows the far jaw on its silhouette: no tie on the jaw
CHIN_LM_AXES = "auto"                 # ... "xy" | "y" | "x" | "none" | "auto" = left out when the set has a SIDE view (its outline reads
#   the chin's height and projection to 0.3 mm; the detector's chin on a dressed picture stands 2.6 +-1.1 mm higher and
#   2.4 mm aside of its chin on our clay render of the SAME head (eyes: 0.1) and, against that outline, left known heads'
#   chins 3.9 mm short on average and their lower faces worse than the class mean they started from: the notes' "## chinread"), kept when it has none (nothing else reads the chin)
SIDE_MIN = 60.0                       # degrees: a view whose fitted camera is turned at least this much is a side view
LM_SIG_SCALE = 1.0                    # differential anchors: their sigma x this (their errors are CORRELATED: a bias, not scatter)
LM_STRETCH = False                    # differential anchors: a free stretch (x, y apart) of the detector's face per view
LM_STRETCH_UNIT = 0.05                # its nuisance column's unit: 5 % (prior sd NU_SD = 2 units: wide)
SIG_IRIS_3Q = 0.5                     # mm: a 3/4 view's iris centre, detector on picture - detector on render (gaze differs)
LM_SIG_DIFF = 1.0                    # mm: a DIFFERENTIAL anchor (the same detector on picture and render), + its pixel floor
LM_PX = 0.6                           # picture px: the detector's own scatter on a small face (Garrett's: 1.2 mm / px)
# (readmix, from groundtruth's Part 2) THE DIFFERENTIAL ANCHORS DO NOT CANCEL AT THE NOSE: at the TRUE head the detector on a
# PHOTOGRAPH draws the nose base (landmarks 31-35) +1.7 / +1.6 mm wider than on our render of the same head (two scanned heads;
# -0.1 on a render of a scan): our renders of a nose do not look to it like a photographed one. That much width is taken out
# of the nose-base anchors of a view styled "photo", in proportion to each point's place across the base (0 = left as it was)
LM_NOSE_WIDE = 0.0          # OFF (2026-10-14): scored on the three HELD-OUT HSRD subjects it was not calibrated on, the 1.65 mm
#                             took the nose base from +0.6 / +1.4 / +0.6 mm to -0.9 / -0.8 / -1.5 (mean |error| 0.87 -> 1.07): the
#                             wide nose of the two calibration heads is not a constant of the detector
def _detect_model(head, cam, box):
    """The detector's 478 points (picture px) on the MODEL's own clay picture through cam, cropped to box as the
    picture's own detection is (likeness.model_sides does the same for the table); cached by head and camera."""
    from . import likeness
    key = (np.asarray(head["c"], np.float32).tobytes(),
           tuple(np.round(np.r_[cam["r"], cam["t"], cam["f"], cam.get("yaw", 0.0), cam["centre"]], 6)), tuple(np.round(box, 1)))
    D = _C.setdefault("det", {})
    if key not in D:
        if len(D) > 64:
            D.clear()
        im, k = likeness.render(head["mesh"], cam, box)[:2]
        P = likeness.detect([im])[0]
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
    cl = ch.get("chin_lm", CHIN_LM_AXES)
    if cl == "auto":          # reference_views resolves it per set (a side view present or not); a bare view: the old behaviour
        cl = "xy"
    chin_ax = {"xy": (0, 1), "y": (1,), "x": (0,), "fx": (0,) if view["kind"] == "front" else (), "none": ()}[cl]
    if keys and view["kind"] in ("front", "3q") and chin_ax:      # the CHIN: a picture's stored points often leave the jaw contour out
        keys += [f"lm{i}" for i in view.get("jaw_lm", CHIN_LM) if f"lm{i}" not in keys]   # (the detector guesses it); like with like it is the
    stretch = ch.get("lm_stretch", LM_STRETCH)        # table's own chin read, and nothing else sees the chin from the front
    P0 = np.asarray(det["P"], float)[[likeness.MP68[int(k_[2:])] for k_ in keys]].mean(0) if keys else np.zeros(2)
    for key in keys:
        i = int(key[2:])
        m = likeness.MP68[i]
        Jp, mm1 = _proj_jac_pt(view["cam"], L[i], head["LB"][:, i])
        p, q = Pm[m], np.asarray(det["P"], float)[m]
        sig = float(np.hypot(LM_SIG_DIFF, LM_PX * mm1)) * float(ch.get("lm_sig", LM_SIG_SCALE))
        nb = np.zeros(2)
        if 31 <= i <= 35 and LM_NOSE_WIDE and view.get("style") == "photo" and not view.get("render"):
            # the sim-to-real width: along the base's own line in the render, in proportion to the point's place across it
            a_, b_ = Pm[likeness.MP68[31]], Pm[likeness.MP68[35]]
            wd = float(np.linalg.norm(b_ - a_))
            if wd > 1e-6:
                u_ = (b_ - a_) / wd
                fs = min(1.0, wd * mm1 / max(float(np.linalg.norm(L[35] - L[31])) * 1000.0, 1e-6))     # a turned view shows less of it
                nb = LM_NOSE_WIDE * fs * (float((p - a_) @ u_) / wd - 0.5) * u_
        for ax in ((0, 1) if i not in CHIN_LM else chin_ax):
            lb_ = lip_bias("landmark", key) if (ax == 1 and 48 <= i <= 67 and view.get("style") == "photo" and not view.get("render")) else 0.0
            ob = {"type": "landmark", "view": view["kind"], "name": f"{key}.{'xy'[ax]}", "o": float(q[ax] - p[ax]) * mm1 - float(nb[ax]) - lb_,
                  "J": Jp[ax] * mm1, "sig": sig, "p": list(map(float, p)), "q": list(map(float, q)),
                  "X": list(map(float, L[i])), "diff": True}
            if stretch:       # THE DETECTOR'S OWN STRETCH (chinread): its face on a photo is not its face on our clay render
                ob["nu"] = {f"lm_{view['kind']}_s{'xy'[ax]}": LM_STRETCH_UNIT * float(q[ax] - P0[ax]) * mm1}
            out.append(ob)
    if view["kind"] == "3q" and (keys or skip) and "eye_X" in head and len(Pm) > max(likeness.MP_EYES):
        # BOTH IRIS CENTRES of a turned view (the detector's, picture - render): two irises pin its yaw (one limbus
        # does not: the profile and 3/4 cameras over-rotated 3.5-4 deg over four calls on Tess)
        xs = [float(e[0]) for e in head["eye_X"]]
        for s_, m in enumerate(likeness.MP_EYES):     # the subject's right eye first (world x smaller)
            j = int(np.argmin(xs)) if s_ == 0 else int(np.argmax(xs))
            Jp, mm1 = _proj_jac_pt(view["cam"], head["eye_X"][j], head["eye_B"][j])
            p, q = Pm[m], np.asarray(det["P"], float)[m]
            sig = float(np.hypot(SIG_IRIS_3Q, LM_PX * mm1))
            for ax in (0, 1):
                out.append({"type": "iris", "view": view["kind"], "name": f"iris_{'rl'[s_]}.{'xy'[ax]}", "o": float(q[ax] - p[ax]) * mm1,
                            "J": Jp[ax] * mm1, "sig": sig, "p": list(map(float, p)), "q": list(map(float, q)),
                            "X": list(map(float, head["eye_X"][j])), "diff": True})
    return out


# DENSE LANDMARKS (denselm, 2026-10-12; docs/notes/fitter_whitepaper.md "## denselm"): our own detector's ~600 points, each a
# GNM skin vertex's picture position with the network's own sigma. ABSOLUTE (no render of the model): the network is
# trained on our renders, so its landmark IS the vertex's projection. OFF by default (a pilot network).
DENSE = False                         # reference_views(dense=None) takes this
DENSE_SIG_SCALE = 1.0                 # x the network's sigma (2.0 until solvecams: the region floors and DENSE_NEFF do that job now)
DENSE_SIG_FLOOR = 0.5                 # mm: never surer than this
DENSE_MAX_MM = 3.0                    # a landmark the network is less sure of than this (mm) is left out (hidden, under hair)
# (solvecams, 2026-10-13) THE NETWORK'S MEASURED ERROR at known heads through true cameras (6 heads, 3 dressings, one with
# hair; spikes/solvecams/dres.py): per-axis mm by view kind and region = the FLOOR of a dense read's sigma there. Its own
# sigma said 1.5-2.5 mm everywhere; at the truth it is 0.7 mm on a front view's lids and 4 on a true profile's, and the
# solve fitted it to 1.6-1.9 mm rms where its error is 2.3-3.0: it fitted the network's biases (every width +4-6 mm).
# EARS and SCALP / NECK are out (4-9 and 5-12 mm; under hair worse).
# (readmix, 2026-10-13) ... AND ON PHOTOGRAPHS OF SCANNED HEADS (two HSRD-100 heads through the rig's cameras against the
# scan-fitted GNM; spikes/readmix/gmix.py, the error left after the network's own 2D similarity per view): 1.4-2.8 mm
# everywhere, lids 2.1 where the renders said 0.5, chin 2.3 against 1.1, lips 1.8 against 0.8: trained on our renders only,
# it is a coarse read on a real face. Each floor = the larger of the two measurements.
DENSE_REGION_SIG = {"front": {"lids": 2.1, "eyes": 2.3, "lips": 1.8, "brows": 2.1, "mouth": 1.4, "chin": 2.3, "nose": 1.5, "cheeks": 2.4, "forehead": 2.8},
                    "3q": {"lids": 2.4, "eyes": 2.2, "lips": 1.7, "brows": 1.9, "mouth": 1.7, "chin": 1.7, "nose": 1.8, "cheeks": 2.6, "forehead": 2.4},
                    "profile": {"lids": 2.9, "eyes": 2.6, "lips": 1.3, "brows": 2.5, "mouth": 1.8, "chin": 2.9, "nose": 2.0, "cheeks": 3.2, "forehead": 2.6}}
DENSE_REGIONS = tuple(DENSE_REGION_SIG["front"])     # None = every skin landmark; or a tuple of denselm regions
DENSE_IDENTITY = "all"                # "all" | "inner" (DENSE_INNER's regions only) | "none": the dense reads that may move identity
DENSE_INNER = ("lids", "eyes", "lips", "brows", "mouth", "nose")
DENSE_NEFF = 80                       # a view's dense reads count as this many independent ones (one crop, one network: neighbours err
#                                       together): every sigma x sqrt(n / DENSE_NEFF)
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
    scale, floor = float(ch.get("dense_sig", DENSE_SIG_SCALE)), float(ch.get("dense_floor", DENSE_SIG_FLOOR))
    regions = ch.get("dense_regions", DENSE_REGIONS)
    out = []
    _, Q = _cam_points(view["cam"], head["V"][head["dense_v"]])
    for j, v in enumerate(head["dense_v"]):
        if v < 0 or (regions and Lm["region"][j] not in regions):
            continue
        Jp, mm1 = _proj_jac(view["cam"], head, int(v))
        sg = float(pred["sigma"][j]) * mm1
        if not np.isfinite(sg) or sg > DENSE_MAX_MM:
            continue
        sig = max(floor, sg * scale, float((DENSE_REGION_SIG.get(view["kind"]) or {}).get(str(Lm["region"][j]), 0.0)) if ch.get("dense_region_sig", True) else 0.0)
        idn = ch.get("dense_identity", DENSE_IDENTITY)       # which dense reads may move the IDENTITY (all of them move the cameras)
        keep_id = idn == "all" or (idn == "inner" and str(Lm["region"][j]) in DENSE_INNER)
        for ax in (0, 1):
            out.append({"type": "dense", "view": view["kind"], "name": f"{Lm['names'][j]}.{'xy'[ax]}",
                        "o": float(pred["xy"][j, ax] - Q[j, ax]) * mm1, "J": Jp[ax] * mm1 if keep_id else np.zeros_like(Jp[ax]), "sig": sig,
                        "p": list(map(float, Q[j])), "q": list(map(float, pred["xy"][j])), "X": list(map(float, head["V"][int(v)])),
                        "region": str(Lm["region"][j])})
    neff = float(ch.get("dense_neff", DENSE_NEFF) or 0)
    if neff and len(out) > 2 * neff:
        k_ = float(np.sqrt(len(out) / (2 * neff)))
        for ob in out:
            ob["sig"] *= k_
    return out


def view_yaw(cam: dict) -> float:
    """How far the head is turned from the camera, from the FITTED camera itself (degrees; 0 = facing it, 90 = a true
    profile): the angle between the camera's line of sight and the head's forward axis, about the vertical."""
    from . import humanfit
    f = humanfit._cam_rot(cam) @ np.array([0.0, -1.0, 0.0])      # the head's forward (-Y) in the camera's frame
    return float(np.degrees(np.arctan2(f[0], -f[2])))


def view_pitch(cam: dict) -> float:
    """How far the camera looks DOWN on the head (degrees; 0 = level with it, + = from above: the head reads as nodded
    forward), from the fitted camera: the head's up axis against the picture's vertical, in the camera's frame."""
    from . import humanfit
    u = humanfit._cam_rot(cam) @ np.array([0.0, 0.0, 1.0])      # the head's up (+Z) in the camera's frame (y down, z away)
    return float(np.degrees(np.arctan2(-u[2], -u[1])))


def lens_mm(cam: dict, frame=None) -> float:
    """The camera's focal length as a 35 mm equivalent in EXIF's convention: on the frame's DIAGONAL (f / diagonal x
    43.27), the one a view's lens_mm and FocalLengthIn35mmFilm are in (readmix: this counted on the WIDTH, x1.39 on a 3:4
    portrait against what a caller states). frame: the uncropped frame's size when the picture is a crop of it."""
    w, h = frame or cam["size"]
    return float(cam["f"]) * 43.27 / float(np.hypot(w, h))
