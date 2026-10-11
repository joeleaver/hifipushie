"""regmodes.py: REGIONAL MODES: the principal directions of how a region differs between people with the rest of the
face held (the transplant projector P of drv.transplant: a donor's region onto a head, dc = P (cD - cA); for cD - cA ~
N(0, 2 I) the change's covariance is 2 P P^T). Per region: the variance share of the leading modes, and each mode's
macro loadings (sd per unit; unit = 1 population sd of that mode) -> out/regmodes.npz, out/regmodes.txt"""
import numpy as np

import drv
from hifipushie import humanmacro as hm

out, lines = {}, []
z0 = hm.read(np.zeros(hm.K))
for reg in drv.REGIONS:
    drv.transplant(np.zeros(170), np.zeros(170), reg)
    P = [v for k, v in drv._TP.items() if k[1] == reg][0]
    C = 2 * P @ P.T
    w, U = np.linalg.eigh(C)
    w, U = w[::-1], U[:, ::-1]
    share = np.cumsum(w) / w.sum()
    modes = U[:, :12] * np.sqrt(w[:12])     # unit = 1 sd of the population's regional difference
    # sign: + moves the region forward (out) on average
    R = drv.mask(drv.REGIONS[reg])
    fwd = drv.IBH[:, R, 2].mean(1)
    modes *= np.sign(fwd @ modes + 1e-12)
    out[reg] = modes
    lines.append(f"== {reg}: variance share of modes 1..8: " + " ".join(f"{s:.2f}" for s in share[:8])
                 + f"; total sd {np.sqrt(w.sum()):.2f}")
    for k in range(6):
        z = hm.read(modes[:hm.K, k])
        dz = sorted(((m, z[m] - z0[m]) for m in z), key=lambda t: -abs(t[1]))[:5]
        D = np.tensordot(modes[:, k], drv.IBH, 1) * 1000
        n = np.sqrt((D[R] ** 2).sum(1))
        lines.append(f"   {reg}{k}: |dc| {np.linalg.norm(modes[:, k]):.2f}, region rms {np.sqrt((n**2).mean()):.2f} mm; "
                     + ", ".join(f"{m} {v:+.2f}" for m, v in dz))
np.savez(drv.G / "out" / "regmodes.npz", **out)
(drv.G / "out" / "regmodes.txt").write_text("\n".join(lines))
print("\n".join(lines))
