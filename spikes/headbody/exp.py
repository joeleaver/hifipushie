"""exp.py <model> <out dir> [json kwargs]: export_asset (rig, face shapes) and what the GLB holds (meshes, seam)."""
import json, sys, time
from pathlib import Path
from hifipushie import asset
name, out = sys.argv[1], Path(sys.argv[2])
kw = {"triangles": 30000, "texture": 1024, "rig": True, "fbx": False, "face_shapes": True}
kw.update(json.loads(sys.argv[3]) if len(sys.argv) > 3 else {})
t = time.time()
out.mkdir(parents=True, exist_ok=True)
r = asset.export(name, out, kw.pop("triangles"), kw.pop("texture"), 256, 1, None, True, kw.pop("rig"), kw.pop("fbx"), kw.pop("face_shapes") or None)
for line in r.get("log", []):
    if any(k in line for k in ("WARNING", "two meshes", "wrapped", "rig", "face shape", "seam")):
        print("LOG", line[:500])
print("seconds", round(time.time() - t), {k: v for k, v in r.items() if k in ("glb", "triangles")})
