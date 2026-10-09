"""neck.py <model> [view]: the neck's length like with like, the photo against the model's clay render through the
photo's fitted camera: each picture's silhouette (the photo against its plain background; the render's own mask),
its width row by row under the chin (detector point 152), the neck's narrowest width, and where the outline turns
out into the shoulders (the first row under the narrowest one wider than 1.5 x it): chin -> that shoulder line (mm,
at the face's depth). Prints both and saves out/neck_<model>.png (the two silhouettes with the rows)."""
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import likeness, store

name = sys.argv[1]
view = int(sys.argv[2]) if len(sys.argv) > 2 else 0
refs = likeness._refs(name)
ph = likeness.photo_sides(refs)[view]
cam = ph["cam"]
img = np.asarray(ph["img"].convert("RGB"), float)
H, W = img.shape[:2]
bg = np.median(np.r_[img[:20, :20].reshape(-1, 3), img[:20, -20:].reshape(-1, 3)], axis=0)
fg_ph = np.linalg.norm(img - bg, axis=2) > 28
mesh = likeness.model_mesh(store.load(name)["base"])
im_m, k, ps = likeness.render(mesh, cam, (0, 0, W, H), px=max(W, H), brows=False, passes=True)
fg_md = np.isfinite(ps["zb"])
fg_md = np.asarray(Image.fromarray(fg_md.astype(np.uint8) * 255).resize((W, H))) > 127


def profile(fg, chin_y, mmpx, cx):
    rows = np.arange(int(chin_y), H)
    w = []
    for y in rows:
        xs = np.flatnonzero(fg[y])
        if len(xs) == 0:
            w.append(np.nan)
            continue
        # the run through the face's centre column
        c = int(cx)
        if not fg[y, c]:
            w.append(np.nan)
            continue
        l, r = c, c
        while l > 0 and fg[y, l - 1]:
            l -= 1
        while r < W - 1 and fg[y, r + 1]:
            r += 1
        w.append((r - l) * mmpx)
    w = np.array(w)
    a0, a1 = int(8 / mmpx), int(90 / mmpx)  # (the neck: 8-90 mm under the chin; the chin's own rows are narrow)
    i0 = a0 + int(np.nanargmin(w[a0:a1]))
    nmin = w[i0]
    out = np.flatnonzero(w[i0:] > 1.5 * nmin)
    i1 = i0 + int(out[0]) if len(out) else len(w) - 1
    return {"neck_min_mm": float(nmin), "chin_to_neck_min_mm": float(i0 * mmpx), "chin_to_shoulder_mm": float(i1 * mmpx),
            "rows": (rows[i0], rows[i1])}


P = ph["side"].P
chin = P[152]
res = {"photo": profile(fg_ph, chin[1], ph["mmpx"], P[152][0])}
md = likeness.model_sides(store.load(name)["base"], [ph], refit=False)[0]
Pm = md["side"].P
res["model"] = profile(fg_md, Pm[152][1], md["mmpx"], Pm[152][0])
for k_, r in res.items():
    print(f"{k_:6s} neck narrowest {r['neck_min_mm']:.1f} mm, {r['chin_to_neck_min_mm']:.1f} mm under the chin; chin -> "
          f"shoulder line {r['chin_to_shoulder_mm']:.1f} mm")
S = Image.new("RGB", (2 * W, H), (255, 255, 255))
for i, (fg, r) in enumerate(((fg_ph, res["photo"]), (fg_md, res["model"]))):
    t = Image.fromarray((fg * 200).astype(np.uint8)).convert("RGB")
    d = ImageDraw.Draw(t)
    for y in r["rows"]:
        d.line([(0, y), (W, y)], fill=(255, 0, 0), width=2)
    S.paste(t, (i * W, 0))
S.thumbnail((1200, 1200))
S.save(f"/mnt/data/hifipushie/facesliders/out/neck_{name}.png")
