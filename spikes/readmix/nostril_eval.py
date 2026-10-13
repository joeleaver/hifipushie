"""nostril_eval.py <k> [<k> ..]: the nostril read AT THE TRUTH: groundtruth's gt_<k>_T models (identity = the Part 1
direct fit, the rig's true cameras): per near-frontal view each read's value (mm; 0 = unbiased), the picture's nostril
outer width against the truth rim's, and a tile (out/nostril_<k>_<view>.png: the model's rim yellow, the picture's
opening ends cyan) to LOOK at."""
import os, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import blockin as bi, face_ruler as fr, store

RM = Path(os.environ["HIFIPUSHIE_READMIX"])
allo = {"lateral": [], "medial": []}
for k in sys.argv[1:]:
    name = f"gt_{k}_T"
    head = fr.model_head(store.load(name))
    rj = bi._refs(name)
    for v, cam in zip(rj["views"], rj["cameras"]):
        if abs(fr.view_yaw(cam)) > fr.NOSTRIL_TURN:
            continue
        img = Image.open(v["image"]).convert("RGB")
        view = {"img": img, "cam": cam, "kind": "front"}
        obs = fr._nostril_obs(head, view)
        txt = "; ".join(f"{ob['name'][8:]} {ob['o']:+.2f}" for ob in obs)
        w = None
        lat = {ob["name"][8]: ob for ob in obs if ob["name"].endswith("lateral")}
        if len(lat) == 2:
            w = -lat["r"]["o"] + lat["l"]["o"] if False else (lat["l"]["o"] + lat["r"]["o"])
        print(f"{k} {v['name']} (turn {abs(fr.view_yaw(cam)):.0f}, pitch {fr.view_pitch(cam):+.0f}): {txt or 'NOT READ'}" + (f" | outer width picture - truth {w:+.2f} mm" if w is not None else ""))
        for ob in obs:
            allo[ob["name"].split("_")[-1]].append(ob["o"])
        rims = fr.nostril_rims(head)
        _, P = fr._cam_points(cam, np.asarray(head["V"], float)[np.r_[rims[0], rims[1]]])
        c = P.mean(0)
        h = 22 / (cam["t"][2] / cam["f"] * 1000)
        s = 900 / (2 * h)
        im = img.crop((int(c[0] - h), int(c[1] - h), int(c[0] + h), int(c[1] + h))).resize((900, 900), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        T = lambda p: tuple((np.asarray(p) - [int(c[0] - h), int(c[1] - h)]) * s)  # noqa: E731
        for p in P:
            x, y = T(p)
            d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(255, 235, 0))
        for ob in obs:
            x, y = T(ob["q"])
            d.line([x, y - 14, x, y + 14], fill=(0, 255, 255), width=3)
            x, y = T(ob["p"])
            d.ellipse([x - 5, y - 5, x + 5, y + 5], outline=(255, 0, 0), width=2)
        im.save(RM / "out" / f"nostril_{k}_{v['name']}.png")
for nm, x in allo.items():
    if x:
        print(f"{nm}: n {len(x)} mean {np.mean(x):+.2f} sd {np.std(x):.2f} rms {np.sqrt(np.mean(np.square(x))):.2f}")
