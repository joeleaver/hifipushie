"""apmeas.py <model> <stage model> ...: the part-ID aperture (aperture.measure) of each stage's scene through <model>'s
front reference camera (the front close-up box, as eyeshot.py), 1024 px. Prints per eye (picture left, right)."""
import json
import sys

import numpy as np

import stage
from hifipushie import aperture, scene, store
from hifipushie.spec import expand_mirror

name = sys.argv[1]
spec = store.load(name)
J = {k: np.asarray(v["pos"], float) for k, v in expand_mirror(spec)["joints"].items() if "pos" in v}
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
v, cam = refs["views"][0], refs["cameras"][0]
U = np.array(list(v["points"].values()), float)
lo, hi = U.min(0), U.max(0)
s = 0.95 * (hi - lo)[0]
c = np.array([0.5 * (lo[0] + hi[0]), lo[1] + 0.55 * (hi[1] - lo[1])])
fr = stage.fitted_frame(cam, [c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2], "id")
rows = {}
for st in sys.argv[2:]:
    r = aperture.measure(str(scene.blend_path(st)), fr, [J["eye.L"], J["eye.R"]], size=1024)
    rows[st] = r
    print(f"{st:>16}: " + "  |  ".join(" ".join(f"{k} {e[k]}" for k in e) for e in r))
if len(rows) > 1:
    a = list(rows.values())[0]
    for st, r in list(rows.items())[1:]:
        print(f"{st} - first: " + "  ".join(f"{k} {np.mean([e[k] for e in r]) - np.mean([e[k] for e in a]):+.2f}"
                                            for k in a[0]))
