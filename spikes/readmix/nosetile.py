"""nosetile.py <tag> [view=f]: a close look at the NOSE and MOUTH of one real picture: the scan-fitted GNM's surface
points (red: where the correspondence says each MediaPipe point should be) against MediaPipe's own points (cyan), a few
named points only, joined; and GNM's fitted skin mesh edges round the nose drawn thin (yellow) so the eye can check the
TRUTH against the photo. -> out/nose_<k>_<view>.png"""
import json, os, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
import gt
from gmk import SHORT
from hifipushie import face_ruler as fr, likeness, mpread, store

RM = Path(os.environ["HIFIPUSHIE_READMIX"])
tag = sys.argv[1]
kw = dict(a.split("=") for a in sys.argv[2:])
k = SHORT[tag]
fj = json.loads((gt.WORK / tag / "fit_p1eb3.json").read_text())
fb = json.loads((gt.WORK / tag / "fit_p1b3.json").read_text())
sim = lambda j: (j["S"]["s"], np.asarray(j["S"]["R"]), np.asarray(j["S"]["t"]))
Mj = json.loads((gt.WORK / tag / "model_world.json").read_text())["M"]
X = gt.compose((Mj["s"], np.asarray(Mj["R"]), np.asarray(Mj["t"])), gt.compose(sim(fb), gt.inverse(sim(fj))))
G = gt.gnm()
V = gt.apply(X, gt.verts(np.asarray(fj["c"]), None if fj["e"] is None else np.asarray(fj["e"])))
rj = json.loads((store.HOME / f"gt_{k}_T" / "human_refs.json").read_text())
vi = [v["name"] for v in rj["views"]].index(kw.get("view", "f"))
v, cam = rj["views"][vi], rj["cameras"][vi]
img = Image.open(v["image"]).convert("RGB")
_, P = fr._cam_points(cam, V)
_, q68 = fr._cam_points(cam, G["WL"] @ V)
Pd = likeness.detect_region(img, likeness._box({f"lm{i}": q68[i] for i in range(68)}, img.size))
by = {p["mp"]: p for p in mpread.table()["points"]}
gr = G["gr"]
for name, ctr, ids in (("nose", q68[[30, 31, 35, 33]].mean(0), [129, 358, 98, 327, 64, 294, 2, 1, 4, 48, 278]), ("mouth", q68[[48, 54, 51, 57]].mean(0), list(mpread.LIP_OUTER) + [78, 308, 13, 14])):
    h = 0.75 * np.linalg.norm(q68[36] - q68[45]) * (0.55 if name == "nose" else 0.7)
    x0, y0 = ctr - h
    s = 1100 / (2 * h)
    im = img.crop((int(x0), int(y0), int(x0 + 2 * h), int(y0 + 2 * h))).resize((1100, 1100), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    T = lambda p: tuple((np.asarray(p) - [int(x0), int(y0)]) * s)  # noqa: E731
    reg = gr["nose_region"] if name == "nose" else (gr["upper_lip"] | gr["lower_lip"])
    F = G["F"][reg[G["F"]].all(1)]
    for f in F:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            d.line([T(P[f[a]]), T(P[f[b]])], fill=(255, 235, 0), width=1)
    for m in ids:
        pt = by[m]
        a = np.asarray(pt["w"]) @ P[pt["tri"]]
        b = Pd[m]
        d.line([T(a), T(b)], fill=(255, 255, 255), width=2)
        for p_, col in ((a, (255, 0, 0)), (b, (0, 255, 255))):
            x, y = T(p_)
            d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=col, outline=(0, 0, 0))
    im.save(RM / "out" / f"nose_{k}_{kw.get('view', 'f')}_{name}.png")
    print(RM / "out" / f"nose_{k}_{kw.get('view', 'f')}_{name}.png")
