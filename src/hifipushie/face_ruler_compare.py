"""reference_views and compare: a block-in model against its reference pictures, with what the reads disagree
on and the overlay. Part of the face ruler (face_ruler.py has the overview)."""
from __future__ import annotations

import numpy as np

from .face_ruler import _cam_points, clay
from .face_ruler_blockin import EXPR_SET, expr_prior_of, model_head
from .face_ruler_camera import (
    CHIN_LM_AXES, CHIN_TIE, DENSE, LENS_PINS, MODEL_ERR, MP_DROPS_ANCHORS, NECK_HOLD, PHOTO_CAM_SD7, SIDE_MIN,
    SIZE_HOLD, TIE_OPEN, _anchor_obs, _dense_obs, dense_predict, distance_inferred, distance_lines, lens_info,
    lens_mm, view_pitch, view_yaw,
)
from .face_ruler_features import _iris_obs, _lid_obs, _lip_obs, _normal_obs, _normals_of_model, _shade_obs
from .face_ruler_nose import ALAR, NOSTRIL, NOSTRIL_TURN, _alar_obs, _nostril_obs
from .face_ruler_orbit import orbit_text, text
from .face_ruler_outline import (
    HAIR_EDGE, OUTLINE_FEW, PARSE_MODEL, PARSE_SIG, PLAIN_MIN, PLAIN_READS, _curve, photo_masks, plain_backdrop,
)
from .face_ruler_solve import cam_sd_of, observe, read

def kind_of(yaw: float) -> str:
    a = abs(float(yaw or 0.0))
    return "front" if a < 20 else ("3q" if a < 70 else "profile")


VIEW_DOUBT = 15.0                     # degrees between a view's stated yaw and its fitted camera's turn: say so
KIND_SAY = {"front": "a front view", "3q": "a three-quarter view", "profile": "a profile"}


def camera_lines(views0: list, views1: list, cam_done, cam_sd, stated=None) -> list:
    """What each camera did in a solve, one line a view: turn / pitch / distance at the call's start -> end, the whole
    move since the block-in's start against its prior, and what the picture was said to be."""
    out = []
    for i, (v0, v1) in enumerate(zip(views0, views1)):
        a, b = v0["cam"], v1["cam"]
        sd = cam_sd_of(cam_sd, v1["kind"]) if cam_sd is not None else None
        d = list(cam_done[i]) if cam_done is not None else []
        st = "" if not stated else f" (given as {abs(float(stated[i])):.0f})"
        s = (f"CAMERA {v1.get('name', v1['kind'])}: turn {abs(view_yaw(a)):.1f} -> {abs(view_yaw(b)):.1f} deg{st}; pitch {view_pitch(a):+.1f} -> "
             f"{view_pitch(b):+.1f}; distance {a['t'][2]:.2f} -> {b['t'][2]:.2f} m (a {lens_mm(a):.0f} -> {lens_mm(b):.0f} mm lens)")
        if sd is not None and len(d) > 5:
            far = [f"{nm} {d[j]:+.1f} = {abs(d[j]) / sd[j]:.1f} sd" for j, nm in ((4, "yaw"), (5, "pitch"), (6, "distance")) if j < len(d) and j < len(sd) and abs(d[j]) > 1.5 * sd[j]]
            s += (f"; whole move since the start: yaw {d[4]:+.1f} (prior +-{sd[4]:.1f}), pitch {d[5]:+.1f} (+-{sd[5]:.1f})"
                  + (f", distance {d[6]:+.0f} % (+-{sd[6]:.0f})" if len(d) > 6 and len(sd) > 6 else "")
                  + (". FAR FROM ITS START: " + ", ".join(far) + " (the reads pull this camera well away from where it was fitted or given: check the picture's angle)" if far else ""))
        out.append(s)
    return out


def view_sanity(views: list, cameras: list) -> list:
    """Per reference view: what it was SAID to be against what its fitted camera says ({"stated", "fitted", "kind",
    "stated_kind", "warn"}). A "profile" whose camera sits at 72 degrees has no true side (the far brow shows: depth
    rides on one camera's angle); a "three-quarter" at 23 shows little more than the front."""
    out = []
    for v, cam in zip(views, cameras):
        st = abs(float(v.get("yaw", 0.0) or 0.0))
        if not cam:
            out.append({"stated": st, "fitted": None, "kind": kind_of(st), "stated_kind": kind_of(st), "warn": ""})
            continue
        fy = abs(view_yaw(cam))
        w = ""
        if abs(fy - st) > VIEW_DOUBT:
            nm = str(v.get("image", "")).split("/")[-1]
            w = (f"VIEW: {nm} was given as {KIND_SAY[kind_of(st)]} (yaw {st:.0f}) but its fitted camera is turned {fy:.0f} deg"
                 + (f" = {KIND_SAY[kind_of(fy)]}" if kind_of(fy) != kind_of(st) else "")
                 + (": NO TRUE SIDE VIEW (at this angle the far brow and cheek show in front of the profile line; forehead "
                    "slope, eye depth and chin projection ride on this one camera's angle: INFERRED)" if st >= 70 else
                    ": it shows less of the side than a 3/4 should (the far cheek's outline reads width, little depth)" if fy < st
                    else ""))
        out.append({"stated": st, "fitted": fy, "kind": kind_of(fy), "stated_kind": kind_of(st), "warn": w})
    return out


def reference_views(name: str, hair: bool = True, lids: bool = False, lips: bool = False, shade: bool = False,
                    anchors: str = "differential", parse: bool | str = False, normals: bool = False,
                    kinds: list | None = None, readers: list | None = None, jaw_lm=None, expr: bool = False,
                    jaw: bool = False, chin: dict | None = None, dense: bool | None = None, mp: bool | None = None,
                    hair_edge: bool | None = None, nostrils: bool | None = None, alar: bool | None = None) -> tuple:
    """A block-in model's reference pictures as the ruler's views: per picture its fitted camera, the skin's own
    outline where the picture has one (a profile in front of a plain background: blockin_look.profile_contour; any view's
    "outline" points), and on the front picture the iris centres (eye_ruler). -> (views, notes)."""
    from PIL import Image
    from . import eye_ruler as er, humanfit, mpread, store
    from . import likeness_detect, likeness_render, likeness_sides
    from . import blockin_clay, blockin_models
    rj = blockin_models._refs(name)
    spec = store.load(name)
    head = model_head(spec, expr={"names": EXPR_SET} if expr else None)
    views, notes = [], []
    want_mp = bool(mpread.ENABLED if mp is None else mp) and mpread.available() and likeness_detect.detector_available()
    want_he = bool(HAIR_EDGE if hair_edge is None else hair_edge)
    iris_mm = None
    chin = dict(chin or {})
    if chin.get("chin_lm", CHIN_LM_AXES) == "auto":
        side = any(cam and abs(view_yaw(cam)) >= SIDE_MIN for cam in rj["cameras"])
        chin["chin_lm"] = "none" if side else "xy"
        if side and anchors == "differential":
            notes.append("CHIN: the detector's chin points are left out: this set has a side view, whose outline reads the chin's "
                         "height and projection (the block-in table's chin_height / lower_third rows are the detector's: expect "
                         "them out by 2-4 mm where the side view disagrees with it)")
    for vi, (v, cam) in enumerate(zip(rj["views"], rj["cameras"])):
        # the READERS go by the view's STATED kind, fixed for the whole block-in (kinds). TRIED and wrong (solvereads):
        # the kind from the fitted camera. Tess's "profile" camera stands at 67 deg, so it became a second "3q": two
        # views of one kind share their camera columns here (obs are keyed by kind), and its readers changed (every
        # sigma x3.6, the camera turned 26 deg). What the fitted camera says is REPORTED instead (view_sanity, compare).
        k = kinds[vi] if kinds and vi < len(kinds) and kinds[vi] else kind_of(v.get("yaw", 0))
        img = Image.open(v["image"]).convert("RGB")
        view = {"img": img, "cam": cam, "kind": k, "style": "photo", "hair": hair, "name": str(v["image"]).split("/")[-1],
                "face_only": True, "reader": "points", "jaw": bool(jaw), "chin": dict(chin or {})}
        if v.get("render"):          # one of OUR renders as a reference (a benchmark): the detector sees it as it sees the model's
            view["render"] = True
        li = lens_info(v)
        view["lens"] = li
        if li["mm"] and LENS_PINS:       # a known lens: the focal length stays, the picture's scale is the camera's distance
            view["lens_known"] = True
        if li["warn"]:
            notes.append(li["warn"])
        if jaw_lm:
            view["jaw_lm"] = tuple(jaw_lm)
        pts = dict(v.get("points") or {})
        det = None
        has_lm = any(k_.startswith("lm") and k_[2:].isdigit() for k_ in pts)
        mp_view = want_mp and cam is not None and abs(view_yaw(cam)) < mpread.TURNS[-1] + 10.0
        if (anchors == "differential" and has_lm) or mp_view:
            # the detector on the picture, on the crop the table uses (a view without stored points: round the model's own landmarks)
            box = likeness_sides._box(pts if has_lm else {f"lm{i}": q_ for i, q_ in enumerate(_cam_points(cam, np.asarray(head["L"], float)[:68])[1])}, img.size)
            Pd = likeness_detect.detect_region(img, box)
            if Pd is None:
                notes.append(f"{view['name']}: the detector finds no face" + (": its stored points are absolute anchors" if has_lm else ""))
            else:
                det = {"P": Pd, "box": box}
        extras = []
        if mp_view and det is not None:
            # MEDIAPIPE'S MESH AS ABSOLUTE READS (readmix): lips / mouth corners / nostril base / eye contours / bridge through the
            # learned correspondence, at the sigma measured on photographs of scanned heads
            mix_ = (chin or {}).get("mp_mix")
            view["mp_P"] = det["P"]

            def _mp_and_anchors(h, vw, pts=pts, det=det, mix_=mix_):
                m = mpread.obs(h, vw, det["P"], mix=mix_, neff=(vw.get("chin") or {}).get("mp_neff"))
                # (MP_DROPS_ANCHORS: TRIED dropping the same detector's differential inner anchors where the mesh is read: on a
                # scanned head the mouth's width went from +0.6 to +2.3 mm: 102 anchors at 1 mm each were replaced by reads that
                # count as 16. They stay; the mesh's reads are ADDED at their honest weight)
                a = [] if anchors == "none" else _anchor_obs(h, vw, pts, det if anchors == "differential" else None,
                                                             skip=tuple(range(17, 68)) if (m and MP_DROPS_ANCHORS) else ())
                return m + a
            extras.append(_mp_and_anchors)
        elif anchors != "none":
            extras.append(lambda h, vw, pts=pts, det=det: _anchor_obs(h, vw, pts, det))
        if v.get("outline"):
            view["outline"] = np.asarray(v["outline"], float)
        else:
            view["mask"], view["trust"] = photo_masks(img, cam, head)
            use = bool(parse) and parse != "auto"
            rd0 = readers[vi] if readers and vi < len(readers) else None
            if rd0 in ("plain", "parser"):       # ONE outline reader per view for a whole block-in (solve_step keeps it):
                use = rd0 == "parser"            # re-decided per call it flipped with the head (outline 211 -> 77 -> 160)
            elif parse == "auto":    # the plain-background reader where it works (a finer edge), the parser elsewhere
                n0 = sum(ob["type"] == "outline" for ob in observe(head, [dict(view, limbus=False, jaw=False)], colour=False))
                use = plain_backdrop(img) < PLAIN_MIN or n0 < PLAIN_READS
            view["reader"] = "parser" if use else "plain"
            if use:
                from . import faceparse
                try:
                    view["mask"], view["trust"], _ = faceparse.masks(img, cam, head, model=parse if parse in faceparse.SIZE else PARSE_MODEL)
                    view["outline_sig"] = PARSE_SIG
                    view["ears"] = True      # the parser knows hair from skin: an ear it shows bare is the head's outline
                    notes.append(f"{view['name']}: outline from the face parser ({parse if parse in faceparse.SIZE else PARSE_MODEL})")
                except (FileNotFoundError, RuntimeError, ValueError) as e:
                    notes.append(f"{view['name']}: the face parser is not available ({str(e)[:160]}): plain-background outline")
                    view["reader"] = "plain"
        if want_he and k != "profile" and not v.get("outline"):
            # the skin | hair boundary as a ONE-SIDED outline read (_hair_edge_obs): needs the parser, whatever reads the outline
            try:
                from . import faceparse
                fm = faceparse.masks(img, cam, head, model=PARSE_MODEL)[2]
                if "hair" in fm:
                    view["hair_edge"] = {"skin": fm["skin"] > 0.5, "hair": fm["hair"] > 0.5}
            except (FileNotFoundError, RuntimeError, ValueError) as e:
                notes.append(f"{view['name']}: no hair-edge read (the face parser is not available: {str(e)[:100]})")
        if k == "front":
            try:
                P = blockin_clay.detect_view(img, v)
                mm = likeness_render._mm_per_px(cam, humanfit.state(spec["base"])["L"][27:48])
                eyes = er.read(img, P, mm)
                extras.append(lambda h, vw, eyes=eyes: _iris_obs(h, vw, eyes))
                iris_mm = float(np.mean([e["iris"] for e in eyes]))
                rv = er.mean(eyes)
                if lids and rv["iris"] / mm >= 30.0 and all(np.isfinite(rv[q]).sum() >= 5 for q in ("up", "lo")):
                    extras.append(lambda h, vw, rv=rv: _lid_obs(h, vw, rv))
                elif lids:
                    notes.append(f"{view['name']}: the lids were not read (iris {rv['iris'] / mm:.0f} px; needs 30)")
            except Exception as e:  # noqa: BLE001
                notes.append(f"{view['name']}: the irises were not read ({e})")
            if lips:
                try:
                    from . import blockin_lips as bl
                    lev = bl.photo_evidence(img, v)
                    extras.append(lambda h, vw, lev=lev: _lip_obs(h, vw, lev))
                except Exception as e:  # noqa: BLE001
                    notes.append(f"{view['name']}: the lip borders were not read ({e})")
        if (NOSTRIL if nostrils is None else nostrils) and k != "profile":      # the nose's own read: the nostril openings
            extras.append(_nostril_obs)
        if (ALAR if alar is None else alar) and k != "profile":                 # the nose's width from the wings' edges
            extras.append(_alar_obs)
        if shade:
            extras.append(_shade_obs)
        if DENSE if dense is None else dense:      # our own dense landmarks (absolute; the picture is read ONCE per call)
            try:
                pred = dense_predict(head, view)
                if pred is None:
                    notes.append(f"{view['name']}: dense landmarks asked for, but no trained network is set up")
                else:
                    view["dense"] = pred
                    extras.append(lambda h, vw, pred=pred: _dense_obs(h, vw, pred))
            except Exception as e:  # noqa: BLE001
                notes.append(f"{view['name']}: the dense landmarks were not read ({str(e)[:200]})")
        if normals:      # OFF by default: failed its validation (the notes' "## refread", 3): differential against the
            extras.append(lambda h, vw: _normal_obs(h, vw, _normals_of_model(h, vw)))     # model's own clay picture
        view["extra"] = lambda h, vw, extras=tuple(extras): [ob for f in extras for ob in f(h, vw)]
        views.append(view)
    if iris_mm and np.isfinite(iris_mm):       # the turned views draw the limbus at the PICTURE's iris size (the limbus'
        for view in views:                     # plane lies 0.4 mm further forward for an iris 1.4 mm smaller)
            view["iris_mm"] = iris_mm
    return head, views, notes


def compare(name: str, rounds: int = 3, cam_sd=PHOTO_CAM_SD7, hair: bool = True, views: list | None = None,
            prior_off=None, lids: bool = False, lips: bool = False, shade: bool = False, anchors: str = "differential",
            parse: bool | str = False, normals: bool = False, cam_first: int = 0, adapt: bool = False, cam_reset: bool = True,
            cam_done0=None, cmax: float | None = None, relax0: float = 1.0, hold=None, held0=None, expr: bool | str = False,
            expr_sd: float | None = None, kinds: list | None = None, readers: list | None = None, jaw_lm=None,
            jaw: bool = False, chin: dict | None = None, dense: bool | None = None, mp: bool | None = None,
            hair_edge: bool | None = None, nostrils: bool | None = None, alar: bool | None = None) -> dict:
    """The face ruler on a block-in model: its reference pictures against the model, the 23 measures' gaps (picture -
    model, GNM's mm), largest first, each with the reader's error and its `mm:` move. {"rows", "text", "notes", "n"}."""
    only = views
    head, views, notes = reference_views(name, hair, lids=lids, lips=lips, shade=shade, anchors=anchors, parse=parse,
                                         normals=normals, kinds=kinds, readers=readers, jaw_lm=jaw_lm, expr=bool(expr), jaw=jaw, chin=chin, dense=dense,
                                         mp=mp, hair_edge=hair_edge, nostrils=nostrils, alar=alar)
    if only is not None:          # a subset of the pictures (indices): what one view alone says
        views = [v for i, v in enumerate(views) if i in set(int(j) for j in only)]
    tie = None
    tc = (chin or {}).get("tie", CHIN_TIE)
    sz = (chin or {}).get("size", SIZE_HOLD)
    if sz is not False and sz is not None:      # True: held at the start's; a number: held at that size against the start's
        tgt = 0.0 if sz is True else float(sz)
        tie = {"names": (), "size": True, "size_target": tgt}
        notes.append((chin or {}).get("size_note") or (
            "SIZE: the head's overall size is HELD at the block-in's start head's (the class mean on this body): no "
            "picture reads it (each camera's scale and distance are free), shape is free. block_in_solve(size=\"free\") "
            "releases it; size=\"iris\" lets the picture's iris pull it (weakly: +- 7 % person to person); teeth would read it better"))
    nk = (chin or {}).get("neck", NECK_HOLD)
    if nk is not False and nk is not None:
        # THE NECK (nativedefault). On a GNM-NATIVE head only (a body-carried head's neck is the body's: GNM's is faded
        # out): True / "prior" = ANSUR II's neck girth for the model's sex and stature as a PRIOR (its mean, its own sd);
        # "held" = held at that mean (+- 1 %); a number = held at that girth in real mm (on a body-carried head: GNM's own
        # mm, for benchmarks; chin["neck_sig"] sets its sigma)
        from . import onemesh, solve_report as sr, store as _store
        b_ = _store.load(name)["base"]
        nat = onemesh.native(b_)
        tgt = sig_ = None
        if nat:
            ns = onemesh.native_size(b_)
            given = not isinstance(nk, (bool, str))
            tgt = (float(nk) * 1e-3 if given else ns["neck"]) / ns["size"]
            sig_ = float((chin or {}).get("neck_sig") or (sr.NECK_SIG if (given or nk == "held") else ns["neck_sd"] / ns["neck"]))
            g0 = sr.neck_girth(head["c"])[0] * ns["size"]
            an = f"ANSUR II for this sex and stature ({ns['stature']:.3f} m): {1e3 * ns['neck']:.0f} +- {1e3 * ns['neck_sd']:.0f} mm"
            notes.append(
                (f"NECK: its girth is HELD at {1e3 * tgt * ns['size']:.0f} mm (+- {100 * sig_:.0f} %; " + ("given" if given else an) + ")"
                 if sig_ <= 0.02 else
                 f"NECK: an anthropometric PRIOR on its girth: {an} (a weak pull: GNM's correlations with the face the pictures "
                 "do read may still move it)")
                + f"; it stood at {1e3 * g0:.0f}. NO DIRECT READ: no picture reads the neck's girth, and GNM's identity moves it "
                  "36 mm per sd (its female class mean is 363, 11 % over ANSUR; its male 385). block_in_solve(neck=\"free\") "
                  "releases it, neck=\"held\" pins the mean, neck=<mm> holds a girth you measured")
        elif not isinstance(nk, (bool, str)):
            tgt, sig_ = float(nk) * 1e-3, float((chin or {}).get("neck_sig") or sr.NECK_SIG)
            notes.append(f"NECK: GNM's own neck girth at {float(nk):.0f} GNM mm +- {100 * sig_:.1f} % (a body-carried head: its neck is the body's)")
        if tgt:
            tie = {**(tie or {"names": ()}), "neck": tgt, "neck_sig": sig_}
    if tc:
        from . import solve_report as sr
        side = any(abs(view_yaw(v["cam"])) >= 60.0 for v in views)       # a side view's outline reads the profile line
        t35 = [abs(view_yaw(v["cam"])) for v in views]
        names = tuple(sr.TIE) if isinstance(tc, (bool, int, float)) else (tuple(tc.split("+")) if isinstance(tc, str) else tuple(tc))
        if any(TIE_OPEN[0] <= y <= TIE_OPEN[1] for y in t35):            # a TRUE 3/4: the far jaw and chin make its silhouette
            names = tuple(n for n in names if n not in ("jaw_width", "gonial_width", "jaw_square"))
            notes.append("CHIN / JAW: a view turned 35-60 deg shows the far jaw on its silhouette: jaw width and squareness are left to the pictures")
        tie = {**(tie or {}), "names": names, "given": sr.TIE_GIVEN + (sr.TIE_GIVEN_SIDE if side else ()), "sig": float((chin or {}).get("tie_sig", sr.TIE_SIG))}
    views_in = [dict(v) for v in views]
    res = read(head, views, rounds=rounds, cam_sd=cam_sd, cam_first=cam_first, cam_reset=cam_reset, adapt=adapt, cam_done0=cam_done0, cmax=cmax,
               relax0=relax0, hold=hold, held0=held0, tie=tie, expr_mode="shared" if expr == "shared" else "view", expr_sd=expr_sd,
               expr_prior=expr_prior_of(expr, views),
               **({} if prior_off is None else {"prior_off": prior_off}))
    from . import gnm_mm
    sd = gnm_mm.sd()
    for r in res["gaps"]:
        r["picture"] = r["current"] + r["gap"]
        r["err"] = float(np.hypot(r["err"], MODEL_ERR[r["measure"]]))
        r["read"] = float(max(0.0, 1 - (r["err"] / sd[r["measure"]]) ** 2))
    n = {t: sum(ob["type"] == t for ob in res["obs"]) for t in ("outline", "hairedge", "iris", "landmark", "limbus", "lid", "lip", "jaw", "cloth", "ramp", "shade", "normal", "dense", "mp", "nostril", "alar")}
    # OUTLINE READS PER VIEW (readmix): the total hid a front picture with none (loose hair: the figure's edge is hair)
    n_view = {v["kind"]: {t: sum(ob["type"] == t and ob["view"] == v["kind"] for ob in res["obs"]) for t in ("outline", "hairedge", "mp", "dense", "lip", "lid")} for v in views}
    notes = list(notes) + ["OUTLINE READS per view: " + "; ".join(
        f"{v.get('name', v['kind'])} ({v['kind']}): {n_view[v['kind']]['outline']}" + (f" + {n_view[v['kind']]['hairedge']} one-sided at the skin | hair edge" if n_view[v['kind']]["hairedge"] else "") for v in views)]
    for v in views:
        nv = n_view[v["kind"]]
        if nv["outline"] < OUTLINE_FEW:
            notes.append(f"NO OUTLINE: {v.get('name', v['kind'])} ({KIND_SAY.get(v['kind'], v['kind'])}) gives {nv['outline']} outline reads (the figure's edge there is hair, "
                         "cloth or a busy background, not skin)" + (f"; {nv['hairedge']} one-sided reads at the skin | hair edge say where the face is at least as wide" if nv["hairedge"] else "")
                         + (": the face's WIDTHS in this view (cheekbone, jaw, gonial) are " + ("the dense landmarks' and " if nv["dense"] else "") + "GNM's average for the rest of the head, not a measurement"
                            if v["kind"] != "profile" else ": the profile line is not read"))
    from . import mpread
    notes = list(notes) + mpread.nose_lines(res["obs"]) + nostril_lines(res["obs"], views)
    for r in res["orbit"]:        # the orbit rows' error: never under the block-in path's validated floor
        fl = np.sqrt(sum((w * MODEL_ERR[k]) ** 2 for k, w in gnm_mm.ORBIT_SEEN[r["row"]].items()))
        r["err"] = float(np.hypot(r["err"], fl))
        r["read"] = float(max(0.0, 1 - (r["err"] / r["sd"]) ** 2))
    cams = []
    cam_lines = []
    if res.get("cam_post"):
        try:
            from . import blockin_models
            st_ = [v.get("yaw", 0.0) or 0.0 for v in blockin_models._refs(name)["views"]]
            if only is not None:
                st_ = [x for i, x in enumerate(st_) if i in set(int(j) for j in only)]
        except Exception:  # noqa: BLE001
            st_ = None
        cam_lines = camera_lines(views_in, res["views"], res["cam_done"], cam_sd, st_)
    try:      # each view's stated kind against the camera the solve ended on
        from . import blockin_models
        rv_ = blockin_models._refs(name)["views"]
        if only is not None:
            rv_ = [v for i, v in enumerate(rv_) if i in set(int(j) for j in only)]
        notes = list(notes) + [x["warn"] for x in view_sanity(rv_, [v["cam"] for v in res["views"]]) if x["warn"]]
    except Exception:  # noqa: BLE001
        pass
    lim = sorted({(ob["view"], ob["name"][:8]) for ob in res["obs"] if ob["type"] == "limbus"})
    notes = list(notes) + [f"limbus read in: {', '.join(f'{a} {b}' for a, b in lim) or 'no turned view'}"]
    dis = disagreement(res)
    notes = list(notes) + dis["lines"]
    if res.get("relax", 1.0) > 1.0:
        notes.append(f"INCONSISTENT PICTURES: at their own sigmas the most likely head had a component past {cmax:g} sd; every "
                     f"read's sigma was raised x{res['relax']:.2f} until none did (the pictures disagree with each other or "
                     "with any one GNM head by that much: paintings, expressions, a wrong camera)")
    big = {k: v for k, v in (res.get("sig_scale") or {}).items() if v > 1.5}
    if big:
        notes.append("NOISIER than assumed (the head that fits best leaves these reads scattered; their sigma was raised by): "
                     + ", ".join(f"{t} {vw} x{v:.1f}" for (t, vw), v in sorted(big.items())))
    notes = list(notes) + cam_lines + distance_lines(res["views"], [v.get("lens") for v in views])
    per = {v["kind"]: sum(ob["view"] == v["kind"] for ob in res["obs"]) for v in views}
    head_txt = (f"face ruler: {name} against its {len(views)} pictures ({', '.join(f'{k}: {m} reads' for k, m in per.items())}); "
                "gap = picture - model in GNM's mm; cameras were fitted, so a shift / scale / roll of each picture is left free")
    views = res["views"]
    return {"rows": res["gaps"], "orbit": res["orbit"],
            "text": head_txt + "\n" + orbit_text(res["orbit"]) + "\n" + text(res["gaps"]) + ("\n" + "\n".join(notes) if notes else ""),
            "notes": notes, "n": n, "dc": res["dc"], "views": views, "head": head, "obs": res["obs"],
            "cam_done": res.get("cam_done"), "cam_post": res.get("cam_post"), "post": res.get("post"),
            "sig_scale": res.get("sig_scale") or {}, "relax": res.get("relax", 1.0), "cam_step": res.get("cam_step"),
            "held": res.get("held") or [], "tie": tie, "expr": res.get("expr") or {}, "kinds": [v["kind"] for v in views],
            "readers": [v.get("reader") for v in views], "camera_lines": cam_lines, "bound": res.get("bound") or [], "disagree": dis["groups"],
            "n_view": n_view, "inferred": distance_inferred(res["views"], [v.get("lens") for v in views])}




def nostril_lines(obs: list, views: list) -> list:
    """The nose's own reads, said per view: each nostril opening's ends against the model's rim (mm, + = the picture's
    opening reaches further out / further toward the midline than the model's), or that the picture shows none."""
    out = []
    for v in views:
        if v["kind"] == "profile":
            continue
        oo = [ob for ob in obs if ob["type"] == "nostril" and ob["view"] == v["kind"]]
        if oo:
            lat = {ob["name"][8]: ob["o"] for ob in oo if ob["name"].endswith("lateral")}
            wd = lat["l"] - lat["r"] if len(lat) == 2 else None      # (o runs along the line toward the subject's left)
            out.append(f"NOSE READ in {v.get('name', v['kind'])}: the nostril openings ({len(oo)} reads): "
                       + ", ".join(f"{ob['name'][8:].replace('_', ' ')} {ob['o']:+.1f} mm" for ob in oo)
                       + (f"; the openings' outer width picture - model {wd:+.1f} mm" if wd is not None else "")
                       + " (read at the call's last round: near 0 = the model's nostrils lie on the picture's)")
        elif (NOSTRIL and abs(view_yaw(v["cam"])) <= NOSTRIL_TURN):
            out.append(f"NOSE: no nostril opening found in {v.get('name', v['kind'])} (hidden under the tip, filled by a flat light, or a "
                       "moustache): the nose's WIDTH is not read in this view")
    return out


DISAGREE = 2.0        # a read group left at more than this many of its own sigmas (rms) after the solve is named


def disagreement(res: dict) -> dict:
    """WHY a solve is strained, by read type and picture (instead of one factor on every sigma): each group's rms
    residual after the solve in its own sigmas and in mm, the groups past DISAGREE named, and the identity components
    held at the bound. {"groups": {(type, view): {"n", "sig", "mm"}}, "lines"}."""
    obs, rs = res.get("obs") or [], res.get("resid")
    g = {}
    if rs is not None and len(rs) == len(obs):
        for ob, r in zip(obs, rs):
            if ob["type"] != "hold":
                g.setdefault((ob["type"], ob["view"]), []).append((float(r), float(r) * float(ob["sig"])))
    groups = {k: {"n": len(v), "sig": float(np.sqrt(np.mean([a * a for a, _ in v]))), "mm": float(np.sqrt(np.mean([b * b for _, b in v])))} for k, v in g.items()}
    lines = []
    bad = sorted(((k, x) for k, x in groups.items() if x["sig"] > DISAGREE and x["n"] >= 2), key=lambda t: -t[1]["sig"])
    if bad:
        lines.append("DISAGREE (reads the solved head and cameras still miss by more than " + f"{DISAGREE:g} of their own sigmas, rms): "
                     + "; ".join(f"{t} in the {vw} picture {x['sig']:.1f} sigma ({x['mm']:.1f} mm, {x['n']} reads)" for (t, vw), x in bad)
                     + ": that read, that picture's camera, or a shape GNM does not reach there")
    bd = res.get("bound") or []
    if bd:
        lines.append(f"AT THE BOUND: {len(bd)} identity component(s) held at the limit ({', '.join(str(i) for i in bd[:8])}): the reads ask for a head "
                     "more unusual than the bound allows there; nothing was down-weighted for it")
    return {"groups": groups, "lines": lines}


def overlay(res: dict, height: int = 640):
    """compare()'s pictures side by side: the model's outline (green), the matched outline reads (yellow: from the
    model's outline to the picture's), the iris reads (magenta = picture, cyan = model)."""
    from PIL import Image, ImageDraw
    tiles = []
    for v in res["views"]:
        im = v["img"].copy()
        d = ImageDraw.Draw(im)
        _, ps = clay(res["head"], v["cam"], passes=True)
        cm = _curve(ps["part"] >= 0)
        if cm is not None:
            d.line([tuple(p) for p in cm], fill=(0, 220, 0), width=2)
        for ob in res["obs"]:
            if ob["view"] != v["kind"]:
                continue
            if ob["type"] == "outline":
                d.line([tuple(ob["p"]), tuple(ob["q"])], fill=(255, 235, 0), width=2)
            else:
                for q, col in ((ob["q"], (255, 0, 255)), (ob["p"], (0, 255, 255))):
                    d.ellipse([q[0] - 6, q[1] - 6, q[0] + 6, q[1] + 6], outline=col, width=2)
        k = height / im.size[1]
        tiles.append(im.resize((int(im.size[0] * k), height), Image.LANCZOS))
    W = Image.new("RGB", (sum(t.size[0] for t in tiles), height), "white")
    x = 0
    for t in tiles:
        W.paste(t, (x, 0))
        x += t.size[0]
    return W
