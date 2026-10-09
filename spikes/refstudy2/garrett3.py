"""garrett3.py: Garrett refitted by the coordinator's rules (2026-10-09):
  1. widths and build from the PICTURE: macros measured on the front photo (measured.py's regression, the detector's
     points + the outline's widths at levels a photo shows: cheeks, jaw, neck against the background), given to the MAP
     as evidence with honest noise;
  2. Joe's words as SHAPE words only (no widths, no neck, no cheek fullness; "handsome" = no heavy brow);
  3. the photo's expression OUT of the identity: the fit is made with the photo's squint / frown / set mouth as a pose
     on the head, the saved head is the same identity without the pose.
  run.sh garrett3.py measure     the measured macros of the photo (+ the mask picture $D2/out/garrett_mask.png)
  run.sh garrett3.py fit         -> models rs2_m0 (MAP), prints evidence residuals
"""
import copy
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

import garrett
import measured as ms
import rs
from hifipushie import humanfit, humanfit_map, humanmacro as hm, likeness, likeness_read as lr, store

D2 = os.environ.get("D2", "/mnt/data/hifipushie/refstudy2")
LOW = (0.6, 0.75)   # outline levels THIS photo shows: cheeks and jaw below the ear lobes. At 0.9 and 1.2 the jacket's collar is the edge: no neck width from it
WIDTH_MACROS = ("jaw_width", "face_width", "cheekbone_width", "chin_width", "face_length", "jaw_square", "cheek_fullness")
# Joe: "handsome guy with a square jaw, cleft chin, cute nose" as SHAPE words ("chunky" is left to the picture)
SHAPE_READ = {"jaw_square": (1.2, 0.5), "jaw_angle": (1.0, 0.6), "chin_projection": (1.0, 0.5), "under_chin": (0.8, 0.5),
              "nose_length": (-0.8, 0.5), "nose_upturn": (0.6, 0.5), "bridge_hump": (0.0, 0.5), "brow_ridge": (0.0, 0.6), "eye_depth": (0.0, 0.7)}
POSE = {"lid_upper": 0.0013, "brow_inner": -0.0015, "brow_outer": -0.0012, "smile": -0.0015}   # the photo's squint 0.70, frown, set mouth


def low_model():
    """measured.py's regression on the features a PHOTO has: points + the outline at the LOW levels (no shading: a
    photo's stubble, hair and light are not the renders'). Returns (model, cv rms per macro)."""
    z = np.load(f"{D2}/measured_train_1200.npz")
    cols = [j for i, lv in enumerate(ms.LEVELS) for j in (2 * i, 2 * i + 1) if min(abs(lv - x) for x in LOW) < 0.01] + [2 * len(ms.LEVELS)]
    F = {"pts": z["pts"], "sil": z["sil"][:, cols], "shade": z["shade"]}
    keys = ("pts", "sil")
    P = ms.cv(F, z["Z"], keys)
    rms = np.sqrt(((P - z["Z"]) ** 2).mean(0))
    return ms.fit_model(F, z["Z"], keys), rms, cols


def photo_features(cols):
    v = garrett.refs()[0]
    img = Image.open(v["image"]).convert("RGB")
    box = [int(x) for x in likeness._box(v["points"], img.size)]
    w = box[2] - box[0]
    box = [max(box[0] - w // 3, 0), max(box[1] - w // 3, 0), min(box[2] + w // 3, img.size[0]), min(box[3] + w // 2, img.size[1])]
    c = np.asarray(img.crop(box))
    d = rs.detect([c])[0]
    # the head against the plain backdrop: colour distance from the backdrop (the crop's top corners), holes filled
    bg = np.median(np.r_[c[:20, :20].reshape(-1, 3), c[:20, -20:].reshape(-1, 3)], 0)
    m = np.linalg.norm(c.astype(float) - bg, axis=2) > 28
    m = ndimage.binary_fill_holes(ndimage.binary_opening(m, iterations=2))
    lab, n = ndimage.label(m)
    if n > 1:
        m = lab == (1 + np.argmax(ndimage.sum(m, lab, range(1, n + 1))))
    zb = np.where(m, 1.0, np.inf)
    f = ms.features(c, zb, d)
    out = Image.fromarray((np.where(m[..., None], c, c // 3)).astype(np.uint8))
    out.save(f"{D2}/out/garrett_mask.png")
    return {"pts": f["pts"][None], "sil": f["sil"][cols][None]}, f, d


def measure():
    M, rms, cols = low_model()
    F, f, d = photo_features(cols)
    z = ms.predict(M, F)[0]
    out = {}
    print("macros measured on Garrett's front photo (points + low outline), sigmas; cv rms:")
    for k in WIDTH_MACROS:
        i = hm.NAMES.index(k)
        out[k] = (round(float(z[i]), 2), round(float(rms[i] * 1.5), 2))   # truth-set error is ~1.5 x the cv rms
        print(f"   {k:16s} {z[i]:+.2f}  +-{rms[i] * 1.5:.2f}   (cv rms {rms[i]:.2f})")
    print("   outline widths / interocular at levels", LOW, ":", np.round(F["sil"][0][:-1].reshape(-1, 2).sum(1), 2), "; eye line -> chin / io", round(float(F["sil"][0][-1]), 2))
    json.dump(out, open(f"{D2}/garrett_measured.json", "w"), indent=1)
    return out


def fit(scale=1.25):
    meas = {k: tuple(v) for k, v in json.load(open(f"{D2}/garrett_measured.json")).items()}
    read = {**SHAPE_READ, **{k: v for k, v in meas.items() if k not in SHAPE_READ}}
    sp = garrett.hist("lk_garrett", 1)
    vs = garrett.refs()
    b0 = copy.deepcopy(sp["base"])
    b0["head"]["pose"] = dict(POSE)
    b, rep = humanfit_map.fit(b0, vs, read=read, read_sd=0.5)
    if rep.get("refused"):
        print("REFUSED:", rep["refused"][:300])
        b, rep = humanfit_map.fit(b0, vs, read=read, read_sd=0.5, force=True)
    print("fit WITH the photo's pose:", [(v["rms_mm"], v["lens_mm"]) for v in rep["views"]], rep["plausibility"])
    print("read asked -> got:", {k: (v["asked"], v["got"]) for k, v in rep["read"].items()})
    idn = b["head"]["identity"]
    b["head"]["identity"] = {k: float(v) * scale for k, v in idn.items()}
    posed = copy.deepcopy(b)
    b["head"].pop("pose", None)
    for tag, bb, note in (("rs2_m0", b, "neutral"), ("rs2_m0_posed", posed, "with the photo's pose (comparison renders only)")):
        store.save(tag, {**copy.deepcopy(sp), "base": bb}, f"refstudy2: MAP + measured widths + shape words, expression fitted as pose; {note}; deviation x{scale}")
        (store.HOME / tag / "human_refs.json").write_text(json.dumps({"views": vs, "cameras": rep["cameras"]}, indent=1))
    import structure
    structure.info("rs2_m0 (neutral)", b)
    structure.info("rs2_m0_posed", posed)
    print(lr.render_views("rs2_m0", f"{D2}/out/six_rs2_m0.png", base=b))


if __name__ == "__main__":
    {"measure": measure, "fit": fit}[sys.argv[1]]()
