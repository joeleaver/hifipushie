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

from . import veg_leaf
from .vegetation import _child, _u

BOUGH = {"variants": 4, "size": 384, "verts": 7, "cross": 2, "cup": 0.12}  # cross 2 = the bough from its face AND from its side
TRIS = BOUGH["verts"] * BOUGH["cross"]  # triangles the richest bough card costs (a fan per card)
# The card's cut, richest first. A budget buys GRANULARITY before polish: a 20k spruce cut into 937 fourteen-triangle
# cards was 2.7 m boughs (palm fronds from 30 m); the same triangles as six-triangle cards are twice as many, smaller.
THIN, THIN_GROW = 0.2, 2.2  # the least share of the finest cut a thinned LOD keeps; the most its cards grow
FORMS = ({"verts": 7, "centre": True, "cup": 0.12}, {"verts": 5, "centre": False, "cup": 0.06})


def tris(form: int = 0) -> int:
    f = FORMS[form]
    return (f["verts"] if f["centre"] else f["verts"] - 2) * BOUGH["cross"]


def fit(tree: dict, triangles: int) -> tuple[int, int]:
    """(cards, form) for a foliage triangle count. While the count buys at least `THIN` of the tree's finest cut
    (`most`) on the cheapest cards, the LOD is that finest cut THINNED: some of its boughs left out, the rest drawn
    larger (`place`), all LODs sharing one atlas and one silhouette (what a foliage artist does: remove cards, grow
    the rest; a spruce's LOD 1 re-cut into 425 whole-limb cards lost 15% of its covered area in Godot and its top).
    Under that, the tree is re-cut into fewer, larger boughs on the richest cards. Remembered on the tree."""
    m = most(tree)
    mr = len(plan(tree, m)["roots"])
    cheap = len(FORMS) - 1
    t = max(int(triangles), 0)
    memo = tree.setdefault("_bough_form", {})
    if mr and t // tris(cheap) >= THIN * mr and os.environ.get("HIFIPUSHIE_BOUGH_THIN", "1") != "0":
        form = 0 if t // tris(0) >= mr else cheap
        n = min(t // tris(form), mr)
        memo[n] = (form, m)
        return n, form
    n = min(t // tris(0), m)
    n2 = len(plan(tree, n)["roots"])
    memo[n] = memo[n2] = (0, None)
    return n2, 0


def form_of(tree: dict, cards: int) -> int:
    return int((tree.get("_bough_form") or {}).get(cards, (0, None))[0])


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
            cm = veg_leaf.card_mesh(R["alpha"], R["frame"], fm["verts"], fm["cup"] if side == 0 else 0.0, 1, 0.0, max(float(ext[b]), 0.1), 0, centre=fm["centre"])
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
        k_ = float(np.clip(lum(np.asarray(col, float)) / max(seen, 1e-6), 1.0, 1.8))
        g_ = len(out_cards) and A["color"].shape[0] // size
        for j_, dead_ in enumerate(isd[b_] for b_ in pick):  # (the foliage's pictures only: dead boughs keep their grey)
            if not dead_:
                for side in range(BOUGH["cross"]):
                    r, c = divmod(BOUGH["cross"] * j_ + side, g_)
                    A["color"][r * size:(r + 1) * size, c * size:(c + 1) * size, :3] = np.clip(A["color"][r * size:(r + 1) * size, c * size:(c + 1) * size, :3] * k_, 0, 1)
    if len(_CACHE) > 8:
        _CACHE.pop(next(iter(_CACHE)))
    A = {k_: np.clip(v_ * 255 + 0.5, 0, 255).astype(np.uint8).astype(np.float32) / 255.0 for k_, v_ in A.items()}  # (as the disk keeps it)
    _CACHE[key] = {**A, "cards": out_cards, "fill": float(np.mean(fills)) if fills else 0.0, "grid": g, "size": size,
                   "triangles": int(np.mean([len(c["F"]) for c in out_cards])) if out_cards else tris(fi),
                   "extent": extent, "size_m": pl["size"], "bough": True, "dead": [bool(isd[b_]) for b_ in pick]}
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
    out = {"pos": tree["pos"][pl["roots"]], "frame": Fr, "scale": scale, "variant": card.astype(int), "node": pl["roots"].astype(int),
           "key": key, "card": card.astype(int)}
    if base and cards < k:  # a thinned LOD: `cards` of the cut's boughs, evenly by their hash, each larger
        keep = np.argsort(np.argsort(_u(key, 91))) < cards
        # how much larger: until the kept cards cover what all of them covered, seen from two sides (sqrt(k / cards)
        # is right only where cards overlap heavily: a sparse pine's LOD 2 came out 25% fatter than its LOD 0 in Godot)
        from PIL import Image, ImageDraw
        cV = [np.asarray(c_["V"], float) for c_ in at["cards"]]
        cF = [np.asarray(c_["F"], int) for c_ in at["cards"]]
        reach = max(float(np.abs(v_).max()) for v_ in cV) * float(scale.max()) * THIN_GROW
        lo3 = out["pos"].min(0) - reach
        px = max(0.08 * float(np.median(ext)), 0.04)
        wh = np.ceil((out["pos"].max(0) + reach - lo3) / px).astype(int) + 2

        def covered(sel, s):  # the cards' own polygons, drawn from the front and from the side
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
        want = covered(np.ones(k, bool), 1.0)
        lo_, hi_ = 1.0, min(math.sqrt(k / max(cards, 1)), THIN_GROW)
        for _ in range(7):
            m_ = 0.5 * (lo_ + hi_)
            if covered(keep, m_) < want:
                lo_ = m_
            else:
                hi_ = m_
        out = {k_: v_[keep] for k_, v_ in out.items()}
        out["scale"] = out["scale"] * hi_
        out["grow"] = float(hi_)
    return {**out, "size_m": pl["size"]}


def most(tree: dict) -> int:
    """The most bough cards this tree can use (its foliage cut at twice a twig's length)."""
    st = subtrees(tree)
    return int(len(roots(tree, 2.0 * st["twig_length"])))
