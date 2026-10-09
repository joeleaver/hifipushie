"""camdbg.py <model> ...: the stored reference cameras (focal, distance, yaw, rotation, centre) of models."""
import json
import sys

import numpy as np

from hifipushie import store

for n in sys.argv[1:]:
    r = json.loads((store.HOME / n / "human_refs.json").read_text())
    for i, c in enumerate(r["cameras"]):
        print(n, i, "f", round(c["f"], 1), "t", np.round(c["t"], 3).tolist(), "yaw", c.get("yaw"), "r", np.round(c["r"], 3).tolist(),
              "centre", np.round(c["centre"], 3).tolist(), "size", c["size"])
