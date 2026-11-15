"""After the cards are cut: the cap under them, baby hairs, the budget, the clump cards' bake, the meshes, clearance,
the files. The last seven stages of `cards_job` (hair_cards_job.cards_job calls them in order; hair.py has the
overview)."""
from __future__ import annotations

import hashlib
import os

import numpy as np

from . import hair
from .hair import _ss, _unit
from .hair_groom import inside
from .hair_job import baby_locks, card_allowance, card_cap
from .hair_lockmesh import shell_gaps

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
