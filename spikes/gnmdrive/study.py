"""study.py <n per region> [seed]: which vocabulary moves the oracle uses for each region's differences, over many
random transplants (A random, donor random, amount 1). Per region: how often each move is picked (all / named oracle,
k <= 6), and for each picked move the regression of its amount on the region's character-macro differences (what you
SEE -> what you USE). -> out/study.json, out/study.txt"""
import json
import sys
from collections import Counter, defaultdict

import numpy as np

import drv
import pairs
import score

N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
rng = np.random.default_rng(int(sys.argv[2]) if len(sys.argv) > 2 else 7)
out = {}
txt = []
for reg in drv.REGIONS:
    recs = []
    for i in range(N):
        cA = pairs.draw_A(rng, "prior" if i % 2 else "sampler")
        cD = pairs.draw_A(rng, "sampler" if i % 2 else "prior")
        cB = drv.transplant(cA, cD, reg, 1.0)
        m0, m1 = drv.macros(cA), drv.macros(cB)
        dm = {k: m1[k] - m0[k] for k in m0}
        o_all = score.oracle(cA, cB, kmax=6)
        o_nam = score.oracle(cA, cB, kmax=6, named=True)
        recs.append({"dm": dm, "all": o_all["moves"], "named": o_nam["moves"], "e0": o_all["err0"],
                     "e_all": o_all["err_after"][-1] if o_all["err_after"] else o_all["err0"],
                     "e_nam": o_nam["err_after"][-1] if o_nam["err_after"] else o_nam["err0"]})
    out[reg] = recs
    txt.append(f"== {reg}: closure all {np.mean([1 - r['e_all'] / r['e0'] for r in recs]):.2f}, "
               f"named {np.mean([1 - r['e_nam'] / r['e0'] for r in recs]):.2f} (k <= 6, mean of {N})")
    for kind in ("all", "named"):
        cnt = Counter(k for r in recs for k in r[kind])
        txt.append(f"  {kind}: " + ", ".join(f"{k} {v}" for k, v in cnt.most_common(12)))
        # what you see -> what you use: per frequent move, its best-correlated macro difference
        for k, v in cnt.most_common(8):
            a = np.array([r[kind].get(k, 0.0) for r in recs])
            best = []
            for m in drv.hm.NAMES:
                x = np.array([r["dm"][m] for r in recs])
                if x.std() < 1e-6:
                    continue
                cc = np.corrcoef(x, a)[0, 1]
                best.append((abs(cc), m, cc, np.polyfit(x, a, 1)[0]))
            best.sort(reverse=True)
            txt.append(f"     {k}: " + "; ".join(f"d{m} r {cc:+.2f} (amount {b:+.2f} per sd)" for _, m, cc, b in best[:3]))
    print("\n".join(txt[-20:]), flush=True)
(drv.G / "out" / "study.json").write_text(json.dumps(out))
(drv.G / "out" / "study.txt").write_text("\n".join(txt))
