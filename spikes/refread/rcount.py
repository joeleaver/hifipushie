"""rcount.py <model>...: the outline reads of a block-in model's REAL reference pictures, plain-background reader vs the
parser (mediapipe / bisenet): count, mean, rms per view, and how the two readers agree where both read the same model
outline sample (mm). Saves out/rcount_<model>.png (yellow = parser reads, cyan = plain reader's)."""
import sys
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import blockin as bi, face_ruler as fr, faceparse as fp, store

OUT = "/mnt/data/hifipushie/refread/out"
for m in sys.argv[1:]:
    spec, rj = store.load(m), bi._refs(m)
    head = fr.model_head(spec)
    tiles = []
    for vi, (v, cam) in enumerate(zip(rj["views"], rj["cameras"])):
        img = Image.open(v["image"]).convert("RGB")
        kind = fr.kind_of(v.get("yaw", 0))
        base = {"cam": cam, "kind": kind, "style": "photo", "hair": True, "face_only": True, "img": img, "limbus": False}
        res = {}
        pm, ps = fr.photo_masks(img, cam, head)
        res["photo"] = [o for o in fr.observe(head, [dict(base, mask=pm, trust=ps)], colour=False) if o["type"] == "outline"]
        for model in ("mediapipe", "bisenet"):
            g, s, full = fp.masks(img, cam, head, model=model)
            res[model] = [o for o in fr.observe(head, [dict(base, mask=g, trust=s)], colour=False) if o["type"] == "outline"]
        print(f"{m} view {vi} {kind}: plain backdrop {fr.plain_backdrop(img):.2f}")
        for k, ob in res.items():
            o = np.array([x["o"] for x in ob])
            if len(o):
                print(f"   {k:9s} n {len(o):4d}  mean {o.mean():+5.2f}  rms {np.sqrt((o ** 2).mean()):5.2f} mm")
            else:
                print(f"   {k:9s} n    0")
        a = {tuple(np.round(x["p"], 1)): x["o"] for x in res["photo"]}
        for k in ("mediapipe", "bisenet"):
            d = np.array([x["o"] - a[tuple(np.round(x["p"], 1))] for x in res[k] if tuple(np.round(x["p"], 1)) in a])
            if len(d):
                print(f"   {k} - photo at the {len(d)} shared samples: mean {d.mean():+.2f}, sd {d.std():.2f} mm")
        P = fr._cam_points(cam, np.asarray(head["L"], float)[:68])[1]
        bx = fp.head_box(P, img.size)
        t = img.copy()
        d_ = ImageDraw.Draw(t)
        for k, col in (("photo", (0, 255, 255)), ("mediapipe", (255, 235, 0))):
            for x in res[k]:
                d_.line([tuple(x["p"]), tuple(x["q"])], fill=col, width=1)
                d_.point(tuple(x["q"]), fill=(255, 0, 0))
        tiles.append(t.crop(tuple(int(b) for b in bx)).resize((640, 640), Image.LANCZOS))
    W = Image.new("RGB", (640 * len(tiles), 640))
    for i, t in enumerate(tiles):
        W.paste(t, (640 * i, 0))
    W.save(f"{OUT}/rcount_{m}.png")
