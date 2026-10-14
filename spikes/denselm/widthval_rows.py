"""widthval_rows.py: adds to width_rows.json the jaw width (mm from `mean`, the same row) of every class mean the stage-1
generator draws identities around (gen2.identity: blockin.data()'s eth_means[sex, eth]) and of their POOLED mean, so
widthval.py (torch venv, no hifipushie) can ask whether the network shrinks toward the pooled mean or the class mean."""
import json
from pathlib import Path

import numpy as np

from hifipushie import blockin as bi

p = Path(__file__).parent / "width_rows.json"
R = json.loads(p.read_text())
D = bi.data()
en = [str(x) for x in D["eth_names"]]
mean, jw = np.array(R["mean"]), np.array(R["jaw_width"])
M = np.asarray(D["eth_means"], float)
R["class_jaw"] = {f"{int(s)}|{e}": float((M[s, k] - mean) @ jw) for s in (0, 1) for k, e in enumerate(en)}
R["pooled_jaw"] = float((M.reshape(-1, M.shape[-1]).mean(0) - mean) @ jw)
p.write_text(json.dumps(R))
print(R["class_jaw"], R["pooled_jaw"])
