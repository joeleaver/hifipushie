"""export.py <model> <out dir> [triangles=20000] [texture=1024]: export_asset(face_shapes=True, rig=True) of a
GNM-native head's model and what the GLB then holds: per mesh the target names and how many move it, the teeth /
tongue / eyes parts, and jawOpen / tongueOut / eyeBlink checked on the decoded targets (the lower teeth drop with
jawOpen, the upper stay; the tongue passes the lips with tongueOut). Prints the export log's face-shape lines."""
import json
import sys
from pathlib import Path

import numpy as np

from hifipushie import asset, faceshapes

m, out = sys.argv[1], Path(sys.argv[2])
kw = dict(a.split("=", 1) for a in sys.argv[3:])
out.mkdir(parents=True, exist_ok=True)
r = asset.export(m, out, triangles=int(kw.get("triangles", 20000)), texture=int(kw.get("texture", 1024)), face_shapes=True,
                 rig=kw.get("rig", "1") == "1")
log = r.get("log") if isinstance(r, dict) else None
for line in (log or []):
    if "face shape" in line or "mouth" in line or "WARNING" in line or "teeth" in line or "tongue" in line:
        print("LOG", line[:400])
glb = next(out.glob("*.glb"))
g = faceshapes.read_glb(glb)
for mesh, d in g.items():
    names = d["names"]
    mv = {n: float(np.abs(d["targets"][n]).max()) for n in names} if "targets" in d else {}
    moved = [n for n, v in mv.items() if v > 1e-6]
    print(f"MESH {mesh}: {d.get('count')} vertices, {len(names)} targets, {len(moved)} move it; "
          + ", ".join(f"{n} {1000 * mv[n]:.1f} mm" for n in ("jawOpen", "tongueOut", "eyeBlinkLeft", "mouthSmileLeft", "eyeLookUpLeft") if n in mv))
print(json.dumps({k: v for k, v in (r if isinstance(r, dict) else {}).items() if k in ("triangles", "parts", "seconds", "glb")}, default=str)[:1500])
