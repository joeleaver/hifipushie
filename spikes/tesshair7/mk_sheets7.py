"""mk_sheets7.py <best model> [which=50,51,52]: the round's sheets into workspace/human_renders (LARGE labels, the result
directly beside the reference):
  th_50_tess_volume_colour.png  REFERENCE | NEW | th_T66; rows front, three-quarter, profile, back three-quarter, crown
  th_51_part_arcs.png           flowlines.py's panels (three-quarter, front): strand paths from the parting, hers | ours
  th_52_riffs.png               riffs7.py's looks on two other heads, each with its words"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

best = sys.argv[1]
which = next((a[6:] for a in sys.argv[2:] if a.startswith("which=")), "50,51,52").split(",")
OUT = os.environ.get("TOUT", "/mnt/data/hifipushie/tesshair7/out")
OLD = "/mnt/data/hifipushie/tesshair6/out"
R = "/home/joe/dev/s0urc3/docs/img/tess_ref_full/"
DST = "/home/joe/dev/hifipushie/workspace/human_renders/"


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
        o = Image.new("RGB", (S, S), (190, 190, 190))
        ImageDraw.Draw(o).text((S // 5, S // 2), "no picture", fill=(90, 90, 90), font=font(S // 14))
        return o
    s = im.size[0]
    return im.crop((int(box[0] * s), int(box[1] * s), int(box[2] * s), int(box[3] * s))).resize((S, S), Image.LANCZOS)


def tile(m, v):
    for d in (OUT, OLD):
        f = f"{d}/s_{m}_{v}.png"
        if os.path.exists(f):
            return Image.open(f).convert("RGB")
    return None


if "50" in which:
    S, HD, LW = 760, 110, 330
    B = (0.1, 0.0, 0.9, 0.8)
    rows = [("FRONT", "v0", "tess_head_front.png", B, B), ("THREE-QUARTER", "v1", "tess_head_three_quarter_left.png", B, B),
            ("PROFILE", "v2", "tess_head_profile_left.png", B, B),
            ("BACK 3/4", "backl", "tess_head_three_quarter_rear.png", (0.12, 0.08, 0.92, 0.88), (0.2, 0.12, 0.84, 0.76)),
            ("CROWN\nfrom above", "crown", None, None, (0.22, 0.2, 0.78, 0.76))]
    cols = ["REFERENCE", f"NEW  {best}", "th_T66 (before)"]
    sheet = Image.new("RGB", (LW + 3 * S, HD + len(rows) * S), "white")
    dr = ImageDraw.Draw(sheet)
    for k, c in enumerate(cols):
        dr.text((LW + k * S + 20, 20), c, fill="black", font=font(62))
    for r, (lab, v, rf, rb, ob) in enumerate(rows):
        dr.text((12, HD + r * S + 30), lab, fill="black", font=font(34))
        ims = [(sq(R + rf) if rf else None, rb), (tile(best, v), ob), (tile("th_T66", v), ob)]
        for k, (im, box) in enumerate(ims):
            sheet.paste(cell(im, box, S), (LW + k * S, HD + r * S))
    sheet.save(DST + "th_50_tess_volume_colour.png")
    print("saved", DST + "th_50_tess_volume_colour.png", sheet.size)

if "51" in which:
    ps = [Image.open(f"{OUT}/fl_v{i}.png").convert("RGB") for i in (1, 0) if os.path.exists(f"{OUT}/fl_v{i}.png")]
    Wd = 2400
    ps = [p.resize((Wd, int(p.height * Wd / p.width)), Image.LANCZOS) for p in ps]
    HD = 150
    sheet = Image.new("RGB", (Wd, HD + sum(p.height for p in ps)), "white")
    dr = ImageDraw.Draw(sheet)
    dr.text((20, 12), "STRAND PATHS FROM THE PARTING (Joe's markup, by measure)", fill="black", font=font(60))
    dr.text((20, 88), "red = stream lines of the image's own strand direction, same seeds on the head in every panel;  "
            "cyan = our lock spines rooted on the part", fill="black", font=font(34))
    y = HD
    for p in ps:
        sheet.paste(p, (0, y))
        y += p.height
    sheet.save(DST + "th_51_part_arcs.png")
    print("saved", DST + "th_51_part_arcs.png", sheet.size)

if "52" in which:
    names = [n for n in ("a1", "a2", "a3", "a4", "a5", "b1", "b2", "b3", "b4") if os.path.exists(f"{OUT}/rf_{n}.png")]
    Wd, HD = 1500, 120
    cells = []
    for n in names:
        im = Image.open(f"{OUT}/rf_{n}.png").convert("RGB")
        im = im.resize((Wd, int(im.height * Wd / im.width)), Image.LANCZOS)
        t = open(f"{OUT}/rf_{n}.txt").read().split("\n")
        c = Image.new("RGB", (Wd, HD + im.height), "white")
        d = ImageDraw.Draw(c)
        d.text((14, 8), ("WOMAN  " if n[0] == "a" else "MAN  ") + t[0], fill="black", font=font(46))
        d.text((14, 70), ("style " + t[1] + "   look " + t[2])[:150], fill=(60, 60, 60), font=font(22))
        c.paste(im, (0, HD))
        cells.append(c)
    if cells:
        nc = 2
        nr = (len(cells) + 1) // 2
        ch = max(c.height for c in cells)
        sheet = Image.new("RGB", (nc * Wd, nr * ch), "white")
        # (the two heads side by side: woman left, man right)
        ca = [c for c, n in zip(cells, names) if n[0] == "a"]
        cb = [c for c, n in zip(cells, names) if n[0] == "b"]
        sheet = Image.new("RGB", (2 * Wd, max(len(ca), len(cb)) * ch), "white")
        for col, lst in enumerate((ca, cb)):
            for r, c in enumerate(lst):
                sheet.paste(c, (col * Wd, r * ch))
        sheet.save(DST + "th_52_riffs.png")
        print("saved", DST + "th_52_riffs.png", sheet.size)
