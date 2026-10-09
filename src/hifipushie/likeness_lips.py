"""The lips read like with like (likeness_eyes' counterpart): MediaPipe's 478 on the photo and on a render through
the photo's camera, mm at the face's depth on the face's axes (ey DOWN the face).

bow_width (the Cupid's bow peaks 37 / 267 apart), bow_depth (the peaks above the bow's dip 0: the V's depth),
bow_angle (the V's opening at the dip, deg: deep narrow V small), tubercle (the upper lip's lower edge at the middle
(13) below the line through its sides (82 / 312): + = the tubercle bulges down), upper (0 -> 13), lower (14 -> 17),
width (61 -> 291), corner_tilt (corners above the seam: + = up). The photo's mouth is ~45 px wide (~1.3 mm a pixel):
read bow_depth and tubercle as +-1 px.
"""
from __future__ import annotations

import numpy as np

NAMES = ("bow_width", "bow_depth", "bow_angle", "tubercle", "upper", "lower", "width", "corner_tilt")
TOL = {"bow_width": 1.2, "bow_depth": 0.6, "bow_angle": 12.0, "tubercle": 0.5, "upper": 1.0, "lower": 1.0, "width": 1.5,
       "corner_tilt": 2.5}


def measures(P, mmpx: float) -> dict:
    from .likeness_eyes import frame
    P = np.asarray(P, float)
    ex, ey = frame(P)
    y = lambda i: float(P[i] @ ey)  # noqa: E731
    out = {}
    out["bow_width"] = abs(float((P[267] - P[37]) @ ex)) * mmpx
    out["bow_depth"] = (y(0) - 0.5 * (y(37) + y(267))) * mmpx
    u, v = P[37] - P[0], P[267] - P[0]
    out["bow_angle"] = float(np.degrees(np.arccos(np.clip(u @ v / (np.linalg.norm(u) * np.linalg.norm(v)), -1, 1))))
    a, b, m = P[82], P[312], P[13]
    t = float((m - a) @ ex) / max(float((b - a) @ ex), 1e-9)
    out["tubercle"] = (float(m @ ey) - float((a + t * (b - a)) @ ey)) * mmpx
    out["upper"] = (y(13) - y(0)) * mmpx
    out["lower"] = (y(17) - y(14)) * mmpx
    out["width"] = float(np.linalg.norm(P[291] - P[61])) * mmpx
    seam = 0.5 * (y(13) + y(14))
    out["corner_tilt"] = float(np.degrees(np.arctan2(seam - 0.5 * (y(61) + y(291)), 0.5 * out["width"] / mmpx)))
    return {k: [round(float(out[k]), 3)] for k in NAMES}


def table(rows: dict, ref: str = "photo") -> str:
    cols = list(rows)
    lines = [f"{'':13s}" + "".join(f"{c:>16s}" for c in cols)]
    for k in NAMES:
        r0 = float(np.mean(rows[ref][k]))
        s = f"{k:13s}"
        for c in cols:
            v = float(np.mean(rows[c][k]))
            s += f"{v:9.2f}" + (f" ({(v - r0) / TOL[k]:+4.1f})" if c != ref else " " * 7)
        lines.append(s)
    return "\n".join(lines)


def lip_box(P, aspect: float = 1.8, pad: float = 0.6) -> tuple:
    """(x0, y0, x1, y1) round the mouth, the philtrum and the chin's top."""
    P = np.asarray(P, float)
    Q = P[[61, 291, 0, 17, 2, 164, 18]]
    lo, hi = Q.min(0), Q.max(0)
    w = (hi[0] - lo[0]) * (1 + pad)
    h = max(hi[1] - lo[1], w / aspect)
    cx, cy = (lo + hi) / 2
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
