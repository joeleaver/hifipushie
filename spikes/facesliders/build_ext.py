"""build_ext.py: faceext.build() and a report: per extension the share GNM's identity explained, the field's size."""
import numpy as np

from hifipushie import faceext

old = dict(faceext.table())
out = faceext.build()
for k in faceext.EXT:
    d = out[k]
    m = np.linalg.norm(d, axis=1)
    print(f"{k:20s} the identity's cheap directions ({int(out[k + '__cheap_dirs'])}) make {float(out[k + '__explained']):.2f}; scale {float(out[k + '__scale']):.2f}, max {m.max() * 1000:.2f} mm, "
          f"vertices > 0.2 mm {int((m > 2e-4).sum())}")
    if k in old:
        print(f"   was: scale {float(old[k + '__scale']):.2f}, max {np.linalg.norm(old[k], axis=1).max() * 1000:.2f} mm")
# what the crease hold changed: the field before / after it, at +1
for k in faceext.EXT:
    h = faceext.HOLD_CREASES
    faceext.HOLD_CREASES = 0.0
    d0 = faceext.field(k)[0]
    faceext.HOLD_CREASES = h
    d1 = faceext.field(k)[0]
    print(f"{k:20s} crease hold changed {np.linalg.norm(d1 - d0) / np.linalg.norm(d0):.3f} of the field (rms), "
          f"at most {np.linalg.norm(d1 - d0, axis=1).max() * 1000:.2f} mm")
# ... on the visible lip (facing forward, outside the contact ring) vs inside the mouth
from hifipushie import faceslide  # noqa: E402
T = faceslide.template()
R = faceslide._lip_rings()
inner = np.zeros(len(T["X"]), bool)
for r in R["rings"][:R["contact"] + 1]:
    inner[r] = True
vis = (T["n"][:, 2] > 0.3) & ~inner
for k in faceext.EXT:
    h = faceext.HOLD_CREASES
    faceext.HOLD_CREASES = 0.0
    d0 = faceext.field(k)[0]
    faceext.HOLD_CREASES = h
    d1 = faceext.field(k)[0]
    for nm, s in (("visible", vis), ("inside", inner)):
        print(f"   {k} {nm}: field rms {np.linalg.norm(d0[s]) * 1e3:.2f}, change rms {np.linalg.norm((d1 - d0)[s]) * 1e3:.2f}, "
              f"max change {np.linalg.norm((d1 - d0)[s], axis=1).max() * 1e3:.2f} mm")
