"""noserender.py <model> [out png]: faces6, the nose readers (nosereader.read) on the photo AND on our render read the
same way: the model through the front picture's fitted camera at the picture's pixels, lit by the photo's light fitted
on the model's normals (likeness_shape.fit_light over the face skin), with AO + soft key shadow (likeness.render
ao / shadow); MediaPipe run on the render for the reader's anchors; mm per pixel from the camera at the nose for
both (not each picture's iris: the clay iris is ours). Prints both reads side by side; writes the two overlays."""
import json
import os
import sys

import numpy as np
from PIL import Image

import nosereader as NR
from hifipushie import humanfit, likeness, likeness_shape as ls, store

SOFT = float(os.environ.get("SOFT", "8"))


def lit_render(mesh, cam, img, box=None, px=None):
    """The model at the picture's pixels (box = whole picture), the photo's light fitted on the face's skin."""
    W, H = cam["size"]
    box = box or (0.0, 0.0, float(W), float(H))
    px = px or int(max(box[2] - box[0], box[3] - box[1]))
    _, k, ps = likeness.render(mesh, cam, box, px=px, brows=False, passes=True)
    Hh, Ww = ps["zb"].shape
    crop = img.crop(tuple(int(round(v)) for v in box)).resize((Ww, Hh), Image.LANCZOS)
    Y = ls._lin(crop)
    P = likeness.detect([img])[0]
    side = likeness.Side(np.asarray(P, float)[:, :2], None) if P is not None else None
    mask = ps["part"] == 0
    if side is not None:
        try:
            to_px = lambda Q: (np.asarray(Q, float) - [box[0], box[1]]) * k  # noqa: E731
            mmpx = likeness._mm_per_px(cam, mesh["L"][27:36])
            mask = ls.skin_mask(side, (Hh, Ww), to_px, k / mmpx) & mask
        except Exception as e:  # noqa: BLE001
            print("skin mask failed, whole skin used:", e)
    c0, w, rms = ls.fit_light(Y, ps["nrm"], mask)
    lt = (c0, w, float(np.median(Y[mask])))
    im, k, ps = likeness.render(mesh, cam, box, px=px, brows=False, passes=True, ao=True, shadow=SOFT, light=lt)
    return im, lt, ps


def nose_reads(m, view=0):
    refs = json.loads((store.HOME / m / "human_refs.json").read_text())
    cam = refs["cameras"][view]
    img = Image.open(refs["views"][view]["image"]).convert("RGB")
    st = humanfit.state(store.load(m)["base"])
    mesh = likeness.model_mesh_from_state(st)
    mmpx = likeness._mm_per_px(cam, mesh["L"][27:36])
    ren, lt, _ = lit_render(mesh, cam, img)
    Pp = likeness.detect([img])[0]
    Pm = likeness.detect([ren])[0]
    return {"photo": (img, NR.read(img, Pp, mmpx)), "model": (ren, NR.read(ren, Pm, mmpx) if Pm is not None else None),
            "mmpx": mmpx, "light": lt}


def summary(r):
    if r is None:
        return None
    out = {k: round(float(r[k]), 2) for k in ("alar_width", "alar_R", "alar_L") if k in r}
    for s in ("R", "L"):
        nb = r.get("nostril_" + s)
        out["nostril_" + s] = None if nb is None else {k: round(float(v), 2) for k, v in nb.items() if k != "px"}
    return out


if __name__ == "__main__":
    m = sys.argv[1]
    o = sys.argv[2] if len(sys.argv) > 2 else f"/mnt/data/hifipushie/faces6/out/nose_{m}"
    R = nose_reads(m)
    print("mm/px", round(R["mmpx"], 4), "light", round(R["light"][0], 3), np.round(R["light"][1], 3).tolist())
    for k in ("photo", "model"):
        print(k, json.dumps(summary(R[k][1])))
        if R[k][1] is not None:
            NR.overlay(R[k][0], R[k][1], f"{o}_{k}.png")
    R["model"][0].save(f"{o}_render.png")
