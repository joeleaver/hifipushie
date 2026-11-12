"""`cut`: the groom cut into cards; the flow row, tuck under, the hairline row. Part of hair clumps (hair_clumps.py has the overview)."""
from __future__ import annotations

import hashlib

import numpy as np

from . import hair_clumps
from .hair_clumps import _cen_of, _ss, _unit, features, kmeans, strands
from .hair_clumps_fit import (
    _crown_fill, _grade_fill, _root_seat, _under_envelope, card_offset, crown_loops, envelope, fit, layer_offset,
)
from .hair_clumps_part import _part_root, arch_row, part_cover, part_visible, strand_part

def cut(D: dict, locks: list, C, S: dict, side_of=None, seed: int = 0, layers: dict | None = None,
        triangles: int = 20000) -> list:
    """Cards cut by clumps, per class and layer (see LAYERS). `side_of(points) -> (side -1/0/+1, distance to the
    part m)` for strand roots, or None. Each card: hair_cards' card keys + "strands" (indices into `St` = the
    module-level strands this cut used, kept on the first card as "_St") and "draw" (share of its strands drawn)."""
    St = strands(D, locks)
    hair_clumps._HOOKS.clear()
    hair_clumps._FILL_BACK.clear()
    env = envelope(St, C, pct=hair_clumps.ENV_PCT)
    env_side = envelope(St, C, pct=hair_clumps.SIDE_ENV_PCT) if hair_clumps.SIDE_ENV_PCT != hair_clumps.ENV_PCT else None
    env_g = envelope(St, C, pct=hair_clumps.ENV_PCT, grade=hair_clumps.GRADE_SLOPE) if hair_clumps.GRADE_SLOPE > 0 else None
    hair_clumps._GRADED.clear()
    layers = layers or hair_clumps.LAYERS
    rng = np.random.default_rng(seed + 31)
    out = []
    side = np.zeros(len(St["len"]))
    if hair_clumps.PART_FROM_STRANDS and side_of is not None:  # (c2: never where the groom says "parting none": Garrett's G88a
        # swept back with no part, the strands' near-even vote (21.7k / 24.2k) made one at the centre front, cards
        # trimmed PART_GAP off it: the M-shaped notch in the hairline, hl.py notch +4.9 % vs the groom's -0.7)
        # the strands' own part first: the spec's default line (x = 3 cm) sat 3 cm off a tied
        # groom's emergent centre part (b25 part dip at col 285, the groom's at 245; top roots sweep -x left of x = 0,
        # +x right of it, t18/partprobe.py)
        side_of = strand_part(St, C) or side_of
    side_vis = side_of  # (round 37) the top cover rows' part: only where the groom shows one (PART_VISIBLE)
    if side_of is not None:
        sd, dist = side_of(St["root"])
        side = np.where(dist < hair_clumps.PART_SPLIT, sd, 0.0)
        if hair_clumps.PART_DUMP:  # (round 37, diagnostics) the head strands + the part at their roots, for part_visible probes
            hd_ = St["cls"] == "head"
            np.savez_compressed(hair_clumps.PART_DUMP, Q=St["Q"][hd_][:, ::2].astype(np.float32), root=St["root"][hd_],
                                sd=sd[hd_], dist=dist[hd_], C=np.asarray(C, float))
        if hair_clumps.PART_VISIBLE:
            side_vis = part_visible(St, C, side_of)
            on_ = np.isfinite(dist) & (dist < hair_clumps.PART_GAP)
            if on_.any():
                dp_ = side_vis.dip(St["root"][on_], sd[on_], dist[on_])
                dp_ = dp_[np.isfinite(dp_)]
                if len(dp_):
                    print(f"part visible: {int((dp_ >= hair_clumps.PART_DIP).sum())} of {len(dp_)} roots on the part show a >= "
                          f"{hair_clumps.PART_DIP * 1000:.0f} mm notch in the outline along it (p10 / p50 / p90 "
                          f"{np.percentile(dp_, 10) * 1000:.1f} / {np.percentile(dp_, 50) * 1000:.1f} / "
                          f"{np.percentile(dp_, 90) * 1000:.1f} mm)", flush=True)
    loop = crown_loops(St, C)
    for cls in ("head", "tail", "face"):
        idx = np.nonzero((St["cls"] == cls) & ~(loop & (cls == "head")))[0]
        if not len(idx):
            continue
        F = features(St, idx)
        per_card = max(4.0, 2.0 * float(np.median(St["len"][idx])) / float(S.get("segment", 0.008)))
        # strands rooted near the part are clustered per side: no card spans the part (a soft side key in the
        # features still let k-means mix them)
        # a tail's clumps never mix its locks: each wavy lock is a visible S-clump, and averaged with a neighbour of
        # another phase its wave cancelled (the tail read as one flat sheet, reviews c5-c6)
        grp = side[idx] if cls == "head" else St["lock"][idx].astype(float) if cls == "tail" else np.zeros(len(idx))
        for la, (tshare, max_hw, share) in enumerate(layers[cls]):
            if cls == "face":  # each face-framing lock: its own clumps of FACE_PER hairs (they frame the face)
                lab = np.zeros(len(idx), int)
                off = 0
                for li in np.unique(St["lock"][idx]):
                    sel = St["lock"][idx] == li
                    k_ = max(1, int(round(int(locks[li].get("hairs") or 4) / hair_clumps.FACE_PER)))
                    lab[sel] = kmeans(F[sel], k_, seed + 13) + off
                    off = int(lab[sel].max()) + 1
            else:
                k_all = max(1, int(round(tshare * triangles / per_card)))
                lab = np.zeros(len(idx), int)
                off = 0
                for gv in np.unique(grp):
                    sel = grp == gv
                    lab[sel] = kmeans(F[sel], max(1, int(round(k_all * sel.mean()))), seed + 7 * la) + off
                    off = int(lab[sel].max()) + 1
            todo = [(idx[lab == g], 0) for g in np.unique(lab)]
            rng_long = np.random.default_rng(seed + 991 + 13 * la)  # (its own stream: TAIL_JIT's draws unchanged)
            while todo:
                it_ = todo.pop(0)
                mem, dep = it_[:2]
                long_ = len(it_) > 2
                if (cls == "tail" and hair_clumps.TAIL_LONG > 0 and not long_ and rng_long.uniform() < hair_clumps.TAIL_LONG):  # (round 44) see TAIL_LONG
                    ln_ = St["len"][mem]
                    sel_ = mem[ln_ >= np.percentile(ln_, 100.0 * (1.0 - hair_clumps.TAIL_LONG_TOP))]
                    if len(sel_) >= hair_clumps.TAIL_LONG_MIN:
                        todo.append((sel_, dep, True))
                lk = locks[int(np.bincount(St["lock"][mem]).argmax())]
                # (hanging hair runs on to its longest strands' tips: ended where a quarter were left, Tess's tail
                # ended in a straight cut 3 cm short)
                # (and is its outline: a tail's outer strands spread past the 90th percentile; at it the cards' tail
                # was 0.8 of the strands' width)
                end_ = 0.0 if long_ else hair_clumps.TAIL_END + (hair_clumps.TAIL_END_JIT * rng.uniform() if cls == "tail" else 0.0)
                c = fit(St["Q"][mem], _cen_of(C, lk.get("core")), end_share=(hair_clumps.FACE_END if cls == "face" else end_) if cls != "head" else hair_clumps.HEAD_END,
                        max_hw=max_hw, spread=97.0 if cls == "tail" else 90.0, reference=cls == "head",
                        tip_taper=hair_clumps.TIP_TAPER_TAIL if cls == "tail" else hair_clumps.TIP_TAPER,
                        medoid=(hair_clumps.MEDOID_TAIL_TOP if la == len(hair_clumps.LAYERS["tail"]) - 1 else hair_clumps.MEDOID_TAIL) if cls == "tail"
                        else hair_clumps.MEDOID_FACE if cls == "face" else 0.0,
                        per_strand=hair_clumps.HW_PER_STRAND if cls == "tail" else 0.0)
                if c is None:  # (c6) no stretch where half its strands run: a clump spread ALONG the flow (behind the ears:
                    # short strands rooted in a row down the hair's run, 64-68 % of those hairline strands had no card):
                    # split it in two (k-means on the same features) and fit each half
                    if dep < hair_clumps.SPLIT_DEPTH and len(mem) >= hair_clumps.SPLIT_MIN:
                        sub = kmeans(features(St, mem), 2, seed + 17 * (dep + 1))
                        if 0 < int(sub.sum()) < len(sub):
                            todo += [(mem[sub == 0], dep + 1), (mem[sub == 1], dep + 1)]
                    continue
                if cls == "head" and hair_clumps.HOOK_RISE > 0 and la >= hair_clumps.HOOK_LAYER_MIN:  # (round 26) a head card that comes down and turns back UP (the two
                    # hooked top-layer flaps at the front crown's outline, t25/crown_layers.png) ends where it turned
                    z_ = np.asarray(c["P"], float)[:, 2]
                    ka = int(np.argmax(z_))
                    rm = np.minimum.accumulate(z_[ka:])
                    up = np.nonzero(z_[ka:] - rm > hair_clumps.HOOK_RISE)[0]
                    if len(up):
                        k1 = ka + int(np.argmin(z_[ka:ka + int(up[0]) + 1])) + 1
                        if k1 < 4:
                            continue
                        n_ = len(c["P"])
                        for k_ in ("P", "T", "N", "X", "bend", "hw", "sn", "u", "share", "out", "rad", "s"):
                            if np.ndim(c.get(k_)) and len(c[k_]) == n_:
                                c[k_] = np.asarray(c[k_])[:k1]
                        hair_clumps._HOOKS.append((la, n_, k1))
                back_ = False
                if cls == "head" and hair_clumps.ARCH_FILL and side_of is not None:  # (round 35, ARCH_FILL (a)) a root end running back:
                    # no visible part there, the card keeps its root in the centre strip
                    P_ = np.asarray(c["P"], float)
                    kk_ = min(len(P_) - 1, max(1, int(round(hair_clumps.PART_REACH / hair_clumps.STEP))))
                    dv_ = P_[kk_] - P_[0]
                    back_ = abs(dv_[0]) / max(float(np.linalg.norm(dv_)), 1e-9) < hair_clumps.PART_SIDEWAYS
                    # (round 36) part-safe: only behind the part's back end (no voters near the root: distance inf)
                    # (round 37) ... or where the groom shows no part there (PART_VISIBLE: side_vis)
                    back_ = back_ and not bool(np.isfinite(side_vis(P_[:1])[1][0]))
                    if back_:
                        hair_clumps._FILL_BACK.append(float(P_[0, 0] - np.asarray(C, float)[0]))
                if cls == "head" and side_of is not None and not back_:  # its root stays PART_GAP off the part
                    _, dpart = side_of(c["P"])
                    near = np.nonzero(dpart >= hair_clumps.PART_GAP)[0]
                    k0 = int(near[0]) if len(near) else len(c["P"])
                    if k0 > 0:
                        if len(c["P"]) - k0 < 4:
                            continue
                        for k_ in ("P", "T", "N", "X", "bend", "hw", "sn", "u", "share", "out", "rad"):
                            if np.ndim(c.get(k_)):
                                c[k_] = np.asarray(c[k_])[k0:]
                        c["i0"] += k0
                        c["s"] = c["s"][k0:] - c["s"][k0]
                    if hair_clumps.PART_ROOT_REACH > 0:  # its root brought back to the part, leaving it sideways
                        _part_root(c, side_of, C)
                # coverage under, mid at the clump, top over it (the clump's spread along its normal)
                # (a tail's upper layers stand out round its core: at the clump's mean the cards' tail was 0.75 of the
                # strands' width in profile, a slab)
                yo = card_offset(c, la, len(layers[cls]), cls, C) * (hair_clumps.FACE_YO if cls == "face" else 1.0)
                P = c["P"] + c["N"] * yo[:, None]
                if cls in ("head", "face"):
                    cc_ = {"P": P, "X": c["X"], "hw": c["hw"]}
                    _under_envelope(cc_, env, C, env_side if cls == "head" else None)
                    P = cc_["P"]
                if cls == "head" and hair_clumps.ROOT_SEAT > 0:  # (round 27) the card's root end eased down onto the scalp
                    P = _root_seat(P, c["s"], St["root"][mem], C)
                if cls == "head" and hair_clumps.CROWN_FILL > 0:  # (round 31) the head's layers raised toward the strands' envelope (after
                    # the root seat: seated roots were most of the shortfall over the crown)
                    P = _crown_fill(P, la, len(layers[cls]), env, C, c["s"])
                if cls == "head" and env_g is not None:  # (c13) the back's step graded (GRADE_SLOPE)
                    P_ = _grade_fill(P, la, len(layers[cls]), env, env_g, C, c["s"])
                    hair_clumps._GRADED.append(float(np.max(np.linalg.norm(P_ - P, axis=1))) if len(P) else 0.0)
                    P = P_
                kind = "baked"
                u = (c["i0"] * hair_clumps.STEP + c["s"]) / max(float(np.percentile(St["len"][mem], 95)), 0.02)
                out.append({"P": P, "X": c["X"], "N": c["N"], "T": c["T"], "bend": c["bend"], "hw": c["hw"],
                            "rad": np.asarray(c["rad"], float) + yo, "u": u, "s": c["s"], "kind": kind, "layer": la, "cls": cls,
                            "prio": la + (-0.8 if cls == "face" else -0.4 if cls == "tail" else 0.0)
                            + 0.1 * rng.uniform(),
                            "cval": 1.0, "value": 1.0, "lock": lk["name"], "sn": c["sn"],
                            "strands": mem, "draw": share, "s0": c["i0"] * hair_clumps.STEP, "wisp": cls == "face",
                            "edge": bool(lk.get("at_hairline")) or cls == "face"})
    if hair_clumps.PART_COVER and side_of is not None:  # (round 33) the part's cover row, over the side cards
        cov = part_cover(St, C, side_of, env, np.nonzero((St["cls"] == "head") & ~loop)[0], seed)
        for c_ in cov:
            c_["lock"] = locks[c_["lock"]]["name"]
        out.extend(cov)
        print(f"part cover: {len(cov)} cards", flush=True)
    if hair_clumps.ARCH:  # (round 34) the crown arch row, over the dome
        arc = arch_row(St, C, np.nonzero((St["cls"] == "head") & ~loop)[0], seed, side_of=side_vis)
        if hair_clumps.ARCH_FILL:
            fb_ = np.abs(np.asarray(hair_clumps._FILL_BACK))
            print(f"fill: {len(fb_)} head cards keep their back-running roots ({int((fb_ < 0.015).sum())} rooted within "
                  f"15 mm of the centre line)", flush=True)
        for c_ in arc:
            c_["lock"] = locks[c_["lock"]]["name"]
        out.extend(arc)
    ft = S.get("flow_top")
    ft = ft and {**hair_clumps.FLOW_TOP, **(ft if isinstance(ft, dict) else {})}
    if ft and triangles >= float(ft["min_triangles"]):  # (c9) a top layer of a few long cards along the groom's flow, the others' ends tucked under it
        fl = flow_row(St, C, ft, len(layers["head"]) - 1, triangles, seed)
        tuck_under(out, fl, C, float(ft["tuck"]))
        out += fl
    hr = S.get("hairline_row")
    hr = hr and {**hair_clumps.HAIRLINE_ROW, **(hr if isinstance(hr, dict) else {})}
    if hr and triangles >= float(hr["min_triangles"]):  # (c9) a dedicated row of short cards along the temple / sideburn hairline band
        out += hairline_row(St, C, hr, env, triangles, seed, env_side=env_side)
    # flyaways: single strands that break the outline, a card each (Epic: one card per flyaway strand)
    idx = np.nonzero(St["cls"] == "single")[0]
    if len(idx):
        far = np.zeros(len(idx))
        others = St["Q"][St["cls"] != "single"][:, ::4].reshape(-1, 3)
        others = others[np.isfinite(others[:, 0])]
        if len(others):
            from scipy.spatial import cKDTree
            tr = cKDTree(others[:: max(1, len(others) // 200000)])
            for i, j in enumerate(idx):
                q = St["Q"][j]
                q = q[np.isfinite(q[:, 0])]
                far[i] = float(tr.query(q)[0].max()) if len(q) else 0.0
        front_ = (St["root"][idx][:, 1] < float(np.asarray(C)[1]) - hair_clumps.FLY_FRONT) if hair_clumps.FLY_FRONT > 0 else np.zeros(len(idx), bool)
        far = np.where(far > np.where(front_, hair_clumps.FLY_FRONT_FAR, hair_clumps.FLY_FAR), 0.0, far)  # (hairs standing 2 cm+ off the head read as spikes on cards)
        far = np.where(front_ & (far > 0), far + 1.0, far)  # (round 44) FLY_FRONT: first in the budget
        for i, j in enumerate(idx):
            lk_ = locks[int(St["lock"][j])]
            if front_[i]:
                continue
            if St["root"][j][2] > float(np.asarray(C)[2]) + (hair_clumps.FLY_CROWN_FREE if lk_.get("off_head") else hair_clumps.FLY_CROWN):
                far[i] = 0.0  # (the halo over the crown as cards: a crest of thin strips, reviews c5-c6; a few single
                # hairs there are below what a 25k card hero can show: left to the strands' look)
        for i, j in enumerate(idx):  # (looping hairs read as stiff arcs over the crown as cards, review c5)
            q = St["Q"][j][np.isfinite(St["Q"][j][:, 0])]
            if len(q) < 3 or np.linalg.norm(q[-1] - q[0]) < hair_clumps.FLY_STRAIGHT * St["len"][j]:
                far[i] = 0.0
        n = max(1, min(int(hair_clumps.FLY_SHARE * len(idx)),
                       int(hair_clumps.FLY_TRIS * triangles / max(4.0, 2.0 * float(np.median(St["len"][idx])) / float(S.get("segment", 0.008))))))
        for j in idx[np.argsort(-far)[:n]]:
            lk = locks[int(St["lock"][j])]
            c = fit(St["Q"][j:j + 1], _cen_of(C, None), end_share=1.0, max_hw=hair_clumps.FLY_W)
            if c is None:
                continue
            c["hw"] = hair_clumps.FLY_W * (1 - 0.6 * _ss(c["s"] / max(c["s"][-1], 1e-6)))  # (tapers to its tip)
            out.append({"P": c["P"], "X": c["X"], "N": c["N"], "T": c["T"], "bend": c["bend"], "hw": c["hw"],
                        "u": (c["i0"] * hair_clumps.STEP + c["s"]) / max(float(St["len"][j]), 0.02), "s": c["s"], "kind": "baked", "layer": 3, "cls": "fly", "prio": 3.0,
                        "cval": 1.0, "value": 1.0, "lock": lk["name"], "sn": 0.0, "strands": np.array([j]),
                        "draw": 1.0, "s0": c["i0"] * hair_clumps.STEP, "fly": True})
    if hair_clumps._HOOKS:
        print(f"hook cut: {len(hair_clumps._HOOKS)} head cards (layer, stations kept / of): "
              f"{', '.join(f'L{a} {k}/{n}' for a, n, k in hair_clumps._HOOKS[:12])}", flush=True)
    if out:
        out[0]["_St"] = St
    if hair_clumps._GRADED:
        g_ = np.asarray(hair_clumps._GRADED)
        print(f"grade: {int((g_ > 5e-4).sum())} of {len(g_)} head cards raised onto the graded back (max {1000 * g_.max():.1f} mm)", flush=True)
    return out


# (c11) `rise`: a row card's stations (past its root seat) raised this share of the way out to the SIDE envelope
# (SIDE_ENV_PCT, ENV_UNDER under it), and held under the side envelope instead of the top's ENV_PCT one: the groom's
# temple-to-ear sheet stands off the head (c10L front width 168 px vs 182 at 1 m), the row lay on it
# (c11) `low_el`: the band's strands whose entry (root, or a passing strand's first station in the band) lies under this
# el are clustered on their own (`low_cards` per side at 20k triangles, default `cards`; half width up to `low_hw`,
# default `hw`): c10's passing strands joined the band's 24 clusters a side and the clusters' cards followed the upper
# strands, so the groom's sheet in front of the ear (el ~-30..-10) stayed bare
# (c10) `pass`: also the head strands that PASS THROUGH the band (a station in it, rooted up to `pass_el`): Garrett's
# silver temple sheet is long hair from above lying down over the band, few roots in it. Such a strand's card starts
# `pass_back` m before it enters the band (cut there, not root-seated). `lit` as FLOW_TOP's (own tile group).
# (`edge`: wear the hairline tile (thin, HL_ALPHA-faded roots); False = the body tiles: c9b with edge on drew sparse thin
# strips in front of the ear, the groom's patch there is a solid sheet)
def _azel(P, C):
    v = np.asarray(P, float) - np.asarray(C, float)
    r = np.maximum(np.linalg.norm(v, axis=-1), 1e-9)
    return np.degrees(np.arctan2(v[..., 0], -v[..., 1])), np.degrees(np.arcsin(np.clip(v[..., 2] / r, -1, 1))), r


def _sweep(St: dict, idx, sx: float) -> np.ndarray:
    """-1 / 0 / +1: a strand's first PART_REACH runs to -x / back (or forward) / +x (|x share| >= sx)."""
    Q = St["Q"][idx]
    k = min(Q.shape[1] - 1, max(1, int(round(hair_clumps.PART_REACH / hair_clumps.STEP))))
    n = np.isfinite(Q[..., 0]).sum(1)
    kk = np.clip(np.minimum(k, n - 1), 0, None)
    d = Q[np.arange(len(idx)), kk].astype(float) - Q[:, 0].astype(float)
    xs = d[:, 0] / np.maximum(np.linalg.norm(d, axis=1), 1e-9)
    return np.where(xs >= sx, 1.0, np.where(xs <= -sx, -1.0, 0.0))


def _card(c, P, la, mem, St, lk, share, prio, **kw) -> dict:
    u = (c["i0"] * hair_clumps.STEP + c["s"]) / max(float(np.percentile(St["len"][mem], 95)), 0.02)
    return {"P": P, "X": c["X"], "N": c["N"], "T": c["T"], "bend": c["bend"], "hw": c["hw"], "rad": np.asarray(c["rad"], float),
            "u": u, "s": c["s"], "kind": "baked", "layer": la, "cls": "head", "prio": prio, "cval": 1.0, "value": 1.0,
            "lock": lk["name"], "sn": c["sn"], "strands": mem, "draw": share, "s0": c["i0"] * hair_clumps.STEP, "wisp": False,
            "edge": bool(lk.get("at_hairline")), **kw}


def _tier_n(n, triangles):
    return max(2, int(round(float(n) * np.sqrt(max(triangles, 1) / 20000.0))))


def flow_row(St: dict, C, o: dict, la: int, triangles: int, seed: int = 0, locks=None) -> list:
    """FLOW_TOP's cards (see there)."""
    C = np.asarray(C, float)
    _, el, _ = _azel(St["root"], C)
    idx = np.nonzero((St["cls"] == "head") & (el > float(o["el"])))[0]
    if len(idx) < hair_clumps.MIN_STRANDS:
        return []
    idx = idx[St["len"][idx] >= np.percentile(St["len"][idx], float(o["len_pct"]))]
    grp = _sweep(St, idx, float(o["sweep_x"]))
    env = envelope(St, C, pct=float(o["pct"]))
    n = _tier_n(o["cards"], triangles)
    out = []
    for gv in np.unique(grp):
        sel = idx[grp == gv]
        if len(sel) < hair_clumps.MIN_STRANDS:
            continue
        k_ = max(1, int(round(n * len(sel) / len(idx) * 3)))  # (n per group on an even three-way split)
        lab = kmeans(features(St, sel), k_, seed + 101)
        for g in np.unique(lab):
            mem = sel[lab == g]
            if len(mem) < hair_clumps.MIN_STRANDS:
                continue
            c = fit(St["Q"][mem], _cen_of(C, None), end_share=float(o["end"]), max_hw=float(o["hw"]), spread=90.0,
                    reference=True, medoid=1.0)
            if c is None:
                continue
            P = np.asarray(c["P"], float)
            X, hw = np.asarray(c["X"], float), np.asarray(c["hw"], float)
            r = np.linalg.norm(P - C, axis=1)
            tg = []
            for E in (P, P - X * hw[:, None], P + X * hw[:, None]):  # (the card AND its edges on / under the surface)
                e, rE = env(E)
                tg.append(e - (rE - r))
            from scipy.ndimage import gaussian_filter1d
            with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
                __import__("warnings").simplefilter("ignore")
                tgt = np.nanmin(np.stack(tg), axis=0) - hair_clumps.ENV_UNDER
            ok_ = np.isfinite(tgt)
            if not ok_.any():
                continue
            tgt = gaussian_filter1d(np.interp(np.arange(len(r)), np.flatnonzero(ok_), tgt[ok_]), 1.5)
            w = _ss(np.clip(np.asarray(c["s"]) / max(float(o["seat"]), 1e-6), 0.0, 1.0)) * float(o["reach"])
            rn = r + w * (tgt - r)  # (onto the outer surface past the seat; the root stays seated)
            P = C + (P - C) * (rn / np.maximum(r, 1e-9))[:, None]
            cc_ = {"P": P}
            P = _root_seat(cc_["P"], c["s"], St["root"][mem], C) if hair_clumps.ROOT_SEAT > 0 else cc_["P"]
            lk = {"name": f"flow{len(out)}"}
            out.append(_card(c, P, la, mem, St, lk, 1.0, la + 0.9 + 0.05 * (len(out) % 2), flow=True,
                             **({"lit": float(o["lit"])} if float(o["lit"]) > 0 else {})))
    print(f"flow top: {len(out)} cards (groups {dict(zip(*np.unique(grp, return_counts=True)))}, strands {len(idx)}, "
          f"length p50 {np.median([c['s'][-1] for c in out]) * 1000 if out else 0:.0f} mm)", flush=True)
    return out


def tuck_under(cards: list, flow: list, C, tuck: float) -> int:
    """Head cards' stations lying under a flow card (within its half width across, nearer than its station along)
    pulled in toward the head's centre to `tuck` m under it (only ever lowered). Returns stations moved."""
    if not flow or not cards:
        return 0
    from scipy.spatial import cKDTree
    C = np.asarray(C, float)
    FP = np.concatenate([np.asarray(f["P"], float) for f in flow])
    FH = np.concatenate([np.asarray(f["hw"], float) for f in flow])
    FT = np.concatenate([np.gradient(np.asarray(f["P"], float), axis=0) for f in flow])
    FT /= np.maximum(np.linalg.norm(FT, axis=1), 1e-12)[:, None]
    FR = np.linalg.norm(FP - C, axis=1)
    U = (FP - C) / FR[:, None]
    tr = cKDTree(U)
    moved = 0
    for c in cards:
        if c.get("cls") != "head" or c.get("fly"):
            continue
        P = np.asarray(c["P"], float)
        r = np.linalg.norm(P - C, axis=1)
        d, j = tr.query((P - C) / r[:, None])
        # across distance on the flow card's surface: the angular offset at its radius, less the along part
        off = (P - C) / r[:, None] * FR[j][:, None] - (FP[j] - C)
        off -= (off * FT[j]).sum(1)[:, None] * FT[j]
        under = (np.linalg.norm(off, axis=1) < FH[j]) & (r > FR[j] - tuck)
        if under.any():
            from scipy.ndimage import gaussian_filter1d
            dr = gaussian_filter1d(np.where(under, r - (FR[j] - tuck), 0.0), 1.0)
            dr = np.maximum(dr, 0.0)
            c["P"] = C + (P - C) * ((r - dr) / r)[:, None]
            moved += int(under.sum())
    print(f"flow top: {moved} stations of the other head cards tucked under it", flush=True)
    return moved


def hairline_row(St: dict, C, o: dict, env, triangles: int, seed: int = 0, env_side=None) -> list:
    """HAIRLINE_ROW's cards (see there)."""
    C = np.asarray(C, float)
    az, el, _ = _azel(St["root"], C)
    a0, a1 = o["az"]
    e0, e1 = o["el"]
    out = []
    n = _tier_n(o["cards"], triangles)
    for sgn in (-1.0, 1.0):
        idx = np.nonzero((St["cls"] == "head") & (sgn * az >= a0) & (sgn * az <= a1) & (el >= e0) & (el <= e1))[0]
        start, enter = {}, {}
        if o.get("pass"):  # (c10) strands that pass through the band: cut from just before they enter it
            Q_ = St["Q"]
            hd = np.nonzero((St["cls"] == "head") & (el > e1) & (el <= float(o["pass_el"])))[0]
            qa, qe, _ = _azel(Q_[hd], C)
            inb = np.isfinite(Q_[hd][..., 0]) & (sgn * qa >= a0) & (sgn * qa <= a1) & (qe >= e0) & (qe <= e1)
            hit = inb.any(1)
            first = np.argmax(inb, 1)
            back = int(round(float(o["pass_back"]) / hair_clumps.STEP))
            for j, f in zip(hd[hit], first[hit]):
                start[int(j)] = max(0, int(f) - back)
                enter[int(j)] = int(f)
            idx = np.r_[idx, hd[hit]]
        if len(idx) < hair_clumps.MIN_STRANDS:
            continue
        groups = [(idx, n, float(o["hw"]))]
        if o.get("low_el") is not None:  # (c11) the low band clustered on its own
            ent = np.array([el[j] if int(j) not in enter else float(_azel(St["Q"][j][enter[int(j)]], C)[1])
                            for j in idx])
            lo = ent < float(o["low_el"])
            groups = [(idx[~lo], n, float(o["hw"])),
                      (idx[lo], _tier_n(o.get("low_cards") or o["cards"], triangles), float(o.get("low_hw") or o["hw"]))]
        todo = []
        for gi_, (ix_, n_, hw_) in enumerate(groups):
            if len(ix_) < hair_clumps.MIN_STRANDS:
                continue
            lab = kmeans(features(St, ix_), min(n_, max(1, len(ix_) // hair_clumps.MIN_STRANDS)), seed + 211 + 7 * gi_)
            todo += [(ix_[lab == g], 0, hw_) for g in np.unique(lab)]
        while todo:
            mem, dep, hw_ = todo.pop(0)
            if len(mem) < hair_clumps.MIN_STRANDS:
                continue
            Qm = St["Q"][mem]
            sh = np.array([start.get(int(j), 0) for j in mem])
            if sh.any():  # (passing strands: their stations from the cut on, the rest padded)
                Qm = np.full_like(Qm, np.nan)
                for i_, (j, k_) in enumerate(zip(mem, sh)):
                    Qm[i_, :Qm.shape[1] - k_] = St["Q"][j][k_:]
            c = fit(Qm, _cen_of(C, None), end_share=hair_clumps.HEAD_END, max_hw=hw_, spread=90.0,
                    reference=True, min_stations=int(o["min_stations"]), min_len=float(o["min_len"]))
            if c is None:  # (short hairs rooted in a row down their own run: split, as the cut's SPLIT_DEPTH)
                if dep < 3 and len(mem) >= 2 * hair_clumps.MIN_STRANDS:
                    sub = kmeans(features(St, mem), 2, seed + 223 + dep)
                    if 0 < int(sub.sum()) < len(sub):
                        todo += [(mem[sub == 0], dep + 1, hw_), (mem[sub == 1], dep + 1, hw_)]
                continue
            la = int(o["layer"])
            yo = layer_offset(c["sn"], la, "head")
            P = c["P"] + c["N"] * yo[:, None]
            rs_ = float(o.get("rise") or 0.0)
            if rs_ > 0 and env_side is not None:  # (c11) out toward the side envelope
                es_, r_ = env_side(P)
                up_ = np.clip(np.nan_to_num(es_ - hair_clumps.ENV_UNDER - r_, nan=0.0), 0.0, None) * rs_
                up_ *= np.clip(np.asarray(c["s"], float) / 0.01, 0.0, 1.0)  # (not at the root)
                P = P + _unit(P - C) * up_[:, None]
            cc_ = {"P": P, "X": c["X"], "hw": c["hw"]}
            _under_envelope(cc_, env, C, env_side if rs_ > 0 else None)
            P = _root_seat(cc_["P"], c["s"], St["root"][mem], C) if (hair_clumps.ROOT_SEAT > 0 and not sh.any()) else cc_["P"]
            out.append(_card(c, P, la, mem, St, {"name": f"hrow{len(out)}", "at_hairline": bool(o["edge"])}, 1.0, la + 0.05,
                             hrow=True, **({"lit": float(o["lit"])} if float(o["lit"]) > 0 else {})))
    print(f"hairline row: {len(out)} cards", flush=True)
    return out


def card_hash(c: dict) -> int:
    return int(hashlib.md5(np.asarray(c["P"], np.float32).tobytes()).hexdigest()[:8], 16)
