"""final.py <model> ...: identity distances between the scratch models and the block-in's head, the eye expression's
size, and the humanmacro readings that moved (sd) against gd_T12."""
import sys

import numpy as np

from hifipushie import blockin as bi, humanmacro as hm, store

ref = {n: bi.identity(store.load(n)) for n in ("gd_T12", "gb_fx")}
z0 = hm.read(V=hm.head(ref["gd_T12"]))
for name in sys.argv[1:]:
    sp = store.load(name)
    c = bi.identity(sp)
    ex = sp["base"]["head"].get("expression") or {}
    e = np.linalg.norm([v for k, v in ex.items() if "left_eye_region" in k])
    z = hm.read(V=hm.head(c))
    dz = sorted(((z[k] - z0[k], k) for k in z0), key=lambda t: -abs(t[0]))[:8]
    print(f"{name:10s} |c - gd_T12| {np.linalg.norm(c - ref['gd_T12']):.2f}  |c - gb_fx| {np.linalg.norm(c - ref['gb_fx']):.2f}  |c| {np.linalg.norm(c):.2f}  eye expression |e| (one side) {e:.2f}  "
          f"eye_radius {sp['base']['head'].get('eye_radius')}\n           identity readings moved vs gd_T12 (sd): " + ", ".join(f"{k} {d:+.2f}" for d, k in dz))
