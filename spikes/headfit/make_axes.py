"""One-off, after make_table.py: how MakeHuman's age / sex / weight move a head, sampled once and stored as package data
(src/hifipushie/head_axes.npz), so headfit works without the MakeHuman pack at runtime and on any body.

    uv run python spikes/headfit/make_axes.py

Stored, all at the table's points (68 landmarks, 4 cranium points, the dense pairs), in interocular units round the eye
midpoint, GNM's frame, as moves from the reference head (age 25, sex 0.5, weight 0.5):
  age_sex  (ages, 2, points, 3)   the head at each age for sex 0 (female) and 1 (male), weight 0.5
  weight   (2, 2, points, 3)      [sex][light 0.1, heavy 0.9] minus that sex's weight-0.5 head, at age 30
  io       (ages, 2)              the interocular (m) at height-free scale, for the head's size
  ref      (points, 3)            the reference head's own points (what MakeHuman's head IS, for headfit's `toward`)
"""
from pathlib import Path

import numpy as np

from hifipushie import headfit

AGES = [1, 3, 6, 9, 12, 15, 18, 25, 35, 50, 65, 80, 90]


def main():
    t = headfit.table()
    ref, _ = headfit.mh_points(t["reference"])
    A, IO = [], []
    for a in AGES:
        row, ior = [], []
        for s in (0.0, 1.0):
            X, io = headfit.mh_points({"age": a, "sex": s, "weight": 0.5, "muscle": 0.5, "growth": False})
            row.append(X - ref)
            ior.append(io)
        A.append(row)
        IO.append(ior)
    W = []
    for s in (0.0, 1.0):
        mid, _ = headfit.mh_points({"age": 30, "sex": s, "weight": 0.5, "muscle": 0.5, "growth": False})
        W.append([headfit.mh_points({"age": 30, "sex": s, "weight": w, "muscle": 0.5})[0] - mid for w in (0.1, 0.9)])
    dest = Path(headfit.__file__).with_name("head_axes.npz")
    np.savez_compressed(dest, ages=np.array(AGES, float), age_sex=np.array(A, np.float32), weight=np.array(W, np.float32),
                        io=np.array(IO, np.float32), ref=np.array(ref, np.float32))
    print("wrote", dest, np.array(A).shape, "rms move child", float(np.sqrt((np.array(A)[2] ** 2).sum(-1).mean())))
    # how well the table reproduces MakeHuman between its samples
    headfit._CACHE.pop("axes_data", None)
    for p in ({"age": 7, "sex": 0.5, "weight": 0.45}, {"age": 32, "sex": 0.0, "weight": 0.5}, {"age": 54, "sex": 1.0, "weight": 0.6},
              {"age": 78, "sex": 0.0, "weight": 0.4}, {"age": 82, "sex": 1.0, "weight": 0.5}, {"age": 16, "sex": 0.0, "weight": 0.42}):
        d0 = headfit.mh_points({**p, "muscle": 0.5, "growth": False})[0] - ref
        d1, io = headfit.shape_delta(p["age"], p["sex"], p["weight"])
        print(p, "table vs MakeHuman rms (io)", round(float(np.sqrt(((d0 - d1) ** 2).sum(1).mean())), 4), "of", round(float(np.sqrt((d0 ** 2).sum(1).mean())), 4))


if __name__ == "__main__":
    main()
