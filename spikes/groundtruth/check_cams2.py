"""check_cams2.py <pose> <cam> [<cam> ..]: the calibration chain checked by eye: each camera's head picture
(hsrd.head_view: undistorted, turned onto the head) beside the scan's clay through the SAME pipeline camera
(hsrd.pipeline_cam) and their blend -> out/cams2_<pose>.png. The clay must lie on the photo."""
import json
import sys
import numpy as np
from PIL import Image
import gt, hsrd, rast, draw

Image.MAX_IMAGE_PIXELS = None
pose = sys.argv[1]
scan = gt.load_scan(pose)
Lm = np.asarray(json.loads((gt.WORK / pose / "S0.json").read_text())["landmarks_scan"])
ctr = np.nanmean(Lm[[36, 45, 48, 54, 30]], 0)
C = hsrd.cams(pose)
I = (1.0, np.eye(3), np.zeros(3))
rows = []
for n in sys.argv[2:]:
    c = C[n]
    im = Image.open(c["image"]).convert("RGB")
    hv = hsrd.head_view(c, im.size, ctr, out_size=(576, 768), px_per_m=1750.0)
    pic, inside = hsrd.resample(np.asarray(im), hv["map"])
    cam = hsrd.pipeline_cam(hv, I)
    cl = np.asarray(draw.clay(scan["V"], scan["F"], cam, ss=1))
    bl = (0.5 * pic + 0.5 * cl).astype(np.uint8)
    rows.append(draw.label(draw.hstack([Image.fromarray(pic), Image.fromarray(cl), Image.fromarray(bl)]), f"{n}: photo (head view) | scan through the true camera | blend; native {hv['native_px_per_m']:.0f} px/m", sz=22))
draw.vstack(rows).save(gt.OUT / f"cams2_{pose}.png")
print(gt.OUT / f"cams2_{pose}.png")
