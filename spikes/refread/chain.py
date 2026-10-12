"""chain.py <src> <prefix> <n calls> [key=value ...]: block_in_solve called n times in a row (blockin.solve_step: the
first with cameras="free", the rest "trust"), results <prefix>01 .. ; per call: reads by type, |dc|, |c|, the largest
component, the sigma scales, the table's passes and its rows that are out. keys go to solve_step (parse=auto|0|1,
anchors=.., normals=0|1, adapt=0|1, lids=.., lips=..); first=trust starts with trusted cameras."""
import sys, time
import numpy as np
from hifipushie import blockin as bi, resources, store

src, pre, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
kw = {a: {"0": False, "1": True}.get(b, b) for a, b in (x.split("=", 1) for x in sys.argv[4:])}
first = kw.pop("first", "free")
rest = kw.pop("rest", "free")
for i in range(1, n + 1):
    out = f"{pre}{i:02d}"
    if (store.HOME / out / "spec.json").exists():
        print(out, "exists: skipped")
        src = out
        continue
    t = time.time()
    rep = bi.solve_step(src, out=out, cameras=first if i == 1 else rest, **kw)   # (numpy, one process, ~2 GB: no heavy slot)
    so = rep["solve"]
    c = bi.identity(store.load(out))
    print(f"== {src} -> {out} ({time.time() - t:.0f} s): reads {so['n']}")
    print(f"   |dc| {so['dc']:.2f}  |c| {so['c']:.2f}  largest comp {so['max_sd']:.2f} sd (#{int(np.abs(c).argmax())}); past 2.5 sd: {int((np.abs(c) > 2.5).sum())}; "
          f"sigma scales > 1.2: { {k: v for k, v in so['sig_scale'].items() if v > 1.2} }")
    print(f"   cameras' whole move since the start: {so['cameras']}; this call: {so['camera_step']}; relax x{so['relax']:.2f}")
    print("   table:", rep["entry"]["passes"])
    for g, rows in rep["table"].items():
        for r in rows:
            if not r["ok"] and "flag" not in r:
                print(f"      OUT {r['id']:20s} {str(r['view']):12s} {r['diff']:+.2f} (tol {r['tol']:.2f}) {r['unit']}")
    for x in so.get("notes") or []:
        print("   note:", x)
    src = out
