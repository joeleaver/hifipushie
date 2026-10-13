"""mk_sheets8.py <best> [which=60,61,62] [old=th_V86]: round two's sheets into workspace/human_renders (LARGE labels):
  th_60_tess_colour_wisps.png   REFERENCE | NEW | th_V86; rows front, three-quarter, profile, back three-quarter
  th_61_closeups.png            her photo | ours, one area a pair: parting, both temples, forehead corner, the dome's
                                highlight, tail (same camera, same crop of the picture's own square)
  th_62_riffs.png               riffs8.py's looks (rf8_*.png) on two other heads, each with its words"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

best = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:] if "=" in a)
which = kw.get("which", "60,61,62").split(",")
old = kw.get("old", "th_V86")
OUT = os.environ.get("TOUT", "/mnt/data/hifipushie/tesshair7/out")
R = "/home/joe/dev/s0urc3/docs/img/tess_ref_full/"
DST = "/home/joe/dev/hifipushie/workspace/human_renders/"
REF = {"v0": "tess_head_front.png", "v1": "tess_head_three_quarter_left.png", "v2": "tess_head_profile_left.png",
       "backl": "tess_head_three_quarter_rear.png"}


def font(px):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", px)
    except OSError:
        return ImageFont.load_default()


def sq(f):
    im = Image.open(f).convert("RGB")
    w, h = im.size
    s = max(w, h)
    o = Image.new("RGB", (s, s), (205, 205, 208))
    o.paste(im, ((s - w) // 2, (s - h) // 2))
    return o


def cell(im, box, S):
    if im is None:
        return Image.new("RGB", (S, S), (190, 190, 190))
    s = im.size[0]
    return im.crop((int(box[0] * s), int(box[1] * s), int(box[2] * s), int(box[3] * s))).resize((S, S), Image.LANCZOS)


def tile(m, v):
    f = f"{OUT}/s_{m}_{v}.png"
    return Image.open(f).convert("RGB") if os.path.exists(f) else None


if "60" in which:
    S, HD, LW = 760, 110, 330
    B = (0.1, 0.0, 0.9, 0.8)
    rows = [("FRONT", "v0", B, B), ("THREE-QUARTER", "v1", B, B), ("PROFILE", "v2", B, B),
            ("BACK 3/4", "backl", (0.12, 0.08, 0.92, 0.88), (0.2, 0.12, 0.84, 0.76))]
    cols = ["REFERENCE", f"NEW  {best}", f"{old} (before)"]
    sheet = Image.new("RGB", (LW + 3 * S, HD + len(rows) * S), "white")
    dr = ImageDraw.Draw(sheet)
    for k, c in enumerate(cols):
        dr.text((LW + k * S + 20, 20), c, fill="black", font=font(62))
    for r, (lab, v, rb, ob) in enumerate(rows):
        dr.text((12, HD + r * S + 30), lab, fill="black", font=font(34))
        for k, (im, box) in enumerate([(sq(R + REF[v]), rb), (tile(best, v), ob), (tile(old, v), ob)]):
            sheet.paste(cell(im, box, S), (LW + k * S, HD + r * S))
    sheet.save(DST + "th_60_tess_colour_wisps.png")
    print("saved", DST + "th_60_tess_colour_wisps.png", sheet.size)

if "61" in which:
    S, HD = 620, 90
    areas = [("PARTING", "v0", (0.35, 0.03, 0.61, 0.29)), ("HER RIGHT TEMPLE", "v0", (0.22, 0.12, 0.44, 0.34)),
             ("HER LEFT TEMPLE + EAR", "v1", (0.50, 0.14, 0.74, 0.38)), ("FOREHEAD CORNER", "v1", (0.33, 0.06, 0.57, 0.30)),
             ("THE DOME'S HIGHLIGHT", "v2", (0.42, 0.03, 0.74, 0.35)), ("TAIL", "v2", (0.62, 0.22, 0.94, 0.54))]
    nc = 2
    nr = (len(areas) + 1) // 2
    sheet = Image.new("RGB", (nc * (2 * S + 30), nr * (S + HD)), "white")
    dr = ImageDraw.Draw(sheet)
    for i, (lab, v, box) in enumerate(areas):
        x0, y0 = (i % nc) * (2 * S + 30), (i // nc) * (S + HD)
        dr.text((x0 + 12, y0 + 14), f"{lab}:  hers | {best}", fill="black", font=font(46))
        sheet.paste(cell(sq(R + REF[v]), box, S), (x0, y0 + HD))
        sheet.paste(cell(tile(best, v), box, S), (x0 + S, y0 + HD))
    sheet.save(DST + "th_61_closeups.png")
    print("saved", DST + "th_61_closeups.png", sheet.size)

if "62" in which:
    names = [n for n in ("a1", "a2", "a3", "a4", "a5", "a6", "b1", "b2", "b3", "b4") if os.path.exists(f"{OUT}/rf8_{n}.png")]
    Wd, HD = 1500, 120
    cells = {}
    for n in names:
        im = Image.open(f"{OUT}/rf8_{n}.png").convert("RGB")
        im = im.crop((0, 0, int(im.width * 0.75), im.height))  # (without look_hair's thumbnail strip)
        im = im.resize((Wd, int(im.height * Wd / im.width)), Image.LANCZOS)
        t = open(f"{OUT}/rf8_{n}.txt").read().split("\n")
        c = Image.new("RGB", (Wd, HD + im.height), "white")
        d = ImageDraw.Draw(c)
        d.text((14, 8), ("WOMAN  " if n[0] == "a" else "MAN  ") + t[0], fill="black", font=font(44))
        d.text((14, 70), ("style " + t[1] + "   look " + t[2])[:150], fill=(60, 60, 60), font=font(22))
        c.paste(im, (0, HD))
        cells[n] = c
    if cells:
        ch = max(c.height for c in cells.values())
        ca = [cells[n] for n in names if n[0] == "a"]
        cb = [cells[n] for n in names if n[0] == "b"]
        sheet = Image.new("RGB", (2 * Wd, max(len(ca), len(cb)) * ch), "white")
        for col, lst in enumerate((ca, cb)):
            for r, c in enumerate(lst):
                sheet.paste(c, (col * Wd, r * ch))
        sheet.save(DST + "th_62_riffs.png")
        print("saved", DST + "th_62_riffs.png", sheet.size)
