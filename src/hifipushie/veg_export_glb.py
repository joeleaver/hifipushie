"""`write_glb`: the plant's GLB (one function), and write_impostor. Part of the plant export (veg_export.py has the contract)."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from . import veg_export
from . import veg_bark, veg_bough, veg_cloud, veg_impostor, veg_mesh, veg_style
from . import veg_leaf_atlas, veg_leaf_place
from . import veg_style_dress, veg_style_small
from . import vegetation_grow
from .veg_export import _normals, _png, _yup, veg_small_state
from .veg_export_parts import (
    budget, cluster_leaves, collision, foliage_mesh, impostor_frames, season_atlas, snow_numbers, wind_nodes,
)


class PlantGlb:
    """What the writing of one plant GLB carries from stage to stage: the arguments of `write_glb`, then what each stage sets for
    the ones after it. A stage reads and writes it as `pg.<name>`; what a stage only uses itself is a local there.
    _subject sets:
      trees, names, s, st, bark, bm, tile, twc, has_leaves, at
    _builders sets:
      buf, views, accessors, images, textures, materials, meshes, nodes, ext_used, acc, tex, prim
    _bark sets:
      M_BARK, dabs
    _foliage_materials sets:
      foliage_material, variants, var_fol, var_bark, M_FOL, se0, M_CARDS, var_cards, M_FW, var_fw
    _forks sets:
      M_FORK, var_fork, with_variants
    _impostor_materials sets:
      M_IMP, crop_, var_imp
    _plants sets:
      per, roots
    """

    def __init__(self, **arguments):
        self.__dict__.update(arguments)


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
    pg = PlantGlb(tree=tree, path=path, name=name, triangles=triangles, spacing=spacing, lods=lods, seasons=seasons,
                  impostor=impostor, wet=wet, cap=cap, only_impostor=only_impostor)
    _subject(pg)
    _builders(pg)
    _bark(pg)
    _foliage_materials(pg)
    _leaf_materials(pg)
    _forks(pg)
    _impostor_materials(pg)
    _plants(pg)
    return _finish(pg)


def _subject(pg):
    """What is written: the trees and their names (one plant or a set), the first one's spec and style, the bark's maps and
    tiling, the twig colour, whether anything has leaves, the leaf atlas."""
    pg.trees = pg.tree if isinstance(pg.tree, list) else [pg.tree]
    pg.names = pg.name if isinstance(pg.name, list) else [pg.name]
    pg.tree = pg.trees[0]
    pg.s = pg.tree["spec"]
    pg.st = veg_style.sheet(pg.s)  # a style: the same plant dressed another way (veg_style)
    if pg.st and pg.triangles is None:
        pg.triangles = int(({**veg_style.CLUMP, **(pg.st.get("clump") or {})})["budget"] if pg.tree.get("clump") else pg.st.get("budget", 5000))
    pg.bark = pg.s.get("bark") or {}
    pg.bm = veg_bark.bark_maps(pg.bark.get("kind", "furrowed"), 256, seed=int(pg.s.get("seed", 1)))
    sc = float(pg.bark.get("scale", 1.0))
    pg.tile = [pg.bm["tile"][0] * sc, pg.bm["tile"][1] * sc]
    pg.twc = pg.bark.get("twig_color") or [0.45, 0.4, 0.35]
    pg.has_leaves = any(len(veg_leaf_place.place(t)["pos"]) for t in pg.trees)
    pg.at = veg_leaf_atlas.atlas(pg.s["leaves"], pg.twc) if pg.has_leaves and not pg.st else None


def _builders(pg):
    """The file's buffer and glTF lists, and the builders every later stage calls: view, acc, tex (a picture once), prim
    (one primitive with its wind channels)."""
    pg.buf = bytearray()
    pg.views, pg.accessors, pg.images, pg.textures, pg.materials, pg.meshes, pg.nodes = [], [], [], [], [], [], []
    pg.ext_used = set()

    def view(data: bytes, target=None):
        while len(pg.buf) % 4:
            pg.buf.append(0)
        v = {"buffer": 0, "byteOffset": len(pg.buf), "byteLength": len(data)}
        if target:
            v["target"] = target
        pg.buf.extend(data)
        pg.views.append(v)
        return len(pg.views) - 1

    def acc(a, kind, comp, target, minmax=False):
        a = np.ascontiguousarray(a)
        d = {"bufferView": view(a.tobytes(), target), "componentType": comp, "count": int(len(a)), "type": kind}
        if minmax:
            d["min"], d["max"] = a.min(0).astype(float).tolist(), a.max(0).astype(float).tolist()
        pg.accessors.append(d)
        return len(pg.accessors) - 1
    pg.acc = acc

    tex_seen = {}

    def tex(png: bytes, repeat: bool):
        k_ = (hash(png), len(png), repeat)  # (the same picture is stored once: an impostor's normal map rarely changes with the season)
        if k_ in tex_seen:
            return tex_seen[k_]
        tex_seen[k_] = len(pg.textures)
        pg.images.append({"bufferView": view(png), "mimeType": "image/png"})
        pg.textures.append({"source": len(pg.images) - 1, "sampler": 0 if repeat else 1})
        return len(pg.textures) - 1
    pg.tex = tex

    def prim(V, F, uv, material, wind, colour=None, N=None, uv3=None):
        N = _normals(V, F) if N is None else N
        w4 = np.stack(wind, 1).astype(np.float32)
        at_ = {"POSITION": pg.acc(_yup(V).astype(np.float32), "VEC3", 5126, 34962, minmax=True),
               "NORMAL": pg.acc(_yup(N).astype(np.float32), "VEC3", 5126, 34962),
               "TEXCOORD_0": pg.acc(np.c_[uv[:, 0], 1 - uv[:, 1]].astype(np.float32), "VEC2", 5126, 34962),
               "TEXCOORD_1": pg.acc(w4[:, :2].copy(), "VEC2", 5126, 34962),
               "TEXCOORD_2": pg.acc(w4[:, 2:].copy(), "VEC2", 5126, 34962),
               "_WIND": pg.acc(w4, "VEC4", 5126, 34962)}
        if colour is not None:
            c = np.clip(colour, 0, 1)
            c = np.c_[c, c, c] if c.ndim == 1 else c
            at_["COLOR_0"] = pg.acc(np.c_[c, np.ones(len(c))].astype(np.float32), "VEC4", 5126, 34962)
        if uv3 is not None:  # (a style's own pair of numbers per vertex: Godot reads TEXCOORD_2 + TEXCOORD_3 as CUSTOM0)
            at_["TEXCOORD_3"] = pg.acc(np.asarray(uv3, np.float32), "VEC2", 5126, 34962)
        return {"attributes": at_, "indices": pg.acc(F.astype(np.uint32).ravel(), "SCALAR", 5125, 34963), "material": material}
    pg.prim = prim


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


def _finish(pg):
    """The counts of the whole file, the glTF json (scene, extras, variants, extensions) and the file itself: the result."""
    counts = {"wood_triangles": sum(c["wood_triangles"] for c in pg.per), "foliage_triangles": sum(c["foliage_triangles"] for c in pg.per),
              "twigs_kept": pg.per[0]["twigs_kept"], "wood_min_radius_m": pg.per[0]["wood_min_radius_m"], "budget": pg.triangles,
              "floating": max(c["floating"] for c in pg.per), "lods": pg.per[0]["lods"], "variants": pg.variants,
              "collision_capsules": len(pg.per[0]["collision"]), "collision_triangles": pg.per[0].get("collision_triangles", 0)}
    if pg.st and pg.per[0]["lods"] and pg.per[0]["lods"][0].get("style"):
        counts["style"] = pg.per[0]["lods"][0]["style"]
    if pg.at is not None:
        counts["atlas_px"] = int(pg.at["color"].shape[0])
    if len(pg.trees) > 1:
        counts["plants"] = pg.per
    pg.name = pg.names[0] if len(pg.trees) == 1 else "set"
    while len(pg.buf) % 4:
        pg.buf.append(0)
    gltf = {"asset": {"version": "2.0", "generator": "hifipushie vegetation"},
            "scene": 0, "scenes": [{"nodes": pg.roots}], "nodes": pg.nodes, "meshes": pg.meshes,
            "materials": pg.materials, **({"textures": pg.textures, "images": pg.images} if pg.textures else {}),
            "samplers": [{"wrapS": 10497, "wrapT": 10497, "magFilter": 9729, "minFilter": 9987},
                         {"wrapS": 33071, "wrapT": 33071, "magFilter": 9729, "minFilter": 9987}],
            "accessors": pg.accessors, "bufferViews": pg.views, "buffers": [{"byteLength": len(pg.buf)}],
            "extras": {"hifipushie_plant": {"name": pg.name, "species": pg.s.get("species"), "age": pg.s.get("age"),
                                            "height_m": round(pg.tree["height"], 2), "stats": pg.tree["stats"],
                                            "set": len(pg.trees) if len(pg.trees) > 1 else None, "bark_tile_m": pg.bm["tile"],
                                            "lods": [[{k_: v_ for k_, v_ in c.items()} for c in p_["lods"]] for p_ in pg.per],
                                            "wind": veg_export.WIND_RECIPE, "variants": pg.variants, "contract": veg_export.CONTRACT,
                                            "style": None if not pg.st else {
                                                "name": pg.st["name"], "sheet": {k_: v_ for k_, v_ in pg.st.items() if k_ != "about"},
                                                "simplified": veg_style_small.lines(pg.per[0]["lods"][0]["style"]) if pg.per[0]["lods"] and pg.per[0]["lods"][0].get("style") else [],
                                                "kind": "clouds" if pg.dabs is not None else "masses",
                                                "foliage": ("leaf clouds: alpha-MASK cards, double sided; albedo = the dab atlas's grey tone x the "
                                                            "`foliage` material's baseColorFactor (one per season variant) x COLOR_0 (the clump's "
                                                            "painted gradient, one step per card); NORMAL = out of the clump's middle; TEXCOORD_0 = "
                                                            "the atlas uv; TEXCOORD_3 = (gradient 0 base .. 1 top of its clump, (clump + 0.5) / clumps); "
                                                            "wind: TEXCOORD_2.y = flutter, 0 at a card's middle .. at its rim") if pg.dabs is not None else
                                                           "closed masses, no texture: albedo = the `foliage` material's baseColorFactor "
                                                           "(one per season variant) x COLOR_0 (each mass's tone); NORMAL = smooth over each "
                                                           "mass; TEXCOORD_0 = (height within its mass 0..1, (mass index + 0.5) / masses)",
                                                "season_colors_srgb": {se: veg_style.season_color(pg.s, se, pg.st) for se in veg_style.SEASONS}},
                                            "snow": "engine shader: see snow_numbers (in <name>_seasons.json as `snow`); "
                                                    "the `snow` variant is the ready-mixed foliage colour / picture",
                                            "snow_numbers": snow_numbers(pg.s, pg.st),
                                            "collision": [{"plant": p_["name"], "capsules": p_["collision"],
                                                           "mesh_node": p_.get("collision_node")} for p_ in pg.per]}}}
    if pg.variants:  # (declared even when no slot changes with the season: <name>_seasons.json is the contract's first file,
        # and a styled clover that looks the same all year wrote none)
        pg.ext_used.add("KHR_materials_variants")
        gltf["extensions"] = {"KHR_materials_variants": {"variants": [{"name": v_} for v_ in pg.variants]}}
    if pg.ext_used:
        gltf["extensionsUsed"] = sorted(pg.ext_used)
    js = json.dumps(gltf, separators=(",", ":"), default=float).encode()
    js += b" " * (-len(js) % 4)
    out = Path(pg.path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(pg.buf)))
        f.write(struct.pack("<I4s", len(js), b"JSON"))
        f.write(js)
        f.write(struct.pack("<I4s", len(pg.buf), b"BIN\0"))
        f.write(bytes(pg.buf))
    counts["bytes"] = out.stat().st_size
    counts["path"] = str(out)
    return counts


def write_impostor(tree: dict, path: str, name: str, impostor: dict, seasons=("summer",)) -> str:
    """The impostor LOD alone, as a file of its own (its pictures per season as variants)."""
    return write_glb(tree, path, name, impostor=impostor, only_impostor=True, seasons=seasons)["path"]
