"""v0.py <model> [views=0,2] [size=768]: only the fitted-camera tiles (s_<model>_v<n>.png) on the shared stage: a
quick front / profile check before a whole round (then hline.py <model> 0)."""
import json, os, sys
import shared
shared.patch()
import stage
from hifipushie import resources, store

m = sys.argv[1]
kw = dict(a.split("=") for a in sys.argv[2:])
vs = [int(v) for v in kw.get("views", "0,2").split(",")]
N = int(kw.get("size", 768))
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
W, H = 1152, 1536
BOX = [-(H - W) / 2, 0, W + (H - W) / 2, H]
with resources.heavy(f"tesshair2 v0 {m}", gb=6):
    for v in vs:
        f = stage.fitted_frame(refs["cameras"][v], BOX, f"v{v}")
        stage.shoot(m, [f], stage.photo_light(m, v), size=N, hair_on=True)[f"v{v}"].save(f"{os.environ['TOUT']}/s_{m}_v{v}.png")
print("done", m)
