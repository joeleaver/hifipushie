"""sample.py <kind> <n> <seed> [render=1]: random GNM identities measured (gk.geo / clay / macro) -> out/s_<kind>_<seed>.npz
kind: gnm (N(0, I) over 170), ict (faces5's ICT-led prior m3_em_tau0.01), cls (gnm_sampler's identity decoder: random sex
0/1, random ethnicity one-hot, z ~ N(0, I))."""
import json
import sys
import time

import numpy as np

import gk
import lidgnm

kind, n, seed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
render = (sys.argv[4] != "0") if len(sys.argv) > 4 else True
rng = np.random.default_rng(seed)
HC = lidgnm.HC
if kind == "ict":
    S = np.load("/mnt/data/hifipushie/faces5/out/m3_em_tau0.01.npz")["cov"]
    w, Vv = np.linalg.eigh(S)
    A = Vv * np.sqrt(np.maximum(w, 0))
labs = []


def draw():
    if kind == "gnm":
        return rng.standard_normal(170), None
    if kind == "ict":
        return A @ rng.standard_normal(170), None
    from hifipushie import gnm_sampler as gs
    sex = int(rng.integers(2))
    eth = gs.ETH[int(rng.integers(4))]
    lab = gs.id_label(sex, eth)
    return gs.identity()(rng.standard_normal(64), lab)[0][HC], [sex, eth]


C, G, K, M, PR, L = [], [], [], [], [], []
t0 = time.time()
for i in range(n):
    c, lab = draw()
    g, prof, _ = gk.geo(c)
    k = gk.clay(c)[0] if render else {}
    m = gk.macro(c)
    C.append(c); G.append(g); K.append(k); M.append(m); L.append(lab)
    PR.append(prof if prof is not None else np.full((200, 2), np.nan))
    if i % 20 == 0:
        print(f"{i} {time.time() - t0:.0f}s drop {g['drop']:.2f} hidden {g.get('x_hidden', 0):.2f} local {g['local']:.2f} "
              f"narrow {g.get('x_narrow', 0):.2f} krad {g.get('x_krad', 0):.2f} dark {k.get('dark', np.nan):.2f}", flush=True)
np.savez(f"/mnt/data/hifipushie/gnmcrease/out/s_{kind}_{seed}.npz", C=np.array(C), prof=np.array(PR),
         geo=json.dumps(G), clay=json.dumps(K), macro=json.dumps(M), lab=json.dumps(L))
print("done", n, time.time() - t0)
