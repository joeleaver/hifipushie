"""hscore.py <k> <label>=<chain prefix> ..: the held-out table for one subject: per chain's LAST call, the solved identity
against the truth (the pose's Part 1 fit = rm_<k>_T's identity): errmap's face / lower-face rms and, after errmap's
similarity, groundtruth's signed nose / lip measures (noselip.py) and the front camera's distance error. Records:
$HIFIPUSHIE_GROUNDTRUTH/out/chains/<prefix>.json (gchain.py). Also the START (call 0) of the first chain.
Vertex measures under ~1.3 mm are inside the truth's own slack (groundtruth: two direct fits differ 0.6-1.3 mm)."""
import json, os, sys
import numpy as np
sys.path.insert(0, "/home/joe/dev/hifipushie/.claude/worktrees/groundtruth/spikes/groundtruth")
import errmap, noselip
from hifipushie import blockin as bi, store

k = sys.argv[1]
chains = dict(a.split("=") for a in sys.argv[2:])
ct = bi.identity(store.load(f"rm_{k}_T"))
mt = noselip.measures(ct)
M = ("nose_base_width", "alar_width", "tip_width", "tip_radius_h", "nose_length", "nose_projection", "mouth_width", "upper_vermilion_mid", "lower_vermilion_mid")
OUT = os.environ["HIFIPUSHIE_GROUNDTRUTH"] + "/out/chains"
rows = []
for lab, pre in chains.items():
    f = f"{OUT}/{pre}.json"
    if not os.path.exists(f):
        continue
    r = json.load(open(f))
    for nm, call in ((("start", r["calls"][0]),) if not rows else ()) + ((lab, r["calls"][-1]),):
        c = bi.identity(store.load(call["model"]))
        e = errmap.rms(c, ct)
        m = noselip.measures(c, e["scale"])
        cam = list(call["cams"].values())[0]
        rows.append({"label": nm, "n": len(r["calls"]) - 1 if nm != "start" else 0, "face": e["face"], "low": e["low"], **{x: m[x] - mt[x] for x in M},
                     "dist": cam.get("dist")})
print(f"\n#### {k}: solved - truth (mm), last call; truth nose base {mt['nose_base_width']:.1f}, alar {mt['alar_width']:.1f}, mouth {mt['mouth_width']:.1f}\n")
print("| chain | calls | face / low rms | " + " | ".join(M) + " | front dist % |")
print("|---|---|---|" + "---|" * (len(M) + 1))
for r in rows:
    print(f"| {r['label']} | {r['n']} | {r['face']:.2f} / {r['low']:.2f} | " + " | ".join(f"{r[x]:+.1f}" for x in M) + f" | {r['dist']:+.0f} |")
json.dump(rows, open(f"{os.environ['HIFIPUSHIE_READMIX']}/out/hscore_{k}.json", "w"))
