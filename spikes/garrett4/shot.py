"""shot.py <model> <tag> [tex=0]: ONE look-dev render through the front reference's fitted camera (1536 px, the
light from $LIGHT json or light.json in $D3, else stage.FRONT_LIGHT), saved as $D3/out/<tag>_front.png (768, what
skinm / silw read) and a comparison picture $D3/out/<tag>_cmp.jpg: photo | ours for the whole head, the eyes + brows
and the mouth + chin (same crops of both; the photo upscaled). HAIR=0 leaves the groom out. ENGINE=cycles."""
import json
import os
import sys

import numpy as np
from PIL import Image

import sheet1
import stage

D3 = os.environ.get("D3")
BIG = 1536


def light():
    f = os.environ.get("LIGHT") or f"{D3}/light.json"
    return json.load(open(f)) if os.path.exists(f) else stage.FRONT_LIGHT


def main(name, tag, tex=None):
    vs, cams = sheet1.cameras(name)
    crop = sheet1.crop_of(vs[0])
    fr = stage.fitted_frame(cams[0], crop, "front")
    im = stage.shoot(name, [fr], light(), size=BIG, hair_on=os.environ.get("HAIR", "1") == "1", tex=tex,
                     engine=os.environ.get("ENGINE", "eevee"))["front"]
    im.resize((768, 768), Image.LANCZOS).save(f"{D3}/out/{tag}_front.png")
    im.save(f"{D3}/out/{tag}_front_big.png")
    ph = Image.open(vs[0]["image"]).convert("RGB").crop(tuple(int(round(v)) for v in crop)).resize((BIG, BIG), Image.LANCZOS)
    U = np.array(list(vs[0]["points"].values()), float)
    c = (U.mean(0) - np.array(crop[:2])) / (crop[2] - crop[0]) * BIG      # the face's middle in the tile
    s = BIG
    boxes = [(0, 0, s, s), (c[0] - 0.19 * s, c[1] - 0.2 * s, c[0] + 0.19 * s, c[1] - 0.01 * s),
             (c[0] - 0.19 * s, c[1] + 0.0 * s, c[0] + 0.19 * s, c[1] + 0.19 * s)]
    W = 760
    tiles = []
    for b in boxes:
        b = tuple(int(v) for v in b)
        h = int(W * (b[3] - b[1]) / (b[2] - b[0]))
        row = Image.new("RGB", (2 * W, h))
        row.paste(ph.crop(b).resize((W, h), Image.LANCZOS), (0, 0))
        row.paste(im.crop(b).resize((W, h), Image.LANCZOS), (W, 0))
        tiles.append(row)
    S = Image.new("RGB", (2 * W, sum(t.size[1] for t in tiles)))
    y = 0
    for t in tiles:
        S.paste(t, (0, y))
        y += t.size[1]
    S.save(f"{D3}/out/{tag}_cmp.jpg", quality=88)
    print("wrote", f"{D3}/out/{tag}_cmp.jpg")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], [0] if len(a) > 2 and a[2] == "1" else None)
