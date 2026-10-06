"""atlas.py <model> <out.png>: the card atlas (colour over grey | alpha | aux) of a model's groom."""
import os, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from hifipushie import hair, store, hair_cards as hc, hair_strands as hs
name, out = sys.argv[1], sys.argv[2]
spec = store.load(name)
sc = hair.scalp(name, spec)
g = hair.groom_params(spec)
S = hc.strands_of(spec)
lk = {**hair.LOOK, **(spec["hair"].get("look") or {})}
tmp = Path(tempfile.mkdtemp())
locks = hair.resolve(spec, sc)
sd = hs.job(sc, g, spec, [k for k in locks if not k["name"].endswith("band")], tmp)
D = hs.strands_of_model(sd)
chart = hs.cap_chart(sc, g, hair.hairline(sc, g), S, D, sd["e0"], int(S["atlas"]))
at = hc.atlas(S, lk, lines=hs.tile_lines(S), cap=chart, key=hs.key(sd))
print("coverage", at["coverage"], at["color"].shape)
c = at["color"]
bg = np.full_like(c[..., :3], 0.55)
comp = c[..., :3] * c[..., 3:] + bg * (1 - c[..., 3:])
sheet = np.concatenate([comp, np.repeat(c[..., 3:], 3, -1), at["aux"][..., :3]], 0)
Image.fromarray((np.clip(sheet, 0, 1) * 255).astype(np.uint8)).resize((sheet.shape[1] // 2, sheet.shape[0] // 2)).save(os.path.join(os.environ["HR"], out))
