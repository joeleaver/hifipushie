"""GNM's skin round the eye as RINGS (eyelid / orbit, 2026-10-11; from spikes/eyelid/lidmap.py).

GNM's skin round the eye is a quad grid of closed rings round the opening: ring 0 = the lid margin (skin next to the
socket lining), ring k = k edges out (rings 0-2 the margin, 2-5 the platform, 5-6 GNM's crease, 7-10 fold and drape, 11+
the brow / orbital rims: ring 12-13's top is the supraorbital rim over the pupil, ring 13-14's lateral end the lateral
orbital rim, ring 9-10's bottom the infraorbital rim); negative rings go into the socket lining. Each ring is ordered
round the eye, so (ring, place along it) is a grid on which any head with GNM's vertex order compares vertex for vertex.
GNM frame (x = the subject's left, y up, z forward); the LEFT eye; `mirror()` gives the right one's vertex ids."""
from __future__ import annotations

import numpy as np

_C: dict = {}
NR = 14     # rings out from the margin
NI = 5      # rings into the socket


def topo() -> dict:
    """{"ring": per GNM vertex ring index of the LEFT eye (-NI..NR, 99 elsewhere), "loops": {k: ordered vertex ids}}."""
    if "t" in _C:
        return _C["t"]
    from . import gnm_controls as gc
    g = gc.gnm()
    Q, gr, T = g["quads"], g["groups"], g["T"]
    n = len(T)
    skin, sock = gr["skin"], gr["eye_sockets"]
    E = np.concatenate([Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]])
    E = E[skin[E].all(1)]
    nb = [[] for _ in range(n)]
    for a, b in E:
        nb[a].append(b)
        nb[b].append(a)
    cl = g["J"][2]
    m = (sock[E[:, 0]] != sock[E[:, 1]])
    r0 = np.unique(np.where(sock[E[m, 0]], E[m, 1], E[m, 0]))
    r0 = r0[np.linalg.norm(T[r0] - cl, axis=1) < 0.03]
    ring = np.full(n, 99)
    ring[r0] = 0
    for sgn, ok, lim in ((1, ~sock, NR), (-1, sock, NI)):     # outward: skin that is not lining; inward: lining
        cur = list(r0)
        for k in range(1, lim + 1):
            nxt = []
            for a in cur:
                for b in nb[a]:
                    if ring[b] == 99 and ok[b]:
                        ring[b] = sgn * k
                        nxt.append(b)
            cur = nxt
    loops = {}
    for k in range(-NI, NR + 1):
        ids = np.flatnonzero(ring == k)
        if len(ids) < 4:
            continue
        P = T[ids] - cl
        loops[k] = ids[np.argsort(np.arctan2(P[:, 1], P[:, 0]))]     # 0 = outer corner (+x), +90 = top
    _C["t"] = {"ring": ring, "loops": loops, "nb": nb, "centre": cl}
    return _C["t"]


def mirror() -> np.ndarray:
    """Per GNM vertex: the id of its mirror image across x = 0 (the template is symmetric)."""
    if "m" not in _C:
        from scipy.spatial import cKDTree
        from . import gnm_controls as gc
        T = gc.gnm()["T"]
        _C["m"] = cKDTree(T).query(T * [-1, 1, 1])[1]
    return _C["m"]


def ball(V: np.ndarray, side: str = "left") -> tuple:
    """GNM's own eyeball on vertices V (any unit): (centre, radius) of the sphere through its sclera."""
    from . import gnm_controls as gc
    gr = gc.gnm()["groups"]
    P = V[gr[f"{side}_eye"] & gr["scleras"]]
    A = np.c_[2 * P, np.ones(len(P))]
    sol = np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)[0]
    return sol[:3], float(np.sqrt(sol[3] + sol[:3] @ sol[:3]))


def upper_ids(k: int) -> np.ndarray:
    """Ring k's upper half (by the template), ordered inner -> outer."""
    from . import gnm_controls as gc
    g = gc.gnm()
    ids = topo()["loops"][k]
    ids = ids[g["T"][ids, 1] > g["J"][2][1] + 0.0005]
    return ids[np.argsort(g["T"][ids, 0])]


def column(V, ctr, u: float = 0.0, upper: bool = True) -> list:
    """The lid's rows at the column u (V's unit, from the eye centre ctr): per ring k the point where its upper
    (lower) half crosses x = u: [(k, v, w)] from the deepest lining ring to the brow."""
    from . import gnm_controls as gc
    t, g = topo(), gc.gnm()
    TUP = g["T"][:, 1] > g["J"][2][1] + 0.0003
    span = np.ptp(V[t["loops"][0]][:, 0])
    out = []
    for k in sorted(t["loops"]):
        ids = t["loops"][k]
        P = V[ids] - ctr
        nn = len(ids)
        best = None
        for i in range(nn):
            a, b = P[i], P[(i + 1) % nn]
            if (a[0] - u) * (b[0] - u) > 0 or a[0] == b[0]:
                continue
            p = a + (u - a[0]) / (b[0] - a[0]) * (b - a)
            if np.linalg.norm(b - a) > 0.4 * span:
                continue
            if k >= 0 and (TUP[ids[i]] and TUP[ids[(i + 1) % nn]]) != upper:
                continue
            if k < 0 and (p[1] > -0.05 * span) != upper:
                continue
            if best is None or (upper and p[1] > best[1]) or (not upper and p[1] < best[1]):
                best = p
        if best is not None:
            out.append((k, float(best[1]), float(best[2])))
    return out


def sets() -> dict:
    """Vertex sets of the LEFT orbit on GNM's rings (ids), for the orbit measures (gnm_mm): "brow_ridge" (the
    supraorbital rim over the pupil: rings 12-13's top, within 6 mm of the pupil's column), "side_rim" (the lateral
    orbital rim: rings 13-14's outer end, within 4 mm of the eye's height), "under_eye" (the infraorbital rim under the
    pupil: rings 9-10's bottom), "sulcus" (the skin under the brow: ring 8's top), "platform" (the lid on the ball:
    ring 3's top), "margin_up" / "margin_lo" (ring 0 over / under the pupil)."""
    if "s" in _C:
        return _C["s"]
    from . import gnm_controls as gc
    t = topo()
    T = (gc.gnm()["T"] - t["centre"]) * 1000.0

    def pick(rings, ok):
        ids = np.concatenate([t["loops"][k] for k in rings])
        return ids[ok(T[ids])]
    _C["s"] = {
        "brow_ridge": pick((12, 13), lambda P: (P[:, 1] > 8) & (np.abs(P[:, 0]) < 6)),
        "side_rim": pick((13, 14), lambda P: (P[:, 0] > 15) & (np.abs(P[:, 1]) < 4)),
        "under_eye": pick((9, 10), lambda P: (P[:, 1] < -10) & (np.abs(P[:, 0]) < 6)),
        "sulcus": pick((8,), lambda P: (P[:, 1] > 3) & (np.abs(P[:, 0]) < 6)),
        "platform": pick((3,), lambda P: (P[:, 1] > 1) & (np.abs(P[:, 0]) < 6)),
        "margin_up": pick((0,), lambda P: (P[:, 1] > 0) & (np.abs(P[:, 0]) < 5)),
        "margin_lo": pick((0,), lambda P: (P[:, 1] < -2) & (np.abs(P[:, 0]) < 5)),
    }
    return _C["s"]
