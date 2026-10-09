"""seam1.py <seed> <sex>: seam.check on a wide-spread humans.spec identity (the test's), printing every bad place."""
import sys

import seam
from hifipushie import humans

sp = humans.spec(age=35, sex=float(sys.argv[2]), seed=int(sys.argv[1]), skin=False, source="human")
sp["base"]["head"]["spread"] = 1.2
sp["base"]["head"].pop("mouth_gap", None)
sp["base"]["head"]["lip_seal"] = 1.0
seam.check(sp)
