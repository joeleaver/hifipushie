"""sheet.py: workspace/human_renders/nd_tess_native.png (REFERENCE | tess_n1 | tess_a1; rows whole head front / three-quarter /
profile with hair, eyes, mouth and chin, neck and shoulders front + side, clay front; EEVEE) and nd_tess_figure.png (full
figure front / side, tess_n1 | tess_a1) from the tiles of tiles.py / necks.py. sheet.py <n1 model> <a1 model with hair> <a1 model>"""
import sys
from PIL import Image, ImageDraw, ImageFont
O = "/mnt/data/hifipushie/nativedefault/out"
HR = "/home/joe/dev/hifipushie/workspace/human_renders"
F = lambda s: ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", s)  # noqa: E731
n1, a1h, a1 = sys.argv[1:4]
title2 = sys.argv[4] if len(sys.argv) > 4 else ""
T = 600
ROWS = [("WHOLE HEAD, FRONT (hair)", "head_v0", "head_v0_ref"), ("THREE-QUARTER (hair)", "head_v1", "head_v1_ref"), ("PROFILE (hair)", "head_v2", "head_v2_ref"),
        ("EYES", "eyes_v0", "eyes_v0_ref"), ("MOUTH AND CHIN", "mouth_chin_v0", "mouth_chin_v0_ref"),
        ("NECK AND SHOULDERS, FRONT", "neck_front", "neck_ref_v0"), ("NECK AND SHOULDERS, SIDE", "neck_side", "neck_ref_v2"),
        ("CLAY, FRONT (no paint, no hair)", "clay_front", "head_v0_ref")]


def cell(p):
    try:
        return Image.open(p).convert("RGB").resize((T, T), Image.LANCZOS)
    except Exception:  # noqa: BLE001
        im = Image.new("RGB", (T, T), (60, 60, 60)); ImageDraw.Draw(im).text((20, 20), "missing: " + p.split("/")[-1], font=F(22), fill=(255, 200, 200)); return im


LAB = 64
HEAD = 250
W = Image.new("RGB", (3 * T + 40, HEAD + len(ROWS) * (T + LAB) + 20), (250, 250, 250))
d = ImageDraw.Draw(W)
d.text((20, 10), "TESS:  REFERENCE  |  tess_n1  |  tess_a1", font=F(60), fill=(0, 0, 0))
for j, lab in enumerate(("REFERENCE", f"{n1}  (GNM native)", f"{a1}  (accepted; hair th_T66)")):
    d.text((20 + j * T + 8, 196), lab, font=F(32), fill=(0, 0, 0))
for i, ln in enumerate(title2.split(";;")):
    d.text((20, 96 + i * 44), ln.strip(), font=F(30), fill=(0, 90, 30))
for i, (lab, key, ref) in enumerate(ROWS):
    y = HEAD + i * (T + LAB)
    d.text((24, y + 8), lab, font=F(40), fill=(0, 0, 0))
    for j, p in enumerate((f"{O}/{n1}/dressed/{ref}.png", f"{O}/{n1}/dressed/{key}.png", f"{O}/{a1h}/dressed/{key}.png")):
        W.paste(cell(p), (20 + j * T, y + LAB))
W.save(f"{HR}/nd_tess_native.png"); print(f"{HR}/nd_tess_native.png", W.size)
H = 1100
W = Image.new("RGB", (4 * 800 + 40, H + 170), (250, 250, 250))
d = ImageDraw.Draw(W)
d.text((20, 10), f"TESS, FULL FIGURE:   {n1} (GNM native head)   |   {a1} (accepted)", font=F(50), fill=(0, 0, 0))
for i, ln in enumerate(title2.split(";;")):
    d.text((20, 72 + i * 36), ln.strip(), font=F(28), fill=(0, 90, 30))
for j, (m, v) in enumerate(((n1, "front"), (n1, "side"), (a1h, "front"), (a1h, "side"))):
    try:
        im = Image.open(f"{O}/{m}/dressed/figure_{v}.png").convert("RGB")
        im = im.resize((int(im.width * H / im.height), H), Image.LANCZOS)
        x0 = 20 + j * 800 + (800 - min(im.width, 800)) // 2
        W.paste(im.crop(((im.width - min(im.width, 800)) // 2, 0, (im.width + min(im.width, 800)) // 2, H)), (x0, 150))
    except Exception as e:  # noqa: BLE001
        d.text((20 + j * 800, 300), f"missing {m} {v}", font=F(24), fill=(170, 30, 30))
    d.text((20 + j * 800 + 10, 150), f"{'tess_n1' if m == n1 else 'tess_a1'} {v}", font=F(36), fill=(255, 255, 0))
W.save(f"{HR}/nd_tess_figure.png"); print(f"{HR}/nd_tess_figure.png", W.size)
