"""orbitlid.py: how much of a lid's change comes with the ORBIT's measures (gnm_mm: eyes_forward, brows_over_eyes,
pupils_apart), on GNM's raw mesh.
1. gnmdrive's pair s5_04 (START A -> TARGET B; r5_04 = the driver's result): the upper lid's vertices (rings 0..11,
   upper half, left eye) in the EYE frame (ball centre at the origin): rms distance to B's for A, A + each mm move at
   B's value (every other measure held; eyes_forward carries subnasale_forward back, as the driver did), their sum,
   and r5_04.
2. Tess (er_s4): the same mm moves dialled (EF=<mm list>, BR=<mm list>): the lid's structure numbers.
Usage: orbitlid.py [tess model=er_s4]"""
import json
import sys

import numpy as np

import lidmap as lm
import lidstruct as ls
from hifipushie import gnm_controls as gc, gnm_mm

D = "/mnt/data/hifipushie/gnmdrive"
h = json.load(open(f"{D}/hidden/s5_04.json"))
A, B = np.asarray(h["A"], float), np.asarray(h["B"], float)
Rr = np.asarray(json.load(open(f"{D}/cases/r5_04/state.json"))["c"], float)
t = lm.topo()
g = gc.gnm()
ids = np.concatenate([t["loops"][k][g["T"][t["loops"][k], 1] > g["J"][2][1] + 0.0005] for k in range(0, 12)])
rk = t["ring"][ids]


def lid(c):
    V = gc.vertices(c) * 1000
    ctr, _ = lm.eye_frame_raw(c)
    return V[ids] - ctr


def mm_of(c):
    rd = gnm_mm.readers(gc.vertices(c))
    return {k: float(rd[k]) for k in gnm_mm.NAMES}


def move(c, **kw):
    c = c.copy()
    for k, x in kw.items():
        c = c + gnm_mm.direction(k) * x
    return c


LB = lid(B)
ma, mb = mm_of(A), mm_of(B)
print("s5_04: orbit measures A -> B (mm): " + ", ".join(f"{k} {ma[k]:.1f} -> {mb[k]:.1f}" for k in ("eyes_forward", "brows_over_eyes", "pupils_apart", "eyes_height", "forehead_forward")))


def rep(lab, c):
    d = np.linalg.norm(lid(c) - LB, axis=1)
    q = ls.mean_structure(c)
    print(f"  {lab:44s} lid vs B rms {np.sqrt((d ** 2).mean()):5.2f} mm (rings 0-5 {np.sqrt((d[rk <= 5] ** 2).mean()):5.2f}, 6-11 {np.sqrt((d[rk >= 6] ** 2).mean()):5.2f}) | "
          f"platform {q['platform_s']:.2f} tuck {q['tuck']:.0f} wall {q['wall']:.0f} drape {q['drape']:.2f} brow stand-off {q['brow']:.1f} brow_v {q['brow_v']:.1f}")


de, db, dp = mb["eyes_forward"] - ma["eyes_forward"], mb["brows_over_eyes"] - ma["brows_over_eyes"], mb["pupils_apart"] - ma["pupils_apart"]
rep("A (start)", A)
rep(f"A + eyes_forward {de:+.1f} (muzzle kept)", move(A, eyes_forward=de, subnasale_forward=-de))
rep(f"A + brows_over_eyes {db:+.1f}", move(A, brows_over_eyes=db))
rep(f"A + pupils_apart {dp:+.1f}", move(A, pupils_apart=dp))
rep("A + eyes_forward + brows_over_eyes", move(A, eyes_forward=de, subnasale_forward=-de, brows_over_eyes=db))
rep("A + all three", move(A, eyes_forward=de, subnasale_forward=-de, brows_over_eyes=db, pupils_apart=dp))
allmm = A + gnm_mm.jacobian().T @ np.linalg.solve(gnm_mm.jacobian() @ gnm_mm.jacobian().T + 1e-6 * np.eye(len(gnm_mm.HELD)),
                                                 np.array([mm_of(B).get(k, 0) - mm_of(A).get(k, 0) if k in gnm_mm.NAMES else 0.0 for k in gnm_mm.HELD]))
rep("A + ALL 23 mm measures set to B's", allmm)
rep("r5_04 (the driver's result)", Rr)
rep("B (target)", B)

name = sys.argv[1] if len(sys.argv) > 1 else "er_s4"
c = ls.ident(name)
m = mm_of(c)
print(f"\n{name}: eyes_forward {m['eyes_forward']:.1f}, brows_over_eyes {m['brows_over_eyes']:.1f}, pupils_apart {m['pupils_apart']:.1f} (GNM frame mm; population sd "
      f"{gnm_mm.sd()['eyes_forward']:.1f} / {gnm_mm.sd()['brows_over_eyes']:.1f} / {gnm_mm.sd()['pupils_apart']:.1f})")
print(f"  {'move':36s} " + " ".join(f"{k[:9]:>9s}" for k in ls.KEYS) + "  |dc|")
for lab, kw in (("as is", {}), ("eyes_forward +2", dict(eyes_forward=2, subnasale_forward=-2)), ("eyes_forward +4", dict(eyes_forward=4, subnasale_forward=-4)),
                ("eyes_forward +6", dict(eyes_forward=6, subnasale_forward=-6)), ("eyes_forward -4", dict(eyes_forward=-4, subnasale_forward=4)),
                ("brows_over_eyes +3", dict(brows_over_eyes=3)), ("brows_over_eyes -3", dict(brows_over_eyes=-3)),
                ("eyes_forward +4, brows +3", dict(eyes_forward=4, subnasale_forward=-4, brows_over_eyes=3))):
    c1 = move(c, **kw)
    q = ls.mean_structure(c1)
    print(f"  {lab:36s} " + " ".join(f"{q[k]:9.2f}" for k in ls.KEYS) + f"  {np.linalg.norm(c1 - c):.2f}")
