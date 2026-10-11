"""pool.py: pass rates by arm (no manual = s1..s4, manual = m2..m4), grade and region, from out/scores.json."""
import json
from collections import defaultdict

import numpy as np

import drv

sc = {k: v for k, v in json.loads((drv.G / "out" / "scores.json").read_text()).items() if k.endswith(":state")}
arms = {"no manual (s1-s4)": ("s1", "s2", "s3", "s4"), "no manual, matched (s2-s4)": ("s2", "s3", "s4"),
        "manual v1 (m2)": ("m2",), "manual v2 (m3)": ("m3",), "manual v3 + mm: (m4)": ("m4",),
        "manual, all (m2-m4)": ("m2", "m3", "m4")}
for arm, sets in arms.items():
    rows = [v for v in sc.values() if v["case"].split("_")[0] in sets]
    if not rows:
        continue
    g, r = defaultdict(list), defaultdict(list)
    for v in rows:
        g[v["difficulty"]].append(v["pass"])
        for x in v["regions"]:
            r[x].append(v["pass"])
    print(f"{arm}: {sum(v['pass'] for v in rows)}/{len(rows)} | " + ", ".join(f"{k} {sum(x)}/{len(x)}" for k, x in g.items())
          + f" | region closed {np.mean([v['region_closed_mean'] for v in rows]):.2f}, ID closed {np.mean([v['id_closed'] for v in rows]):.2f}"
          + " | " + ", ".join(f"{k} {sum(x)}/{len(x)}" for k, x in sorted(r.items())))
