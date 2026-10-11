"""sep.py: where #376 / #540 / gd_T30 / gd_T12 sit in the population on the column measures (percentiles)."""
import json
import numpy as np
G = "/mnt/data/hifipushie/gnmcrease/out/"
S = []
for f in ("gnm_1", "ict_2"):
    S += [s for s in json.loads(str(np.load(G + f"col_{f}.npz")["S"])) if s]
keys = ["h_mid", "h_spread", "h_arch", "depth_mid", "narrow_mid", "narrow_mean", "reach", "lip_mid", "show_mid", "brow_mid", "h_over_brow"]
A = {k: np.array([s[k] for s in S], float) for k in keys}
ref = {"#376": dict(h_mid=2.88, h_spread=7.57, h_arch=-0.25, depth_mid=1.31, narrow_mid=0.49, narrow_mean=0.32, reach=6, lip_mid=0.91, show_mid=2.39, brow_mid=9.49, h_over_brow=0.30),
       "#540": dict(h_mid=2.35, h_spread=0.66, h_arch=-0.54, depth_mid=0.86, narrow_mid=0.40, narrow_mean=0.37, reach=7, lip_mid=0.69, show_mid=1.74, brow_mid=7.68, h_over_brow=0.31),
       "T30": dict(h_mid=4.85, h_spread=1.18, h_arch=-0.55, depth_mid=1.67, narrow_mid=0.68, narrow_mean=0.60, reach=7, lip_mid=0.77, show_mid=4.52, brow_mid=9.00, h_over_brow=0.54),
       "T12": dict(h_mid=4.97, h_spread=1.13, h_arch=-0.57, depth_mid=1.00, narrow_mid=0.26, narrow_mean=0.23, reach=6, lip_mid=0.0, show_mid=4.32, brow_mid=10.07, h_over_brow=0.49)}
print(f"{len(S)} samples; percentile of each value in the population")
print("key          p10    p50    p90  | " + "  ".join(f"{n:>12s}" for n in ref))
for k in keys:
    v = A[k][np.isfinite(A[k])]
    print(f"{k:12s} {np.percentile(v, 10):5.2f} {np.percentile(v, 50):6.2f} {np.percentile(v, 90):6.2f} | " +
          "  ".join(f"{r[k]:6.2f} ({100 * np.mean(v < r[k]):3.0f}%)" for r in ref.values()))
# how common is the 376/540 shape: low crease + narrow valley + parallel
m = (A["h_mid"] < 3.2) & (A["narrow_mean"] > 0.3) & (A["h_spread"] < 1.5)
print("low (<3.2) + narrow (>0.3) + parallel (spread<1.5):", int(m.sum()), "of", len(S))
