"""The grown tree: its arrays in metres and its girths, the dead wood, the prunes on the finished tree, the stats.
The last three stages of `grow` (vegetation_grow.grow calls them in order; vegetation.py has the overview)."""
from __future__ import annotations

import math
import time

import numpy as np

from . import vegetation
from .vegetation_kernels import _child, _pipe, _u
from .vegetation_tree import _inside, _norm, _per, find_limb, ground_at, stout_path

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
