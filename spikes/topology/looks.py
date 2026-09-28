"""looks.py model out_prefix [resolution]: full-body look (front, side, three_quarter) and a face close-up, as PNGs
(server.look called directly, so the worktree's code renders)."""
import sys

from hifipushie import server, store
from hifipushie.spec import expand_mirror, resolve_point

name, out = sys.argv[1], sys.argv[2]
res = int(sys.argv[3]) if len(sys.argv) > 3 else 256
r = server.look(name, views=["front", "side", "three_quarter"], resolution=res, size=520, paint=False)
open(out + "_body.png", "wb").write(r[0].data)
s = expand_mirror(store.load(name))
h = resolve_point(s, "head")
r = server.look(name, views=["front", "side", "three_quarter"], focus=[0.0, float(h[1]) - 0.05, float(h[2]) + 0.0],
                zoom=6, resolution=res, size=520, paint=False)
open(out + "_face.png", "wb").write(r[0].data)
print(out)
