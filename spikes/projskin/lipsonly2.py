"""lipsonly2.py <model with a picture-hue atlas + fitted tone> : the stack from that atlas, then ONLY the lips layer laid
(skin_layers.only), saved in place. LIGHT."""
import sys
from hifipushie import blockin as bi, skin_layers as sl, store
m = sys.argv[1]
r = sl.apply(m, log=lambda s: None)
print("\n".join(l for l in r["text"].split("\n") if "lips" in l or "vermilion" in l))
s = sl.only(store.load(m), ("lips",))
bi._save(m, s, "lips layer only (our painted vermilion off), picture-hue atlas, fitted tone", bi._refs(m))
