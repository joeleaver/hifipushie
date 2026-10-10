import json, sys, numpy as np
from PIL import Image
import stage
from hifipushie import aperture, scene, store
name, st = sys.argv[1], sys.argv[2]
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
v, cam = refs["views"][0], refs["cameras"][0]
U = np.array(list(v["points"].values()), float); lo, hi = U.min(0), U.max(0); s = 0.95 * (hi - lo)[0]
c = np.array([0.5 * (lo[0] + hi[0]), lo[1] + 0.55 * (hi[1] - lo[1])])
fr = stage.fitted_frame(cam, [c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2], "id")
m = aperture.mask(str(scene.blend_path(st)), fr, 1024)
Image.fromarray((m * 255).astype(np.uint8)).save(sys.argv[3])
