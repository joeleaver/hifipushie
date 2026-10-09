"""nosesens.py <model> <slider>: the shading dorsal widths (gm.measure) at the slider -1 / 0 / +1 on the model."""
import copy
import sys

import gm
from hifipushie import store

b0 = store.load(sys.argv[1])["base"]
for v in (-1.0, 0.0, 1.0):
    b = copy.deepcopy(b0)
    b["head"].setdefault("sliders", {})[sys.argv[2]] = v
    ph, md, _ = gm.measure(sys.argv[1], b)
    print(sys.argv[2], v, {k: round(md[k], 2) for k in ("radix_w", "dorsum_w", "alar_width", "nose_length")},
          "photo", {k: round(ph[k], 2) for k in ("radix_w", "dorsum_w")})
