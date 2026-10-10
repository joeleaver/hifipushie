"""mouthid.py <model> ...: the mouth's INTERIOR seen through a sealed mouth, by part ID (aperture.mask: the part the
nearest surface belongs to): teeth / tongue pixels in a front close-up of the lips (+ the body part's pixels to scale).
A sealed mouth shows none."""
import json
import sys

import numpy as np

import stage
from hifipushie import aperture, humanfit, scene, store

for name in sys.argv[1:]:
    refs = json.loads((store.HOME / name / "human_refs.json").read_text())
    cam = refs["cameras"][0]
    st = humanfit.state(store.load(name)["base"])
    uv = humanfit.project(cam, st["L"][48:68])
    c = uv.mean(0)
    s = 2.2 * np.ptp(uv[:, 0])
    fr = stage.fitted_frame(cam, [c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2], "mouth")
    blend = str(scene.blend_path(stage.ensure(name, with_hair=False)))
    out = {}
    for part in ("teeth", "tongue"):
        try:
            out[part] = int(aperture.mask(blend, fr, 512, part, hide=("lashes", "hair")).sum())
        except Exception as e:  # noqa: BLE001
            out[part] = f"err {e}"
    print(name, "interior pixels (512 px close-up of the lips):", out)
