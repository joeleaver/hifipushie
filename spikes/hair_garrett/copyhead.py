"""copyhead.py <src> <dst>: dst (hg_* / hj_* / hl_* only) = a copy of the head model src: spec without hair, human_refs.json,
skin_layers/ (the skin is copied, never edited). The source is not touched."""
import json
import shutil
import sys

from hifipushie import store

src, dst = sys.argv[1:3]
assert dst.startswith(("hg_", "hj_", "hl_")), dst
s, d = store.HOME / src, store.HOME / dst
d.mkdir(exist_ok=True)
sp = json.loads((s / "spec.json").read_text())
sp.pop("hair", None)
(d / "spec.json").write_text(json.dumps(sp, indent=1))
for f in ("human_refs.json", "pose.json"):
    if (s / f).exists():
        shutil.copy(s / f, d / f)
if (s / "skin_layers").exists() and not (d / "skin_layers").exists():
    shutil.copytree(s / "skin_layers", d / "skin_layers")
print("copied", src, "->", dst)
