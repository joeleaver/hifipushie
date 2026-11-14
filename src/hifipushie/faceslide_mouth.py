"""The mouth's sliders as fields: mouth fields, the lip rings, the seal and its steps. Part of the face sliders (faceslide.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import faceslide
from .faceslide import _g, _ss, template

def _mouth_fields() -> dict:
    """The mouth's sliders (whole mouth, GNM frame, metres at +1). Per x the lips are read between curves through
    the 68 landmarks: the upper border (48-54 over 49-53), the upper seam (60-64 over 61-63), the lower seam (64-60
    under 65-67) and the lower border (54-48 under 55-59); s = 0 at the seam .. 1 at the border."""
    T = template()
    X, n, lm = T["X"], T["n"], T["lm"]
    mm = 0.001
    up = np.array([0.0, 1.0, 0.0])
    fwd = np.array([0.0, 0.0, 1.0])

    def curve(ids):
        P = lm[list(ids)]
        o = np.argsort(P[:, 0])
        return lambda x: np.interp(x, P[o, 0], P[o, 1])  # noqa: E731
    yU = curve((48, 49, 50, 51, 52, 53, 54))
    ySu = curve((60, 61, 62, 63, 64))
    ySl = curve((60, 67, 66, 65, 64))
    yL = curve((48, 59, 58, 57, 56, 55, 54))
    x, y = X[:, 0], X[:, 1]
    hw = 0.5 * float(lm[54][0] - lm[48][0])
    zc = float(lm[[51, 57, 62, 66]][:, 2].mean())
    front = T["ext"] & (X[:, 2] > zc - 0.012) & (np.abs(x) < hw + 0.008)
    front &= (y < float(lm[33][1]) - 0.002) & (y > float(lm[8][1]) + 0.01)  # under the nose, over the chin
    su = (y - ySu(x)) / np.maximum(yU(x) - ySu(x), 1.5 * mm)
    sl = (ySl(x) - y) / np.maximum(ySl(x) - yL(x), 1.5 * mm)
    ax = np.abs(x) / hw
    taper = _ss((1.0 - ax) / 0.45)  # full over the middle, tucked at the corners
    upper = front & (y > ySu(x) - 0.3 * mm)
    lower = front & (y < ySl(x) + 0.3 * mm)
    # how far past each border the skin follows (fading over ~3 mm)
    past_u = np.where(su > 1, _ss(1 - (su - 1) * (yU(x) - ySu(x)) / (faceslide.PAST * mm)), 1.0)
    past_l = np.where(sl > 1, _ss(1 - (sl - 1) * (ySl(x) - yL(x)) / (faceslide.PAST * mm)), 1.0)
    # (the heights move the border up to 2.5-3 mm: the skin past it follows over 8 mm, not 3: at 3 it folded)
    hu = np.where(su > 1, _ss(1 - (su - 1) * (yU(x) - ySu(x)) / (8 * mm)), 1.0)
    hl = np.where(sl > 1, _ss(1 - (sl - 1) * (ySl(x) - yL(x)) / (8 * mm)), 1.0)
    seam_hold_u = _ss(su / 0.25)  # the contact ring stays where it is (no lip through the other)
    seam_hold_l = _ss(sl / 0.25)
    F = {}
    # eversion: the vermilion rolled forward (volume, not height); upper: peaks in its upper part (catches light on
    # top, a shadow under it); lower: its middle, a shadow beneath
    pu = upper * taper * past_u * _g(np.minimum(su, 1.6), 0.65, 0.35)
    F["lip_upper_roll"] = pu[:, None] * (0.9 * fwd + 0.25 * up * seam_hold_u[:, None])
    pl = lower * taper * past_l * _g(np.minimum(sl, 1.6), 0.5, 0.35)
    F["lip_lower_roll"] = pl[:, None] * (0.9 * fwd - 0.25 * up * seam_hold_l[:, None])
    # Cupid's bow: the border's peaks up and its dip down (the border band only, fading 3 mm into lip and skin)
    xp = 0.5 * abs(float(lm[52][0] - lm[50][0]))
    band = upper * _g(su, 1.0, 0.35) * seam_hold_u
    bow = _g(np.abs(x), xp, 0.45 * xp) - 0.8 * _g(x, 0.0, 0.45 * xp)
    F["lip_bow"] = (band * bow)[:, None] * up[None]
    # tubercle: the upper lip's middle down and forward over the seam
    tub = upper * _g(x, 0.0, 0.55 * xp) * _g(su, 0.25, 0.3)
    F["lip_tubercle"] = tub[:, None] * (0.85 * fwd - 0.4 * up * seam_hold_u[:, None])
    # corner tuck: the commissures in and back (a deeper corner; - = fuller corners)
    # vermilion height: the border slides away from the seam (the seam held, the skin past the border following over
    # ~3 mm): how much red lip shows, apart from how far it stands forward (the rolls)
    F["lip_upper_height"] = (upper * taper * hu * _ss((su - 0.15) / 0.85))[:, None] * up[None]  # (the seam
    # rows held: at -1 the lip went down through the lower one)
    F["lip_lower_height"] = (lower * taper * hl * _ss((sl - 0.15) / 0.85))[:, None] * -up[None]
    # lower lip width: its border laterally (the outer half, toward the corners) away from / toward the seam: + more red
    # out to the corners, - the lower lip a short cushion ending inside them (the seam and the middle held)
    lat_l = _ss((ax - 0.3) / 0.45) * (1 - _ss((ax - 1.05) / 0.15))
    F["lip_lower_width"] = (lower * hl * lat_l * _ss((sl - 0.15) / 0.85))[:, None] * -up[None]
    F["mouth_corner"] = np.zeros_like(X)
    for c in (lm[48], lm[54]):
        r = np.linalg.norm(X - c, axis=1)
        side = np.sign(c[0])
        F["mouth_corner"] += (T["skin"] * _g(r, 0, 3.5 * mm))[:, None] * (-0.85 * fwd + 0.35 * np.array([-side, 0, 0]))[None]  # (one direction: the corner's normals turn fast)
    return {k: v * (faceslide.UNITS[k][0] * mm) for k, v in F.items()}


def _lip_rings() -> dict:
    """GNM's lips by topology (its raw ids): rings out from the skin's open mouth loop (the inner rolls' end) over the
    skin's quads; ring base.LIP_RING is the contact ring (landmarks 61-63 / 65-67 sit on it)."""
    if "lip_rings" in faceslide._CACHE:
        return faceslide._CACHE["lip_rings"]
    from collections import defaultdict

    from . import base as basemod
    from . import base_identity
    g = base_identity._gnm_data()
    skin = np.asarray(g["skin"], bool)
    Q = np.asarray(g["quads"])
    Q = Q[skin[Q].all(1)]
    e = np.sort(np.r_[Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]], 1)
    ue, ce = np.unique(e, axis=0, return_counts=True)
    adj = defaultdict(set)
    for a, b in e:
        adj[a].add(b)
        adj[b].add(a)
    bd = np.unique(ue[ce == 1])
    X = np.asarray(g["template_vertex_positions"], float)
    lm = np.array([sum(float(w) * X[int(v)] for v, w in zip(r[0::2], r[1::2])) for r in g["lm68"]])
    mouth = 0.5 * (lm[62] + lm[66])
    loop = set(int(v) for v in bd[np.linalg.norm(X[bd] - mouth, axis=1) < 0.04])
    rings, seen, ring = [sorted(loop)], set(loop), loop
    for _ in range(basemod.LIP_RING + 16):  # (out past where the fade has died: ~1 mm a ring)
        nxt = set()
        for v in ring:
            nxt |= adj[v]
        nxt -= seen
        seen |= nxt
        ring = nxt
        rings.append(sorted(ring))
    faceslide._CACHE["lip_rings"] = {"rings": [np.array(r, int) for r in rings], "contact": basemod.LIP_RING,
                           "adj": {int(v): [int(u) for u in adj[v]] for r in rings for v in r},
                           "upper": np.asarray(g["groups"]["upper_lip"]) > np.asarray(g["groups"]["lower_lip"])}
    return faceslide._CACHE["lip_rings"]


def seal_delta(V: np.ndarray, amount: float = 1.0) -> np.ndarray:
    """(n, 3) GNM-frame move that closes the lips of head V (GNM's raw vertices, its frame) to `amount` of contact
    along the full width: the contact ring's upper and lower halves meet halfway (per x, the gap's y and z),
    everything from the open loop out to the contact ring moves whole (the rolls behind the contact go with it: no
    lip through the other), the lips beyond it fade out over ~5 mm (they shift, not squash). A rest mouth, not a
    pressed one: nothing goes past contact."""
    R = _lip_rings()
    D = np.zeros_like(V)
    for _ in range(faceslide.SEAL_PASSES):  # (re-measured each pass: the contact ring's halves aren't single-valued in x)
        D = D + _seal_step(V + D, 1.0, R)
    return float(amount) * D


def _seal_step(V, amount, R):
    rings, kc = R["rings"], R["contact"]
    C = rings[kc]
    x = V[C, 0]
    lo_x, hi_x = x.min(), x.max()
    # upper / lower half: GNM's own upper_lip / lower_lip groups (each ring splits 29 / 29). By height (above the
    # corners' line) a downturned, wide-open mouth put lower-lip vertices in the upper half: their edges to the
    # rolls stretched x6 (Tess)
    up_g = R["upper"]
    side = up_g[C]
    U, Lw = C[side], C[~side]
    if len(U) < 3 or len(Lw) < 3:
        return np.zeros_like(V)
    ou, ol = np.argsort(V[U, 0]), np.argsort(V[Lw, 0])
    U, Lw = U[ou], Lw[ol]
    gap_at = lambda xx: np.c_[[np.interp(xx, V[Lw, 0], V[Lw, k]) - np.interp(xx, V[U, 0], V[U, k]) for k in (1, 2)]].T  # noqa: E731
    import scipy.sparse as sp
    from scipy.sparse.linalg import spsolve
    D = np.zeros_like(V)
    # the contact ring's own move: each half halfway to the other (per x; touching or crossed: nothing)
    xx = np.clip(V[C, 0], lo_x, hi_x)
    gp = gap_at(xx)
    sgn = np.where(side, 0.5, -0.5)
    tgt = np.c_[np.zeros(len(C)), amount * sgn * np.minimum(gp[:, 0], 0.0), amount * sgn * gp[:, 1]]
    # everything else as a MEMBRANE over the lips' rings (a harmonic fill: the contact ring held at its move, the
    # outermost ring at 0, the rolls inside free): the travel spreads over every row in between. (Moving whole bands
    # with a fade by height stretched edges x4 and turned quads on wide-open, thin-lipped heads: Tess)
    ids = np.unique(np.concatenate(rings))
    loc = {int(v): i for i, v in enumerate(ids)}
    rows, cols = [], []
    for v in ids:
        for u in R["adj"].get(int(v), []):
            if u in loc:
                rows.append(loc[int(v)])
                cols.append(loc[u])
    n = len(ids)
    A = sp.coo_matrix((np.ones(len(rows)), (rows, cols)), (n, n)).tocsr()
    deg = np.asarray(A.sum(1)).ravel()
    Lp = sp.diags(deg) - A
    fixed = np.zeros(n, bool)
    val = np.zeros((n, 3))
    ci = np.array([loc[int(v)] for v in C])
    fixed[ci] = True
    val[ci] = tgt
    # the rolls inside the contact move whole with their own lip (by topology from the contact ring: by height the
    # rolls' quads straddle the middle; left free, the corners' rolls averaged both lips and turned over)
    up_of = {int(v): bool(s) for v, s in zip(C, side)}
    for k in range(kc - 1, -1, -1):
        for v in rings[k]:
            nb = [up_of[u] for u in R["adj"].get(int(v), []) if u in up_of]
            up_of[int(v)] = bool(R["upper"][v])  # (GNM's groups: see above)
    inner = np.array([int(v) for k in range(kc) for v in rings[k]], int)
    # ... except near the corners, where the two lips' rolls join: there the membrane spreads it (held whole, an
    # upper roll vertex going down beside a lower one going up stretched their edge x4: Tess's wide-open mouth)
    span = max(hi_x - lo_x, 1e-6)
    inner = inner[np.minimum(V[inner, 0] - lo_x, hi_x - V[inner, 0]) > faceslide.CORNER_FREE * span]
    if len(inner):
        g_in = gap_at(np.clip(V[inner, 0], lo_x, hi_x))
        s_in = np.where([up_of[int(v)] for v in inner], 0.5, -0.5)
        ii = np.array([loc[int(v)] for v in inner])
        fixed[ii] = True
        val[ii] = np.c_[np.zeros(len(inner)), amount * s_in * np.minimum(g_in[:, 0], 0.0), amount * s_in * g_in[:, 1]]
    oi = np.array([loc[int(v)] for v in rings[-1]])
    fixed[oi] = True
    free = ~fixed
    if free.any():
        Lff = Lp[free][:, free].tocsc()
        rhs = -(Lp[free][:, fixed] @ val[fixed])
        val[free] = np.column_stack([spsolve(Lff, rhs[:, k]) for k in range(3)])
    D[ids] = val
    return D
