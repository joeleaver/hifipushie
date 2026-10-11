"""freedom2.py: the lid's freedom GIVEN the rest of the head. Under GNM's prior x ~ N(0, I) (identity 170 [+ the eye's
expression 100]) and the rest of the skin known to sig_h mm (every exterior skin vertex outside the upper lids' rings
1..9, the eyeballs, the margins at 0.05), the posterior covariance of x is (I + Bh' Bh / sig_h^2)^-1. Printed: per ring
the sd left in a row's own motion (mean over the lid's middle, along v and w), the sd of the two-ring reversal
v[k] - v[k+2] that an overhang needs, and how many sd the template's spacing is away from 0 / from a 1 mm overhang."""
import numpy as np

import foldopt as fo
import ohlib as oh

g = oh.g
for ne in (0, 100):
    S = fo.setup(ne)
    B, ch, chR, wc = S["B"], S["ch"], S["chR"], S["wc"]
    nx = len(B)
    print(f"\n=== identity 170 + eye expression {ne} (unit prior) ===")
    for sig in (1e9, 3.0, 1.0, 0.3):
        Q, hm = fo.hold_gram(S, hold=sig, free_rings=(1, 9))
        C = np.linalg.inv(np.eye(nx) + Q)

        def sd(row):
            return float(np.sqrt(row @ C @ row))

        def lin(k, ax):
            return 0.5 * (np.tensordot(B[:, ch[:, k], ax], wc, 1) + np.tensordot(B[:, chR[:, k], ax], wc, 1))
        print(f" rest of the head known to {sig:g} mm:" if sig < 1e8 else " nothing held (the prior alone):")
        print("   ring:            " + " ".join(f"{k:5d}" for k in range(1, 11)))
        print("   sd of v (mm):    " + " ".join(f"{sd(lin(k, 1)):5.2f}" for k in range(1, 11)))
        print("   sd of w (mm):    " + " ".join(f"{sd(lin(k, 2)):5.2f}" for k in range(1, 11)))
        out = []
        for k in range(3, 8):
            R = fo.rows(S, k, k + 2)
            s = sd(R["hang"])
            out.append(f"{k}->{k + 2}: spacing {-R['hang0']:.2f} sd {s:.3f} = {-R['hang0'] / s:.1f} sd to 0, {(1 - R['hang0']) / s:.1f} sd to 1 mm")
        print("   reversal " + "\n            ".join(out))
