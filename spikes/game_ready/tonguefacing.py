"""tonguevis.py <dump.pkl> <glb> <out prefix> [CONST=value ...] [-- pose ...]: how the visible tongue FACES the camera (-n.y of its posed normals), not its
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
W = mouthhits.SH[poses[0]]
Vp = V + sum(float(w) * g["meshes"]["tongue"]["targets"][k] for k, w in W.items() if k in g["meshes"]["tongue"]["targets"])
N = fs.vertex_normals(Vp, F); fac = np.clip(-N[:, 1], 0, 1); upz = np.clip(N[:, 2], 0, 1)
UVF["tongue"] = np.stack([fac[F], np.full(F.shape, 0.5)], -1)
TEX["tongue"] = np.repeat(np.arange(256, dtype=np.uint8)[None, :, None], 4, 0).repeat(3, 2)
mouthhits.measure(g, UVF, TEX, out, poses)
for pose in poses[:1]:
    idm = np.asarray(Image.open(f"{out}_{pose}_id.png")); alb = np.asarray(Image.open(f"{out}_{pose}_alb.png"))
    tg = (idm == [240, 120, 160]).all(-1); op = ~(idm == [220, 190, 170]).all(-1)
    f = alb[..., 0][tg] / 255; rows = np.where(op.any(1))[0]
    prof = [f"{(alb[r, :, 0][tg[r]] / 255).mean():.2f}" if tg[r].sum() > 20 else "-" for r in range(rows.min(), rows.max() + 1, 8)]
    print(f"{pose}: tongue share {tg.sum() / op.sum():.3f}; facing the camera (-n.y) p25/50/75 {np.percentile(f, [25, 50, 75]).round(2)}; down the opening (every 2 mm): {' '.join(prof)}")
