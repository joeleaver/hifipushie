"""cu.py <model> <out dir> [tag=<suffix of the tile names>] ref=<model with the references> [own=<model with the fitted lights>] [size=700] [hair=1] [pose=json]:
single-feature CLOSE-UPS of a stored model through the reference cameras (dressed EEVEE, the tool's own fitted light per
view): tiles <out>/<feature>_v<i>.png and the reference crops <feature>_v<i>_ref.png. Features: mouth, eye (one eye, tight:
the iris), eyes (the eye region with the lids' folds). Views 0 and 1 (front, three-quarter). pose: a base.head.pose dict
rendered as its own set (suffix _pose), e.g. '{"lid_upper": 0.006}' = a blink. HEAVY."""
import json, os, sys
import numpy as np
from PIL import Image
import stage
from hifipushie import blockin as bi, humanfit, skin_project, store

m, out = sys.argv[1:3]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
ref, T, hair = kw.get("ref", m), int(kw.get("size", 700)), kw.get("hair", "1") == "1"
own = kw.get("own", m)
os.makedirs(out, exist_ok=True)
rj = bi._refs(ref)
F = bi.FEATURES
F.setdefault("cu_mouth", {"lm": list(range(48, 68)) + [33, 8], "pairs": [], "lines": [], "stages": (), "squint_mm": 2.0, "pad": 1.25})
F.setdefault("cu_eye", {"lm": list(range(42, 48)), "pairs": [], "lines": [], "stages": (), "squint_mm": 1.0, "pad": 1.9})
F.setdefault("cu_cheek", {"lm": [46, 47, 35, 13, 14, 54, 45], "pairs": [], "lines": [], "stages": (), "squint_mm": 2.0, "pad": 1.15})
F.setdefault("cu_face", {"lm": list(range(0, 68)), "pairs": [], "lines": [], "stages": (), "squint_mm": 6.0, "pad": 1.25})
F.setdefault("cu_eyes", {"lm": list(range(42, 48)) + [22, 23, 24, 25, 26], "pairs": [], "lines": [], "stages": (), "squint_mm": 2.0, "pad": 1.35})
F.setdefault("cu_eyesR", {"lm": list(range(36, 42)) + [17, 18, 19, 20, 21], "pairs": [], "lines": [], "stages": (), "squint_mm": 2.0, "pad": 1.35})
VI = [int(x) for x in kw.get("views", "0,1").split(",")][: len(rj["views"])]
meshes = bi._per_view(store.load(ref)["base"], rj, VI, lambda b: bi.presented_mesh(b, rj=rj))
rp = store._dir(own) / "skin_projection" / "report.json"
rep = json.loads(rp.read_text()) if rp.exists() else None
pose = json.loads(kw["pose"]) if kw.get("pose") else None
try:   # the eyes' mean axis (eye -> eye_front joints): the catchlight is aimed by it
    from hifipushie import skin as _skin
    _J = _skin._joints(store.load(m))
    _GAZE = sum((_J[f"eye_front{s_}"] - _J[f"eye{s_}"]) / np.linalg.norm(_J[f"eye_front{s_}"] - _J[f"eye{s_}"]) for s_ in (".L", ".R"))
    _GAZE = _GAZE / np.linalg.norm(_GAZE)
except Exception as _e:   # (no eye joints: the camera-relative window)
    print("catch: no gaze", _e); _GAZE = None
flat = kw.get("flat") == "1"
shots, first = [], None   # every view's close-ups, each under its own view's light: ONE Blender for the run
for vi in VI:
    cam = rj["cameras"][vi]
    L2 = humanfit.project(cam, meshes[vi]["state"]["L"])
    frames = []
    for f in ((("cheek",) if "only" not in kw else tuple(kw["only"].split(","))) if kw.get("rake") == "1" else tuple(kw.get("only", "mouth,eye,eyes").split(","))):
        b = [float(x) for x in bi._feature_box("cu_" + f, L2)]
        frames.append(stage.fitted_frame(cam, b, f"{f}_v{vi}"))
        Image.open(rj["views"][vi]["image"]).convert("RGB").crop(tuple(int(round(x)) for x in b)).resize((T, T), Image.LANCZOS).save(f"{out}/{f}_v{vi}_ref{('_' + kw['tag']) if kw.get('tag') else ''}.png")
    lt = ((rep or {}).get("views") or {}).get(str(vi), {}).get("light")
    light = skin_project.stage_light(lt) if lt else bi.photo_lighting(ref, stage.FRONT_LIGHT, vi)
    if kw.get("rake") == "1":   # a RAKING light: one low sun from the subject's side, across the cheek (relief)
        light = {"lights": [{"dir": [0.85, -0.25, -0.1], "energy": 3.5, "color": [1, 1, 1], "angle": 4},
                            {"dir": [0.0, -1.0, 0.1], "energy": 0.15, "color": [1, 1, 1], "angle": 40, "shadow": False, "specular": 0.0}],
                 "world": {"color": [1, 1, 1], "strength": 0.08}, "view": "Standard", "exposure": 0.0}
    if kw.get("neutral", "1" if kw.get("photo_neutral", "1") == "1" else "0") == "1" and kw.get("rake") != "1":   # the fitted light's directions and strengths, its COLOUR made white
        for l_ in light["lights"]:
            l_["color"] = [1.0, 1.0, 1.0]
        light["world"] = {**light.get("world", {}), "color": [1.0, 1.0, 1.0]}
    if float(kw.get("skin_key", 0)) > 0 and kw.get("rake") != "1":
        # the SKIN's specular key (2026-10-16, coordinator decision (a)): the photo's skin highlights come from its key light,
        # but the fitted light is soft suns with specular 0 (their discs lay in the cornea) and no key, so no roughness / oil
        # value moved the sheen rows. A highlight-only sun from the fitted light's dominant direction (energy-weighted mean of
        # its suns), its energy skin_key x theirs, light-linked to the skin part(s) only (skin_key_on, default body): the
        # eyes keep their catch window alone.
        _su = [l_ for l_ in light["lights"] if float(l_.get("diffuse", 1.0)) > 0 and not l_.get("window")]
        _e = np.array([float(l_.get("energy", 0)) for l_ in _su])
        if _su and _e.sum() > 0:
            _kd = (np.asarray([l_["dir"] for l_ in _su], float) * _e[:, None]).sum(0)
            _kd /= max(np.linalg.norm(_kd), 1e-9)
            light = {**light, "lights": list(light["lights"]) + [{"dir": _kd.tolist(), "energy": round(float(kw["skin_key"]) * float(_e.sum()), 4),
                     "color": list(_su[int(_e.argmax())].get("color", [1, 1, 1])), "angle": float(kw.get("skin_key_angle", 14)),
                     "diffuse": 0.0, "specular": 1.0, "shadow": False, "receivers": kw.get("skin_key_on", "body").split(",")}]}
    if kw.get("catch", "1") == "1" and kw.get("rake") != "1" and frames:
        _gaze = _GAZE
        # ONE catchlight and the face's sheen, as a studio photograph has (the fills carry no highlight): a soft box a little above the camera,
        # specular only, no shadow, weak (a strong one silvered the lashes and the nostrils)
        _d, _u = np.asarray(frames[0]["dir"], float), np.asarray(frames[0]["up"], float)
        _r = np.cross(_u, _d)
        dv = _d + float(kw.get("catch_up", 0.45)) * _u + float(kw.get("catch_x", -0.35)) * _r   # (catch_aim=camera: up and to the side)
        if kw.get("catch_aim", "gaze") == "gaze" and _gaze is not None:
            # aimed by the EYES (default): the window placed so its mirror image on the ball sits catch_deg above the gaze
            # axis (the pupil's upper edge, where a studio photo has it) and catch_side deg to the side, whatever the
            # head's gaze and lids (a fixed camera-relative window landed under a low lid: Garrett had none at 1.2 / .45).
            # -4 / -6 / sheen 1.6 put a hard square in the pupil's centre and mirrored the window on every camera-facing patch of
            # skin (all four heads' reviews: wet / plastic): 4 up (a low lid hides more) / -12 side and sheen 1.0. Still wet + square
            # (s14 / g8e): the window now lights ONLY the eyes part (catch_on=eyes, light linking; catch_on= for all, the old way)
            _up = _u - (_u @ _gaze) * _gaze; _up /= np.linalg.norm(_up)
            _n = _gaze + np.tan(np.radians(float(kw.get("catch_deg", 4)))) * _up + np.tan(np.radians(float(kw.get("catch_side", -12)))) * _r
            _n /= np.linalg.norm(_n)
            _v = _d / np.linalg.norm(_d)
            dv = 2 * (_n @ _v) * _n - _v
        dv /= np.linalg.norm(dv)
        # r3 (all heads): with the catch window linked to the eyes the skin read MATTE / plastic (no sheen on forehead, nose,
        # lips: Tess, Garrett, a private head). A second, LARGE, dim window (skin_sheen gain, sheen_size m) on every part
        # gives a broad soft sheen, not the small window's hard rectangle / wet streaks. skin_sheen=0 = off.
        if float(kw.get("skin_sheen", 0.35)) > 0:
            light = {**light, "lights": list(light["lights"]) + [{"dir": dv.tolist(), "energy": 0.6, "color": [1, 1, 1], "angle": 3,
                     "specular": 0.0, "diffuse": 0.0, "shadow": False, "window": {"receivers": None, "size": [float(x) for x in kw.get("sheen_size", "1.6,1.6").split(",")],
                     "distance": 2.5, "gain": float(kw.get("skin_sheen", 0.35))}}]}
        light = {**light, "lights": list(light["lights"]) + [{"dir": dv.tolist(), "energy": 0.6, "color": [1, 1, 1], "angle": 3,
                 "specular": 0.0, "diffuse": 0.0, "shadow": False, "window": {"receivers": ([p_ for p_ in kw.get("catch_on", "eyes").split(",") if p_] or None), "size": [float(x) for x in kw.get("catch_size", "0.4,0.5").split(",")], "distance": 2.5, "gain": float(kw.get("sheen", 1.0))}}]}
    first = first or light
    shots += [{**f, "lighting": light} for f in frames] if not flat else frames
if shots:
    for k, im in stage.shoot(m, shots, None if flat else first, size=T, hair_on=hair, posed=pose or False, flat=flat, engine=kw.get("engine", "eevee"), samples=int(kw.get("samples", 24)), eevee=json.loads(kw["eevee"]) if kw.get("eevee") else None).items():
        k = k + ("_flat" if flat else "")
        im.save(f"{out}/{k}{'_pose' if pose else ''}{'_rake' if kw.get('rake') == '1' else ''}{'_cy' if kw.get('engine') == 'cycles' else ''}{('_' + kw['tag']) if kw.get('tag') else ''}.png")
print("close-ups ->", out)
