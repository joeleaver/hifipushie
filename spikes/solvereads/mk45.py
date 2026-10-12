"""mk45.py <tag> [deg=45]: the benchmark head sx_<tag> with its "3/4" picture re-shot at a TRUE 45 degrees (the set's
own is at 23): does a real 3/4, where the far jaw and chin make the silhouette, read the chin's and jaw's width?
sx_<tag>q_R / sx_<tag>q_00; truth stays sx_<tag>_T."""
import copy, json, os, sys
sys.path[:0] = ["/home/joe/dev/hifipushie/spikes/garrett3"]
import stage
from hifipushie import blockin as bi, face_ruler as fr, resources, server, store
tag = sys.argv[1]
deg = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0
S = "/mnt/data/hifipushie/solvereads/synth"
T = f"sx_{tag}_T"
rj = bi._refs(T)
cam = rj["cameras"][1]
y0 = fr.view_yaw(cam)
c1 = fr.cam_moved(cam, yaw=deg - abs(y0))
if abs(abs(fr.view_yaw(c1)) - deg) > 1.0:
    c1 = fr.cam_moved(cam, yaw=-(deg - abs(y0)))
print("3/4 camera:", y0, "->", fr.view_yaw(c1))
w, h = cam["size"]
f = f"{S}/sx_{tag}_q.png"
if not os.path.exists(f):
    with resources.heavy(f"synthetic 45 deg reference {T}", gb=6):
        im = stage.shoot(T, [stage.fitted_frame(c1, [w / 2 - h / 2, 0.0, w / 2 + h / 2, float(h)], "q")], stage.photo_light(T, 0), size=int(h), hair_on=False)["q"]
    x0 = int(round((h - w) / 2))
    im.convert("RGB").crop((x0, 0, x0 + int(w), int(h))).save(f)
src = bi._refs(f"sx_{tag}_R")
views = copy.deepcopy(src["views"])
views[1] = {"image": f, "size": [int(w), int(h)], "yaw": 45, "points": {}}
views = bi.with_anchor_points(views)
holder = f"sx_{tag}q_R"
d = store._dir(holder); d.mkdir(parents=True, exist_ok=True)
(d / "spec.json").write_text(json.dumps(store.load(f"sx_{tag}_R")))
(d / "human_refs.json").write_text(json.dumps({"views": views, "cameras": [None] * len(views)}))
r = server.block_in_start(f"sx_{tag}q_00", holder, sex="male", age=52, cameras="refit", replace=True, save=f"{S}/sx_{tag}q_00.png")
print("\n".join(x for x in r if isinstance(x, str))[-400:])
