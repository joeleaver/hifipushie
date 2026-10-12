"""shots.py <model> [engine=eevee] [size=768]: the DRESSED stage with the groom through the three references' fitted
cameras (the whole picture, squared) + views the pictures do not show (back three-quarter from her right, right
profile, back). Tiles in $TOUT/s_<model>_<view>[_cyc].png."""
import os, sys, json
import numpy as np
import stage
from hifipushie import render, resources, skin_look, store

m = sys.argv[1]
kw = dict(a.split("=") for a in sys.argv[2:])
eng, N = kw.get("engine", "eevee"), int(kw.get("size", 768))
OUT = os.environ["TOUT"]
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
W, H = 1152, 1536
BOX = [-(H - W) / 2, 0, W + (H - W) / 2, H]
suf = "_cyc" if eng == "cycles" else ""
frames = [stage.fitted_frame(refs["cameras"][v], BOX, f"v{v}") for v in range(3)]
J = skin_look._J(store.load(m))
nt = J["lm_nose_tip"]
c = np.array([0.0, nt[1] + 0.11, nt[2] - 0.03])
extra = []
for i, (n, d) in enumerate((("backl", [0.62, 0.78, 0.06]), ("backq", [-0.6, 0.8, 0.08]), ("right", [-1, 0.0, 0.0]))):
    d = np.asarray(d, float) / np.linalg.norm(d)
    extra.append(render.camera_frame({"eye": (c + d * 1.6).tolist(), "target": c.tolist(), "fov": 17.0, "name": n}, i))
with resources.heavy(f"tesshair shots {m}", gb=6):
    for v in ([] if kw.get("extra_only") else range(3)):
        im = stage.shoot(m, [frames[v]], stage.photo_light(m, v), size=N, hair_on=True, engine=eng)[f"v{v}"]
        im.save(f"{OUT}/s_{m}_v{v}{suf}.png")
    ims = stage.shoot(m, extra, stage.photo_light(m, 0), size=N, hair_on=True, engine=eng)
    for n, im in ims.items():
        im.save(f"{OUT}/s_{m}_{n}{suf}.png")
print("done", m)
