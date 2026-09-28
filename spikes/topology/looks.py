"""looks.py model out_prefix [resolution]: full-body look (front, side, three_quarter) and a face close-up, as PNGs
(server.look called directly, so the worktree's code renders)."""
import sys

from hifipushie import server, store
from hifipushie.spec import expand_mirror, resolve_point

name, out = sys.argv[1], sys.argv[2]
res = int(sys.argv[3]) if len(sys.argv) > 3 else 256
PAINT = len(sys.argv) > 4 and sys.argv[4] == "paint"
r = server.look(name, views=["front", "side", "three_quarter"], resolution=res, size=520, paint=PAINT)
open(out + "_body.png", "wb").write(r[0].data)
s = expand_mirror(store.load(name))
h = resolve_point(s, "head")
r = server.look(name, views=["front", "side", "three_quarter"], focus=[0.0, float(h[1]) - 0.05, float(h[2]) + 0.0],
                zoom=6, resolution=res, size=520, paint=PAINT)
open(out + "_face.png", "wb").write(r[0].data)
n = resolve_point(s, "neck")
r = server.look(name, views=["side", "three_quarter", "three_quarter_back"], focus=[0.0, float(n[1]), float(n[2]) + 0.02],
                zoom=4, resolution=res, size=520, paint=PAINT)
open(out + "_neck.png", "wb").write(r[0].data)
print(out)
