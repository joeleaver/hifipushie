"""strip.py <out.jpg> <width per panel> <label=path> ...: panels side by side with labels (a judging strip).
A path ending in '#ref' takes the LEFT half of a reference | ours pair; '#ours' the right half."""
import sys

from PIL import Image, ImageDraw

out, W = sys.argv[1], int(sys.argv[2])
ims = []
for a in sys.argv[3:]:
    lab, p = a.split("=", 1)
    half = None
    if "#" in p:
        p, half = p.split("#")
    im = Image.open(p).convert("RGB")
    if half:
        w = im.width // 2
        im = im.crop((0, 0, w, im.height) if half == "ref" else (w, 0, im.width, im.height))
    im = im.resize((W, int(im.height * W / im.width)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 7 * len(lab) + 10, 16], fill=(20, 20, 20))
    d.text((5, 2), lab, fill=(255, 255, 255))
    ims.append(im)
H = max(i.height for i in ims)
S = Image.new("RGB", (W * len(ims), H), (230, 230, 230))
for k, i in enumerate(ims):
    S.paste(i, (k * W, 0))
S.save(out, quality=88)
print(out, S.size)
