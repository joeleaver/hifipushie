"""featsheet.py <out png> <refs model> <regions> <model>...: FEATURE-CROP comparison sheet (faces5): per region and view,
the photo's crop beside each model's DRESSED render (eevee, no hair, the photo's fitted light: shot.light) through the
model's own fitted camera for that picture (so the crops line up with the photo's pixels). One Blender call per model
(all crops as frames). regions: comma list of nose, lips, eyes, mouth_nose; views: every reference view (front, 3/4,
profile), profile crops from its clicked points."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import sheet1  # noqa: F401
import stage
from hifipushie import likeness, store
from shot import light

SCR = os.environ.get("SCR", "f5_feat")
SIZE = int(os.environ.get("SIZE", "512"))
MP = {"nose": [1, 2, 98, 327, 168, 6, 64, 294, 48, 278, 129, 358],
      "lips": [61, 291, 0, 17, 37, 267, 84, 314, 13, 14],
      "eyes": [33, 133, 263, 362, 105, 334, 159, 145, 386, 374],
      "mouth_nose": [61, 291, 17, 1, 98, 327, 168]}
CLICK = {"nose": ["nose_tip", "nose_base", "nose_bridge"], "lips": ["lip_upper", "lip_lower", "nose_base", "mouth_corner.L"],
         "eyes": ["eye_outer.L", "nose_bridge"], "mouth_nose": ["nose_tip", "lip_lower", "nose_bridge", "mouth_corner.L"]}
PAD = {"nose": 1.5, "lips": 1.5, "eyes": 1.25, "mouth_nose": 1.3}


def boxes(refs, regions):
    out = []
    for vi, v in enumerate(refs["views"]):
        img = Image.open(v["image"]).convert("RGB")
        yaw = abs(float(v.get("yaw", 0.0)))
        P = likeness.detect([img])[0] if yaw < 70 else None
        for rg in regions:
            if P is not None:
                Q = np.asarray(P, float)[MP[rg], :2]
            else:
                pts = v.get("points") or {}
                Q = np.array([pts[k] for k in CLICK[rg] if k in pts], float)
                if len(Q) < 2:
                    continue
            lo, hi = Q.min(0), Q.max(0)
            c = 0.5 * (lo + hi)
            side = PAD[rg] * max(hi - lo) + 20
            out.append((vi, rg, [c[0] - side / 2, c[1] - side / 2, c[0] + side / 2, c[1] + side / 2], img))
    return out


def render_model(m, bx):
    sp = store.load(m)
    d = store.HOME / SCR
    d.mkdir(exist_ok=True)
    (d / "spec.json").write_text(json.dumps(sp, indent=1))
    r = json.loads((store.HOME / m / "human_refs.json").read_text())
    (d / "human_refs.json").write_text(json.dumps(r))
    frames = [stage.fitted_frame(r["cameras"][vi], box, f"v{vi}_{rg}") for vi, rg, box, _ in bx]
    ims = stage.shoot(SCR, frames, light(), size=SIZE, hair_on=False)
    return {k: v_.convert("RGB") for k, v_ in ims.items()}


if __name__ == "__main__":
    out, refm, regions, models = sys.argv[1], sys.argv[2], sys.argv[3].split(","), sys.argv[4:]
    refs = json.loads((store.HOME / refm / "human_refs.json").read_text())
    bx = boxes(refs, regions)
    rend = {m: render_model(m, bx) for m in models}
    T = 300
    sheet = Image.new("RGB", (T * (1 + len(models)), (T + 18) * len(bx) + 18), "white")
    dr = ImageDraw.Draw(sheet)
    for j, lab in enumerate(["photo"] + models):
        dr.text((j * T + 4, 2), lab, fill=(0, 0, 0))
    for i, (vi, rg, box, img) in enumerate(bx):
        y = 18 + i * (T + 18)
        dr.text((4, y), f"view {vi} {rg}", fill=(0, 0, 0))
        sheet.paste(img.crop(tuple(int(round(b)) for b in box)).resize((T, T), Image.LANCZOS), (0, y + 16))
        for j, m in enumerate(models):
            sheet.paste(rend[m][f"v{vi}_{rg}"].resize((T, T), Image.LANCZOS), ((j + 1) * T, y + 16))
    sheet.save(out)
    print("wrote", out)
