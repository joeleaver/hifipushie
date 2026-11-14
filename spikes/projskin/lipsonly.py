"""lipsonly.py <src with references> <dst>: the atlas (skin_project, measurement only) + the stack, then ONLY the lips layer
laid over the model's own skin (our painted vermilion off, every other stack layer off, no mesh change). LIGHT."""
import sys
from hifipushie import blockin as bi, skin_layers as sl, skin_project as sp, store
from hifipushie import skin_layers_stack
from hifipushie import blockin_models, skin_project_model
src, dst = sys.argv[1:3]
a = skin_project_model.apply(src, out=dst, opacity=0.0, log=lambda s: None)
print(a["text"].split("\n")[0])
r = skin_layers_stack.apply(dst, log=lambda s: None)
print("\n".join(l for l in r["text"].split("\n") if "lips" in l or "RECOMPOSED" in l or "ALL" in l))
s = skin_layers_stack.only(store.load(dst), ("lips",))
blockin_models._save(dst, s, "lips layer only (our painted vermilion off)", blockin_models._refs(dst))
print(dst, "skin.only", s["skin"]["only"], [(l["name"], l["opacity"]) for l in s["skin"]["stack"]["layers"]])
