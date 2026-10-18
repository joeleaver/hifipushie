"""shapesfast.py <dump.pkl> <glb for textures> <out prefix> [CONST=value ...] [-- pose ...]: the face shapes rebuilt
from an export's HP_SHAPES_DUMP (the parts as faceshapes.apply gets them) with faceshapes constants overridden
(e.g. JAW_UPPER_LIFT=0.18,0.08 JAW_CORNER_OUT=0.09), then mouthhits + teethcount on them. Seconds, not a 14-min export.
Textures come from the GLB (shapes don't move UVs)."""
import copy, pickle, sys, time
import numpy as np
from hifipushie import faceshapes as fs
import mouthhits, teethcount

dump, glb, out = sys.argv[1:4]
rest = sys.argv[4:]
poses = rest[rest.index("--") + 1:] if "--" in rest else ["jaw", "smile", "smileteeth"]
consts = rest[:rest.index("--")] if "--" in rest else rest
for kv in consts:
    k, v = kv.split("=", 1)
    old = getattr(fs, k)
    val = tuple(float(x) for x in v.split(",")) if isinstance(old, tuple) else type(old)(float(v)) if not isinstance(old, bool) else v in ("1", "True")
    setattr(fs, k, val); print(f"{k}: {old} -> {val}")
d = pickle.load(open(dump, "rb"))
parts = copy.deepcopy(d["parts"]); log = []
print("parts:", list(parts))
want = sorted({k for po in poses for k in mouthhits.SH[po]} | {"jawOpen"})  # only the shapes measured
names = [n for n in fs.names_of(d["face_shapes"]) if n in want]
t = time.time()
fs.apply(d["spec"], parts, names, log)
print(f"apply {time.time() - t:.0f}s;", next((l for l in log if "closed lips' seam" in l), ""))
_, _, TEX = mouthhits.load(glb)
g = {"meshes": {}}; UVF = {}
ALIAS = {"head": "body"}  # the export splits the body's head off as its own mesh
for pn in mouthhits.PARTS:
    p = parts[ALIAS.get(pn, pn) if pn not in parts else pn]; F = np.asarray(p["corner_vert"]).reshape(-1, 3)
    V = np.asarray(p["verts"], float)
    g["meshes"][pn] = {"V": V, "F": F, "targets": {nm: np.asarray(x[0], float) for nm, x in p.get("shapes", {}).items()}}
    UVF[pn] = np.asarray(p["uv"], float).reshape(-1, 3, 2) * [1, -1] + [0, 1]  # (Blender UVs: v up; the GLB textures v down)
mouthhits.measure(g, UVF, TEX, out, poses)
teethcount.count(g, ["jawOpen", "1"])
