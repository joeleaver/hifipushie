"""errmap.py <truth> <model> ...: where a solved head's SHAPE is off the known head (GNM vertices, mm, GNM's frame: x
left, y up, z forward), after a SIMILARITY fit (rotation, shift AND scale) of the solved face onto the true one over the
hockey mask. A slid or nodded face is the camera's business, and so is the head's absolute SIZE: every camera's scale is
free in the solve, so pictures cannot tell a head 4 % larger from a camera 4 % closer (the solved heads come out 2-5 %
large: a size error, not a likeness error). rms and mean per axis over the chin (below the lower lip, within 22 mm of
the midline), the jaw's body (below the lip line, further out), the jaw angle / ramus, the cheeks, the whole face; "low"
= chin + jaw body + jaw angle. regions() / aligned() / rms() / measures() are used by bt.py."""
import sys
import numpy as np
from hifipushie import blockin as bi, gnm_mm, solve_report as sr, store

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


def aligned(c, ct, scale=True):
    """(solved - true) per GNM vertex, mm, after the similarity fit over the hockey mask; the true vertices (mm); the
    scale that lays the solved head on the true one (0.96 = the solved head is 4 % large)."""
    sp = gnm_mm._space()
    A = (sp["T"] + np.tensordot(c, sp["IB"], 1)) * 1000
    B = (sp["T"] + np.tensordot(ct, sp["IB"], 1)) * 1000
    m = sp["gr"]["hockey_mask"]
    a0, b0 = A[m].mean(0), B[m].mean(0)
    U, S, Vt = np.linalg.svd((A[m] - a0).T @ (B[m] - b0))
    D = np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))])
    Rm = U @ D @ Vt
    s = float((S * np.diag(D)).sum() / ((A[m] - a0) ** 2).sum()) if scale else 1.0
    return s * (A - a0) @ Rm + b0 - B, B, s


def rms(c, ct, scale=True):
    D, _, s = aligned(c, ct, scale)
    out = {k: float(np.sqrt((D[v] ** 2).sum(1).mean())) for k, v in regions().items()}
    out["scale"] = s
    return out


def measures(c, scale=1.0):
    """The mm measures (gnm_mm + the chin set) of identity c with the head scaled; macros (sd) as they are."""
    sp = gnm_mm._space()
    V = sp["T"] + np.tensordot(c, sp["IB"], 1)
    r = {**gnm_mm.readers(V), **sr.chin_readers(V)}
    out = {k: float(v) * scale for k, v in r.items()}
    rw = sr.rows()
    for i, n in enumerate(rw["names"]):
        if rw["unit"][i] == "sd":
            out[n] = float(rw["R"][i] @ c)
    return out


if __name__ == "__main__":
    T = gnm_mm._space()["T"] * 1000
    ct = bi.identity(store.load(sys.argv[1]))
    for m in sys.argv[2:]:
        c = bi.identity(store.load(m))
        D, _, s = aligned(c, ct)
        Dm = D.copy()
        Dm[:, 0] *= np.sign(T[:, 0])            # x as OUTWARD (+ = wider) on both sides
        print(f"{m} (scale {s:.3f}): " + "; ".join(f"{k} rms {np.sqrt((D[v] ** 2).sum(1).mean()):.2f} [out {Dm[v, 0].mean():+.1f} up {Dm[v, 1].mean():+.1f} fwd {Dm[v, 2].mean():+.1f}]" for k, v in regions().items()))
