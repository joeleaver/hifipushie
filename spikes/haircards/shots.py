"""shots.py <model> [stage=<model whose head stage is used>] [size=768] [samples=8] [views=v0,v1,v2,backl] [tag=]
[like=<model>] [glb=<hair GLB> params=<json> alpha=game cutoff=0.33 only=<json tri ranges>]: hair renders for the
hair-cards gates, ALL views in ONE Blender start (per-view light rigs: blender_scene.render's view "lights"), each with
the hair's id pass at the same frame (an exact hair mask): $TOUT/s_<model><tag>_<v>.png, id_<model><tag>_<v>.png.
- views v0, v1, v2: the reference pictures' fitted cameras under the fitted photo light (spikes/tesshair7 shots7);
  backl / backq / right / back / left / front / crown / top: the front light turned round with the camera.
- like=<model>: THAT model's cameras, moved and scaled with the head (scalp centre / median radius): the same view
  OF THE HEAD, for a groom re-seated on a different head (hair.reseat).
- glb=: an exported hair GLB drawn as a game draws it (blender_cards.game_material: the export's shading notes) in
  place of the model's strand groom; only= keeps triangle ranges (the report's "layers") to isolate one.
Light by design: 768 px, 8 samples by default (heavy hair renders reset the laptop's GPU, 2026-10-14); full renders
go to the offload machine (spikes/haircards/job_cards.py)."""
import copy
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

import stage
from hifipushie import hair, render, resources, scene, skin_look, store

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
N = int(kw.get("size", 768))
views = kw.get("views", "v0,v1,v2,backl").split(",")
OUT = os.environ["TOUT"]
TAG = kw.get("tag", "")
spec = store.load(m)
like = kw.get("like")
refs = json.loads((store.HOME / (like or m) / "human_refs.json").read_text())
if like:
    sc_a, sc_b = hair.scalp(like), hair.scalp(m, spec)
    CA, CB, KS = np.asarray(sc_a.C, float), np.asarray(sc_b.C, float), float(np.median(sc_b.R) / np.median(sc_a.R))
    print(f"like {like}: head x{KS:.3f}, centre moved {np.round((CB - CA) * 1000, 1)} mm", flush=True)


def moved(f):
    if not like:
        return f
    f = dict(f)
    for key in ("eye", "center"):
        f[key] = (CB + KS * (np.asarray(f[key], float) - CA)).tolist()
    return f


W, H = 1152, 1536
BOX = [-(H - W) / 2, 0, W + (H - W) / 2, H]
J = skin_look._J(store.load(like) if like else spec)
nt = J["lm_nose_tip"]
c = np.array([0.0, nt[1] + 0.11, nt[2] - 0.03])
DIRS = {"backl": [0.62, 0.78, 0.06], "backq": [-0.6, 0.8, 0.08], "right": [-1, 0.0, 0.0], "back": [0.0, 1.0, 0.1],
        "left": [1.0, 0.0, 0.0], "front": [0.0, -1.0, 0.05], "crown": [0.25, -0.45, 1.0], "top": [0.0, -0.2, 1.0]}
_sm = kw.get("stage", m)
sn = stage.ensure(_sm) if (store.HOME / _sm / "spec.json").exists() else "_g3_" + _sm
st = json.loads((store._dir(sn) / "spec.json").read_text())
st["hair"] = spec["hair"]
GLB = kw.get("glb")
CARD = json.loads(open(kw["params"][1:]).read() if kw.get("params", "").startswith("@") else kw.get("params", "{}"))

frames, rigs = [], []
for i, v in enumerate(views):
    if v[0] == "v" and v[1:].isdigit():
        f = stage.fitted_frame(refs["cameras"][int(v[1:])], BOX, v)
        lt = stage.photo_light(like or m, int(v[1:]))
    else:
        d = np.asarray(DIRS[v], float) / np.linalg.norm(DIRS[v])
        f = render.camera_frame({"eye": (c + d * 1.6).tolist(), "target": c.tolist(), "fov": 17.0, "name": v}, i)
        e = np.asarray(f["eye"], float) - c
        a = np.arctan2(e[0], -e[1])
        R = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
        lt = copy.deepcopy(stage.FRONT_LIGHT)
        for l in lt["lights"]:
            l["dir"] = (R @ np.asarray(l["dir"], float)).tolist()
            l.pop("window", None)
    frames.append(moved(f))
    rigs.append(lt)
# (one rig shape for every view: the first view's, with a window on its key; views re-aim / re-weight its suns)
base = copy.deepcopy(next((r for r in rigs if any(l.get("window") for l in r["lights"])), rigs[0]))

with resources.heavy(f"haircards shots {m}{TAG}", gb=8), tempfile.TemporaryDirectory() as tmp:
    vf, idf = [], []
    for v, f, lt in zip(views, frames, rigs):
        vf.append({**f, "name": v, "out": str(Path(tmp) / f"{v}.png"), "lights": lt["lights"]})
        idf.append({**f, "name": v + "_id", "out": str(Path(tmp) / f"{v}_id.png")})
    job = {"blend": str(scene.blend_path(sn)), "views": vf, "size": N, "samples": int(kw.get("samples", 8)), "hide": [],
           "flat": False, "transparent": True, "lighting": {**base, "target": frames[0]["center"]}, "eevee": stage.STAGE_EEVEE,
           "mode": "hair_look", "clay_views": [], "id_views": idf, "look_engine": "eevee"}
    if GLB:
        job.update(mode="hair_glb_look", glb=GLB, alpha=kw.get("alpha", "game"), card_params=CARD,
                   aux=str(Path(GLB).parent / "hair_aux.png"), cutoff=float(kw.get("cutoff", 0.33)))
        if kw.get("only"):
            job["only_tris"] = json.loads(kw["only"])
    else:
        job["hair"] = hair.job(sn, st)
    t0 = time.time()
    out = scene._blender(job, 3600)
    fr = [float(ln.split()[1]) for ln in str(out).splitlines() if ln.startswith("@@frame")]
    print(f"{m}{TAG}: {len(views)} views in {time.time() - t0:.0f} s wall; frames {fr} s", flush=True)
    for v, f, lt in zip(views, vf, rigs):
        im = Image.open(f["out"])
        if im.mode == "RGBA":
            bg = Image.new("RGBA", im.size, tuple(int(255 * min(1.0, x)) for x in lt.get("backdrop", [0.86, 0.86, 0.86])) + (255,))
            im = Image.alpha_composite(bg, im)
        im.convert("RGB").save(f"{OUT}/s_{m}{TAG}_{v}.png")
    for v, f in zip(views, idf):
        Image.open(f["out"]).convert("RGB").save(f"{OUT}/id_{m}{TAG}_{v}.png")
print("done", m, flush=True)
