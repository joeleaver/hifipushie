"""skinm.py <model> [tile=$D3/out/<model>_m_front.png] [tag]: the skin's look by measure, photo against our render
through the front reference's fitted camera (sheet1's tile), LIKE WITH LIKE: the same detector places the same skin
boxes on both pictures (forehead, cheeks, nose, upper lip, chin, jaw sides, under-eye), the render is brought to the
photo's own pixel size first (the photo's face is ~0.9 mm a pixel: nothing finer can be compared), then
skin_measure: zone colour (Lab, offsets from the forehead), contrast per octave, highlight share, plus the brow's
and lips' own numbers (brow darkness / thickness, lip redness against the skin beside it).
Writes $D3/out/skinm_<tag>.json and a picture of the boxes."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import rs
import sheet1
from hifipushie import skin_measure as sm

D3 = os.environ.get("D3")
# zone: (detector point(s) whose mean is the centre, half width mm, half height mm)
ZONES = {"forehead": ((151, 9), 14, 6), "cheek_r": ((50,), 8, 7), "cheek_l": ((280,), 8, 7), "nose": ((195, 5), 4, 6),
         "under_eye_r": ((119,), 6, 3), "under_eye_l": ((348,), 6, 3), "upper_lip": ((164,), 7, 3),
         "chin": ((199, 175), 9, 5), "jaw_r": ((135, 214), 7, 7), "jaw_l": ((364, 434), 7, 7), "temple_r": ((54,), 4, 5),
         "temple_l": ((284,), 4, 5), "neck": ((152,), 9, 5, 26)}   # (4th: mm below the points' mean)
BROW = {"r": (70, 63, 105, 66, 107), "l": (300, 293, 334, 296, 336)}
LIPS_UP, LIPS_LO = (37, 0, 267), (84, 17, 314)


def boxes(P, mm):
    out = {}
    for n, (ids, hw, hh, *dn) in ZONES.items():
        c = P[list(ids), :2].mean(0) + np.array([0.0, (dn[0] if dn else 0.0) / mm])
        out[n] = [c[0] - hw / mm, c[1] - hh / mm, c[0] + hw / mm, c[1] + hh / mm]
    return out


def extras(a, P, mm):
    L = sm.lab(a)
    out = {}
    for s, ids in BROW.items():
        c = P[list(ids), :2].mean(0)
        x0, x1 = int(c[0] - 14 / mm), int(c[0] + 14 / mm)
        y0, y1 = int(c[1] - 11 / mm), int(c[1] + 9 / mm)
        col = L[y0:y1, x0:x1, 0]
        skin = np.percentile(col, 85)
        prof = col.mean(1)                                  # lightness down the brow (rows)
        dark = skin - prof
        thick = float((dark > 0.5 * dark.max()).sum() * mm)   # rows darker than half the brow's depth
        cover = float((col < skin - 0.5 * (skin - col.min())).mean())
        out[f"brow_{s}"] = {"dL_max": round(float(dark.max()), 1), "dL_min_pixel": round(float(skin - col.min()), 1),
                            "thick_mm": round(thick, 1), "dark_share": round(cover, 3),
                            "fine_L": round(float(np.std(col - __import__("scipy.ndimage").ndimage.gaussian_filter(col, 1.2))), 2)}
    for n, ids in (("lip_upper", LIPS_UP), ("lip_lower", LIPS_LO)):
        c = P[list(ids), :2].mean(0)
        p = L[int(c[1] - 1.5 / mm):int(c[1] + 1.5 / mm) + 1, int(c[0] - 8 / mm):int(c[0] + 8 / mm)].reshape(-1, 3).mean(0)
        out[n] = {"L": round(float(p[0]), 1), "a": round(float(p[1]), 1), "b": round(float(p[2]), 1)}
    return out


def measure(img, mm, draw=None):
    a = np.asarray(img.convert("RGB"))
    P = np.asarray(rs.detect([a])[0]["P"], float)
    bx = boxes(P, mm)
    rep = sm.patch_report(a, bx, mm)
    rep["extras"] = extras(a, P, mm)
    if draw:
        im = img.convert("RGB").copy()
        d = ImageDraw.Draw(im)
        for n, b in bx.items():
            d.rectangle([int(v) for v in b], outline=(0, 255, 0))
        im.save(draw)
    rep.pop("per_box", None)
    return rep


def photo_and_scale(name):
    vs, cams = sheet1.cameras(name)
    v, cam = vs[0], cams[0]
    crop = [int(round(c)) for c in sheet1.crop_of(v)]
    ph = Image.open(v["image"]).convert("RGB").crop(tuple(crop))
    mm = cam["t"][2] / cam["f"] * 1000          # mm a photo pixel at the face
    return ph, mm


def show(rows):
    print(sm.table(rows))
    keys = list(next(iter(rows.values()))["zones"])
    print("zone colour L / a / b:")
    for lab_, r in rows.items():
        print(f"  {lab_[:10]:<10} " + "  ".join(f"{k} {r['zones'][k]['L']:.0f}/{r['zones'][k]['a']:.0f}/{r['zones'][k]['b']:.0f}" for k in keys if k in r["zones"]))
    print("highlight share / peak L by zone:")
    for lab_, r in rows.items():
        print(f"  {lab_[:10]:<10} " + "  ".join(f"{k} {v['share']:.2f}/{v.get('peak_L')}" for k, v in r["highlight"].items()))
    print("brows, lips:")
    for lab_, r in rows.items():
        print(f"  {lab_[:10]:<10} " + json.dumps(r["extras"]))
    print("shadow:")
    for lab_, r in rows.items():
        print(f"  {lab_[:10]:<10} " + json.dumps(r["shadow"]))


if __name__ == "__main__":
    name = sys.argv[1]
    tile = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else f"{D3}/out/{name}_m_front.png"
    tag = sys.argv[3] if len(sys.argv) > 3 else name
    ph, mm = photo_and_scale(name)
    ours = Image.open(tile).convert("RGB").resize(ph.size, Image.LANCZOS)
    rows = {"photo": measure(ph, mm, f"{D3}/out/skinm_photo_boxes.png"), "ours": measure(ours, mm, f"{D3}/out/skinm_{tag}_boxes.png")}
    show(rows)
    json.dump(rows, open(f"{D3}/out/skinm_{tag}.json", "w"), indent=1, default=str)
