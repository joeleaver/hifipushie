"""estep.py <src> <out>: the eye step (blockin_eyes.eye_step, default crease template) written as a scratch model;
or estep.py check <model>: the iris check only."""
import sys

from hifipushie import blockin_eyes as be

if sys.argv[1] == "check":
    print(be.iris_check(sys.argv[2])["text"])
else:
    rep = be.eye_step(sys.argv[1], out=sys.argv[2], log=lambda m: print(m, flush=True))
    print(be.text(rep["eyes"]))
    print("done", sys.argv[2])
