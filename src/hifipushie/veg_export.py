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

from . import veg_bark, veg_leaf, veg_mesh, vegetation


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


def foliage_mesh(tree: dict, at: dict, keep: float = 1.0, min_radius: float = 0.0, protect=None) -> dict:
    """Every twig's card placed on the tree, as one mesh: V, F, uv, tint (per vertex). keep < 1: see pick_twigs."""
    tw = pick_twigs(tree, keep, min_radius, protect)[0]
    if not len(tw["pos"]):
        return {"V": np.zeros((0, 3)), "F": np.zeros((0, 3), int), "uv": np.zeros((0, 2)), "tint": np.zeros(0)}
    nv = len(at["cards"])
    var = (vegetation._child(tw["key"], 11) % np.uint64(nv)).astype(int)
    tint = 0.75 + 0.5 * vegetation._u(tw["key"], 77)
    Vs, Fs, Us, Ts = [], [], [], []
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
        base += len(sel) * k
    return {"V": np.vstack(Vs), "F": np.vstack(Fs), "uv": np.vstack(Us), "tint": np.concatenate(Ts)}


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


def pick_twigs(tree: dict, keep: float, min_radius: float = 0.0, protect=None, tw: dict | None = None) -> tuple[dict, float]:
    """The twigs a budget draws: `keep` of them, each larger by 1 / sqrt(keep). Those standing on drawn wood (or within
    a card's reach of it along the branch) go first: cards chosen by their hash alone were left floating round bare
    spars. Returns (twigs, the share of the kept ones farther than that from drawn wood)."""
    tw = veg_leaf.place(tree) if tw is None else tw
    n = len(tw["pos"])
    if not n or keep >= 1:
        return tw, 0.0
    grow = min(1.0 / np.sqrt(max(keep, 1e-6)), 2.5)
    ok = kept_wood(tree, min_radius, protect)
    par, P = tree["parent"], tree["pos"]
    seg = np.linalg.norm(P - P[par], axis=1)
    d = np.zeros(len(P))
    for i in range(2, len(P)):  # distance back along the branch to drawn wood (parents come first)
        d[i] = 0.0 if ok[i] else d[par[i]] + seg[i]
    lf = tree["spec"]["leaves"]
    reach = 0.6 * float((lf.get("card") or {}).get("twig", {}).get("length", (lf.get("twig") or {}).get("length", 0.3))) * grow
    far = d[tw["node"]] > reach
    rank = np.argsort(np.argsort(far.astype(float) + 0.999 * vegetation._u(tw["key"], 91)))
    sel = rank < int(np.floor(n * keep + 1e-9))  # (exactly that many: a threshold on the hash overshot budgets)
    out = {k: v[sel] for k, v in tw.items()}
    out["scale"] = out["scale"] * grow
    return out, float(far[sel].mean()) if sel.any() else 0.0


def budget(tree: dict, triangles: int | None, tile, card_triangles: int) -> dict:
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
            out["floating"] = pick_twigs(tree, out["keep"], out["min_radius"], pr, tw)[1]
        if out["floating"] <= 0.2 or out["min_radius"] == 0.0:
            break
    fol = int(np.floor(n_tw * out["keep"] + 1e-9)) * card_triangles
    out["total"] = int(len(out["wood"]["F"]) + fol)
    out["over"] = max(0, out["total"] - int(triangles)) if triangles else 0
    return out


def write_glb(tree, path: str, name="plant", triangles: int | None = None, spacing: float | None = None) -> dict:
    """Write the plant to `path` (.glb). Returns counts: triangles per mesh, texture sizes, bytes. `triangles` = a
    budget: thin wood is left out and branches get fewer sides until the wood fits half of it; twigs are thinned
    (the rest drawn larger) until the foliage fits the other half.
    A list of trees (and names) writes a SET: one file, one bark and one foliage material (the first tree's leaves
    and bark: a set is one species), a node per plant holding its wood and foliage, stood `spacing` m apart in a
    row along x (0 = all at the origin); the budget is each plant's own. Counts then carry "plants": [per plant]."""
    trees = tree if isinstance(tree, list) else [tree]
    names = name if isinstance(name, list) else [name]
    tree = trees[0]
    s = tree["spec"]
    bark = s.get("bark") or {}
    bm = veg_bark.bark_maps(bark.get("kind", "furrowed"), 256, seed=int(s.get("seed", 1)))
    sc = float(bark.get("scale", 1.0))
    tile = [bm["tile"][0] * sc, bm["tile"][1] * sc]
    has_leaves = any(len(veg_leaf.place(t)["pos"]) for t in trees)
    at = veg_leaf.atlas(s["leaves"], bark.get("twig_color") or [0.45, 0.4, 0.35]) if has_leaves else None
    buf = bytearray()
    views, accessors, images, textures, materials, meshes, nodes = [], [], [], [], [], [], []

    def view(data: bytes, target=None):
        while len(buf) % 4:
            buf.append(0)
        v = {"buffer": 0, "byteOffset": len(buf), "byteLength": len(data)}
        if target:
            v["target"] = target
        buf.extend(data)
        views.append(v)
        return len(views) - 1

    def acc(a, kind, comp, target, minmax=False, normalized=False):
        a = np.ascontiguousarray(a)
        d = {"bufferView": view(a.tobytes(), target), "componentType": comp, "count": int(len(a)), "type": kind}
        if minmax:
            d["min"], d["max"] = a.min(0).astype(float).tolist(), a.max(0).astype(float).tolist()
        if normalized:
            d["normalized"] = True
        accessors.append(d)
        return len(accessors) - 1

    def tex(png: bytes, repeat: bool):
        images.append({"bufferView": view(png), "mimeType": "image/png"})
        textures.append({"source": len(images) - 1, "sampler": 0 if repeat else 1})
        return len(textures) - 1

    def prim(V, F, uv, material, colour=None):
        N = _normals(V, F)
        at_ = {"POSITION": acc(_yup(V).astype(np.float32), "VEC3", 5126, 34962, minmax=True),
               "NORMAL": acc(_yup(N).astype(np.float32), "VEC3", 5126, 34962),
               "TEXCOORD_0": acc(np.c_[uv[:, 0], 1 - uv[:, 1]].astype(np.float32), "VEC2", 5126, 34962)}
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
    if at is not None:
        m = at["mask"]
        orm = np.stack([np.ones_like(m[..., 1]), m[..., 1], np.zeros_like(m[..., 1])], -1)
        materials.append({"name": "foliage", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": tex(_png(at["color"]), False)},
            "metallicRoughnessTexture": {"index": tex(_png(orm), False)}},
            "normalTexture": {"index": tex(_png(at["normal"]), False)},
            "alphaMode": "MASK", "alphaCutoff": 0.4, "doubleSided": True,
            "extras": {"mask_texture": "R = light comes through (leaf), G = roughness, B = shade",
                       "card_fill": round(at["fill"], 3)}})
        materials[-1]["extras"]["mask_texture_index"] = tex(_png(at["mask"]), False)
    per, roots = [], []
    if spacing is None:
        spacing = 0.0 if len(trees) == 1 else 1.2 * max(float(np.percentile(np.linalg.norm(t["pos"][:, :2], axis=1), 98)) for t in trees) * 2
    for k, (t, nm) in enumerate(zip(trees, names)):
        bud = budget(t, triangles, tile, at["triangles"] if at else 0)
        W = bud["wood"]
        L = foliage_mesh(t, at, bud["keep"], bud["min_radius"], bud["protect"]) if at and len(veg_leaf.place(t)["pos"]) else None
        pre = "" if len(trees) == 1 else f"{nm}_"
        kids = []
        meshes.append({"name": pre + "wood", "primitives": [prim(W["V"], W["F"], W["uv"], 0)]})
        nodes.append({"name": pre + "wood", "mesh": len(meshes) - 1})
        kids.append(len(nodes) - 1)
        c = {"name": nm, "height_m": round(t["height"], 2), "wood_triangles": int(len(W["F"])), "foliage_triangles": 0,
             "twigs_kept": round(bud["keep"], 3), "wood_min_radius_m": round(bud["min_radius"], 4),
             "floating": round(bud["floating"], 3)}
        if L is not None and len(L["F"]):
            meshes.append({"name": pre + "foliage", "primitives": [prim(L["V"], L["F"], L["uv"], 1, L["tint"])]})
            nodes.append({"name": pre + "foliage", "mesh": len(meshes) - 1})
            kids.append(len(nodes) - 1)
            c["foliage_triangles"] = int(len(L["F"]))
        if len(trees) == 1:
            roots = kids
        else:
            nodes.append({"name": nm, "children": kids, "translation": [float((k - (len(trees) - 1) / 2) * spacing), 0.0, 0.0],
                          "extras": {"height_m": c["height_m"], "seed": t["spec"].get("seed"), "age": t["spec"].get("age")}})
            roots.append(len(nodes) - 1)
        per.append(c)
    counts = {"wood_triangles": sum(c["wood_triangles"] for c in per), "foliage_triangles": sum(c["foliage_triangles"] for c in per),
              "twigs_kept": per[0]["twigs_kept"], "wood_min_radius_m": per[0]["wood_min_radius_m"], "budget": triangles,
              "floating": max(c["floating"] for c in per)}
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
                                            "height_m": round(tree["height"], 2), "stats": tree["stats"], **counts, "set": len(trees) if len(trees) > 1 else None,
                                            "bark_tile_m": bm["tile"], "lods": 1, "wind": None}}}
    js = json.dumps(gltf, separators=(",", ":")).encode()
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
