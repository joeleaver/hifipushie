"""wholeclay.py <out png> <camera model> <model>...: faces6, WHOLE-FACE clay comparison (the coordinator: dressed renders
were masking what the shape reads as): photo | each model, front / 3/4 / profile, all through the SAME cameras (the
camera model's fitted ones), fast clay with AO + a soft key (likeness.render), brows drawn. Prints per model |c| (head
comps) and a few whole-face widths (mm): bizygomatic-ish (landmarks 1-15), jaw (4-12), chin (6-10), face height
(27-8)."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import humanfit, likeness, store

T = int(os.environ.get("T", "360"))
SHADE = os.environ.get("SHADE", "1") == "1"


def ident(sp):
    idn = sp["base"]["head"].get("identity") or {}
    return np.array([v for k, v in idn.items() if k.startswith("head")]) if isinstance(idn, dict) else np.asarray(idn)


if __name__ == "__main__":
    out, cm, models = sys.argv[1], sys.argv[2], sys.argv[3:]
    refs = json.loads((store.HOME / cm / "human_refs.json").read_text())
    views = [i for i in range(len(refs["views"]))]
    meshes = {}
    for m in models:
        sp = store.load(m)
        st = humanfit.state(sp["base"])
        meshes[m] = likeness.model_mesh_from_state(st)
        L = st["L"]
        w = lambda a, b: float(np.linalg.norm(L[a] - L[b])) * 1000  # noqa: E731
        print(f"{m}: |c| {np.linalg.norm(ident(sp)):.2f} ({len(ident(sp))} comps); widths 1-15 {w(1, 15):.1f}, jaw 4-12 "
              f"{w(4, 12):.1f}, chin 6-10 {w(6, 10):.1f}, height 27-8 {w(27, 8):.1f}", flush=True)
    sheet = Image.new("RGB", (T * (1 + len(models)), (T + 18) * len(views) + 18), "white")
    dr = ImageDraw.Draw(sheet)
    for j, lab in enumerate(["photo"] + models):
        dr.text((j * T + 4, 2), lab, fill=(0, 0, 0))
    ref_st = humanfit.state(store.load(cm)["base"])
    for i, vi in enumerate(views):
        cam = refs["cameras"][vi]
        P = humanfit.project(cam, ref_st["L"])
        c = 0.5 * (P.min(0) + P.max(0))
        side = 1.35 * float(np.max(P.max(0) - P.min(0)))
        box = (c[0] - side / 2, c[1] - side / 2 - 0.05 * side, c[0] + side / 2, c[1] + side / 2 - 0.05 * side)
        img = Image.open(refs["views"][vi]["image"]).convert("RGB")
        y = 18 + i * (T + 18)
        dr.text((4, y), f"view {vi} (cameras of {cm})", fill=(0, 0, 0))
        sheet.paste(img.crop(tuple(int(round(b)) for b in box)).resize((T, T), Image.LANCZOS), (0, y + 16))
        for j, m in enumerate(models):
            kw = dict(ao=True, shadow=8.0) if SHADE else {}
            im = likeness.render(meshes[m], cam, box, px=2 * T, brows=True, **kw)[0]
            sheet.paste(im.resize((T, T), Image.LANCZOS), ((j + 1) * T, y + 16))
    sheet.save(out)
    print("wrote", out)
