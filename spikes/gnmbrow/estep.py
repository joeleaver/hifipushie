"""estep.py <src> <out>: the eye step (blockin_eyes.eye_step, default crease template) written as a scratch model;
or estep.py check <model>: the iris check only."""
import sys

from hifipushie import blockin_eyes as be
from hifipushie import blockin_eyes_evidence, blockin_eyes_solve

if sys.argv[1] == "check":
    print(blockin_eyes_evidence.iris_check(sys.argv[2])["text"])
else:
    rep = blockin_eyes_solve.eye_step(sys.argv[1], out=sys.argv[2], log=lambda m: print(m, flush=True))
    print(blockin_eyes_solve.text(rep["eyes"]))
    print("done", sys.argv[2])
