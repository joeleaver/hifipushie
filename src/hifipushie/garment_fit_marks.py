"""Step 0's fit marks measured on the picture itself (garment_fit.py), for any garment: a SEEN edge is where the
picture's edge is, not where the mark was dropped (t s0-2: a garment's edges marked 12 px wide of a crisp edge),
and the landmarks a height hangs on, with how far each height moves when one is wrong.

EDGES: each end of a seen width (garment or body) is moved to the picture's edge across the mark, within WINDOW of it:
the strongest luminance step there (averaged over a few rows square to the mark). It stays where it was marked when
there is no clear step (STEP levels) or two near-equal ones (legs touching, a shadow): said so in the answer.
LANDMARKS: v | [u, v] | [[u, v], [u, v]] (both sides: their mean row) | {at: one of those, from: "seen" | how it was
inferred (a covered landmark)}. SENSITIVITY: a height's mm per 10 px of each landmark it was read between.
"""
from __future__ import annotations

import numpy as np

STEP = 20.0  # (luminance levels, 0-255: the least step that counts as an edge)
TIE = 0.8  # (a second step this strong, elsewhere in the window: ambiguous, the mark stays)
_IMG: dict = {}


def window(shape) -> int:
    return max(6, round(0.012 * max(shape)))


def gray(path: str):
    import os
    from PIL import Image
    key = (path, os.path.getmtime(path))
    if key not in _IMG:
        _IMG.clear()
        _IMG[key] = np.asarray(Image.open(path).convert("L"), float)
    return _IMG[key]


def _profile(a, p, d, W):
    """Luminance along d through p, t = -W..W, averaged over 5 px square to d (nearest pixel)."""
    n = np.array([-d[1], d[0]])
    t = np.arange(-W, W + 1)
    prof = np.zeros(len(t))
    for o in range(-2, 3):
        q = p[None, :] + t[:, None] * d[None, :] + o * n[None, :]
        u = np.clip(np.round(q[:, 0]).astype(int), 0, a.shape[1] - 1)
        v = np.clip(np.round(q[:, 1]).astype(int), 0, a.shape[0] - 1)
        prof += a[v, u]
    return t, prof / 5


def snap(a, p, d, W):
    """(the edge nearest-strongest within W of p along d, px moved, why-not or None)."""
    p, d = np.asarray(p, float), np.asarray(d, float)
    t, prof = _profile(a, p, d, W)
    k = 3
    step = np.zeros(len(t))
    for i in range(k, len(t) - k):  # (the step across i: mean of k px after less k px before)
        step[i] = abs(prof[i + 1:i + 1 + k].mean() - prof[i - k:i].mean())
    if step.max() < STEP:
        return p, 0.0, "no clear edge within %d px" % W
    peaks = [i for i in range(1, len(t) - 1) if step[i] >= STEP and step[i] >= step[i - 1] and step[i] >= step[i + 1]]
    best = max(peaks, key=lambda i: step[i])
    rivals = [i for i in peaks if abs(i - best) > 3 and step[i] >= TIE * step[best]]
    if rivals:
        return p, 0.0, "two edges within %d px (%+d, %+d): kept as marked" % (W, t[best], t[rivals[0]])
    q = p + (t[best] + 0.5) * d
    return q, float(abs(t[best] + 0.5)), None


def measure(image: str, pair):
    """A seen width's two ends moved to the picture's edges: (pair, [moved px, moved px], notes)."""
    try:
        a = gray(image)
    except OSError:
        return pair, [0.0, 0.0], ["picture not readable: kept as marked"]
    P = np.asarray(pair, float)
    d = P[1] - P[0]
    d = d / (np.linalg.norm(d) or 1.0)
    W = window(a.shape)
    out, moved, notes = [], [], []
    for i, p in enumerate(P):
        q, m, why = snap(a, p, d, W)
        out.append([round(float(q[0]), 1), round(float(q[1]), 1)])
        moved.append(round(m, 1))
        if why:
            notes.append(f"{'first' if i == 0 else 'second'} end: {why}")
    return out, moved, notes


def landmark(x):
    """(v, from) of a landmark mark, or None when the form is wrong."""
    def uv(y):
        if isinstance(y, (int, float)) and not isinstance(y, bool):
            return float(y)
        if isinstance(y, (list, tuple)) and len(y) == 2 and all(isinstance(c, (int, float)) for c in y):
            return float(y[1])
        if isinstance(y, (list, tuple)) and y and all(isinstance(c, (list, tuple)) for c in y):
            vs = [uv(c) for c in y]
            return None if None in vs else float(np.mean(vs))
        return None
    if isinstance(x, dict):
        v, fr = uv(x.get("at")), str(x.get("from") or "").strip()
        return None if v is None or not fr else (v, fr)
    v = uv(x)
    return None if v is None else (v, "seen")


def sensitivity(v, va, vb, za, zb):
    """mm a height moves per 10 px of landmark a and of landmark b (read at v between them)."""
    den = (vb - va) ** 2 or 1.0
    return round(abs((zb - za) * (v - vb) / den) * 10, 1), round(abs((zb - za) * (v - va) / den) * 10, 1)
