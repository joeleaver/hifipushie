"""Twigs on a tree: where dead and live twigs go, and the parts they make. Part of the leaves, twigs and their cards (veg_leaf.py has the overview)."""
from __future__ import annotations

import math

import numpy as np

from . import veg_leaf
from .vegetation_kernels import _child, _u
from .vegetation_tree import _norm
from .veg_leaf_atlas import part_cards, part_specs

def dead_part(leaves: dict):
    """The spec of the atlas part that draws dead twigs (`leaves.parts.dead`), or None."""
    return part_specs(leaves).get("dead") if (leaves.get("parts") or {}).get("dead") is not None else None


def place_dead(tree: dict) -> dict | None:
    """Dead twig cards along the wood the shade killed (`tree["shade_dead"]`): the fine haze of bare twigs no tube can
    draw (a 2 mm twig is under a pixel from anywhere; a stand's dead zone is thousands of them). Placements like
    `place`'s, hanging; None when the plant has no dead part or no such wood."""
    lf = tree["spec"]["leaves"]
    dp = dead_part(lf)
    sd = tree.get("shade_dead")
    if dp is None or sd is None or not sd.any():
        return None
    tw = {**veg_leaf.TWIG, **(dp.get("twig") or {})}
    P, par = tree["pos"], tree["parent"]
    src = np.flatnonzero(sd & (tree["radius"] < float(dp.get("max_radius", 0.03))))
    seg = np.linalg.norm(P[src] - P[par[src]], axis=1)
    cnt = np.floor(seg * tw["per_m"] + _u(tree["key"][src], 141)).astype(int)
    rep = np.repeat(src, cnt)
    if not len(rep):
        return None
    j = np.concatenate([np.arange(c) for c in cnt])
    k = _child(tree["key"][rep], 1901 + j)
    t = (j + _u(k, 1)) / np.maximum(np.repeat(cnt, cnt), 1)
    a = _norm(P[rep] - P[par[rep]])
    up = np.array([0, 0, 1.0])
    ref = np.where(np.abs(a[:, 2:3]) > 0.95, np.array([[1.0, 0, 0]]), up[None])
    u = _norm(np.cross(a, ref))
    side = np.where(_u(k, 2) < 0.5, -1.0, 1.0)[:, None]
    sp = np.radians(tw["spread"] * (0.6 + 0.8 * _u(k, 3)))[:, None]
    d = _norm(a * np.cos(sp) + side * u * np.sin(sp) + tw["up"] * up + (np.stack([_u(k, 5), _u(k, 6), _u(k, 7)], 1) - 0.5) * 0.5)
    z = up[None] - d * d[:, 2:3]
    bad = np.linalg.norm(z, axis=1) < 1e-4
    z[bad] = np.array([1.0, 0, 0]) - d[bad] * d[bad][:, :1]
    z = _norm(z)
    x = np.cross(d, z)
    roll = math.pi * (2 * _u(k, 12) - 1) * 0.6
    c_, s_ = np.cos(roll)[:, None], np.sin(roll)[:, None]
    x, z = x * c_ + z * s_, z * c_ - x * s_
    lo, hi = tw["scale"]
    return {"pos": P[par[rep]] + (P[rep] - P[par[rep]]) * t[:, None], "frame": np.stack([x, d, z], axis=2),
            "scale": lo + (hi - lo) * _u(k, 8), "variant": np.zeros(len(rep), int), "node": rep, "key": k}


def place(tree: dict) -> dict:
    """Every card placement of a grown tree: its twigs (`place_live`) and, where the shade killed limbs and the leaves
    spec has a `parts.dead` picture, dead twig cards on them. With a dead part, placements carry `card` (the atlas
    card each draws) and `part` (0 foliage, 1 dead)."""
    if tree.get("twigs") is not None:  # a plant assembled from parts (veg_small) knows where its cards stand
        return tree["twigs"]
    live = place_live(tree)
    lf = tree["spec"]["leaves"]
    if dead_part(lf) is None:
        return live
    pc = part_cards(lf)
    main, dc = np.asarray(pc["main"]), np.asarray(pc["dead"])
    out = dict(live)
    out["card"] = main[(_child(live["key"], 11) % np.uint64(len(main))).astype(int)] if len(live["pos"]) else np.zeros(0, int)
    out["part"] = np.zeros(len(live["pos"]), int)
    dd = place_dead(tree) if tree["spec"].get("season") not in ("dead",) else None
    if dd is None:
        return out
    dd["card"] = dc[(_child(dd["key"], 11) % np.uint64(len(dc))).astype(int)]
    dd["part"] = np.ones(len(dd["pos"]), int)
    return {k_: (np.concatenate([out[k_], dd[k_]]) if k_ != "frame" else np.vstack([out[k_], dd[k_]])) for k_ in out}


def place_live(tree: dict) -> dict:
    """Twig instances on a grown tree: pos, frames (3x3: x, y = the twig's run, z = its upper side), scale, variant,
    node, key. A twig ends every leafy shoot; more stand along leafy shoots (`twig.per_m`, turned by the golden angle,
    leaning out by `spread` and up to the light by `up`); `where: "ends"` keeps them to the shoot ends (pines)."""
    s = tree["spec"]
    lf = s["leaves"]
    tw = {**veg_leaf.TWIG, **(lf.get("twig") or {})}
    P, par = tree["pos"], tree["parent"]
    n = len(P)
    empty = {"pos": np.zeros((0, 3)), "frame": np.zeros((0, 3, 3)), "scale": np.zeros(0), "variant": np.zeros(0, int),
             "node": np.zeros(0, int), "key": np.zeros(0, np.uint64)}
    evergreen = bool(lf.get("evergreen", str(lf.get("shape", "")).startswith("needle")))
    if s.get("season") in ("bare", "dead") or (s.get("season") == "winter" and not evergreen) or s.get("decay") or n < 3:
        return empty
    steps_ = tw["steps"]
    if lf.get("retention"):  # years a shoot keeps its leaves (needles: spruce 4-10, Scots pine 2-6)
        steps_ = max(1, int(math.ceil(float(lf["retention"]) / float(s["habit"]["years_per_step"]))))
    leafy = (tree["steps"] - 1 - tree["born"]) < steps_  # shoots this young carry twigs
    leafy[:2] = False
    if tree.get("dead") is not None:  # dead wood carries nothing, however lately it grew
        leafy &= ~tree["dead"]
    ends = tree["ends"] & (tree["leafy"] | leafy)
    d_node = _norm(P - P[par])
    up = np.array([0, 0, 1.0])
    pos, dirs, node, key = [P[ends]], [d_node[ends]], [np.flatnonzero(ends)], [_child(tree["key"][ends], 900)]
    if tw["where"] == "ends":
        src = np.flatnonzero(ends)
    else:
        src = np.flatnonzero(leafy & (tree["order"] >= tw["min_order"]))
    if len(src) and tw["per_m"] > 0:
        seg = np.linalg.norm(P[src] - P[par[src]], axis=1)
        want = seg * tw["per_m"]
        cnt = np.floor(want + _u(tree["key"][src], 41)).astype(int)
        rep = np.repeat(src, cnt)
        j = np.concatenate([np.arange(c) for c in cnt]) if len(rep) else np.zeros(0, int)
        k = _child(tree["key"][rep], 901 + j)
        t = (j + _u(k, 1)) / np.maximum(np.repeat(cnt, cnt), 1)
        a = d_node[rep]
        ref = np.where(np.abs(a[:, 2:3]) > 0.95, np.array([[1.0, 0, 0]]), up[None])
        u = _norm(np.cross(a, ref))
        w = np.cross(u, a)
        phi = 2.399963 * j + 6.283 * _u(tree["key"][rep], 42)
        out = u * np.cos(phi)[:, None] + w * np.sin(phi)[:, None]
        sp = math.radians(tw["spread"])
        d = _norm(a * math.cos(sp) + out * math.sin(sp) + tw["up"] * up)
        pos.append(P[par[rep]] + (P[rep] - P[par[rep]]) * t[:, None])
        dirs.append(d)
        node.append(rep)
        key.append(k)
    pos, dirs, node, key = np.vstack(pos), np.vstack(dirs), np.concatenate(node), np.concatenate(key)
    d = _norm(dirs + (np.stack([_u(key, 5), _u(key, 6), _u(key, 7)], 1) - 0.5) * 0.35)
    z = up[None] - d * d[:, 2:3]
    bad = np.linalg.norm(z, axis=1) < 1e-4
    z[bad] = np.array([1.0, 0, 0]) - d[bad] * d[bad][:, :1]
    z = _norm(z)
    x = np.cross(d, z)
    if tw["face"] < 1:  # rolled round its own run: not every twig lies flat with its upper side to the sky
        roll = (1 - float(tw["face"])) * math.pi * (2 * _u(key, 12) - 1)
        c_, s_ = np.cos(roll)[:, None], np.sin(roll)[:, None]
        x, z = x * c_ + z * s_, z * c_ - x * s_
    lo, hi = tw["scale"]
    sc_ = lo + (hi - lo) * _u(key, 8)
    from .vegetation_tree import ground_at
    gz = ground_at(s, pos[:, :2]) + 0.04
    pos[:, 2] = np.maximum(pos[:, 2], gz)
    need = (gz - pos[:, 2]) / np.maximum(tw["length"] * sc_, 1e-6)  # the least rise of its run that keeps its tip above
    under = d[:, 2] < need
    if under.any():
        dz = np.minimum(need[under], 0.0)
        hz = _norm(d[under] * [1, 1, 0] + 1e-9)
        d[under] = hz * np.sqrt(np.maximum(1 - dz ** 2, 0))[:, None] + np.array([0, 0, 1.0]) * dz[:, None]
        zz = up[None] - d[under] * d[under][:, 2:3]
        z[under] = _norm(zz)
        x[under] = np.cross(d[under], z[under])
    return {"pos": pos, "frame": np.stack([x, d, z], axis=2), "scale": sc_,
            "variant": (_child(key, 9) % np.uint64(int(tw["variants"]))).astype(int), "node": node, "key": key}
