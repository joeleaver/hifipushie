"""The GNM head that follows a body vs that body's own MakeHuman head: size and distance."""
import sys
import numpy as np
from scipy.spatial import cKDTree
from hifipushie import base, makehuman, headfit
import quick

S = "/tmp/claude-1000/-home-joe-dev-hifipushie/1d5c679b-4c56-495b-8635-72e86a3b3567/scratchpad/humans3/"
ims, labels = [], []
for age, sex in ((1, 0.5), (3, 0.0)):
    body = {"source": "makehuman", "age": age, "sex": sex}
    b = {"body": body, "eyes": "eyes", "head": {"source": "gnm", "follow_body": True, "seed": 5, "spread": 0.4, "mouth_gap": 0.0}}
    b["head"].update(eval(sys.argv[1]) if len(sys.argv) > 1 else {})
    spec = base.inject({"base": b, "joints": {}})
    h = base.head_of(spec, b)
    tpl = base.source(b)
    P = np.asarray(tpl["P"], float)
    lmb = P[headfit.table()["lm68"]]
    W, lm = h["verts"], h["lm68"]
    c, pn, _ = h["plane"]
    top_b, top_h = P[:, 2].max(), W[:, 2].max()
    hb = top_b - lmb[8][2]
    hh = top_h - lm[8][2]
    up = (W - c) @ pn > 0.01
    d = cKDTree(P).query(W[up])[0]
    io_b = 2 * abs(tpl["face"]["landmarks"]["eye.L"][0])
    print(f"age {age} sex {sex}: stature {top_b:.3f} head height body {hb * 100:.1f} cm, GNM {hh * 100:.1f} ({hh / hb:.3f}); top {100 * (top_h - top_b):+.1f} cm chin {100 * (lm[8][2] - lmb[8][2]):+.1f} cm; "
          f"breadth body {100 * np.ptp(P[P[:, 2] > lmb[27][2]][:, 0]):.1f} GNM {100 * np.ptp(W[W[:, 2] > lm[27][2]][:, 0]):.1f}; depth body {100 * np.ptp(P[P[:, 2] > lmb[27][2]][:, 1]):.1f} GNM {100 * np.ptp(W[W[:, 2] > lm[27][2]][:, 1]):.1f}; "
          f"dist to body's head mean {1000 * d.mean():.1f} mm p95 {1000 * np.percentile(d, 95):.1f}; scale {h['carry']['s']:.3f} io body {io_b * 1000:.1f} plane z {c[2]:.3f} chin z {lm[8][2]:.3f} neck joint z {tpl['J']['neck'][2]:.3f}")
    z0 = lmb[8][2] - 0.12 * top_b / 1.0 * 0.6
    box = ([-0.16 * hb / 0.2, -0.2 * hb / 0.2, lmb[8][2] - 0.6 * hb], [0.16 * hb / 0.2, 0.2 * hb / 0.2, top_b + 0.1 * hb])
    Fb = quick.faces_of(tpl)
    for az in (0, 90):
        bx = (box[0], box[1]) if az == 0 else ([box[0][1], box[0][0], box[0][2]], [box[1][1], box[1][0], box[1][2]])
        ims.append(quick.view(P, Fb, az=az, px_per_m=420 / (1.7 * hb), box=bx))
        labels.append(f"body {age} az{az}")
        ims.append(quick.view(W, h["faces"], az=az, px_per_m=420 / (1.7 * hb), box=bx))
        labels.append(f"GNM {age} az{az}")
from PIL import Image
rows = [quick.row(ims[i:i + 8], labels[i:i + 8]) for i in range(0, len(ims), 8)]
sheet = Image.new("RGB", (max(r.width for r in rows), sum(r.height for r in rows)))
y = 0
for r in rows:
    sheet.paste(r, (0, y))
    y += r.height
sheet.save(S + "heads_cmp.png")
