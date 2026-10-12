"""gnmnative: GNM's tongue components: how far each moves the tongue, where, and which way."""
import numpy as np

from hifipushie import base as basemod

g = basemod._gnm_data()
G = {k: np.asarray(v) > 0.5 for k, v in g["groups"].items()}
T = g["template_vertex_positions"].astype(float)
E = g["expression_basis"]
enm = [str(x) for x in g["expression_names"]]
tg = np.flatnonzero(G["tongue"])
P = T[tg] * 1000
print("tongue bbox mm", P.min(0).round(1), P.max(0).round(1), "centroid", P.mean(0).round(1))
# the blade's front: the front 10 % along z
front = tg[P[:, 2] > np.percentile(P[:, 2], 92)]
print("front set", len(front), "mean", (T[front].mean(0) * 1000).round(1))
for i, n in enumerate(enm):
    if not n.startswith("tongue"):
        continue
    D = E[i][tg] * 1000
    k = np.argmax(np.linalg.norm(D, axis=1))
    print(f"{n:12s} max {np.linalg.norm(D, axis=1).max():6.2f} mm at {P[k].round(0)} dir {(D[k] / np.linalg.norm(D[k])).round(2)}; "
          f"front set mean move {(E[i][front].mean(0) * 1000).round(2)}; rms {np.sqrt((D ** 2).sum(1).mean()):.2f}")
li = [i for i, n in enumerate(enm) if n.startswith("lower_face")]
mv = [(enm[i], np.linalg.norm(E[i][front].mean(0)) * 1000) for i in li]
print("lower_face comps moving the tongue's front most:", sorted(mv, key=lambda t: -t[1])[:6])
