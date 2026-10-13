"""widthbias.py [truth models..]: does the detector pull an unusual face toward the average one? On the known-head
benchmark's FRONT pictures, per region: the least-squares scale of the predicted landmarks' x about the face's
mid-line against the truth's (1 = the true width; < 1 on a wide head and > 1 on a narrow one = regression to the
mean), beside the head's true chin / jaw width (GNM mm from GNM's mean). WS=main; HIFIPUSHIE_DENSELM set."""
import sys

import numpy as np
from PIL import Image

from hifipushie import blockin as bi, denselm, face_ruler as fr, likeness, solve_report as sr, store

models = sys.argv[1:] or [f"cz_{t}_T" for t in ("c", "d", "e", "f", "g", "h")]
L = denselm.landmarks()
reg = L["region"][:L["n_skin"]]
rw = sr.rows()
print(f"{'head':10s} true chin_w jaw_w (mm) | x scale pred / true: chin   lips  mouth  cheeks  nose   eyes | y scale chin")
for m in models:
    rj = bi._refs(m)
    spec = store.load(m)
    head = fr.model_head(spec)
    v, cam = rj["views"][0], rj["cameras"][0]
    img = Image.open(v["image"]).convert("RGB")
    _, q68 = fr._cam_points(cam, np.asarray(head["L"], float)[:68])
    pr = denselm.predict(img, q68)
    fr._dense_obs(head, {"cam": cam, "kind": "front"}, pr)
    hv = head["dense_v"]
    _, Q = fr._cam_points(cam, head["V"][hv])
    P = pr["xy"][:len(hv)]
    x0 = Q[:, 0].mean()
    mm = rw["R"] @ bi.identity(spec)
    out = []
    for r in ("chin", "lips", "mouth", "cheeks", "nose", "eyes"):
        k = reg == r
        a, b = Q[k, 0] - x0, P[k, 0] - x0
        out.append(float(a @ b / (a @ a)))
    k = reg == "chin"
    a, b = Q[k, 1] - Q[k, 1].mean(), P[k, 1] - P[k, 1].mean()
    print(f"{m:10s} {mm[rw['names'].index('chin_width')]:+6.1f} {mm[rw['names'].index('jaw_width')]:+6.1f}        |                     "
          + " ".join(f"{x:6.3f}" for x in out) + f" | {float(a @ b / (a @ a)):6.3f}")
