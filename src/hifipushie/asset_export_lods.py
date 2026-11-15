"""LOD0 written, then the LODs. Stages of the game-ready export (asset_export._export calls them in order; asset.py has the overview)."""
from __future__ import annotations

import os
import time

import numpy as np

from . import asset
from .asset_glb import _garment_stack, write_glb
from .asset_hidden import cull_tris, cull_under_garments, garment_cull_masks, skin_pose_exposed

def _lods(ex):
    """LOD0 written, then the LODs: per part by its role's ratios, hair tiers, chain garments' own files, garments kept over each other."""
    write_glb(ex.glb, ex.aname, ex.parts, ex.atlas_files, ex.ctx["prefabs"], ex.looks, ex.rigged, ex.extra_ext)
    ex.lod_info = []
    if ex.lods:
        from . import lods as lodmod
        from . import lods_part, lods_under
        ratios = list(lodmod.LOD_RATIOS) if ex.lods is True else [float(r) for r in ex.lods]
        above = below = None  # (the role's LOD ratios above and below the neck; set with a role's budgets)
        ratio_of, mesh_r, shape_lods = None, None, None
        if ex.rb is not None and ex.lods is True:
            from . import budgets as budgetmod
            above, below = budgetmod.lod_ratios("head"), budgetmod.lod_ratios("body")
            ratios = budgetmod.lod_ratios(None)[1:]
            shape_lods = set((ex.rb.get("face_shapes") or {}).get("lods") or [0])

            ratio_of = True
        cards = [pn for pn in ex.parts if ex.report[pn].get("curves") or ex.report[pn].get("lashes")]
        tier_parts = {}
        if ex.hair_cards:  # hair LODs are the groom's own card TIERS (one atlas for all:
            # hair.export_hair), cut for their budget; thinning LOD0's cards dropped the tail first. (Unrigged too,
            # round 25: whole layers dropped once, 11996 -> 5324 at LOD1 and flat at LOD2 / LOD3.)
            from . import hair as hairmod
            from . import hair_export, hair_head
            hb_ = next((i for i, b in enumerate(ex.rigged["bones"]) if b["name"].endswith("Head")), 0) if ex.rigged else 0
            for k, r in enumerate(ratios, 1):
                tier_ = lodmod.HAIR_TIERS[min(k, len(lodmod.HAIR_TIERS)) - 1]
                sp_ = {**ex.spec, "hair": {**ex.spec["hair"], "export": {**(ex.spec["hair"].get("export") or {}), "tier": tier_}}}
                try:
                    ex.tp_, ex._tf = hair_export.export_cards(ex.name, ex.out_dir / f"_lod{k}", sp_, ex.log)
                except Exception as e:  # (LOD0 hair kept)
                    ex.log.append(f"WARNING LOD{k}: hair tier {tier_} failed ({type(e).__name__}: {e}); LOD0's cards kept")
                    continue
                ex.tp_.pop("hair", None)
                own_ = None
                if hair_export.share_atlas(ex.tp_, ex._tf, dict(ex.atlas_files[ex.parts[ex.pn_h]["atlas"]][1])):
                    ex.tp_["atlas"] = ex.parts[ex.pn_h]["atlas"]  # (its uv on LOD0's atlas: a tier's atlas lacks the baked rows)
                else:  # its own maps beside the GLBs (a tier whose pictures differ from LOD0's)
                    import shutil
                    own_ = {}
                    for mk_, f_ in ex._tf.items():
                        own_[mk_] = ex.out_dir / f"{ex.pn_h}_lod{k}_{mk_}.png"
                        shutil.copyfile(f_, own_[mk_])
                    ex.log.append(f"LOD{k}: hair tier {tier_}'s atlas differs from LOD0's: it carries its own maps")
                nv_ = len(ex.tp_["verts"])
                Jh = np.zeros((nv_, 4), np.int64)
                Jh[:, 0] = hb_
                Wh = np.zeros((nv_, 4), np.float32)
                Wh[:, 0] = 1.0
                tier_parts[k] = (ex.tp_, (Jh, Wh), tier_, own_)
        layer_stack = {}  # (r53) {under garment part: the garment parts over it, transitively}: each LOD puts the under
        # garments back under their decimated covers (lods_under.push_under_layers)
        if ex.spec.get("cloth") and asset.LOD_PUSH_UNDER:
            layer_stack = _garment_stack(ex.spec, ex.parts)
        under_masks = {}  # (r54) parts worn under garments that are not garments (socks, the body): put back under the
        # garments too, but only where they were under one at LOD0 (lods_under.under_at_lod0). rc2c's LOD2 showed the socks
        # (kept whole) through the decimated jeans' calves (101 vertices poking, 1 at LOD0) and the body through the sweater.
        garm_ = [pn for pn in ex.parts if pn.startswith("cloth_") and pn not in ex.pf_of]
        if garm_ and asset.LOD_PUSH_UNDER and asset.LOD_PUSH_WORN:
            for pn, p in ex.parts.items():
                if (pn in garm_ or pn in ex.pf_of or pn in cards or pn in asset.LOD_PUSH_WORN_SKIP or ex.report.get(pn, {}).get("lashes")
                        or p.get("shell")):
                    continue
                P0_, un0_, sh_, ov0_, N0_ = lods_under.under_at_lod0(p, [ex.parts[g] for g in garm_], share=True)
                if int(un0_.sum()) >= asset.LOD_PUSH_WORN_MIN and sh_ >= asset.LOD_PUSH_WORN_SHARE:
                    layer_stack[pn] = list(garm_)
                    under_masks[pn] = (P0_, ~ov0_ if asset.LOD_PUSH_WORN_NOT_OVER else un0_, sh_, N0_, un0_)  # (r55) every vertex NOT over a
                    # garment at LOD0 may move: rc2d's LOD2 left calf showed 22 sock vertices through the jeans whose LOD0
                    # vertices had no jeans within reach (a loose leg), so the 'under at LOD0' mask kept them still
            sk_ = (ex.spec.get("skin") or {}).get("part", "body")
            if sk_ in under_masks and asset.LOD_SKIN_CULL_FROM is not None:  # (Garrett s14) the skin's deep-covered faces drop at
                # LOD >= LOD_SKIN_CULL_FROM too (its residue under the jacket's armhole poked through the decimated sleeve:
                # the underarm notch), except where a dumped clip frame (cull_poses: the seated poses) uncovers it
                P0_, a_, b_, c_, un0_ = under_masks[sk_]
                exp_ = skin_pose_exposed(ex.parts[sk_], P0_, [ex.parts[g] for g in garm_], sk_, garm_, ex.cull_poses)
                under_masks[sk_] = (P0_, a_, b_, c_, un0_, un0_ & ~exp_)  # [5]: what the per-LOD cull may drop
                ex.log.append(f"LODs: {sk_}: {int(un0_.sum())} LOD0 points under the garments, {int((un0_ & exp_).sum())} of them "
                           f"uncovered in a clip frame (kept at every LOD)")
            if under_masks:
                ex.log.append("LODs: parts worn under garments also put back under them: " + ", ".join(
                    f"{pn} ({int(m_[1].sum())} vertices free to move, {m_[2]:.0%} of those in reach under)" for pn, m_ in under_masks.items()))
        garment_cull = garment_cull_masks(ex.parts, layer_stack, garm_)  # (Garrett s10) under garments' LOD0 cover masks
        through0 = {}  # (C441) {part worn under: (its LOD0 points, covered by a chain garment there)}: garment_asset.skin_through
        if ex.chain_lods:
            from . import garment_asset
            ex.garment_asset = garment_asset
            cov0_ = [ex.parts[g_] for g_ in ex.chain_w if g_ in ex.parts and ex.parts[g_].get("shell")]
            through0 = {pn: ex.garment_asset.covered_at_lod0(ex.parts[pn], cov0_, m_) for pn, m_ in under_masks.items()
                        if cov0_ and len(m_) >= 5}
        if os.environ.get("HP_LOD_DUMP"):  # (r60, debug: the LOD inputs, to probe a part's LOD steps offline)
            import pickle
            with open(os.environ["HP_LOD_DUMP"], "wb") as fh:
                pickle.dump({"parts": {pn: p for pn, p in ex.parts.items() if pn not in ex.pf_of and pn not in cards},
                             "rigged": ex.rigged, "layer_stack": layer_stack, "under_masks": under_masks,
                             "ratios": ratios, "above": above, "below": below}, fh)
        for k, r in enumerate(ratios, 1):
            tl = time.time()
            if ratio_of is not None:  # above the neck holds detail longer than below it (budgets.lod_ratios)
                ex.kk_ = min(k, len(above) - 1)
                skin_pn_ = (ex.spec.get("skin") or {}).get("part", "body")

                def r_part(pn, kk_=ex.kk_):  # head parts (the skin's head mesh by mesh_ratios) above, the rest below
                    if pn == skin_pn_ or pn in ("eyes", "teeth", "teeth_lower", "tongue") or ex.report.get(pn, {}).get("lashes"):
                        return above[kk_]
                    return below[min(kk_, len(below) - 1)]
                rr_, mesh_r = r_part, {"head": above[ex.kk_], "body": below[min(ex.kk_, len(below) - 1)]}
            else:
                rr_ = r
            own_ = {pn: v for pn, v in ex.chain_lods.get(k, {}).items() if pn in ex.parts}  # (C439) a chain garment's LOD is
            # its own file (export_garment's re-grid at a coarser grid), never a decimation of its LOD0
            lp, lr, rep_l = lods_part.lod_parts({pn: p for pn, p in ex.parts.items() if pn not in ex.pf_of and pn not in own_},
                                             ex.rigged, rr_, skip=cards,
                                             cards={ex.pn_h: ex.hair_cards["layers"]} if ex.hair_cards and k not in tier_parts else None,
                                             mesh_ratios=mesh_r, shapes=(shape_lods is None or k in shape_lods),
                                             ribbons=[pn for pn in cards if ex.report[pn].get("lashes")])
            if own_:
                from . import garment_asset
                ex.garment_asset = garment_asset
                ex.log.append(f"LOD{k}: " + ex.garment_asset.take_lods(own_, ex.parts, lp, lr, rep_l, ex.rigged and ex.rigged["bones"]))
            for pn in ex.chain_w:  # (a garment with LOD files, but none for this LOD: more LODs asked than its role has)
                if pn in ex.parts and pn not in own_ and any(pn in v_ for v_ in ex.chain_lods.values()):
                    ex.log.append(f"WARNING LOD{k}: {pn} has no LOD{k} file of its own: DECIMATED from LOD0 like any part "
                               "(export_garment writes one file per LOD of its role)")
            if layer_stack:
                rb_ = below[min(ex.kk_, len(below) - 1)] if ratio_of is not None else r
                pu_ = lods_under.push_under_layers(lp, layer_stack, masks=under_masks, face_deep=(
                    lodmod.LOD_UNDER_FACE_DEEP_FAR if rb_ < lodmod.LOD_SMALL_FAR_RATIO else None))
                ex.log.append(f"LOD{k}: under garments put back under their covers (lods_under.push_under_layers): " + ", ".join(
                    f"{pn} poking {v['poking0']} -> {v['poking']} ({v['moved']} moved{', %d capped' % v['capped'] if v.get('capped') else ''})" for pn, v in pu_.items()))
                for pn, v in pu_.items():
                    rep_l.setdefault(pn, {})["under"] = v
            skin_pn0_ = (ex.spec.get("skin") or {}).get("part", "body")
            for pn, m_ in under_masks.items():  # (r60) the worn parts' covered rims (socks); (s14) the skin's from its own LOD
                    from_ = asset.LOD_SKIN_CULL_FROM if pn == skin_pn0_ else lodmod.LOD_UNDER_CULL_FROM
                    if not from_ or k < from_ or pn not in lp or len(m_) < 5:
                        continue
                    kc_ = lods_under.cull_covered(lp[pn], m_[0], m_[5] if len(m_) > 5 else m_[4])
                    if not kc_.all():
                        lp[pn] = cull_tris(lp[pn], kc_)
                        rep_l.setdefault(pn, {})["covered_culled"] = int((~kc_).sum())
                        rep_l[pn]["triangles"] = len(lp[pn]["corner_vert"]) // 3
                        ex.log.append(f"LOD{k}: {pn}: {int((~kc_).sum())} of {len(kc_)} triangles deep under the garments at LOD0 "
                                   f"dropped (lods_under.cull_covered, {lodmod.LOD_UNDER_CULL_RIM * 1000:.0f} mm rim)")
            for pn, m_ in (through0.items() if own_ else ()):  # (C441) skin still THROUGH a chain garment's own LOD
                # cloth (its flat faces sink further than the push-under looks or moves), covered at LOD0: cut
                cov_ = [lp[g_] for g_ in own_ if g_ in lp and lp[g_].get("shell")]
                if pn not in lp or not cov_:
                    continue
                kt_ = ex.garment_asset.skin_through(lp[pn], cov_, m_[0], m_[1])
                if not kt_.all():
                    lp[pn] = cull_tris(lp[pn], kt_)
                    rep_l.setdefault(pn, {})["through_cut"] = int((~kt_).sum())
                    rep_l[pn]["triangles"] = len(lp[pn]["corner_vert"]) // 3
                    ex.log.append(f"LOD{k}: {pn}: {int((~kt_).sum())} of {len(kt_)} triangles through the garments' own LOD "
                               f"cloth cut (covered at LOD0; garment_asset.skin_through, {ex.garment_asset.THROUGH_REACH * 1000:.0f} mm reach)")
            cull_under_garments(lp, garment_cull, k, ex.log, rep_l)
            atl_k, ext_k = ex.atlas_files, ex.extra_ext
            if k in tier_parts:
                ex.tp_, w_, tier_, own_ = tier_parts[k]
                if own_ is not None:  # (an atlas of its own, wearing the hair material's extensions)
                    hi_ = ex.parts[ex.pn_h]["atlas"]
                    ex.tp_ = {**ex.tp_, "atlas": len(ex.atlas_files)}
                    atl_k = ex.atlas_files + [(f"{ex.pn_h}_lod{k}", own_)]
                    ext_k = {**ex.extra_ext, **({len(ex.atlas_files): ex.extra_ext[hi_]} if hi_ in ex.extra_ext else {})}
                lp[ex.pn_h] = ex.tp_
                if lr is not None:
                    lr["weights"][ex.pn_h] = w_
                rep_l[ex.pn_h] = {"triangles0": len(ex.parts[ex.pn_h]["corner_vert"]) // 3,
                               "triangles": len(ex.tp_["corner_vert"]) // 3, "tier": tier_,
                               "atlas": "own" if own_ is not None else "LOD0's"}
            lg = ex.out_dir / f"{ex.aname}_LOD{k}.glb"
            write_glb(lg, ex.aname, lp, atl_k, {}, ex.looks, lr, ext_k, external=True)
            tri_k = sum(v["triangles"] for v in rep_l.values())
            ex.lod_info.append({"lod": k, "ratio": r, "glb": str(lg), "triangles": tri_k,
                             "parts": {pn: v["triangles"] for pn, v in rep_l.items()}})
            ex.log.append(f"LOD{k} ({r:g} of LOD0): {tri_k} triangles in {time.time() - tl:.1f}s -> {lg.name} (maps "
                       f"by file name beside it); " + ", ".join(f"{pn} {v['triangles']}" for pn, v in rep_l.items()))
        import shutil
        for k in tier_parts:  # (the tiers' own copies of the shared hair atlas)
            shutil.rmtree(ex.out_dir / f"_lod{k}", ignore_errors=True)
