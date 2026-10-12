"""lidgroove.py <model> ..: where GNM's OWN upper-lid groove lies against the fold layer's lid_fold line (skin_folds'
landmark path, no shift): per side, the head's own crease across the path (skin_folds.own_crease on the fold-free
skin: the most concave point within 4 mm, a quadratic through the stations that have one) in mm, + = above the
layer's line (away from the lashes); share = stations where the skin is concave enough to call a crease; and the
groove's raw depth of curvature (max d2h/du2 at a 2 mm scale, 1/mm x 1000) at inner / middle / outer thirds."""
import sys

import numpy as np
from scipy.ndimage import gaussian_filter1d

from hifipushie import skin_folds as sf, skin_look, store

for m in sys.argv[1:]:
    spec = store.load(m)
    J = skin_look._J(spec)
    S = sf.surface(spec, "body", J)
    pt = sf.paths(None, "body", J, names=["lid_fold"], S=S)
    for (nm, sd), p in pt.items():
        P, ac, nrm = p["P"], p["across"], p["normal"]
        off, share = sf.own_crease(S, P, ac, nrm, 4.0)
        du = 0.5
        u = np.arange(-7.0, 7.0 + 1e-6, du)
        X = S.seat((P[:, None, :] + 0.001 * u[None, :, None] * ac[:, None, :]).reshape(-1, 3)).reshape(len(P), len(u), 3)
        h = ((X - P[:, None, :]) * nrm[:, None, :]).sum(-1) * 1000.0
        h = gaussian_filter1d(gaussian_filter1d(h, 2.0 / du, axis=1, mode="nearest"), 2.0, axis=0, mode="nearest")
        d2 = np.gradient(np.gradient(h, du, axis=1), du, axis=1)
        inner = np.abs(u) <= 4.0
        k = np.argmax(np.where(inner[None, :], d2, -np.inf), 1)
        n = len(P)
        th = [slice(0, n // 3), slice(n // 3, 2 * n // 3), slice(2 * n // 3, n)]
        print(f"{m} lid_fold{sd}: own groove vs the layer's line (mm, + up) inner / middle / outer "
              f"{' / '.join(f'{np.median(u[k][s]):+.1f}' for s in th)}; fitted (own_crease) {' / '.join(f'{np.median(off[s]):+.2f}' for s in th)}; "
              f"share {share:.2f}; concavity x1000 {' / '.join(f'{1000 * np.median(d2[np.arange(n), k][s]):.0f}' for s in th)} (SNAP_CURV {1000 * sf.SNAP_CURV:.0f})")
