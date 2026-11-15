"""`write_glb`: the plant's GLB, and write_impostor. Part of the plant export (veg_export.py has the contract).

write_glb is nine stages over one context (PlantGlb), called in order: _subject, _builders (here), _bark,
_foliage_materials, _leaf_materials, _forks, _impostor_materials (veg_export_glb_materials), _plants
(veg_export_glb_plants), _finish (here). No statement of the one function it was has changed (docs/state/export_stages.md).
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from . import veg_export
from . import veg_bark, veg_style
from . import veg_leaf_atlas, veg_leaf_place
from . import veg_style_small
from .veg_export import _normals, _yup
from .veg_export_parts import snow_numbers
from .veg_export_glb_materials import _bark, _foliage_materials, _forks, _impostor_materials, _leaf_materials
from .veg_export_glb_plants import _plants

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
