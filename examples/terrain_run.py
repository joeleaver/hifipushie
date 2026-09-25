"""Terrain spike: compile a terrain spec, print its report, write a labelled map and perspective views.
uv run python examples/terrain_run.py examples/glen_terrain.json [--no3d]"""
import sys
import time
from pathlib import Path

from hifipushie import terrain

src = Path(sys.argv[1])
out = Path("workspace/terrain")
out.mkdir(parents=True, exist_ok=True)
t0 = time.time()
T = terrain.load(src)
print(f"compiled {time.time() - t0:.1f}s")
print(T.report())
terrain.map_image(T).save(out / f"{src.stem}_map.png")
if "--no3d" not in sys.argv and T.spec.get("views"):
    print(terrain.render(T, out, T.spec["views"]))
sheet = terrain.mask_sheet(T)
if sheet is not None:
    sheet.save(out / f"{src.stem}_masks.png")
if "--export" in sys.argv:
    size = (T.spec.get("export") or {}).get("size")
    print("exported", T.export(out / f"{src.stem}_export", size=size))
