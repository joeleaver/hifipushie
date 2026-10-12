"""tab.py <model> ...: the block-in target table of each model (picture vs model through the fitted cameras), side by
side: group scores, then every row's diff per model."""
import sys
from hifipushie import blockin as bi
T = {m: bi.table(m) for m in sys.argv[1:]}
for m, t in T.items():
    cnt = {g: (sum(r["ok"] for r in rs if not r.get("flag")), sum(1 for r in rs if not r.get("flag"))) for g, rs in t.items()}
    print(m, "; ".join(f"{g} {a}/{b}" for g, (a, b) in cnt.items()), "| total", sum(a for a, _ in cnt.values()), "/", sum(b for _, b in cnt.values()))
m0 = sys.argv[1]
print(f"\n{'row':22s} {'view':14s} {'photo':>8s} " + " ".join(f"{m:>18s}" for m in T))
for g, rs in T[m0].items():
    print("==", g)
    for r in rs:
        cells = []
        for m in T:
            q = [x for x in T[m][g] if x["id"] == r["id"] and x["view"] == r["view"]]
            cells.append(f"{q[0]['diff']:+8.2f} {'ok  ' if q[0]['ok'] else 'MISS'}{' flag' if q[0].get('flag') else '     '}" if q else " " * 18)
        print(f"{r['id']:22s} {str(r['view']):14s} {r['photo']:8.2f} " + " ".join(cells) + f"  tol {r['tol']}")
