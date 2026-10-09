"""liptone.py [model]: (1) the lips' layer colours as skin.lips' blood / melanin go up (does the colour model saturate?)
(2) the share of each lip's vermilion (GNM upper_lip / lower_lip, exterior skin) inside its paint zone (the outline
mask evaluated on the template's vertices with their normals, as paint does)."""
import sys

import numpy as np

from hifipushie import base as basemod
from hifipushie import humanfit, onemesh, paint, skin, store

name = sys.argv[1] if len(sys.argv) > 1 else "ll_e14"
s = store.load(name)
s = s.get("spec", s)
lys = skin.layers(s)
for k in ("skin:lips_upper", "skin:lips_lower"):
    print(k, lys[k]["color"], lys[k].get("opacity"))
for bl in (0.5, 1, 2, 5):
    s2 = {**s, "skin": {**s["skin"], "lips": {**s["skin"].get("lips", {}), "blood": bl}}}
    l2 = skin.layers(s2)
    print("blood", bl, "upper", l2["skin:lips_upper"]["color"], "lower", l2["skin:lips_lower"]["color"])
st = humanfit.state(s["base"])
P = np.asarray(st["tpl"]["P"], float)
Q = np.asarray(st["tpl"]["L"]).reshape(-1, 4)
n = np.zeros_like(P)
for a, b, c in ((0, 1, 3), (1, 2, 0), (2, 3, 1), (3, 0, 2)):
    np.add.at(n, Q[:, a], np.cross(P[Q[:, b]] - P[Q[:, a]], P[Q[:, c]] - P[Q[:, a]]))
n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-15)
gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(st["tpl"]["fid"])]
g = basemod._gnm_data()
L = np.asarray(st["L"])
J = {k: L[i] for k, i in basemod.LANDMARKS.items()}
J.update({k[:-2] + ".R": L[{48: 48}.get(i, i)] * [1, 1, 1] for k, i in basemod.LANDMARKS.items() if k.endswith(".L")})
mirror68 = {54: 48, 53: 49, 52: 50, 55: 59, 56: 58, 63: 61, 65: 67, 35: 31, 42: 39, 45: 36, 22: 21, 24: 19, 26: 17}
for k, i in basemod.LANDMARKS.items():
    if k.endswith(".L") and i in mirror68:
        J[k[:-2] + ".R"] = L[mirror68[i]]
sp = {"joints": {k: {"pos": v.tolist(), "r": 0.001} for k, v in J.items()}, "bones": {}, "blobs": {}}
EJ = paint._expanded(s)["joints"]
print("dense joints:", sum(1 for k in EJ if k.startswith("verm_")))
sp["joints"].update({k: v for k, v in EJ.items() if k.startswith("verm_")})
for zone, grp in (("lip_upper", "upper_lip"), ("lip_lower", "lower_lip"), ("lips", "upper_lip"), ("lips", "lower_lip")):
    o = skin.zone(s, zone, grow=2.2)[0]["outline"]
    m = paint._outline_mask(sp, zone, o, P, n)
    ext = np.asarray(g["groups"]["skin_exterior"]) > 0.5
    sel = (gid >= 0) & (np.asarray(g["groups"][grp])[np.maximum(gid, 0)] > 0.5) & ext[np.maximum(gid, 0)]
    m2 = paint._outline_mask(sp, zone, o, P, np.tile([0.0, -1.0, 0.0], (len(P), 1)))
    vis = sel & (-n[:, 1] > 0.3)
    print(zone, "| inside the outline (facing ignored)", round(float((m2[sel] > 0.5).mean()), 3),
          "| facing the camera (> 0.3):", int(vis.sum()), "of which masked", round(float((m[vis] > 0.5).mean()), 3))
    print(zone, "vermilion vertices", int(sel.sum()), "mask > 0.5:", round(float((m[sel] > 0.5).mean()), 3),
          "mean", round(float(m[sel].mean()), 3), "| facing -(n.y) mean", round(float((-n[sel, 1]).mean()), 3))
