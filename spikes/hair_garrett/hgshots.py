"""hgshots.py <model> [size=1536] [views=v0,v1,v2,y125,y180] [tag=] [look=@file] [S=<json>] [engine=eevee]
The model's CURRENT hair (its spec, in memory) on its dressed head stage (spikes/garrett3/stage.py), EEVEE:
  v<i>     through the i-th reference's fitted camera under the picture's fitted light (the whole picture, squared)
  y<deg>   the FRONT fitted camera turned <deg> round the head's vertical axis (+ = toward his left: y125 = the back
           three-quarter from his left, y180 = the back), its light turned with it: framed like the front, so the
           unfitted back pictures (same generator framing) sit beside it
Tiles $TOUT/s_<model><tag>_<view>.png (size x size; the picture's 1152 x 1536 sits in the middle 3/4 of the width).
Skin: this branch has no skin layer stack (projskin, unmerged): skin.projection / skin.stack are dropped from the
STAGE in memory (the procedural skin stands in); the model's spec is never changed."""
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
N = int(kw.get("size", 1536))
views = kw.get("views", "v0,v1,v2,y125,y180").split(",")
OUT = os.environ["TOUT"]
TAG = kw.get("tag", "")
eng = kw.get("engine", "eevee")

_ss = skin_look.stage_spec


def stage_spec(spec, region, voxel=None):
    s = _ss(spec, region, voxel) if voxel is not None else _ss(spec, region)
    for k in ("projection", "stack"):
        (s.get("skin") or {}).pop(k, None)
    return s


skin_look.stage_spec = stage_spec
_load = store.load


def load(name, *a, **k):  # (stage.ensure loads the model: hand it the skin-stripped spec)
    sp = _load(name, *a, **k)
    if name == m:
        sp = copy.deepcopy(sp)
        for kk in ("projection", "stack"):
            (sp.get("skin") or {}).pop(kk, None)
    return sp


store.load = load
spec = store.load(m)
if kw.get("look"):
    lk_ = kw["look"]
    spec["hair"]["look"] = {**(spec["hair"].get("look") or {}), **json.loads(open(lk_[1:]).read() if lk_.startswith("@") else lk_)}
if kw.get("S"):
    spec["hair"]["strands"] = {**(spec["hair"].get("strands") or {}), **json.loads(kw["S"])}
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
W, H = refs["cameras"][0]["size"]
BOX = [-(H - W) / 2, 0, W + (H - W) / 2, H]


def shoot(sn, st, f, lt):
    with tempfile.TemporaryDirectory() as tmp:
        fr = {**f, "out": str(Path(tmp) / "a.png")}
        job = {"blend": str(scene.blend_path(sn)), "views": [fr], "size": N, "samples": 24, "hide": [], "flat": False,
               "transparent": True, "lighting": {**lt, "target": fr["center"]}, "eevee": stage.STAGE_EEVEE,
               "mode": "hair_look", "hair": hair.job(sn, st), "clay_views": [], "id_views": [], "look_engine": eng}
        scene._blender(job, 3600)
        im = Image.open(fr["out"])
        if im.mode == "RGBA":
            bg = Image.new("RGBA", im.size, tuple(int(255 * min(1.0, x)) for x in lt.get("backdrop", [0.86, 0.86, 0.86])) + (255,))
            im = Image.alpha_composite(bg, im)
        return im.convert("RGB")


def turned(f, lt, deg, C):
    a = np.radians(deg)
    R = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    g = dict(f)
    for k in ("eye", "center"):
        g[k] = (C + R @ (np.asarray(f[k], float) - C)).tolist()
    for k in ("dir", "up"):
        g[k] = (R @ np.asarray(f[k], float)).tolist()
    l2 = copy.deepcopy(lt)
    for l in l2["lights"]:
        l["dir"] = (R @ np.asarray(l["dir"], float)).tolist()
        l.pop("window", None)
    return g, l2


with resources.heavy(f"hair-garrett shots {m}", gb=8):
    sn = stage.ensure(m, with_hair=False)
    st = json.loads((store._dir(sn) / "spec.json").read_text())
    st["hair"] = spec["hair"]
    C = hair.scalp(m, spec).C
    for v in views:
        if v[0] == "v":
            i = int(v[1:])
            f = stage.fitted_frame(refs["cameras"][i], BOX, v)
            lt = stage.photo_light(m, i)
        else:
            f0 = stage.fitted_frame(refs["cameras"][0], BOX, v)
            f, lt = turned(f0, stage.photo_light(m, 0), float(v[1:]), C)
        shoot(sn, st, f, lt).save(f"{OUT}/s_{m}{TAG}_{v}.png")
        print("done", v, flush=True)
print("done", m)
