"""mmdiff.py <a> <b>: gnm_mm's 23 measures b - a (mm, GNM frame) + |dc|; identity sources as lidstruct.ident."""
import sys

import numpy as np

import lidstruct as ls
from hifipushie import gnm_controls as gc, gnm_mm

a, b = ls.ident(sys.argv[1]), ls.ident(sys.argv[2])
ra, rb = gnm_mm.readers(gc.vertices(a)), gnm_mm.readers(gc.vertices(b))
d = {k: float(rb[k] - ra[k]) for k in gnm_mm.NAMES}
print(f"|dc| {np.linalg.norm(b - a):.2f}; largest: " + ", ".join(f"{k} {v:+.2f}" for k, v in sorted(d.items(), key=lambda x: -abs(x[1]))[:8]) + f"; rms {np.sqrt(np.mean(np.square(list(d.values())))):.2f} mm")
