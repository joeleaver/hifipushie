"""gates.py <accepted model> <model>...: faces6 WHOLE-FACE GATES (coordinator: a fit that wins feature crops while the
whole face becomes someone else is a regression). Per model, whole-head clay renders (fast renderer, AO + soft key,
brows) through the ACCEPTED model's front and 3/4 cameras, then:
  sex_gnm   the identity on GNM's own labelled sex direction (the semantic sampler's class means, the audit's
            cvae_stats.npz): -1 = the female class mean, +1 = the male class mean, along the LDA-free mean difference;
  p_female, age   InsightFace genderage on the clay renders (agesex.py; read relative to the accepted model's clay:
            clay is bald and greyish, it reads older and more male than the person) and on the photos (calibration);
  id_acc    ArcFace cosine of each render to the accepted model's render of the same view (does this step keep the
            person?), id_photo the same to the photo.
Writes $F/out/gates_<model>_v<k>.png and $F/out/gates.json (appends)."""
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import agesex
from hifipushie import faceid, humanfit, likeness, store

F = Path(os.environ.get("F", "/mnt/data/hifipushie/faces6"))
PX = int(os.environ.get("PX", "512"))
VIEWS = [int(v) for v in os.environ.get("GVIEWS", "0,1").split(",")]
CV = np.load(F / "cvae_stats.npz")


def sex_read(c):
    c = np.r_[np.asarray(c, float), np.zeros(170)][:170]
    d = CV["m_m"] - CV["m_f"]
    mid = 0.5 * (CV["m_m"] + CV["m_f"])
    return float((c - mid) @ d / (d @ d) * 2)


def ident(sp):
    idn = sp["base"]["head"].get("identity") or {}
    if isinstance(idn, dict):
        v = np.zeros(170)
        for k, x in idn.items():
            if k.startswith("head_"):
                v[int(k.split("_")[1])] = float(x)
        return v
    return np.asarray(idn, float)


def renders(m, refs):
    st = humanfit.state(store.load(m)["base"])
    mesh = likeness.model_mesh_from_state(st)
    out = {}
    for vi in VIEWS:
        cam = refs["cameras"][vi]
        P = humanfit.project(cam, st["L"])
        c = 0.5 * (P.min(0) + P.max(0))
        side = 1.6 * float(np.max(P.max(0) - P.min(0)))
        box = (c[0] - side / 2, c[1] - side * 0.55, c[0] + side / 2, c[1] + side * 0.45)
        im = likeness.render(mesh, cam, box, px=PX, brows=True, ao=True, shadow=8.0)[0].convert("RGB")
        p = F / "out" / f"gates_{m}_v{vi}.png"
        im.save(p)
        out[vi] = (im, p, box)
    return out


if __name__ == "__main__":
    acc, models = sys.argv[1], sys.argv[2:]
    refs = json.loads((store.HOME / acc / "human_refs.json").read_text())
    R = {m: renders(m, refs) for m in [acc] + [m for m in models if m != acc]}
    photos = {vi: Image.open(refs["views"][vi]["image"]).convert("RGB") for vi in VIEWS}
    ph_reads = agesex.read([refs["views"][vi]["image"] for vi in VIEWS])
    print("photo", {vi: {k: round(v, 3) for k, v in r.items() if k in ("p_female", "age")} for vi, r in zip(VIEWS, ph_reads)})
    rows = []
    for m in R:
        sp = store.load(m)
        c = ident(sp)
        reads = agesex.read([str(R[m][vi][1]) for vi in VIEWS])
        row = {"model": m, "c_norm": round(float(np.linalg.norm(c)), 2), "sex_gnm": round(sex_read(c), 2)}
        for vi, rd in zip(VIEWS, reads):
            row[f"v{vi}_p_female"] = None if rd is None else round(rd["p_female"], 3)
            row[f"v{vi}_age"] = None if rd is None else round(rd["age"], 1)
            row[f"v{vi}_id_acc"] = faceid.similarity(R[m][vi][0], R[acc][vi][0])["arcface"]
            row[f"v{vi}_id_photo"] = faceid.similarity(R[m][vi][0], photos[vi])["arcface"]
        rows.append(row)
        print(json.dumps(row), flush=True)
    with open(F / "out" / "gates.json", "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
