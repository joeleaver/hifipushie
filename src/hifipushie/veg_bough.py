"""Bough cards: what a low LOD draws instead of twigs. As foliage artists do it: real limb ends of the grown tree
itself (the wood, its branchlets and every twig on them) are baked into pictures (colour, alpha, normal, mask: the
same maps a twig card has), a few per tree, and a card with one of them stands wherever the tree has such a bough.
The fewer cards a budget allows, the larger the boughs it is cut into (`plan`): a hierarchy by LOD from the same
tree. (Enlarging a twig's picture instead, the earlier way, drew a pine as fern fans and a spruce as palm fronds.)"""
from __future__ import annotations

import json
import math
import os

import numpy as np

from numba import njit

from . import veg_leaf
from .vegetation import _child, _u

BOUGH = {"variants": 4, "size": 384, "verts": 7, "cross": 2, "cup": 0.12}  # cross 2 = the bough from its face AND from its side
TRIS = BOUGH["verts"] * BOUGH["cross"]  # triangles the richest bough card costs (a fan per card)
# The card's cut, richest first. A budget buys GRANULARITY before polish: a 20k spruce cut into 937 fourteen-triangle
# cards was 2.7 m boughs (palm fronds from 30 m); the same triangles as six-triangle cards are twice as many, smaller.
SINGLE = os.environ.get("HIFIPUSHIE_BOUGH_SINGLE", "0") != "0"  # (tried: one card of each pair, the one facing out: a spruce went ragged and see-through from the front, its flank cards edge-on)
FULL = float(os.environ.get("HIFIPUSHIE_BOUGH_FULL", "0.45"))  # the share of the finest cut's boughs the fullest LOD draws
FULL_LEAST = 500
PAIR_BELOW = 7.0  # m over the ground: boughs a player stands beside keep their crossed pair
CULL = os.environ.get("HIFIPUSHIE_BOUGH_CULL", "0") != "0"  # (tried: a spruce's or a pine's boughs are ALL seen from somewhere; nothing to cull)
THIN, THIN_GROW = 0.08, 2.4  # the least share of the finest cut a thinned LOD keeps; the most its cards grow
FORMS = ({"verts": 7, "centre": True, "cup": 0.12}, {"verts": 7, "centre": False, "cup": 0.08})


def _ground(tree: dict, P: np.ndarray) -> np.ndarray:
    from . import vegetation
    return np.asarray(vegetation.ground_at(tree["spec"], P), float)


def tris(form: int = 0) -> int:
    f = FORMS[form]
    return (f["verts"] if f["centre"] else f["verts"] - 2) * BOUGH["cross"]


OUTER = {"layers": 2, "share": 0.25, "px": 0.07, "width": 0.35}  # a bough is drawn if, from some side, this share of it is within the first `layers` cards


@njit(cache=True)
def _layer_counts(X, Y, Z, own, k, W, H, L):
    """Rasterise triangles (X, Y, Z per corner: pixels and depth, nearer = smaller) keeping per pixel the L nearest
    OWNERS; returns per owner (pixels it covers, pixels where it is among the L nearest)."""
    zb = np.full((L, H, W), 1e30)
    ib = np.full((L, H, W), -1, np.int64)
    tot = np.zeros(k, np.int64)
    for f in range(X.shape[0]):
        x0, x1, x2 = X[f, 0], X[f, 1], X[f, 2]
        y0, y1, y2 = Y[f, 0], Y[f, 1], Y[f, 2]
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-9:
            continue
        xa, xb = max(int(np.floor(min(x0, x1, x2))), 0), min(int(np.ceil(max(x0, x1, x2))), W - 1)
        ya, yb = max(int(np.floor(min(y0, y1, y2))), 0), min(int(np.ceil(max(y0, y1, y2))), H - 1)
        o = own[f]
        for py in range(ya, yb + 1):
            for px in range(xa, xb + 1):
                cx, cy = px + 0.5, py + 0.5
                w0 = ((y1 - y2) * (cx - x2) + (x2 - x1) * (cy - y2)) / den
                w1 = ((y2 - y0) * (cx - x2) + (x0 - x2) * (cy - y2)) / den
                w2 = 1.0 - w0 - w1
                if w0 < 0 or w1 < 0 or w2 < 0:
                    continue
                z = w0 * Z[f, 0] + w1 * Z[f, 1] + w2 * Z[f, 2]
                tot[o] += 1
                had = False
                for l in range(L):  # (a card's own second triangle is not another layer)
                    if ib[l, py, px] == o:
                        had = True
                        if z < zb[l, py, px]:
                            zb[l, py, px] = z
                        break
                if had:
                    continue
                zi, oi = z, o
                for l in range(L):
                    if zi < zb[l, py, px]:
                        zb[l, py, px], zi = zi, zb[l, py, px]
                        ib[l, py, px], oi = oi, ib[l, py, px]
    vis = np.zeros(k, np.int64)
    for l in range(L):
        for py in range(H):
            for px in range(W):
                if ib[l, py, px] >= 0:
                    vis[ib[l, py, px]] += 1
    return tot, vis


def outer(tree: dict, cards: int) -> np.ndarray:
    """Per bough of the cut `plan(tree, cards)`: is it seen from outside the crown? (From 22 directions all round, above
    and below, a bough counts where it is among the first `OUTER.layers` cards along the ray; it is kept if from some
    direction `OUTER.share` of it is.) The boughs behind those are overdraw and nothing else: a 20k spruce drew 6.6
    card layers per covered pixel, and a stand of them cost 1.6x the anime spruce's GPU time in Godot."""
    memo = tree.setdefault("_bough_outer", {})
    if cards in memo:
        return memo[cards]
    pl = plan(tree, cards)
    k = len(pl["roots"])
    if k < 8:
        memo[cards] = np.ones(k, bool)
        return memo[cards]
    Fr, ext, cnt = _frames(tree, pl)
    base = tree["pos"][pl["roots"]]
    w = OUTER["width"] * ext
    x, y, z = Fr[:, :, 0], Fr[:, :, 1], Fr[:, :, 2]
    tip = base + y * ext[:, None]
    quads = []
    for side in (x, z):  # the face card and the card across it
        quads.append(np.stack([base - side * w[:, None], base + side * w[:, None], tip + side * w[:, None], tip - side * w[:, None]], axis=1))
    Q = np.concatenate(quads)  # (2k, 4, 3)
    T = np.concatenate([Q[:, [0, 1, 2]], Q[:, [0, 2, 3]]])  # (4k, 3, 3)
    own = np.tile(np.arange(k), 4)
    dirs = [(az, 10.0) for az in range(0, 360, 45)] + [(az, 50.0) for az in range(0, 360, 90)] + [(0.0, 90.0)] \
        + [(az + 22.5, -35.0) for az in range(0, 360, 45)] + [(0.0, -90.0)]
    if OUTER.get("far"):  # (seen from afar: from the side and from a hill, never from under it)
        dirs = [(az, 5.0) for az in range(0, 360, 30)] + [(az + 15.0, 35.0) for az in range(0, 360, 45)]
    px = max(OUTER["px"], 0.12 * float(np.median(ext)))
    best = np.zeros(k)
    for az, el in dirs:
        ca, sa, ce, se = math.cos(math.radians(az)), math.sin(math.radians(az)), math.cos(math.radians(el)), math.sin(math.radians(el))
        d = np.array([sa * ce, ca * ce, se])  # toward the eye
        r = np.array([ca, -sa, 0.0])
        u = np.cross(d, r)
        P = np.stack([T @ r, T @ u, -(T @ d)], axis=-1)
        lo = P[..., :2].reshape(-1, 2).min(0)
        X, Y = (P[..., 0] - lo[0]) / px, (P[..., 1] - lo[1]) / px
        W, H = int(X.max()) + 2, int(Y.max()) + 2
        tot, vis = _layer_counts(np.ascontiguousarray(X), np.ascontiguousarray(Y), np.ascontiguousarray(P[..., 2]), own, k, W, H, int(OUTER["layers"]))
        best = np.maximum(best, np.where(tot >= 3, vis / np.maximum(tot, 1), 0.0))
    keep = best >= OUTER["share"]
    keep |= dead_boughs(tree, pl)  # (dead wood is already a few cards)
    memo[cards] = keep
    return keep


def limbs_on(tree: dict) -> bool:
    """`leaves.card.limbs`: the species' crown is built of flat LIMBS (a spruce's tiers: long boughs sweeping out with
    hanging branchlets), so every LOD draws each whole limb on a crossed pair of cards (seen from above and from its
    side: the drooping comb) UNDER the fine bough cards. The limbs carry the tiers, the dark mass toward the trunk and
    a dense silhouette; without them a spruce thinned for overdraw was a cone of separate round pads."""
    return bool((tree["spec"]["leaves"].get("card") or {}).get("limbs")) and not tree.get("clump")


def limb_plan(tree: dict) -> dict:
    """The tree cut into whole limbs (each first-order branch one bough; the leader's top its own)."""
    if "_limb_plan" not in tree:
        st = subtrees(tree)
        lim = (tree["spec"]["leaves"].get("card") or {}).get("limbs")
        hi = max(0.7 * tree["height"], st["twig_length"] * 2)
        if not isinstance(lim, bool) and float(lim) > 0:  # a size in m: the crown's MASSES (a pine's foliage plates), not whole limbs
            hi = max(float(lim), st["twig_length"] * 2)
        tree["_limb_plan"] = plan(tree, len(roots(tree, hi)))
    return tree["_limb_plan"]


def extra(tree: dict) -> int:
    """Triangles the limb layer costs at every LOD (0 without one)."""
    if not limbs_on(tree):
        return 0
    pl = limb_plan(tree)
    return int((~dead_boughs(tree, pl)).sum()) * tris(0)


def fit(tree: dict, triangles: int) -> tuple[int, int]:
    """(cards, form) for a foliage triangle count. While the count buys at least `THIN` of the tree's finest cut
    (`most`) on the cheapest cards, the LOD is that finest cut THINNED: some of its boughs left out, the rest drawn
    larger (`place`), all LODs sharing one atlas and one silhouette (what a foliage artist does: remove cards, grow
    the rest; a spruce's LOD 1 re-cut into 425 whole-limb cards lost 15% of its covered area in Godot and its top).
    Under that, the tree is re-cut into fewer, larger boughs on the richest cards. Remembered on the tree."""
    m = most(tree)
    mr = int(outer(tree, m).sum()) if CULL else len(plan(tree, m)["roots"])  # (boughs nothing sees are not drawn)
    cheap = len(FORMS) - 1
    t = max(int(triangles), 0)
    memo = tree.setdefault("_bough_form", {})
    if mr and t // tris(0) >= THIN * mr and os.environ.get("HIFIPUSHIE_BOUGH_THIN", "1") != "0":
        # How many: what the triangles buy, and never more than `FULL` of the cut: more cards
        # only stack layers (a 20k spruce, card layers per covered pixel in the file: all 1695 boughs 6.6; 937 of
        # them grown to the same cover 4.7; a stand of the first cost 1.6x the anime spruce's GPU time in Godot).
        # The triangles this leaves go to the wood (veg_export._budget).
        form = cheap
        t_fine = max(t - extra(tree), tris(form))  # (the limb layer, where the species has one, comes first)
        n = max(min(t_fine // tris(form), max(int(FULL * mr), min(mr, FULL_LEAST))), 1)  # (a thin crown keeps all its boughs)
        memo[n] = (form, m, False)
        return n, form
    n = min(t // tris(0), m)
    n2 = len(plan(tree, n)["roots"])
    memo[n] = memo[n2] = (0, None, False)
    return n2, 0


def form_of(tree: dict, cards: int) -> int:
    return int((tree.get("_bough_form") or {}).get(cards, (0, None))[0])


def thinned_of(tree: dict, cards: int) -> bool:
    """A LOD under the fullest one (it draws single cards)."""
    return bool((tree.get("_bough_form") or {}).get(cards, (0, None, False))[2])


def cost(tree: dict, cards: int) -> int:
    """Triangles a card of this LOD costs at most (a thinned LOD's bough is one card of the pair)."""
    t = tris(form_of(tree, cards))
    return t // 2 if thinned_of(tree, cards) and SINGLE else t


def base_of(tree: dict, cards: int):
    """The cut a thinned LOD's cards come from (a card count for `plan`), or None: the cut is `cards` itself."""
    return (tree.get("_bough_form") or {}).get(cards, (0, None))[1]


DEAD_SHARE, DEAD_MIN = 0.08, 12  # of a budget's bough cards, the most that draw dead wood (and the fewest a tree with dead wood keeps)
LEADER = 1.2  # m: the most of the trunk's own top one bough card stands for
DEAD_THIN = 0.5  # the share of a dead bough's twigs its picture is baked from (real alpha gaps)
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
    # the trunk's own top is never one big bough (its picture was some limb's, stood upright on the leader: a flag):
    # limbs off the trunk start their own boughs, and the leader's tip is a small one of its own
    o = tree["order"]
    lead = min(size, LEADER)
    m = (r >= 0) & (r <= size) & ((r[par] > size) | (np.arange(len(r)) <= 1) | (o[par] == 0)) & (o > 0)
    m |= (o == 0) & (r >= 0) & (r <= lead) & (r[par] > lead)
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
    pl = {"roots": best, "size": float(size), "owner": own[st["twigs"]["node"]], "node_owner": own}
    # dead wood is a haze, not a mass: at a budget it gets few cards (`DEAD_SHARE` of them at most, the longest boughs),
    # and the rest of its twigs are simply not drawn (every dead bough carded, a stand tree's bare stem wore a brown fur)
    isd = dead_boughs(tree, pl)
    cap = int(max(DEAD_SHARE * cards, min(DEAD_MIN, isd.sum())))
    if isd.sum() > cap:
        di = np.flatnonzero(isd)
        # spread up the stem: the longest bough of each height band first
        z = tree["pos"][best[di], 2]
        band = np.minimum((np.argsort(np.argsort(z)) * cap // max(len(di), 1)), cap - 1)
        keep_d = np.zeros(len(di), bool)
        r_ = st["reach"][best[di]]
        for b_ in range(cap):
            m_ = np.flatnonzero(band == b_)
            if len(m_):
                keep_d[m_[np.argmax(r_[m_])]] = True
        drop = np.zeros(len(best), bool)
        drop[di[~keep_d]] = True
        new = np.cumsum(~drop) - 1
        new[drop] = -1
        remap = lambda o: np.where(o >= 0, new[np.maximum(o, 0)], -1)
        pl = {"roots": best[~drop], "size": float(size), "owner": remap(pl["owner"]), "node_owner": remap(own), "dead_left_out": int(drop.sum())}
    return pl


def dead_boughs(tree: dict, pl: dict) -> np.ndarray:
    """Per bough of the plan: it is dead wood (most of its cards are dead-twig cards)."""
    part = subtrees(tree)["twigs"].get("part")
    k = len(pl["roots"])
    if part is None or not k:
        return np.zeros(k, bool)
    ok = pl["owner"] >= 0
    tot = np.bincount(pl["owner"][ok], minlength=k)
    dead = np.bincount(pl["owner"][ok], weights=(part[ok] == 1).astype(float), minlength=k)
    return dead > 0.5 * np.maximum(tot, 1)


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
    dp = veg_leaf.dead_part(leaves)
    cs_d = veg_leaf.card_spec(dp) if dp is not None else None
    part = tw.get("part")
    for t in np.flatnonzero(pl["owner"] == b):
        v_ = int(tw["variant"][t]) % nv
        isd = part is not None and part[t] == 1  # a dead twig: bare, grey (its own part's picture)
        if isd and float(_u(tw["key"][t:t + 1], 78)[0]) > DEAD_THIN:
            continue  # (a dead bough's picture is thin: sky shows through it)
        if isd:
            v_ = int(tw["card"][t]) if tw.get("card") is not None else v_
        if (v_, isd) not in twm:
            m_ = veg_leaf.twig_mesh(cs_d if isd else cs, v_)
            if isd:
                wc_ = np.asarray(dp.get("wood_color", [0.45, 0.42, 0.38]), float)
                own_ = np.isnan(m_["rgb"][:, 0])  # (lichen keeps its colour; wood takes the part's grey x its own tone)
                m_ = {**m_, "rgb": np.where(own_[:, None], wc_[None] * m_["col"][:, None], m_["rgb"]), "col": m_["col"] * 0 + 1.0}
            twm[(v_, isd)] = m_
        m = twm[(v_, isd)]
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
    fi = form_of(tree, cards)
    pl = plan(tree, base_of(tree, cards) or cards)
    fm = FORMS[fi]
    key = json.dumps([tree["spec"], leaves, list(wood_color), round(pl["size"], 2), fi], sort_keys=True, default=float)
    if key in _CACHE:
        return _CACHE[key]
    # on disk too, by the tree itself and this module's source (a stand look bakes a dozen of these: half an hour)
    import hashlib
    from pathlib import Path
    dkey = "bough" + hashlib.sha1(np.ascontiguousarray(tree["pos"]).tobytes() + Path(__file__).read_bytes() + key.encode()).hexdigest()
    got = veg_leaf._disk_get(dkey)
    if got is not None:
        if len(_CACHE) > 8:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = got
        return got
    Fr, ext, cnt = _frames(tree, pl)
    nv, size = BOUGH["variants"], BOUGH["size"]
    order = np.argsort(cnt * (0.5 + ext / max(ext.max(), 1e-9)), kind="stable")
    isd = dead_boughs(tree, pl)
    lv_, dd_ = order[~isd[order]], order[isd[order]]  # live boughs' pictures, and (when the shade killed limbs) dead ones'
    pick = [int(lv_[int(q * (len(lv_) - 1))]) for q in np.linspace(0.6, 0.97, nv)] if len(lv_) else []
    pick += [int(dd_[int(q * (len(dd_) - 1))]) for q in np.linspace(0.6, 0.95, 2)] if len(dd_) else []
    jobs = [(pl, Fr, ext, b, fm) for b in pick]
    n_fine = len(pick)
    limb_extent = []
    if limbs_on(tree) and base_of(tree, cards):
        plL = limb_plan(tree)
        FrL, extL, cntL = _frames(tree, plL)
        liveL = np.flatnonzero(~dead_boughs(tree, plL))
        oL = liveL[np.argsort(cntL[liveL] * (0.5 + extL[liveL] / max(extL.max(), 1e-9)), kind="stable")]
        for q in (np.linspace(0.35, 0.95, nv) if len(oL) else []):  # short upper limbs to the long low ones
            b_ = int(oL[int(q * (len(oL) - 1))])
            jobs.append((plL, FrL, extL, b_, FORMS[0]))
            limb_extent.append(float(extL[b_]))
    g = int(math.ceil(math.sqrt(max(len(jobs) * BOUGH["cross"], 1))))
    A = {"color": np.zeros((g * size, g * size, 4), np.float32), "normal": np.zeros((g * size, g * size, 3), np.float32),
         "mask": np.zeros((g * size, g * size, 3), np.float32)}
    A["normal"][...] = (0.5, 0.5, 1.0)
    out_cards, fills, extent, singles = [], [], [], []
    col = leaves.get("color", [0.16, 0.3, 0.08])
    for i, (pl_j, Fr_j, ext_j, b, fm_j) in enumerate(jobs):
        mesh = _mesh(tree, pl_j, b, Fr_j[b], leaves)
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
            cm = veg_leaf.card_mesh(R["alpha"], R["frame"], fm_j["verts"], fm_j["cup"] if side == 0 else 0.0, 1, 0.0, max(float(ext_j[b]), 0.1), 0, centre=fm_j["centre"])
            if side == 0:
                (fills if i < n_fine else []).append(float((R["alpha"] > 0.5).sum()) * (R["frame"][2] / size) ** 2 / max(cm["area"], 1e-12))
            else:
                cm["V"] = np.c_[-cm["V"][:, 2], cm["V"][:, 1], cm["V"][:, 0]]
            cm["uv"] = np.c_[(c + cm["uv"][:, 0]) / g, 1 - (r + 1 - cm["uv"][:, 1]) / g]
            parts.append(cm)
        nv0 = np.cumsum([0] + [len(q["V"]) for q in parts])
        out_cards.append({"V": np.vstack([q["V"] for q in parts]), "F": np.vstack([q["F"] + nv0[j] for j, q in enumerate(parts)]),
                          "uv": np.vstack([q["uv"] for q in parts]), "area": sum(q["area"] for q in parts)})
        if i < n_fine:
            singles.append(parts)
            extent.append(float(ext[b]))
    # after the n crossed pairs: each pair's face card alone (n .. 2n - 1), then its side card alone (2n .. 3n - 1),
    # then the limb pairs (`limb_first` ..)
    limb_cards, out_cards = out_cards[n_fine:], out_cards[:n_fine]
    out_cards += [{"V": q[j]["V"], "F": q[j]["F"], "uv": q[j]["uv"], "area": q[j]["area"]} for j in (0, 1) for q in singles]
    limb_first = len(out_cards)
    out_cards += limb_cards
    leaf_px = (A["color"][..., 3] > 0.6) & (A["mask"][..., 0] > 0.5)
    if leaf_px.any():  # (as the twig atlas: `leaves.color` is the leaf as seen lit)
        lum = lambda c_: 0.2126 * c_[..., 0] + 0.7152 * c_[..., 1] + 0.0722 * c_[..., 2]
        seen = float(np.median(lum(A["color"][leaf_px][:, :3]) * A["mask"][leaf_px][:, 2]))
        k_ = float(np.clip(lum(np.asarray(col, float)) / max(seen, 1e-6), 1.0, 1.8))
        g_ = len(out_cards) and A["color"].shape[0] // size
        for j_, dead_ in enumerate([isd[b_] for b_ in pick] + [False] * len(limb_extent)):  # (the foliage's pictures only: dead boughs keep their grey)
            if not dead_:
                for side in range(BOUGH["cross"]):
                    r, c = divmod(BOUGH["cross"] * j_ + side, g_)
                    A["color"][r * size:(r + 1) * size, c * size:(c + 1) * size, :3] = np.clip(A["color"][r * size:(r + 1) * size, c * size:(c + 1) * size, :3] * k_, 0, 1)
    if len(_CACHE) > 8:
        _CACHE.pop(next(iter(_CACHE)))
    A = {k_: np.clip(v_ * 255 + 0.5, 0, 255).astype(np.uint8).astype(np.float32) / 255.0 for k_, v_ in A.items()}  # (as the disk keeps it)
    _CACHE[key] = {**A, "cards": out_cards, "fill": float(np.mean(fills)) if fills else 0.0, "grid": g, "size": size,
                   "triangles": int(np.mean([len(c["F"]) for c in out_cards[:len(pick)]])) if out_cards else tris(fi), "pairs": len(pick),
                   "extent": extent, "size_m": pl["size"], "bough": True, "dead": [bool(isd[b_]) for b_ in pick],
                   "limb_first": limb_first if limb_extent else None, "limb_extent": limb_extent}
    veg_leaf._disk_put(dkey, _CACHE[key])
    return _CACHE[key]


def place(tree: dict, cards: int, at: dict) -> dict:
    """Where the bough cards stand on this tree for a budget of `cards`: one per bough of `plan`, in its own frame,
    scaled to its own length against the picture's, the picture nearest it in length. The same keys as twig
    placements (pos, frame, scale, node, key, card)."""
    base = base_of(tree, cards)
    pl = plan(tree, base or cards)
    k = len(pl["roots"])
    if not k or not at["cards"]:
        return {"pos": np.zeros((0, 3)), "frame": np.zeros((0, 3, 3)), "scale": np.zeros(0), "variant": np.zeros(0, int),
                "node": np.zeros(0, int), "key": np.zeros(0, np.uint64), "card": np.zeros(0, int)}
    Fr, ext, cnt = _frames(tree, pl)
    key = _child(tree["key"][pl["roots"]], 31)
    E = np.asarray(at["extent"])
    cost = np.abs(np.log(np.maximum(ext[:, None], 1e-3) / np.maximum(E[None], 1e-3)))
    kind = np.asarray(at.get("dead") or np.zeros(len(E), bool), bool)
    isd = dead_boughs(tree, pl)
    cost = cost + 100.0 * (isd[:, None] != kind[None])  # a dead bough draws a dead bough's picture
    near = np.argsort(cost, axis=1)[:, : min(2, len(E))]
    pick_ = (_u(key, 3) * near.shape[1]).astype(int) % near.shape[1]
    pick_ = np.where(cost[np.arange(k), near[np.arange(k), pick_]] >= 100.0, 0, pick_)  # (never the other kind when its own exists)
    card = near[np.arange(k), pick_]
    scale = np.clip(ext / np.maximum(E[card], 1e-6), 0.2, 1.35)  # (0.45 at least: a short bough drew a card twice its size)
    # One card or the crossed pair? A pair is two layers wherever both are seen: a 20k spruce drew 6.6 card layers per
    # covered pixel, a stand of them cost 1.6x the anime spruce in Godot. The pair stays where a player comes close
    # (boughs under `PAIR_BELOW` m on the full cut); higher up, and on every thinned LOD, a bough draws the ONE card
    # that faces someone on the ground outside the crown (out from the trunk and a little down).
    npair = int(at.get("pairs", len(at["cards"])))
    one = card.copy()
    if base and len(at["cards"]) >= 3 * npair and SINGLE:
        mid_ = tree["pos"][pl["roots"]] + Fr[:, :, 1] * (0.5 * ext)[:, None]
        rad_ = mid_ * [1.0, 1.0, 0.0]
        rad_ = rad_ / np.maximum(np.linalg.norm(rad_, axis=1, keepdims=True), 1e-6)
        v_ = _norm(rad_ + np.array([0.0, 0.0, -0.5]))
        face = np.abs(np.sum(Fr[:, :, 2] * v_, axis=1)) >= np.abs(np.sum(Fr[:, :, 0] * v_, axis=1))
        one = card + np.where(face, npair, 2 * npair)
        gz = mid_[:, 2] - _ground(tree, mid_)
        card0 = np.where(gz > PAIR_BELOW, one, card)
    else:
        card0 = card
    thinned = thinned_of(tree, cards)  # (a LOD under the fullest)
    card_full, card = card0, (one if thinned else card0)
    out = {"pos": tree["pos"][pl["roots"]], "frame": Fr, "scale": scale, "variant": card.astype(int), "node": pl["roots"].astype(int),
           "key": key, "card": card.astype(int)}
    seen = outer(tree, base) if base and CULL else np.ones(k, bool)
    if base and not seen.all() and cards >= int(seen.sum()):
        out = {k_: v_[seen] for k_, v_ in out.items()}
    elif base and cards < int(seen.sum()):  # a thinned LOD: `cards` of the cut's (seen) boughs, evenly by their hash, each larger
        # which ones: spread evenly (one per cell of a grid just fine enough, then the rest by their hash); chosen by
        # hash alone, kept cards bunch and overlap, and must grow more to cover the same
        h_ = _u(key, 91)
        mid_k = tree["pos"][pl["roots"]] + Fr[:, :, 1] * (0.5 * ext)[:, None]
        lo_c, hi_c = 0.5 * float(np.median(ext)), 8.0 * float(np.median(ext))
        first = np.zeros(k, bool)
        for _ in range(12):
            cs = math.sqrt(lo_c * hi_c)
            cid = np.unique(np.floor(mid_k / cs).astype(np.int64), axis=0, return_inverse=True)[1].ravel()
            o_ = np.lexsort((h_, cid))
            f_ = np.zeros(k, bool)
            ok_ = seen[o_]
            o_ = o_[ok_]
            f_[o_[np.r_[True, cid[o_][1:] != cid[o_][:-1]]]] = True
            if f_.sum() > cards:
                lo_c = cs
            else:
                hi_c, first = cs, f_
        rank = np.argsort(np.argsort(np.where(seen, h_ + np.where(first, 0.0, 1.0), 9.0)))
        keep = seen & (rank < cards)
        # how much larger: until the kept cards cover what all of them covered, seen from two sides (sqrt(k / cards)
        # is right only where cards overlap heavily: a sparse pine's LOD 2 came out 25% fatter than its LOD 0 in Godot)
        from PIL import Image, ImageDraw
        cV = [np.asarray(c_["V"], float) for c_ in at["cards"]]
        cF = [np.asarray(c_["F"], int) for c_ in at["cards"]]
        reach = max(float(np.abs(v_).max()) for v_ in cV) * float(scale.max()) * THIN_GROW
        lo3 = out["pos"].min(0) - reach
        px = max(0.08 * float(np.median(ext)), 0.04)
        wh = np.ceil((out["pos"].max(0) + reach - lo3) / px).astype(int) + 2

        def covered(sel, s, card=card):  # the cards' own polygons, drawn from the front and from the side
            tot = 0
            for ax in (0, 1):
                im = Image.new("1", (int(wh[ax]), int(wh[2])), 0)
                dr = ImageDraw.Draw(im)
                for ci in range(len(cV)):
                    ii = np.flatnonzero(sel & (card == ci))
                    if not len(ii):
                        continue
                    W = np.einsum("nij,kj->nki", Fr[ii], cV[ci]) * (scale[ii] * s)[:, None, None] + out["pos"][ii][:, None, :]
                    q = (W[:, :, [ax, 2]] - lo3[[ax, 2]]) / px
                    for t_ in q[:, cF[ci]].reshape(-1, 3, 2):
                        dr.polygon([(float(t_[0, 0]), float(t_[0, 1])), (float(t_[1, 0]), float(t_[1, 1])), (float(t_[2, 0]), float(t_[2, 1]))], fill=1)
                tot += int(np.asarray(im).sum())
            return tot
        # (under a limb layer the fine cards are detail on a mass that is already there: they keep their size)
        want = covered(seen, 1.0, card_full) if not limbs_on(tree) else 0.0
        lo_, hi_ = 1.0, (THIN_GROW if not limbs_on(tree) else 1.0)
        for _ in range(7 if not limbs_on(tree) else 0):
            m_ = 0.5 * (lo_ + hi_)
            if covered(keep, m_) < want:
                lo_ = m_
            else:
                hi_ = m_
        out = {k_: v_[keep] for k_, v_ in out.items()}
        out["scale"] = out["scale"] * hi_
        out["grow"] = float(hi_)
    n_out = len(out["pos"])
    out["core"] = np.zeros(n_out)
    if at.get("limb_first") is not None and limbs_on(tree) and base:
        plL = limb_plan(tree)
        FrL, extL, cntL = _frames(tree, plL)
        live = np.flatnonzero(~dead_boughs(tree, plL))
        EL = np.asarray(at["limb_extent"])
        cL = np.argmin(np.abs(np.log(np.maximum(extL[live, None], 1e-3) / np.maximum(EL[None], 1e-3))), axis=1)
        keyL = _child(tree["key"][plL["roots"][live]], 33)
        add = {"pos": tree["pos"][plL["roots"][live]], "frame": FrL[live], "scale": np.clip(extL[live] / np.maximum(EL[cL], 1e-6), 0.25, 1.3),
               "variant": (at["limb_first"] + cL).astype(int), "node": plL["roots"][live].astype(int), "key": keyL,
               "card": (at["limb_first"] + cL).astype(int), "core": np.ones(len(live))}
        grow_ = out.get("grow")
        out = {k_: np.concatenate([out[k_], add[k_]]) for k_ in add}
        if grow_ is not None:
            out["grow"] = grow_
        out["limbs"] = int(len(live))
    return {**out, "size_m": pl["size"]}


def most(tree: dict) -> int:
    """The most bough cards this tree can use (its foliage cut at twice a twig's length)."""
    st = subtrees(tree)
    return int(len(roots(tree, 2.0 * st["twig_length"])))
