"""mkgen.py: generic scratch heads on Tess's refs / cameras (from tn_T00): GNM's overall mean (tg_mean), the male class
mean (tg_male), two random heads from the prior (tg_r1, tg_r2: |c| ~ 10)."""
import copy, json, shutil
import numpy as np
from hifipushie import blockin as bi, store
sp0 = store.load("tn_T00"); D = bi.data()
rng = np.random.default_rng(7)
r = [rng.standard_normal(170) for _ in range(2)]
for name, c in (("tg_mean", np.zeros(170)), ("tg_male", np.asarray(D["m_m"], float)), ("tg_r1", 10 * r[0] / np.linalg.norm(r[0])), ("tg_r2", 10 * r[1] / np.linalg.norm(r[1]))):
    sp = copy.deepcopy(sp0); bi.set_identity(sp, c)
    d = store._dir(name); d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(sp)); shutil.copy(store._dir("tn_T00") / "human_refs.json", d / "human_refs.json")
    print(name, round(float(np.linalg.norm(c)), 1))
