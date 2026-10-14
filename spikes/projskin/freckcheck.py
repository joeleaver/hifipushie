"""freckcheck.py <model> ...: the stack's freckle density line per model (decompose only, nothing saved). LIGHT."""
import sys
from hifipushie import skin_layers as sl
for m in sys.argv[1:]:
    for lips in ("texels",):
        r = sl.decompose(m, log=lambda s: None)
        print(m, " | ".join(l.strip() for l in r["text"].split("\n") if "density map" in l), flush=True)
