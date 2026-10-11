"""dress.py <tag>=<source> ...: dressed (full-res EEVEE, Tess's photo-fitted light, hair off) + raking clay eye crops.
source = <kind_seed>:<i> (a sampled identity on gd_T12's body, expression / lid pose cleared) | model:<name> (a model as
is) | npy:<path>[@<model>] (an identity on <model> (default gd_T12), expression kept from FROM_EXPR=<model> if set).
Writes out/d_<tag>_dressed.png, out/d_<tag>_clay.png and reads lidfold on the dressed crop (MediaPipe points)."""
import copy
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image

import stage
from hifipushie import blockin as bi, resources, store

G = "/mnt/data/hifipushie/gnmcrease/out"
RAKE = {"lights": [{"dir": [0.86, -0.3, 0.42], "energy": 4.0, "color": [1, 1, 1], "angle": 6},
                   {"dir": [0.0, -1.0, 0.1], "energy": 0.25, "color": [1, 1, 1], "angle": 40, "shadow": False, "specular": 0.0}],
        "world": {"color": [0.8, 0.8, 0.8], "strength": 0.15}, "view": "Khronos PBR Neutral", "exposure": 0.0}
CLAYTOP = {"lights": [{"dir": [0.08, -0.74, 0.67], "energy": 3.0, "color": [1, 1, 1], "angle": 20}],
           "world": {"color": [0.8, 0.8, 0.8], "strength": 0.3}, "view": "Khronos PBR Neutral", "exposure": 0.0}


def make_model(tag, src):
    if src.startswith("model:"):
        return src[6:]
    name = f"gk_{tag}"
    if src.startswith("npy:"):
        p, _, m = src[4:].partition("@")
        m = m or "gd_T12"
        c = np.load(p)
        sp = copy.deepcopy(store.load(m))
        keep_expr = os.environ.get("KEEP_EXPR") == "1"
    else:
        m = "gd_T12"
        k, i = src.split(":")
        c = np.load(f"{G}/s_{k}.npz")["C"][int(i)]
        sp = copy.deepcopy(store.load(m))
        keep_expr = False
    bi.set_identity(sp, c)
    if not keep_expr:
        sp["base"]["head"].pop("expression", None)
    pose = dict(sp["base"]["head"].get("pose") or {})
    pose.pop("lid_upper", None); pose.pop("lid_lower", None)
    sp["base"]["head"]["pose"] = pose
    if not pose:
        sp["base"]["head"].pop("pose")
    sp.pop("hair", None)
    d = store._dir(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(sp))
    shutil.copy(store._dir(m) / "human_refs.json", d / "human_refs.json")
    return name


def eye_frame(name, model_for_cam):
    rj = json.loads((store.HOME / model_for_cam / "human_refs.json").read_text())
    b = rj["blockin"]["boxes"][0]
    w = b[2] - b[0]
    side = 0.76 * w
    cx, cy = 0.5 * (b[0] + b[2]), b[1] + 0.39 * (b[3] - b[1])
    box = [cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2]
    from hifipushie import render, skin_look
    J = skin_look._J(store.load(name))
    t = 0.5 * (J["eye.L"] + J["eye.R"]) + [0, -0.012, 0.003]
    fr = render.camera_frame({"eye": (t + [0, -0.6, 0]).tolist(), "target": t.tolist(), "fov": 8.0, "name": "front"}, 0)
    fr2 = render.camera_frame({"eye": (t + [0, -0.6, 0]).tolist(), "target": (t + [0, 0, -0.03]).tolist(), "fov": 22.0, "name": "face"}, 1)
    return [fr, fr2], box, rj


if __name__ == "__main__":
    light = stage.photo_light(os.environ.get("LIGHT", "gd_T12"))
    for a in sys.argv[1:]:
        tag, src = a.split("=", 1)
        name = make_model(tag, src)
        camm = name if (store.HOME / name / "human_refs.json").exists() else "gd_T12"
        fr, box, rj = eye_frame(name, camm)
        with resources.heavy(f"gnmcrease dress {tag}", gb=6):
            sh = stage.shoot(name, fr, light, size=1600, hair_on=False)
            sh["front"].save(f"{G}/d_{tag}_dressed.png")
            sh["face"].save(f"{G}/d_{tag}_face.png")
            if os.environ.get("NOCLAY") != "1":
                cl = stage.shoot(name, fr[:1], CLAYTOP, size=1600, hair_on=False, layer="__clay__")["front"]
                cl.save(f"{G}/d_{tag}_clay.png")
        if not os.path.exists(f"{G}/photo_eyes_{camm[:3]}.png"):
            ph = Image.open(rj["views"][0]["image"]).convert("RGB").crop(tuple(int(round(v)) for v in box))
            ph.save(f"{G}/photo_eyes_{camm[:3]}.png")
        print("done", tag, name, flush=True)
