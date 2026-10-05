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
        "min_order": 1, "steps": 2, "sub_shoots": 0, "side_angle": 40, "side_length": 0.6, "side_taper": 0.58, "spray_angle": 57}
CARD = {"variants": 4, "size": 384, "verts": 7, "cup": 0.1, "cross": 1, "scale": 1.0, "twig": {}, "leaf": {}, "strips": 0}


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
                    sa_ = math.radians(float(tw["spray_angle"]))
                    out = _norm(np.array([side * math.sin(sa_), math.cos(sa_), -0.12 - 0.15 * rnd(60 + j)]))
                    tt = np.linspace(0, 1, 4)[:, None]
                    pts = p + out * ln * tt + np.array([0, 0, -0.1 * ln]) * tt ** 2
                    V, F = _stem(pts, tw["radius"] * 0.6, tw["radius"] * 0.3)
                    add(V, F, 0, 1.0, -1)
                    shoots.append((pts, 0.8))
                    for q in range(int(tw["sub_shoots"])):  # last year's side shoots carry their own: a fan
                        for s2 in (-1, 1):
                            u2 = 0.3 + 0.5 * q / max(int(tw["sub_shoots"]), 1)
                            p2 = pts[0] + (pts[-1] - pts[0]) * u2
                            o2 = _norm(_norm(pts[-1] - pts[0]) * 0.6 + np.array([0, 1.0, 0]) * 0.5 * s2 * side
                                       + np.array([side * 0.3 * s2, 0, -0.1]))
                            l2 = ln * (0.45 - 0.15 * q / max(int(tw["sub_shoots"]), 1))
                            pts2 = p2 + o2 * l2 * tt + np.array([0, 0, -0.08 * l2]) * tt ** 2
                            V, F = _stem(pts2, tw["radius"] * 0.4, tw["radius"] * 0.2)
                            add(V, F, 0, 1.0, -1)
                            shoots.append((pts2, 0.7))
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
        shoots = [(axis, 1.0)]
        ns = int(tw["side_shoots"])
        for j in range(ns):  # a spray: side twigs left and right in turn, shorter toward the tip, hanging as the twig does
            side = -1 if j % 2 else 1
            sj = 0.12 + 0.7 * (j + 0.5 * rnd(800 + j)) / ns
            p, d = at(min(sj, 0.99))
            ln = L * float(tw.get("side_length", 0.6)) * (1 - float(tw.get("side_taper", 0.58)) * sj) * (0.75 + 0.5 * rnd(820 + j))
            sa = math.radians(float(tw.get("side_angle", 40)) * (0.75 + 0.5 * rnd(840 + j)))
            out = _norm(d * math.cos(sa) + np.array([side, 0, 0.0]) * math.sin(sa) + np.array([0, 0, 0.25 * (rnd(860 + j) - 0.5)]))
            tt = np.linspace(0, 1, 5)[:, None]
            pts = p + out * ln * tt + np.array([0, 0, -tw["droop"] * ln]) * tt ** 2 \
                + np.array([side * 0.06 * ln, 0, 0]) * np.sin(3 * tt + 6 * rnd(880 + j))
            V, F = _stem(pts, tw["radius"] * 0.6, tw["radius"] * 0.3)
            add(V, F, 0, 1.0, -1)
            shoots.append((pts, 0.9))
        lens = np.array([np.linalg.norm(np.diff(pts, axis=0), axis=1).sum() for pts, _ in shoots])
        share = np.maximum(np.round(n * lens / lens.sum()).astype(int), 2 if ns else n)
        lid = 0
        for si, (pts, sc0) in enumerate(shoots):
            seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
            cum = np.concatenate([[0], np.cumsum(seg)])
            nj = int(share[si])
            for j in range(nj):
                terminal = j == nj - 1
                s_ = (1.0 if terminal else 0.12 + 0.86 * j / max(nj - 1, 1)) * cum[-1] * 0.999
                i = min(np.searchsorted(cum, s_, side="right") - 1, len(pts) - 2)
                p = pts[i] + (s_ - cum[i]) / max(seg[i], 1e-9) * (pts[i + 1] - pts[i])
                d = _norm(pts[i + 1] - pts[i])
                Fr = _frame(d)
                q = 1000 * si + j
                if tw["arrangement"] == "alternate":  # two ranks, leaning up
                    az = (0 if j % 2 else math.pi) + (rnd(400 + q) - 0.5) * 0.7
                elif tw["arrangement"] == "opposite":
                    az = (j % 2) * math.pi + (j // 2) * math.pi / 2
                else:  # spiral
                    az = 2.399963 * j
                side = math.cos(az) * Fr[:, 0] + math.sin(az) * Fr[:, 2]
                dirv = d if terminal else _norm(d * math.cos(ang) + side * math.sin(ang) + np.array([0, 0, -lf.get("hang", 0.0)]))
                R = _frame(dirv, up=_norm(np.array([0, 0, 1.0]) + 0.5 * side))
                R = R @ _rot(np.array([0, 1.0, 0]), (rnd(500 + q) - 0.5) * 0.9)  # each blade rolls a little
                sc = (0.75 + 0.45 * rnd(600 + q) if not terminal else 1.0) * sc0
                V = (M["V"] * sc) @ R.T + p
                tone = 0.82 + 0.3 * rnd(700 + q)
                add(V, M["F"], 1, 1.0, lid)
                Cs[-1] = M["shade"] * tone
                lid += 1
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


# ---------------------------------------------------------------- atlases and cards

def _srgb(c):
    c = np.clip(np.asarray(c, float), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def card_spec(leaves: dict) -> dict:
    """The leaves spec a card's picture is made from: the mesh twig's, with `leaves.card.twig` / `.leaf` over it (a
    picture can afford thousands of true-width needles and a three-year fan where a mesh twig can't)."""
    cd = {**CARD, **(leaves.get("card") or {})}
    out = {**leaves, **cd["leaf"]}
    out["twig"] = {**(leaves.get("twig") or {}), **cd["twig"], "variants": cd["variants"]}
    return out


def _enclose(poly: np.ndarray, k: int) -> np.ndarray:
    """A convex polygon of at most k corners round a convex one: drop the edge whose neighbours meet nearest."""
    P = [np.asarray(q, float) for q in poly]
    while len(P) > k:
        n = len(P)
        best = None
        for i in range(n):
            a0, a1, b0, b1 = P[i - 1], P[i], P[(i + 1) % n], P[(i + 2) % n]
            d1, d2 = a1 - a0, b0 - b1
            den = d1[0] * d2[1] - d1[1] * d2[0]
            if abs(den) < 1e-12:
                continue
            t = ((b1[0] - a0[0]) * d2[1] - (b1[1] - a0[1]) * d2[0]) / den
            if t < 1:  # the neighbours diverge: this edge can't go
                continue
            X = a0 + t * d1
            area = 0.5 * abs((b0[0] - a1[0]) * (X[1] - a1[1]) - (b0[1] - a1[1]) * (X[0] - a1[0]))
            if best is None or area < best[0]:
                best = (area, i, X)
        if best is None:
            break
        _, i, X = best
        j = (i + 1) % n
        P[i] = X
        del P[j]
    return np.array(P)


def rasterize(mesh: dict, leaf_color, wood_color, size: int = 384, ss: int = 2, rough=(0.5, 0.85)) -> dict:
    """A twig seen from above (its upper side toward the eye, running up the picture) as maps: color (sRGB, the
    colour bled past the alpha's edge), alpha, normal (tangent space of the card), mask (R = light comes through:
    leaf 1 / wood 0, thinner where leaves overlap; G = roughness; B = shade: lower leaves darker). `frame` = the
    picture's square in the twig's metres [x0, y0, side]."""
    from PIL import Image, ImageDraw
    from scipy import ndimage
    V, F = mesh["V"], mesh["F"]
    lo, hi = V[:, :2].min(0), V[:, :2].max(0)
    side = float(max(hi - lo)) * 1.06
    cx = 0.5 * (lo[0] + hi[0])
    x0, y0 = cx - side / 2, lo[1] - 0.03 * side
    n = size * ss
    px = (V[:, 0] - x0) / side * n
    py = (1 - (V[:, 1] - y0) / side) * n
    tri = V[F]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    fn[fn[:, 2] < 0] *= -1
    zmean = tri[:, :, 2].mean(1)
    zr = (zmean - zmean.min()) / max(np.ptp(zmean), 1e-9)
    tone = mesh["col"][F].mean(1)
    leaf = mesh["mat"] == 1
    lc, wc = np.asarray(leaf_color, float), np.asarray(wood_color, float)  # (spec colours are sRGB already)
    col = np.where(leaf[:, None], lc[None] * np.clip(tone, 0, 1.6)[:, None], wc[None]) * (0.8 + 0.2 * zr)[:, None]
    im_c = Image.new("RGB", (n, n), (0, 0, 0))
    im_a = Image.new("L", (n, n), 0)
    im_n = Image.new("RGB", (n, n), (128, 128, 255))
    im_m = Image.new("RGB", (n, n), (0, 255, 255))
    dc, da, dn, dm = (ImageDraw.Draw(i) for i in (im_c, im_a, im_n, im_m))
    cnt = np.zeros((n, n), np.float32)
    for f in np.argsort(zmean):  # painter's order: the upper leaves last
        pts = [(float(px[v]), float(py[v])) for v in F[f]]
        dc.polygon(pts, fill=tuple(int(v) for v in np.clip(col[f] * 255, 0, 255)))
        da.polygon(pts, fill=255)
        dn.polygon(pts, fill=tuple(int(v) for v in np.clip((fn[f] * 0.5 + 0.5) * 255, 0, 255)))
        dm.polygon(pts, fill=(255 if leaf[f] else 0, int(255 * (rough[0] if leaf[f] else rough[1])), int(255 * (0.55 + 0.45 * zr[f]))))
    down = lambda im: np.asarray(im.resize((size, size), Image.BOX)).astype(np.float32) / 255
    a = down(im_a)
    c = down(im_c)
    c = np.where(a[..., None] > 1e-3, c / np.maximum(a[..., None], 1e-3), 0)  # un-premultiply the box filter
    solid = a > 0.02
    if solid.any():  # bleed the colour out past the edge (no dark fringe under filtering)
        idx = ndimage.distance_transform_edt(~solid, return_distances=False, return_indices=True)
        c = c[idx[0], idx[1]]
    nrm = down(im_n)
    m = down(im_m)
    return {"color": np.clip(c, 0, 1), "alpha": a, "normal": nrm, "mask": m, "frame": [x0, y0, side],
            "coverage": float((a > 0.5).mean())}


def _strip_outline(alpha: np.ndarray, strips: int):
    """A ladder round a long thin picture: per band along the twig the alpha's own left and right, as uv rows
    (bottom to top) of [left, right, v]."""
    n = alpha.shape[0]
    m = alpha > 0.08
    rows = np.flatnonzero(m.any(1))
    r0, r1 = rows[0], rows[-1] + 1
    edges = np.linspace(r0, r1, strips + 1)
    left = np.where(m.any(1), m.argmax(1), n).astype(float)
    right = np.where(m.any(1), n - m[:, ::-1].argmax(1), 0).astype(float)
    out = []
    for j, e in enumerate(edges):  # each rung spans the bands it borders
        a = int(np.floor(edges[max(j - 1, 0)]))
        b = int(np.ceil(edges[min(j + 1, strips)]))
        out.append([left[a:b].min() / n, right[a:b].max() / n, 1 - e / n])
    return np.array(out[::-1])


def card_mesh(alpha: np.ndarray, frame, verts: int = 7, cup: float = 0.1, cross: int = 1, droop: float = 0.0,
              length: float = 0.3, strips: int = 0) -> dict:
    """A card cut tight round a twig's picture: a convex polygon of at most `verts` corners round the alpha, as a
    fan from its middle (cupped, drooping like the twig), in the twig's own frame; uv = 0..1 in the picture.
    cross 2 adds the same card turned a quarter round the twig (tufts). `strips` n cuts a long thin twig as a
    ladder of n quads following its own width instead (a hanging birch or willow twig fills a fifth of one polygon)."""
    from scipy.spatial import ConvexHull
    n = alpha.shape[0]
    ys, xs = np.nonzero(alpha > 0.08)
    if len(xs) < 3:
        raise ValueError("an empty twig picture")
    x0, y0, side = frame
    if strips and strips > 1:
        lad = _strip_outline(alpha, int(strips))
        UV = np.vstack([np.c_[lad[:, 0], lad[:, 2]], np.c_[lad[:, 1], lad[:, 2]]])
        m_ = len(lad)
        F = np.array([t for i in range(m_ - 1) for t in ([i, m_ + i, m_ + i + 1], [i, m_ + i + 1, i + 1])])
    else:
        pts = np.c_[np.r_[xs, xs + 1, xs, xs + 1], np.r_[ys, ys, ys + 1, ys + 1]].astype(float)
        hull = pts[ConvexHull(pts).vertices]
        poly = _enclose(hull, verts)
        uv = np.clip(np.c_[poly[:, 0] / n, 1 - poly[:, 1] / n], -0.05, 1.05)
        UV = np.vstack([uv.mean(0), uv])
        k = len(poly)
        F = np.array([[0, 1 + i, 1 + (i + 1) % k] for i in range(k)])
    X = x0 + UV[:, 0] * side
    Y = y0 + UV[:, 1] * side
    hw = max(np.abs(X).max(), 1e-6)
    Z = cup * hw * (np.abs(X) / hw) ** 2 - droop * length * np.clip(Y / max(length, 1e-6), 0, 1.5) ** 2
    V = np.c_[X, Y, Z]
    if np.cross(V[F[0, 1]] - V[F[0, 0]], V[F[0, 2]] - V[F[0, 0]])[2] < 0:
        F = F[:, ::-1]
    if cross > 1:
        V2 = np.c_[-V[:, 2], V[:, 1], V[:, 0]]
        V, F, UV = np.vstack([V, V2]), np.vstack([F, F + len(V)]), np.vstack([UV, UV])
    area = 0.5 * np.abs(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])).sum(-1 if V.shape[1] == 2 else None) if False else \
        float(0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1).sum())
    return {"V": V, "F": F, "uv": UV, "area": area}


_ATLAS: dict = {}


def atlas(leaves: dict, wood_color=(0.2, 0.15, 0.1)) -> dict:
    """The foliage atlas of a plant: every card variant's picture in a grid (color RGBA, normal, mask), and the cards
    cut to them with their uvs in the atlas. `fill` = the share of each card's area its alpha covers (overdraw's
    other side: a card half empty is drawn twice for nothing). Kept by content (a dense needle atlas takes 20 s)."""
    import json
    key = json.dumps([leaves, list(wood_color)], sort_keys=True, default=float)
    if key not in _ATLAS:
        if len(_ATLAS) > 12:
            _ATLAS.pop(next(iter(_ATLAS)))
        _ATLAS[key] = _atlas(leaves, wood_color)
    a = _ATLAS[key]
    return {**a, "cards": [dict(c) for c in a["cards"]]}


def _atlas(leaves, wood_color) -> dict:
    cd = {**CARD, **(leaves.get("card") or {})}
    cs = card_spec(leaves)
    tw = {**TWIG, **cs["twig"]}
    nv, size = int(cd["variants"]), int(cd["size"])
    g = int(math.ceil(math.sqrt(nv)))
    A = {"color": np.zeros((g * size, g * size, 4), np.float32), "normal": np.zeros((g * size, g * size, 3), np.float32),
         "mask": np.zeros((g * size, g * size, 3), np.float32)}
    A["normal"][...] = (0.5, 0.5, 1.0)
    cards, fills = [], []
    for i in range(nv):
        tm = twig_mesh(cs, i)
        R = rasterize(tm, leaves.get("color", [0.16, 0.3, 0.08]), wood_color, size)
        r, c = divmod(i, g)
        sl = (slice(r * size, (r + 1) * size), slice(c * size, (c + 1) * size))
        A["color"][sl][..., :3] = R["color"]
        A["color"][sl][..., 3] = R["alpha"]
        A["normal"][sl] = R["normal"]
        A["mask"][sl] = R["mask"]
        cm = card_mesh(R["alpha"], R["frame"], int(cd["verts"]), cd["cup"], int(cd["cross"]), tw["droop"], tw["length"],
                       int(cd["strips"]))
        cm["V"] = cm["V"] * cd["scale"]
        px_area = float((R["alpha"] > 0.5).sum()) * (R["frame"][2] / size) ** 2 * cd["scale"] ** 2
        fills.append(px_area / max(cm["area"] / int(cd["cross"]) * cd["scale"] ** 2, 1e-12))
        cm["uv"] = np.c_[(c + cm["uv"][:, 0]) / g, 1 - (r + 1 - cm["uv"][:, 1]) / g]
        cards.append(cm)
    # `leaves.color` is the leaf as you SEE it lit: the per-leaf tones, blade shading and the mask's shade had the
    # atlas's median leaf at 0.7 of it (a lit birch rendered at V 0.43 against a photo's 0.69)
    leaf_px = (A["color"][..., 3] > 0.6) & (A["mask"][..., 0] > 0.5)
    if leaf_px.any():
        lum = lambda c_: 0.2126 * c_[..., 0] + 0.7152 * c_[..., 1] + 0.0722 * c_[..., 2]
        seen = float(np.median(lum(A["color"][leaf_px][:, :3]) * A["mask"][leaf_px][:, 2]))
        k_ = float(np.clip(lum(np.asarray(leaves.get("color", [0.16, 0.3, 0.08]), float)) / max(seen, 1e-6), 1.0, 1.8))
        A["color"][..., :3] = np.clip(A["color"][..., :3] * k_, 0, 1)
    return {**A, "cards": cards, "fill": float(np.mean(fills)), "grid": g, "size": size,
            "triangles": int(np.mean([len(c["F"]) for c in cards]))}


def write_atlas(at: dict, stem: str) -> dict:
    """<stem>_color.png (RGBA), _normal.png, _mask.png (R through, G rough, B shade)."""
    from PIL import Image
    out = {}
    for k in ("color", "normal", "mask"):
        out[k] = f"{stem}_{k}.png"
        Image.fromarray(np.clip(at[k] * 255 + 0.5, 0, 255).astype(np.uint8)).save(out[k])
    return out
