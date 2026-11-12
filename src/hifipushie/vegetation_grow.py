"""`grow`: a tree from its resolved style. Part of vegetation (vegetation.py has the overview)."""
from __future__ import annotations

import math
import time

import numpy as np
from scipy import ndimage

from . import vegetation
from .vegetation import resolve
from .vegetation_kernels import _child, _collect, _distribute, _mix, _pipe, _pose, _shed, _u
from .vegetation_tree import (
    _Nodes, _along, _compass, _envelope, _inside, _norm, _path, _per, _shadow, find_limb, ground_at, steps_of,
    stout_path,
)

def grow(spec: dict, unit_scale: float | None = None, log=None) -> dict:
    """Grow the tree. Returns arrays in metres (pos, parent, radius, order, born, axis, key, tip, leafy), axes, and
    stats. With `height`, an unedited run is grown first and its height sets the unit, so edits stay in metres."""
    s = resolve(spec)
    if s.get("plant") == "sward":  # a tile of blades, not a plant with a skeleton
        from . import veg_sward
        return veg_sward.grow(s)
    if s.get("plant") == "clump":  # assembled, not grown
        from . import veg_small
        return veg_small.grow(s)
    h = s["habit"]
    t0 = time.perf_counter()
    if s.get("height") and unit_scale is None:
        bare = {k: v for k, v in spec.items() if k not in ("guides", "prune", "envelope", "forces", "height", "cuts", "dead")}
        ref = grow(bare, unit_scale=1.0)
        k = float(s["height"]) / max(ref["height"], 1e-6)
        if abs(k - 1) > 0.02:
            out = grow(spec, unit_scale=k)
            out["stats"]["unit_scale"] = round(k, 3)
            out["stats"]["grow_s"] = round(time.perf_counter() - t0, 3)
            return out
        unit_scale = 1.0
    unit = h["unit"] * (unit_scale or 1.0)
    steps = steps_of(s)
    yps = h["years_per_step"]
    seed = np.uint64(int(s["seed"]) * 2654435761 % (1 << 62) + 12345)
    sa, sb, sd = h["shadow"]
    sd = int(sd)
    env = s.get("environment") or {}
    light = _norm(np.asarray(env.get("light", [0, 0, 1]), float))
    tilt = (-light[0] / max(light[2], 0.3), -light[1] / max(light[2], 0.3))  # shadows fall away from the light
    wind = env.get("wind")
    wdir = _compass(wind["from"]) * -1 if wind else None  # the way it blows
    wstr = float(wind.get("strength", 0.5)) if wind else 0.0
    g_ = env.get("ground") or {}  # the ground in growth units: z = g0u + [x, y] . gvu
    g0u = float(g_.get("level", 0.0)) / unit
    gvu = np.zeros(2)
    if g_.get("slope"):
        t_ = np.asarray(g_.get("toward", [1, 0]), float)
        gvu = -math.tan(math.radians(float(g_["slope"]))) * t_ / max(np.linalg.norm(t_), 1e-9)
    clear_u = float(h["ground_clear"]) / unit
    forces = [(np.asarray(f["dir"], float) * float(f.get("strength", 1.0)), f.get("orders")) for f in s.get("forces") or []]
    stand = env.get("stand") if env.get("setting") in ("forest", "stand", "edge") or env.get("stand") else None
    if env.get("setting") in ("forest", "edge") and stand is None:
        stand = {}
    if env.get("setting") == "edge":  # a stand's edge: closed behind, open to one side (foliage down that side only)
        stand = {**stand, "open_side": env.get("open_side", stand.get("open_side", [1, 0]))}
    dead_log_ = []  # limbs the shade killed: (the trunk node's key, direction, girth, step)
    prunes = s.get("prune") or []
    cuts = []
    for c in s.get("cuts") or []:  # the steps each cut is made at
        y, last_y = float(c["year"]), float(c.get("until_year", s["age"]))
        ys = [y]
        while c.get("every") and ys[-1] + float(c["every"]) <= last_y:
            ys.append(ys[-1] + float(c["every"]))
        cuts.append(({int(round(q / yps)) for q in ys}, c))
    cut_log = []
    bolls = {}  # node key -> swelling: where a pollard is cut again and again the wood heals into a knuckled head
    envl = s.get("envelope")

    # guides: paths in metres -> units; each starts at a step
    guides = []
    for name, g in (s.get("guides") or {}).items():
        pts, cum = _path(np.asarray(g["path"], float) / unit, smooth=not g.get("straight"))
        st = int(round(g.get("from_year", 0) / yps))
        until = g.get("until_year")
        en = int(round(until / yps)) if until is not None else None
        guides.append({"name": name, "pts": pts, "cum": cum, "start": st, "end": en, "s": 0.0, "node": -1,
                       "vigour": float(g.get("vigour", 1.0)), "done": False, "free": bool(g.get("free", False)),
                       "on": g.get("on"), "bare": float(g.get("bare", 0.0))})
    guides.sort(key=lambda g: (g["start"], g["name"]))
    # a limb taken over as a guide: the shoot it was grown from is not made again (its lineage key)
    replaced = np.array([int(k) for g in (s.get("guides") or {}).values() for k in (g.get("replaces") or [])], np.uint64)

    T = _Nodes()
    T.add(1, key=_mix(seed), tip=False, guide=-1, R=np.eye(3))
    axes = [{"order": 0, "node": 1, "guide": None}]
    trunk = next((g for g in guides if g["start"] == 0 and np.linalg.norm(g["pts"][0]) < 1.5), None)
    if trunk is None:  # the first internode: straight up
        T.add(1, pos=[0, 0, 1.0], off=[0, 0, 1.0], parent=0, main=True, key=_child(_mix(seed), 0), tip=True,
              nb=0, guide=-1, R=np.eye(3), vig=1.0)
        for si_ in range(1, int(h["stems"])):  # more stems from the same foot, leaning out round it
            a_ = 2.399963 * si_ + 6.283 * float(_u(_child(_mix(seed), 300), 1))
            t_ = math.radians(float(h["stem_angle"]) * (0.6 + 0.8 * float(_u(_child(_mix(seed), 300 + si_), 2))))
            d_ = [math.sin(t_) * math.cos(a_), math.sin(t_) * math.sin(a_), math.cos(t_)]
            axes.append({"order": 0, "node": T.n, "guide": None, "born": 0})
            T.add(1, pos=d_, off=d_, parent=0, main=True, key=_child(_mix(seed), 300 + si_), tip=True,
                  nb=0, guide=-1, R=np.eye(3), vig=1.0, axis=len(axes) - 1)
    else:  # a drawn trunk: its path is the seedling
        trunk.update(node=0, axis=0)
        axes[0]["guide"] = trunk["name"]

    def new_axis(order, guide=None):
        axes.append({"order": int(order), "guide": guide, "born": step})
        return len(axes) - 1

    lam_young = list(h["apical"])
    ring_l = h["ring"] if isinstance(h["ring"], (list, tuple)) else [h["ring"]]  # (per order, or one number for all wood)
    step = 0
    tip_life = any(h["tip_life"])
    slowing = any(h["slowing"])
    for step in range(steps):
        for when, c in cuts:  # a cut made now: the wood goes, the stubs sprout (pollard, coppice, a lopped limb)
            if step not in when or T.n < 3:
                continue
            Pm_ = T.pos * unit
            if "under" in c:
                hit = (T.order > 0) & (Pm_[:, 2] < float(c["under"]))
            elif "below" in c:
                hit = (~T.main) & (T.order == 1) & (Pm_[T.parent, 2] < float(c["below"]))
            else:
                hit = _inside(Pm_, c)
            hit[:2] = False
            gone = hit.copy()
            par_ = T.parent
            for i in range(2, T.n):
                gone[i] |= gone[par_[i]]
            if not gone.any():
                cut_log.append({"year": round(step * yps, 1), "nodes": 0, "stubs": 0})
                continue
            first_ = gone & ~gone[par_]
            stubs = np.unique(par_[first_])
            new = T.keep(~gone)
            for g in guides:
                if g["node"] >= 0:
                    g["node"] = int(new[g["node"]])
                    if g["node"] < 0:
                        g["done"] = True
            stubs = new[stubs]
            stubs = stubs[stubs > 0]
            if float(c.get("boll", 1.0)) > 1.0:
                for q_ in stubs:
                    k_b = int(T.key[q_])
                    bolls[k_b] = min(bolls.get(k_b, 1.0) + (float(c["boll"]) - 1.0) * 0.5, float(c["boll"]))
            k_sp = int(c.get("sprouts", 4))
            if k_sp:
                more = [stubs]
                for _ in range(int(c.get("sprout_nodes", 1)) - 1):  # ... and the nodes just under the cut
                    q = T.parent[more[-1]]
                    more.append(q[q > 0])
                sp = np.unique(np.concatenate(more))
                if len(sp) > 12:  # (re-cutting a head leaves a stub per rod: only the stoutest dozen sprout again)
                    sp = sp[np.lexsort((T.born[sp], T.order[sp]))[:12]]
                T.nb[sp] = k_sp
                T.budstep[sp] = step
                T.starve[sp] = 0
            cut_log.append({"year": round(step * yps, 1), "nodes": int(gone.sum()), "stubs": int(len(stubs))})
        n = T.n
        P = T.pos
        age_t = (step + 1) / steps
        lam = np.array(lam_young, float)
        if h.get("apical_old") is not None:
            f0, f1 = h["apical_fade"]
            w = float(np.clip((age_t - f0) / max(f1 - f0, 1e-6), 0, 1))
            lam[0] = lam[0] + w * (h["apical_old"] - lam[0])
        # ---- 1. light
        leafy = (step - T.born) < h["leaf_steps"]
        leafy[0] = False
        cell = 1.0
        lo = P.min(0) - (sd + 3)
        hi = P.max(0) + (sd + 3)
        while np.prod((hi - lo) / cell) > 6e6:
            cell *= 1.5
        dims = tuple(np.ceil((hi - lo) / cell).astype(int) + 1)
        wl = np.clip(T.vig.astype(float), 0.05, 1.5)
        S = _shadow(P[leafy] / cell, lo / cell, dims, sa, sb, sd, tilt, wl[leafy], tail=float(h["shadow_tail"]))
        ij = np.clip(((P - lo) / cell).astype(np.int64), 1, np.array(dims) - 2)
        s_here = S[ij[:, 0], ij[:, 1], ij[:, 2]]
        Qn = np.clip(1.0 - s_here + sa * leafy * wl, 0.0, 1.0)
        Sg = ndimage.gaussian_filter(S, 1.5)  # (the raw grid's gradient stacks shoots in voxel layers)
        G = np.stack([Sg[ij[:, 0] + 1, ij[:, 1], ij[:, 2]] - Sg[ij[:, 0] - 1, ij[:, 1], ij[:, 2]],
                      Sg[ij[:, 0], ij[:, 1] + 1, ij[:, 2]] - Sg[ij[:, 0], ij[:, 1] - 1, ij[:, 2]],
                      Sg[ij[:, 0], ij[:, 1], ij[:, 2] + 1] - Sg[ij[:, 0], ij[:, 1], ij[:, 2] - 1]], 1)
        V = -G / (2 * sa)
        V = V / np.maximum(np.linalg.norm(V, axis=1, keepdims=True), 1.0)  # at most a unit pull
        Pm = P * unit
        top = P[:, 2].max()
        if stand is not None:  # a closed stand: the canopy's top rises with the tree; light falls off below it and away from the gap
            gap = stand.get("gap", 0.18) * max(top, 4.0)
            if env.get("spacing") or stand.get("spacing"):  # m between the stand's trees: its own share of the canopy
                gap = min(gap, 0.55 * float(env.get("spacing") or stand["spacing"]) / unit)
            depth = stand.get("depth", 0.35) * max(top, 4.0)
            zc = top * stand.get("height", 1.0)
            r = np.linalg.norm(P[:, :2], axis=1)
            side = np.clip((r - gap) / max(0.5 * gap, 1e-6), 0, 1) * np.clip((zc - P[:, 2]) / max(depth, 1e-6), 0, 1.5)  # (over a whole gap width, crowns 4 m apart interlocked 8 m wide)
            # the canopy's own shade deepens steadily below its top (a step at one depth made a stand tree's crown all or nothing:
            # live to the ground or a tuft, on a hair of `stand_shed`)
            below = np.clip((zc - P[:, 2]) / max(2.0 * depth, 1e-6), 0, 1) * stand.get("floor", 0.8)
            closed = np.ones(n)
            if stand.get("open_side") is not None:  # the open side keeps its light
                od = _norm(np.asarray(list(stand["open_side"])[:2], float))
                we = np.clip(0.5 - 0.5 * (P[:, :2] @ od) / max(gap, 1e-6), 0, 1)
                side, below = side * we, below * we
                closed = we
            Qn = np.clip(Qn - stand.get("strength", 1.0) * (side + below), 0, 1)
            V[:, :2] -= 0.5 * stand.get("strength", 1.0) * side[:, None] * _norm(np.c_[P[:, 0], P[:, 1]] + 1e-9)
        for nb_ in env.get("neighbours") or []:  # crowns beside it: {"at": [x, y], "height", "radius"} (m)
            c = np.asarray(nb_["at"], float)
            d = np.linalg.norm(Pm[:, :2] - c, axis=1)
            hh = nb_.get("height", 10.0) * min(1.0, age_t * 1.2)
            sh = np.clip(1 - d / (nb_.get("radius", 4.0) * 2.0), 0, 1) * np.clip((hh - Pm[:, 2]) / (0.3 * hh + 1e-6), 0, 1)
            Qn = np.clip(Qn - sh, 0, 1)
            V[:, :2] += 0.6 * sh[:, None] * _norm(Pm[:, :2] - c)
        if envl is not None:
            out_ = _envelope(Pm, envl)
            Qn = np.clip(Qn - envl.get("strength", 1.0) * out_, 0, 1)
        if wind:  # the windward side's buds suffer
            cen = P[leafy].mean(0) if leafy.any() else P.mean(0)
            rad = max(np.linalg.norm(P[:, :2] - cen[:2], axis=1).max(), 1.0)
            ex = np.clip(-((P - cen) @ wdir) / rad, 0, 1) * np.clip(P[:, 2] / max(top, 1), 0, 1)
            Qn = np.clip(Qn * (1 - wstr * ex), 0, 1)
        cut = np.zeros(n, bool)
        for vol in prunes:  # (a prune with no from_year is a cut on the finished tree: after the loop)
            if "from_year" in vol and step >= int(round(vol["from_year"] / yps)):
                if "under" in vol:
                    c_ = (T.order > 0) & (Pm[:, 2] < float(vol["under"]))
                elif "below" in vol:  # clear the trunk: laterals leaving it under this height
                    c_ = (~T.main) & (T.order == 1) & (Pm[T.parent, 2] < float(vol["below"]))
                else:
                    c_ = _inside(Pm, vol)
                cut |= c_ & ~T.pin
        Qn[cut] = 0
        # ---- 2. bud fate
        dead_bud = (step - np.maximum(T.born, T.budstep)) > h["bud_life"]
        T.nb[dead_bud] = 0
        qtip = Qn * T.tip
        qlat = Qn * T.nb
        Q = np.zeros(n)
        size = np.zeros(n, np.int64)
        _collect(T.parent, qtip + qlat, Q, size)
        v = np.zeros(n)
        vtip = np.zeros(n)
        vlat = np.zeros(n)
        _distribute(T.parent, T.main, T.order, Q, qtip, qlat, lam, h["vigour"] * Q[0], v, vtip, vlat)
        # ---- 4 (before growth, on last step's light). shedding and pruning
        dead = np.zeros(n, bool)
        thr_ = np.full(n, float(h["shed"]))
        if stand is not None:  # a stand's shade-bearers self-prune (`stand_shed`); on an edge's open side they keep their skirt
            thr_ = thr_ + h["stand_shed"] * closed
        # wood past its last living branch (no tip, no bud, no leaf beyond it) is dead: it goes like any shaded branch
        # (a limb whose own tip had stopped trailed on for decades as a bare sagging snake)
        LQ = np.zeros(n)
        _collect(T.parent, leafy.astype(float), LQ, np.zeros(n, np.int64))
        cut |= (Q <= 0) & (LQ <= 0) & (T.order > 0) & ~T.pin & ((step - T.born) >= h["shed_age"] + 2)
        _shed(T.parent, T.main, T.born, T.pin, Q, size, cut, step, thr_, h["shed_age"], dead)
        if dead.any():
            # the pipe model remembers what it carried
            area = np.zeros(n)
            _pipe(T.parent, T.mem, 1.0, h["pipe"], area)
            first = dead & ~dead[T.parent]
            if h["dead_keep"]:  # a limb off the trunk dies but stays for years: its wood is remembered as it was, and
                # put back at the end as dead wood, as far decayed as its years (twigs fallen, broken back, drooping)
                roots_ = first & (T.order == 1) & (T.order[T.parent] == 0)
                if stand is not None:  # in a stand the branches a limb loses stay on it too: its dead twigs
                    roots_ |= first & (T.order >= 2)
                roots_ = np.flatnonzero(roots_)
                if len(roots_):
                    own = np.full(n, -1)
                    own[roots_] = roots_
                    for j_ in np.flatnonzero(dead):  # (parents come first)
                        if own[j_] < 0:
                            own[j_] = own[T.parent[j_]]
                    rad_m = area * h["tip_radius"] + (step + 1 - T.born) * (yps * _per(ring_l, T.order))
                    for i_ in roots_:
                        ix = np.flatnonzero(own == i_)[:vegetation.DEAD_NODES]
                        loc = {int(q_): k_ for k_, q_ in enumerate(ix)}
                        dead_log_.append({"pk": int(T.key[T.parent[i_]]), "step": step, "key": T.key[ix].copy(), "root": int(T.order[i_]),
                                          "pos": (T.pos[ix] - T.pos[T.parent[i_]]) * unit,
                                          "par": np.array([loc.get(int(T.parent[q_]), -1) for q_ in ix]), "rad": rad_m[ix].copy(),
                                          "order": T.order[ix].copy(), "axis": T.axis[ix].copy(), "born": T.born[ix].copy()})
            np.add.at(T.mem, T.parent[first], 0.6 * area[first] ** h["pipe"])
            keep = ~dead
            new = T.keep(keep)
            for g in guides:
                if g["node"] >= 0:
                    g["node"] = int(new[g["node"]])
                    if g["node"] < 0:
                        g["done"] = True
            vtip, vlat, V, Qn = vtip[keep], vlat[keep], V[keep], Qn[keep]
            n = T.n
        # ---- 3. shoots
        order = T.order.astype(int)
        nmax = _per(h["shoot_max"], order).astype(int)
        nt = np.minimum(np.floor(vtip).astype(int), nmax) * T.tip
        if h["leader"] and age_t <= h["leader_until"]:
            lead = T.tip & (T.order == 0)
            nt[lead] = np.maximum(nt[lead], int(h["leader"]))
        gnode = {g["node"]: g for g in guides if g["node"] >= 0 and not g["done"]}
        for i in gnode:
            nt[i] = 0  # a guide's tip grows along its path, below
        per_bud = np.where(T.nb > 0, vlat / np.maximum(T.nb, 1), 0)
        ob = np.minimum(order + 1, 99)
        can = (_u(T.key, 7) < _per(h["bud_break"], ob)) | (T.budstep > 0)  # (a cut's sprouts always can)
        if h["bud_each"]:
            can = can | (T.nb > 1)  # (each bud is drawn below)
        nl = np.minimum(np.floor(per_bud).astype(int), _per(h["shoot_max"], ob).astype(int)) * (T.nb > 0) * can
        nl[order >= h["max_order"]] = 0
        # starving tips die
        st = T.starve
        hungry = T.tip & (nt == 0)
        st[hungry] = np.minimum(st[hungry] + 1, 200)
        st[~hungry] = 0
        T.tip[(st > 3) & (T.order > 0) & ~T.pin] = False
        if tip_life:  # determinate axes: after their years they stop reaching (their buds may still break)
            ab = np.fromiter((a.get("born", 0) for a in axes), np.int64, len(axes))
            lf_ = _per(h["tip_life"], order)
            old = T.tip & (lf_ > 0) & (step - ab[T.axis] >= lf_) & ~T.pin
            T.tip[old] = False
            nt[old] = 0

        par = T.parent
        dir_here = _norm(T.pos - T.pos[par])
        dir_here[0] = [0, 0, 1]
        up = np.array([0.0, 0.0, 1.0])

        def shoots(src, count, d0, order_new, keys, vres, is_main, phi0, axis_ids):
            """Grow `count[k]` metamers from node src[k] in direction d0[k]; returns the last node of each."""
            last = src.copy()
            d = d0.copy()
            # a shoot keeps turning the way it was turning: crookedness as curves, not a kink at every node
            turn = np.where(is_main[:, None], dir_here[src] - dir_here[par[src]], 0.0)
            alive = np.arange(len(src))
            ln = (0.45 + 0.55 * np.clip(vres / _per(h["shoot_max"], order_new), 0, 1)) * _per(h["length"], order_new)
            ln = ln * (1 + _per(h["uneven"], order_new) * (2 * _u(_mix(axis_ids.astype(np.uint64) + seed), 9) - 1))
            if slowing:  # an old axis creeps
                sl_ = _per(h["slowing"], order_new)
                born_ = np.fromiter((axes[a_].get("born", 0) for a_ in axis_ids), np.float64, len(axis_ids))
                ln = np.where(sl_ > 0, ln / (1 + (step - born_) / np.maximum(sl_, 1e-9)), ln)
            if h["limb_pace"]:  # no side shoot outgrows the leader's pace at this age
                s0_ = _per(h["slowing"], np.zeros(1, int))[0]
                lead_ = _per(h["shoot_max"], np.zeros(1, int))[0] * _per(h["length"], np.zeros(1, int))[0] / (1 + (step / s0_ if s0_ > 0 else 0.0))
                cap_ = _per(h["limb_pace"], order_new) * lead_ / np.maximum(_per(h["shoot_max"], order_new), 1)
                ln = np.where(order_new > 0, np.minimum(ln, cap_), ln)
            eta = _per(h["tropism"], order_new)
            jit = _per(h["jitter"], order_new)
            pl = _per(h["plagio"], order_new)
            el = np.radians(_per(h["elevation"], order_new))
            nbuds = _per(h["buds"], np.minimum(order_new, 99)).astype(int)
            whorl = _per(h["whorl"], order_new).astype(bool)
            div = np.radians(_per(h["divergence"], order_new))
            for j in range(int(count.max()) if len(count) else 0):
                a = alive[count[alive] > j]
                if not len(a):
                    break
                kj = _child(keys[a], 10 + j)
                rnd = np.stack([_u(kj, 1), _u(kj, 2), _u(kj, 3)], 1) * 2 - 1
                mom = 0.65 * np.clip(jit[a] / 0.3, 0, 1)
                # a side shoot's first segment leaves at its own angle: light and tropism bend what follows (they were
                # folding it back along its parent: angle 40 measured 23)
                w1 = np.where(is_main[a], 1.0, 0.2)[:, None] if j == 0 else 1.0
                dd = d[a] + w1 * (h["light"] * V[src[a]] + eta[a, None] * up + jit[a, None] * 0.6 * rnd) + mom[:, None] * turn[a]
                fw = _per(h["force_orders"], order_new[a])[:, None]
                for fv, fo in forces:
                    m_ = np.ones(len(a), bool) if fo is None else np.isin(order_new[a], fo)
                    dd = dd + (m_[:, None] * fw if fo is None else m_[:, None]) * fv
                if wind:
                    dd = dd + 0.5 * wstr * wdir * fw
                dd = _norm(dd)
                if pl[a].any():  # toward a set elevation, keeping the heading
                    hz = _norm(dd * [1, 1, 0] + 1e-9 * d[a])
                    tgt = hz * np.cos(el[a])[:, None] + up * np.sin(el[a])[:, None]
                    dd = _norm(dd + pl[a, None] * (tgt - dd))
                p0 = T.pos[last[a]]
                o = dd * ln[a, None]
                # the ground: nothing grows into it. A hanging shoot stops over it (`ground_clear`); any other slides
                # along it, and its own pull to the light turns it up from there
                end = p0 + o
                fl_ = g0u + end[:, :2] @ gvu + clear_u
                low_ = end[:, 2] < fl_
                if low_.any():
                    # (hanging: steeply down, or an order that hangs by habit; a side shoot's first segment always
                    # grows: its axis is counted on)
                    stop = low_ & ((dd[:, 2] < -0.5) | (eta[a] < -0.3)) & ((j > 0) | is_main[a])
                    sl_ = low_ & ~stop
                    oz = np.minimum(np.maximum(fl_ - p0[:, 2], 0.35 * ln[a]), 0.9 * ln[a])  # (its end turns up, ~20 deg; from under the line it climbs to it)
                    hl = np.sqrt(np.maximum(ln[a] ** 2 - oz ** 2, 1e-12))
                    hz_ = _norm(dd * [1, 1, 0] + 1e-9)
                    o[sl_] = (hz_ * hl[:, None] + up * oz[:, None])[sl_]
                    dd[sl_] = _norm(o[sl_])
                    if stop.any():
                        count[a[stop]] = j  # (it ends here; its tip lives and may try again when the tree has moved)
                        a, kj, dd, o, p0 = a[~stop], kj[~stop], dd[~stop], o[~stop], p0[~stop]
                        if not len(a):
                            continue
                Rp = T.R[last[a]]
                off = np.einsum("nji,nj->ni", Rp, o)  # into the parent's rest frame
                endm = (count[a] == j + 1)
                nbn = np.where(whorl[a] & ~endm, 0, nbuds[a])
                nbn[order_new[a] >= h["max_order"]] = 0
                nbn[(order_new[a] == 0) & ((p0[:, 2] + o[:, 2]) * unit < h["clear"])] = 0
                ids = T.add(len(a), pos=p0 + o, off=off, parent=last[a], order=order_new[a],
                            main=(is_main[a] if j == 0 else True), born=step, key=kj, tip=False, nb=nbn,
                            phi=phi0[a] + (j + 1) * div[a], R=Rp, guide=-1, axis=axis_ids[a], vig=ln[a])
                last[a] = ids
                turn[a] = dd - d[a]
                d[a] = dd
            return last

        # terminal shoots
        ti = np.flatnonzero(nt > 0)
        if len(ti):
            T.tip[ti] = False
            last = shoots(ti, nt[ti], dir_here[ti], order[ti], T.key[ti], vtip[ti], np.ones(len(ti), bool), T.phi[ti],
                          T.axis[ti].copy())
            T.tip[last] = True
        # lateral shoots: every bud of the node breaks together (a whorl)
        li = np.flatnonzero(nl > 0)
        if len(li):
            src, bud = [], []
            for b in range(int(T.nb[li].max())):
                m_ = li[T.nb[li] > b]
                src.append(m_)
                bud.append(np.full(len(m_), b))
            src, bud = np.concatenate(src), np.concatenate(bud)
            o_new = order[src] + 1
            a_ = dir_here[src]
            plane = _per(h["plane"], o_new).astype(bool)
            ref = np.where(np.abs(a_[:, 2:3]) > 0.95, np.array([[1.0, 0, 0]]), up[None])
            u_ = _norm(np.cross(a_, ref))
            w_ = np.cross(u_, a_)
            phi = np.where(plane, np.round(T.phi[src] / math.pi) * math.pi, T.phi[src]) + 2 * math.pi * bud / T.nb[src]
            ang = np.radians(_per(h["angle"], o_new - 1)) * (0.85 + 0.3 * _u(T.key[src], 20 + 1))  # by the PARENT's order
            d0 = a_ * np.cos(ang)[:, None] + (u_ * np.cos(phi)[:, None] + w_ * np.sin(phi)[:, None]) * np.sin(ang)[:, None]
            keys = _child(T.key[src], 100 + bud)
            if h["bud_each"]:
                ok_ = (T.nb[src] <= 1) | (_u(keys, 7) < _per(h["bud_break"], o_new)) | (T.budstep[src] > 0)
                src, bud, o_new, d0, keys = src[ok_], bud[ok_], o_new[ok_], d0[ok_], keys[ok_]
            if len(replaced):
                ok_ = ~np.isin(_child(keys, 10), replaced)
                src, bud, o_new, d0, keys = src[ok_], bud[ok_], o_new[ok_], d0[ok_], keys[ok_]
            ax0 = len(axes)
            for k_ in range(len(src)):
                new_axis(o_new[k_])
            first = T.n + np.arange(len(src))  # (pass 0 makes every shoot's first metamer, in order)
            last = shoots(src, nl[src], d0, o_new, keys, per_bud[src], np.zeros(len(src), bool),
                          _u(keys, 5) * 2 * math.pi, ax0 + np.arange(len(src)))
            for k_, f_ in enumerate(first):
                axes[ax0 + k_]["node"] = int(f_)
            T.tip[last] = True
            T.nb[li] = 0
        # ---- guides
        for gi, g in enumerate(guides):
            if g["done"] or step < g["start"]:
                continue
            pts, cum = g["pts"], g["cum"]
            if g["node"] < 0:  # attach: a lateral from the nearest wood, the stoutest of what's about equally near
                dist = np.linalg.norm(T.pos - pts[0], axis=1)
                cand = np.ones(T.n, bool)
                if g["on"]:  # ... of the guide (or "trunk") it's drawn on
                    on = next((q for q in guides if q["name"] == g["on"]), None)
                    cand = (T.order == 0) if g["on"] == "trunk" else \
                        (T.axis == on["axis"]) if on is not None and "axis" in on else cand
                    if not cand.any():
                        cand = np.ones(T.n, bool)
                dist = np.where(cand, dist, 1e9)
                near = np.flatnonzero(dist <= dist.min() + 0.75)
                near = near[T.order[near] == T.order[near].min()]
                base = int(near[np.argmin(dist[near])])
                g["node"], g["axis"] = base, new_axis(int(T.order[base]) + 1, g["name"])
                g["first"] = True
            left = cum[-1] - g["s"]
            remaining = max((g["end"] if g["end"] is not None else steps) - step, 1)
            want = left / remaining * g["vigour"] if g["end"] is not None else 2.2 * g["vigour"]
            nm = int(max(1, min(math.ceil(want / 1.0), 8)))
            ln = min(left, max(want, 0.6)) / nm
            o_g = axes[g["axis"]]["order"]
            node = g["node"]
            if not g.get("first") and T.guide[node] == gi:  # (never the wood it leaves: that was killing a young trunk's leader)
                T.tip[node] = False
            for j in range(nm):
                if g["s"] >= cum[-1] - 1e-6:
                    break
                g["s"] = min(g["s"] + ln, cum[-1])
                p = _along(pts, cum, g["s"])
                kj = _child(_child(seed, 5000 + gi), int(round(g["s"] * 16)))
                nbn = int(_per(h["buds"], o_g)) if o_g < h["max_order"] else 0
                if (o_g == 0 and p[2] * unit < h["clear"]) or g["s"] * unit < g["bare"]:
                    nbn = 0  # (a drawn trunk has its clear bole too; a limb may be drawn bare for its first metres)
                i_ = T.add(1, pos=p, pinpos=p, off=p - T.pos[node], parent=node, order=o_g,
                           main=(not g.pop("first", False)) or o_g == 0, born=step, key=kj, tip=False, nb=nbn,
                           phi=T.phi[node] + math.radians(float(_per(h["divergence"], o_g))), R=np.eye(3),
                           guide=gi, axis=g["axis"], pin=not g["free"], vig=1.0)[0]
                axes[g["axis"]].setdefault("node", int(i_))
                node = int(i_)
            g["node"] = node
            T.tip[node] = True
            if g["s"] >= cum[-1] - 1e-6:
                g["done"] = True  # the path is drawn: the tip grows on by itself
        # ---- 5. widths, bending
        n = T.n
        area = np.zeros(n)
        _pipe(T.parent, T.mem, 1.0, h["pipe"], area)
        rad = area * (h["tip_radius"] / unit) + (step + 1 - T.born) * (yps * _per(ring_l, T.order) / unit)
        leafy = (step - T.born) < h["leaf_steps"]
        if h["sag"] > 0:
            _pose(T.parent, T.off, T.pin, T.pinpos, T.order, rad, leafy, T.theta, h["sag"], h["sag_max"],
                  0.0, T.pos, T.R, g0u + 0.03 / unit, gvu[0], gvu[1])
        if log:
            log(f"step {step}: {T.n} nodes, top {T.pos[:, 2].max() * unit:.1f} m")

    n = T.n
    area = np.zeros(n)
    _pipe(T.parent, T.mem, 1.0, h["pipe"], area)
    radius = area * h["tip_radius"] + (steps - T.born) * (yps * _per(ring_l, T.order))
    radius[0] = radius[1] if n > 1 else radius[0]
    pos = T.pos * unit
    # the foot flares
    radius = radius * (1 + (h["flare"] - 1) * np.exp(-pos[:, 2] / max(h["flare_height"], 1e-6)) * (T.order == 0))
    leafy = (steps - 1 - T.born) < h["leaf_steps"]
    leafy[0] = False
    kids = np.bincount(T.parent[1:], minlength=n)
    first = {}
    for i in range(1, n):
        first.setdefault(int(T.axis[i]), i)
    for i, a in enumerate(axes):
        a.pop("node", None)
        if i in first:
            a["node"] = first[i]
    ax_names = {}
    for i, a in enumerate(axes):
        if a.get("guide"):
            ax_names[a["guide"]] = i
    out = {"pos": pos, "parent": T.parent.copy(), "radius": radius, "order": T.order.copy(), "born": T.born.copy(),
           "axis": T.axis.copy(), "key": T.key.copy(), "tip": T.tip.copy(), "leafy": leafy, "main": T.main.copy(),
           "pin": T.pin.copy(), "ends": kids == 0, "unit": unit, "steps": steps, "axes": axes, "guides": ax_names,
           "height": float(pos[:, 2].max()), "spec": s}
    if s.get("trunk_diameter"):  # girth in metres: thick wood scaled to it, twigs left as they are
        r1, tip_r = float(radius[1]), 3 * h["tip_radius"]
        k_ = 0.5 * float(s["trunk_diameter"]) / max(r1, 1e-9)
        w_ = np.clip((radius - tip_r) / max(r1 - tip_r, 1e-9), 0, 1) ** 0.5
        if s.get("limb_diameter"):  # the trunk alone
            w_ = w_ * (T.order == 0)
        out["radius"] = radius = radius * (1 + (k_ - 1) * w_)
        if s.get("trunk_taper") is not None:  # a column: the trunk keeps its girth to its top, whatever it carries
            tr = np.flatnonzero(T.order == 0)
            zt = max(float(pos[tr, 2].max()), 1e-6)
            want = 0.5 * float(s["trunk_diameter"]) * (1 - float(s["trunk_taper"]) * pos[tr, 2] / zt)
            radius[tr] = np.maximum(radius[tr], want) if not s.get("cuts") else want
            out["radius"] = radius
    elif stand is not None and (env.get("spacing") or stand.get("spacing")) and h["sdi_max"]:
        # a stand's stems are as stout as its stocking allows (Reineke 1933: N x (dbh / 25 cm)^1.6 <= the species' most):
        # the pipe model and the ring sized a tree by its own wood alone, and 3 m apart stood 42 cm stems (173 m2 / ha)
        sp_ = float(env.get("spacing") or stand["spacing"])
        cap = 0.25 * (float(h["sdi_max"]) / (1e4 / sp_ ** 2)) ** (1 / 1.6) * (1.0 if stand.get("open_side") is None else 1.25)
        tr = np.flatnonzero(T.order == 0)
        if len(tr) > 2 and pos[tr, 2].max() > 1.3:
            dbh = 2 * float(np.interp(1.3, pos[tr, 2], radius[tr]))
            if dbh > cap:
                r1, tip_r = 0.5 * dbh, 3 * h["tip_radius"]
                w_ = np.clip((radius - tip_r) / max(r1 - tip_r, 1e-9), 0, 1) ** 0.5
                out["radius"] = radius = radius * (1 + (cap / dbh - 1) * w_)
                out["stand_dbh_cap"] = round(cap, 3)
    if s.get("limb_diameter") and (T.order == 1).any():  # limbs sized by themselves: a fat trunk under ordinary limbs
        o1 = np.flatnonzero((T.order == 1) & (T.order[T.parent] == 0))
        rl, tip_r = float(radius[o1].max()), 3 * h["tip_radius"]
        k_ = 0.5 * float(s["limb_diameter"]) / max(rl, 1e-9)
        w_ = np.clip((radius - tip_r) / max(rl - tip_r, 1e-9), 0, 1) ** 0.5 * (T.order > 0)
        out["radius"] = radius = radius * (1 + (k_ - 1) * w_)

    def subset(keep, leafless=False):
        nonlocal n
        keep = keep.copy()
        keep[:2] = True
        par0 = out["parent"]
        for i in range(2, len(keep)):  # (parents come first: a cut takes everything it carries)
            keep[i] &= keep[par0[i]]
        new = -np.ones(len(keep), np.int64)
        new[keep] = np.arange(int(keep.sum()))
        for k_ in ("pos", "radius", "order", "born", "axis", "key", "tip", "leafy", "main", "pin", "dead", "shade_dead"):
            out[k_] = out[k_][keep]
        par = new[par0[keep]]
        par[0] = 0
        out["parent"] = par.astype(np.int32)
        n = int(keep.sum())
        out["ends"] = np.bincount(par[1:], minlength=n) == 0
        if leafless:
            out["leafy"] = np.zeros(n, bool)
        out["height"] = float(out["pos"][:, 2].max())
        first = {}
        for i in range(1, n):
            first.setdefault(int(out["axis"][i]), i)
        for i, a in enumerate(axes):
            a.pop("node", None)
            if i in first:
                a["node"] = first[i]

    if bolls:  # swell the cut ends, easing out ~4 radii down the wood that carries them
        r_ = out["radius"]
        fac = np.ones(n)
        for i_ in np.flatnonzero(np.isin(out["key"], np.array(list(bolls), np.uint64))):
            if out["order"][i_] > 1:
                continue  # (a head, not every rod's stub)
            k_b, q_, d_ = bolls[int(out["key"][i_])], int(i_), 0.0
            reach = max(4.0 * float(r_[i_]), 0.3)
            while q_ > 0 and d_ < reach:
                fac[q_] = max(fac[q_], 1 + (k_b - 1) * (1 - d_ / reach) ** 2)
                p_ = int(out["parent"][q_])
                d_ += float(np.linalg.norm(out["pos"][q_] - out["pos"][p_]))
                q_ = p_
        out["radius"] = r_ * fac
    out["dead"] = np.zeros(n, bool)
    out["shade_dead"] = np.zeros(n, bool)
    if dead_log_:  # the limbs the shade killed within `dead_keep` years, as dead wood on the trunk
        where = {int(k_): i_ for i_, k_ in enumerate(out["key"])}
        add = {k_: [] for k_ in ("pos", "parent", "radius", "order", "born", "axis", "key")}
        keep_y = float(h["dead_keep"])
        dk = {**vegetation.DEAD, **(s.get("deadwood") or {})}
        n_add = 0
        for L_ in sorted(dead_log_, key=lambda e_: (e_["root"], e_["step"])):  # (limbs first: their dead branches hang on them)
            age_ = (steps - L_["step"]) * yps
            if age_ > keep_y or L_["pk"] not in where or len(L_["pos"]) == 0:
                continue
            f_ = age_ / keep_y  # 0 = just died .. 1 = about to fall
            Pd, pr_, rd = L_["pos"], L_["par"], L_["rad"]
            m0 = len(Pd)
            u1, u2, u3 = (float(_u(_child(np.uint64(L_["key"][0]), 70 + q_), 1)) for q_ in range(3))
            seg_ = np.linalg.norm(Pd - np.where(pr_[:, None] >= 0, Pd[np.maximum(pr_, 0)], 0.0), axis=1)
            along = np.zeros(m0)
            for q_ in range(m0):
                along[q_] = seg_[q_] + (along[pr_[q_]] if pr_[q_] >= 0 else 0.0)
            reach = float(along.max())
            # broken back with the years (the oldest, lowest whorls are short spurs), fine twigs first
            ok_ = along <= max(reach * (1 - dk["break"] * f_ ** 0.8) * (0.7 + 0.3 * u1), min(reach, dk["stub"]))
            un = _u(L_["key"], 73)
            ok_ &= (rd >= (dk["twig"][0] + (dk["twig"][1] - dk["twig"][0]) * f_) * (0.5 + un)) | (np.arange(m0) == 0)
            for q_ in range(1, m0):
                ok_[q_] &= pr_[q_] >= 0 and ok_[pr_[q_]]
            ok_[0] = True
            # it hangs: turned down about its foot, and bowed down along its length
            hd = _norm(Pd[min(m0 - 1, 2)] * [1, 1, 0] + 1e-9)
            ang = math.radians(dk["droop"][0] + (dk["droop"][1] - dk["droop"][0]) * f_) * (0.6 + 0.8 * u2)
            hx = Pd @ hd
            ca_, sa_ = math.cos(ang), math.sin(ang)
            Pn = Pd + hd[None] * (hx * ca_ + Pd[:, 2] * sa_ - hx)[:, None]
            Pn[:, 2] = -hx * sa_ + Pd[:, 2] * ca_ - dk["bow"] * (0.4 + 0.6 * f_) * along ** 2 / max(reach, 1e-6)
            w_ = where[L_["pk"]]
            base_ = out["pos"][w_] if w_ < n else np.asarray(add["pos"][w_ - n])
            new_i = -np.ones(m0, np.int64)
            amap = {}
            for q_ in np.flatnonzero(ok_):
                new_i[q_] = n + n_add
                where.setdefault(int(L_["key"][q_]), n + n_add)
                n_add += 1
                a0 = int(L_["axis"][q_])
                if a0 not in amap:
                    amap[a0] = len(axes)
                    axes.append({"order": int(L_["order"][q_]), "guide": None, "born": int(L_["born"][q_]), "dead": True})
                add["pos"].append(base_ + Pn[q_])
                add["parent"].append(where[L_["pk"]] if pr_[q_] < 0 else int(new_i[pr_[q_]]))
                add["radius"].append(max(float(rd[q_]) * dk["shrink"], 0.0015))
                add["order"].append(int(L_["order"][q_]))
                add["born"].append(int(L_["born"][q_]))
                add["axis"].append(amap[a0])
                add["key"].append(_child(np.uint64(L_["key"][q_]), 80))
        m_ = len(add["pos"])
        if m_:
            out["pos"] = np.vstack([out["pos"], np.asarray(add["pos"])])
            out["parent"] = np.concatenate([out["parent"], np.asarray(add["parent"], np.int32)])
            out["radius"] = np.concatenate([out["radius"], add["radius"]])
            out["order"] = np.concatenate([out["order"], np.asarray(add["order"], out["order"].dtype)])
            out["born"] = np.concatenate([out["born"], np.asarray(add["born"], out["born"].dtype)])
            out["axis"] = np.concatenate([out["axis"], np.asarray(add["axis"], out["axis"].dtype)])
            out["key"] = np.concatenate([out["key"], np.asarray(add["key"], np.uint64)])
            for k_, val in (("tip", False), ("leafy", False), ("main", True), ("pin", False)):
                out[k_] = np.concatenate([out[k_], np.full(m_, val)])
            out["dead"] = np.concatenate([out["dead"], np.ones(m_, bool)])
            out["shade_dead"] = np.concatenate([np.zeros(n, bool), np.ones(m_, bool)])  # (not an artist's dead wood)
            n += m_
            out["ends"] = np.bincount(out["parent"][1:], minlength=n) == 0
            for i_ in range(n - m_, n):
                axes[int(out["axis"][i_])].setdefault("node", i_)
    # nothing lies under the ground: wood that drooped into it lies along it
    gz_ = ground_at(s, out["pos"][:, :2]) + 0.03 + out["radius"]
    low_ = (out["pos"][:, 2] < gz_) & (out["order"] > 0)
    out["pos"][low_, 2] = gz_[low_]
    grounded_ = int(low_.sum())
    cut_n = 0
    for vol in prunes:  # cuts on the finished tree: nothing else changes
        if "from_year" in vol:
            continue
        P_, o_ = out["pos"], out["order"]
        if "under" in vol:  # nothing hangs under this height (the trunk stays)
            c_ = (o_ > 0) & (P_[:, 2] < float(vol["under"]))
        elif "below" in vol:  # limbs that leave the trunk under this height
            c_ = (~out["main"]) & (o_ == 1) & (P_[out["parent"], 2] < float(vol["below"]))
        else:
            c_ = _inside(P_, vol)
        c_ &= ~out["pin"]
        if c_.any():
            before = n
            subset(~c_)
            cut_n += before - n
    dead_log = []
    for dd in s.get("dead") or []:  # dead wood kept on the live tree: a stag-headed oak's antlers, a snag limb
        if "limb" in dd:
            ai_ = find_limb(out, dd["limb"])
            if ai_ is None or "node" not in out["axes"][ai_]:  # (an edit regrew the tree without it: said, not fatal)
                dead_log.append({"what": f"limb {dd['limb']}", "missing": True})
                continue
            m_ = np.zeros(n, bool)
            m_[out["axes"][ai_]["node"]] = True
            if dd.get("from"):  # only past this many metres along it
                nd_ = stout_path(out, out["axes"][ai_]["node"])
                cum_ = np.cumsum(np.linalg.norm(out["pos"][nd_] - out["pos"][out["parent"][nd_]], axis=1))
                m_[:] = False
                later = nd_[cum_ >= float(dd["from"])]
                if len(later):
                    m_[later[0]] = True
        elif "under" in dd or "below" in dd:
            raise ValueError("dead takes box, sphere, above or a limb")
        else:
            m_ = _inside(out["pos"], dd)
            m_[:2] = False
        for i_ in range(2, n):
            m_[i_] |= m_[out["parent"][i_]]
        out["dead"] |= m_
        out["leafy"] = out["leafy"] & ~m_
        gone = m_ & (out["radius"] < float(dd.get("min_radius", 0.012)))
        zs_ = out["pos"][m_][:, 2] if m_.any() else np.zeros(1)
        before_ = n
        if gone.any():
            subset(~gone)
        dead_log.append({"what": f"limb {dd['limb']}" if "limb" in dd else next(f"{k_} {dd[k_]}" for k_ in ("above", "box", "sphere") if k_ in dd),
                         "nodes": int(m_.sum()), "broken_off": int(before_ - n), "low": round(float(zs_.min()), 1), "high": round(float(zs_.max()), 1)})
    dec = s.get("decay")
    if dec and dec.get("min_radius"):
        subset(out["radius"] >= float(dec["min_radius"]), leafless=True)
    out["stats"] = {"nodes": int(n), "steps": steps, "height_m": round(out["height"], 2),
                    "trunk_diameter_m": round(float(2 * out["radius"][1]) if n > 1 else 0, 3),
                    "max_order": int(out["order"].max()), "grow_s": round(time.perf_counter() - t0, 3),
                    "pruned_nodes": int(cut_n), "cuts": cut_log, "dead": dead_log, "on_ground": grounded_,
                    "dead_stubs": int(out["dead"].sum()) if dead_log_ else 0}
    return out
