"""rescore.py <dir> <set>...: driven cases (state.json) and their phrase oracles graded with BOTH pass rules (score2).
<dir> = the test's scratch (its cases/ and hidden/): /mnt/data/hifipushie/gnmdrive for the old sets, $G for s6.
-> $G/out/rescore_<set>.json and a table: driver old / new, oracle old / new, by region and difficulty."""
import json
import os
import sys
from pathlib import Path

import numpy as np

import score2
from hifipushie import blockin as bi

G = os.environ["G"]
D = Path(sys.argv[1])
for s in sys.argv[2:]:
    out = {}
    for i in range(14):
        case = f"{s}_{i:02d}"
        hp, sp = D / "hidden" / f"{case}.json", D / "cases" / case / "state.json"
        if not hp.exists() or not sp.exists():
            continue
        h, st = json.loads(hp.read_text()), json.loads(sp.read_text())
        cA, cB, c = np.array(h["A"]), np.array(h["B"]), np.array(st["c"])
        regs = [x["region"] for x in h["changes"]]
        cs = [c]
        op = D / "hidden" / f"{case}_oracle.json"
        if op.exists():
            cO = cA.copy()
            for k, v in json.loads(op.read_text())["moves"].items():
                cO = cO + v * bi.direction(k)
            cs.append(cO)
        g = score2.grade(cA, cB, cs, regs)
        out[case] = {"difficulty": h["difficulty"], "regions": regs, "driver": g[0], "oracle": g[1] if len(g) > 1 else None,
                     "moves": [m["moves"] for m in st["moves"]], "rejected": len(st.get("rejected", []))}
        print(case, h["difficulty"][:4], "+".join(regs).ljust(18), " | ".join(
            f"{k} region {x['region']:.2f} id {x['id']:.2f} outline {x['outline']:.2f} face {x['face'][0]:.1f}->{x['face'][1]:.1f} "
            f"{'PASS' if x['pass'] else '-'}{'' if x['pass'] == x['pass_old'] else ' (old rule: ' + ('PASS' if x['pass_old'] else '-') + ')'}"
            for k, x in zip(("driver", "oracle"), g)), f"| {len(st['moves'])} kept, {len(st.get('rejected', []))} rejected", flush=True)
        json.dump(out, open(f"{G}/out/rescore_{s}.json", "w"), indent=1)
    n = len(out)
    for who in ("driver", "oracle"):
        R = [r for r in out.values() if r[who]]
        if R:
            print(f"== {s} {who}: new rule {sum(r[who]['pass'] for r in R)}/{len(R)}, old rule {sum(r[who]['pass_old'] for r in R)}/{len(R)}")
