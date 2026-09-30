"""A fast look at a terrain's rock for design rounds: the tiles round one place exported with one LOD at a low texel
density and no checks (`terrain_mesh.preview_tiles`, the export's own code path), then rendered.
uv run python examples/terrain_rock_look.py <spec.json> <out dir> <at: address or x,y> [radius m] [texels/m] [views.json]
Default views: the face at `at` seen from out along its downhill direction (the way it faces), 90 m and 35 m away,
the eye 25 / 10 m over the ground there, plus one from 40 deg to the side. views.json: render_tiles views instead."""
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
print(f"preview tiles {time.time() - t1:.1f} s (export {r['manifest']['timing_s'].get('total before check')} s)",
      flush=True)
xy = np.asarray(at[:2], float) if isinstance(at, list) else np.asarray(T.address(at)[0], float)
if len(sys.argv) > 6:
    views = json.loads(Path(sys.argv[6]).read_text())
else:
    h = float(T.sample(xy[None])[0])
    e = 5.0
    g = np.array([T.sample((xy + [e, 0])[None])[0] - T.sample((xy - [e, 0])[None])[0],
                  T.sample((xy + [0, e])[None])[0] - T.sample((xy - [0, e])[None])[0]]) / (2 * e)
    down = -g / max(np.linalg.norm(g), 1e-9)  # the way the face looks
    views = []
    for name, dist, lift, turn in (("far", 90.0, 25.0, 0.0), ("near", 35.0, 10.0, 0.0), ("side", 70.0, 20.0, 40.0)):
        c, s = np.cos(np.radians(turn)), np.sin(np.radians(turn))
        d = np.array([c * down[0] - s * down[1], s * down[0] + c * down[1]])
        eye = xy + dist * d
        ez = max(float(T.sample(eye[None])[0]), h - dist) + lift
        views.append({"name": name, "eye": [float(eye[0]), float(eye[1]), ez], "look": [float(xy[0]), float(xy[1]), h],
                      "fov": 50})
b = [[float(xy[0] - radius - 120), float(xy[1] - radius - 120)], [float(xy[0] + radius + 120), float(xy[1] + radius + 120)]]
t2 = time.time()
for v in views:
    v["out"] = str(out / f"look_{v['name']}.png")
print(terrain_mesh.render_tiles(T, out, views, size=(1200, 800), samples=32, box=b))
print(f"render {time.time() - t2:.1f} s; total {time.time() - t0:.1f} s")
