"""skintour.py <model> [out dir] [features=...] [tile=480] [proj=1]: THE FEATURE TOUR FOR SKIN / DRESSING. One small
image per feature and view: reference crop | the model DRESSED (its own skin) through the same camera, crop and the
picture's fitted light | 50 % overlay | (proj=1) the references projected as skin = the bar. Same feature boxes as
tour.py (blockin._feature_box on the model's landmarks, shifted like focus's registration is NOT done here: the
crop is the camera's own, so a shape offset shows as an offset).
Two uses (Joe, 2026-10-12: "this pattern will also really help you judge the texture work, and also set up the
textures"): JUDGE a dressing feature by feature; and SET UP: look at the reference crop alone and list what the skin
must carry there (stubble edge, lip colour and border, brow shape, lines, bags, moles) before reading / fitting."""
import os, sys
sys.path[:0] = ["/home/joe/dev/hifipushie/spikes/garrett3", os.path.dirname(os.path.abspath(__file__))]
from PIL import Image
import stage
from hifipushie import blockin as bi, humanfit, resources, store
import tour  # noqa: F401  (registers the chin / brow_forehead features; its main part is guarded below)

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:] if "=" in a)
out = next((a for a in sys.argv[2:] if "=" not in a), f"/mnt/data/hifipushie/tour/{m}_skin")
os.makedirs(out, exist_ok=True)
T = int(kw.get("tile", 480))
proj = kw.get("proj", "1") == "1"
feats = kw.get("features", "eyes,brow_forehead,nose,mouth,chin,chin_jaw,cheeks").split(",")
rj = bi._refs(m)
VI = list(range(len(rj["views"])))
meshes = bi._per_view(store.load(m)["base"], rj, VI, lambda b: bi.presented_mesh(b, rj=rj))
order = [i for i in VI if i != bi._front(rj)] + [bi._front(rj)]
BOXES, FRAMES = {}, []   # every view's features in ONE Blender (each frame under its own view's light)
for vi in VI:
    cam = rj["cameras"][vi]
    L2 = humanfit.project(cam, meshes[vi]["state"]["L"])
    BOXES[vi] = {f: [float(x) for x in bi._feature_box(f, L2)] for f in feats}
    light = stage.photo_light(m, vi)
    FRAMES += [{**stage.fitted_frame(cam, b, f"{f}@{vi}"), "lighting": light} for f, b in BOXES[vi].items()]
with resources.heavy(f"skin tour {m}", gb=6):
    OWN = stage.shoot(m, FRAMES, FRAMES[0]["lighting"], size=T, hair_on=False)
    PRJ = stage.shoot(m, FRAMES, FRAMES[0]["lighting"], size=T, hair_on=False, tex=order) if proj else {}
for vi in VI:
    v, boxes = rj["views"][vi], BOXES[vi]
    own = {f: OWN[f"{f}@{vi}"] for f in boxes}
    prj = {f: PRJ[f"{f}@{vi}"] for f in boxes} if proj else {}
    img = Image.open(v["image"]).convert("RGB")
    for f, b in boxes.items():
        ph = img.crop(tuple(int(round(x)) for x in b)).resize((T, T), Image.LANCZOS)
        def flat(im):
            bg = Image.new("RGB", im.size, (200, 200, 200))
            bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
            return bg.resize((T, T), Image.LANCZOS)
        tiles = [ph, flat(own[f]), Image.blend(ph, flat(own[f]), 0.5)] + ([flat(prj[f])] if proj else [])
        W = Image.new("RGB", (T * len(tiles), T), "white")
        for k, t in enumerate(tiles):
            W.paste(t, (k * T, 0))
        p = f"{out}/{f}_v{vi}.png"
        W.save(p); print(p)
