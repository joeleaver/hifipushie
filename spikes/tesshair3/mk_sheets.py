"""mk_sheets.py [best=th_T31]: the round's sheets into workspace/human_renders (sheet3.py layouts):
th_10_tess_swept_back.png   REFERENCE | new best EEVEE | new best CYCLES | th_T11 | th_T14; rows front / three-quarter /
                            profile (fitted cameras), back from her left (beside the unfitted back picture), back from
                            her right and right profile (not in the references)
th_11_tied_riffs.png        the same style call riffed: a row a hairstyle, six sides
th_12_tied_other_head.png   her style carried to another head through the tool (look_hair "around" tiles)"""
import json, os, subprocess, sys
from PIL import Image

best = dict(a.split("=") for a in sys.argv[1:]).get("best", "th_T31")
O = "/mnt/data/hifipushie/tesshair3/out/"
O2 = "/mnt/data/hifipushie/tesshair2/out/"
R = "/home/joe/dev/s0urc3/docs/img/tess_ref_full/"
HR = "/home/joe/dev/hifipushie/workspace/human_renders/"
here = os.path.dirname(os.path.abspath(__file__))


def ex(p):
    return p if os.path.exists(p) else None


def build(layout, out):
    f = O + "_layout.json"
    json.dump(layout, open(f, "w"))
    subprocess.run([sys.executable, here + "/sheet3.py", f, out], check=True)


views = [("front\n(fitted camera)", "v0", R + "tess_head_front.png"),
         ("three-quarter\n(fitted camera)", "v1", R + "tess_head_three_quarter_left.png"),
         ("profile\n(fitted camera)", "v2", R + "tess_head_profile_left.png"),
         ("back, from her left\n(reference: unfitted picture)", "backl", R + "tess_head_hair_as_worn_back.png"),
         ("back, from her right\n(UNSEEN: no reference)", "backq", None),
         ("right profile\n(UNSEEN: no reference)", "right", None)]
rows = [{"label": lab, "tiles": [ref, ex(f"{O}s_{best}_{v}.png"), ex(f"{O}s_{best}_{v}_cyc.png"),
                                 ex(f"{O2}s_th_T11_{v}.png"), ex(f"{O2}s_th_T14_{v}.png")]} for lab, v, ref in views]
build({"title": f"Tess: swept-back low side ponytail. New construction ({best}) beside round two (th_T11, th_T14)",
       "tile": 640, "label_w": 360,
       "cols": ["REFERENCE", f"NEW BEST {best} (EEVEE)", f"NEW BEST {best} (Cycles, look uncalibrated)", "th_T11 (round two, Joe's pick)",
                "th_T14 (round two's last)"], "rows": rows}, HR + "th_10_tess_swept_back.png")

riffs = [(best, "HER STYLE\nlow, left, loose (tightness 0.3), messy (neatness 0.2), wavy full tail")]
for ln in open("/mnt/data/hifipushie/tesshair3/riffs.txt"):
    if "|" in ln:
        n, st = ln.strip().split("|", 1)
        riffs.append(("th_" + n, st))
NAMES = {"th_R1": "HIGH TIGHT PONYTAIL", "th_R2": "LOW CENTRE PONYTAIL", "th_R3": "LOW SIDE, SLEEK", "th_R4": "HALF UP",
         "th_R5": "TOP KNOT (bun)", "th_R6": "LOW PLAIT"}


def words(st):
    try:
        d = json.loads(st)
    except Exception:
        return st
    t = d.get("tail")
    out = [f"tie {d.get('tie')}, side {d.get('side')}", f"tightness {d.get('tightness')}, neatness {d.get('neatness')}"]
    if "part" in d:
        out.append(f"part {d['part']}")
    if d.get("half"):
        out.append("half: true")
    out.append("tail " + (t if isinstance(t, str) else ", ".join(f"{k} {v}" for k, v in (t or {}).items())))
    return "\n".join(out)


cols = ["front", "front three-quarter", "left", "back left", "back", "right"]
vn = ["front", "frontq", "left", "backl", "back", "right"]
rows = []
for m, st in riffs:
    lab = st if m == best else NAMES.get(m, m) + "\n" + words(st)
    rows.append({"label": f"{m}\n{lab}", "tiles": [ex(f"{O}iso_{m}_a_{v}.png") for v in vn]})
build({"title": "One style call, riffed (tie_hair on Tess's head; no references: would you recognise the hairstyle at a glance?)",
       "tile": 520, "label_w": 520, "cols": cols, "rows": rows}, HR + "th_11_tied_riffs.png")

lk = O + "look_th_H1.png"
if os.path.exists(lk):
    im = Image.open(lk).convert("RGB")
    names = ["bust_front", "bust_three_quarter", "bust_side", "bust_back_quarter", "bust_back", "bust_side_r"]
    n = int(dict(a.split("=") for a in sys.argv[1:]).get("look_tile", 640))
    y0 = int(dict(a.split("=") for a in sys.argv[1:]).get("look_y", 22))
    tiles = []
    for i, v in enumerate(names):
        p = f"{O}_h1_{v}.png"
        im.crop((i * n, y0, (i + 1) * n, y0 + n)).save(p)
        tiles.append(p)
    build({"title": "Her style on another head (hu_w28d): tie_hair(carry_from=th_T31), look_hair(views=['around'])",
           "tile": 560, "label_w": 300, "cols": ["front", "three-quarter", "left", "back left", "back", "right"],
           "rows": [{"label": "th_H1\nthe same style, hairline = this head's default", "tiles": tiles}]},
          HR + "th_12_tied_other_head.png")
