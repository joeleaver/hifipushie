"""widths.py: does the front picture's OUTLINE AT A FEW LEVELS (face width at the nose base / mouth / jaw, the neck
under the jaw: clean edges against the background) cut jaw / cheek error on the truth set? The outline as short runs
of edge pixels at each level, both sides, as evidence beside the detector's points (fitlib's outline rows: along
the edge's normal, against the model's own silhouette vertices), with an honest sigma. The lens stays unknown
(prior 70 mm +-40%): the full outline was harmful there (study round 1); a few levels low on the face are tried here.
  run.sh widths.py"""
import json
import os

import numpy as np
from scipy import ndimage

import exp2
import fitlib
import rs
import subjects
import table as tb
from hifipushie import humanmacro as hm

D2 = os.environ.get("D2", "/mnt/data/hifipushie/refstudy2")
FACE = (0.50, 0.65, 0.80, 0.92)     # levels: 0 = the eye line, 1 = the chin's bottom (detector 152)
NECK = (1.22,)


def runs(sub, view="front", levels=FACE + NECK, half=5):
    """Edge pixels of the head's mask at the levels (each a run of 2 x half + 1 rows), left and right."""
    d = tb.det(sub["name"], view)
    zb = np.load(subjects.OUT / f"{sub['name']}_{view}_zb.npy")
    m = np.isfinite(zb)
    P = d["P"][:, :2]
    eye_y = 0.5 * (P[468, 1] + P[473, 1])
    chin_y = P[152, 1]
    out = []
    for lv in levels:
        y0 = int(round(eye_y + lv * (chin_y - eye_y)))
        for y in range(y0 - half, y0 + half + 1):
            if 0 <= y < m.shape[0] and m[y].any():
                xs = np.flatnonzero(m[y])
                out += [(xs.min() + 0.5, y + 0.5), (xs.max() + 0.5, y + 0.5)]
    return np.array(out)


def ev(s, levels, sig_o, views=("front",)):
    e = exp2.ev(s, list(views))
    e[0] = {**e[0], "outline": runs(s, "front", levels), "sig_o": sig_o}
    return e


F = dict(robust=True, rounds=10, f_prior=None)
METHODS = {
    "W0 front, detector MAP": lambda s: fitlib.fit(exp2.ev(s, ["front"]), robust=True),
    "W1 + face widths at 4 levels (sigma 1.5 mm)": lambda s: fitlib.fit(ev(s, FACE, 1.5), **F),
    "W2 + face widths + neck (1.5 mm)": lambda s: fitlib.fit(ev(s, FACE + NECK, 1.5), **F),
    "W3 + face widths + neck (3 mm)": lambda s: fitlib.fit(ev(s, FACE + NECK, 3.0), **F),
    "W4 + jaw levels only 0.8 / 0.92 + neck (1.5 mm)": lambda s: fitlib.fit(ev(s, (0.80, 0.92) + NECK, 1.5), **F),
    "W5 W0 + said read": lambda s: fitlib.fit(exp2.ev(s, ["front"]), robust=True, rows=hm.prior_rows(exp2.reader(s))),
    "W6 W2 + said read": lambda s: fitlib.fit(ev(s, FACE + NECK, 1.5), rows=hm.prior_rows(exp2.reader(s)), **F),
    "W7 W2 + read of SHAPE words only (no widths, no neck)": lambda s: fitlib.fit(ev(s, FACE + NECK, 1.5), rows=hm.prior_rows(exp2.reader(s, only=[
        k for k in exp2.READABLE if k not in ("face_width", "cheekbone_width", "jaw_width", "neck_width", "cheek_fullness")])), **F),
    "W8 W0 + read of SHAPE words only": lambda s: fitlib.fit(exp2.ev(s, ["front"]), robust=True, rows=hm.prior_rows(exp2.reader(s, only=[
        k for k in exp2.READABLE if k not in ("face_width", "cheekbone_width", "jaw_width", "neck_width", "cheek_fullness")]))),
}

if __name__ == "__main__":
    subs = [subjects.load(n) for n in subjects.names()]
    res = {}
    WM = ("jaw_width", "face_width", "cheekbone_width", "neck_width", "jaw_square", "cheek_fullness")
    for m, fn in METHODS.items():
        res[m] = {}
        err = []
        for s in subs:
            f = fn(s)
            sc = rs.score(rs.head(f["c"]), s["V"])
            sc["sigma"] = float(np.sqrt((np.asarray(f["c"]) ** 2).mean()))
            res[m][s["name"]] = sc
            zt, zf = hm.read(V=s["V"]), hm.read(f["c"])
            err.append([zf[k] - zt[k] for k in WM])
        tb.show(res, [m])
        e = np.sqrt((np.array(err) ** 2).mean(0))
        print("      macro error (sigma): " + "  ".join(f"{k} {v:.2f}" for k, v in zip(WM, e)))
    json.dump(res, open(f"{D2}/widths_table.json", "w"), indent=1)
