"""hips.py: how the measure modifiers move humanfit's body measures (a woman, 30)."""
import copy

from hifipushie import humanfit, humans

sp = humans.spec(age=30, sex=0.0, seed=3, skin=False, source="human")
m0 = humanfit.state(sp["base"])["measures"]
keys = [k for k in m0 if any(w in k for w in ("hip", "waist", "shoulder", "chest", "bust", "biacrom"))]
print({k: round(m0[k], 2) for k in keys})
for mod in ("hips", "waist", "shoulders", "chest"):
    b = copy.deepcopy(sp["base"])
    b["body"][mod] = 1.0
    m1 = humanfit.state(b)["measures"]
    print(mod, {k: round(m1[k] - m0[k], 2) for k in keys})
nb, rep = humanfit.solve(sp["base"], {"hip_breadth": "-2"}, free=("body",))
print(nb["body"], {k: rep[k] for k in rep if k in ("refused", "unintended")})
