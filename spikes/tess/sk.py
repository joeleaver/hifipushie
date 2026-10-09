"""sk.py <src> <dst> <skin patch json | ""> [head patch json] [tag]: copy src -> dst with a skin patch (and base.head
keys merged), render the face through v5's (and v4's) fitted camera under stage.FRONT_LIGHT, sample the same skin
patches as on v5, print ref | ours, save ref | ours pair to $T/out/<tag>.png."""
import copy, json, os, sys

import numpy as np
from PIL import Image

import stage
from hifipushie import server, store

T = os.environ["T"]
src, dst = sys.argv[1], sys.argv[2]
skp = json.loads(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else None
hp = json.loads(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else None
tag = sys.argv[5] if len(sys.argv) > 5 else dst
if src != dst:
    sp = copy.deepcopy(store.load(src))
    store.save(dst, sp, f"tess: copy of {src}")
    (store.HOME / dst / "human_refs.json").write_text((store.HOME / src / "human_refs.json").read_text())
if hp:
    sp = store.load(dst)
    h = sp["base"]["head"]
    for k, v in hp.items():
        if isinstance(v, dict) and isinstance(h.get(k), dict):
            h[k].update(v)
        else:
            h[k] = v
    store.save(dst, sp, f"tess: head {hp}")
if skp:
    print(server.skin(dst, skp, note=f"tess: skin {skp}")[:300])
refs = json.loads((store.HOME / dst / "human_refs.json").read_text())
frames = [stage.fitted_frame(c, [0, 0, 900, 900], f"f{i}") for i, c in enumerate(refs["cameras"])]
LIGHT = {**stage.FRONT_LIGHT, "exposure": float(os.environ.get("EXPO", stage.FRONT_LIGHT["exposure"]))}
shots = stage.shoot(dst, frames, LIGHT, size=900, hair_on=False)
PTS = {"forehead": (502, 128), "cheekR": (468, 203), "cheekL": (537, 203), "nose": (502, 195), "chin": (502, 238)}
ref = np.asarray(Image.open(T + "/ref/v5_face_x3.png").convert("RGB")).astype(float)
ours = np.asarray(shots["f0"]).astype(float)
for n, (x, y) in PTS.items():
    u, v = (x - 390) * 3, (y - 60) * 3
    pr = ref[v - 12:v + 12, u - 12:u + 12].reshape(-1, 3).mean(0)
    po = ours[v - 12:v + 12, u - 12:u + 12].reshape(-1, 3).mean(0)
    print(f"{n:9s} ref {pr.round(0)}  ours {po.round(0)}  ratio {(po / pr).round(2)}")
pair = Image.new("RGB", (1800 * 2 // 2, 900), (230, 230, 230))
r = [Image.open(T + "/ref/v5_face_x3.png").convert("RGB"), shots["f0"], Image.open(T + "/ref/v4_face_x3.png").convert("RGB"), shots["f1"]]
out = Image.new("RGB", (3600, 900))
for i, im in enumerate(r):
    out.paste(im.resize((900, 900)), (900 * i, 0))
out.save(f"{T}/out/{tag}.png")
out.resize((1400, 350)).save(f"{T}/out/{tag}_s.png")
print("saved", f"{T}/out/{tag}.png")
