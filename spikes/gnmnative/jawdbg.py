"""gnmnative debug: what a jawOpen expression moves on the built head (skin regions, pieces)."""
import copy

import numpy as np

from hifipushie import base, faceshapes, humans, onemesh
from hifipushie.spec import empty_spec

sp0 = {**empty_spec(), **humans.spec(age=30, sex=1.0, source="human", skin=False, outfit_kind="none")}
sp0["base"]["head"].pop("lip_seal", None)
sp0["base"]["head"]["lip_close"] = True
face = faceshapes.face_of(sp0)
cf = face.shape_coeffs("jawOpen")
sp1 = copy.deepcopy(sp0)
sp1["base"]["head"]["expression"] = cf
h0, h1 = onemesh.head_rest(sp0["base"]), onemesh.head_rest(sp1["base"])
g = base._gnm_data()
G = {k: np.asarray(v) > 0.5 for k, v in g["groups"].items()}
D = (h1["gnm_world"] - h0["gnm_world"]) * 1000
for k in ("forehead_region", "nose_region", "upper_lip_region", "lower_lip_region", "chin_region", "upper_teeth_and_gums",
          "lower_teeth_and_gums", "tongue", "left_eye", "ears"):
    d = D[G[k]]
    print(f"{k:22s} mean move {d.mean(0).round(3)} max |d| {np.linalg.norm(d, axis=1).max():.3f}")
print("eyes", (np.array(h1["eyes"]) - np.array(h0["eyes"])) * 1000, "carry mid", (h1["carry"]["mid"] - h0["carry"]["mid"]) * 1000,
      "eye_mid", (h1["carry"]["eye_mid"] - h0["carry"]["eye_mid"]) * 1000)
nf = onemesh.neck_fade()
for ids, anc in base._gnm_piece_sets(g)[2:]:
    for k in ("upper_lip_region", "lower_lip_region", "chin_region"):
        m = G[k]
        print(k, "n", m.sum(), "fade min", nf[m].min().round(3), "share < 0.999", float((nf[m] < 0.999).mean()))
c = h0["carry"]
names = [str(n) for n in g["expression_names"]]
ce = base._gnm_coeffs(g["expression_names"], cf)
En = np.tensordot(ce, g["expression_basis"], 1).astype(float)
pred = c["s"] * (En * nf[:, None]) @ np.asarray(c["R"], float).T * 1000
for k in ("upper_lip_region", "lower_lip_region", "chin_region"):
    m = G[k]
    print(k, "actual - predicted skin move: mean", (D[m] - pred[m]).mean(0).round(3), "max", np.abs(D[m] - pred[m]).max().round(3))
cap = []
orig = base._gnm_pieces
def spy(V, Vg, g_, En=None, fade=None):
    cap.append((V.copy(), Vg.copy(), En.copy()))
    return orig(V, Vg, g_, En, fade)
base._gnm_pieces = spy
onemesh._CACHE.clear(); base._CACHE.pop("piece_sets", None)
for k in [k for k in base._CACHE if isinstance(k, tuple) and k[0] == "head"]:
    base._CACHE.pop(k)
onemesh.head_template(sp0["base"]); onemesh.head_template(sp1["base"])
(V0, Vg0, E0), (V1, Vg1, E1) = cap[-2:]
ids, anc = base._gnm_piece_sets(g)[2]
print("neutral anchors differ (mm):", np.abs((V1 - E1 * nf[:, None])[anc] - (V0 - E0 * nf[:, None])[anc]).max() * 1000,
      "| Vg - En differ:", np.abs((Vg1 - E1) - (Vg0 - E0)).max() * 1000, "| En upper teeth:", np.abs(E1[G['upper_teeth_and_gums']]).max() * 1000, np.abs(E0[G['upper_teeth_and_gums']]).max() * 1000)
R_ = (V1 - V0) - nf[:, None] * (E1 - E0)
dd = (E1 - E0) - En
sk = np.asarray(g["skin"])
print("V1-V0 - fade (E1-E0): max mm over skin", np.abs(R_[sk]).max() * 1000, "at lips", np.abs(R_[G['lower_lip_region']]).max() * 1000,
      "| dp1 - dp0 max mm", np.abs(dd).max() * 1000, "on lips", np.abs(dd[G['lower_lip_region']]).max() * 1000)
i = np.argmax(np.abs(R_[sk]).max(1)); gi = np.flatnonzero(sk)[i]
print("worst skin vertex", gi, "groups", [k for k in G if G[k][gi]][:8], "fade", nf[gi], "g_fade", onemesh.asset()["g_fade"][gi])
