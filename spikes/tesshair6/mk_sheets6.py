"""mk_sheets6.py [best=th_T66]: round six's sheets into workspace/human_renders (tesshair3's sheet3.py layouts):
th_40_tess_loose_front_soft_tail.png  REFERENCE | new best EEVEE | new best Cycles | th_T56 EEVEE | th_T56 Cycles |
                                      th_T48 EEVEE; six rows as th_30
th_41_closeups.png                    the SAME PIXELS of the reference and ours: front hairline (front, 3/4), temple
                                      (3/4, profile), the tail from the side (profile) and from behind
th_42_hairline_other_humans.png       the hairline BEFORE (ear guessed from the brow) | AFTER (ear found) on seven
                                      other humans, + the no-Blender plot of every head's ear and both lines
th_43_tied_riffs.png                  the six riffs: round five (th_S*) over now (th_V*)
th_44_upstyle_temple.png              the temple edge of the high ponytail / top knot close up: round five | now"""
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

best = dict(a.split("=") for a in sys.argv[1:]).get("best", "th_T66")
O = "/mnt/data/hifipushie/tesshair6/out/"
O5 = "/mnt/data/hifipushie/tesshair5/out/"
O4 = "/mnt/data/hifipushie/tesshair4/out/"
R = "/home/joe/dev/s0urc3/docs/img/tess_ref_full/"
HR = "/home/joe/dev/hifipushie/workspace/human_renders/"
here = os.path.dirname(os.path.abspath(__file__))
S3 = os.path.join(os.path.dirname(here), "tesshair3", "sheet3.py")
T = O + "_crops/"
os.makedirs(T, exist_ok=True)


def ex(*ps):
    for p in ps:
        if os.path.exists(p):
            return p
    return None


def build(layout, out):
    f = O + "_layout.json"
    json.dump(layout, open(f, "w"))
    subprocess.run([sys.executable, S3, f, out], check=True)
    print("sheet", out)


# ---- (a)
views = [("front\n(fitted camera)", "v0", R + "tess_head_front.png"),
         ("three-quarter\n(fitted camera)", "v1", R + "tess_head_three_quarter_left.png"),
         ("profile\n(fitted camera)", "v2", R + "tess_head_profile_left.png"),
         ("back, from her left\n(reference: unfitted picture)", "backl", R + "tess_head_hair_as_worn_back.png"),
         ("back, from her right\n(UNSEEN: no reference)", "backq", None),
         ("right profile\n(UNSEEN: no reference)", "right", None)]
rows = [{"label": lab, "tiles": [ref, ex(f"{O}s_{best}_{v}.png"), ex(f"{O}s_{best}_{v}_cyc.png"),
                                 ex(f"{O5}s_th_T56_{v}.png"), ex(f"{O5}s_th_T56_{v}_cyc.png"), ex(f"{O4}s_th_T48_{v}.png")]}
        for lab, v, ref in views]
build({"title": f"Tess round six: the ear found (no hairline patch), a loose front, the tail as soft hair ({best})",
       "tile": 640, "label_w": 360,
       "cols": ["REFERENCE", f"NEW BEST {best} (EEVEE)", f"NEW BEST {best} (Cycles)", "th_T56 (round five, EEVEE)",
                "th_T56 (round five, Cycles)", "th_T48 (round four, EEVEE)"], "rows": rows},
      HR + "th_40_tess_loose_front_soft_tail.png")


# ---- (b) close-ups at the same pixels (a fitted tile = the whole reference picture squared, 1152 x 1536 -> 1536 wide)
def crop(src, box, name, ref=False):
    if not src or not os.path.exists(src):
        return None
    im = Image.open(src).convert("RGB")
    if ref:
        b = box
    else:
        k = im.size[0] / 1536.0
        b = tuple(int(round(v * k)) for v in (box[0] + 192, box[1], box[2] + 192, box[3]))
    im.crop(b).resize((760, 760), Image.LANCZOS).save(T + name)
    return T + name


CU = [("FRONT HAIRLINE + PART\nfront", "v0", "tess_head_front.png", (370, 170, 790, 590)),
      ("FRONT, WHOLE\n(loosened locks, wisps)", "v0", "tess_head_front.png", (130, 130, 930, 930)),
      ("FRONT HAIRLINE\nthree-quarter", "v1", "tess_head_three_quarter_left.png", (300, 170, 720, 590)),
      ("TEMPLE / SIDEBURN\nthree-quarter", "v1", "tess_head_three_quarter_left.png", (480, 300, 900, 720)),
      ("TEMPLE / SIDEBURN\nprofile", "v2", "tess_head_profile_left.png", (330, 250, 750, 670)),
      ("THE TAIL\nfrom the side (profile)", "v2", "tess_head_profile_left.png", (600, 420, 1152, 972))]
rows = []
for i, (lab, v, rf, box) in enumerate(CU):
    rows.append({"label": lab, "tiles": [crop(R + rf, box, f"ref_{i}.png", ref=True),
                                         crop(f"{O}s_{best}_{v}.png", box, f"best_{i}.png"),
                                         crop(f"{O}s_{best}_{v}_cyc.png", box, f"cyc_{i}.png"),
                                         crop(f"{O5}s_th_T56_{v}.png", box, f"t56_{i}.png"),
                                         crop(f"{O4}s_th_T48_{v}.png", box, f"t48_{i}.png")]})
bl = []
for p, nm in ((f"{O}s_{best}_backl.png", "best_b.png"), (f"{O}s_{best}_backl_cyc.png", "cyc_b.png"),
              (f"{O5}s_th_T56_backl.png", "t56_b.png"), (f"{O4}s_th_T48_backl.png", "t48_b.png")):
    if os.path.exists(p):
        im = Image.open(p).convert("RGB")
        n = im.size[0]
        im.crop((int(0.17 * n), int(0.2 * n), int(0.85 * n), int(0.88 * n))).resize((760, 760), Image.LANCZOS).save(T + nm)
        bl.append(T + nm)
    else:
        bl.append(None)
Image.open(R + "tess_head_hair_as_worn_back.png").convert("RGB").crop((200, 250, 1100, 1150)).resize((760, 760), Image.LANCZOS).save(T + "ref_b.png")
rows.append({"label": "THE TAIL\nfrom behind (her left; unfitted)", "tiles": [T + "ref_b.png"] + bl})
build({"title": f"Close-ups at the same pixels, reference beside ours ({best} | th_T56 round five | th_T48 round four)",
       "tile": 760, "label_w": 360,
       "cols": ["REFERENCE", f"NEW {best} (EEVEE)", f"NEW {best} (Cycles)", "th_T56 (round five, EEVEE)", "th_T48 (round four, EEVEE)"],
       "rows": rows}, HR + "th_41_closeups.png")

# ---- (c) the hairline on other humans: before | after (look_hair sheets: side, three_quarter, front tiles in a row)
E = [("E3", "hu_s_wavy\n(MakeHuman body, GNM head)"), ("E4", "hu_s_child\n(MakeHuman, a child)"),
     ("E0", "hu_s_tousled\n(MakeHuman)"), ("E5", "hc_golfer\n(MakeHuman, stylised; groom had ear -0.004)"),
     ("E7", "dg_hair_long\n(MakeHuman; groom had ear -0.03)"), ("E6", "rs_real_S3\n(one mesh, GNM)"),
     ("E8", "lk_mem\n(one mesh, GNM)")]
VERDICT = json.load(open(O + "verdicts.json")) if os.path.exists(O + "verdicts.json") else {}


def tiles(m, n=3):
    p = f"{O}E_{m}.png"
    if not os.path.exists(p):
        return [None] * n
    im = Image.open(p).convert("RGB")
    w = (im.size[1] - 22)
    out = []
    for i in range(n):
        f = f"{T}E_{m}_{i}.png"
        im.crop((i * w, 22, (i + 1) * w, 22 + w)).save(f)
        out.append(f)
    return out


rows = []
for e, lab in E:
    b, a = tiles(f"th_{e}b"), tiles(f"th_{e}")
    v = VERDICT.get(e, "")
    rows.append({"label": f"th_{e} = {lab}" + (f"\n{v}" if v else ""), "tiles": [b[0], a[0], b[1], a[1]]})
build({"title": "Hairline on other humans: BEFORE (ear guessed from the brow) | AFTER (ear found). Copies th_E*",
       "tile": 600, "label_w": 620,
       "cols": ["BEFORE side", "NEW AFTER side", "BEFORE three-quarter", "NEW AFTER three-quarter"], "rows": rows},
      HR + "th_42_hairline_other_humans.png")
pl = ex(O + "hl_all.png")
if pl:  # the no-Blender plot under it
    a, b = Image.open(HR + "th_42_hairline_other_humans.png"), Image.open(pl).convert("RGB")
    k = a.size[0] / b.size[0]
    b = b.resize((a.size[0], int(b.size[1] * k)), Image.LANCZOS)
    s = Image.new("RGB", (a.size[0], a.size[1] + b.size[1] + 110), "white")
    s.paste(a, (0, 0))
    d = ImageDraw.Draw(s)
    d.text((24, a.size[1] + 24), "Every head from its left, drawn from the scalp rays: the ear FOUND (cyan), the OLD line (red), the NEW line (green)",
           fill="black", font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 44))
    s.paste(b, (0, a.size[1] + 110))
    s.save(HR + "th_42_hairline_other_humans.png")

# ---- (d) riffs: round five over now
NAMES = {"1": "HIGH TIGHT PONYTAIL", "2": "LOW CENTRE PONYTAIL", "3": "LOW SIDE, SLEEK", "4": "HALF UP",
         "5": "TOP KNOT (bun)", "6": "LOW PLAIT"}
vn = ["front", "frontq", "left", "backl", "back", "right"]
rows = []
for k, nm in NAMES.items():
    rows.append({"label": f"th_S{k} ROUND FIVE\n{nm}\n(with the hairline patch)", "tiles": [ex(f"{O5}iso_th_S{k}_a_{v}.png") for v in vn]})
    rows.append({"label": f"th_V{k} NOW\nthe same style call, NO patch", "tiles": [ex(f"{O}iso_th_V{k}_a_{v}.png") for v in vn]})
build({"title": "The six riffs re-grown with round six's code (same style words; round five above, now below)",
       "tile": 440, "label_w": 420, "cols": ["front", "front 3/4", "left", "back left", "back", "right"], "rows": rows},
      HR + "th_43_tied_riffs.png")

# ---- (e) the up-styles' temple edge, close up
rows = []
for k, nm in (("1", "HIGH TIGHT PONYTAIL"), ("5", "TOP KNOT")):
    ts = []
    for src, tag in ((O5, f"S{k}"), (O, f"V{k}")):
        for v, box in (("frontq", (130, 100, 830, 800)), ("left", (130, 130, 830, 830))):
            p = f"{src}iso_th_{tag}_c_{v}.png"
            if os.path.exists(p):
                Image.open(p).convert("RGB").crop(box).save(T + f"u_{tag}_{v}.png")
                ts.append(T + f"u_{tag}_{v}.png")
            else:
                ts.append(None)
    rows.append({"label": nm, "tiles": ts})
build({"title": "Up-styles, the temple edge close up (EEVEE): round five | now",
       "tile": 700, "label_w": 380,
       "cols": ["ROUND FIVE three-quarter", "ROUND FIVE profile", "NEW three-quarter", "NEW profile"], "rows": rows},
      HR + "th_44_upstyle_temple.png")
