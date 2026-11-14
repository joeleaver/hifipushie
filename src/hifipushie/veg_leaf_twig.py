"""Twig meshes: a dead twig and a live one (leaves on their stems along a shoot). Part of the leaves, twigs and their cards (veg_leaf.py has the overview)."""
from __future__ import annotations

import math

import numpy as np

from . import veg_leaf
from .vegetation_kernels import _child, _u
from .vegetation_tree import _norm
from .veg_leaf import _frame, _rot, _stem, leaf_mesh

def dead_twig_mesh(leaves: dict, variant: int = 0) -> dict:
    """A dead branchlet as the eye meets it in a stand's dead zone: a crooked sagging axis that forks at uneven
    intervals to either side (never in pairs: a spray's ranks drawn bare read as a fishbone), each fork shorter,
    thinner and crooked itself, a share of them broken to stubs, every variant its own tangle. `twig` keys beside
    length / radius / droop: `forks` (per m of wood), `depth` (fork generations), `crook`, `broken` (share snapped
    short), `fork_angle` [deg, deg], `child` [shortest, longest share of the parent], `flat` (how far forks leave the
    card's plane), `lichen` 0..1 (beard-lichen tufts hanging from the wood) + `lichen_color`. Wood tone varies per
    branch (weathered grey to darker bark-on wood)."""
    tw = {**veg_leaf.TWIG, **veg_leaf.DEAD_TWIG, **(leaves.get("twig") or {})}
    key = _child(np.uint64(4391), 53 * variant + 11)
    ctr = [0]

    def rnd():
        ctr[0] += 1
        return float(_u(_child(key, ctr[0]), 5))

    L = float(tw["length"])
    Vs, Fs, Ms, Cs, Gs = [], [], [], [], []
    base = [0]

    def add(V, F, mat, col, rgb=None):
        Vs.append(V)
        Fs.append(F + base[0])
        Ms.append(np.full(len(F), mat))
        Cs.append(np.full(len(V), col))
        Gs.append(np.full((len(V), 3), np.nan) if rgb is None else np.broadcast_to(np.asarray(rgb, float), (len(V), 3)).copy())
        base[0] += len(V)

    a0, a1 = [math.radians(float(v)) for v in tw["fork_angle"]]
    c0, c1 = [float(v) for v in tw["child"]]
    depth_max = int(tw["depth"])

    def branch(p0, d, ln, r, depth):
        n = max(3, int(4 + 6 * ln / L))
        pts = [np.asarray(p0, float)]
        turn = np.zeros(3)
        seg = ln / (n - 1)
        for i in range(1, n):  # a wandering line with momentum, sagging along its length
            kick = np.array([rnd() - 0.5, 0.3 * (rnd() - 0.5), float(tw["flat"]) * (rnd() - 0.5)]) * float(tw["crook"])
            turn = 0.6 * turn + kick
            d = _norm(d + turn + np.array([0, 0, -float(tw["droop"]) * 0.25 * i / n]))
            pts.append(pts[-1] + d * seg)
        pts = np.array(pts)
        tone = 0.75 + 0.5 * rnd()
        V, F = _stem(pts, r, max(r * 0.35, 0.0006))
        add(V, F, 0, tone)
        if tw["lichen"] and rnd() < float(tw["lichen"]):  # a beard hanging from the wood
            for _ in range(2 + int(5 * rnd())):  # (threads, a few together: in the card's plane they hang "down" the picture's side)
                q = pts[int(rnd() * (n - 1))]
                h_ = 0.03 + 0.07 * rnd()
                sx = 0.5 * h_ * (rnd() - 0.5)
                sy = (1 if rnd() < 0.5 else -1) * h_ * (0.5 + 0.5 * rnd())
                thr = np.array([q, q + [0.5 * sx, 0.6 * sy, -0.3 * h_], q + [sx, sy, -0.6 * h_]])
                Vl, Fl = _stem(thr, 0.0012, 0.0006)
                add(Vl, Fl, 0, 0.85 + 0.3 * rnd(), tw["lichen_color"])
        if depth >= depth_max or ln < 0.04:
            return
        k = int(float(tw["forks"]) * ln * (0.6 + 0.8 * rnd()) + rnd())
        side = 1.0 if rnd() < 0.5 else -1.0
        for _ in range(k):
            s = 0.08 + 0.88 * rnd()
            i = min(int(s * (n - 1)), n - 2)
            f = s * (n - 1) - i
            p = pts[i] + f * (pts[i + 1] - pts[i])
            dd = _norm(pts[i + 1] - pts[i])
            if rnd() < 0.72:  # mostly the other side from the last, never a mirrored pair
                side = -side
            ang = a0 + (a1 - a0) * rnd()
            across = _norm(np.cross(dd, [0, 0, 1.0]) + 1e-9)
            out = _norm(dd * math.cos(ang) + side * across * math.sin(ang) + np.array([0, 0, float(tw["flat"]) * 2 * (rnd() - 0.5)]) * math.sin(ang))
            l2 = ln * (c0 + (c1 - c0) * rnd()) * (1 - 0.45 * s)
            if rnd() < float(tw["broken"]):
                l2 *= 0.12 + 0.2 * rnd()
                branch(p, out, l2, r * 0.6, depth_max)  # a stub: no forks of its own
            else:
                branch(p, out, l2, r * (0.45 + 0.2 * rnd()), depth + 1)

    branch([0, 0, 0], _norm(np.array([0.25 * (rnd() - 0.5), 1.0, 0])), L * (0.8 + 0.3 * rnd()), float(tw["radius"]), 1)
    return {"V": np.vstack(Vs), "F": np.vstack(Fs), "mat": np.concatenate(Ms), "col": np.concatenate(Cs),
            "leaf": np.full(sum(len(v) for v in Vs), -1), "rgb": np.vstack(Gs)}


def twig_mesh(leaves: dict, variant: int = 0) -> dict:
    """A twig with its leaves or needles: V, F, mat per face (0 wood, 1 leaf), col per vertex (a grey multiplier of
    the leaf colour: per-leaf tone x the blade's shade), leaf (per-vertex leaf id, -1 on wood: wind flutter later)."""
    lf = {**veg_leaf.LEAF, **{k: v for k, v in leaves.items() if k in veg_leaf.LEAF}}
    tw = {**veg_leaf.TWIG, **(leaves.get("twig") or {})}
    if leaves.get("bare") and tw.get("form", "tangle") != "spray":  # dead twigs are their own thing, not a leafless spray
        return dead_twig_mesh(leaves, variant)
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
                    if tw["curl"]:
                        pts = pts + (d - out * float(d @ out)) * (tw["curl"] * 0.45 * ln * (0.6 + 0.8 * rnd(130 + 2 * j + (side > 0)))) * tt ** 2
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
                if tw["tips"]:
                    tone *= 1.0 + tw["tips"] * float(np.clip((u - 0.5) / 0.4, 0, 1)) ** 2
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
    out_ = {"V": np.vstack(Vs), "F": np.vstack(Fs), "mat": np.concatenate(Ms), "col": np.concatenate(Cs),
            "leaf": np.concatenate(Ls), "rgb": np.vstack(Gs)}
    if leaves.get("bare"):  # a dead twig: its wood only
        out_ = {**out_, "F": out_["F"][out_["mat"] == 0], "mat": out_["mat"][out_["mat"] == 0]}
    return out_
