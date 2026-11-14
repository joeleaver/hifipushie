"""lipsonly2.py <model with a picture-hue atlas + fitted tone> : the stack from that atlas, then ONLY the lips layer laid
(skin_layers.only), saved in place. LIGHT."""
import sys
from hifipushie import blockin as bi, skin_layers as sl, store
from hifipushie import skin_layers_stack
from hifipushie import blockin_models
m = sys.argv[1]
r = skin_layers_stack.apply(m, log=lambda s: None)
print("\n".join(l for l in r["text"].split("\n") if "lips" in l or "vermilion" in l))
s = skin_layers_stack.only(store.load(m), ("lips",))
blockin_models._save(m, s, "lips layer only (our painted vermilion off), picture-hue atlas, fitted tone", blockin_models._refs(m))
