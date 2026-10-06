"""Plants and the ground they stand on: nothing a plant draws may lie under it.

The ground is `vegetation.ground_at` (environment.ground: level, slope). Three things can go under it: wood (limbs that
droop or sag into it), cards (a card is a polygon round its anchor: an anchor above the ground says nothing about its
corners; a hanging card reaches its whole length below its anchor) and bough cards (metres long). `audit` measures what
a look or an export of the plant DRAWS (the same wood mesh, placements and cards), `audit_glb` an exported file, and
`clear` makes a set of card placements stand clear: turned up, shortened, or left out.
"""
from __future__ import annotations

import json
import math
import struct

import numpy as np

from . import vegetation

MARGIN = 0.01  # m: nearer the ground than this counts as on it


def _world(tw: dict, cards: list, var: np.ndarray):
    """Every placement's card vertices in the plant's frame: [(indices into tw, (n, k, 3))] per card variant."""
    out = []
    for i, c in enumerate(cards):
        sel = np.flatnonzero(var == i)
        if len(sel):
            V = np.einsum("nij,kj->nki", tw["frame"][sel], c["V"]) * tw["scale"][sel][:, None, None] + tw["pos"][sel][:, None, :]
            out.append((sel, V))
    return out


def lowest(spec: dict, tw: dict, cards: list, var: np.ndarray) -> np.ndarray:
    """Per placement: its lowest card vertex's height over the ground (m; negative = under it)."""
    low = np.full(len(tw["pos"]), np.inf)
    for sel, V in _world(tw, cards, var):
        g = vegetation.ground_at(spec, V.reshape(-1, 3)[:, :2]).reshape(V.shape[:2])
        low[sel] = (V[:, :, 2] - g).min(1)
    return low


def floor_of(spec: dict) -> float:
    """How far over the ground a plant's foliage ends (m): `leaves.clear` (a browse or mowing line under hanging
    curtains; default 3 cm, a clump's cards 0: they stand on the ground)."""
    return float((spec.get("leaves") or {}).get("clear", 0.03))


def clear(spec: dict, tw: dict, cards: list, var: np.ndarray, floor: float | None = None, stats: dict | None = None) -> dict:
    """The placements with no card vertex under `floor` m over the ground. A card that would reach under it is, in
    this order: turned up about its foot (a twig lying on the ground turns its end up, as far as 50 deg; a hanging
    one is not turned: that would stand a curtain on its head), shortened (to no less than `SHORT` of its size: the
    shoot ends higher), or left out. Placements keep their keys; `stats` gets counts {"turned", "shortened", "dropped"}."""
    n = len(tw["pos"])
    st = {"turned": 0, "shortened": 0, "dropped": 0}
    if stats is not None:
        stats.update(st)
    if not n or not cards:
        return tw
    floor = floor_of(spec) if floor is None else float(floor)
    low = lowest(spec, tw, cards, var) - floor
    bad = np.flatnonzero(low < 0)
    if not len(bad):
        return tw
    tw = {**tw, "pos": tw["pos"].copy(), "frame": tw["frame"].copy(), "scale": tw["scale"].copy()}
    up = np.array([0, 0, 1.0])

    def sub(idx):
        return {"pos": tw["pos"][idx], "frame": tw["frame"][idx], "scale": tw["scale"][idx]}

    def low_of(idx, fr=None, sc=None):
        t_ = sub(idx)
        if fr is not None:
            t_["frame"] = fr
        if sc is not None:
            t_["scale"] = sc
        return lowest(spec, t_, cards, var[idx]) - floor

    # 1. turn it up about its foot: flat (upper side to the sky), its run raised step by step
    d = tw["frame"][bad][:, :, 1]
    turn = d[:, 2] > -0.5  # (hanging cards are shortened instead)
    idx = bad[turn]
    left = np.ones(len(idx), bool)
    if len(idx):
        hz = tw["frame"][idx][:, :, 1] * [1, 1, 0]
        nz = np.linalg.norm(hz, axis=1) < 1e-6
        hz[nz] = [1.0, 0, 0]
        hz /= np.linalg.norm(hz, axis=1, keepdims=True)
        el0 = np.degrees(np.arcsin(np.clip(tw["frame"][idx][:, 2, 1], -1, 1)))
        for el in (0.0, 10.0, 20.0, 35.0, 50.0):
            e = np.radians(np.maximum(el0, el))
            dd = hz * np.cos(e)[:, None] + up[None] * np.sin(e)[:, None]
            zz = up[None] - dd * dd[:, 2:3]
            zz /= np.maximum(np.linalg.norm(zz, axis=1, keepdims=True), 1e-9)
            fr = np.stack([np.cross(dd, zz), dd, zz], axis=2)
            ok = left & (low_of(idx, fr=fr) >= 0)
            tw["frame"][idx[ok]] = fr[ok]
            st["turned"] += int(ok.sum())
            left &= ~ok
            if not left.any():
                break
            if el == 50.0:  # (still under: it keeps the steepest turn for the next step)
                tw["frame"][idx[left]] = fr[left]
    # 2. shorten it
    rest = np.concatenate([bad[~turn], idx[left]])
    drop = np.zeros(n, bool)
    if len(rest):
        ok_any = np.zeros(len(rest), bool)
        for f in (0.85, 0.7, 0.55, SHORT):
            sc = tw["scale"][rest] * f
            ok = ~ok_any & (low_of(rest, sc=sc) >= 0)
            tw["scale"][rest[ok]] = sc[ok]
            ok_any |= ok
        st["shortened"] += int(ok_any.sum())
        drop[rest[~ok_any]] = True  # 3. or it isn't there
        st["dropped"] += int((~ok_any).sum())
    if drop.any():
        keep = ~drop
        tw = {k: (v[keep] if isinstance(v, np.ndarray) and len(v) == n else v) for k, v in tw.items()}
    if stats is not None:
        stats.update(st)
    return tw


SHORT = 0.4


def _measure(depth: np.ndarray, owner: np.ndarray | None = None) -> dict:
    """depth = height over the ground per vertex (m). Counts of vertices under it and how deep (mm)."""
    under = depth < -MARGIN * 0.1
    d = -depth[under]
    out = {"vertices": int(len(depth)), "under": int(under.sum()),
           "p50_mm": round(float(np.median(d)) * 1000, 1) if len(d) else 0.0,
           "max_mm": round(float(d.max()) * 1000, 1) if len(d) else 0.0}
    if owner is not None:
        out["cards"] = int(len(np.unique(owner)))
        out["cards_under"] = int(len(np.unique(owner[under])))
    return out


def wood_depth(tree: dict, W: dict) -> tuple[np.ndarray, np.ndarray]:
    """(height over the ground per wood vertex, which of them are the trunk's own foot: the trunk is drawn into the
    ground on purpose, so a foot on a slope shows no gap)."""
    spec = tree["spec"]
    V = W["V"]
    depth = V[:, 2] - vegetation.ground_at(spec, V[:, :2])
    node = np.asarray(W.get("node", np.zeros(len(V), int)))
    order = tree["order"][np.clip(node, 0, len(tree["order"]) - 1)]
    free = tree.get("free")
    foot = (order == 0) & (tree["pos"][np.clip(node, 0, len(tree["pos"]) - 1), 2] - vegetation.ground_at(spec, tree["pos"][np.clip(node, 0, len(tree["pos"]) - 1), :2]) < 1.0)
    if free is not None:  # a clump's stalks each stand on the ground by themselves
        foot |= True
    return depth, foot


def drawn(tree: dict, triangles: int | None = None) -> dict:
    """What a look or an export of the plant draws at a budget: {"wood": mesh, "tw": placements, "cards", "var",
    "boughs": bool, "leaves"} (the same calls as veg_look and veg_export.write_glb's LOD 0)."""
    from . import veg_bark, veg_bough, veg_export, veg_leaf, veg_mesh
    s = tree["spec"]
    lf = s["leaves"]
    bark = s.get("bark") or {}
    bm = veg_bark.bark_maps(bark.get("kind", "furrowed"), 256, seed=int(s.get("seed", 1)))
    sc = float(bark.get("scale", 1.0))
    tile = [bm["tile"][0] * sc, bm["tile"][1] * sc]
    twc = bark.get("twig_color") or [0.45, 0.4, 0.35]
    tw = veg_leaf.place(tree)
    out = {"wood": veg_mesh.tubes(tree, tile=tile), "tw": tw, "cards": [], "var": np.zeros(0, int), "boughs": False, "leaves": lf}
    if not len(tw["pos"]):
        return out
    at = veg_leaf.atlas(lf, twc)
    if triangles:
        bud = veg_export.budget(tree, triangles, tile, at["triangles"])
        out["wood"] = bud["wood"]
        if bud.get("boughs"):
            at = veg_bough.atlas(tree, lf, twc, bud["boughs"])
            tw = veg_bough.place(tree, bud["boughs"], at)
            out["boughs"] = True
        else:
            lf, cap_c, back_c = veg_export.cluster_leaves(lf, bud["keep"])
            if lf is not s["leaves"]:
                at = veg_leaf.atlas(lf, twc)
            tw = veg_export.pick_twigs(tree, bud["keep"], bud["min_radius"], bud["protect"], tw, cap=cap_c, back=back_c)[0]
    var = veg_leaf.card_variant(tw, len(at["cards"]))
    st = {}
    tw = clear(s, tw, at["cards"], var, stats=st) if CLEAR and not tree.get("clump") else tw
    out["cleared"] = st
    out.update(tw=tw, cards=at["cards"], var=veg_leaf.card_variant(tw, len(at["cards"])), leaves=lf)
    return out


CLEAR = True  # (False: placements as they were before `clear` existed; for before / after measurements only)


def audit(tree: dict, triangles: int | None = None, d: dict | None = None) -> dict:
    """Where the drawn plant stands against its ground: {"wood": {vertices, under, p50_mm, max_mm}, "foot": the
    trunk's own foot under the ground (by design), "cards": {..., cards, cards_under}, "anchors": card anchors under
    the ground, "boughs": bool, "lowest_wood_m", "lowest_card_m"}."""
    d = d or drawn(tree, triangles)
    s = tree["spec"]
    depth, foot = wood_depth(tree, d["wood"])
    out = {"triangles": triangles, "wood": _measure(depth[~foot]), "foot": _measure(depth[foot]), "boughs": bool(d["boughs"]),
           "lowest_wood_m": round(float(depth[~foot].min()), 3) if (~foot).any() else None, "cleared": d.get("cleared") or {},
           "height_m": round(float(tree["height"]), 2)}
    P, par = tree["pos"], tree["parent"]
    rest = (tree["order"] > 0) & (P[:, 2] - vegetation.ground_at(s, P[:, :2]) - tree["radius"] < 0.06)
    out["resting_m"] = round(float(np.linalg.norm(P - P[par], axis=1)[rest].sum()), 1)  # wood lying on the ground
    tw = d["tw"]
    if len(tw["pos"]) and d["cards"]:
        deps, own = [], []
        for sel, V in _world(tw, d["cards"], d["var"]):
            g = vegetation.ground_at(s, V.reshape(-1, 3)[:, :2])
            deps.append(V.reshape(-1, 3)[:, 2] - g)
            own.append(np.repeat(sel, V.shape[1]))
        dep, own = np.concatenate(deps), np.concatenate(own)
        out["cards"] = _measure(dep, own)
        out["anchors"] = int((tw["pos"][:, 2] - vegetation.ground_at(s, tw["pos"][:, :2]) < -1e-4).sum())
        out["lowest_card_m"] = round(float(dep.min()), 3)
        out["cards_within_30cm"] = int(len(np.unique(own[dep < 0.3])))
    else:
        out["cards"] = _measure(np.zeros(0), np.zeros(0, int))
        out["anchors"] = 0
    return out


def audit_glb(path: str, spec: dict | None = None, trunk_radius: float | None = None) -> dict:
    """The same count on an exported GLB, as an engine gets it: per mesh (wood / foliage, by name) the vertices under
    the ground (glTF is Y up; a node's translation is applied). Wood within 2.5 trunk radii of its plant's foot, less
    than a metre up, is the trunk's own foot."""
    raw = open(path, "rb").read()
    jl = struct.unpack("<I", raw[12:16])[0]
    G = json.loads(raw[20:20 + jl])
    binp = raw[20 + jl + 8:]
    out = {}

    def positions(mesh):
        Vs = []
        for p in mesh["primitives"]:
            a = G["accessors"][p["attributes"]["POSITION"]]
            bv = G["bufferViews"][a["bufferView"]]
            Vs.append(np.frombuffer(binp, np.float32, a["count"] * 3, bv.get("byteOffset", 0) + a.get("byteOffset", 0)).reshape(-1, 3))
        return np.vstack(Vs)

    parent = {}
    for i, nd in enumerate(G["nodes"]):
        for c in nd.get("children", []):
            parent[c] = i

    def offset(i):
        t = np.zeros(3)
        while i is not None:
            t += np.asarray(G["nodes"][i].get("translation", [0, 0, 0]), float)
            i = parent.get(i)
        return t

    for i, nd in enumerate(G["nodes"]):
        if "mesh" not in nd:
            continue
        name = nd.get("name", "")
        kind = "wood" if "wood" in name else "foliage" if "foliage" in name else None
        if kind is None:
            continue
        V = positions(G["meshes"][nd["mesh"]]).astype(float)
        zup = np.c_[V[:, 0], -V[:, 2], V[:, 1]]  # in the plant's own frame (the node's offset only stands it in a set)
        depth = zup[:, 2] - (vegetation.ground_at(spec, zup[:, :2]) if spec else 0.0)
        if kind == "wood":
            r = trunk_radius if trunk_radius is not None else 0.5
            foot = (np.hypot(zup[:, 0], zup[:, 1]) < 2.5 * r) & (zup[:, 2] < 1.0)
            out[name] = {**_measure(depth[~foot]), "foot_under": int((depth[foot] < 0).sum())}
        else:
            out[name] = _measure(depth)
        out[name]["lowest_m"] = round(float(depth.min()), 3)
    return out


def line(a: dict) -> str:
    """One audit as a line of text."""
    w, c = a["wood"], a["cards"]
    return (f"wood {w['under']}/{w['vertices']} under (p50 {w['p50_mm']} mm, max {w['max_mm']} mm), foot {a['foot']['under']} by design; "
            f"{'bough' if a['boughs'] else 'twig'} cards {c.get('cards_under', 0)}/{c.get('cards', 0)} reach under "
            f"({c['under']} vertices, p50 {c['p50_mm']} mm, max {c['max_mm']} mm), anchors under {a['anchors']}")


def report(a: dict) -> list[str]:
    """An audit as report lines; a WARNING for anything drawn under the ground (the trunk's own foot is not)."""
    w, c, cl = a["wood"], a["cards"], a.get("cleared") or {}
    what = f"at {a['triangles']} triangles" if a.get("triangles") else "at full detail"
    out = [f"ground ({what}): lowest limb wood {a['lowest_wood_m']} m and lowest card corner {a.get('lowest_card_m', '-')} m over it; "
           f"{a['resting_m']} m of limbs rest on it; of {c.get('cards', 0)} {'bough' if a['boughs'] else 'twig'} cards "
           f"{cl.get('turned', 0)} were turned up, {cl.get('shortened', 0)} shortened and {cl.get('dropped', 0)} left out to stay over it"]
    if w["under"]:
        out.append(f"WARNING: {w['under']} wood vertices are under the ground (deepest {w['max_mm']} mm, median {w['p50_mm']} mm): "
                   f"limbs, not the trunk's foot")
    if c["under"]:
        out.append(f"WARNING: {c.get('cards_under', 0)} cards reach under the ground ({c['under']} vertices, deepest {c['max_mm']} mm, "
                   f"median {c['p50_mm']} mm)")
    if a["resting_m"] > 0.25 * a["height_m"]:
        out.append(f"WARNING: {a['resting_m']} m of limbs lie on the ground (the tree is {a['height_m']} m tall): raise `habit.clear` "
                   f"(bare trunk), lower `habit.sag`, or prune {{\"below\": m}}")
    return out
