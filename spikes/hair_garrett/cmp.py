"""cmp.py <model> [views=0,1,2] [tag=]: hair_read.compare on the model's tiles $TOUT/s_<model><tag>_v<i>.png (hgshots.py)
against the pictures; prints the table, saves $TOUT/cmp_<model><tag>.txt."""
import os
import sys

from hifipushie import hair_read

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
OUT = os.environ["TOUT"]
tag = kw.get("tag", "")
views = [int(v) for v in kw.get("views", "0,1,2").split(",")]
r = hair_read.compare(m, {i: f"{OUT}/s_{m}{tag}_v{i}.png" for i in views})
print(r["text"])
open(f"{OUT}/cmp_{m}{tag}.txt", "w").write(r["text"])
