"""hgshots.py <model> [size=1536] [views=v0,v1,v2,y125,y180] [tag=] [look=@file] [S=<json>] [engine=eevee] [one=1]
(one=1: every view in ONE Blender, each under its own light; one=0: a Blender per view, the old way)
The model's CURRENT hair (its spec, in memory) on its dressed head stage (spikes/garrett3/stage.py), EEVEE:
  v<i>     through the i-th reference's fitted camera under the picture's fitted light (the whole picture, squared)
  y<deg>   the FRONT fitted camera turned <deg> round the head's vertical axis (+ = toward his left: y125 = the back
           three-quarter from his left, y180 = the back), its light turned with it: framed like the front, so the
           unfitted back pictures (same generator framing) sit beside it
Tiles $TOUT/s_<model><tag>_<view>.png (size x size; the picture's 1152 x 1536 sits in the middle 3/4 of the width).
Skin: this branch has no skin layer stack (projskin, unmerged): skin keys this branch doesn't know (projection, stack,
eyes.iris_inner ...) are dropped from the STAGE in memory (the procedural skin stands in); the model's spec is never changed."""
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
N0 = int(kw.get("size", 1536))
# ss=<k>: render k x larger and average down. EEVEE draws every strand at least a pixel wide: at the pictures' own
# scale (~0.3 mm a pixel) a 0.05 mm hair became a 0.3 mm wire (hair-garrett r4: strand_sd 9.3 vs the photo's 6.8)
SS = int(kw.get("ss", 1))
N = N0 * SS
# samples a frame (default 24): check renders use fewer (the iGPU wedges on long hair frames: a heavy EEVEE frame of
# ~6.6 M strand points ran past the driver timeout, 2026-10-14); wall time is printed per frame (> ~5 s is a risk)
SAMPLES = int(kw.get("samples", 24))
views = kw.get("views", "v0,v1,v2,y125,y180").split(",")
OUT = os.environ["TOUT"]
TAG = kw.get("tag", "")
eng = kw.get("engine", "eevee")

_ss = skin_look.stage_spec


def _known_skin(sk):
    """Only the skin keys this branch knows (projskin's newer keys dropped: the procedural skin stands in)."""
    from hifipushie import skin as skin_mod, skin_features
    sk = {k: v for k, v in (sk or {}).items() if k in skin_mod.KEYS}
    if isinstance(sk.get("eyes"), dict):
        sk["eyes"] = {k: v for k, v in sk["eyes"].items() if k in skin_features.EYE_KEYS}
    return sk


def stage_spec(spec, region, voxel=None):
    s = _ss(spec, region, voxel) if voxel is not None else _ss(spec, region)
    if s.get("skin"):
        s["skin"] = _known_skin(s["skin"])
    return s


skin_look.stage_spec = stage_spec
_load = store.load


def load(name, *a, **k):  # (stage.ensure loads the model: hand it the skin-stripped spec)
    sp = _load(name, *a, **k)
    if name == m or name == kw.get("stage", os.environ.get("HG_STAGE")):
        sp = copy.deepcopy(sp)
        if sp.get("skin"):
            sp["skin"] = _known_skin(sp["skin"])
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


def shoot(sn, st, shots):
    """shots: [(frame, lighting)] -> [RGB image], every view in ONE Blender (one scene load, groom build and shader
    compile; each view's own photo-fitted light swapped in between frames, blender_scene._light_rig). one=0: a Blender
    per view (the old way: ~70 s a frame on NICO-TOP, all of it set-up)."""
    with tempfile.TemporaryDirectory() as tmp:
        fr = [{**f, "out": str(Path(tmp) / f"{i}.png"), "lighting": {**lt, "target": f["center"]}}
              for i, (f, lt) in enumerate(shots)]
        job = {"blend": str(scene.blend_path(sn)), "views": fr, "size": N, "samples": SAMPLES, "hide": [], "flat": False,
               "transparent": True, "lighting": fr[0]["lighting"], "eevee": stage.STAGE_EEVEE,
               "mode": "hair_look", "hair": hair.job(sn, st), "clay_views": [], "id_views": [], "look_engine": eng}
        out = scene._blender(job, 3600 + 900 * len(fr))
        for ln in out.splitlines():
            if ln.startswith(("@@phase", "@@frame")):
                print(ln, flush=True)
        ims = []
        for f, (_, lt) in zip(fr, shots):
            im = Image.open(f["out"])
            if im.mode == "RGBA":
                bg = Image.new("RGBA", im.size, tuple(int(255 * min(1.0, x)) for x in lt.get("backdrop", [0.86, 0.86, 0.86])) + (255,))
                im = Image.alpha_composite(bg, im)
            ims.append(im.convert("RGB"))
        return ims


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


def tipped(f, lt, deg, C):
    """The frame rotated about the head's left-right axis through C: the camera rises over the top (the lights keep)."""
    a = np.radians(deg)
    a = -a  # (positive deg: the camera rises)
    R = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
    g = dict(f)
    for k in ("eye", "center"):
        g[k] = (C + R @ (np.asarray(f[k], float) - C)).tolist()
    for k in ("dir", "up"):
        g[k] = (R @ np.asarray(f[k], float)).tolist()
    return g, copy.deepcopy(lt)


with resources.heavy(f"hair-garrett shots {m}", gb=8):
    # ONE stage for every groom on the same head (stage=<head model>, default the model's source head hg_g0 / the
    # model): a stage per groom model cost a sync each and its ~0.33 GB pushed other agents' stages (the regression's
    # _g3_th_T04) out of the shared _g3_ budget (store.prune_stages)
    _st = kw.get("stage", os.environ.get("HG_STAGE", m))
    sn = stage.ensure(_st, with_hair=False)
    st = json.loads((store._dir(sn) / "spec.json").read_text())
    st["hair"] = spec["hair"]
    C = hair.scalp(m, spec).C
    shots = []
    for v in views:
        if v[0] == "v":
            i = int(v[1:])
            f = stage.fitted_frame(refs["cameras"][i], BOX, v)
            lt = stage.photo_light(m, i)
        elif v[0] == "t":  # t<deg>: the front camera tipped <deg> over the top (60 = looking down on the parting)
            f0 = stage.fitted_frame(refs["cameras"][0], BOX, v)
            f, lt = tipped(f0, stage.photo_light(m, 0), float(v[1:]), C)
        else:
            f0 = stage.fitted_frame(refs["cameras"][0], BOX, v)
            f, lt = turned(f0, stage.photo_light(m, 0), float(v[1:]), C)
        shots.append((v, f, lt))
    groups = [shots] if kw.get("one", "1") == "1" else [[x] for x in shots]
    for g in groups:
        t0_ = time.time()
        ims = shoot(sn, st, [(f, lt) for _, f, lt in g])
        print(f"frames {','.join(v for v, _, _ in g)}: {time.time() - t0_:.1f} s (one Blender, incl. scene load)", flush=True)
        for (v, _, _), im in zip(g, ims):
            if SS > 1:  # supersampled: rendered SS x larger, averaged down (strands thinner than a pixel blend as in a photo)
                im = im.resize((N0, N0), Image.LANCZOS)
            im.save(f"{OUT}/s_{m}{TAG}_{v}.png")
            print("done", v, flush=True)
print("done", m)
