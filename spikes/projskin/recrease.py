"""recrease.py <model> [strength=] [occlusion=1]: the stack's crease line map (and the baked occlusion) made again from the head's fold (skin_layers.crease_map,
current code), stored in place. LIGHT."""
import copy, sys
import numpy as np
from PIL import Image
from hifipushie import blockin as bi, images, skin_layers as sl, skin_project as sp, store
m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
s = copy.deepcopy(store.load(m))
at = sp.atlas(s["base"])
cm = sl.crease_map(s, at)
H, W = at["shape"]
valid = sp.image(at, np.ones(len(at["ii"]), bool), False)
a = np.zeros((H, W, 4), np.uint8)
a[..., :3] = sp._bleed(sp.image(at, (np.clip(sp._srgb(np.tile(sl.crease_tint(s, at), (len(cm), 1))), 0, 1) * 255 + 0.5).astype(np.uint8)), valid)
a[..., 3] = sp._bleed(sp.image(at, (cm * 255).astype(np.uint8)), valid)
d = store._dir(m) / "skin_layers"; d.mkdir(parents=True, exist_ok=True)
Image.fromarray(a, "RGBA").save(d / "crease.png")
s["skin"]["stack"]["crease"] = images.ingest(d / "crease.png")
if kw.get("occlusion", "1") == "1":   # the baked occlusion again too (same code path as skin_layers.apply)
    for part_, key_ in (("still", "occlusion"), ("lid", "occlusion_lid")):
        o = sl.occlusion(s, at, part_)
        b = np.zeros((H, W, 4), np.uint8)
        b[..., :3] = sp._bleed(sp.image(at, (np.clip(sp._srgb(o), 0, 1) * 255 + 0.5).astype(np.uint8)), valid)
        b[..., 3] = 255
        Image.fromarray(b, "RGBA").save(d / f"{key_}.png")
        s["skin"]["stack"][key_] = images.ingest(d / f"{key_}.png")
if "strength" in kw:
    s["skin"]["stack"]["crease_strength"] = float(kw["strength"])
bi._save(m, s, "crease line map again (recrease)", bi._refs(m))
print(m, "crease texels > 0.5:", int((cm > 0.5).sum()), "strength", s["skin"]["stack"].get("crease_strength"))
