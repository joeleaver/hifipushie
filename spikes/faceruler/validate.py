"""validate.py <n> <tag>: the picture ruler against the mesh truth on clay pictures of known GNM heads.
Pairs: model A, pictures of B (front, 3/4, profile). kinds: transplant (A + one region of a donor, as the driving
test), random (B = A + 0.7 N), far (A = GNM's template, B ~ N(0, 1): a block-in's start).
Variants: exact (clay, the camera known), hair (no outline where hair would be), cam (hair + the pictures taken
through a camera off by a random shift / scale / roll, solved with that much freedom), outline (cam, outlines only: no
iris / lip / brow reads). -> $G/out/validate_<tag>.json + a table (bias, sd of reader - truth, per measure)."""
import json
import os
import sys

import numpy as np

import drv
from hifipushie import face_ruler as fr, gnm_mm

n, tag = int(sys.argv[1]), sys.argv[2]
G = os.environ["G"]
KINDS = ("front", "3q", "profile")
CAM_SD = (3.0, 3.0, 2.0, 1.5)
VAR = ("exact", "hair", "cam", "outline")
rng = np.random.default_rng(20261011)
rows = []
for i in range(n):
    kind = ("transplant", "random", "far")[i % 3]
    cA = rng.normal(size=170) if kind != "far" else np.zeros(170)
    if kind == "transplant":
        cB = drv.transplant(cA, rng.normal(size=170), list(drv.REGIONS)[(i // 3) % len(drv.REGIONS)], 1.0)
    elif kind == "random":
        cB = cA + 0.7 * rng.normal(size=170)
    else:
        cB = rng.normal(size=170)
    A, B = fr.gnm_head(cA), fr.gnm_head(cB)
    truth = {r["measure"]: r["gap"] for r in gnm_mm.gaps(drv.verts(cA), drv.verts(cB))}
    cams = {k: fr.camera(k) for k in KINDS}
    pert = {}
    for k in KINDS:        # the camera the picture was REALLY taken through (the ruler is given cams[k])
        c = dict(cams[k])
        c["t"] = [rng.normal(0, CAM_SD[0] * 1e-3), rng.normal(0, CAM_SD[1] * 1e-3), c["t"][2]]
        c["f"] = c["f"] * (1 + rng.normal(0, CAM_SD[2] * 0.01))
        c["r"] = [0.0, 0.0, float(np.radians(rng.normal(0, CAM_SD[3])))]
        pert[k] = c
    pics = {k: fr.clay(B, cams[k]) for k in KINDS}
    pics_p = {k: fr.clay(B, pert[k]) for k in KINDS}
    row = {"kind": kind, "truth": truth, "dc": float(np.linalg.norm(cB - cA))}
    for v in VAR:
        views = [{"img": (pics if v in ("exact", "hair") else pics_p)[k], "cam": cams[k], "kind": k, "style": "clay",
                  "hair": v != "exact", "colour": v != "outline"} for k in KINDS]
        res = fr.read(A, views, cam_sd=None if v in ("exact", "hair") else CAM_SD, rounds=3 if v in ("exact", "hair") else 4)
        row[v] = {r["measure"]: [r["gap"], r["err"]] for r in res["gaps"]}
        row[v + "_dc"] = float(np.linalg.norm(res["dc"] - (cB - cA)))
    rows.append(row)
    print(i, kind, f"|dc| {row['dc']:.1f}", " ".join(f"{v}: dc err {row[v + '_dc']:.1f}" for v in VAR), flush=True)
    json.dump(rows, open(f"{G}/out/validate_{tag}.json", "w"))
sd = gnm_mm.sd()
for sel in ("all", "transplant", "random", "far"):
    R = [r for r in rows if sel in ("all", r["kind"])]
    print(f"\n== {sel} ({len(R)} pairs): reader - truth, mm: bias / sd per variant; pop sd; S/N = pop sd / rms error")
    print(f"{'measure':18s} pop sd | " + " | ".join(f"{v:^18s}" for v in VAR))
    for m in gnm_mm.NAMES:
        line = f"{m:18s} {sd[m]:5.1f}  | "
        for v in VAR:
            e = np.array([r[v][m][0] - r["truth"][m] for r in R])
            rms = np.sqrt((e ** 2).mean())
            line += f"{e.mean():+5.2f} {e.std():5.2f} {sd[m] / rms:4.0f}x | "
        print(line)
