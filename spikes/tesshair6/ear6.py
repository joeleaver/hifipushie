"""ear6.py <model> ...: the ear found on the scalp rays (a bump over the median-smoothed head) against the old
hairline's idea of it (brow_outer + 4 mm, jaw_0's azimuth). map=1 prints the residual map (mm) over the ear window."""
import sys

import numpy as np
from scipy import ndimage

from hifipushie import hair, store


kw_open = 19


def find(sc, thr=0.004, verbose=False):
    R = sc.R
    pad = 24
    Rp = np.concatenate([R[-pad:], R, R[:pad]], 0)
    S = ndimage.grey_opening(Rp, size=(int(kw_open), 1))[pad:-pad]
    D = R - S
    ia = np.nonzero((sc.A >= 50) & (sc.A <= 140))[0]
    ie = np.nonzero((sc.E >= -64) & (sc.E <= 24))[0]
    W = D[np.ix_(ia, ie)]
    if verbose:
        print("     el " + " ".join(f"{e:4.0f}" for e in sc.E[ie][::-1]))
        for k, a in enumerate(sc.A[ia]):
            print(f"az {a:4.0f} " + " ".join(f"{v * 1000:4.0f}" for v in W[k][::-1]))
    M = ndimage.binary_closing(W > thr, iterations=2)
    lab, n = ndimage.label(M)
    if not n:
        return None
    sizes = ndimage.sum(M, lab, range(1, n + 1))
    k = int(np.argmax(sizes)) + 1
    m = lab == k
    AA, EE = np.meshgrid(sc.A[ia], sc.E[ie], indexing="ij")
    P = sc.point(AA[m], EE[m], 0.0) - sc.C
    az, el = AA[m], EE[m]
    return {"cells": int(m.sum()), "top": float(P[:, 2].max()), "bot": float(P[:, 2].min()),
            "az0": float(az.min()), "az1": float(az.max()), "el0": float(el.min()), "el1": float(el.max()),
            "peak": float(W[m].max()), "az_top": float(az[np.argmax(P[:, 2])])}


if __name__ == "__main__":
    names = [a for a in sys.argv[1:] if "=" not in a]
    kw = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
    for m in names:
        spec = store.load(m)
        sc = hair.scalp(m, spec)
        if "lm_brow_outer.L" not in sc.lm:
            print(m, "no landmarks")
            continue
        j0 = np.array(sc.lm["lm_jaw_0.L"]) - sc.C
        azj = float(np.degrees(np.arctan2(j0[0], -j0[1])))
        old = sc.lm["lm_brow_outer.L"][2] - sc.C[2] + 0.004
        e = find(sc, verbose=bool(int(kw.get("map", 0))))
        b = (spec.get("base") or {})
        print(f"{m}: base {(b.get('body') or {}).get('source') or b.get('template')} R med {np.median(sc.R) * 100:.1f} cm | OLD ear top z {old * 100:+.2f} cm, az_j {azj:.0f}"
              f" | lm ear* {[k for k in sc.lm if 'ear' in k]} | FOUND {None if e is None else {k: round(v * 100, 2) if k in ('top', 'bot', 'peak') else v for k, v in e.items()}}")
