"""grid.py <out.png> <title> [tile=N] cols=<label>:<model>,<label>:<model>,.. rows=<label>:<tile>[:<ref tile>],..
A sheet with a REFERENCE column first (the reference crop <ref tile>_ref.png of the model named ref=<model>, when the
row gives one) and one column per model; tiles are out/<model>/<tile>.png. LARGE labels."""
import os
import sys

from strip import row, stack

O = "/mnt/data/hifipushie/gnmnative/out"
out, title = sys.argv[1:3]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
T = int(kw.get("tile", 480))
cols = [c.split(":") for c in kw["cols"].split(",")]
rows = [r.split(":") for r in kw["rows"].split(",")]
ref = kw.get("ref")


def t(m, f):
    p = f"{O}/{m}/{f}.png"
    return p if os.path.exists(p) else None


R = []
for k, r in enumerate(rows):
    lab, tile = r[0], r[1]
    rt = t(ref, r[2] + "_ref") if (ref and len(r) > 2) else None
    items = [(("REFERENCE: " if k == 0 else "") + lab, rt)] + [(c[0] if k == 0 else "", t(c[1], tile)) for c in cols]
    R.append(row(items, T, fs=max(16, T // 17)))
os.makedirs(os.path.dirname(out), exist_ok=True)
stack(R, title, fs=40).save(out)
print(out)
