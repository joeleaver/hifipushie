"""mk.py [dst=g3_garrett] [src=rs2_m3]: the dressed-head candidate: src's spec (om_garrett's body, rs2_m3's head) with
rs2_n4's eye settings (eyes 1.0, the lid-opening expression regions at half), the SKIN PIPELINE instead of the
hand-painted layers (tone measured on the front photo, age 52, stubble, brows, eyes), the groom as it is (hand locks
in [az, el, h]: they re-seat on this scalp). patch file: $D3/skin_patch.json is merged over the skin if it exists."""
import copy
import json
import os
import sys

import numpy as np
from PIL import Image

from hifipushie import skin as skinmod
from hifipushie import store

D3 = os.environ.get("D3", "/mnt/data/hifipushie/garrett3")
PHOTO = str(store.HOME / "garrett_v20" / "concept_v8_front_apose.png")
# skin-only boxes on the front photo (pixels): forehead, both cheeks under the eyes, nose bridge side
BOXES = {"forehead": (592, 192, 648, 214), "cheek_r": (572, 262, 596, 282), "cheek_l": (646, 258, 668, 278)}
IRIS = (588, 243, 598, 249)


def _lab(rgb):
    rgb = np.asarray(rgb, float)
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def measure_tone(path=PHOTO, boxes=BOXES):
    """Tone parameters whose albedo has the photo's skin chroma (Lab a, b of the boxes' medians; lightness is the
    light's: only loosely held). Returns (tone dict, measured sRGB by box, the tone's sRGB)."""
    im = np.asarray(Image.open(path).convert("RGB"), float) / 255
    got = {k: np.median(im[y0:y1, x0:x1].reshape(-1, 3), 0) for k, (x0, y0, x1, y1) in boxes.items()}
    lab = {k: _lab(v) for k, v in got.items()}
    fore, cheek = lab["forehead"], 0.5 * (lab["cheek_r"] + lab["cheek_l"])
    target = 0.6 * fore + 0.4 * cheek
    best = None
    for mel in np.linspace(0.04, 0.4, 19):
        for bl in np.linspace(0.2, 0.75, 12):
            for ut in np.linspace(-0.4, 0.8, 13):
                t = {"melanin": float(mel), "blood": float(bl), "undertone": float(ut)}
                c = _lab(np.array(skinmod.tone_rgb(t)))
                e = (c[1] - target[1]) ** 2 + (c[2] - target[2]) ** 2 + 0.05 * (c[0] - min(target[0] + 4, 80)) ** 2
                if best is None or e < best[0]:
                    best = (e, t, c)
    tone = {k: round(v, 3) for k, v in best[1].items()}
    return tone, {k: [round(float(x), 3) for x in v] for k, v in got.items()}, skinmod.tone_rgb(tone), \
        {"target_lab": target.round(1).tolist(), "tone_lab": best[2].round(1).tolist(), "cheek_minus_forehead_ab": (cheek - fore)[1:].round(1).tolist()}


def iris_colour(path=PHOTO, box=IRIS):
    im = np.asarray(Image.open(path).convert("RGB"), float)
    x0, y0, x1, y1 = box
    px = im[y0:y1, x0:x1].reshape(-1, 3)
    lum = px.mean(1)
    mid = px[(lum > np.percentile(lum, 35)) & (lum < np.percentile(lum, 80))]
    return "#" + "".join(f"{int(round(c)):02x}" for c in mid.mean(0))


def main(dst="g3_garrett", src="rs2_m3"):
    sp = json.loads((store.HOME / src / "spec.json").read_text())
    n4 = json.loads((store.HOME / "rs2_n4" / "spec.json").read_text())
    h = sp["base"]["head"]
    if src.startswith("rs2_"):       # (the study's heads carry the old eye settings; refit.py's heads have their own)
        h["eyes"] = n4["base"]["head"]["eyes"]
        h["expression"] = copy.deepcopy(n4["base"]["head"]["expression"])
    tone, got, rgb, info = measure_tone()
    tone = {**tone, "blood": round(0.75 * tone["blood"], 3), "undertone": round(tone["undertone"] / 3, 3)}  # (under the
    # look's light the measured tone rendered more orange than the photo: the photo's lit skin is paler and greyer)
    iris = iris_colour()
    print("photo skin (sRGB 0..1):", got)
    print("tone:", tone, "-> albedo", rgb, info)
    print("iris from the photo:", iris)
    sp["skin"] = {
        "part": "body", "sex": 1, "age": 52, "tone": tone, "variation": 1.0, "detail": 1.0, "oil": 0.35, "thin": 0.5,
        "sun": 0.45,
        "eyes": {"iris": "#3f4a52", "pupil": 0.32, "veins": 0.4},
        "hair": {"brows": {"color": "#4a4541", "density": 0.85, "thickness": 1.15, "grey": 0.2},
                 "lashes": {"amount": 0.55}, "stubble": {"amount": 0.75, "color": "#6f6a66"}, "body": 0},
        "features": {"flush": 0.12},
    }
    pf = os.path.join(D3, "skin_patch.json")
    if os.path.exists(pf):
        from hifipushie.server import _merge_patch
        sp["skin"] = _merge_patch(sp["skin"], json.load(open(pf)))
    sp["paint"] = {k: v for k, v in (sp.get("paint") or {}).items() if k in ("180_mouth_inside",)}
    for k in ("subsurface", "subsurface_radius", "subsurface_scale"):   # the skin pipeline shades the skin part itself
        sp["parts"]["body"].pop(k, None)
    sp["parts"]["eyes"] = {k: v for k, v in sp["parts"]["eyes"].items() if k in ("voxel",)}
    lk = sp["hair"].setdefault("look", {})   # the photo's hair: grey-brown, greyer at the temples
    lk.update({"lit": "#6b6661", "sheen": "#b9b5af", "gap": "#4a4541", "grey": "#b5b1ab"})
    store.save(dst, sp, f"garrett3: {src}'s head, n4's eyes, the skin pipeline (tone from the photo), groom as is")
    for fn in ("human_refs.json", "pose.json"):
        rf = store.HOME / src / fn
        if rf.exists():
            (store.HOME / dst / fn).write_text(rf.read_text())
    print("saved", dst)


if __name__ == "__main__":
    main(*sys.argv[1:])
