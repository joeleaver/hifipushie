"""dump_landmarks.py <out.json>: the landmark set as plain json (mirror, lm68, region, names, gnm), for the training
environment (torch only: no hifipushie there)."""
import json
import sys

from hifipushie import denselm

L = denselm.landmarks()
json.dump({"mirror": L["mirror"].tolist(), "lm68": L["lm68"].tolist(), "region": L["region"].tolist(), "names": L["names"],
           "gnm": L["gnm"].tolist(), "n": int(L["n"]), "n_skin": int(L["n_skin"]), "version": L["version"]}, open(sys.argv[1], "w"))
print(sys.argv[1], L["n"])
