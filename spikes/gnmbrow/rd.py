"""rd.py <tag> ...: reads of fitted-camera shots (shot.py's out/s_<tag>.png; "photo" = the picture's own crop), all
in mm AT THE MODEL (one mm/px for every image: the fitted camera's):
  gap     brow hair lower edge over the upper lid margin at the eye's inner third / pupil / outer third (bm.read: the
          detector's lid margin ON THAT IMAGE, the luminance band above it), both eyes' mean
  band    the brow band against the PHOTO's at the photo's own 9 columns (blockin_brows.band + errors; + = lower)
  iris    limbus diameter, ring colour; the opening at the pupil (detector lids)
Writes out/rd.json."""
import json
import sys

import numpy as np
from PIL import Image

import bm
from hifipushie import blockin as bi, blockin_brows as bb, blockin_eyes as be, likeness, lidfold

REFS = "gd_T12"
bx = json.load(open(bm.G + "/box.json"))
K, box = bx["K"], bx["box"]
q = bb._inputs(REFS)
mm = q["mm"] / K                                   # mm per shot pixel
Pp = (q["P"] - box[:2]) * K                         # the photo's detector points in shot pixels
pb = bb.band(q["img"], q["P"], q["mm"])
out = {}
for tag in sys.argv[1:]:
    im = Image.open(f"{bm.G}/s_{tag}.png").convert("RGB")
    P = likeness.detect([im])[0]
    r = {}
    if P is None:
        print(tag, "no detection on the shot; the photo's points are used for the lids")
        P = Pp
    P = np.asarray(P, float)[:, :2]
    b = bm.read(im, P)
    kpx = b["iris_px"] / lidfold.IRIS_MM            # px per reader-mm
    E = np.array([[c["edge_mm"] for c in e["cols"]] for e in b["eyes"]]) * kpx * mm
    C = np.array([[c["core_mm"] for c in e["cols"]] for e in b["eyes"]]) * kpx * mm
    O = np.array([[c["open_iris"] for c in e["cols"]] for e in b["eyes"]]) * b["iris_px"] * mm
    r["gap"] = E.mean(0).round(2).tolist()
    r["core"] = C.mean(0).round(2).tolist()
    r["open"] = round(float(O[:, 1].mean()), 2)
    lb = be.limbus(im, P)
    r["iris_mm"] = round(2 * float(np.mean([e["r_px"] for e in lb])) * mm, 2)
    rgb = np.mean([e["rgb"] for e in lb], 0)
    r["iris_hex"] = "#%02x%02x%02x" % tuple(int(round(255 * float(x))) for x in rgb)
    r["gap_iris"] = (E.mean(0) / r["iris_mm"]).round(2).tolist()
    rb = bb.band(im, q["P"], q["mm"], scale=K, origin=box[:2])
    e = bb.errors(pb, [{"low": x["low"], "mid": 0.5 * (x["low"] + x["top"]), "top": x["top"]} for x in rb], q["mm"])
    r["band_low_rms"], r["band_mid_rms"], r["band_thick"] = round(e["low_rms"], 2), round(e["mid_rms"], 2), round(e["thick_mean"], 2)
    r["band_low"] = np.round(e["low"], 1).tolist()
    out[tag] = r
    print(tag, json.dumps(r), flush=True)
old = {}
try:
    old = json.load(open(bm.G + "/rd.json"))
except Exception:  # noqa: BLE001
    pass
old.update(out)
json.dump(old, open(bm.G + "/rd.json", "w"), indent=1)
