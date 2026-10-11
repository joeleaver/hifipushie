"""ceil.py: the test's ceiling. Would the ORACLE (<= 10 least-cost moves from the whole vocabulary, amounts refit) pass the
driver's PASS rule? Per set and region, from out/scores.json; + the start sizes (face err mm, ID distance)."""
import json
from collections import defaultdict

import drv

sc = json.loads((drv.G / "out" / "scores.json").read_text())
by = defaultdict(list)
reg = defaultdict(list)
seen = set()
for k, v in sorted(sc.items()):
    s, i = v["case"].split("_")
    pairset = {"m2": "s2", "m3": "s3", "m4": "s4", "m5": "s5", "g5": "s5"}.get(s, s)
    if (pairset, i) in seen:
        continue
    seen.add((pairset, i))
    o = v["oracle_score"]
    rc = sum(o["region_closed"].values()) / len(o["region_closed"])
    idc = 1 - o["id"] / v["id"][0]
    ok = rc >= 0.4 and idc >= 0.25
    by[pairset].append(ok)
    for r in v["regions"]:
        reg[r].append(ok)
    print(pairset, i, v["difficulty"][:4], "+".join(v["regions"]).ljust(18), f"start face {v['face_err'][0]:.1f} mm id {v['id'][0]:.3f}",
          f"oracle region {rc:.2f} id {idc:.2f}", "PASS" if ok else "-")
print({k: f"{sum(x)}/{len(x)}" for k, x in by.items()})
print({k: f"{sum(x)}/{len(x)}" for k, x in sorted(reg.items())})
