"""Runs inside headless Blender: the exported GLB as FBX, the usual way into Unity and Unreal for skinned meshes.

blender -b --factory-startup --python blender_fbx.py -- in.glb out.fbx
Imported with Blender's glTF importer (bones pointed along their chains) and written with the settings the engines
expect: no leaf bones (Mixamo's *_End joints are already there), Y primary / X secondary bone axes, textures
embedded, metres (unit scale 1, applied), -Z forward / Y up.
"""

import sys

import bpy

src, dst = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src, bone_heuristic="TEMPERANCE")
for ob in list(bpy.data.objects):  # the importer's bone display shape
    if ob.type == "MESH" and ob.name.startswith("Icosphere") and not ob.data.materials:
        bpy.data.objects.remove(ob)
bpy.ops.export_scene.fbx(filepath=dst, path_mode="COPY", embed_textures=True, add_leaf_bones=False,
                         primary_bone_axis="Y", secondary_bone_axis="X", apply_scale_options="FBX_SCALE_UNITS",
                         axis_forward="-Z", axis_up="Y", use_mesh_modifiers=False, mesh_smooth_type="FACE",
                         use_tspace=True)
