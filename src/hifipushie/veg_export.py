"""A plant as a GLB (first export: one LOD; LODs, wind data and season variants are stage 4).

Two meshes: `wood` (branch tubes; bark base colour = the bark's colour x its tiling albedo, normal and roughness maps,
REPEAT sampling on the branch uv) and `foliage` (every twig's card, realised into one mesh; the twig atlas as base
colour with alpha MASK, double sided; COLOR_0 = a per-twig tint). glTF axes (Y up: x, z, -y), uv v flipped. Textures
are embedded. extras carry the plant's name, stats and counts.
"""

from __future__ import annotations

import io
import json
import math
import struct
from pathlib import Path

import numpy as np

from . import veg_bark, veg_bough, veg_cloud, veg_ground, veg_impostor, veg_leaf, veg_mesh, veg_style, vegetation


def veg_small_state(spec: dict, season: str):
    from . import veg_small
    return veg_small.season_state(spec, season)


def _normals(V, F):
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    ln = np.linalg.norm(N, axis=1, keepdims=True)
    return np.where(ln > 1e-12, N / np.maximum(ln, 1e-12), [0, 0, 1.0])


def _png(a) -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(np.clip(np.asarray(a) * 255 + 0.5, 0, 255).astype(np.uint8)).save(b, "PNG")
    return b.getvalue()


def _yup(v):
    return np.stack([v[:, 0], v[:, 2], -v[:, 1]], 1)


def wind_nodes(tree: dict) -> dict:
    """Per node, what a wind shader needs: `trunk` (0 at the foot .. 1 at the top, ^1.5: the whole tree's sway),
    `branch` (0 where a limb leaves the trunk .. 1 at its farthest end, ^1.3; 0 on the trunk), `phase` (0..1, one per
    limb: limbs must not swing together)."""
    P, par, order = tree["pos"], tree["parent"], tree["order"]
    n = len(P)
    seg = np.linalg.norm(P - P[par], axis=1)
    d = np.zeros(n)
    limb = np.zeros(n, np.int64)
    for i in range(2, n):
        if order[i] > 0:
            p_ = par[i]
            d[i] = d[p_] + seg[i]
            limb[i] = limb[p_] if order[p_] > 0 else i
    far = np.zeros(n)
    np.maximum.at(far, limb, d)
    return {"trunk": np.clip(P[:, 2] / max(tree["height"], 1e-6), 0, 1) ** 1.5,
            "branch": np.where(order > 0, (d / np.maximum(far[limb], 1e-6)) ** 1.3, 0.0),
            "phase": np.where(order > 0, vegetation._u(tree["key"][limb], 55), 0.0)}


def foliage_mesh(tree: dict, at: dict, keep: float = 1.0, min_radius: float = 0.0, protect=None, cap: float = 2.5,
                 back: float = 0.0, tw: dict | None = None) -> dict:
    """Every twig's card placed on the tree, as one mesh: V, F, uv, tint, node (the tree node it stands on), flutter
    (0 at the card's foot .. 1 at its tip), N (normals bent out from the crown's middle: a crown shades as a volume).
    keep < 1: see pick_twigs."""
    if tw is None:  # (given: bough cards, placed by veg_bough)
        tw = pick_twigs(tree, keep, min_radius, protect, cap=cap, back=back)[0]
    if not len(tw["pos"]):
        return {"V": np.zeros((0, 3)), "F": np.zeros((0, 3), int), "uv": np.zeros((0, 2)), "tint": np.zeros(0),
                "node": np.zeros(0, int), "flutter": np.zeros(0), "N": np.zeros((0, 3)), "reach": np.zeros(0), "phase": np.zeros(0)}
    nv = len(at["cards"])
    if not tree.get("clump") and veg_ground.CLEAR:  # no card reaches under the ground (turned up, shortened or left out)
        tw = veg_ground.clear(tree["spec"], tw, at["cards"], veg_leaf.card_variant(tw, nv))
        if not len(tw["pos"]):
            return foliage_mesh(tree, at, tw={**tw, "pos": np.zeros((0, 3))})
    var = veg_leaf.card_variant(tw, nv)
    tint = 0.75 + 0.5 * vegetation._u(tw["key"], 77)
    if "size_m" in tw:  # bough cards are big: a tone per card as wide as a twig's read as a crown of pale and dark leaves
        tint = 0.88 + 0.24 * vegetation._u(tw["key"], 77)
    core = np.asarray(tw["core"], float) if tw.get("core") is not None and len(np.atleast_1d(tw["core"])) == len(tw["pos"]) else None
    Vs, Fs, Us, Ts, Ns, Fl, Nr, Rc, Ph = [], [], [], [], [], [], [], [], []
    base = 0
    for i, c in enumerate(at["cards"]):
        sel = np.flatnonzero(var == i)
        if not len(sel):
            continue
        k = len(c["V"])
        V = np.einsum("nij,kj->nki", tw["frame"][sel], c["V"]) * tw["scale"][sel][:, None, None] + tw["pos"][sel][:, None, :]
        Vs.append(V.reshape(-1, 3))
        Fs.append((c["F"][None] + (base + np.arange(len(sel)) * k)[:, None, None]).reshape(-1, 3))
        Us.append(np.tile(c["uv"], (len(sel), 1)))
        if core is not None and core[sel].any():  # a whole limb's card: dark toward the trunk (the crown's shadowed inside), full tone at its tip
            fl_ = np.clip(c["V"][:, 1] / max(float(c["V"][:, 1].max()), 1e-6), 0, 1)
            Ts.append((tint[sel][:, None] * (1.0 - CORE_DARK * core[sel][:, None] * (1.0 - fl_[None]) ** 1.5)).ravel())
        else:
            Ts.append(np.repeat(tint[sel], k))
        Ns.append(np.repeat(tw["node"][sel], k))
        Fl.append(np.tile(np.clip(c["V"][:, 1] / max(float(c["V"][:, 1].max()), 1e-6), 0, 1), len(sel)))
        Nr.append(np.repeat(tw["frame"][sel][:, :, 2], k, axis=0))  # the card's own upper side
        Rc.append(np.repeat(tw["scale"][sel] * float(c["V"][:, 1].max()), k))  # how long the card is, m
        Ph.append(np.repeat(vegetation._u(tw["key"][sel], 56), k))
        base += len(sel) * k
    V = np.vstack(Vs)
    cen = np.array([tw["pos"][:, 0].mean(), tw["pos"][:, 1].mean(), np.percentile(tw["pos"][:, 2], 30)])
    out_ = V - cen
    out_ /= np.maximum(np.linalg.norm(out_, axis=1, keepdims=True), 1e-9)
    w = float(tree["spec"]["leaves"].get("round", 0.7))
    N = (1 - w) * np.vstack(Nr) + w * out_
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    if tree.get("clump") and tree["spec"]["leaves"].get("normals", "up") == "up":
        # a small plant shades with the ground it stands on: normals lean up (cards lit each by its own face flicker)
        N = N * [1, 1, 0.35] + [0, 0, 1.0]
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    return {"V": V, "F": np.vstack(Fs), "uv": np.vstack(Us), "tint": np.concatenate(Ts), "node": np.concatenate(Ns),
            "flutter": np.concatenate(Fl), "N": N, "reach": np.concatenate(Rc), "phase": np.concatenate(Ph)}


def protected(tree: dict) -> np.ndarray:
    """Per node: wood a triangle budget keeps far longer than its girth earns (down to a quarter of the cut-off radius): what the artist marked (dead wood kept on the
    tree, drawn guides). Without it a 20k stag-headed oak lost its antlers: they are the thinnest wood on it."""
    pr = np.zeros(len(tree["pos"]), bool)
    if tree.get("dead") is not None:
        pr |= tree["dead"]
        if tree.get("shade_dead") is not None:  # (limbs the shade killed are nobody's mark: they go by their girth)
            pr &= ~tree["shade_dead"]
    for ai in (tree.get("guides") or {}).values():
        pr |= (tree["axis"] == ai) & tree["pin"]
    return pr


def kept_wood(tree: dict, min_radius: float, protect=None) -> np.ndarray:
    """Per node: is its axis drawn at this cut-off radius?"""
    ax, rad = tree["axis"], tree["radius"]
    first = np.full(int(ax.max()) + 1, -1)
    idx = np.arange(len(ax))[::-1]
    first[ax[idx]] = idx  # an axis's first node
    ok = rad[first[ax]] >= min_radius
    if protect is not None:
        ok |= protect[first[ax]] & (rad[first[ax]] >= min_radius * veg_mesh.PROTECT)
    ok[:2] = True
    return ok


def cluster_leaves(leaves: dict, keep: float) -> tuple[dict, float, float]:
    """When a budget draws under a quarter of the twigs, each card must show a BOUGH, not a twig blown up: the leaves
    spec with the card's twig K x longer, with more side shoots and K^2 x the leaves (the leaves keep their size).
    Returns (leaves spec, cap: how much a kept card may still be enlarged, back: metres to seat the longer card back
    along its shoot so the crown doesn't grow). Twig cards scaled 2.5x left a 20k oak a few clumps of giant leaves."""
    if keep >= 0.25:
        return leaves, 2.5, 0.0
    K = float(np.clip(0.75 / np.sqrt(max(keep, 1e-4)), 1.3, 3.0))
    tw = {**veg_leaf.TWIG, **veg_leaf.card_spec(leaves)["twig"]}
    card = dict(leaves.get("card") or {})
    card["twig"] = {**(card.get("twig") or {}), "length": round(tw["length"] * K, 3),
                    "leaves": int(tw["leaves"] * min(K * K, 5.0)), "side_shoots": int(round(max(tw["side_shoots"], 3) * min(K, 2.0)))}
    card["end"] = False  # (a bough is a spray, not a round tuft: its end-on card was a third of each card's triangles)
    return {**leaves, "card": card}, 1.25, 0.45 * (K - 1) * tw["length"]


def pick_twigs(tree: dict, keep: float, min_radius: float = 0.0, protect=None, tw: dict | None = None,
               cap: float = 2.5, back: float = 0.0) -> tuple[dict, float]:
    """The twigs a budget draws: `keep` of them, each larger by 1 / sqrt(keep). Those standing on drawn wood (or within
    a card's reach of it along the branch) go first: cards chosen by their hash alone were left floating round bare
    spars. Returns (twigs, the share of the kept ones farther than that from drawn wood)."""
    tw = veg_leaf.place(tree) if tw is None else tw
    n = len(tw["pos"])
    if not n or keep >= 1:
        return tw, 0.0
    grow = min(1.0 / np.sqrt(max(keep, 1e-6)), cap)
    ok = kept_wood(tree, min_radius, protect)
    par, P = tree["parent"], tree["pos"]
    seg = np.linalg.norm(P - P[par], axis=1)
    d = np.zeros(len(P))
    for i in range(2, len(P)):  # distance back along the branch to drawn wood (parents come first)
        d[i] = 0.0 if ok[i] else d[par[i]] + seg[i]
    lf = tree["spec"]["leaves"]
    reach = 0.6 * float((lf.get("card") or {}).get("twig", {}).get("length", (lf.get("twig") or {}).get("length", 0.3))) * grow
    far = d[tw["node"]] > reach
    if back:  # bough cards: spread over the crown first (one per cell of about a card's size, then a second each...)
        cell = np.floor(tw["pos"] / max(2.2 * back + 0.3, 0.3)).astype(np.int64)
        cid = np.unique(cell, axis=0, return_inverse=True)[1].ravel()
        h_ = vegetation._u(tw["key"], 91)
        order_ = np.lexsort((h_, cid))
        within = np.empty(n, np.int64)
        start = np.r_[0, np.flatnonzero(np.diff(cid[order_])) + 1]
        within[order_] = np.arange(n) - np.repeat(start, np.diff(np.r_[start, n]))
        rank = np.argsort(np.argsort(within + 0.999 * h_))
        far = far & False
    else:
        rank = np.argsort(np.argsort(far.astype(float) + 0.999 * vegetation._u(tw["key"], 91)))
    sel = rank < int(np.floor(n * keep + 1e-9))  # (exactly that many: a threshold on the hash overshot budgets)
    out = {k: v[sel] for k, v in tw.items()}
    out["scale"] = out["scale"] * grow
    if back:
        out["pos"] = out["pos"] - out["frame"][:, :, 1] * (back * out["scale"])[:, None]
    return out, float(far[sel].mean()) if sel.any() else 0.0


def _wood_for(tree, tile, wood_budget, pr):
    """The wood within a triangle count: {"wood", "sides", "simplify", "min_radius"}."""
    out = {"sides": (3, 7), "simplify": 0.5}
    kw = dict(tile=tile, sides=(3, 7), simplify=0.5, protect=pr)
    radii = np.unique(tree["radius"][1:])
    lo_, hi_ = 0, len(radii) - 1
    while lo_ < hi_:
        mid = (lo_ + hi_) // 2
        if len(veg_mesh.tubes(tree, min_radius=float(radii[mid]), **kw)["F"]) > wood_budget:
            lo_ = mid + 1
        else:
            hi_ = mid
    out["min_radius"] = float(radii[hi_])
    out["wood"] = veg_mesh.tubes(tree, min_radius=out["min_radius"], **kw)
    return out


def budget(tree: dict, triangles: int | None, tile, card_triangles: int, cap: float = 2.5) -> dict:
    """`_budget`, with the marked wood (dead antlers, drawn limbs) kept only as far as the living tree can afford: when
    keeping all of it leaves most cards with no drawn wood under them (a stag-headed oak's antlers took the whole wood
    budget and the live limbs were cut at 20 cm), the thinnest marked wood goes by its girth like the rest."""
    pr = protected(tree)
    first = None
    for rp in (0.0, 0.01, 0.02, 0.04, 0.08, 1e9):
        out = _budget(tree, triangles, tile, card_triangles, cap, pr & (tree["radius"] >= rp))
        first = first or out
        if not triangles or not pr.any() or out.get("boughs") or not len(veg_leaf.place(tree)["pos"]):
            return out
        if pick_twigs(tree, out["keep"], out["min_radius"], out["protect"], cap=cap)[1] <= 0.5:
            return out
    return first  # (it floats whatever is given up: the marked wood stays, and the export says the budget is too small)


def _budget(tree: dict, triangles: int | None, tile, card_triangles: int, cap: float = 2.5, pr=None) -> dict:
    """What a triangle budget leaves of a plant: {"wood": the tube mesh, "sides", "min_radius" (thinner wood is left
    out, except `protected` wood), "keep" (the share of twigs drawn, each larger by 1 / sqrt(keep)), "floating" (the
    share of drawn twigs with no drawn wood near them), "total", "over": triangles past the budget (the trunk alone can
    be more than a tiny budget)}. Half the budget is the wood's; two thirds when at half too many cards would float."""
    tw = veg_leaf.place(tree)
    n_tw = len(tw["pos"])
    pr = protected(tree) if pr is None else pr
    W0 = veg_mesh.tubes(tree, tile=tile)
    out = {"wood": W0, "sides": (3, 12), "min_radius": 0.0, "keep": 1.0, "floating": 0.0, "protect": pr}
    for share in ((0.5, 0.66, 0.8) if n_tw else (1.0,)) if triangles else ():
        if share > 0.5 and out["keep"] < 0.25:
            break  # (bough cards stand off the wood anyway: the foliage keeps its half)
        W = W0
        out.update(sides=(3, 12), min_radius=0.0, simplify=0.0)
        wood_budget = triangles * share
        for sides, simp in (((3, 10), 0.15), ((3, 8), 0.3), ((3, 7), 0.5)):  # fewer rings and sides before any wood goes
            if len(W["F"]) <= wood_budget:
                break
            out.update(sides=sides, simplify=simp)
            W = veg_mesh.tubes(tree, tile=tile, sides=sides, simplify=simp)
        if len(W["F"]) > wood_budget:  # then leave out the thinnest axes
            kw = dict(tile=tile, sides=out["sides"], simplify=out["simplify"], protect=pr)
            radii = np.unique(tree["radius"][1:])
            lo_, hi_ = 0, len(radii) - 1
            while lo_ < hi_:  # the smallest cut-off radius that fits
                mid = (lo_ + hi_) // 2
                if len(veg_mesh.tubes(tree, min_radius=float(radii[mid]), **kw)["F"]) > wood_budget:
                    lo_ = mid + 1
                else:
                    hi_ = mid
            out["min_radius"] = float(radii[hi_])
            W = veg_mesh.tubes(tree, min_radius=out["min_radius"], **kw)
        out["wood"] = W
        if n_tw:
            left = max(triangles - len(W["F"]), 0)
            out["keep"] = float(np.clip((left // max(card_triangles, 1)) / max(n_tw, 1), 0.0, 1.0))
            out["floating"] = pick_twigs(tree, out["keep"], out["min_radius"], pr, tw, cap=cap)[1]
        if out["floating"] <= 0.2 or out["min_radius"] == 0.0:
            break
    if n_tw and triangles and out["keep"] < 0.25:  # a crown of bough cards wants cover more than twig wood: 35% wood
        out2 = _wood_for(tree, tile, triangles * 0.35, pr)
        if (tree["spec"]["leaves"].get("card") or {}).get("end"):  # bough cards drop the end-on card
            cr_ = int((tree["spec"]["leaves"].get("card") or {}).get("cross", 1))
            card_triangles = int(round(card_triangles * cr_ / (cr_ + 1)))
        if out2 is not None:
            out.update(out2)
            out["keep"] = float(np.clip(((triangles - len(out["wood"]["F"])) // max(card_triangles, 1)) / max(n_tw, 1), 0.0, 1.0))
            out["floating"] = 0.0
        if not tree.get("clump"):  # a grown tree: cards of its own boughs, as many as the foliage's share buys
            out["boughs"], out["bough_form"] = veg_bough.fit(tree, max(triangles - len(out["wood"]["F"]), 0))
            spare = triangles - len(out["wood"]["F"]) - out["boughs"] * veg_bough.cost(tree, out["boughs"]) - veg_bough.extra(tree)
            if spare > 0.1 * triangles:  # the foliage can't use more (cards beyond its cut only stack layers): finer wood
                out.update(_wood_for(tree, tile, len(out["wood"]["F"]) + spare, pr))
    fol = out["boughs"] * veg_bough.tris(out["bough_form"]) + veg_bough.extra(tree) if out.get("boughs") else int(np.floor(n_tw * out["keep"] + 1e-9)) * card_triangles
    out["total"] = int(len(out["wood"]["F"]) + fol)
    out["over"] = max(0, out["total"] - int(triangles)) if triangles else 0
    return out


CORE_DARK = 0.55  # how much darker a limb card is at the trunk than at its tip
LODS = ((1.0, 2.5), (0.45, 2.5), (0.18, 4.0))  # (share of the budget, how much larger a kept card may be drawn)
AUTUMN = [0.78, 0.56, 0.16]
WIND_RECIPE = ("vertex shader: TEXCOORD_1 = (trunk, branch) weights, TEXCOORD_2 = (phase, flutter); the same four in _WIND "
               "(VEC4: trunk, branch, phase, flutter). P += windDir * (trunk * A_tree * sin(w_tree * t) + branch * A_limb * "
               "sin(w_limb * t + 6.283 * phase)) + N * flutter * A_leaf * sin(w_leaf * t + 40 * phase + dot(P, 3)); "
               "A_tree ~0.02 x height x gust, A_limb ~0.25 m x gust, A_leaf ~0.02 m, w_tree ~1, w_limb ~2.3, w_leaf ~9 rad/s")


def evergreen(spec: dict) -> bool:
    lf = spec["leaves"]
    return bool(lf.get("evergreen", str(lf.get("shape", "")).startswith("needle")))


def spring_leaves(spec: dict) -> dict:
    """The leaves spec in spring: fresh colour (`leaves.spring`, else the summer colour toward yellow-green; an
    evergreen only a little: its new shoots) and, on a deciduous plant, leaves `leaves.spring_size` (0.75) of their
    length: a thinner crown. Blossom and catkins are not built."""
    lf = spec["leaves"]
    out = {**lf, "color": veg_style.season_color(spec, "spring")}
    if not evergreen(spec):
        out["length"] = float(lf.get("length", veg_leaf.LEAF["length"])) * float(lf.get("spring_size", 0.75))
    return {k_: v_ for k_, v_ in out.items() if k_ not in ("spring", "spring_size")}


def season_atlas(spec: dict, season: str, twig_color, make=None) -> dict | None:
    """The foliage atlas in a season: summer as specified; autumn = the same leaves in `leaves.autumn` (deciduous only;
    an evergreen keeps its colour); snow = the summer picture frosted. None = no leaves then (a deciduous winter)."""
    lf = spec["leaves"]
    make = make or veg_leaf.atlas  # (bough cards: veg_bough.atlas of the tree)
    if spec.get("plant") == "clump":  # a small plant: its own states (veg_small.SEASONS); layers out of season = their pictures blanked
        from . import veg_small
        stt = veg_small.season_state(spec, season)
        if stt is None:
            return None
        if season == "summer" and not veg_small.hidden_parts(spec, season):
            return make(lf, twig_color)
        at = make({**lf, "color": stt["color"]}, twig_color)
        hid = veg_small.hidden_parts(spec, season)
        col = at["color"].copy()
        if hid:
            pc = veg_leaf.part_cards(lf)
            h, w = col.shape[:2]
            for p_ in hid:
                for ci in pc.get(p_, ()):
                    uv = at["cards"][ci]["uv"]
                    x0, x1 = int(np.floor(uv[:, 0].min() * w)), int(np.ceil(uv[:, 0].max() * w))
                    y0, y1 = int(np.floor((1 - uv[:, 1].max()) * h)), int(np.ceil((1 - uv[:, 1].min()) * h))
                    col[max(y0, 0): y1, max(x0, 0): x1, 3] = 0.0
        if season == "snow":
            k_ = 0.55
            col[..., :3] = col[..., :3] * (1 - k_) + np.array([0.93, 0.95, 0.98]) * k_
        return {**at, "color": col}
    if season in ("winter", "bare", "snow") and not evergreen(spec):  # (snow = the winter state with snow on it: a leaf-dropping plant is bare)
        return None
    if season == "autumn" and not evergreen(spec):
        return make({**lf, "color": lf.get("autumn", AUTUMN)}, twig_color)
    if season == "spring":
        return make(spring_leaves(spec), twig_color)
    at = make(lf, twig_color)
    if season == "snow":
        rng = np.random.default_rng(5)
        h, w = at["color"].shape[:2]
        from scipy import ndimage
        n_ = ndimage.gaussian_filter(rng.random((h, w)), 5, mode="wrap")
        n_ = (n_ - n_.min()) / max(float(np.ptp(n_)), 1e-9)
        k_ = np.clip((n_ - 0.35) / 0.2, 0, 1)[..., None] * 0.85
        col = at["color"].copy()
        col[..., :3] = col[..., :3] * (1 - k_) + np.array([0.93, 0.95, 0.98]) * k_
        at = {**at, "color": col}
    return at


def collision(tree: dict, limit: int = 24) -> list[dict]:
    """Capsules for the wood a player or a ball meets: the trunk and the limbs at least a fifth of its girth (and 5 cm),
    each as straight pieces along its stoutest wood: [{"a", "b", "ra", "rb"}] in the plant's frame (m, Z up)."""
    P, rad, par = tree["pos"], tree["radius"], tree["parent"]
    kids = {}
    for i in range(1, len(par)):
        kids.setdefault(int(par[i]), []).append(i)
    thr = max(0.05, 0.2 * float(rad[1]))
    starts = [1] + [L["axis"] for L in ()]
    caps = []
    roots_ = [1] + [tree["axes"][L["axis"]]["node"] for L in vegetation.limbs(tree, 40, 0.0) if 0.5 * L["diameter"] >= thr]
    for n0 in roots_:
        nodes = vegetation.stout_path(tree, n0, kids)
        nodes = np.concatenate([[par[n0]], nodes[rad[nodes] >= 0.6 * thr]])
        if len(nodes) < 2:
            continue
        pts, rr = P[nodes], rad[nodes]
        keep = veg_mesh._rdp(pts, np.maximum(rr, 0.02) * 0.6, rr * 0 + 1)
        for i0, i1 in zip(keep[:-1], keep[1:]):
            caps.append({"a": pts[i0].round(3).tolist(), "b": pts[i1].round(3).tolist(),
                         "ra": round(float(rr[i0]), 3), "rb": round(float(rr[i1]), 3)})
    caps.sort(key=lambda c: -(c["ra"] + c["rb"]) * float(np.linalg.norm(np.subtract(c["a"], c["b"]))))
    return caps[:limit]


# The export contract an engine maps by name: material slots, vertex channels, files. Bump it whenever a slot or a
# channel is added, renamed or changes meaning (and say so in vegetation_guide.md "The export contract").
CONTRACT = 9
CONTRACT_LOG = {
    1: "slots bark, foliage (+ foliage_boughs<n>), impostor; TEXCOORD_1 = (trunk, branch), TEXCOORD_2 = (phase, flutter), _WIND; "
       "COLOR_0 on foliage; season variants; <name>_collision.glb; <name>_seasons.json",
    2: "styled deciduous plants: slot bark_forks (the wood mesh's second primitive, hidden except in bare seasons); "
       "impostor_<season> pictures",
    3: "styled small plants: slot heads (the foliage mesh's second primitive: flower / seed heads, hidden out of their seasons); "
       "impostor: normalTexture + TANGENT, 16 vertices (front and back of each quad apart, opposite normals), the second "
       "picture no longer mirrored, albedo with baked shade; seasons json: contract, slot_list, normalTexture files",
    4: "style anime (leaf clouds): slot foliage is alpha-MASK cards, double sided, with a baseColorTexture (a grey dab atlas: tone x "
       "baseColorFactor x COLOR_0) and TEXCOORD_0 = the atlas uv (in blobby it is (height in mass, mass id)); new channel TEXCOORD_3 = "
       "(gradient 0 base .. 1 top of its clump, (clump + 0.5) / clumps) (Godot: CUSTOM0.zw); COLOR_0 = the clump's painted gradient step; "
       "no bark_forks slot (the forks are in `bark`); seasons json: `snow` numbers (colour, coverage, the normal threshold), "
       "`style` (name, foliage kind); impostor albedo: baked shade scaled by the season's brightness",
    5: "the `snow` variant of a leaf-dropping plant (realistic or styled) is its WINTER state under snow: foliage (and a style's "
       "heads) hidden, bark_forks shown, the snow impostor the bare tree; evergreens keep their crown in snow (as in 4)",
    6: "the impostor LOD is HEMI-OCTAHEDRAL by default: ONE quad (2 triangles, uv = its corners) that the engine's shader turns "
       "to the camera, slot impostor's baseColorTexture = an N x N atlas of views over the upper hemisphere (sRGB + alpha), its "
       "object-space normal map (+ depth in alpha) in extras.hifipushie_impostor.normal_texture_index (NOT normalTexture), "
       "frames / size / centre / recipe there and in the seasons json `impostor` (+ impostorNormalTexture files per season); "
       "reference Godot shader spikes/godot_veg/impostor_octa.gdshader. impostor=\"cross\" keeps the old two crossed quads. A plant exported without an impostor (small plants, clumps) carries \"impostor\": null in the seasons json. "
       "Slot heads (styled small plants) now carries COLOR_0 = each part's colour (petals / dab / ball, the flower's centre, the "
       "stalk) with a WHITE baseColorFactor: switch vertex colour on for heads as for foliage. A style's clump block takes "
       "heads_kind ball | dab | petals (anime: colour dabs; cartoon: petalled daisies). Styled small plants whose blades lie down "
       "in winter: slot foliage_winter (the foliage mesh's next primitive: the blades lying, shown only in winter and snow, "
       "when foliage is hidden)",
    7: "a styled closed crown's (blobby / cartoon masses or tiers) season material MAY carry a baseColorTexture: a RAMP over "
       "TEXCOORD_0.x (0 = a mass's foot / a cone tier's rim .. 1 its top; clamp sampler; v ignored), albedo = baseColorFactor x "
       "texture x COLOR_0 (cartoon conifers' spring: lime tips on every tier's rim). The seasons json lists it under that "
       "season's foliage slot as baseColorTexture {file}: an engine that sets season materials from the json must set the "
       "texture too (or keep the GLB's variant material). Anime seed / flower heads (slot heads, kind dab) are clusters of "
       "small closed blobs now, not flat discs (same slot, same channels)",
    8: "the octahedral impostor's quad is CROPPED: extras.hifipushie_impostor.crop (and the seasons json `impostor.crop`) = "
       "[u0, u1, v0, v1] of a frame that every frame of every season draws inside; the engine's quad is centre + (mix(u0, u1, "
       "uv.x) - 0.5) * size * right + (0.5 - mix(v0, v1, uv.y)) * size * up (reference shader: uniform `crop`); frames, atlas "
       "uv and size unchanged; the GLB's stored quad is that rectangle. A reader that ignores crop still draws correctly, "
       "just with the old (bigger) square. Anime crowns' LOD1 / LOD2 carry fewer card layers (outer shells only) and smaller "
       "cards: same slots and channels",
    9: "style PIXAR: slot foliage = the closed canopy shell (opaque, no texture; COLOR_0 = a gradient base-to-tip, warmer at "
       "the tips, x the material's baseColorFactor; NORMAL = the shell's, blended half way toward out of the canopy's middle) "
       "and NEW slot foliage_cards = the foliage mesh's next primitive: real leaf cards on the shell's outside (alpha MASK, "
       "double sided, baseColorTexture = a grey atlas of the species' own leaf outlines x baseColorFactor x COLOR_0; NORMAL = "
       "the shell's under the card; TEXCOORD_0 = the atlas uv), its own material per season variant (hidden when the plant "
       "is bare). On both: TEXCOORD_3 = (gradient 0 base / inside .. 1 tip, THICKNESS = metres of canopy behind the point "
       "along -NORMAL, capped 4 m; cards 0.02) for the engine's subsurface / back light; material extras.translucency = "
       "{color sRGB, amount}. Wood: every structural limb in one mesh (no bark_forks slot). REALISTIC small plants whose blades "
       "lie down in winter now carry slot foliage_winter too (their cards regrown lying; the atlas the season's own)",
}
IMPOSTOR_AZIMUTHS = (0, 90)  # the two pictures: looking along +y (image right = +x), then along +x (image right = -y)
IMPOSTOR = {"shade": 0.5, "depth": 1.0, "depth_cards": 0.5, "shade_bright": 0.7}  # (measured in Godot: spikes/godot_veg; cards let light through a crown)


SNOW = {"color": [0.9, 0.92, 0.95], "coverage": 0.8}  # (the looks' snow: blender_vegetation._weather at season "snow")


def snow_numbers(spec: dict, st: dict | None) -> dict:
    """Snow as numbers for an engine's own shader (the ready-mixed `snow` variant stays): where our looks lay it and how
    the variant's colour was made."""
    c = SNOW["coverage"]
    sn = ((st or {}).get("seasons") or {}).get("snow") or {"mix": [0.93, 0.95, 0.98], "amount": 0.7}
    return {"color_linear": SNOW["color"], "coverage": c,
            "by_normal": {"from": round(1.0 - 1.3 * c, 3), "to": round(1.25 - 1.3 * c, 3),
                          "formula": "snow = saturate((N.up + 0.5 * (noise(6 / m) - 0.5) - from) / (to - from)); albedo = mix(albedo, color, snow); "
                                     "roughness = max(roughness, 0.6 * snow). N = the vertex NORMAL (a style's mass / clump normal, so a crown "
                                     "whitens from its top); on realistic card foliage use 0.75 * |face normal.up| + 0.4 * (out of the crown).up"},
            "variant": ({"mix_srgb": sn["mix"], "amount": sn["amount"], "how": "the snow variant's foliage colour = mix(summer colour, mix_srgb, amount), no normal test"}
                        if st else {"how": "the snow variant's foliage picture is the summer atlas frosted"})}


def impostor_frames() -> list:
    """Per picture: (right, out) in the plant's axes (up = z): the quad's tangent and its front normal (toward the
    camera that made the picture)."""
    out = []
    for az in IMPOSTOR_AZIMUTHS:
        a = math.radians(az)
        out.append((np.array([math.cos(a), -math.sin(a), 0.0]).round(9), np.array([-math.sin(a), -math.cos(a), 0.0]).round(9)))
    return out


def _bleed(rgb: np.ndarray, solid: np.ndarray) -> np.ndarray:
    """Every empty pixel takes its nearest solid pixel's value (black under the alpha darkened the picture's edges in
    every mip level: an impostor's quad seen edge-on is nothing but low mips, a dark wedge)."""
    if solid.all() or not solid.any():
        return rgb
    from scipy import ndimage
    i = ndimage.distance_transform_edt(~solid, return_distances=False, return_indices=True)
    return rgb[i[0], i[1]]


def impostor_maps(albedo: list, normal: list, shade: list, shade_amount: float | None = None, depth: float | None = None) -> dict:
    """An impostor's two textures from its unlit passes (one RGBA picture per view of each): {"image": albedo (sRGB) x
    the baked shade, with alpha; "normal": the tangent-space normal map in each quad's own frame}.
    shade_amount (IMPOSTOR 0.5): how much of the shade pass goes into the albedo: 0 none; 1 = what gets no sky from
    above is black. The engine lights the picture by its normals but casts no shadow in it: limbs under a crown and the
    crown's lower parts were as bright as its top. depth (1.0): the normal's share toward the picture's camera; under
    1 the quad is lit more by its up / sideways slopes alone (both quads more alike under a sun from the side)."""
    from scipy import ndimage
    k = IMPOSTOR["shade"] if shade_amount is None else float(shade_amount)
    dz = IMPOSTOR["depth"] if depth is None else float(depth)
    ims, nms = [], []
    for (right, out), A, Nw, Sh in zip(impostor_frames(), albedo, normal, shade):
        solid = A[..., 3] > 0.5
        got = Sh[..., 3] > 0.05
        sh = ndimage.gaussian_filter(_bleed(np.where(got, Sh[..., 0], 1.0), got), 1.2)  # (12 samples a pixel: noisy)
        # bright colours take less of it: at full strength autumn's clean orange came out with brown patches (shade on
        # a bright saturated colour reads as dirt; on a dark green as depth). By the pixel's own value (sRGB max).
        val = np.clip((A[..., :3].max(-1) - 0.35) / 0.5, 0, 1)
        kk = k * (1 - IMPOSTOR.get("shade_bright", 0.7) * val * val * (3 - 2 * val))
        lin_ = np.where(A[..., :3] <= 0.04045, A[..., :3] / 12.92, ((A[..., :3] + 0.055) / 1.055) ** 2.4) * (1 - kk + kk * sh)[..., None]
        rgb = np.where(lin_ <= 0.0031308, lin_ * 12.92, 1.055 * np.maximum(lin_, 0) ** (1 / 2.4) - 0.055)
        ims.append(np.dstack([_bleed(rgb, solid), A[..., 3]]))
        n = Nw[..., :3] * 2 - 1
        ts = np.stack([n @ right, n[..., 2], (n @ out) * dz], -1)
        ts[..., 2] = np.maximum(ts[..., 2], 0.08)  # (a bent normal that faces away from its own camera can't be lit from this side)
        ts /= np.maximum(np.linalg.norm(ts, axis=-1, keepdims=True), 1e-6)
        ts = _bleed(ts, solid & (Nw[..., 3] > 0.5))
        nms.append(ts * 0.5 + 0.5)
    return {"image": np.concatenate(ims, 1).astype(np.float32), "normal": np.concatenate(nms, 1).astype(np.float32)}


def write_glb(tree, path: str, name="plant", triangles: int | None = None, spacing: float | None = None,
              lods: int = 1, seasons=("summer",), impostor: dict | None = None, wet: bool = False,
              cap: float | None = None, only_impostor: bool = False) -> dict:
    """Write the plant to `path` (.glb). Returns counts. `triangles` = LOD 0's budget (see `budget`).
    lods: 1-3 mesh LODs at LODS' shares of the budget, each drawn from the same tree (fewer rings, sides and axes;
    fewer, larger cards), + `impostor` ({"image" RGBA, "size" m, "height" m}: two crossed quads) as the last. LOD 0
    is the scene; the others hang on it through MSFT_lod and are listed in extras (and written as files of their own
    by veg_tools.export, for engines without the extension).
    Wind: TEXCOORD_1 / TEXCOORD_2 / _WIND on every vertex (WIND_RECIPE). COLOR_0 on foliage = a per-twig tint.
    seasons: KHR_materials_variants over the foliage material (season_atlas; a deciduous winter hides the foliage
    by an alpha cut-off above 1); `wet` adds a "wet" variant (darker, glossier bark and leaves).
    Collision: capsules in extras, and a low mesh `<name>_collision` (not in the scene).
    A list of trees (and names) writes a SET: one bark and one foliage material, a node per plant stood `spacing` m
    apart along x; the budget is each plant's own."""
    trees = tree if isinstance(tree, list) else [tree]
    names = name if isinstance(name, list) else [name]
    tree = trees[0]
    s = tree["spec"]
    st = veg_style.sheet(s)  # a style: the same plant dressed another way (veg_style)
    if st and triangles is None:
        triangles = int(({**veg_style.CLUMP, **(st.get("clump") or {})})["budget"] if tree.get("clump") else st.get("budget", 5000))
    bark = s.get("bark") or {}
    bm = veg_bark.bark_maps(bark.get("kind", "furrowed"), 256, seed=int(s.get("seed", 1)))
    sc = float(bark.get("scale", 1.0))
    tile = [bm["tile"][0] * sc, bm["tile"][1] * sc]
    twc = bark.get("twig_color") or [0.45, 0.4, 0.35]
    has_leaves = any(len(veg_leaf.place(t)["pos"]) for t in trees)
    at = veg_leaf.atlas(s["leaves"], twc) if has_leaves and not st else None
    buf = bytearray()
    views, accessors, images, textures, materials, meshes, nodes = [], [], [], [], [], [], []
    ext_used = set()

    def view(data: bytes, target=None):
        while len(buf) % 4:
            buf.append(0)
        v = {"buffer": 0, "byteOffset": len(buf), "byteLength": len(data)}
        if target:
            v["target"] = target
        buf.extend(data)
        views.append(v)
        return len(views) - 1

    def acc(a, kind, comp, target, minmax=False):
        a = np.ascontiguousarray(a)
        d = {"bufferView": view(a.tobytes(), target), "componentType": comp, "count": int(len(a)), "type": kind}
        if minmax:
            d["min"], d["max"] = a.min(0).astype(float).tolist(), a.max(0).astype(float).tolist()
        accessors.append(d)
        return len(accessors) - 1

    tex_seen = {}

    def tex(png: bytes, repeat: bool):
        k_ = (hash(png), len(png), repeat)  # (the same picture is stored once: an impostor's normal map rarely changes with the season)
        if k_ in tex_seen:
            return tex_seen[k_]
        tex_seen[k_] = len(textures)
        images.append({"bufferView": view(png), "mimeType": "image/png"})
        textures.append({"source": len(images) - 1, "sampler": 0 if repeat else 1})
        return len(textures) - 1

    def prim(V, F, uv, material, wind, colour=None, N=None, uv3=None):
        N = _normals(V, F) if N is None else N
        w4 = np.stack(wind, 1).astype(np.float32)
        at_ = {"POSITION": acc(_yup(V).astype(np.float32), "VEC3", 5126, 34962, minmax=True),
               "NORMAL": acc(_yup(N).astype(np.float32), "VEC3", 5126, 34962),
               "TEXCOORD_0": acc(np.c_[uv[:, 0], 1 - uv[:, 1]].astype(np.float32), "VEC2", 5126, 34962),
               "TEXCOORD_1": acc(w4[:, :2].copy(), "VEC2", 5126, 34962),
               "TEXCOORD_2": acc(w4[:, 2:].copy(), "VEC2", 5126, 34962),
               "_WIND": acc(w4, "VEC4", 5126, 34962)}
        if colour is not None:
            c = np.clip(colour, 0, 1)
            c = np.c_[c, c, c] if c.ndim == 1 else c
            at_["COLOR_0"] = acc(np.c_[c, np.ones(len(c))].astype(np.float32), "VEC4", 5126, 34962)
        if uv3 is not None:  # (a style's own pair of numbers per vertex: Godot reads TEXCOORD_2 + TEXCOORD_3 as CUSTOM0)
            at_["TEXCOORD_3"] = acc(np.asarray(uv3, np.float32), "VEC2", 5126, 34962)
        return {"attributes": at_, "indices": acc(F.astype(np.uint32).ravel(), "SCALAR", 5125, 34963), "material": material}

    col = np.asarray(bark.get("color", [0.5, 0.45, 0.4]), float)
    base = np.clip(bm["albedo"][..., None] * col[None, None], 0, 1)  # (sRGB colour x a multiplier: near enough)
    orm = np.stack([np.ones_like(bm["rough"]), bm["rough"], np.zeros_like(bm["rough"])], -1)
    if st and st["wood"].get("flat", True):  # a style's bark: one colour
        materials.append({"name": "bark", "pbrMetallicRoughness": {
            "baseColorFactor": [*veg_style.lin(veg_style.bark_color(s, st)), 1.0], "metallicFactor": 0.0,
            "roughnessFactor": float(st["wood"].get("roughness", 0.9))}})
    else:
        materials.append({"name": "bark", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": tex(_png(base), True)},
            "metallicRoughnessTexture": {"index": tex(_png(orm), True)}},
            "normalTexture": {"index": tex(_png(bm["normal"]), True)}})
    M_BARK = 0

    dabs = None
    if st and (st.get("crown") or {}).get("kind") == "clouds" and not tree.get("clump"):
        dabs = veg_cloud.dab_atlas(s, st)

    def solid_material(nm, rgb, season=None):  # a style's closed crown: one colour (x COLOR_0, the tone of each mass); None = bare then
        m_ = {"name": nm, "pbrMetallicRoughness": {"baseColorFactor": [*veg_style.material_color(rgb or [0.5, 0.5, 0.5], st), 1.0], "metallicFactor": 0.0,
                                                    "roughnessFactor": float(st["crown"].get("roughness", 0.85))}}
        if dabs is not None:  # leaf clouds: cards cut by the dab atlas's alpha; its grey tone x the colour x COLOR_0
            da_ = veg_cloud.dab_atlas(s, st, season) if season else dabs  # (spring may paint fresh tips: its own picture, the same alpha)
            m_["pbrMetallicRoughness"]["baseColorTexture"] = {"index": tex(_png(da_["color"] / 255.0), False)}  # (uint8 x 255 wraps round: the atlas must go in as 0..1)
            m_.update(alphaMode="MASK", alphaCutoff=float(st["crown"].get("alpha_cut", 0.5)), doubleSided=True,
                      extras={"card_fill": round(dabs["fill"], 3)})
        if st.get("translucency"):  # pixar: what light through the canopy turns (the engine's subsurface / back light)
            m_["extras"] = {**m_.get("extras", {}), "translucency": {**st["translucency"], "thickness": "TEXCOORD_3.y = metres of canopy behind the point"}}
        rp_ = veg_style.season_ramp(s, season, st) if (season and dabs is None and rgb is not None) else None
        if rp_ is not None:  # (a season painting the masses' edges: a ramp over TEXCOORD_0.x, factor x texture = the colour)
            img_, fac_ = veg_style.ramp_texture(rp_)
            m_["pbrMetallicRoughness"]["baseColorFactor"] = [*fac_, 1.0]
            m_["pbrMetallicRoughness"]["baseColorTexture"] = {"index": tex(_png(img_), False)}
            m_["extras"] = {**m_.get("extras", {}), "ramp": "baseColorTexture is a ramp over TEXCOORD_0.x (0 = a mass's foot / a tier's rim)"}
        if rgb is None:
            m_.update(alphaMode="MASK", alphaCutoff=1.01, extras={**m_.get("extras", {}), "hidden": True})  # (bare then: the cut-off above 1 hides it in viewers that read variants)
        materials.append(m_)
        return len(materials) - 1

    def foliage_material(a_, nm, hidden=False):
        m = a_["mask"]
        orm_ = np.stack([np.ones_like(m[..., 1]), m[..., 1], np.zeros_like(m[..., 1])], -1)
        materials.append({"name": nm, "pbrMetallicRoughness": {
            "baseColorTexture": {"index": tex(_png(a_["color"]), False)},
            "metallicRoughnessTexture": {"index": tex(_png(orm_), False)}},
            "normalTexture": {"index": tex(_png(a_["normal"]), False)},
            "alphaMode": "MASK", "alphaCutoff": 1.01 if hidden else 0.4, "doubleSided": True,
            "extras": {"mask_texture": "R = light comes through (leaf), G = roughness, B = shade",
                       "card_fill": round(a_["fill"], 3)}})
        materials[-1]["extras"]["mask_texture_index"] = tex(_png(a_["mask"]), False)
        return len(materials) - 1

    seasons = list(seasons or ["summer"])
    variants, var_fol, var_bark = [], {}, {}
    M_FOL = None
    if st and has_leaves:
        se0 = s.get("season", "summer") if s.get("season") in seasons else seasons[0]
        M_FOL = solid_material("foliage", veg_style.season_color(s, se0, st), se0)
        for se in seasons:
            var_fol[se] = M_FOL if se == se0 else solid_material(f"foliage_{se}", veg_style.season_color(s, se, st), se)
        if wet:
            mw = json.loads(json.dumps(materials[M_FOL]))
            mw["name"] = "foliage_wet"
            mw["pbrMetallicRoughness"]["baseColorFactor"] = [0.7 * c_ for c_ in mw["pbrMetallicRoughness"]["baseColorFactor"][:3]] + [1.0]
            mw["pbrMetallicRoughness"]["roughnessFactor"] = 0.4
            materials.append(mw)
            var_fol["wet"] = len(materials) - 1
    # pixar: a layer of real leaf cards on the closed shell = the foliage mesh's next primitive, slot `foliage_cards`
    # (alpha MASK, double sided, a grey leaf atlas x baseColorFactor x COLOR_0), its own material per season
    M_CARDS, var_cards = None, {}
    if st and has_leaves and (st.get("crown") or {}).get("cards") and not trees[0].get("clump"):
        cs_ = {**veg_cloud.CARDS, **st["crown"]["cards"]}
        kg_ = float(max(cs_["tone"]) * (1 + float(cs_["warm_tip"])))

        def cards_material(nm, rgb, season):
            sub_ = veg_cloud.shell_atlas(s, st, season)
            c_ = np.array(veg_style.lin(rgb or [0.5, 0.5, 0.5])) * kg_
            m_ = {"name": nm, "pbrMetallicRoughness": {"baseColorFactor": [*(c_ / max(1.0, float(c_.max()))).tolist(), 1.0], "metallicFactor": 0.0,
                                                        "roughnessFactor": float(st["crown"].get("roughness", 0.8)),
                                                        "baseColorTexture": {"index": tex(_png(sub_["color"] / 255.0), False)}},
                  "alphaMode": "MASK", "alphaCutoff": float(cs_.get("alpha_cut", 0.5)), "doubleSided": True,
                  "extras": {"card_fill": round(sub_["fill"], 3), **({"translucency": {**st["translucency"], "thickness": "TEXCOORD_3.y = metres (cards: thin)"}} if st.get("translucency") else {})}}
            if rgb is None:
                m_.update(alphaCutoff=1.01, extras={**m_["extras"], "hidden": True})
            materials.append(m_)
            return len(materials) - 1
        M_CARDS = cards_material("foliage_cards", veg_style.season_color(s, se0, st), se0)
        for se in seasons:
            var_cards[se] = M_CARDS if se == se0 else cards_material(f"foliage_cards_{se}", veg_style.season_color(s, se, st), se)
    # a styled small plant whose blades lie down in winter (veg_small's winter `flatten`): the lying blades are the
    # foliage mesh's own primitive, slot `foliage_winter`, shown only in winter and snow (when `foliage` is hidden).
    # A second primitive rather than a morph target: the engine already hides slots per season from the seasons json,
    # blades are a few hundred triangles, and it needs no blend weights kept in step with wind and LODs.
    M_FW, var_fw, lie = None, {}, [se for se in seasons if se in ("winter", "snow")]
    if st and has_leaves and len(trees) == 1 and trees[0].get("clump") and lie and se0 not in lie:
        from . import veg_small
        if float((veg_small.season_state(s, "winter") or {}).get("flatten", 0.0)) > 0:
            M_FW = solid_material("foliage_winter", None)
            gone = solid_material("foliage_lying", None)  # (the upright blades' material in winter: hidden)
            for se in seasons:
                if se in lie:
                    var_fw[se] = solid_material(f"foliage_winter_{se}", veg_style.season_color(s, se, st), se)
                    var_fol[se] = gone
                else:
                    var_fw[se] = M_FW
    if at is not None:
        M_FOL = foliage_material(at, "foliage")
        for se in seasons:
            if se == "summer":
                var_fol[se] = M_FOL
                continue
            a_ = season_atlas(s, se, twc)
            if a_ is at:
                var_fol[se] = M_FOL
            elif a_ is None:
                materials.append({**json.loads(json.dumps(materials[M_FOL])), "name": f"foliage_{se}", "alphaCutoff": 1.01})
                materials[-1]["extras"] = {**materials[-1].get("extras", {}), "hidden": True}
                var_fol[se] = len(materials) - 1
            else:
                var_fol[se] = foliage_material(a_, f"foliage_{se}")
        if wet:
            mw = json.loads(json.dumps(materials[M_FOL]))
            mw["name"] = "foliage_wet"
            mw["pbrMetallicRoughness"].update(baseColorFactor=[0.78, 0.8, 0.76, 1.0], roughnessFactor=0.45)
            materials.append(mw)
            var_fol["wet"] = len(materials) - 1
    if wet:
        mw = json.loads(json.dumps(materials[M_BARK]))
        mw["name"] = "bark_wet"
        f0 = mw["pbrMetallicRoughness"].get("baseColorFactor", [1, 1, 1, 1])
        mw["pbrMetallicRoughness"].update(baseColorFactor=[0.55 * f0[0], 0.53 * f0[1], 0.5 * f0[2], 1.0], roughnessFactor=0.5)
        materials.append(mw)
        var_bark["wet"] = len(materials) - 1
    variants = [v_ for v_ in seasons + (["wet"] if wet else []) if len(seasons) + bool(wet) > 1]
    # a style's forks (the wood's second primitive): there when the foliage is not
    M_FORK, var_fork = None, {}
    if st and has_leaves:
        bare = {se: veg_style.season_color(s, se, st) is None for se in seasons}
        if any(bare.values()):
            hid = {**json.loads(json.dumps(materials[M_BARK])), "name": "bark_forks", "alphaMode": "MASK", "alphaCutoff": 1.01, "extras": {"hidden": True}}
            vis = {**json.loads(json.dumps(materials[M_BARK])), "name": "bark_forks_bare"}
            materials.extend([hid, vis])
            var_fork = {se: len(materials) - (1 if bare[se] else 2) for se in seasons}
            M_FORK = var_fork[se0]

    def with_variants(p_, table, default):
        if variants and table:
            ext_used.add("KHR_materials_variants")
            by = {}
            for i_, v_ in enumerate(variants):
                by.setdefault(table.get(v_, default), []).append(i_)
            p_["extensions"] = {"KHR_materials_variants": {"mappings": [{"material": m_, "variants": vs} for m_, vs in by.items()]}}
        return p_

    M_IMP = None
    crop_ = crops_ = None
    if impostor is not None and impostor.get("kind") == veg_impostor.KIND:
        # the quad covers only what any frame of any season draws (the game: a square the bake sphere's size spent
        # half its pixels on nothing)
        ims_ = [impostor["image"]] + [(v_["image"] if isinstance(v_, dict) else v_) for v_ in (impostor.get("seasons") or {}).values()]
        crop_ = veg_impostor.crop(ims_, int(impostor["frames"]))
        crops_ = veg_impostor.crops(ims_, int(impostor["frames"]))
    if impostor is not None:
        def imp_material(nm, im_, nrm_):
            m_ = {"name": nm, "pbrMetallicRoughness": {
                "baseColorTexture": {"index": tex(_png(im_), False)}, "metallicFactor": 0.0, "roughnessFactor": 0.9},
                "alphaMode": "MASK", "alphaCutoff": 0.5, "doubleSided": False,
                "extras": {"impostor": "albedo (unlit; the shade of what stands above it baked in, no sun) + a tangent-space normal map "
                                       "baked from the same two views: light it like any mesh. Front and back of each quad are faces of "
                                       "their own (single sided) with opposite NORMAL and their own TANGENT (w = -1 on the back), so "
                                       "the one normal map reads mirrored through the quad from behind. "
                                       "Engine: the material must NOT RECEIVE shadows (Godot: disable_receive_shadows): the two quads "
                                       "shadow each other, a dark wedge down the middle; casting onto the ground is fine",
                           "receive_shadows": False}}
            if impostor.get("kind") == veg_impostor.KIND:  # one camera-facing quad: the normal map is OBJECT space (+ depth in alpha),
                m_["extras"] = {"hifipushie_impostor": {  # so it is not a glTF normalTexture (tangent space): it rides in the extras
                    "kind": veg_impostor.KIND, "frames": int(impostor["frames"]), "size": round(float(impostor["size"]), 4),
                    "centre": [round(float(c_), 4) for c_ in impostor["centre"]],
                    "normal_texture_index": tex(_png(nrm_), False) if nrm_ is not None else None,
                    "normal": "object space, glTF axes: rgb * 2 - 1; alpha = depth behind the frame's middle plane (0 front .. 1 back of "
                              "the bake sphere, x size)", "recipe": veg_impostor.recipe(int(impostor["frames"]), float(impostor["size"]), impostor["centre"], crop_),
                    "crop": crop_, "crops": crops_, "drawn_share": round(veg_impostor.drawn_share(crops_, int(impostor["frames"])), 3) if crops_ else None,
                    "shader": veg_impostor.SHADER}, "receive_shadows": False}
            elif nrm_ is not None:
                m_["normalTexture"] = {"index": tex(_png(nrm_), False)}
            materials.append(m_)
            return len(materials) - 1
        M_IMP = imp_material("impostor", impostor["image"], impostor.get("normal"))
        var_imp = {}
        for se, im_ in (impostor.get("seasons") or {}).items():
            if se in seasons and se != seasons[0]:
                im_ = im_ if isinstance(im_, dict) else {"image": im_}
                var_imp[se] = imp_material(f"impostor_{se}", im_["image"], im_.get("normal"))
    per, roots = [], []
    cluster_mats = {}
    head_mats = {}
    if spacing is None:
        spacing = 0.0 if len(trees) == 1 else 1.2 * max(float(np.percentile(np.linalg.norm(t["pos"][:, :2], axis=1), 98)) for t in trees) * 2
    n_lod = int(np.clip(lods, 1, len(LODS)))
    for k, (t, nm) in enumerate(zip(trees, names)):
        wn = wind_nodes(t)
        lod_nodes, lod_info = [], []
        for li in range(0 if only_impostor else n_lod):
            share, cap_ = LODS[li]
            cap_i = cap_ if n_lod > 1 or cap is None else cap
            if st:
                D = veg_style.dress(t, st, int(triangles * share), se0 if has_leaves else "summer")
                if has_leaves and D["crown"] is None:  # (the file's default season is a bare one: the masses are still in it, hidden)
                    D = veg_style.dress(t, st, int(triangles * share), "summer")
                pre = (f"{nm}_" if len(trees) > 1 else "") + (f"LOD{li}_" if n_lod > 1 or impostor is not None else "")
                W = D["wood"]
                kids = []
                wp = [with_variants(prim(W["V"], W["F"], W["uv"], M_BARK, D["wood_wind"], N=W["N"]), var_bark, M_BARK)]
                K_ = D["forks"]
                if K_ is not None and M_FORK is not None:
                    wp.append(with_variants(prim(K_["V"], K_["F"], K_["uv"], M_FORK, K_["wind"], N=K_["N"]), var_fork, M_FORK))
                meshes.append({"name": pre + "wood", "primitives": wp})
                nodes.append({"name": pre + "wood", "mesh": len(meshes) - 1})
                kids.append(len(nodes) - 1)
                c = {"name": nm, "lod": li, "height_m": round(t["height"], 2), "wood_triangles": int(len(W["F"])), "foliage_triangles": 0,
                     "twigs_kept": 1.0, "wood_min_radius_m": 0.0, "floating": 0.0, "style": D["info"]}
                C_ = D["crown"]
                if C_ is not None:
                    p_ = prim(C_["V"], C_["F"], C_["uv"], M_FOL, C_["wind"], C_["col"], C_["N"], uv3=C_.get("grad"))
                    fp = [with_variants(p_, var_fol, M_FOL)]
                    K_ = D.get("cards")
                    if K_ is not None and M_CARDS is not None:  # pixar: the leaf cards on the shell
                        fp.append(with_variants(prim(K_["V"], K_["F"], K_["uv"], M_CARDS, K_["wind"], K_["col"], K_["N"], uv3=K_["grad"]), var_cards, M_CARDS))
                        c["cards_triangles"] = int(len(K_["F"]))
                    Hd = D.get("heads")
                    if Hd is not None:  # a small plant's flower / seed heads: the foliage mesh's second primitive, slot `heads`
                        if "heads" not in head_mats:
                            shown = {"name": "heads", "pbrMetallicRoughness": {"baseColorFactor": [1.0, 1.0, 1.0, 1.0], "metallicFactor": 0.0,
                                                                                "roughnessFactor": float(st["crown"].get("roughness", 0.85))}}
                            hid_ = {**json.loads(json.dumps(shown)), "alphaMode": "MASK", "alphaCutoff": 1.01, "extras": {"hidden": True}}
                            d_show = se0 in Hd["seasons"]
                            (hid_ if d_show else shown)["name"] = "heads_hidden" if d_show else "heads_shown"
                            (shown if d_show else hid_)["name"] = "heads"
                            materials.extend([shown, hid_])
                            head_mats["heads"] = {se: len(materials) - (2 if se in Hd["seasons"] else 1) for se in seasons}
                        vh = head_mats["heads"]
                        hcol = np.array([veg_style.lin(c_) for c_ in Hd["part_colors"]])[Hd["part"]]  # (COLOR_0 = each part's colour, linear: petals, centre, stalk)
                        fp.append(with_variants(prim(Hd["V"], Hd["F"], Hd["uv"], vh[se0], Hd["wind"], hcol, N=Hd["N"]), vh, vh[se0]))
                        c["heads_triangles"] = int(len(Hd["F"]))
                    if M_FW is not None:  # the blades lying down (winter, snow): their own primitive
                        if "_winter_tree" not in t:
                            t["_winter_tree"] = vegetation.grow({**t["spec"], "season": "winter"})
                        Dw = veg_style.dress(t["_winter_tree"], st, int(triangles * share), "winter")
                        Cw = Dw["crown"]
                        if Cw is not None:
                            fp.append(with_variants(prim(Cw["V"], Cw["F"], Cw["uv"], M_FW, Cw["wind"], Cw["col"], Cw["N"], uv3=Cw.get("grad")), var_fw, M_FW))
                            c["winter_triangles"] = int(len(Cw["F"]))
                    meshes.append({"name": pre + "foliage", "primitives": fp})
                    nodes.append({"name": pre + "foliage", "mesh": len(meshes) - 1})
                    kids.append(len(nodes) - 1)
                    c["foliage_triangles"] = int(len(C_["F"])) + c.get("heads_triangles", 0) + c.get("cards_triangles", 0)
                c["triangles"] = c["wood_triangles"] + c["foliage_triangles"]
                lod_info.append(c)
                if n_lod == 1 and impostor is None and len(trees) == 1:
                    lod_nodes.append(kids)
                else:
                    nodes.append({"name": f"{nm}_LOD{li}", "children": kids})
                    lod_nodes.append([len(nodes) - 1])
                continue
            bud = budget(t, int(triangles * share) if triangles else None, tile, at["triangles"] if at else 0, cap_i)
            if li and not triangles:  # no budget asked: lower LODs still step down from the full tree
                full = lod_info[0]["triangles"]
                bud = budget(t, int(full * share), tile, at["triangles"] if at else 0, cap_i)
            W = bud["wood"]
            lf_c, cap_c, back_c = cluster_leaves(s["leaves"], bud["keep"])
            at_c, m_c, vf_c = at, M_FOL, var_fol
            tw_c = None
            boughs = bool(bud.get("boughs")) and at is not None
            if at is not None and (boughs or lf_c is not s["leaves"]):  # bough cards: their own picture (and its season variants)
                # (LODs thinned from one cut of the tree share its atlas and material: one foliage_boughs slot)
                cut_ = (veg_bough.base_of(t, bud["boughs"]), veg_bough.form_of(t, bud["boughs"])) if boughs and len(trees) == 1 else (None, 0)
                ck = (f"boughs_cut{cut_[0]}_{cut_[1]}" if cut_[0] else f"boughs{li}") if boughs else json.dumps(lf_c["card"], sort_keys=True)
                if ck not in cluster_mats:
                    # (a set shares one bough atlas per LOD: baked from the first plant that needs it)
                    make = (lambda lf_, twc_, t0=t, nb=bud["boughs"]: veg_bough.atlas(t0, lf_, twc_, nb)) if boughs else veg_leaf.atlas
                    sp_c = {**s, "leaves": s["leaves"] if boughs else lf_c}
                    at_c = make(sp_c["leaves"], twc)
                    m_ = foliage_material(at_c, f"foliage_boughs{len(cluster_mats) + 1}")
                    vf_ = {}
                    for se in seasons:
                        a_ = season_atlas(sp_c, se, twc, make) if se != "summer" else at_c
                        if a_ is None:
                            materials.append({**json.loads(json.dumps(materials[m_])), "name": f"{materials[m_]['name']}_{se}", "alphaCutoff": 1.01})
                            materials[-1]["extras"] = {**materials[-1].get("extras", {}), "hidden": True}
                            vf_[se] = len(materials) - 1
                        else:
                            vf_[se] = m_ if a_ is at_c else foliage_material(a_, f"{materials[m_]['name']}_{se}")
                    if wet:
                        mw_ = json.loads(json.dumps(materials[m_]))
                        mw_["name"] += "_wet"
                        mw_["pbrMetallicRoughness"].update(baseColorFactor=[0.78, 0.8, 0.76, 1.0], roughnessFactor=0.45)
                        materials.append(mw_)
                        vf_["wet"] = len(materials) - 1
                    cluster_mats[ck] = (at_c, m_, vf_)
                at_c, m_c, vf_c = cluster_mats[ck]
                if boughs:
                    tw_c = veg_bough.place(t, bud["boughs"], at_c)
            L = foliage_mesh(t, at_c, bud["keep"], bud["min_radius"], bud["protect"], cap_c if at_c is not at else cap_i, back_c, tw=tw_c) \
                if at and len(veg_leaf.place(t)["pos"]) else None
            pre = (f"{nm}_" if len(trees) > 1 else "") + (f"LOD{li}_" if n_lod > 1 or impostor is not None else "")
            kids = []
            wn_w = W["node"]
            p_ = prim(W["V"], W["F"], W["uv"], M_BARK, (wn["trunk"][wn_w], wn["branch"][wn_w], wn["phase"][wn_w], np.zeros(len(wn_w))))
            meshes.append({"name": pre + "wood", "primitives": [with_variants(p_, var_bark, M_BARK)]})
            nodes.append({"name": pre + "wood", "mesh": len(meshes) - 1})
            kids.append(len(nodes) - 1)
            c = {"name": nm, "lod": li, "height_m": round(t["height"], 2), "wood_triangles": int(len(W["F"])), "foliage_triangles": 0,
                 "twigs_kept": round(bud["keep"], 3), "wood_min_radius_m": round(bud["min_radius"], 4),
                 "floating": round(bud["floating"], 3)}
            if L is not None and len(L["F"]):
                def card_wind(L, wn):
                    fn = L["node"]
                    wch = (wn["trunk"][fn], wn["branch"][fn], wn["phase"][fn], L["flutter"])
                    if t.get("clump"):  # a small plant's card bends as a whole from its foot, each in its own phase; long
                        # cards swing further (the recipe's limb amplitude is 0.25 m: a 30 cm tuft's tip moves ~5 cm)
                        own = L["flutter"] ** 1.5 * np.clip(L["reach"] / 1.2, 0.08, 1.0)
                        wch = (wn["trunk"][fn], np.maximum(wn["branch"][fn], own), np.where(wn["branch"][fn] > own, wn["phase"][fn], L["phase"]),
                               0.5 * L["flutter"])
                    return wch
                p_ = prim(L["V"], L["F"], L["uv"], m_c, card_wind(L, wn),
                          L["tint"], L["N"])
                fprims = [p_]
                lie_r = [se for se in seasons if se in ("winter", "snow")]
                if (t.get("clump") and len(trees) == 1 and lie_r and seasons[0] not in lie_r
                        and float((veg_small_state(s, "winter") or {}).get("flatten", 0.0)) > 0):
                    # a realistic small plant whose blades lie down in winter: as the styled ones, slot foliage_winter =
                    # the cards of the plant regrown at season winter, shown in winter / snow while foliage is hidden
                    if "_winter_tree" not in t:
                        t["_winter_tree"] = vegetation.grow({**t["spec"], "season": "winter"})
                    tw_ = t["_winter_tree"]
                    Lw = foliage_mesh(tw_, at_c, bud["keep"], bud["min_radius"], bud["protect"], cap_c if at_c is not at else cap_i, back_c)
                    if not len(Lw["F"]):  # (a low LOD's keep share can leave the lying plant no cards: keep them all, it is small)
                        Lw = foliage_mesh(tw_, at_c, 1.0, 0.0, None, cap_c if at_c is not at else cap_i, back_c)
                    if len(Lw["F"]):
                        hk = ("lie", m_c)
                        if hk not in cluster_mats:
                            hid = [{**json.loads(json.dumps(materials[m_c])), "name": f"{materials[m_c]['name']}_{sfx}", "alphaCutoff": 1.01}
                                   for sfx in ("winter", "lying")]
                            for h_ in hid:
                                h_["extras"] = {**h_.get("extras", {}), "hidden": True}
                            materials.extend(hid)
                            cluster_mats[hk] = (len(materials) - 2, len(materials) - 1)
                        m_w, m_l = cluster_mats[hk]
                        tab_main = {se: (m_l if se in lie_r else vf_c.get(se, m_c)) for se in seasons}
                        tab_w = {se: (vf_c.get(se, m_c) if se in lie_r else m_w) for se in seasons}
                        fprims = [with_variants(p_, tab_main, m_c),
                                  with_variants(prim(Lw["V"], Lw["F"], Lw["uv"], m_w, card_wind(Lw, wind_nodes(tw_)), Lw["tint"], Lw["N"]), tab_w, m_w)]
                        c["winter_triangles"] = int(len(Lw["F"]))
                if len(fprims) == 1:
                    fprims = [with_variants(p_, vf_c, m_c)]
                meshes.append({"name": pre + "foliage", "primitives": fprims})
                c["boughs"] = at_c is not at
                nodes.append({"name": pre + "foliage", "mesh": len(meshes) - 1})
                kids.append(len(nodes) - 1)
                c["foliage_triangles"] = int(len(L["F"]))
            c["triangles"] = c["wood_triangles"] + c["foliage_triangles"]
            lod_info.append(c)
            if n_lod == 1 and impostor is None and len(trees) == 1:
                lod_nodes.append(kids)
            else:
                nodes.append({"name": (f"{nm}_" if len(trees) > 1 else f"{nm}_") + f"LOD{li}", "children": kids})
                lod_nodes.append([len(nodes) - 1])
        if impostor is not None and k == 0 and len(trees) == 1 and impostor.get("kind") == veg_impostor.KIND:
            # hemi-octahedral: ONE quad, rebuilt to face the camera by the engine's shader (veg_impostor.recipe); stored as
            # a vertical square through the bake centre facing +y (glTF +z), uv 0..1 = its corners
            S_, Cg = float(impostor["size"]), np.asarray(impostor["centre"], float)
            Cb = np.array([Cg[0], -Cg[2], Cg[1]])
            u0_, u1_, v0_, v1_ = crop_ or [0.0, 1.0, 0.0, 1.0]
            xa_, xb_ = (u0_ - 0.5) * S_, (u1_ - 0.5) * S_
            za_, zb_ = (0.5 - v1_) * S_, (0.5 - v0_) * S_
            Vq = np.array([Cb + [xa_, 0, za_], Cb + [xb_, 0, za_], Cb + [xb_, 0, zb_], Cb + [xa_, 0, zb_]])
            Uq = np.array([[0, 1.0], [1, 1], [1, 0], [0, 0]])
            Fq = np.array([[0, 1, 2], [0, 2, 3]])
            Nq = np.tile([0, -1.0, 0], (4, 1))
            zt = np.clip(Vq[:, 2] / max(t["height"], 1e-6), 0, 1) ** 1.5
            z4 = np.zeros(4)
            p_ = prim(Vq, Fq, Uq[:, [0, 1]] * [1, -1] + [0, 1], M_IMP, (zt, z4, z4, z4), N=Nq)
            meshes.append({"name": f"LOD{n_lod}_impostor", "primitives": [with_variants(p_, var_imp, M_IMP)],
                           "extras": {"hifipushie_impostor": veg_impostor.KIND, "cull_margin_m": round(0.5 * S_, 3)}})
            nodes.append({"name": f"{nm}_LOD{0 if only_impostor else n_lod}", "mesh": len(meshes) - 1})
            lod_nodes.append([len(nodes) - 1])
            lod_info.append({"name": nm, "lod": n_lod, "triangles": 2, "impostor": True, "impostor_kind": veg_impostor.KIND})
        elif impostor is not None and k == 0 and len(trees) == 1:
            S_, H_ = float(impostor["size"]), float(impostor["height"])
            Vq, Fq, Uq, Nq, Tq = [], [], [], [], []
            for j, (r_, o_) in enumerate(impostor_frames()):  # each picture on the quad its camera faced; then that quad's back
                q = np.array([-0.5 * S_ * r_ + [0, 0, H_ - 0.5 * S_], 0.5 * S_ * r_ + [0, 0, H_ - 0.5 * S_],
                              0.5 * S_ * r_ + [0, 0, H_ + 0.5 * S_], -0.5 * S_ * r_ + [0, 0, H_ + 0.5 * S_]])
                uq = np.array([[0, 0], [1, 0], [1, 1], [0, 1]]) * [0.5, 1] + [0.5 * j, 0]
                for side in (1.0, -1.0):
                    f0 = np.array([[0, 1, 2], [0, 2, 3]]) + 4 * len(Vq)
                    Vq.append(q)
                    Uq.append(uq)
                    Fq.append(f0 if side > 0 else f0[:, ::-1])
                    Nq.append(np.tile(side * o_, (4, 1)))
                    Tq.append(np.tile(np.r_[r_, side], (4, 1)))  # (bitangent = N x T x w = up on both sides)
            Vq, Fq, Uq, Nq, Tq = np.vstack(Vq), np.vstack(Fq), np.vstack(Uq), np.vstack(Nq), np.vstack(Tq)
            zt = np.clip(Vq[:, 2] / max(t["height"], 1e-6), 0, 1) ** 1.5
            z16 = np.zeros(len(Vq))
            p_ = prim(Vq, Fq, Uq, M_IMP, (zt, z16, z16, z16), N=Nq)
            p_["attributes"]["TANGENT"] = acc(np.c_[_yup(Tq[:, :3]), Tq[:, 3]].astype(np.float32), "VEC4", 5126, 34962)
            meshes.append({"name": f"LOD{n_lod}_impostor", "primitives": [with_variants(p_, var_imp, M_IMP)]})
            nodes.append({"name": f"{nm}_LOD{0 if only_impostor else n_lod}", "mesh": len(meshes) - 1})
            lod_nodes.append([len(nodes) - 1])
            lod_info.append({"name": nm, "lod": n_lod, "triangles": 8, "impostor": True})
        # screen heights (the plant's share of the view's height) under which an engine should switch down
        for li, c in enumerate(lod_info):
            c["switch_below_screen_height"] = [None, 0.45, 0.2, 0.08][li] if li < 4 else 0.05
        head = lod_nodes[0]
        if len(lod_nodes) > 1:
            ext_used.add("MSFT_lod")
            nodes[head[0]]["extensions"] = {"MSFT_lod": {"ids": [ln[0] for ln in lod_nodes[1:]]}}
            nodes[head[0]]["extras"] = {"MSFT_screencoverage": [0.45, 0.2, 0.08, 0.0][:len(lod_nodes)]}
        if len(trees) == 1:
            roots = head
        else:
            nodes.append({"name": nm, "children": head, "translation": [float((k - (len(trees) - 1) / 2) * spacing), 0.0, 0.0],
                          "extras": {"height_m": round(t["height"], 2), "seed": t["spec"].get("seed"), "age": t["spec"].get("age")}})
            roots.append(len(nodes) - 1)
        c0 = {"wood_triangles": 0, "foliage_triangles": 0, "twigs_kept": 1.0, "wood_min_radius_m": 0.0, "floating": 0.0,
              **lod_info[0]}
        c0["lods"] = lod_info
        caps = [] if only_impostor else collision(t)  # (the grown tree's, whatever the style: a style must not change gameplay)
        c0["collision"] = [{"a": _yup(np.array([q["a"]]))[0].tolist(), "b": _yup(np.array([q["b"]]))[0].tolist(), "ra": q["ra"], "rb": q["rb"]}
                           for q in caps]
        if caps:
            thr = max(0.05, 0.3 * float(t["radius"][1]))
            C = veg_mesh.tubes(t, sides=(4, 5), min_radius=thr, simplify=1.5, collar=0, tile=tile)
            z4 = np.zeros(len(C["V"]))
            if len(C["F"]):  # (a shrub's stems can be thinner than anything a player bumps into)
                meshes.append({"name": f"{nm}_collision", "primitives": [prim(C["V"], C["F"], C["uv"], M_BARK, (z4, z4, z4, z4))]})
                nodes.append({"name": f"{nm}_collision", "mesh": len(meshes) - 1, "extras": {"collision": True}})
                c0["collision_node"] = len(nodes) - 1
            c0["collision_triangles"] = int(len(C["F"]))
        per.append(c0)
    counts = {"wood_triangles": sum(c["wood_triangles"] for c in per), "foliage_triangles": sum(c["foliage_triangles"] for c in per),
              "twigs_kept": per[0]["twigs_kept"], "wood_min_radius_m": per[0]["wood_min_radius_m"], "budget": triangles,
              "floating": max(c["floating"] for c in per), "lods": per[0]["lods"], "variants": variants,
              "collision_capsules": len(per[0]["collision"]), "collision_triangles": per[0].get("collision_triangles", 0)}
    if st and per[0]["lods"] and per[0]["lods"][0].get("style"):
        counts["style"] = per[0]["lods"][0]["style"]
    if at is not None:
        counts["atlas_px"] = int(at["color"].shape[0])
    if len(trees) > 1:
        counts["plants"] = per
    name = names[0] if len(trees) == 1 else "set"
    while len(buf) % 4:
        buf.append(0)
    gltf = {"asset": {"version": "2.0", "generator": "hifipushie vegetation"},
            "scene": 0, "scenes": [{"nodes": roots}], "nodes": nodes, "meshes": meshes,
            "materials": materials, **({"textures": textures, "images": images} if textures else {}),
            "samplers": [{"wrapS": 10497, "wrapT": 10497, "magFilter": 9729, "minFilter": 9987},
                         {"wrapS": 33071, "wrapT": 33071, "magFilter": 9729, "minFilter": 9987}],
            "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(buf)}],
            "extras": {"hifipushie_plant": {"name": name, "species": s.get("species"), "age": s.get("age"),
                                            "height_m": round(tree["height"], 2), "stats": tree["stats"],
                                            "set": len(trees) if len(trees) > 1 else None, "bark_tile_m": bm["tile"],
                                            "lods": [[{k_: v_ for k_, v_ in c.items()} for c in p_["lods"]] for p_ in per],
                                            "wind": WIND_RECIPE, "variants": variants, "contract": CONTRACT,
                                            "style": None if not st else {
                                                "name": st["name"], "sheet": {k_: v_ for k_, v_ in st.items() if k_ != "about"},
                                                "simplified": veg_style.lines(per[0]["lods"][0]["style"]) if per[0]["lods"] and per[0]["lods"][0].get("style") else [],
                                                "kind": "clouds" if dabs is not None else "masses",
                                                "foliage": ("leaf clouds: alpha-MASK cards, double sided; albedo = the dab atlas's grey tone x the "
                                                            "`foliage` material's baseColorFactor (one per season variant) x COLOR_0 (the clump's "
                                                            "painted gradient, one step per card); NORMAL = out of the clump's middle; TEXCOORD_0 = "
                                                            "the atlas uv; TEXCOORD_3 = (gradient 0 base .. 1 top of its clump, (clump + 0.5) / clumps); "
                                                            "wind: TEXCOORD_2.y = flutter, 0 at a card's middle .. at its rim") if dabs is not None else
                                                           "closed masses, no texture: albedo = the `foliage` material's baseColorFactor "
                                                           "(one per season variant) x COLOR_0 (each mass's tone); NORMAL = smooth over each "
                                                           "mass; TEXCOORD_0 = (height within its mass 0..1, (mass index + 0.5) / masses)",
                                                "season_colors_srgb": {se: veg_style.season_color(s, se, st) for se in veg_style.SEASONS}},
                                            "snow": "engine shader: see snow_numbers (in <name>_seasons.json as `snow`); "
                                                    "the `snow` variant is the ready-mixed foliage colour / picture",
                                            "snow_numbers": snow_numbers(s, st),
                                            "collision": [{"plant": p_["name"], "capsules": p_["collision"],
                                                           "mesh_node": p_.get("collision_node")} for p_ in per]}}}
    if variants and ext_used & {"KHR_materials_variants"}:
        gltf["extensions"] = {"KHR_materials_variants": {"variants": [{"name": v_} for v_ in variants]}}
    if ext_used:
        gltf["extensionsUsed"] = sorted(ext_used)
    js = json.dumps(gltf, separators=(",", ":"), default=float).encode()
    js += b" " * (-len(js) % 4)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(buf)))
        f.write(struct.pack("<I4s", len(js), b"JSON"))
        f.write(js)
        f.write(struct.pack("<I4s", len(buf), b"BIN\0"))
        f.write(bytes(buf))
    counts["bytes"] = out.stat().st_size
    counts["path"] = str(out)
    return counts


def seasons_json(glb: str, images: bool = True) -> dict | None:
    """For engines that drop KHR_materials_variants (Godot 4.7 does: only the default material arrives): what each
    variant puts in each material slot, read back from the written GLB and saved beside it as <stem>_seasons.json:
    {"variants", "default", "slots": {slot (the default material's name): {"material", "baseColorFactor",
    "roughnessFactor", "alphaMode", "alphaCutoff", "doubleSided", "hidden", "baseColorTexture": {"image": index in the
    GLB, "file": the same picture written beside it}}}, "seasons": {variant: {slot: the same keys}}}. `hidden` = the
    slot is not drawn in that season (a deciduous winter): hide the mesh; don't rely on its alpha cut-off."""
    raw = open(glb, "rb").read()
    jl = struct.unpack("<I", raw[12:16])[0]
    G = json.loads(raw[20:20 + jl])
    binp = raw[20 + jl + 8:]
    names = [v_["name"] for v_ in (G.get("extensions") or {}).get("KHR_materials_variants", {}).get("variants", [])]
    if not names:
        return None
    stem = Path(glb).with_suffix("")
    written = {}

    def params(mi):
        m = G["materials"][mi]
        pbr = m.get("pbrMetallicRoughness", {})
        d = {"material": m["name"], "baseColorFactor": pbr.get("baseColorFactor", [1, 1, 1, 1]), "roughnessFactor": pbr.get("roughnessFactor", 1.0),
             "alphaMode": m.get("alphaMode", "OPAQUE"), "doubleSided": bool(m.get("doubleSided", False)),
             "hidden": bool((m.get("extras") or {}).get("hidden"))}
        if (m.get("extras") or {}).get("receive_shadows") is False:
            d["receive_shadows"] = False  # (an impostor's crossed quads shadow each other)
        if "alphaCutoff" in m:
            d["alphaCutoff"] = m["alphaCutoff"]
        hi_ = (m.get("extras") or {}).get("hifipushie_impostor")
        if hi_:
            d["impostor"] = {k_: v_ for k_, v_ in hi_.items() if k_ != "normal_texture_index"}
        for key, src in (("baseColorTexture", pbr.get("baseColorTexture")), ("normalTexture", m.get("normalTexture")),
                         ("metallicRoughnessTexture", pbr.get("metallicRoughnessTexture")),
                         ("impostorNormalTexture", {"index": hi_["normal_texture_index"]} if hi_ and hi_.get("normal_texture_index") is not None else None)):
            if src is None:
                continue
            im = G["textures"][src["index"]]["source"]
            d[key] = {"image": im}
            if images and key in ("baseColorTexture", "normalTexture", "impostorNormalTexture"):
                if im not in written:
                    bv = G["bufferViews"][G["images"][im]["bufferView"]]
                    f = Path(f"{stem}_{m['name']}{'_normal' if key != 'baseColorTexture' else ''}.png")
                    f.write_bytes(binp[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]])
                    written[im] = f.name
                d[key]["file"] = written[im]
        return d

    slots, seasons, where = {}, {n_: {} for n_ in names}, {}
    for mesh in G["meshes"]:
        for pi, p_ in enumerate(mesh["primitives"]):
            maps = (p_.get("extensions") or {}).get("KHR_materials_variants", {}).get("mappings")
            if "material" not in p_ or mesh["name"].endswith("_collision"):
                continue
            slot = G["materials"][p_["material"]]["name"]
            where.setdefault(slot, []).append({"mesh": mesh["name"], "primitive": pi})
            if slot in slots:
                continue
            slots[slot] = params(p_["material"])
            for mp in maps or []:
                for vi in mp["variants"]:
                    seasons[names[vi]][slot] = params(mp["material"])
    for n_ in names:  # (a slot a variant doesn't map keeps its default)
        for slot, d in slots.items():
            seasons[n_].setdefault(slot, d)
    slot_list = [{"slot": slot, "on": where[slot], "hidden_in": [n_ for n_ in names if seasons[n_][slot]["hidden"]],
                  "channels": sorted({a_ for mesh in G["meshes"] for p_ in mesh["primitives"]
                                      if "material" in p_ and G["materials"][p_["material"]]["name"] == slot for a_ in p_["attributes"]})}
                 for slot in slots]
    hp = (G.get("extras") or {}).get("hifipushie_plant") or {}
    out = {"contract": {"version": CONTRACT, "changes": {str(k_): v_ for k_, v_ in CONTRACT_LOG.items()},
                        "rule": "an engine should refuse a version or a slot it doesn't know: every slot is in slot_list"},
           "slot_list": slot_list,
           "style": {"name": (hp.get("style") or {}).get("name", "realistic"), "foliage": (hp.get("style") or {}).get("kind", "cards")},
           "snow": hp.get("snow_numbers"),
           "impostor": next((d_["impostor"] for d_ in slots.values() if "impostor" in d_), None),
           "glb": Path(glb).name, "variants": names, "default": names[0], "slots": slots, "seasons": seasons,
           "note": "colours are linear RGBA factors (x the texture when there is one, x COLOR_0 where the mesh has it); "
                   "hidden = don't draw that slot's meshes in that season"}
    Path(f"{stem}_seasons.json").write_text(json.dumps(out, indent=1))
    out["path"] = f"{stem}_seasons.json"
    return out


def write_collision(tree: dict, path: str, name: str) -> str | None:
    """The collision mesh as a file of its own, its node in the scene and named `<name>_collision-colonly` (Godot's
    importer makes a static body of a node so named and drops the mesh; the plant's own GLB keeps it outside the scene,
    where Godot never sees it). Capsules in extras. The grown tree's, whatever its style."""
    caps = collision(tree)
    thr = max(0.05, 0.3 * float(tree["radius"][1]))
    C = veg_mesh.tubes(tree, sides=(4, 5), min_radius=thr, simplify=1.5, collar=0)
    if not len(C["F"]):
        return None
    V = _yup(C["V"]).astype(np.float32)
    F = C["F"].astype(np.uint32).ravel()
    buf = V.tobytes() + F.tobytes()
    gltf = {"asset": {"version": "2.0", "generator": "hifipushie vegetation"}, "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": [{"name": f"{name}_collision-colonly", "mesh": 0, "extras": {"collision": True}}],
            "meshes": [{"name": f"{name}_collision", "primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(V), "type": "VEC3", "min": V.min(0).tolist(), "max": V.max(0).tolist()},
                          {"bufferView": 1, "componentType": 5125, "count": len(F), "type": "SCALAR"}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": V.nbytes, "target": 34962},
                            {"buffer": 0, "byteOffset": V.nbytes, "byteLength": F.nbytes, "target": 34963}],
            "buffers": [{"byteLength": len(buf)}],
            "extras": {"hifipushie_collision": {"plant": name, "capsules": [
                {"a": _yup(np.array([q["a"]]))[0].tolist(), "b": _yup(np.array([q["b"]]))[0].tolist(), "ra": q["ra"], "rb": q["rb"]} for q in caps]}}}
    js = json.dumps(gltf, separators=(",", ":"), default=float).encode()
    js += b" " * (-len(js) % 4)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(buf)))
        f.write(struct.pack("<I4s", len(js), b"JSON"))
        f.write(js)
        f.write(struct.pack("<I4s", len(buf), b"BIN\0"))
        f.write(buf)
    return str(path)


def write_impostor(tree: dict, path: str, name: str, impostor: dict, seasons=("summer",)) -> str:
    """The impostor LOD alone, as a file of its own (its pictures per season as variants)."""
    return write_glb(tree, path, name, impostor=impostor, only_impostor=True, seasons=seasons)["path"]
