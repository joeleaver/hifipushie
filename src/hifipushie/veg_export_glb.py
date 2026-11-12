"""`write_glb`: the plant's GLB (one function), and write_impostor. Part of the plant export (veg_export.py has the contract)."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from . import veg_export
from . import veg_bark, veg_bough, veg_cloud, veg_impostor, veg_leaf, veg_mesh, veg_style
from . import veg_style_dress, veg_style_small
from . import vegetation_grow
from .veg_export import _normals, _png, _yup, veg_small_state
from .veg_export_parts import (
    budget, cluster_leaves, collision, foliage_mesh, impostor_frames, season_atlas, snow_numbers, wind_nodes,
)

def write_glb(tree, path: str, name="plant", triangles: int | None = None, spacing: float | None = None,
              lods: int = 1, seasons=("summer",), impostor: dict | None = None, wet: bool = False,
              cap: float | None = None, only_impostor: bool = False) -> dict:
    """Write the plant to `path` (.glb). Returns counts. `triangles` = LOD 0's budget (see `budget`).
    lods: 1-3 mesh LODs at LODS' shares of the budget, each drawn from the same tree (fewer rings, sides and axes;
    fewer, larger cards), + `impostor` ({"image" RGBA, "size" m, "height" m}: two crossed quads) as the last. LOD 0
    is the scene; the others hang on it through MSFT_lod and are listed in extras (and written as files of their own
    by veg_tools_look.export, for engines without the extension).
    Wind: TEXCOORD_1 / TEXCOORD_2 / _WIND on every vertex (WIND_RECIPE). COLOR_0 on foliage = a per-twig tint.
    seasons: KHR_materials_variants over the foliage material (season_atlas; a deciduous winter hides the foliage
    by an alpha cut-off above 1); `wet` adds a "wet" variant (darker, glossier bark and leaves).
    Collision: capsules in extras, and a low mesh `<name>_collision` (not in the scene).
    A list of trees (and names) writes a SET: one bark and one foliage material, a node per plant stood `spacing` m
    apart along x; the budget is each plant's own."""
    trees = tree if isinstance(tree, list) else [tree]
    names = name if isinstance(name, list) else [name]
    tree = trees[0]
    s = tree["spec"]
    st = veg_style.sheet(s)  # a style: the same plant dressed another way (veg_style)
    if st and triangles is None:
        triangles = int(({**veg_style.CLUMP, **(st.get("clump") or {})})["budget"] if tree.get("clump") else st.get("budget", 5000))
    bark = s.get("bark") or {}
    bm = veg_bark.bark_maps(bark.get("kind", "furrowed"), 256, seed=int(s.get("seed", 1)))
    sc = float(bark.get("scale", 1.0))
    tile = [bm["tile"][0] * sc, bm["tile"][1] * sc]
    twc = bark.get("twig_color") or [0.45, 0.4, 0.35]
    has_leaves = any(len(veg_leaf.place(t)["pos"]) for t in trees)
    at = veg_leaf.atlas(s["leaves"], twc) if has_leaves and not st else None
    buf = bytearray()
    views, accessors, images, textures, materials, meshes, nodes = [], [], [], [], [], [], []
    ext_used = set()

    def view(data: bytes, target=None):
        while len(buf) % 4:
            buf.append(0)
        v = {"buffer": 0, "byteOffset": len(buf), "byteLength": len(data)}
        if target:
            v["target"] = target
        buf.extend(data)
        views.append(v)
        return len(views) - 1

    def acc(a, kind, comp, target, minmax=False):
        a = np.ascontiguousarray(a)
        d = {"bufferView": view(a.tobytes(), target), "componentType": comp, "count": int(len(a)), "type": kind}
        if minmax:
            d["min"], d["max"] = a.min(0).astype(float).tolist(), a.max(0).astype(float).tolist()
        accessors.append(d)
        return len(accessors) - 1

    tex_seen = {}

    def tex(png: bytes, repeat: bool):
        k_ = (hash(png), len(png), repeat)  # (the same picture is stored once: an impostor's normal map rarely changes with the season)
        if k_ in tex_seen:
            return tex_seen[k_]
        tex_seen[k_] = len(textures)
        images.append({"bufferView": view(png), "mimeType": "image/png"})
        textures.append({"source": len(images) - 1, "sampler": 0 if repeat else 1})
        return len(textures) - 1

    def prim(V, F, uv, material, wind, colour=None, N=None, uv3=None):
        N = _normals(V, F) if N is None else N
        w4 = np.stack(wind, 1).astype(np.float32)
        at_ = {"POSITION": acc(_yup(V).astype(np.float32), "VEC3", 5126, 34962, minmax=True),
               "NORMAL": acc(_yup(N).astype(np.float32), "VEC3", 5126, 34962),
               "TEXCOORD_0": acc(np.c_[uv[:, 0], 1 - uv[:, 1]].astype(np.float32), "VEC2", 5126, 34962),
               "TEXCOORD_1": acc(w4[:, :2].copy(), "VEC2", 5126, 34962),
               "TEXCOORD_2": acc(w4[:, 2:].copy(), "VEC2", 5126, 34962),
               "_WIND": acc(w4, "VEC4", 5126, 34962)}
        if colour is not None:
            c = np.clip(colour, 0, 1)
            c = np.c_[c, c, c] if c.ndim == 1 else c
            at_["COLOR_0"] = acc(np.c_[c, np.ones(len(c))].astype(np.float32), "VEC4", 5126, 34962)
        if uv3 is not None:  # (a style's own pair of numbers per vertex: Godot reads TEXCOORD_2 + TEXCOORD_3 as CUSTOM0)
            at_["TEXCOORD_3"] = acc(np.asarray(uv3, np.float32), "VEC2", 5126, 34962)
        return {"attributes": at_, "indices": acc(F.astype(np.uint32).ravel(), "SCALAR", 5125, 34963), "material": material}

    base = veg_bark.rgb(bm, bark)  # (sRGB colour x a multiplier: near enough)
    orm = np.stack([np.ones_like(bm["rough"]), bm["rough"], np.zeros_like(bm["rough"])], -1)
    if st and st["wood"].get("flat", True):  # a style's bark: one colour
        materials.append({"name": "bark", "pbrMetallicRoughness": {
            "baseColorFactor": [*veg_style.lin(veg_style.bark_color(s, st)), 1.0], "metallicFactor": 0.0,
            "roughnessFactor": float(st["wood"].get("roughness", 0.9))}})
    else:
        materials.append({"name": "bark", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": tex(_png(base), True)},
            "metallicRoughnessTexture": {"index": tex(_png(orm), True)}},
            "normalTexture": {"index": tex(_png(bm["normal"]), True)}})
    M_BARK = 0

    dabs = None
    if st and (st.get("crown") or {}).get("kind") == "clouds" and not tree.get("clump"):
        dabs = veg_cloud.dab_atlas(s, st)

    def solid_material(nm, rgb, season=None):  # a style's closed crown: one colour (x COLOR_0, the tone of each mass); None = bare then
        m_ = {"name": nm, "pbrMetallicRoughness": {"baseColorFactor": [*veg_style.material_color(rgb or [0.5, 0.5, 0.5], st), 1.0], "metallicFactor": 0.0,
                                                    "roughnessFactor": float(st["crown"].get("roughness", 0.85))}}
        if dabs is not None:  # leaf clouds: cards cut by the dab atlas's alpha; its grey tone x the colour x COLOR_0
            da_ = veg_cloud.dab_atlas(s, st, season) if season else dabs  # (spring may paint fresh tips: its own picture, the same alpha)
            m_["pbrMetallicRoughness"]["baseColorTexture"] = {"index": tex(_png(da_["color"] / 255.0), False)}  # (uint8 x 255 wraps round: the atlas must go in as 0..1)
            m_.update(alphaMode="MASK", alphaCutoff=float(st["crown"].get("alpha_cut", 0.5)), doubleSided=True,
                      extras={"card_fill": round(dabs["fill"], 3)})
        if st.get("translucency"):  # pixar: what light through the canopy turns (the engine's subsurface / back light)
            m_["extras"] = {**m_.get("extras", {}), "translucency": {**st["translucency"], "thickness": "TEXCOORD_3.y = metres of canopy behind the point"}}
        rp_ = veg_style.season_ramp(s, season, st) if (season and dabs is None and rgb is not None) else None
        if rp_ is not None:  # (a season painting the masses' edges: a ramp over TEXCOORD_0.x, factor x texture = the colour)
            img_, fac_ = veg_style.ramp_texture(rp_)
            m_["pbrMetallicRoughness"]["baseColorFactor"] = [*fac_, 1.0]
            m_["pbrMetallicRoughness"]["baseColorTexture"] = {"index": tex(_png(img_), False)}
            m_["extras"] = {**m_.get("extras", {}), "ramp": "baseColorTexture is a ramp over TEXCOORD_0.x (0 = a mass's foot / a tier's rim)"}
        if rgb is None:
            m_.update(alphaMode="MASK", alphaCutoff=1.01, extras={**m_.get("extras", {}), "hidden": True})  # (bare then: the cut-off above 1 hides it in viewers that read variants)
        materials.append(m_)
        return len(materials) - 1

    def foliage_material(a_, nm, hidden=False):
        m = a_["mask"]
        orm_ = np.stack([np.ones_like(m[..., 1]), m[..., 1], np.zeros_like(m[..., 1])], -1)
        materials.append({"name": nm, "pbrMetallicRoughness": {
            "baseColorTexture": {"index": tex(_png(a_["color"]), False)},
            "metallicRoughnessTexture": {"index": tex(_png(orm_), False)}},
            "normalTexture": {"index": tex(_png(a_["normal"]), False)},
            "alphaMode": "MASK", "alphaCutoff": 1.01 if hidden else 0.4, "doubleSided": True,
            "extras": {"mask_texture": "R = light comes through (leaf), G = roughness, B = shade",
                       "card_fill": round(a_["fill"], 3)}})
        materials[-1]["extras"]["mask_texture_index"] = tex(_png(a_["mask"]), False)
        return len(materials) - 1

    seasons = list(seasons or ["summer"])
    variants, var_fol, var_bark = [], {}, {}
    M_FOL = None
    if st and has_leaves:
        se0 = s.get("season", "summer") if s.get("season") in seasons else seasons[0]
        M_FOL = solid_material("foliage", veg_style.season_color(s, se0, st), se0)
        for se in seasons:
            var_fol[se] = M_FOL if se == se0 else solid_material(f"foliage_{se}", veg_style.season_color(s, se, st), se)
        if wet:
            mw = json.loads(json.dumps(materials[M_FOL]))
            mw["name"] = "foliage_wet"
            mw["pbrMetallicRoughness"]["baseColorFactor"] = [0.7 * c_ for c_ in mw["pbrMetallicRoughness"]["baseColorFactor"][:3]] + [1.0]
            mw["pbrMetallicRoughness"]["roughnessFactor"] = 0.4
            materials.append(mw)
            var_fol["wet"] = len(materials) - 1
    # pixar: a layer of real leaf cards on the closed shell = the foliage mesh's next primitive, slot `foliage_cards`
    # (alpha MASK, double sided, a grey leaf atlas x baseColorFactor x COLOR_0), its own material per season
    M_CARDS, var_cards = None, {}
    if st and has_leaves and (st.get("crown") or {}).get("cards") and not trees[0].get("clump"):
        cs_ = {**veg_cloud.CARDS, **st["crown"]["cards"]}
        kg_ = float(max(cs_["tone"]) * (1 + float(cs_["warm_tip"])))

        def cards_material(nm, rgb, season):
            sub_ = veg_cloud.shell_atlas(s, st, season)
            c_ = np.array(veg_style.lin(rgb or [0.5, 0.5, 0.5])) * kg_
            m_ = {"name": nm, "pbrMetallicRoughness": {"baseColorFactor": [*(c_ / max(1.0, float(c_.max()))).tolist(), 1.0], "metallicFactor": 0.0,
                                                        "roughnessFactor": float(st["crown"].get("roughness", 0.8)),
                                                        "baseColorTexture": {"index": tex(_png(sub_["color"] / 255.0), False)}},
                  "alphaMode": "MASK", "alphaCutoff": float(cs_.get("alpha_cut", 0.5)), "doubleSided": True,
                  "extras": {"card_fill": round(sub_["fill"], 3), **({"translucency": {**st["translucency"], "thickness": "TEXCOORD_3.y = metres (cards: thin)"}} if st.get("translucency") else {})}}
            if rgb is None:
                m_.update(alphaCutoff=1.01, extras={**m_["extras"], "hidden": True})
            materials.append(m_)
            return len(materials) - 1
        M_CARDS = cards_material("foliage_cards", veg_style.season_color(s, se0, st), se0)
        for se in seasons:
            var_cards[se] = M_CARDS if se == se0 else cards_material(f"foliage_cards_{se}", veg_style.season_color(s, se, st), se)
    # a styled small plant whose blades lie down in winter (veg_small's winter `flatten`): the lying blades are the
    # foliage mesh's own primitive, slot `foliage_winter`, shown only in winter and snow (when `foliage` is hidden).
    # A second primitive rather than a morph target: the engine already hides slots per season from the seasons json,
    # blades are a few hundred triangles, and it needs no blend weights kept in step with wind and LODs.
    M_FW, var_fw, lie = None, {}, [se for se in seasons if se in ("winter", "snow")]
    if st and has_leaves and len(trees) == 1 and trees[0].get("clump") and lie and se0 not in lie:
        from . import veg_small
        if float((veg_small.season_state(s, "winter") or {}).get("flatten", 0.0)) > 0:
            M_FW = solid_material("foliage_winter", None)
            gone = solid_material("foliage_lying", None)  # (the upright blades' material in winter: hidden)
            for se in seasons:
                if se in lie:
                    var_fw[se] = solid_material(f"foliage_winter_{se}", veg_style.season_color(s, se, st), se)
                    var_fol[se] = gone
                else:
                    var_fw[se] = M_FW
    if at is not None:
        M_FOL = foliage_material(at, "foliage")
        for se in seasons:
            if se == "summer":
                var_fol[se] = M_FOL
                continue
            a_ = season_atlas(s, se, twc)
            if a_ is at:
                var_fol[se] = M_FOL
            elif a_ is None:
                materials.append({**json.loads(json.dumps(materials[M_FOL])), "name": f"foliage_{se}", "alphaCutoff": 1.01})
                materials[-1]["extras"] = {**materials[-1].get("extras", {}), "hidden": True}
                var_fol[se] = len(materials) - 1
            else:
                var_fol[se] = foliage_material(a_, f"foliage_{se}")
        if wet:
            mw = json.loads(json.dumps(materials[M_FOL]))
            mw["name"] = "foliage_wet"
            mw["pbrMetallicRoughness"].update(baseColorFactor=[0.78, 0.8, 0.76, 1.0], roughnessFactor=0.45)
            materials.append(mw)
            var_fol["wet"] = len(materials) - 1
    if wet:
        mw = json.loads(json.dumps(materials[M_BARK]))
        mw["name"] = "bark_wet"
        f0 = mw["pbrMetallicRoughness"].get("baseColorFactor", [1, 1, 1, 1])
        mw["pbrMetallicRoughness"].update(baseColorFactor=[0.55 * f0[0], 0.53 * f0[1], 0.5 * f0[2], 1.0], roughnessFactor=0.5)
        materials.append(mw)
        var_bark["wet"] = len(materials) - 1
    variants = [v_ for v_ in seasons + (["wet"] if wet else []) if len(seasons) + bool(wet) > 1]
    # a style's forks (the wood's second primitive): there when the foliage is not
    M_FORK, var_fork = None, {}
    if st and has_leaves:
        bare = {se: veg_style.season_color(s, se, st) is None for se in seasons}
        if any(bare.values()):
            hid = {**json.loads(json.dumps(materials[M_BARK])), "name": "bark_forks", "alphaMode": "MASK", "alphaCutoff": 1.01, "extras": {"hidden": True}}
            vis = {**json.loads(json.dumps(materials[M_BARK])), "name": "bark_forks_bare"}
            materials.extend([hid, vis])
            var_fork = {se: len(materials) - (1 if bare[se] else 2) for se in seasons}
            M_FORK = var_fork[se0]

    def with_variants(p_, table, default):
        if variants and table:
            ext_used.add("KHR_materials_variants")
            by = {}
            for i_, v_ in enumerate(variants):
                by.setdefault(table.get(v_, default), []).append(i_)
            p_["extensions"] = {"KHR_materials_variants": {"mappings": [{"material": m_, "variants": vs} for m_, vs in by.items()]}}
        return p_

    M_IMP = None
    crop_ = crops_ = None
    if impostor is not None and impostor.get("kind") == veg_impostor.KIND:
        # the quad covers only what any frame of any season draws (the game: a square the bake sphere's size spent
        # half its pixels on nothing)
        ims_ = [impostor["image"]] + [(v_["image"] if isinstance(v_, dict) else v_) for v_ in (impostor.get("seasons") or {}).values()]
        crop_ = veg_impostor.crop(ims_, int(impostor["frames"]))
        crops_ = veg_impostor.crops(ims_, int(impostor["frames"]))
    if impostor is not None:
        def imp_material(nm, im_, nrm_):
            m_ = {"name": nm, "pbrMetallicRoughness": {
                "baseColorTexture": {"index": tex(_png(im_), False)}, "metallicFactor": 0.0, "roughnessFactor": 0.9},
                "alphaMode": "MASK", "alphaCutoff": 0.5, "doubleSided": False,
                "extras": {"impostor": "albedo (unlit; the shade of what stands above it baked in, no sun) + a tangent-space normal map "
                                       "baked from the same two views: light it like any mesh. Front and back of each quad are faces of "
                                       "their own (single sided) with opposite NORMAL and their own TANGENT (w = -1 on the back), so "
                                       "the one normal map reads mirrored through the quad from behind. "
                                       "Engine: the material must NOT RECEIVE shadows (Godot: disable_receive_shadows): the two quads "
                                       "shadow each other, a dark wedge down the middle; casting onto the ground is fine",
                           "receive_shadows": False}}
            if impostor.get("kind") == veg_impostor.KIND:  # one camera-facing quad: the normal map is OBJECT space (+ depth in alpha),
                m_["extras"] = {"hifipushie_impostor": {  # so it is not a glTF normalTexture (tangent space): it rides in the extras
                    "kind": veg_impostor.KIND, "frames": int(impostor["frames"]), "size": round(float(impostor["size"]), 4),
                    "centre": [round(float(c_), 4) for c_ in impostor["centre"]],
                    "normal_texture_index": tex(_png(nrm_), False) if nrm_ is not None else None,
                    "normal": "object space, glTF axes: rgb * 2 - 1; alpha = depth behind the frame's middle plane (0 front .. 1 back of "
                              "the bake sphere, x size)", "recipe": veg_impostor.recipe(int(impostor["frames"]), float(impostor["size"]), impostor["centre"], crop_),
                    "crop": crop_, "crops": crops_, "drawn_share": round(veg_impostor.drawn_share(crops_, int(impostor["frames"])), 3) if crops_ else None,
                    "shader": veg_impostor.SHADER}, "receive_shadows": False}
            elif nrm_ is not None:
                m_["normalTexture"] = {"index": tex(_png(nrm_), False)}
            materials.append(m_)
            return len(materials) - 1
        M_IMP = imp_material("impostor", impostor["image"], impostor.get("normal"))
        var_imp = {}
        for se, im_ in (impostor.get("seasons") or {}).items():
            if se in seasons and se != seasons[0]:
                im_ = im_ if isinstance(im_, dict) else {"image": im_}
                var_imp[se] = imp_material(f"impostor_{se}", im_["image"], im_.get("normal"))
    per, roots = [], []
    cluster_mats = {}
    head_mats = {}
    if spacing is None:
        spacing = 0.0 if len(trees) == 1 else 1.2 * max(float(np.percentile(np.linalg.norm(t["pos"][:, :2], axis=1), 98)) for t in trees) * 2
    n_lod = int(np.clip(lods, 1, len(veg_export.LODS)))
    for k, (t, nm) in enumerate(zip(trees, names)):
        wn = wind_nodes(t)
        lod_nodes, lod_info = [], []
        for li in range(0 if only_impostor else n_lod):
            share, cap_ = veg_export.LODS[li]
            cap_i = cap_ if n_lod > 1 or cap is None else cap
            if st:
                D = veg_style_dress.dress(t, st, int(triangles * share), se0 if has_leaves else "summer")
                if has_leaves and D["crown"] is None:  # (the file's default season is a bare one: the masses are still in it, hidden)
                    D = veg_style_dress.dress(t, st, int(triangles * share), "summer")
                pre = (f"{nm}_" if len(trees) > 1 else "") + (f"LOD{li}_" if n_lod > 1 or impostor is not None else "")
                W = D["wood"]
                kids = []
                wp = [with_variants(prim(W["V"], W["F"], W["uv"], M_BARK, D["wood_wind"], N=W["N"]), var_bark, M_BARK)]
                K_ = D["forks"]
                if K_ is not None and M_FORK is not None:
                    wp.append(with_variants(prim(K_["V"], K_["F"], K_["uv"], M_FORK, K_["wind"], N=K_["N"]), var_fork, M_FORK))
                meshes.append({"name": pre + "wood", "primitives": wp})
                nodes.append({"name": pre + "wood", "mesh": len(meshes) - 1})
                kids.append(len(nodes) - 1)
                c = {"name": nm, "lod": li, "height_m": round(t["height"], 2), "wood_triangles": int(len(W["F"])), "foliage_triangles": 0,
                     "twigs_kept": 1.0, "wood_min_radius_m": 0.0, "floating": 0.0, "style": D["info"]}
                C_ = D["crown"]
                if C_ is not None:
                    p_ = prim(C_["V"], C_["F"], C_["uv"], M_FOL, C_["wind"], C_["col"], C_["N"], uv3=C_.get("grad"))
                    fp = [with_variants(p_, var_fol, M_FOL)]
                    K_ = D.get("cards")
                    if K_ is not None and M_CARDS is not None:  # pixar: the leaf cards on the shell
                        fp.append(with_variants(prim(K_["V"], K_["F"], K_["uv"], M_CARDS, K_["wind"], K_["col"], K_["N"], uv3=K_["grad"]), var_cards, M_CARDS))
                        c["cards_triangles"] = int(len(K_["F"]))
                    Hd = D.get("heads")
                    if Hd is not None:  # a small plant's flower / seed heads: the foliage mesh's second primitive, slot `heads`
                        if "heads" not in head_mats:
                            shown = {"name": "heads", "pbrMetallicRoughness": {"baseColorFactor": [1.0, 1.0, 1.0, 1.0], "metallicFactor": 0.0,
                                                                                "roughnessFactor": float(st["crown"].get("roughness", 0.85))}}
                            hid_ = {**json.loads(json.dumps(shown)), "alphaMode": "MASK", "alphaCutoff": 1.01, "extras": {"hidden": True}}
                            d_show = se0 in Hd["seasons"]
                            (hid_ if d_show else shown)["name"] = "heads_hidden" if d_show else "heads_shown"
                            (shown if d_show else hid_)["name"] = "heads"
                            materials.extend([shown, hid_])
                            head_mats["heads"] = {se: len(materials) - (2 if se in Hd["seasons"] else 1) for se in seasons}
                        vh = head_mats["heads"]
                        hcol = np.array([veg_style.lin(c_) for c_ in Hd["part_colors"]])[Hd["part"]]  # (COLOR_0 = each part's colour, linear: petals, centre, stalk)
                        fp.append(with_variants(prim(Hd["V"], Hd["F"], Hd["uv"], vh[se0], Hd["wind"], hcol, N=Hd["N"]), vh, vh[se0]))
                        c["heads_triangles"] = int(len(Hd["F"]))
                    if M_FW is not None:  # the blades lying down (winter, snow): their own primitive
                        if "_winter_tree" not in t:
                            t["_winter_tree"] = vegetation_grow.grow({**t["spec"], "season": "winter"})
                        Dw = veg_style_dress.dress(t["_winter_tree"], st, int(triangles * share), "winter")
                        Cw = Dw["crown"]
                        if Cw is not None:
                            fp.append(with_variants(prim(Cw["V"], Cw["F"], Cw["uv"], M_FW, Cw["wind"], Cw["col"], Cw["N"], uv3=Cw.get("grad")), var_fw, M_FW))
                            c["winter_triangles"] = int(len(Cw["F"]))
                    meshes.append({"name": pre + "foliage", "primitives": fp})
                    nodes.append({"name": pre + "foliage", "mesh": len(meshes) - 1})
                    kids.append(len(nodes) - 1)
                    c["foliage_triangles"] = int(len(C_["F"])) + c.get("heads_triangles", 0) + c.get("cards_triangles", 0)
                c["triangles"] = c["wood_triangles"] + c["foliage_triangles"]
                lod_info.append(c)
                if n_lod == 1 and impostor is None and len(trees) == 1:
                    lod_nodes.append(kids)
                else:
                    nodes.append({"name": f"{nm}_LOD{li}", "children": kids})
                    lod_nodes.append([len(nodes) - 1])
                continue
            bud = budget(t, int(triangles * share) if triangles else None, tile, at["triangles"] if at else 0, cap_i)
            if li and not triangles:  # no budget asked: lower LODs still step down from the full tree
                full = lod_info[0]["triangles"]
                bud = budget(t, int(full * share), tile, at["triangles"] if at else 0, cap_i)
            W = bud["wood"]
            lf_c, cap_c, back_c = cluster_leaves(s["leaves"], bud["keep"])
            at_c, m_c, vf_c = at, M_FOL, var_fol
            tw_c = None
            boughs = bool(bud.get("boughs")) and at is not None
            if at is not None and (boughs or lf_c is not s["leaves"]):  # bough cards: their own picture (and its season variants)
                # (LODs thinned from one cut of the tree share its atlas and material: one foliage_boughs slot)
                cut_ = (veg_bough.base_of(t, bud["boughs"]), veg_bough.form_of(t, bud["boughs"])) if boughs and len(trees) == 1 else (None, 0)
                ck = (f"boughs_cut{cut_[0]}_{cut_[1]}" if cut_[0] else f"boughs{li}") if boughs else json.dumps(lf_c["card"], sort_keys=True)
                if ck not in cluster_mats:
                    # (a set shares one bough atlas per LOD: baked from the first plant that needs it)
                    make = (lambda lf_, twc_, t0=t, nb=bud["boughs"]: veg_bough.atlas(t0, lf_, twc_, nb)) if boughs else veg_leaf.atlas
                    sp_c = {**s, "leaves": s["leaves"] if boughs else lf_c}
                    at_c = make(sp_c["leaves"], twc)
                    m_ = foliage_material(at_c, f"foliage_boughs{len(cluster_mats) + 1}")
                    vf_ = {}
                    for se in seasons:
                        a_ = season_atlas(sp_c, se, twc, make) if se != "summer" else at_c
                        if a_ is None:
                            materials.append({**json.loads(json.dumps(materials[m_])), "name": f"{materials[m_]['name']}_{se}", "alphaCutoff": 1.01})
                            materials[-1]["extras"] = {**materials[-1].get("extras", {}), "hidden": True}
                            vf_[se] = len(materials) - 1
                        else:
                            vf_[se] = m_ if a_ is at_c else foliage_material(a_, f"{materials[m_]['name']}_{se}")
                    if wet:
                        mw_ = json.loads(json.dumps(materials[m_]))
                        mw_["name"] += "_wet"
                        mw_["pbrMetallicRoughness"].update(baseColorFactor=[0.78, 0.8, 0.76, 1.0], roughnessFactor=0.45)
                        materials.append(mw_)
                        vf_["wet"] = len(materials) - 1
                    cluster_mats[ck] = (at_c, m_, vf_)
                at_c, m_c, vf_c = cluster_mats[ck]
                if boughs:
                    tw_c = veg_bough.place(t, bud["boughs"], at_c)
            L = foliage_mesh(t, at_c, bud["keep"], bud["min_radius"], bud["protect"], cap_c if at_c is not at else cap_i, back_c, tw=tw_c) \
                if at and len(veg_leaf.place(t)["pos"]) else None
            pre = (f"{nm}_" if len(trees) > 1 else "") + (f"LOD{li}_" if n_lod > 1 or impostor is not None else "")
            kids = []
            wn_w = W["node"]
            p_ = prim(W["V"], W["F"], W["uv"], M_BARK, (wn["trunk"][wn_w], wn["branch"][wn_w], wn["phase"][wn_w], np.zeros(len(wn_w))))
            meshes.append({"name": pre + "wood", "primitives": [with_variants(p_, var_bark, M_BARK)]})
            nodes.append({"name": pre + "wood", "mesh": len(meshes) - 1})
            kids.append(len(nodes) - 1)
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
                p_ = prim(L["V"], L["F"], L["uv"], m_c, card_wind(L, wn),
                          L["tint"], L["N"])
                fprims = [p_]
                lie_r = [se for se in seasons if se in ("winter", "snow")]
                if (t.get("clump") and len(trees) == 1 and lie_r and seasons[0] not in lie_r
                        and float((veg_small_state(s, "winter") or {}).get("flatten", 0.0)) > 0):
                    # a realistic small plant whose blades lie down in winter: as the styled ones, slot foliage_winter =
                    # the cards of the plant regrown at season winter, shown in winter / snow while foliage is hidden
                    if "_winter_tree" not in t:
                        t["_winter_tree"] = vegetation_grow.grow({**t["spec"], "season": "winter"})
                    tw_ = t["_winter_tree"]
                    Lw = foliage_mesh(tw_, at_c, bud["keep"], bud["min_radius"], bud["protect"], cap_c if at_c is not at else cap_i, back_c)
                    if not len(Lw["F"]):  # (a low LOD's keep share can leave the lying plant no cards: keep them all, it is small)
                        Lw = foliage_mesh(tw_, at_c, 1.0, 0.0, None, cap_c if at_c is not at else cap_i, back_c)
                    if len(Lw["F"]):
                        hk = ("lie", m_c)
                        if hk not in cluster_mats:
                            hid = [{**json.loads(json.dumps(materials[m_c])), "name": f"{materials[m_c]['name']}_{sfx}", "alphaCutoff": 1.01}
                                   for sfx in ("winter", "lying")]
                            for h_ in hid:
                                h_["extras"] = {**h_.get("extras", {}), "hidden": True}
                            materials.extend(hid)
                            cluster_mats[hk] = (len(materials) - 2, len(materials) - 1)
                        m_w, m_l = cluster_mats[hk]
                        tab_main = {se: (m_l if se in lie_r else vf_c.get(se, m_c)) for se in seasons}
                        tab_w = {se: (vf_c.get(se, m_c) if se in lie_r else m_w) for se in seasons}
                        fprims = [with_variants(p_, tab_main, m_c),
                                  with_variants(prim(Lw["V"], Lw["F"], Lw["uv"], m_w, card_wind(Lw, wind_nodes(tw_)), Lw["tint"], Lw["N"]), tab_w, m_w)]
                        c["winter_triangles"] = int(len(Lw["F"]))
                if len(fprims) == 1:
                    fprims = [with_variants(p_, vf_c, m_c)]
                meshes.append({"name": pre + "foliage", "primitives": fprims})
                c["boughs"] = at_c is not at
                nodes.append({"name": pre + "foliage", "mesh": len(meshes) - 1})
                kids.append(len(nodes) - 1)
                c["foliage_triangles"] = int(len(L["F"]))
            c["triangles"] = c["wood_triangles"] + c["foliage_triangles"]
            lod_info.append(c)
            if n_lod == 1 and impostor is None and len(trees) == 1:
                lod_nodes.append(kids)
            else:
                nodes.append({"name": (f"{nm}_" if len(trees) > 1 else f"{nm}_") + f"LOD{li}", "children": kids})
                lod_nodes.append([len(nodes) - 1])
        if impostor is not None and k == 0 and len(trees) == 1 and impostor.get("kind") == veg_impostor.KIND:
            # hemi-octahedral: ONE quad, rebuilt to face the camera by the engine's shader (veg_impostor.recipe); stored as
            # a vertical square through the bake centre facing +y (glTF +z), uv 0..1 = its corners
            S_, Cg = float(impostor["size"]), np.asarray(impostor["centre"], float)
            Cb = np.array([Cg[0], -Cg[2], Cg[1]])
            u0_, u1_, v0_, v1_ = crop_ or [0.0, 1.0, 0.0, 1.0]
            xa_, xb_ = (u0_ - 0.5) * S_, (u1_ - 0.5) * S_
            za_, zb_ = (0.5 - v1_) * S_, (0.5 - v0_) * S_
            Vq = np.array([Cb + [xa_, 0, za_], Cb + [xb_, 0, za_], Cb + [xb_, 0, zb_], Cb + [xa_, 0, zb_]])
            Uq = np.array([[0, 1.0], [1, 1], [1, 0], [0, 0]])
            Fq = np.array([[0, 1, 2], [0, 2, 3]])
            Nq = np.tile([0, -1.0, 0], (4, 1))
            zt = np.clip(Vq[:, 2] / max(t["height"], 1e-6), 0, 1) ** 1.5
            z4 = np.zeros(4)
            p_ = prim(Vq, Fq, Uq[:, [0, 1]] * [1, -1] + [0, 1], M_IMP, (zt, z4, z4, z4), N=Nq)
            meshes.append({"name": f"LOD{n_lod}_impostor", "primitives": [with_variants(p_, var_imp, M_IMP)],
                           "extras": {"hifipushie_impostor": veg_impostor.KIND, "cull_margin_m": round(0.5 * S_, 3)}})
            nodes.append({"name": f"{nm}_LOD{0 if only_impostor else n_lod}", "mesh": len(meshes) - 1})
            lod_nodes.append([len(nodes) - 1])
            lod_info.append({"name": nm, "lod": n_lod, "triangles": 2, "impostor": True, "impostor_kind": veg_impostor.KIND})
        elif impostor is not None and k == 0 and len(trees) == 1:
            S_, H_ = float(impostor["size"]), float(impostor["height"])
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
            p_ = prim(Vq, Fq, Uq, M_IMP, (zt, z16, z16, z16), N=Nq)
            p_["attributes"]["TANGENT"] = acc(np.c_[_yup(Tq[:, :3]), Tq[:, 3]].astype(np.float32), "VEC4", 5126, 34962)
            meshes.append({"name": f"LOD{n_lod}_impostor", "primitives": [with_variants(p_, var_imp, M_IMP)]})
            nodes.append({"name": f"{nm}_LOD{0 if only_impostor else n_lod}", "mesh": len(meshes) - 1})
            lod_nodes.append([len(nodes) - 1])
            lod_info.append({"name": nm, "lod": n_lod, "triangles": 8, "impostor": True})
        # screen heights (the plant's share of the view's height) under which an engine should switch down
        for li, c in enumerate(lod_info):
            c["switch_below_screen_height"] = [None, 0.45, 0.2, 0.08][li] if li < 4 else 0.05
        head = lod_nodes[0]
        if len(lod_nodes) > 1:
            ext_used.add("MSFT_lod")
            nodes[head[0]]["extensions"] = {"MSFT_lod": {"ids": [ln[0] for ln in lod_nodes[1:]]}}
            nodes[head[0]]["extras"] = {"MSFT_screencoverage": [0.45, 0.2, 0.08, 0.0][:len(lod_nodes)]}
        if len(trees) == 1:
            roots = head
        else:
            nodes.append({"name": nm, "children": head, "translation": [float((k - (len(trees) - 1) / 2) * spacing), 0.0, 0.0],
                          "extras": {"height_m": round(t["height"], 2), "seed": t["spec"].get("seed"), "age": t["spec"].get("age")}})
            roots.append(len(nodes) - 1)
        c0 = {"wood_triangles": 0, "foliage_triangles": 0, "twigs_kept": 1.0, "wood_min_radius_m": 0.0, "floating": 0.0,
              **lod_info[0]}
        c0["lods"] = lod_info
        caps = [] if only_impostor else collision(t)  # (the grown tree's, whatever the style: a style must not change gameplay)
        c0["collision"] = [{"a": _yup(np.array([q["a"]]))[0].tolist(), "b": _yup(np.array([q["b"]]))[0].tolist(), "ra": q["ra"], "rb": q["rb"]}
                           for q in caps]
        if caps:
            thr = max(0.05, 0.3 * float(t["radius"][1]))
            C = veg_mesh.tubes(t, sides=(4, 5), min_radius=thr, simplify=1.5, collar=0, tile=tile)
            z4 = np.zeros(len(C["V"]))
            if len(C["F"]):  # (a shrub's stems can be thinner than anything a player bumps into)
                meshes.append({"name": f"{nm}_collision", "primitives": [prim(C["V"], C["F"], C["uv"], M_BARK, (z4, z4, z4, z4))]})
                nodes.append({"name": f"{nm}_collision", "mesh": len(meshes) - 1, "extras": {"collision": True}})
                c0["collision_node"] = len(nodes) - 1
            c0["collision_triangles"] = int(len(C["F"]))
        per.append(c0)
    counts = {"wood_triangles": sum(c["wood_triangles"] for c in per), "foliage_triangles": sum(c["foliage_triangles"] for c in per),
              "twigs_kept": per[0]["twigs_kept"], "wood_min_radius_m": per[0]["wood_min_radius_m"], "budget": triangles,
              "floating": max(c["floating"] for c in per), "lods": per[0]["lods"], "variants": variants,
              "collision_capsules": len(per[0]["collision"]), "collision_triangles": per[0].get("collision_triangles", 0)}
    if st and per[0]["lods"] and per[0]["lods"][0].get("style"):
        counts["style"] = per[0]["lods"][0]["style"]
    if at is not None:
        counts["atlas_px"] = int(at["color"].shape[0])
    if len(trees) > 1:
        counts["plants"] = per
    name = names[0] if len(trees) == 1 else "set"
    while len(buf) % 4:
        buf.append(0)
    gltf = {"asset": {"version": "2.0", "generator": "hifipushie vegetation"},
            "scene": 0, "scenes": [{"nodes": roots}], "nodes": nodes, "meshes": meshes,
            "materials": materials, **({"textures": textures, "images": images} if textures else {}),
            "samplers": [{"wrapS": 10497, "wrapT": 10497, "magFilter": 9729, "minFilter": 9987},
                         {"wrapS": 33071, "wrapT": 33071, "magFilter": 9729, "minFilter": 9987}],
            "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(buf)}],
            "extras": {"hifipushie_plant": {"name": name, "species": s.get("species"), "age": s.get("age"),
                                            "height_m": round(tree["height"], 2), "stats": tree["stats"],
                                            "set": len(trees) if len(trees) > 1 else None, "bark_tile_m": bm["tile"],
                                            "lods": [[{k_: v_ for k_, v_ in c.items()} for c in p_["lods"]] for p_ in per],
                                            "wind": veg_export.WIND_RECIPE, "variants": variants, "contract": veg_export.CONTRACT,
                                            "style": None if not st else {
                                                "name": st["name"], "sheet": {k_: v_ for k_, v_ in st.items() if k_ != "about"},
                                                "simplified": veg_style_small.lines(per[0]["lods"][0]["style"]) if per[0]["lods"] and per[0]["lods"][0].get("style") else [],
                                                "kind": "clouds" if dabs is not None else "masses",
                                                "foliage": ("leaf clouds: alpha-MASK cards, double sided; albedo = the dab atlas's grey tone x the "
                                                            "`foliage` material's baseColorFactor (one per season variant) x COLOR_0 (the clump's "
                                                            "painted gradient, one step per card); NORMAL = out of the clump's middle; TEXCOORD_0 = "
                                                            "the atlas uv; TEXCOORD_3 = (gradient 0 base .. 1 top of its clump, (clump + 0.5) / clumps); "
                                                            "wind: TEXCOORD_2.y = flutter, 0 at a card's middle .. at its rim") if dabs is not None else
                                                           "closed masses, no texture: albedo = the `foliage` material's baseColorFactor "
                                                           "(one per season variant) x COLOR_0 (each mass's tone); NORMAL = smooth over each "
                                                           "mass; TEXCOORD_0 = (height within its mass 0..1, (mass index + 0.5) / masses)",
                                                "season_colors_srgb": {se: veg_style.season_color(s, se, st) for se in veg_style.SEASONS}},
                                            "snow": "engine shader: see snow_numbers (in <name>_seasons.json as `snow`); "
                                                    "the `snow` variant is the ready-mixed foliage colour / picture",
                                            "snow_numbers": snow_numbers(s, st),
                                            "collision": [{"plant": p_["name"], "capsules": p_["collision"],
                                                           "mesh_node": p_.get("collision_node")} for p_ in per]}}}
    if variants:  # (declared even when no slot changes with the season: <name>_seasons.json is the contract's first file,
        # and a styled clover that looks the same all year wrote none)
        ext_used.add("KHR_materials_variants")
        gltf["extensions"] = {"KHR_materials_variants": {"variants": [{"name": v_} for v_ in variants]}}
    if ext_used:
        gltf["extensionsUsed"] = sorted(ext_used)
    js = json.dumps(gltf, separators=(",", ":"), default=float).encode()
    js += b" " * (-len(js) % 4)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(buf)))
        f.write(struct.pack("<I4s", len(js), b"JSON"))
        f.write(js)
        f.write(struct.pack("<I4s", len(buf), b"BIN\0"))
        f.write(bytes(buf))
    counts["bytes"] = out.stat().st_size
    counts["path"] = str(out)
    return counts


def write_impostor(tree: dict, path: str, name: str, impostor: dict, seasons=("summer",)) -> str:
    """The impostor LOD alone, as a file of its own (its pictures per season as variants)."""
    return write_glb(tree, path, name, impostor=impostor, only_impostor=True, seasons=seasons)["path"]
