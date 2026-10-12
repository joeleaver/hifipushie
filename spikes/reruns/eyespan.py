"""eyespan.py <model> ...: per reference view, the distance between the two iris centres on the PICTURE (the detector's
iris points 468 / 473) and on the MODEL (its eye centres + the iris pole, through that view's fitted camera), px and
mm at the model; and the nasion-to-chin length the same way (landmarks 27, 8)."""
import sys
import numpy as np
from PIL import Image
from hifipushie import blockin as bi, humanfit, store
for m in sys.argv[1:]:
    rj = bi._refs(m); st = humanfit.state(store.load(m)["base"])
    L = np.asarray(st["L"], float)
    for vi, (v, cam) in enumerate(zip(rj["views"], rj["cameras"])):
        img = Image.open(v["image"]).convert("RGB")
        P = bi.detect_view(img, v)
        if P is None:
            print(m, vi, "no detection"); continue
        P = np.asarray(P, float)[:, :2]
        mm = float(cam["t"][2]) / cam["f"] * 1000
        q = humanfit.project(cam, L[68:70])
        dp, dm = np.linalg.norm(P[468] - P[473]), np.linalg.norm(q[0] - q[1])
        # detector on the picture vs the model's own 68 landmarks (nasion 27, chin 8 as MediaPipe 168 / 152)
        hp = np.linalg.norm(P[168] - P[152]); hm = np.linalg.norm(humanfit.project(cam, L[[27]])[0] - humanfit.project(cam, L[[8]])[0])
        print(f"{m} view {vi} (yaw {v.get('yaw')}): iris span picture {dp:.1f} px ({dp * mm:.1f} mm) model {dm:.1f} px ({dm * mm:.1f} mm) ratio {dm / dp:.3f} | "
              f"nasion-chin picture {hp:.1f} px model {hm:.1f} px ratio {hm / hp:.3f} | camera: dist {cam['t'][2]:.3f} m f {cam['f']:.0f} mm/px {mm:.4f}")
