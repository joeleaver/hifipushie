"""regtest.py: oracle closure (k <= 6) with the regional modes (reg:<region><k>, 8 per region) added to the vocabulary,
on fresh random transplants (seed 99) and the s1 cases."""
import json

import numpy as np

import drv
import pairs
import score

M = dict(np.load(drv.G / "out" / "regmodes.npz"))
names, D = score.dictionary()
extra = [(f"reg:{r}{k}", M[r][:, k]) for r in M for k in range(8)]
score._D["names"] = names + [n for n, _ in extra]
score._D["D"] = np.c_[D, np.array([v for _, v in extra]).T]
rng = np.random.default_rng(99)
for reg in drv.REGIONS:
    cl, used = [], []
    for i in range(12):
        cA = pairs.draw_A(rng, "prior" if i % 2 else "sampler")
        cD = pairs.draw_A(rng, "sampler" if i % 2 else "prior")
        cB = drv.transplant(cA, cD, reg, 1.0)
        o = score.oracle(cA, cB, kmax=6)
        cl.append(1 - o["err_after"][-1] / o["err0"])
        used += [k for k in o["moves"] if k.startswith("reg:")]
    print(reg, f"closure with reg: {np.mean(cl):.2f}", "reg moves used:", len(used), sorted(set(used))[:8], flush=True)
for case in sorted(p.stem for p in drv.HIDDEN.glob("s1_??.json")):
    h = json.loads((drv.HIDDEN / f"{case}.json").read_text())
    o = score.oracle(np.array(h["A"]), np.array(h["B"]), kmax=6)
    print(case, h["difficulty"], [x["region"] for x in h["changes"]], f"{o['err0']:.2f} -> {o['err_after'][-1]:.2f}",
          json.dumps(o["moves"]))
