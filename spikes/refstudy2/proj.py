"""proj.py <out.png> model[:label] ...: likeness_read.project_reference of each model (the front photo projected onto
the head through ITS OWN best front camera, seen from the six views), stacked into one sheet. "om16" as in sheet.py."""
import json
import os
import sys

from PIL import Image, ImageDraw

import garrett
import sheet
from hifipushie import humanfit_map, likeness_read as lr, store

D2 = os.environ.get("D2")
out = sys.argv[1]
rows = []
for a in sys.argv[2:]:
    name, label = (a.split(":", 1) + [a])[:2]
    name = sheet.resolve(name)
    b = store.load(name)["base"]
    vs = garrett.refs()
    _, rep = humanfit_map.fit(b, vs, free=())   # this head's own best cameras on the same evidence
    (store.HOME / name / "human_refs.json").write_text(json.dumps({"views": vs, "cameras": rep["cameras"]}, indent=1))
    f = f"{D2}/out/proj_{name}.png"
    r = lr.project_reference(name, f, base=b)
    print(label, r["seen"])
    im = Image.open(f).convert("RGB")
    ImageDraw.Draw(im).text((200, 4), label, fill=(160, 0, 0))
    rows.append(im)
W = max(r.size[0] for r in rows)
S = Image.new("RGB", (W, sum(r.size[1] + 8 for r in rows)), (24, 24, 28))
y = 0
for r in rows:
    S.paste(r, (0, y))
    y += r.size[1] + 8
S.save(out)
print("wrote", out, S.size)
