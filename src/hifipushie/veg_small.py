"""Small plants the way game foliage artists build them: not grown, ASSEMBLED. A grass tuft, a fern, a flower, a
palm crown is a handful of pictures (a fan of blades, a frond, a flowering stalk: the atlas, `leaves` + `leaves.parts`)
cut onto cards and arranged in layers round a foot: rings of cards standing, leaning or lying, some on stalks, some on
a trunk's top. `spec["clump"]["layers"]` says how; `grow` returns the same dict a grown tree has (a small skeleton:
the stalks; `twigs`: where every card stands), so looks, budgets, LODs, wind and the export are the tree's own.

Sources for the practice (see vegetation_guide.md): polycount's foliage threads (cards in clumps, normals pointing up
or taken from a dome so a clump shades as one volume), Guerrilla's Horizon Zero Dawn talks (few assets per ecotope,
placed by density maps), Sucker Punch's Ghost of Tsushima grass (clumps share height and lean; wind by height)."""
from __future__ import annotations

import math
import time

import numpy as np

from . import veg_leaf
from .vegetation import _child, _mix, _u

LAYER = {"part": "main", "count": 12, "ring": [0.0, 0.1], "lean": [0, 25], "scale": [0.8, 1.2], "stem": [0.0, 0.0],
         "stem_radius": 0.004, "bend": 0.3, "facing": "auto", "on": None, "along": [1.0, 1.0], "turn": 0.0,
         "trunk": False, "segments": 0, "sink": 0.02, "tilt": 0.0}
LAYER_INFO = {
    "part": '"main" (the plant\'s `leaves`) or a name in `leaves.parts`: which picture this layer\'s cards show',
    "count": "cards (and stalks) in the layer",
    "ring": "[m, m] from the plant's middle: where they stand (a tuft [0, 0.05]; a patch [0, 0.5])",
    "lean": "[deg, deg] off upright, outward: 0-25 a standing tuft, 30-60 arching fronds, 70-90 a rosette lying on the ground; over 90 hangs (a palm's old fronds)",
    "scale": "[lo, hi] x the picture's size", "stem": "[m, m]: a stalk this tall carries the card at its top (flowers, seed heads); 0 = the card stands on the ground",
    "stem_radius": "m at the stalk's foot", "bend": "0-1: how far the stalk curves over toward its lean",
    "facing": '"up" (the card\'s face to the sky: fronds, rosette leaves), "any" (standing cards turned any way: grass), "out" (face outward), "auto" (up when leaning past 40 deg)',
    "on": "another layer's name (its index as text, or its `name`): stand on that layer's stalks instead of the ground (a palm's fronds on its trunk, leaves up a flower's stalk)",
    "along": "[lo, hi] share of the stalk's height the cards sit at, with `on` (1 = the top)",
    "turn": "deg: cards twisted about their own run (0 = flat as `facing` says)",
    "tilt": "deg the card is tipped over from its stalk's direction: 90 = it lies across the stalk's top, its face along the stalk (a daisy's head, a clover leaf, a lily pad)",
    "trunk": "true: the stalk is the plant's trunk (stout, barked, never sways at its foot): a palm, a tree fern, a yucca",
    "segments": "rings along a stalk (0 = by its height)", "sink": "m the card's foot sits under the ground (no gap on a slope)",
}


def _norm(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def part_length(leaves: dict, part: str, wood=(0.45, 0.4, 0.35)) -> float:
    """How long a part's card is (m): measured on the cards cut for it (a tuft of basal blades is as tall as its
    blades, not as its twig)."""
    at = veg_leaf.atlas(leaves, list(wood))
    return float(np.mean([at["cards"][i]["V"][:, 1].max() for i in veg_leaf.part_cards(leaves)[part]]))


def validate(s: dict):
    cl = s.get("clump") or {}
    layers = cl.get("layers") or []
    if not layers:
        raise ValueError('a clump needs layers: "clump": {"layers": [{"part": "main", "count": 20, "ring": [0, 0.1], "lean": [0, 30]}]}; '
                         f"layer keys: {sorted(LAYER)}")
    parts = veg_leaf.part_specs(s["leaves"])
    names = {str(i) for i in range(len(layers))} | {L.get("name") for L in layers if L.get("name")}
    for i, L in enumerate(layers):
        bad = set(L) - set(LAYER) - {"name"}
        if bad:
            raise ValueError(f"clump layer {i}: unknown keys {sorted(bad)}; it takes {sorted(LAYER) + ['name']}")
        if L.get("part", "main") is not None and L.get("part", "main") not in parts:
            raise ValueError(f"clump layer {i}: no part {L.get('part')!r}; this plant's parts: {sorted(parts)} (add it under leaves.parts)")
        if L.get("on") is not None and str(L["on"]) not in names:
            raise ValueError(f"clump layer {i}: `on` {L['on']!r} names no layer; layers: {sorted(n for n in names if n)}")


def grow(s: dict) -> dict:
    """Assemble the plant (s = the resolved spec). Deterministic in `seed`."""
    t0 = time.perf_counter()
    validate(s)
    seed = _mix(np.uint64(int(s.get("seed", 1)) * 2654435761 % (1 << 62) + 777))
    lf = s["leaves"]
    cards_of = veg_leaf.part_cards(lf)
    layers = [{**LAYER, **L} for L in s["clump"]["layers"]]
    size = float(s["clump"].get("size", 1.0))  # the whole plant's scale (a set varies it)
    up = np.array([0.0, 0.0, 1.0])
    # skeleton: node 0 under the ground, node 1 at the foot; then one chain per stalk
    pos, par, rad, order, axis, key, pin = [[0, 0, -0.05], [0, 0, 0.0]], [0, 0], [0.002, 0.002], [0, 0], [0, 0], [seed, _child(seed, 1)], [False, False]
    axes = [{"order": 0, "node": 1, "guide": None}]
    free = []
    tops = {}  # layer index -> [(node ids along the stalk, positions)]
    T = {k: [] for k in ("pos", "frame", "scale", "node", "key", "card")}
    by_name = {}
    for i, L in enumerate(layers):
        by_name[str(i)] = i
        if L.get("name"):
            by_name[L["name"]] = i
    for li, L in enumerate(layers):
        k0 = _child(seed, 100 + li)
        n = int(L["count"])
        hosts = tops.get(by_name[str(L["on"])]) if L["on"] is not None else None
        if L["on"] is not None and not hosts:
            raise ValueError(f"clump layer {li}: layer {L['on']!r} has no stalks to stand on (give it a `stem`)")
        tops[li] = []
        for j in range(n):
            kj = _child(k0, j)
            r = lambda q: float(_u(_child(kj, q), 3))
            az = 2.399963 * j + 6.283 * float(_u(k0, 5)) + 0.5 * (r(1) - 0.5)
            out = np.array([math.cos(az), math.sin(az), 0.0])
            lean = math.radians(L["lean"][0] + (L["lean"][1] - L["lean"][0]) * r(2))
            sc = (L["scale"][0] + (L["scale"][1] - L["scale"][0]) * r(3)) * size
            if hosts is not None:  # on a stalk of the host layer
                nodes, P = hosts[j % len(hosts)]
                a = L["along"][0] + (L["along"][1] - L["along"][0]) * r(4)
                f = a * (len(P) - 1)
                i0 = min(int(f), len(P) - 2)
                base = P[i0] + (f - i0) * (P[i0 + 1] - P[i0])
                node = int(nodes[min(int(round(f)), len(nodes) - 1)])
                base_order = 1 if not layers[by_name[str(L["on"])]]["trunk"] else 0
            else:
                rr = (L["ring"][0] + (L["ring"][1] - L["ring"][0]) * math.sqrt(r(4))) * size
                base = out * rr - up * float(L["sink"])
                node, base_order = 1, 0
            d = _norm(up * math.cos(lean) + out * math.sin(lean))
            h = (L["stem"][0] + (L["stem"][1] - L["stem"][0]) * r(5)) * size
            if h > 0 and float(L["stem_radius"]) <= 0:  # an unseen stalk: the card stands at its top (leaves seen from above)
                tt = np.linspace(0, 1, 4)[1:]
                w = ((1 - float(L["bend"])) + float(L["bend"]) * tt ** 1.5)[:, None]
                dirs = _norm(up[None] * (1 - w) + d[None] * w)
                base, d = base + (dirs * (h / 3)).sum(0), dirs[-1]
            elif h > 0:  # a stalk: curving over toward its lean
                m = int(L["segments"]) or max(3, int(math.ceil(h / 0.35)) + 1)
                tt = np.linspace(0, 1, m + 1)[1:]
                bend = float(L["bend"])
                w = ((1 - bend) + bend * tt ** 1.5)[:, None]  # bend 0 = straight along its lean; 1 = upright at the foot
                dirs = _norm(up[None] * (1 - w) + d[None] * w)
                P = np.vstack([base, base + np.cumsum(dirs * (h / m), axis=0)])
                ax = len(axes)
                o_ = 0 if L["trunk"] else base_order + 1
                axes.append({"order": o_, "guide": None, "born": 0, "node": len(pos)})
                ids, prev = [node], node
                r0 = float(L["stem_radius"]) * (size if not L["trunk"] else 1.0)
                if hosts is None and not L["trunk"]:  # its own foot on the ground
                    pos.append(P[0].tolist()); par.append(node); rad.append(r0); order.append(o_); axis.append(ax)
                    key.append(_child(kj, 50)); pin.append(False); free.append(len(pos) - 1)
                    prev = len(pos) - 1
                    ids = [prev]
                for q in range(1, m + 1):
                    pos.append(P[q].tolist())
                    par.append(prev)
                    rad.append(r0 * (1 - (0.25 if L["trunk"] else 0.6) * q / m))
                    order.append(o_)
                    axis.append(ax)
                    key.append(_child(kj, 50 + q))
                    pin.append(False)
                    prev = len(pos) - 1
                    ids.append(prev)
                tops[li].append((ids, P))
                base, node, d = P[-1], prev, dirs[-1]
            if L["part"] is None or not cards_of.get(L["part"]):
                continue
            if L["tilt"]:  # tipped over from the stalk: its run turns outward, its face follows the stalk
                tl_ = math.radians(float(L["tilt"]))
                o_ = out - d * (d @ out)
                o_ = _norm(o_) if np.linalg.norm(o_) > 1e-3 else _norm(np.cross(d, [0.0, 1.0, 0.3]))
                d_card, z_card = _norm(d * math.cos(tl_) + o_ * math.sin(tl_)), _norm(d * math.sin(tl_) - o_ * math.cos(tl_))
                T["pos"].append(base)
                T["frame"].append(np.stack([np.cross(d_card, z_card), d_card, z_card], axis=1))
                T["scale"].append(sc)
                T["node"].append(node)
                T["key"].append(kj)
                cs_ = cards_of[L["part"]]
                T["card"].append(cs_[int(_child(kj, 9) % np.uint64(len(cs_)))])
                continue
            # the card's frame: y = its run, z = its upper side
            facing = L["facing"] if L["facing"] != "auto" else ("up" if math.degrees(lean) > 40 else "any")
            if facing == "up":
                z = up - d * d[2]
                z = _norm(z) if np.linalg.norm(z) > 1e-4 else out
            elif facing == "out":
                z = _norm(out - d * (d @ out)) if abs(d @ out) < 0.999 else up
            else:
                a2 = 6.283 * r(6)
                z0 = _norm(np.cross(d, [0.3, 0.2, 1.0]) if abs(d[2]) > 0.9 else np.cross(d, up))
                z = z0 * math.cos(a2) + np.cross(d, z0) * math.sin(a2)
            if L["turn"]:
                tr = math.radians(float(L["turn"])) * (2 * r(7) - 1)
                z = z * math.cos(tr) + np.cross(d, z) * math.sin(tr)
            x = np.cross(d, z)
            cs_ = cards_of[L["part"]]
            T["pos"].append(base)
            T["frame"].append(np.stack([x, d, z], axis=1))
            T["scale"].append(sc)
            T["node"].append(node)
            T["key"].append(kj)
            T["card"].append(cs_[int(_child(kj, 9) % np.uint64(len(cs_)))])
    n = len(pos)
    P = np.asarray(pos, float)
    par = np.asarray(par, np.int32)
    tw = {"pos": np.asarray(T["pos"], float).reshape(-1, 3), "frame": np.asarray(T["frame"], float).reshape(-1, 3, 3),
          "scale": np.asarray(T["scale"], float), "variant": np.zeros(len(T["pos"]), int), "node": np.asarray(T["node"], int),
          "key": np.asarray(T["key"], np.uint64), "card": np.asarray(T["card"], int)}
    if s.get("season") in ("bare", "dead") or (s.get("season") == "winter" and not lf.get("evergreen")):
        tw = {k: v[:0] for k, v in tw.items()}  # a herb in winter has died back to its foot
    tips = [P[:, 2].max()]
    if len(tw["pos"]):  # the plant's height: its stalks and the tips of its cards
        wood = (s.get("bark") or {}).get("twig_color") or [0.45, 0.4, 0.35]
        reach = np.array([part_length(lf, p_, wood) for p_ in veg_leaf.part_specs(lf)])
        owner = np.zeros(max(max(c) for c in cards_of.values()) + 1, int)
        for pi, (p_, cc) in enumerate(cards_of.items()):
            owner[cc] = pi
        tip = tw["pos"] + tw["frame"][:, :, 1] * (reach[owner[tw["card"]]] * tw["scale"])[:, None]
        tips.append(float(tip[:, 2].max()))
        tw["reach"] = reach[owner[tw["card"]]] * tw["scale"]
    kids = np.bincount(par[1:], minlength=n)
    out = {"pos": P, "parent": par, "radius": np.asarray(rad, float), "order": np.asarray(order, np.int32),
           "born": np.zeros(n, np.int32), "axis": np.asarray(axis, np.int32), "key": np.asarray(key, np.uint64),
           "tip": kids == 0, "leafy": np.zeros(n, bool), "main": np.ones(n, bool), "pin": np.asarray(pin, bool),
           "ends": kids == 0, "unit": 1.0, "steps": 1, "axes": axes, "guides": {}, "height": float(max(tips)), "spec": s,
           "dead": np.zeros(n, bool), "twigs": tw, "clump": True, "free": np.isin(np.arange(n), free)}
    tr_ = [i for i, a_ in enumerate(axes) if a_["order"] == 0 and i > 0]
    if tr_:  # a trunk: the foot's girth is its girth
        out["radius"][:2] = out["radius"][np.asarray(axis) == tr_[0]][0]
    out["stats"] = {"nodes": n, "steps": 1, "height_m": round(out["height"], 3), "trunk_diameter_m": round(2 * float(out["radius"][1]), 3),
                    "max_order": int(out["order"].max()), "grow_s": round(time.perf_counter() - t0, 3), "pruned_nodes": 0,
                    "cuts": [], "dead": [], "cards": int(len(tw["pos"])), "stalks": len(axes) - 1}
    return out


def measures(tree: dict) -> dict:
    """What a clump is, in numbers: height, spread, cards per layer part, how upright its cards stand, cover seen from
    above (the share of its footprint disc the cards hide: a groundcover wants 0.8+, a tuft doesn't care)."""
    tw = tree["twigs"]
    if not len(tw["pos"]):
        return {"height_m": tree["height"], "spread_m": 0.0, "cards": 0}
    tips = tw["pos"] + tw["frame"][:, :, 1] * tw["reach"][:, None]
    pts = np.vstack([tw["pos"], tips, 0.5 * (tw["pos"] + tips)])
    r = float(np.percentile(np.linalg.norm(pts[:, :2], axis=1), 98))
    g = 48
    grid = np.zeros((g, g), bool)
    for a in np.linspace(0, 1, 12):  # each card as its midline, widened by a third of its reach
        q = tw["pos"] + (tips - tw["pos"]) * a
        w = np.maximum(1, (0.3 * tw["reach"] / max(2 * r / g, 1e-6)).astype(int))
        ij = np.clip(((q[:, :2] + r) / max(2 * r, 1e-6) * g).astype(int), 0, g - 1)
        for (i, j), w_ in zip(ij, w):
            grid[max(i - w_, 0): i + w_ + 1, max(j - w_, 0): j + w_ + 1] = True
    yy, xx = np.mgrid[0:g, 0:g]
    disc = (xx - g / 2 + 0.5) ** 2 + (yy - g / 2 + 0.5) ** 2 <= (g / 2) ** 2
    elev = np.degrees(np.arcsin(np.clip(tw["frame"][:, 2, 1], -1, 1)))
    return {"height_m": round(tree["height"], 3), "spread_m": round(2 * r, 3), "cards": int(len(tw["pos"])),
            "stalks": int(tree["stats"]["stalks"]), "cover_from_above": round(float((grid & disc).sum() / max(disc.sum(), 1)), 2),
            "card_elevation_p10_50_90": [round(float(v), 0) for v in np.percentile(elev, [10, 50, 90])]}
