"""sheet.py <prefix> <out.png> [cols]: the PNGs check.gd wrote for a prefix, laid out as one labelled sheet."""
import sys, glob, os
from PIL import Image, ImageDraw

pre, out = sys.argv[1], sys.argv[2]
cols = int(sys.argv[3]) if len(sys.argv) > 3 else 4
files = sorted(glob.glob(pre + "_*.png"), key=os.path.getmtime)
ims = [Image.open(f).convert("RGB") for f in files]
w, h = 640, 360
rows = -(-len(ims) // cols)
sheet = Image.new("RGB", (cols * w, rows * (h + 18)), (28, 29, 33))
d = ImageDraw.Draw(sheet)
for k, (f, im) in enumerate(zip(files, ims)):
    x, y = (k % cols) * w, (k // cols) * (h + 18)
    sheet.paste(im.resize((w, h), Image.LANCZOS), (x, y + 18))
    d.text((x + 6, y + 3), os.path.basename(f)[len(os.path.basename(pre)) + 1:-4] + "  (Godot)", fill=(235, 235, 235))
sheet.save(out)
print("wrote", out)
