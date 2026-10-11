"""dshots.py <model>...: DRESSED pictures (EEVEE stage, the photo's fitted light, hair off) of known heads through the
THREE fitted cameras of a reference set (env REFS, default gd_T12: front, 3/4, profile), one square crop of each
picture (BOX), at the picture's own pixels -> $G/out/d_<model>_<kind>.png + d_box.json. For the ruler's validation on
dressed renders (dval.py)."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "garrett3"))
import stage  # noqa: E402
from hifipushie import blockin as bi, face_ruler as fr, resources  # noqa: E402

G = os.environ["G"] + "/out"
REFS = os.environ.get("REFS", "gd_T12")
BOX = [0.0, 150.0, 1152.0, 1302.0]

if __name__ == "__main__":
    rj = bi._refs(REFS)
    frames = [stage.fitted_frame(cam, BOX, fr.kind_of(v.get("yaw", 0))) for v, cam in zip(rj["views"], rj["cameras"])]
    light = stage.photo_light(REFS)
    json.dump({"box": BOX, "refs": REFS}, open(f"{G}/d_box.json", "w"))
    for name in sys.argv[1:]:
        t = time.time()
        with resources.heavy(f"faceruler dressed shots {name}", gb=6):
            ims = stage.shoot(name, frames, light, size=1152, hair_on=False)
        for k, im in ims.items():
            im.save(f"{G}/d_{name}_{k}.png")
        print("done", name, list(ims), f"{time.time() - t:.0f} s", flush=True)
