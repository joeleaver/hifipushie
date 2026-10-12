"""errmap.py <truth> <model> ...: where a solved head's SURFACE is off the known head (GNM vertices, mm, GNM's frame: x
left, y up, z forward), after a rigid fit (rotation + shift, no scale) of the solved face onto the true one over the
hockey mask (a slid or nodded face is the camera's business, not a shape error): rms and mean per axis over the chin
(below the lower lip, within 22 mm of the midline), the jaw's body (below the lip line, further out), the jaw angle /
ramus, the cheeks, the whole face; "low" = chin + jaw body + jaw angle. regions() / aligned() are used by cchain.py."""
import sys
import numpy as np
from hifipushie import blockin as bi, gnm_mm, store

_C = {}


def regions():
    if "R" not in _C:
        sp = gnm_mm._space()
        T = sp["T"] * 1000
        L = sp["WL"] @ T
        gr = sp["gr"]
        face = gr["hockey_mask"] & gr["skin_exterior"]
        low = face & (T[:, 1] < L[57, 1])
        R = {"chin": low & (np.abs(T[:, 0]) < 22), "jaw body": low & (np.abs(T[:, 0]) >= 22) & (T[:, 2] > L[4, 2] + 15),
             "jaw angle": face & (T[:, 1] < 0.5 * (L[1, 1] + L[2, 1])) & (T[:, 2] <= L[4, 2] + 15),
             "cheeks": face & (T[:, 1] >= L[57, 1]) & (T[:, 1] < L[29, 1]) & (np.abs(T[:, 0]) > 18), "face": gr["hockey_mask"]}
        R["low"] = R["chin"] | R["jaw body"] | R["jaw angle"]
        _C["R"] = R
    return _C["R"]


def aligned(c, ct):
    """(solved - true) per GNM vertex, mm, after the rigid fit over the hockey mask; + the true vertices (mm)."""
    sp = gnm_mm._space()
    A = (sp["T"] + np.tensordot(c, sp["IB"], 1)) * 1000
    B = (sp["T"] + np.tensordot(ct, sp["IB"], 1)) * 1000
    m = sp["gr"]["hockey_mask"]
    a0, b0 = A[m].mean(0), B[m].mean(0)
    U, _, Vt = np.linalg.svd((A[m] - a0).T @ (B[m] - b0))
    Rm = (U @ np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))]) @ Vt)
    return (A - a0) @ Rm + b0 - B, B


def rms(c, ct):
    D, _ = aligned(c, ct)
    return {k: float(np.sqrt((D[v] ** 2).sum(1).mean())) for k, v in regions().items()}


if __name__ == "__main__":
    T = gnm_mm._space()["T"] * 1000
    ct = bi.identity(store.load(sys.argv[1]))
    for m in sys.argv[2:]:
        c = bi.identity(store.load(m))
        D, _ = aligned(c, ct)
        Dm = D.copy()
        Dm[:, 0] *= np.sign(T[:, 0])            # x as OUTWARD (+ = wider) on both sides
        print(f"{m}: " + "; ".join(f"{k} rms {np.sqrt((D[v] ** 2).sum(1).mean()):.2f} [out {Dm[v, 0].mean():+.1f} up {Dm[v, 1].mean():+.1f} fwd {Dm[v, 2].mean():+.1f}]" for k, v in regions().items()))
