"""liplayers.py <model>: the paint layer stack in order (paint.layers), each layer that can touch the lips: name,
_pre, colour, opacity, mask (short); then the expanded mask of skin:lips_upper."""
import json
import sys

from hifipushie import paint, store

spec = store.load(sys.argv[1])
ly = paint.layers(spec)
names = list(ly)
for i, n in enumerate(names):
    L = ly[n]
    m = json.dumps(L.get("mask"))
    if any(k in n for k in ("lip", "mouth", "stubble", "beard", "tone", "zone", "shading", "over_", "pre")) or "lip" in m:
        print(i, n, "pre" if L.get("_pre") else "   ", L.get("color") if not isinstance(L.get("color"), dict) else "{..}",
              L.get("opacity"), L.get("mix", ""), m[:160])
print(len(names), "layers")
print(json.dumps(ly.get("skin:lips_upper"))[:1500])
