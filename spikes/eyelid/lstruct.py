"""lstruct.py <label>=<identity source> ...: the upper lid's structure on GNM's RAW mesh, ring by ring
(lidstruct.structure), mean of the columns u = -4, 0, +4 of the left eye; the same at the inner (u -8) and outer (+8)
thirds (crease height / tuck / hang); + the orbit's gnm_mm measures (eyes_forward = eye centres minus nasion, forward;
brows_over_eyes; pupils_apart; mm) and the opening. Sources as lidstruct.ident (model | mean | json:path:key |
cls:sex:ethnicity). CLS=1 adds, per identity, its place on the sampler's class directions."""
import os
import sys

import numpy as np

import lidmap as lm
import lidstruct as ls
from hifipushie import gnm_controls as gc, gnm_mm

MM = ("eyes_forward", "brows_over_eyes", "pupils_apart")
K1 = ("margin_v", "crease_h", "platform_s", "roll", "tuck", "wall", "drape", "hang", "brow", "brow_v")
print(f"{'':16s}" + " ".join(f"{k[:9]:>9s}" for k in K1) + " | inner: crease tuck hang | outer: crease tuck hang | " + " ".join(f"{k[:12]:>12s}" for k in MM) + "  opening")
rows = {}
for a in sys.argv[1:]:
    lab, src = a.split("=", 1)
    c = ls.ident(src)
    q = ls.mean_structure(c)
    qi, qo = ls.structure(c, u=-8.0), ls.structure(c, u=8.0)
    V = gc.vertices(c)
    rd = gnm_mm.readers(V)
    ctr, _ = lm.eye_frame_raw(c)
    lo = {k: v for k, v, w in lm.column(V * 1000, ctr, 0.0, upper=False)}
    rows[lab] = c
    print(f"{lab:16s}" + " ".join(f"{q[k]:9.2f}" for k in K1) + f" | {qi['crease_h']:13.2f} {qi['tuck']:4.0f} {qi['hang']:4.2f} | {qo['crease_h']:13.2f} {qo['tuck']:4.0f} {qo['hang']:4.2f} | "
          + " ".join(f"{float(rd[k]):12.2f}" for k in MM) + f"  {q['margin_v'] - lo.get(0, np.nan):7.2f}")
if os.environ.get("CLS") == "1":
    from hifipushie import gnm_sampler as gs
    D = gs.identity()
    mu = D(np.zeros(64), gs.id_label(0.5, None))[0][:170]
    sexd = D(np.zeros(64), gs.id_label("male", None))[0][:170] - D(np.zeros(64), gs.id_label("female", None))[0][:170]
    E = {e: D(np.zeros(64), gs.id_label(0.5, e))[0][:170] - mu for e in gs.ETH}
    print(f"\nthe sampler's class directions (z = 0): |all-class mean| {np.linalg.norm(mu):.2f} from GNM's template; |male - female| {np.linalg.norm(sexd):.2f}; "
          + ", ".join(f"|{e} - all| {np.linalg.norm(v):.2f}" for e, v in E.items()))
    B = np.c_[sexd, *[E[e] for e in gs.ETH]]
    print(f"{'':16s}  sex(0 f..1 m)  " + " ".join(f"{e[:14]:>14s}" for e in gs.ETH) + "   (least-squares weights of c - all-class mean on the 5 directions; ethnicity rows sum to ~0 at the mean) | cos to each")
    for lab, c in rows.items():
        d = c - mu
        w = np.linalg.lstsq(B, d, rcond=None)[0]
        cs = [float(d @ E[e] / (np.linalg.norm(d) * np.linalg.norm(E[e]) + 1e-12)) for e in gs.ETH]
        print(f"{lab:16s}  {0.5 + w[0]:13.2f}  " + " ".join(f"{x:14.2f}" for x in w[1:]) + "   | " + " ".join(f"{x:+.2f}" for x in cs))
