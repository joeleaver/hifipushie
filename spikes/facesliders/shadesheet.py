"""shadesheet.py <out png> <model> [regions]: faces6, the fast renderer's new shading (likeness.render ao / shadow) on
feature crops through the model's own fitted cameras: photo | clay (old) | clay + AO + key shadow | the photo's fitted
light + AO + its shadow. The point: nostril show, the upper lip's shadow and the lid fold's shading must be readable on
the model the same way as on the photo before readers compare them."""
import json
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

from featsheet import boxes
from hifipushie import humanfit, likeness, likeness_shape as ls, store

T = int(os.environ.get("T", "300"))
SOFT = float(os.environ.get("SOFT", "8"))   # degrees: the light disc's radius


def photo_light(mesh, cam, box, img, px):
    _, k, ps = likeness.render(mesh, cam, box, px=px, brows=False, passes=True)
    H, W = ps["zb"].shape
    crop = img.crop(tuple(int(round(v)) for v in box)).resize((W, H), Image.LANCZOS)
    Y = ls._lin(crop)
    mask = ps["part"] == 0
    c0, w, rms = ls.fit_light(Y, ps["nrm"], mask)
    return (c0, w, float(np.median(Y[mask])))


if __name__ == "__main__":
    out, m = sys.argv[1], sys.argv[2]
    regions = (sys.argv[3] if len(sys.argv) > 3 else "nose,lips,eyes").split(",")
    refs = json.loads((store.HOME / m / "human_refs.json").read_text())
    bx = boxes(refs, regions)
    st = humanfit.state(store.load(m)["base"])
    mesh = likeness.model_mesh_from_state(st)
    t = time.time()
    likeness.ambient_occlusion(mesh)
    print(f"ao {time.time() - t:.2f} s, {len(mesh['V'])} verts", flush=True)
    cols = ["photo", "clay", "clay+ao+shadow", "photo light+ao+shadow"]
    sheet = Image.new("RGB", (T * len(cols), (T + 18) * len(bx) + 18), "white")
    dr = ImageDraw.Draw(sheet)
    for j, lab in enumerate(cols):
        dr.text((j * T + 4, 2), lab, fill=(0, 0, 0))
    for i, (vi, rg, box, img) in enumerate(bx):
        cam = refs["cameras"][vi]
        y = 18 + i * (T + 18)
        dr.text((4, y), f"{m} view {vi} {rg}", fill=(0, 0, 0))
        sheet.paste(img.crop(tuple(int(round(b)) for b in box)).resize((T, T), Image.LANCZOS), (0, y + 16))
        t = time.time()
        a = likeness.render(mesh, cam, box, px=2 * T, brows=False)[0]
        b = likeness.render(mesh, cam, box, px=2 * T, brows=False, ao=True, shadow=SOFT)[0]
        lt = photo_light(mesh, cam, box, img, 2 * T)
        c = likeness.render(mesh, cam, box, px=2 * T, brows=False, ao=True, shadow=SOFT, light=lt)[0]
        print(f"view {vi} {rg}: {time.time() - t:.2f} s, light c0 {lt[0]:.3f} w {np.round(lt[1], 3).tolist()}", flush=True)
        for j, im in enumerate((a, b, c)):
            sheet.paste(im.resize((T, T), Image.LANCZOS), ((j + 1) * T, y + 16))
    sheet.save(out)
    print("wrote", out)
