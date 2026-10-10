"""tgate.py <shared refs model> <model> ...: Tess's gate through ONE shared set of cameras (the refs model's
human_refs: tess's refit true profile camera): per model a gate copy fs_g_<model> (its spec, the shared refs), the
points rms per view (sigmas, the cameras fixed: the same for every model) and a clay sheet hers | models for every
view ($F/out/tgate_<tag>.jpg, tag = $TAG)."""
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw

import joint as J0
from hifipushie import humanfit, humanfit_map as hm, likeness, store

F = "/mnt/data/hifipushie/facesliders"
refm, models = sys.argv[1], sys.argv[2:]
refs = json.loads((store.HOME / refm / "human_refs.json").read_text())
T = 380
rows = []
for vi, v in enumerate(refs["views"]):
    rows.append([])
    im = Image.open(v["image"]).convert("RGB")
    cam = refs["cameras"][vi]
    w, h = im.size
    # the crop: the head through the camera (its landmarks' box, padded)
    rows[-1].append((im, cam, "hers"))
out = {}
for m in models:
    gm = f"fs_g_{m}"
    d = store.HOME / gm
    d.mkdir(exist_ok=True)
    sp = json.loads((store.HOME / m / "spec.json").read_text())
    (d / "spec.json").write_text(json.dumps(sp, indent=1))
    shutil.copy(store.HOME / refm / "human_refs.json", d / "human_refs.json")
    base = sp.get("spec", sp)["base"]
    st = humanfit.state(base)
    views = [dict(v) for v in refs["views"]]
    views = hm._resolve(st, views)
    rms = J0.view_rms(st, views, refs["cameras"])
    out[m] = rms
    print(f"{m:12s} points rms per view (sigmas, shared cameras): " + "  ".join(f"{x:5.2f}" for x in rms))
    mesh = likeness.model_mesh(base)
    for vi in range(len(refs["views"])):
        rows[vi].append((mesh, refs["cameras"][vi], m))
# the sheet: per view the picture's head crop, then each model's clay through the same camera and crop
S = Image.new("RGB", (T * (1 + len(models)), T * len(rows)), (24, 24, 24))
for vi, row in enumerate(rows):
    im, cam, _ = row[0]
    st0 = humanfit.state(json.loads((store.HOME / models[0] / "spec.json").read_text()).get("base"))
    uv = humanfit.project(cam, st0["L"][:68])
    c = uv.mean(0)
    r = 1.15 * np.ptp(uv, axis=0).max()
    box = [c[0] - r, c[1] - r * 1.1, c[0] + r, c[1] + r * 0.9]
    pim = im.crop(tuple(int(x) for x in box)).resize((T, T), Image.LANCZOS)
    if os.environ.get("DOTS"):   # (check: the model's landmarks through the camera on the picture)
        dd0 = ImageDraw.Draw(pim)
        kk = T / (box[2] - box[0])
        for q in uv:
            dd0.ellipse([(q[0] - box[0]) * kk - 2, (q[1] - box[1]) * kk - 2, (q[0] - box[0]) * kk + 2, (q[1] - box[1]) * kk + 2], fill=(255, 0, 0))
    S.paste(pim, (0, vi * T))
    for j, (mesh, cam_, m) in enumerate(row[1:]):
        rim = likeness.render(mesh, cam_, box, px=T)[0].convert("RGB").resize((T, T))
        dd = ImageDraw.Draw(rim)
        if os.environ.get("DOTS"):
            kk = T / (box[2] - box[0])
            for q in humanfit.project(cam_, mesh["L"][:68]):
                dd.ellipse([(q[0] - box[0]) * kk - 2, (q[1] - box[1]) * kk - 2, (q[0] - box[0]) * kk + 2, (q[1] - box[1]) * kk + 2], fill=(255, 0, 0))
        dd.rectangle([0, 0, 8 + 7 * len(m), 16], fill=(0, 0, 0))
        dd.text((4, 2), m, fill=(255, 255, 255))
        S.paste(rim, ((j + 1) * T, vi * T))
tag = os.environ.get("TAG", "x")
S.save(f"{F}/out/tgate_{tag}.jpg", quality=88)
print("wrote", f"{F}/out/tgate_{tag}.jpg")
