"""shots.py <model> <out dir> [features=eyes,mouth,face] [views=0,1,2] [tile=640] [extra=1] [refs=1] [light=photo|front]:
DRESSED EEVEE tiles of a model through its references' fitted cameras, one file per feature and view
(<feature>_v<i>.png; the reference's own crop as <feature>_v<i>_ref.png), plus (extra=1) views no reference has: the
left eye from the side (eye_side: the cornea's profile against the lids), both eyes from 3/4 below (eyes_34), the
mouth from the front and 3/4 (mouth_front, mouth_34) and the whole face (face_front), from the model's own landmarks.
One heavy job (resources.heavy); the stage is the garrett3 stage (head crop, own skin, no hair)."""
import os
import sys

import numpy as np
from PIL import Image

sys.path[:0] = ["/home/joe/dev/hifipushie/spikes/garrett3", "/home/joe/dev/hifipushie/spikes/tour"]
import stage  # noqa: E402
import tour  # noqa: E402,F401

from hifipushie import blockin as bi, humanfit, render, resources, store  # noqa: E402

bi.FEATURES.setdefault("face", {"lm": list(range(0, 68)), "pairs": [], "lines": [], "stages": (), "squint_mm": 6.0, "pad": 1.25})


def own_frames(spec):
    """Frames from the model's own landmarks (world): no reference needed."""
    st = humanfit.state(spec["base"])
    L, ht = st["L"], st["head"]
    eyes = sorted([np.asarray(c, float) for c in ht["eyes"]], key=lambda c: -c[0])  # the subject's left (+x) first
    r = float(ht["eye_r"])
    fwd = np.asarray(ht["forward"], float)
    mouth = 0.5 * (L[62] + L[66])
    mid = 0.5 * (eyes[0] + eyes[1])
    face = 0.5 * (L[27] + L[8])
    out = []

    def cam(name, target, d, dist, fov):
        d = np.asarray(d, float) / np.linalg.norm(d)
        out.append(render.camera_frame({"eye": (np.asarray(target) + d * dist).tolist(), "target": list(map(float, target)),
                                        "fov": fov, "name": name}, len(out)))
    cam("eye_side", eyes[0] + fwd * 0.6 * r, [1.0, -0.12, 0.0], 0.6, 5.2)
    cam("eyes_34", mid + fwd * r, [0.62, -0.75, -0.12], 0.9, 6.5)
    cam("eyes_front", mid + fwd * r, [0.0, -1.0, 0.0], 0.9, 6.5)
    cam("mouth_front", mouth, [0.0, -1.0, -0.05], 0.9, 6.0)
    cam("mouth_34", mouth, [0.62, -0.75, -0.1], 0.9, 6.0)
    cam("face_front", face, [0.0, -1.0, 0.0], 1.2, 12.0)
    cam("face_34", face, [0.62, -0.75, 0.0], 1.2, 12.0)
    return out


def main():
    m, out = sys.argv[1:3]
    kw = dict(a.split("=", 1) for a in sys.argv[3:])
    os.makedirs(out, exist_ok=True)
    T = int(kw.get("tile", 640))
    feats = [f for f in kw.get("features", "eyes,mouth,face").split(",") if f]
    spec = store.load(m)
    rj = bi._refs(m)
    VI = [int(x) for x in kw["views"].split(",")] if kw.get("views") else list(range(len(rj["views"])))
    frames, boxes = [], {}
    if feats:
        meshes = bi._per_view(spec["base"], rj, VI, lambda b: bi.presented_mesh(b, rj=rj))
        for vi in VI:
            cam = rj["cameras"][vi]
            L2 = humanfit.project(cam, meshes[vi]["state"]["L"])
            for f in feats:
                b = [float(x) for x in bi._feature_box(f, L2)]
                boxes[f"{f}_v{vi}"] = (vi, b)
                frames.append(stage.fitted_frame(cam, b, f"{f}_v{vi}"))
    if kw.get("extra", "1") == "1":
        frames += own_frames(spec)
    light = stage.photo_light(m, bi._front(rj)) if kw.get("light", "photo") == "photo" else stage.FRONT_LIGHT
    with resources.heavy(f"gnmnative shots {m}", gb=6):
        own = stage.shoot(m, frames, light, size=T, hair_on=False)
    for k, im in own.items():
        im.convert("RGB").resize((T, T), Image.LANCZOS).save(f"{out}/{k}.png")
        print(f"{out}/{k}.png")
    if kw.get("refs", "1") == "1":
        for k, (vi, b) in boxes.items():
            img = Image.open(rj["views"][vi]["image"]).convert("RGB")
            img.crop(tuple(int(round(x)) for x in b)).resize((T, T), Image.LANCZOS).save(f"{out}/{k}_ref.png")


main()
