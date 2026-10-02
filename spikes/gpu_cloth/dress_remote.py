"""A garment dressed end to end through the "remote" backend (cloth.build -> cloth_job -> $HIFIPUSHIE_CLOTH_REMOTE),
coarse sim + fine refine as hifipushie runs them, then the usual report.

    HIFIPUSHIE_HOME=... HIFIPUSHIE_CLOTH_REMOTE="spikes/gpu_cloth/remote.sh" \
        uv run python spikes/gpu_cloth/dress_remote.py <model> <garment> [key=json ...]

For a local check: HIFIPUSHIE_CLOTH_REMOTE="<venv>/bin/python spikes/gpu_cloth/run_newton.py --device cpu"."""
import json
import sys
import time

from hifipushie import cloth, store

model, gname = sys.argv[1], sys.argv[2]
spec = store.load(model)
g = dict(spec["cloth"][gname], backend="remote")
for kv in sys.argv[3:]:
    k, v = kv.split("=", 1)
    g[k] = json.loads(v)
t = time.time()
res = cloth.build(cloth._garment_for_sim(g), cloth.model_body(model, spec, g), f"{model}:{gname}", log=print,
                  progress=lambda s: print("  ", s, flush=True))
print(f"dressed in {time.time() - t:.0f} s")
print(cloth.report(gname, res))
