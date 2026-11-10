"""wire.py out.png a.npz [b.npz ...]: hips close-up front / side / back / below, wire, one row per mesh (verts/loops/sizes)."""
import json, subprocess, sys, os
from PIL import Image
D = os.environ.get("WIRE_TMP", "/mnt/data/hifipushie/flesh_weights/tmp"); os.makedirs(D, exist_ok=True)
TB = os.path.expanduser("~/dev/hifipushie/.claude/worktrees/limb-loops/spikes/topology/topo_blender.py")
out, meshes = sys.argv[1], sys.argv[2:]
c = [float(x) for x in os.environ.get("CENTER", "0,0,0.13").split(",")]; sc = float(os.environ.get("SCALE", "0.38"))
views = [(n, d) for n, d in [x.split(":") and (x.split(":")[0], [float(v) for v in x.split(":")[1].split("/")]) for x in os.environ.get("VIEWS", "front:0/-1/0,side:1/0/0,tq:0.7/-1/0.25,below:0.25/-0.5/-1").split(",")]]
rows = []
for i, m in enumerate(meshes):
    vs = [{"dir": d, "up": [0, 0, 1] if n != "below" else [0, 1, 0], "center": c, "scale": sc, "wire": os.environ.get("WIRE", "1") == "1", "out": f"{D}/w_{i}_{n}.png"} for n, d in views]
    json.dump({"mode": "render", "mesh": m, "views": vs, "size": 450}, open(f"{D}/w.json", "w"))
    r = subprocess.run(["blender", "-b", "--factory-startup", "--python", TB, "--", f"{D}/w.json"], capture_output=True, text=True)
    if r.returncode: print(r.stderr[-800:])
    row = Image.new("RGB", (1800, 450)); [row.paste(Image.open(v["out"]), (450 * k, 0)) for k, v in enumerate(vs)]; rows.append(row)
im = Image.new("RGB", (1800, 450 * len(rows))); [im.paste(r, (0, 450 * k)) for k, r in enumerate(rows)]; im.save(out); print(out)
