"""shot.py <tag>=<model> ...: the DRESSED stage (EEVEE, the photo's fitted light, hair off) through the FRONT PICTURE'S
FITTED CAMERA, cropped to one fixed square of the picture (both eyes and brows: BOX, from the photo's own iris centres),
at K x the picture's pixels. So a render and the photo crop are the same mm/px, the same landmark at the same pixel.
Writes out/s_<tag>.png and out/s_photo.png (the picture's crop, LANCZOS x K), out/box.json.
Env: REFS=<model whose human_refs / photo to use> (default gd_T12), K (3), PATCH='{"skin": {...}}' deep-merged into a
scratch copy gb_<tag> of the model first (brows / eyes / makeup variants; never the source model)."""
import copy
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image

import stage
from hifipushie import blockin as bi, resources, store

G = os.environ.get("G", "/mnt/data/hifipushie/gnmbrow") + "/out"
K = int(os.environ.get("K", "3"))
REFS = os.environ.get("REFS", "gd_T12")
SIDE = 560          # picture px (133 mm at the model)


def box_of(rj):
    v = rj["views"][bi._front(rj)]
    img = Image.open(v["image"]).convert("RGB")
    P = np.asarray(bi.detect_view(img, v), float)[:, :2]
    c = 0.5 * (P[468] + P[473]) + [0, -40.0]
    return img, [float(c[0] - SIDE / 2), float(c[1] - SIDE / 2), float(c[0] + SIDE / 2), float(c[1] + SIDE / 2)], P


def merge(a, b):
    for k, v in b.items():
        if v is None:
            a.pop(k, None)
        elif isinstance(v, dict) and isinstance(a.get(k), dict):
            merge(a[k], v)
        else:
            a[k] = v
    return a


def variant(tag, model, patch):
    name = f"gb_{tag}"
    sp = merge(copy.deepcopy(store.load(model)), patch)
    sp.pop("hair", None)
    d = store._dir(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(sp))
    shutil.copy(store._dir(REFS) / "human_refs.json", d / "human_refs.json")
    return name


if __name__ == "__main__":
    rj = bi._refs(REFS)
    img, box, P = box_of(rj)
    json.dump({"box": box, "K": K, "P": P.tolist()}, open(f"{G}/box.json", "w"))
    ib = [int(round(v)) for v in box]
    img.crop(tuple(ib)).resize((SIDE * K, SIDE * K), Image.LANCZOS).save(f"{G}/s_photo.png")
    cam = rj["cameras"][bi._front(rj)]
    fr = stage.fitted_frame(cam, [float(v) for v in ib], "front")
    light = stage.photo_light(REFS)
    patch = json.loads(os.environ["PATCH"]) if os.environ.get("PATCH") else None
    for a in sys.argv[1:]:
        tag, model = a.split("=", 1)
        name = variant(tag, model, patch) if patch is not None else model
        with resources.heavy(f"gnmbrow shot {tag}", gb=6):
            im = stage.shoot(name, [fr], light, size=SIDE * K, hair_on=False)["front"]
        im.save(f"{G}/s_{tag}.png")
        print("done", tag, name, flush=True)
