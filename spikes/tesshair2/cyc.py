"""cyc.py <model> <tag>=<look json> ... [view=0] [size=640] [engine=cycles]: the hair's LOOK (colour, sheen) tried in
Cycles through a reference's fitted camera and photo light, one render a variant on the shared stage (the look merged
into the model's in memory, nothing saved). Tiles $TOUT/cyc_<model>_<tag>_v<view>.png + a row with the picture first.
Cycles is heavy: under the machine-wide slot, one at a time."""
import copy, json, os, sys
from PIL import Image, ImageDraw
import shared
shared.patch()
import stage, iso, hline
from hifipushie import resources, store

m = sys.argv[1]
args = [a.split("=", 1) for a in sys.argv[2:]]
kw = {k: v for k, v in args if k in ("view", "size", "engine")}
vs = [(k, json.loads(v)) for k, v in args if k not in kw]
v, N, eng = int(kw.get("view", 0)), int(kw.get("size", 640)), kw.get("engine", "cycles")
OUT = os.environ["TOUT"]
spec = store.load(m)
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
W, H = 1152, 1536
f = stage.fitted_frame(refs["cameras"][v], [-(H - W) / 2, 0, W + (H - W) / 2, H], f"v{v}")
sn = stage.ensure(m)
sh = Image.new("RGB", (N * (1 + len(vs)), N + 18), "white")
d = ImageDraw.Draw(sh)
sh.paste(hline.photo_tile(refs["views"][v]["image"], N), (0, 18))
with resources.heavy(f"tesshair2 cyc {m}", gb=8):
    for j, (tag, lk) in enumerate(vs):
        sp = copy.deepcopy(spec)
        sp["hair"]["look"] = {**(sp["hair"].get("look") or {}), **lk}
        im = iso.shoot_spec(sn, sp, [f], stage.photo_light(m, v), size=N, engine=eng)[f"v{v}"]
        im.save(f"{OUT}/cyc_{m}_{tag}_v{v}.png")
        sh.paste(im, ((j + 1) * N, 18))
        d.text(((j + 1) * N + 4, 3), f"{tag} {json.dumps(lk)}"[:110], fill=(0, 0, 0))
        print("done", tag, flush=True)
p = f"{OUT}/cyc_{m}_{'_'.join(t for t, _ in vs)}_v{v}.png"
sh.save(p)
print(p)
