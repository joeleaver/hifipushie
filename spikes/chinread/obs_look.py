"""obs_look.py <model> <out.png> <types: cloth,ramp,outline..> [chin.<key>=<value> ..]: the reads of the given types drawn on
the model's reference pictures (front and 3/4 lower face): green = the model's contour point, red = where the picture
has it; + the parser's skin (red tint) / cloth (blue tint) maps when cloth is asked. Prints each group's n, mean, rms."""
import sys
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import face_ruler as fr

m, out, types = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
chin = {}
for a in sys.argv[4:]:
    k, v = a.split("=")
    chin[k[5:]] = v if k == "chin.chin_lm" else ({"0": False, "1": True}[v] if v in "01" else float(v))
head, views, notes = fr.reference_views(m, lids=False, lips=False, parse="auto", chin=chin)
for v in views:
    if v.get("extra"):
        v["extra_obs"] = v["extra"](head, v)
obs = fr.observe(head, views)
tiles = []
for v in views:
    if v["kind"] == "profile" and "outline" not in types:
        continue
    im = v["img"].copy()
    if "cloth" in types and v.get("_parse"):
        a = np.asarray(im, float)
        a[..., 0] = np.clip(a[..., 0] + 60 * (v["_parse"]["skin"] > 0.5), 0, 255)
        a[..., 2] = np.clip(a[..., 2] + 90 * (v["_parse"]["cloth"] > 0.5), 0, 255)
        im = Image.fromarray(a.astype(np.uint8))
    d = ImageDraw.Draw(im)
    oo = [ob for ob in obs if ob["view"] == v["kind"] and ob["type"] in types]
    for ob in oo:
        d.line([tuple(ob["p"]), tuple(ob["q"])], fill=(255, 255, 0), width=2)
        d.ellipse([ob["p"][0] - 3, ob["p"][1] - 3, ob["p"][0] + 3, ob["p"][1] + 3], fill=(0, 220, 0))
        d.ellipse([ob["q"][0] - 3, ob["q"][1] - 3, ob["q"][0] + 3, ob["q"][1] + 3], fill=(255, 0, 0))
    for t in types:
        o = np.array([ob["o"] for ob in oo if ob["type"] == t])
        if len(o):
            print(f"{m} {v['kind']} {t}: n {len(o)} mean {o.mean():+.2f} rms {np.sqrt((o ** 2).mean()):.2f} mm (reader {v.get('reader')})")
        else:
            print(f"{m} {v['kind']} {t}: n 0")
    P = fr._cam_points(v["cam"], np.asarray(head["L"], float)[:68])[1]
    s = 1.5 * (P[8, 1] - P[33, 1])
    cx, cy = P[[48, 54, 8]].mean(0)
    box = (cx - 1.2 * s, cy - s, cx + 1.2 * s, cy + 1.2 * s) if "outline" not in types else (0, 0, im.size[0], im.size[1])
    tiles.append(im.crop(tuple(int(x) for x in box)).resize((720, int(720 * (box[3] - box[1]) / (box[2] - box[0]))), Image.LANCZOS))
W = Image.new("RGB", (sum(t.size[0] for t in tiles), max(t.size[1] for t in tiles)), "white")
x = 0
for t in tiles:
    W.paste(t, (x, 0)); x += t.size[0]
W.save(out)
print(out)
