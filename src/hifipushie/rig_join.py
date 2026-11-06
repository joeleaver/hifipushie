"""Where a limb's skin joins the body's: the limb's weight blended over a band round the seam the mesh really has.

A limb hanging beside the body (an arm a few mm off the side, joined only at the shoulder) shares no skin with the
side: a weight blend by distance alone spreads across the air between them, so a raised arm drags the side up
(the body's skin, the arm's) or the side holds the arm's inner skin down (a web of long triangles). Here every
vertex is labelled by the flesh its surface comes from (the limb chain's sculpted shapes, or the rest), the seam
is where the two labels meet along the mesh's edges (no edge crosses an air gap, so a hanging arm's seam is only
at the shoulder), and the limb's share goes from 0 to 1 over JOIN_BAND x the limb's girth of surface distance
across that seam (half each side). Away from the band a vertex keeps only its own side's weights.

Only for a limb laid on as a layer above the body (its shapes in a later layer: the artist's "this hangs beside,
joined where it touches"); a limb sculpted in the body's own layer keeps its blend. Runs after every other weight
pass (rig.rig_weights). Limbs: JOIN_ROOTS (arms). Off for a base body (a
person's weights come from the template) and with spec["rig"]["join"] = False.
"""
import numpy as np

from . import sdf

JOIN_ROOTS = ("Arm",)  # a thigh blended into the hips is the stub repaint's (rig._arc_bend, leg_blend): left to it
JOIN_BAND = 2.5  # x the limb's girth: the band's full width along the surface, across the seam (swept on Puddles, arms 80)
JOIN_SPLIT = 0.2  # the limb's share on the seam: low, so the body's side stays put and the limb's skin takes the stretch
JOIN_SPLIT_L = 0.9  # the part of the band on the limb's side
JOIN_MIN_BAND = 0.01  # m: never narrower than this (a few edges of an export mesh)
JOIN_LABEL_TOL = 0.0005  # m: a vertex is the limb's when the limb's flesh is nearer its surface by more than this


def _sstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _chain(rb: list[dict], root: int) -> list[int]:
    """The root and every bone below it (rb lists parents first), bend helpers of joints below included."""
    out = {root}
    for i, b in enumerate(rb):
        if b["parent"] in out:
            out.add(i)
    return sorted(out)


def _edges(F: np.ndarray) -> np.ndarray:
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    e = np.unique(np.sort(e, 1), axis=0)
    return e


def limb_join(spec: dict, rb: list[dict], V: np.ndarray, F, J: np.ndarray, W: np.ndarray, carry: list[dict],
              girth: dict | None = None):
    """(J, W) with each limb's weight re-blended across its seam (module docstring). `carry`: rig._flesh_tree's
    weight-carrying bones (their "prims" name the sculpted shapes each bone holds)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    from .rig import PREFIX
    from .spec import compile_prims
    if F is None or not len(F) or spec.get("base") or (spec.get("rig") or {}).get("join") is False:
        return J, W
    V = np.asarray(V, float)
    F = np.asarray(F)
    names = [b["name"] for b in rb]
    roots = [i for i, n in enumerate(names)
             if any(n == PREFIX + s + r for s in ("Left", "Right") for r in JOIN_ROOTS)]
    if not roots:
        return J, W
    by_name = {c["name"]: c for c in carry}
    prims = [p for p in compile_prims(spec) if p.op == "add"]
    n = len(V)
    D = np.zeros((n, len(rb)))
    np.add.at(D, (np.repeat(np.arange(n), J.shape[1]), np.asarray(J).ravel()), np.asarray(W, float).ravel())
    e = _edges(F)
    ln = np.linalg.norm(V[e[:, 0]] - V[e[:, 1]], axis=1)
    G = coo_matrix((np.r_[ln, ln], (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(n, n)).tocsr()
    changed = False
    for root in roots:
        chain = _chain(rb, root)
        own = {p.name for i in chain if names[i] in by_name for p in by_name[names[i]]["prims"]}
        mine = [p for p in prims if p.name in own]
        rest = [p for p in prims if p.name not in own]
        if not mine or not rest or max(p.layer for p in mine) <= min(p.layer for p in rest):
            continue  # a limb sculpted into the body's own layer blends as it was built (the goblin's arm)
        lo, hi = np.min([p.lo for p in mine], 0), np.max([p.hi for p in mine], 0)
        near = np.flatnonzero(np.all((V > lo - 0.05) & (V < hi + 0.05), 1))
        if not len(near):
            continue
        da = np.full(n, np.inf)
        db = np.full(n, -np.inf)
        da[near] = sdf.field_at(mine, V[near], clip=False)
        db[near] = sdf.field_at(rest, V[near], clip=False)
        limb = da < db - JOIN_LABEL_TOL
        if not limb.any():
            continue
        seam = np.unique(e[limb[e[:, 0]] != limb[e[:, 1]]])
        if not len(seam):  # a limb whose skin never meets the body's on this mesh: its own part, weights stand
            continue
        g_ = (girth or {}).get(root)
        band = max(JOIN_BAND * g_ if g_ else JOIN_MIN_BAND, JOIN_MIN_BAND)
        dist = dijkstra(G, indices=seam, min_only=True, limit=band)
        sgn = np.where(limb, 1.0, -1.0)
        t = np.where(np.isfinite(dist), sgn * dist, sgn * band)
        # the limb's share: JOIN_SPLIT on the seam, 0 a body side's (1 - JOIN_SPLIT) x band off it, 1 the limb's
        g = np.where(t >= 0, JOIN_SPLIT + (1 - JOIN_SPLIT) * _sstep(t / max(JOIN_SPLIT_L * band, 1e-9)),
                     JOIN_SPLIT * (1 - _sstep(-t / max((1 - JOIN_SPLIT_L) * band, 1e-9))))
        cols = np.zeros(len(rb), bool)
        cols[chain] = True  # (the root's own bend helper hangs from the parent: the body's side, half turned)
        wl, wb = D[:, cols].sum(1), D[:, ~cols].sum(1)
        tot = wl + wb
        # a side with none of its own weight takes the joint's: the limb root, or the bone it hangs from
        fill_l = np.zeros(len(rb)); fill_l[root] = 1.0
        fill_b = np.zeros(len(rb)); fill_b[rb[root]["parent"]] = 1.0
        L_ = np.where(wl[:, None] > 1e-6, D * cols / np.maximum(wl, 1e-12)[:, None], fill_l[None, :])
        B_ = np.where(wb[:, None] > 1e-6, D * ~cols / np.maximum(wb, 1e-12)[:, None], fill_b[None, :])
        new = tot[:, None] * (g[:, None] * L_ + (1 - g)[:, None] * B_)
        upd = near[(np.abs(g[near] * tot[near] - wl[near]) > 1e-4)]
        D[upd] = new[upd]
        changed = changed or len(upd) > 0
    if not changed:
        return J, W
    k = J.shape[1]
    order = np.argsort(-D, axis=1, kind="stable")[:, :k]
    Wk = np.take_along_axis(D, order, 1)
    Wk /= np.maximum(Wk.sum(1, keepdims=True), 1e-12)
    Jk = np.where(Wk > 0, order, 0)
    return Jk.astype(np.asarray(J).dtype), Wk
