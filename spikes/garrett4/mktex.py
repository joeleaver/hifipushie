"""mktex.py <src dressed model> <dst> [ours scene model]: dst = src + the front reference picture as a saved paint
layer (likeness_texture.apply, harmonised against the unlit render of `ours scene model`'s scene.blend: by default the
head stage of src, which has no picture layer). The export bakes it like any image layer."""
import shutil
import sys

import stage
from hifipushie import likeness_texture as lt, store

src, dst = sys.argv[1], sys.argv[2]
ours = sys.argv[3] if len(sys.argv) > 3 else stage.ensure(src, with_hair=False)
sp = store.load(src)
store.save(dst, sp, f"garrett4: {src} for the reference texture")
for fn in ("human_refs.json", "pose.json"):
    f = store.HOME / src / fn
    if f.exists():
        shutil.copy(f, store.HOME / dst / fn)
r = lt.apply(dst, views=[0], opacity=1.0, ours=lt.scene_albedo(ours), note="garrett4: the front picture as albedo, harmonised")
sp = store.load(dst)      # layers named over_* lie OVER the picture (a lip seam the parted export mouth hides in its gap)
pt = sp["paint"]
sp["paint"] = {**{k: v for k, v in pt.items() if not k.startswith("over_")}, **{k: v for k, v in pt.items() if k.startswith("over_")}}
store.save(dst, sp, "garrett4: over_* layers after the picture")
print(r["text"])
print("layers", {k: {kk: vv for kk, vv in v.items() if kk != "image"} for k, v in store.load(dst)["paint"].items() if k.startswith("ref_")})
