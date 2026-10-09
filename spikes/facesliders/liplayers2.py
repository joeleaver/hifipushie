"""liplayers2.py [model]: every skin layer after skin:lips_upper whose mask names a zone / line touching the mouth, its
opacity and colour, in order (what could paint over the upper vermilion)."""
import json
import sys

from hifipushie import skin, store

s = store.load(sys.argv[1] if len(sys.argv) > 1 else "ll_e14")
s = s.get("spec", s)
lys = list(skin.layers(s).items())
i0 = [k for k, _ in lys].index("skin:lips_upper")
for k, ly in lys[i0:]:
    m = json.dumps(ly.get("mask"))
    if any(w in m for w in ("lip", "mouth", "beard", "upper", "face", "stubble", "nasolabial", "muzzle")) or "lip" in k:
        print(k, "op", ly.get("opacity"), "col", ly.get("color"), "| mask", m[:230])
