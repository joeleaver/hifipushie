"""fid2.py <model> [out png]: faces6, the fast renderer against the SHIPPED LOOK (featsheet's dressed EEVEE render
through the same fitted cameras and crops) and against the photo. Per crop (front / 3/4 / profile x nose / lips /
eyes), on the model's skin pixels, at the crop's native picture pixels:
  corr   correlation of BAND-PASS luminance (difference of Gaussians, BP_LO..BP_HI mm): the shading cues (folds,
         nostrils, lip shadow) independent of overall light level and albedo;
  dL     mean |L / median - L' / median'| (the overall shading's contrast and level).
Columns: photo | Blender (shipped look) | fast raw mesh, photo light calibrated (AO share + direct scale) | fast,
old clay key. Readers are fine on the fast render if corr(fast, Blender) is high and corr(fast, photo) is not
below corr(Blender, photo)."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter

import featsheet
from featsheet import boxes
from fidelity import crop_render, lum
from hifipushie import humanfit, likeness, store

BP_LO, BP_HI = float(os.environ.get("BP_LO", "0.6")), float(os.environ.get("BP_HI", "3.0"))


def bandpass(L, mmpx):
    return gaussian_filter(L, BP_LO / mmpx) - gaussian_filter(L, BP_HI / mmpx)


def corr(a, b, m):
    a, b = a[m] - a[m].mean(), b[m] - b[m].mean()
    return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum() + 1e-12))


if __name__ == "__main__":
    m = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else f"/mnt/data/hifipushie/faces6/out/fid2_{m}.png"
    refs = json.loads((store.HOME / m / "human_refs.json").read_text())
    st = humanfit.state(store.load(m)["base"])
    raw = likeness.model_mesh_from_state(st)
    bx = boxes(refs, ["nose", "lips", "eyes"])
    blend = featsheet.render_model(m, bx)
    T = 260
    cols = ["photo", "Blender (shipped)", "fast, photo light calibrated", "fast, old clay"]
    sheet = Image.new("RGB", (T * len(cols), (T + 30) * len(bx) + 18), "white")
    dr = ImageDraw.Draw(sheet)
    for j, lab in enumerate(cols):
        dr.text((j * T + 4, 2), lab, fill=(0, 0, 0))
    rows = []
    for i, (vi, rg, box, img) in enumerate(bx):
        cam = refs["cameras"][vi]
        side = int(round(max(box[2] - box[0], box[3] - box[1])))
        ph = img.crop(tuple(int(round(b)) for b in box)).resize((side, side), Image.LANCZOS)
        bl = blend[f"v{vi}_{rg}"].resize((side, side), Image.LANCZOS)
        fa = crop_render(raw, cam, box, img)
        cl = likeness.render(raw, cam, box, px=side * 2, brows=False)[0].resize((side, side), Image.LANCZOS)
        _, k, ps = likeness.render(raw, cam, box, px=side, brows=False, passes=True)
        msk = ps["part"] == 0
        mmpx = likeness._mm_per_px(cam, raw["L"][27:48])
        Ls = {"photo": lum(ph), "blender": lum(bl), "fast": lum(fa), "clay": lum(cl)}
        Ln = {k_: v / np.median(v[msk]) for k_, v in Ls.items()}
        B = {k_: bandpass(v, mmpx) for k_, v in Ln.items()}
        r = {"view": vi, "region": rg,
             "corr fast~blender": corr(B["fast"], B["blender"], msk), "corr clay~blender": corr(B["clay"], B["blender"], msk),
             "corr photo~blender": corr(B["photo"], B["blender"], msk), "corr photo~fast": corr(B["photo"], B["fast"], msk),
             "corr photo~clay": corr(B["photo"], B["clay"], msk),
             "dL fast~blender": float(np.abs(Ln["fast"] - Ln["blender"])[msk].mean()),
             "dL clay~blender": float(np.abs(Ln["clay"] - Ln["blender"])[msk].mean()),
             "dL fast~photo": float(np.abs(Ln["fast"] - Ln["photo"])[msk].mean()),
             "dL blender~photo": float(np.abs(Ln["blender"] - Ln["photo"])[msk].mean())}
        rows.append(r)
        print(json.dumps({k_: (round(v, 3) if isinstance(v, float) else v) for k_, v in r.items()}), flush=True)
        y = 18 + i * (T + 30)
        dr.text((4, y), f"view {vi} {rg}  corr fast~blender {r['corr fast~blender']:.2f} (clay {r['corr clay~blender']:.2f}); "
                f"photo~blender {r['corr photo~blender']:.2f} photo~fast {r['corr photo~fast']:.2f}", fill=(0, 0, 0))
        for j, im in enumerate((ph, bl, fa, cl)):
            sheet.paste(im.resize((T, T), Image.LANCZOS), (j * T, y + 26))
    sheet.save(out)
    keys = [k_ for k_ in rows[0] if k_ not in ("view", "region")]
    print("MEAN", json.dumps({k_: round(float(np.mean([r[k_] for r in rows])), 3) for k_ in keys}))
    print("wrote", out)
