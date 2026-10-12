"""mk_sheets4.py [best=th_T47]: round four's sheets into workspace/human_renders (tesshair3's sheet3.py layouts):
th_20_tess_wisps_poof.png   REFERENCE | new best EEVEE | new best CYCLES | th_R3 (round three's sleek) | th_W1 (round
                            three's code, dials only) | th_T34 (round three's best); rows front / three-quarter / profile
                            (fitted cameras), back from her left, back from her right, right profile (unseen)
th_21_wisps_tail_closeups.png   close-ups, reference beside ours at the same pixels: the front hairline + wisps (front,
                            three-quarter, profile) and the tail (three-quarter, profile, back)
th_22_tail_dials.png        fullness x wave, the same head and tie: from the side and from behind
th_23_tied_riffs.png        round three's six riff styles: round three's render over the same style with this code"""
import json, os, subprocess, sys
from PIL import Image

best = dict(a.split("=") for a in sys.argv[1:]).get("best", "th_T47")
O = "/mnt/data/hifipushie/tesshair4/out/"
O3 = "/mnt/data/hifipushie/tesshair3/out/"
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
                                 ex(f"{O}s_th_R3_{v}.png"), ex(f"{O}s_th_W1_{v}.png"), ex(f"{O3}s_th_T34_{v}.png")]}
        for lab, v, ref in views]
build({"title": f"Tess round four: the sleek low side ponytail + front wisps + a poofed tail ({best})",
       "tile": 640, "label_w": 360,
       "cols": ["REFERENCE", f"NEW BEST {best} (EEVEE)", f"NEW BEST {best} (Cycles)", "th_R3 (round three's sleek: Joe's \"almost right\")",
                "th_W1 (round three's code, dials only)", "th_T34 (round three's best)"], "rows": rows},
      HR + "th_20_tess_wisps_poof.png")

# ---- (b) close-ups: the fitted tiles are the whole reference picture squared (1152 x 1536 padded to 1536 wide)
T = O + "_crops/"
os.makedirs(T, exist_ok=True)


def crop(src, box, name, ref=False):
    """box in REFERENCE pixels (x0, y0, x1, y1); a fitted tile is the reference padded by 192 px each side."""
    if not src or not os.path.exists(src):
        return None
    im = Image.open(src).convert("RGB")
    if ref:
        b = box
    else:
        k = im.size[0] / 1536.0
        b = tuple(int(round(v * k)) for v in (box[0] + 192, box[1], box[2] + 192, box[3]))
    im.crop(b).resize((720, 720), Image.LANCZOS).save(T + name)
    return T + name


CU = [("front hairline + wisps\nfront", "v0", "tess_head_front.png", (226, 180, 926, 880)),
      ("front hairline + wisps\nthree-quarter", "v1", "tess_head_three_quarter_left.png", (180, 150, 880, 850)),
      ("temple + sideburn wisps\nprofile", "v2", "tess_head_profile_left.png", (250, 180, 950, 880)),
      ("the tail\nthree-quarter", "v1", "tess_head_three_quarter_left.png", (560, 420, 1152, 1012)),
      ("the tail\nprofile", "v2", "tess_head_profile_left.png", (560, 400, 1152, 992))]
rows = []
for i, (lab, v, rf, box) in enumerate(CU):
    rows.append({"label": lab, "tiles": [crop(R + rf, box, f"ref_{i}.png", ref=True),
                                         crop(f"{O}s_{best}_{v}.png", box, f"best_{i}.png"),
                                         crop(f"{O}s_{best}_{v}_cyc.png", box, f"cyc_{i}.png"),
                                         crop(f"{O}s_th_R3_{v}.png", box, f"r3_{i}.png"),
                                         crop(f"{O}s_th_W1_{v}.png", box, f"w1_{i}.png")]})
# the back: no fitted camera; the reference's own crop beside our back-left tile's
bl = [None, None, None]
for j, (p, nm) in enumerate(((f"{O}s_{best}_backl.png", "best_b.png"), (f"{O}s_{best}_backl_cyc.png", "cyc_b.png"),
                             (f"{O}s_th_R3_backl.png", "r3_b.png"), (f"{O}s_th_W1_backl.png", "w1_b.png"))):
    if os.path.exists(p):
        im = Image.open(p).convert("RGB")
        n = im.size[0]
        im.crop((int(0.18 * n), int(0.08 * n), int(0.88 * n), int(0.78 * n))).resize((720, 720), Image.LANCZOS).save(T + nm)
        bl.append(T + nm) if j >= 3 else bl.__setitem__(j, T + nm)
rb = Image.open(R + "tess_head_hair_as_worn_back.png").convert("RGB").crop((150, 150, 1150, 1150)).resize((720, 720), Image.LANCZOS)
rb.save(T + "ref_b.png")
rows.append({"label": "the tail\nback, from her left (unfitted)", "tiles": [T + "ref_b.png"] + bl[:4]})
build({"title": f"Close-ups: wisps at the hairline and the tail, reference beside ours ({best})", "tile": 720, "label_w": 330,
       "cols": ["REFERENCE", f"NEW {best} (EEVEE)", f"NEW {best} (Cycles)", "th_R3 (round three)", "th_W1 (dials only)"],
       "rows": rows}, HR + "th_21_wisps_tail_closeups.png")

# ---- (c) the dials
FU, WV = (0.0, 0.5, 1.0), (0.0, 0.5, 1.0)
rows = []
for i, fu in enumerate(FU):
    rows.append({"label": f"fullness {fu}\n" + ("sleek" if fu == 0 else "bushy" if fu == 1 else ""),
                 "tiles": [ex(f"{O}iso_th_D{i}{j}_a_left.png") for j in range(3)]
                 + [ex(f"{O}iso_th_D{i}{j}_a_back.png") for j in range(3)]})
build({"title": "The tail's two dials on one head and tie (tail.fullness x tail.wave; everything else the same style call)",
       "tile": 560, "label_w": 300,
       "cols": [f"SIDE wave {w}" + (" straight" if w == 0 else " loose waves" if w == 1 else "") for w in WV]
       + [f"BACK wave {w}" for w in WV], "rows": rows}, HR + "th_22_tail_dials.png")

# ---- (d) riffs: round three's render over this code's
NAMES = {"1": "HIGH TIGHT PONYTAIL", "2": "LOW CENTRE PONYTAIL", "3": "LOW SIDE, SLEEK", "4": "HALF UP",
         "5": "TOP KNOT (bun)", "6": "LOW PLAIT"}
vn = ["front", "frontq", "left", "backl", "back", "right"]
rows = []
for k, nm in NAMES.items():
    rows.append({"label": f"th_R{k} ROUND THREE\n{nm}", "tiles": [ex(f"{O3}iso_th_R{k}_a_{v}.png") for v in vn]})
    rows.append({"label": f"th_Q{k} NOW\nthe same style call", "tiles": [ex(f"{O}iso_th_Q{k}_a_{v}.png") for v in vn]})
build({"title": "Round three's six riffs re-grown with round four's code (same style words; round three above, now below)",
       "tile": 440, "label_w": 420, "cols": ["front", "front 3/4", "left", "back left", "back", "right"], "rows": rows},
      HR + "th_23_tied_riffs.png")
