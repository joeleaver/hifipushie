"""summary.py <out.png> <start cmp.jpg> <end cmp.jpg> <start pair.png> <end pair.png>: photo | start | end, dressed
(shot.py's whole-head halves and its eye / mouth crops) over clay (the matched pairs' photo and model tiles)."""
import sys

from PIL import Image, ImageDraw

out, c0, c1, p0, p1 = sys.argv[1:6]
A, B = Image.open(c0).convert("RGB"), Image.open(c1).convert("RGB")
w, h = A.size[0] // 2, A.size[1]
T = 520
cells = [[A.crop((0, 0, w, h)), A.crop((w, 0, 2 * w, h)), B.crop((w, 0, 2 * w, h))]]
P0, P1 = Image.open(p0).convert("RGB"), Image.open(p1).convert("RGB")
cells.append([P0.crop((0, 34, T, 34 + T)), P0.crop((T, 34, 2 * T, 34 + T)), P1.crop((T, 34, 2 * T, 34 + T))])
W = 600
rows = []
for r in cells:
    hh = int(W * r[0].size[1] / r[0].size[0])
    rows.append([c.resize((W, hh), Image.LANCZOS) for c in r])
S = Image.new("RGB", (3 * W, 40 + sum(r[0].size[1] for r in rows)), (24, 24, 24))
d = ImageDraw.Draw(S)
for i, lab in enumerate(("photo", "start (g4_a head, g4 skin)", "end (likeloop round 5)")):
    d.text((i * W + 10, 12), lab, fill=(240, 240, 240))
y = 40
for r in rows:
    for i, c in enumerate(r):
        S.paste(c, (i * W, y))
    y += r[0].size[1]
S.save(out)
print(out, S.size)
