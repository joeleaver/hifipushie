"""The modelling rig: the skeleton from a spec, weights against its flesh, settling and smoothing, `pose`. Part of rig (rig.py has the overview)."""
from __future__ import annotations

from collections import deque

import numpy as np

from . import rig
from . import sdf
from .spec import compile_prims, expand_mirror, resolve_point

def skeleton(spec: dict) -> list[dict]:
    """[{"name", "head", "tail" (world, Blender axes), "parent" (index, -1 for the root's bones), "prim" (its
    cone), "prims" (its cone and the blobs on it)}] in an order where every parent comes before its children."""
    s = expand_mirror(spec)
    prims = {p.name: p for p in compile_prims(spec) if p.op == "add"}
    bones = {n: b for n, b in s["bones"].items() if b.get("op", "add") == "add" and n in prims}
    if not bones:
        return []
    pos = {j: resolve_point(s, j) for b in bones.values() for j in (b["a"], b["b"])}
    adj: dict = {}
    for n, b in bones.items():
        adj.setdefault(b["a"], []).append((n, b["b"]))
        adj.setdefault(b["b"], []).append((n, b["a"]))
    root = next((r for r in rig.ROOTS if r in adj), None) or _centre(adj)
    out, index, reached = [], {}, {root: -1}  # joint -> the bone that reached it

    def walk(start):
        q = deque([start])
        while q:
            j = q.popleft()
            for n, other in adj[j]:
                if n in index:
                    continue
                index[n] = len(out)
                out.append({"name": n, "head": pos[j], "tail": pos[other], "parent": reached[j], "prim": prims[n]})
                if other not in reached:
                    reached[other] = index[n]
                    q.append(other)
    walk(root)
    heads, tails = None, None
    while len(index) < len(bones):  # a piece not joined to the rest: from its joint nearest the skeleton so far
        rest = [j for j in adj if j not in reached]
        heads = np.array([b["head"] for b in out])
        tails = np.array([b["tail"] for b in out])
        d = [(_seg_dist(pos[j], heads, tails), j) for j in rest]
        (dist, near), j = min(((float(v.min()), int(v.argmin())), j) for v, j in d)
        reached[j] = near
        walk(j)
    # blobs go with the bone they sit on: at a joint, the bone that reached it (the root's first bone for the
    # root); on a bone, that bone; anywhere else, the bone nearest their centre
    heads = np.array([b["head"] for b in out])
    tails = np.array([b["tail"] for b in out])
    for b in out:
        b["prims"] = [b["prim"]]
    for n, bl in s["blobs"].items():
        pr = prims.get(n)
        if pr is None or pr.kind not in ("ellipsoid", "box", "cylinder", "blade", "lids", "csg") + rig.SOFT:
            continue
        at = bl.get("at")
        if isinstance(at, dict) and at.get("bone") in index:
            i = index[at["bone"]]
        elif isinstance(at, str) and at in reached:
            i = max(reached[at], 0)
        else:
            c = resolve_point(s, at if at is not None else [0, 0, 0]) + np.array(bl.get("offset", [0, 0, 0]), float)
            if pr.kind in rig.SOFT:  # a loft's or sheet's "at" is its origin, not its middle
                c = 0.5 * (pr.lo + pr.hi)
            i = int(np.argmin(_seg_dist(c, heads, tails)))
        out[i]["prims"].append(pr)
    return out


def _centre(adj: dict) -> str:
    """The joint whose farthest joint (in bones) is nearest: the middle of the skeleton."""
    best, key = None, None
    for j in adj:
        seen, q = {j: 0}, deque([j])
        while q:
            x = q.popleft()
            for _, y in adj[x]:
                if y not in seen:
                    seen[y] = seen[x] + 1
                    q.append(y)
        k = (max(seen.values()), -len(seen))
        if key is None or k < key:
            best, key = j, k
    return best


def _seg_dist(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    t = np.clip(((p - a) * ab).sum(-1) / np.maximum((ab * ab).sum(-1), 1e-12), 0, 1)
    return np.linalg.norm(a + t[..., None] * ab - p, axis=-1)


def weights(bones: list[dict], verts: np.ndarray, faces: np.ndarray | None = None, k: int = 4,
            falloff: float = rig.FALLOFF, smooth: int = rig.SMOOTH) -> tuple[np.ndarray, np.ndarray]:
    """(bone indices (n, k), weights (n, k), rows summing to 1) for vertices, from each bone's own cone and blobs,
    then averaged with the vertices around (`smooth` rounds over the faces' edges) so that where one bone's flesh
    meets another's the weights blend instead of stepping (a crease down the chest when an arm lifts)."""
    V = np.asarray(verts, np.float64)
    D = np.stack([np.min([_flesh(p, b.get("cuts", ()), V) for p in b["prims"]], 0) for b in bones], 1)
    r = np.array([b["falloff_r"] if "falloff_r" in b else 0.5 * (b["prim"].params["ra"] + b["prim"].params["rb"])
                  for b in bones])
    near = D.argmin(1)
    # the blend's width is set by the thinner bone: the fat torso's own radius would spread it down the arm
    fall = np.maximum(falloff * np.minimum(r[None, :], r[near][:, None]), 1e-3)
    d0 = D.min(1, keepdims=True)
    W = np.exp(-(D - d0) / fall)
    # a vertex blends only between its nearest bone and that bone's family (two steps of parents, children and
    # siblings): unrelated
    # bones that happen to be near (a tusk by the jaw, the other thigh) would crowd the four kept and step
    n = len(bones)
    fam = np.eye(n, dtype=bool)
    par = np.array([b["parent"] for b in bones])
    for i, p in enumerate(par):
        if p >= 0:
            fam[i, p] = fam[p, i] = True
    for p in set(par.tolist()):
        kids = np.flatnonzero(par == p)
        fam[np.ix_(kids, kids)] = True
    fam = (fam.astype(np.int32) @ fam.astype(np.int32)) > 0  # two steps: a fat upper arm's grandparent spine too
    W *= fam[D.argmin(1)]
    W /= W.sum(1, keepdims=True)
    W = _smooth(W, faces, smooth)
    k = min(k, len(bones))
    J = np.argsort(-W, axis=1)[:, :k]
    Wk = np.take_along_axis(W, J, 1)
    Wk[Wk < 0.01 * Wk[:, :1]] = 0.0
    Wk /= Wk.sum(1, keepdims=True)
    return J.astype(np.int64), _settle(J, Wk, faces, smooth)


def _flesh(p, cuts, V: np.ndarray) -> np.ndarray:
    """A flesh primitive's distance; a bone's cone stops at its joints' planes ({"cuts": [(point, normal)]}, keeping
    the -normal side). Blobs aren't cut: a belly on the spine would lose its sides to a hanging arm."""
    d = sdf.field_at([p], V, clip=False)
    if p.kind == "cone":
        for q, n in cuts:
            d = np.maximum(d, (V - q) @ n)
    for q, n in getattr(p, "flesh_cuts", ()):  # a blob shared along a chain (`_chain_pieces`): this bone's slab
        d = np.maximum(d, (V - q) @ n)
    return d


def _chain_pieces(bl, A: np.ndarray, B: np.ndarray):
    """A blob holding two or more rig segments end to end (a torso loft round Hips, Spine, Spine1, Spine2): [(q,
    piece)], each segment q its slab of the blob, cut where it meets the next by the plane bisecting the two, so the
    spine bends through the torso as it does through a spine cone's pieces. None when it holds fewer than two."""
    import copy
    L = np.linalg.norm(B - A, axis=1)
    pts = np.concatenate([A, B])
    f = sdf.field_at([bl], pts, clip=False)
    inside = [q for q in range(len(A)) if L[q] > 1e-3 and f[q] < 0 and f[len(A) + q] < 0]
    U = (B - A) / np.maximum(L, 1e-12)[:, None]
    # only one chain, end to end and running on (a thigh hanging from the hips inside the loft isn't the torso's)
    nxt = {q: [o for o in inside if o != q and np.linalg.norm(A[o] - B[q]) < 1e-6 and U[o] @ U[q] > 0.5]
           for q in inside}
    best = []
    for q in inside:
        if any(q in v for v in nxt.values()):
            continue
        run = [q]
        while nxt[run[-1]]:
            run.append(nxt[run[-1]][0])
        best = max(best, run, key=len)
    inside = best
    if len(inside) < 2:
        return None
    out = []
    for q in inside:
        cuts = []
        for o in inside:
            if o == q:
                continue
            if np.linalg.norm(B[o] - A[q]) < 1e-6:  # o runs into q's head
                n = U[q] + U[o]
                cuts.append((A[q], -n / max(np.linalg.norm(n), 1e-12)))
            elif np.linalg.norm(A[o] - B[q]) < 1e-6 and U[o] @ U[q] > 0.5:  # o carries on from q's tail (not a branch)
                n = U[q] + U[o]
                cuts.append((B[q], n / max(np.linalg.norm(n), 1e-12)))
        if q == inside[0] and rig.CHAIN_ROOT_CAP:  # the run's root slab stops at its head: the loft hanging below the
            cuts.append((A[q], -U[q]))  # hips (over a stub's thigh and knee) is the legs' to carry, as without it
        p = copy.copy(bl)
        p.flesh_cuts = cuts
        out.append((q, p))
    return out


def _settle(J: np.ndarray, W: np.ndarray, faces, rounds: int) -> np.ndarray:
    """Smooth weights once each vertex's bones are chosen, each vertex keeping only its own: where a bone
    drops out of a vertex's four its weight fades to zero on the way there instead of stepping (a hairline crack
    when posed)."""
    if faces is None or not rounds:
        return W
    F = np.asarray(faces, np.int64)
    a = np.r_[F[:, 0], F[:, 1], F[:, 2], F[:, 1], F[:, 2], F[:, 0]]
    b = np.r_[F[:, 1], F[:, 2], F[:, 0], F[:, 0], F[:, 1], F[:, 2]]
    deg = np.maximum(np.bincount(a, minlength=len(W)), 1).astype(np.float64)[:, None]
    for _ in range(rounds):
        # each neighbour's weight for each of this vertex's bones (0 if the neighbour doesn't have it)
        match = (J[b][:, None, :] == J[a][:, :, None])  # (edges, my slot, its slot)
        got = (match * W[b][:, None, :]).sum(2)
        acc = np.zeros_like(W)
        np.add.at(acc, a, got)
        W = 0.5 * W + 0.5 * acc / deg
        W /= np.maximum(W.sum(1, keepdims=True), 1e-12)
    return W


def _smooth(W: np.ndarray, faces, rounds: int) -> np.ndarray:
    """Each vertex's weights averaged half-and-half with its neighbours' (over the faces' edges), `rounds` times."""
    if faces is None or not rounds:
        return W
    F = np.asarray(faces, np.int64)
    a = np.r_[F[:, 0], F[:, 1], F[:, 2], F[:, 1], F[:, 2], F[:, 0]]
    b = np.r_[F[:, 1], F[:, 2], F[:, 0], F[:, 0], F[:, 1], F[:, 2]]
    deg = np.maximum(np.bincount(a, minlength=len(W)), 1).astype(np.float64)[:, None]
    for _ in range(rounds):
        acc = np.zeros_like(W)
        np.add.at(acc, a, W[b])
        W = 0.5 * W + 0.5 * acc / deg
    return W


def pose(bones: list[dict], verts: np.ndarray, J: np.ndarray, W: np.ndarray, turns: dict) -> np.ndarray:
    """Linear blend skinning of the rest vertices with some bones turned: {bone: (axis [x, y, z], degrees)} about
    their heads, children following. For checking weights (bend an elbow, look at it)."""
    n = len(bones)
    M = np.tile(np.eye(4), (n, 1, 1))
    for i, b in enumerate(bones):  # parents come first
        L = np.eye(4)
        if b["name"] in turns:
            ax, deg = turns[b["name"]]
            ax = np.asarray(ax, float) / np.linalg.norm(ax)
            t = np.radians(deg)
            K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
            R = np.eye(3) + np.sin(t) * K + (1 - np.cos(t)) * K @ K
            h = np.asarray(b["head"], float)
            L[:3, :3], L[:3, 3] = R, h - R @ h
        M[i] = (M[b["parent"]] if b["parent"] >= 0 else np.eye(4)) @ L
    V4 = np.c_[verts, np.ones(len(verts))]
    out = np.zeros((len(verts), 3))
    for c in range(J.shape[1]):
        out += W[:, c:c + 1] * np.einsum("nij,nj->ni", M[J[:, c]], V4)[:, :3]
    return out
