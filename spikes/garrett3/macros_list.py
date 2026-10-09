"""macros_list.py [model]: humanmacro's macro names (and a model's read in sigmas)."""
import sys

from hifipushie import humanfit, humanmacro as hm, store

print(list(hm.NAMES))
if len(sys.argv) > 1:
    z = hm.read(humanfit.identity(store.load(sys.argv[1])["base"]))
    print({k: round(float(v), 2) for k, v in z.items()})
