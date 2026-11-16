"""garment_cut's TURNED FLAPS (R2 / R2b's method, C490-C491, made general): a flap the toile turns back about a roll line
(step 4's part, e.g. a lapel lying on the chest, facing out) is flattened alone, then UNFOLDED onto the piece it is cut
on: laid on that piece's flat by one rigid move WITH a reflection (the turn of the cloth) along their shared roll edge,
landing ACROSS the roll line from the piece. The piece's flat then includes the flap; the roll line becomes a fold of the
flat pattern (planned_folds' row: {name, piece, line: [<fold>.a, <fold>.b], kind: roll}).

THE DECLARATION (garment_cut's `flaps`):
  flaps {toile part: {"onto": cut piece, "fold": step 2's fold name, "edges": {"top" | "bottom" | "side": edge name}}}:
        the flap's own free outline (not its roll edge) named by class as cut.free names a free edge (a segment "side"
        when it runs more up than across, else top / bottom by its height against the flap's middle); a run of the same
        name as the piece's neighbouring run joins it (a lapel's outer edge continues the front edge). ".L" parts serve
        their ".R" mirror (onto the mirrored piece).
THE ROLL EDGE: the piece's outline points within HINGE_M of the flap's outline (the flap lies LAPEL_LIFT off the piece),
the longest such run; refused by name when there is none. Rows: the hinge's fit (mm), the flap landing across, the roll
edge's flat length on both sides. Nothing here knows a garment."""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from .flatten import flatten, strain
from .mark_split import areas
from .cut import FREE_MERGE_MM

HINGE_M = 0.008  # m: a piece's outline point this near the flap's outline is on the roll edge


class FlapRefused(ValueError):
    """A flap that shares no roll edge with its piece, or an outline run no declared edge takes (named)."""


def _loop(F):
    from .cut import outline
    return np.asarray(outline(F, np.zeros(len(F), int), 0))


def _longest_run(mask):
    """(start, end) positions (inclusive, cyclic) of the longest run of True in mask."""
    n = len(mask)
    if mask.all():
        return 0, n - 1
    s0 = int(np.argmin(mask))
    best, cur = (0, -1), None
    for k in range(1, n + 1):
        i = (s0 + k) % n
        if mask[i]:
            cur = (cur[0], i) if cur else (i, i)
            ln = (cur[1] - cur[0]) % n
            if ln > (best[1] - best[0]) % n or best == (0, -1):
                best = cur
        else:
            cur = None
    return best


def _rigid(X, Y, refl):
    Xm = X * ([-1.0, 1.0] if refl else [1.0, 1.0])
    mx, my = Xm.mean(0), Y.mean(0)
    U, _, Wt = np.linalg.svd((Xm - mx).T @ (Y - my))
    R = U @ Wt
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1
        R = U @ Wt
    return lambda Z: (Z * ([-1.0, 1.0] if refl else [1.0, 1.0]) - mx) @ R + my


def zipper(A, B, U):
    """Triangles joining polyline A (piece ids) to polyline B (flap ids, from A's start end) in the flat: the turned
    flap and its piece made one mesh along the roll edge (a layer traced across it stays one piece)."""
    if np.linalg.norm(U[B[0]] - U[A[0]]) > np.linalg.norm(U[B[-1]] - U[A[0]]):
        B = B[::-1]
    i = j = 0
    T = []
    while i < len(A) - 1 or j < len(B) - 1:
        adv_a = j == len(B) - 1 or (i < len(A) - 1 and np.linalg.norm(U[A[i + 1]] - U[B[j]]) <
                                     np.linalg.norm(U[B[j + 1]] - U[A[i]]))
        if adv_a:
            T.append([A[i], A[i + 1], B[j]])
            i += 1
        else:
            T.append([A[i], B[j + 1], B[j]])
            j += 1
    return np.asarray(T, int).reshape(-1, 3)


def unfold(f: dict, edges: dict, Vf: np.ndarray, Ff: np.ndarray, emap: dict, fold: str, name: str):
    """(f with the flap merged in: U, F, V, bad, lp, loop; its edges {name: [positions]}; the fold's names {fold.a, fold.b}
    as outline positions; report). f / edges: the piece as cut.flatten_piece / cut.name_runs give them."""
    from .cut import _group
    Uf, Sf, Ff = flatten(Vf, Ff)
    badf = strain(Sf)
    fl = _loop(Ff)
    lp = np.asarray(f["lp"])
    P3 = f["V"][lp]
    near_p = cKDTree(Vf[fl]).query(P3)[0] < HINGE_M
    if near_p.sum() < 3:
        raise FlapRefused(f"{name}: no roll edge with {f['name']} (no outline point of the piece within "
                          f"{HINGE_M * 1000:.0f} mm of the flap's outline): the flap must be turned from this piece")
    hs, he = _longest_run(near_p)
    n = len(lp)
    hinge = [(hs + k) % n for k in range(((he - hs) % n) + 1)]
    near_f = cKDTree(P3[hinge]).query(Vf[fl])[0] < HINGE_M
    kd_f = cKDTree(Vf[fl])
    pair_f = kd_f.query(P3[hinge])[1]
    X, Y = Uf[fl[pair_f]], f["U"][lp[hinge]]
    cen_p = np.nanmean(f["U"][lp], 0)
    t = Y[-1] - Y[0]
    nrm = np.array([-t[1], t[0]])
    fits = []
    for refl in (True, False):
        tf = _rigid(X, Y, refl)
        res = np.linalg.norm(tf(X) - Y, axis=1)
        across = np.sign((np.nanmean(tf(Uf[fl]), 0) - Y.mean(0)) @ nrm) != np.sign((cen_p - Y.mean(0)) @ nrm)
        fits.append((not across, res.mean(), refl, tf, res))
    fits.sort(key=lambda x: (x[0], x[1]))
    not_across, _, refl, tf, res = fits[0]
    # the flap's outer path: between the flap points nearest the hinge's ends, the way with fewer hinge points
    a, b = int(kd_f.query(P3[hs])[1]), int(kd_f.query(P3[he])[1])
    m = len(fl)
    fwd = [(a + k) % m for k in range(((b - a) % m) + 1)]
    bwd = [(a - k) % m for k in range(((a - b) % m) + 1)]
    path = min((fwd, bwd), key=lambda p: near_f[p].sum())
    inner = path  # (a and b too: the zipper joins them to the hinge's ends)
    other = fwd if path is bwd else bwd
    npc = len(f["V"])
    order = [(he + k) % n for k in range(((hs - he) % n) + 1)]  # he ... round the piece ... hs
    new_lp = np.r_[lp[order], npc + fl[inner]].astype(int)
    zip_f = zipper(lp[hinge], npc + fl[other], np.r_[f["U"], tf(Uf)])
    old_name = {}
    for e, idx in edges.items():
        for i in idx:
            old_name[i] = e
    keys, bad = [], []
    zmid = 0.5 * (Vf[fl, 2].min() + Vf[fl, 2].max())
    for k in range(len(order) - 1):
        keys.append(old_name.get(order[k], "?"))
    seq = [None] + inner + [None]  # flap edges: hs -> inner[0] -> ... -> inner[-1] -> he
    for k in range(len(seq) - 1):
        i, j = seq[k], seq[k + 1]
        ii = fl[i] if i is not None else None
        jj = fl[j] if j is not None else None
        Va = Vf[ii] if ii is not None else P3[hs]
        Vb = Vf[jj] if jj is not None else P3[he]
        d = Vb - Va
        c = "side" if abs(d[2]) > 0.7 * np.linalg.norm(d) else ("bottom" if 0.5 * (Va[2] + Vb[2]) < zmid else "top")
        if c not in emap:
            bad.append(f"{name}: a {c} run of the flap's outline no declared edge takes: flaps.{name}.edges: {{\"{c}\": edge}}")
        keys.append(emap.get(c, f"{name}_{c}"))
    seg = np.linalg.norm(np.diff(np.r_[Vf[fl[inner]], P3[he][None]], axis=0), axis=1)
    seg = np.r_[np.linalg.norm(Vf[fl[inner[0]]] - P3[hs]), seg]
    nfix = len(order) - 1
    for _ in range(3):  # (short flap runs join a neighbour: cut.FREE_MERGE_MM, as a free edge's)
        rs = _group(keys)
        for k, (key, idx) in enumerate(rs):
            if min(idx) >= nfix and seg[np.asarray(idx) - nfix].sum() * 1000 < FREE_MERGE_MM and len(rs) > 1:
                for i in idx:
                    keys[i] = rs[(k - 1) % len(rs)][0]
    U = np.r_[f["U"], tf(Uf)]
    Vm = np.r_[f["V"], Vf]
    Fm = np.r_[f["F"], Ff + npc, zip_f]
    badm = np.r_[f["bad"], badf, np.zeros(len(zip_f))]
    P = U[new_lp]
    area = 0.5 * float(np.dot(P[:, 0], np.roll(P[:, 1], -1)) - np.dot(P[:, 1], np.roll(P[:, 0], -1)))
    new_edges = {}
    for key, idx in _group(keys):
        nm = key
        j = 2
        while nm in new_edges:
            nm, j = f"{key}_{j}", j + 1
        if nm != key:
            bad.append(f"{f['name']}: edge {key!r} is {j - 1} runs apart after the unfold")
        new_edges[nm] = idx
    fold_names = {f"{fold}.a": 0, f"{fold}.b": len(order) - 1}
    roll_p = float(np.linalg.norm(np.diff(Y, axis=0), axis=1).sum())
    roll_f = float(np.linalg.norm(np.diff(X, axis=0), axis=1).sum())
    rep = {"flap": name, "onto": f["name"], "reflected": bool(refl), "lands_across_roll": not not_across,
           "hinge_mean_mm": round(float(res.mean()) * 1000, 2), "hinge_max_mm": round(float(res.max()) * 1000, 2),
           "roll_flat_mm": {"piece": round(roll_p * 1000, 1), "flap": round(roll_f * 1000, 1)},
           "flap_area_cm2": round(float(areas(Vf, Ff).sum()) * 1e4, 1),
           "flap_strain_mean_pct": round(float((badf * areas(Vf, Ff)).sum() / areas(Vf, Ff).sum() * 100), 2),
           "outline_ccw": area > 0}
    if not_across:
        bad.append(f"{name}: unfolded, it lands on {f['name']} not across its roll line")
    if area <= 0:
        bad.append(f"{f['name']}: the outline with {name} unfolded runs clockwise (the flap overlaps the piece)")
    g = dict(f, U=U, V=Vm, F=Fm, bad=badm, lp=new_lp, loop=list(new_lp))
    g["rep"] = dict(f["rep"], flap=rep)
    return g, new_edges, fold_names, rep, bad
