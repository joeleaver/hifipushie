"""gb1.py: sheet gb_01: Tess's photo eye | gk_07's result | the fixed result / fixed + crease makeup 0.4 | 0.8 | numbers.
Every tile is the SAME pixel crop of a shot through the photo's fitted camera (shot.py): one mm/px (0.0792 mm per sheet
px), the same landmark at the same place. The reads printed on the tiles are rd.py's (out/rd.json)."""
import json

from PIL import Image, ImageDraw

G = "/mnt/data/hifipushie/gnmbrow/out/"
rd = json.load(open(G + "rd.json"))
MM = 0.2377 / 3
CROP = (850, 540, 1510, 1040)
W, H = CROP[2] - CROP[0], CROP[3] - CROP[1]
HEAD = 78
tiles = [("photo", "Tess photo (through its fitted camera)"),
         ("gk07", "gk_07 result (s376 at photo height), as it was dressed"),
         ("fx", "FIXED: iris 10.7 mm + eye step, brows from the picture"),
         ("mk4", "FIXED + crease makeup 0.4"),
         ("mk8", "FIXED + crease makeup 0.8")]
S = Image.new("RGB", (3 * W, 2 * (H + HEAD)), (255, 255, 255))
d = ImageDraw.Draw(S)
for i, (tag, lab) in enumerate(tiles):
    x, y = (i % 3) * W, (i // 3) * (H + HEAD)
    im = Image.open(f"{G}s_{tag}.png").convert("RGB").crop(CROP)
    S.paste(im, (x, y + HEAD))
    r = rd[tag]
    d.text((x + 8, y + 4), lab, fill=(0, 0, 0), font_size=21)
    d.text((x + 8, y + 30), f"brow lower edge over the lid margin: {r['gap'][0]:.1f} / {r['gap'][1]:.1f} / {r['gap'][2]:.1f} mm "
                            f"(inner / pupil / outer)", fill=(0, 0, 0), font_size=17)
    d.text((x + 8, y + 52), f"= {r['gap_iris'][0]:.2f} / {r['gap_iris'][1]:.2f} / {r['gap_iris'][2]:.2f} iris diameters; iris "
                            f"{r['iris_mm']:.1f} mm {r['iris_hex']}; opening {r['open']:.1f} mm"
                            + ("" if tag == "photo" else f"; brow edge vs photo {r['band_low_rms']:.1f} mm rms"),
           fill=(0, 0, 0), font_size=17)
    # a 10 mm bar
    x0, y0 = x + 16, y + HEAD + H - 22
    d.line([(x0, y0), (x0 + 10 / MM, y0)], fill=(255, 255, 255), width=5)
    d.line([(x0, y0), (x0 + 10 / MM, y0)], fill=(0, 0, 0), width=2)
    d.text((x0 + 10 / MM + 6, y0 - 10), "10 mm", fill=(0, 0, 0), font_size=16)
x, y = 2 * W + 14, (H + HEAD) + 10
p, a, b = rd["photo"], rd["gk07"], rd["fx"]
lines = [
    "ALL TILES: one camera (the photo's fitted one), one crop,",
    "0.079 mm / px. mm are AT THE MODEL (her pupil distance 53 mm).",
    "",
    "Why the brow sat on the crease in gk_07 (pupil column):",
    f"  photo {p['gap'][1]:.1f} mm, gk_07 {a['gap'][1]:.1f} mm  ->  {p['gap'][1] - a['gap'][1]:.1f} mm short",
    "  - brow HAIR drawn low: 3.3 mm, hand offsets carried over",
    "    from an older head (skin.hair.brows drop 4 mm ...);",
    "    the bare landmark placement adds ~0.2 (tail: ~3 mm)",
    "  - upper lid margin ~1.2 mm higher than hers (detector);",
    "    ~0.35 of it from the iris drawn 12.7 mm vs 10.7 hers",
    "    (lids are matched in iris radii)",
    "  - model brow landmarks: on her brow (0 mm; tail 1.5 low)",
    "  - gk_07's eye step dragging the brow: 0.1 mm (gd_T30: 1.4)",
    "  + gk_07's SHEET showed the photo 17 % magnified against",
    "    the renders (11.7 mm iris assumed): +1.9 mm apparent",
    "",
    f"Fixed: {b['gap'][0]:.1f} / {b['gap'][1]:.1f} / {b['gap'][2]:.1f} mm vs photo "
    f"{p['gap'][0]:.1f} / {p['gap'][1]:.1f} / {p['gap'][2]:.1f}",
    f"  brow edge in the picture {b['band_low_rms']:.1f} mm rms off (was {a['band_low_rms']:.1f})",
    "  left: ~1 mm: the detector still reads our upper lid",
    "  ~0.9 mm higher than hers (iris centres agree to 0.1 mm)",
    "Crease: s376 make at her line (4.3 mm), section rms 0.18 mm",
]
for k, t in enumerate(lines):
    d.text((x, y + k * 25), t, fill=(0, 0, 0), font_size=18)
out = "/home/joe/dev/hifipushie/workspace/human_renders/gb_01_brow_iris_fixed_matched_framing.png"
S.save(out)
print(out, S.size)
