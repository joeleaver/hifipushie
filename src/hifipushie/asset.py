"""Game-ready export: a low-poly mesh with UV atlases and PBR textures baked from the exact model.

Triangles per part follow geometric error (one joint decimation), scaled by parts.<p>.triangle_weight; texels
per metre follow parts.<p>.texel_density and texel_focus regions; a texel density (texels/m) opens atlases as
needed (or parts.<p>.atlas / atlases=n split the parts by hand), each with its own maps and GLB material.
Prefabs with 2+ instances are meshed and baked once (at their first instance) and placed by a node per instance.

Geometry is never baked from a high-poly mesh: each texel's point on the low-poly surface is projected onto the
exact field, and read there:
  normal        tangent-space (MikkTSpace, OpenGL / glTF convention: green = +V), from the field's gradient,
                tilted by the painted relief's slope
  height        signed distance from the low-poly surface to the exact one along the low-poly normal (m), plus
                the painted relief; low poly + height reproduces the sculpt. 16-bit PNG, 0.5 = 0,
                +-`height_range` m at 0 / 1.
Paint and AO come from the model's Blender scene (`scene_maps`), baked by Cycles onto the low poly per pixel:
  basecolor, roughness, metallic, specular   the scene's shader nodes (paint layers compiled by paintnodes)
  ao            the scene's Cycles AO: each asset's own (a prop never shadows the building or another prop)
  orm           glTF packing: R = ao, G = roughness, B = metallic
Plus asset.glb (glTF 2.0, Y up, the creature facing +Z, one mesh per part, one material per atlas with base
colour, ORM, normal and KHR_materials_specular) and asset.json describing all of it (mm/texel per part).

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at asset.NAME: C422). asset_budget: running Blender for the export, and its budgets: the lash cap, export_gb,
budget_check, hair_budget, margins. asset_parts: parts on the way to the atlas: planar UVs, the low poly, flattened
parts, part weights and triangle limits, focus regions and decals, atlas groups, texture loads, the log. asset_split:
splitting parts: density groups, split, mesh parts, big parts, topology parts. asset_hidden: what does not show: skin
under cloth, culling under garments, deep hidden faces, hidden export parts. asset_raster: rasterizing and UV space:
rasterize, UV islands, projection, corners, dilation, fills across seams, PNG. asset_bake: the bake: inner paint, the
face's keep paint, the lip floor, and `bake`. asset_quality: checks on the result: seam steps, designed interiors,
mesh quality, defect regions. asset_scene: the bake's scene: whether it needs OSL, the cage and its clearance, scene
maps, FBX. asset_glb: GLB: vertices, transforms, the bend / corrective / twist recipes, garment stacks, write_glb,
head and body meshes, texel sizes. asset_gates: gates at the export: cloth decimation, the approved head, the face's
light, fold form, the default hair tier. asset_export: `_export`: the export as
thirteen stages over one context (`Export`), and `preview`; the stages: asset_export_parts (split and mesh, texel density,
the low poly, the bake), asset_export_wear (hair, clothes, lashes, each part's look), asset_export_rig (the rig, face
shapes, pose correctives), asset_export_lods, asset_export_finish.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import store
from . import moved

SCRIPT = Path(__file__).with_name("blender_asset.py")

GAME_SCRIPT = Path(__file__).with_name("blender_game.py")


EML_PARTS = ("eyes", "teeth", "teeth_lower", "tongue", "brows")

_ROLE_T = {"parts": {"hair_cards": {"default": 25000, "range": [15000, 50000]}, "head": {"default": 10000}},
           "lod0_triangles": {"default": 100000}}

EYES_AO_OFF = True  # (r23: the export's sclera AO read mean 0.38, CoV 0.77, p5 0.02 in the rest pose's lid shadow: the
# "blotchy sclera" in engine renders, absent from the scene's gate render; real-time eyes take their occlusion from
# the lids as they stand, not a baked map) the base's eyes part gets AO 1
DECAL_MAX = 2000.0  # texels per metre a decal asks for at most (0.5 mm: small print stays readable)
DECAL_GAIN = 16.0  # and at most this many times its part's own density

SEAM_LIMIT = 1.5  # seam_steps excess over which the export warns (texture space; ~1 = invisible)
BAKE_SS = 2  # Cycles bakes BAKE_SS^2 points per texel, box-filtered (one point per texel aliased sharp paint)
BAKE_PREFILTER = True  # (s14) paint images finer than the bake's sample spacing are box-downsampled first (a mip level):
# Cycles point-samples image textures, so Garrett's 0.06 mm stubble hairs under 0.2 mm bake samples came out as sparse
# texel-sized black / white specks (the stage's EEVEE mipmaps them into a soft shadow). False = the old point sampling.
BAKE_SS_PX = 8192  # ... while the supersampled image's side stays within this
BAKE_SAMPLES = 1  # emission bakes: one sample per texel (4 cost 4x and changed nothing measurable)
FILL = 0.6  # the fraction of an atlas the packed islands fill: a first guess, corrected from the first unwrap

HIDDEN_RIM = 0.012  # m: buried skin and cloth is kept this far in from what shows
OWN_SURFACE = 0.0012  # m: a GNM mouth part's meshed vertex this near GNM's own (subdivided) vertices is its surface


UNDER_CLOTH_REACH = 0.06  # m: skin with a garment this close along its normal is covered
UNDER_CLOTH_TUBE = 0.012  # m: ... within this radius of the normal's line (the sim mesh is ~1 cm)
UNDER_CLOTH_RIM = 0.04  # m: covered skin this close to uncovered skin stays (a sleeve's cuff, a collar, a hem
# lifting in a pose: what the opening shows)
LOD_PUSH_WORN = True  # (r54) ... and the parts worn under them (socks, the body), where they were under at LOD0
LOD_PUSH_WORN_MIN = 20  # LOD0 vertices under a garment for a part to count as worn under it
LOD_PUSH_WORN_NOT_OVER = True  # (r55) see the mask in export
LOD_PUSH_WORN_SHARE = 0.85  # (r55) ... and at least this share of its vertices with a garment in reach UNDER it (the
# rest have the garment poking through them): worn under, not over. rc2d LOD0: socks 0.99, body 0.89, shoes 1.00 (the
# collar under the jeans' hem: 46 vertices, those move); worn over: badge 0.49, lanyard 0.48, clip 0.58, laces 0.67,
# badge_card 0.83 (the margin is thin there: a flat card's back faces see the coat)
LOD_PUSH_WORN_SKIP = ("head", "eyes", "teeth", "teeth_lower", "tongue")  # (the head's meshes: its neck seam ring meets
# the body's; the body's side of it is under the collar at most)
LOD0_PUSH_UNDER = True  # (r57) the garments' under layers are put under their covers at LOD0 too
LOD0_UNDER_GAP = 0.0015  # m: ... this far under (cloth.PUSH_UNDER_GAP); the LODs use lods.LOD_UNDER_GAP
LOD_PUSH_UNDER = True  # (r53) each LOD puts the under garments back under their decimated covers (lods_under.push_under_layers)

LOD_SKIN_CULL_FROM = 1  # (Garrett s14) from this LOD on the skin too drops its faces deep under the garments at LOD0
# (lods_under.cull_covered), keeping every face a clip frame of cull_poses uncovers; None = the skin is never culled per LOD

CLOTH_UNDER_CULL = True  # (r53) asset.export's cull_under_cloth also drops an under garment's faces its covers hide

MISS_FILL_3D = 8  # (r66) texels whose Cycles ray found no scene mesh INSIDE their triangle take the inverse-distance mean
# of this many nearest baked texels of the same part ON THE SURFACE (3D), not the nearest texel in the atlas: filled in
# the atlas, a run of missed texels (rc2p/q: 1.9% of the head's, at the nostril rims and the ala's groove) copied its
# border in a texel staircase, from whatever lay next to it in the atlas (a tiny island beside it: blocky dark / pink
# patches, game_ready.md r64-r66). 0 = the atlas fill only.

INNER_PAINT_ROUGHNESS = 0.4  # the inner lip: moist, a soft sheen (0.25 read as wet plastic streaks in every
# smile and the jaw open: coordinator on m18, 2026-10-15)

# (r65) the skin's tiling micro detail is baked into the part's own normal / roughness / colour maps (False = the
# old split: tiling maps only, which the GLB can't carry)
BAKE_SKIN_DETAIL = True

LIP_FLOOR_ROUGHNESS = 0.38  # (r66) bake(): the export's lower lip is never glossier than this. The stage's lip sheen pad
# (skin:lip_sheen, 0.24 at 0.8) was tuned with the lip lines breaking its highlight; baked, those lines are sub-texel
# (0.24 mm deep, ~1 mm period at 0.77 mm texels: a faint ripple, r65), so the GLB's lower lip was one unbroken, wet-plastic
# highlight at ~0.31 (game_ready.md r64 / r65). The floor is laid by the skin's own lower-lip zone, per texel.
LIP_FLOOR_ZONE = {"zone": {"name": "lip_lower", "grow": 0.6}}  # (lip_sheen's own zone: the pad never reaches past it)

LIP_ASTRAY_WARN = 0.045  # bake(): the share of the lips' front-band texels whose projection went astray, over which
# the log warns (clean v31/v37 2.5%, v32's torn streaks 6.5%: tests/test_lip_astray.py; a narrow margin, 2.6x)

DEFECT_CLUSTER = 12  # this many folded edges / turned faces by one joint is a tear or a tangle someone will see

BAKE_CAGE = True  # (r51) bake through a per-vertex cage (cage_verts) instead of one extrusion per part

CAGE_CLEAR = 0.45  # cage_verts: a vertex's cage at most this share of its clearance (first hit of the part's own surface
CAGE_MIN = 0.0002  # along its cage normal), never under CAGE_MIN metres (a ray starting on the surface misses it)

# ---- GLB -------------------------------------------------------------------------------------------------------
_Z_TO_Y = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], np.float64)  # Blender (Z up, faces -Y) -> glTF (Y up, faces +Z)

BEND_RECIPE = ("Bend helpers (<joint>Bend: ForeArmBend at the elbow, LegBend at the knee, ArmBend at the shoulder, "
               "UpLegBend at the hip) are leaf joints after the Mixamo set, children of the joint's PARENT, standing at the "
               "joint. Drive each every frame after the animation: local rotation = slerp(identity, the driver joint's "
               "local rotation from its rest, share) (share 0.5: half the elbow's bend). The blend zone of the hinge's "
               "skin rides them, so a bent elbow / knee keeps its volume instead of collapsing to the chord. Undriven they "
               "stay on the parent and the hinge's skin lags: they MUST be driven (Unreal: a Control Rig / AnimBP "
               "'Copy Bone' with weight 0.5 or a pose driver; Unity: a Multi-Rotation Constraint at 0.5; Godot: copy "
               "the slerped rotation in _process).")


REST_HOW = ("A rest expression (spec face_shapes.rest: a grin, a scowl) is carried, not baked: the mesh stays the true "
            "neutral (mouth closed) and each face-shape mesh's glTF mesh.weights (the default morph weights every glTF "
            "loader applies) are the rest weights, correctives by formula unless the rest sets one; mesh.extras.restExpression "
            "names them. An engine shows the rest by default; to play a clip or lipsync on it, set ABSOLUTE weights "
            "(e.g. max(rest, clip) per channel, or blend from the rest) and the correctives by formula every frame, "
            "and return to restExpression after. Not baked because correctives are min() of absolute weights and a "
            "closed mouth, a blink or a viseme over a baked grin needs weights below it (negative), which engines "
            "clamp (facepose.compare_rest).")
CORRECTIVE_RECIPE = (
    "Pose correctives are morph targets named corr_<Side><Joint>_<motion><deg> (on the skin and the parts worn over the "
    "joint; every LOD keeps them). Each is faded in by its joint's angle, every frame after the animation and the "
    "helper / twist drivers: take the joint's local rotation from its rest, split it into swing (about an axis across "
    "the bone) and twist (about the bone); deg = swing angle x dot(swing axis, axis_rest) (axis_rest in the parent's "
    "frame at rest = the json's Blender axes; glTF: (x, z, -y)); weight = 0 below from_deg, rising linearly to 1 at "
    "key_deg, then (when to_deg is set) falling to 0 at to_deg while the next key of the motion rises. Unreal: a Pose "
    "Driver node (swing, the joint, these targets as curves) or a Control Rig writing the curves; Unity: a script or "
    "Animation Rigging job setting SkinnedMeshRenderer.SetBlendShapeWeight (x100) in LateUpdate; Godot: a script "
    "setting MeshInstance3D.set_blend_shape_value in _process after the AnimationPlayer. Left at 0 the mesh bends "
    "by its weights alone (the arc weights, still sound).")
TWIST_RECIPE = {
    "what": "Twist bones are extra leaf joints after the Mixamo set (children of the Arm / ForeArm / UpLeg / Leg "
            "joints, named <segment>Twist<k>, k counted away from the body). Nothing animates them: left alone they "
            "ride their parent and the skin is what it would be without them. Drive them every frame, after the "
            "animation, to spread a segment's roll along it.",
    "driver": "roll = the twist of the DRIVER joint's local rotation (its pose relative to its rest; every Mixamo "
              "joint here rests unrotated) about the segment's axis (extras.axis_parent, in the driver's parent's "
              "rest frame = model space at rest): with q = (w, v) the local rotation and a the axis, "
              "roll = 2 atan2(v . a, w) (swing-twist decomposition). Then set each twist joint's local rotation to "
              "rest x turn(axis_local +Y, share x roll). After an import that re-orients bones (FBX), use "
              "q = inverse(rest local rotation) x pose local rotation, and for a the direction from the segment's "
              "joint to its child joint in that joint's rest frame; the twist joint still turns about its own "
              "length.",
    "modes": "follow: the driver is the segment's child (Hand for ForeArmTwist, Foot for LegTwist); shares rise to "
             "1.0 at the wrist/ankle, so the joint itself keeps no twist. counter: the driver is the segment's own "
             "joint (Arm for ArmTwist, UpLeg for UpLegTwist); shares are negative, -1.0 at the shoulder/hip (that "
             "skin stays with the clavicle/pelvis) rising to 0 at the elbow/knee.",
    "godot": "Godot 4: a SkeletonModifier3D after the AnimationMixer (in _process_modification read "
             "get_bone_pose_rotation(driver), compute roll as above, set_bone_pose_rotation(twist, rest_rotation * "
             "Quaternion(Vector3.UP, share * roll))); newer versions also have BoneTwistDisperser3D, which spreads "
             "a child's twist over a chain. Bone names lose the colon on import (mixamorig_LeftForeArmTwist1).",
    "unity": "Unity: Humanoid avatars ignore the extra joints (keep them as extra transforms: untick 'Strip bones' "
             "/ leave Optimize Game Objects off, or expose them), so Mixamo clips play unchanged; drive them in "
             "LateUpdate, or with the Animation Rigging package's Twist Correction constraint (source = the driver "
             "joint, twist axis = the segment's, twist nodes with weights = the shares; its weights run -1..1, so "
             "counter chains work too). The avatar's own 'Upper/Lower Arm Twist' muscle settings only move roll "
             "between the two Mixamo joints of a limb (they know no extra bones): set them so the roll stays on the "
             "hand / upper-arm joint, and let the twist joints spread it.",
    "unreal": "Unreal: in a Post Process Anim Blueprint or Control Rig on the skeletal mesh (where the Mannequin "
              "drives its lowerarm_twist_01/02 and upperarm_twist_01/02), per twist bone: read the driver's roll "
              "about the segment axis and set the bone's local rotation to rest x (share x roll about its Y); "
              "Control Rig's 'Twist Bones' node does a follow chain in one node. Keep the twist bones out of the IK "
              "Rig's retarget chains so retargeted animation leaves them to the post process.",
}


_FROZEN_OVER: dict = {}  # {(path, mtime, size): the frozen garment's own "over"} (the pickles are big: read once)


def export(name: str, out_dir: Path, *args, **kw) -> dict:
    """See `_export`; holds the machine's heavy-job slot (`resources.heavy`) so exports don't stack up."""
    from . import asset_budget, asset_export
    from . import resources
    prog = store.HOME / name / "progress.log"

    def waiting(msg: str):  # the wait shows where the export's progress does (an oxidegen artist's task progress)
        print(msg, flush=True)
        try:
            with open(prog, "a") as f:
                f.write(msg + "\n")
        except OSError:
            pass
    with resources.heavy(f"export {name}", kind="export_asset", model=name, log=waiting,
                         gb=asset_budget.export_gb(store.load(name), name)):
        from . import faceshapes
        notes = []
        with faceshapes.character_fits(store.load(name), notes, store._dir(name)):  # per-character fits from the spec, not the env
            for m in notes:
                waiting(m)
            res = asset_export._export(name, out_dir, *args, **kw)
        if isinstance(res, dict) and isinstance(res.get("log"), list):
            res["log"][:0] = notes
        return res


CLOTH_BUDGET_ROUNDS = 4  # decimation rounds to bring the garments under cloth_triangles

ROLE_HAIR_TIER = {"hero": "hero", "main_npc": "main", "secondary_npc": "npc", "crowd": "far"}  # LOD0 card tier by role


HEAD_KEEP_FROM_BUILD = ("attach",)  # base.head keys the build keeps over the approved head's (how it joins the body)

# The GAME rig as blender_game.light_rig(None) builds it, in blender_scene's "lighting" format (world colour sRGB): a stage
# render meant to be compared with the shipped GLB's game render must use THIS, view transform included. (Garrett s12:
# the stage's "game" frames used AgX while blender_game renders Khronos PBR Neutral (since 2026-10-16): the GLB read
# lighter and ~2x yellower (cheek b* 8.6 -> 15.0, forehead L* 68 -> 79) and its lid band ~10 L* darker, all of it the
# view transform; with the same view the GLB matched the stage within ~1 L* / 1 b* (photo light: 80.7 vs 80.8).)
GAME_LIGHT = {"lights": [{"dir": [-1.0, -1.2, 1.4], "energy": 3.0, "angle": 2.0, "color": [1.0, 1.0, 1.0]},
                         {"dir": [1.4, -0.6, 0.6], "energy": 1.0, "angle": 10.0, "color": [1.0, 1.0, 1.0]},
                         {"dir": [0.3, 1.5, 1.0], "energy": 1.5, "angle": 3.0, "color": [1.0, 1.0, 1.0]}],
              "world": {"color": [0.584, 0.600, 0.631], "strength": 0.8}, "view": "Khronos PBR Neutral", "exposure": 0.0}
FACE_LIGHT_TOL = {"lid-cheek": 5.0, "under-cheek": 3.0}  # L* (CIE) the shipped head may differ from the approved stage render
FACE_LIGHT_TEX_RATIO = 1.4  # forehead fine-texture (high-pass L* std) the shipped head may have over the approved render

FOLD_FORM_MAX_MM = 1.0  # (coordinator, Garrett s8) skin.folds up to this much relief are SKIN detail (grooves, creases);
# more (a roll / bag / cheek mass, a lid's overhang) changes the head's FORM: head geometry, Joe's approval


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("asset_budget", "asset_parts", "asset_split", "asset_hidden", "asset_raster", "asset_bake",
           "asset_quality", "asset_scene", "asset_glb", "asset_gates", "asset_export", "asset_export_parts",
           "asset_export_wear", "asset_export_rig", "asset_export_lods", "asset_export_finish")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C427)
