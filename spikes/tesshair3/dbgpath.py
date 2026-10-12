"""dbgpath.py <model> [az,el_over_line ...]: the flow path of single roots (az, el, hairline el there) step by step."""
import sys
import numpy as np
from hifipushie import hair, hair_flow, hair_tied, store

m = sys.argv[1]
sp = store.load(m)
sc = hair.scalp(m, sp)
g = hair.fit_to_head(hair.groom_params(sp), sc)
line = hair.hairline(sc, g)
tp = hair_tied.params(g["tie"])[0]
ga = tp["gather"]
print({k: ga[k] for k in ("sag", "overhang", "ears", "part_push", "part_length", "puff", "root_lift", "body")})
print("hairline el at az 0..180 step 15:", np.round(hair._line_at(line, np.arange(0, 181, 15.0)), 0).tolist())
rng = np.random.default_rng(0)
for a in sys.argv[2:] or ["20,6", "40,6", "60,6", "10,20", "-20,6", "-40,6"]:
    az, de = (float(x) for x in a.split(","))
    el = float(hair._line_at(line, az)) + de
    D, w = hair_flow.paths(sc, line, hair.dirs(np.array([az]), np.array([el])), hair.dirs(*tp["at"]), hair._part_x(g), ga, rng, 12)
    aa, ee = hair.az_el(D[0])
    ll = hair._line_at(line, aa)
    print(a, "len", round(float(np.degrees(w[0]))), " ".join(f"{((x + 180) % 360) - 180:.0f}/{y:.0f}({y - z:+.0f})" for x, y, z in zip(aa, ee, ll)))
