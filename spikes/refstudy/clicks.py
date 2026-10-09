"""The click test: how well does an LLM click ~20 named points on a gridded crop of a reference picture?
  run.sh clicks.py make                 -> D/clicks/<subject>_front_grid.png + names.txt
  run.sh clicks.py score <subject>=<answers.json> ...   -> error per point (mm) vs the truth, and the fits with the
                                                           real clicks (front picture: clicks alone, + detector, + read)
Answers: {"<name>": [x, y]} in the GRID's coordinates (the numbers printed on the picture)."""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

import exp2
import fitlib
import rs
import subjects
import table as tb
from hifipushie import humanmacro as hm

OUT = rs.D / "clicks"
POINTS = {   # name: (landmark index, what to click). The subject's LEFT is on the picture's RIGHT.
    "eye_outer_R": (36, "outer corner of the eye on the picture's LEFT"), "eye_inner_R": (39, "inner corner (by the nose) of the eye on the picture's LEFT"),
    "eye_inner_L": (42, "inner corner of the eye on the picture's RIGHT"), "eye_outer_L": (45, "outer corner of the eye on the picture's RIGHT"),
    "pupil_R": (69, "centre of the iris of the eye on the picture's LEFT"), "pupil_L": (68, "centre of the iris of the eye on the picture's RIGHT"),
    "nasion": (27, "the deepest point of the nose's root between the eyes, on the mid-line"), "nose_tip": (30, "the most forward point of the nose tip"),
    "subnasale": (33, "where the nose's underside meets the upper lip, on the mid-line"),
    "ala_R": (31, "outermost point of the nostril wing on the picture's LEFT"), "ala_L": (35, "outermost point of the nostril wing on the picture's RIGHT"),
    "mouth_corner_R": (48, "mouth corner on the picture's LEFT"), "mouth_corner_L": (54, "mouth corner on the picture's RIGHT"),
    "lip_top": (51, "top edge of the upper lip's red, on the mid-line (the cupid's bow's dip)"),
    "lip_seam": (62, "where the lips meet, on the mid-line"), "lip_bottom": (57, "bottom edge of the lower lip's red, on the mid-line"),
    "chin_bottom": (8, "lowest point of the chin on the mid-line"),
    "brow_outer_R": (17, "outer end of the eyebrow on the picture's LEFT"), "brow_inner_R": (21, "inner end of the eyebrow on the picture's LEFT"),
    "brow_inner_L": (22, "inner end of the eyebrow on the picture's RIGHT"), "brow_outer_L": (26, "outer end of the eyebrow on the picture's RIGHT")}
SCALE = 2.5


def crop_box(s, view="front"):
    cam, V = tb.view_true(s, view)
    L = rs.humanfit.project(cam, rs.landmarks(V))
    lo, hi = L.min(0), L.max(0)
    pad = 0.25 * (hi - lo).max()
    return [int(lo[0] - pad), int(lo[1] - pad * 1.6), int(hi[0] + pad), int(hi[1] + pad)]


def make(names):
    OUT.mkdir(exist_ok=True)
    for n in names:
        s = subjects.load(n)
        box = crop_box(s)
        im = Image.fromarray(subjects.image(n, "front")).crop(box)
        im = im.resize((int(im.size[0] * SCALE), int(im.size[1] * SCALE)), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        for x in range(0, im.size[0], 50):
            d.line([(x, 0), (x, im.size[1])], fill=(60, 120, 255) if x % 100 == 0 else (150, 190, 255), width=1)
            if x % 100 == 0:
                d.text((x + 2, 2), str(x), fill=(0, 0, 200))
        for y in range(0, im.size[1], 50):
            d.line([(0, y), (im.size[0], y)], fill=(60, 120, 255) if y % 100 == 0 else (150, 190, 255), width=1)
            if y % 100 == 0:
                d.text((2, y + 2), str(y), fill=(0, 0, 200))
        im.save(OUT / f"{n}_front_grid.png")
        print(OUT / f"{n}_front_grid.png", im.size)
    (OUT / "names.txt").write_text("\n".join(f"{k}: {v[1]}" for k, v in POINTS.items()))


def score(pairs):
    errs = {k: [] for k in POINTS}
    res = {}
    for p in pairs:
        n, f = p.split("=")
        s = subjects.load(n)
        ans = json.load(open(f))
        box = crop_box(s)
        cam, V = tb.view_true(s, "front")
        Lp = rs.humanfit.project(cam, rs.landmarks(V))
        mmpx = cam["t"][2] / cam["f"] * 1000
        ids, uv = [], []
        for k, (i, _) in POINTS.items():
            if k not in ans:
                continue
            q = np.array(ans[k], float) / SCALE + box[:2]
            errs[k].append(float(np.linalg.norm(q - Lp[i]) * mmpx))
            ids.append(i)
            uv.append(q)
        e = np.array([errs[k][-1] for k in POINTS if k in ans])
        print(f"{n} ({s['views']['front']['look']}{', expression' if s['views']['front']['expression'] else ''}): {len(e)} points, "
              f"median {np.median(e):.2f} mm, mean {e.mean():.2f}, worst {e.max():.2f}")
        click = {"pts": fitlib.points_lm(np.array(ids)), "uv": np.array(uv), "sig": 2.0, "size": cam["size"], "yaw": 0.0}
        det = exp2.ev(s, ["front"])
        rd = hm.prior_rows(exp2.reader(s))
        for tag, fn in (("mean head", lambda: {"c": np.zeros(hm.K)}), ("front, detector MAP", lambda: fitlib.fit(det, robust=True)),
                        ("front, REAL clicks alone", lambda: fitlib.fit([click])),
                        ("front, detector + REAL clicks", lambda: fitlib.fit(det + [click], robust=True)),
                        ("front, detector + REAL clicks + read", lambda: fitlib.fit(det + [click], robust=True, rows=rd)),
                        ("front, detector + read", lambda: fitlib.fit(det, robust=True, rows=rd))):
            res.setdefault(tag, {})[n] = rs.score(rs.head(fn()["c"]), s["V"])
    print("\nerror per point over the pictures (mm): " + ", ".join(f"{k} {np.mean(v):.1f}" for k, v in errs.items() if v))
    print()
    tb.show(res)


if __name__ == "__main__":
    if sys.argv[1] == "make":
        make(sys.argv[2:])
    else:
        score(sys.argv[2:])
