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


class Growth:
    """What one plant's growth carries from stage to stage: the arguments of `grow`, then what each stage sets for
    the ones after it. A stage reads and writes it as `gx.<name>`; what a stage only uses itself is a local there.
    grow itself sets, before the first stage:
      s, h, t0
    _setting sets:
      unit, steps, yps, seed, sa, sb, sd, env, tilt, wind, wdir, wstr, g0u, gvu, clear_u, forces, stand, dead_log_,
      prunes, cuts, cut_log, bolls, envl
    _guides sets:
      guides, replaced
    _seedling sets:
      T, axes
    _seasons sets:
      ring_l, step, n, closed, m_
    _wood sets:
      out
    _dead_wood sets:
      subset
    """

    def __init__(self, **arguments):
        self.__dict__.update(arguments)


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
    gx = Growth(spec=spec, unit_scale=unit_scale, log=log, s=s, h=h, t0=t0)
    _setting(gx)
    _guides(gx)
    _seedling(gx)
    _seasons(gx)
    _wood(gx)
    _dead_wood(gx)
    return _finish(gx)


def _setting(gx):
    """What the growth is given: the unit, the steps and the seed, the shadow's numbers, the light, wind, ground and stand
    of its environment, the forces, the steps each cut is made at."""
    gx.unit = gx.h["unit"] * (gx.unit_scale or 1.0)
    gx.steps = steps_of(gx.s)
    gx.yps = gx.h["years_per_step"]
    gx.seed = np.uint64(int(gx.s["seed"]) * 2654435761 % (1 << 62) + 12345)
    gx.sa, gx.sb, gx.sd = gx.h["shadow"]
    gx.sd = int(gx.sd)
    gx.env = gx.s.get("environment") or {}
    light = _norm(np.asarray(gx.env.get("light", [0, 0, 1]), float))
    gx.tilt = (-light[0] / max(light[2], 0.3), -light[1] / max(light[2], 0.3))  # shadows fall away from the light
    gx.wind = gx.env.get("wind")
    gx.wdir = _compass(gx.wind["from"]) * -1 if gx.wind else None  # the way it blows
    gx.wstr = float(gx.wind.get("strength", 0.5)) if gx.wind else 0.0
    g_ = gx.env.get("ground") or {}  # the ground in growth units: z = g0u + [x, y] . gvu
    gx.g0u = float(g_.get("level", 0.0)) / gx.unit
    gx.gvu = np.zeros(2)
    if g_.get("slope"):
        t_ = np.asarray(g_.get("toward", [1, 0]), float)
        gx.gvu = -math.tan(math.radians(float(g_["slope"]))) * t_ / max(np.linalg.norm(t_), 1e-9)
    gx.clear_u = float(gx.h["ground_clear"]) / gx.unit
    gx.forces = [(np.asarray(f["dir"], float) * float(f.get("strength", 1.0)), f.get("orders")) for f in gx.s.get("forces") or []]
    gx.stand = gx.env.get("stand") if gx.env.get("setting") in ("forest", "stand", "edge") or gx.env.get("stand") else None
    if gx.env.get("setting") in ("forest", "edge") and gx.stand is None:
        gx.stand = {}
    if gx.env.get("setting") == "edge":  # a stand's edge: closed behind, open to one side (foliage down that side only)
        gx.stand = {**gx.stand, "open_side": gx.env.get("open_side", gx.stand.get("open_side", [1, 0]))}
    gx.dead_log_ = []  # limbs the shade killed: (the trunk node's key, direction, girth, step)
    gx.prunes = gx.s.get("prune") or []
    gx.cuts = []
    for c in gx.s.get("cuts") or []:  # the steps each cut is made at
        y, last_y = float(c["year"]), float(c.get("until_year", gx.s["age"]))
        ys = [y]
        while c.get("every") and ys[-1] + float(c["every"]) <= last_y:
            ys.append(ys[-1] + float(c["every"]))
        gx.cuts.append(({int(round(q / gx.yps)) for q in ys}, c))
    gx.cut_log = []
    gx.bolls = {}  # node key -> swelling: where a pollard is cut again and again the wood heals into a knuckled head
    gx.envl = gx.s.get("envelope")


def _guides(gx):
    """The guides: each path in metres made growth units, with the step it starts at; the shoots a guide replaces."""

    # guides: paths in metres -> units; each starts at a step
    gx.guides = []
    for name, g in (gx.s.get("guides") or {}).items():
        pts, cum = _path(np.asarray(g["path"], float) / gx.unit, smooth=not g.get("straight"))
        st = int(round(g.get("from_year", 0) / gx.yps))
        until = g.get("until_year")
        en = int(round(until / gx.yps)) if until is not None else None
        gx.guides.append({"name": name, "pts": pts, "cum": cum, "start": st, "end": en, "s": 0.0, "node": -1,
                       "vigour": float(g.get("vigour", 1.0)), "done": False, "free": bool(g.get("free", False)),
                       "on": g.get("on"), "bare": float(g.get("bare", 0.0))})
    gx.guides.sort(key=lambda g: (g["start"], g["name"]))
    # a limb taken over as a guide: the shoot it was grown from is not made again (its lineage key)
    gx.replaced = np.array([int(k) for g in (gx.s.get("guides") or {}).values() for k in (g.get("replaces") or [])], np.uint64)


def _seedling(gx):
    """The foot and the first internode of each stem (straight up, more stems leaning out round it), or a drawn trunk
    as the seedling."""

    gx.T = _Nodes()
    gx.T.add(1, key=_mix(gx.seed), tip=False, guide=-1, R=np.eye(3))
    gx.axes = [{"order": 0, "node": 1, "guide": None}]
    trunk = next((g for g in gx.guides if g["start"] == 0 and np.linalg.norm(g["pts"][0]) < 1.5), None)
    if trunk is None:  # the first internode: straight up
        gx.T.add(1, pos=[0, 0, 1.0], off=[0, 0, 1.0], parent=0, main=True, key=_child(_mix(gx.seed), 0), tip=True,
              nb=0, guide=-1, R=np.eye(3), vig=1.0)
        for si_ in range(1, int(gx.h["stems"])):  # more stems from the same foot, leaning out round it
            a_ = 2.399963 * si_ + 6.283 * float(_u(_child(_mix(gx.seed), 300), 1))
            t_ = math.radians(float(gx.h["stem_angle"]) * (0.6 + 0.8 * float(_u(_child(_mix(gx.seed), 300 + si_), 2))))
            d_ = [math.sin(t_) * math.cos(a_), math.sin(t_) * math.sin(a_), math.cos(t_)]
            gx.axes.append({"order": 0, "node": gx.T.n, "guide": None, "born": 0})
            gx.T.add(1, pos=d_, off=d_, parent=0, main=True, key=_child(_mix(gx.seed), 300 + si_), tip=True,
                  nb=0, guide=-1, R=np.eye(3), vig=1.0, axis=len(gx.axes) - 1)
    else:  # a drawn trunk: its path is the seedling
        trunk.update(node=0, axis=0)
        gx.axes[0]["guide"] = trunk["name"]


def _seasons(gx):
    """The growth itself, one step after another: the cuts made at this step, 1. light, 2. bud fate, 4. shedding and
    pruning (on last step's light), 3. shoots. One loop: a stage begins only at a statement of `grow` itself."""

    def new_axis(order, guide=None):
        gx.axes.append({"order": int(order), "guide": guide, "born": gx.step})
        return len(gx.axes) - 1

    lam_young = list(gx.h["apical"])
    gx.ring_l = gx.h["ring"] if isinstance(gx.h["ring"], (list, tuple)) else [gx.h["ring"]]  # (per order, or one number for all wood)
    gx.step = 0
    tip_life = any(gx.h["tip_life"])
    slowing = any(gx.h["slowing"])
    for gx.step in range(gx.steps):
        for when, c in gx.cuts:  # a cut made now: the wood goes, the stubs sprout (pollard, coppice, a lopped limb)
            if gx.step not in when or gx.T.n < 3:
                continue
            Pm_ = gx.T.pos * gx.unit
            if "under" in c:
                hit = (gx.T.order > 0) & (Pm_[:, 2] < float(c["under"]))
            elif "below" in c:
                hit = (~gx.T.main) & (gx.T.order == 1) & (Pm_[gx.T.parent, 2] < float(c["below"]))
            else:
                hit = _inside(Pm_, c)
            hit[:2] = False
            gone = hit.copy()
            par_ = gx.T.parent
            for i in range(2, gx.T.n):
                gone[i] |= gone[par_[i]]
            if not gone.any():
                gx.cut_log.append({"year": round(gx.step * gx.yps, 1), "nodes": 0, "stubs": 0})
                continue
            first_ = gone & ~gone[par_]
            stubs = np.unique(par_[first_])
            new = gx.T.keep(~gone)
            for g in gx.guides:
                if g["node"] >= 0:
                    g["node"] = int(new[g["node"]])
                    if g["node"] < 0:
                        g["done"] = True
            stubs = new[stubs]
            stubs = stubs[stubs > 0]
            if float(c.get("boll", 1.0)) > 1.0:
                for q_ in stubs:
                    k_b = int(gx.T.key[q_])
                    gx.bolls[k_b] = min(gx.bolls.get(k_b, 1.0) + (float(c["boll"]) - 1.0) * 0.5, float(c["boll"]))
            k_sp = int(c.get("sprouts", 4))
            if k_sp:
                more = [stubs]
                for _ in range(int(c.get("sprout_nodes", 1)) - 1):  # ... and the nodes just under the cut
                    q = gx.T.parent[more[-1]]
                    more.append(q[q > 0])
                sp = np.unique(np.concatenate(more))
                if len(sp) > 12:  # (re-cutting a head leaves a stub per rod: only the stoutest dozen sprout again)
                    sp = sp[np.lexsort((gx.T.born[sp], gx.T.order[sp]))[:12]]
                gx.T.nb[sp] = k_sp
                gx.T.budstep[sp] = gx.step
                gx.T.starve[sp] = 0
            gx.cut_log.append({"year": round(gx.step * gx.yps, 1), "nodes": int(gone.sum()), "stubs": int(len(stubs))})
        gx.n = gx.T.n
        P = gx.T.pos
        age_t = (gx.step + 1) / gx.steps
        lam = np.array(lam_young, float)
        if gx.h.get("apical_old") is not None:
            f0, f1 = gx.h["apical_fade"]
            w = float(np.clip((age_t - f0) / max(f1 - f0, 1e-6), 0, 1))
            lam[0] = lam[0] + w * (gx.h["apical_old"] - lam[0])
        # ---- 1. light
        leafy = (gx.step - gx.T.born) < gx.h["leaf_steps"]
        leafy[0] = False
        cell = 1.0
        lo = P.min(0) - (gx.sd + 3)
        hi = P.max(0) + (gx.sd + 3)
        while np.prod((hi - lo) / cell) > 6e6:
            cell *= 1.5
        dims = tuple(np.ceil((hi - lo) / cell).astype(int) + 1)
        wl = np.clip(gx.T.vig.astype(float), 0.05, 1.5)
        S = _shadow(P[leafy] / cell, lo / cell, dims, gx.sa, gx.sb, gx.sd, gx.tilt, wl[leafy], tail=float(gx.h["shadow_tail"]))
        ij = np.clip(((P - lo) / cell).astype(np.int64), 1, np.array(dims) - 2)
        s_here = S[ij[:, 0], ij[:, 1], ij[:, 2]]
        Qn = np.clip(1.0 - s_here + gx.sa * leafy * wl, 0.0, 1.0)
        Sg = ndimage.gaussian_filter(S, 1.5)  # (the raw grid's gradient stacks shoots in voxel layers)
        G = np.stack([Sg[ij[:, 0] + 1, ij[:, 1], ij[:, 2]] - Sg[ij[:, 0] - 1, ij[:, 1], ij[:, 2]],
                      Sg[ij[:, 0], ij[:, 1] + 1, ij[:, 2]] - Sg[ij[:, 0], ij[:, 1] - 1, ij[:, 2]],
                      Sg[ij[:, 0], ij[:, 1], ij[:, 2] + 1] - Sg[ij[:, 0], ij[:, 1], ij[:, 2] - 1]], 1)
        V = -G / (2 * gx.sa)
        V = V / np.maximum(np.linalg.norm(V, axis=1, keepdims=True), 1.0)  # at most a unit pull
        Pm = P * gx.unit
        top = P[:, 2].max()
        if gx.stand is not None:  # a closed stand: the canopy's top rises with the tree; light falls off below it and away from the gap
            gap = gx.stand.get("gap", 0.18) * max(top, 4.0)
            if gx.env.get("spacing") or gx.stand.get("spacing"):  # m between the stand's trees: its own share of the canopy
                gap = min(gap, 0.55 * float(gx.env.get("spacing") or gx.stand["spacing"]) / gx.unit)
            depth = gx.stand.get("depth", 0.35) * max(top, 4.0)
            zc = top * gx.stand.get("height", 1.0)
            r = np.linalg.norm(P[:, :2], axis=1)
            side = np.clip((r - gap) / max(0.5 * gap, 1e-6), 0, 1) * np.clip((zc - P[:, 2]) / max(depth, 1e-6), 0, 1.5)  # (over a whole gap width, crowns 4 m apart interlocked 8 m wide)
            # the canopy's own shade deepens steadily below its top (a step at one depth made a stand tree's crown all or nothing:
            # live to the ground or a tuft, on a hair of `stand_shed`)
            below = np.clip((zc - P[:, 2]) / max(2.0 * depth, 1e-6), 0, 1) * gx.stand.get("floor", 0.8)
            gx.closed = np.ones(gx.n)
            if gx.stand.get("open_side") is not None:  # the open side keeps its light
                od = _norm(np.asarray(list(gx.stand["open_side"])[:2], float))
                we = np.clip(0.5 - 0.5 * (P[:, :2] @ od) / max(gap, 1e-6), 0, 1)
                side, below = side * we, below * we
                gx.closed = we
            Qn = np.clip(Qn - gx.stand.get("strength", 1.0) * (side + below), 0, 1)
            V[:, :2] -= 0.5 * gx.stand.get("strength", 1.0) * side[:, None] * _norm(np.c_[P[:, 0], P[:, 1]] + 1e-9)
        for nb_ in gx.env.get("neighbours") or []:  # crowns beside it: {"at": [x, y], "height", "radius"} (m)
            c = np.asarray(nb_["at"], float)
            d = np.linalg.norm(Pm[:, :2] - c, axis=1)
            hh = nb_.get("height", 10.0) * min(1.0, age_t * 1.2)
            sh = np.clip(1 - d / (nb_.get("radius", 4.0) * 2.0), 0, 1) * np.clip((hh - Pm[:, 2]) / (0.3 * hh + 1e-6), 0, 1)
            Qn = np.clip(Qn - sh, 0, 1)
            V[:, :2] += 0.6 * sh[:, None] * _norm(Pm[:, :2] - c)
        if gx.envl is not None:
            out_ = _envelope(Pm, gx.envl)
            Qn = np.clip(Qn - gx.envl.get("strength", 1.0) * out_, 0, 1)
        if gx.wind:  # the windward side's buds suffer
            cen = P[leafy].mean(0) if leafy.any() else P.mean(0)
            rad = max(np.linalg.norm(P[:, :2] - cen[:2], axis=1).max(), 1.0)
            ex = np.clip(-((P - cen) @ gx.wdir) / rad, 0, 1) * np.clip(P[:, 2] / max(top, 1), 0, 1)
            Qn = np.clip(Qn * (1 - gx.wstr * ex), 0, 1)
        cut = np.zeros(gx.n, bool)
        for vol in gx.prunes:  # (a prune with no from_year is a cut on the finished tree: after the loop)
            if "from_year" in vol and gx.step >= int(round(vol["from_year"] / gx.yps)):
                if "under" in vol:
                    c_ = (gx.T.order > 0) & (Pm[:, 2] < float(vol["under"]))
                elif "below" in vol:  # clear the trunk: laterals leaving it under this height
                    c_ = (~gx.T.main) & (gx.T.order == 1) & (Pm[gx.T.parent, 2] < float(vol["below"]))
                else:
                    c_ = _inside(Pm, vol)
                cut |= c_ & ~gx.T.pin
        Qn[cut] = 0
        # ---- 2. bud fate
        dead_bud = (gx.step - np.maximum(gx.T.born, gx.T.budstep)) > gx.h["bud_life"]
        gx.T.nb[dead_bud] = 0
        qtip = Qn * gx.T.tip
        qlat = Qn * gx.T.nb
        Q = np.zeros(gx.n)
        size = np.zeros(gx.n, np.int64)
        _collect(gx.T.parent, qtip + qlat, Q, size)
        v = np.zeros(gx.n)
        vtip = np.zeros(gx.n)
        vlat = np.zeros(gx.n)
        _distribute(gx.T.parent, gx.T.main, gx.T.order, Q, qtip, qlat, lam, gx.h["vigour"] * Q[0], v, vtip, vlat)
        # ---- 4 (before growth, on last step's light). shedding and pruning
        dead = np.zeros(gx.n, bool)
        thr_ = np.full(gx.n, float(gx.h["shed"]))
        if gx.stand is not None:  # a stand's shade-bearers self-prune (`stand_shed`); on an edge's open side they keep their skirt
            thr_ = thr_ + gx.h["stand_shed"] * gx.closed
        # wood past its last living branch (no tip, no bud, no leaf beyond it) is dead: it goes like any shaded branch
        # (a limb whose own tip had stopped trailed on for decades as a bare sagging snake)
        LQ = np.zeros(gx.n)
        _collect(gx.T.parent, leafy.astype(float), LQ, np.zeros(gx.n, np.int64))
        cut |= (Q <= 0) & (LQ <= 0) & (gx.T.order > 0) & ~gx.T.pin & ((gx.step - gx.T.born) >= gx.h["shed_age"] + 2)
        _shed(gx.T.parent, gx.T.main, gx.T.born, gx.T.pin, Q, size, cut, gx.step, thr_, gx.h["shed_age"], dead)
        if dead.any():
            # the pipe model remembers what it carried
            area = np.zeros(gx.n)
            _pipe(gx.T.parent, gx.T.mem, 1.0, gx.h["pipe"], area)
            first = dead & ~dead[gx.T.parent]
            if gx.h["dead_keep"]:  # a limb off the trunk dies but stays for years: its wood is remembered as it was, and
                # put back at the end as dead wood, as far decayed as its years (twigs fallen, broken back, drooping)
                roots_ = first & (gx.T.order == 1) & (gx.T.order[gx.T.parent] == 0)
                if gx.stand is not None:  # in a stand the branches a limb loses stay on it too: its dead twigs
                    roots_ |= first & (gx.T.order >= 2)
                roots_ = np.flatnonzero(roots_)
                if len(roots_):
                    own = np.full(gx.n, -1)
                    own[roots_] = roots_
                    for j_ in np.flatnonzero(dead):  # (parents come first)
                        if own[j_] < 0:
                            own[j_] = own[gx.T.parent[j_]]
                    rad_m = area * gx.h["tip_radius"] + (gx.step + 1 - gx.T.born) * (gx.yps * _per(gx.ring_l, gx.T.order))
                    for i_ in roots_:
                        ix = np.flatnonzero(own == i_)[:vegetation.DEAD_NODES]
                        loc = {int(q_): k_ for k_, q_ in enumerate(ix)}
                        gx.dead_log_.append({"pk": int(gx.T.key[gx.T.parent[i_]]), "step": gx.step, "key": gx.T.key[ix].copy(), "root": int(gx.T.order[i_]),
                                          "pos": (gx.T.pos[ix] - gx.T.pos[gx.T.parent[i_]]) * gx.unit,
                                          "par": np.array([loc.get(int(gx.T.parent[q_]), -1) for q_ in ix]), "rad": rad_m[ix].copy(),
                                          "order": gx.T.order[ix].copy(), "axis": gx.T.axis[ix].copy(), "born": gx.T.born[ix].copy()})
            np.add.at(gx.T.mem, gx.T.parent[first], 0.6 * area[first] ** gx.h["pipe"])
            keep = ~dead
            new = gx.T.keep(keep)
            for g in gx.guides:
                if g["node"] >= 0:
                    g["node"] = int(new[g["node"]])
                    if g["node"] < 0:
                        g["done"] = True
            vtip, vlat, V, Qn = vtip[keep], vlat[keep], V[keep], Qn[keep]
            gx.n = gx.T.n
        # ---- 3. shoots
        order = gx.T.order.astype(int)
        nmax = _per(gx.h["shoot_max"], order).astype(int)
        nt = np.minimum(np.floor(vtip).astype(int), nmax) * gx.T.tip
        if gx.h["leader"] and age_t <= gx.h["leader_until"]:
            lead = gx.T.tip & (gx.T.order == 0)
            nt[lead] = np.maximum(nt[lead], int(gx.h["leader"]))
        gnode = {g["node"]: g for g in gx.guides if g["node"] >= 0 and not g["done"]}
        for i in gnode:
            nt[i] = 0  # a guide's tip grows along its path, below
        per_bud = np.where(gx.T.nb > 0, vlat / np.maximum(gx.T.nb, 1), 0)
        ob = np.minimum(order + 1, 99)
        can = (_u(gx.T.key, 7) < _per(gx.h["bud_break"], ob)) | (gx.T.budstep > 0)  # (a cut's sprouts always can)
        if gx.h["bud_each"]:
            can = can | (gx.T.nb > 1)  # (each bud is drawn below)
        nl = np.minimum(np.floor(per_bud).astype(int), _per(gx.h["shoot_max"], ob).astype(int)) * (gx.T.nb > 0) * can
        nl[order >= gx.h["max_order"]] = 0
        # starving tips die
        st = gx.T.starve
        hungry = gx.T.tip & (nt == 0)
        st[hungry] = np.minimum(st[hungry] + 1, 200)
        st[~hungry] = 0
        gx.T.tip[(st > 3) & (gx.T.order > 0) & ~gx.T.pin] = False
        if tip_life:  # determinate axes: after their years they stop reaching (their buds may still break)
            ab = np.fromiter((a.get("born", 0) for a in gx.axes), np.int64, len(gx.axes))
            lf_ = _per(gx.h["tip_life"], order)
            old = gx.T.tip & (lf_ > 0) & (gx.step - ab[gx.T.axis] >= lf_) & ~gx.T.pin
            gx.T.tip[old] = False
            nt[old] = 0

        par = gx.T.parent
        dir_here = _norm(gx.T.pos - gx.T.pos[par])
        dir_here[0] = [0, 0, 1]
        up = np.array([0.0, 0.0, 1.0])

        def shoots(src, count, d0, order_new, keys, vres, is_main, phi0, axis_ids):
            """Grow `count[k]` metamers from node src[k] in direction d0[k]; returns the last node of each."""
            last = src.copy()
            d = d0.copy()
            # a shoot keeps turning the way it was turning: crookedness as curves, not a kink at every node
            turn = np.where(is_main[:, None], dir_here[src] - dir_here[par[src]], 0.0)
            alive = np.arange(len(src))
            ln = (0.45 + 0.55 * np.clip(vres / _per(gx.h["shoot_max"], order_new), 0, 1)) * _per(gx.h["length"], order_new)
            ln = ln * (1 + _per(gx.h["uneven"], order_new) * (2 * _u(_mix(axis_ids.astype(np.uint64) + gx.seed), 9) - 1))
            if slowing:  # an old axis creeps
                sl_ = _per(gx.h["slowing"], order_new)
                born_ = np.fromiter((gx.axes[a_].get("born", 0) for a_ in axis_ids), np.float64, len(axis_ids))
                ln = np.where(sl_ > 0, ln / (1 + (gx.step - born_) / np.maximum(sl_, 1e-9)), ln)
            if gx.h["limb_pace"]:  # no side shoot outgrows the leader's pace at this age
                s0_ = _per(gx.h["slowing"], np.zeros(1, int))[0]
                lead_ = _per(gx.h["shoot_max"], np.zeros(1, int))[0] * _per(gx.h["length"], np.zeros(1, int))[0] / (1 + (gx.step / s0_ if s0_ > 0 else 0.0))
                cap_ = _per(gx.h["limb_pace"], order_new) * lead_ / np.maximum(_per(gx.h["shoot_max"], order_new), 1)
                ln = np.where(order_new > 0, np.minimum(ln, cap_), ln)
            eta = _per(gx.h["tropism"], order_new)
            jit = _per(gx.h["jitter"], order_new)
            pl = _per(gx.h["plagio"], order_new)
            el = np.radians(_per(gx.h["elevation"], order_new))
            nbuds = _per(gx.h["buds"], np.minimum(order_new, 99)).astype(int)
            whorl = _per(gx.h["whorl"], order_new).astype(bool)
            div = np.radians(_per(gx.h["divergence"], order_new))
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
                dd = d[a] + w1 * (gx.h["light"] * V[src[a]] + eta[a, None] * up + jit[a, None] * 0.6 * rnd) + mom[:, None] * turn[a]
                fw = _per(gx.h["force_orders"], order_new[a])[:, None]
                for fv, fo in gx.forces:
                    m_ = np.ones(len(a), bool) if fo is None else np.isin(order_new[a], fo)
                    dd = dd + (m_[:, None] * fw if fo is None else m_[:, None]) * fv
                if gx.wind:
                    dd = dd + 0.5 * gx.wstr * gx.wdir * fw
                dd = _norm(dd)
                if pl[a].any():  # toward a set elevation, keeping the heading
                    hz = _norm(dd * [1, 1, 0] + 1e-9 * d[a])
                    tgt = hz * np.cos(el[a])[:, None] + up * np.sin(el[a])[:, None]
                    dd = _norm(dd + pl[a, None] * (tgt - dd))
                p0 = gx.T.pos[last[a]]
                o = dd * ln[a, None]
                # the ground: nothing grows into it. A hanging shoot stops over it (`ground_clear`); any other slides
                # along it, and its own pull to the light turns it up from there
                end = p0 + o
                fl_ = gx.g0u + end[:, :2] @ gx.gvu + gx.clear_u
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
                Rp = gx.T.R[last[a]]
                off = np.einsum("nji,nj->ni", Rp, o)  # into the parent's rest frame
                endm = (count[a] == j + 1)
                nbn = np.where(whorl[a] & ~endm, 0, nbuds[a])
                nbn[order_new[a] >= gx.h["max_order"]] = 0
                nbn[(order_new[a] == 0) & ((p0[:, 2] + o[:, 2]) * gx.unit < gx.h["clear"])] = 0
                ids = gx.T.add(len(a), pos=p0 + o, off=off, parent=last[a], order=order_new[a],
                            main=(is_main[a] if j == 0 else True), born=gx.step, key=kj, tip=False, nb=nbn,
                            phi=phi0[a] + (j + 1) * div[a], R=Rp, guide=-1, axis=axis_ids[a], vig=ln[a])
                last[a] = ids
                turn[a] = dd - d[a]
                d[a] = dd
            return last

        # terminal shoots
        ti = np.flatnonzero(nt > 0)
        if len(ti):
            gx.T.tip[ti] = False
            last = shoots(ti, nt[ti], dir_here[ti], order[ti], gx.T.key[ti], vtip[ti], np.ones(len(ti), bool), gx.T.phi[ti],
                          gx.T.axis[ti].copy())
            gx.T.tip[last] = True
        # lateral shoots: every bud of the node breaks together (a whorl)
        li = np.flatnonzero(nl > 0)
        if len(li):
            src, bud = [], []
            for b in range(int(gx.T.nb[li].max())):
                gx.m_ = li[gx.T.nb[li] > b]
                src.append(gx.m_)
                bud.append(np.full(len(gx.m_), b))
            src, bud = np.concatenate(src), np.concatenate(bud)
            o_new = order[src] + 1
            a_ = dir_here[src]
            plane = _per(gx.h["plane"], o_new).astype(bool)
            ref = np.where(np.abs(a_[:, 2:3]) > 0.95, np.array([[1.0, 0, 0]]), up[None])
            u_ = _norm(np.cross(a_, ref))
            w_ = np.cross(u_, a_)
            phi = np.where(plane, np.round(gx.T.phi[src] / math.pi) * math.pi, gx.T.phi[src]) + 2 * math.pi * bud / gx.T.nb[src]
            ang = np.radians(_per(gx.h["angle"], o_new - 1)) * (0.85 + 0.3 * _u(gx.T.key[src], 20 + 1))  # by the PARENT's order
            d0 = a_ * np.cos(ang)[:, None] + (u_ * np.cos(phi)[:, None] + w_ * np.sin(phi)[:, None]) * np.sin(ang)[:, None]
            keys = _child(gx.T.key[src], 100 + bud)
            if gx.h["bud_each"]:
                ok_ = (gx.T.nb[src] <= 1) | (_u(keys, 7) < _per(gx.h["bud_break"], o_new)) | (gx.T.budstep[src] > 0)
                src, bud, o_new, d0, keys = src[ok_], bud[ok_], o_new[ok_], d0[ok_], keys[ok_]
            if len(gx.replaced):
                ok_ = ~np.isin(_child(keys, 10), gx.replaced)
                src, bud, o_new, d0, keys = src[ok_], bud[ok_], o_new[ok_], d0[ok_], keys[ok_]
            ax0 = len(gx.axes)
            for k_ in range(len(src)):
                new_axis(o_new[k_])
            first = gx.T.n + np.arange(len(src))  # (pass 0 makes every shoot's first metamer, in order)
            last = shoots(src, nl[src], d0, o_new, keys, per_bud[src], np.zeros(len(src), bool),
                          _u(keys, 5) * 2 * math.pi, ax0 + np.arange(len(src)))
            for k_, f_ in enumerate(first):
                gx.axes[ax0 + k_]["node"] = int(f_)
            gx.T.tip[last] = True
            gx.T.nb[li] = 0
        # ---- guides
        for gi, g in enumerate(gx.guides):
            if g["done"] or gx.step < g["start"]:
                continue
            pts, cum = g["pts"], g["cum"]
            if g["node"] < 0:  # attach: a lateral from the nearest wood, the stoutest of what's about equally near
                dist = np.linalg.norm(gx.T.pos - pts[0], axis=1)
                cand = np.ones(gx.T.n, bool)
                if g["on"]:  # ... of the guide (or "trunk") it's drawn on
                    on = next((q for q in gx.guides if q["name"] == g["on"]), None)
                    cand = (gx.T.order == 0) if g["on"] == "trunk" else \
                        (gx.T.axis == on["axis"]) if on is not None and "axis" in on else cand
                    if not cand.any():
                        cand = np.ones(gx.T.n, bool)
                dist = np.where(cand, dist, 1e9)
                near = np.flatnonzero(dist <= dist.min() + 0.75)
                near = near[gx.T.order[near] == gx.T.order[near].min()]
                base = int(near[np.argmin(dist[near])])
                g["node"], g["axis"] = base, new_axis(int(gx.T.order[base]) + 1, g["name"])
                g["first"] = True
            left = cum[-1] - g["s"]
            remaining = max((g["end"] if g["end"] is not None else gx.steps) - gx.step, 1)
            want = left / remaining * g["vigour"] if g["end"] is not None else 2.2 * g["vigour"]
            nm = int(max(1, min(math.ceil(want / 1.0), 8)))
            ln = min(left, max(want, 0.6)) / nm
            o_g = gx.axes[g["axis"]]["order"]
            node = g["node"]
            if not g.get("first") and gx.T.guide[node] == gi:  # (never the wood it leaves: that was killing a young trunk's leader)
                gx.T.tip[node] = False
            for j in range(nm):
                if g["s"] >= cum[-1] - 1e-6:
                    break
                g["s"] = min(g["s"] + ln, cum[-1])
                p = _along(pts, cum, g["s"])
                kj = _child(_child(gx.seed, 5000 + gi), int(round(g["s"] * 16)))
                nbn = int(_per(gx.h["buds"], o_g)) if o_g < gx.h["max_order"] else 0
                if (o_g == 0 and p[2] * gx.unit < gx.h["clear"]) or g["s"] * gx.unit < g["bare"]:
                    nbn = 0  # (a drawn trunk has its clear bole too; a limb may be drawn bare for its first metres)
                i_ = gx.T.add(1, pos=p, pinpos=p, off=p - gx.T.pos[node], parent=node, order=o_g,
                           main=(not g.pop("first", False)) or o_g == 0, born=gx.step, key=kj, tip=False, nb=nbn,
                           phi=gx.T.phi[node] + math.radians(float(_per(gx.h["divergence"], o_g))), R=np.eye(3),
                           guide=gi, axis=g["axis"], pin=not g["free"], vig=1.0)[0]
                gx.axes[g["axis"]].setdefault("node", int(i_))
                node = int(i_)
            g["node"] = node
            gx.T.tip[node] = True
            if g["s"] >= cum[-1] - 1e-6:
                g["done"] = True  # the path is drawn: the tip grows on by itself
        # ---- 5. widths, bending
        gx.n = gx.T.n
        area = np.zeros(gx.n)
        _pipe(gx.T.parent, gx.T.mem, 1.0, gx.h["pipe"], area)
        rad = area * (gx.h["tip_radius"] / gx.unit) + (gx.step + 1 - gx.T.born) * (gx.yps * _per(gx.ring_l, gx.T.order) / gx.unit)
        leafy = (gx.step - gx.T.born) < gx.h["leaf_steps"]
        if gx.h["sag"] > 0:
            _pose(gx.T.parent, gx.T.off, gx.T.pin, gx.T.pinpos, gx.T.order, rad, leafy, gx.T.theta, gx.h["sag"], gx.h["sag_max"],
                  0.0, gx.T.pos, gx.T.R, gx.g0u + 0.03 / gx.unit, gx.gvu[0], gx.gvu[1])
        if gx.log:
            gx.log(f"step {gx.step}: {gx.T.n} nodes, top {gx.T.pos[:, 2].max() * gx.unit:.1f} m")


def _wood(gx):
    """The grown tree as arrays in metres: radii from the pipe model and the rings, the foot's flare, leafy wood, the axes;
    then the trunk's and the limbs' girths where the spec or the stand sets them."""

    gx.n = gx.T.n
    area = np.zeros(gx.n)
    _pipe(gx.T.parent, gx.T.mem, 1.0, gx.h["pipe"], area)
    radius = area * gx.h["tip_radius"] + (gx.steps - gx.T.born) * (gx.yps * _per(gx.ring_l, gx.T.order))
    radius[0] = radius[1] if gx.n > 1 else radius[0]
    pos = gx.T.pos * gx.unit
    # the foot flares
    radius = radius * (1 + (gx.h["flare"] - 1) * np.exp(-pos[:, 2] / max(gx.h["flare_height"], 1e-6)) * (gx.T.order == 0))
    leafy = (gx.steps - 1 - gx.T.born) < gx.h["leaf_steps"]
    leafy[0] = False
    kids = np.bincount(gx.T.parent[1:], minlength=gx.n)
    first = {}
    for i in range(1, gx.n):
        first.setdefault(int(gx.T.axis[i]), i)
    for i, a in enumerate(gx.axes):
        a.pop("node", None)
        if i in first:
            a["node"] = first[i]
    ax_names = {}
    for i, a in enumerate(gx.axes):
        if a.get("guide"):
            ax_names[a["guide"]] = i
    gx.out = {"pos": pos, "parent": gx.T.parent.copy(), "radius": radius, "order": gx.T.order.copy(), "born": gx.T.born.copy(),
           "axis": gx.T.axis.copy(), "key": gx.T.key.copy(), "tip": gx.T.tip.copy(), "leafy": leafy, "main": gx.T.main.copy(),
           "pin": gx.T.pin.copy(), "ends": kids == 0, "unit": gx.unit, "steps": gx.steps, "axes": gx.axes, "guides": ax_names,
           "height": float(pos[:, 2].max()), "spec": gx.s}
    if gx.s.get("trunk_diameter"):  # girth in metres: thick wood scaled to it, twigs left as they are
        r1, tip_r = float(radius[1]), 3 * gx.h["tip_radius"]
        k_ = 0.5 * float(gx.s["trunk_diameter"]) / max(r1, 1e-9)
        w_ = np.clip((radius - tip_r) / max(r1 - tip_r, 1e-9), 0, 1) ** 0.5
        if gx.s.get("limb_diameter"):  # the trunk alone
            w_ = w_ * (gx.T.order == 0)
        gx.out["radius"] = radius = radius * (1 + (k_ - 1) * w_)
        if gx.s.get("trunk_taper") is not None:  # a column: the trunk keeps its girth to its top, whatever it carries
            tr = np.flatnonzero(gx.T.order == 0)
            zt = max(float(pos[tr, 2].max()), 1e-6)
            want = 0.5 * float(gx.s["trunk_diameter"]) * (1 - float(gx.s["trunk_taper"]) * pos[tr, 2] / zt)
            radius[tr] = np.maximum(radius[tr], want) if not gx.s.get("cuts") else want
            gx.out["radius"] = radius
    elif gx.stand is not None and (gx.env.get("spacing") or gx.stand.get("spacing")) and gx.h["sdi_max"]:
        # a stand's stems are as stout as its stocking allows (Reineke 1933: N x (dbh / 25 cm)^1.6 <= the species' most):
        # the pipe model and the ring sized a tree by its own wood alone, and 3 m apart stood 42 cm stems (173 m2 / ha)
        sp_ = float(gx.env.get("spacing") or gx.stand["spacing"])
        cap = 0.25 * (float(gx.h["sdi_max"]) / (1e4 / sp_ ** 2)) ** (1 / 1.6) * (1.0 if gx.stand.get("open_side") is None else 1.25)
        tr = np.flatnonzero(gx.T.order == 0)
        if len(tr) > 2 and pos[tr, 2].max() > 1.3:
            dbh = 2 * float(np.interp(1.3, pos[tr, 2], radius[tr]))
            if dbh > cap:
                r1, tip_r = 0.5 * dbh, 3 * gx.h["tip_radius"]
                w_ = np.clip((radius - tip_r) / max(r1 - tip_r, 1e-9), 0, 1) ** 0.5
                gx.out["radius"] = radius = radius * (1 + (cap / dbh - 1) * w_)
                gx.out["stand_dbh_cap"] = round(cap, 3)
    if gx.s.get("limb_diameter") and (gx.T.order == 1).any():  # limbs sized by themselves: a fat trunk under ordinary limbs
        o1 = np.flatnonzero((gx.T.order == 1) & (gx.T.order[gx.T.parent] == 0))
        rl, tip_r = float(radius[o1].max()), 3 * gx.h["tip_radius"]
        k_ = 0.5 * float(gx.s["limb_diameter"]) / max(rl, 1e-9)
        w_ = np.clip((radius - tip_r) / max(rl - tip_r, 1e-9), 0, 1) ** 0.5 * (gx.T.order > 0)
        gx.out["radius"] = radius = radius * (1 + (k_ - 1) * w_)


def _dead_wood(gx):
    """`subset` (the tree kept to some of its nodes), the cut ends swollen, the limbs the shade killed as dead wood on
    the trunk."""

    def subset(keep, leafless=False):
        keep = keep.copy()
        keep[:2] = True
        par0 = gx.out["parent"]
        for i in range(2, len(keep)):  # (parents come first: a cut takes everything it carries)
            keep[i] &= keep[par0[i]]
        new = -np.ones(len(keep), np.int64)
        new[keep] = np.arange(int(keep.sum()))
        for k_ in ("pos", "radius", "order", "born", "axis", "key", "tip", "leafy", "main", "pin", "dead", "shade_dead"):
            gx.out[k_] = gx.out[k_][keep]
        par = new[par0[keep]]
        par[0] = 0
        gx.out["parent"] = par.astype(np.int32)
        gx.n = int(keep.sum())
        gx.out["ends"] = np.bincount(par[1:], minlength=gx.n) == 0
        if leafless:
            gx.out["leafy"] = np.zeros(gx.n, bool)
        gx.out["height"] = float(gx.out["pos"][:, 2].max())
        first = {}
        for i in range(1, gx.n):
            first.setdefault(int(gx.out["axis"][i]), i)
        for i, a in enumerate(gx.axes):
            a.pop("node", None)
            if i in first:
                a["node"] = first[i]
    gx.subset = subset

    if gx.bolls:  # swell the cut ends, easing out ~4 radii down the wood that carries them
        r_ = gx.out["radius"]
        fac = np.ones(gx.n)
        for i_ in np.flatnonzero(np.isin(gx.out["key"], np.array(list(gx.bolls), np.uint64))):
            if gx.out["order"][i_] > 1:
                continue  # (a head, not every rod's stub)
            k_b, q_, d_ = gx.bolls[int(gx.out["key"][i_])], int(i_), 0.0
            reach = max(4.0 * float(r_[i_]), 0.3)
            while q_ > 0 and d_ < reach:
                fac[q_] = max(fac[q_], 1 + (k_b - 1) * (1 - d_ / reach) ** 2)
                p_ = int(gx.out["parent"][q_])
                d_ += float(np.linalg.norm(gx.out["pos"][q_] - gx.out["pos"][p_]))
                q_ = p_
        gx.out["radius"] = r_ * fac
    gx.out["dead"] = np.zeros(gx.n, bool)
    gx.out["shade_dead"] = np.zeros(gx.n, bool)
    if gx.dead_log_:  # the limbs the shade killed within `dead_keep` years, as dead wood on the trunk
        where = {int(k_): i_ for i_, k_ in enumerate(gx.out["key"])}
        add = {k_: [] for k_ in ("pos", "parent", "radius", "order", "born", "axis", "key")}
        keep_y = float(gx.h["dead_keep"])
        dk = {**vegetation.DEAD, **(gx.s.get("deadwood") or {})}
        n_add = 0
        for L_ in sorted(gx.dead_log_, key=lambda e_: (e_["root"], e_["step"])):  # (limbs first: their dead branches hang on them)
            age_ = (gx.steps - L_["step"]) * gx.yps
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
            base_ = gx.out["pos"][w_] if w_ < gx.n else np.asarray(add["pos"][w_ - gx.n])
            new_i = -np.ones(m0, np.int64)
            amap = {}
            for q_ in np.flatnonzero(ok_):
                new_i[q_] = gx.n + n_add
                where.setdefault(int(L_["key"][q_]), gx.n + n_add)
                n_add += 1
                a0 = int(L_["axis"][q_])
                if a0 not in amap:
                    amap[a0] = len(gx.axes)
                    gx.axes.append({"order": int(L_["order"][q_]), "guide": None, "born": int(L_["born"][q_]), "dead": True})
                add["pos"].append(base_ + Pn[q_])
                add["parent"].append(where[L_["pk"]] if pr_[q_] < 0 else int(new_i[pr_[q_]]))
                add["radius"].append(max(float(rd[q_]) * dk["shrink"], 0.0015))
                add["order"].append(int(L_["order"][q_]))
                add["born"].append(int(L_["born"][q_]))
                add["axis"].append(amap[a0])
                add["key"].append(_child(np.uint64(L_["key"][q_]), 80))
        gx.m_ = len(add["pos"])
        if gx.m_:
            gx.out["pos"] = np.vstack([gx.out["pos"], np.asarray(add["pos"])])
            gx.out["parent"] = np.concatenate([gx.out["parent"], np.asarray(add["parent"], np.int32)])
            gx.out["radius"] = np.concatenate([gx.out["radius"], add["radius"]])
            gx.out["order"] = np.concatenate([gx.out["order"], np.asarray(add["order"], gx.out["order"].dtype)])
            gx.out["born"] = np.concatenate([gx.out["born"], np.asarray(add["born"], gx.out["born"].dtype)])
            gx.out["axis"] = np.concatenate([gx.out["axis"], np.asarray(add["axis"], gx.out["axis"].dtype)])
            gx.out["key"] = np.concatenate([gx.out["key"], np.asarray(add["key"], np.uint64)])
            for k_, val in (("tip", False), ("leafy", False), ("main", True), ("pin", False)):
                gx.out[k_] = np.concatenate([gx.out[k_], np.full(gx.m_, val)])
            gx.out["dead"] = np.concatenate([gx.out["dead"], np.ones(gx.m_, bool)])
            gx.out["shade_dead"] = np.concatenate([np.zeros(gx.n, bool), np.ones(gx.m_, bool)])  # (not an artist's dead wood)
            gx.n += gx.m_
            gx.out["ends"] = np.bincount(gx.out["parent"][1:], minlength=gx.n) == 0
            for i_ in range(gx.n - gx.m_, gx.n):
                gx.axes[int(gx.out["axis"][i_])].setdefault("node", i_)


def _finish(gx):
    """Wood lifted off the ground, the prunes on the finished tree, dead wood kept on the live tree, decay, the stats:
    the result."""
    # nothing lies under the ground: wood that drooped into it lies along it
    gz_ = ground_at(gx.s, gx.out["pos"][:, :2]) + 0.03 + gx.out["radius"]
    low_ = (gx.out["pos"][:, 2] < gz_) & (gx.out["order"] > 0)
    gx.out["pos"][low_, 2] = gz_[low_]
    grounded_ = int(low_.sum())
    cut_n = 0
    for vol in gx.prunes:  # cuts on the finished tree: nothing else changes
        if "from_year" in vol:
            continue
        P_, o_ = gx.out["pos"], gx.out["order"]
        if "under" in vol:  # nothing hangs under this height (the trunk stays)
            c_ = (o_ > 0) & (P_[:, 2] < float(vol["under"]))
        elif "below" in vol:  # limbs that leave the trunk under this height
            c_ = (~gx.out["main"]) & (o_ == 1) & (P_[gx.out["parent"], 2] < float(vol["below"]))
        else:
            c_ = _inside(P_, vol)
        c_ &= ~gx.out["pin"]
        if c_.any():
            before = gx.n
            gx.subset(~c_)
            cut_n += before - gx.n
    dead_log = []
    for dd in gx.s.get("dead") or []:  # dead wood kept on the live tree: a stag-headed oak's antlers, a snag limb
        if "limb" in dd:
            ai_ = find_limb(gx.out, dd["limb"])
            if ai_ is None or "node" not in gx.out["axes"][ai_]:  # (an edit regrew the tree without it: said, not fatal)
                dead_log.append({"what": f"limb {dd['limb']}", "missing": True})
                continue
            gx.m_ = np.zeros(gx.n, bool)
            gx.m_[gx.out["axes"][ai_]["node"]] = True
            if dd.get("from"):  # only past this many metres along it
                nd_ = stout_path(gx.out, gx.out["axes"][ai_]["node"])
                cum_ = np.cumsum(np.linalg.norm(gx.out["pos"][nd_] - gx.out["pos"][gx.out["parent"][nd_]], axis=1))
                gx.m_[:] = False
                later = nd_[cum_ >= float(dd["from"])]
                if len(later):
                    gx.m_[later[0]] = True
        elif "under" in dd or "below" in dd:
            raise ValueError("dead takes box, sphere, above or a limb")
        else:
            gx.m_ = _inside(gx.out["pos"], dd)
            gx.m_[:2] = False
        for i_ in range(2, gx.n):
            gx.m_[i_] |= gx.m_[gx.out["parent"][i_]]
        gx.out["dead"] |= gx.m_
        gx.out["leafy"] = gx.out["leafy"] & ~gx.m_
        gone = gx.m_ & (gx.out["radius"] < float(dd.get("min_radius", 0.012)))
        zs_ = gx.out["pos"][gx.m_][:, 2] if gx.m_.any() else np.zeros(1)
        before_ = gx.n
        if gone.any():
            gx.subset(~gone)
        dead_log.append({"what": f"limb {dd['limb']}" if "limb" in dd else next(f"{k_} {dd[k_]}" for k_ in ("above", "box", "sphere") if k_ in dd),
                         "nodes": int(gx.m_.sum()), "broken_off": int(before_ - gx.n), "low": round(float(zs_.min()), 1), "high": round(float(zs_.max()), 1)})
    dec = gx.s.get("decay")
    if dec and dec.get("min_radius"):
        gx.subset(gx.out["radius"] >= float(dec["min_radius"]), leafless=True)
    gx.out["stats"] = {"nodes": int(gx.n), "steps": gx.steps, "height_m": round(gx.out["height"], 2),
                    "trunk_diameter_m": round(float(2 * gx.out["radius"][1]) if gx.n > 1 else 0, 3),
                    "max_order": int(gx.out["order"].max()), "grow_s": round(time.perf_counter() - gx.t0, 3),
                    "pruned_nodes": int(cut_n), "cuts": gx.cut_log, "dead": dead_log, "on_ground": grounded_,
                    "dead_stubs": int(gx.out["dead"].sum()) if gx.dead_log_ else 0}
    return gx.out
