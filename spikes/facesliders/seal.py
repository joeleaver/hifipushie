"""seal.py [model]: the lips' contact along the width (GNM frame, mm: lower - upper contact ring y, per x across
the mouth's middle 90%) for lip_seal 0 / 0.5 / 1, and with a jaw-opening expression on top of the seal."""
import copy
import sys

import numpy as np

from hifipushie import base as basemod
from hifipushie import faceslide, humans, onemesh, store

b0 = store.load(sys.argv[1])["base"] if len(sys.argv) > 1 else humans.spec(age=40, sex=1.0, seed=None, skin=False,
                                                                           source="human")["base"]
R = faceslide._lip_rings()
C = R["rings"][R["contact"]]


def gaps(V):
    x = V[C, 0]
    a, b = V[C[np.argmin(x)]], V[C[np.argmax(x)]]
    side = (V[C, 1] - (a[1] + (x - a[0]) / (b[0] - a[0]) * (b[1] - a[1]))) > 0
    U, L = C[side], C[~side]
    U, L = U[np.argsort(V[U, 0])], L[np.argsort(V[L, 0])]
    xs = np.linspace(x.min(), x.max(), 21)[1:-1]
    return 1000 * (np.interp(xs, V[U, 0], V[U, 1]) - np.interp(xs, V[L, 0], V[L, 1]))  # + = apart


g = basemod._gnm_data()
X0 = np.asarray(g["template_vertex_positions"], float)
lower = [i for i, n in enumerate(g["expression_names"]) if str(n).startswith("lower_face")]
opening = [float(np.mean(gaps(X0 + 0.5 * g["expression_basis"][i]) - gaps(X0))) for i in lower]
jaw = [lower[int(np.argmax(opening))]]
print("the most opening lower-face component:", str(g["expression_names"][jaw[0]]), round(max(opening), 2), "mm at 0.5")
for seal, expr in ((0.0, None), (0.5, None), (1.0, None), (1.0, "jaw")):
    b = copy.deepcopy(b0)
    b.setdefault("head", {})["lip_seal"] = seal
    b["head"].pop("mouth_gap", None)
    if expr:
        b["head"]["expression"] = {str(g["expression_names"][jaw[0]]): 1.0}
    ht = onemesh.head_template(b)
    gp = gaps(np.asarray(ht["carry"]["V"], float))
    print(f"seal {seal} {expr or ''}: gap mm min {gp.min():.2f} max {gp.max():.2f} mean {gp.mean():.2f}")
D = faceslide.seal_delta(X0, 1.0)
print("template alone: before", gaps(X0).round(2).tolist())
print("template alone: after ", gaps(X0 + D).round(2).tolist())
