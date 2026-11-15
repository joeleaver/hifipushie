"""cards_job: the job that makes hair cards. Part of hair (hair.py has the overview)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from . import hair
from .hair import HairError
from .hair_groom import hairline, inside, look_of
from .hair_head import Scalp
from .hair_job import tier_drawn_max, tier_settings
from .hair_spec import hair_of
from .hair_cards_job_cards import _cards, _shell_cards
from .hair_cards_job_finish import _baby, _bake, _budget, _cap, _clearance, _meshes, _write

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
