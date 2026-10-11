"""lay.py <model>: the skin's layers around the eyes (names in order, the crease / caruncle ones in full)."""
import json
import sys

from hifipushie import skin, store

sp = store.load(sys.argv[1])
ly = skin.layers(sp)
names = list(ly)
print(len(names), "layers; eye-ish:", [n for n in names if any(k in n for k in ("eye", "carunc", "crease", "lash", "water"))])
for n in names:
    if "carunc" in n or "crease" in n:
        print(n, names.index(n), json.dumps(ly[n])[:600])
