"""mkhead.py <tag> <identity: model | mean | rand:<seed>:<sd>> [move=<measure>:<mm>,..] [light=photo|soft|top] [yaw=0,23,72]
[pitch=<deg>] [start=1]: a KNOWN head as a reference set (solvereads' mk_synth.py generalised; the chinread benchmark).
cz_<tag>_T = gg_A06's body, dressing and cameras with the given identity (a model's; the male class-mean start's = "mean";
that + a random GNM draw; then gnm_mm `mm:` moves), DRESSED EEVEE shots through gg_A06's three fitted cameras, re-turned
to the given yaws (the set's own: 0 / 23 / 72) and pitched (the head tilted DOWN by pitch > 0 in every view), under the
photo's fitted light, a SOFT frontal light (key from the camera, a wide source, a bright room) or a TOP light; pictures in
/mnt/data/hifipushie/chinread/synth/cz_<tag>_<view>.png. start=1: a block-in start cz_<tag>_00 from the male class mean
(detector points, the side view's 8 clicks from the truth, cameras refit)."""
import copy, json, os, sys
import numpy as np
sys.path[:0] = ["/home/joe/dev/hifipushie/spikes/garrett3"]
import stage
from hifipushie import blockin as bi, face_ruler as fr, gnm_mm, humanfit, resources, server, store

S = "/mnt/data/hifipushie/chinread/synth"
os.makedirs(S, exist_ok=True)
tag, src = sys.argv[1], sys.argv[2]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
moves = [(x.split(":")[0], float(x.split(":")[1])) for x in kw.get("move", "").split(",") if x]
light = kw.get("light", "photo")
yaws = [float(x) for x in kw.get("yaw", "").split(",") if x]
pitch = float(kw.get("pitch", 0))
T = f"cz_{tag}_T"
base = "gg_A06"
sp = copy.deepcopy(store.load(base))
rj = copy.deepcopy(bi._refs(base))
if src == "mean":
    c = bi.identity(store.load("gg_G00"))
elif src.startswith("rand:"):
    _, seed, sd = src.split(":")
    c = bi.identity(store.load("gg_G00")) + float(sd) * np.random.default_rng(int(seed)).standard_normal(170)
else:
    c = bi.identity(store.load(src))
for nm, mm in moves:
    c = c + gnm_mm.direction(nm) * mm
bi.set_identity(sp, c)
d = store._dir(T); d.mkdir(parents=True, exist_ok=True)
(d / "spec.json").write_text(json.dumps(sp))
cams = []
for vi, cam in enumerate(rj["cameras"]):
    if yaws:
        y0 = fr.view_yaw(cam)
        c1 = fr.cam_moved(cam, yaw=yaws[vi] - abs(y0))
        if abs(abs(fr.view_yaw(c1)) - yaws[vi]) > 1.0:
            c1 = fr.cam_moved(cam, yaw=-(yaws[vi] - abs(y0)))
        cam = c1
    if pitch:
        p0 = fr._cam_points(cam, np.asarray(humanfit.state(sp["base"])["L"], float)[[27, 8]])[1]
        c1 = fr.cam_moved(cam, pitch=pitch)
        p1 = fr._cam_points(c1, np.asarray(humanfit.state(sp["base"])["L"], float)[[27, 8]])[1]
        if (p1[1, 1] - p1[0, 1]) > (p0[1, 1] - p0[0, 1]) and False:
            pass
        cam = c1
    cams.append(cam)
rj["cameras"] = cams
rj["blockin"] = {**rj["blockin"], "root": T, "truth": {"identity": src, "moves": moves, "light": light, "yaw": yaws, "pitch": pitch}}
(d / "human_refs.json").write_text(json.dumps(rj))
lt = stage.photo_light(base, 0)
if light == "soft":       # a SOFT FRONTAL light: the key from the camera's side, a wide source, a bright room: little shade anywhere
    lt = copy.deepcopy(stage.FRONT_LIGHT)
    lt["lights"][0].update({"dir": [0.0, -0.97, 0.24], "energy": 2.2, "angle": 60})
    lt["lights"][1]["energy"] = 1.2
    lt["world"]["strength"] = 0.9
elif light == "top":      # a hard light from above
    lt = copy.deepcopy(stage.FRONT_LIGHT)
    lt["lights"][0].update({"dir": [0.1, -0.45, 0.89], "energy": 4.0, "angle": 12})
    lt["lights"][1]["energy"] = 0.35
    lt["world"]["strength"] = 0.3
views = []
L = np.asarray(humanfit.state(sp["base"])["L"], float)
CL = {"nose_tip": 30, "nose_base": 33, "nose_bridge": 27, "lip_upper": 51, "lip_lower": 57, "chin": 8, "eye_outer.L": 45, "mouth_corner.L": 54}
for vi, (v, cam) in enumerate(zip(rj["views"], cams)):
    f = f"{S}/cz_{tag}_{vi}.png"
    w, h = cam["size"]
    if not os.path.exists(f):
        with resources.heavy(f"synthetic reference {T} {vi}", gb=6):
            im = stage.shoot(T, [stage.fitted_frame(cam, [w / 2 - h / 2, 0.0, w / 2 + h / 2, float(h)], f"v{vi}")], lt, size=int(h), hair_on=False)[f"v{vi}"]
        x0 = int(round((h - w) / 2))
        im.convert("RGB").crop((x0, 0, x0 + int(w), int(h))).save(f)
    yw = abs(fr.view_yaw(cam))
    pts = {}
    if yw >= 60:
        P = humanfit.project(cam, L[list(CL.values())])
        pts = {k: [round(float(p[0]), 1), round(float(p[1]), 1)] for k, p in zip(CL, P)}
    views.append({"image": f, "size": [int(w), int(h)], "yaw": (v.get("yaw", 0) if not yaws else (yaws[vi] if yaws[vi] < 60 else -90)), "points": pts})
    print("shot", f, "camera yaw", round(yw, 1), flush=True)
# the truth model's own references = its own pictures and true cameras (readers validate against these)
rj["views"] = [dict(v) for v in views]
(d / "human_refs.json").write_text(json.dumps(rj))
if kw.get("start", "1") == "1":
    hs = copy.deepcopy(store.load("gj_G00"))
    hs["base"]["style"]["human"].pop("eye_spacing", None)
    for k in ("hair", "cloth"):
        hs.pop(k, None)
    holder = f"cz_{tag}_R"
    d = store._dir(holder); d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(hs))
    views = bi.with_anchor_points(views)
    (d / "human_refs.json").write_text(json.dumps({"views": views, "cameras": [None] * len(views)}))
    # the truth keeps the detector points too (differential anchors on the truth's own model: the null)
    rj["views"] = views
    (store._dir(T) / "human_refs.json").write_text(json.dumps(rj))
    r = server.block_in_start(f"cz_{tag}_00", holder, sex="male", age=52, cameras="refit", replace=True, save=f"{S}/cz_{tag}_00.png")
    print("\n".join(x for x in r if isinstance(x, str))[-300:])
