"""aperture.py <model> <label=face png (ours, eyeshot's front close-up)> ...: the eye aperture by the 478-point detector
(likeness_eyes.measures, as facesliders' eyedbg.py): opening, width, iris radius, cover, white below, canthal tilt
and the corner angles, per eye (subject's right, left), mm at the model's own scale (the fitted camera's px/mm at the
eyes). A label 'photo=<pair png>' measures the reference half of an eyeshot pair at the same scale."""
import json
import sys

import numpy as np
from PIL import Image

import stage
from hifipushie import likeness, likeness_eyes as le
from hifipushie import store
from hifipushie.spec import expand_mirror

CORNERS = {"inner": ((133, 173, 155), (362, 398, 382)), "outer": ((33, 246, 7), (263, 466, 249))}
name = sys.argv[1]
spec = store.load(name)
J = {k: np.asarray(v["pos"], float) for k, v in expand_mirror(spec)["joints"].items() if "pos" in v}
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
v, cam = refs["views"][0], refs["cameras"][0]
U = np.array(list(v["points"].values()), float)
lo, hi = U.min(0), U.max(0)
s = 0.95 * (hi - lo)[0]
c = np.array([0.5 * (lo[0] + hi[0]), lo[1] + 0.55 * (hi[1] - lo[1])])
fr = stage.fitted_frame(cam, [c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2], "zoom")
eyes = 0.5 * (J["eye.L"] + J["eye.R"])
dist = float(np.linalg.norm(eyes - np.asarray(fr["eye"])))


def angle(P, c_, a, b):
    u, w = P[a] - P[c_], P[b] - P[c_]
    return float(np.degrees(np.arccos(np.clip(u @ w / np.linalg.norm(u) / np.linalg.norm(w), -1, 1))))


rows = {}
for arg in sys.argv[2:]:
    lab, p = arg.split("=", 1)
    im = Image.open(p).convert("RGB")
    if lab == "photo":
        im = im.crop((0, 0, im.width // 2, im.height))
    elif im.width == 2 * im.height:
        im = im.crop((im.width // 2, 0, im.width, im.height))
    mmpx = 2 * dist * np.tan(np.radians(fr["fov"]) / 2) * 1000 / im.width
    d = likeness.detect([im])[0]
    if d is None:
        print(lab, "no face found")
        continue
    P = np.asarray(d["P"] if isinstance(d, dict) else d, float)[:, :2]
    ms = le.measures(P, mmpx)
    out = {k: ms[k] for k in ("open", "width", "iris_r", "cover", "white_below", "canthal_tilt")}
    for nm, ids in CORNERS.items():
        out[f"{nm}_angle"] = [round(angle(P, *t), 1) for t in ids]
    rows[lab] = out
    print(f"{lab:>10}: " + "  ".join(f"{k} {v[0]:.2f}/{v[1]:.2f}" for k, v in out.items()))
if len(rows) > 1:
    ks = list(rows)
    a = rows[ks[0]]
    for b_ in ks[1:]:
        print(f"{b_} - {ks[0]}: " + "  ".join(f"{k} {np.mean(rows[b_][k]) - np.mean(a[k]):+.2f}" for k in a))
