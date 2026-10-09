"""Rows of MM/out/fits.json side by side on the SAME subjects.  run.sh cmp.py "<base prefix>" "<prefix>" ..."""
import json, sys
import numpy as np
import mm, rs
res = json.loads((mm.MM / "out" / "fits.json").read_text())
pick = [next(m for m in res if m.startswith(w)) for w in sys.argv[1:]]
for tag in ("S", "O", ""):
    print()
    for m in pick[1:]:
        subs = [s for s in res[m] if isinstance(res[m][s], dict) and s in res[pick[0]] and s.startswith(tag)]
        if not subs:
            continue
        a = {k: np.mean([res[pick[0]][s][k] for s in subs]) for k in rs.REGIONS}
        b = {k: np.mean([res[m][s][k] for s in subs]) for k in rs.REGIONS}
        print(f"{tag or 'all':3s} n {len(subs):2d} {pick[0][:44]:44s} " + rs.row(a))
        print(f"{'':8s} {m[:44]:44s} " + rs.row(b))
        if all("surf" in res[x][s] for x in (pick[0], m) for s in subs):
            a = {k: np.mean([res[pick[0]][s]["surf"][k] for s in subs]) for k in rs.REGIONS}
            b = {k: np.mean([res[m][s]["surf"][k] for s in subs]) for k in rs.REGIONS}
            print(f"{'':8s} {'  to the true surface: ' + pick[0][:20]:44s} " + rs.row(a))
            print(f"{'':8s} {'  to the true surface: ' + m[:20]:44s} " + rs.row(b))
print(" " * 53 + rs.HEADER)
