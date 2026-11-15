"""A plant GLB's materials: the bark, a style's foliage, leaf cards and lying winter blades, the leaf atlas per season,
wet, a style's forks, the impostor's. Five stages of `write_glb` (veg_export_glb.write_glb calls them in order; veg_export.py has the contract)."""
from __future__ import annotations

import json

import numpy as np

from . import veg_bark, veg_cloud, veg_impostor, veg_style
from .veg_export import _png
from .veg_export_parts import season_atlas

def _bark(pg):
    """The bark material (a style's one colour, or the bark's maps), and a cloud crown's dab atlas."""

    base = veg_bark.rgb(pg.bm, pg.bark)  # (sRGB colour x a multiplier: near enough)
    orm = np.stack([np.ones_like(pg.bm["rough"]), pg.bm["rough"], np.zeros_like(pg.bm["rough"])], -1)
    if pg.st and pg.st["wood"].get("flat", True):  # a style's bark: one colour
        pg.materials.append({"name": "bark", "pbrMetallicRoughness": {
            "baseColorFactor": [*veg_style.lin(veg_style.bark_color(pg.s, pg.st)), 1.0], "metallicFactor": 0.0,
            "roughnessFactor": float(pg.st["wood"].get("roughness", 0.9))}})
    else:
        pg.materials.append({"name": "bark", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": pg.tex(_png(base), True)},
            "metallicRoughnessTexture": {"index": pg.tex(_png(orm), True)}},
            "normalTexture": {"index": pg.tex(_png(pg.bm["normal"]), True)}})
    pg.M_BARK = 0

    pg.dabs = None
    if pg.st and (pg.st.get("crown") or {}).get("kind") == "clouds" and not pg.tree.get("clump"):
        pg.dabs = veg_cloud.dab_atlas(pg.s, pg.st)


def _foliage_materials(pg):
    """The foliage materials' builders (a style's solid colour, the leaf atlas), the seasons, then a style's foliage per
    season, its leaf cards on the shell (pixar) and a small plant's lying winter blades."""

    def solid_material(nm, rgb, season=None):  # a style's closed crown: one colour (x COLOR_0, the tone of each mass); None = bare then
        m_ = {"name": nm, "pbrMetallicRoughness": {"baseColorFactor": [*veg_style.material_color(rgb or [0.5, 0.5, 0.5], pg.st), 1.0], "metallicFactor": 0.0,
                                                    "roughnessFactor": float(pg.st["crown"].get("roughness", 0.85))}}
        if pg.dabs is not None:  # leaf clouds: cards cut by the dab atlas's alpha; its grey tone x the colour x COLOR_0
            da_ = veg_cloud.dab_atlas(pg.s, pg.st, season) if season else pg.dabs  # (spring may paint fresh tips: its own picture, the same alpha)
            m_["pbrMetallicRoughness"]["baseColorTexture"] = {"index": pg.tex(_png(da_["color"] / 255.0), False)}  # (uint8 x 255 wraps round: the atlas must go in as 0..1)
            m_.update(alphaMode="MASK", alphaCutoff=float(pg.st["crown"].get("alpha_cut", 0.5)), doubleSided=True,
                      extras={"card_fill": round(pg.dabs["fill"], 3)})
        if pg.st.get("translucency"):  # pixar: what light through the canopy turns (the engine's subsurface / back light)
            m_["extras"] = {**m_.get("extras", {}), "translucency": {**pg.st["translucency"], "thickness": "TEXCOORD_3.y = metres of canopy behind the point"}}
        rp_ = veg_style.season_ramp(pg.s, season, pg.st) if (season and pg.dabs is None and rgb is not None) else None
        if rp_ is not None:  # (a season painting the masses' edges: a ramp over TEXCOORD_0.x, factor x texture = the colour)
            img_, fac_ = veg_style.ramp_texture(rp_)
            m_["pbrMetallicRoughness"]["baseColorFactor"] = [*fac_, 1.0]
            m_["pbrMetallicRoughness"]["baseColorTexture"] = {"index": pg.tex(_png(img_), False)}
            m_["extras"] = {**m_.get("extras", {}), "ramp": "baseColorTexture is a ramp over TEXCOORD_0.x (0 = a mass's foot / a tier's rim)"}
        if rgb is None:
            m_.update(alphaMode="MASK", alphaCutoff=1.01, extras={**m_.get("extras", {}), "hidden": True})  # (bare then: the cut-off above 1 hides it in viewers that read variants)
        pg.materials.append(m_)
        return len(pg.materials) - 1

    def foliage_material(a_, nm, hidden=False):
        m = a_["mask"]
        orm_ = np.stack([np.ones_like(m[..., 1]), m[..., 1], np.zeros_like(m[..., 1])], -1)
        pg.materials.append({"name": nm, "pbrMetallicRoughness": {
            "baseColorTexture": {"index": pg.tex(_png(a_["color"]), False)},
            "metallicRoughnessTexture": {"index": pg.tex(_png(orm_), False)}},
            "normalTexture": {"index": pg.tex(_png(a_["normal"]), False)},
            "alphaMode": "MASK", "alphaCutoff": 1.01 if hidden else 0.4, "doubleSided": True,
            "extras": {"mask_texture": "R = light comes through (leaf), G = roughness, B = shade",
                       "card_fill": round(a_["fill"], 3)}})
        pg.materials[-1]["extras"]["mask_texture_index"] = pg.tex(_png(a_["mask"]), False)
        return len(pg.materials) - 1
    pg.foliage_material = foliage_material

    pg.seasons = list(pg.seasons or ["summer"])
    pg.variants, pg.var_fol, pg.var_bark = [], {}, {}
    pg.M_FOL = None
    if pg.st and pg.has_leaves:
        pg.se0 = pg.s.get("season", "summer") if pg.s.get("season") in pg.seasons else pg.seasons[0]
        pg.M_FOL = solid_material("foliage", veg_style.season_color(pg.s, pg.se0, pg.st), pg.se0)
        for se in pg.seasons:
            pg.var_fol[se] = pg.M_FOL if se == pg.se0 else solid_material(f"foliage_{se}", veg_style.season_color(pg.s, se, pg.st), se)
        if pg.wet:
            mw = json.loads(json.dumps(pg.materials[pg.M_FOL]))
            mw["name"] = "foliage_wet"
            mw["pbrMetallicRoughness"]["baseColorFactor"] = [0.7 * c_ for c_ in mw["pbrMetallicRoughness"]["baseColorFactor"][:3]] + [1.0]
            mw["pbrMetallicRoughness"]["roughnessFactor"] = 0.4
            pg.materials.append(mw)
            pg.var_fol["wet"] = len(pg.materials) - 1
    # pixar: a layer of real leaf cards on the closed shell = the foliage mesh's next primitive, slot `foliage_cards`
    # (alpha MASK, double sided, a grey leaf atlas x baseColorFactor x COLOR_0), its own material per season
    pg.M_CARDS, pg.var_cards = None, {}
    if pg.st and pg.has_leaves and (pg.st.get("crown") or {}).get("cards") and not pg.trees[0].get("clump"):
        cs_ = {**veg_cloud.CARDS, **pg.st["crown"]["cards"]}
        kg_ = float(max(cs_["tone"]) * (1 + float(cs_["warm_tip"])))

        def cards_material(nm, rgb, season):
            sub_ = veg_cloud.shell_atlas(pg.s, pg.st, season)
            c_ = np.array(veg_style.lin(rgb or [0.5, 0.5, 0.5])) * kg_
            m_ = {"name": nm, "pbrMetallicRoughness": {"baseColorFactor": [*(c_ / max(1.0, float(c_.max()))).tolist(), 1.0], "metallicFactor": 0.0,
                                                        "roughnessFactor": float(pg.st["crown"].get("roughness", 0.8)),
                                                        "baseColorTexture": {"index": pg.tex(_png(sub_["color"] / 255.0), False)}},
                  "alphaMode": "MASK", "alphaCutoff": float(cs_.get("alpha_cut", 0.5)), "doubleSided": True,
                  "extras": {"card_fill": round(sub_["fill"], 3), **({"translucency": {**pg.st["translucency"], "thickness": "TEXCOORD_3.y = metres (cards: thin)"}} if pg.st.get("translucency") else {})}}
            if rgb is None:
                m_.update(alphaCutoff=1.01, extras={**m_["extras"], "hidden": True})
            pg.materials.append(m_)
            return len(pg.materials) - 1
        pg.M_CARDS = cards_material("foliage_cards", veg_style.season_color(pg.s, pg.se0, pg.st), pg.se0)
        for se in pg.seasons:
            pg.var_cards[se] = pg.M_CARDS if se == pg.se0 else cards_material(f"foliage_cards_{se}", veg_style.season_color(pg.s, se, pg.st), se)
    # a styled small plant whose blades lie down in winter (veg_small's winter `flatten`): the lying blades are the
    # foliage mesh's own primitive, slot `foliage_winter`, shown only in winter and snow (when `foliage` is hidden).
    # A second primitive rather than a morph target: the engine already hides slots per season from the seasons json,
    # blades are a few hundred triangles, and it needs no blend weights kept in step with wind and LODs.
    pg.M_FW, pg.var_fw, lie = None, {}, [se for se in pg.seasons if se in ("winter", "snow")]
    if pg.st and pg.has_leaves and len(pg.trees) == 1 and pg.trees[0].get("clump") and lie and pg.se0 not in lie:
        from . import veg_small
        if float((veg_small.season_state(pg.s, "winter") or {}).get("flatten", 0.0)) > 0:
            pg.M_FW = solid_material("foliage_winter", None)
            gone = solid_material("foliage_lying", None)  # (the upright blades' material in winter: hidden)
            for se in pg.seasons:
                if se in lie:
                    pg.var_fw[se] = solid_material(f"foliage_winter_{se}", veg_style.season_color(pg.s, se, pg.st), se)
                    pg.var_fol[se] = gone
                else:
                    pg.var_fw[se] = pg.M_FW


def _leaf_materials(pg):
    """The leaf atlas' material per season (hidden where the plant is bare), the wet foliage and bark, the variants' names."""
    if pg.at is not None:
        pg.M_FOL = pg.foliage_material(pg.at, "foliage")
        for se in pg.seasons:
            if se == "summer":
                pg.var_fol[se] = pg.M_FOL
                continue
            a_ = season_atlas(pg.s, se, pg.twc)
            if a_ is pg.at:
                pg.var_fol[se] = pg.M_FOL
            elif a_ is None:
                pg.materials.append({**json.loads(json.dumps(pg.materials[pg.M_FOL])), "name": f"foliage_{se}", "alphaCutoff": 1.01})
                pg.materials[-1]["extras"] = {**pg.materials[-1].get("extras", {}), "hidden": True}
                pg.var_fol[se] = len(pg.materials) - 1
            else:
                pg.var_fol[se] = pg.foliage_material(a_, f"foliage_{se}")
        if pg.wet:
            mw = json.loads(json.dumps(pg.materials[pg.M_FOL]))
            mw["name"] = "foliage_wet"
            mw["pbrMetallicRoughness"].update(baseColorFactor=[0.78, 0.8, 0.76, 1.0], roughnessFactor=0.45)
            pg.materials.append(mw)
            pg.var_fol["wet"] = len(pg.materials) - 1
    if pg.wet:
        mw = json.loads(json.dumps(pg.materials[pg.M_BARK]))
        mw["name"] = "bark_wet"
        f0 = mw["pbrMetallicRoughness"].get("baseColorFactor", [1, 1, 1, 1])
        mw["pbrMetallicRoughness"].update(baseColorFactor=[0.55 * f0[0], 0.53 * f0[1], 0.5 * f0[2], 1.0], roughnessFactor=0.5)
        pg.materials.append(mw)
        pg.var_bark["wet"] = len(pg.materials) - 1
    pg.variants = [v_ for v_ in pg.seasons + (["wet"] if pg.wet else []) if len(pg.seasons) + bool(pg.wet) > 1]


def _forks(pg):
    """A style's forks (shown when the foliage is not), and with_variants: a primitive's material per variant."""
    # a style's forks (the wood's second primitive): there when the foliage is not
    pg.M_FORK, pg.var_fork = None, {}
    if pg.st and pg.has_leaves:
        bare = {se: veg_style.season_color(pg.s, se, pg.st) is None for se in pg.seasons}
        if any(bare.values()):
            hid = {**json.loads(json.dumps(pg.materials[pg.M_BARK])), "name": "bark_forks", "alphaMode": "MASK", "alphaCutoff": 1.01, "extras": {"hidden": True}}
            vis = {**json.loads(json.dumps(pg.materials[pg.M_BARK])), "name": "bark_forks_bare"}
            pg.materials.extend([hid, vis])
            pg.var_fork = {se: len(pg.materials) - (1 if bare[se] else 2) for se in pg.seasons}
            pg.M_FORK = pg.var_fork[pg.se0]

    def with_variants(p_, table, default):
        if pg.variants and table:
            pg.ext_used.add("KHR_materials_variants")
            by = {}
            for i_, v_ in enumerate(pg.variants):
                by.setdefault(table.get(v_, default), []).append(i_)
            p_["extensions"] = {"KHR_materials_variants": {"mappings": [{"material": m_, "variants": vs} for m_, vs in by.items()]}}
        return p_
    pg.with_variants = with_variants


def _impostor_materials(pg):
    """The impostor's crop and its material per season (crossed quads, or the one camera-facing quad with its recipe)."""

    pg.M_IMP = None
    pg.crop_ = crops_ = None
    if pg.impostor is not None and pg.impostor.get("kind") == veg_impostor.KIND:
        # the quad covers only what any frame of any season draws (the game: a square the bake sphere's size spent
        # half its pixels on nothing)
        ims_ = [pg.impostor["image"]] + [(v_["image"] if isinstance(v_, dict) else v_) for v_ in (pg.impostor.get("seasons") or {}).values()]
        pg.crop_ = veg_impostor.crop(ims_, int(pg.impostor["frames"]))
        crops_ = veg_impostor.crops(ims_, int(pg.impostor["frames"]))
    if pg.impostor is not None:
        def imp_material(nm, im_, nrm_):
            m_ = {"name": nm, "pbrMetallicRoughness": {
                "baseColorTexture": {"index": pg.tex(_png(im_), False)}, "metallicFactor": 0.0, "roughnessFactor": 0.9},
                "alphaMode": "MASK", "alphaCutoff": 0.5, "doubleSided": False,
                "extras": {"impostor": "albedo (unlit; the shade of what stands above it baked in, no sun) + a tangent-space normal map "
                                       "baked from the same two views: light it like any mesh. Front and back of each quad are faces of "
                                       "their own (single sided) with opposite NORMAL and their own TANGENT (w = -1 on the back), so "
                                       "the one normal map reads mirrored through the quad from behind. "
                                       "Engine: the material must NOT RECEIVE shadows (Godot: disable_receive_shadows): the two quads "
                                       "shadow each other, a dark wedge down the middle; casting onto the ground is fine",
                           "receive_shadows": False}}
            if pg.impostor.get("kind") == veg_impostor.KIND:  # one camera-facing quad: the normal map is OBJECT space (+ depth in alpha),
                m_["extras"] = {"hifipushie_impostor": {  # so it is not a glTF normalTexture (tangent space): it rides in the extras
                    "kind": veg_impostor.KIND, "frames": int(pg.impostor["frames"]), "size": round(float(pg.impostor["size"]), 4),
                    "centre": [round(float(c_), 4) for c_ in pg.impostor["centre"]],
                    "normal_texture_index": pg.tex(_png(nrm_), False) if nrm_ is not None else None,
                    "normal": "object space, glTF axes: rgb * 2 - 1; alpha = depth behind the frame's middle plane (0 front .. 1 back of "
                              "the bake sphere, x size)", "recipe": veg_impostor.recipe(int(pg.impostor["frames"]), float(pg.impostor["size"]), pg.impostor["centre"], pg.crop_),
                    "crop": pg.crop_, "crops": crops_, "drawn_share": round(veg_impostor.drawn_share(crops_, int(pg.impostor["frames"])), 3) if crops_ else None,
                    "shader": veg_impostor.SHADER}, "receive_shadows": False}
            elif nrm_ is not None:
                m_["normalTexture"] = {"index": pg.tex(_png(nrm_), False)}
            pg.materials.append(m_)
            return len(pg.materials) - 1
        pg.M_IMP = imp_material("impostor", pg.impostor["image"], pg.impostor.get("normal"))
        pg.var_imp = {}
        for se, im_ in (pg.impostor.get("seasons") or {}).items():
            if se in pg.seasons and se != pg.seasons[0]:
                im_ = im_ if isinstance(im_, dict) else {"image": im_}
                pg.var_imp[se] = imp_material(f"impostor_{se}", im_["image"], im_.get("normal"))
