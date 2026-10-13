"""alar_eval.py <truth model> ..: the alar-edge read AT THE TRUTH (a truth model: identity = the scan's direct fit, its
views through the rig's TRUE cameras): per front view and side, where each FEATURE ("valley", "edge") lies against the
model's true wing contour (mm, + = outside). Train subjects set ALAR_BIAS; held-out ones score it. Also a tile per view
(out/alar_<model>_<view>.png: the contour vertices red, each feature's place cyan / yellow) to LOOK at."""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import blockin as bi, face_ruler as fr, store

RM = os.environ["HIFIPUSHIE_READMIX"]
res = {}
for name in sys.argv[1:]:
    head = fr.model_head(store.load(name))
    rj = bi._refs(name)
    for v, cam in zip(rj["views"], rj["cameras"]):
        if abs(fr.view_yaw(cam)) > fr.ALAR_TURN:
            continue
        img = Image.open(v["image"]).convert("RGB")
        prs = fr.alar_profiles(head, cam, img)
        im = img.copy()
        d = ImageDraw.Draw(im)
        line = []
        for pr in prs:
            for feat, col in (("valley", (0, 255, 255)), ("edge", (255, 255, 0))):
                f = [fr.alar_feature(pp, pr["t"], feat) for pp in pr["prof"]]
                ok = [x[0] for x in f if x is not None]
                if ok:
                    res.setdefault((name, feat), []).append(float(np.median(ok)))
                    line.append(f"{'RL'[pr['side']]} {feat} {np.median(ok):+.2f} (n {len(ok)}/{len(f)})")
                for p_, x in zip(pr["px"], f):
                    if x is not None:
                        q = p_ + np.asarray(pr["u"]) * x[0] / pr["mm1"]
                        d.ellipse([q[0] - 2, q[1] - 2, q[0] + 2, q[1] + 2], fill=col)
            for p_ in pr["px"]:
                d.ellipse([p_[0] - 2, p_[1] - 2, p_[0] + 2, p_[1] + 2], fill=(255, 0, 0))
        print(f"{name} {v['name']} turn {abs(fr.view_yaw(cam)):.0f}: " + ("; ".join(line) or "NOTHING"))
        if prs:
            c = np.mean([pr["px"].mean(0) for pr in prs], 0)
            h = 18.0 / prs[0]["mm1"]
            im.crop((int(c[0] - 1.6 * h), int(c[1] - h), int(c[0] + 1.6 * h), int(c[1] + h))).resize((960, 600), Image.LANCZOS).save(f"{RM}/out/alar_{name}_{v['name']}.png")
for feat in ("valley", "edge"):
    allv = [x for (n, f), xs in res.items() if f == feat for x in xs]
    if allv:
        print(f"{feat}: n {len(allv)} mean {np.mean(allv):+.2f} sd {np.std(allv):.2f}; per model " + ", ".join(f"{n} {np.mean(xs):+.2f}" for (n, f), xs in res.items() if f == feat))
json.dump({f"{n}|{f}": xs for (n, f), xs in res.items()}, open(f"{RM}/out/alar_eval_{'_'.join(sys.argv[1:])[:60]}.json", "w"))
