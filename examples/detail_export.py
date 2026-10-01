"""The regression exports for the tiling detail: pebble (full) and the alps wall block (3 x 3), with every check.
uv run python examples/detail_export.py <out dir> <pebble|alps> [cfg json]
Prints the summary, the check and the stage times; the manifest is in <out dir>/<name>."""
import json
import sys
import time
from pathlib import Path

from hifipushie import terrain, terrain_mesh

ROOT = Path("/home/joe/dev/hifipushie")
SPECS = {"alps": ("workspace/terrain/t3_alps/spec.json", {"only": [[33, 56], [35, 58]]}),
         "pebble": ("workspace/terrain/pebble_disc/spec.json", {})}


def main():
    out, name = Path(sys.argv[1]), sys.argv[2]
    extra = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
    spec, cfg = SPECS[name]
    T = terrain.load(ROOT / spec)
    t0 = time.time()
    r = terrain_mesh.export_tiles(T, out / name, {**cfg, **extra})
    print(f"{name}: export {time.time() - t0:.0f} s")
    print(terrain_mesh.summary(r))
    M = r["manifest"]
    print(json.dumps({"timing_s": M["timing_s"], "seam_check": M["seam_check"], "memory_gb": M.get("memory_gb"),
                      "texel_density_used": M.get("texel_density_used")}, indent=1))


if __name__ == "__main__":
    main()
