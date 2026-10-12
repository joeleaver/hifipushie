"""augpeek.py <data root> <out.png>: 24 training crops as the network sees them (every other one with its labels:
visible green, hidden red, the subject's-left eye points cyan). Needs torch (the training venv)."""
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
P = T.pack(root, tmp, 24)
ds = T.Data(P, np.arange(min(P["n"], 12)), L, True, 0)
S = Image.new("RGB", (6 * 256, 4 * 256))
for k in range(24):
    ds.epoch = k // 12
    x, t, vis, mmpx, i = ds[k % len(ds)]
    a = (x.transpose(1, 2, 0) * T.STD + T.MEAN) * 255
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    if k % 2 == 0:
        for j, (p, v) in enumerate(zip((t + 1) * 128, vis)):
            col = (60, 255, 60) if v else (255, 60, 60)
            if ".L" in Ld["names"][j]:
                col = (0, 255, 255)
            d.point((p[0], p[1]), fill=col)
    S.paste(im, ((k % 6) * 256, (k // 6) * 256))
S.save(outp)
print(outp, "mm/px", mmpx)
