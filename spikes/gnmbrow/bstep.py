"""bstep.py <src> <out> '<moves json>' [why]: one block-in step onto a scratch model (blockin.step)."""
import json
import sys

from hifipushie import blockin as bi

rep = bi.step(sys.argv[1], json.loads(sys.argv[3]), out=sys.argv[2], seen=sys.argv[4] if len(sys.argv) > 4 else "gnmbrow",
              why=sys.argv[5] if len(sys.argv) > 5 else "")
print(bi.step_text(rep))
print("done", sys.argv[2])
