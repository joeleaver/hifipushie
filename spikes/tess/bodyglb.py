"""bodyglb.py <model> <out glb>: the model's built mesh (all parts but hair) as a GLB in glTF axes (Y up), grey,
for look2.gd's body (so the cards are seen over a head, not through it)."""
import sys, tempfile
from pathlib import Path

import numpy as np

from hifipushie import server

name, out = sys.argv[1], sys.argv[2]
with tempfile.TemporaryDirectory() as d:
    p = str(Path(d) / "b.obj")
    print(server.export(name, p, 220))
    V, F = [], []
    for ln in open(p):
        if ln.startswith("v "):
            V.append([float(x) for x in ln.split()[1:4]])
        elif ln.startswith("f "):
            idx = [int(x.split("/")[0]) - 1 for x in ln.split()[1:]]
            for k in range(1, len(idx) - 1):
                F.append([idx[0], idx[k], idx[k + 1]])
V = np.asarray(V, float)
V = np.c_[V[:, 0], V[:, 2], -V[:, 1]]
import json, struct
F = np.asarray(F, np.uint32)
pos = V.astype(np.float32).tobytes()
ind = F.astype(np.uint32).tobytes()
buf = pos + ind
gl = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": "body"}],
      "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
      "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [0.75, 0.6, 0.52, 1], "metallicFactor": 0, "roughnessFactor": 0.6}}],
      "buffers": [{"byteLength": len(buf)}],
      "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pos), "target": 34962},
                      {"buffer": 0, "byteOffset": len(pos), "byteLength": len(ind), "target": 34963}],
      "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(V), "type": "VEC3",
                     "min": V.min(0).tolist(), "max": V.max(0).tolist()},
                    {"bufferView": 1, "componentType": 5125, "count": int(F.size), "type": "SCALAR"}]}
js = json.dumps(gl).encode()
js += b" " * (-len(js) % 4)
buf += b"\0" * (-len(buf) % 4)
with open(out, "wb") as fh:
    fh.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(buf)))
    fh.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
    fh.write(struct.pack("<II", len(buf), 0x004E4942) + buf)
print("saved", out, len(V), len(F))
