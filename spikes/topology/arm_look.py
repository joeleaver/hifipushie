"""arm_look.py model out.png [shading]: the right upper arm and elbow close up (front, three-quarter), raking light."""
import sys

from hifipushie import server, store
from hifipushie.spec import expand_mirror, resolve_point

name, out = sys.argv[1], sys.argv[2]
shading = sys.argv[3] if len(sys.argv) > 3 else "raking"
s = expand_mirror(store.load(name))
c = 0.5 * (resolve_point(s, "shoulder.R") + resolve_point(s, "elbow.R"))
r = server.look(name, views=["front", "three_quarter", "back"], focus=[float(x) for x in c], zoom=3.2, resolution=256,
                size=480, shading=shading, paint=False)
open(out, "wb").write(r[0].data)
print(out)
