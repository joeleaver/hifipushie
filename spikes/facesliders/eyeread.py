"""eyeread.py <model> [ref model]: faces6, the LID MARGINS AGAINST THE IRIS (the audit's finding 5: our back-set eyeball
shifts the lid / iris relation; the clay's eyes read small and squinty), read the same way on the photo and on our
front render, in iris radii from the iris centre (MRD1 / MRD2 style, scale-free):
  photo   MediaPipe iris centre 468 / 473 and radius (469-472 / 474-477), upper lid 159 / 386, lower lid 145 / 374;
  model   the fast render's eye pass (part == 1: the visible eyeball) in the column through the iris centre (the
          sphere's forward pole, projected), top and bottom of the visible eyeball; iris radius = the drawn iris cap's
          (likeness._sphere: cos > 0.86) projected radius.
Also the visible eye opening's width / height ratio (palpebral aspect). Prints both and the differences."""
import json
import sys

import numpy as np
from PIL import Image

from hifipushie import humanfit, likeness, store


def photo_read(img):
    P = np.asarray(likeness.detect([img])[0], float)[:, :2]
    out = {}
    for side, (c, rim, up, lo, a, b) in {"R": (468, [469, 470, 471, 472], 159, 145, 33, 133),
                                          "L": (473, [474, 475, 476, 477], 386, 374, 263, 362)}.items():
        r = float(np.mean(np.linalg.norm(P[rim] - P[c], axis=1)))
        out[side] = {"upper": float((P[c, 1] - P[up, 1]) / r), "lower": float((P[lo, 1] - P[c, 1]) / r),
                     "aspect": float(np.linalg.norm(P[a] - P[b]) / max(P[lo, 1] - P[up, 1], 1e-6))}
    return out


def model_read(mesh, cam, img_size):
    W, H = cam["size"]
    im, k, ps = likeness.render(mesh, cam, (0.0, 0.0, float(W), float(H)), px=int(max(W, H)), brows=False, passes=True)
    st = mesh["state"]
    fwd = np.asarray(st["head"].get("forward", [0, -1, 0]), float)
    r = float(st["head"].get("eye_r", 0.012)) * 0.985
    out = {}
    for c in st["head"]["eyes"]:
        c = np.asarray(c, float)
        pole = humanfit.project(cam, (c + r * fwd)[None])[0]
        # the iris cap's rim: points at cos 0.86 from the pole, projected: radius as their mean distance
        u = np.cross(fwd, [0, 0, 1.0])
        u /= np.linalg.norm(u)
        ring = [c + r * (0.86 * fwd + 0.51 * (np.cos(t) * u + np.sin(t) * np.array([0, 0, 1.0]))) for t in np.linspace(0, 2 * np.pi, 16, endpoint=False)]
        R_ = float(np.mean(np.linalg.norm(humanfit.project(cam, np.array(ring)) - pole, axis=1))) * k
        x, y = int(round(pole[0] * k)), pole[1] * k
        col = np.flatnonzero(ps["part"][:, x] == 1)
        col = col[np.abs(col - y) < 4 * R_]
        if len(col) == 0:
            continue
        row = np.flatnonzero(ps["part"][int(round(y)), :] == 1)
        row = row[np.abs(row - x) < 6 * R_]
        side = "L" if c[0] > 0 else "R"
        out[side] = {"upper": float((y - col.min()) / R_), "lower": float((col.max() - y) / R_),
                     "aspect": float((row.max() - row.min()) / max(col.max() - col.min(), 1))}
    return out


if __name__ == "__main__":
    m = sys.argv[1]
    ref = sys.argv[2] if len(sys.argv) > 2 else "f6_M_mace"
    refs = json.loads((store.HOME / ref / "human_refs.json").read_text())
    img = Image.open(refs["views"][0]["image"]).convert("RGB")
    mesh = likeness.model_mesh_from_state(humanfit.state(store.load(m)["base"]))
    ph, md = photo_read(img), model_read(mesh, refs["cameras"][0], img.size)
    for s in ("R", "L"):
        p, q = ph.get(s), md.get(s)
        print(s, "photo", {k: round(v, 3) for k, v in p.items()}, "model", None if q is None else {k: round(v, 3) for k, v in q.items()})
    print(json.dumps({"photo": ph, "model": md}))
