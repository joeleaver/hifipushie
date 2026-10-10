"""prof.py <model> [model ...]: the true-left PROFILE gate. Each model's bare head (no hair) is rendered through its
fitted profile camera (human_refs view 2); its front contour (the first non-background pixel from the face side, per
row) is compared with the photo's, rows from the brow to under the chin: chamfer (mean |dx|, mm) per segment
(forehead, nose, lips, chin, under-chin) and the extreme points' offsets (nose tip, upper / lower lip, chin: mm,
+ = ours sticks out further). Saves $T/out/prof_<model>.png (photo | ours | contours)."""
import json, os, sys, tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import stage
from hifipushie import scene, store

T = os.environ["T"]
PHOTO = "/home/joe/dev/s0urc3/docs/img/tess_ref_full/tess_head_profile_left.png"
CROP = [0, 192, 1152, 1344]
PX = 768
SEG = {"forehead": (380, 560), "nose": (560, 715), "lips": (715, 830), "chin": (830, 905), "under_chin": (905, 990)}


def contour_photo():
    a = np.asarray(Image.open(PHOTO).convert("RGB").crop(CROP).resize((PX, PX), Image.LANCZOS)).astype(float)
    bg = np.median(a[:, :15].reshape(-1, 3), 0)
    fg = np.abs(a - bg).sum(-1) > 40
    return np.array([int(np.argmax(r)) if r.any() else -1 for r in fg]), a


def contour_model(name):
    refs = json.loads((store.HOME / name / "human_refs.json").read_text())
    cam = refs["cameras"][2]
    fr = stage.fitted_frame(cam, CROP, "prof")
    sp = store.load(name)
    sn = stage.ensure(name, with_hair=False)
    with tempfile.TemporaryDirectory() as tmp:
        f = {**fr, "out": str(Path(tmp) / "p.png")}
        job = {"blend": str(scene.blend_path(sn)), "views": [f], "size": PX, "samples": 16, "hide": ["hair"], "flat": False,
               "transparent": True, "mode": "render", "lighting": {**stage.FRONT_LIGHT, "exposure": -0.1, "target": f["center"]}}
        scene._blender(job, 2400)
        im = Image.open(f["out"]).convert("RGBA")
    al = np.asarray(im)[..., 3] > 128
    mmpx = cam["t"][2] / cam["f"] * 1000 * (CROP[2] - CROP[0]) / PX
    return np.array([int(np.argmax(r)) if r.any() else -1 for r in al]), im, mmpx


cp, photo = contour_photo()
s = PX / (CROP[2] - CROP[0])
for name in sys.argv[1:]:
    cm, im, mmpx = contour_model(name)
    print(f"{name}: profile vs photo ({mmpx:.2f} mm a px)")
    tot = []
    # bands from the photo's own nose tip (rows of the 768 px crop): no hand-set heights
    band = lambda a, b: (max(a, 0), min(b, PX))  # noqa: E731
    rn = 300 + int(np.argmin(np.where(cp[300:520] >= 0, cp[300:520], 9999)))
    segs = {"brow+glabella": band(rn - 130, rn - 70), "nose": band(rn - 70, rn + 18), "lips": band(rn + 18, rn + 90),
            "chin": band(rn + 90, rn + 150)}
    for k, (r0, r1) in segs.items():
        ok = [(r, cp[r], cm[r]) for r in range(r0, r1) if cp[r] >= 0 and cm[r] >= 0]
        d = np.array([c - b for _, b, c in ok], float) * mmpx
        tot += list(np.abs(d))
        ia, ib = min(ok, key=lambda q: q[1]), min(ok, key=lambda q: q[2])
        print(f"  {k:14s} chamfer {np.abs(d).mean():5.2f} mm   mean {-d.mean():+5.2f} mm (+ ours forward)   "
              f"extreme {(ia[1] - ib[2]) * mmpx:+5.1f} mm forward, {(ib[0] - ia[0]) * mmpx:+5.1f} mm lower")
    print(f"  ALL            chamfer {np.mean(tot):5.2f} mm")
    ov = Image.fromarray(photo.astype(np.uint8)).convert("RGB")
    dr = ImageDraw.Draw(ov)
    for r in range(PX):
        if cp[r] >= 0:
            dr.point((cp[r], r), fill=(255, 0, 0))
        if cm[r] >= 0:
            dr.point((cm[r], r), fill=(0, 120, 255))
    bg = Image.new("RGBA", im.size, (230, 230, 230, 255))
    ours = Image.alpha_composite(bg, im).convert("RGB")
    out = Image.new("RGB", (PX * 3, PX))
    out.paste(Image.fromarray(photo.astype(np.uint8)), (0, 0))
    out.paste(ours, (PX, 0))
    out.paste(ov, (2 * PX, 0))
    out.save(f"{T}/out/prof_{name}.png")
