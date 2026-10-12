"""section.py <model> <folds.json | -> [fold names..]: the displacement each fold really makes, read off the field.
Points on the FOLD-FREE skin across each path (every 0.5 mm, +-12 mm, at 5 stations): the folded field's value there
is minus the skin's move along its normal. Prints the profile in mm (+ = out)."""
import json, os, sys
import numpy as np
from hifipushie import store, sdf, images, skin_folds as sf
from hifipushie.spec import expand_mirror

name, folds = sys.argv[1:3]
want = sys.argv[3:]
spec = store.load(name)
if folds != "-":
    spec["skin"] = {**{k: v for k, v in (spec.get("skin") or {}).items() if k != "folds"},
                    "folds": json.load(open(folds)) if os.path.exists(folds) else json.loads(folds)}
part = (spec.get("skin") or {}).get("part", "body")
J = {k: np.asarray(v["pos"], float) for k, v in expand_mirror(spec)["joints"].items() if "pos" in v}
S = sf.surface(spec, part, J)
prims = images.prims_on(spec, [part])
cfg = sf.options(spec["skin"]["folds"])
ps = sf.paths(spec, part, J, cfg)
u = np.arange(-12, 12.01, 1.0)
for (nm, sd), q in ps.items():
    if want and nm not in want:
        continue
    print(f"{nm}{sd}: {len(q['P'])} stations, amount max {q['amount'].max():.2f}; across mm: " + " ".join(f"{x:5.0f}" for x in u))
    for i in np.linspace(0, len(q["P"]) - 1, 5).astype(int):
        X = S.seat(q["P"][i] + 0.001 * u[:, None] * q["across"][i])
        d = -sdf.field_at(prims, X) * 1000
        print(f"   t {q['t'][i]:.2f} amount {q['amount'][i]:.2f}            " + " ".join(f"{x:5.2f}" for x in d))
