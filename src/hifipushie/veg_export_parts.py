"""What goes into a plant's GLB: wind nodes, the foliage mesh, kept wood and twigs, budgets, the season atlas,
collision, snow numbers, impostor frames and maps. Part of the plant export (veg_export.py has the contract)."""
from __future__ import annotations

import math

import numpy as np

from . import veg_export
from . import veg_bough, veg_ground, veg_leaf, veg_mesh, veg_style
from . import vegetation_kernels, vegetation_tree

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
            "phase": np.where(order > 0, vegetation_kernels._u(tree["key"][limb], 55), 0.0)}


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
    tint = 0.75 + 0.5 * vegetation_kernels._u(tw["key"], 77)
    if "size_m" in tw:  # bough cards are big: a tone per card as wide as a twig's read as a crown of pale and dark leaves
        tint = 0.88 + 0.24 * vegetation_kernels._u(tw["key"], 77)
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
            Ts.append((tint[sel][:, None] * (1.0 - veg_export.CORE_DARK * core[sel][:, None] * np.clip(1.0 - fl_[None] / 0.7, 0, 1) ** 1.2)).ravel())
        else:
            Ts.append(np.repeat(tint[sel], k))
        Ns.append(np.repeat(tw["node"][sel], k))
        Fl.append(np.tile(np.clip(c["V"][:, 1] / max(float(c["V"][:, 1].max()), 1e-6), 0, 1), len(sel)))
        Nr.append(np.repeat(tw["frame"][sel][:, :, 2], k, axis=0))  # the card's own upper side
        Rc.append(np.repeat(tw["scale"][sel] * float(c["V"][:, 1].max()), k))  # how long the card is, m
        Ph.append(np.repeat(vegetation_kernels._u(tw["key"][sel], 56), k))
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
        h_ = vegetation_kernels._u(tw["key"], 91)
        order_ = np.lexsort((h_, cid))
        within = np.empty(n, np.int64)
        start = np.r_[0, np.flatnonzero(np.diff(cid[order_])) + 1]
        within[order_] = np.arange(n) - np.repeat(start, np.diff(np.r_[start, n]))
        rank = np.argsort(np.argsort(within + 0.999 * h_))
        far = far & False
    else:
        rank = np.argsort(np.argsort(far.astype(float) + 0.999 * vegetation_kernels._u(tw["key"], 91)))
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
        return make({**lf, "color": lf.get("autumn", veg_export.AUTUMN)}, twig_color)
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
    roots_ = [1] + [tree["axes"][L["axis"]]["node"] for L in vegetation_tree.limbs(tree, 40, 0.0) if 0.5 * L["diameter"] >= thr]
    for n0 in roots_:
        nodes = vegetation_tree.stout_path(tree, n0, kids)
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


def snow_numbers(spec: dict, st: dict | None) -> dict:
    """Snow as numbers for an engine's own shader (the ready-mixed `snow` variant stays): where our looks lay it and how
    the variant's colour was made."""
    c = veg_export.SNOW["coverage"]
    sn = ((st or {}).get("seasons") or {}).get("snow") or {"mix": [0.93, 0.95, 0.98], "amount": 0.7}
    return {"color_linear": veg_export.SNOW["color"], "coverage": c,
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
    for az in veg_export.IMPOSTOR_AZIMUTHS:
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
    k = veg_export.IMPOSTOR["shade"] if shade_amount is None else float(shade_amount)
    dz = veg_export.IMPOSTOR["depth"] if depth is None else float(depth)
    ims, nms = [], []
    for (right, out), A, Nw, Sh in zip(impostor_frames(), albedo, normal, shade):
        solid = A[..., 3] > 0.5
        got = Sh[..., 3] > 0.05
        sh = ndimage.gaussian_filter(_bleed(np.where(got, Sh[..., 0], 1.0), got), 1.2)  # (12 samples a pixel: noisy)
        # bright colours take less of it: at full strength autumn's clean orange came out with brown patches (shade on
        # a bright saturated colour reads as dirt; on a dark green as depth). By the pixel's own value (sRGB max).
        val = np.clip((A[..., :3].max(-1) - 0.35) / 0.5, 0, 1)
        kk = k * (1 - veg_export.IMPOSTOR.get("shade_bright", 0.7) * val * val * (3 - 2 * val))
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
