"""nosedbg.py: the mid-dorsum section of GNM's mean head and two samples: points in the band (x, z mm)."""
import numpy as np

from hifipushie import faceatlas, faceslide

rng = np.random.default_rng(1)
for c in (np.zeros(120), rng.normal(0, 1, 120)):
    V, J = faceatlas.head(c)
    Th = faceslide.head_template(V)
    X, lm, ext = Th["X"], Th["lm"], Th["ext"]
    y = lm[27][1] + 0.5 * (lm[30][1] - lm[27][1])
    s = ext & (np.abs(X[:, 1] - y) < 0.001) & (np.abs(X[:, 0]) < 0.018)
    P = X[s][np.argsort(X[s][:, 0])]
    print("lm27", np.round(lm[27] * 1000, 1), "lm30", np.round(lm[30] * 1000, 1), "band", s.sum())
    print(" ", [(round(p[0] * 1000, 1), round(p[2] * 1000, 1)) for p in P][:60])
    print("  width", faceatlas._nose_width(X, Th["n"], ext, lm, y, lm[33][1]))
