"""lists.py <dir>: writes the batch lists (batch.sh <list>): riffs.txt (round three's six riff styles, as th_Q1..Q6),
tess.txt (Tess's style), dial.txt (fullness x wave, th_D<f><w>)."""
import json, sys

d = sys.argv[1]
R = {
    "Q1": {"tie": "high", "side": "centre", "tightness": 0.9, "neatness": 0.85, "part": "none", "tail": {"length": 0.32, "wave": 0.1, "fullness": 0.6}},
    "Q2": {"tie": "low", "side": "centre", "tightness": 0.5, "neatness": 0.6, "tail": {"length": 0.28, "wave": 0.3, "fullness": 0.5}},
    "Q3": {"tie": "low", "side": "left", "tightness": 0.85, "neatness": 0.95, "tail": {"length": 0.24, "wave": 0.1, "fullness": 0.5}},
    "Q4": {"tie": "mid", "side": "centre", "tightness": 0.5, "neatness": 0.6, "half": True, "length": 0.24, "tail": {"length": 0.2, "wave": 0.3, "fullness": 0.3}},
    "Q5": {"tie": "top", "side": "centre", "tightness": 0.8, "neatness": 0.7, "part": "none", "tail": "bun"},
    "Q6": {"tie": "low", "side": "centre", "tightness": 0.6, "neatness": 0.7, "tail": {"kind": "plait", "length": 0.34, "fullness": 0.6}},
}
T = {"T47": {"tie": "low", "side": "left", "tightness": 0.85, "neatness": 0.95, "wisps": {"amount": 0.7},
             "tail": {"length": 0.24, "wave": 0.6, "fullness": 0.75}},
     "T48": {"tie": "low", "side": "left", "tightness": 0.85, "neatness": 0.95, "wisps": {"amount": 1.0, "softness": 0.7},
             "tail": {"length": 0.23, "wave": 0.6, "fullness": 0.6}}}
D = {f"D{i}{j}": {"tie": "low", "side": "centre", "tightness": 0.85, "neatness": 0.95, "wisps": 0,
                  "tail": {"length": 0.26, "wave": wv, "fullness": fu}}
     for i, fu in enumerate((0.0, 0.5, 1.0)) for j, wv in enumerate((0.0, 0.5, 1.0))}
for name, L in (("riffs", R), ("tess", T), ("dial", D)):
    with open(f"{d}/{name}.txt", "w") as f:
        for n, st in L.items():
            f.write(f"{n}|{json.dumps(st)}\n")
