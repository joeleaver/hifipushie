"""lockplot.py <model> [<model> ...] [only=part|all]: the gather locks' lines from five sides WITHOUT Blender (1 s):
$TOUT/locks_<model>.png. Head locks brown (the ones rooted on the parting RED: Joe's lines), tail blue, wisps grey;
the head as skin dots. Second row: the same five views with only every lock's HEIGHT off the scalp as colour is not
drawn; instead prints the stand-off of the top layer (max h over locks) at the crown / side / nape."""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import hair, store

names = [a for a in sys.argv[1:] if "=" not in a]
kw = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
for m in names:
    sp = store.load(m)
    sc = hair.scalp(m, sp)
    L = sp["hair"]["locks"]
    A, E = np.meshgrid(np.arange(0, 360, 5.0), np.arange(-60, 90, 5.0))
    H = sc.point(A.ravel(), E.ravel(), 0.0) - sc.C
    views = {"front": ([1, 0, 0], [0, 0, 1], [0, -1, 0]), "left": ([0, 1, 0], [0, 0, 1], [1, 0, 0]),
             "back": ([-1, 0, 0], [0, 0, 1], [0, 1, 0]), "top": ([1, 0, 0], [0, 1, 0], [0, 0, 1]),
             "right": ([0, -1, 0], [0, 0, 1], [-1, 0, 0])}
    N, k = 560, 560 / 0.42
    im = Image.new("RGB", (N * 5, N), "white")
    dr = ImageDraw.Draw(im)
    hs = {"crown": [], "side": [], "nape": []}
    for n, lk in L.items():
        if lk.get("space") == "xyz" or lk.get("hairs"):
            continue
        p = np.asarray(lk["pts"], float)
        for a_, e_, h_ in p:
            fa = abs(((a_ + 180) % 360) - 180)
            (hs["crown"] if e_ > 55 else hs["nape"] if (fa > 120 and e_ < 15) else hs["side"] if (60 < fa < 120 and 10 < e_ < 45) else []).append(h_)
    print(m, "top layer (95th pct of lock heights, mm):", {k_: round(1000 * float(np.percentile(v, 95)), 1) for k_, v in hs.items() if v},
          "median:", {k_: round(1000 * float(np.median(v)), 1) for k_, v in hs.items() if v})
    for vi, (vn, (ex, ey, ez)) in enumerate(views.items()):
        ex, ey, ez = (np.asarray(v, float) for v in (ex, ey, ez))
        px = lambda P: np.stack([vi * N + N / 2 + (P @ ex) * k, N * 0.36 - (P @ ey) * k], 1)  # noqa: E731
        for q in px(H[H @ ez > 0]):
            dr.ellipse([q[0] - 2, q[1] - 2, q[0] + 2, q[1] + 2], fill="#e2c4ac")
        order = sorted(L.items(), key=lambda kv: "g1_" in kv[0] and abs(np.asarray(kv[1]["pts"])[0][0] % 360 - 0) < 0)
        for n, lk in order:
            P = hair.lock_world(sc, lk, lk["pts"]) - sc.C
            if lk.get("space") != "xyz" and len(P) >= 4:
                from hifipushie import hair_cards as hc
                P = hc.spine({**lk, "pts": P.tolist()}, 48)[0]
            part = lk.get("space") != "xyz" and abs(P[0][0] - 0.0) < 0.012 and P[0][1] < -0.02 and P[0][2] > 0.04
            if kw.get("only") == "part" and not part and not lk.get("free"):
                continue
            c = "#999" if lk.get("hairs") else "#247" if lk.get("free") else "#e11" if part else "#532"
            Q = px(P)
            for j in range(len(P) - 1):
                if P[j] @ ez > -0.01 and P[j + 1] @ ez > -0.01:
                    dr.line([tuple(Q[j]), tuple(Q[j + 1])], fill=c, width=3 if part else 1)
        dr.text((vi * N + 8, 6), f"{m} {vn}", fill="black")
    im.save(f"{os.environ['TOUT']}/locks_{m}.png")
    print("plot", f"{os.environ['TOUT']}/locks_{m}.png")
