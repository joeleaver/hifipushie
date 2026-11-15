"""What is worn: hair, clothes, lashes, and each part's look. Stages of the game-ready export (asset_export._export calls them in order; asset.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import asset
from .asset_budget import lash_cap
from .asset_gates import decimate_cloth, hair_tier_default
from .asset_glb import garment_over
from .asset_hidden import _over_chain, cloth_under_keep, cull_exposed_keep, cull_tris, under_cloth_keep

def _hair(ex):
    """Hair: curve locks meshed and baked in Blender on their own atlas, or a strand groom's cards."""
    ex.extra_ext = {}
    ex.hair_cards = None  # (the cards a strand groom ships as; set where the hair is exported)
    if (ex.spec.get("hair") or {}).get("locks"):  # curve locks (hair.py): meshed and baked in Blender, their own atlas
        from . import hair as hairmod
        from . import hair_export, hair_head
        ex.spec = hair_tier_default(ex.spec, ex.role, ex.log)
        from . import hair_route
        hw_ = hair_route.head_warning(ex.name, ex.spec)
        if hw_:
            ex.log.append(hw_)
        hp = hair_export.export_part(ex.name, ex.out_dir, ex.spec, texture=min(ex.texture, 2048), log=ex.log)
        if hp is not None:
            hpart, hfiles = hp
            ex.pn_h = (ex.spec["hair"].get("part") or "hair")
            hpart["atlas"] = len(ex.atlas_files)
            ex.parts[ex.pn_h] = hpart
            ex.origin[ex.pn_h] = ex.pn_h
            ex.atlas_files.append((ex.pn_h, hfiles))
            ex.maps_info[ex.pn_h] = {k: str(v) for k, v in hfiles.items()}
            ex.heights[ex.pn_h], ex.cover[ex.pn_h] = 0.0, 1.0
            ex.report[ex.pn_h] = {"triangles": len(hpart["corner_vert"]) // 3, "atlas": ex.pn_h, "curves": True}
            ex.hair_cards = hpart.pop("hair", None)
            if ex.hair_cards:
                k0 = sum(len(i_) for _, i_ in ex.atlas_files[:-1])
                ex.hair_cards["aux_texture"] = k0 + list(hfiles).index("aux")
                ex.report[ex.pn_h].update(cards=True, layers=ex.hair_cards["layers"], budget=ex.hair_cards["budget"],
                                    back_faces=bool(ex.hair_cards.get("back_faces")), vertices=len(hpart["verts"]))
            ex.names.append(ex.pn_h)
            ex.sizes[len(ex.names) - 1] = min(ex.texture, 2048)
            ex.ntri += ex.report[ex.pn_h]["triangles"]
            # a lock's sheen runs along it (the uv's v): anisotropy turned 90 degrees from the tangent (u, round the
            # lens), and a soft warm sheen
            lk = hairmod.full_look(ex.spec["hair"].get("look"))
            sheen = [round(float(c), 3) for c in hair_export.srgb_to_linear(lk["sheen"])]
            ex.extra_ext[len(ex.atlas_files) - 1] = {
                # (r59) half the specular, in the sheen's colour (hair.card_specular_tint): the default white x 2 mirrored
                # the key light off the crown's cards as a white plate (Tess rc2i, Garrett v5)
                # (no specular texture: the hair's is a flat 0.5; F0 = 0.04 x factor x colour = 0.02 x tint)
                "KHR_materials_specular": {"specularFactor": hairmod.CARD_SPECULAR,
                                           "specularColorFactor": hair_export.card_specular_tint(sheen)},
                "KHR_materials_anisotropy": {"anisotropyStrength": float(lk.get("anisotropic", 0.7)),
                                             "anisotropyRotation": 1.5708},
                "KHR_materials_sheen": {"sheenColorFactor": sheen, "sheenRoughnessFactor": 0.35}}


def _clothes(ex):
    """Clothes: a chain garment as export_garment wrote it, any other from the old simulation; the skin they cover dropped."""
    ex.chain_w, ex.chain_looks, ex.left_out, ex.chain_lods = {}, {}, [], {}
    if ex.spec.get("cloth"):  # garments. A chain garment (one with a garment record) ships as export_garment wrote it at
        # step 10 (garment_asset, C434: the old route re-simulated its draft and shipped that); any other garment is
        # the old simulation's (cloth.py): its settled mesh, the flat pattern as the uv
        from . import cloth as clothmod
        from . import garment_asset
        ex.garment_asset = garment_asset
        chain = ex.garment_asset.records(ex.name, ex.spec)
        gparts, ex.chain_w, ex.chain_looks, ex.left_out, ex.chain_lods = ex.garment_asset.parts(ex.name, chain, ex.out_dir, ex.log.append)
        for g_, why_ in ex.left_out:
            ex.log.append(f"NOT IN THIS EXPORT: garment {g_}: {why_}")
        old_ = {g_: v_ for g_, v_ in ex.spec["cloth"].items() if g_ not in chain}
        cparts = clothmod.export_part(ex.name, {**ex.spec, "cloth": old_}, ex.out_dir, texture=min(ex.texture, 2048),
                                      log=ex.log.append) if old_ else []
        n_c = sum(len(cp["corner_vert"]) // 3 for _, cp, _ in cparts)
        # (what covers the skin: the sim's own mesh before any decimation, and the chain garments as they ship)
        cover_by = [cp for _, cp, _ in cparts + gparts]
        if ex.cloth_triangles and n_c > ex.cloth_triangles:  # the sim's 1 cm mesh (two-sided) is far over a game budget:
            # decimated like a LOD (patches with their borders held: seams, hems, the pattern's uv)
            from . import lods as lodmod
            from . import lods_part, lods_under
            cparts = decimate_cloth(cparts, ex.cloth_triangles, ex.log)
        cparts = cparts + gparts  # (a chain garment's grid was already chosen for its role's budget: never decimated here)
        for pn_c, cpart, cfiles in cparts:
            cpart["atlas"] = len(ex.atlas_files)
            ex.parts[pn_c] = cpart
            ex.origin[pn_c] = pn_c
            ex.atlas_files.append((pn_c, cfiles))
            ex.maps_info[pn_c] = {k: str(v) for k, v in cfiles.items()}
            ex.heights[pn_c], ex.cover[pn_c] = 0.0, 1.0
            ex.report[pn_c] = {"triangles": len(cpart["corner_vert"]) // 3, "atlas": pn_c, "cloth": True}
            ex.names.append(pn_c)
            ex.sizes[len(ex.names) - 1] = min(ex.texture, 2048)
            ex.ntri += ex.report[pn_c]["triangles"]
        if ex.cull_under_cloth and cparts:  # skin the garments cover: never seen, and a bent limb pokes it through
            cl = cover_by
            skin_pn = (ex.spec.get("skin") or {}).get("part", "body")
            under = {skin_pn} | {p_ for p_, d_ in ex.defs.items() if (d_ or {}).get("shell") == skin_pn
                                 and not (d_ or {}).get("garment")}  # (the skin and paint-like shells: socks)
            for pn in list(ex.parts):
                if ex.report.get(pn, {}).get("cloth") or ex.report.get(pn, {}).get("curves") or pn in ex.pf_of:
                    continue
                if ex.origin.get(pn) not in under:
                    continue
                n0 = len(ex.parts[pn]["corner_vert"]) // 3
                keep = under_cloth_keep(ex.parts[pn], cl)
                if keep.all():
                    continue
                cm = np.repeat(keep, 3)
                for k_ in ("corner_vert", "uv", "normal", "tangent", "sign"):
                    ex.parts[pn][k_] = ex.parts[pn][k_][cm]
                ex.report[pn]["triangles"] = int(keep.sum())
                ex.report[pn]["under_cloth_dropped"] = int(n0 - keep.sum())
                ex.ntri -= int(n0 - keep.sum())
                ex.log.append(f"{pn}: {n0 - int(keep.sum())} of {n0} triangles under the garments dropped (covered "
                           f"within {asset.UNDER_CLOTH_REACH * 1000:.0f} mm along the normal, {asset.UNDER_CLOTH_RIM * 1000:.0f} mm "
                           "rim kept at every opening)")
            # (r53, coordinator) garment under garment: the faces of an under garment its covers hide (the same test,
            # reach and rim) are dropped at LOD0, so every LOD inherits it: rc2's jeans / sweater kept every triangle under
            # the coat, which cost budget and poked through at LOD1+
            cnames = [pn_c for pn_c, _, _ in cparts]
            over_ = garment_over(ex.spec, ex.log.append)
            for gn in over_:
                un = f"cloth_{gn}"
                ups = [f"cloth_{o_}" for o_ in over_ if gn in _over_chain(over_, o_)]
                cov = [cover_by[cnames.index(u_)] for u_ in ups if u_ in cnames]
                if un not in ex.parts or not cov or not asset.CLOTH_UNDER_CULL:
                    continue
                n0 = len(ex.parts[un]["corner_vert"]) // 3
                keep = cloth_under_keep(ex.parts[un], cov)
                if keep.all():
                    continue
                if ex.cull_poses:  # (r54) a face uncovered in ANY dumped clip frame is kept (cull_exposed_keep)
                    ups_ = [u_ for u_ in ups if u_ in ex.parts]
                    keep, ex_ = cull_exposed_keep(ex.parts[un], [ex.parts[u_] for u_ in ups_], un, ups_, ex.cull_poses, keep)
                    ex.log.append(f"{un}: {ex_['restored']} culled triangles restored, exposed in a clip frame "
                               f"({ex_['frames']} frames; worst {ex_['worst']})")
                    ex.report[un]["cull_exposed"] = ex_
                ex.parts[un] = cull_tris(ex.parts[un], keep)
                ex.report[un]["triangles"] = int(keep.sum())
                ex.report[un]["under_cloth_dropped"] = int(n0 - keep.sum())
                ex.ntri -= int(n0 - keep.sum())
                ex.log.append(f"{un}: {n0 - int(keep.sum())} of {n0} triangles under {', '.join(ups)} dropped (garment "
                           f"under garment, {asset.UNDER_CLOTH_RIM * 1000:.0f} mm rim kept at every opening)")


def _materials(ex):
    """Lashes, then each part's look: alpha, the hair cards' material, the skin's film and sheen, the eyes' tear film."""
    from . import lashes as lashmod
    lash = lashmod.export_part(ex.spec, ex.out_dir, log=ex.log.append)
    if lash:  # eyelash ribbons (lashes.py): their own mesh and tiny maps, two-sided; face shapes turn them with the lids
        pn_l, lpart, lfiles = lash
        cap_ = lash_cap(ex.rb, ex.report) if ex.rb else None
        if cap_ is not None:  # the eyes / mouth / lashes budget: the lashes fit what eyes, teeth, tongue and brows leave
            from .lods_part import ribbon_fit
            lpart, linfo_ = ribbon_fit(lpart, cap_)
            if linfo_["triangles"] < linfo_["triangles0"]:
                ex.log.append(f"lashes: {linfo_['triangles0']} -> {linfo_['triangles']} triangles ({linfo_['ribbons_kept']} of "
                           f"{linfo_['ribbons']} lashes, widened x{linfo_['widen']:.2f}) to fit eyes_mouth_lashes "
                           f"{int(ex.rb['parts']['eyes_mouth_lashes']['default'])}")
        lpart["atlas"] = len(ex.atlas_files)
        ex.parts[pn_l] = lpart
        ex.origin[pn_l] = pn_l
        ex.atlas_files.append((pn_l, lfiles))
        ex.maps_info[pn_l] = {k: str(v) for k, v in lfiles.items()}
        ex.heights[pn_l], ex.cover[pn_l] = 0.0, 1.0
        ex.report[pn_l] = {"triangles": len(lpart["corner_vert"]) // 3, "atlas": pn_l, "lashes": True}
        ex.names.append(pn_l)
        ex.sizes[len(ex.names) - 1] = 16
        ex.ntri += ex.report[pn_l]["triangles"]
    ex.glb = ex.out_dir / f"{ex.aname}.glb"
    ex.looks = {pn: {k: float(d[k]) for k in ("transmission", "alpha", "ior") if k in d}
             for pn in ex.parts for d in [ex.defs.get(ex.origin[pn]) or {}] if any(k in d for k in ("transmission", "alpha"))}
    for pn, lk_ in ex.chain_looks.items():  # (a chain garment's alpha-cut base map: frayed or lace edges)
        if pn in ex.parts:
            ex.looks.setdefault(pn, {}).update(lk_)
    if (ex.spec.get("hair") or {}).get("locks") and ex.hair_cards:
        ex.looks.setdefault(ex.pn_h, {}).update(alpha_cutoff=ex.hair_cards["alpha_cutoff"],
                                          double_sided=not ex.hair_cards.get("back_faces"),  # (c6: own back faces)
                                          extras={"hifipushie_hair": ex.hair_cards})
    if ex.skin_recipe:  # the skin part's own material: the film's second lobe and the sheen as ratified extensions, the
        sp = (ex.spec.get("skin") or {}).get("part", "body")  # rest (scattering, tiling detail) in its extras
        for pn in ex.parts:
            if ex.origin[pn] == sp:
                ex.looks.setdefault(pn, {}).update(
                    ext={"KHR_materials_clearcoat": {"clearcoatFactor": float(ex.skin_recipe["specular"]["coat"]),
                                                     "clearcoatRoughnessFactor": float(ex.skin_recipe["specular"]["coat_roughness"])},
                         "KHR_materials_sheen": {"sheenColorFactor": [float(ex.skin_recipe["sheen"])] * 3, "sheenRoughnessFactor": 0.5}},
                    extras={"hifipushie_skin": ex.skin_recipe})
    if lash:
        ex.looks.setdefault(lash[0], {})["double_sided"] = True
    from .skin_features_eyes import eye_base
    ex.ek = eye_base(ex.spec)
    if ex.ek:  # the eyes' tear film: a clear coat over the matte iris and sclera (the catchlight)
        for pn in ex.parts:
            if ex.origin.get(pn) == ex.ek[0]:
                ex.looks.setdefault(pn, {}).setdefault("ext", {})["KHR_materials_clearcoat"] = {
                    "clearcoatFactor": float(ex.ek[1]["coat"]), "clearcoatRoughnessFactor": float(ex.ek[1]["coat_roughness"])}
