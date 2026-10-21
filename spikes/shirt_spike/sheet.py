"""sheet.py <tag>: clay row (front | q | side) over diag row, one PNG <tag>.png; plus a collar crop row <tag>_collar.png."""
import sys
from PIL import Image, ImageDraw
D = "/mnt/data/hifipushie/shirt_spike/"; t = sys.argv[1]; note = sys.argv[2] if len(sys.argv) > 2 else ""
ims = [[Image.open(f"{D}{t}_{k}_{v}.png").convert("RGB") for v in ("front", "q", "side")] for k in ("clay", "diag")]
w, h = ims[0][0].size; H = 300
sc = lambda im, hh: im.resize((int(im.size[0] * hh / im.size[1]), hh))
rows = [[sc(i, H * 2) for i in r] for r in ims]
W = sum(i.size[0] for i in rows[0])
sh = Image.new("RGB", (W, 2 * 2 * H + 30), "white"); y = 30
for r in rows:
    x = 0
    for i in r: sh.paste(i, (x, y)); x += i.size[0]
    y += 2 * H
ImageDraw.Draw(sh).text((8, 8), f"{t}: {note}", fill="black"); sh.save(f"{D}{t}.png")
# collar crops: top 30 % of each clay frame, centre 60 %
cr = [i.crop((int(i.size[0] * .2), 0, int(i.size[0] * .8), int(i.size[1] * .32))) for i in ims[0] + ims[1][:1]]
cr = [sc(c, 360) for c in cr]
cs = Image.new("RGB", (sum(c.size[0] for c in cr), 390), "white"); x = 0
for c in cr: cs.paste(c, (x, 30)); x += c.size[0]
ImageDraw.Draw(cs).text((8, 8), f"{t} collar: clay front | q | side | diag front. {note}", fill="black"); cs.save(f"{D}{t}_collar.png")
print(D + t + ".png")
