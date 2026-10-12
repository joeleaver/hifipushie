"""p5_necklen.py <model> ...: the neck's LENGTH on each model's template cage and on the MakeHuman body's own figure.
Landmarks: top of head; chin = menton (lm 8); suprasternale = MakeHuman body vertex 1522 (the front midline's pit
between the clavicles); acromion = MakeHuman body vertex 8275 (the shoulder's outer top). Both are MakeHuman's own
vertices below the neck loop, present in every build (moved by the neck field on a native head).
ANSUR II (computed from the public per-subject tables, /mnt/data/hifipushie/headbody/ansur/ansur.py):
  top of head - suprasternale 298.8 F / 317.6 M mm = 0.1836 / 0.1809 of stature (sd 0.0071);
  top of head - acromion 293.4 / 315.5; suprasternale - acromion height -5 / +2 mm.
Chin - suprasternale is NOT in ANSUR II: 299 - 218 = 81 F, 318 - 232 = 86 M uses the head heights from memory."""
import sys
import numpy as np
from hifipushie import headfit, makehuman, onemesh, store

OUT = "/mnt/data/hifipushie/headbody/out"
SUPRA, ACRO = 1522, 8275
a = onemesh.asset()
mh_rows = np.flatnonzero(a["m2f"] >= 0)
row = {int(v): i for i, v in enumerate(mh_rows)}
assert SUPRA in row and ACRO in row


def prof(P, half=0.012, step=0.003):
    m = np.abs(P[:, 0]) < half
    b = np.floor(P[m, 2] / step).astype(int)
    u = np.unique(b)
    return (u + 0.5) * step, np.array([P[m][b == k][:, 1].min() for k in u]), np.array([P[m][b == k][:, 1].max() for k in u])


res = {}
for name in sys.argv[1:]:
    base = store.load(name)["base"]
    tpl = onemesh.template(base)
    ht = onemesh.head_rest(base)
    P = np.asarray(tpl["P"], float)
    res[name] = {"top": P[:, 2].max(), "chin": np.asarray(ht["lm68"][8], float), "supra": P[row[SUPRA]], "acro": P[row[ACRO]], "prof": prof(P),
                 "lm": np.asarray(ht["lm68"], float), "eyes": np.asarray(ht["eyes"], float)}
    if not onemesh.native(base):
        mb = makehuman.body(onemesh.body_params(base))
        Pm = np.asarray(mb["P"], float)
        res[f"MakeHuman's own ({name}'s body)"] = {"top": Pm[:, 2].max(), "chin": Pm[headfit.table()["lm68"][8]], "supra": Pm[SUPRA], "acro": Pm[ACRO], "prof": prof(Pm)}
print(f"{'':40s} stature head  chin-supra  top-supra  /stature  top-acromion  supra-acro  chin fwd of supra  neck girth")
for k, M in res.items():
    st = M["top"]
    print(f"{k:40s} {1e3*st:6.0f} {1e3*(st-M['chin'][2]):5.0f}  {1e3*(M['chin'][2]-M['supra'][2]):7.0f}   {1e3*(st-M['supra'][2]):7.0f}    {(st-M['supra'][2])/st:.3f}    {1e3*(st-M['acro'][2]):7.0f}     {1e3*(M['supra'][2]-M['acro'][2]):6.0f}       {1e3*(M['supra'][1]-M['chin'][1]):6.0f}")
np.save(f"{OUT}/necklen.npy", res, allow_pickle=True)
