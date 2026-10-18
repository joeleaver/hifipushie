"""tonguevis.py <dump.pkl> <glb> <out prefix> [CONST=value ...] [-- pose ...]: which part of the tongue the front sees, in
REST depth behind its tip (what skin_features.TONGUE_BACK ramps on). shapesfast's apply, then mouthhits' flat pass with
the tongue's UVs replaced by its rest depth (u = depth / 100 mm on a gradient texture). Prints the visible tongue's
depth percentiles and the top-half pixels' share past each candidate ramp start."""
import copy, pickle, sys
import numpy as np
from PIL import Image
from hifipushie import faceshapes as fs
import mouthhits

dump, glb, out = sys.argv[1:4]; rest = sys.argv[4:]
poses = rest[rest.index("--") + 1:] if "--" in rest else ["jaw"]
for kv in (rest[:rest.index("--")] if "--" in rest else rest):
    k, v = kv.split("=", 1); old = getattr(fs, k)
    setattr(fs, k, tuple(float(x) for x in v.split(",")) if isinstance(old, tuple) else type(old)(float(v))); print(k, "->", getattr(fs, k))
d = pickle.load(open(dump, "rb")); parts = copy.deepcopy(d["parts"])
want = sorted({k for po in poses for k in mouthhits.SH[po]} | {"jawOpen"})
fs.apply(d["spec"], parts, [n for n in fs.names_of(d["face_shapes"]) if n in want], [])
_, _, TEX = mouthhits.load(glb)
g = {"meshes": {}}; UVF = {}
for pn in mouthhits.PARTS:
    p = parts[pn if pn in parts else {"head": "body"}[pn]]; F = np.asarray(p["corner_vert"]).reshape(-1, 3); V = np.asarray(p["verts"], float)
    g["meshes"][pn] = {"V": V, "F": F, "targets": {nm: np.asarray(x[0], float) for nm, x in p.get("shapes", {}).items()}}
    UVF[pn] = np.asarray(p["uv"], float).reshape(-1, 3, 2) * [1, -1] + [0, 1]
V = g["meshes"]["tongue"]["V"]; dep = (V[:, 1] - V[:, 1].min())  # rest depth behind the tip (Blender: face looks -y)
F = g["meshes"]["tongue"]["F"]
UVF["tongue"] = np.stack([dep[F] / 0.1, np.full(F.shape, 0.5)], -1)
TEX["tongue"] = np.repeat(np.arange(256, dtype=np.uint8)[None, :, None], 4, 0).repeat(3, 2)
print(f"tongue rest length {dep.max()*1e3:.1f} mm")
mouthhits.measure(g, UVF, TEX, out, poses)
for pose in poses:
    idm = np.asarray(Image.open(f"{out}_{pose}_id.png")); alb = np.asarray(Image.open(f"{out}_{pose}_alb.png"))
    tg = (idm == [240, 120, 160]).all(-1)
    if not tg.any():
        print(pose, "tongue not seen"); continue
    dd = alb[..., 0][tg] / 255 * 100; rows = np.where(tg.any(1))[0]; top = tg & (np.arange(tg.shape[0])[:, None] < rows.min() + (np.ptp(rows) + 1) / 2)
    print(f"{pose}: visible tongue rest depth mm p5/25/50/75/95 {np.percentile(dd, [5, 25, 50, 75, 95]).round(1)}; upper half median {np.median(alb[..., 0][top] / 255 * 100):.1f}")
    for s in (30, 35, 40, 45, 50, 55, 60):
        print(f"   share past {s} mm: {(dd > s).mean():.2f}")
