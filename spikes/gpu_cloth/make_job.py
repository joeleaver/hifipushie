"""Write a garment's solver-neutral cloth job (cloth_job.py) without running it.
uv run python spikes/gpu_cloth/make_job.py <model> <garment> <out_dir> [resolution m] [key=json ...]
The garment is sim'd directly at `resolution` (coarse = resolution, quality draft: no coarse->fine refine).
Needs HIFIPUSHIE_HOME (the workspace with the model)."""
import json
import os
import sys
from pathlib import Path

os.environ["HIFIPUSHIE_CLOTH_WAIT"] = "0"
from hifipushie import cloth, store  # noqa: E402

model, gname, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
h = float(sys.argv[4]) if len(sys.argv) > 4 else 0.01
spec = store.load(model)
g = dict(spec["cloth"][gname])
g.update(resolution=h, coarse=h, quality="draft", backend="file")
for kv in sys.argv[5:]:
    k, v = kv.split("=", 1)
    g[k] = json.loads(v)
src = cloth.model_body(model, spec, g)
try:
    cloth.build(cloth._garment_for_sim(g), src, f"{model}:{gname}", out_dir=out)
except RuntimeError as e:
    print("written:", e)
