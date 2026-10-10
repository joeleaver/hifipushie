"""gscore.py <model> <trace json>: hair scored against HAND-TRACED hair outlines (polygons in picture px, one per
reference view: {"views": {"0": {"hair": [[x, y], ...], "box": [x0, y0, x1, y1]}, ...}}), through the model's fitted
cameras: our hair by the ID pass (as hscore.py), IoU and outline chamfer (mm), and colour bands (shadow / mid /
highlight luminance inside each mask). Saves $T/out/gscore_<model>_<view>.png (photo | ours | masks)."""
import json, os, sys, tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

import stage
from hifipushie import scene, store

T = os.environ["T"]
name, tj = sys.argv[1], sys.argv[2]
tr = json.load(open(tj))
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
PX = 640
LIGHT = {**stage.FRONT_LIGHT, "exposure": -0.1}
views = sorted(int(k) for k in tr["views"])
frames = [stage.fitted_frame(refs["cameras"][v], tr["views"][str(v)]["box"], f"v{v}") for v in views]
on = stage.shoot(name, frames, LIGHT, size=PX, hair_on=True)
sn = stage.ensure(name)
st = json.loads((store._dir(sn) / "spec.json").read_text())
white = {p: [1.0, 1.0, 1.0] for p in list(st.get("parts") or {}) + ["body"] if p != "hair"}
ids = {}
with tempfile.TemporaryDirectory() as tmp:
    fr = [{**f, "out": str(Path(tmp) / f"{f['name']}.png")} for f in frames]
    scene._blender({"mode": "render", "blend": str(scene.blend_path(sn)), "views": fr, "size": PX, "samples": 4,
                    "hide": [], "flat": True, "transparent": True, "id_parts": white}, 2400)
    for f in fr:
        a = np.asarray(Image.open(f["out"]).convert("RGBA"), float)
        ids[f["name"]] = (a[..., 3] > 127) & (a[..., :3].max(-1) < 60)


def bands(img, m):
    m = ndi.binary_erosion(m, iterations=2)
    L = img @ [0.299, 0.587, 0.114]
    out = []
    for lo, hi in ((0, 20), (40, 60), (85, 98)):
        a0, a1 = np.percentile(L[m], [lo, hi])
        out.append("#%02x%02x%02x" % tuple(int(255 * x) for x in img[m & (L >= a0) & (L <= a1)].mean(0)))
    return out


for v in views:
    tv = tr["views"][str(v)]
    x0, y0, x1, y1 = tv["box"]
    s = PX / (x1 - x0)
    photo = Image.open(refs["views"][v]["image"]).convert("RGB").crop((x0, y0, x1, y1)).resize((PX, PX), Image.LANCZOS)
    P = np.asarray(photo, float) / 255
    hm = Image.new("L", (PX, PX), 0)
    ImageDraw.Draw(hm).polygon([((x - x0) * s, (y - y0) * s) for x, y in tv["hair"]], fill=255)
    mh = np.asarray(hm) > 127
    mo = ndi.binary_closing(ndi.binary_opening(ids[f"v{v}"], iterations=1), iterations=3)
    cam = refs["cameras"][v]
    mm = cam["t"][2] / cam["f"] * 1000 / s
    iou = (mh & mo).sum() / max((mh | mo).sum(), 1)
    eh, eo = mh ^ ndi.binary_erosion(mh), mo ^ ndi.binary_erosion(mo)
    dh, do = ndi.distance_transform_edt(~eh), ndi.distance_transform_edt(~eo)
    ch = 0.5 * (do[eh].mean() + dh[eo].mean()) * mm
    a = np.asarray(on[f"v{v}"].resize((PX, PX)), float) / 255
    ys, xs = np.nonzero(mh)
    yc = ys.min() + 0.35 * (ys.max() - ys.min())
    top_h = (mh & (np.arange(PX)[:, None] < yc)).sum()
    top_o = (mo & (np.arange(PX)[:, None] < yc)).sum()
    print(f"view {v}: IoU {iou:.3f}  outline chamfer {ch:.1f} mm  area ours / hers {mo.sum() / max(mh.sum(), 1):.2f} "
          f"(top third {top_o / max(top_h, 1):.2f})  extra {100 * (mo & ~mh).sum() / max(mh.sum(), 1):.0f}% "
          f"missing {100 * (mh & ~mo).sum() / max(mh.sum(), 1):.0f}%")
    print(f"   colour shadow / mid / highlight: hers {bands(P, mh)}  ours {bands(a, mo)}")
    vis = np.zeros((PX, PX, 3))
    vis[..., 0], vis[..., 2] = mh, mo
    out = Image.new("RGB", (PX * 3, PX))
    out.paste(photo, (0, 0))
    out.paste(on[f"v{v}"].resize((PX, PX)), (PX, 0))
    out.paste(Image.fromarray((vis * 255).astype(np.uint8)), (2 * PX, 0))
    out.save(f"{T}/out/gscore_{name}_{v}.png")
