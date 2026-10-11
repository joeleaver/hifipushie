"""mmmove.py <src> <dst el_*> <measure>=<mm> ... | eth=<name>:<w>,...: a scratch copy with gnm_mm moves (GNM-frame mm,
every other measure held; eyes_forward=x also moves subnasale_forward -x unless given, so the muzzle stays), and / or
the identity's place on the sampler's ethnicity directions SET (eth=white:0.8,asian:0,middle_eastern:0,black:0: the
least-squares weights of lstruct.py's CLS table moved to these values)."""
import copy
import json
import shutil
import sys

import numpy as np

from hifipushie import blockin as bi, gnm_mm, gnm_sampler as gs, store

src, dst = sys.argv[1:3]
assert dst.startswith("el_")
sp = copy.deepcopy(store.load(src))
c = bi.identity(sp)
c0 = c.copy()
kw = dict(a.split("=", 1) for a in sys.argv[3:])
eth = kw.pop("eth", None)
mv = {k: float(v) for k, v in kw.items()}
if "eyes_forward" in mv and "subnasale_forward" not in mv:
    mv["subnasale_forward"] = -mv["eyes_forward"]
for k, x in mv.items():
    c = c + gnm_mm.direction(k) * x
if eth:
    D = gs.identity()
    mu = D(np.zeros(64), gs.id_label(0.5, None))[0][:170]
    sexd = D(np.zeros(64), gs.id_label("male", None))[0][:170] - D(np.zeros(64), gs.id_label("female", None))[0][:170]
    E = {e: D(np.zeros(64), gs.id_label(0.5, e))[0][:170] - mu for e in gs.ETH}
    B = np.c_[sexd, *[E[e] for e in gs.ETH]]
    w = np.linalg.lstsq(B, c - mu, rcond=None)[0]
    want = w.copy()
    for a in eth.split(","):
        n, x = a.split(":")
        want[1 + gs.ETH.index(n)] = float(x)
    c = c + B @ (want - w)
    print("ethnicity weights", dict(zip(["sex"] + gs.ETH, np.round(w, 2))), "->", dict(zip(["sex"] + gs.ETH, np.round(want, 2))))
bi.set_identity(sp, c)
sp.pop("hair", None)
d = store._dir(dst)
d.mkdir(parents=True, exist_ok=True)
(d / "spec.json").write_text(json.dumps(sp))
shutil.copy(store._dir(src) / "human_refs.json", d / "human_refs.json")
print(f"wrote {dst}: |dc| {np.linalg.norm(c - c0):.2f}, |c| {np.linalg.norm(c0):.2f} -> {np.linalg.norm(c):.2f}")
