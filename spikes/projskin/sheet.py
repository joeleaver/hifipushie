"""sheet.py <out.png> <tile px> <rows: frame,frame,...> <col>... [footer=text file]: a judging sheet from shots.py's tiles.
col = "LABEL|dir|suffix" (tile = <dir>/<frame>_<suffix>.png; a missing tile is a grey cell). LARGE labels.
Also prints, for cols marked "LABEL|dir|suffix|vs=<k>", the mean Lab dE of that column against column k over the
pixels that are not backdrop in column k (the relit comparison)."""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from hifipushie import skin_project as sp

out, T = sys.argv[1], int(sys.argv[2])
rows = sys.argv[3].split(",")
cols, footer = [], None
for a in sys.argv[4:]:
    if a.startswith("footer="):
        footer = open(a[7:]).read()
    else:
        cols.append(a.split("|"))
def font(px):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, px)
    return ImageFont.load_default()
F1, F2, F3 = font(max(T // 14, 22)), font(max(T // 18, 18)), font(max(T // 26, 15))
HEAD, LEFT = int(T * 0.24), int(T * 0.5)
flines = footer.strip().split("\n") if footer else []
FH = int(len(flines) * F3.size * 1.35) + (20 if flines else 0)
S = Image.new("RGB", (LEFT + T * len(cols), HEAD + T * len(rows) + FH), (24, 24, 24))
d = ImageDraw.Draw(S)
def wrap(text, f, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if d.textlength((cur + " " + w).strip(), font=f) > width and cur:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    return lines + [cur]
tiles = {}
for j, c in enumerate(cols):
    for k, ln in enumerate(wrap(c[0], F1, T - 16)):
        d.text((LEFT + j * T + 8, 6 + k * F1.size * 1.1), ln, fill=(255, 255, 255), font=F1)
    for i, r in enumerate(rows):
        p = f"{c[1]}/{r}_{c[2]}.png"
        if os.path.exists(p):
            im = Image.open(p).convert("RGB").resize((T, T), Image.LANCZOS)
            tiles[i, j] = np.asarray(im, float)
        else:
            im = Image.new("RGB", (T, T), (60, 60, 60))
            ImageDraw.Draw(im).text((T // 4, T // 2), "(no picture from here)" if c[2] == "ref" else "(not rendered)", fill=(150, 150, 150), font=F3)
        S.paste(im, (LEFT + j * T, HEAD + i * T))
for i, r in enumerate(rows):
    for k, ln in enumerate(wrap(r.replace("_", " ").replace("view", "reference view "), F2, LEFT - 12)):
        d.text((8, HEAD + i * T + T // 3 + k * F2.size * 1.15), ln, fill=(230, 230, 230), font=F2)
for j, c in enumerate(cols):
    vs = [x for x in c[3:] if x.startswith("vs=")]
    if not vs:
        continue
    k = int(vs[0][3:])
    for i, r in enumerate(rows):
        if (i, j) in tiles and (i, k) in tiles:
            A, B = tiles[i, j], tiles[i, k]
            bg = B[2, 2]
            m = np.abs(B - bg).sum(-1) > 24
            de = np.linalg.norm(sp.lab(sp._lin(A / 255.0)) - sp.lab(sp._lin(B / 255.0)), axis=-1)
            v = float(de[m].mean())
            print(f"{r:22s} {c[0][:40]:40s} vs {cols[k][0][:30]:30s} mean dE {v:5.2f}")
            d.text((LEFT + j * T + 8, HEAD + (i + 1) * T - F3.size - 8), f"dE to the true head {v:.1f}", fill=(255, 235, 120), font=F3)
for k, ln in enumerate(flines):
    d.text((12, HEAD + T * len(rows) + 10 + k * F3.size * 1.35), ln, fill=(235, 235, 235), font=F3)
S.save(out)
print("->", out, S.size)
