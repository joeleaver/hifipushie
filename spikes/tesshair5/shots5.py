"""shots5.py <model> [engine=eevee|cycles] [size=768] [views=v0,v1,v2,backl,backq,right,back] [stage=th_T66]
[look=@file.json]: the model's CURRENT hair on the shared dressed stage: through the three references' fitted cameras
under the fitted photo light (v0 front, v1 three-quarter, v2 profile; the whole picture, squared) and the views the
pictures do not show (the front light turned round the head with the camera). Tiles $TOUT/s_<model>_<view>[_cyc].png.

Unlike spikes/tesshair/shots.py: (1) the hair is the model's spec NOW, in memory (a model's own stage .blend keeps the
hair it was built with); (2) Cycles renders strands as hair.look_hair does (hair_bounces 10, denoised, adaptive 0.01:
stage.shoot leaves Cycles at 2 transmission bounces, which renders dark hair near black: every "Cycles" column of the
tesshair sheets before th_30)."""
import copy
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

import stage
from hifipushie import hair, render, resources, scene, skin_look, store

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
eng, N = kw.get("engine", "eevee"), int(kw.get("size", 768))
views = kw.get("views", "v0,v1,v2,backl,backq,right").split(",")
OUT = os.environ["TOUT"]
spec = store.load(m)
if kw.get("look"):
    lk_ = kw["look"]
    spec["hair"]["look"] = {**(spec["hair"].get("look") or {}), **json.loads(open(lk_[1:]).read() if lk_.startswith("@") else lk_)}
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
W, H = 1152, 1536
BOX = [-(H - W) / 2, 0, W + (H - W) / 2, H]
suf = "_cyc" if eng == "cycles" else ""
J = skin_look._J(spec)
nt = J["lm_nose_tip"]
c = np.array([0.0, nt[1] + 0.11, nt[2] - 0.03])
DIRS = {"backl": [0.62, 0.78, 0.06], "backq": [-0.6, 0.8, 0.08], "right": [-1, 0.0, 0.0], "back": [0.0, 1.0, 0.1],
        "left": [1.0, 0.0, 0.0], "front": [0.0, -1.0, 0.05]}
sn = stage.ensure(kw.get("stage", os.environ.get("STAGE_MODEL", "th_T66")))
st = json.loads((store._dir(sn) / "spec.json").read_text())
st["hair"] = spec["hair"]


def shoot(f, lt):
    with tempfile.TemporaryDirectory() as tmp:
        fr = {**f, "out": str(Path(tmp) / "a.png")}
        job = {"blend": str(scene.blend_path(sn)), "views": [fr], "size": N, "samples": 24, "hide": [], "flat": False,
               "transparent": True, "lighting": {**lt, "target": fr["center"]}, "eevee": stage.STAGE_EEVEE,
               "mode": "hair_look", "hair": hair.job(sn, st), "clay_views": [], "id_views": [], "look_engine": eng}
        if eng == "cycles":
            job.update(hair_bounces=10, denoise=True, adaptive_threshold=0.01, samples=int(kw.get("samples", 96)))
        scene._blender(job, 3600)
        im = Image.open(fr["out"])
        if im.mode == "RGBA":
            bg = Image.new("RGBA", im.size, tuple(int(255 * min(1.0, x)) for x in lt.get("backdrop", [0.86, 0.86, 0.86])) + (255,))
            im = Image.alpha_composite(bg, im)
        return im.convert("RGB")


with resources.heavy(f"tesshair5 shots {m}", gb=8):
    for i, v in enumerate(views):
        if v[0] == "v" and v[1:].isdigit():
            f = stage.fitted_frame(refs["cameras"][int(v[1:])], BOX, v)
            lt = stage.photo_light(m, int(v[1:]))
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
        shoot(f, lt).save(f"{OUT}/s_{m}_{v}{suf}.png")
        print("done", v, flush=True)
print("done", m)
