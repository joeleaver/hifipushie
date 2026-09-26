"""Terrain spike: compile a terrain spec, print its report, write a labelled map and perspective views.
uv run python examples/terrain_run.py examples/glen_terrain.json [--no3d]"""
import sys
import time
from pathlib import Path

from hifipushie import terrain

src = Path(sys.argv[1])
out = src.parent if "workspace" in src.parts else Path("workspace/terrain")  # outputs beside the spec
out.mkdir(parents=True, exist_ok=True)
t0 = time.time()
from hifipushie.terrain_world import Questions, save_kind
try:
    T = terrain.load(src)
except Questions as q:  # the designer has to decide something: relay these to them
    print(q.text())
    sys.exit(3)
if T.new_kind:
    print("saved the new kind for next time:", save_kind(T.new_kind) or "(already saved)")
print(f"compiled {time.time() - t0:.1f}s")
print(T.report())
terrain.map_image(T).save(out / f"{src.stem}_map.png")
if "--no3d" not in sys.argv and T.spec.get("views"):
    print(terrain.render(T, out, T.spec["views"]))
    print("\n".join(T.view_notes))
sheet = terrain.mask_sheet(T)
if sheet is not None:
    sheet.save(out / f"{src.stem}_masks.png")
if "--export" in sys.argv:
    size = (T.spec.get("export") or {}).get("size")
    print("exported", T.export(out / f"{src.stem}_export", size=size))
