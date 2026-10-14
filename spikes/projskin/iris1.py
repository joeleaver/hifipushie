"""iris1.py <src with references> <model to set> ...: the iris read alone (no atlas made): each front-ish view's profile, the
zones, the calibrated skin.eyes values; written onto the named models' skin.eyes (iris, iris_inner, limbal). LIGHT.
The lightness gain = the model's atlas tone gain when it has a projection report, else 1 (the picture's exposure)."""
import json, sys
import numpy as np
from PIL import Image
from hifipushie import blockin as bi, face_ruler as fr, skin_project as sp, store
src = sys.argv[1]
rj = bi._refs(src)
from hifipushie import skin
targets = [a for a in sys.argv[2:] if "=" not in a]
sp0 = store.load(targets[0] if targets else src)
e0 = sp0["skin"].get("eyes") if isinstance(sp0["skin"].get("eyes"), dict) else {}
yt = float(sp._lin(np.asarray(skin.tone_rgb(skin.params(sp0)["tone"]), float)) @ sp.Y)
profs, gains = [], []
for vi, (v, cam) in enumerate(zip(rj["views"], rj["cameras"])):
    if cam is None or abs(fr.view_yaw(cam)) > sp.IRIS_YAW:
        continue
    img = Image.open(v["image"]).convert("RGB")
    p = sp.iris_profile(img, v)
    if p is None:
        print("view", vi, "NOT READ"); continue
    # the skin under the eye in this picture (MediaPipe's infraorbital points): its luminance against the model's tone = the gain
    P = np.asarray(bi.detect_view(img, v), float)[:, :2]
    a = sp._lin(np.asarray(img, float) / 255.0)
    ys = []
    for i in (230, 231, 232, 450, 451, 452):
        x, y = int(round(P[i, 0])), int(round(P[i, 1]))
        ys.append(float(np.median(a[max(y - 4, 0):y + 5, max(x - 4, 0):x + 5].reshape(-1, 3) @ sp.Y)))
    g = yt / max(float(np.median(ys)), 1e-4)
    print("view", vi, {k: round(float(p[k]), 2) for k in ("radius_px", "pupil", "open")}, "gain", round(g, 3))
    profs.append(p); gains.append(np.ones(3) * g)
r = sp.iris_read(profs, gains, e0)
print(r["text"] if r else "NOT READ")
for m in [a for a in sys.argv[2:] if "=" not in a]:
    s = store.load(m)
    e = dict(s["skin"].get("eyes") or {})
    was = {k: e.get(k) for k in ("iris", "iris_inner", "limbal")}
    e.update(iris=r["iris"], iris_inner=r["iris_inner"], limbal=r["limbal"])
    s["skin"]["eyes"] = e
    store.save(m, s, "the iris from the picture: two zones + limbal ring (skin_project.iris_read)", checked=False)
    print(m, was, "->", {k: e[k] for k in ("iris", "iris_inner", "limbal")})
