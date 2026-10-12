"""solve.py <from> <prefix> <first index> <n calls> [first cameras]: block_in_solve calls in a row (first call's camera
setting, default "refit", then "free"), each a new model <prefix><nn>; stops when the reply's |dc| < 2."""
import re, sys
from hifipushie import server
src, pre, i0, n = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
cam = sys.argv[5] if len(sys.argv) > 5 else "refit"
for i in range(i0, i0 + n):
    out = f"{pre}{i:02d}"
    r = server.block_in_solve(src, out=out, cameras=cam, save=f"/mnt/data/hifipushie/garrettgood/out/{out}.png")
    t = "\n".join(x for x in r if isinstance(x, str)) if not isinstance(r, str) else r
    print(f"===== {src} -> {out} (cameras {cam})\n{t}", flush=True)
    src, cam = out, "free"
    m = re.search(r"\|dc\|\s*=?\s*([0-9.]+)", t)
    if m and float(m.group(1)) < 2.0:
        print("settled: |dc| < 2")
        break
