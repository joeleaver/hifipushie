"""dressed.py <accepted model> <model>...: faces6, WHOLE-FACE dressed renders (featsheet's EEVEE look, no hair, the
photo's fitted light) through the accepted model's front and 3/4 cameras, then agesex (genderage) on each and ArcFace
to the photo / the accepted model's render. Clay is out of the age net's domain (every fit read 22-27 on clay,
tl10's old-man clay included); the dressed look is closer to the photos it was trained on. Saves
$F/out/dressed_<model>_v<k>.png, prints one json row per model."""
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import agesex
import featsheet
import stage
from hifipushie import faceid, humanfit, store
from shot import light

F = Path(os.environ.get("F", "/mnt/data/hifipushie/faces6"))
VIEWS = [int(v) for v in os.environ.get("GVIEWS", "0,1").split(",")]


def boxes(acc, refs):
    st = humanfit.state(store.load(acc)["base"])
    out = []
    for vi in VIEWS:
        P = humanfit.project(refs["cameras"][vi], st["L"])
        c = 0.5 * (P.min(0) + P.max(0))
        side = 1.6 * float(np.max(P.max(0) - P.min(0)))
        out.append((vi, [c[0] - side / 2, c[1] - side * 0.55, c[0] + side / 2, c[1] + side * 0.45]))
    return out


def shoot(m, acc_refs, bx):
    sp = store.load(m)
    d = store.HOME / featsheet.SCR
    d.mkdir(exist_ok=True)
    (d / "spec.json").write_text(json.dumps(sp, indent=1))
    (d / "human_refs.json").write_text(json.dumps(acc_refs))
    frames = [stage.fitted_frame(acc_refs["cameras"][vi], box, f"v{vi}") for vi, box in bx]
    ims = stage.shoot(featsheet.SCR, frames, light(), size=featsheet.SIZE, hair_on=False)
    return {vi: ims[f"v{vi}"].convert("RGB") for vi, _ in bx}


if __name__ == "__main__":
    acc, models = sys.argv[1], sys.argv[2:]
    refs = json.loads((store.HOME / acc / "human_refs.json").read_text())
    bx = boxes(acc, refs)
    photos = {vi: Image.open(refs["views"][vi]["image"]).convert("RGB").crop(tuple(int(round(b)) for b in box))
              for vi, box in bx}
    for vi, im in photos.items():
        im.save(F / "out" / f"dressed_photo_v{vi}.png")
    pr = agesex.read([F / "out" / f"dressed_photo_v{vi}.png" for vi in photos])
    print("photo", json.dumps({vi: None if r is None else {"p_female": round(r["p_female"], 3), "age": round(r["age"], 1)}
                               for vi, r in zip(photos, pr)}))
    R = {}
    for m in [acc] + [m for m in models if m != acc]:
        R[m] = shoot(m, refs, bx)
        paths = []
        for vi, im in R[m].items():
            p = F / "out" / f"dressed_{m}_v{vi}.png"
            im.save(p)
            paths.append(p)
        reads = agesex.read(paths)
        row = {"model": m}
        for (vi, im), r in zip(R[m].items(), reads):
            row[f"v{vi}_p_female"] = None if r is None else round(r["p_female"], 3)
            row[f"v{vi}_age"] = None if r is None else round(r["age"], 1)
            row[f"v{vi}_id_photo"] = faceid.similarity(im, photos[vi])["arcface"]
            row[f"v{vi}_id_acc"] = faceid.similarity(im, R[acc][vi])["arcface"]
        print(json.dumps(row), flush=True)
