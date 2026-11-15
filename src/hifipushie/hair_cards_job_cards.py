"""The cards themselves: cut by visual clumps or clustered from the groom's strands, a short cut's cards, the tail's
core and a loose mass; under shells only the hairline's rows. Two stages of `cards_job` (hair_cards_job.cards_job
calls them in order; hair.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import hair
from .hair import _ss, _unit, dirs
from .hair_groom import inside, part_side_of
from .hair_job import _hcap_vm
from .hair_lockmesh import _hrow_dropped

def _cards(cj):
    """The cards: cut by visual clumps, or clustered from the groom's strands (thinned toward a budget, the part's cover
    row and the crown's arch at the tiers that ask, a short cut's cards over its cap, the tail's core, a loose
    mass), or the locks' own cards when the pictures are drawn. One `if`: a stage begins only at a statement of
    the function."""
    cj.core = None
    cj.clumped = cj.D is not None and not cj.short and cj.S.get("cut") == "clumps"
    cj.St_ = None
    if cj.clumped:  # cards cut by visual clumps across locks and textured from their own strands (hair_clumps.py)
        from . import hair_clumps
        from . import hair_clumps_bake, hair_clumps_cut, hair_clumps_fit, hair_clumps_part
        cj.cards = hair_clumps_cut.cut(cj.D, cj.hair_locks, cj.sc.C, cj.S, part_side_of(cj.sc, cj.g), int(cj.g.get("seed", 0)),
                                triangles=int(hair.CARD_CUT_SHARE * int(cj.budget)) if cj.budget else 20000)
        cj.St_ = cj.cards[0].pop("_St") if cj.cards else None
    elif cj.D is not None:  # cards cut from the groom's own strands, clustered as coarsely as the tier asks
        cj.cards = stamp_cls(cj.hair_cards_clumps.clump_cards(cj.D, cj.hair_locks, cj.sc.C, cj.S, cj.lk, int(cj.g.get("seed", 0))), cj.hair_locks)
    if cj.D is not None:
        if cj.budget and not cj.short and not cj.clumped:
            # a groom with many locks (tesshair7's volume rows, halo, curls: Tess's W18 cut 7,123 cards / 243k
            # triangles for a 40k hero) left the budget to drop whole layers AND whole regions (the tail's cards, every
            # layer over the coverage one: 34 % of her silhouette bare). Cut coarser instead, as an artist would: the
            # coverage layer of every lock must fit in CUT_SHARE of the budget, else the next coarser group, wider cards
            S_ = cj.S
            for _ in range(len(hair.CUT_GROUPS)):
                cov_ = [c_ for c_ in cj.cards if c_["layer"] == 0 and c_["kind"] != "fly"]
                if cj.hair_cards_budget.triangles(cov_, S_, float(S_["segment"]) * 1.5) <= hair.CUT_SHARE * int(cj.budget):
                    break
                gi_ = hair.CUT_GROUPS.index(S_.get("group", "sub")) if S_.get("group", "sub") in hair.CUT_GROUPS else 0
                if gi_ + 1 >= len(hair.CUT_GROUPS):
                    break
                S_ = {**S_, "group": hair.CUT_GROUPS[gi_ + 1], "card_width": float(S_["card_width"]) * 1.4}
                cj.cards = stamp_cls(cj.hair_cards_clumps.clump_cards(cj.D, cj.hair_locks, cj.sc.C, S_, cj.lk, int(cj.g.get("seed", 0))), cj.hair_locks)
            if S_ is not cj.S:
                print(f"hair cards: cut as group {S_['group']!r}, card_width {S_['card_width'] * 1000:.0f} mm (the tier's "
                      f"{cj.S.get('group')!r} cut's coverage layer alone was over {hair.CUT_SHARE:.0%} of {int(cj.budget)} triangles)",
                      flush=True)
                cj.S = {**cj.S, "group": S_["group"], "card_width": S_["card_width"]}
            # what the budget keeps first: hanging hair (a tail, loose lengths) is the silhouette and goes before the
            # second layer of hair lying on the head; single hairs (halo, curls, strays) go before both, except the
            # face-framing wisps at the hairline. Tess's W18 kept 420 halo cards and 85 tail cards (a thin black tail)
            by_ = {k_["name"]: k_ for k_ in cj.hair_locks}
            for c_ in cj.cards:
                lk_ = by_.get(c_.get("lock")) or {}
                p_ = float(c_.get("prio", c_["layer"]))
                if c_.get("pooled"):  # cheap and it is the outline's soft edge: before any second layer
                    p_ = hair.PRIO_HALO
                elif lk_.get("face"):
                    p_ += hair.PRIO_FACE
                elif lk_.get("off_head"):  # a tail's strays are its ragged outline, not single hairs on the head
                    p_ += hair.PRIO_FREE
                elif c_["kind"] == "fly":
                    p_ += 0.2 if lk_.get("at_hairline") else hair.PRIO_FLY
                elif float(lk_.get("free", 0.0)) > 0.5:
                    p_ += hair.PRIO_FREE
                c_["prio"] = p_
        if (not cj.clumped and not cj.short and hair.COVER_TIERS and cj.tier_name
                and float(hair.COVER_TIERS.get(cj.tier_name, 0.0)) > 0):  # (round 33) the part's cover row at a coarser tier:
            # hair_clumps_part.part_cover with fewer, wider cards (COVER_TIERS x PART_COVER per side) on the tiles
            from . import hair_clumps
            from . import hair_clumps_bake, hair_clumps_cut, hair_clumps_fit, hair_clumps_part
            n_cov = int(round(float(hair.COVER_TIERS[cj.tier_name]) * max(hair_clumps.PART_COVER, 1)))
            if n_cov > 0:
                St_c = hair_clumps.strands(cj.D, cj.hair_locks)
                so_c = (hair_clumps_part.strand_part(St_c, cj.sc.C) if hair_clumps.PART_FROM_STRANDS else None) or part_side_of(cj.sc, cj.g)
                if so_c is not None:
                    env_c = hair_clumps_fit.envelope(St_c, cj.sc.C, pct=hair_clumps.ENV_PCT)
                    pc_, hw_ = hair_clumps.PART_COVER, hair_clumps.COVER_HW
                    hair_clumps.PART_COVER, hair_clumps.COVER_HW = n_cov, hw_ * max(1.0, float(hair_clumps.PART_COVER) / n_cov) ** 0.5
                    try:
                        cov_ = hair_clumps_part.part_cover(St_c, cj.sc.C, so_c, env_c,
                                              np.nonzero((St_c["cls"] == "head") & ~hair_clumps_fit.crown_loops(St_c, cj.sc.C))[0],
                                              int(cj.g.get("seed", 0)))
                    finally:
                        hair_clumps.PART_COVER, hair_clumps.COVER_HW = pc_, hw_
                    top_ = max([int(c_["layer"]) for c_ in cj.cards if c_["kind"] != "fly"] or [0])
                    for c_ in cov_:
                        c_.update(kind="medium" if top_ == 0 else "sparse", layer=top_, prio=top_ + 0.5,
                                  lock=cj.hair_locks[int(c_["lock"])]["name"],
                                  u=np.asarray(c_["s"], float) / max(float(np.asarray(c_["s"])[-1]), 1e-6))
                        for k_ in ("strands", "draw", "cover"):
                            c_.pop(k_, None)
                    cj.cards = cj.cards + cov_
                    print(f"hair cards: part cover {len(cov_)} cards at tier {cj.tier_name!r}", flush=True)
        if (not cj.clumped and not cj.short and hair.ARCH_TIERS and cj.tier_name
                and float(hair.ARCH_TIERS.get(cj.tier_name, 0.0)) > 0):  # (round 35) the crown arch at a coarser tier
            from . import hair_clumps
            from . import hair_clumps_bake, hair_clumps_cut, hair_clumps_fit, hair_clumps_part
            n_ar = max(1, int(round(float(hair.ARCH_TIERS[cj.tier_name]) * max(hair_clumps.ARCH, 1))))
            St_c = hair_clumps.strands(cj.D, cj.hair_locks)
            ar_, hw_ = hair_clumps.ARCH, hair_clumps.ARCH_HW
            hair_clumps.ARCH, hair_clumps.ARCH_HW = n_ar, hw_ * max(1.0, float(max(hair_clumps.ARCH, 1)) / n_ar) ** 0.5
            try:
                so_ = (hair_clumps_part.strand_part(St_c, cj.sc.C) if hair_clumps.PART_FROM_STRANDS else None) or part_side_of(cj.sc, cj.g)
                if so_ is not None and hair_clumps.PART_VISIBLE:  # (round 37) only where the groom shows the part
                    so_ = hair_clumps_part.part_visible(St_c, cj.sc.C, so_)
                arc_ = hair_clumps_part.arch_row(St_c, cj.sc.C, np.nonzero((St_c["cls"] == "head") & ~hair_clumps_fit.crown_loops(St_c, cj.sc.C))[0],
                                    int(cj.g.get("seed", 0)), side_of=so_)
            finally:
                hair_clumps.ARCH, hair_clumps.ARCH_HW = ar_, hw_
            top_ = max([int(c_["layer"]) for c_ in cj.cards if c_["kind"] != "fly"] or [0])
            for c_ in arc_:
                c_.update(kind="medium" if top_ == 0 else "sparse", layer=top_, prio=top_ + 0.5,
                          lock=cj.hair_locks[int(c_["lock"])]["name"],
                          u=np.asarray(c_["s"], float) / max(float(np.asarray(c_["s"])[-1]), 1e-6))
                for k_ in ("strands", "draw", "cover", "P_fit", "row"):
                    c_.pop(k_, None)
            cj.cards = cj.cards + arc_
            print(f"hair cards: crown arch {len(arc_)} cards at tier {cj.tier_name!r}", flush=True)
        if cj.short:  # cards wherever the groom has length, lying just over the cap (which stands at the hair's mid
            # height), on the open tiles (a few thick strands, no opaque base). The budget thins them EVENLY: what
            # stands off the cap (the lifted front, the outline) and the hairline's cards stay longest, the rest go
            # at random, so the whole top keeps a broken, layered surface instead of a rim of tufts round a dome
            edge_ = {k_["name"] for k_ in cj.hair_locks if k_.get("at_hairline")}
            grey_ = {k_["name"]: float((k_.get("inputs") or {}).get("Grey", k_.get("grey", 0.0)) or 0.0) for k_ in cj.hair_locks}
            gmax_ = float(np.percentile(list(grey_.values()), 90)) if grey_ else 0.0
            from scipy.spatial import cKDTree as _KD
            va_, ve_, vh_ = cj.sc.coords(np.asarray(cj.V, float))
            capt_ = _KD(dirs(va_, ve_))
            capb_ = np.maximum(vh_, 0.0) + 0.1 * (1 - np.cos(np.radians(cj.cap_step) / 2)) * 1.6 + 0.002
            hr_ = np.random.default_rng(int(cj.g.get("seed", 0)) + 17)
            kept_ = []
            for c_ in cj.cards:
                P_ = np.asarray(c_["P"], float)
                a_, e_, h_ = cj.sc.coords(P_)
                din_ = inside(cj.sc, cj.line, a_, e_)
                # a card ends at the hairline: past it (over the forehead, round the ear) its few thick strands
                # stood off the skin as wires. The cap's own thinned strands are the hairline.
                ok_ = np.cumprod(din_ > hair.SHORT_EDGE).astype(bool) if din_[0] > hair.SHORT_EDGE else np.zeros(len(din_), bool)
                if ok_.sum() < 3:
                    continue
                if not ok_.all():
                    for k__ in ("P", "X", "N", "hw", "u", "s", "bend", "T"):
                        c_[k__] = np.asarray(c_[k__])[ok_]
                    if np.ndim(c_.get("sn", 0.0)):
                        c_["sn"] = np.asarray(c_["sn"])[ok_]
                    P_, a_, e_, h_, din_ = P_[ok_], a_[ok_], e_[ok_], h_[ok_], din_[ok_]
                kept_.append(c_)
                if hair.SHORT_STRAIGHT > 0 and len(P_) > 2:  # a 2 cm card along its clump's mean path keeps the hook where
                    # the strands leave the scalp and are laid down: from behind, rows of hooks read as curls / kinks
                    # (Garrett's back). Drawn toward the chord root -> tip, its length kept by the chord's end
                    s__ = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P_, axis=0), axis=1))]
                    f__ = (s__ / max(s__[-1], 1e-9))[:, None]
                    P_ = P_ * (1 - hair.SHORT_STRAIGHT) + hair.SHORT_STRAIGHT * (P_[:1] + f__ * (P_[-1:] - P_[:1]))
                    a_, e_, h_ = cj.sc.coords(P_)
                if c_["kind"] != "fly":  # the card stands at the TOP of its clump (its line is the clump's mean: the
                    # hair's outline is the strands above it), along the strands' own direction
                    sn_ = np.broadcast_to(np.asarray(c_.get("sn", 0.0), float), (len(P_),))
                    P_ = P_ + (hair.SHORT_TOP * sn_ * _ss(din_ / 0.015))[:, None] * np.asarray(c_["N"], float)
                    a_, e_, h_ = cj.sc.coords(P_)
                # (+ where the cap's own mesh stands before that lift: the groom's volume, a few mm over the scalp.
                # Without it the cards lay UNDER the cap they were meant to break up: nothing of them showed)
                cz_ = cj.hair_cap.cap_height(cj.chart["lift"], din_, a_, e_) + capb_[capt_.query(dirs(a_, e_))[1]]
                f_ = (c_["s"] - c_["s"][0]) / max(float(c_["s"][-1] - c_["s"][0]), 1e-9)
                need_ = cz_ + 0.0012 + 0.0006 * c_["layer"] - 0.002 * (1 - _ss(f_ / 0.25))  # (the root dives into the cap)
                # the tip leaves the cap (SHORT_TIP, uneven card to card): lying IN the cap's surface every card was a
                # decal on a helmet; a crop's outline is tufts' ends
                need_ = need_ + hair.SHORT_TIP * float(hr_.uniform(0.2, 1.6)) * f_ ** 1.5
                up_ = np.where(h_ > -0.004, np.clip(need_ - h_, 0.0, 0.03), 0.0)  # (not where a ray meets the ear first)
                c_["P"] = P_ + up_[:, None] * _unit(P_ - cj.sc.C)
                c_["hw"] = np.asarray(c_["hw"], float) * (1 - 0.45 * _ss((f_ - 0.55) / 0.45))  # no square end
                if c_["kind"] != "fly":
                    c_["kind"] = "medium" if c_["layer"] == 0 else "sparse"
                # grey by region: the tiles are drawn with ONE grey share (the locks' mean); a card of a less grey
                # lock is darker by its vertex colour (the cap's own picture has the per-lock grey, but the cards
                # now cover it: greying temples under a uniform top)
                c_["value"] = float(c_.get("value", 1.0)) * (1.0 - hair.SHORT_GREY * (gmax_ - grey_.get(c_.get("lock"), gmax_)))
                off_ = float((h_ - cz_).max())
                c_["prio"] = ((0.0 if off_ > 0.005 else 0.45 if c_.get("lock") in edge_ else 1.0)
                              + 0.5 * min(c_["layer"], 1) + float(hr_.uniform(0.0, 0.9)))
            cj.cards = kept_
            # a swoop (groom.loose.swoop) is ONE lock with body: clump cards cut it into fine scraps lying at the
            # cap's height (Garrett: no swoop in the cards). It gets SWOOP_CARDS dedicated cards on the dense tile
            # along its strongest locks' own spines (their lift included), wide, kept first by the budget
            sw_ = sorted([k_ for k_ in cj.hair_locks if float(k_.get("swoop", 0.0)) >= 0.5], key=lambda k_: -float(k_["swoop"]))
            if sw_:
                pick_ = [sw_[int(i_)] for i_ in np.unique(np.linspace(0, len(sw_) - 1, min(hair.SWOOP_CARDS, len(sw_))).round())]
                S1_ = {**cj.S, "layers": 1, "card_width": hair.SWOOP_WIDTH, "flyaway": 0.0}
                for c_ in cj.hair_cards_mesh.cards_of(pick_, cj.sc.C, S1_, cj.lk):
                    P_ = np.asarray(c_["P"], float)
                    a_, e_, h_ = cj.sc.coords(P_)
                    din_ = inside(cj.sc, cj.line, a_, e_)
                    # its root starts behind the hairline (the dense tile's square root end on the forehead read as
                    # a plate's edge); the hairline's own fine cards and the cap carry the line
                    ok_ = np.cumsum(din_ >= hair.SWOOP_BACK) > 0
                    if ok_.sum() < 3:
                        continue
                    for k__ in ("P", "X", "N", "hw", "u", "s", "bend", "T"):
                        c_[k__] = np.asarray(c_[k__])[ok_]
                    P_, a_, e_, h_, din_ = P_[ok_], a_[ok_], e_[ok_], h_[ok_], din_[ok_]
                    cz_ = cj.hair_cap.cap_height(cj.chart["lift"], din_, a_, e_) + capb_[capt_.query(dirs(a_, e_))[1]]
                    f_ = (c_["s"] - c_["s"][0]) / max(float(c_["s"][-1] - c_["s"][0]), 1e-9)
                    need_ = cz_ + 0.0015 - 0.002 * (1 - _ss(f_ / 0.2))
                    up_ = np.where(h_ > -0.004, np.clip(need_ - h_, 0.0, 0.03), 0.0)
                    # the wave: the lock rises off the hair round it and rolls back down (cards lying at the cap's height
                    # read as part of the combed mass)
                    up_ = up_ + hair.SWOOP_LIFT * np.sin(np.pi * np.clip(f_, 0, 1)) ** 0.7
                    c_["P"] = P_ + up_[:, None] * _unit(P_ - cj.sc.C)
                    c_["hw"] = (np.asarray(c_["hw"], float) * (1 - 0.6 * _ss((f_ - 0.5) / 0.5))  # a tapered, feathered end
                                * (0.35 + 0.65 * _ss(f_ / 0.25)))  # and a narrow root
                    # body from LAYERS of the fine short tiles, not the dense tile (its 16 cm strands squeezed onto a
                    # 4 cm card read as a smooth grey plate on the forehead in Godot)
                    for li_ in range(hair.SWOOP_LAYERS):
                        d_ = dict(c_)
                        d_["P"] = np.asarray(c_["P"]) + (hair.SWOOP_GAP * li_ * _ss(f_ / 0.3))[:, None] * np.asarray(c_["N"], float)
                        d_["hw"] = np.asarray(c_["hw"]) * (1.0 - 0.15 * li_)
                        d_["kind"], d_["layer"], d_["prio"] = ("medium" if li_ < hair.SWOOP_LAYERS - 1 else "sparse"), li_, -1.0
                        cj.cards.append(d_)
        tc = cj.hair_cards_mass.tail_cores(cj.D, cj.hair_locks, sides=int(cj.S.get("core_sides", 10)))
        cj.core = cj.hair_cards_mass.core_mesh(tc, cj.at["tiles"]) if tc is not None else None
        # (not for a short cut: hair under MASS_MIN long has no inside; its shell stood OUTSIDE the cards on the
        # sides and back as a pale dome with a dark rim at the temples (Garrett's crop). The cap, wearing the
        # scalp chart, is the surface under short cards.)
        lens = [float(np.linalg.norm(np.diff(np.asarray(k_["pts"], float), axis=0), axis=1).sum()) for k_ in cj.hair_locks]
        if cj.g.get("loose") and lens and float(np.mean(lens)) > hair.MASS_MIN:  # a loose mass: a solid surface inside it
            shell = cj.hair_cards_mass.mass_shell(cj.D, cj.hair_locks, cj.sc.C, cj.at["tiles"], col=cj.col, triangles=int(cj.S.get("mass", 3000)))
            if shell is not None:
                cj.core = cj.hair_cards_budget.join(cj.core, shell)
    else:
        cj.cards = cj.hair_cards_mesh.cards_of(cj.hair_locks, cj.sc.C, cj.S, cj.lk)


def _shell_cards(cj):
    """Under shells only the hairline's rows and the fins stay cards, toned to the cap."""
    if cj.shell_n is not None:  # (sh1) the shells carry the head: only the hairline / sideburn rows stay cards
        n_all_ = len(cj.cards)
        fin_ = float(cj.shell_o.get("fins", hair.SHELL_FINS)) if (cj.tier_name or "hero") in hair.SHELL_FIN_TIERS else 0.0

        def _fin(c_):
            if fin_ <= 0 or not (c_.get("flow") or c_.get("arch")):
                return False
            m_ = np.asarray(c_["P"], float).mean(0) - np.asarray(cj.sc.C, float)
            u_ = m_ / max(float(np.linalg.norm(m_)), 1e-9)
            return bool(np.degrees(np.arcsin(np.clip(u_[2], -1, 1))) > hair.SHELL_FIN_EL and min(abs(u_[0]), abs(u_[1])) < fin_)
        nf_ = sum(1 for c_ in cj.cards if not c_.get("hrow") and _fin(c_))
        cj.cards = [c_ for c_ in cj.cards if c_.get("hrow") or _fin(c_)]
        if hair.SHELL_HROW_DROP:  # (sh6) hairline-row cards dropped in a region (the cap's own tapered strands show there)
            n0_ = len(cj.cards)
            cj.cards = [c_ for c_ in cj.cards if not _hrow_dropped(cj.sc, c_)]
            print(f"hair shells: {n0_ - len(cj.cards)} hairline cards dropped in {hair.SHELL_HROW_DROP}", flush=True)
        if hair.SHELL_CARD_VALUE != 1.0 or _hcap_vm():  # (sh4) the kept cards toned to the cap (vertex colour factor):
            # the cap's own regional VALUE_MAP ("low" row: the hairline's) by the card's angle from the front, and on the
            # sides (> 40 deg from the front) x SHELL_CARD_VALUE (sh3d: temple cards 55.1 L* over a 49.6 cap in profile,
            # the front's equal at 48)
            from . import hair_cap as hcap_
            vm_ = {**hcap_.GREY_MAP, **(hcap_.VALUE_MAP or {"low": [1.0] * 5})}
            for c_ in cj.cards:
                a_, _e, _h = cj.sc.coords(np.asarray(c_["P"], float).mean(0)[None])
                fa_ = abs(((float(a_[0]) + 180) % 360) - 180)
                k_ = float(np.interp(fa_, vm_["fa"], vm_["low"])) * (1 + (hair.SHELL_CARD_VALUE - 1) * _ss((fa_ - 30.0) / 20.0))
                c_["cval"] = float(c_.get("cval", 1.0)) * k_
        print(f"hair shells: {len(cj.cards)} of {n_all_} cards kept (hairline rows + {nf_} fins)", flush=True)


def stamp_cls(cards: list, locks: list) -> list:
    """(round 47) hair_clumps' card class ("tail" / "face" / "single" / "head"; "fly" for fly-aways) on clump_cards'
    cards, which carried none: every class filter (BEND_CLS, TAIL_AXIS_N, FIT_FLOOR) matched 0 cards at LOD1-3."""
    from .hair_clumps import classify
    by_ = {k_["name"]: k_ for k_ in locks}
    for c_ in cards:
        if c_.get("cls") is None:
            c_["cls"] = "fly" if c_.get("kind") == "fly" else classify(by_.get(c_.get("lock")) or {})
    return cards
