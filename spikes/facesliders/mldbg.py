"""mldbg.py <model>: the profile outline's matched points and the mentolabial depth on photo / model."""
import json
import sys

import numpy as np

import joint2
import outl
from hifipushie import humanfit, store

m = sys.argv[1]
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
st = humanfit.state(store.load(m)["base"])
vi = 2
o = outl.profile_auto(refs["views"][vi])
sl = joint2.outline_rows(st, refs["cameras"][vi], o, [], "profile")
print("trace", len(o), "matched", len(sl["p"]))
uv = humanfit.project(refs["cameras"][vi], sl["X"])
print("photo", joint2.mentolabial(sl["p"]), "model", joint2.mentolabial(uv))
