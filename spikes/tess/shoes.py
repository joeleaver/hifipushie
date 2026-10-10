"""shoes.py <src model with shoes> <dst model> [color hex] [sole hex]: copy the src's simple shoes (blobs of parts socks /
shoes / soles + those parts) onto dst, moved from the src's ankle.L to dst's and scaled by the foot length ratio
(ankle -> toe joint), mirrored by the .L names. Trainers: grey upper, light sole."""
import copy, json, sys

import numpy as np

from hifipushie import paint, store

src, dst = sys.argv[1], sys.argv[2]
col = sys.argv[3] if len(sys.argv) > 3 else "#8d8f93"
sole = sys.argv[4] if len(sys.argv) > 4 else "#e6e4df"
a, b = store.load(src), copy.deepcopy(store.load(dst))


def J(sp):
    return {k: np.asarray(v["pos"], float) for k, v in paint._expanded(sp)["joints"].items() if "pos" in v}


ja, jb = J(a), J(b)
toe = next(k for k in ("toe.L", "toes.L", "ball.L", "foot_tip.L") if k in ja and k in jb)
la = np.linalg.norm(ja[toe] - ja["ankle.L"])
lb = np.linalg.norm(jb[toe] - jb["ankle.L"])
k = lb / la
print("foot joint", toe, "length", round(la, 4), "->", round(lb, 4), "scale", round(k, 3))
for n, bl in a["blobs"].items():
    if bl.get("part") in ("socks", "shoes", "soles"):
        nb = copy.deepcopy(bl)
        at = np.asarray(bl["at"], float)
        nb["at"] = [round(float(x), 4) for x in jb["ankle.L"] + (at - ja["ankle.L"]) * k]
        nb["size"] = [round(float(x) * k, 4) for x in bl["size"]]
        for key in ("round", "blend"):
            if isinstance(nb.get(key), (int, float)):
                nb[key] = round(float(nb[key]) * k, 4)
        b.setdefault("blobs", {})[n] = nb
for p in ("socks", "shoes", "soles"):
    b["parts"][p] = copy.deepcopy(a["parts"][p])
b["parts"]["shoes"]["color"] = col
b["parts"]["shoes"]["roughness"] = 0.7
b["parts"]["soles"]["color"] = sole
b["parts"]["socks"]["color"] = "#d9d7d2"
store.save(dst, b, f"tess: shoes from {src}, scaled {k:.3f}, trainers")
print("saved", dst)
