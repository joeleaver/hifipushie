"""exportcheck.py <model with a skin projection> <out dir>: does the projection go through export_asset's bake? The model's
head stage (bare skin + eyes, no hair) is saved as its own model ps_exp_<model> and exported (GLB + maps, 2048, no
preview); prints the albedo map's statistics on the face so a missing projection shows (a flat tone has no brows).
HEAVY (asset.export takes resources.heavy itself: run through bin/capped, not heavy.sh)."""
import json, sys
import numpy as np
from PIL import Image
import stage
from hifipushie import asset, store
from pathlib import Path
m, out = sys.argv[1:3]
sn = stage.ensure(m, with_hair=False)
st = json.loads((store._dir(sn) / "spec.json").read_text())
st.pop("hair", None)
dst = "ps_exp_" + m
store.save(dst, st, f"export check of {m}'s head stage", checked=False)
info = asset.export(dst, Path(out), 20000, 2048, 256, 1, None, True, False, False, None)
print(json.dumps({k: v for k, v in info.items() if k in ("glb", "triangles", "seconds")}, default=str))
for a in info["atlases"].values():
    for k, f in a["maps"].items():
        if not Path(f).exists():
            continue
        im = np.asarray(Image.open(f).convert("RGB"), float)
        print(k, Path(f).name, im.shape, "mean", im.reshape(-1, 3).mean(0).round(1), "std", im.reshape(-1, 3).std(0).round(1))
print("\n".join(info["log"][-12:]))
