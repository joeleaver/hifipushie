"""Profile pictures: clicks may be the ONLY evidence there (the detector finds 1 profile in 36). Is "the view that
pays" still true with REAL placed points?
  run.sh clicks3.py makep <subject> ...                 -> D/clicks/<subject>_profile_grid.png, names_profile.txt
  run.sh clicks3.py scorep <subject>=<answers.json> ... -> bias / scatter per point, fits (bias held out by picture)"""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

import exp2
import fitlib
import rs
import subjects
import table as tb
from clicks import OUT
from hifipushie import humanmacro as hm

PROF = {"nasion": (27, "the deepest point of the hollow between forehead and nose, on the profile's outline"),
        "nose_tip": (30, "the most forward point of the nose on the profile's outline"),
        "subnasale": (33, "the corner where the nose's underside meets the upper lip, on the outline"),
        "lip_top": (51, "on the outline, where the upper lip's red begins (the top edge of the red of the upper lip)"),
        "lip_seam": (62, "on the outline, where the two lips meet"),
        "lip_bottom": (57, "on the outline, where the lower lip's red ends (its bottom edge, above the groove over the chin)"),
        "chin_bottom": (8, "the lowest point of the chin's outline (where the chin turns into the underside of the jaw)"),
        "eye_outer": ((45, 36), "the outer corner of the visible eye"),
        "mouth_corner": ((54, 48), "the visible corner of the mouth")}
K = 3.0


def prof_truth(s):
    cam, V = tb.view_true(s, "profile")
    L = rs.landmarks(V)
    z = rs.cam_xform(cam, L)[:, 2]
    ids = {k: (i if isinstance(i, int) else (i[0] if z[i[0]] < z[i[1]] else i[1])) for k, (i, _) in PROF.items()}
    return cam, rs.humanfit.project(cam, L), ids


def prof_box(s):
    cam, Lp, ids = prof_truth(s)
    P = np.array([Lp[i] for i in ids.values()])
    lo, hi = P.min(0), P.max(0)
    pad = 0.35 * (hi - lo).max()
    return [int(lo[0] - pad), int(lo[1] - pad), int(hi[0] + pad), int(hi[1] + pad)]


def makep(names):
    OUT.mkdir(exist_ok=True)
    for n in names:
        s = subjects.load(n)
        im = Image.fromarray(subjects.image(n, "profile")).crop(prof_box(s))
        im = im.resize((int(im.size[0] * K), int(im.size[1] * K)), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        for x in range(0, im.size[0], 50):
            d.line([(x, 0), (x, im.size[1])], fill=(60, 120, 255) if x % 100 == 0 else (170, 200, 255))
            if x % 100 == 0:
                d.text((x + 2, 2), str(x), fill=(0, 0, 200))
        for y in range(0, im.size[1], 50):
            d.line([(0, y), (im.size[0], y)], fill=(60, 120, 255) if y % 100 == 0 else (170, 200, 255))
            if y % 100 == 0:
                d.text((2, y + 2), str(y), fill=(0, 0, 200))
        im.save(OUT / f"{n}_profile_grid.png")
        print(OUT / f"{n}_profile_grid.png", im.size)
    (OUT / "names_profile.txt").write_text("\n".join(f"{k}: {v[1]}" for k, v in PROF.items()))


def scorep(pairs):
    err, pix, truth = {}, {}, {}
    for p in pairs:
        n, f = p.split("=")
        s = subjects.load(n)
        cam, Lp, ids = prof_truth(s)
        box = prof_box(s)
        mmpx = cam["t"][2] / cam["f"] * 1000
        ans = json.load(open(f))
        pix[n] = {k: np.array(ans[k], float) / K + box[:2] for k in PROF if k in ans}
        err[n] = {k: (pix[n][k] - Lp[ids[k]]) * mmpx for k in pix[n]}
        truth[n] = (s, cam, ids, mmpx)
    print("profile clicks: bias (dx, dy mm in the picture; y down), scatter about it, rms")
    for k in PROF:
        v = np.array([err[n][k] for n in err if k in err[n]])
        print(f"  {k:13s} bias {v.mean(0)[0]:+5.1f} {v.mean(0)[1]:+5.1f}   scatter {np.sqrt(((v - v.mean(0)) ** 2).sum(1).mean()):4.1f}   rms {np.sqrt((v ** 2).sum(1).mean()):4.1f}")
    res = {}
    for n in err:
        s, cam, ids, mmpx = truth[n]
        others = [m for m in err if m != n]
        ks = [k for k in err[n] if all(k in err[m] for m in others)]
        bias = {k: np.mean([err[m][k] for m in others], 0) for k in ks}
        sig = np.array([max(float(np.sqrt(np.mean([((err[m][k] - bias[k]) ** 2).sum() for m in others]))), 1.0) for k in ks])
        li = np.array([ids[k] for k in ks])
        uv_raw = np.array([pix[n][k] for k in ks])
        uv_cal = np.array([pix[n][k] - bias[k] / mmpx for k in ks])
        mk = lambda uv, sg: {"pts": fitlib.points_lm(li), "uv": uv, "sig": sg, "size": cam["size"], "yaw": subjects.VIEWS["profile"]}  # noqa: E731
        det = exp2.ev(s, ["front"])
        rd = hm.prior_rows(exp2.reader(s))
        sim = tb.ev_oracle(s, "profile", noise=1.5, ids=tb.HAND, seed=3)
        for tag, fn in (("front detector alone", lambda: fitlib.fit(det, robust=True)),
                        ("+ profile, SIMULATED clicks +-1.5", lambda: fitlib.fit(det + [sim], robust=True)),
                        ("+ profile, REAL clicks raw (sigma 3)", lambda: fitlib.fit(det + [mk(uv_raw, 3.0)], robust=True)),
                        ("+ profile, REAL clicks, bias out", lambda: fitlib.fit(det + [mk(uv_cal, sig)], robust=True)),
                        ("+ profile REAL (bias out) + read", lambda: fitlib.fit(det + [mk(uv_cal, sig)], robust=True, rows=rd)),
                        ("front detector + read", lambda: fitlib.fit(det, robust=True, rows=rd))):
            res.setdefault(tag, {})[n] = rs.score(rs.head(fn()["c"]), s["V"])
    print()
    tb.show(res)


if __name__ == "__main__":
    {"makep": makep, "scorep": scorep}[sys.argv[1]](sys.argv[2:])
