"""feat.py <a1 model> <jobs.json> <after tag> <before tag>: ONE SMALL IMAGE PER FEATURE (Joe, 2026-10-12: judge one
feature at a time from small tiles, not from the wide sheet) from tiles.py's tiles: reference crop | AFTER under the
photo light at the picture's exposure | BEFORE the same | AFTER under the raking light -> $G/out/feat_<after>_<feature>.png
(front, eyeR, eyeL, mouth; the other reference views as view<i>)."""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont
from hifipushie import blockin as bi, skin_read as sr

a1, jpath, ta, tb = sys.argv[1:5]
G = os.environ["G"] + "/out"
J = json.load(open(jpath))
rj = bi._refs(a1)
boxes = sr.boxes(a1)
T = 420
F = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)


def tile(tag, k):
    f = f"{G}/t_{tag}_{k}.png"
    return Image.open(f).convert("RGB").resize((T, T), Image.LANCZOS) if os.path.exists(f) else Image.new("RGB", (T, T), (230, 230, 230))


def crop(vi, box):
    return Image.open(rj["views"][vi]["image"]).convert("RGB").crop(tuple(int(round(x)) for x in box)).resize((T, T), Image.LANCZOS)


def row(name, ims):
    W = Image.new("RGB", (T * len(ims), T + 28), "white")
    d = ImageDraw.Draw(W)
    for i, (lab, im) in enumerate(ims):
        W.paste(im, (i * T, 28))
        d.text((i * T + 6, 3), lab, fill=(0, 0, 0), font=F)
    W.save(f"{G}/feat_{ta}_{name}.png")
    print(f"{G}/feat_{ta}_{name}.png")


front = J["front"]
for vi in range(J["views"]):
    row("front" if vi == front else f"view{vi}", [("REFERENCE", crop(vi, boxes[vi])), ("AFTER, photo light", tile(ta, f"v{vi}")), ("BEFORE (sf)", tile(tb, f"v{vi}"))])
for k in ("zoomR", "zoomL"):
    if k in J["crops"]:
        row(k, [("REFERENCE", crop(front, J["crops"][k])), ("AFTER, photo light", tile(ta, k)), ("BEFORE (sf)", tile(tb, k))])
for k in ("eyeR", "eyeL", "mouth"):
    row(k, [("REFERENCE", crop(front, J["crops"][k])), ("AFTER, photo light", tile(ta, k)), ("BEFORE (sf)", tile(tb, k)), ("AFTER, raking", tile(ta, k + "_rk"))])
