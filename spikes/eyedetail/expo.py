"""expo.py <model> <out dir>: a small export_asset (20k triangles, 512 maps, rigged, a few face shapes) to check the
lashes go out: their part, triangles, two-sided material, rig weights and blink targets."""
import json
import sys
import time
from pathlib import Path

from hifipushie import asset

name, out = sys.argv[1], Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
t = time.time()
r = asset.export(name, out, triangles=20000, texture=512, rig=True,
                 face_shapes=["eyeBlinkLeft", "eyeBlinkRight", "eyeWideLeft", "eyeLookUpLeft", "jawOpen"])
print(f"{time.time() - t:.0f} s")
for ln in r.get("log", []):
    if "lash" in ln.lower() or "WARNING" in ln or "face shapes:" in ln:
        print(" ", ln)
rep = r.get("report") or r.get("parts") or {}
print(json.dumps({k: v for k, v in rep.items() if "lash" in k or k in ("body", "eyes")}, default=str)[:1500])
gl = list(out.glob("*.glb"))
print("glb", gl)
if gl:
    g = json.loads(open(gl[0], "rb").read()[20:20 + int.from_bytes(open(gl[0], "rb").read()[12:16], "little")])
    for m in g["materials"]:
        if "lash" in m["name"] or "eye" in m["name"]:
            print("material", m["name"], m.get("doubleSided"), list(m.get("extensions", {})))
    for me in g["meshes"]:
        if "lash" in me["name"]:
            print("mesh", me["name"], (me.get("extras") or {}).get("targetNames"))
