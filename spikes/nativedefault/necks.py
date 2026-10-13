"""necks.py <model> [light=<model>] [tile=640]: DRESSED EEVEE tiles of the neck and shoulders (front, side, three-quarter;
hair on) and the head from the front / side (unfitted cameras), from the model's own landmarks:
$S/out/<model>/dressed/neck_front|neck_side|neck_34.png; and the FULL FIGURE front / side (server.look, the model's own
dressing): figure_front.png, figure_side.png. Reference crops of the lower part of each picture: neck_ref_v<i>.png."""
import os, sys
import numpy as np
from PIL import Image
_S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(_S, "garrett3"), os.path.join(_S, "tour")]
import stage  # noqa: E402
from hifipushie import blockin as bi, humanfit, onemesh, render, resources, server, skin_read, store  # noqa: E402

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
T = int(kw.get("tile", 640))
out = f"/mnt/data/hifipushie/nativedefault/out/{m}/dressed"
os.makedirs(out, exist_ok=True)
spec = store.load(m)
L = np.asarray(humanfit.state(spec["base"])["L"], float)
r = onemesh.attach_report(spec["base"])
chin = L[8]
tgt = np.array([0.0, chin[1] + 0.06, chin[2] - 0.5 * r["chin_over_pit"] - 0.015])
frames = []
for nm, d in (("neck_front", [0, -1, 0.0]), ("neck_side", [1, 0.0, 0.0]), ("neck_34", [0.66, -0.75, 0.05])):
    d = np.asarray(d, float) / np.linalg.norm(d)
    frames.append(render.camera_frame({"eye": (tgt + d * 1.4).tolist(), "target": tgt.tolist(), "fov": float(kw.get("fov", 10.0)), "name": nm}, len(frames)))
light = skin_read.photo_light(kw.get("light", m), 0)
with resources.heavy(f"nativedefault necks {m}", gb=8):
    ims = stage.shoot(m, frames, light, size=T, hair_on=bool(spec.get("hair")))
    for k, im in ims.items():
        im.convert("RGB").resize((T, T), Image.LANCZOS).save(f"{out}/{k}.png"); print(f"{out}/{k}.png")
    fc = 0.5 * (L[27] + L[8])
    for v in ("front", "side"):   # the head in CLAY (no paint, no hair): GNM's surface as meshed
        server.look(m, views=[v], size=T, resolution=300, shading="clay", paint=False, focus=[0.0, float(fc[1]) + 0.07, float(fc[2]) + 0.02],
                    zoom=5.6 * r["stature"] / 1.7 * 0.214 / r["head_height"], **({"hide_parts": ["hair"]} if spec.get("hair") else {}), save=f"{out}/clay_{v}.png")
        print(f"{out}/clay_{v}.png")
    if kw.get("figure", "1") == "1":
        for v in ("front", "side"):
            server.look(m, views=[v], size=1100, resolution=260, save=f"{out}/figure_{v}.png"); print(f"{out}/figure_{v}.png")
rj = bi._refs(m)
for vi, v in enumerate(rj["views"]):
    img = Image.open(v["image"]).convert("RGB")
    W, H = img.size
    img.crop((int(0.1 * W), H - int(0.8 * W), int(0.9 * W), H)).resize((T, T), Image.LANCZOS).save(f"{out}/neck_ref_v{vi}.png")
