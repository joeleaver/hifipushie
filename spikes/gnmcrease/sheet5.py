"""sheet5.py: gk_05: Tess's photo next to #376, #540, gd_T30 and the shape results, all dressed in the same eye frame,
the crease-makeup variants, Garrett's row, and the section plots under them."""
from PIL import Image, ImageDraw

G = "/mnt/data/hifipushie/gnmcrease/out/"
W, H = 736, 512
box = (0.52, 0.30, 0.98, 0.62)
gbox = (0.555, 0.305, 0.775, 0.458)     # Garrett: his face frame (his eyes fall outside the 84 mm eye frame)


def cr(p, b=box):
    im = Image.open(p).convert("RGB").resize((1600, 1600))
    return im.crop(tuple(int(v * 1600) for v in b)).resize((W, H), Image.LANCZOS)


tiles = [("photo_tess.png", "Tess photo", box),
         ("d_s376_dressed.png", "#376 (sampled head; Joe: right)", box),
         ("d_s540_dressed.png", "#540 (sampled head; Joe: right)", box),
         ("d_t30_dressed.png", "gd_T30 (old eye step, deep 1.64 mm valley)", box),
         ("d_ssT376_dressed.png", "Tess: shape -> #376 (|dc| 5.3 from T30)", box),
         ("d_ssT540_dressed.png", "Tess: shape -> #540 (|dc| 5.8 from T30)", box),
         ("d_evT12_dressed.png", "Tess: NEW eye step, 'fold' template (|dc| 4.3)", box),
         ("d_mkT376_dressed.png", "shape -> #376 + crease makeup 0.3", box),
         ("d_mkT540_dressed.png", "shape -> #540 + crease makeup 0.3", box),
         ("d_g17_face.png", "Garrett b3_G17 (as is)", gbox),
         ("d_ssG376_face.png", "Garrett: shape -> #376 (|dc| 4.8)", gbox),
         ("d_ssG540_face.png", "Garrett: shape -> #540 (|dc| 3.0)", gbox)]
ncol = 3
rows = (len(tiles) + ncol - 1) // ncol
sec = Image.open(G + "sec_b.png").convert("RGB")
sec = sec.resize((ncol * W, int(sec.height * ncol * W / sec.width)), Image.LANCZOS)
S = Image.new("RGB", (ncol * W, rows * (H + 34) + sec.height + 40), (255, 255, 255))
d = ImageDraw.Draw(S)
for i, (f, lab, b) in enumerate(tiles):
    x, y = (i % ncol) * W, (i // ncol) * (H + 34)
    S.paste(cr(G + f, b), (x, y + 34))
    d.text((x + 8, y + 6), lab, fill=(0, 0, 0), font_size=22)
y = rows * (H + 34) + 6
d.text((8, y), "upper-lid sections (Tess's results: identity + eye pairs read on gd_T12's body) and the fold line across the lid",
       fill=(0, 0, 0), font_size=22)
S.paste(sec, (0, y + 34))
S.save("/home/joe/dev/hifipushie/workspace/human_renders/gk_05_crease_shape_dressed.png")
print("ok", S.size)
