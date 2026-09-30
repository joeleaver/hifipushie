"""A fast look at a terrain's rock for design rounds: the tiles round one place exported with one LOD at a low texel
density and no checks (`terrain_mesh.preview_tiles`, the export's own code path), then rendered.
uv run python examples/terrain_rock_look.py <spec.json> <out dir> <at: address or x,y> [radius m] [texels/m]
Views: an eye 60 m out from `at` looking at it (from the 4 compass sides that aren't inside rock), plus a close one."""
import json
import sys
import time
from pathlib import Path

import numpy as np

from hifipushie import terrain, terrain_mesh

spec, out = Path(sys.argv[1]), Path(sys.argv[2])
at = [float(v) for v in sys.argv[3].split(",")] if "," in sys.argv[3] else sys.argv[3]
radius = float(sys.argv[4]) if len(sys.argv) > 4 else 40.0
density = float(sys.argv[5]) if len(sys.argv) > 5 else 6.0
t0 = time.time()
T = terrain.load(spec)
print(f"compiled {time.time() - t0:.1f} s", flush=True)
t1 = time.time()
r = terrain_mesh.preview_tiles(T, out, at, radius, density)
print(f"preview tiles {time.time() - t1:.1f} s", flush=True)
xy = np.asarray(at[:2], float) if isinstance(at, list) else np.asarray(T.address(at)[0], float)
h = float(T.sample(xy[None])[0])
views = []
for name, d in (("n", (0, 1)), ("e", (1, 0)), ("s", (0, -1)), ("w", (-1, 0))):
    e = xy + 60 * np.array(d)
    eh = float(T.sample(e[None])[0])
    if eh < h + 20:  # (an eye standing in open air in front of the rock)
        views.append({"name": f"far_{name}", "eye": [float(e[0]), float(e[1]), max(eh, h) + 8.0],
                      "look": [float(xy[0]), float(xy[1]), h], "fov": 50})
if views:
    v = dict(views[0])
    e = np.array(v["eye"][:2])
    c = xy + 0.4 * (e - xy)
    views.append({"name": "close", "eye": [float(c[0]), float(c[1]), v["eye"][2] - 4], "look": v["look"], "fov": 45})
b = [[float(xy[0] - radius - 80), float(xy[1] - radius - 80)], [float(xy[0] + radius + 80), float(xy[1] + radius + 80)]]
t2 = time.time()
for v in views:
    v["out"] = str(out / f"look_{v['name']}.png")
print(terrain_mesh.render_tiles(T, out, views, size=(1200, 800), samples=32, box=b))
print(f"render {time.time() - t2:.1f} s; total {time.time() - t0:.1f} s")
print(json.dumps(r["manifest"].get("timing_s", {})))
