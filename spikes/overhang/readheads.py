"""readheads.py <label>=<identity source | npz> ...: ohlib.read (overhang, turn, crease ring / height) + lidstruct's
numbers for named heads, the same reader for all."""
import sys

import numpy as np

import lidstruct as ls
import ohlib as oh
import sect

ch = oh.chains(7.0)
for a in sys.argv[1:]:
    lab, src = a.split("=", 1)
    c, e = sect.load(src)
    q = oh.read(oh.verts(c, e), ch)
    try:
        m = ls.mean_structure(c, e)
        extra = f"| lidstruct: crease_h {m['crease_h']:.1f} platform {m['platform_s']:.2f} tuck {m['tuck']:.0f} wall {m['wall']:.0f} hang {m['hang']:.2f}"
    except (IndexError, KeyError, ValueError) as ex:
        extra = f"| lidstruct failed ({type(ex).__name__})"
    print(f"{lab:14s} |c| {np.linalg.norm(c):5.2f} {oh.fmt(q)} {extra}")
