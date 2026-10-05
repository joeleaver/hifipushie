"""A plant as a GLB (first export: one LOD; LODs, wind data and season variants are stage 4).

Two meshes: `wood` (branch tubes; bark base colour = the bark's colour x its tiling albedo, normal and roughness maps,
REPEAT sampling on the branch uv) and `foliage` (every twig's card, realised into one mesh; the twig atlas as base
colour with alpha MASK, double sided; COLOR_0 = a per-twig tint). glTF axes (Y up: x, z, -y), uv v flipped. Textures
are embedded. extras carry the plant's name, stats and counts.
"""

from __future__ import annotations

import io
import json
import struct
from pathlib import Path

import numpy as np

from . import veg_bark, veg_bough, veg_leaf, veg_mesh, vegetation


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
    var = veg_leaf.card_variant(tw, nv)
    tint = 0.75 + 0.5 * vegetation._u(tw["key"], 77)
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
    """What a triangle budget leaves of a plant: {"wood": the tube mesh, "sides", "min_radius" (thinner wood is left
    out, except `protected` wood), "keep" (the share of twigs drawn, each larger by 1 / sqrt(keep)), "floating" (the
    share of drawn twigs with no drawn wood near them), "total", "over": triangles past the budget (the trunk alone can
    be more than a tiny budget)}. Half the budget is the wood's; two thirds when at half too many cards would float."""
    tw = veg_leaf.place(tree)
    n_tw = len(tw["pos"])
    pr = protected(tree)
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
            out["boughs"] = int(min(max(triangles - len(out["wood"]["F"]), 0) // veg_bough.TRIS, veg_bough.most(tree)))
            out["boughs"] = len(veg_bough.plan(tree, out["boughs"])["roots"])
    fol = out["boughs"] * veg_bough.TRIS if out.get("boughs") else int(np.floor(n_tw * out["keep"] + 1e-9)) * card_triangles
    out["total"] = int(len(out["wood"]["F"]) + fol)
    out["over"] = max(0, out["total"] - int(triangles)) if triangles else 0
    return out


LODS = ((1.0, 2.5), (0.45, 2.5), (0.18, 4.0))  # (share of the budget, how much larger a kept card may be drawn)
AUTUMN = [0.78, 0.56, 0.16]
WIND_RECIPE = ("vertex shader: TEXCOORD_1 = (trunk, branch) weights, TEXCOORD_2 = (phase, flutter); the same four in _WIND "
               "(VEC4: trunk, branch, phase, flutter). P += windDir * (trunk * A_tree * sin(w_tree * t) + branch * A_limb * "
               "sin(w_limb * t + 6.283 * phase)) + N * flutter * A_leaf * sin(w_leaf * t + 40 * phase + dot(P, 3)); "
               "A_tree ~0.02 x height x gust, A_limb ~0.25 m x gust, A_leaf ~0.02 m, w_tree ~1, w_limb ~2.3, w_leaf ~9 rad/s")


def evergreen(spec: dict) -> bool:
    lf = spec["leaves"]
    return bool(lf.get("evergreen", str(lf.get("shape", "")).startswith("needle")))


def season_atlas(spec: dict, season: str, twig_color, make=None) -> dict | None:
    """The foliage atlas in a season: summer as specified; autumn = the same leaves in `leaves.autumn` (deciduous only;
    an evergreen keeps its colour); snow = the summer picture frosted. None = no leaves then (a deciduous winter)."""
    lf = spec["leaves"]
    make = make or veg_leaf.atlas  # (bough cards: veg_bough.atlas of the tree)
    if season in ("winter", "bare") and not evergreen(spec):
        return None
    if season == "autumn" and not evergreen(spec):
        return make({**lf, "color": lf.get("autumn", AUTUMN)}, twig_color)
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
    bark = s.get("bark") or {}
    bm = veg_bark.bark_maps(bark.get("kind", "furrowed"), 256, seed=int(s.get("seed", 1)))
    sc = float(bark.get("scale", 1.0))
    tile = [bm["tile"][0] * sc, bm["tile"][1] * sc]
    twc = bark.get("twig_color") or [0.45, 0.4, 0.35]
    has_leaves = any(len(veg_leaf.place(t)["pos"]) for t in trees)
    at = veg_leaf.atlas(s["leaves"], twc) if has_leaves else None
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

    def tex(png: bytes, repeat: bool):
        images.append({"bufferView": view(png), "mimeType": "image/png"})
        textures.append({"source": len(images) - 1, "sampler": 0 if repeat else 1})
        return len(textures) - 1

    def prim(V, F, uv, material, wind, colour=None, N=None):
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
            at_["COLOR_0"] = acc(np.c_[c, c, c, np.ones(len(c))].astype(np.float32), "VEC4", 5126, 34962)
        return {"attributes": at_, "indices": acc(F.astype(np.uint32).ravel(), "SCALAR", 5125, 34963), "material": material}

    col = np.asarray(bark.get("color", [0.5, 0.45, 0.4]), float)
    base = np.clip(bm["albedo"][..., None] * col[None, None], 0, 1)  # (sRGB colour x a multiplier: near enough)
    orm = np.stack([np.ones_like(bm["rough"]), bm["rough"], np.zeros_like(bm["rough"])], -1)
    materials.append({"name": "bark", "pbrMetallicRoughness": {
        "baseColorTexture": {"index": tex(_png(base), True)},
        "metallicRoughnessTexture": {"index": tex(_png(orm), True)}},
        "normalTexture": {"index": tex(_png(bm["normal"]), True)}})
    M_BARK = 0

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
        mw["pbrMetallicRoughness"].update(baseColorFactor=[0.55, 0.53, 0.5, 1.0], roughnessFactor=0.5)
        materials.append(mw)
        var_bark["wet"] = len(materials) - 1
    variants = [v_ for v_ in seasons + (["wet"] if wet else []) if len(seasons) + bool(wet) > 1]

    def with_variants(p_, table, default):
        if variants and table:
            ext_used.add("KHR_materials_variants")
            by = {}
            for i_, v_ in enumerate(variants):
                by.setdefault(table.get(v_, default), []).append(i_)
            p_["extensions"] = {"KHR_materials_variants": {"mappings": [{"material": m_, "variants": vs} for m_, vs in by.items()]}}
        return p_

    M_IMP = None
    if impostor is not None:
        materials.append({"name": "impostor", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": tex(_png(impostor["image"]), False)}, "metallicFactor": 0.0, "roughnessFactor": 0.9},
            "alphaMode": "MASK", "alphaCutoff": 0.5, "doubleSided": True})
        M_IMP = len(materials) - 1
    per, roots = [], []
    cluster_mats = {}
    if spacing is None:
        spacing = 0.0 if len(trees) == 1 else 1.2 * max(float(np.percentile(np.linalg.norm(t["pos"][:, :2], axis=1), 98)) for t in trees) * 2
    n_lod = int(np.clip(lods, 1, len(LODS)))
    for k, (t, nm) in enumerate(zip(trees, names)):
        wn = wind_nodes(t)
        lod_nodes, lod_info = [], []
        for li in range(0 if only_impostor else n_lod):
            share, cap_ = LODS[li]
            cap_i = cap_ if n_lod > 1 or cap is None else cap
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
                ck = f"boughs{li}" if boughs else json.dumps(lf_c["card"], sort_keys=True)
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
                fn = L["node"]
                wch = (wn["trunk"][fn], wn["branch"][fn], wn["phase"][fn], L["flutter"])
                if t.get("clump"):  # a small plant's card bends as a whole from its foot, each in its own phase; long
                    # cards swing further (the recipe's limb amplitude is 0.25 m: a 30 cm tuft's tip moves ~5 cm)
                    own = L["flutter"] ** 1.5 * np.clip(L["reach"] / 1.2, 0.08, 1.0)
                    wch = (wn["trunk"][fn], np.maximum(wn["branch"][fn], own), np.where(wn["branch"][fn] > own, wn["phase"][fn], L["phase"]),
                           0.5 * L["flutter"])
                p_ = prim(L["V"], L["F"], L["uv"], m_c, wch,
                          L["tint"], L["N"])
                meshes.append({"name": pre + "foliage", "primitives": [with_variants(p_, vf_c, m_c)]})
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
        if impostor is not None and k == 0 and len(trees) == 1:
            S_, H_ = float(impostor["size"]), float(impostor["height"])
            Vq, Fq, Uq = [], [], []
            for j, (dx, dy) in enumerate(((1, 0), (0, 1))):  # the picture seen along +y, then the one seen along -x
                r_ = np.array([dx, dy, 0.0])
                q = np.array([-0.5 * S_ * r_ + [0, 0, H_ - 0.5 * S_], 0.5 * S_ * r_ + [0, 0, H_ - 0.5 * S_],
                              0.5 * S_ * r_ + [0, 0, H_ + 0.5 * S_], -0.5 * S_ * r_ + [0, 0, H_ + 0.5 * S_]])
                Vq.append(q)
                Fq.append(np.array([[0, 1, 2], [0, 2, 3]]) + 4 * j)
                Uq.append(np.array([[0, 0], [1, 0], [1, 1], [0, 1]]) * [0.5, 1] + [0.5 * j, 0])
            Vq, Fq, Uq = np.vstack(Vq), np.vstack(Fq), np.vstack(Uq)
            zt = np.clip(Vq[:, 2] / max(t["height"], 1e-6), 0, 1) ** 1.5
            up_ = np.tile([0, 0, 1.0], (len(Vq), 1))
            p_ = prim(Vq, Fq, Uq, M_IMP, (zt, np.zeros(8), np.zeros(8), np.zeros(8)), N=up_)
            meshes.append({"name": f"LOD{n_lod}_impostor", "primitives": [p_]})
            nodes.append({"name": f"{nm}_LOD{0 if only_impostor else n_lod}", "mesh": len(meshes) - 1})
            lod_nodes.append([len(nodes) - 1])
            lod_info.append({"name": nm, "lod": n_lod, "triangles": 4, "impostor": True})
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
        caps = [] if only_impostor else collision(t)
        c0["collision"] = [{"a": _yup(np.array([q["a"]]))[0].tolist(), "b": _yup(np.array([q["b"]]))[0].tolist(), "ra": q["ra"], "rb": q["rb"]}
                           for q in caps]
        if caps:
            thr = max(0.05, 0.3 * float(t["radius"][1]))
            C = veg_mesh.tubes(t, sides=(4, 5), min_radius=thr, simplify=1.5, collar=0, tile=tile)
            z4 = np.zeros(len(C["V"]))
            meshes.append({"name": f"{nm}_collision", "primitives": [prim(C["V"], C["F"], C["uv"], M_BARK, (z4, z4, z4, z4))]})
            nodes.append({"name": f"{nm}_collision", "mesh": len(meshes) - 1, "extras": {"collision": True}})
            c0["collision_node"] = len(nodes) - 1
            c0["collision_triangles"] = int(len(C["F"]))
        per.append(c0)
    counts = {"wood_triangles": sum(c["wood_triangles"] for c in per), "foliage_triangles": sum(c["foliage_triangles"] for c in per),
              "twigs_kept": per[0]["twigs_kept"], "wood_min_radius_m": per[0]["wood_min_radius_m"], "budget": triangles,
              "floating": max(c["floating"] for c in per), "lods": per[0]["lods"], "variants": variants,
              "collision_capsules": len(per[0]["collision"]), "collision_triangles": per[0].get("collision_triangles", 0)}
    if at is not None:
        counts["atlas_px"] = int(at["color"].shape[0])
    if len(trees) > 1:
        counts["plants"] = per
    name = names[0] if len(trees) == 1 else "set"
    while len(buf) % 4:
        buf.append(0)
    gltf = {"asset": {"version": "2.0", "generator": "hifipushie vegetation"},
            "scene": 0, "scenes": [{"nodes": roots}], "nodes": nodes, "meshes": meshes,
            "materials": materials, "textures": textures, "images": images,
            "samplers": [{"wrapS": 10497, "wrapT": 10497, "magFilter": 9729, "minFilter": 9987},
                         {"wrapS": 33071, "wrapT": 33071, "magFilter": 9729, "minFilter": 9987}],
            "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(buf)}],
            "extras": {"hifipushie_plant": {"name": name, "species": s.get("species"), "age": s.get("age"),
                                            "height_m": round(tree["height"], 2), "stats": tree["stats"],
                                            "set": len(trees) if len(trees) > 1 else None, "bark_tile_m": bm["tile"],
                                            "lods": [[{k_: v_ for k_, v_ in c.items()} for c in p_["lods"]] for p_ in per],
                                            "wind": WIND_RECIPE, "variants": variants,
                                            "snow": "engine shader: lerp base colour to snow by saturate(worldNormal.up * 2 - 0.6); "
                                                    "the `snow` variant only frosts the foliage picture",
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


def write_impostor(tree: dict, path: str, name: str, impostor: dict) -> str:
    """The impostor LOD alone, as a file of its own."""
    return write_glb(tree, path, name, impostor=impostor, only_impostor=True)["path"]
