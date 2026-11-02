"""gexsum.py: the expression test's table (gexpr.py's sets, solvecams' head a as the truth): the identity-only solve on
the NEUTRAL front, on the slightly SMILING front, the smiling front with the per-view expression nuisance
(solve_step(expression="view")), each with dense off / on where run: errmap against the true identity, lips signed
(noselip), what the solve said about the lip / lid reads, the expression it fitted."""
import json
import numpy as np
import gt, noselip
from hifipushie import blockin as bi, store

ct = bi.identity(store.load("sc_a_T"))
c0 = bi.identity(store.load("sc_a_A00"))
CH = {"neutral front, off": "gt_exn_A", "neutral front, on": "gt_exnd_A", "smiling front, off": "gt_exs_A", "smiling front, on": "gt_exsd_A",
      "smiling front, off, expression=view": "gt_exsv_A", "smiling front, off: 4 calls, expression_step, 2 calls": "gt_exse_A"}
recs = {k: json.loads((gt.OUT / "chains" / f"{v}.json").read_text()) for k, v in CH.items() if (gt.OUT / "chains" / f"{v}.json").exists()}
print("\n#### expression test (known GNM head a; truth = its NEUTRAL identity): against the truth, mm\n")
print("| chain | calls | face rms | lower face rms | chin | jaw_width | mouth_width | what the solve said of lips / lids | fitted expression (front view) |")
print("|---|---|---|---|---|---|---|---|---|")
models = {}
for k, r in recs.items():
    c = r["calls"][-1]
    said = "; ".join(x[:230] for x in (c.get("notes") or []) if ("lip" in x or "lid" in x) and x[:4] in ("NOIS", "DISA", "INCO"))
    rjm = json.loads((store.HOME / c["model"] / "human_refs.json").read_text())
    ex = (rjm.get("expressions") or [None])[0]
    se = (rjm.get("blockin") or {}).get("solve_expression")
    exs = (", ".join(f"{a} {b:+.2f}" for a, b in sorted((ex or {}).items(), key=lambda t: -abs(t[1]))[:4]) if ex else "") + (f" solve: {json.dumps(se)[:160]}" if se else "") or "-"
    print(f"| {k} | {len(r['calls']) - 1} | {c['face']:.2f} | {c['low']:.2f} | {c['chin']:.2f} | {c['meas']['jaw_width']:+.1f} | {c['meas']['mouth_width']:+.1f} | {said or '-'} | {exs} |")
    models[k] = bi.identity(store.load(c["model"]))
s0 = next(iter(recs.values()))["calls"][0]
print(f"| start (class mean) | 0 | {s0['face']:.2f} | {s0['low']:.2f} | {s0['chin']:.2f} | {s0['meas']['jaw_width']:+.1f} | {s0['meas']['mouth_width']:+.1f} | | |")
cmp = noselip.compare(ct, c0, models)
print(noselip.text(cmp, "\n#### expression test: nose and lips, signed (solved - true identity, mm)\n"))
