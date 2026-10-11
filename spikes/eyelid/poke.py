"""poke.py <tag> ...: does OUR eyeball come through the upper lid? On surf.py's height maps (out/surf_<tag>.npz): the
lid skin's stand-off from the seated ball over the platform (above the margin, v up to 9 mm, |u| <= 9): min, the area
under 0 (mm2: the ball shows through) and under 0.15."""
import os
import sys

import numpy as np

G = os.environ["G"] + "/out"
for tag in sys.argv[1:]:
    z = np.load(f"{G}/surf_{tag}.npz")
    U, V, W, r, M = z["U"], z["V"], z["W"], float(z["r"]), z["M"]
    UU, VV = np.meshgrid(U, V)
    S = np.sqrt(UU ** 2 + VV ** 2 + W ** 2) - r
    mv = np.interp(UU, M[:, 0], M[:, 1])
    m = (np.abs(UU) <= 9) & (VV > mv + 1.0) & (VV < mv + 7) & np.isfinite(S) & (S > -1.5)   # (the map's edge at the opening reads the lining: -6)
    cell = (U[1] - U[0]) * (V[1] - V[0])
    i = np.argmin(np.where(m, S, 9))
    print(f"{tag:6s} platform stand-off from our ball: min {S[m].min():+.2f} mm at u {UU.flat[i]:+.1f} v {VV.flat[i]:+.1f}; under 0: {(S[m] < 0).sum() * cell:.1f} mm2; under 0.15: {(S[m] < 0.15).sum() * cell:.1f} mm2; median {np.median(S[m]):.2f}")
