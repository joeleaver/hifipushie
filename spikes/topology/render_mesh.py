"""render_mesh.py out.png a.npz [b.npz ...]: front / side / 3-quarter / shoulder close-up, wire, one row per mesh"""
import json, subprocess, sys
import numpy as np
from PIL import Image
SP = "/tmp/claude-1000/-home-joe-dev-hifipushie/e7d4e711-ed61-4554-ae24-d3b25d4f287b/scratchpad"
out, meshes = sys.argv[1], sys.argv[2:]
rows = []
for i, m in enumerate(meshes):
    V = np.load(m)["verts"]; c = 0.5 * (V.min(0) + V.max(0)); h = (V.max(0) - V.min(0)).max() * 1.1
    sh = V[np.argmax(V[:, 0] - 3 * np.abs(V[:, 2] - (V[:, 2].min() + 0.75 * (V[:, 2].max() - V[:, 2].min()))))]
    views = [("front", [0, -1, 0], c, h), ("side", [1, 0, 0], c, h), ("tq", [0.6, -1, 0.3], c, h),
             ("face", [0.2, -1, 0.1], [c[0], V[:, 1].min() + 0.1 * h, V[:, 2].max() - 0.12 * h], 0.3 * h)]
    vs = [{"dir": d, "up": [0, 0, 1], "center": list(map(float, cc)), "scale": float(sc), "wire": True, "out": f"{SP}/rm_{i}_{n}.png"} for n, d, cc, sc in views]
    json.dump({"mode": "render", "mesh": m, "views": vs, "size": 450}, open(f"{SP}/rm.json", "w"))
    subprocess.run(["blender", "-b", "--factory-startup", "--python", f"{SP}/topo_blender.py", "--", f"{SP}/rm.json"], capture_output=True)
    row = Image.new("RGB", (1800, 450)); [row.paste(Image.open(v["out"]), (450 * k, 0)) for k, v in enumerate(vs)]; rows.append(row)
im = Image.new("RGB", (1800, 450 * len(rows))); [im.paste(r, (0, 450 * k)) for k, r in enumerate(rows)]; im.save(out); print(out)
