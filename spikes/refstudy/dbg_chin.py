"""What made the 3 cm chin nudge BROKEN before the sliver rule, and what is left of it now."""
import sys

sys.path.insert(0, "tests")
import test_humanfit as t
from hifipushie import humanfit as hf

b = t.base()
for sl, sq in ((0.0, 0.0), (hf.SLIVER, hf.SLIVER_SQUEEZE), (0.0015, 0.0008), (0.0012, 0.0008)):
    hf.SLIVER, hf.SLIVER_SQUEEZE = sl, sq
    nb, rep = hf.nudge(b, "chin", move=[0.0, 0.0, -0.03], force=True)
    print(sl, sq, hf.verdict(rep["integrity"])[:400].replace("\n", " | "))
