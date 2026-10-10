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
    if mask.sum() < 200:   # (a crop the skin mask misses, e.g. a profile: the whole skin)
        mask = ps["part"] == 0
    c0, w, rms = ls.fit_light(Y, ps["nrm"], mask)
    lt = (c0, w, float(np.median(Y[mask])), 1.0)
    # second pass: with AO and the shadow known, Y ~ A + B ao + C max(w.n, 0) lit + E min(w.n, 0): the ambient's AO
    # share aw = B / (A + B) and the direct's scale C, fitted to the photo (AO at full weight darkened her subnasal
    # area far more than her soft light does)
    _, _, p2 = likeness.render(mesh, cam, box, px=px, brows=False, passes=True, ao=True, shadow=SOFT, light=lt)
    dn = p2["nrm"] @ np.asarray(w, float)
    m2 = mask & (p2["part"] == 0)
    X = np.c_[np.ones(m2.sum()), p2["ao"][m2], (np.maximum(dn, 0) * p2["lit"])[m2], np.minimum(dn, 0)[m2]]
    sol = np.linalg.lstsq(X, Y[m2], rcond=None)[0]
    A, B, C = sol[:3]
    c0n = float(A + B)
    aw = float(np.clip(B / c0n, 0.0, 1.0)) if c0n > 1e-6 else 0.0
    lt = (c0n, np.asarray(w, float) * max(float(C), 0.0), lt[2], aw)
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
    print("mm/px", round(R["mmpx"], 4), "light c0", round(R["light"][0], 3), "w", np.round(R["light"][1], 3).tolist(), "ao share", round(R["light"][3], 3))
    for k in ("photo", "model"):
        print(k, json.dumps(summary(R[k][1])))
        if R[k][1] is not None:
            NR.overlay(R[k][0], R[k][1], f"{o}_{k}.png")
    R["model"][0].save(f"{o}_render.png")
