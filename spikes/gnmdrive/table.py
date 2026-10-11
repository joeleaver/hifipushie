"""table.py <set> ...: score rows (from out/scores.json) as a markdown table + pass rates by grade / region."""
import json
import sys
from collections import defaultdict

import drv

sc = json.loads((drv.G / "out" / "scores.json").read_text())
for st in sys.argv[1:]:
    rows = sorted((v for k, v in sc.items() if k.endswith(":state") and v["case"].startswith(st + "_")), key=lambda r: r["case"])
    print(f"\n{st}: | case | grade | regions | kept / rejected | region closed | ID start -> end (closed) | face err | pass | oracle region / ID |")
    byg, byr = defaultdict(list), defaultdict(list)
    for r in rows:
        o = r["oracle_score"]
        orc = sum(o["region_closed"].values()) / len(o["region_closed"])
        print(f"| {r['case']} | {r['difficulty']} | {'+'.join(r['regions'])} | {r['n_moves']} / {r['n_rejected']} | {r['region_closed_mean']:.2f} | "
              f"{r['id'][0]:.3f} -> {r['id'][1]:.3f} ({r['id_closed']:.2f}) | {r['face_err'][0]:.1f} -> {r['face_err'][1]:.1f} | "
              f"{'PASS' if r['pass'] else '-'} | {orc:.2f} / {o['id']:.3f} |")
        byg[r["difficulty"]].append(r["pass"])
        for g in r["regions"]:
            byr[g].append(r["pass"])
    tot = [r["pass"] for r in rows]
    print(f"{st} pass {sum(tot)}/{len(tot)}; " + ", ".join(f"{g} {sum(v)}/{len(v)}" for g, v in byg.items()) + " | by region: "
          + ", ".join(f"{g} {sum(v)}/{len(v)}" for g, v in sorted(byr.items())))
    import numpy as np
    print(f"{st} mean region closed {np.mean([r['region_closed_mean'] for r in rows]):.2f}, mean ID closed "
          f"{np.mean([r['id_closed'] for r in rows]):.2f}, face err worse in {sum(r['face_err'][1] > r['face_err'][0] for r in rows)}")
