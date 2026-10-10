"""mouthchk.py <model> <tag> [hair 0|1]: the mouth through the front reference camera, close (stage.shoot, eevee),
saved $F/out/mouth_<tag>.png."""
import json
import os
import sys

import numpy as np

import stage
from hifipushie import humanfit, store

F = "/mnt/data/hifipushie/facesliders"
name, tag = sys.argv[1], sys.argv[2]
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
cam = refs["cameras"][0]
st = humanfit.state(store.load(name)["base"])
uv = humanfit.project(cam, st["L"][48:68])
c = uv.mean(0)
s = 2.2 * np.ptp(uv[:, 0])
fr = stage.fitted_frame(cam, [c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2], "mouth")
im = stage.shoot(name, [fr], json.load(open(os.environ.get("LIGHT", "/mnt/data/hifipushie/likeloop/light_m.json"))),
                 size=600, hair_on=len(sys.argv) > 3 and sys.argv[3] == "1")["mouth"]
im.save(f"{F}/out/mouth_{tag}.png")
print("wrote", f"{F}/out/mouth_{tag}.png")
