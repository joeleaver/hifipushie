"""gnmnative debug: tongueOut on GNM's own tongue."""
import numpy as np

from hifipushie import base, faceshapes, humans
from hifipushie.spec import empty_spec

sp = {**empty_spec(), **humans.spec(age=30, sex=1.0, source="human", skin=False, outfit_kind="none")}
sp["base"]["head"].pop("lip_seal", None)
sp["base"]["head"]["lip_close"] = True
face = faceshapes.face_of(sp)
dV, cf = face._tongue_out()
G = face._setup()
g = G["g"]
names = [str(n) for n in g["expression_names"]]
print("coeffs", {names[i]: round(float(v), 2) for i, v in cf.items()})
tg = np.flatnonzero(np.asarray(g["groups"]["tongue"]) > 0.5)
V = G["c"]["V"]
front = tg[V[tg, 2] > np.percentile(V[tg, 2], 92)]
print("front set mean GNM mm", (V[front].mean(0) * 1000).round(1), "lips z", (G["X0"][[51, 57], 2] * 1000).round(1), "move mm", (dV[front].mean(0) * 1000).round(1))
dW = face._by_index(dV)
print("world move of the front set mm", (dW[front].mean(0) * 1000).round(1), "out", face.out.round(2))
mp = base.gnm_mouth(face.head)
tgv = mp["tongue"]["verts"]
D = face.displacements(tgv, tgv, np.zeros_like(tgv), "tongue", ["tongueOut", "jawOpen"])
tip = np.argmax(tgv @ face.out)
print("tip move tongueOut mm", (D["tongueOut"][tip] * 1000).round(1), "jawOpen", (D["jawOpen"][tip] * 1000).round(1))
print("dV stored has tongue part:", float(np.abs(G["dV"]["tongueOut"][tg]).max() * 1000), "jaw-only would be", float(np.abs((G["dV"]["tongueOut"] - dV)[tg]).max() * 1000))
