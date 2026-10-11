"""validate.py: the image reader's error against the mesh truth over the dressed validation shots (out/rule.json)."""
import json
import os

import numpy as np

from hifipushie import blockin_brows as bb, eye_ruler as er

G = os.environ["G"] + "/out"
R = json.load(open(G + "/rule.json"))
mm = bb._inputs("gd_T12")["mm"]
rows = {}


def add(k, d):
    rows.setdefault(k, []).append(d)


for tag, v in R.items():
    if not v.get("model"):
        continue
    for e, m in zip(v["read"], v["model"]):
        dc = (np.array(e["c"]) - np.array(m["c"])) * mm
        add("iris centre x", dc[0])
        add("iris centre y (down)", dc[1])
        for k in ("iris", "fissure", "tilt", "caruncle", "sclera_in", "sclera_out", "mrd1", "mrd2", "peak_u"):
            add(k, e[k] - m[k])
        for k, i in (("inner u", 0), ("inner v", 1)):
            add(k, e["inner"][i] - m["inner"][i])
        for k, i in (("outer u", 0), ("outer v", 1)):
            add(k, e["outer"][i] - m["outer"][i])
        for k in ("up", "lo", "open", "crease", "brow"):
            for j, x in enumerate(er.COLS):
                add(f"{k}[{x:+.0f}]", e[k][j] - m[k][j])
        add("crease[mid] vs platform", np.nanmean(np.array(e["crease"], float)[2:5] - np.array(m["platform"], float)[2:5]))
print(f"{'measure':24s} {'n':>3s} {'bias':>6s} {'sd':>6s} {'rms':>6s} {'max|e|':>6s}")
out = {}
for k, d in rows.items():
    d = np.array(d, float)
    d = d[np.isfinite(d)]
    if len(d) == 0:
        print(f"{k:24s}   0")
        continue
    out[k] = {"n": len(d), "bias": float(d.mean()), "sd": float(d.std()), "rms": float(np.sqrt((d ** 2).mean())),
              "max": float(np.abs(d).max())}
    print(f"{k:24s} {len(d):3d} {d.mean():6.2f} {d.std():6.2f} {np.sqrt((d ** 2).mean()):6.2f} {np.abs(d).max():6.2f}")
json.dump(out, open(G + "/validate.json", "w"), indent=1)
