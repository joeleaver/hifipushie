"""pread.py <model> [rounds=4]: READ ONLY: the orbit rows of a block-in model against its reference pictures, from
front + profile, front + 3/4 and all three (face_ruler.compare(views=)); the cameras' yaw / pitch the solve took.
-> out/pread_<model>.json + the tables."""
import json
import os
import sys

import numpy as np

from hifipushie import blockin as bi, face_ruler as fr, gnm_mm

G = os.environ["G"] + "/out"
name = sys.argv[1]
rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 4
rj = bi._refs(name)
kinds = [fr.kind_of(v.get("yaw", 0)) for v in rj["views"]]
print(name, "views:", kinds)
out = {}
subs = {"front + profile": ("front", "profile"), "front + 3/4": ("front", "3q"), "all three": ("front", "3q", "profile"),
        "front alone": ("front",)}
for lab, use in subs.items():
    vi = [i for i, k in enumerate(kinds) if k in use]
    if len(vi) != len(use):
        continue
    res = fr.compare(name, rounds=rounds, views=vi)
    print(f"\n=== {lab} ({res['n']})")
    print(fr.orbit_text(res["orbit"]))
    rows = {r["measure"]: r for r in res["rows"]}
    print("  measures: " + "; ".join(f"{m} {rows[m]['gap']:+.1f} +-{rows[m]['err']:.1f}" for m in gnm_mm.ORBIT))
    for n in res["notes"]:
        print("  " + n)
    lim = [(ob["view"], ob["name"], round(ob["o"], 2), round(ob.get("score", 0), 3), round(ob.get("open", 0), 2)) for ob in res["obs"] if ob["type"] == "limbus"]
    print("  limbus reads left after the solve (mm):", lim)
    out[lab] = {"orbit": res["orbit"], "rows": {m: [rows[m]["gap"], rows[m]["err"]] for m in rows}, "cam_done": res["cam_done"],
                "cam_post": res["cam_post"], "n": res["n"], "dc": np.asarray(res["dc"]).tolist()}
    json.dump(out, open(f"{G}/pread_{name}.json", "w"))
