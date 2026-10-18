"""sfwrap.py: shapesfast.py with faceshapes.WRAP_SHAPES minus the names in $NOWRAP (comma list), then the usual args."""
import os, sys, runpy
from hifipushie import faceshapes as fs
drop = set(os.environ.get("NOWRAP", "").split(","))
fs.WRAP_SHAPES = tuple(n for n in fs.WRAP_SHAPES if n not in drop); print("WRAP_SHAPES", fs.WRAP_SHAPES)
sys.argv = [sys.argv[0]] + sys.argv[1:]; sys.path.insert(0, "/mnt/data/hifipushie/assembly")
runpy.run_path("/mnt/data/hifipushie/assembly/shapesfast.py", run_name="__main__")
