"""Apply a cloth result to its garment exactly as hifipushie applies any sim (clean-up, fit, integrity, report) and
render it: the result comes in through the "remote" backend (a command that copies out.npz into the job folder).

uv run python spikes/gpu_cloth/evaluate.py <model> <garment> <resolution m> <out.npz | "blender"> <render prefix>
    [key=json ...]
"blender" runs Blender's sim (cached like any dress) at the same direct resolution, for the side by side.
Prints the report and a JSON line of the numbers; writes <prefix>.png (front/side/back/three + strain).
Needs HIFIPUSHIE_HOME."""
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

from hifipushie import cloth, store

model, gname, h, result, prefix = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4], Path(sys.argv[5])
spec = store.load(model)
g = dict(spec["cloth"][gname])
g.update(resolution=h, coarse=h, quality="draft")
for kv in sys.argv[6:]:
    k, v = kv.split("=", 1)
    g[k] = json.loads(v)
if result != "blender":
    tmp = Path(tempfile.mkdtemp(prefix="gpucloth_"))
    src = Path(result).resolve()
    (tmp / "out.npz").write_bytes(src.read_bytes())
    os.environ["HIFIPUSHIE_CLOTH_REMOTE"] = f"cp {tmp / 'out.npz'}"
    g["backend"] = "remote"
    g["note"] = f"result {src}"  # NOT_SIM: kept out of the key; the key below differs per result instead
    os.environ["HIFIPUSHIE_CLOTH_SOLVER"] = f"newton:{src}:{src.stat().st_mtime}"
src_body = cloth.model_body(model, spec, g)
res = cloth.build(cloth._garment_for_sim(g), src_body, f"{model}:{gname}", log=print)
print(cloth.report(gname, res))
ig = res["integrity"]
nums = {"crossings": ig["self_intersections"], "crossings_sim": ig["sim"]["self_intersections"],
        "crumpled": {p: round(v["crumpled"], 3) for p, v in ig["pieces"].items() if v["crumpled"] > 0.005},
        "corrupt": ig["corrupt_pieces"], "shape": res["shape"], "verdict": res["fit"]["verdict"],
        "strain_p95": res["fit"]["strain_p95"], "verts": len(res["mesh"]["uv"])}
print("NUMBERS", json.dumps(nums, default=str))
# render: body (or rack) + garment, and the strain row
from PIL import Image  # noqa: E402

objs = []
st = cloth._state(g)
if isinstance(st, dict) and "hang" in st:
    for k, (a, b, r) in enumerate(st["hang"].get("rack") or []):
        V, F = cloth._cylinder(a, b, r)
        objs.append({"name": f"rack{k}", "V": V, "F": F, "color": "#8a6b45"})
else:
    objs.append({"name": "body", "V": res["body"].V, "F": res["body"].T, "color": "#d9c3b0"})
objs.append({"name": "g", "V": res["V"], "F": res["mesh"]["F"], "color": g.get("color", "#8fb3d9"),
             "thickness": max(0.0006, cloth.fabric(g).get("thickness", 0.0008))})
allV = np.concatenate([o["V"] for o in objs])
box = (allV.min(0) - 0.05, allV.max(0) + 0.05)
if "body" in [o["name"] for o in objs]:  # the garment's own height, not the whole body
    Vg = res["V"]
    box = (np.r_[allV.min(0)[:2], Vg[:, 2].min()] - 0.05, np.r_[allV.max(0)[:2], Vg[:, 2].max()] + 0.05)
ext = box[1] - box[0]
aspect = float(np.clip(max(ext[0], ext[1]) / ext[2], 0.62, 1.8))
vs = ["front", "side", "back", {"name": "three", "dir": [-0.65, -0.72, 0.25]}]
prefix.parent.mkdir(parents=True, exist_ok=True)
paths = cloth.render(objs, str(prefix) + "_r", views=vs, resolution=640, box=box, aspect=aspect)
so = [dict(o, C=cloth.strain_colors(res["fit"]["vertex_strain"], res["fabric"]["limit"])) if o["name"] == "g" else o
      for o in objs]
sp = cloth.render(so, str(prefix) + "_s", views=["front", "back"], resolution=640, box=box, aspect=aspect)
ims = [Image.open(p).convert("RGB") for p in paths + sp]
W = sum(i.width for i in ims[:4])
sheet = Image.new("RGB", (W, ims[0].height * 2), (60, 60, 60))
for k, im in enumerate(ims):
    sheet.paste(im, ((k % 4) * im.width, (k // 4) * im.height))
sheet.save(str(prefix) + ".png")
for p in paths + sp:
    Path(p).unlink(missing_ok=True)
np.savez_compressed(str(prefix) + "_mesh.npz", V=res["V"], V_sim=res["V_sim"], F=res["mesh"]["F"])
print("wrote", str(prefix) + ".png")
