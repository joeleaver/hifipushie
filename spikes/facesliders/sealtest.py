"""sealtest.py <model> [seals]: lip_seal on a model: humanfit.integrity (broken / warnings) and the contact gap along the
width (mm, GNM frame) per seal value; mouth_gap / interior dropped as the Tess repro does."""
import copy
import sys

import numpy as np

from hifipushie import faceslide, humanfit, onemesh, store

name = sys.argv[1]
seals = [float(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else [0.0, 0.25, 0.5, 1.0]
b0 = store.load(name)["base"]
R = faceslide._lip_rings()
C = R["rings"][R["contact"]]


def gaps(V):
    x = V[C, 0]
    a, b = V[C[np.argmin(x)]], V[C[np.argmax(x)]]
    side = R["upper"][C]
    U, L = C[side], C[~side]
    U, L = U[np.argsort(V[U, 0])], L[np.argsort(V[L, 0])]
    xs = np.linspace(x.min(), x.max(), 21)[1:-1]
    return 1000 * (np.interp(xs, V[U, 0], V[U, 1]) - np.interp(xs, V[L, 0], V[L, 1]))


st0 = None
for s in seals:
    b = copy.deepcopy(b0)
    b["head"]["lip_seal"] = s
    b["head"].pop("mouth_gap", None)
    b["head"].pop("interior", None)
    st = humanfit.state(b)
    st0 = st0 or st
    integ = humanfit.integrity(b, st)
    gp = gaps(np.asarray(onemesh.head_template(b)["carry"]["V"], float))
    print(f"seal {s}: gap mm max {gp.max():.2f} mean {gp.mean():.2f} | ok {integ['ok']} broken {integ['broken']} "
          f"warnings {[w[:80] for w in integ['warnings']][:3]}")
