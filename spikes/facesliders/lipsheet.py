"""lipsheet.py <out png> <refs model> <model>...: front lip crops, photo | each model's DRESSED render through the reference's
front camera (lipsolve.render: eevee, no hair), each with the traced vermilion border (lipborder.read, red) and its
under-lip shadow read (lipshade), plus the model's border loop vs the photo's traced border (mm rms) under each."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

os.environ.setdefault("SCR", "f5_lipv")
import lipborder as LB  # noqa: E402
import lipborder_model as LBM  # noqa: E402
import lipshade as LS  # noqa: E402
import lipsolve as LV  # noqa: E402
import sheet1  # noqa: E402
from hifipushie import humanfit, likeness, store  # noqa: E402

out, refm, models = sys.argv[1], sys.argv[2], sys.argv[3:]
refs = json.loads((store.HOME / refm / "human_refs.json").read_text())
v0 = refs["views"][0]
crop = [int(round(c)) for c in sheet1.crop_of(v0)]
ph = np.asarray(Image.open(v0["image"]).convert("RGB").crop(tuple(crop)).resize((LV.SIZE, LV.SIZE), Image.LANCZOS))
full = Image.open(v0["image"]).convert("RGB")
Pfull = likeness.detect([full])[0]
trace = LB.read(full, Pfull)
tiles = [("photo", ph, None)]
for m in models:
    sp = store.load(m)
    im = LV.render(sp, m)
    # the model's border loop vs the photo's traced border, through the model's own front camera
    r2 = json.loads((store.HOME / m / "human_refs.json").read_text())
    st = humanfit.state(sp["base"])
    mb = LBM.model_border_px(st, r2["cameras"][0])
    rm = []
    for k, poly in (("up", trace["upper"][trace["keep"]]), ("lo", trace["lower"][trace["keep"]])):
        lo_x, hi_x = poly[:, 0].min(), poly[:, 0].max()
        px = mb[k][(mb[k][:, 0] > lo_x) & (mb[k][:, 0] < hi_x)]
        d = [dd for _, dd, _ in LBM.miss(px, poly, trace["mmpx"])]
        rm.append(float(np.sqrt(np.mean(np.square(d)))) * trace["mmpx"])
    tiles.append((m, im, rm))
cols = []
for lab, im, rm in tiles:
    pil = Image.fromarray(im.astype(np.uint8))
    P = LS.rs.detect([im.astype(np.uint8)])[0]["P"]
    r = LS.read_values(P, (im.astype(float) / 255.0) @ LS.LUM)
    tr = LB.read(pil, P)
    d = ImageDraw.Draw(pil)
    for k in ("upper", "lower"):
        d.line([tuple(p) for p in tr[k]], fill=(255, 30, 30), width=1)
    box = LS.crop_img(None, P, pad=1.6)
    c = pil.crop(box)
    c = c.resize((420, int(420 * c.height / c.width)), Image.LANCZOS)
    dd = ImageDraw.Draw(c)
    dd.rectangle([0, 0, 420, 30], fill=(255, 255, 255))
    txt = f"{lab}: shadow mid {r['shadow']:.3f} sides {0.5 * (r['shadow_u'][0] + r['shadow_u'][2]):.3f}"
    if rm:
        txt += f"\nborder vs hers (rms mm): upper {rm[0]:.2f} lower {rm[1]:.2f}"
    dd.text((4, 2), txt, fill=(0, 0, 0))
    cols.append(c)
H = max(c.height for c in cols)
sheet = Image.new("RGB", (sum(c.width for c in cols), H), "white")
x = 0
for c in cols:
    sheet.paste(c, (x, 0))
    x += c.width
sheet.save(out)
print("wrote", out)
