"""Cut the harmonic-field loops on the rest high mesh and render them (no QuadriFlow)."""
import json, os, subprocess, sys
import numpy as np
from PIL import Image
import topo_eval as E, topo_iso as I
OUT = E.SP / os.environ.get("TAG", "isoprev"); OUT.mkdir(exist_ok=True)
labels = os.environ.get("JOINTS", "L shoulder,L elbow").split(",")
levels = tuple(float(x) for x in os.environ.get("LEVELS", "0.5").split(","))
lo, hi = (float(x) for x in os.environ.get("LOHI", "0.1,0.9").split(","))
flds = I.fields(E.HV, E.HF, labels, lo, hi)
V, F, ids, names, _ = I.cut_loops(E.HV, E.HF, flds, levels)
e = E.edges_of(F); e = e[(ids[e[:, 0]] >= 0) & (ids[e[:, 0]] == ids[e[:, 1]])]
rings = []
for k in np.unique(ids[ids >= 0]):
    ek = e[ids[e[:, 0]] == k]; nb = {}
    for a, b in ek: nb.setdefault(a, []).append(b); nb.setdefault(b, []).append(a)
    start = ek[0, 0]; path = [start]; prev = None; cur = start
    while True:
        nxt = [x for x in nb[cur] if x != prev]
        if not nxt or nxt[0] == start: break
        prev, cur = cur, nxt[0]; path.append(cur)
    rings.append(V[path].tolist())
np.savez(OUT / "rest.npz", verts=V, loops=F.ravel(), sizes=np.full(len(F), 3))
c = [0.2, 0, 0.62]
views = [{"dir": d, "up": u, "center": c, "scale": 0.45, "wire": False, "out": str(OUT / f"{n}.png")}
         for n, d, u in (("front", [0, -1, 0], [0, 0, 1]), ("side", [1, 0, 0], [0, 0, 1]), ("back", [0, 1, 0], [0, 0, 1]),
                         ("top", [0.3, -0.4, 1], [0, 1, 0]))]
json.dump({"mode": "render", "mesh": str(OUT / "rest.npz"), "views": views, "size": 400, "rings": rings,
           "ring_width": 0.002}, open(OUT / "job.json", "w"))
subprocess.run(["blender", "-b", "--factory-startup", "--python", str(E.SP / "topo_blender.py"), "--", str(OUT / "job.json")],
               capture_output=True)
im = Image.new("RGB", (1600, 400)); [im.paste(Image.open(v["out"]), (400 * i, 0)) for i, v in enumerate(views)]
im.save(OUT / "loops.png")
