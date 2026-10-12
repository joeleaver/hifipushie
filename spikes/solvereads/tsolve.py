"""tsolve.py: where a cmax solve's time goes (synthetic reads of the size of a real call: 900 x 190)."""
import time, cProfile, pstats
import numpy as np
from hifipushie import face_ruler as fr
head = fr.gnm_head(np.zeros(170))
rng = np.random.default_rng(1)
J = rng.standard_normal((900, 170)) * 0.5
c = np.zeros(170); c[40] = 9.0
o = J @ c + 0.3 * rng.standard_normal(900)
obs = [{"type": "outline", "view": "front", "o": float(o[i]), "J": J[i], "sig": 0.3} for i in range(900)]
t = time.time(); fr.solve(obs, head, adapt=True); print("one solve", time.time() - t)
pr = cProfile.Profile(); pr.enable()
t = time.time(); r = fr.solve(obs, head, adapt=True, cmax=3.0); print("cmax solve", time.time() - t, r["relax"])
pr.disable(); pstats.Stats(pr).sort_stats("cumtime").print_stats(14)
