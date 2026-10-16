"""cu.py <model> <out dir> ref=<model with the references> [own=<model with the fitted lights>] [size=700] [hair=1] [pose=json]:
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
flat = kw.get("flat") == "1"
shots, first = [], None   # every view's close-ups, each under its own view's light: ONE Blender for the run
for vi in VI:
    cam = rj["cameras"][vi]
    L2 = humanfit.project(cam, meshes[vi]["state"]["L"])
    frames = []
    for f in ((("cheek",) if "only" not in kw else tuple(kw["only"].split(","))) if kw.get("rake") == "1" else tuple(kw.get("only", "mouth,eye,eyes").split(","))):
        b = [float(x) for x in bi._feature_box("cu_" + f, L2)]
        frames.append(stage.fitted_frame(cam, b, f"{f}_v{vi}"))
        Image.open(rj["views"][vi]["image"]).convert("RGB").crop(tuple(int(round(x)) for x in b)).resize((T, T), Image.LANCZOS).save(f"{out}/{f}_v{vi}_ref.png")
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
    if kw.get("catch", "1") == "1" and kw.get("rake") != "1" and frames:
        # ONE catchlight and the face's sheen, as a studio photograph has (the fills carry no highlight): a soft box a little above the camera,
        # specular only, no shadow, weak (a strong one silvered the lashes and the nostrils)
        _d, _u = np.asarray(frames[0]["dir"], float), np.asarray(frames[0]["up"], float)
        _r = np.cross(_u, _d)
        dv = _d + 1.2 * _u + float(kw.get("catch_x", -0.9)) * _r   # (up and to the side: on the iris' edge, not on the pupil)
        dv /= np.linalg.norm(dv)
        light = {**light, "lights": list(light["lights"]) + [{"dir": dv.tolist(), "energy": 0.6, "color": [1, 1, 1], "angle": 3,
                 "specular": 0.0, "diffuse": 0.0, "shadow": False, "window": {"size": [0.25, 0.3], "distance": 2.5, "gain": float(kw.get("sheen", 1.0))}}]}
    first = first or light
    shots += [{**f, "lighting": light} for f in frames] if not flat else frames
if shots:
    for k, im in stage.shoot(m, shots, None if flat else first, size=T, hair_on=hair, posed=pose or False, flat=flat, engine=kw.get("engine", "eevee"), samples=int(kw.get("samples", 24))).items():
        k = k + ("_flat" if flat else "")
        im.save(f"{out}/{k}{'_pose' if pose else ''}{'_rake' if kw.get('rake') == '1' else ''}{'_cy' if kw.get('engine') == 'cycles' else ''}.png")
print("close-ups ->", out)
