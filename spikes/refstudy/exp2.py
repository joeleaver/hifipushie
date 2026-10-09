"""Second table: macros as the fit's parameters, a character read as a prior, the lens, expression by subject.
  run.sh exp2.py [prefix ...]"""
import json
import sys
import time

import numpy as np

import fitlib
import rs
import subjects
import table as tb
from hifipushie import humanmacro as hm

READABLE = ["face_length", "face_width", "cheekbone_width", "jaw_width", "jaw_square", "chin_width", "chin_height",
            "chin_projection", "nose_length", "nose_projection", "nose_width", "nose_upturn", "bridge_height", "brow_ridge",
            "brow_height", "eye_depth", "eye_width", "eye_height", "eye_spacing", "mouth_width", "lip_fullness",
            "cheek_fullness", "forehead_slope", "neck_width", "ear_size", "ear_out", "under_chin"]
FT = ["front", "tq"]


def reader(sub, noise=0.7, thr=0.8, sd=0.8, exact=False, only=None):
    """What a person (or a vision model) says looking at the pictures, simulated from the truth: each readable macro
    seen with an error of `noise` sigma, said as "strongly +", "strongly -" or nothing special."""
    z = hm.read(V=sub["V"])
    rng = np.random.default_rng(abs(hash(sub["name"])) % 10000)
    out = {}
    for k in (only or READABLE):
        if exact:
            out[k] = (z[k], 0.2)
            continue
        zo = z[k] + rng.normal(0, noise)
        out[k] = (1.5 * np.sign(zo) if abs(zo) > thr else 0.0, sd)
    return out


def macro_basis_rows(w=30.0):
    t = hm.table()
    Q = np.linalg.qr((t["A"] / t["sd"][:, None]).T)[0]
    return (np.eye(hm.K) - Q @ Q.T) * w, np.zeros(hm.K)


def stack(*rows):
    return np.vstack([r[0] for r in rows]), np.concatenate([r[1] for r in rows])


def ev(s, views=FT, **kw):
    return tb.evidence(s, views, "mp478", infl=2.0, **kw)


def macro_then_residual(s):
    f1 = fitlib.fit(ev(s), robust=True, rows=macro_basis_rows())
    return fitlib.fit(ev(s), robust=True, mu=f1["c"], lam=4.0, c_init=f1["c"])


def true_focal(s, views):
    e = ev(s, views)
    for x, v in zip(e, views):
        x["focal"] = s["views"][v]["cam"]["f"]
    return e


def guess_focal(s, views, lens=60.0):
    e = ev(s, views)
    for x in e:
        x["f_prior"] = (lens / 36.0 * x["size"][0], 0.35)
    return e


METHODS = {
    "M0 detector points, MAP (= B3b)": lambda s: fitlib.fit(ev(s), robust=True),
    "M1 macros only (37 numbers)": lambda s: fitlib.fit(ev(s), robust=True, rows=macro_basis_rows()),
    "M2 macros, then residual with a strong prior": macro_then_residual,
    "P0 a character read ALONE (no pictures fitted)": lambda s: {"c": np.linalg.lstsq(np.vstack([hm.prior_rows(reader(s))[0], np.eye(hm.K)]), np.r_[hm.prior_rows(reader(s))[1], np.zeros(hm.K)], rcond=None)[0]},
    "P1 M0 + character read (noisy reader)": lambda s: fitlib.fit(ev(s), robust=True, rows=hm.prior_rows(reader(s))),
    "P2 M0 + read of jaw/chin/nose depth only": lambda s: fitlib.fit(ev(s), robust=True, rows=hm.prior_rows(reader(s, only=["jaw_square", "jaw_width", "chin_projection", "chin_width", "nose_projection", "nose_upturn", "brow_ridge", "cheek_fullness", "forehead_slope", "under_chin"]))),
    "P3 M0 + macros measured exactly (ceiling)": lambda s: fitlib.fit(ev(s), robust=True, rows=hm.prior_rows(reader(s, exact=True))),
    "P4 front only + character read": lambda s: fitlib.fit(ev(s, ["front"]), robust=True, rows=hm.prior_rows(reader(s))),
    "P5 front only, no read": lambda s: fitlib.fit(ev(s, ["front"]), robust=True),
    "F1 M0, the true lens given": lambda s: fitlib.fit(true_focal(s, FT), robust=True),
    "F2 M0, lens guessed 60 mm +-35%": lambda s: fitlib.fit(guess_focal(s, FT), robust=True),
    "E1 M0 + expression solved per picture": lambda s: fitlib.fit(ev(s), robust=True, expr=True, lam_e=1.0),
    "E2 same, expression prior x4": lambda s: fitlib.fit(ev(s), robust=True, expr=True, lam_e=4.0),
}


def far_contour(e, s, view, sig=1.0):
    """A hand trace of the face's far-side contour in a turned picture (brow, cheek / nose, lips, chin against the
    background): the true outline's pixels on the side the nose points to."""
    cam, V = tb.view_true(s, view)
    zb = np.load(subjects.OUT / f"{s['name']}_{view}_zb.npy")
    o = rs.outline(zb, cam, V)
    L = rs.humanfit.project(cam, rs.landmarks(V))
    sgn = np.sign(L[30, 0] - L[36:48, 0].mean())
    far_eye = L[36:48, 0].max() if sgn > 0 else L[36:48, 0].min()
    k = (o[:, 0] - far_eye) * sgn > -3
    rng = np.random.default_rng(5)
    mmpx = cam["t"][2] / cam["f"] * 1000
    return {**e, "outline": o[k][::2] + rng.normal(0, 0.5 / mmpx, (int(np.ceil(k.sum() / 2)), 2)), "sig_o": sig}


def jaw_points(s, view, noise=1.5):
    """Hand-clicked jaw line points with the right definition (GNM's own jaw contour, the visible ones)."""
    e = tb.ev_oracle(s, view, noise=noise, ids=np.arange(0, 17), seed=11)
    return e


def traced(s, contour=True, jaw=True, views=FT, profile=False):
    out = []
    for e, v in zip(ev(s, views), views):
        if contour and v != "front":
            e = far_contour(e, s, v)
        out.append(e)
        if jaw:
            out.append(jaw_points(s, v))
    if profile:
        e = tb.ev_oracle(s, "profile", noise=1.5, ids=tb.HAND, seed=3)
        out.append(far_contour(e, s, "profile"))
    return out


METHODS.update({
    "C1 M0 + traced far contour in the 3/4": lambda s: fitlib.fit(traced(s, jaw=False), robust=True, rounds=10),
    "C2 M0 + clicked jaw line (right definition)": lambda s: fitlib.fit(traced(s, contour=False), robust=True),
    "C3 M0 + contour + jaw line": lambda s: fitlib.fit(traced(s), robust=True, rounds=10),
    "C4 C3 + character read": lambda s: fitlib.fit(traced(s), robust=True, rounds=10, rows=hm.prior_rows(reader(s))),
    "C5 C4 + a true profile (clicked points + traced contour)": lambda s: fitlib.fit(traced(s, profile=True), robust=True, rounds=10, rows=hm.prior_rows(reader(s))),
    "W1 front only": lambda s: fitlib.fit(ev(s, ["front"]), robust=True),
    "W2 front + 3/4": lambda s: fitlib.fit(ev(s, FT), robust=True),
    "W3 front + both 3/4": lambda s: fitlib.fit(ev(s, FT + ["tq2"]), robust=True),
    "W4 front + 3/4 + profile (clicked + contour)": lambda s: fitlib.fit(traced(s, contour=False, jaw=False, profile=True), robust=True, rounds=10),
    "W5 front + profile (clicked + contour)": lambda s: fitlib.fit(traced(s, contour=False, jaw=False, views=["front"], profile=True), robust=True, rounds=10),
    "W6 front + 3/4, both neutral & 85 mm known": None,
})
del METHODS["W6 front + 3/4, both neutral & 85 mm known"]

CLICK = [36, 39, 42, 45, 27, 30, 31, 33, 35, 48, 54, 51, 57, 62, 8, 17, 21, 22, 26, 68, 69]   # points a person can find


def clicked(s, noise, views=FT, with_det=False, ids=CLICK):
    out = list(ev(s, views)) if with_det else []
    for v in views:
        out.append(tb.ev_oracle(s, v, noise=noise, ids=ids, seed=21))
    return out


METHODS.update({
    "D1 21 clicked points +-1.5 mm, 2 views, MAP": lambda s: fitlib.fit(clicked(s, 1.5)),
    "D2 21 clicked points +-2.5 mm, 2 views, MAP": lambda s: fitlib.fit(clicked(s, 2.5)),
    "D3 detector + 21 clicked +-1.5": lambda s: fitlib.fit(clicked(s, 1.5, with_det=True), robust=True),
    "D4 D3 + character read": lambda s: fitlib.fit(clicked(s, 1.5, with_det=True), robust=True, rows=hm.prior_rows(reader(s))),
    "D5 D4 + clicked jaw line + profile picture": lambda s: fitlib.fit(clicked(s, 1.5, with_det=True) + [jaw_points(s, v) for v in FT] + traced(s, contour=False, jaw=False, views=[], profile=True), robust=True, rounds=10, rows=hm.prior_rows(reader(s))),
    "D6 D1 front only + read": lambda s: fitlib.fit(clicked(s, 1.5, views=["front"]), rows=hm.prior_rows(reader(s))),
})


def main():
    want = sys.argv[1:]
    res_f = rs.D / "out" / "table2.json"
    res = json.loads(res_f.read_text()) if res_f.exists() else {}
    subs = [subjects.load(n) for n in subjects.names()]
    for m, fn in METHODS.items():
        if want and not any(m.startswith(w) for w in want):
            continue
        t0 = time.time()
        res[m] = {}
        for s in subs:
            try:
                f = fn(s)
                sc = rs.score(rs.head(f["c"]), s["V"])
                sc["sigma"] = float(np.sqrt((np.asarray(f["c"]) ** 2).mean()))
                sc["expr"] = bool(s["e"] is not None)
                res[m][s["name"]] = sc
            except Exception as ex:  # noqa: BLE001
                print("FAILED", m, s["name"], repr(ex)[:300])
        res[m]["_time"] = (time.time() - t0) / max(len(subs), 1)
        res_f.write_text(json.dumps(res, indent=1))
        tb.show(res, [m])
    print()
    tb.show(res)
    for m in ("M0 detector points, MAP (= B3b)", "E1 M0 + expression solved per picture", "E2 same, expression prior x4"):
        if m in res:
            for tag, pick in (("pictures WITH an expression", True), ("neutral pictures", False)):
                rows = [v for k, v in res[m].items() if not k.startswith("_") and v.get("expr") == pick]
                if rows:
                    print(f"{m[:40]:40s} {tag:28s} " + rs.row({k: float(np.mean([x[k] for x in rows])) for k in rs.REGIONS}))


if __name__ == "__main__":
    main()
