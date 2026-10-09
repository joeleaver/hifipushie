"""Why does the desk painting fit at 12 mm? Camera-only fits of pass 6's head on the painting's detector points at
several yaw hints and table classes."""
import numpy as np

import garrett
from hifipushie import humanfit, humanfit_map as fm

b = garrett.hist("om_garrett", 16)["base"]
v = garrett.refs()[1]
st = humanfit.state(b)
det = fm.detector_points(v)
print("detected", None if det is None else det.shape, "size", v["size"], "bbox of detection", det.min(0).round(0), det.max(0).round(0))
tab = fm.table()
for yaw in (-45, -30, -15, 20, 40):
    for cls in (0, 1, 3):
        old = fm.view_class
        fm.view_class = lambda y, c=cls: c
        try:
            _, rep = fm.fit(b, [{**v, "yaw": yaw, "mp478": det}], free=())
            cam = rep["cameras"][0]
            R = humanfit._cam_rot(cam)
            f = R @ np.array([0, -1.0, 0])   # where the face points in the camera's frame
            print(f"yaw hint {yaw:4d} class {fm.CLASSES[cls]:6s}: rms {rep['views'][0]['rms_mm']:5.2f} mm, lens {rep['views'][0]['lens_mm']:.0f}, "
                  f"face direction in camera (x right, z away) {np.round(f, 2)}, head yaw {np.degrees(np.arctan2(f[0], -f[2])):.0f} deg")
        finally:
            fm.view_class = old
