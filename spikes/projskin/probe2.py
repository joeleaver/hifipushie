"""probe2.py <model>: the atlas + raw projection of each view, written as PNGs (debug)."""
import sys, time, numpy as np
from PIL import Image
from hifipushie import blockin as bi, store, likeness as lk, skin_project as sp, humanfit
from hifipushie import blockin_expression, blockin_models, likeness_render, skin_project_atlas, skin_project_sample
m = sys.argv[1]; out = "/mnt/data/hifipushie/projskin/out/" + m; import os; os.makedirs(out, exist_ok=True)
spec = store.load(m); rj = blockin_models._refs(m)
t = time.time(); at = skin_project_atlas.atlas(spec["base"]); print("atlas", at["shape"], "valid", len(at["ii"]), "mm/texel", round(at["mm"], 3), "tris", len(at["T"]), f"{time.time()-t:.1f}s", "box", at["box"])
print("new verts", at["is_new"].sum(), "head verts", at["head"].sum())
VI = range(len(rj["views"]))
meshes = blockin_expression._per_view(spec["base"], rj, VI, lambda b: likeness_render.model_mesh(b))
for vi in VI:
    t = time.time()
    ph = np.asarray(Image.open(rj["views"][vi]["image"]).convert("RGB"))
    s = skin_project_sample.sample_view(at, meshes[vi], rj["cameras"][vi], ph)
    c = np.clip(sp._sstep((s["facing"] - sp.FACE[0]) / (sp.FACE[1] - sp.FACE[0])) * s["vis"], 0, 1)
    img = skin_project_atlas.image(at, np.c_[sp._srgb(s["rgb"]) * 255, c * 255].astype(np.uint8))
    Image.fromarray(img, "RGBA").save(f"{out}/raw_v{vi}.png")
    print("view", vi, "seen", round(s["vis"].mean(), 3), "conf>0.5", round((c > 0.5).mean(), 3), "mm/px", round(s["mm"], 3), f"{time.time()-t:.1f}s")
