"""cards_job: the job that makes hair cards. Part of hair (hair.py has the overview)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np

from . import hair
from .hair import HairError, _ss, _unit, dirs
from .hair_groom import hairline, inside, look_of, part_side_of
from .hair_head import Scalp
from .hair_job import _hcap_vm, baby_locks, card_allowance, card_cap, tier_drawn_max, tier_settings
from .hair_lockmesh import _hrow_dropped, shell_gaps
from .hair_spec import hair_of


class CardsJob:
    """What one hair-cards job carries from stage to stage: the arguments of `cards_job`, then what each stage sets for
    the ones after it. A stage reads and writes it as `cj.<name>`; what a stage only uses itself is a local there.
    _settings sets:
      hair_card_fit, hc, hair_cards_mesh, hair_cards_mass, hair_cards_atlas, hair_cards_clumps, hair_cards_budget, S,
      short, short_len, tier_name, drawn_max_, lk, D, e_chart, ex_s, shell_o, shell_n, shell_maps, shell_key
    _pictures sets:
      hair_cap, chart, bs_, make_atlas, at
    _lock_marks sets:
      bands, line, hair_locks
    _cards sets:
      core, clumped, St_, cards
    _cap sets:
      hz_, cap, shell_raw
    _baby sets:
      baby, _c0
    _budget sets:
      info, seg, mb, band
    _meshes sets:
      mc
    _clearance sets:
      clearance
    """

    def __init__(self, **arguments):
        self.__dict__.update(arguments)


def cards_job(sc: Scalp, g: dict, spec: dict, locks: list, tmp: Path, V, F, budget: int | None = None,
              cap_step: float = 1.0, col=None, clear_col=None) -> dict:
    """The hair as cards (hair_cards.py): the card mesh of every lock + baby hairs, the underlayer wearing the strand
    atlas, and the atlas's pictures. `budget`: triangles for the cards (segments lengthen, then layers go)."""
    cj = CardsJob(sc=sc, g=g, spec=spec, locks=locks, tmp=tmp, V=V, F=F, budget=budget, cap_step=cap_step, col=col,
                  clear_col=clear_col)
    _settings(cj)
    _pictures(cj)
    _lock_marks(cj)
    _cards(cj)
    _shell_cards(cj)
    _cap(cj)
    _baby(cj)
    _budget(cj)
    _bake(cj)
    _meshes(cj)
    _clearance(cj)
    return _write(cj)


def _settings(cj):
    """What the job is given: the strand settings under the tier's (a short cut's, an even groom's), the triangles,
    the look with the export's card-only settings and the grey share, how many shells."""
    from . import hair_card_fit
    cj.hair_card_fit = hair_card_fit
    from . import hair_cards as hc
    cj.hc = hc
    from . import hair_cards_atlas, hair_cards_budget, hair_cards_clumps, hair_cards_mass, hair_cards_mesh
    cj.hair_cards_atlas = hair_cards_atlas
    cj.hair_cards_budget = hair_cards_budget
    cj.hair_cards_clumps = hair_cards_clumps
    cj.hair_cards_mass = hair_cards_mass
    cj.hair_cards_mesh = hair_cards_mesh
    h = hair_of(cj.spec)
    cj.S = cj.hc.strands_of(cj.spec)
    lens_ = [float(np.linalg.norm(np.diff(np.asarray(k_["pts"], float), axis=0), axis=1).sum())
             for k_ in cj.locks] if cj.g.get("loose") else []
    cj.short = bool(lens_) and float(np.mean(lens_)) < hair.MASS_MIN
    # an EVEN groom (strands.even: one field over the scalp, hair_even*, Garrett's G88a) has no per-lock guide strands:
    # the short cut's per-lock cards (clump_cards) found none (c1a: the cap alone, 0 cards). It is cut by visual
    # clumps (hair_clumps, the hero tier's cut) like any other groom
    cj.short_len = cj.short
    even = float((h.get("strands") or {}).get("even", 0.0) or 0.0) > 0
    if cj.short and even:
        cj.short = False
    tier_given = isinstance(cj.budget, str)
    cj.tier_name = cj.budget if tier_given else None
    cj.drawn_max_ = None
    if isinstance(cj.budget, str):  # a tier: its triangles, and how fine the cards are cut to spend them
        if cj.budget not in hair.CARD_TIERS:
            raise HairError(f"hair cards: tier is one of {', '.join(hair.CARD_TIERS)} (or a triangle count)")
        tier = tier_settings(cj.budget, cj.short, even)
        cj.S = {**cj.S, **{k: v for k, v in tier.items() if k not in ("triangles", "cap_step", "cap")}}
        ex_ = h.get("export") or {}
        cj.budget = hair.tier_triangles(cj.budget, ex_.get("role", "hero"), ex_.get("tier_triangles"))
        cj.drawn_max_ = tier_drawn_max(cj.tier_name, ex_.get("tier_drawn_max"))
    if cj.short:
        cj.S = {**cj.S, "atlas": max(int(cj.S["atlas"]), hair.SHORT_ATLAS), "fly": int(cj.S.get("fly", 0)) if tier_given else 0,
             "short": True}
    elif cj.short_len and hair.EVEN_SHORT_CAP:  # an even short groom (clumps cards): the short cut's BAKED cap all the same
        cj.S = {**cj.S, "atlas": max(int(cj.S["atlas"]), hair.SHORT_ATLAS)}
    cj.lk = look_of(cj.spec, h)
    if (h.get("export") or {}).get("card_gain") is not None:  # the cards' colour gain measured against the strand look
        cj.lk["card_gain"] = float(h["export"]["card_gain"])  # (an export setting: the approved groom's look stays)
    for k_ in ("tone_front", "tone_back", "card_sat", "headroom"):  # (c10) more card-only look settings carried by hair.export
        # (c14: headroom = hair_cards_atlas.atlas moves up to that factor of the baked cards' tone into the atlas)
        if (h.get("export") or {}).get(k_) is not None:
            cj.lk[k_] = float(h["export"][k_])
    # (c11) per-tier card look: hair.export.tier_look {tier: {card_gain, card_sat, tone_front, tone_back}} over the
    # above (a far tier has no rows / top layer and one coarse atlas: Garrett's far read L* 37-42 vs the groom's 47-53)
    for k_, v_ in ((h.get("export") or {}).get("tier_look") or {}).get(cj.tier_name or "", {}).items():
        if k_ in ("card_gain", "card_sat", "tone_front", "tone_back", "card_grey"):
            cj.lk[k_] = float(v_)
    # grey hairs in the cards' pictures: the share the strand look draws (the look's own + the locks' mean grey)
    gl = [float((k_.get("inputs") or {}).get("Grey", k_.get("grey", 0.0)) or 0.0) for k_ in cj.locks]
    cj.lk["grey_share"] = round(float(np.clip(float(cj.lk.get("grey_amount", 0.0))
                                           + float(cj.lk.get("grey_locks", 1.0)) * (np.mean(gl) if gl else 0.0), 0, 1)), 3)
    cj.D, cj.e_chart = None, None
    # (sh1) SHELLS: hair.export.style "shells" (a short cut only): {"shells": {"heights", "base", "cover", "tiers":
    # {tier: n}}}: the cap + n alpha-tested shells carry the hair, cards only along the hairline (hrow)
    cj.ex_s = h.get("export") or {}
    cj.shell_o = dict(cj.ex_s.get("shells") or {})
    cj.shell_n = None
    if str(cj.ex_s.get("style", "cards")) == "shells" and (cj.short or (cj.short_len and hair.EVEN_SHORT_CAP)):
        cj.shell_n = int((cj.shell_o.get("tiers") or {}).get(cj.tier_name or "", hair.SHELL_TIERS.get(cj.tier_name or "hero", 2)))
    cj.shell_maps, cj.shell_key = None, ""


def _pictures(cj):
    """The pictures: the groom's own strands evaluated, the cap's chart (a short cut's is baked from the strands, combed
    under shells, trimmed at a fade), the atlas; or the drawn atlas."""
    if cj.S.get("source", "groom") == "groom":  # the pictures are the groom's own strands (hair_strands.py)
        from . import hair_strands_eval, hair_strands_job
        import re as _re
        sd = hair_strands_job.job(cj.sc, cj.g, cj.spec, [k_ for k_ in cj.locks if not _re.fullmatch(r"t\d*band", k_["name"])], cj.tmp, col=cj.col)
        cj.D, cj.e_chart = hair_strands_eval.strands_of_model(sd), sd["e0"]
        if cj.short or (cj.short_len and hair.EVEN_SHORT_CAP):  # the cap's picture is BAKED from the strands: colour, depth, normal, flow, grey (hair_cap.py)
            from . import hair_cap
            cj.hair_cap = hair_cap
            ck = (hair_strands_job.key(sd), int(cj.S["atlas"]), cj.hair_cap.VERSION, cj.hair_cap.BASE_IN, cj.hair_cap.BASE_RAMP, cj.hair_cap.KEEP_SOFT, cj.hair_cap.THIN_SOFT, cj.lk.get("grey_locks"), cj.lk.get("grey_amount"), cj.lk.get("card_grey"), float(cj.S["soft"]))
            if ck not in hair._CHARTS:
                hair._CHARTS.clear()
                hair._CHARTS[ck] = cj.hair_cap.chart(cj.sc, cj.g, hairline(cj.sc, cj.g), cj.S, cj.D, [k_ for k_ in cj.locks if not _re.fullmatch(r"t\d*band", k_["name"])],
                                             cj.e_chart, int(cj.S["atlas"]), cj.lk)
            cj.chart = hair._CHARTS[ck]
            if cj.shell_n is not None:  # (sh1) hair.export.style "shells": the cap wears COMBED strands, shells over it
                hts_ = tuple(float(x_) for x_ in (cj.shell_o.get("heights") or cj.hair_cap.SHELL_HEIGHTS))[:cj.shell_n]
                cj.bs_ = float(cj.shell_o.get("base", cj.hair_cap.SHELL_BASE))
                ck2 = ck + ("combed", hts_, cj.bs_, float(cj.shell_o.get("cover", cj.hair_cap.LAY_COVER)), cj.hair_cap.LAY_LEN, cj.hair_cap.LAY_MIN, cj.hair_cap.LAY_MAX,
                            cj.hair_cap.LAY_WOBBLE, cj.hair_cap.SHELL_WIDTH, cj.hair_cap.SHELL_LIT, cj.hair_cap.LAY_DEP0, cj.hair_cap.LAY_DEP_T, cj.hair_cap.LAY_DEP_S, int(cj.g.get("seed", 0)),
                            cj.hair_cap.GREY_SPREAD, cj.hair_cap.GREY_REGION, json.dumps(cj.hair_cap.GREY_MAP), json.dumps(cj.hair_cap.SHADE_MAP), json.dumps(cj.hair_cap.VALUE_MAP), cj.hair_cap.EDGE_SHADE, cj.hair_cap.BASE_EDGE, cj.hair_cap.BASE_DEPTH, cj.hair_cap.BASE_EDGE_DEPTH)
                if ck2 not in hair._CHARTS:
                    hair._CHARTS[ck2] = cj.hair_cap.combed(cj.chart, hts_, cj.bs_, seed=int(cj.g.get("seed", 0)),
                                                   cover=float(cj.shell_o.get("cover", cj.hair_cap.LAY_COVER)))
                    print(f"hair shells: combed {hair._CHARTS[ck2]['strands']} strands, shells at {hts_} (cap {cj.bs_})", flush=True)
                comb_ = hair._CHARTS[ck2]
                cj.chart = {**comb_["cap"], "lift": cj.chart["lift"]}
                cj.shell_maps = comb_["shells"]
                cj.shell_key = f"_shells{hts_}_{cj.bs_}_{hashlib.sha1(repr(ck2).encode()).hexdigest()[:12]}"
                fade_o = cj.ex_s.get("fade")
                if fade_o and fade_o.get("trim"):  # (sh7) the mesh hair's edge moved up to meet the skin's painted fade
                    from . import hair_fade
                    Hc_, Wc_ = cj.chart["alpha"].shape
                    km_ = hair_fade.trim_mask(fade_o, float(np.median(cj.sc.R)), 90.0 - (np.arange(Hc_) + 0.5) / Hc_ * (90.0 - cj.e_chart), Wc_)
                    cj.chart = {**cj.chart, "alpha": (cj.chart["alpha"] * km_).astype(np.float32)}
                    cj.shell_maps = [{**m_, "alpha": (m_["alpha"] * (km_ if m_["alpha"].shape == km_.shape else hair_fade.trim_mask(
                        fade_o, float(np.median(cj.sc.R)), 90.0 - (np.arange(m_["alpha"].shape[0]) + 0.5) / m_["alpha"].shape[0] * (90.0 - cj.e_chart),
                        m_["alpha"].shape[1]))).astype(np.float32)} for m_ in cj.shell_maps]
                    cj.shell_key += "_trim" + hashlib.sha1(json.dumps([fade_o["trim"], fade_o.get("trim_soft_mm"), fade_o.get("trim_breakup_mm"), fade_o.get("seed")]).encode()).hexdigest()[:8]
                    print(f"hair fade: cap / shells trimmed below {fade_o['trim']}", flush=True)
        else:
            cj.chart = hair_strands_eval.cap_chart(cj.sc, cj.g, hairline(cj.sc, cj.g), cj.S, cj.D, cj.e_chart, int(cj.S["atlas"]))
        akey_ = hair_strands_job.key(sd) + (f"short{cj.hair_cap.VERSION}_{cj.hair_cap.BASE_IN}_{cj.hair_cap.BASE_RAMP}_{cj.hair_cap.KEEP_SOFT}_{cj.hair_cap.THIN_SOFT}" if cj.short or (cj.short_len and hair.EVEN_SHORT_CAP) else "")

        def make_atlas(bake=None):
            return cj.hair_cards_atlas.atlas(cj.S, cj.lk, lines=hair_strands_eval.tile_lines(cj.S), cap=cj.chart, key=akey_ + cj.shell_key, bake=bake, shells=cj.shell_maps or None)
        cj.make_atlas = make_atlas
        cj.at = cj.make_atlas()
    else:
        cj.at = cj.hair_cards_atlas.atlas(cj.S, cj.lk)


def _lock_marks(cj):
    """The tie's bands apart from the hair; each lock marked: at the hairline, face-framing, off the head, lying on it."""
    import re
    cj.bands = [k_ for k_ in cj.locks if re.fullmatch(r"t\d*band", k_["name"])]  # the tie is its own mesh, not hair
    cj.line = hairline(cj.sc, cj.g)
    for k_ in cj.locks:  # locks rooted at the hairline wear the thin-rooted tile there
        a0, e0, h0 = cj.sc.coords(np.asarray(k_["pts"][0], float)[None])
        if not k_.get("free"):
            k_["at_hairline"] = bool(h0[0] < 0.01 and inside(cj.sc, cj.line, a0, e0)[0] < 0.008)
        # FACE-FRAMING: hair off the head rooted near the hairline in front of the ears (wisps, curls, loose locks
        # at the temples): the budget keeps it with the coverage. Ranked as single hairs, Tess's W18 lost every
        # face wisp at every tier (the assembly review, hair_r2). Not a halo's single hairs rooted at the part (1-2
        # hairs: as face-framing wisps they were 2-3 cards each, a tuft standing up out of the part, review c3)
        k_["face"] = bool(float(k_.get("free", 0.0)) > 0.5 and h0[0] < 0.02 and int(k_.get("hairs") or 0) not in (1, 2)
                          and inside(cj.sc, cj.line, a0, e0)[0] < hair.FACE_IN
                          and abs(((float(a0[0]) + 180.0) % 360.0) - 180.0) < hair.FACE_AZ)
        k_["off_head"] = bool(float(k_.get("free", 0.0)) > 0.5 and h0[0] > 0.02)  # (rooted in hanging hair: a tail's strays)
        # a SHORT loose cut's locks are all "free" (none tied) but lie on the head: head cards, not a tail's hanging
        # ones (G88a's clumps cut drew 100% hanging cards with the ponytail's tone / twist / tip knobs, c1)
        k_["lies"] = bool(cj.short_len and cj.g.get("loose") and not cj.g.get("tied") and h0[0] < 0.02)
        k_["face"] = k_["face"] and not k_["lies"]  # (its hairline locks lie on the head too: no face-framing wisps)
    cj.hair_locks = [k_ for k_ in cj.locks if k_ not in cj.bands]


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


def _cap(cj):
    """The cap: lifted off the coarse mesh's chords, an even short groom's at the hair's mid height, under the cards
    (relaxed, never under its floor) or at the shells' base or a short cut's mass height; its card mesh; the
    shells as copies of it."""
    # a coarse cap's flat faces cut under the round head between their corners (skin through the hair): it is
    # lifted by that sagitta
    Vc = np.asarray(cj.V, float)
    lift = 0.1 * (1 - np.cos(np.radians(cj.cap_step) / 2)) * 1.6 + 0.002  # (+ the scalp grid vs the skin mesh: ~1 mm)
    Vc = Vc + lift * _unit(Vc - cj.sc.C)
    even_lift = cj.D is not None and not cj.short and cj.short_len and hair.EVEN_SHORT_CAP and hair.EVEN_SHORT_LIFT and cj.shell_n is None
    if even_lift:  # (c2) an even short groom's cap stands at the hair's mid height (cap_height over the SCALP, not over
        # whatever the cap mesh had: on a mass cap the two added up) and then goes under its cards like any cap: added
        # AFTER cap_under_cards it stood over the cards wherever they were few (main / npc / far: +17-28 % outline height)
        ca_, ce_, ch_ = cj.sc.coords(Vc)
        cj.hz_ = lift + cj.hair_cap.cap_height(cj.chart["lift"], inside(cj.sc, cj.line, ca_, ce_), ca_, ce_)
        Vc = Vc + (cj.hz_ - ch_)[:, None] * _unit(Vc - cj.sc.C)
    # (c3) and never sinks under EVEN_CAP_KEEP x that height going under the cards: at the floor (lift, ~2 mm) it lay
    # under the head's skin where cards were sparse (c2's hero: rows of bare-scalp holes at the back, behind the ear)
    cfloor = np.maximum(lift, hair.EVEN_CAP_KEEP * cj.hz_) if even_lift else lift
    if cj.shell_n is not None:  # (sh1) the cap at SHELL_BASE of the hair's height (no cards over it to go under)
        ca_, ce_, ch_ = cj.sc.coords(Vc)
        di0_ = inside(cj.sc, cj.line, ca_, ce_)
        lv_ = lift
        if hair.SHELL_EDGE_LIFT is not None:  # (sh4) the lift eases to SHELL_EDGE_LIFT over the last SHELL_LIFT_EASE in from the
            # hairline: lifted whole, the cap's edge floated ~2-3 mm over the skin and its gap read as a black rim
            lv_ = hair.SHELL_EDGE_LIFT + (lift - hair.SHELL_EDGE_LIFT) * _ss(np.maximum(di0_, 0.0) / hair.SHELL_LIFT_EASE)
        Vc = Vc + (lv_ + cj.hair_cap.shell_height(cj.chart["lift"], di0_, ca_, ce_, cj.bs_) - ch_)[:, None] * _unit(Vc - cj.sc.C)
    elif cj.D is not None and not cj.short and cj.cards:  # the cap is UNDER the cards: it is the scalp's tint between them, never
        # the surface. The groom's envelope stood 25 mm off the top of Tess's W18 where the coverage cards lie at 17:
        # a lighter, flatter helmet over the cards with a seam where they came out from under it (hair_r2)
        Vc = cj.hair_card_fit.cap_under_cards(cj.sc, Vc, [c_ for c_ in cj.cards if c_["layer"] == 0 and c_["kind"] != "fly"], cfloor,
                             bare_floor=hair.CAP_BARE_FLOOR and not even_lift)  # (an even cap keeps its mid height where no card is: c1d's bare patches)
        if hair.CAP_RELAX > 0:  # (round 26) the cap's radius relaxed over its mesh and only ever lowered: its top under the
            # cards was a flat notched block that stood up at the front crown's outline (RC review "flat spike")
            Fq = np.asarray(cj.F)
            Fq = Fq.reshape(len(Fq), -1)
            e_ = np.concatenate([Fq[:, [k_, (k_ + 1) % Fq.shape[1]]] for k_ in range(Fq.shape[1])])
            e_ = np.concatenate([e_, e_[:, ::-1]])
            deg_ = np.bincount(e_[:, 0], minlength=len(Vc)).astype(float)
            d_ = Vc - cj.sc.C
            r0 = np.linalg.norm(d_, axis=1)
            r_ = r0.copy()
            for _ in range(int(hair.CAP_RELAX)):
                nb = np.bincount(e_[:, 0], weights=r_[e_[:, 1]], minlength=len(Vc)) / np.maximum(deg_, 1)
                r_ = 0.5 * r_ + 0.5 * np.where(deg_ > 0, nb, r_)
            r_ = np.minimum(r_, r0)
            if hair.CAP_RELAX_FLOOR:  # (round 30) never under the floor it was given (lift: the sagitta + the scalp grid vs
                # the skin): relaxed toward the hairline's dive rows, a coarse cap (the far tier, 14 deg) sank under the
                # skin over the lower back of the head (LOD3's bare patch beside the tie)
                vh_ = cj.sc.coords(Vc)[2]
                r_ = np.maximum(r_, r0 - np.maximum(vh_ - lift, 0.0))
            Vc = cj.sc.C + d_ * (r_ / np.maximum(r0, 1e-9))[:, None]
        if even_lift and hair.EVEN_CAP_KEEP > 0:  # (the relaxation lowers too: the even cap's floor holds after it)
            _a, _e, ch_ = cj.sc.coords(Vc)
            Vc = Vc + np.maximum(cfloor - ch_, 0.0)[:, None] * _unit(Vc - cj.sc.C)
        Vc = cj.hair_card_fit.cap_fill_arch(cj.sc, Vc, [c_ for c_ in cj.cards if c_.get("arch")])
    if cj.D is not None and cj.short and cj.shell_n is None:  # the cap is the hair's MASS: it stands at the hair's mid height, easing down to the
        # skin at the hairline (on the scalp itself the head's profile was a bald dome under a fringe of cards)
        ca_, ce_, _ch = cj.sc.coords(Vc)
        Vc = Vc + cj.hair_cap.cap_height(cj.chart["lift"], inside(cj.sc, cj.line, ca_, ce_), ca_, ce_)[:, None] * _unit(Vc - cj.sc.C)
    cj.cap = card_cap(cj.sc, cj.g, cj.S, cj.at["tiles"], Vc, cj.F, e0=cj.e_chart)
    cj.shell_raw = None
    if cj.shell_n and cj.shell_maps:  # (sh1) the shells: copies of the cap at their heights, uv set once the atlas is final
        nc_ = len(cj.cap["verts"])
        ca_, ce_, _h = cj.sc.coords(cj.cap["verts"])
        di_ = inside(cj.sc, cj.line, ca_, ce_)
        h0_ = cj.hair_cap.shell_height(cj.chart["lift"], di_, ca_, ce_, cj.bs_)
        cu_ = np.clip((np.asarray(cj.cap["uv"][:, 0], float) - 0.5) / 0.5, 0, 1)
        cv_ = np.asarray(cj.cap["uv"][:, 1], float)
        parts_ = [cj.cap]
        dhs_ = shell_gaps([cj.hair_cap.shell_height(cj.chart["lift"], di_, ca_, ce_, sm_["height"]) - h0_ for sm_ in cj.shell_maps])
        for sm_, dh_ in zip(cj.shell_maps, dhs_):
            parts_.append({**cj.cap, "verts": (np.asarray(cj.cap["verts"], float) + dh_[:, None] * _unit(np.asarray(cj.cap["verts"], float) - cj.sc.C)).astype(np.float32),
                           "layer": np.full(nc_, -1.0, np.float32)})
        cj.cap = cj.hair_cards_budget.join(*parts_)
        cj.shell_raw = (nc_, cu_, cv_, len(cj.shell_maps))


def _baby(cj):
    """The baby hairs along the hairline: none at a tied groom's nape, their kind, layer, priority and tone."""
    cj.baby = cj.hair_cards_mesh.cards_of(baby_locks(cj.sc, cj.g, cj.S, int(cj.g.get("seed", 0))), cj.sc.C, cj.S, cj.lk)
    if hair.BABY_NAPE and cj.bands:  # (round 44) see BABY_NAPE
        cj._c0 = np.asarray(cj.sc.C, float)
        cj.baby = [c for c in cj.baby if not ((np.asarray(c["P"], float)[0, 2] - cj._c0[2]) < -float(hair.BABY_NAPE[0])
                                        and (np.asarray(c["P"], float)[0, 1] - cj._c0[1]) > float(hair.BABY_NAPE[1]))]
    for c in cj.baby:  # (the first to go under a budget, after single fly-aways)
        # (a short cut's soft line: on the hairline tile they were opaque stamps on the forehead; the baby tile
        # needs enough hairs to show: SHORT_TILE["baby"])
        c["kind"], c["layer"], c["prio"] = "baby", 1, (hair.SHORT_BABY_PRIO if cj.short else float(cj.S["layers"]) + 0.6)
        if hair.BABY_TONE != 1.0:  # (round 43, opt-in) see BABY_TONE
            c["value"] = float(c.get("value", 1.0)) * hair.BABY_TONE


def _budget(cj):
    """What goes: short front cards (opt-in), then the budget: the cap, the baby hairs, the tie and the core come off
    it first, the cards are fitted to the rest; `info` is its report."""
    if hair.FRONT_SHORT > 0 and cj.cards:  # (round 46) see FRONT_SHORT
        cj._c0 = np.asarray(cj.sc.C, float); _dr = {}
        def _fs(c_):
            if c_.get("kind") != "baked" or c_.get("fly") or c_.get("cls") == "face" or not len(c_.get("P", [])):
                return False
            r_ = np.asarray(c_["P"], float)[0] - cj._c0
            hit = float(c_["s"][-1]) < hair.FRONT_SHORT and r_[1] < hair.FRONT_SHORT_YZ[0] and r_[2] > hair.FRONT_SHORT_YZ[1]
            if hit:
                k_ = f"{c_.get('cls')}/L{c_.get('layer')}" + "".join(f"/{f}" for f in ("edge", "arch", "cover", "lit", "row") if c_.get(f))
                _dr[k_] = _dr.get(k_, 0) + 1
            return hit
        _pop = sum(1 for c_ in cj.cards if c_.get("kind") == "baked")
        cj.cards = [c_ for c_ in cj.cards if not _fs(c_)]
        print(f"FRONT_SHORT {hair.FRONT_SHORT}: dropped {sum(_dr.values())} front cards: {_dr}", flush=True)
        cj.hair_cards_budget.lever_matched("hair.FRONT_SHORT", sum(_dr.values()), _pop)  # (round 47) r46f dropped 0, said only in a log
    cj.info = {}
    cj.seg = None
    if cj.budget:  # baby hairs are cards like any others: they go before coverage does
        cj.cards, cj.baby = cj.cards + cj.baby, []
    cj.mb = cj.hair_cards_mesh.mesh(cj.baby, cj.S, cj.lk, cj.at["tiles"])
    cj.band = []
    if cj.bands:
        from . import hair_tied
        cj.band = [hair_tied.band_mesh(b, cj.at["tiles"]) for b in cj.bands]
    if cj.budget:  # the budget is the whole hair's: the cap, the baby hairs and the tie come off it first
        fixed = (len(cj.cap["tris"]) + len(cj.mb["tris"]) + sum(len(b["tris"]) for b in cj.band)
                 + (len(cj.core["tris"]) if cj.core is not None else 0))
        before_ = cj.cards
        # (hair-budget rule, coordinator 2026-10-19, reversing c10's drawn-triangle fit) the budget (the role DEFAULT)
        # counts CARD FACES, one side; DRAWN triangles (BACK_FACES exports every triangle but the cap's twice) stay
        # within the tier's drawn max when the tier names one (c13 card_allowance) and are checked against the role's
        # range MAX at export (asset_budget.hair_budget). BUDGET_UNIT names the unit; "drawn" restores c10's fit.
        if hair.BUDGET_UNIT == "drawn":
            dmax_ = None
        else:
            dmax_ = cj.drawn_max_ if cj.drawn_max_ is not None else 10 ** 12  # no tier max: card faces alone
        bf_, fixed_d, allow_ = card_allowance(int(cj.budget), len(cj.cap["tris"]), fixed - len(cj.cap["tris"]), drawn_max=dmax_)
        cj.cards, cj.seg, cj.info = cj.hair_cards_budget.fit_budget(cj.cards, cj.S, allow_)
        cj.info["asked"], cj.info["fixed"], cj.info["drawn_x"], cj.info["unit"] = int(cj.budget), int(fixed_d), bf_, hair.BUDGET_UNIT
        cj.info["drawn_max"] = cj.drawn_max_  # (c13) "asked" = card faces (one side), drawn_max = drawn triangles
        cj.info["fixed_parts"] = {"cap": len(cj.cap["tris"]), "core": len(cj.core["tris"]) if cj.core is not None else 0,
                               "baby": len(cj.mb["tris"]), "tie": sum(len(b["tris"]) for b in cj.band)}
        cj.info["by_class"] = cj.hair_card_fit.card_classes(before_, cj.cards, cj.S, cj.seg, {k_["name"]: k_ for k_ in cj.hair_locks})


def _bake(cj):
    """Each kept clump card's picture baked from its own strands; the atlas made again with the bake under the tiles."""
    if cj.clumped and cj.St_ is not None and any(c_["kind"] == "baked" for c_ in cj.cards):  # each kept clump card's picture
        # baked from its own strands, under the tiles (sh4: a shells far tier keeps no cards at all: nothing to bake)
        from . import hair_clumps
        from . import hair_clumps_bake, hair_clumps_cut, hair_clumps_fit, hair_clumps_part
        bk = [c_ for c_ in cj.cards if c_["kind"] == "baked"]
        Wt = int(cj.at["color"].shape[1])
        Hb = int(cj.S.get("bake_rows") or Wt // 2)
        nt_ = int(cj.S.get("bake_tiles", hair_clumps.TILES))
        if nt_ > 0:  # shared pictures (a few dozen tiles at a fine texel, tinted per card): unique islands for ~500
            # cards in one block were ~1 texel/mm, smeared bands with no strands (c5-c7)
            B = hair_clumps_bake.bake_tiles(bk, cj.St_, Wt, Hb, n=nt_, seed=int(cj.g.get("seed", 0)), look=cj.lk, C=cj.sc.C,
                                       locks=cj.hair_locks)
        else:
            B = hair_clumps_bake.bake(bk, cj.St_, Wt, Hb, seed=int(cj.g.get("seed", 0)), look=cj.lk, C=cj.sc.C, locks=cj.hair_locks)
        cj.at = cj.make_atlas({**B, "key": hashlib.sha1(B["alpha"].tobytes() + (np.nan_to_num(B["gshare"]).tobytes()
                                                                         if B.get("gshare") is not None else b"")).hexdigest()})
        Ht, Hall = cj.at["rows"], cj.at["rows_total"]
        tint_ = B.get("tint", np.ones(len(bk)))
        for c_, (x_, y_, w_, h_), t_ in zip(bk, B["islands"], tint_):
            c_["tone_k"] = cj.at["bake_k"] * float(t_)
            c_["island"] = ((x_ + 0.5) / Wt, (x_ + w_ - 0.5) / Wt, 1 - (Ht + y_ + 0.5) / Hall, 1 - (Ht + y_ + h_ - 0.5) / Hall)
        cj.info["bake"] = {"cards": len(bk), "texel_mm": round(B["texel"] * 1000, 3), "rows": Hb,
                        "tiles": len(B.get("reps", [])) or None}


def _meshes(cj):
    """The colour model's peak taken out of the cap, the core and the tie; the card mesh; every uv moved to the final
    atlas's rows; each shell's uv in the atlas's shell block."""
    if cj.S.get("colour_model", True) and not cj.short:  # the atlas is lifted by the colour model's peak and the cards'
        # vertex colours carry tone / peak (hc.mesh); the cap, the tail's core and the tie wore 0.8-1.0: twice the
        # cards' value wherever they showed (the pale helmet / crown patch, the pale stripe down the back)
        from . import hair_colour as hcol
        pk_ = hcol.peak(cj.lk)
        cj.cap = {**cj.cap, "col": np.clip(np.asarray(cj.cap["col"], np.float32)
                                     * float(hair.CAP_TONE_TIERS.get(cj.tier_name, hair.CAP_TONE)) / pk_, 0, 1)}
        cj.core = None if cj.core is None else {**cj.core, "col": np.asarray(cj.core["col"], np.float32) / pk_}
        cj.band = [{**b_, "col": np.asarray(b_["col"], np.float32) / pk_} for b_ in cj.band]
    if cj.hc.BEND_ROWS > 0 and cj.cards:  # (round 47) see hc.lever_matched
        cj.hair_cards_budget.lever_matched("hair_cards.BEND_ROWS" + (f"[{','.join(cj.hc.BEND_CLS)}]" if cj.hc.BEND_CLS else ""),
                         sum(1 for c_ in cj.cards if cj.hair_cards_budget.bend_selected(c_)), len(cj.cards))
    cj.mc = cj.hair_cards_mesh.mesh(cj.cards, cj.S, cj.lk, cj.at["tiles"], segment=cj.seg)
    if cj.clumped or cj.at.get("rows_total", cj.at.get("rows")) != cj.at.get("rows"):  # everything else wears the tiles / chart, now the top rows of the atlas
        cj.mc = cj.hair_cards_atlas.remap_v(cj.mc, cj.at, cj.mc.get("baked"))
        cj.cap, cj.core, cj.mb = cj.hair_cards_atlas.remap_v(cj.cap, cj.at), cj.hair_cards_atlas.remap_v(cj.core, cj.at), cj.hair_cards_atlas.remap_v(cj.mb, cj.at)
        cj.band = [cj.hair_cards_atlas.remap_v(b_, cj.at) for b_ in cj.band]
    if cj.shell_raw is not None:  # (sh1) each shell's uv: its slot in the atlas's shell block (full-atlas coordinates)
        nc_, cu_, cv_, ns_ = cj.shell_raw
        sb_ = cj.at["shells"]
        Wt_, Hall_ = float(cj.at["color"].shape[1]), float(cj.at["rows_total"])
        uv_ = np.array(cj.cap["uv"], np.float32)
        for j_ in range(ns_):
            sl_ = slice(nc_ * (j_ + 1), nc_ * (j_ + 2))
            uv_[sl_, 0] = (j_ * sb_["slot_w"] + 0.5 + cu_ * (sb_["slot_w"] - 1.0)) / Wt_
            uv_[sl_, 1] = 1.0 - (sb_["row0"] + 0.5 + (1.0 - cv_) * (sb_["rows"] - 1.0)) / Hall_
        cj.cap = {**cj.cap, "uv": uv_}
        cj.info["shells"] = {"n": ns_, "triangles": int(len(cj.cap["tris"]) - len(cj.cap["tris"]) // (ns_ + 1)), "heights": [float(m_["height"]) for m_ in cj.shell_maps]}


def _clearance(cj):
    """Cards under the skin (against the body's own distance), and free cards rooted on bare skin: detached wisps."""
    # against the body's own signed distance (hair_loose_body.collider), not the scalp's rays: a ray from the head's centre
    # meets the EAR first, so cards lying on the head behind and over the ear read 5-6 cm "under the skin" and were
    # moved out to the ear's silhouette (Garrett: 936 hero vertices, the ragged dark patches behind the ear and at
    # the temple)
    cj.clearance = cj.hair_card_fit.card_clearance(cj.sc, cj.mc, [c.get("lock", "?") for c in cj.cards], fix=hair.CARD_CLEAR,
                               col=cj.col if cj.col is not None else cj.clear_col)
    # hair off the head must come OUT of the hair: a free card whose root lies on bare skin outside the hairline
    # is a detached wisp
    free_names = {k_["name"] for k_ in cj.hair_locks if float(k_.get("free", 0.0)) > 0.5 and k_.get("core") is None}
    det: dict = {}
    for c in cj.cards:
        if c.get("lock") in free_names:
            a_, e_, _h = cj.sc.coords(np.asarray(c["P"][:1], float))
            d_ = float(inside(cj.sc, cj.line, a_, e_)[0])
            if d_ < -0.003:
                det[c["lock"]] = round(min(det.get(c["lock"], 0.0), d_) * 1000, 1)
    cj.clearance["detached"] = det


def _write(cj):
    """The meshes joined and written, the atlas's files: the job's result."""
    m = cj.hair_cards_budget.join(cj.core, cj.mc, cj.mb, *cj.band)
    if os.environ.get("HP_CARDS_DUMP"):  # (debug: the kept cards, for probes)
        import pickle as _pk
        _pk.dump([{k_: c_.get(k_) for k_ in ("lock", "P", "X", "N", "hw", "layer", "kind", "prio", "s", "cls")} for c_ in cj.cards],
                 open(os.environ["HP_CARDS_DUMP"], "wb"))
    np.savez(cj.tmp / "cards.npz", **m)
    np.savez(cj.tmp / "cards_cap.npz", **cj.cap)
    files = cj.hair_cards_atlas.write_atlas(cj.at, str(cj.tmp / "hair"))
    return {"mesh": str(cj.tmp / "cards.npz"), "cap": str(cj.tmp / "cards_cap.npz"), "color": files["color"],
            "normal": files["normal"], "aux": files["aux"], "flow": files["flow"], "short": bool(cj.short),
            "triangles": int(len(m["tris"])),
            "cap_triangles": int(len(cj.cap["tris"])), "cards": len(cj.cards), "baby": len(cj.baby), "budget": cj.info,
            "coverage": cj.at["coverage"], "clearance": cj.clearance}


def stamp_cls(cards: list, locks: list) -> list:
    """(round 47) hair_clumps' card class ("tail" / "face" / "single" / "head"; "fly" for fly-aways) on clump_cards'
    cards, which carried none: every class filter (BEND_CLS, TAIL_AXIS_N, FIT_FLOOR) matched 0 cards at LOD1-3."""
    from .hair_clumps import classify
    by_ = {k_["name"]: k_ for k_ in locks}
    for c_ in cards:
        if c_.get("cls") is None:
            c_["cls"] = "fly" if c_.get("kind") == "fly" else classify(by_.get(c_.get("lock")) or {})
    return cards
