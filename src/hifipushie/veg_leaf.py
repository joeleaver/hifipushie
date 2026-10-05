"""Leaves, needles and twigs: the small assets a tree's foliage is made of (The Grove's "twigs", SpeedTree's leaf
meshes). A leaf is generated from botanical words (shape family, lobes, length, width, fold, curl, petiole); a twig
is a short shoot carrying leaves by its own phyllotaxis, or needles; `place` puts twigs on a grown tree (at shoot ends
and along leafy shoots). Twig meshes are the source for mesh foliage (close LODs, video) and, later, for the atlas
cards games use. Local frame: the twig runs along +y from the origin, +z is up (the side leaves turn to the light).
"""

from __future__ import annotations

import math

import numpy as np

from .vegetation import _child, _norm, _u

LEAF = {"shape": "ovate", "length": 0.07, "width": 0.55, "lobes": 4, "fold": 0.25, "curl": 0.25, "petiole": 0.15,
        "serrate": 0.0, "needle_width": 0.1}  # needle_width: a needle's width / length (far wider than life: a mesh
# needle has to cover what hundreds of real ones do)
TWIG = {"length": 0.3, "leaves": 9, "arrangement": "alternate", "angle": 55, "droop": 0.15, "side_shoots": 0,
        "variants": 3, "per_m": 5.0, "where": "shoots", "spread": 45, "up": 0.3, "scale": [0.8, 1.15], "radius": 0.0025,
        "min_order": 1, "steps": 2}


def _profile(shape: str, t: np.ndarray, lobes: int) -> np.ndarray:
    """Half width (0..1) along the blade, t = 0 at the petiole."""
    if shape == "ovate":
        return np.sin(np.pi * t ** 0.75) ** 0.9
    if shape == "triangular":  # birch: widest low, a drawn-out tip
        return np.minimum(t / 0.2, 1.0) ** 0.8 * (1 - t) ** 0.85 * 1.25
    if shape == "lanceolate":
        return np.sin(np.pi * t ** 0.9) ** 1.1
    if shape == "lobed":  # oak: widest past the middle, round lobes and sinuses
        return np.sin(np.pi * t ** 1.35) ** 0.8 * (0.55 + 0.45 * np.abs(np.sin(np.pi * lobes * t)) ** 0.7)
    raise ValueError(f"leaf shape {shape!r}: ovate, triangular, lanceolate or lobed")


def leaf_mesh(leaf: dict) -> dict:
    """One leaf blade: V (unit = metres), F, shade per vertex (midrib pale, edge darker), along (0 base, 1 tip)."""
    lf = {**LEAF, **leaf}
    k = 16 if lf["shape"] == "lobed" else 7
    t = np.linspace(0, 1, k + 1)
    L = lf["length"]
    w = _profile(lf["shape"], t, int(lf["lobes"])) * 0.5 * lf["width"] * L
    if lf["serrate"]:
        w = w * (1 + lf["serrate"] * (np.arange(k + 1) % 2 - 0.5))
    y = lf["petiole"] * L + t * L
    zmid = -lf["curl"] * L * t ** 2
    zedge = zmid + lf["fold"] * w
    V = np.vstack([np.c_[np.zeros(k + 1), y, zmid], np.c_[-w, y, zedge], np.c_[w, y, zedge],
                   [[-0.004 * L / 0.07, 0, 0], [0.004 * L / 0.07, 0, 0]]])
    F = []
    for i in range(k):
        m0, m1, l0, l1, r0, r1 = i, i + 1, k + 1 + i, k + 2 + i, 2 * k + 2 + i, 2 * k + 3 + i
        F += [[m0, m1, l1], [m0, l1, l0], [m0, r1, m1], [m0, r0, r1]]
    b = 3 * (k + 1)
    F.append([b, b + 1, 0])  # the petiole
    shade = np.concatenate([np.full(k + 1, 1.0), np.full(2 * (k + 1), 0.82), [0.9, 0.9]])
    along = np.concatenate([t, t, t, [0, 0]])
    return {"V": V, "F": np.array(F), "shade": shade, "along": along}


def _rot(axis, ang):
    axis = axis / np.linalg.norm(axis)
    c, s = math.cos(ang), math.sin(ang)
    x, y, z = axis
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])


def _frame(d, up=(0, 0, 1.0)):
    """Columns x, y = d, z: z as near `up` as it can be."""
    d = d / np.linalg.norm(d)
    z = np.asarray(up, float) - d * (d @ np.asarray(up, float))
    if np.linalg.norm(z) < 1e-6:
        z = np.array([1.0, 0, 0]) - d * d[0]
    z /= np.linalg.norm(z)
    return np.stack([np.cross(d, z), d, z], axis=1)


def _stem(pts, r0, r1, sides=3):
    """A thin tube along a polyline."""
    m = len(pts)
    V, F = [], []
    for i, p in enumerate(pts):
        d = pts[min(i + 1, m - 1)] - pts[max(i - 1, 0)]
        Fr = _frame(d)
        r = r0 + (r1 - r0) * i / max(m - 1, 1)
        for j in range(sides):
            a = 2 * math.pi * j / sides
            V.append(p + r * (math.cos(a) * Fr[:, 0] + math.sin(a) * Fr[:, 2]))
    for i in range(m - 1):
        for j in range(sides):
            a, b = i * sides + j, i * sides + (j + 1) % sides
            F += [[a, b, b + sides], [a, b + sides, a + sides]]
    return np.array(V), np.array(F)


def twig_mesh(leaves: dict, variant: int = 0) -> dict:
    """A twig with its leaves or needles: V, F, mat per face (0 wood, 1 leaf), col per vertex (a grey multiplier of
    the leaf colour: per-leaf tone x the blade's shade), leaf (per-vertex leaf id, -1 on wood: wind flutter later)."""
    lf = {**LEAF, **{k: v for k, v in leaves.items() if k in LEAF}}
    tw = {**TWIG, **(leaves.get("twig") or {})}
    key = _child(np.uint64(977), 31 * variant + 7)
    rnd = lambda i: float(_u(_child(key, i), 3))
    L = tw["length"]
    n_ax = 7
    t = np.linspace(0, 1, n_ax)
    bend = (rnd(1) - 0.5) * 0.25
    axis = np.c_[bend * L * t ** 2, L * t, -tw["droop"] * L * t ** 2 + 0.04 * L * np.sin(3 * t + 6 * rnd(2))]
    Vs, Fs, Ms, Cs, Ls = [], [], [], [], []
    base = 0

    def add(V, F, mat, col, leaf_id):
        nonlocal base
        Vs.append(V)
        Fs.append(F + base)
        Ms.append(np.full(len(F), mat))
        Cs.append(np.broadcast_to(col, (len(V),)).copy())
        Ls.append(np.full(len(V), leaf_id))
        base += len(V)

    def at(s):
        i = min(int(s * (n_ax - 1)), n_ax - 2)
        f = s * (n_ax - 1) - i
        p = axis[i] + f * (axis[i + 1] - axis[i])
        d = axis[i + 1] - axis[i]
        return p, d / np.linalg.norm(d)

    V, F = _stem(axis, tw["radius"], tw["radius"] * 0.4)
    add(V, F, 0, 1.0, -1)
    shape = lf["shape"]
    if shape in ("needle_tuft", "needle_spray"):
        shoots = [(axis, 1.0)]
        if shape == "needle_spray" or tw["side_shoots"]:  # flat side shoots, shorter toward the tip (a spruce's spray)
            ns = int(tw["side_shoots"] or 4)
            for j in range(ns):
                for side in (-1, 1):
                    s = 0.15 + 0.7 * j / ns
                    p, d = at(s)
                    ln = L * (0.55 - 0.3 * j / ns) * (0.8 + 0.4 * rnd(40 + 2 * j + (side > 0)))
                    out = _norm(np.array([side * 0.85, 0.55, -0.12 - 0.15 * rnd(60 + j)]))
                    tt = np.linspace(0, 1, 4)[:, None]
                    pts = p + out * ln * tt + np.array([0, 0, -0.1 * ln]) * tt ** 2
                    V, F = _stem(pts, tw["radius"] * 0.6, tw["radius"] * 0.3)
                    add(V, F, 0, 1.0, -1)
                    shoots.append((pts, 0.8))
        nl = lf["length"]
        per = int(tw["leaves"])
        lid = 0
        for si, (pts, sc) in enumerate(shoots):
            seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
            cum = np.concatenate([[0], np.cumsum(seg)])
            cnt = max(4, int(per * cum[-1] / L))
            for j in range(cnt):
                u = (j + 0.5) / cnt
                if shape == "needle_tuft":
                    u = 0.25 + 0.75 * u  # needles crowd the shoot's end
                s = u * cum[-1]
                i = min(np.searchsorted(cum, s, side="right") - 1, len(pts) - 2)
                p = pts[i] + (s - cum[i]) / max(seg[i], 1e-9) * (pts[i + 1] - pts[i])
                d = _norm(pts[i + 1] - pts[i])
                Fr = _frame(d)
                a = 2.399963 * j + 6.28 * rnd(100 + si)
                if shape == "needle_spray":  # combed: mostly sideways and up
                    side = math.cos(a) * Fr[:, 0] + (0.25 + 0.6 * abs(math.sin(a))) * Fr[:, 2]
                    out = _norm(side + 0.7 * d)
                else:
                    out = _norm(math.cos(a) * Fr[:, 0] + math.sin(a) * Fr[:, 2] + 0.75 * d)
                ln = nl * sc * (0.8 + 0.4 * float(_u(_child(key, 200 + si), j)))
                wv = _norm(np.cross(out, d)) * (0.5 * nl * lf["needle_width"])
                V = np.array([p - wv, p + wv, p + out * ln + np.array([0, 0, -0.08 * ln])])
                tone = 0.8 + 0.35 * float(_u(_child(key, 300 + si), j))
                add(V, np.array([[0, 1, 2]]), 1, tone, lid)
                lid += 1
    else:
        M = leaf_mesh(lf)
        n = int(tw["leaves"])
        ang = math.radians(tw["angle"])
        for j in range(n):
            terminal = j == n - 1
            s = 1.0 if terminal else 0.12 + 0.86 * j / max(n - 1, 1)
            p, d = at(min(s, 0.999))
            Fr = _frame(d)
            if tw["arrangement"] == "alternate":  # two ranks, leaning up
                az = (0 if j % 2 else math.pi) + (rnd(400 + j) - 0.5) * 0.7
            elif tw["arrangement"] == "opposite":
                az = (j % 2) * math.pi + (j // 2) * math.pi / 2
            else:  # spiral
                az = 2.399963 * j
            side = math.cos(az) * Fr[:, 0] + math.sin(az) * Fr[:, 2]
            dirv = d if terminal else _norm(d * math.cos(ang) + side * math.sin(ang) + np.array([0, 0, -lf.get("hang", 0.0)]))
            R = _frame(dirv, up=_norm(np.array([0, 0, 1.0]) + 0.5 * side))
            R = R @ _rot(np.array([0, 1.0, 0]), (rnd(500 + j) - 0.5) * 0.9)  # each blade rolls a little
            sc = 0.75 + 0.45 * rnd(600 + j) if not terminal else 1.0
            V = (M["V"] * sc) @ R.T + p
            tone = 0.82 + 0.3 * rnd(700 + j)
            add(V, M["F"], 1, 1.0, j)
            Cs[-1] = M["shade"] * tone
    return {"V": np.vstack(Vs), "F": np.vstack(Fs), "mat": np.concatenate(Ms), "col": np.concatenate(Cs),
            "leaf": np.concatenate(Ls)}


def place(tree: dict) -> dict:
    """Twig instances on a grown tree: pos, frames (3x3: x, y = the twig's run, z = its upper side), scale, variant,
    node, key. A twig ends every leafy shoot; more stand along leafy shoots (`twig.per_m`, turned by the golden angle,
    leaning out by `spread` and up to the light by `up`); `where: "ends"` keeps them to the shoot ends (pines)."""
    s = tree["spec"]
    lf = s["leaves"]
    tw = {**TWIG, **(lf.get("twig") or {})}
    P, par = tree["pos"], tree["parent"]
    n = len(P)
    empty = {"pos": np.zeros((0, 3)), "frame": np.zeros((0, 3, 3)), "scale": np.zeros(0), "variant": np.zeros(0, int),
             "node": np.zeros(0, int), "key": np.zeros(0, np.uint64)}
    if s.get("season") in ("winter", "bare", "dead") or s.get("decay") or n < 3:
        return empty
    leafy = (tree["steps"] - 1 - tree["born"]) < tw["steps"]  # shoots this young carry twigs
    leafy[:2] = False
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
    lo, hi = tw["scale"]
    return {"pos": pos, "frame": np.stack([x, d, z], axis=2), "scale": lo + (hi - lo) * _u(key, 8),
            "variant": (_child(key, 9) % np.uint64(int(tw["variants"]))).astype(int), "node": node, "key": key}
