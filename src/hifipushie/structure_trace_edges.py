"""TRACES SIT ON THE PICTURE'S EDGES (C353), for any garment: a traced edge (structure_outline, step 2) is checked against
the reference itself, as step 0's seen widths are (garment_fit_marks). t s2-3: a hussar's stepped cutaway notch was
traced as two straight diagonals across plain cloth; the agent judged its own look and passed it, and step 6 would
have held the build to the wrong shape.

CHECK: the trace is sampled every SAMPLE_PX along its course; at each sample the luminance profile square to the trace
(garment_fit_marks._profile, WINDOW px either side) must show a step of at least STEP (an edge). A
run of samples with none, longer than RUN_X windows, is refused BY POINTS ("points 2-4: 96 px with no edge within 10 px
of the line"). A run the picture can't show (dark on dark, a soft fold in shadow) is kept with the trace's `why`.
"""
from __future__ import annotations

import numpy as np

SAMPLE_PX = 3.0
RUN_X = 2.0  # (an off-edge run longer than this many windows: the line is not on an edge there; 2: both of t s2-3's
#              notch diagonals caught, none of the approved suit jacket's traces (s2-1, s2-2) flagged)
STEP = 10.0  # (luminance levels: half step 0's. A real edge of dark cloth on dark cloth (a lapel on its suit, t s2-2)
#              steps 11-14 levels; plain cloth beside it 0-7 (2 on the hussar's red))


def off_edge(image: str, points: list) -> list:
    """[(i0, i1, run px, window px)]: runs of the trace with no picture edge near it (point indices bounding each)."""
    from . import garment_fit_marks as gm
    a = gm.gray(image)
    W = gm.window(a.shape)
    P = np.asarray(points, float)
    samples = []  # (segment index, on an edge)
    for i in range(len(P) - 1):
        d = P[i + 1] - P[i]
        L = float(np.linalg.norm(d))
        if L < 1e-6:
            continue
        d = d / L
        n = np.array([-d[1], d[0]])
        for t in np.arange(SAMPLE_PX / 2, L, SAMPLE_PX):
            tt, prof = gm._profile(a, P[i] + t * d, n, W)
            k = 3
            step = max((abs(prof[j + 1:j + 1 + k].mean() - prof[j - k:j].mean()) for j in range(k, len(tt) - k)),
                       default=0.0)
            samples.append((i, step >= STEP))
    out, j = [], 0
    while j < len(samples):
        if samples[j][1]:
            j += 1
            continue
        k = j
        while k + 1 < len(samples) and not samples[k + 1][1]:
            k += 1
        run = (k - j + 1) * SAMPLE_PX
        if run > RUN_X * W:
            out.append((samples[j][0], samples[k][0] + 1, run, W))
        j = k + 1
    return out


def check(traces: list, views: list, bad: list):
    """Each trace on its view's picture: off-edge runs refused by name unless the trace says why."""
    for i, t in enumerate(traces or []):
        if not isinstance(t, dict) or str(t.get("why") or "").strip():
            continue
        vi = t.get("view", 0)
        img = (views[vi] if isinstance(vi, int) and 0 <= vi < len(views) else {}).get("image")
        pts = t.get("points")
        if not img or not isinstance(pts, list) or len(pts) < 2:
            continue
        try:
            runs = off_edge(img, pts)
        except (OSError, ValueError):
            continue  # (no picture to read: nothing to check against)
        for i0, i1, run, W in runs:
            bad.append(f"traces[{i}] {t.get('id', '')}: points {i0}-{i1}: {run:.0f} px of the line with no edge in the "
                       f"picture within {W} px: a traced line follows the edge it names (a notch's step, a curve) "
                       "point by point; add points where the picture's edge turns, or keep it with why (an edge the "
                       "picture can't show: dark on dark)")
