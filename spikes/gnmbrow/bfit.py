"""bfit.py <model> [<out>]: blockin_brows.fit on the model (printed); with <out>, written to that scratch model."""
import sys

from hifipushie import blockin_brows as bb

name = sys.argv[1]
print(bb.check(name)["text"])
r = bb.apply(name, out=sys.argv[2], log=print) if len(sys.argv) > 2 else bb.fit(name, log=print)
print(r["text"])
print("before", bb._json(r["before"]))
print("after ", bb._json(r["after"]))
print(r["brows"])
