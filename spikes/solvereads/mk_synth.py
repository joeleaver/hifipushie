"""mk_synth.py <tag> <identity from model> [class=amount ...]: a KNOWN head as a reference set (the benchmark every part
of solvereads is validated on). sx_<tag>_T = gg_A06's body, dressing, cameras and light with the identity of <model>
and the given GNM expression (face_ruler.expression_coeffs: prototypes of gnm_sampler's classes; none = neutral);
DRESSED EEVEE shots of it through gg_A06's three fitted cameras (front, a 23 deg "3/4", a 72 deg "profile": the good
Garrett set's own angles), each the camera's whole 1152 x 1536 picture, in $S/synth/sx_<tag>_<view>.png; then a
block-in START on those pictures from the male class mean (sx_<tag>_00), exactly as spikes/garrettgood/start.py made
gg_G00 (detector points on front and 3/4, the profile's 8 "clicks" = the truth's own landmarks through its camera,
cameras refit). The truth's identity is NOT in the start model: solves are scored against sx_<tag>_T."""
import copy, json, os, sys
import numpy as np
from PIL import Image
sys.path[:0] = ["/home/joe/dev/hifipushie/spikes/garrett3"]
import stage
from hifipushie import blockin as bi, face_ruler as fr, humanfit, resources, server, store

S = "/mnt/data/hifipushie/solvereads/synth"
os.makedirs(S, exist_ok=True)
tag, src = sys.argv[1], sys.argv[2]
ex = {a.split("=")[0]: float(a.split("=")[1]) for a in sys.argv[3:]}
T = f"sx_{tag}_T"
base = "gg_A06"
sp = copy.deepcopy(store.load(base))
rj = copy.deepcopy(bi._refs(base))
bi.set_identity(sp, bi.identity(store.load(src)))
if ex:
    sp["base"]["head"]["expression"] = fr.expression_coeffs(ex)
d = store._dir(T); d.mkdir(parents=True, exist_ok=True)
(d / "spec.json").write_text(json.dumps(sp))
rj["blockin"] = {**rj["blockin"], "root": T, "truth": {"identity_of": src, "expression": ex}}
(d / "human_refs.json").write_text(json.dumps(rj))
views = []
L = np.asarray(humanfit.state(sp["base"])["L"], float)
CL = {"nose_tip": 30, "nose_base": 33, "nose_bridge": 27, "lip_upper": 51, "lip_lower": 57, "chin": 8, "eye_outer.L": 45, "mouth_corner.L": 54}
for vi, (v, cam) in enumerate(zip(rj["views"], rj["cameras"])):
    f = f"{S}/sx_{tag}_{vi}.png"
    w, h = cam["size"]
    if not os.path.exists(f):
        with resources.heavy(f"synthetic reference {T} {vi}", gb=6):
            im = stage.shoot(T, [stage.fitted_frame(cam, [w / 2 - h / 2, 0.0, w / 2 + h / 2, float(h)], f"v{vi}")], stage.photo_light(T, 0), size=int(h),
                             hair_on=False)[f"v{vi}"]
        x0 = int(round((h - w) / 2))
        im.convert("RGB").crop((x0, 0, x0 + int(w), int(h))).save(f)
    pts = {}
    if abs(float(v.get("yaw", 0))) >= 70:
        P = humanfit.project(cam, L[list(CL.values())])
        pts = {k: [round(float(p[0]), 1), round(float(p[1]), 1)] for k, p in zip(CL, P)}
    views.append({"image": f, "size": [int(w), int(h)], "yaw": v.get("yaw", 0), "points": pts})
    print("shot", f, flush=True)
hs = copy.deepcopy(store.load("gj_G00"))
hs["base"]["style"]["human"].pop("eye_spacing", None)
for k in ("hair", "cloth"):
    hs.pop(k, None)
holder = f"sx_{tag}_R"
d = store._dir(holder); d.mkdir(parents=True, exist_ok=True)
(d / "spec.json").write_text(json.dumps(hs))
views = bi.with_anchor_points(views)
(d / "human_refs.json").write_text(json.dumps({"views": views, "cameras": [None] * len(views)}))
r = server.block_in_start(f"sx_{tag}_00", holder, sex="male", age=52, cameras="refit", replace=True, save=f"{S}/sx_{tag}_00.png")
print("\n".join(x for x in r if isinstance(x, str)))
