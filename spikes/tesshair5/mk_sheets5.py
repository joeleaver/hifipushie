"""mk_sheets5.py [best=th_T56]: round five's sheets into workspace/human_renders (tesshair3's sheet3.py layouts):
th_30_tess_soft_hairline.png   REFERENCE | new best EEVEE | new best CYCLES (calibrated look, hair bounces) | th_T48
                               EEVEE | th_T48 Cycles (round four's tile); rows front / three-quarter / profile (fitted
                               cameras), back from her left, back from her right, right profile (unseen)
th_31_closeups.png             the SAME PIXELS of the reference and ours: the front hairline + part (front, three-
                               quarter), the temple / sideburn (three-quarter, profile), the tail from behind
th_32_tied_riffs.png           the six riff styles: round four's render (th_Q*) over the same style call now (th_S*)
th_33_hairline_dial.png        the new style word: hairline 0 / 0.5 / 1 on Tess's style (close-ups, unfitted)"""
import json
import os
import subprocess
import sys

from PIL import Image

best = dict(a.split("=") for a in sys.argv[1:]).get("best", "th_T56")
O = "/mnt/data/hifipushie/tesshair5/out/"
O4 = "/mnt/data/hifipushie/tesshair4/out/"
R = "/home/joe/dev/s0urc3/docs/img/tess_ref_full/"
HR = "/home/joe/dev/hifipushie/workspace/human_renders/"
here = os.path.dirname(os.path.abspath(__file__))
S3 = os.path.join(os.path.dirname(here), "tesshair3", "sheet3.py")


def ex(*ps):
    for p in ps:
        if os.path.exists(p):
            return p
    return None


def build(layout, out):
    f = O + "_layout.json"
    json.dump(layout, open(f, "w"))
    subprocess.run([sys.executable, S3, f, out], check=True)


# ---- (a)
views = [("front\n(fitted camera)", "v0", R + "tess_head_front.png"),
         ("three-quarter\n(fitted camera)", "v1", R + "tess_head_three_quarter_left.png"),
         ("profile\n(fitted camera)", "v2", R + "tess_head_profile_left.png"),
         ("back, from her left\n(reference: unfitted picture)", "backl", R + "tess_head_hair_as_worn_back.png"),
         ("back, from her right\n(UNSEEN: no reference)", "backq", None),
         ("right profile\n(UNSEEN: no reference)", "right", None)]
rows = [{"label": lab, "tiles": [ref, ex(f"{O}s_{best}_{v}.png"), ex(f"{O}s_{best}_{v}_cyc.png"),
                                 ex(f"{O4}s_th_T48_{v}.png"), ex(f"{O4}s_th_T48_{v}_cyc.png")]}
        for lab, v, ref in views]
build({"title": f"Tess round five: a soft hairline, the temple as hair, a tousled tail fitted by measure, Cycles calibrated ({best})",
       "tile": 640, "label_w": 360,
       "cols": ["REFERENCE", f"NEW BEST {best} (EEVEE)", f"NEW BEST {best} (Cycles, calibrated)", "th_T48 (round four, EEVEE)",
                "th_T48 (round four's Cycles)"], "rows": rows},
      HR + "th_30_tess_soft_hairline.png")

# ---- (b) close-ups: a fitted tile is the whole reference picture squared (1152 x 1536 padded to 1536 wide), so a
# box in REFERENCE pixels is the same pixels in ours
T = O + "_crops/"
os.makedirs(T, exist_ok=True)


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
      ("FRONT HAIRLINE\nthree-quarter", "v1", "tess_head_three_quarter_left.png", (300, 170, 720, 590)),
      ("TEMPLE / SIDEBURN\nthree-quarter", "v1", "tess_head_three_quarter_left.png", (480, 300, 900, 720)),
      ("TEMPLE / SIDEBURN\nprofile", "v2", "tess_head_profile_left.png", (330, 250, 750, 670)),
      ("THE TAIL\nprofile", "v2", "tess_head_profile_left.png", (600, 420, 1152, 972))]
rows = []
for i, (lab, v, rf, box) in enumerate(CU):
    rows.append({"label": lab, "tiles": [crop(R + rf, box, f"ref_{i}.png", ref=True),
                                         crop(f"{O}s_{best}_{v}.png", box, f"best_{i}.png"),
                                         crop(f"{O}s_{best}_{v}_cyc.png", box, f"cyc_{i}.png"),
                                         crop(f"{O4}s_th_T48_{v}.png", box, f"t48_{i}.png")]})
bl = []
for p, nm in ((f"{O}s_{best}_backl.png", "best_b.png"), (f"{O}s_{best}_backl_cyc.png", "cyc_b.png"), (f"{O4}s_th_T48_backl.png", "t48_b.png")):
    if os.path.exists(p):
        im = Image.open(p).convert("RGB")
        n = im.size[0]
        im.crop((int(0.17 * n), int(0.2 * n), int(0.85 * n), int(0.88 * n))).resize((760, 760), Image.LANCZOS).save(T + nm)
        bl.append(T + nm)
    else:
        bl.append(None)
Image.open(R + "tess_head_hair_as_worn_back.png").convert("RGB").crop((200, 250, 1100, 1150)).resize((760, 760), Image.LANCZOS).save(T + "ref_b.png")
rows.append({"label": "THE TAIL\nfrom behind (her left; unfitted)", "tiles": [T + "ref_b.png"] + bl})
build({"title": f"Close-ups at the same pixels, reference beside ours ({best} | th_T48 = round four)", "tile": 760, "label_w": 360,
       "cols": ["REFERENCE", f"NEW {best} (EEVEE)", f"NEW {best} (Cycles)", "th_T48 (round four, EEVEE)"],
       "rows": rows}, HR + "th_31_closeups.png")

# ---- (c) riffs: round four's render over this code's
NAMES = {"1": "HIGH TIGHT PONYTAIL", "2": "LOW CENTRE PONYTAIL", "3": "LOW SIDE, SLEEK", "4": "HALF UP",
         "5": "TOP KNOT (bun)", "6": "LOW PLAIT"}
vn = ["front", "frontq", "left", "backl", "back", "right"]
rows = []
for k, nm in NAMES.items():
    rows.append({"label": f"th_Q{k} ROUND FOUR\n{nm}", "tiles": [ex(f"{O4}iso_th_Q{k}_a_{v}.png") for v in vn]})
    rows.append({"label": f"th_S{k} NOW\nthe same style call (+ the hairline's ear lowered)", "tiles": [ex(f"{O}iso_th_S{k}_a_{v}.png") for v in vn]})
build({"title": "The six riffs re-grown with round five's code (same style words; round four above, now below)",
       "tile": 440, "label_w": 420, "cols": ["front", "front 3/4", "left", "back left", "back", "right"], "rows": rows},
      HR + "th_32_tied_riffs.png")

# ---- (d) the hairline word + the temple of the tight riffs, close up
rows = []
for nm, lab in (("H0", "hairline 0\n(a hard edge: round four's row)"), ("H5", "hairline 0.5\n(the default of a neat head)"),
                ("H10", "hairline 1\n(soft: thin rim, baby hairs)"), ("S1", "riff: HIGH TIGHT PONYTAIL\n(default hairline)"),
                ("S5", "riff: TOP KNOT\n(default hairline)")):
    ts = []
    for v, box in (("front", (130, 120, 830, 820)), ("frontq", (130, 100, 830, 800)), ("left", (130, 130, 830, 830))):
        p = f"{O}iso_th_{nm}_c_{v}.png"
        if os.path.exists(p):
            Image.open(p).convert("RGB").crop(box).save(T + f"h_{nm}_{v}.png")
            ts.append(T + f"h_{nm}_{v}.png")
        else:
            ts.append(None)
    rows.append({"label": lab, "tiles": ts})
build({"title": "The style word `hairline` on Tess's style, and the temple hairline of the tight riffs (close-ups, EEVEE)",
       "tile": 700, "label_w": 420, "cols": ["front", "three-quarter", "profile"], "rows": rows},
      HR + "th_33_hairline_dial.png")
