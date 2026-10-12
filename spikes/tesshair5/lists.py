"""lists.py <dir>: writes the styles (go.sh / riffs.sh read <dir>/styles/<NAME>.json): the six riff styles of rounds
three / four as th_S1..S6 (nothing changed in the calls: what changes is the code's defaults), Tess's fitted style
(T53 = T48's words + the tail fitted by measure: side 20, length 0.21, fullness 0.66), and the hairline dial H0 / H5 /
H10 (hairline 0 / 0.5 / 1 on Tess's style)."""
import json
import os
import sys

d = sys.argv[1]
os.makedirs(f"{d}/styles", exist_ok=True)
TESS = {"tie": "low", "side": 20, "tightness": 0.85, "neatness": 0.95, "wisps": {"amount": 1.0, "softness": 0.7},
        "tail": {"length": 0.21, "wave": 0.6, "fullness": 0.66}}
R = {
    "S1": {"tie": "high", "side": "centre", "tightness": 0.9, "neatness": 0.85, "part": "none", "tail": {"length": 0.32, "wave": 0.1, "fullness": 0.6}},
    "S2": {"tie": "low", "side": "centre", "tightness": 0.5, "neatness": 0.6, "tail": {"length": 0.28, "wave": 0.3, "fullness": 0.5}},
    "S3": {"tie": "low", "side": "left", "tightness": 0.85, "neatness": 0.95, "tail": {"length": 0.24, "wave": 0.1, "fullness": 0.5}},
    "S4": {"tie": "mid", "side": "centre", "tightness": 0.5, "neatness": 0.6, "half": True, "length": 0.24, "tail": {"length": 0.2, "wave": 0.3, "fullness": 0.3}},
    "S5": {"tie": "top", "side": "centre", "tightness": 0.8, "neatness": 0.7, "part": "none", "tail": "bun"},
    "S6": {"tie": "low", "side": "centre", "tightness": 0.6, "neatness": 0.7, "tail": {"kind": "plait", "length": 0.34, "fullness": 0.6}},
    "T53": TESS,
    "H0": {**TESS, "hairline": 0.0}, "H5": {**TESS, "hairline": 0.5}, "H10": {**TESS, "hairline": 1.0},
}
for n, st in R.items():
    with open(f"{d}/styles/{n}.json", "w") as f:
        f.write(json.dumps(st) + "\n")
