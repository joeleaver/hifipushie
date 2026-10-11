"""cmp.py <no-manual set> <manual set>: the two arms side by side from out/scores.json (region closed, ID closed, face
error, kept moves, pass) + the oracle's region closure, and each arm's kept moves with their closure (-v)."""
import json
import sys

import drv

sc = json.loads((drv.G / "out" / "scores.json").read_text())
sa, sb = sys.argv[1], sys.argv[2]
verbose = "-v" in sys.argv


def f(r):
    if not r:
        return " " * 47
    return (f"{r['region_closed_mean']:5.2f} id {r['id_closed']:5.2f} face {r['face_err'][0]:.1f}->{r['face_err'][1]:.1f} "
            f"n{r['n_moves']}/{r['n_rejected']} {'PASS' if r['pass'] else '-   '}")


n = [0, 0]
for i in range(14):
    a, b = sc.get(f"{sa}_{i:02d}:state"), sc.get(f"{sb}_{i:02d}:state")
    r = b or a
    if not r:
        continue
    n[0] += bool(a and a["pass"])
    n[1] += bool(b and b["pass"])
    print(f"{i:02d} {r['difficulty'][:4]} {'+'.join(r['regions']):18s} {f(a)} | {f(b)} | orc "
          f"{sum(r['oracle_score']['region_closed'].values()) / len(r['regions']):.2f} id0 {r['id'][0]:.3f}")
    if verbose:
        for arm, x in ((sa, a), (sb, b)):
            if x:
                print("     ", arm, "; ".join(f"{json.dumps(s['moves'])} {s['closed']:+.2f}" for s in x["steps"]))
                print("      per region:", x["region_closed"])
        print("      oracle:", json.dumps(r["oracle"]["moves"]))
print("pass", sa, n[0], sb, n[1])
