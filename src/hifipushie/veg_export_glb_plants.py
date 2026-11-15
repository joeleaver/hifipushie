"""A plant GLB's meshes and nodes: every plant's LODs (wood, foliage, bough cards), the impostor as the last LOD,
MSFT_lod, the collision mesh, the counts. One stage of `write_glb` (veg_export_glb.write_glb calls them in order; veg_export.py has the contract)."""
from __future__ import annotations

import json

import numpy as np

from . import veg_export
from . import veg_bough, veg_impostor, veg_mesh, veg_style
from . import veg_leaf_atlas, veg_leaf_place
from . import veg_style_dress
from . import vegetation_grow
from .veg_export import _yup, veg_small_state
from .veg_export_parts import budget, cluster_leaves, collision, foliage_mesh, impostor_frames, season_atlas, wind_nodes

def _plants(pg):
    """Every plant's meshes and nodes: per LOD its wood and foliage (a style's dress, or the budget's wood and cards, bough
    cards with their own pictures), the impostor as the last LOD, MSFT_lod, the collision mesh, the plant's counts.
    One loop over the plants: a stage begins only at a statement of `write_glb` itself."""
    pg.per, pg.roots = [], []
    cluster_mats = {}
    head_mats = {}
    if pg.spacing is None:
        pg.spacing = 0.0 if len(pg.trees) == 1 else 1.2 * max(float(np.percentile(np.linalg.norm(t["pos"][:, :2], axis=1), 98)) for t in pg.trees) * 2
    n_lod = int(np.clip(pg.lods, 1, len(veg_export.LODS)))
    for k, (t, nm) in enumerate(zip(pg.trees, pg.names)):
        wn = wind_nodes(t)
        lod_nodes, lod_info = [], []
        for li in range(0 if pg.only_impostor else n_lod):
            share, cap_ = veg_export.LODS[li]
            cap_i = cap_ if n_lod > 1 or pg.cap is None else pg.cap
            if pg.st:
                D = veg_style_dress.dress(t, pg.st, int(pg.triangles * share), pg.se0 if pg.has_leaves else "summer")
                if pg.has_leaves and D["crown"] is None:  # (the file's default season is a bare one: the masses are still in it, hidden)
                    D = veg_style_dress.dress(t, pg.st, int(pg.triangles * share), "summer")
                pre = (f"{nm}_" if len(pg.trees) > 1 else "") + (f"LOD{li}_" if n_lod > 1 or pg.impostor is not None else "")
                W = D["wood"]
                kids = []
                wp = [pg.with_variants(pg.prim(W["V"], W["F"], W["uv"], pg.M_BARK, D["wood_wind"], N=W["N"]), pg.var_bark, pg.M_BARK)]
                K_ = D["forks"]
                if K_ is not None and pg.M_FORK is not None:
                    wp.append(pg.with_variants(pg.prim(K_["V"], K_["F"], K_["uv"], pg.M_FORK, K_["wind"], N=K_["N"]), pg.var_fork, pg.M_FORK))
                pg.meshes.append({"name": pre + "wood", "primitives": wp})
                pg.nodes.append({"name": pre + "wood", "mesh": len(pg.meshes) - 1})
                kids.append(len(pg.nodes) - 1)
                c = {"name": nm, "lod": li, "height_m": round(t["height"], 2), "wood_triangles": int(len(W["F"])), "foliage_triangles": 0,
                     "twigs_kept": 1.0, "wood_min_radius_m": 0.0, "floating": 0.0, "style": D["info"]}
                C_ = D["crown"]
                if C_ is not None:
                    p_ = pg.prim(C_["V"], C_["F"], C_["uv"], pg.M_FOL, C_["wind"], C_["col"], C_["N"], uv3=C_.get("grad"))
                    fp = [pg.with_variants(p_, pg.var_fol, pg.M_FOL)]
                    K_ = D.get("cards")
                    if K_ is not None and pg.M_CARDS is not None:  # pixar: the leaf cards on the shell
                        fp.append(pg.with_variants(pg.prim(K_["V"], K_["F"], K_["uv"], pg.M_CARDS, K_["wind"], K_["col"], K_["N"], uv3=K_["grad"]), pg.var_cards, pg.M_CARDS))
                        c["cards_triangles"] = int(len(K_["F"]))
                    Hd = D.get("heads")
                    if Hd is not None:  # a small plant's flower / seed heads: the foliage mesh's second primitive, slot `heads`
                        if "heads" not in head_mats:
                            shown = {"name": "heads", "pbrMetallicRoughness": {"baseColorFactor": [1.0, 1.0, 1.0, 1.0], "metallicFactor": 0.0,
                                                                                "roughnessFactor": float(pg.st["crown"].get("roughness", 0.85))}}
                            hid_ = {**json.loads(json.dumps(shown)), "alphaMode": "MASK", "alphaCutoff": 1.01, "extras": {"hidden": True}}
                            d_show = pg.se0 in Hd["seasons"]
                            (hid_ if d_show else shown)["name"] = "heads_hidden" if d_show else "heads_shown"
                            (shown if d_show else hid_)["name"] = "heads"
                            pg.materials.extend([shown, hid_])
                            head_mats["heads"] = {se: len(pg.materials) - (2 if se in Hd["seasons"] else 1) for se in pg.seasons}
                        vh = head_mats["heads"]
                        hcol = np.array([veg_style.lin(c_) for c_ in Hd["part_colors"]])[Hd["part"]]  # (COLOR_0 = each part's colour, linear: petals, centre, stalk)
                        fp.append(pg.with_variants(pg.prim(Hd["V"], Hd["F"], Hd["uv"], vh[pg.se0], Hd["wind"], hcol, N=Hd["N"]), vh, vh[pg.se0]))
                        c["heads_triangles"] = int(len(Hd["F"]))
                    if pg.M_FW is not None:  # the blades lying down (winter, snow): their own primitive
                        if "_winter_tree" not in t:
                            t["_winter_tree"] = vegetation_grow.grow({**t["spec"], "season": "winter"})
                        Dw = veg_style_dress.dress(t["_winter_tree"], pg.st, int(pg.triangles * share), "winter")
                        Cw = Dw["crown"]
                        if Cw is not None:
                            fp.append(pg.with_variants(pg.prim(Cw["V"], Cw["F"], Cw["uv"], pg.M_FW, Cw["wind"], Cw["col"], Cw["N"], uv3=Cw.get("grad")), pg.var_fw, pg.M_FW))
                            c["winter_triangles"] = int(len(Cw["F"]))
                    pg.meshes.append({"name": pre + "foliage", "primitives": fp})
                    pg.nodes.append({"name": pre + "foliage", "mesh": len(pg.meshes) - 1})
                    kids.append(len(pg.nodes) - 1)
                    c["foliage_triangles"] = int(len(C_["F"])) + c.get("heads_triangles", 0) + c.get("cards_triangles", 0)
                c["triangles"] = c["wood_triangles"] + c["foliage_triangles"]
                lod_info.append(c)
                if n_lod == 1 and pg.impostor is None and len(pg.trees) == 1:
                    lod_nodes.append(kids)
                else:
                    pg.nodes.append({"name": f"{nm}_LOD{li}", "children": kids})
                    lod_nodes.append([len(pg.nodes) - 1])
                continue
            bud = budget(t, int(pg.triangles * share) if pg.triangles else None, pg.tile, pg.at["triangles"] if pg.at else 0, cap_i)
            if li and not pg.triangles:  # no budget asked: lower LODs still step down from the full tree
                full = lod_info[0]["triangles"]
                bud = budget(t, int(full * share), pg.tile, pg.at["triangles"] if pg.at else 0, cap_i)
            W = bud["wood"]
            lf_c, cap_c, back_c = cluster_leaves(pg.s["leaves"], bud["keep"])
            at_c, m_c, vf_c = pg.at, pg.M_FOL, pg.var_fol
            tw_c = None
            boughs = bool(bud.get("boughs")) and pg.at is not None
            if pg.at is not None and (boughs or lf_c is not pg.s["leaves"]):  # bough cards: their own picture (and its season variants)
                # (LODs thinned from one cut of the tree share its atlas and material: one foliage_boughs slot)
                cut_ = (veg_bough.base_of(t, bud["boughs"]), veg_bough.form_of(t, bud["boughs"])) if boughs and len(pg.trees) == 1 else (None, 0)
                ck = (f"boughs_cut{cut_[0]}_{cut_[1]}" if cut_[0] else f"boughs{li}") if boughs else json.dumps(lf_c["card"], sort_keys=True)
                if ck not in cluster_mats:
                    # (a set shares one bough atlas per LOD: baked from the first plant that needs it)
                    make = (lambda lf_, twc_, t0=t, nb=bud["boughs"]: veg_bough.atlas(t0, lf_, twc_, nb)) if boughs else veg_leaf_atlas.atlas
                    sp_c = {**pg.s, "leaves": pg.s["leaves"] if boughs else lf_c}
                    at_c = make(sp_c["leaves"], pg.twc)
                    m_ = pg.foliage_material(at_c, f"foliage_boughs{len(cluster_mats) + 1}")
                    vf_ = {}
                    for se in pg.seasons:
                        a_ = season_atlas(sp_c, se, pg.twc, make) if se != "summer" else at_c
                        if a_ is None:
                            pg.materials.append({**json.loads(json.dumps(pg.materials[m_])), "name": f"{pg.materials[m_]['name']}_{se}", "alphaCutoff": 1.01})
                            pg.materials[-1]["extras"] = {**pg.materials[-1].get("extras", {}), "hidden": True}
                            vf_[se] = len(pg.materials) - 1
                        else:
                            vf_[se] = m_ if a_ is at_c else pg.foliage_material(a_, f"{pg.materials[m_]['name']}_{se}")
                    if pg.wet:
                        mw_ = json.loads(json.dumps(pg.materials[m_]))
                        mw_["name"] += "_wet"
                        mw_["pbrMetallicRoughness"].update(baseColorFactor=[0.78, 0.8, 0.76, 1.0], roughnessFactor=0.45)
                        pg.materials.append(mw_)
                        vf_["wet"] = len(pg.materials) - 1
                    cluster_mats[ck] = (at_c, m_, vf_)
                at_c, m_c, vf_c = cluster_mats[ck]
                if boughs:
                    tw_c = veg_bough.place(t, bud["boughs"], at_c)
            L = foliage_mesh(t, at_c, bud["keep"], bud["min_radius"], bud["protect"], cap_c if at_c is not pg.at else cap_i, back_c, tw=tw_c) \
                if pg.at and len(veg_leaf_place.place(t)["pos"]) else None
            pre = (f"{nm}_" if len(pg.trees) > 1 else "") + (f"LOD{li}_" if n_lod > 1 or pg.impostor is not None else "")
            kids = []
            wn_w = W["node"]
            p_ = pg.prim(W["V"], W["F"], W["uv"], pg.M_BARK, (wn["trunk"][wn_w], wn["branch"][wn_w], wn["phase"][wn_w], np.zeros(len(wn_w))))
            pg.meshes.append({"name": pre + "wood", "primitives": [pg.with_variants(p_, pg.var_bark, pg.M_BARK)]})
            pg.nodes.append({"name": pre + "wood", "mesh": len(pg.meshes) - 1})
            kids.append(len(pg.nodes) - 1)
            c = {"name": nm, "lod": li, "height_m": round(t["height"], 2), "wood_triangles": int(len(W["F"])), "foliage_triangles": 0,
                 "twigs_kept": round(bud["keep"], 3), "wood_min_radius_m": round(bud["min_radius"], 4),
                 "floating": round(bud["floating"], 3)}
            if L is not None and len(L["F"]):
                def card_wind(L, wn):
                    fn = L["node"]
                    wch = (wn["trunk"][fn], wn["branch"][fn], wn["phase"][fn], L["flutter"])
                    if t.get("clump"):  # a small plant's card bends as a whole from its foot, each in its own phase; long
                        # cards swing further (the recipe's limb amplitude is 0.25 m: a 30 cm tuft's tip moves ~5 cm)
                        own = L["flutter"] ** 1.5 * np.clip(L["reach"] / 1.2, 0.08, 1.0)
                        wch = (wn["trunk"][fn], np.maximum(wn["branch"][fn], own), np.where(wn["branch"][fn] > own, wn["phase"][fn], L["phase"]),
                               0.5 * L["flutter"])
                    return wch
                p_ = pg.prim(L["V"], L["F"], L["uv"], m_c, card_wind(L, wn),
                          L["tint"], L["N"])
                fprims = [p_]
                lie_r = [se for se in pg.seasons if se in ("winter", "snow")]
                if (t.get("clump") and len(pg.trees) == 1 and lie_r and pg.seasons[0] not in lie_r
                        and float((veg_small_state(pg.s, "winter") or {}).get("flatten", 0.0)) > 0):
                    # a realistic small plant whose blades lie down in winter: as the styled ones, slot foliage_winter =
                    # the cards of the plant regrown at season winter, shown in winter / snow while foliage is hidden
                    if "_winter_tree" not in t:
                        t["_winter_tree"] = vegetation_grow.grow({**t["spec"], "season": "winter"})
                    tw_ = t["_winter_tree"]
                    Lw = foliage_mesh(tw_, at_c, bud["keep"], bud["min_radius"], bud["protect"], cap_c if at_c is not pg.at else cap_i, back_c)
                    if not len(Lw["F"]):  # (a low LOD's keep share can leave the lying plant no cards: keep them all, it is small)
                        Lw = foliage_mesh(tw_, at_c, 1.0, 0.0, None, cap_c if at_c is not pg.at else cap_i, back_c)
                    if len(Lw["F"]):
                        hk = ("lie", m_c)
                        if hk not in cluster_mats:
                            hid = [{**json.loads(json.dumps(pg.materials[m_c])), "name": f"{pg.materials[m_c]['name']}_{sfx}", "alphaCutoff": 1.01}
                                   for sfx in ("winter", "lying")]
                            for h_ in hid:
                                h_["extras"] = {**h_.get("extras", {}), "hidden": True}
                            pg.materials.extend(hid)
                            cluster_mats[hk] = (len(pg.materials) - 2, len(pg.materials) - 1)
                        m_w, m_l = cluster_mats[hk]
                        tab_main = {se: (m_l if se in lie_r else vf_c.get(se, m_c)) for se in pg.seasons}
                        tab_w = {se: (vf_c.get(se, m_c) if se in lie_r else m_w) for se in pg.seasons}
                        fprims = [pg.with_variants(p_, tab_main, m_c),
                                  pg.with_variants(pg.prim(Lw["V"], Lw["F"], Lw["uv"], m_w, card_wind(Lw, wind_nodes(tw_)), Lw["tint"], Lw["N"]), tab_w, m_w)]
                        c["winter_triangles"] = int(len(Lw["F"]))
                if len(fprims) == 1:
                    fprims = [pg.with_variants(p_, vf_c, m_c)]
                pg.meshes.append({"name": pre + "foliage", "primitives": fprims})
                c["boughs"] = at_c is not pg.at
                pg.nodes.append({"name": pre + "foliage", "mesh": len(pg.meshes) - 1})
                kids.append(len(pg.nodes) - 1)
                c["foliage_triangles"] = int(len(L["F"]))
            c["triangles"] = c["wood_triangles"] + c["foliage_triangles"]
            lod_info.append(c)
            if n_lod == 1 and pg.impostor is None and len(pg.trees) == 1:
                lod_nodes.append(kids)
            else:
                pg.nodes.append({"name": (f"{nm}_" if len(pg.trees) > 1 else f"{nm}_") + f"LOD{li}", "children": kids})
                lod_nodes.append([len(pg.nodes) - 1])
        if pg.impostor is not None and k == 0 and len(pg.trees) == 1 and pg.impostor.get("kind") == veg_impostor.KIND:
            # hemi-octahedral: ONE quad, rebuilt to face the camera by the engine's shader (veg_impostor.recipe); stored as
            # a vertical square through the bake centre facing +y (glTF +z), uv 0..1 = its corners
            S_, Cg = float(pg.impostor["size"]), np.asarray(pg.impostor["centre"], float)
            Cb = np.array([Cg[0], -Cg[2], Cg[1]])
            u0_, u1_, v0_, v1_ = pg.crop_ or [0.0, 1.0, 0.0, 1.0]
            xa_, xb_ = (u0_ - 0.5) * S_, (u1_ - 0.5) * S_
            za_, zb_ = (0.5 - v1_) * S_, (0.5 - v0_) * S_
            Vq = np.array([Cb + [xa_, 0, za_], Cb + [xb_, 0, za_], Cb + [xb_, 0, zb_], Cb + [xa_, 0, zb_]])
            Uq = np.array([[0, 1.0], [1, 1], [1, 0], [0, 0]])
            Fq = np.array([[0, 1, 2], [0, 2, 3]])
            Nq = np.tile([0, -1.0, 0], (4, 1))
            zt = np.clip(Vq[:, 2] / max(t["height"], 1e-6), 0, 1) ** 1.5
            z4 = np.zeros(4)
            p_ = pg.prim(Vq, Fq, Uq[:, [0, 1]] * [1, -1] + [0, 1], pg.M_IMP, (zt, z4, z4, z4), N=Nq)
            pg.meshes.append({"name": f"LOD{n_lod}_impostor", "primitives": [pg.with_variants(p_, pg.var_imp, pg.M_IMP)],
                           "extras": {"hifipushie_impostor": veg_impostor.KIND, "cull_margin_m": round(0.5 * S_, 3)}})
            pg.nodes.append({"name": f"{nm}_LOD{0 if pg.only_impostor else n_lod}", "mesh": len(pg.meshes) - 1})
            lod_nodes.append([len(pg.nodes) - 1])
            lod_info.append({"name": nm, "lod": n_lod, "triangles": 2, "impostor": True, "impostor_kind": veg_impostor.KIND})
        elif pg.impostor is not None and k == 0 and len(pg.trees) == 1:
            S_, H_ = float(pg.impostor["size"]), float(pg.impostor["height"])
            Vq, Fq, Uq, Nq, Tq = [], [], [], [], []
            for j, (r_, o_) in enumerate(impostor_frames()):  # each picture on the quad its camera faced; then that quad's back
                q = np.array([-0.5 * S_ * r_ + [0, 0, H_ - 0.5 * S_], 0.5 * S_ * r_ + [0, 0, H_ - 0.5 * S_],
                              0.5 * S_ * r_ + [0, 0, H_ + 0.5 * S_], -0.5 * S_ * r_ + [0, 0, H_ + 0.5 * S_]])
                uq = np.array([[0, 0], [1, 0], [1, 1], [0, 1]]) * [0.5, 1] + [0.5 * j, 0]
                for side in (1.0, -1.0):
                    f0 = np.array([[0, 1, 2], [0, 2, 3]]) + 4 * len(Vq)
                    Vq.append(q)
                    Uq.append(uq)
                    Fq.append(f0 if side > 0 else f0[:, ::-1])
                    Nq.append(np.tile(side * o_, (4, 1)))
                    Tq.append(np.tile(np.r_[r_, side], (4, 1)))  # (bitangent = N x T x w = up on both sides)
            Vq, Fq, Uq, Nq, Tq = np.vstack(Vq), np.vstack(Fq), np.vstack(Uq), np.vstack(Nq), np.vstack(Tq)
            zt = np.clip(Vq[:, 2] / max(t["height"], 1e-6), 0, 1) ** 1.5
            z16 = np.zeros(len(Vq))
            p_ = pg.prim(Vq, Fq, Uq, pg.M_IMP, (zt, z16, z16, z16), N=Nq)
            p_["attributes"]["TANGENT"] = pg.acc(np.c_[_yup(Tq[:, :3]), Tq[:, 3]].astype(np.float32), "VEC4", 5126, 34962)
            pg.meshes.append({"name": f"LOD{n_lod}_impostor", "primitives": [pg.with_variants(p_, pg.var_imp, pg.M_IMP)]})
            pg.nodes.append({"name": f"{nm}_LOD{0 if pg.only_impostor else n_lod}", "mesh": len(pg.meshes) - 1})
            lod_nodes.append([len(pg.nodes) - 1])
            lod_info.append({"name": nm, "lod": n_lod, "triangles": 8, "impostor": True})
        # screen heights (the plant's share of the view's height) under which an engine should switch down
        for li, c in enumerate(lod_info):
            c["switch_below_screen_height"] = [None, 0.45, 0.2, 0.08][li] if li < 4 else 0.05
        head = lod_nodes[0]
        if len(lod_nodes) > 1:
            pg.ext_used.add("MSFT_lod")
            pg.nodes[head[0]]["extensions"] = {"MSFT_lod": {"ids": [ln[0] for ln in lod_nodes[1:]]}}
            pg.nodes[head[0]]["extras"] = {"MSFT_screencoverage": [0.45, 0.2, 0.08, 0.0][:len(lod_nodes)]}
        if len(pg.trees) == 1:
            pg.roots = head
        else:
            pg.nodes.append({"name": nm, "children": head, "translation": [float((k - (len(pg.trees) - 1) / 2) * pg.spacing), 0.0, 0.0],
                          "extras": {"height_m": round(t["height"], 2), "seed": t["spec"].get("seed"), "age": t["spec"].get("age")}})
            pg.roots.append(len(pg.nodes) - 1)
        c0 = {"wood_triangles": 0, "foliage_triangles": 0, "twigs_kept": 1.0, "wood_min_radius_m": 0.0, "floating": 0.0,
              **lod_info[0]}
        c0["lods"] = lod_info
        caps = [] if pg.only_impostor else collision(t)  # (the grown tree's, whatever the style: a style must not change gameplay)
        c0["collision"] = [{"a": _yup(np.array([q["a"]]))[0].tolist(), "b": _yup(np.array([q["b"]]))[0].tolist(), "ra": q["ra"], "rb": q["rb"]}
                           for q in caps]
        if caps:
            thr = max(0.05, 0.3 * float(t["radius"][1]))
            C = veg_mesh.tubes(t, sides=(4, 5), min_radius=thr, simplify=1.5, collar=0, tile=pg.tile)
            z4 = np.zeros(len(C["V"]))
            if len(C["F"]):  # (a shrub's stems can be thinner than anything a player bumps into)
                pg.meshes.append({"name": f"{nm}_collision", "primitives": [pg.prim(C["V"], C["F"], C["uv"], pg.M_BARK, (z4, z4, z4, z4))]})
                pg.nodes.append({"name": f"{nm}_collision", "mesh": len(pg.meshes) - 1, "extras": {"collision": True}})
                c0["collision_node"] = len(pg.nodes) - 1
            c0["collision_triangles"] = int(len(C["F"]))
        pg.per.append(c0)
