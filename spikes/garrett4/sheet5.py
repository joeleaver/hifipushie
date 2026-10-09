"""sheet5.py <model> <out.png> [rows=ref,six,proc]: the judging sheet with the reference picture as albedo.
  ref rows: per reference (front photo, desk painting): reference | ours, procedural skin | ours, the front PICTURE
            as albedo (harmonised into our skin at its edge), through that reference's fitted camera and light;
  six:      the six views WITH the picture (does it hold when turned: sides, low angle);
  proc:     the six views with the procedural skin only.
Light: $D3/light.json (the photo's) for the front row and the six views. Tiles in $D3/out/<model>_s5_<view>[_tex].png.
HAIR=0 leaves the groom out. PX tile size (640)."""
import os
import sys

from PIL import Image

import sheet1
import shot
import stage
from hifipushie import store

D3 = os.environ.get("D3")
PX = int(os.environ.get("PX", 640))
HAIR = os.environ.get("HAIR", "1") == "1"


def row(tiles):
    r = Image.new("RGB", (len(tiles) * PX, PX), (24, 24, 28))
    for i, t in enumerate(tiles):
        r.paste(t.resize((PX, PX), Image.LANCZOS), (i * PX, 0))
    return r


def main(name, out, rows=("ref", "six", "proc")):
    vs, cams = sheet1.cameras(name)
    sp = store.load(name)
    lt = shot.light()
    R = []
    if "ref" in rows:
        for view, cam, n in zip(vs, cams, ("front", "desk")):
            crop = sheet1.crop_of(view)
            fr = stage.fitted_frame(cam, crop, n)
            L = lt
            if n != "front":     # the painting: a warm lamp from picture right, a blue room (stage.desk_light was far
                L = stage.desk_light(fr)      # too orange and dark: a lamp's colour on skin, not a sodium light)
                L["lights"][0].update(color=[1.0, 0.86, 0.7], energy=3.0, angle=25)
                L["lights"][1].update(energy=0.9, color=[0.7, 0.8, 1.0])
                L = {**L, "world": {"color": [0.3, 0.36, 0.5], "strength": 0.8}, "exposure": 0.1, "backdrop": [0.12, 0.15, 0.22]}
            a = stage.shoot(name, [fr], L, size=PX, hair_on=HAIR)[n]
            b = stage.shoot(name, [fr], L, size=PX, hair_on=HAIR, tex=[0])[n]
            a.save(f"{D3}/out/{name}_s5_{n}.png")
            b.save(f"{D3}/out/{name}_s5_{n}_tex.png")
            ref = Image.open(view["image"]).convert("RGB").crop(tuple(int(round(v)) for v in crop)).resize((PX, PX), Image.LANCZOS)
            R.append(row([sheet1.label(ref, f"reference ({n})"), sheet1.label(a, f"{n}: ours, procedural skin"),
                          sheet1.label(b, f"{n}: ours + the front PICTURE as albedo")]))
    frames = stage.view_frames(sp)
    for key, tex in (("six", [0]), ("proc", None)):
        if key not in rows:
            continue
        six = stage.shoot(name, frames, lt, size=PX, hair_on=HAIR, tex=tex)
        items = list(six.items())
        for n, im in items:
            im.save(f"{D3}/out/{name}_s5_{n}{'_tex' if tex else ''}.png")
        for half in (items[:3], items[3:]):
            R.append(row([sheet1.label(im.copy(), f"{n}: " + ("picture as albedo" if tex else "procedural skin")) for n, im in half]))
    S = Image.new("RGB", (3 * PX, PX * len(R)), (24, 24, 28))
    for i, r in enumerate(R):
        S.paste(r, (0, i * PX))
    S.save(out)
    print("wrote", out, S.size)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], tuple(a[2].split(",")) if len(a) > 2 else ("ref", "six", "proc"))
