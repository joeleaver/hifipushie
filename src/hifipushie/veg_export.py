"""A plant as a GLB (first export: one LOD; LODs, wind data and season variants are stage 4).

Two meshes: `wood` (branch tubes; bark base colour = the bark's colour x its tiling albedo, normal and roughness maps,
REPEAT sampling on the branch uv) and `foliage` (every twig's card, realised into one mesh; the twig atlas as base
colour with alpha MASK, double sided; COLOR_0 = a per-twig tint). glTF axes (Y up: x, z, -y), uv v flipped. Textures
are embedded. extras carry the plant's name, stats and counts.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at veg_export.NAME: C422). veg_export_parts: what goes into a plant's GLB: wind nodes, the foliage mesh, kept
wood and twigs, budgets, the season atlas, collision, snow numbers, impostor frames and maps. veg_export_glb:
`write_glb`: the plant's GLB, as nine stages over one context (PlantGlb): the context, the stages in order, what is
written, the buffer and its builders, the file's end; and write_impostor. veg_export_glb_materials: its materials
(bark, a style's foliage, the leaf atlas per season, wet, forks, the impostor's: five stages). veg_export_glb_plants:
every plant's meshes and nodes per LOD (one stage). veg_export_files: the files beside the GLB: seasons_json,
write_collision.
"""
from __future__ import annotations

import io

import numpy as np
from . import moved

def veg_small_state(spec: dict, season: str):
    from . import veg_small
    return veg_small.season_state(spec, season)


def _normals(V, F):
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    ln = np.linalg.norm(N, axis=1, keepdims=True)
    return np.where(ln > 1e-12, N / np.maximum(ln, 1e-12), [0, 0, 1.0])


def _png(a) -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(np.clip(np.asarray(a) * 255 + 0.5, 0, 255).astype(np.uint8)).save(b, "PNG")
    return b.getvalue()


def _yup(v):
    return np.stack([v[:, 0], v[:, 2], -v[:, 1]], 1)


CORE_DARK = 0.45  # how much darker a limb card is at the trunk than at its tip
LODS = ((1.0, 2.5), (0.45, 2.5), (0.18, 4.0))  # (share of the budget, how much larger a kept card may be drawn)
AUTUMN = [0.78, 0.56, 0.16]
WIND_RECIPE = ("vertex shader: TEXCOORD_1 = (trunk, branch) weights, TEXCOORD_2 = (phase, flutter); the same four in _WIND "
               "(VEC4: trunk, branch, phase, flutter). P += windDir * (trunk * A_tree * sin(w_tree * t) + branch * A_limb * "
               "sin(w_limb * t + 6.283 * phase)) + N * flutter * A_leaf * sin(w_leaf * t + 40 * phase + dot(P, 3)); "
               "A_tree ~0.02 x height x gust, A_limb ~0.25 m x gust, A_leaf ~0.02 m, w_tree ~1, w_limb ~2.3, w_leaf ~9 rad/s")

# The export contract an engine maps by name: material slots, vertex channels, files. Bump it whenever a slot or a
# channel is added, renamed or changes meaning (and say so in vegetation_guide.md "The export contract").
CONTRACT = 13
CONTRACT_LOG = {
    1: "slots bark, foliage (+ foliage_boughs<n>), impostor; TEXCOORD_1 = (trunk, branch), TEXCOORD_2 = (phase, flutter), _WIND; "
       "COLOR_0 on foliage; season variants; <name>_collision.glb; <name>_seasons.json",
    2: "styled deciduous plants: slot bark_forks (the wood mesh's second primitive, hidden except in bare seasons); "
       "impostor_<season> pictures",
    3: "styled small plants: slot heads (the foliage mesh's second primitive: flower / seed heads, hidden out of their seasons); "
       "impostor: normalTexture + TANGENT, 16 vertices (front and back of each quad apart, opposite normals), the second "
       "picture no longer mirrored, albedo with baked shade; seasons json: contract, slot_list, normalTexture files",
    4: "style anime (leaf clouds): slot foliage is alpha-MASK cards, double sided, with a baseColorTexture (a grey dab atlas: tone x "
       "baseColorFactor x COLOR_0) and TEXCOORD_0 = the atlas uv (in blobby it is (height in mass, mass id)); new channel TEXCOORD_3 = "
       "(gradient 0 base .. 1 top of its clump, (clump + 0.5) / clumps) (Godot: CUSTOM0.zw); COLOR_0 = the clump's painted gradient step; "
       "no bark_forks slot (the forks are in `bark`); seasons json: `snow` numbers (colour, coverage, the normal threshold), "
       "`style` (name, foliage kind); impostor albedo: baked shade scaled by the season's brightness",
    5: "the `snow` variant of a leaf-dropping plant (realistic or styled) is its WINTER state under snow: foliage (and a style's "
       "heads) hidden, bark_forks shown, the snow impostor the bare tree; evergreens keep their crown in snow (as in 4)",
    6: "the impostor LOD is HEMI-OCTAHEDRAL by default: ONE quad (2 triangles, uv = its corners) that the engine's shader turns "
       "to the camera, slot impostor's baseColorTexture = an N x N atlas of views over the upper hemisphere (sRGB + alpha), its "
       "object-space normal map (+ depth in alpha) in extras.hifipushie_impostor.normal_texture_index (NOT normalTexture), "
       "frames / size / centre / recipe there and in the seasons json `impostor` (+ impostorNormalTexture files per season); "
       "reference Godot shader spikes/godot_veg/impostor_octa.gdshader. impostor=\"cross\" keeps the old two crossed quads. A plant exported without an impostor (small plants, clumps) carries \"impostor\": null in the seasons json. "
       "Slot heads (styled small plants) now carries COLOR_0 = each part's colour (petals / dab / ball, the flower's centre, the "
       "stalk) with a WHITE baseColorFactor: switch vertex colour on for heads as for foliage. A style's clump block takes "
       "heads_kind ball | dab | petals (anime: colour dabs; cartoon: petalled daisies). Styled small plants whose blades lie down "
       "in winter: slot foliage_winter (the foliage mesh's next primitive: the blades lying, shown only in winter and snow, "
       "when foliage is hidden)",
    7: "a styled closed crown's (blobby / cartoon masses or tiers) season material MAY carry a baseColorTexture: a RAMP over "
       "TEXCOORD_0.x (0 = a mass's foot / a cone tier's rim .. 1 its top; clamp sampler; v ignored), albedo = baseColorFactor x "
       "texture x COLOR_0 (cartoon conifers' spring: lime tips on every tier's rim). The seasons json lists it under that "
       "season's foliage slot as baseColorTexture {file}: an engine that sets season materials from the json must set the "
       "texture too (or keep the GLB's variant material). Anime seed / flower heads (slot heads, kind dab) are clusters of "
       "small closed blobs now, not flat discs (same slot, same channels)",
    8: "the octahedral impostor's quad is CROPPED: extras.hifipushie_impostor.crop (and the seasons json `impostor.crop`) = "
       "[u0, u1, v0, v1] of a frame that every frame of every season draws inside; the engine's quad is centre + (mix(u0, u1, "
       "uv.x) - 0.5) * size * right + (0.5 - mix(v0, v1, uv.y)) * size * up (reference shader: uniform `crop`); frames, atlas "
       "uv and size unchanged; the GLB's stored quad is that rectangle. A reader that ignores crop still draws correctly, "
       "just with the old (bigger) square. Anime crowns' LOD1 / LOD2 carry fewer card layers (outer shells only) and smaller "
       "cards: same slots and channels",
    9: "style PIXAR: slot foliage = the closed canopy shell (opaque, no texture; COLOR_0 = a gradient base-to-tip, warmer at "
       "the tips, x the material's baseColorFactor; NORMAL = the shell's, blended half way toward out of the canopy's middle) "
       "and NEW slot foliage_cards = the foliage mesh's next primitive: real leaf cards on the shell's outside (alpha MASK, "
       "double sided, baseColorTexture = a grey atlas of the species' own leaf outlines x baseColorFactor x COLOR_0; NORMAL = "
       "the shell's under the card; TEXCOORD_0 = the atlas uv), its own material per season variant (hidden when the plant "
       "is bare). On both: TEXCOORD_3 = (gradient 0 base / inside .. 1 tip, THICKNESS = metres of canopy behind the point "
       "along -NORMAL, capped 4 m; cards 0.02) for the engine's subsurface / back light; material extras.translucency = "
       "{color sRGB, amount}. Wood: every structural limb in one mesh (no bark_forks slot). REALISTIC small plants whose blades "
       "lie down in winter now carry slot foliage_winter too (their cards regrown lying; the atlas the season's own)",
    10: "NEW GRADE for small plants, `groundcover` (export_plant(grade=\"groundcover\"), its own folder): LOD 0..2 = 6 / 4 / 3 "
        "vertical alpha cards through the clump's foot (+ one lying flat for low plants: clover, ferns), 288 / 96 / 36 triangles "
        "(+16 / 8 / 2 flat), the full plant in its style BAKED onto them per season. One slot, `foliage`: alpha MASK (cut 0.5), "
        "SINGLE sided (front and back are triangles of their own, NORMALs leaning up and toward their own face, mirror "
        "images through the card; TANGENT is NEW: w = +1 on the front, -1 on the back), baseColorTexture (sRGB, shade baked in) + normalTexture (tangent space) per season variant "
        "(winter = the plant lying, snow = winter under snow); no COLOR_0, no bark / heads / foliage_winter slots (stalks, "
        "flower heads and the lying winter blades are in the pictures). Wind channels as every plant. Each tier's pictures are baked at "
        "the size that tier is seen at. Engine: import the textures WITHOUT mipmaps, or WITH them and alpha scaled by the mip "
        "level in the shader (material extras.alpha_mips: three lines; with mips and without it thin blades vanish past "
        "~4 m), and turn the importer's own mesh LOD generation off for these meshes. Full-grade files are unchanged except this version number",
    11: "NEW PLANT KIND `sward` (species sward / sward_mown / sward_rough, any style): plain grass as a 2 m TILE of blade "
        "ribbons, not a clump. Lay tiles edge to edge on a tile_m grid, each turned a random multiple of 90 deg, NO random "
        "scale and no thinning; LOD by the tile's distance (seasons json `sward.lod_rings_m`, 4 LODs = fewer, wider "
        "blades). One slot, `foliage`: OPAQUE, no texture, single sided (undersides are triangles of their own), albedo "
        "= baseColorFactor x COLOR_0 x sward.color_gain (COLOR_0 = root-to-tip gradient x a tone per blade); "
        "TEXCOORD_3 = (0 root .. 1 tip, blade id); wind channels as every plant. The seasons json has a `sward` block: "
        "tile_m, fade {start, end} + fade_recipe (past start the engine shrinks the blades into the ground and mixes "
        "their colour to the terrain's grass colour; nothing is drawn past end), ground_linear / root_linear / "
        "tip_linear (made for the terrain style's grass colour of that cover kind), blades_per_m2. Other files unchanged",
    12: "<name>_seasons.json says what the files are: top-level `grade` (\"full\" | \"groundcover\" | \"sward\": engines that drop "
        "material extras, Godot, read it here, not from the folder's name), `lods` (triangles per LOD) and, for the "
        "groundcover grade, `alpha_mips` (the mip-scaled alpha recipe). A full plant whose slots never change with the "
        "season now writes the json too. No groundcover grade for ferns (the export refuses: use the full plant). "
        "SWARD: per-blade LOD. New channels TEXCOORD_4 = across (a vertex's offset from its blade's centre line, model "
        "x, z), TEXCOORD_5 = (blade rank 0..1, this mesh's width multiple) (Godot CUSTOM1.xy / .zw); json `sward.lod` "
        "{dist, share, band, recipe}: the vertex shader thins and widens blades by distance so no ring or tile edge "
        "shows; pick a tile's mesh by its NEAREST point (rings moved in: meadow 5 / 12 / 24 m, last LOD 5% of the blades "
        "at 20 x width); `sward.fade.blend_from`: albedo, normal and roughness go to the ground's from there to fade.end; "
        "`sward.renderer` = the steps to build a tile renderer; `sward.wind`. A contract-11 sward drawn the old way still "
        "works (the new channels are extra). Later the same day, no bump (values and added recipe keys only): a sward's "
        "season factors are the terrain style's seasonal grass tints (whole in the json, may exceed 1; snow = winter's "
        "straw), `sward.density` (how a sward ends: a 0..1 density thins and shortens blades), `sward.winter` (lying "
        "straw), `sward.snow` (the tile sinks by the snow depth; fade to the snow colour), `sward.season_ground_linear`",
    13: "NEW GRADE `clutter` (clutter.py; make_clutter / clutter_kit; its own folders <style>_<kind>/): terrain clutter as assets. Top-level "
        "`grade`: \"clutter\", `kind` (boulder | river_rock | cobbles | slab | driftwood | bush | litter) and a `clutter` block: size_m (1: instance "
        "scale = the largest plan dimension in m), height_m, sink_m (the pivot is the ground line; that much of the mesh is below it), size_range_m, "
        "variants [{name, lods [{file, triangles, outline_iou}], collision (a convex hull GLB, node ...-convcolonly) | null}], lod_switch_m (x the "
        "instance's scale), wet / tint / instancing recipes. ONE slot per folder: `rock` or `wood` (OPAQUE; baseColorTexture + normalTexture + "
        "ormTexture = R occlusion, G roughness; POSITION, NORMAL, TANGENT, TEXCOORD_0; textures are separate PNGs referenced by uri, one atlas "
        "shared by every variant and LOD), `foliage` on a bush (alpha MASK; the same maps; + TEXCOORD_1 / TEXCOORD_2 / _WIND as plants; a season = "
        "another albedo picture in seasons.<season>.foliage.baseColorTexture.file) or `litter` (alpha MASK albedo only, a picture per season, hidden "
        "under snow). No <name>_LOD<k>.glb at the folder's top: files are per variant (<stem>_v<k>_LOD<j>.glb). <root>/clutter.json maps terrain "
        "clutter kinds to folders per style. Plants are unchanged. ABSENT VALUES in a clutter json (added 2026-10-09, no number change: a "
        "first loader crashed on \"snow\": null): a STATE or block that does not apply is an EMPTY OBJECT {} or an object saying so (litter: "
        "snow = the snow numbers with coverage 0 and hidden true; clutter.wet {}), an absent LIST is [] (instance_tints), and only an absent "
        "TEXT, FILE or single NUMBER is null (tint, collision, textures.normal, textures.seasons, lod_switch_m.lod2, style.foliage, impostor). "
        "Same day: rock pictures hold their stated colour as their mean and a cliff's tone range (clutter_build.tone_range); clutter.wet.row names "
        "the clutter.csv column (`water`, m) the wet line comes from, `sink` (m) buries a row deeper.",
}
IMPOSTOR_AZIMUTHS = (0, 90)  # the two pictures: looking along +y (image right = +x), then along +x (image right = -y)
IMPOSTOR = {"shade": 0.5, "depth": 1.0, "depth_cards": 0.5, "shade_bright": 0.7}  # (measured in Godot: spikes/godot_veg; cards let light through a crown)


SNOW = {"color": [0.9, 0.92, 0.95], "coverage": 0.8}  # (the looks' snow: blender_vegetation._weather at season "snow")


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("veg_export_parts", "veg_export_glb", "veg_export_glb_materials", "veg_export_glb_plants", "veg_export_files")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
