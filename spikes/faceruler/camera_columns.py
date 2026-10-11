"""t6.py: is a camera perturbation spanned by the nuisance columns? Same head, picture through a perturbed camera."""
import numpy as np
from hifipushie import face_ruler as fr

rng = np.random.default_rng(5)
c = rng.normal(size=170)
A = fr.gnm_head(c)
for trial, (dx, dy, sc, roll) in enumerate([(3, 0, 0, 0), (0, 3, 0, 0), (0, 0, 2, 0), (0, 0, 0, 1.5), (2, -3, 1.5, -1)]):
    for k in ("front", "profile"):
        cam = fr.camera(k)
        cp = dict(cam)
        cp["t"] = [dx * 1e-3, dy * 1e-3, cam["t"][2]]
        cp["f"] = cam["f"] * (1 + sc * 0.01)
        cp["r"] = [0.0, 0.0, float(np.radians(roll))]
        views = [{"img": fr.clay(A, cp), "cam": cam, "kind": k, "style": "clay"}]
        obs = fr.observe(A, views)
        o = np.array([ob["o"] for ob in obs])
        C, _ = fr._cam_columns(obs, views, fr.CAM_SD)
        th, *_ = np.linalg.lstsq(C, o, rcond=None)
        res = o - C @ th
        print((dx, dy, sc, roll), k, f"n {len(o)} |o| rms {np.sqrt((o ** 2).mean()):.2f} -> residual {np.sqrt((res ** 2).mean()):.2f}  fitted (dx, dy, scale %, roll deg) {np.round(th, 2)}")
