"""Steps: expression_step, step, solve_step, the iris size, step_text. Part of the block-in (blockin.py has the overview)."""
from __future__ import annotations

import copy
import json
import time

import numpy as np

from . import blockin_models
from .blockin import (
    BODY_KEYS, GNM_EXPR_SET, GNM_SET, HEAD_KEYS, LOCAL_SD, POSE_KEYS, SHAPE_MOVES, _macro_read, direction,
    identity, set_identity, vocabulary,
)
from .blockin_expression import EXPR_COMPS, EYE_COMPS, fit_expression
from .blockin_models import (
    NATIVE_REFUSE, _adopt_log, _boxes, _log_path, _next_name, _placement, _save, cameras_fit, fit_cameras, log,
)
from .blockin_table import FEATURES, feature_table, passes, table, table_delta

def expression_step(src: str, out: str | None = None, views: list | None = None, clear: bool = False,
                    comps: dict | None = None, eyes: bool = False, seen: str = "", why: str = "") -> dict:
    """A block-in round that changes no shape: <out> = <src> with the views' expressions fitted on its head (default:
    every view with a detector, |yaw| < 70; a profile's few clicks can't separate expression from shape) or cleared.
    Fit it once the big forms are in (on the class mean it would soak up identity), refit after large identity moves.
    The report is step()'s (table before -> after)."""
    from . import store
    sp = copy.deepcopy(store.load(src))
    rj = copy.deepcopy(blockin_models._refs(src))
    if "blockin" not in rj:
        raise ValueError(f"{src}: not a block-in model (block_in_start first)")
    n = len(rj["views"])
    VI = ([i for i in range(n) if abs(float(rj["views"][i].get("yaw", 0))) < 70] if views is None
          else [int(v) for v in views])
    ex = list(rj.get("expressions") or []) + [{}] * (n - len(rj.get("expressions") or []))
    fits = {}
    for vi in VI:
        if clear:
            ex[vi] = {}
            continue
        f = fit_expression(sp["base"], rj["views"][vi], rj["cameras"][vi], comps=comps or ({**EXPR_COMPS, **EYE_COMPS} if eyes else None))
        ex[vi], fits[vi] = f["expression"], f
    rj["expressions"] = ex
    out = out or _next_name(src)
    if (store.HOME / out / "spec.json").exists():
        raise ValueError(f"{out} exists: block-in steps write new models")
    t0 = table(src)
    _save(out, sp, f"block_in expression from {src}: views {VI}" + (" cleared" if clear else " fitted"), rj)
    t1 = table(out)
    lg = log(src)
    if lg and lg[-1].get("to") != src:
        lg[-1]["reverted"] = f"the next step went from {src}, not {lg[-1].get('to')}"
    c = identity(sp)
    entry = {"round": 1 + max([e.get("round", 0) for e in lg] or [0]), "from": src, "to": out, "moves": {},
             "expression": {str(vi): ("cleared" if clear else {"chi2": fits[vi]["chi2"], "norm": fits[vi]["norm"]})
                            for vi in VI},
             "seen": seen, "why": why or "per-picture expression (the identity unchanged)", "c_norm": round(float(np.linalg.norm(c)), 3),
             "read": {}, "coupled": [], "camera_moves": [], "passes": passes(t1), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    lg.append(entry)
    _log_path(rj, out).write_text(json.dumps(lg, indent=1))
    return {"entry": entry, "c0": entry["c_norm"], "big": [], "delta": table_delta(t0, t1), "table": t1,
            "before": passes(t0), "fits": fits}


def expression_text(rep: dict) -> str:
    s = []
    for vi, f in (rep.get("fits") or {}).items():
        top = sorted(f["expression"].items(), key=lambda t: -abs(t[1]))[:6]
        s.append(f"view {vi}: expression fitted, chi2 {f['chi2'][0]} -> {f['chi2'][1]} over {f['points']} points, |e| "
                 f"{f['norm']} ({', '.join(f'{k} {v:+.2f}' for k, v in top)})")
    return "\n".join(s + [step_text(rep)])


def over_sd(move: str, v: float) -> bool:
    """A hand move past 1 population sd: mm: moves are in mm, read against that measure's own sd; the rest are in sd."""
    if move.startswith("mm:"):
        from . import gnm_mm
        return abs(v) > float(gnm_mm.sd()[move[3:].rstrip("!")])
    return abs(v) > 1.0


def step(src: str, moves: dict, out: str | None = None, seen: str = "", why: str = "",
         cameras: list | None = None, feature: str | None = None, _identity=None, _head_set: dict | None = None) -> dict:
    """<out> = <src> moved: directions add (amount x direction), base keys and lids are SET. Logged with what was seen
    and why. cameras = view indices to refit on the result head (camera only). Returns the report (see step_text)."""
    from . import store
    if not moves and not cameras and _identity is None and not _head_set:
        raise ValueError("block_in_step: no moves. Vocabulary:\n" + vocabulary())
    if "attach" in (moves or {}):
        raise ValueError('block_in_step: {"attach": "native"} is a step of its own (blockin_models.native_step)')
    sp = copy.deepcopy(store.load(src))
    rj = blockin_models._refs(src)
    c0 = identity(sp)
    c = c0.copy()
    big, designed = [], []
    sculpts = {}
    idx_extra, iris_mm, neck = {}, None, None
    from . import onemesh
    if onemesh.native(sp["base"]):
        # (nativedefault) on a GNM-native head these keys do NOTHING (onemesh drops them): refused, not silently ignored
        bad = [k for k in (moves or {}) if k in NATIVE_REFUSE]
        if bad:
            raise ValueError("; ".join(f"block_in_step {k}: REFUSED on a GNM-native head: {NATIVE_REFUSE[k]}" for k in bad)
                             + ". (A child or a stylised figure: edit_model set_key base.head.size.)")
    for k, v in (moves or {}).items():
        v = float(v)
        if k in BODY_KEYS:
            sp["base"]["body"][k] = v
        elif k in HEAD_KEYS:
            sp["base"]["head"][HEAD_KEYS[k]] = v
        elif k == "head_scale":
            sp["base"].setdefault("style", {}).setdefault("human", {})["head_size"] = v
        elif k in POSE_KEYS:
            sp["base"]["head"].setdefault("pose", {})[k] = v
        elif k.startswith("id:") and k[3:].startswith(GNM_SET):   # GNM's eye / teeth identity components, SET (sd)
            idx_extra[k[3:]] = v
            if abs(v) > 3.0:
                big.append(f"{k} (past 3 sd)")
        elif k.startswith("ex:") and k[3:].startswith(GNM_EXPR_SET):   # the pupil / tongue expression components, SET
            sp["base"]["head"].setdefault("expression", {})[k[3:]] = v
        elif k == "iris_mm":   # the iris' diameter (mm at the model): GNM's limbus component, solved after the identity
            iris_mm = v
        elif k == "neck_mm":   # the neck's girth at its narrowest (real mm), SET: the least identity change, the head's
            from . import solve_report as sr   # size and the face's measures held (no picture reads the neck)
            if not onemesh.native(sp["base"]):
                raise ValueError("neck_mm: a body-carried head's neck is the BODY's (GNM's own neck is faded out under the "
                                 "jaw): change the body, or switch the head ({\"attach\": \"native\"})")
            nm_ = sr.neck_move(c, v * 1e-3 / onemesh.native_size(sp["base"])["size"])
            c = c + nm_["dc"]
            neck = nm_
            if nm_["cost"] > 2.0:
                big.append(f"neck_mm (|dc| {nm_['cost']:.1f})")
        elif k.startswith("shape:"):   # DESIGNED soft-tissue ops (age): not data; flagged in the log and reply
            from . import faceslide, headage
            nm = k[6:]
            if nm not in SHAPE_MOVES:
                raise ValueError(f"shape: one of {', '.join(SHAPE_MOVES)} (designed ops: faceslide's age sliders in "
                                 "their units, headage's ops in m / share)")
            if nm in faceslide.AGE_SLIDERS:
                sp["base"]["head"].setdefault("sliders", {})[nm] = v
            else:
                assert nm in headage.KEYS
                sp["base"]["head"].setdefault("shape", {})[nm] = v
            designed.append(k)
        elif k.startswith("local:"):
            from . import faceslide
            nm = k[6:]
            if nm not in faceslide.UNITS:
                raise ValueError(f"local: no slider {nm!r} (faceslide: {', '.join(sorted(faceslide.UNITS))})")
            sp["base"]["head"].setdefault("sliders", {})[nm] = v
            if nm in LOCAL_SD and abs(v) > 2.5 * LOCAL_SD[nm]:
                big.append(f"{k} (population sd {LOCAL_SD[nm]})")
        elif k.startswith(("sculpt:", "relief:")):
            from . import gnm_controls as gcm
            sc = gcm.sculpt(**gcm.parse_sculpt(k))
            c = c + v * sc["dc"]
            sculpts[k] = {"mm": v, "cost": round(abs(v) * sc["cost"], 2), "released": sc["released"],
                          "outside_mm": round(abs(v) * sc["outside_mm"], 3)}
            if abs(v) * sc["cost"] > 2.0:
                big.append(f"{k} (|dc| {abs(v) * sc['cost']:.1f})")
        else:
            c = c + v * direction(k)
            if over_sd(k, v):
                big.append(k)
    hood = None
    if "hooding" in (moves or {}):
        from . import gnm_fold
        hood = [gnm_fold.read_text(gnm_fold.read(gnm_fold.vertices(x))) for x in (c0, c)]
    if _identity is not None:   # (solved steps: blockin_eyes.eye_step) the identity given, head keys set / cleared
        c = np.asarray(_identity, float)
    for k, v in (_head_set or {}).items():
        if v is None:
            sp["base"]["head"].pop(k, None)
        else:
            sp["base"]["head"][k] = v
    set_identity(sp, c)
    for k, v in idx_extra.items():
        from . import base_identity, base_implied
        if k not in [str(n) for n in base_identity._gnm_data()["identity_names"]]:
            raise ValueError(f"id:{k}: not a GNM identity component (eyes_000..002, teeth_000..079)")
        sp["base"]["head"]["identity"][k] = round(v, 5)
    if iris_mm is not None:
        from . import base_identity, base_implied
        if sp["base"]["head"].get("eye_radius"):
            raise ValueError("iris_mm: the head overrides GNM's eyeball (base.head.eye_radius); with the override the drawn "
                             "iris is skin.eyes.iris_size. Drop the key first (block_in_step {\"eye_radius\": 0})")
        li = base_implied.limbus_identity(sp, iris_mm)
        sp["base"]["head"]["identity"]["eyes_000"] = li["eyes_000"]
        if isinstance((sp.get("skin") or {}).get("eyes"), dict):   # (the dressing's own drawn size would hide the limbus)
            sp["skin"]["eyes"].pop("iris_size", None)
    out = out or _next_name(src)
    if (store.HOME / out / "spec.json").exists():
        raise ValueError(f"{out} exists: block-in steps write new models (revert = step again from an earlier one)")
    rj = copy.deepcopy(rj)
    adopted = "blockin" not in rj   # a model made outside the tools (an older loop, a fit): this step roots a new log
    if adopted:
        rj["blockin"] = {"root": out, "boxes": _boxes(store.load(src)["base"], rj)}
    cam_moves = []
    if "head_scale" in (moves or {}):
        # the head scales about the NECK: the face rises / drops, which a refit would answer by moving the camera back
        # (distance trades with size: a head_scale of 1.06 came back as the same pixels). Each camera follows the face's
        # landmark centre instead (centre shifted with it: the same point at the same pixel, the size change visible)
        from . import humanfit
        d = humanfit.state(sp["base"])["L"][:68].mean(0) - humanfit.state(store.load(src)["base"])["L"][:68].mean(0)
        for i, cam in enumerate(rj["cameras"]):
            if not cameras or i not in [int(j) for j in cameras]:
                cam["centre"] = (np.asarray(cam["centre"], float) + d).tolist()
        cam_moves.append(f"cameras follow the face centre ({1000 * float(np.linalg.norm(d)):.1f} mm)")
    if "mm:eyes_forward" in (moves or {}) and "head_scale" not in (moves or {}):
        d = eye_follow(store.load(src)["base"], sp["base"])
        for i, cam in enumerate(rj["cameras"]):
            if not cameras or i not in [int(j) for j in cameras]:
                cam["centre"] = (np.asarray(cam["centre"], float) + d).tolist()
        cam_moves.append(f"cameras follow the face ({1000 * float(np.linalg.norm(d)):.1f} mm: the one mesh hangs the head on its "
                         "eyes, so an eye moved forward ships as the face moved back; the pictures' profile line stays on the face)")
    if cameras:
        from . import humanfit
        new = fit_cameras(sp["base"], rj["views"], rj)
        for i in cameras:
            a, b = rj["cameras"][int(i)], new[int(i)]
            Rd = humanfit._cam_rot(a).T @ humanfit._cam_rot(b)
            ang = float(np.degrees(np.arccos(np.clip((np.trace(Rd) - 1) / 2, -1, 1))))
            cam_moves.append(f"view {i}: turned {ang:.1f} deg, distance x{b['t'][2] / a['t'][2]:.3f}, focal x{b['f'] / a['f']:.3f}")
            rj["cameras"][int(i)] = b
    pl = (rj.get("blockin") or {}).get("placement")
    if pl is not None and json.loads(json.dumps(pl)) == json.loads(json.dumps(_placement(store.load(src)["base"]))):
        rj["blockin"]["placement"] = list(_placement(sp["base"]))   # (a step's own size / base moves keep the cameras in step)
    _save(out, sp, f"block_in_step from {src}: {json.dumps(moves)}" + (f" cameras {cameras}" if cameras else ""), rj)
    r0, r1 = _macro_read(c0), _macro_read(c)
    names = {k.rstrip("!") for k in (moves or {})}
    read = {k: [round(r0[k], 2), round(r1[k], 2)] for k in names if k in r1}
    moved = [kv for kv in sorted(((k, r1[k] - r0[k]) for k in r1 if k not in names), key=lambda t: -abs(t[1]))[:5]
             if abs(kv[1]) >= 0.05]
    t0, t1 = table(src), table(out)
    lg = _adopt_log(src) if adopted else log(src)
    rnd = 1 + max([e.get("round", 0) for e in lg] or [0])
    if lg and lg[-1].get("to") != src:
        lg[-1]["reverted"] = f"the next step went from {src}, not {lg[-1].get('to')}"
    if feature and feature not in FEATURES:
        raise ValueError(f"feature: one of {', '.join(FEATURES)}")
    entry = {"round": rnd, "from": src, "to": out, "moves": moves, "cameras": cameras, "camera_moves": cam_moves,
             "feature": feature, "seen": seen, "why": why, **({"designed": designed} if designed else {}),
             **({"sculpt": sculpts} if sculpts else {}), **({"hooding": hood} if hood else {}),
             **({"neck": {"girth0": neck["girth0"], "girth": neck["girth"], "cost": neck["cost"], "moved": neck["moved"]}} if neck else {}),
             "c_norm": round(float(np.linalg.norm(c)), 3), "read": read,
             "coupled": [[k, round(float(x), 2)] for k, x in moved],
             "passes": passes(t1), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    lg.append(entry)
    _log_path(rj, out).write_text(json.dumps(lg, indent=1))
    if feature:
        ft0, ft1 = feature_table(src, feature), feature_table(out, feature)
        entry["feature_passes"] = [passes(ft0)[feature], passes(ft1)[feature]]
        _log_path(rj, out).write_text(json.dumps(lg, indent=1))
    manual = None
    if seen:   # (gnmdrive) the driving manual's entries for what was seen: the controls it would have picked
        from . import gnm_manual
        manual = gnm_manual.suggest(seen, top=2)
    return {"entry": entry, "c0": float(np.linalg.norm(c0)), "big": big, "delta": table_delta(t0, t1),
            "table": t1, "before": passes(t0), "manual": manual}


# block_in_solve's defaults (solvereads, 2026-10-12; each decided by the validation in the notes' "## solvereads")
SOLVE_HOLD = None            # "auto": every measure no read looks at is held at the start head's value
SOLVE_EXPRESSION = False     # "view" | "shared": the pictures' expression as a nuisance (face_ruler_blockin.EXPR_SET)
SOLVE_JAW_LM = None          # detector landmarks added to the differential anchors (the jaw line: 3..13)
CAM_FIRST = 1                # cameras-first rounds of every block_in_solve call (the head held; "refit": 2, wider, and the new start)
SEESAW_COS = -0.2            # a step whose cosine with the last call's step is under this is halved
RELAX_KEEP = 0.85            # the cmax down-weighting comes down at most this share a call (it goes up at once)


def solve_step(src: str, out: str | None = None, share: float = 1.0, rounds: int = 3, seen: str = "",
               cameras: str = "free", lids: bool = True, lips: bool = True, anchors: str = "differential",
               parse: bool | str = "auto", normals: bool = False, adapt: bool = True, cmax: float | None = 3.0,
               hold=SOLVE_HOLD, expression=SOLVE_EXPRESSION, jaw_lm=SOLVE_JAW_LM, report: bool = True,
               damp: bool = True, chin: dict | None = None, dense: bool | None = None, mp: bool | None = None,
               hair_edge: bool | None = None, nostrils: bool | None = None) -> dict:
    """ONE JOINT STEP (reruns, 2026-10-11): the face ruler's own solve applied whole. face_ruler_compare.compare reads every
    reference view at once (skin outlines, iris centres, the turned views' limbus) and finds the most likely identity
    change under GNM's prior with each camera's shift / scale / roll / yaw / pitch free; until now only the measures
    were read off it. Here `share` of that change becomes the step and the cameras the solve ended on are kept (read
    through the old cameras the result looks a size wrong). Tess from the class mean: one step = |c| 5.4 -> 10.7,
    table 22 / 26, about where ten hand rounds got. It does NOT see the inside of the face (lids, lips' borders, the
    nose's planes): the eye and lips steps follow. -> step()'s report + "solve": {"n", "dc", "c", "max_sd", "cameras"}."""
    from . import store
    from . import face_ruler_camera, face_ruler_compare
    c0 = identity(store.load(src))
    # the prior is on the WHOLE identity: centred on the block-in's start head (its class mean), not on this call's
    # change (a second call used to move |dc| 4 more and walk a component to 3.1 sd)
    root = (blockin_models._refs(src).get("blockin") or {}).get("root")
    off = None
    if root and (store.HOME / root / "spec.json").exists():
        off = c0 - identity(store.load(root))
    if cameras not in ("free", "trust", "refit"):
        raise ValueError('block_in_solve: cameras = "free" (fitted cameras: shift / scale / roll / yaw / pitch / distance under '
                         'a wide prior: face_ruler_camera.PHOTO_CAM_SD7), "trust" (measured cameras: a third of those widths) or '
                         '"refit" (cameras fitted on ANOTHER head: laid on this head first, then free). A prior, never a '
                         'clip, on the WHOLE camera move since the block-in started: use the same setting on every call.')
    k = 1.0 / 3.0 if cameras == "trust" else 1.0
    rj0 = blockin_models._refs(src)
    # (nativedefault) CAMERAS MUST BELONG TO THIS HEAD. A head switched to GNM-native by an edit is 10-20 % larger and
    # stands elsewhere: the solve would read every outline through cameras of another head (its camera freedom is a
    # few per cent). Measured, then DEMANDED: the step that carries them is one call
    from . import onemesh
    sp_src = store.load(src)
    cam_notes = []
    cf = cameras_fit(sp_src["base"], rj0)
    if cf["stale"]:
        raise ValueError(
            f"block_in_solve: {src}'s cameras do not belong to its head (through them the head is x{cf['scale']:.2f} the pictures' "
            f"own points, {cf['off']:.2f} of the face's spread off centre)"
            + (": the head was switched to GNM-native after they were fitted. block_in_step(name, {\"attach\": \"native\"}) carries "
               "them onto the head's new size and place (a new model); then block_in_solve" if onemesh.native(sp_src["base"]) else
               ": refit them (block_in_step(name, {}, cameras=[0, 1, ..]) or a new block_in_start(cameras=\"refit\"))"))
    pl0 = (rj0.get("blockin") or {}).get("placement")
    moved = pl0 is not None and json.loads(json.dumps(pl0)) != json.loads(json.dumps(_placement(sp_src["base"])))
    if ((rj0.get("blockin") or {}).get("cam_carried") or moved) and cameras == "free":
        cam_notes.append(("CAMERAS: the head's size / place on the body changed since they were fitted (an edit of "
                          "base.head.attach / size / head_size): " if moved else "CAMERAS: carried from another head's fit: ")
                         + 'laid on THIS head first this call (cameras="refit" instead of "free"); later calls use what you pass')
        cameras = "refit"
    cam0 = None if cameras == "refit" else (rj0.get("blockin") or {}).get("cam_done")
    cam_sd = {kk: tuple(k * x for x in v) for kk, v in face_ruler_camera.PHOTO_CAM_SD7.items()}
    from . import denselm
    if (face_ruler_camera.DENSE if dense is None else dense) and denselm.available():      # the dense landmarks read perspective (distance to 5-9 %)
        cam_sd = {kk: tuple(v[:6]) + (k * face_ruler_camera.PHOTO_CAM_DIST_DENSE,) for kk, v in cam_sd.items()}
    b0 = rj0.get("blockin") or {}
    # (readmix) A KNOWN LENS holds its view's distance, dense or not: the prior is on the whole move since block_in_start,
    # whose fit stood at that lens
    lens_notes = []
    kinds0 = b0.get("kinds") or [face_ruler_compare.kind_of(v.get("yaw", 0)) for v in rj0["views"]]
    for v_, kk in zip(rj0["views"], kinds0):
        lm_ = face_ruler_camera.lens_known(v_)
        if lm_ and kk in cam_sd and len(cam_sd[kk]) > 6 and cam_sd[kk][6] > face_ruler_camera.PHOTO_CAM_DIST_LENS:
            cam_sd[kk] = tuple(cam_sd[kk][:6]) + (face_ruler_camera.PHOTO_CAM_DIST_LENS,)
            lens_notes.append(f"LENS: {str(v_.get('image', kk)).split('/')[-1]} was taken through a known {lm_:.0f} mm lens (35 mm equivalent): its camera's "
                              f"distance is held to +- {face_ruler_camera.PHOTO_CAM_DIST_LENS:g} % of the start's")
    # carried across the block-in's calls: the down-weighting the pictures needed (it may come down 15 % a call, never
    # jump), each view's kind (from its fitted camera at the first solve) and its outline reader
    relax0 = 1.0 + RELAX_KEEP * (float(b0.get("relax", 1.0)) - 1.0)
    chin = dict(chin or {})
    size_info = None
    if chin.get("size") in ("iris", "iris_pin"):
        # THE IRIS AS A RULER OF SIZE (gnmnative, 2026-10-12): the front picture's limbus (px, through this head's
        # fitted camera = mm at the model) against GNM's MEAN limbus on this head (eyes_000 = 0) says how large the
        # head is: GNM's eyeball is absolute, a head's size is not. "iris": that read at its person-to-person sigma
        # (SIZE_IRIS_SIG 7 %) combined with GNM's own spread of head size about the start (the class mean): a weak
        # pull. "iris_pin": the size the iris says, whole (an average iris assumed). Not read (a small picture: under
        # blockin_eyes.MIN_IRIS_PX of iris radius; a head that overrides GNM's eyeball): held at the start's.
        size_info = iris_size(src, off)
        mode = chin["size"]
        if size_info["read"]:
            w = 1.0 if mode == "iris_pin" else size_info["weight"]
            chin["size"] = float(w * size_info["iris_size"]) or 1e-9
            chin["size_note"] = (f"SIZE: {'PINNED by' if mode == 'iris_pin' else 'pulled by'} the picture's IRIS: its limbus is "
                                 f"{size_info['photo_mm']:.2f} mm at the model against GNM's mean {size_info['mean_mm']:.2f} mm here, so an "
                                 f"average iris says the head is {100 * size_info['iris_size']:+.1f} % against the start head's size "
                                 f"(+- {100 * size_info['iris_sd']:.0f} % person to person); GNM's own spread of size about the start is +- "
                                 f"{100 * size_info['prior_sd']:.1f} %"
                                 + (f": combined {100 * chin['size']:+.1f} % +- {100 * size_info['combined_sd']:.1f} % is held this call"
                                    if mode == "iris" else f": {100 * chin['size']:+.1f} % is held this call")
                                 + " (shape free; no picture reads size itself)")
        else:
            chin["size"] = True
            chin["size_note"] = ("SIZE: held at the start head's: " + size_info["why"])
    c = face_ruler_compare.compare(src, rounds=rounds, prior_off=off, cam_sd=cam_sd, lids=lids, lips=lips, anchors=anchors, parse=parse,
                   normals=normals, adapt=adapt, cam_first=2 if cameras == "refit" else CAM_FIRST, cam_reset=cameras == "refit", cmax=cmax,
                   cam_done0=cam0 if cam0 is not None else np.zeros((len(rj0["views"]), 7)),
                   relax0=relax0, hold=hold, held0=b0.get("held") if hold == "auto" else None, expr=expression, kinds=b0.get("kinds"), readers=b0.get("readers"), jaw_lm=jaw_lm, chin=chin, dense=dense,
                   mp=mp, hair_edge=hair_edge, nostrils=nostrils)
    dc = float(share) * np.asarray(c["dc"], float)
    # THE SEE-SAW: a settled solve hops back and forth by |dc| 2-2.6 a call (Tess 2.6, 2.0, 2.6 with the cosine of
    # consecutive steps -0.4 .. -0.5: reads that come and go, the lids' and lips' re-linearisation). A step that turns
    # back on the last one is halved: the middle of the see-saw is the head both calls agree on.
    # And once it has see-sawed the block-in is at its fixed point's door: every later step stays halved (undamped
    # calls in between stepped 2.2-2.6 again: Tess 2.6, 1.0d, 2.6, 1.7d).
    last = b0.get("last_dc")
    damped = float(b0.get("damped", 1.0)) if damp else 1.0
    if last is not None and damp and damped == 1.0:
        last = np.asarray(last, float)
        cs = float(dc @ last / max(np.linalg.norm(dc) * np.linalg.norm(last), 1e-12))
        if cs < SEESAW_COS:
            damped = 0.5
    dc = damped * dc
    rep = step(src, {}, out=out, seen=seen or "the face ruler's joint solve (outlines, irises, limbus; every view)",
               why=f"its solved identity change applied ({share:g} of it): |dc| {np.linalg.norm(dc):.2f}", _identity=c0 + dc)
    to = rep["entry"]["to"]
    rp = store.HOME / to / "human_refs.json"
    rj = json.loads(rp.read_text())
    for i, v in enumerate(c["views"]):
        rj["cameras"][i] = {**rj["cameras"][i], **{k: (np.asarray(x).tolist() if hasattr(x, "tolist") else x) for k, x in v["cam"].items()}}
    rj.setdefault("blockin", {})["cam_done"] = np.round(np.asarray(c["cam_done"], float), 4).tolist()   # the cameras' whole
    rj["blockin"].pop("cam_carried", None)              # (they have been laid on this head now)
    rj["blockin"]["placement"] = list(_placement(sp_src["base"]))
    fb = (b0.get("fallback") or {})
    fb_note = ["FALLBACK: what no picture reads stays at " + (fb.get("say") or "the pooled mean of GNM's classes (none given)")
               + ("" if fb.get("source") == "GIVEN" else ": INFERRED (block_in_start(ethnicity=<class> | {class: weight}) sets it; a shape parameter, not a label)")]
    c["notes"] = cam_notes + lens_notes + fb_note + list(c["notes"])
    rj["blockin"].update(relax=round(float(c["relax"]), 4), kinds=list(c["kinds"]), readers=list(c["readers"]),
                         last_dc=np.round(dc, 5).tolist(), damped=damped)
    if c.get("held"):
        rj["blockin"]["held"] = list(c["held"])
    xp = {pc: {n: [round(v, 3), round(sd_, 3)] for n, (v, sd_) in d.items()} for pc, d in (c.get("expr") or {}).items()}
    if xp:
        rj["blockin"]["solve_expression"] = xp
    rp.write_text(json.dumps(rj))                       # move since the start: the next call's prior is on all of it
    t0, t1 = rep["table"], table(to)          # (the table again, through the solve's cameras)
    rep.update(table=t1, delta=table_delta(table(src), t1))
    rep["entry"]["passes"] = passes(t1)
    rep["solve"] = {"n": c["n"], "dc": float(np.linalg.norm(dc)), "c": float(np.linalg.norm(c0 + dc)), "notes": c["notes"],
                    "max_sd": float(np.abs(c0 + dc).max()), "sig_scale": {f"{t} {v}": round(float(x), 2) for (t, v), x in c["sig_scale"].items()}, "cameras": np.round(np.asarray(c["cam_done"], float), 2).tolist(),
                    "camera_step": np.round(np.asarray(c["cam_step"], float), 2).tolist(), "relax": float(c["relax"]),
                    "held": list(c.get("held") or []), "expression": xp, "damped": damped, "kinds": list(c["kinds"]), "readers": list(c["readers"]),
                    "view_yaw": [round(abs(face_ruler_camera.view_yaw(v["cam"])), 1) for v in c["views"]],
                    "stated_yaw": [abs(float(v.get("yaw", 0.0) or 0.0)) for v in rj0["views"]], "camera_lines": list(c.get("camera_lines") or []), "bound": list(c.get("bound") or []),
                    "disagree": {f"{t} {v}": round(x["sig"], 2) for (t, v), x in (c.get("disagree") or {}).items()},
                    "n_view": c.get("n_view") or {}, "inferred": c.get("inferred") or {}}
    if c.get("tie"):
        rep["solve"]["chin"] = {"tied": list(c["tie"].get("names") or ()), "size_held": bool(c["tie"].get("size")),
                                "size_target": float(c["tie"].get("size_target") or 0.0)}
    if size_info is not None:
        rep["solve"]["size"] = {k: v for k, v in size_info.items()}
    if onemesh.native(sp_src["base"]):
        from . import solve_report as sr
        ns = onemesh.native_size(sp_src["base"])
        g0, g1 = sr.neck_girth(c0)[0] * ns["size"], sr.neck_girth(c0 + dc)[0] * ns["size"]
        held = (c.get("tie") or {}).get("neck")
        sg = float((c.get("tie") or {}).get("neck_sig") or 0.0)
        rep["solve"]["neck"] = {"before": g0, "after": g1, "held": bool(held), "target": float(held) * ns["size"] if held else None,
                                "sig": sg, "mode": "free" if not held else ("held" if sg <= 0.02 else "prior"),
                                "ansur": ns["neck"], "ansur_sd": ns["neck_sd"]}
        rep["solve"]["head_size"] = {"size": ns["size"], "allometric": ns["allometric"], "stature": ns["stature"]}
    if report and c.get("post") is not None:      # WHAT WAS READ, and what moved without a read (solve_report)
        from . import solve_report as sr
        croot = c0 - off if off is not None else None
        sup = sr.support(c["post"], c["obs"], groups=False)
        drc = sr.direct(c["post"], c["obs"], c["views"], c["head"])
        rp_ = sr.report(sup, c0 + dc, croot if croot is not None else c0, drc=drc)
        rep["solve"]["report"] = {"text": rp_["text"], "rows": rp_["rows"]}
    return rep


def iris_size(name: str, off=None) -> dict:
    """The head's size as the front picture's IRIS says it (a CHECK, and block_in_solve(size="iris")'s read):
    {"read", "photo_mm" (the picture's limbus diameter in mm at the model, through its fitted camera), "mean_mm" (GNM's
    mean limbus on this head: the identity's eyes_000 at 0), "now" (the head's size now against the start's, from the
    identity), "iris_size" (the size against the start's that would make an AVERAGE iris fit), "iris_sd" (0.07: irises
    differ +- 7 % between people), "prior_sd" (GNM's spread of head size), "weight" / "combined_sd" (the two combined),
    "text"}. off: the identity's change since the block-in's start (default: read from the log's root)."""
    from . import blockin_eyes as be, solve_report as sr, store
    from . import base_implied
    sp = store.load(name)
    if off is None:
        root = (blockin_models._refs(name).get("blockin") or {}).get("root")
        off = identity(sp) - identity(store.load(root)) if root and (store.HOME / root / "spec.json").exists() else np.zeros(170)
    now = float(sr.size_gain() @ np.asarray(off, float))
    psd, isd = sr.size_prior_sd(), sr.SIZE_IRIS_SIG
    out = {"read": False, "now": now, "iris_sd": isd, "prior_sd": psd, "weight": psd ** 2 / (psd ** 2 + isd ** 2),
           "combined_sd": float(1 / np.sqrt(1 / psd ** 2 + 1 / isd ** 2))}
    if base_implied.eye_native(sp) is None:
        return {**out, "why": "the head overrides GNM's eyeball (base.head.eye_radius): its iris is not GNM's limbus",
                "text": "IRIS SIZE CHECK: not read (the head overrides GNM's eyeball)"}
    try:
        ic = be.iris_check(name)
    except ValueError as e:
        return {**out, "why": str(e)[:120], "text": f"IRIS SIZE CHECK: not read ({str(e)[:80]})"}
    if not ic.get("photo_mm"):
        return {**out, "why": f"the front picture's iris is too small to read (under {be.MIN_IRIS_PX:.0f} px of radius)",
                "text": f"IRIS SIZE CHECK: not read (the front picture's iris is under {be.MIN_IRIS_PX:.0f} px of radius)"}
    sp0 = copy.deepcopy(sp)
    if isinstance(sp0["base"]["head"].get("identity"), dict):
        sp0["base"]["head"]["identity"].pop("eyes_000", None)
    if isinstance((sp0.get("skin") or {}).get("eyes"), dict):
        sp0["skin"]["eyes"].pop("iris_size", None)
    mean_mm = 2000.0 * float(base_implied.eye_native(sp0)["limbus"])
    rel = mean_mm / float(ic["photo_mm"]) - 1.0          # how much larger the head must be than NOW for an average iris
    tot = (1 + now) * (1 + rel) - 1
    out.update(read=True, photo_mm=float(ic["photo_mm"]), mean_mm=mean_mm, iris_now=rel, iris_size=tot)
    from . import onemesh
    nat = onemesh.native(sp["base"])
    out["native"] = nat
    out["text"] = (f"IRIS SIZE CHECK{' (a GNM-native head: the model is in real millimetres)' if nat else ' (a body-carried head: the model is NOT in real mm; the ratio is what counts)'}: "
                   f"the picture's limbus is {ic['photo_mm']:.2f} mm at the model, GNM's mean limbus here "
                   f"{mean_mm:.2f} mm: an average iris says the head is {100 * rel:+.1f} % against its size now "
                   f"({100 * tot:+.1f} % against the start head's; the identity stands at {100 * now:+.1f} %). +- {100 * isd:.0f} % "
                   f"person to person; with GNM's spread of size (+- {100 * psd:.1f} %) that is {100 * out['weight'] * tot:+.1f} % +- "
                   f"{100 * out['combined_sd']:.1f} %")
    return out


def eye_follow(base0: dict, base1: dict) -> np.ndarray:
    """The move (world, m) of the face's landmarks OFF the eyes and brows between two bases: what a camera's centre
    must follow after an eye-depth move. The one mesh seats the head by its eyes, so mm:eyes_forward +d ships as the
    eyes where they were and the rest of the face d further back; a camera left alone would see the whole profile
    line slide off the picture's and the eye stay put (el_o3's symptom)."""
    from . import humanfit
    off = [i for i in range(68) if not (17 <= i < 27 or 36 <= i < 48)]
    return (np.asarray(humanfit.state(base1)["L"], float)[off] - np.asarray(humanfit.state(base0)["L"], float)[off]).mean(0)


def step_text(rep: dict) -> str:
    e = rep["entry"]
    s = [f"{e['to']} (round {e['round']}, from {e['from']}): |c| {rep['c0']:.2f} -> {e['c_norm']:.2f}"]
    if e["read"]:
        s.append("moved (macro sd, before -> after): " + ", ".join(f"{k} {a:+.2f} -> {b:+.2f}" for k, (a, b) in e["read"].items()))
    if e["coupled"]:
        s.append("coupled (largest other macro changes, sd): " + ", ".join(f"{k} {v:+.2f}" for k, v in e["coupled"]))
    for k, v in (e.get("sculpt") or {}).items():
        s.append(f"{k} {v['mm']:+g} mm: |dc| {v['cost']:.2f} (macros held"
                 + (f"; let go as the target itself: {', '.join(v['released'])}" if v["released"] else "")
                 + f"; the face's skin beyond 6 mm of the zone moves {v['outside_mm']:.2f} mm rms)")
    if e.get("neck"):
        n_ = e["neck"]
        s.append(f"neck girth (GNM's own mm, at its narrowest): {1e3 * n_['girth0']:.0f} -> {1e3 * n_['girth']:.0f}; |dc| {n_['cost']:.2f}; "
                 "size and the face's measures held; moved most: " + ", ".join(f"{a} {b:+.2f} {u}" for a, b, u in n_["moved"]))
    if e.get("hooding"):
        s.append(f"hooding (GNM's raw lid rings, mm): before {e['hooding'][0]}\n                                   after  {e['hooding'][1]}"
                 "\n  (hooding moves the ORBIT: read face_ruler's orbit rows and brow_read again, then the eye step)")
    if e.get("camera_moves"):
        s.append("cameras refitted (landmarks only: a camera fit does not see the outline): " + "; ".join(e["camera_moves"]))
    if rep["big"]:
        s.append(f"WARNING: {', '.join(rep['big'])}: more than 1 sd (a local: 2.5 of its population sd) in one step: the "
                 "method takes small steps (0.3-0.7)")
    if e.get("designed"):
        s.append(f"DESIGNED (not data): {', '.join(e['designed'])}: hand-authored soft-tissue ops (sizes chosen by eye, "
                 "not learnt from people); judge them zoomed in under the raking light against the pictures")
    if e.get("feature_passes"):
        s.append(f"ZOOM IN, {e['feature']}'s own checklist rows: {e['feature_passes'][0]} -> {e['feature_passes'][1]} pass")
    s.append("ZOOM OUT, targets before -> after: " + ", ".join(f"{g} {rep['before'].get(g, '-')} -> {p}" for g, p in e["passes"].items()))
    if rep["delta"]:
        s.append("items that changed (model - photo, tol):")
        s += ["  " + x for x in rep["delta"]]
    if (rep.get("manual") or {}).get("entries"):
        from . import gnm_manual
        s.append("MANUAL for what you saw (guide topic gnm_driving; compare with the move you took):\n"
                 + gnm_manual.text(rep["manual"]))
    s.append(f"keep it only if the whole face reads closer AND no target went out; else step again from {e['from']} "
             "(this model stays as the record).")
    return "\n".join(s)
