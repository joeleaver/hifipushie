"""t1.py [n] [mode]: first test of the picture ruler: random pairs (A, B), B's clay pictures read against A."""
import sys
import time

import numpy as np

import drv
from hifipushie import face_ruler as fr, gnm_mm

n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
mode = sys.argv[2] if len(sys.argv) > 2 else "transplant"
rng = np.random.default_rng(7)
KINDS = ("front", "3q", "profile")
E = {m: [] for m in ("bayes", "span", "it3")}
T = []
for i in range(n):
    cA = rng.normal(size=170)
    if mode == "random":
        cB = cA + rng.normal(size=170) * 0.7
    else:
        reg = list(drv.REGIONS)[i % len(drv.REGIONS)]
        cB = drv.transplant(cA, rng.normal(size=170), reg, 1.0)
    A, B = fr.gnm_head(cA), fr.gnm_head(cB)
    views = [{"img": fr.clay(B, fr.camera(k)), "cam": fr.camera(k), "kind": k, "style": "clay"} for k in KINDS]
    t = time.time()
    obs = fr.observe(A, views)
    t1 = time.time() - t
    o = np.array([ob["o"] for ob in obs])
    pred = np.array([ob["J"] for ob in obs]) @ (cB - cA)
    if i < 3:
        for typ in ("outline", "iris", "lips", "brows"):
            for k in KINDS:
                s = np.array([ob["type"] == typ and ob["view"] == k for ob in obs])
                if s.sum():
                    print(f"  {typ:8s} {k:8s} n {s.sum():4d} |o| {np.abs(o[s]).mean():.2f} mm, o - J dc: bias {np.mean(o[s] - pred[s]):+.2f} sd {np.std(o[s] - pred[s]):.2f}")
    truth = {r["measure"]: r["gap"] for r in gnm_mm.gaps(drv.verts(cA), drv.verts(cB))}
    for m in E:
        res = fr.solve(obs, A, span=(m == "span")) if m != "it3" else fr.read(A, views, rounds=3)
        E[m].append([r["gap"] - truth[r["measure"]] for r in sorted(res["gaps"], key=lambda r: gnm_mm.NAMES.index(r["measure"]))])
        if m == "bayes":
            post = [r["err"] for r in sorted(res["gaps"], key=lambda r: gnm_mm.NAMES.index(r["measure"]))]
    T.append([truth[k] for k in gnm_mm.NAMES])
    print(i, f"obs {len(obs)} in {t1:.1f}s; |dc| {np.linalg.norm(cB - cA):.1f}; dc_hat err {np.linalg.norm(res['dc'] - (cB - cA)):.1f}", flush=True)
sd = gnm_mm.sd()
T = np.array(T)
print(f"{'measure':18s} pop sd | truth gap rms | bayes: bias  sd  (post) | span: bias  sd")
for j, k in enumerate(gnm_mm.NAMES):
    eb, es, e3 = np.array(E["bayes"])[:, j], np.array(E["span"])[:, j], np.array(E["it3"])[:, j]
    print(f"{k:18s} {sd[k]:5.1f} | {np.sqrt((T[:, j] ** 2).mean()):5.1f} | {eb.mean():+5.2f} {eb.std():5.2f} ({post[j]:.2f}) | {es.mean():+5.2f} {es.std():5.2f} | it3 {e3.mean():+5.2f} {e3.std():5.2f}")
