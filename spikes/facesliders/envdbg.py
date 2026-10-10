"""envdbg.py: which head vertices the chin's envelope picks (GNM groups of them)."""
import json

import numpy as np

import joint2
import outl
from hifipushie import base, humanfit, onemesh, store

g = base._gnm_data()
print(sorted(g["groups"].keys()))
sp = store.load("fs_gj6")
refs = json.loads((store.HOME / "fs_gj6" / "human_refs.json").read_text())
st = humanfit.state(sp["base"])
cam = refs["cameras"][0]
o = np.asarray(outl.traced("fs_traces_g", refs["views"][0]["image"], ("chin",))[0], float)
sl = joint2.envelope(st, cam, o, 0.5)
gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(st["tpl"]["fid"])][sl["vs"]]
for k, v in g["groups"].items():
    w = np.asarray(v, float)[gid]
    if (w > 0.5).any():
        print(k, int((w > 0.5).sum()))
print("fade", np.round(np.asarray(onemesh.asset()["g_fade"], float)[gid], 2))
