"""famstack.py <src with a de-lit atlas> <dst> [lips=texels|indications]: the FULL layer stack from the head's own
pictures (base tone, redness, periorbital, brows, lips, shade, parting, freckle density, fine strength), as the other
heads have; the lips route kept as the head uses it. Drops the lips-only switch (skin.only) the source carried.
LIGHT."""
import sys
from hifipushie import blockin as bi, skin_layers as sl, store
from hifipushie import skin_layers_stack
from hifipushie import blockin_models
src, dst = sys.argv[1:3]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
r = skin_layers_stack.apply(src, out=dst, lips=kw.get("lips", "texels"), log=print)
print(r["text"])
s = store.load(dst)
s["skin"].pop("only", None)
for k in ("base_opacity", "fine_strength"):
    s["skin"]["stack"].pop(k, None)
blockin_models._save(dst, s, f"full layer stack from {src}'s pictures (lips {kw.get('lips', 'texels')})", blockin_models._refs(dst))
print("stack layers:", [(l["name"], l["opacity"]) for l in s["skin"]["stack"]["layers"]], "features:", sorted((s["skin"].get("features") or {}).keys()))
