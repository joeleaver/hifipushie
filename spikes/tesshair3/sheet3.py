"""sheet3.py <layout.json> <out.png>: a grid of tiles with LARGE labels (Joe could not read th_03's small ones).
layout = {"title": str, "tile": px, "cols": [label, ..], "rows": [{"label": str, "tiles": [path | null, ..]}],
"label_w": px}. Column labels on top, row labels down the left; tiles are squared (padded) and scaled."""
import json, sys
from PIL import Image, ImageDraw, ImageFont

L = json.load(open(sys.argv[1]))
N = int(L.get("tile", 640))
LW = int(L.get("label_w", 330))
F = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
ft, fc, fr = ImageFont.truetype(F, 54), ImageFont.truetype(F, 40), ImageFont.truetype(F, 38)
TH, CH = 90, 120
cols, rows = L["cols"], L["rows"]
W, H = LW + N * len(cols), TH + CH + N * len(rows)
S = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(S)
d.text((24, 14), L.get("title", ""), fill="black", font=ft)


def wrap(txt, font, width):
    out = []
    for para in txt.split("\n"):
        cur = ""
        for w in para.split(" "):
            t = (cur + " " + w).strip()
            if d.textlength(t, font=font) > width and cur:
                out.append(cur)
                cur = w
            else:
                cur = t
        out.append(cur)
    return out


for j, c in enumerate(cols):
    for i, ln in enumerate(wrap(c, fc, N - 20)[:2]):
        d.text((LW + j * N + 12, TH + 6 + i * 50), ln, fill=(160, 0, 0) if c.startswith("NEW") else "black", font=fc)
for i, r in enumerate(rows):
    y = TH + CH + i * N
    for k, ln in enumerate(wrap(r["label"], fr, LW - 30)):
        d.text((16, y + 20 + k * 48), ln, fill="black", font=fr)
    for j, p in enumerate(r["tiles"]):
        if not p:
            d.rectangle([LW + j * N, y, LW + (j + 1) * N - 1, y + N - 1], fill=(235, 235, 235))
            d.text((LW + j * N + 30, y + N // 2 - 20), "(no picture)", fill=(120, 120, 120), font=fr)
            continue
        im = Image.open(p).convert("RGB")
        m = max(im.size)
        sq = Image.new("RGB", (m, m), (205, 205, 205))
        sq.paste(im, ((m - im.size[0]) // 2, (m - im.size[1]) // 2))
        S.paste(sq.resize((N, N), Image.LANCZOS), (LW + j * N, y))
    d.line([0, y, W, y], fill=(120, 120, 120), width=2)
S.save(sys.argv[2])
print(sys.argv[2], S.size)
