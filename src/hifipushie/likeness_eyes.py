"""The eye region read like with like: the same detector (MediaPipe's 478, likeness.detect) on the photo and on a
render through the photo's camera, measures in mm at the face's depth on the face's own axes (likeness.Side.frame:
ex across, ey DOWN the face).

`measures(P, mmpx)` -> {"<name>": [subject's right, left]} per eye; `table(rows)` prints photo / model rows;
`eye_box(P, ...)` the crop round both eyes and brows (pixels of P's picture).

Per eye: open (upper lid margin -> lower lid margin over the iris), width (corner to corner), aspect, iris_r (the
iris' radius from its four rim points), cover (how far the upper lid comes down over the iris' top, mm; + = covered),
cover_share (cover / iris diameter), white_below (lower lid under the iris' bottom: + = white shows under it),
brow_gap (the brow's LOWER edge over the pupil -> the upper lid margin: a low heavy brow close to the eye is small),
brow_height (pupil centre -> the brow's UPPER edge), brow_tilt (head -> tail, + = tail higher), canthal_tilt (inner ->
outer corner, + = outer higher). Brow points read paint (a render's brows are the skin's brow hairs).
"""
from __future__ import annotations

import numpy as np

# (subject's right, left): MediaPipe indices
EYES = {
    "upper": (159, 386), "lower": (145, 374), "inner": (133, 362), "outer": (33, 263),
    "iris": (468, 473), "rim": ((469, 470, 471, 472), (474, 475, 476, 477)),
    "brow_low": (52, 282), "brow_up": (105, 334), "brow_head": (107, 336), "brow_tail": (70, 300),
}
NAMES = ("open", "width", "aspect", "iris_r", "cover", "cover_share", "white_below", "brow_gap", "brow_height",
         "brow_tilt", "canthal_tilt")
TOL = {"open": 0.8, "width": 1.2, "aspect": 0.03, "iris_r": 0.4, "cover": 0.6, "cover_share": 0.06, "white_below": 0.5,
       "brow_gap": 1.2, "brow_height": 1.5, "brow_tilt": 3.0, "canthal_tilt": 1.5}


def frame(P) -> tuple:
    from .likeness import Side
    return Side(np.asarray(P, float), None, "detector").frame()


def measures(P, mmpx: float) -> dict:
    """Per-eye measures [right, left] (subject's) from 478 detector points in one picture's pixels."""
    P = np.asarray(P, float)
    ex, ey = frame(P)
    out = {k: [] for k in NAMES}
    for s in (0, 1):
        g = lambda k: P[EYES[k][s]]  # noqa: E731
        c = g("iris")
        r = float(np.mean([np.linalg.norm(P[i] - c) for i in EYES["rim"][s]]))
        up, lo = float(g("upper") @ ey), float(g("lower") @ ey)
        op = (lo - up) * mmpx
        wd = float(np.linalg.norm(g("outer") - g("inner"))) * mmpx
        out["open"].append(op)
        out["width"].append(wd)
        out["aspect"].append(op / max(wd, 1e-9))
        out["iris_r"].append(r * mmpx)
        cov = (up - (float(c @ ey) - r)) * mmpx
        out["cover"].append(cov)
        out["cover_share"].append(cov / max(2 * r * mmpx, 1e-9))
        out["white_below"].append((lo - (float(c @ ey) + r)) * mmpx)
        out["brow_gap"].append((up - float(g("brow_low") @ ey)) * mmpx)
        out["brow_height"].append((float(c @ ey) - float(g("brow_up") @ ey)) * mmpx)
        for name, a, b in (("brow_tilt", "brow_head", "brow_tail"), ("canthal_tilt", "inner", "outer")):
            d = g(b) - g(a)
            out[name].append(float(np.degrees(np.arctan2(-(d @ ey), abs(d @ ex)))))
    return {k: [round(float(v), 3) for v in vs] for k, vs in out.items()}


def table(rows: dict, ref: str = "photo") -> str:
    """rows = {"photo": measures, "start": measures, ...}: one line per measure, both eyes' mean, and the miss of
    each column against `ref` in tolerances."""
    cols = list(rows)
    lines = [f"{'':13s}" + "".join(f"{c:>16s}" for c in cols)]
    for k in NAMES:
        s = f"{k:13s}"
        r0 = float(np.mean(rows[ref][k]))
        for c in cols:
            v = float(np.mean(rows[c][k]))
            s += f"{v:9.2f}" + (f" ({(v - r0) / TOL[k]:+4.1f})" if c != ref else " " * 7)
        lines.append(s)
    return "\n".join(lines)


def eye_box(P, aspect: float = 2.6, pad: float = 0.35) -> tuple:
    """(x0, y0, x1, y1) round both eyes and both brows (points of one picture), widened to `aspect`."""
    P = np.asarray(P, float)
    idx = [i for v in EYES.values() for t in (v if isinstance(v[0], tuple) else (v,)) for i in t]
    idx += [70, 300, 46, 276, 230, 450]  # brow tails' ends, the under-eye
    Q = P[idx]
    lo, hi = Q.min(0), Q.max(0)
    w = (hi[0] - lo[0]) * (1 + pad)
    h = max(hi[1] - lo[1] + w * 0.12, w / aspect)
    cx, cy = (lo + hi) / 2
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
