"""dbg_eye.py <model> <out png> <variant> ...: the front close-up of the eyes (the front reference camera, the eye
band) for variants of the model, one change each, as a labelled strip. Variants:
  base | clay (no skin, no paint) | noeyes (the eyes part hidden) | nosliders (base.head.sliders {}) |
  nopose (base.head.pose {}) | skin:<json patch> (a skin patch, e.g. skin:{"variation":0})"""
import copy, json, os, sys, tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import stage
from hifipushie import scene, store

name, out, variants = sys.argv[1], sys.argv[2], sys.argv[3:]
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
v0, cam = refs["views"][0], refs["cameras"][0]
P = {k: np.array(v, float) for k, v in v0["points"].items()}
c = 0.5 * (P["lm36"] + P["lm45"])
w = 1.25 * np.linalg.norm(P["lm45"] - P["lm36"])
box = [c[0] - w / 2, c[1] - w / 4, c[0] + w / 2, c[1] + w / 4]
sq = [box[0], c[1] - w / 2, box[2], c[1] + w / 2]
frame = stage.fitted_frame(cam, sq, "eyes")
LIGHT = {**stage.FRONT_LIGHT, "exposure": -0.1}
tiles = []
for i, var in enumerate(variants):
    sp = copy.deepcopy(store.load(name))
    hide = []
    if var == "clay":
        sp.pop("skin", None)
        sp["paint"] = {}
    elif var == "noeyes":
        hide = ["eyes"]
    elif var == "nosliders":
        sp["base"]["head"]["sliders"] = {}
    elif var == "nopose":
        sp["base"]["head"]["pose"] = {}
    elif var.startswith("skin:"):
        p = json.loads(var[5:])
        sk = sp.setdefault("skin", {})
        for k, v in p.items():
            if isinstance(v, dict) and isinstance(sk.get(k), dict):
                sk[k].update(v)
            else:
                sk[k] = v
    elif var.startswith("head:"):
        sp["base"]["head"].update(json.loads(var[5:]))
    dn = f"_tsdbg{i}"
    store.save(dn, sp, f"tess eye-band debug: {var}")
    sn = stage.ensure(dn, with_hair=False)
    with tempfile.TemporaryDirectory() as tmp:
        f = {**frame, "out": str(Path(tmp) / "eyes.png")}
        job = {"blend": str(scene.blend_path(sn)), "views": [f], "size": 700, "samples": 24, "hide": hide, "flat": False,
               "transparent": True, "mode": "render", "lighting": {**LIGHT, "target": f["center"]}}
        scene._blender(job, 2400)
        im = Image.open(f["out"]).convert("RGBA")
        bg = Image.new("RGBA", im.size, (220, 220, 220, 255))
        im = Image.alpha_composite(bg, im).convert("RGB").crop((0, 175, 700, 525))
    ImageDraw.Draw(im).rectangle([0, 0, 8 * len(var[:80]) + 10, 18], fill=(20, 20, 20))
    ImageDraw.Draw(im).text((5, 3), var[:80], fill=(255, 255, 255))
    tiles.append(im)
    print("done", var)
S = Image.new("RGB", (700, 350 * len(tiles)))
for i, t in enumerate(tiles):
    S.paste(t, (0, 350 * i))
S.save(out)
print("saved", out)
