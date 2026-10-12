"""ov.py <model> <out png> [cameras=free|trust|refit]: what the joint solve READS on a block-in model's pictures, drawn
(the head crop of each view): green = the model's outline through the view's camera as the solve leaves it, yellow =
outline reads (model -> picture), magenta / cyan = point reads picture / model (anchors, irises, lips). Nothing applied."""
import sys
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import blockin as bi, face_ruler as fr, faceparse as fp, store

m, out = sys.argv[1], sys.argv[2]
cams = sys.argv[3].split("=")[1] if len(sys.argv) > 3 else "free"
c0 = bi.identity(store.load(m))
rj = bi._refs(m)
root = (rj.get("blockin") or {}).get("root")
off = c0 - bi.identity(store.load(root)) if root else None
cam0 = None if cams == "refit" else (rj.get("blockin") or {}).get("cam_done")
c = fr.compare(m, prior_off=off, cam_sd=fr.PHOTO_CAM_SD6, lids=True, lips=True, parse="auto", adapt=True, cmax=3.0, rounds=1,
               cam_first=2 if cams == "refit" else 0, cam_done0=cam0 if cam0 is not None else np.zeros((len(rj["views"]), 6)))
tiles = []
for v0, v in zip(rj["views"], c["views"]):
    im = v["img"].copy()
    d = ImageDraw.Draw(im)
    cam = bi._refs(m)["cameras"][len(tiles)]          # the camera the round READ through (before its own step)
    _, ps = fr.clay(c["head"], cam, passes=True)
    cm = fr._curve(ps["part"] >= 0)
    if cm is not None:
        d.line([tuple(p) for p in cm], fill=(0, 220, 0), width=1)
    for ob in c["obs"]:
        if ob["view"] != v["kind"] or "p" not in ob:
            continue
        if ob["type"] == "outline":
            d.line([tuple(ob["p"]), tuple(ob["q"])], fill=(255, 235, 0), width=1)
            d.point(tuple(ob["q"]), fill=(255, 0, 0))
        else:
            d.line([tuple(ob["p"]), tuple(ob["q"])], fill=(255, 0, 255), width=1)
            d.point(tuple(ob["p"]), fill=(0, 255, 255))
    P = fr._cam_points(cam, np.asarray(c["head"]["L"], float)[:68])[1]
    bx = fp.head_box(P, im.size, pad=1.7)
    tiles.append(im.crop(tuple(int(b) for b in bx)).resize((900, 900), Image.LANCZOS))
W = Image.new("RGB", (900 * len(tiles), 900))
for i, t in enumerate(tiles):
    W.paste(t, (900 * i, 0))
W.save(out)
print(out, c["n"], "relax", c["relax"])
