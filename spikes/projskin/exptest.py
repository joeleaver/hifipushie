"""exptest.py <model> <out dir>: export_asset at a small texture, then report whether the blink map was written. HEAVY (export
takes the heavy slot itself)."""
import sys
from pathlib import Path
from hifipushie import asset
m, out = sys.argv[1:3]
r = asset.export(m, Path(out), triangles=20000, texture=1024, resolution=256)
print("\n".join(l for l in r.get("log", []) if "blink" in l or "WARNING" in l))
print("files:", sorted(p.name for p in Path(out).glob("*blink*")))
