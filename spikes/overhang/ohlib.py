"""ohlib.py: the upper lid's rings as LINEAR functions of GNM's coefficients (library for the overhang study).
Left eye, GNM frame in mm: x = the subject's left (u), y up (v), z forward (w). Ring 0 = the lid margin, ring k = k
edges out (lidmap.topo). A lid vertex's "up" neighbours are its edge neighbours on ring k + 1."""
import numpy as np

import lidmap as lm
from hifipushie import gnm_controls as gc

g = gc.gnm()
t = lm.topo()
T = g["T"] * 1000.0
JL = g["J"][2] * 1000.0
RINGS = range(0, 13)


def upper(k, umax=None):
    """Upper-half vertex ids of ring k, sorted by x; umax: only |x - eye centre| < umax mm (the lid's middle)."""
    ids = t["loops"][k]
    ids = ids[g["T"][ids, 1] > g["J"][2][1] + 0.0005]
    ids = ids[np.argsort(T[ids, 0])]
    if umax is not None:
        ids = ids[np.abs(T[ids, 0] - JL[0]) < umax]
    return ids


def up(v):
    """Edge neighbours of vertex v on the next ring out."""
    k = t["ring"][v]
    return [b for b in t["nb"][v] if t["ring"][b] == k + 1]


def chains(umax=7.0, k0=0, k1=12):
    """Radial chains up the lid: from each ring-k0 vertex within umax, follow the up neighbour nearest in x.
    Returns (n, k1 - k0 + 1) vertex ids."""
    out = []
    for v in upper(k0, umax):
        ch = [int(v)]
        while t["ring"][ch[-1]] < k1:
            nb = up(ch[-1])
            if not nb:
                break
            ch.append(int(min(nb, key=lambda b: abs(T[b, 0] - T[ch[-1], 0]))))
        if len(ch) == k1 - k0 + 1:
            out.append(ch)
    return np.array(out)


def basis(ids, n=170, expr=False):
    """(n, len(ids), 3) mm per unit coefficient at the vertices."""
    B = g["EB"] if expr else g["IB"]
    return B[:n][:, ids].astype(np.float64) * 1000.0


def verts(c=None, e=None):
    return gc.vertices(c, e) * 1000.0


def profile(V, ch):
    """Per chain: v (height), w (forward) per ring (raw mm)."""
    return V[ch][..., 1], V[ch][..., 2]


def read(V, ch=None):
    """Fold numbers of a head on the chains. Per chain:
      hang   mm: max over rings a < b (b within 5 rings) of v[a] - v[b] with b's skin FORWARD of a's: the front-view
             overhang depth (skin of ring b hangs below, and in front of, the skin of ring a)
      ka, kb the rings of that pair (ka = the crease ring)
      turn   deg: the largest turn between successive segments of the (v, w) section at rings 2..9; kt its ring
      h      height over the margin (ring 0) of the crease ring (ka with an overhang, else kt)."""
    ch = chains() if ch is None else ch
    v, w = profile(V, ch)
    n, m = v.shape
    hang = np.zeros(n)
    ka = np.zeros(n, int)
    kb = np.zeros(n, int)
    for a in range(1, m - 1):
        for b in range(a + 1, min(a + 6, m)):
            d = np.where(w[:, b] > w[:, a], v[:, a] - v[:, b], -np.inf)
            better = d > hang
            hang[better], ka[better], kb[better] = d[better], a, b
    sv, sw = np.diff(v, axis=1), np.diff(w, axis=1)
    ang = np.unwrap(np.arctan2(sw, sv), axis=1)      # 0 = straight up, +90 deg = forward, 180 = straight down
    tr = np.degrees(np.diff(ang, axis=1))[:, 1:9]    # turns at rings 2..9
    kt = 2 + tr.argmax(1)
    hk = np.where(hang > 0, ka, kt)
    h = v[np.arange(n), hk] - v[:, 0]
    return {"hang": hang, "ka": ka, "kb": kb, "turn": tr.max(1), "kt": kt, "h": h,
            "hang_mean": float(hang.mean()), "hang_max": float(hang.max()), "hang_frac": float((hang > 0.1).mean()),
            "turn_mean": float(tr.max(1).mean()), "h_mean": float(h.mean()), "k_mode": int(np.bincount(hk).argmax())}


def fmt(q):
    return (f"hang mean {q['hang_mean']:.2f} max {q['hang_max']:.2f} mm ({q['hang_frac'] * 100:.0f} % of columns > 0.1), "
            f"turn {q['turn_mean']:.0f} deg, crease ring {q['k_mode']} at {q['h_mean']:.1f} mm over the margin")
