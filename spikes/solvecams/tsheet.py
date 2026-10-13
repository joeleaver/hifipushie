"""tsheet.py <out png> <after model> <before model> [label_after] [label_before]: REFERENCE | after | before from the
feature tour's tiles (spikes/tour/tour.py: photo | clay | overlay | raking per feature and view; /mnt/data/hifipushie/
tour/<model>/<feature>_v<i>.png): per row one feature and view: the picture's crop, each model's clay and its 50 %
overlay on the picture. Shape and eye placement only (clay: no dressing)."""
import os, sys
from PIL import Image, ImageDraw, ImageFont
out, A, B = sys.argv[1:4]
la = sys.argv[4] if len(sys.argv) > 4 else A
lb = sys.argv[5] if len(sys.argv) > 5 else B
F = lambda s: ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", s)  # noqa: E731
ROWS = [("JAW + CHIN, front", "chin_jaw", 0), ("CHIN, front", "chin", 0), ("EYES, front", "eyes", 0), ("JAW + CHIN, three-quarter", "chin_jaw", 1), ("EYES, three-quarter", "eyes", 1), ("JAW + CHIN, profile", "chin_jaw", 2)]
T = 420
def panels(m, f, v):
    p = f"/mnt/data/hifipushie/tour/{m}/{f}_v{v}.png"
    if not os.path.exists(p):
        return None
    im = Image.open(p).convert("RGB"); w = im.size[0] // 4
    return [im.crop((i * w, 0, (i + 1) * w, im.size[1])).resize((T, int(T * im.size[1] / w))) for i in range(4)]
rows = [(lab, panels(A, f, v), panels(B, f, v)) for lab, f, v in ROWS]
rows = [r for r in rows if r[1] and r[2]]
H = sum(r[1][0].size[1] + 70 for r in rows) + 150
W = Image.new("RGB", (5 * T + 40, H), "white"); d = ImageDraw.Draw(W)
for i, t in enumerate(("REFERENCE", f"AFTER: {la}", "after, over the picture", f"BEFORE: {lb}", "before, over the picture")):
    d.text((20 + i * T + 8, 30), t, fill=(0, 0, 0), font=F(34 if i in (0, 1, 3) else 24))
y = 130
for lab, a, b in rows:
    d.text((20, y), lab, fill=(160, 0, 0), font=F(36)); y += 60
    for i, im in enumerate((a[0], a[1], a[2], b[1], b[2])):
        W.paste(im, (20 + i * T, y))
    y += a[0].size[1] + 10
W.save(out); print(out, W.size)
