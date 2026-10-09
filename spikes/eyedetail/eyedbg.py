"""eyedbg.py <tag> <variant | png=<dressed front_big.png>>: one column of the eye diagnosis strip (Garrett, the photo's
camera and fitted light). Variants of fs_garrett's head: raw (no eye sliders, no age_lid_fold / age_cheek_flat, no
lid pose; run with HIFIPUSHIE_NO_LOOPS=1 for no loops either), loops (= raw with the loops), sliders (+ the eye
sliders), pose (+ the lid pose = fs_garrett as it is), photo. Saves out/eyedbg_<tag>.png (the eyes, 2x crops of the
subject's left inner and outer corner) and out/eyedbg_<tag>.json: per eye (subject's right, left) opening, the lower
lid's height on the iris (white_below), canthal tilt, and the angles at the inner and outer canthus (between the
upper and lower margin points next to each corner), by the detector."""
import copy
import json
import sys

import numpy as np
from PIL import Image

from hifipushie import likeness, likeness_eyes as le
from hifipushie import likeness_pair as lp
from hifipushie import store

OUT = "/mnt/data/hifipushie/eyedetail/out"  # (a copy of facesliders' spikes/facesliders/eyedbg.py)
tag, var = sys.argv[1], sys.argv[2]
EYE_SL = ("eye_hood_lateral", "eye_crease_depth", "brow_lateral", "canthal_tilt", "age_lid_fold", "age_cheek_flat",
          "eye_hood", "eye_platform", "eye_bag", "eye_lidcheek", "eye_tear_trough", "eye_sulcus")
CORNERS = {"inner": ((133, 173, 155), (362, 398, 382)), "outer": ((33, 246, 7), (263, 466, 249))}


def angle(P, c, a, b):
    u, v = P[a] - P[c], P[b] - P[c]
    return float(np.degrees(np.arccos(np.clip(u @ v / np.linalg.norm(u) / np.linalg.norm(v), -1, 1))))


refs = likeness._refs("fs_garrett")
ph = likeness.photo_sides(refs)[0]
if var == "photo":
    img, P, mmpx = ph["img"].crop(tuple(int(round(v)) for v in ph["box"])), None, ph["mmpx"]
    side = ph["side"]
    off = np.array(ph["box"][:2])
    k = 1.0
elif var.startswith("png="):
    import sheet1
    im = Image.open(var[4:]).convert("RGB")
    crop = sheet1.crop_of(refs["views"][0])
    s = im.size[0] / (crop[2] - crop[0])
    d = likeness.detect([im])[0]
    Pr = np.asarray(d["P"] if isinstance(d, dict) else d, float)[:, :2]
    side = likeness.Side(Pr / s + np.array(crop[:2]), None, "detector")
    mmpx = ph["mmpx"]
    img = im.resize((int(im.size[0] / s), int(im.size[1] / s)))
    off = np.array(crop[:2])
    k = 1.0
else:
    b = copy.deepcopy(store.load("fs_garrett")["base"])
    h = b["head"]
    if var in ("raw", "loops"):
        h["sliders"] = {kk: v for kk, v in (h.get("sliders") or {}).items() if kk not in EYE_SL}
    if var in ("raw", "loops", "sliders"):
        (h.get("pose") or {}).pop("lid_upper", None)
    m = lp.matched("fs_garrett", b, face_id=False)
    side, mmpx = m["md"]["side"], m["md"]["mmpx"]
    img = (m.get("render") or m["clay"]).convert("RGB")
    off = np.array(m["box"][:2])
    k = img.size[0] / (m["box"][2] - m["box"][0])
P = np.asarray(side.P, float)
ms = le.measures(P, mmpx)
out = {"open": ms["open"], "white_below": ms["white_below"], "cover": ms["cover"], "canthal_tilt": ms["canthal_tilt"]}
for nm, ids in CORNERS.items():
    out[f"{nm}_angle"] = [round(angle(P, *t), 1) for t in ids]
json.dump(out, open(f"{OUT}/eyedbg_{tag}.json", "w"))
print(tag, out)
# the picture: both eyes, then the subject's left eye's inner and outer corner at 2x (8 mm boxes)
q = lambda p: (np.asarray(p) - off) * k  # noqa: E731
x0, y0, x1, y1 = le.eye_box(P)
eyes = img.crop(tuple(int(round(v)) for v in (*q((x0, y0 + 0.25 * (y1 - y0))), *q((x1, y1)))))
eyes = eyes.resize((520, int(520 * eyes.size[1] / eyes.size[0])))
tiles = [eyes]
for i in (362, 263):
    c = q(P[i])
    r = 4.0 / mmpx * k
    t = img.crop((int(c[0] - r), int(c[1] - r), int(c[0] + r), int(c[1] + r))).resize((260, 260), Image.LANCZOS)
    tiles.append(t)
col = Image.new("RGB", (520, eyes.size[1] + 260), (255, 255, 255))
col.paste(eyes, (0, 0))
col.paste(tiles[1], (0, eyes.size[1]))
col.paste(tiles[2], (260, eyes.size[1]))
col.save(f"{OUT}/eyedbg_{tag}.png")
