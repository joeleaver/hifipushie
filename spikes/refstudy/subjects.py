"""The ground-truth set: heads whose 3D shape is known, rendered as "reference pictures" with what real references
do to us (unknown camera and lens, an expression in one picture, two looks).

  S*: GNM seeds (all 170 head components, sigma 1), picked from a pool for strong features.
  O*: heads GNM's identity space does not contain exactly: MakeHuman's own heads (the registration fields) with a
      half-strength seed on top.
Writes D/truth/<id>.npz (V = neutral truth, c where it has one) + <id>_<view>.png + <id>.json (cameras, notes).
"""
import json
import sys

import numpy as np
from PIL import Image

import rs

OUT = rs.D / "truth"
VIEWS = {"front": 0.0, "tq": 40.0, "profile": 88.0, "tq2": -38.0}


def pool_pick(n_pool=300):
    """Seeds with strong features, by plain measures on the neutral head."""
    g = rs.gnm()
    rows = []
    for seed in range(n_pool):
        c = np.random.default_rng(1000 + seed).normal(0, 1.0, rs.K_TRUE)
        L = g["L0"] + np.tensordot(c, g["LB"][:rs.K_TRUE], 1)
        io = L[68, 0] - L[69, 0]
        rows.append([seed, (L[33, 1] - L[30, 1]) / io,            # nose projection
                     (L[12, 0] - L[4, 0]) / (L[16, 0] - L[0, 0]),  # jaw width / face width: square
                     (L[8, 1] - L[27, 1]) / io,                    # chin behind the nasion: receding (+)
                     (L[16, 0] - L[0, 0]) / (L[27, 2] - L[8, 2]),  # width / height: heavy vs long
                     (L[35, 0] - L[31, 0]) / io])                  # nose width
    R = np.array(rows)
    pick = {"S1_bignose": int(R[np.argmax(R[:, 1]), 0]), "S2_squarejaw": int(R[np.argmax(R[:, 2]), 0]),
            "S3_recedingchin": int(R[np.argmax(R[:, 3]), 0]), "S4_long": int(R[np.argmin(R[:, 4]), 0]),
            "S5_broad": int(R[np.argmax(R[:, 4]), 0]), "S6_plain": 7}
    return pick


def subject_heads():
    g = rs.gnm()
    out = {}
    for name, seed in pool_pick().items():
        c = np.random.default_rng(1000 + seed).normal(0, 1.0, rs.K_TRUE)
        out[name] = {"V": rs.head(c), "c": c, "kind": "gnm seed", "note": f"seed {seed}"}
    for name, (age, sex, wt, seed) in {"O1_mh_heavy_man": (45, 1.0, 0.9, 11), "O2_mh_old_woman": (68, 0.0, 0.3, 12),
                                       "O3_mh_young_man": (22, 1.0, 0.45, 13), "O4_mh_woman": (32, 0.0, 0.6, 14)}.items():
        c = np.random.default_rng(seed).normal(0, 0.5, rs.K_TRUE)
        out[name] = {"V": rs.head(c, extra=rs.mh_field(age, sex, wt)), "c": None, "kind": "makehuman field + 0.5 seed",
                     "note": f"age {age} sex {sex} weight {wt}"}
    return out


def pictures(name, sub, rng):
    V = sub["V"]
    meta = {"views": {}}
    i = int(name[1])
    expr = None
    if i % 3 == 1:   # every third subject squints and smiles a little in the front picture only (as Garrett's does)
        expr = rs.expression({"lid_upper": 0.0018, "lid_lower": 0.0008, "smile": 0.004, "brow_inner": -0.002})
    albedo = rs.skinned_albedo(i) if i % 2 == 0 else None
    for vn, yaw in VIEWS.items():
        lens = float(rng.choice([50, 70, 85]))
        if name.startswith("S5") and vn == "front":
            lens = 28.0
        cam = rs.make_cam(V, yaw=yaw + rng.normal(0, 4), pitch=rng.normal(0, 5), roll=rng.normal(0, 2.5), lens=lens,
                          fill=rng.uniform(0.5, 0.68), off=(rng.normal(0, 0.01), rng.normal(0, 0.01)))
        Vv = V + (expr if (expr is not None and vn == "front") else 0.0)
        light = [-0.35 + rng.normal(0, 0.25), -0.45 + rng.normal(0, 0.15), -0.82]
        img, zb = rs.render(Vv, cam, light=light, albedo=albedo)
        Image.fromarray(img).save(OUT / f"{name}_{vn}.png")
        np.save(OUT / f"{name}_{vn}_zb.npy", zb.astype(np.float32))
        meta["views"][vn] = {"cam": cam, "expression": bool(expr is not None and vn == "front"), "light": light,
                             "look": "skinned" if albedo is not None else "clay"}
    np.savez_compressed(OUT / f"{name}.npz", V=V, c=np.zeros(0) if sub["c"] is None else sub["c"],
                        e=np.zeros(0) if expr is None else expr)
    meta.update(kind=sub["kind"], note=sub["note"])
    (OUT / f"{name}.json").write_text(json.dumps(meta, indent=1))


def load(name):
    z = np.load(OUT / f"{name}.npz")
    meta = json.loads((OUT / f"{name}.json").read_text())
    return {"name": name, "V": z["V"], "c": z["c"] if len(z["c"]) else None, "e": z["e"] if len(z["e"]) else None, **meta}


def names():
    return sorted(p.stem for p in OUT.glob("*.json"))


def image(name, view):
    return np.asarray(Image.open(OUT / f"{name}_{view}.png").convert("RGB"))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    subs = subject_heads()
    mean = rs.head()
    print(f"{'subject':18s} " + rs.HEADER + "   (distance of the truth from GNM's MEAN head, mm: how unusual it is)")
    for name, sub in subs.items():
        pictures(name, sub, rng)
        print(f"{name:18s} " + rs.row(rs.score(mean, sub["V"])), sub["note"])
    tiles = []
    for name in subs:
        tiles.append(np.concatenate([image(name, v)[::2, ::2] for v in VIEWS], 1))
    Image.fromarray(np.concatenate(tiles, 0)).save(rs.D / "out" / "truth_sheet.png")
    print("sheet", rs.D / "out" / "truth_sheet.png", "regions", {k: len(v) for k, v in rs.gnm()["regions"].items()})
