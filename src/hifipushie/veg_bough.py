"""Bough cards: what a low LOD draws instead of twigs. As foliage artists do it: real limb ends of the grown tree
itself (the wood, its branchlets and every twig on them) are baked into pictures (colour, alpha, normal, mask: the
same maps a twig card has), a few per tree, and a card with one of them stands wherever the tree has such a bough.
The fewer cards a budget allows, the larger the boughs it is cut into (`plan`): a hierarchy by LOD from the same
tree. (Enlarging a twig's picture instead, the earlier way, drew a pine as fern fans and a spruce as palm fronds.)"""
from __future__ import annotations

import json
import math

import numpy as np

from . import veg_leaf
from .vegetation import _child, _u

BOUGH = {"variants": 4, "size": 384, "verts": 7, "cross": 2, "cup": 0.12}  # cross 2 = the bough from its face AND from its side
TRIS = BOUGH["verts"] * BOUGH["cross"]  # triangles a bough card costs (a fan per card)
_CACHE: dict = {}


def _norm(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def subtrees(tree: dict) -> dict:
    """Per node: `count` = twigs its subtree carries, `reach` = how far along the wood its farthest twig stands (m;
    -1 where it carries none)."""
    if "_boughs" in tree:
        return tree["_boughs"]
    tw = veg_leaf.place(tree)
    P, par = tree["pos"], tree["parent"]
    n = len(P)
    seg = np.linalg.norm(P - P[par], axis=1)
    cnt = np.bincount(tw["node"], minlength=n).astype(np.int64)
    lf = tree["spec"]["leaves"]
    tl = float({**veg_leaf.TWIG, **(lf.get("twig") or {})}["length"])
    reach = np.where(cnt > 0, 0.6 * tl, -1.0)
    for i in range(n - 1, 0, -1):  # (parents come first in the arrays)
        if reach[i] >= 0:
            p = par[i]
            reach[p] = max(reach[p], reach[i] + seg[i])
            cnt[p] += cnt[i]
    tree["_boughs"] = {"count": cnt, "reach": reach, "twigs": tw, "twig_length": tl}
    return tree["_boughs"]


def roots(tree: dict, size: float) -> np.ndarray:
    """The nodes where boughs no longer than `size` m begin: together they carry every twig once."""
    st = subtrees(tree)
    r, par = st["reach"], tree["parent"]
    m = (r >= 0) & (r <= size) & ((r[par] > size) | (np.arange(len(r)) <= 1))
    m[0] = False
    return np.flatnonzero(m)


def plan(tree: dict, cards: int) -> dict:
    """Cut the foliage into at most `cards` boughs: the smallest bough size that needs no more. Returns {"roots",
    "size" (m), "owner" (per twig: index into roots, -1 = left out)}."""
    st = subtrees(tree)
    lo, hi = st["twig_length"], max(0.7 * tree["height"], st["twig_length"] * 2)
    best = roots(tree, hi)
    if len(best) > cards:  # (even the largest cut is too many: the fullest ones)
        best = best[np.argsort(-st["count"][best], kind="stable")[: max(cards, 0)]]
        size = hi
    else:
        size = hi
        for _ in range(18):
            mid = math.sqrt(lo * hi)
            r_ = roots(tree, mid)
            if len(r_) <= cards:
                best, size, hi = r_, mid, mid
            else:
                lo = mid
    own = -np.ones(len(tree["pos"]), np.int64)
    own[best] = np.arange(len(best))
    par = tree["parent"]
    for i in range(2, len(own)):
        if own[i] < 0:
            own[i] = own[par[i]]
    return {"roots": best, "size": float(size), "owner": own[st["twigs"]["node"]], "node_owner": own}


def _frames(tree: dict, pl: dict):
    """Each bough's frame (columns x, y = its run from the root to the middle of its twigs, z = its upper side; a
    hanging or upright bough turns its face outward from the trunk) and its length along y (m)."""
    st = subtrees(tree)
    tw, P = st["twigs"], tree["pos"]
    k = len(pl["roots"])
    ok = pl["owner"] >= 0
    cen = np.zeros((k, 3))
    cnt = np.bincount(pl["owner"][ok], minlength=k).astype(float)
    tips = tw["pos"] + tw["frame"][:, :, 1] * (0.5 * st["twig_length"] * tw["scale"])[:, None]
    np.add.at(cen, pl["owner"][ok], tips[ok])
    cen /= np.maximum(cnt, 1)[:, None]
    base = P[pl["roots"]]
    y = cen - base
    short = np.linalg.norm(y, axis=1) < 0.05
    y[short] = (P[pl["roots"]] - P[tree["parent"][pl["roots"]]])[short]
    y = _norm(y)
    up = np.array([0, 0, 1.0])
    z = up[None] - y * y[:, 2:3]
    steep = np.abs(y[:, 2]) > 0.8
    out = base * [1, 1, 0] + 1e-6
    zo = out - y * np.sum(out * y, axis=1, keepdims=True)
    z[steep] = zo[steep]
    z = _norm(z)
    # a bough's face is the plane it spreads in: a pine's plate is seen from above, a spruce's hanging comb or a
    # willow's curtain from its side (every picture from above drew a spruce as slats of a blind)
    d = tips[ok] - cen[pl["owner"][ok]]
    M = np.zeros((k, 3, 3))
    np.add.at(M, pl["owner"][ok], d[:, :, None] * d[:, None, :])
    many = cnt >= 4
    if many.any():
        w_, v_ = np.linalg.eigh(M[many])
        thin = v_[:, :, 0]  # the direction it is thinnest in
        flat = w_[:, 0] < 0.6 * w_[:, 1]  # (a round bough has no face: keep the upper side)
        thin = thin - y[many] * np.sum(thin * y[many], axis=1, keepdims=True)
        good = flat & (np.linalg.norm(thin, axis=1) > 0.3)
        thin = _norm(thin)
        ref = np.where(np.abs(thin[:, 2:3]) > 0.3, up[None], out[many])  # its face up, or outward from the trunk
        thin = thin * np.where(np.sum(thin * ref, axis=1, keepdims=True) < 0, -1.0, 1.0)
        zi = z[many]
        zi[good] = thin[good]
        z[many] = zi
    Fr = np.stack([np.cross(y, z), y, z], axis=2)
    ext = np.zeros(k)
    along = np.einsum("ni,ni->n", tips[ok] - base[pl["owner"][ok]], y[pl["owner"][ok]]) + 0.5 * st["twig_length"] * tw["scale"][ok]
    np.maximum.at(ext, pl["owner"][ok], along)
    return Fr, np.maximum(ext, 0.5 * st["twig_length"]), cnt


def _mesh(tree: dict, pl: dict, b: int, Fr: np.ndarray, leaves: dict) -> dict:
    """One bough as a mesh in its own frame: its wood and every twig on it (the card picture's twigs: true-width
    needles, whole sprays)."""
    st = subtrees(tree)
    tw, P, par, rad = st["twigs"], tree["pos"], tree["parent"], tree["radius"]
    root = int(pl["roots"][b])
    cs = veg_leaf.card_spec(leaves)
    nv = int({**veg_leaf.TWIG, **cs["twig"]}["variants"])
    Vs, Fs, Ms, Cs, Gs = [], [], [], [], []
    base = 0

    def add(V, F, mat, col, rgb=None):
        nonlocal base
        Vs.append((V - P[root]) @ Fr)
        Fs.append(F + base)
        Ms.append(np.broadcast_to(mat, (len(F),)).copy())
        Cs.append(np.broadcast_to(col, (len(V),)).copy())
        Gs.append(np.full((len(V), 3), np.nan) if rgb is None else rgb)
        base += len(V)

    nodes = np.flatnonzero(pl["node_owner"] == b)
    for i in nodes[nodes != root]:
        V, F = veg_leaf._stem(np.array([P[par[i]], P[i]]), max(float(rad[par[i]]), 0.003), max(float(rad[i]), 0.002), sides=4)
        add(V, F, 0, 1.0)
    twm = {}
    for t in np.flatnonzero(pl["owner"] == b):
        v_ = int(tw["variant"][t]) % nv
        if v_ not in twm:
            twm[v_] = veg_leaf.twig_mesh(cs, v_)
        m = twm[v_]
        cd = float({**veg_leaf.CARD, **(leaves.get("card") or {})}["scale"])
        V = (m["V"] * (tw["scale"][t] * cd)) @ tw["frame"][t].T + tw["pos"][t]
        add(V, m["F"], m["mat"], m["col"] * (0.85 + 0.3 * float(_u(tw["key"][t:t + 1], 77)[0])), m.get("rgb"))
    return {"V": np.vstack(Vs), "F": np.vstack(Fs), "mat": np.concatenate(Ms), "col": np.concatenate(Cs), "rgb": np.vstack(Gs)}


def atlas(tree: dict, leaves: dict | None = None, wood_color=(0.3, 0.25, 0.2), cards: int = 400) -> dict:
    """The tree's bough atlas at a cut of about `cards` boughs: `variants` pictures of its own boughs (the fullest
    typical ones: between the 55th and 95th percentile by twigs), with the cards cut to them. Same keys as a twig
    atlas (color RGBA, normal, mask, cards, fill, grid, size, triangles), plus "extent" (each picture's length, m)
    and "size_m" (the cut)."""
    leaves = leaves or tree["spec"]["leaves"]
    pl = plan(tree, cards)
    key = json.dumps([tree["spec"], leaves, list(wood_color), round(pl["size"], 2)], sort_keys=True, default=float)
    if key in _CACHE:
        return _CACHE[key]
    Fr, ext, cnt = _frames(tree, pl)
    nv, size = BOUGH["variants"], BOUGH["size"]
    order = np.argsort(cnt * (0.5 + ext / max(ext.max(), 1e-9)), kind="stable")
    pick = [int(order[int(q * (len(order) - 1))]) for q in np.linspace(0.6, 0.97, nv)] if len(order) else []
    g = int(math.ceil(math.sqrt(max(len(pick) * BOUGH["cross"], 1))))
    A = {"color": np.zeros((g * size, g * size, 4), np.float32), "normal": np.zeros((g * size, g * size, 3), np.float32),
         "mask": np.zeros((g * size, g * size, 3), np.float32)}
    A["normal"][...] = (0.5, 0.5, 1.0)
    out_cards, fills, extent = [], [], []
    col = leaves.get("color", [0.16, 0.3, 0.08])
    for i, b in enumerate(pick):
        mesh = _mesh(tree, pl, b, Fr[b], leaves)
        parts = []
        for side in range(BOUGH["cross"]):  # its face, then the same bough seen from its side on a card across the first
            V = mesh["V"] if side == 0 else np.c_[mesh["V"][:, 2], mesh["V"][:, 1], -mesh["V"][:, 0]]
            R = veg_leaf.rasterize({**mesh, "V": V}, col, wood_color, size)
            r, c = divmod(BOUGH["cross"] * i + side, g)
            sl = (slice(r * size, (r + 1) * size), slice(c * size, (c + 1) * size))
            A["color"][sl][..., :3] = R["color"]
            A["color"][sl][..., 3] = R["alpha"]
            A["normal"][sl] = R["normal"]
            A["mask"][sl] = R["mask"]
            cm = veg_leaf.card_mesh(R["alpha"], R["frame"], BOUGH["verts"], BOUGH["cup"] if side == 0 else 0.0, 1, 0.0, max(float(ext[b]), 0.1), 0)
            if side == 0:
                fills.append(float((R["alpha"] > 0.5).sum()) * (R["frame"][2] / size) ** 2 / max(cm["area"], 1e-12))
            else:
                cm["V"] = np.c_[-cm["V"][:, 2], cm["V"][:, 1], cm["V"][:, 0]]
            cm["uv"] = np.c_[(c + cm["uv"][:, 0]) / g, 1 - (r + 1 - cm["uv"][:, 1]) / g]
            parts.append(cm)
        nv0 = np.cumsum([0] + [len(q["V"]) for q in parts])
        out_cards.append({"V": np.vstack([q["V"] for q in parts]), "F": np.vstack([q["F"] + nv0[j] for j, q in enumerate(parts)]),
                          "uv": np.vstack([q["uv"] for q in parts]), "area": sum(q["area"] for q in parts)})
        extent.append(float(ext[b]))
    leaf_px = (A["color"][..., 3] > 0.6) & (A["mask"][..., 0] > 0.5)
    if leaf_px.any():  # (as the twig atlas: `leaves.color` is the leaf as seen lit)
        lum = lambda c_: 0.2126 * c_[..., 0] + 0.7152 * c_[..., 1] + 0.0722 * c_[..., 2]
        seen = float(np.median(lum(A["color"][leaf_px][:, :3]) * A["mask"][leaf_px][:, 2]))
        A["color"][..., :3] = np.clip(A["color"][..., :3] * float(np.clip(lum(np.asarray(col, float)) / max(seen, 1e-6), 1.0, 1.8)), 0, 1)
    if len(_CACHE) > 8:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = {**A, "cards": out_cards, "fill": float(np.mean(fills)) if fills else 0.0, "grid": g, "size": size,
                   "triangles": int(np.mean([len(c["F"]) for c in out_cards])) if out_cards else TRIS,
                   "extent": extent, "size_m": pl["size"], "bough": True}
    return _CACHE[key]


def place(tree: dict, cards: int, at: dict) -> dict:
    """Where the bough cards stand on this tree for a budget of `cards`: one per bough of `plan`, in its own frame,
    scaled to its own length against the picture's, the picture nearest it in length. The same keys as twig
    placements (pos, frame, scale, node, key, card)."""
    pl = plan(tree, cards)
    k = len(pl["roots"])
    if not k or not at["cards"]:
        return {"pos": np.zeros((0, 3)), "frame": np.zeros((0, 3, 3)), "scale": np.zeros(0), "variant": np.zeros(0, int),
                "node": np.zeros(0, int), "key": np.zeros(0, np.uint64), "card": np.zeros(0, int)}
    Fr, ext, cnt = _frames(tree, pl)
    key = _child(tree["key"][pl["roots"]], 31)
    E = np.asarray(at["extent"])
    near = np.argsort(np.abs(np.log(np.maximum(ext[:, None], 1e-3) / np.maximum(E[None], 1e-3))), axis=1)[:, : min(2, len(E))]
    card = near[np.arange(k), (_u(key, 3) * near.shape[1]).astype(int) % near.shape[1]]
    scale = np.clip(ext / np.maximum(E[card], 1e-6), 0.45, 1.35)
    return {"pos": tree["pos"][pl["roots"]], "frame": Fr, "scale": scale, "variant": card.astype(int), "node": pl["roots"].astype(int),
            "key": key, "card": card.astype(int), "size_m": pl["size"]}


def most(tree: dict) -> int:
    """The most bough cards this tree can use (its foliage cut at twice a twig's length)."""
    st = subtrees(tree)
    return int(len(roots(tree, 2.0 * st["twig_length"])))
