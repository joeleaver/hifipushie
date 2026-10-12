"""export_check.py <model> <tag> [triangles=20000] [texture=2048]: what the GAME ASSET keeps of skin.folds.
The model's head stage (skin_read.stage_spec: bare head + eyes) is exported twice, with its folds and without, at the
same budget (export_asset: low poly, unique normal / AO / colour maps, GLB), and previewed (Cycles, the GLB as a game
would draw it). Printed: each export's per-part quality (the low poly's distance to the exact field), and how far the
two low polys differ where the folds are (the share of the relief that is GEOMETRY in the asset; the rest is in the
normal map, which is baked from the exact field)."""
import json, os, sys, time
from pathlib import Path
import numpy as np
from hifipushie import asset, render, skin_read as sr, store

model, tag = sys.argv[1:3]
kw = dict(a.split("=") for a in sys.argv[3:])
G = os.environ["G"] + "/out"
spec = store.load(model)
for label in ("folds", "nofolds"):
    st = sr.stage_spec(spec)
    if label == "nofolds":
        st["skin"] = {k: v for k, v in st["skin"].items() if k != "folds"}
    name = f"sf_x_{tag}_{label}"
    d = store._dir(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(st))
    out = Path(f"{G}/export_{tag}_{label}")
    t = time.time()
    info = asset.export(name, out, int(kw.get("triangles", 20000)), int(kw.get("texture", 2048)), 256, 1, None, True, False, False, None)
    print(f"== {label}: {info['glb']} {info['triangles']} triangles, height range +-{info['height_range_m'] * 1000:.2f} mm, {time.time() - t:.0f} s")
    for ln in info["log"]:
        if "quality" in ln or "error" in ln or "body" in ln:
            print("   ", ln[:300])
    im = asset.preview(Path(info["glb"]), render.DEFAULT_VIEWS)
    data = im.data if hasattr(im, "data") else im
    open(f"{G}/export_{tag}_{label}_preview.png", "wb").write(data)
    print("   preview", f"{G}/export_{tag}_{label}_preview.png")
