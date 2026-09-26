# Template: Blender Studio "Human Base Meshes" v1.4.1 (CC0)

From blender.org Demo Files → Asset Bundles (human-base-meshes-bundle-v1.4.1.zip, 49 MB). Not in the repo:

    blender -b human_base_meshes_bundle.blend --python hbm_export.py -- GEO-body_male_stylized male_stylized.npz

then re-centre it (x on 0, feet at z = 0: `verts[:, 0] -= (min + max) / 2; verts[:, 2] -= min`). Used as-is: 12,502 vertices,
12,500 quads, A-pose, facing -Y. `male_stylized_joints.json`: its skeleton, measured from cross-sections (leg and arm
centrelines, narrowest points at knee, ankle, wrist; checked by an x-ray render). `male_stylized_face.json`: face landmarks
(eye centres from the eye objects, `hbm_eyes.py`; nose tip and mouth line from the midline profile; ear tips) and anchors.
