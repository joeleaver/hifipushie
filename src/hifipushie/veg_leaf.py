"""Leaves, needles and twigs: the small assets a tree's foliage is made of (The Grove's "twigs", SpeedTree's leaf
meshes). A leaf is generated from botanical words (shape family, lobes, length, width, fold, curl, petiole); a twig
is a short shoot carrying leaves by its own phyllotaxis, or needles; `place` puts twigs on a grown tree (at shoot ends
and along leafy shoots). Twig meshes are the source for mesh foliage (close LODs, video) and, later, for the atlas
cards games use. Local frame: the twig runs along +y from the origin, +z is up (the side leaves turn to the light).
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

from .vegetation import _child, _norm, _u

LEAF = {"shape": "ovate", "length": 0.07, "width": 0.55, "lobes": 4, "fold": 0.25, "curl": 0.25, "petiole": 0.15,
        "serrate": 0.0, "needle_width": 0.1, "bend": 0.0}  # bend: the blade curves sideways (a grass blade's arc), x its length  # needle_width: a needle's width / length (far wider than life: a mesh
# needle has to cover what hundreds of real ones do)
TWIG = {"length": 0.3, "leaves": 9, "arrangement": "alternate", "angle": 55, "droop": 0.15, "side_shoots": 0,
        "variants": 3, "per_m": 5.0, "where": "shoots", "spread": 45, "up": 0.3, "scale": [0.8, 1.15], "radius": 0.0025,
        "min_order": 1, "steps": 2, "sub_shoots": 0, "side_angle": 40, "side_length": 0.6, "side_taper": 0.58, "spray_angle": 57,
        "divergence": 137.5, "light": 0.7, "needles": "auto", "parted": 0.3, "forward": 0.7,
        "taper": 0.0, "flower": None,  # taper: leaves shrink toward the tip by this share (a frond's outline); flower:
        # {"form": "ray" | "cup" | "spike", "petals", "radius" m, "color", "center", "center_size", "spike": share of the stalk}
        "fascicle": 1, "needle_angle": None, "bud": 0.0,  # fascicles: needles per bundle (pines 2 / 3 / 5); [deg off the
        # shoot at the foliage's base, at its tip] (old needles stand out, young ones lie forward: a bottlebrush); a bud (m)
        "face": 0.5}  # face: 1 = every twig's upper side to the sky (a roof of plates), 0 = rolled any way round its shoot
CARD = {"variants": 4, "size": 384, "verts": 7, "cup": 0.1, "cross": 1, "scale": 1.0, "twig": {}, "leaf": {}, "strips": 0,
        "end": False}  # end: one more card across the shoot with the twig's picture seen from its tip (a tuft is round)


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
    if shape == "linear":  # a grass blade: parallel-sided, a long drawn-out point
        return np.minimum(t / 0.04, 1.0) * np.minimum((1 - t) / 0.45, 1.0) ** 0.7
    if shape == "strap":  # iris, daffodil, a palm's leaflet: parallel, a short point
        return np.minimum(t / 0.06, 1.0) * np.minimum((1 - t) / 0.15, 1.0) ** 0.6
    if shape == "round":  # clover leaflet, nasturtium, a water lily's pad
        return np.sin(np.pi * np.clip(t, 0, 1)) ** 0.5
    if shape == "petal":  # widest near the tip, narrowing to a claw
        return np.sin(np.pi * t ** 1.8) ** 0.7
    raise ValueError(f"leaf shape {shape!r}: ovate, triangular, lanceolate, lobed, linear, strap, round or petal")


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
    xb = lf["bend"] * L * t ** 2
    V = np.vstack([np.c_[xb, y, zmid], np.c_[xb - w, y, zedge], np.c_[xb + w, y, zedge],
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
    Vs, Fs, Ms, Cs, Ls, Gs = [], [], [], [], [], []
    base = 0

    def add(V, F, mat, col, leaf_id, rgb=None):
        nonlocal base
        Vs.append(V)
        Fs.append(F + base)
        Ms.append(np.full(len(F), mat))
        Cs.append(np.broadcast_to(col, (len(V),)).copy())
        Ls.append(np.full(len(V), leaf_id))
        Gs.append(np.full((len(V), 3), np.nan) if rgb is None else np.broadcast_to(np.asarray(rgb, float), (len(V), 3)).copy())
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
                    s = float(np.clip(0.15 + 0.7 * (j + 0.7 * (rnd(70 + 2 * j + (side > 0)) - 0.5)) / ns, 0.08, 0.92))
                    if rnd(90 + 2 * j + (side > 0)) < 0.12:
                        continue  # (a spray is never a stencil: shoots missing, uneven, off their rank)
                    p, d = at(s)
                    ln = L * (0.55 - 0.3 * j / ns) * (0.8 + 0.4 * rnd(40 + 2 * j + (side > 0)))
                    sa_ = math.radians(float(tw["spray_angle"]) * (0.75 + 0.5 * rnd(110 + 2 * j + (side > 0))))
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
            cnt = max(4, int(per * cum[-1] / L) // max(int(tw["fascicle"]), 1))
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
                arr = tw["needles"] if tw["needles"] != "auto" else ("radial" if shape == "needle_spray" else "fascicles")
                if arr == "ranked":  # fir, yew: flattened into two ranks with a parting above
                    side = math.copysign(1.0, math.cos(a)) * Fr[:, 0] * (0.6 + 0.4 * abs(math.cos(a))) + 0.15 * abs(math.sin(a)) * Fr[:, 2]
                    out = _norm(side + tw["forward"] * d)
                elif arr == "radial":  # spruce: singly on pegs all round the shoot, brushed forward, thinner underneath
                    sz_ = math.sin(a)
                    if sz_ < 0:
                        sz_ *= 1 - tw["parted"]
                    out = _norm(math.cos(a) * Fr[:, 0] + sz_ * Fr[:, 2] + tw["forward"] * d)
                else:  # fascicles (pine): bundles radiating round the shoot
                    fw_ = 0.75
                    if tw["needle_angle"]:
                        na0, na1 = tw["needle_angle"]
                        uu = (u - 0.25) / 0.75 if shape == "needle_tuft" else u
                        fw_ = 1.0 / math.tan(math.radians(max(na0 + (na1 - na0) * uu ** 1.5, 8.0) * (0.85 + 0.3 * float(_u(_child(key, 400 + si), j)))))
                    out = _norm(math.cos(a) * Fr[:, 0] + math.sin(a) * Fr[:, 2] + fw_ * d)
                ln = nl * sc * (0.8 + 0.4 * float(_u(_child(key, 200 + si), j)))
                wv = _norm(np.cross(out, d)) * (0.5 * nl * lf["needle_width"])
                tone = 0.8 + 0.35 * float(_u(_child(key, 300 + si), j))
                nf = int(tw["fascicle"]) if arr == "fascicles" else 1
                for q_ in range(nf):  # a bundle's needles part in a narrow V from one sheath
                    o_ = out if nf == 1 else _norm(out + 0.11 * (math.cos(2.1 * q_ + j) * _norm(wv) + math.sin(2.1 * q_ + j) * np.cross(out, _norm(wv))))
                    V = np.array([p - wv, p + wv, p + o_ * ln + np.array([0, 0, -0.08 * ln])])
                    add(V, np.array([[0, 1, 2]]), 1, tone * (1.0 if q_ == 0 else 0.93), lid)
                lid += 1
        if tw["bud"]:  # the resting bud at the shoot's end
            p, d = at(0.999)
            V, F = _stem(np.array([p, p + d * 0.6 * tw["bud"], p + d * tw["bud"]]), tw["radius"] * 2.2, tw["radius"] * 0.3)
            add(V, F, 0, 1.25, -1)
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
            arr_ = tw["arrangement"]
            for j in range(nj):
                terminal = j == nj - 1 and arr_ != "basal"
                s_ = (1.0 if terminal else 0.12 + 0.86 * j / max(nj - 1, 1)) * cum[-1] * 0.999
                if arr_ == "basal":  # every leaf from the foot (a grass tuft, a rosette seen from the side)
                    s_ = 0.01 * cum[-1]
                elif arr_ == "pinnate" and not terminal:  # pairs along the rachis
                    s_ = (0.1 + 0.88 * (j // 2) / max((nj - 1) // 2, 1)) * cum[-1] * 0.999
                u_s = s_ / max(cum[-1], 1e-9)
                i = min(np.searchsorted(cum, s_, side="right") - 1, len(pts) - 2)
                p = pts[i] + (s_ - cum[i]) / max(seg[i], 1e-9) * (pts[i + 1] - pts[i])
                d = _norm(pts[i + 1] - pts[i])
                Fr = _frame(d)
                q = 1000 * si + j
                if tw["arrangement"] == "alternate":  # two ranks, leaning up
                    az = (0 if j % 2 else math.pi) + (rnd(400 + q) - 0.5) * 0.7
                elif tw["arrangement"] == "opposite":
                    az = (j % 2) * math.pi + (j // 2) * math.pi / 2
                elif tw["arrangement"] == "whorled":
                    az = (j % 3) * 2 * math.pi / 3 + (j // 3) * math.pi / 3
                elif arr_ == "basal":
                    az = (0 if j % 2 else math.pi) + (rnd(400 + q) - 0.5) * 1.1
                elif arr_ == "pinnate":
                    az = (0 if j % 2 else math.pi) + (rnd(400 + q) - 0.5) * 0.12
                else:  # spiral, by the species' divergence (137.5 deg ~ 3/8; 144 = 2/5; 120 = 1/3)
                    az = math.radians(float(tw["divergence"])) * j
                side = math.cos(az) * Fr[:, 0] + math.sin(az) * Fr[:, 2]
                ang_j = ang * (rnd(450 + q) ** 0.7 if arr_ == "basal" else 1.0)
                dirv = d if terminal else _norm(d * math.cos(ang_j) + side * math.sin(ang_j) + np.array([0, 0, -lf.get("hang", 0.0)]))
                lt_ = float(tw["light"])  # 1 = every blade's upper side to the sky; 0 = as the bud set it (toward the shoot's tip)
                R = _frame(dirv, up=_norm(lt_ * (np.array([0, 0, 1.0]) + 0.5 * side) + (1 - lt_) * (d + 0.3 * side) + 1e-6))
                R = R @ _rot(np.array([0, 1.0, 0]), (rnd(500 + q) - 0.5) * 0.9)  # each blade rolls a little
                sc = (0.75 + 0.45 * rnd(600 + q) if not terminal else 1.0) * sc0
                if arr_ == "basal":
                    sc = (0.45 + 0.65 * rnd(600 + q)) * sc0
                elif arr_ == "pinnate":  # a frond's outline: short at the foot, longest low down, drawn out to the tip
                    sc = sc0 * (0.92 + 0.16 * rnd(600 + q)) * min(u_s / 0.18, 1.0) ** 0.6 * (0.35 if terminal else 1.0)
                if tw["taper"]:
                    sc = sc * (1 - float(tw["taper"]) * u_s)
                Vm = M["V"] * ([-1, 1, 1] if lf["bend"] and rnd(650 + q) < 0.5 else [1, 1, 1])  # arcs to either side
                V = (Vm * sc) @ R.T + p
                tone = 0.82 + 0.3 * rnd(700 + q)
                add(V, M["F"], 1, 1.0, lid)
                Cs[-1] = M["shade"] * tone
                lid += 1
    fl = tw["flower"]
    if fl:
        fl = {"form": "ray", "petals": 13, "radius": 0.012, "color": [0.95, 0.95, 0.92], "center": [0.9, 0.7, 0.1],
              "center_size": 0.35, "spike": 0.35, **fl}
        p, d = at(0.999)
        r_ = float(fl["radius"])
        np_ = int(fl["petals"])
        zf = np.array([0, 0, 0.004 + 0.3 * r_])  # the head stands proud of the leaves, facing the card's eye
        if fl["form"] == "spike":  # florets up the stalk's last part (lupin, lavender, a grass's seed head)
            PM = leaf_mesh({"shape": "ovate", "length": r_, "width": 0.7, "petiole": 0.1, "fold": 0.1, "curl": 0.1})
            for j in range(np_):
                u_ = 1 - float(fl["spike"]) * (1 - (j + 0.5) / np_)
                pj, dj = at(min(u_, 0.999))
                sd = (1 if j % 2 else -1) * (0.5 + 0.5 * rnd(1200 + j))
                dv = _norm(dj * 0.8 + sd * np.array([1.0, 0, 0]) + np.array([0, 0, 0.3 * (rnd(1300 + j) - 0.5)]))
                R = _frame(dv, up=np.array([0, 0, 1.0]))
                add((PM["V"] * (0.6 + 0.6 * (1 - (j + 0.5) / np_))) @ R.T + pj + zf, PM["F"], 1, 0.85 + 0.3 * rnd(1400 + j), 9000 + j, fl["color"])
        else:
            PM = leaf_mesh({"shape": "petal", "length": r_, "width": min(0.9, 2.6 * math.pi / max(np_, 3)) if fl["form"] == "ray" else 0.8,
                            "petiole": 0.0, "fold": 0.08, "curl": 0.15 if fl["form"] == "ray" else -0.1})
            for j in range(np_):
                if fl["form"] == "ray":  # a daisy seen from its face
                    a_ = 2 * math.pi * (j + 0.3 * rnd(1200 + j)) / np_
                    dv = np.array([math.cos(a_), math.sin(a_), 0.12])
                else:  # cup: tulip, poppy, crocus seen from the side: petals stand along the stalk
                    a_ = (j - (np_ - 1) / 2) / max(np_ - 1, 1)
                    dv = _norm(d + 0.9 * a_ * np.array([1.0, 0, 0]) + np.array([0, 0, 0.1 * (j % 2)]))
                R = _frame(_norm(dv), up=np.array([0, 0, 1.0]))
                add((PM["V"] * (0.9 + 0.2 * rnd(1300 + j))) @ R.T + p + zf * (1 + 0.1 * (j % 2)), PM["F"], 1,
                    0.9 + 0.2 * rnd(1400 + j), 9000 + j, fl["color"])
            if fl["form"] == "ray" and fl["center_size"]:
                k_ = 10
                rc = r_ * float(fl["center_size"])
                ring = np.array([[rc * math.cos(2 * math.pi * i / k_), rc * math.sin(2 * math.pi * i / k_), 0] for i in range(k_)])
                Vc = np.vstack([[0, 0, 0.3 * rc], ring]) + p + zf * 1.5
                add(Vc, np.array([[0, 1 + i, 1 + (i + 1) % k_] for i in range(k_)]), 1, 1.0, 9999, fl["center"])
    return {"V": np.vstack(Vs), "F": np.vstack(Fs), "mat": np.concatenate(Ms), "col": np.concatenate(Cs),
            "leaf": np.concatenate(Ls), "rgb": np.vstack(Gs)}


def place(tree: dict) -> dict:
    """Twig instances on a grown tree: pos, frames (3x3: x, y = the twig's run, z = its upper side), scale, variant,
    node, key. A twig ends every leafy shoot; more stand along leafy shoots (`twig.per_m`, turned by the golden angle,
    leaning out by `spread` and up to the light by `up`); `where: "ends"` keeps them to the shoot ends (pines)."""
    if tree.get("twigs") is not None:  # a plant assembled from parts (veg_small) knows where its cards stand
        return tree["twigs"]
    s = tree["spec"]
    lf = s["leaves"]
    tw = {**TWIG, **(lf.get("twig") or {})}
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
    from .vegetation import ground_at  # no twig runs into the ground: one that would is lifted to lie along it
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


@njit(cache=True)
def _face_ids(px, py, F, z, n):
    """Per pixel of an n x n picture: the highest face (by its own z) covering the pixel's centre, or within half a
    pixel of it (a needle thinner than a pixel still draws, as a line); -1 = none."""
    ids = np.full((n, n), -1, np.int64)
    zb = np.full((n, n), -1e30)
    for f in range(len(F)):
        x0, y0 = px[F[f, 0]], py[F[f, 0]]
        x1, y1 = px[F[f, 1]], py[F[f, 1]]
        x2, y2 = px[F[f, 2]], py[F[f, 2]]
        ix0 = max(int(math.floor(min(x0, x1, x2) - 1.0)), 0)
        ix1 = min(int(math.ceil(max(x0, x1, x2) + 1.0)), n - 1)
        iy0 = max(int(math.floor(min(y0, y1, y2) - 1.0)), 0)
        iy1 = min(int(math.ceil(max(y0, y1, y2) + 1.0)), n - 1)
        if ix1 < ix0 or iy1 < iy0:
            continue
        ar = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        sg = 1.0 if ar >= 0 else -1.0
        l0 = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2) * 0.5
        l1 = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2) * 0.5
        l2 = math.sqrt((x0 - x2) ** 2 + (y0 - y2) ** 2) * 0.5
        zf = z[f]
        for iy in range(iy0, iy1 + 1):
            cy = iy + 0.5
            for ix in range(ix0, ix1 + 1):
                if zf < zb[iy, ix]:
                    continue
                cx = ix + 0.5
                if sg * ((x1 - x0) * (cy - y0) - (y1 - y0) * (cx - x0)) < -l0:
                    continue
                if sg * ((x2 - x1) * (cy - y1) - (y2 - y1) * (cx - x1)) < -l1:
                    continue
                if sg * ((x0 - x2) * (cy - y2) - (y0 - y2) * (cx - x2)) < -l2:
                    continue
                zb[iy, ix] = zf
                ids[iy, ix] = f
    return ids


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
    # a leaf is not one flat green: each blade half catches the light by its own tilt, pale ones run yellow and dark
    # ones blue-green, lower ones sit in the upper ones' shade (flat per-leaf tones read as poster paint at 2 m)
    lit = 0.7 + 0.42 * np.clip(fn @ np.array([-0.38, 0.42, 0.82]), 0, 1)
    dev = np.clip((tone - np.median(tone[leaf]) if leaf.any() else tone * 0) * 2.2, -0.6, 0.6)
    hue = np.stack([1 + 0.22 * dev, 1 + 0.06 * dev, 1 - 0.35 * dev], 1)
    col = np.where(leaf[:, None], lc[None] * hue * (np.clip(tone, 0, 1.6) * lit)[:, None], wc[None]) * (0.72 + 0.28 * zr)[:, None]
    if "rgb" in mesh:  # parts with a colour of their own (petals, a flower's eye)
        own = mesh["rgb"][F].mean(1)
        has = ~np.isnan(own[:, 0])
        col[has] = own[has] * (np.clip(tone[has], 0, 1.6) * (0.85 + 0.15 * lit[has]))[:, None]
    # which face shows in each pixel: the upper faces over the lower (a painter's order, as a depth test on each
    # face's own height). One compiled pass: PIL polygons, four a face, took 20 min for a spruce's bough atlas
    ids = _face_ids(np.ascontiguousarray(px, np.float64), np.ascontiguousarray(py, np.float64),
                    np.ascontiguousarray(F, np.int64), np.ascontiguousarray(zmean, np.float64), n)
    hit = ids >= 0
    fi = np.where(hit, ids, 0)

    def paint(vals, empty):
        img = np.asarray(vals, np.float32)[fi]
        img[~hit] = empty
        return img.reshape(size, ss, size, ss, -1).mean((1, 3))  # (a box filter down to the picture's size)

    a = paint(np.ones((len(F), 1)), 0.0)[..., 0]
    c = paint(np.clip(col, 0, 1), 0.0)
    im_n = np.clip(fn * 0.5 + 0.5, 0, 1)
    im_m = np.stack([leaf.astype(float), np.where(leaf, rough[0], rough[1]), 0.55 + 0.45 * zr], 1)
    c = np.where(a[..., None] > 1e-3, c / np.maximum(a[..., None], 1e-3), 0)  # un-premultiply the box filter
    grain = ndimage.gaussian_filter(np.random.default_rng(3).random((size, size)), 1.2)
    c = c * (0.93 + 0.14 * (grain - grain.min()) / max(float(np.ptp(grain)), 1e-9))[..., None]
    solid = a > 0.02
    if solid.any():  # bleed the colour out past the edge (no dark fringe under filtering)
        idx = ndimage.distance_transform_edt(~solid, return_distances=False, return_indices=True)
        c = c[idx[0], idx[1]]
    nrm = paint(im_n, (128 / 255, 128 / 255, 1.0))
    m = paint(im_m, (0.0, 1.0, 1.0))
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
    key = _atlas_key(leaves, wood_color)
    if key not in _ATLAS:
        if len(_ATLAS) > 12:
            _ATLAS.pop(next(iter(_ATLAS)))
        a = _disk_get(key)
        if a is None:
            a = _atlas(leaves, wood_color)
            _disk_put(key, a)
            a = _disk_get(key) or a  # (the same 8-bit maps whether it was just made or read back)
        _ATLAS[key] = a
    a = _ATLAS[key]
    return {**a, "cards": [dict(c) for c in a["cards"]]}


def _atlas_key(leaves, wood_color) -> str:
    import json
    return json.dumps([leaves, list(wood_color)], sort_keys=True, default=float)


def atlas_ready(leaves: dict, wood_color=(0.2, 0.15, 0.1)) -> bool:
    """Whether this atlas is already made (in memory or on disk): asking for it costs nothing."""
    key = _atlas_key(leaves, wood_color)
    return key in _ATLAS or _disk_path(key).exists()


def _disk_path(key: str):
    """Atlases are kept on disk by content and this module's source (a needle atlas takes minutes to rasterise):
    $HIFIPUSHIE_VEG_CACHE, else ~/.cache/hifipushie/veg_atlas; the 60 most recently used are kept."""
    import hashlib
    import os
    from pathlib import Path
    root = Path(os.environ.get("HIFIPUSHIE_VEG_CACHE") or Path.home() / ".cache" / "hifipushie" / "veg_atlas")
    code = hashlib.sha1(Path(__file__).read_bytes()).hexdigest()[:10]
    return root / f"{hashlib.sha1((code + key).encode()).hexdigest()[:24]}.npz"


def _disk_get(key: str):
    p = _disk_path(key)
    if not p.exists():
        return None
    try:
        z = np.load(p, allow_pickle=False)
        import json
        meta = json.loads(str(z["meta"]))
        a = {k: z[k].astype(np.float32) / 255.0 for k in ("color", "normal", "mask")}
        a["cards"] = [{"V": z[f"c{i}_V"], "F": z[f"c{i}_F"], "uv": z[f"c{i}_uv"], "area": float(ar)} for i, ar in enumerate(meta["areas"])]
        a.update(meta["rest"])
        p.touch()
        return a
    except Exception:
        return None


def _disk_put(key: str, a: dict) -> None:
    import json
    try:
        p = _disk_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        arr = {k: np.clip(a[k] * 255 + 0.5, 0, 255).astype(np.uint8) for k in ("color", "normal", "mask")}
        for i, c in enumerate(a["cards"]):
            arr.update({f"c{i}_V": c["V"], f"c{i}_F": c["F"], f"c{i}_uv": c["uv"]})
        rest = {k: v for k, v in a.items() if k not in ("color", "normal", "mask", "cards")}
        tmp = p.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, meta=json.dumps({"areas": [c["area"] for c in a["cards"]], "rest": rest}, default=float), **arr)
        tmp.replace(p)
        old = sorted(p.parent.glob("*.npz"), key=lambda q: q.stat().st_mtime)[:-60]
        for q in old:
            q.unlink(missing_ok=True)
    except OSError:
        pass


def part_specs(leaves: dict) -> dict:
    """The pictures a plant's atlas holds: {"main": leaves} plus `leaves.parts` ({name: overrides merged over the
    leaves spec, its twig and its card}): a flower stalk beside the leaves, a dead frond, a seed head."""
    base = {k: v for k, v in leaves.items() if k != "parts"}
    out = {"main": base}
    for name, ov in (leaves.get("parts") or {}).items():
        sp = {**base, **{k: v for k, v in ov.items() if k not in ("twig", "card")}}
        sp["twig"] = {**(base.get("twig") or {}), **(ov.get("twig") or {})}
        cb, co = base.get("card") or {}, ov.get("card") or {}
        sp["card"] = {**cb, **co, "twig": {**(cb.get("twig") or {}), **(co.get("twig") or {})},
                      "leaf": {**(cb.get("leaf") or {}), **(co.get("leaf") or {})}}
        out[name] = sp
    return out


def part_cards(leaves: dict) -> dict:
    """{part name: [the atlas's card indices that show it]}."""
    out, k = {}, 0
    for name, sp in part_specs(leaves).items():
        nv = int({**CARD, **(sp.get("card") or {})}["variants"])
        out[name] = list(range(k, k + nv))
        k += nv
    return out


def card_variant(tw: dict, nv: int) -> np.ndarray:
    """Which card each twig draws: its own (`card`, plants assembled from named parts) or one by its key."""
    if tw.get("card") is not None:
        return np.asarray(tw["card"], int) % max(nv, 1)
    return (_child(tw["key"], 11) % np.uint64(nv)).astype(int)


def _atlas(leaves, wood_color) -> dict:
    parts = part_specs(leaves)
    if len(parts) > 1:
        return _atlas_parts(parts, leaves, wood_color)
    return _atlas_one(leaves, wood_color)


def _atlas_parts(parts, leaves, wood_color) -> dict:
    """Each part's own atlas, laid side by side in one square image (uvs rescaled)."""
    subs = [_atlas_one(sp, wood_color) for sp in parts.values()]
    size = max(a["color"].shape[0] for a in subs)
    g = int(math.ceil(math.sqrt(len(subs))))
    A = {"color": np.zeros((g * size, g * size, 4), np.float32), "normal": np.zeros((g * size, g * size, 3), np.float32),
         "mask": np.zeros((g * size, g * size, 3), np.float32)}
    A["normal"][...] = (0.5, 0.5, 1.0)
    cards, fills = [], []
    for i, a in enumerate(subs):
        r, c = divmod(i, g)
        n = a["color"].shape[0]
        for k in A:
            A[k][r * size: r * size + n, c * size: c * size + n] = a[k]
        f = n / (g * size)
        for cm in a["cards"]:  # (v = 0 is the image's bottom row)
            cm = dict(cm)
            cm["uv"] = np.c_[c * size / (g * size) + cm["uv"][:, 0] * f, 1 - (r * size / (g * size) + (1 - cm["uv"][:, 1]) * f)]
            cards.append(cm)
        fills.append(a["fill"])
    return {**A, "cards": cards, "fill": float(np.mean(fills)), "grid": g, "size": size,
            "triangles": int(np.mean([len(c["F"]) for c in cards]))}


def _atlas_one(leaves, wood_color) -> dict:
    cd = {**CARD, **(leaves.get("card") or {})}
    cs = card_spec(leaves)
    tw = {**TWIG, **cs["twig"]}
    nv, size = int(cd["variants"]), int(cd["size"])
    g = int(math.ceil(math.sqrt(nv * (2 if cd["end"] else 1))))
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
        if cd["end"]:  # the same twig seen from its tip, on a card across the shoot where its foliage is
            Vt = tm["V"]
            leafv = np.unique(tm["F"][tm["mat"] == 1])
            yc = float(np.median(Vt[leafv, 1])) if len(leafv) else 0.6 * tw["length"]
            R2 = rasterize({**tm, "V": np.c_[Vt[:, 0], Vt[:, 2], Vt[:, 1]]}, leaves.get("color", [0.16, 0.3, 0.08]), wood_color, size)
            r2, c2 = divmod(nv + i, g)
            sl2 = (slice(r2 * size, (r2 + 1) * size), slice(c2 * size, (c2 + 1) * size))
            A["color"][sl2][..., :3] = R2["color"]
            A["color"][sl2][..., 3] = R2["alpha"]
            A["normal"][sl2] = R2["normal"]
            A["mask"][sl2] = R2["mask"]
            ce = card_mesh(R2["alpha"], R2["frame"], int(cd["verts"]), 0.0, 1, 0.0, tw["length"], 0)
            # (a shallow cone opening toward the tip: seen from the side it is not a line)
            Ve = np.c_[ce["V"][:, 0], yc + 0.25 * np.hypot(ce["V"][:, 0], ce["V"][:, 1]), ce["V"][:, 1]] * cd["scale"]
            uve = np.c_[(c2 + ce["uv"][:, 0]) / g, 1 - (r2 + 1 - ce["uv"][:, 1]) / g]
            cm = {"V": np.vstack([cm["V"], Ve]), "F": np.vstack([cm["F"], ce["F"] + len(cm["V"])]),
                  "uv": np.vstack([cm["uv"], uve]), "area": cm["area"]}
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
