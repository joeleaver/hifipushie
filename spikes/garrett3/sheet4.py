"""sheet4.py <model> <out.png> [views=0]: WITH / WITHOUT the reference texture (likeness_texture: the fitted
pictures projected as albedo on this head). Rows: front camera, desk camera, then three-quarter, profile, the other
three-quarter. Columns: reference (where there is one) | procedural skin only (sheet1's tiles, $D3/out) | + the
picture as albedo | what is the PICTURE (the decal's alpha, white = the picture's colour) for the front row.
Needs sheet1 run first (same PX)."""
import os
import sys

import numpy as np
from PIL import Image

import sheet1
import stage
from hifipushie import store

D3 = os.environ.get("D3")
PX = sheet1.PX


def main(name, out, views=(0,)):
    vs, cams = sheet1.cameras(name, refit=False)
    sp = store.load(name)
    rows = []
    tex = list(views)
    six = {f["name"]: f for f in stage.view_frames(sp)}
    plan = [("front", stage.fitted_frame(cams[0], sheet1.crop_of(vs[0]), "front"), stage.FRONT_LIGHT, vs[0]),
            ("desk", stage.fitted_frame(cams[1], sheet1.crop_of(vs[1]), "desk"), None, vs[1])]
    plan += [(n, six[n], stage.FRONT_LIGHT, None) for n in ("three_quarter", "profile_right", "three_quarter_other")]
    for n, fr, lt, view in plan:
        if lt is None:
            lt = {**stage.desk_light(fr), "backdrop": [0.12, 0.15, 0.22]}
        im = stage.shoot(name, [fr], lt, size=PX, tex=tex)[n]
        im.save(f"{D3}/out/{name}_{n}_tex.png")
        f0 = f"{D3}/out/{name}_{'m_' if view is not None else ''}{n}.png"
        plain = Image.open(f0).convert("RGB") if os.path.exists(f0) else Image.new("RGB", (PX, PX), (40, 40, 40))
        if view is not None:
            crop = sheet1.crop_of(view)
            ref = Image.open(view["image"]).convert("RGB").crop(tuple(int(round(v)) for v in crop)).resize((PX, PX), Image.LANCZOS)
        else:
            ref = Image.new("RGB", (PX, PX), (24, 24, 28))
        tiles = [sheet1.label(ref, "reference" if view is not None else "(no reference from here)"),
                 sheet1.label(plain.copy(), f"{n}: OURS only (skin description, groom)"),
                 sheet1.label(im.copy(), f"{n}: + the front PICTURE as albedo (de-lit), ours elsewhere")]
        row = Image.new("RGB", (3 * PX, PX))
        for i, t in enumerate(tiles):
            row.paste(t, (i * PX, 0))
        rows.append(row)
    S = Image.new("RGB", (3 * PX, sum(r.size[1] for r in rows)), (24, 24, 28))
    y = 0
    for r in rows:
        S.paste(r, (0, y))
        y += r.size[1]
    S.save(out)
    print("wrote", out, S.size)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], tuple(int(x) for x in a[2].split(",")) if len(a) > 2 else (0,))
