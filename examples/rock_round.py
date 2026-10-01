"""One rock design round: preview tiles of the alps wall block and the pebble sea cliffs, rendered from the fixed views
in examples/rock_views.json. Two passes per terrain: "far" (the block round `center`, `density` texels/m, default 6:
the 150 m views) and "near" (one or two tiles round `near.center` at the export's density, 16/m: the 40 m and close
views; at preview density they're only blur).
uv run python examples/rock_round.py <out dir> [alps|pebble ...] [far|near] [--render-only] [--views] [--noblocks]
Views are built from {"at", "dist", "dz", "lift", "yaw", "sun"} (the eye out along the face's downhill direction, D m
away, at max(ground + 1.7, look height + lift x D)): the same eyes every round."""
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy import ndimage

from hifipushie import terrain, terrain_mesh

HERE = Path(__file__).parent
SPECS = {"alps": "workspace/terrain/t3_alps/spec.json", "pebble": "workspace/terrain/pebble_disc/spec.json"}
ROOT = Path("/home/joe/dev/hifipushie")


def views_for(T, defs):
    Hs = ndimage.gaussian_filter(T.H, 3.0)
    gy, gx = np.gradient(Hs, T.cell)
    out = []
    for v in defs:
        x, y = v["at"]
        rc = [[(y - T.ys[0]) / T.cell], [(x - T.xs[0]) / T.cell]]
        g = np.array([ndimage.map_coordinates(gx, rc, order=1)[0], ndimage.map_coordinates(gy, rc, order=1)[0]])
        d = -g / max(np.linalg.norm(g), 1e-9)
        a = np.radians(v.get("yaw", 0.0))
        d = np.array([d[0] * np.cos(a) - d[1] * np.sin(a), d[0] * np.sin(a) + d[1] * np.cos(a)])
        h = float(T.sample(np.array([[x, y]]))[0]) + v.get("dz", 0.0)
        for D in v["dist"]:
            e = np.array([x, y]) + d * D
            gz = max(float(T.sample(e[None])[0]), 0.0 if T.spec.get("sea") else -1e9)
            ez = max(gz + 1.7, h + v.get("lift", 0.0) * D)
            out.append({"name": f"{v['name']}_{D}m", "eye": [float(e[0]), float(e[1]), ez], "look": [x, y, h],
                        "fov": v.get("fov", 50), "sun": v.get("sun", [225, 30])})
    return out


def main():
    out = Path(sys.argv[1])
    which = [a for a in sys.argv[2:] if a in SPECS] or list(SPECS)
    passes = [a for a in sys.argv[2:] if a in ("far", "near")] or ["far", "near"]
    V = json.loads((HERE / "rock_views.json").read_text())
    for name in which:
        T = terrain.load(ROOT / SPECS[name])
        if "--noblocks" in sys.argv:  # (the rock as it was before terrain_blocks: a baseline for the same views)
            T.spec["rock"] = {**(T.spec.get("rock") or {}), "blocks": 0}
        for ps in passes:
            t0 = time.time()
            cfg = V[name][ps]
            o = out / f"{name}_{ps}"
            if "--render-only" not in sys.argv:
                r = terrain_mesh.preview_tiles(T, o, cfg["center"], cfg.get("radius", 40.0), cfg.get("density", 6.0),
                                               cfg.get("cfg"))
                print(f"{name} {ps}: preview {time.time() - t0:.0f} s, memory {r['manifest'].get('memory_gb')}",
                      flush=True)
            views = views_for(T, cfg["views"])
            for v in views:
                v["out"] = str(o / f"{name}_{v['name']}.png")
            if "--views" in sys.argv:
                print(json.dumps(views))
            terrain_mesh.render_tiles(T, o, views, size=(1200, 750), samples=32, trees=False, box=cfg.get("box"))
            print(f"{name} {ps}: done {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
