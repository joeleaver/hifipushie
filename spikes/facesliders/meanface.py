"""meanface.py <base model> <out model> <sex>: the base with its identity set to the within-sex population mean
(sex * delta / 2; sliders cleared): what "an average woman / man" of GNM looks like on this body and camera."""
import json
import sys

import numpy as np

from hifipushie import faceatlas, humanfit, store

src, out, sex = sys.argv[1], sys.argv[2], float(sys.argv[3])
sp = json.loads((store.HOME / src / "spec.json").read_text())
sp = sp.get("spec", sp)
mu = sex * np.asarray(faceatlas.table()["delta_sex"], float) / 2
sp["base"] = humanfit._with_identity(sp["base"], mu)
sp["base"]["head"]["sliders"] = {}
d = store.HOME / out
d.mkdir(exist_ok=True)
(d / "spec.json").write_text(json.dumps(sp, indent=1))
(d / "human_refs.json").write_text((store.HOME / src / "human_refs.json").read_text())
print("wrote", d)
