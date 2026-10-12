import sys, pathlib, tempfile
import numpy as np
sys.path.insert(0, "tests")
from hifipushie import skin, skin_folds as sf, skin_marks as sm, store
from test_skin import head_spec
store.HOME = pathlib.Path(tempfile.mkdtemp())
spec = head_spec(age=30, folds={"nasolabial": {"amount": 1.0, "L": {"shift": [3.0] * 5}}, "tear_trough": 0.8}, fold_relief="paint")
J = skin._joints(spec)
cfg = sf.options(spec["skin"]["folds"])
ps = sf.paths(spec, "body", J, cfg)
S = sf.map_surface(spec, "body", J)
for k, q in ps.items():
    x = sm.pix(S.sp, q["P"])
    d = S._tree.query(q["P"])[0] * 1000
    print(k, len(q["P"]), "amount", q["amount"].max(), "pix", np.nanmin(x, 0), np.nanmax(x, 0), "W H", S.sp["W"], S.sp["H"], "dist to mesh mm", d.min(), d.max(),
          "P", q["P"][0].round(4), q["P"][-1].round(4))
print(sf.fold_map(spec, "body", J, cfg)[2])
