"""build_ext.py: faceext.build() and a report: per extension the share GNM's identity explained, the field's size."""
import numpy as np

from hifipushie import faceext

out = faceext.build()
for k in faceext.EXT:
    d = out[k]
    m = np.linalg.norm(d, axis=1)
    print(f"{k:20s} the identity's cheap directions ({int(out[k + '__cheap_dirs'])}) make {float(out[k + '__explained']):.2f}; scale {float(out[k + '__scale']):.2f}, max {m.max() * 1000:.2f} mm, "
          f"vertices > 0.2 mm {int((m > 2e-4).sum())}")
