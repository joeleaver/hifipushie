"""foldgate.py <model> <tag> [<tag> ...]: the fold gate. lidfold.read_lid on eyeshot's front close-up pair (photo | ours)
at the model's own scale (the fitted camera's mm per px at the eyes, both halves the same crop): visible crease
height (tps), brow fat span (bfs), the line's darkness and width, per eye at inner / middle / outer. The photo row is
read once (from the first tag's pair)."""
import json
import os
import sys

import numpy as np
from PIL import Image

import stage
from hifipushie import likeness, lidfold, store
from hifipushie.spec import expand_mirror

name, tags = sys.argv[1], sys.argv[2:]
E = "/mnt/data/hifipushie/eyedetail/out"
spec = store.load(name)
J = {k: np.asarray(v["pos"], float) for k, v in expand_mirror(spec)["joints"].items() if "pos" in v}
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
v, cam = refs["views"][0], refs["cameras"][0]
U = np.array(list(v["points"].values()), float)
lo, hi = U.min(0), U.max(0)
s = 0.95 * (hi - lo)[0] * float(os.environ.get("ZOOM_SCALE", "1"))
c = np.array([0.5 * (lo[0] + hi[0]), lo[1] + 0.55 * (hi[1] - lo[1])])
fr = stage.fitted_frame(cam, [c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2], "zoom")
dist = float(np.linalg.norm(0.5 * (J["eye.L"] + J["eye.R"]) - np.asarray(fr["eye"])))


def read(im):
    mmpx = 2 * dist * np.tan(np.radians(fr["fov"]) / 2) * 1000 / im.width
    up = int(__import__("os").environ.get("UP", "2"))
    big = im.resize((im.width * up, im.height * up), Image.LANCZOS)  # (the detector likes a bigger face)
    d = likeness.detect([big])[0]
    if d is None:
        return None
    return lidfold.read_lid(big, np.asarray(d, float)[:, :2], mmpx / up)


def row(lab, r):
    if r is None:
        print(f"{lab:>12}: no face")
        return
    for sd, cols in zip(("R", "L"), r):
        print(f"{lab:>12} {sd}: " + "  ".join(f"tps {c_['tps']:5.2f} bfs {c_['bfs']:5.2f} dark {c_['dark']:.2f} w {c_['width']}"
                                              for c_ in cols))
        cs = [c_ for c_ in cols if "line_v" in c_]
        if cs:
            print(f"{'':>14}colour (mean of thirds): " + "  ".join(
                f"{k} {np.nanmean([c_[k] for c_ in cs]):+.3f}" for k in ("line_v", "line_ds", "line_dh", "above_v", "below_v")))


out = {}
for i, tag in enumerate(tags):
    pair = Image.open(f"{E}/{tag}_face.png").convert("RGB")
    w = pair.width // 2
    if i == 0:
        out["photo"] = read(pair.crop((0, 0, w, pair.height)))
        row("photo", out["photo"])
    out[tag] = read(pair.crop((w, 0, 2 * w, pair.height)))
    row(tag, out[tag])
json.dump(out, open(f"{E}/foldgate_{name}_{'_'.join(tags)}.json", "w"), default=float)
