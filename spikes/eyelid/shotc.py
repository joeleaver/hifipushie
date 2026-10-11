"""shotc.py <tag>=<model> ...: the stage through the FRONT PICTURE'S FITTED CAMERA (gnmbrow/shot.py's fixed crop, so
every shot and the photo share pixels): out/s_<tag>.png dressed (skipped if DRESSED=0 or it exists), out/k_<tag>.png
CLAY under a hard light raking down the lid from above (the form: a fold casts a shadow, a soft valley only shades),
out/r_<tag>.png clay under a hard side rake. Env REFS (gd_T12), K (3), FORCE=1 re-renders."""
import json
import os
import sys

import numpy as np
from PIL import Image

import shot
import stage
from hifipushie import blockin as bi, resources

G = os.environ["G"] + "/out"
K = int(os.environ.get("K", "3"))
REFS = os.environ.get("REFS", "gd_T12")
TOP = {"lights": [{"dir": [0.1, -0.77, 0.63], "energy": 5.0, "color": [1, 1, 1], "angle": 3},
                  {"dir": [0.0, -1.0, 0.1], "energy": 0.3, "color": [1, 1, 1], "angle": 40, "shadow": False, "specular": 0.0}],
       "world": {"color": [0.8, 0.8, 0.8], "strength": 0.25}, "view": "Khronos PBR Neutral", "exposure": 0.0}
SIDE = {"lights": [{"dir": [0.8, -0.55, 0.25], "energy": 5.0, "color": [1, 1, 1], "angle": 3},
                   {"dir": [0.0, -1.0, 0.1], "energy": 0.3, "color": [1, 1, 1], "angle": 40, "shadow": False, "specular": 0.0}],
        "world": {"color": [0.8, 0.8, 0.8], "strength": 0.25}, "view": "Khronos PBR Neutral", "exposure": 0.0}

if __name__ == "__main__":
    rj = bi._refs(REFS)
    img, box, P = shot.box_of(rj)
    json.dump({"box": box, "K": K, "P": np.asarray(P).tolist()}, open(f"{G}/box.json", "w"))
    ib = [int(round(v)) for v in box]
    if not os.path.exists(f"{G}/s_photo.png"):
        img.crop(tuple(ib)).resize((shot.SIDE * K, shot.SIDE * K), Image.LANCZOS).save(f"{G}/s_photo.png")
    cam = rj["cameras"][bi._front(rj)]
    fr = stage.fitted_frame(cam, [float(v) for v in ib], "front")
    light = stage.photo_light(REFS)
    force = os.environ.get("FORCE") == "1"
    # (first try: the top light 64 deg up: the brow's shadow covered the whole lid. 39 deg up now)
    for a in sys.argv[1:]:
        tag, model = a.split("=", 1)
        with resources.heavy(f"eyelid shot {tag}", gb=6):
            if os.environ.get("DRESSED", "1") == "1" and (force or not os.path.exists(f"{G}/s_{tag}.png")):
                stage.shoot(model, [fr], light, size=shot.SIDE * K, hair_on=False)["front"].save(f"{G}/s_{tag}.png")
            for pre, lt in (("k", TOP), ("r", SIDE)):
                if force or not os.path.exists(f"{G}/{pre}_{tag}.png"):
                    stage.shoot(model, [fr], lt, size=shot.SIDE * K, hair_on=False, layer="__clay__")["front"].save(f"{G}/{pre}_{tag}.png")
        print("done", tag, model, flush=True)
