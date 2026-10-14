"""smilecal.py <model> ..: MediaPipe's mouthSmile score (mean of left / right) against GNM's "happy" prototype amount, on
CLAY renders of known heads through each model's own front camera (likeness.render, as the differential anchors render
the model): the slope the expression gate uses (face_ruler.SMILE_PER_HAPPY). -> a table on stdout."""
import copy, json, sys
import numpy as np
from hifipushie import blockin as bi, face_ruler as fr, likeness, store

AM = (0.0, 0.1, 0.2, 0.3, 0.45, 0.6)
rows = []
for name in sys.argv[1:]:
    sp = store.load(name)
    rj = bi._refs(name)
    vi = int(np.argmin([abs(fr.view_yaw(c)) for c in rj["cameras"]]))
    cam, v = rj["cameras"][vi], rj["views"][vi]
    box = likeness._box(v["points"], v["size"]) if v.get("points") else None
    sc = []
    for a in AM:
        s2 = copy.deepcopy(sp)
        e0 = dict(s2["base"]["head"].get("expression") or {})
        for k, x in fr.expression_coeffs({"happy": a}).items():
            e0[k] = float(e0.get(k, 0.0)) + x
        s2["base"]["head"]["expression"] = e0
        mesh = likeness.model_mesh(s2["base"])
        im, kk = likeness.render(mesh, cam, box)[:2]
        d = likeness.detect_info([im])[0]
        sc.append(np.nan if d is None else 0.5 * (d["bs"].get("mouthSmileLeft", 0) + d["bs"].get("mouthSmileRight", 0)))
    rows.append(sc)
    print(name, " ".join(f"{a:.2f}:{s:.3f}" for a, s in zip(AM, sc)))
R = np.array(rows)
m = np.nanmean(R, 0)
A = np.array(AM)
k = np.polyfit(A[1:5], m[1:5] - m[0], 1)
print("mean score by amount:", np.round(m, 3), "slope (score per happy, from the neutral render):", round(float(k[0]), 3))
