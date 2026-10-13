"""dump_landmarks.py <out.json> [version=2]: the landmark set as plain json (mirror, lm68, region, names, gnm), for the
training environment (torch only: no hifipushie there)."""
import json
import sys

from hifipushie import denselm

v = int(sys.argv[2]) if len(sys.argv) > 2 else 2
L = denselm.landmarks_v2() if v == 2 else denselm.landmarks()
json.dump({"mirror": L["mirror"].tolist(), "lm68": L["lm68"].tolist(), "region": L["region"].tolist(), "names": L["names"],
           "gnm": L["gnm"].tolist(), "gnm_all": L.get("gnm_all", L["gnm"]).tolist(), "n": int(L["n"]), "n_skin": int(L["n_skin"]),
           "version": L["version"]}, open(sys.argv[1], "w"))
print(sys.argv[1], L["n"])
