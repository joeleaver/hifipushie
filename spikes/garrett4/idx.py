"""idx.py <model> [png]: onemesh2's idx1.py (face shapes by index on the one mesh's own quads, no export: neutral
lips' gap, mouth crops in clay) with this worktree's code. Env as idx1: NOSOCK, CC, LC, NOMEET, RAW."""
import runpy
import sys

sys.path.insert(0, "/mnt/data/hifipushie/onemesh2")
runpy.run_path("/mnt/data/hifipushie/onemesh2/idx1.py", run_name="__main__")
