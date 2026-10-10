"""cpm.py <src> <dst>: copy a model (spec + human_refs.json) for experiments."""
import copy, sys
from hifipushie import store

src, dst = sys.argv[1], sys.argv[2]
store.save(dst, copy.deepcopy(store.load(src)), f"tess2: copy of {src}")
(store.HOME / dst / "human_refs.json").write_text((store.HOME / src / "human_refs.json").read_text())
print("copied", src, "->", dst)
