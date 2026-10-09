"""sheet.py out.png model:label ... [six=<six-view png>]: the sheet Joe judges. Per reference (front photo, desk
painting): reference | each model through ITS OWN best cameras on the same evidence (humanfit_map, identity not
free), LIT (key from the upper left, as om2_r9) with his locks re-seated on each model's own scalp; large tiles; the
six-view sheet of the last head under it. PX=<tile width> (default 560). "omNN" as a model = om_garrett's history
version NN saved as rs2_om<NN> (a copy; om_garrett is never written)."""
import copy
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import garrett
import hairmesh
import litrender
from hifipushie import humanfit, humanfit_map, onemesh, store

PX = int(os.environ.get("PX", 560))


def resolve(name):
    if name.startswith("om") and name[2:].isdigit():
        dst = f"rs2_{name}"
        if not (store.HOME / dst / "spec.json").exists():
            store.save(dst, copy.deepcopy(garrett.hist("om_garrett", int(name[2:]))), f"refstudy2: a copy of om_garrett v{name[2:]} for sheets")
        return dst
    return name


def mesh_of(name):
    sp = store.load(name)
    tpl = onemesh.template(sp["base"])
    V = np.asarray(tpl["P"], float)
    Lf = np.asarray(tpl["L"]).reshape(-1, 4)
    F = np.r_[Lf[:, [0, 1, 2]], Lf[:, [0, 2, 3]]]
    col = two = None
    col = np.tile([225.0, 205.0, 185.0], (len(F), 1))
    two = np.zeros(len(F), bool)
    from hifipushie import likeness
    for Ve, Fe, ce in likeness.model_mesh(sp["base"])["eyes"]:      # eyeballs with irises (the template has none)
        col = np.r_[col, ce[Fe].mean(1)]
        two = np.r_[two, np.zeros(len(Fe), bool)]
        F = np.r_[F, Fe + len(V)]
        V = np.r_[V, Ve]
    gm = hairmesh.groom_mesh(name, sp) if os.environ.get("HAIR", "1") == "1" else None
    if gm is not None:
        col = np.r_[col, gm[2]].astype(float)
        two = np.r_[two, np.ones(len(gm[1]), bool)]
        F = np.r_[F, gm[1] + len(V)]
        V = np.r_[V, gm[0]]
    return sp, V, F, col, two


def main(out, models, six=None):
    vs = garrett.refs()
    ms = []
    for name, label in models:
        name = resolve(name)
        sp, V, F, col, two = mesh_of(name)
        _, rep = humanfit_map.fit(sp["base"], vs, free=())
        ms.append((label, V, F, col, two, rep["cameras"], [v["rms_mm"] for v in rep["views"]]))
        print(label, "residual", ms[-1][-1])
    rows = []
    for vi, view in enumerate(vs):
        U = np.array(list(view["points"].values()), float)
        lo, hi = U.min(0), U.max(0)
        pad = 0.45 * (hi - lo).max()
        box = (lo[0] - pad * 1.3, lo[1] - pad * 2.6, hi[0] + pad * 1.3, hi[1] + pad * 0.9)
        ref = Image.open(view["image"]).convert("RGB").crop(tuple(int(v) for v in box))
        sz = (PX, int(PX * ref.size[1] / ref.size[0]))
        tiles = [ref.resize(sz, Image.LANCZOS)]
        for label, V, F, col, two, cams, rms in ms:
            im, _ = litrender.render(V, F, cams[vi], box, PX, True, col, two)
            im = im.resize(sz)
            ImageDraw.Draw(im).text((6, 5), f"{label}  [{rms[vi]} mm]", fill=(20, 20, 20))
            tiles.append(im)
        bl = Image.blend(tiles[0], tiles[-1], 0.5)
        ImageDraw.Draw(bl).text((6, 5), "reference + " + ms[-1][0] + " (50%)", fill=(255, 255, 255))
        tiles.append(bl)
        rows.append(litrender.row(tiles, sz[1]))
    if six:
        s6 = Image.open(six).convert("RGB")
        Wd = max(r.size[0] for r in rows)
        w6 = min(Wd, int(s6.size[0] * 1.3))
        rows.append(s6.resize((w6, int(s6.size[1] * w6 / s6.size[0])), Image.LANCZOS))
    Wd = max(r.size[0] for r in rows)
    S = Image.new("RGB", (Wd, sum(r.size[1] for r in rows)), (30, 30, 34))
    y = 0
    for r in rows:
        S.paste(r, (0, y))
        y += r.size[1]
    S.save(out)
    print("wrote", out, S.size)


if __name__ == "__main__":
    a = sys.argv[1:]
    six = next((x[4:] for x in a if x.startswith("six=")), None)
    main(a[0], [(x.split(":", 1) + [x])[:2] for x in a[1:] if not x.startswith("six=")], six)
