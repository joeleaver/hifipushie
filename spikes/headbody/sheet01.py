"""sheet01.py: workspace/human_renders/hb_01_scale.png from the look tiles (out/L_<model>_<view>.png) + attach_report."""
import sys
from PIL import Image, ImageDraw, ImageFont
from hifipushie import onemesh, store

OUT = "/mnt/data/hifipushie/headbody/out"
F = lambda s: ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", s)  # noqa: E731
rows = [("TESS", "nt_N06", "hb_tess"), ("GARRETT", "ng_N05", "hb_garrett")]
T = 760
W = Image.new("RGB", (4 * T + 40, 2 * (T + 190) + 90), (250, 250, 250))
d = ImageDraw.Draw(W)
d.text((20, 14), "CURRENT (head at the body's scale)", font=F(40), fill=(150, 30, 30))
d.text((20 + 2 * T + 20, 14), "HEAD AT GNM'S SIZE, BODY FITTED", font=F(40), fill=(20, 110, 40))
for r, (who, cur, new) in enumerate(rows):
    y0 = 80 + r * (T + 190)
    for c, m in enumerate((cur, new)):
        rep = onemesh.attach_report(store.load(m)["base"])
        x0 = 10 + c * (2 * T + 20)
        for v, view in enumerate(("front", "side")):
            im = Image.open(f"{OUT}/L_{m}_{view}.png").convert("RGB")
            im = im.resize((T, int(T * im.height / im.width)))
            W.paste(im.crop((0, 0, T, T)), (x0 + v * T, y0 + 150))
        col = (150, 30, 30) if c == 0 else (20, 110, 40)
        d.text((x0 + 10, y0), f"{who}  ({m})", font=F(34), fill=(20, 20, 20))
        d.text((x0 + 10, y0 + 44), f"{rep['heads_tall']:.1f} HEADS TALL   stature {rep['stature']:.3f} m   head {rep['head_height'] * 1000:.0f} mm",
               font=F(38), fill=col)
        d.text((x0 + 10, y0 + 94), f"head = {rep['size']:.2f} x GNM   eyes {rep['eyes_apart'] * 1000:.0f} mm apart   eyeball r {rep['eyeball_r'] * 1000:.1f} mm   "
               f"neck {rep['neck']['head'] * 1000:.0f} mm", font=F(26), fill=(40, 40, 40))
W.save(sys.argv[1] if len(sys.argv) > 1 else "/home/joe/dev/hifipushie/workspace/human_renders/hb_01_scale.png")
print("saved")
