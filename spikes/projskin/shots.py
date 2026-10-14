"""shots.py <model> <out dir> [ref=<model whose references / cameras frame the shots>] [size=700] [hair=1]: dressed EEVEE tiles
of a stored model (a fresh Blender per light): frames = each reference view's own camera (the face box) + unseen angles
(three_quarter_other, low_angle, high_angle, profile_other); lights = "photo" (each reference view's own fitted light;
the front view's for the unseen angles), "side" (a NEW hard key from the side the pictures did not light), "top".
Tiles: <out>/<frame>_<light>.png; the reference crops <out>/<frame>_ref.png. HEAVY (run through heavy.sh)."""
import json, os, sys
import numpy as np
from PIL import Image
import stage
from hifipushie import blockin as bi, humanfit, render, skin_look, store

m, out = sys.argv[1:3]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
ref, T, hair = kw.get("ref", m), int(kw.get("size", 700)), kw.get("hair", "1") == "1"
os.makedirs(out, exist_ok=True)
spec, rj = store.load(m), bi._refs(ref)
F = bi.FEATURES
F.setdefault("face", {"lm": list(range(0, 68)), "pairs": [], "lines": [], "stages": (), "squint_mm": 6.0, "pad": 1.25})
VI = list(range(len(rj["views"])))
meshes = bi._per_view(store.load(ref)["base"], rj, VI, lambda b: bi.presented_mesh(b, rj=rj))
frames, own = [], {}
for vi in VI:
    cam = rj["cameras"][vi]
    b = [float(x) for x in bi._feature_box("face", humanfit.project(cam, meshes[vi]["state"]["L"]))]
    own[vi] = stage.fitted_frame(cam, b, f"view{vi}")
    Image.open(rj["views"][vi]["image"]).convert("RGB").crop(tuple(int(round(x)) for x in b)).resize((T, T), Image.LANCZOS).save(f"{out}/view{vi}_ref.png")
J = skin_look._J(spec)
nt = J["lm_nose_tip"]
c = np.array([0.0, nt[1] + 0.085, nt[2] + 0.03])
from hifipushie import face_ruler as fr
yaws = [fr.view_yaw(rj["cameras"][vi]) for vi in VI]
sgn = -1.0 if np.mean(yaws) < 0 else 1.0     # camera on the subject's +x side for positive yaw (checked on the tiles)
D = {"three_quarter_other": [sgn * 0.66, -0.75, 0.05], "low_angle": [sgn * 0.2, -0.86, -0.47], "high_angle": [-sgn * 0.2, -0.82, 0.52],
     "profile_other": [sgn * 1.0, 0.0, 0.0]}
unseen = []
for n, d in D.items():
    d = np.asarray(d, float); d /= np.linalg.norm(d)
    unseen.append(render.camera_frame({"eye": (c + d * 1.25).tolist(), "target": (c - [0, 0, 0.02]).tolist(), "fov": 12.0, "name": n}, len(unseen)))
SIDE = {"lights": [{"dir": [sgn * 0.88, -0.42, 0.22], "energy": 3.6, "color": [1.0, 0.98, 0.96], "angle": 12},
                   {"dir": [-sgn * 0.3, -0.9, 0.3], "energy": 0.35, "color": [1.0, 1.0, 1.0], "angle": 40, "shadow": False, "specular": 0.0}],
        "world": {"color": [0.8, 0.8, 0.8], "strength": 0.25}, "view": "Khronos PBR Neutral", "exposure": -0.3}
TOP = {"lights": [{"dir": [0.05, -0.25, 0.97], "energy": 3.8, "color": [1.0, 0.99, 0.97], "angle": 16},
                  {"dir": [0.0, -1.0, 0.1], "energy": 0.3, "color": [1.0, 1.0, 1.0], "angle": 40, "shadow": False, "specular": 0.0}],
       "world": {"color": [0.8, 0.8, 0.8], "strength": 0.25}, "view": "Khronos PBR Neutral", "exposure": -0.3}
front = bi._front(rj)
own_m = kw.get("own", m)       # the model whose skin projection's FITTED lights are the "photo light" (default: this one)
_rp = store._dir(own_m) / "skin_projection" / "report.json"
_rep = json.loads(_rp.read_text()) if _rp.exists() else None
def photo(vi):
    """The picture's light: the tool's OWN fitted light of that view (skin_project.stage_light: what a caller gets),
    else the judging sheets' template re-aimed (blockin.photo_lighting)."""
    lt = ((_rep or {}).get("views") or {}).get(str(vi), {}).get("light") if _rep else None
    if lt:
        from hifipushie import skin_project
        return skin_project.stage_light(lt)
    return bi.photo_lighting(ref, stage.FRONT_LIGHT, vi)
def save(d, tag):
    for k, im in d.items():
        im.save(f"{out}/{k}_{tag}.png")
allf = [own[vi] for vi in VI] + unseen
only = kw.get("lights", "photo,side,top").split(",")
if "photo" in only:
    for vi in VI:
        save(stage.shoot(m, [own[vi]] + (unseen if vi == front else []), photo(vi), size=T, hair_on=hair), "photo")
if "side" in only:
    save(stage.shoot(m, allf, SIDE, size=T, hair_on=hair), "side")
if "top" in only:
    save(stage.shoot(m, allf, TOP, size=T, hair_on=hair), "top")
if "flat" in only:
    save(stage.shoot(m, allf, None, size=T, hair_on=False, flat=True), "flat")
print("tiles ->", out, "yaws", [round(y) for y in yaws], "sgn", sgn)
