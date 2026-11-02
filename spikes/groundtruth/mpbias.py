"""mpbias.py <k> ..: what the solve's DIFFERENTIAL detector anchors read AT THE TRUTH (k = lps | h40 | h112 | ph30 ..):
MediaPipe on the picture minus MediaPipe on our clay render of the truth model (the Part 1 fit as a block-in model)
through the TRUE camera, as widths and heights in mm at the head (front-ish views). 0 = the anchors would leave a
correct head alone; + = they ask for a wider / taller feature than the true one. This is the read that sets the nose's
width when dense is off (solve reports: nose_width "carried by landmark front")."""
import json
import sys
import numpy as np
from PIL import Image
from hifipushie import face_ruler as fr, likeness, store

PAIRS = {"nose base width (31-35)": (31, 35, 0), "mouth width (48-54)": (48, 54, 0), "eyes outer (36-45)": (36, 45, 0), "eyes inner (39-42)": (39, 42, 0),
         "jaw width (4-12)": (4, 12, 0), "chin width (6-10)": (6, 10, 0), "upper lip height (51-62)": (51, 62, 1), "lower lip height (66-57)": (66, 57, 1),
         "nose length (27-33)": (27, 33, 1), "philtrum (33-51)": (33, 51, 1), "chin height (57-8)": (57, 8, 1)}
for k in sys.argv[1:]:
    T = f"gt_{k}_AT" if not k.startswith("sc_") else k
    sp = store.load(T)
    rj = json.loads((store.HOME / T / "human_refs.json").read_text())
    head = fr.model_head(sp)
    print(f"\n{k}: detector on the picture - detector on the truth's render, mm (front-ish views)\n")
    cols = []
    for v, cam in zip(rj["views"], rj["cameras"]):
        if abs(fr.view_yaw(cam)) > 30:
            continue
        img = Image.open(v["image"]).convert("RGB")
        ren = fr.clay(head, cam)
        P = likeness.detect([img, ren])
        if P[0] is None or P[1] is None:
            continue
        a, b = np.asarray(P[0])[likeness.MP68][:, :2], np.asarray(P[1])[likeness.MP68][:, :2]
        Xc, _ = fr._cam_points(cam, np.asarray(head["L"], float)[:68])
        mm = float(Xc[:, 2].mean() / cam["f"] * 1000)
        cols.append((v["name"], {n: (abs(a[i, ax] - a[j, ax]) - abs(b[i, ax] - b[j, ax])) * mm for n, (i, j, ax) in PAIRS.items()},
                     {n: abs(b[i, ax] - b[j, ax]) * mm for n, (i, j, ax) in PAIRS.items()}))
    print("| measure | " + " | ".join(f"{c[0]} (on the render: mm)" for c in cols) + " |")
    print("|---|" + "---|" * len(cols))
    for n in PAIRS:
        print(f"| {n} | " + " | ".join(f"{c[1][n]:+.1f} ({c[2][n]:.1f})" for c in cols) + " |")
