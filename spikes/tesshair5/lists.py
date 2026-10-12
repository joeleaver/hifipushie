"""lists.py <dir>: writes the styles (go.sh / riffs.sh read <dir>/styles/<NAME>.json): the six riff styles of rounds
three / four as th_S1..S6 (nothing changed in the calls: what changes is the code's defaults), Tess's fitted style
(T54 = T48's words + the tail fitted by measure, tailfit.py: side 20, length 0.2, fullness 0.76; T53 = the step before:
0.21 / 0.66; T55 = T54 + the hairline's ear lowered: <dir>/grooms/T55.json, applied by go.sh through server.groom_hair;
T56 = BEST: T55 refitted on the new hairline's random draw, fullness 0.66),
and the hairline dial H0 / H5 / H10 (hairline 0 / 0.5 / 1 on Tess's style). Also the looks (<dir>/looks/<NAME>.json:
the Cycles calibration) and the groom patches."""
import json
import os
import sys

d = sys.argv[1]
os.makedirs(f"{d}/styles", exist_ok=True)
TESS = {"tie": "low", "side": 20, "tightness": 0.85, "neatness": 0.95, "wisps": {"amount": 1.0, "softness": 0.7},
        "tail": {"length": 0.2, "wave": 0.6, "fullness": 0.76, "tousle": 0.55}}
R = {
    "S1": {"tie": "high", "side": "centre", "tightness": 0.9, "neatness": 0.85, "part": "none", "tail": {"length": 0.32, "wave": 0.1, "fullness": 0.6}},
    "S2": {"tie": "low", "side": "centre", "tightness": 0.5, "neatness": 0.6, "tail": {"length": 0.28, "wave": 0.3, "fullness": 0.5}},
    "S3": {"tie": "low", "side": "left", "tightness": 0.85, "neatness": 0.95, "tail": {"length": 0.24, "wave": 0.1, "fullness": 0.5}},
    "S4": {"tie": "mid", "side": "centre", "tightness": 0.5, "neatness": 0.6, "half": True, "length": 0.24, "tail": {"length": 0.2, "wave": 0.3, "fullness": 0.3}},
    "S5": {"tie": "top", "side": "centre", "tightness": 0.8, "neatness": 0.7, "part": "none", "tail": "bun"},
    "S6": {"tie": "low", "side": "centre", "tightness": 0.6, "neatness": 0.7, "tail": {"kind": "plait", "length": 0.34, "fullness": 0.6}},
    "T56": {**TESS, "tail": {**TESS["tail"], "fullness": 0.66}}, "T55": TESS, "T54": TESS, "T53": {**TESS, "tail": {"length": 0.21, "wave": 0.6, "fullness": 0.66}},
    "H0": {**TESS, "hairline": 0.0}, "H5": {**TESS, "hairline": 0.5}, "H10": {**TESS, "hairline": 1.0},
}
LOOK = {"cycles_width": 1.8, "cycles_sat": 0.65}  # (cyccal.py: against her pictures, dense hair, both views)
EAR = {"hairline": {"ear": -0.013, "sideburns": 0.035}}  # (ear.py: tess_a1's ear top is 1.8 cm under the assumed one)
for sub, names, val in (("looks", ("T53", "T54", "T55", "T56"), LOOK), ("grooms", ("T55", "T56", "S1", "S2", "S3", "S4", "S5", "S6"), EAR)):
    os.makedirs(f"{d}/{sub}", exist_ok=True)
    for n in names:
        with open(f"{d}/{sub}/{n}.json", "w") as f:
            f.write(json.dumps(val) + "\n")
for n, st in R.items():
    with open(f"{d}/styles/{n}.json", "w") as f:
        f.write(json.dumps(st) + "\n")
