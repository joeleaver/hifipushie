"""tlid.py <model> [patch.json ...]: garrett3's lidcmp (the same detector on the reference and on our render through
the fitted front camera) for views fitted from images alone (no clicked points): the box comes from the detector's
own points on the reference."""
import copy, json, sys

import numpy as np
from PIL import Image

import lidcmp as L
import rs
from hifipushie import humanfit, store


def setup(name):
    refs = json.loads((store.HOME / name / "human_refs.json").read_text())
    v, cam = refs["views"][0], refs["cameras"][0]
    im = Image.open(v["image"]).convert("RGB")
    d = rs.detect([np.asarray(im)])[0]
    P = d["P"][:, :2]
    lo, hi = P.min(0), P.max(0)
    c, side = 0.5 * (lo + hi), 2.2 * max(hi - lo)
    box = (c[0] - side / 2, c[1] - side / 2, c[0] + side / 2, c[1] + side / 2)
    photo = np.asarray(im.crop(tuple(int(round(x)) for x in box)).resize((L.PX, L.PX), Image.LANCZOS))
    mm = cam["t"][2] / cam["f"] * 1000 * side / L.PX
    return cam, box, photo, mm


name = sys.argv[1]
sp = store.load(name)
b = copy.deepcopy(sp["base"])
cam, box, photo, mm = setup(name)
dp = rs.detect([photo])[0]
a = L.numbers(dp, mm)
print("scores ref:", {k: round(dp["bs"].get(k, 0.0), 2) for k in L.KS})
m, dm = L.measure(b, cam, box, mm)
L.show(f"{name}: ref|model(diff), mm ({mm:.2f} mm a pixel)", a, m, dm)
for pf in sys.argv[2:]:
    p = json.load(open(pf))
    b2 = L.patched(b, p)
    m2, dm2 = L.measure(b2, cam, box, mm)
    L.show(f"+ {pf.split('/')[-1]}: {json.dumps({k: v for k, v in p.items() if k != 'save'})[:200]}", a, m2, dm2)
    print("  plausibility", humanfit.plausibility(b2), "| integrity:",
          humanfit.verdict(humanfit.integrity(b2, humanfit.state(b2), humanfit.state(b)))[:160])
    if p.get("save"):
        store.save(p["save"], {**copy.deepcopy(sp), "base": b2}, f"tess: {name} + {pf.split('/')[-1]} (like with like)")
        (store.HOME / p["save"] / "human_refs.json").write_text((store.HOME / name / "human_refs.json").read_text())
        print("saved", p["save"])
