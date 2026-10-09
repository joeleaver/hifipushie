"""xr_compare.py: XR Blocks' MediaPipe <-> GNM correspondence (google/xrblocks samples/avatar_lab/gnm/
FaceCorrespondence.js, Apache-2.0: 166 skull-fixed points, each a MediaPipe index + a GNM vertex + a reference-cloud
position) against our calibrated table mp478_gnm.npz (front class): for each of their points, how far their GNM
vertex lies from the surface point our table gives the same MediaPipe index (mm, on GNM's template)."""
import base64
import os
import re
import urllib.request

import numpy as np

import rs
from hifipushie import humanfit_map

D2 = os.environ.get("D2", "/mnt/data/hifipushie/refstudy2")
URL = "https://raw.githubusercontent.com/google/xrblocks/main/samples/avatar_lab/gnm/FaceCorrespondence.js"
f = f"{D2}/xr/FaceCorrespondence.js"
if not os.path.exists(f):
    open(f, "wb").write(urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "hifipushie"}), timeout=60).read())
js = open(f).read()
b = base64.b64decode(re.search(r"PACKED =\s*'([^']+)'", js).group(1))
n = int(re.search(r"const COUNT = (\d+)", js).group(1))
ref = np.frombuffer(b, np.float32, n * 3, 0).reshape(n, 3)
o = n * 12
lm = np.frombuffer(b, np.uint16, n, o)
vx = np.frombuffer(b, np.uint16, n, o + 2 * n)
rigid = np.frombuffer(b, np.uint8, n, o + 4 * n)
print(n, "points; rigid", int(rigid.sum()), "; mediapipe ids", lm.min(), "..", lm.max(), "; gnm vertices", vx.min(), "..", vx.max())
g = rs.gnm()
V0 = g["V0"]
t = humanfit_map.table()
names = ["front", "left", "profile", "right"]
theirs = V0[vx.astype(int)]
for ci in (0, 1, 3):
    ours = (V0[t["vid"][ci][lm]] * t["w"][ci][lm][..., None]).sum(1)
    sd = t["sd"][ci][lm]
    d = np.linalg.norm(ours - theirs, axis=1) * 1000
    ok = np.isfinite(sd) & (sd < humanfit_map.CUT)
    print(f"class {names[ci]}: of their {n} points, {int(ok.sum())} are usable in our table (scatter < {humanfit_map.CUT} mm)")
    if ok.any():
        print(f"   their GNM vertex vs our calibrated surface point: median {np.median(d[ok]):.2f} mm, mean {d[ok].mean():.2f}, p90 {np.percentile(d[ok], 90):.2f}, max {d[ok].max():.2f}")
        rg = ok & (rigid > 0)
        print(f"   their 166 skull-fixed points only: {int(rg.sum())} usable, median {np.median(d[rg]):.2f} mm; over 6 mm apart: "
              + ", ".join(f"mp{int(lm[i])} {d[i]:.0f}" for i in np.flatnonzero(ok & (d > 6))[:12]))
        dv = (ours - theirs)[ok] * 1000
        print(f"   mean offset ours - theirs (x left, y back, z up) mm: {dv.mean(0).round(2)}; their points we call unusable: {int((~ok).sum())}")
        grp = {"brow / forehead": g["gr"].get("middle_brow_region"), "nose": g["gr"].get("nose_region"), "chin": g["gr"].get("chin_region")}
        for k, m in grp.items():
            if m is not None:
                s = ok & m[vx.astype(int)]
                if s.any():
                    print(f"     {k:16s} n {int(s.sum()):3d}  median {np.median(d[s]):.2f} mm")
# which of OUR usable front points they don't have (non-rigid: lips, lids) and vice versa
ours_ok = np.flatnonzero(np.isfinite(t["sd"][0]) & (t["sd"][0] < humanfit_map.CUT))
print("our usable front points:", len(ours_ok), "; shared with theirs:", len(set(ours_ok) & set(lm.tolist())), "; theirs only:", len(set(lm.tolist()) - set(ours_ok)))
# their reference cloud vs their own vertices (their README: landmarks sit ~0.7 mm off their vertices)
print("their reference cloud is in their own frame (units m?): extent", np.ptp(ref, 0).round(4))
