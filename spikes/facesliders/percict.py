"""percict.py: perc.py's perceptual effect (1 - cos SFace, -1 vs +1 sd, heads mean / tess / garrett, views 0 / -30 / 30)
for ICT's 100 carried modes (faces5: the checklist coverage ranks every direction by it). Writes out/perc/perc_ict.json
{ict_NN: effect}."""
import json
import os
from pathlib import Path

import numpy as np

import perc

F = Path(os.environ.get("F", "/mnt/data/hifipushie/faces5"))
M = np.load(F / "out" / "ict_modes.npz")["modes"].astype(float)
heads = {h: perc.head(h) for h in ("mean", "tess", "garrett")}
out = {}
for k in range(len(M)):
    D = M[k]
    r = perc.measure(f"ict_{k:02d}", lambda c, D=D: perc.verts(c, D=D), lambda c, D=D: perc.verts(c, D=-D), heads)
    out[f"ict_{k:02d}"] = r["id"]["sface"]
    print(k, round(out[f"ict_{k:02d}"], 4), r["mm"], flush=True)
(F / "out" / "perc" / "perc_ict.json").write_text(json.dumps(out))
