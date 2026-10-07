"""sheet.py <out.png> <suffix> <panel px> <n panels> style [style ...]: rows of look sheets ($HR/hu_<style>_<suffix>.png,
panels 480 px under a 22 px title) shrunk into one image, a label per row."""
import os, sys
from PIL import Image, ImageDraw

HR = os.environ.get("HR", "/home/joe/dev/hifipushie/workspace/hair_renders")
out, suf, px, n = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
styles = sys.argv[5:]
img = Image.new("RGB", (px * n, (px + 16) * len(styles)), (30, 31, 35))
d = ImageDraw.Draw(img)
for r, s in enumerate(styles):
    im = Image.open(f"{HR}/hu_{s}_{suf}.png").convert("RGB")
    S = 480
    for k in range(n):
        p = im.crop((k * S, 22, (k + 1) * S, 22 + S)).resize((px, px), Image.LANCZOS)
        img.paste(p, (k * px, r * (px + 16) + 16))
    d.text((6, r * (px + 16) + 2), f"{s} ({suf})", fill=(240, 220, 160))
img.save(out if os.path.isabs(out) else f"{HR}/{out}")
print(out)
