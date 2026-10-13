"""augcheck.py <data root> <out.png>: 18 training crops with FIVE named landmarks drawn large (nose tip red, chin
yellow, the subject's LEFT outer eye corner cyan, RIGHT outer eye corner blue, left mouth corner green): the check
that crop, rotation and mirroring carry the labels with the picture."""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import train as T  # noqa: E402

root, outp = Path(sys.argv[1]), sys.argv[2]
tmp = Path(outp + ".pack")
tmp.mkdir(exist_ok=True)
Ld = json.loads((root / "landmarks.json").read_text())
L = {"mirror": np.array(Ld["mirror"]), "lm68": np.array(Ld["lm68"]), "region": np.array(Ld["region"]), "n": Ld["n"]}
P = T.pack(root, tmp, 18)
ds = T.Data(P, np.arange(min(P["n"], 18)), L, True, 0)
MARK = {30: (255, 40, 40), 8: (255, 230, 40), 45: (40, 255, 255), 36: (60, 90, 255), 54: (60, 255, 60)}
S = Image.new("RGB", (6 * 256, 3 * 256))
for k in range(18):
    x, t, vis, mmpx, i = ds[k]
    a = (x.transpose(1, 2, 0) * T.STD + T.MEAN) * 255
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    p = (t + 1) * 128
    for lm, col in MARK.items():
        q = p[L["lm68"][lm]]
        d.ellipse((q[0] - 4, q[1] - 4, q[0] + 4, q[1] + 4), outline=col, width=2)
    S.paste(im, ((k % 6) * 256, (k // 6) * 256))
S.save(outp)
print(outp)
