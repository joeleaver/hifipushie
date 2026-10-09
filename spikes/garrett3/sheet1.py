"""sheet1.py <model> <out.png> [hair=1] [label]: the sheet Joe judges. Per reference (front photo, desk painting):
reference | the model SKINNED with its groom, through this head's own best camera on that reference (humanfit_map,
identity not free), lit like the reference | 50% blend; the six views skinned under it. Tiles are saved one by one
in $D3/out/<model>_<view>.png as well. PX = tile size (default 900)."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import garrett
import stage
from hifipushie import humanfit_map, store

D3 = os.environ.get("D3")
PX = int(os.environ.get("PX", 900))
POSED = os.environ.get("POSED", "1") == "1"   # the matched views wear the photo's pose (squint, frown, set mouth)


def cameras(name, refit=True):
    sp = store.load(name)
    vs = garrett.refs()
    f = store.HOME / name / "human_refs.json"
    if refit or not f.exists():
        _, rep = humanfit_map.fit(sp["base"], vs, free=())
        f.write_text(json.dumps({"views": vs, "cameras": rep["cameras"]}, indent=1))
        print("evidence residual mm (front, desk):", [v["rms_mm"] for v in rep["views"]])
        return vs, rep["cameras"]
    return vs, json.loads(f.read_text())["cameras"]


def crop_of(view):
    U = np.array(list(view["points"].values()), float)
    lo, hi = U.min(0), U.max(0)
    c = 0.5 * (lo + hi)
    side = 2.75 * max(hi - lo)
    return [c[0] - side / 2, c[1] - side * 0.58, c[0] + side / 2, c[1] + side * 0.42]


def label(im, text, fill=(255, 255, 255)):
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 + 7 * len(text), 18], fill=(0, 0, 0))
    d.text((5, 3), text, fill=fill)
    return im


def main(name, out, hair_on=True, tag=None):
    tag = tag or name
    vs, cams = cameras(name)
    rows = []
    for vi, (view, cam, lit) in enumerate(zip(vs, cams, ("front", "desk"))):
        crop = crop_of(view)
        fr = stage.fitted_frame(cam, crop, lit)
        lt = stage.FRONT_LIGHT if lit == "front" else {**stage.desk_light(fr), "backdrop": [0.12, 0.15, 0.22]}
        im = stage.shoot(name, [fr], lt, size=PX, hair_on=hair_on, posed=POSED)[lit]
        im.save(f"{D3}/out/{name}_{lit}.png")
        ref = Image.open(view["image"]).convert("RGB").crop(tuple(int(round(v)) for v in crop)).resize((PX, PX), Image.LANCZOS)
        bl = Image.blend(ref, im, 0.5)
        tiles = [label(ref, "reference"), label(im.copy(), f"{tag}: skin pipeline + groom, fitted camera"), label(bl, "50% blend")]
        row = Image.new("RGB", (3 * PX, PX))
        for i, t in enumerate(tiles):
            row.paste(t, (i * PX, 0))
        rows.append(row)
    sp = store.load(name)
    six = stage.shoot(name, stage.view_frames(sp), stage.FRONT_LIGHT, size=PX, hair_on=hair_on)
    for half in (list(six.items())[:3], list(six.items())[3:]):
        row = Image.new("RGB", (3 * PX, PX))
        for i, (n, im) in enumerate(half):
            im.save(f"{D3}/out/{name}_{n}.png")
            row.paste(label(im.copy(), n), (i * PX, 0))
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
    main(a[0], a[1], (a[2] if len(a) > 2 else "1") == "1", a[3] if len(a) > 3 else None)
