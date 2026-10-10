"""lipdiag2.py <model>: lipfit's shadow directions, checked on the BUILT head: the raw proxy's predicted move vs the built
one's, and how much of the direction is identity vs habitual expression (the shadow hardly moved along directions the
raw proxy said moved the lip-over-sulcus step 2.4 mm per unit)."""
import json
import sys

import numpy as np

import lipfit as LF
import lipdiag as LD  # noqa: F401  (built_proxy)
from hifipushie import humanfit, humanfit_map as hm, store

spec = store.load(sys.argv[1])
refs = json.loads((store.HOME / sys.argv[1] / "human_refs.json").read_text())
views = [dict(v) for v in refs["views"]]
cams = [dict(cm) for cm in refs["cameras"]]
z0 = np.r_[humanfit.identity(spec["base"]), LF.h_of(spec)]
st = humanfit.state(LF.spec_with(spec, z0[:LF.NC], z0[LF.NC:])["base"])
rv = hm._resolve(st, views)
H, b, _, _ = LF.point_system(st, rv, cams, z0, z0)
Hp = H + LF.prior_inv()
p0, Jp = LF.proxy_jac(z0)
D = np.linalg.solve(Hp, Jp.T)
D /= np.sqrt(np.einsum("ij,jk,ki->i", D.T, Hp, D))[None, :]
LD.spec = spec
b0, s = LD.built_proxy(z0)
for j in range(2):
    d = D[:, j]
    print(f"dir {j}: |c part| {np.linalg.norm(d[:LF.NC]):.3f} |h part| {np.linalg.norm(d[LF.NC:]):.3f}; raw proxy per unit "
          f"{(Jp @ d * 1e3).round(3)} mm")
    for stp in (1.5, 5.0):
        b1, _ = LD.built_proxy(z0 + stp * d)
        print(f"   step {stp}: built proxy move {((b1 - b0) * 1e3).round(3)} mm (raw x scale {(Jp @ d * stp * s * 1e3).round(3)})")
